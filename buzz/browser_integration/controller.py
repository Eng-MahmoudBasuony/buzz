"""Consume browser jobs on Qt's GUI thread, through the normal Buzz queue."""
import logging
import os
import fcntl
import weakref
from uuid import UUID

from PyQt6.QtCore import QObject, QTimer

from buzz.browser_integration.protocol import Store, VIDEO_ID, read_json, bridge_root

log = logging.getLogger(__name__)


def create_task(url, uid, settings):
    from platformdirs import user_documents_dir
    from pathlib import Path
    from buzz.model_loader import ModelType
    from buzz.store.keyring_store import get_password, Key
    from buzz.transcriber.transcriber import (
        TranscriptionOptions, FileTranscriptionOptions, FileTranscriptionTask, OutputFormat, Task,
    )
    from buzz.widgets.preferences_dialog.models.file_transcription_preferences import FileTranscriptionPreferences

    settings.settings.beginGroup("file_transcriber")
    try:
        preferences = FileTranscriptionPreferences.load(settings.settings)
    finally:
        settings.settings.endGroup()
    model = preferences.model
    token = ""
    if model.model_type == ModelType.OPEN_AI_WHISPER_API:
        token = get_password(Key.OPENAI_API_KEY)
        if not token:
            raise ValueError("احفظ مفتاح API في إعدادات Buzz أولًا.")
        model_path = ""
    else:
        model_path = model.get_local_model_path()
        if not model_path:
            raise ValueError("نزّل النموذج المحلي من Buzz أولًا.")
    output = Path(user_documents_dir()) / "Buzz Transcripts"
    output.mkdir(parents=True, exist_ok=True)
    return FileTranscriptionTask(
        uid=UUID(uid), url=url, source=FileTranscriptionTask.Source.URL_IMPORT,
        model_path=model_path, output_directory=str(output),
        transcription_options=TranscriptionOptions(
            model=model, task=Task.TRANSCRIBE, language=preferences.language,
            initial_prompt=preferences.initial_prompt, openai_access_token=token,
        ),
        file_transcription_options=FileTranscriptionOptions(url=url, output_formats={OutputFormat.TXT}),
    )


class BrowserController(QObject):
    def __init__(self, window, settings, root=None, task_factory=create_task, start_timer=True):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.store = Store(root)
        self.task_factory = task_factory
        self.busy = False
        self.controller_fd = os.open(self.store.root / ".controller.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.controller_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.controller_fd)
            self.controller_fd = None
            return
        self._release_lock = weakref.finalize(self, os.close, self.controller_fd)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        if start_timer:
            self.timer.start()

    def close(self):
        if self.controller_fd is not None:
            self.timer.stop()
            self._release_lock()
            self.controller_fd = None

    def poll(self):
        if self.busy or self.controller_fd is None:
            return
        self.busy = True
        try:
            for path in self.store.root.glob("*.json"):
                if VIDEO_ID.fullmatch(path.stem):
                    try:
                        self.process(path.stem)
                    except Exception:
                        log.exception("Browser bridge could not process a local job")
        finally:
            self.busy = False

    def process(self, video):
        from uuid import uuid4
        from buzz.transcriber.cloud_transcription import STAGES
        from buzz.locale import localize_transcription_message
        with self.store.locked():
            job = self.store.read(video)
            if job["state"] == "waiting":
                existing = self.window.transcription_service.find_completed_transcription_by_url(job["url"])
                # Reuse a saved result even on the first browser click.
                # Otherwise persist identity before enqueueing: a crash never
                # silently resubmits a possibly paid request.
                job.update(state="completed" if existing else "submitting",
                           task_uid=str(existing or uuid4()))
                self.store.save(job)
                submit = not bool(existing)
            else:
                submit = False
        if submit:
            try:
                task = self.task_factory(job["url"], job["task_uid"], self.settings)
                self.window.add_task(task)
                self.update(video, state="queued", message="")
            except Exception:
                log.error("Could not enqueue browser transcription; check Buzz model and credential settings")
                self.update(video, state="failed", message="تعذّر بدء التفريغ. تحقّق من إعدادات النموذج ومفتاح API في Buzz.")
            return
        uid = job.get("task_uid")
        if job["state"] in {"failed", "canceled", "missing"}:
            return
        if job["state"] in {"completed", "skipped"} and not job.get("open_requested"):
            return
        if not uid:
            return
        transcription = self.window.transcription_service.get_transcription(UUID(uid))
        if transcription is None:
            self.update(video, state="missing", message="المهمة غير موجودة في Buzz. اختر «إعادة المحاولة» لبدء مهمة جديدة.")
            return
        status = transcription.status
        values = {"state": status, "progress": max(0.0, min(float(transcription.progress or 0), 1.0)),
                  "stage": localize_transcription_message(STAGES.get(uid, ""))}
        if status in {"failed", "canceled"}:
            values["message"] = "توقفت المهمة. راجع التفاصيل في Buzz قبل إعادة المحاولة."
        with self.store.locked():
            latest = self.store.read(video)
            open_result = status in {"completed", "skipped"} and latest.get("open_requested") is True
            latest.update(values)
            if open_result:
                latest["open_requested"] = False
            self.store.save(latest)
        if open_result:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
            self.window.open_transcription_viewer(transcription)

    def update(self, video, **values):
        with self.store.locked():
            job = self.store.read(video)
            job.update(values)
            self.store.save(job)


def start_if_enabled(window, settings):
    path = bridge_root() / "enabled.json"
    if not path.exists():
        return None
    try:
        config = read_json(path)
        if config.get("enabled") is True:
            return BrowserController(window, settings)
    except Exception:
        log.exception("Browser integration is unavailable")
    return None
