from unittest.mock import Mock, patch

import numpy as np
import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QSlider

from buzz.db.entity.transcription import Transcription
from buzz.model_loader import ModelType, TranscriptionModel
from buzz.transcriber.transcriber import FileTranscriptionTask, Task
from buzz.widgets.main_window import MainWindow
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcription_viewer.studio_panels import WaveformSeekBar
from buzz.widgets.transcription_viewer.transcription_viewer_widget import (
    TranscriptionViewerWidget,
)


@pytest.fixture
def window(qtbot, transcription_service):
    widget = MainWindow(transcription_service)
    qtbot.addWidget(widget)
    yield widget
    widget.close()


def test_home_rejects_invalid_url_without_starting_work(window):
    home = window.home
    with patch.object(window, "open_file_transcriber_widget") as open_dialog:
        home.url_edit.setText("https://example.org/watch?v=abcdefghijk")
        home.submit()
        open_dialog.assert_not_called()
        assert not home.validation_label.isHidden()


def test_home_passes_selected_model_language_and_original_timecode(window):
    home = window.home
    for index, (code, _name) in enumerate(home.language_combo.languages):
        if code == "ar":
            home.language_combo.setCurrentIndex(index)
    url = "https://www.youtube.com/watch?v=abcdefghijk&t=399s"
    home.url_edit.setText(url)
    with patch.object(window, "open_file_transcriber_widget") as open_dialog:
        home.submit()
        kwargs = open_dialog.call_args.kwargs
        assert kwargs["url"] == url
        assert kwargs["initial_language"] == "ar"
        assert str(kwargs["initial_model"]) == home.model_combo.currentText()
        assert kwargs["start_immediately"] is True
        assert kwargs["use_initial_options"] is True
        assert not hasattr(kwargs["initial_model"], "openai_access_token")


def test_advanced_settings_never_automatically_start_a_paid_task(window):
    window.home.url_edit.setText("https://youtu.be/abcdefghijk")
    with patch.object(window, "open_file_transcriber_widget") as open_dialog:
        window.home.submit(review=True)
        assert open_dialog.call_args.kwargs["start_immediately"] is False


def test_library_search_handles_quotes_and_restores_rows(window):
    dao = window.transcription_service.transcription_dao
    first = Transcription(name="O'Reilly العربية", status="completed")
    second = Transcription(name="Second lesson", status="completed")
    dao.insert(first)
    dao.insert(second)
    table = window.table_widget
    table.refresh_all()
    window.home.refresh_cards()
    window.home.library_search.setText("O'Reilly")
    shown = [
        table.model().record(row).value("name")
        for row in range(table.model().rowCount())
        if not table.isRowHidden(row)
    ]
    assert shown == [first.name]
    assert table.model().filter() == ""
    window.home.library_search.clear()
    assert all(not table.isRowHidden(row) for row in range(table.model().rowCount()))


def test_recent_card_opens_the_record_that_was_clicked(window):
    record = Transcription(name="Arabic lesson", status="completed")
    window.transcription_service.transcription_dao.insert(record)
    window.table_widget.refresh_all()
    window.home.refresh_cards()
    with patch.object(window, "open_transcription_viewer") as open_viewer:
        buttons = window.home.recent_container.findChildren(QPushButton)
        assert buttons
        buttons[0].click()
        assert open_viewer.call_args.args[0].id == record.id


def test_active_card_cancels_only_its_own_task(window):
    first = Transcription(
        name="First", status=FileTranscriptionTask.Status.QUEUED.value
    )
    second = Transcription(
        name="Second", status=FileTranscriptionTask.Status.QUEUED.value
    )
    for record in (first, second):
        window.transcription_service.transcription_dao.insert(record)
    window.table_widget.refresh_all()
    window.home.refresh_cards()
    window.home._row_action(first.id, window.on_stop_transcription_action_triggered)
    service = window.transcription_service
    assert service.get_transcription(first.id_as_uuid).status == "canceled"
    assert service.get_transcription(second.id_as_uuid).status == "queued"


def test_home_initial_options_override_saved_translate_task(qtbot):
    model = TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
    widget = FileTranscriberWidget(
        url="https://youtu.be/abcdefghijk",
        initial_model=model,
        initial_language="ar",
        use_initial_options=True,
    )
    qtbot.addWidget(widget)
    assert widget.transcription_options.task == Task.TRANSCRIBE
    assert widget.transcription_options.language == "ar"
    assert widget.transcription_options.model is model
    widget.close()


class FakePlayer(QObject):
    position_ms_changed = pyqtSignal(int)

    def __init__(self, samples):
        super().__init__()
        self.scrubber = QSlider()
        self.scrubber.setRange(0, 10000)
        self.samples = samples
        self.set_position = Mock()

    def decoded_samples(self):
        return self.samples


def test_waveform_follows_player_without_seeking_back(qtbot):
    player = FakePlayer(None)
    waveform = WaveformSeekBar(player)
    qtbot.addWidget(waveform)
    player.position_ms_changed.emit(2500)
    assert waveform.value() == 2500
    player.set_position.assert_not_called()
    waveform.setValue(7000)
    player.set_position.assert_called_once_with(7000)


def test_waveform_uses_real_samples_and_silence_remains_flat(qtbot):
    player = FakePlayer(np.zeros((1000, 2), dtype=np.int16))
    waveform = WaveformSeekBar(player)
    qtbot.addWidget(waveform)
    waveform.load_peaks()
    assert np.all(waveform.peaks == 0)
    player.samples[500] = -32768
    waveform.load_peaks()
    assert np.isfinite(waveform.peaks).all()
    assert waveform.peaks.max() == 1
    assert waveform.layoutDirection() == Qt.LayoutDirection.LeftToRight


def test_opening_studio_never_requests_keychain_access(qtbot, window, tmp_path):
    import wave

    audio = tmp_path / "studio.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 1600)
    transcription = Transcription(file=str(audio), status="completed")
    window.transcription_service.transcription_dao.insert(transcription)
    with patch(
        "buzz.widgets.transcription_viewer.transcription_viewer_widget.get_password",
        side_effect=AssertionError("Unexpected credential access"),
    ), patch(
        "buzz.translator.get_password",
        side_effect=AssertionError("Unexpected credential access"),
    ):
        viewer = TranscriptionViewerWidget(
            transcription, window.transcription_service, window.shortcuts
        )
        qtbot.addWidget(viewer)
        assert viewer.openai_access_token is None
        viewer.close()
