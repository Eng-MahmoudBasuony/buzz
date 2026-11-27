"""Source/library panes and a seekable waveform for the transcript studio."""


import numpy as np
import unicodedata
from PyQt6.QtCore import Qt, QTimer, QRectF, QUrl
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from buzz.db.entity.transcription import Transcription
from buzz.locale import _
from buzz.paths import file_path_as_title
from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.focus_home import label
from buzz.widgets.icon import BUZZ_ICON_PATH
from buzz.widgets.transcription_viewer.transcription_segments_editor_widget import (
    Column,
    TimeStampEditorDelegate,
    WordWrapDelegate,
)


class StudioTimestampDelegate(TimeStampEditorDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        editor.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        return editor

    def displayText(self, value, locale):
        text = super().displayText(value, locale)
        return text[3:] if text.startswith("00:") else text

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.direction = Qt.LayoutDirection.LeftToRight
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter
        option.font = QFont(option.font.family(), 11)


class StudioTextDelegate(WordWrapDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        for character in option.text:
            direction = unicodedata.bidirectional(character)
            if direction in ("L", "R", "AL"):
                rtl = direction in ("R", "AL")
                option.direction = (
                    Qt.LayoutDirection.RightToLeft
                    if rtl
                    else Qt.LayoutDirection.LeftToRight
                )
                option.displayAlignment = (
                    Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
                ) | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute
                break


def style_transcript_table(table):
    delegate = StudioTimestampDelegate(table)
    delegate.timestamp_editing.connect(table.timestamp_being_edited)
    for column in (Column.START, Column.END):
        table.setItemDelegateForColumn(column.value, delegate)
        table.setColumnWidth(column.value, 100)
    for column in (Column.TEXT, Column.TRANSLATION):
        table.setItemDelegateForColumn(column.value, StudioTextDelegate(table))


class LibraryEntryButton(QPushButton):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.setMinimumWidth(0)

    def resizeEvent(self, event):
        self.setText(
            self.fontMetrics().elidedText(
                self.name, Qt.TextElideMode.ElideRight, max(10, self.width() - 24)
            )
        )
        super().resizeEvent(event)


class WaveformSeekBar(QSlider):
    """Draw real decoded samples, sharing the player's existing seek range.

    A plain seek track remains usable until samples are ready. No fabricated
    waveform and no second decoder are needed.
    """

    def __init__(self, player, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.player = player
        self.peaks = None
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setAccessibleName(_("Audio timeline"))
        self.setMinimumHeight(44)
        self.setRange(player.scrubber.minimum(), player.scrubber.maximum())
        self.setSingleStep(5000)
        self.setPageStep(15000)
        player.scrubber.rangeChanged.connect(self.setRange)
        player.position_ms_changed.connect(self.follow_position)
        player.scrubber.valueChanged.connect(self.follow_position)
        # Preserve the player's seek policy, including leaving a selected
        # passage's repeat range when the user seeks elsewhere.
        self.valueChanged.connect(player.on_slider_moved)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.load_peaks)
        self.timer.start()

    def load_peaks(self):
        samples = self.player.decoded_samples()
        if samples is None or not len(samples):
            return
        # Bound the work for very long recordings, and promote before abs so
        # an int16 value of -32768 does not overflow.
        sampled = samples[:: max(1, len(samples) // 160000)].astype(np.float32)
        if sampled.ndim > 1:
            sampled = np.max(np.abs(sampled), axis=1)
        else:
            sampled = np.abs(sampled)
        bins = np.array_split(sampled, min(240, len(sampled)))
        peaks = np.array([float(chunk.max()) for chunk in bins])
        maximum = float(peaks.max())
        self.peaks = peaks / maximum if maximum > 0 else np.zeros_like(peaks)
        self.timer.stop()
        self.update()

    def follow_position(self, value):
        if not self.isSliderDown():
            self.blockSignals(True)
            self.setValue(value)
            self.blockSignals(False)

    def _seek(self, event):
        ratio = max(0, min(1, event.position().x() / max(1, self.width())))
        self.setValue(round(self.minimum() + ratio * (self.maximum() - self.minimum())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus()
            self.setSliderDown(True)
            self._seek(event)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self._seek(event)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setSliderDown(False)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = max(1, self.width() - 8)
        ratio = (self.value() - self.minimum()) / max(
            1, self.maximum() - self.minimum()
        )
        x = 4 + width * ratio
        painter.setPen(Qt.PenStyle.NoPen)
        if self.peaks is None:
            painter.setBrush(QColor("#3d4a50"))
            painter.drawRoundedRect(QRectF(4, self.height() / 2 - 2, width, 4), 2, 2)
            painter.setBrush(QColor("#57c7a6"))
            painter.drawRoundedRect(
                QRectF(4, self.height() / 2 - 2, width * ratio, 4), 2, 2
            )
        else:
            step = max(3.5, width / max(1, len(self.peaks)))
            for index in range(max(1, int(width / step))):
                peak = self.peaks[
                    min(
                        len(self.peaks) - 1,
                        round(index * step / width * (len(self.peaks) - 1)),
                    )
                ]
                height = max(3, float(peak) ** 0.6 * (self.height() - 10))
                bx = 4 + index * step
                painter.setBrush(QColor("#57c7a6" if bx <= x else "#4b5b60"))
                painter.drawRoundedRect(
                    QRectF(bx, (self.height() - height) / 2, max(2, step - 2), height),
                    1,
                    1,
                )
        painter.setPen(QPen(QColor("#d0f8e9"), 2))
        painter.drawLine(round(x), 5, round(x), self.height() - 5)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#57c7a6"), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 5, 5)


def source_panel(viewer):
    panel = QFrame()
    panel.setObjectName("StudioPanel")
    panel.setMinimumWidth(210)
    panel.setMaximumWidth(310)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(18, 20, 18, 20)
    layout.setSpacing(18)
    layout.addWidget(label(_("Source"), "heading"))
    transcription = viewer.transcription
    source = QLineEdit(transcription.url or transcription.file or "")
    source.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    source.setReadOnly(True)
    source.setCursorPosition(0)
    source.setAccessibleName(_("Source"))
    source.setToolTip(source.text())
    layout.addWidget(source)
    if viewer.is_video:
        viewer.media_player_stack.setMaximumHeight(300)
        viewer.media_player_stack.setMinimumHeight(180)
        layout.addWidget(viewer.media_player_stack)
    else:
        media = label(
            _("Media from a link") if transcription.url else _("Audio recording"),
            "heading",
        )
        media.setAlignment(Qt.AlignmentFlag.AlignCenter)
        media.setMinimumHeight(90)
        layout.addWidget(media)
        if transcription.url and QUrl(transcription.url).scheme() in ("http", "https"):
            open_source = QPushButton(_("Open source video"))
            open_source.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(transcription.url))
            )
            layout.addWidget(open_source)
    layout.addWidget(label(_("Transcription details"), "heading"))
    details = [
        (
            _("Language:"),
            "العربية"
            if transcription.language == "ar"
            else transcription.language or _("Detect Language"),
        ),
        (_("Model:"), transcription.model_type or "—"),
    ]
    from buzz.model_loader import ModelType

    if transcription.model_type != ModelType.OPEN_AI_WHISPER_API.value:
        details.append(
            (
                _("Model size"),
                transcription.whisper_model_size
                or transcription.hugging_face_model_id
                or "—",
            )
        )
    for heading, value in details:
        layout.addWidget(label(heading, "muted"))
        value_label = label(value)
        value_label.setWordWrap(True)
        if heading != _("Language:"):
            value_label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(value_label)
    layout.addStretch()
    hint = label(
        _("Double-click a passage to edit. Changes are saved automatically."), "muted"
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    return panel


def library_panel(viewer):
    panel = QFrame()
    panel.setObjectName("StudioPanel")
    panel.setMinimumWidth(190)
    panel.setMaximumWidth(250)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(16, 20, 16, 20)
    layout.setSpacing(14)
    brand_row = QHBoxLayout()
    icon = QLabel()
    icon.setPixmap(
        QPixmap(BUZZ_ICON_PATH).scaled(
            26,
            26,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
    brand_row.addWidget(icon)
    brand_row.addWidget(label("Buzz", "heading"))
    brand_row.addStretch()
    layout.addLayout(brand_row)
    home_button = QPushButton(_("Library"))
    home_button.clicked.connect(lambda: _show_main(viewer, library=True))
    layout.addWidget(home_button)
    new_button = QPushButton(_("New transcription"))
    new_button.clicked.connect(lambda: _show_main(viewer, library=False))
    layout.addWidget(new_button)
    layout.addSpacing(10)
    layout.addWidget(label(_("Recent transcripts"), "heading"))
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.viewport().setAutoFillBackground(False)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName("StudioLibraryContent")
    content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    entries = QVBoxLayout(content)
    entries.setContentsMargins(0, 0, 0, 0)
    entries.setSpacing(10)
    # Use the same connection and read-only query as the normal library.
    dao = viewer.transcription_service.transcription_dao
    query = dao._create_query()
    query.prepare(
        "SELECT * FROM transcription WHERE status IN (:completed, :skipped) "
        "ORDER BY time_queued DESC LIMIT 12"
    )
    query.bindValue(":completed", FileTranscriptionTask.Status.COMPLETED.value)
    query.bindValue(":skipped", FileTranscriptionTask.Status.SKIPPED.value)
    if query.exec():
        while query.next():
            transcription = Transcription.from_record(query.record())
            if transcription.status not in (
                FileTranscriptionTask.Status.COMPLETED.value,
                FileTranscriptionTask.Status.SKIPPED.value,
            ):
                continue
            name = (
                transcription.name
                or (
                    file_path_as_title(transcription.file)
                    if transcription.file
                    else transcription.url
                )
                or _("Transcript")
            )
            button = LibraryEntryButton(name)
            button.setCheckable(True)
            button.setChecked(transcription.id == viewer.transcription.id)
            button.clicked.connect(
                lambda _checked=False, item=transcription: _open_record(viewer, item)
            )
            entries.addWidget(button)
    entries.addStretch()
    scroll.setWidget(content)
    layout.addWidget(scroll, 1)
    return panel


def _show_main(viewer, library):
    main = viewer.parentWidget()
    if main is None or not hasattr(main, "home"):
        return
    main.show()
    main.raise_()
    main.activateWindow()
    main.home.pages.setCurrentIndex(1 if library else 0)
    (main.home.library_button if library else main.home.home_button).setChecked(True)


def _open_record(viewer, transcription):
    main = viewer.parentWidget()
    if main is not None and hasattr(main, "open_transcription_viewer"):
        if transcription.id == viewer.transcription.id:
            return
        main.open_transcription_viewer(transcription)
