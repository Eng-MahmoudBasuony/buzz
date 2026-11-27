"""Focused import home backed by the existing transcription queue and model."""

import copy
import os

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from buzz.db.entity.transcription import Transcription
from buzz.locale import _
from buzz.model_loader import ModelType, TranscriptionModel, WhisperModelSize
from buzz.transcriber.transcriber import FileTranscriptionTask
from buzz.widgets.icon import BUZZ_ICON_PATH
from buzz.widgets.line_edit import LineEdit
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcriber.languages_combo_box import LanguagesComboBox
from buzz.widgets.transcription_tasks_table_widget import format_record_status_text
from buzz.widgets.workspace_style import HOME_STYLE, apply_workspace_palette


def label(text, role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    return widget


class FocusHome(QWidget):
    transcribe_requested = pyqtSignal(str, object, object, bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName("FocusHome")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        apply_workspace_palette(self)
        self.setStyleSheet(HOME_STYLE)
        self.file_mode = False
        self._cards_signature = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        nav = QFrame()
        nav.setObjectName("TopNav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(32, 14, 32, 14)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(BUZZ_ICON_PATH).scaled(
                30,
                30,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand = label("Buzz")
        brand.setObjectName("Brand")
        nav_layout.addWidget(logo)
        nav_layout.addWidget(brand)
        nav_layout.addSpacing(25)
        self.home_button = QPushButton(_("New transcription"))
        self.library_button = QPushButton(_("Library"))
        group = QButtonGroup(self)
        for button in (self.home_button, self.library_button):
            button.setCheckable(True)
            group.addButton(button)
            nav_layout.addWidget(button)
        self.home_button.setChecked(True)
        nav_layout.addStretch()
        record = QPushButton(_("Record"))
        record.clicked.connect(window.toolbar.record_action.trigger)
        nav_layout.addWidget(record)
        preferences = QPushButton(_("Preferences"))
        preferences.clicked.connect(window.menu_bar.preferences_action.trigger)
        nav_layout.addWidget(preferences)
        root.addWidget(nav)

        self.pages = QStackedWidget()
        root.addWidget(self.pages)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("HomeScrollContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QHBoxLayout(content)
        outer.setContentsMargins(28, 28, 28, 28)
        body = QWidget()
        body.setMaximumWidth(1040)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        title = label(_("Turn video into text"))
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        subtitle = label(
            _("Add a YouTube link or choose a file from your device."), "muted"
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(5)
        layout.addWidget(self._create_import_card())
        self.active_container = QWidget()
        self.active_layout = QVBoxLayout(self.active_container)
        self.active_layout.setContentsMargins(0, 0, 0, 0)
        self.active_layout.setSpacing(10)
        layout.addWidget(self.active_container)
        layout.addWidget(label(_("Recent transcripts"), "heading"))
        self.recent_container = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(10)
        layout.addWidget(self.recent_container)
        layout.addStretch()
        outer.addStretch()
        outer.addWidget(body, 1)
        outer.addStretch()
        scroll.setWidget(content)
        self.pages.addWidget(scroll)

        library = QWidget()
        library_layout = QVBoxLayout(library)
        library_layout.setContentsMargins(32, 24, 32, 24)
        library_heading = QHBoxLayout()
        library_heading.addWidget(label(_("Library"), "heading"))
        library_heading.addStretch()
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText(_("Search transcripts…"))
        self.library_search.setClearButtonEnabled(True)
        self.library_search.textChanged.connect(self._filter_library)
        library_heading.addWidget(self.library_search)
        library_layout.addLayout(library_heading)
        actions = QHBoxLayout()
        for action in (
            window.toolbar.open_transcript_action,
            window.toolbar.stop_transcription_action,
            window.toolbar.clear_history_action,
        ):
            button = QToolButton()
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            actions.addWidget(button)
        actions.addStretch()
        library_layout.addLayout(actions)
        window.table_widget.setAlternatingRowColors(True)
        window.table_widget.setShowGrid(False)
        window.table_widget.verticalHeader().setDefaultSectionSize(56)
        library_layout.addWidget(window.table_widget, 1)
        self.pages.addWidget(library)
        self.home_button.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.library_button.clicked.connect(lambda: self.pages.setCurrentIndex(1))

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(120)
        self.refresh_timer.timeout.connect(self.refresh_cards)
        model = window.table_widget.model()
        for signal in (
            model.modelReset,
            model.dataChanged,
            model.rowsInserted,
            model.rowsRemoved,
        ):
            signal.connect(self.schedule_refresh)
        # Queue phase messages can change while the numeric progress stays fixed.
        self.phase_timer = QTimer(self)
        self.phase_timer.setInterval(1500)
        self.phase_timer.timeout.connect(self.schedule_refresh)
        self.phase_timer.start()
        self.refresh_cards()

    def _create_import_card(self):
        card = QFrame()
        card.setObjectName("ImportCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        tabs = QHBoxLayout()
        group = QButtonGroup(card)
        self.url_tab = QPushButton(_("YouTube link"))
        self.file_tab = QPushButton(_("Audio or video file"))
        for button in (self.url_tab, self.file_tab):
            button.setCheckable(True)
            group.addButton(button)
            tabs.addWidget(button)
        self.url_tab.setChecked(True)
        self.url_tab.clicked.connect(lambda: self.set_file_mode(False))
        self.file_tab.clicked.connect(lambda: self.set_file_mode(True))
        layout.addLayout(tabs)
        self.input_stack = QStackedWidget()
        input_row = QWidget()
        inputs = QHBoxLayout(input_row)
        inputs.setContentsMargins(0, 0, 0, 0)
        self.url_edit = LineEdit()
        self.url_edit.set_technical_text()
        self.url_edit.setAccessibleName(_("Video link"))
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.submit)
        inputs.addWidget(self.url_edit, 1)
        paste = QPushButton(_("Paste"))
        paste.clicked.connect(
            lambda: self.url_edit.setText(QApplication.clipboard().text().strip())
        )
        inputs.addWidget(paste)
        self.input_stack.addWidget(input_row)
        self.input_stack.addWidget(
            label(
                _(
                    "Choose an audio or video file to review its transcription settings."
                ),
                "muted",
            )
        )
        layout.addWidget(self.input_stack)

        self.window.settings.settings.beginGroup("file_transcriber")
        try:
            preferences = FileTranscriptionPreferences.load(
                self.window.settings.settings
            )
        finally:
            self.window.settings.settings.endGroup()
        options = QHBoxLayout()
        options.addWidget(label(_("Language:")))
        self.language_combo = LanguagesComboBox(preferences.language, card)
        # Display the native name of the current UI language in the short form.
        for index, (code, _name) in enumerate(self.language_combo.languages):
            if code == "ar":
                self.language_combo.setItemText(index, "العربية")
        options.addWidget(self.language_combo, 1)
        options.addSpacing(14)
        options.addWidget(label(_("Model:")))
        self.model_combo = QComboBox()
        self.model_combo.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.model_combo.setMinimumContentsLength(16)
        self.model_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        saved = copy.deepcopy(preferences.model)
        self.model_combo.addItem(str(saved), saved)
        if (
            ModelType.OPEN_AI_WHISPER_API.is_available()
            and saved.model_type != ModelType.OPEN_AI_WHISPER_API
        ):
            model = TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
            self.model_combo.addItem(str(model), model)
        local_type = (
            ModelType.WHISPER_CPP
            if ModelType.WHISPER_CPP.is_available()
            else ModelType.WHISPER
        )
        for size in (
            WhisperModelSize.SMALL,
            WhisperModelSize.MEDIUM,
            WhisperModelSize.LARGEV3,
        ):
            model = TranscriptionModel(model_type=local_type, whisper_model_size=size)
            if model != saved:
                self.model_combo.addItem(str(model), model)
        options.addWidget(self.model_combo, 2)
        layout.addLayout(options)
        self.validation_label = label("", "muted")
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        layout.addWidget(self.validation_label)
        self.start_button = QPushButton(_("Start transcription"))
        self.start_button.setObjectName("StartButton")
        self.start_button.clicked.connect(self.submit)
        layout.addWidget(self.start_button)
        advanced = QPushButton(_("Review advanced settings"))
        advanced.clicked.connect(lambda: self.submit(review=True))
        layout.addWidget(advanced, 0, Qt.AlignmentFlag.AlignTrailing)
        return card

    def set_file_mode(self, enabled):
        self.file_mode = enabled
        self.input_stack.setCurrentIndex(int(enabled))
        self.start_button.setText(
            _("Choose file…") if enabled else _("Start transcription")
        )
        self.validation_label.hide()

    def submit(self, _checked=False, review=False):
        url = self.url_edit.text().strip()
        if not self.file_mode:
            from buzz.youtube_url import canonical_video

            try:
                canonical_video(url)
            except ValueError:
                self.validation_label.setText(_("Enter a valid YouTube video link."))
                self.validation_label.show()
                self.url_edit.setFocus()
                return
        self.validation_label.hide()
        language = self.language_combo.languages[self.language_combo.currentIndex()][0]
        self.transcribe_requested.emit(
            "" if self.file_mode else url,
            copy.deepcopy(self.model_combo.currentData()),
            language or None,
            review or self.file_mode,
        )

    def schedule_refresh(self, *_args):
        if not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def _filter_library(self, text):
        model = self.window.table_widget.model()
        needle = text.casefold().strip()
        for row in range(model.rowCount()):
            record = model.record(row)
            haystack = " ".join(
                str(record.value(key) or "") for key in ("name", "file", "url", "notes")
            )
            self.window.table_widget.setRowHidden(
                row, needle not in haystack.casefold()
            )

    def refresh_cards(self):
        model = self.window.table_widget.model()
        # Qt SQL fetches rows in pages; library search and recent selection must
        # include the whole history, not just the first fetched page.
        while model.canFetchMore():
            model.fetchMore()
        records = [model.record(row) for row in range(model.rowCount())]
        records.sort(
            key=lambda record: str(record.value("time_queued") or ""), reverse=True
        )
        active = [
            r
            for r in records
            if r.value("status")
            in (
                FileTranscriptionTask.Status.QUEUED.value,
                FileTranscriptionTask.Status.IN_PROGRESS.value,
            )
        ]
        recent = [r for r in records if r not in active][:4]
        signature = tuple(
            (
                str(r.value("id")),
                r.value("name"),
                r.value("file"),
                r.value("progress"),
                format_record_status_text(r),
            )
            for r in active + recent
        )
        if signature == self._cards_signature:
            self._filter_library(self.library_search.text())
            return
        self._cards_signature = signature
        for layout in (self.active_layout, self.recent_layout):
            while layout.count():
                item = layout.takeAt(0)
                item.widget().deleteLater()
        self.active_container.setVisible(bool(active))
        for record in active:
            self.active_layout.addWidget(self._record_card(record, active=True))
        for record in recent:
            self.recent_layout.addWidget(self._record_card(record))
        if not recent:
            self.recent_layout.addWidget(
                label(_("Your completed transcripts will appear here."), "muted")
            )
        self._filter_library(self.library_search.text())

    def _record_card(self, record, active=False):
        transcription = Transcription.from_record(record)
        card = QFrame()
        card.setObjectName("RecentCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        text = QVBoxLayout()
        title = (
            transcription.name
            or (
                os.path.basename(transcription.file)
                if transcription.file
                else transcription.url
            )
            or _("Transcript")
        )
        title_label = label(title)
        title_label.setWordWrap(True)
        text.addWidget(title_label)
        status = label(format_record_status_text(record), "muted")
        status.setWordWrap(True)
        text.addWidget(status)
        row.addLayout(text, 1)
        if self.window.can_open_transcript(transcription):
            open_button = QPushButton(_("Open Transcript"))
            open_button.clicked.connect(
                lambda: self.window.open_transcription_viewer(transcription)
            )
            row.addWidget(open_button)
        if active:
            stop = QPushButton(_("Cancel Transcription"))
            stop.clicked.connect(
                lambda: self._row_action(
                    transcription.id, self.window.on_stop_transcription_action_triggered
                )
            )
            row.addWidget(stop)
        more = QToolButton()
        more.setText("⋯")
        more.setAccessibleName(_("More actions"))
        menu = QMenu(more)
        menu.addAction(
            _("Show in library"), lambda: self.show_in_library(transcription.id)
        )
        menu.addAction(
            _("Clear History"),
            lambda: self._row_action(
                transcription.id, self.window.on_clear_history_action_triggered
            ),
        )
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(more)
        layout.addLayout(row)
        if active:
            progress = QProgressBar()
            progress.setTextVisible(False)
            value = float(transcription.progress or 0)
            if value <= 0:
                progress.setRange(0, 0)
            else:
                progress.setRange(0, 1000)
                progress.setValue(round(max(0, min(value, 1)) * 1000))
            layout.addWidget(progress)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return card

    def _row_action(self, transcription_id, callback):
        model = self.window.table_widget.model()
        for row in range(model.rowCount()):
            if str(model.record(row).value("id")) == str(transcription_id):
                self.window.table_widget.selectRow(row)
                callback()
                return

    def show_in_library(self, transcription_id):
        self.library_search.clear()
        self.library_button.setChecked(True)
        self.pages.setCurrentIndex(1)
        self._row_action(
            transcription_id,
            lambda: self.window.table_widget.scrollTo(
                self.window.table_widget.currentIndex()
            ),
        )
