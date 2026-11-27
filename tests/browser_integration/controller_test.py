from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4, UUID

import pytest
from PyQt6.QtWidgets import QWidget

from buzz.browser_integration.controller import BrowserController, create_task

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def bridge(qtbot, tmp_path):
    window = QWidget()
    qtbot.addWidget(window)
    window.transcription_service = Mock()
    window.transcription_service.find_completed_transcription_by_url.return_value = None
    window.add_task = Mock()
    window.open_transcription_viewer = Mock()
    record = SimpleNamespace(status="queued", progress=0)
    window.transcription_service.get_transcription.return_value = record
    factory = Mock(side_effect=lambda url, uid, settings: SimpleNamespace(uid=UUID(uid), url=url))
    controller = BrowserController(window, Mock(), tmp_path, factory, start_timer=False)
    yield window, controller, factory, record
    controller.close()


def test_click_polling_and_repeated_click_do_not_submit_twice(bridge):
    window, controller, factory, record = bridge
    controller.store.start(URL)
    controller.poll()
    controller.poll()
    controller.store.start(URL + "&t=100")
    controller.poll()
    assert factory.call_count == window.add_task.call_count == 1


def test_result_opens_only_after_database_completion(bridge):
    window, controller, factory, record = bridge
    controller.store.start(URL)
    controller.poll()
    record.status = "in_progress"
    controller.poll()
    window.open_transcription_viewer.assert_not_called()
    record.status, record.progress = "completed", 1
    controller.poll()
    controller.poll()
    window.open_transcription_viewer.assert_called_once_with(record)
    controller.store.start(URL)
    controller.poll()
    assert window.open_transcription_viewer.call_count == 2
    assert window.add_task.call_count == 1


def test_crash_after_claim_never_silently_resubmits(bridge):
    window, controller, factory, record = bridge
    job = controller.store.start(URL)
    job.update(state="submitting", task_uid=str(uuid4()))
    controller.store.save(job)
    window.transcription_service.get_transcription.return_value = None
    controller.poll()
    assert controller.store.read("abcdefghijk")["state"] == "missing"
    window.add_task.assert_not_called()
    factory.assert_not_called()


def test_factory_failure_is_terminal_and_does_not_expose_exception(bridge):
    window, controller, factory, record = bridge
    factory.side_effect = ValueError("fixture-private-value")
    controller.store.start(URL)
    controller.poll()
    controller.poll()
    assert controller.store.read("abcdefghijk")["state"] == "failed"
    assert "fixture-private-value" not in controller.store.path("abcdefghijk").read_text()
    assert factory.call_count == 1


def test_controller_has_single_owner(bridge):
    window, controller, factory, record = bridge
    second = BrowserController(window, Mock(), controller.store.root, factory, start_timer=False)
    assert second.controller_fd is None
    controller.store.start(URL)
    second.poll()
    factory.assert_not_called()


def test_first_browser_click_reuses_a_completed_buzz_result(bridge):
    window, controller, factory, record = bridge
    uid = uuid4()
    window.transcription_service.find_completed_transcription_by_url.return_value = str(uid)
    record.status, record.progress = "completed", 1
    controller.store.start(URL)
    controller.poll()
    assert controller.store.read("abcdefghijk")["task_uid"] == str(uid)
    window.open_transcription_viewer.assert_called_once_with(record)
    window.add_task.assert_not_called()
    factory.assert_not_called()


def test_task_uses_saved_language_and_local_key_not_browser_input(tmp_path, monkeypatch):
    from buzz.model_loader import TranscriptionModel, ModelType
    from buzz.transcriber.transcriber import Task, OutputFormat
    from buzz.store import keyring_store
    from buzz.widgets.preferences_dialog.models.file_transcription_preferences import FileTranscriptionPreferences
    preferences = SimpleNamespace(model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API),
                                  language="ar", initial_prompt="برمجة")
    monkeypatch.setattr(FileTranscriptionPreferences, "load", lambda settings: preferences)
    getter = Mock(return_value="fixture-api-key")
    monkeypatch.setattr(keyring_store, "get_password", getter)
    monkeypatch.setattr('platformdirs.user_documents_dir', lambda: str(tmp_path))
    uid = str(uuid4())
    task = create_task(URL, uid, Mock())
    assert task.uid == UUID(uid)
    assert task.transcription_options.task == Task.TRANSCRIBE
    assert task.transcription_options.language == "ar"
    assert task.transcription_options.openai_access_token == "fixture-api-key"
    assert task.file_transcription_options.output_formats == {OutputFormat.TXT}
    assert task.output_directory == str(tmp_path / "Buzz Transcripts")
    assert getter.call_count == 1


def test_missing_api_key_is_not_automatically_replaced_or_retried(monkeypatch):
    from buzz.model_loader import TranscriptionModel, ModelType
    from buzz.store import keyring_store
    from buzz.widgets.preferences_dialog.models.file_transcription_preferences import FileTranscriptionPreferences
    preferences = SimpleNamespace(model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API))
    monkeypatch.setattr(FileTranscriptionPreferences, "load", lambda settings: preferences)
    monkeypatch.setattr(keyring_store, "get_password", lambda key: None)
    with pytest.raises(ValueError):
        create_task(URL, str(uuid4()), Mock())
