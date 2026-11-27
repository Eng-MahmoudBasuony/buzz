import os
import logging
from typing import Tuple, List, Optional, Set
from uuid import UUID

from PyQt6 import QtGui, sip
from PyQt6.QtCore import (
    Qt,
    QThread,
    QThreadPool,
    QModelIndex,
    pyqtSignal,
    pyqtSlot,
)

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QFileDialog,
)

from buzz.db.entity.transcription import Transcription
from buzz.db.service.transcription_service import TranscriptionService
from buzz.file_transcriber_queue_worker import FileTranscriberQueueWorker
from buzz.locale import _
from buzz.paths import resolve_document_portal_path
from buzz.plugins.manager import PluginManager
from buzz.plugins.post_processing import FnRunnable
from buzz.settings.settings import APP_NAME, Settings
from buzz.sleep_inhibitor import SleepInhibitor
from buzz.update_checker import UpdateChecker, UpdateInfo
from buzz.widgets.update_dialog import UpdateDialog
from buzz.settings.shortcuts import Shortcuts
from buzz.store.keyring_store import set_password, Key
from buzz.transcriber.transcriber import (
    FileTranscriptionTask,
    TranscriptionOptions,
    FileTranscriptionOptions,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_EXTENSIONS,
    Segment,
)
from buzz.widgets.icon import BUZZ_ICON_PATH
from buzz.widgets.import_url_dialog import ImportURLDialog
from buzz.widgets.main_window_toolbar import MainWindowToolbar
from buzz.widgets.menu_bar import MenuBar
from buzz.widgets.system_tray import SystemTray
from buzz.widgets.preferences_dialog.models.preferences import Preferences
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcriber.speaker_identification_options_widget import (
    SpeakerIdentificationOptions,
)
from buzz.widgets.transcription_task_folder_watcher import (
    TranscriptionTaskFolderWatcher,
)
from buzz.widgets.transcription_tasks_table_widget import (
    TranscriptionTasksTableWidget,
)
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)


def find_media_files_in_folder(folder: str) -> List[str]:
    file_paths = []
    for dirpath, _dirs, filenames in os.walk(folder):
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() in SUPPORTED_EXTENSIONS:
                file_paths.append(os.path.join(dirpath, filename))
    return file_paths


class MainWindow(QMainWindow):
    table_widget: TranscriptionTasksTableWidget
    transcriptions_updated = pyqtSignal(UUID)

    def __init__(self, transcription_service: TranscriptionService):
        super().__init__(flags=Qt.WindowType.Window)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(BUZZ_ICON_PATH))

        self.setAcceptDrops(True)

        self.settings = Settings()
        self.sleep_inhibitor = SleepInhibitor(
            enabled=self.settings.value(
                Settings.Key.PREVENT_SLEEP_WHILE_TRANSCRIBING,
                True,
            )
        )

        self.shortcuts = Shortcuts(settings=self.settings)

        self.quit_on_complete = False
        # Set when the window closes, plugin hooks then run synchronously
        self._quitting = False
        self.pending_quit_task_uids: Set[UUID] = set()
        self.transcription_service = transcription_service

        self.plugin_manager = PluginManager(self.transcription_service, self.settings)
        try:
            self.plugin_manager.initialize()
        except Exception as exc:
            logging.error(f"Failed to initialize plugins: {exc}", exc_info=True)

        #update checker
        self._update_info: Optional[UpdateInfo] = None

        self.toolbar = MainWindowToolbar(shortcuts=self.shortcuts, parent=self)
        self.toolbar.new_transcription_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.toolbar.new_url_transcription_action_triggered.connect(
            self.on_new_url_transcription_action_triggered
        )
        self.toolbar.open_transcript_action_triggered.connect(
            self.open_transcript_viewer
        )
        self.toolbar.clear_history_action_triggered.connect(
            self.on_clear_history_action_triggered
        )
        self.toolbar.stop_transcription_action_triggered.connect(
            self.on_stop_transcription_action_triggered
        )
        self.addToolBar(self.toolbar)
        self.toolbar.update_action_triggered.connect(self.on_update_action_triggered)
        self.setUnifiedTitleAndToolBarOnMac(True)

        self.preferences = self.load_preferences(settings=self.settings)
        self.menu_bar = MenuBar(
            shortcuts=self.shortcuts,
            preferences=self.preferences,
            plugin_manager=self.plugin_manager,
            parent=self,
        )
        self.menu_bar.import_action_triggered.connect(
            self.on_new_transcription_action_triggered
        )
        self.menu_bar.import_url_action_triggered.connect(
            self.on_new_url_transcription_action_triggered
        )
        self.menu_bar.import_folder_action_triggered.connect(
            self.on_import_folder_action_triggered
        )
        self.menu_bar.shortcuts_changed.connect(self.on_shortcuts_changed)
        self.menu_bar.openai_api_key_changed.connect(
            self.on_openai_access_token_changed
        )
        self.menu_bar.preferences_changed.connect(self.on_preferences_changed)
        self.setMenuBar(self.menu_bar)

        self.table_widget = TranscriptionTasksTableWidget(self)
        self.table_widget.transcription_service = self.transcription_service
        self.table_widget.doubleClicked.connect(self.on_table_double_clicked)
        self.table_widget.return_clicked.connect(self.open_transcript_viewer)
        self.table_widget.delete_requested.connect(self.on_clear_history_action_triggered)
        self.table_widget.selectionModel().selectionChanged.connect(
            self.on_table_selection_changed
        )
        self.transcriptions_updated.connect(
            self.on_transcriptions_updated
        )

        self.setCentralWidget(self.table_widget)

        # Start transcriber thread
        self.transcriber_thread = QThread()

        self.transcriber_worker = FileTranscriberQueueWorker()
        self.transcriber_worker.plugin_manager = self.plugin_manager
        self.transcriber_worker.moveToThread(self.transcriber_thread)

        self.transcriber_worker.task_started.connect(self.on_task_started)
        self.transcriber_worker.task_progress.connect(self.on_task_progress)
        self.transcriber_worker.task_download_progress.connect(
            self.on_task_download_progress
        )
        self.transcriber_worker.task_error.connect(self.on_task_error)
        self.transcriber_worker.task_completed.connect(self.on_task_completed)
        self.transcriber_worker.queue_busy_changed.connect(
            self.on_queue_busy_changed,
            Qt.ConnectionType.QueuedConnection,
        )

        self.transcriber_worker.completed.connect(self.transcriber_thread.quit)

        self.transcriber_thread.started.connect(self.transcriber_worker.run)

        self.transcriber_thread.start()

        self.load_geometry()

        self.folder_watcher = TranscriptionTaskFolderWatcher(
            tasks={},
            preferences=self.preferences.folder_watch,
        )
        self.folder_watcher.task_found.connect(self.on_folder_watch_task_found)
        self.folder_watcher.task_settled.connect(self.on_folder_watch_task_settled)
        self.folder_watcher.task_discarded.connect(
            self.on_folder_watch_task_discarded
        )
        self.folder_watcher.find_tasks()

        self.transcription_viewer_widget = None

        #Initialize and run update checker
        self._init_update_checker()

        #Offer CUDA installation on Windows if not done before
        self._maybe_show_cuda_prompt()

        self.system_tray = SystemTray(self, self.settings)
        # Quit through the tray controller so close-to-tray does not just hide the window.
        self.menu_bar.quit_action_triggered.connect(lambda: self.system_tray.quit())

    def on_preferences_changed(self, preferences: Preferences):
        self.preferences = preferences
        self.save_preferences(preferences)
        self.system_tray.update_preferences()
        self.sleep_inhibitor.set_enabled(
            self.settings.value(
                Settings.Key.PREVENT_SLEEP_WHILE_TRANSCRIBING,
                True,
            )
        )
        self.folder_watcher.set_preferences(preferences.folder_watch)
        self.folder_watcher.find_tasks()

    @pyqtSlot(bool)
    def on_queue_busy_changed(self, busy: bool):
        self.sleep_inhibitor.set_busy(busy)

    def save_preferences(self, preferences: Preferences):
        self.settings.settings.beginGroup("preferences")
        preferences.save(self.settings.settings)
        self.settings.settings.endGroup()

    def load_preferences(self, settings: Settings):
        settings.settings.beginGroup("preferences")
        preferences = Preferences.load(settings.settings)
        settings.settings.endGroup()
        return preferences

    def dragEnterEvent(self, event):
        # Accept file drag events
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        file_paths = []
        for url in event.mimeData().urls():
            path = resolve_document_portal_path(url.toLocalFile())
            if os.path.isdir(path):
                file_paths.extend(find_media_files_in_folder(path))
            elif path:
                file_paths.append(path)

        if le…12696 tokens truncated… model loads rows lazily, so a row may not be fetched yet
                if not model.canFetchMore():
                    break
                model.fetchMore()
                continue
            row_id = model.record(row).value("id")
            if row_id in remaining_ids:
                remaining_ids.discard(row_id)
                removed_ids.append(row_id)
                # Removed rows stay in the model until submitAll()
                model.removeRow(row)
            row += 1
        if model.submitAll():
            for id in removed_ids:
                metadata_cache.delete_metadata(id)

    def transcription(self, index: QModelIndex) -> Transcription:
        return Transcription.from_record(self.model().record(index.row()))

    def refresh_all(self):
        self.model().select()

    def refresh_row(self, id: UUID):
        for i in range(self.model().rowCount()):
            record = self.model().record(i)
            if record.value("id") == str(id):
                self.model().selectRow(i)
                return

    @staticmethod
    def format_timedelta(delta: timedelta):
        mm, ss = divmod(delta.seconds, 60)
        result = f"{ss}s"
        if mm == 0:
            return result
        hh, mm = divmod(mm, 60)
        result = f"{mm}m {result}"
        if hh == 0:
            return result
        return f"{hh}h {result}"

    def on_rename_action(self):
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get the first selected transcription
        transcription = self.transcription(selected_rows[0])
        
        # Get current name or fallback to file name
        current_name = transcription.name or (
            transcription.url if transcription.url 
            else os.path.basename(transcription.file) if transcription.file 
            else ""
        )
        
        # Show input dialog
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, 
            _("Rename Transcription"), 
            _("Enter new name:"), 
            text=current_name
        )
        
        if ok and new_name.strip():
            # Update the transcription name
            from uuid import UUID
            self.transcription_service.update_transcription_name(
                UUID(transcription.id), 
                new_name.strip()
            )
            self.refresh_all()

    def on_notes_action(self):
        selected_rows = self.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        # Get the first selected transcription
        transcription = self.transcription(selected_rows[0])
        
        # Show input dialog for notes
        from PyQt6.QtWidgets import QInputDialog
        current_notes = transcription.notes or ""
        new_notes, ok = QInputDialog.getMultiLineText(
            self, 
            _("Notes"),
            _("Enter some relevant notes for this transcription:"),
            text=current_notes
        )
        
        if ok:
            # Update the transcription notes
            from uuid import UUID
            self.transcription_service.update_transcription_notes(
                UUID(transcription.id), 
                new_notes
            )
            self.refresh_all()

    def on_restart_transcription_action(self):
        """Restart the selected failed, canceled or skipped transcriptions"""
        selected = self.selected_transcriptions()
        if not selected:
            return

        # Rows that can't be restarted are left as they are
        restartable = [
            transcription
            for transcription in selected
            if transcription.status in ["failed", "canceled", "skipped"]
        ]
        if not restartable:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                _("Cannot Restart"),
                _("Only failed, canceled, or skipped transcriptions can be restarted.")
            )
            return

        for transcription in restartable:
            try:
                self.transcription_service.reset_transcription_for_restart(UUID(transcription.id))
                self._restart_transcription_task(transcription)
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    _("Error"),
                    _("Failed to restart transcription: {}").format(str(e))
                )
        self.refresh_all()
    
    def _restart_transcription_task(self, transcription):
        """Create a new FileTranscriptionTask and add it to the queue worker"""
        from buzz.transcriber.transcriber import (
            FileTranscriptionTask, 
            TranscriptionOptions, 
            FileTranscriptionOptions,
            Task
        )
        from buzz.model_loader import TranscriptionModel, ModelType
        from buzz.transcriber.transcriber import OutputFormat
        
        # Recreate the transcription options from the database record
        from buzz.model_loader import WhisperModelSize
        
        # Convert string whisper_model_size to enum if it exists
        whisper_model_size = None
        if transcription.whisper_model_size:
            try:
                whisper_model_size = WhisperModelSize(transcription.whisper_model_size)
            except ValueError:
                # If the stored value is invalid, use a default
                whisper_model_size = WhisperModelSize.TINY
        
        transcription_options = TranscriptionOptions(
            language=transcription.language if transcription.language else None,
            task=Task(transcription.task) if transcription.task else Task.TRANSCRIBE,
            model=TranscriptionModel(
                model_type=ModelType(transcription.model_type) if transcription.model_type else ModelType.WHISPER,
                whisper_model_size=whisper_model_size,
                hugging_face_model_id=transcription.hugging_face_model_id
            ),
            # SQLite returns these BOOLEAN columns as 1 or 0
            word_level_timings=transcription.word_level_timings == 1,
            extract_speech=transcription.extract_speech == 1,
            initial_prompt="",  # Not stored in database, use default
            openai_access_token="",  # Not stored in database, use default
            enable_llm_translation=False,  # Not stored in database, use default
            llm_prompt="",  # Not stored in database, use default
            llm_model=""  # Not stored in database, use default
        )
        
        # Recreate the file transcription options
        output_formats = set()
        if transcription.export_formats:
            for format_str in transcription.export_formats.split(','):
                try:
                    output_formats.add(OutputFormat(format_str.strip()))
                except ValueError:
                    pass  # Skip invalid formats
        
        file_transcription_options = FileTranscriptionOptions(
            url=transcription.url if transcription.url else None,
            output_formats=output_formats
        )
        
        # Get the model path from the transcription options
        model_path = transcription_options.model.get_local_model_path()
        if model_path is None:
            # If model is not available locally, we need to download it
            from buzz.model_loader import ModelDownloader
            ModelDownloader(model=transcription_options.model).run()
            model_path = transcription_options.model.get_local_model_path()
        
        if model_path is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                _("Error"), 
                _("Could not restart transcription: model not available and could not be downloaded.")
            )
            return
        
        # Create the new task
        task = FileTranscriptionTask(
            transcription_options=transcription_options,
            file_transcription_options=file_transcription_options,
            model_path=model_path,
            file_path=transcription.file if transcription.file else None,
            url=transcription.url if transcription.url else None,
            output_directory=transcription.output_folder if transcription.output_folder else None,
            source=FileTranscriptionTask.Source(transcription.source) if transcription.source else FileTranscriptionTask.Source.FILE_IMPORT,
            uid=UUID(transcription.id)
        )
        
        # Add the task to the queue worker
        # We need to access the main window's transcriber worker
        # This is a bit of a hack, but it's the cleanest way given the current architecture
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'transcriber_worker'):
            main_window = main_window.parent()
        
        if main_window and hasattr(main_window, 'transcriber_worker'):
            main_window.transcriber_worker.add_task(task)
        else:
            # Fallback: show error if we can't find the transcriber worker
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                _("Error"), 
                _("Could not restart transcription: transcriber worker not found.")
            )