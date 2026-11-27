"""Scoped desktop palettes: a quiet home and a focused transcript studio."""

from PyQt6.QtGui import QColor, QPalette


def apply_workspace_palette(widget, dark=False):
    palette = widget.palette()
    colors = {
        QPalette.ColorRole.Window: "#171b1e" if dark else "#f3f5fa",
        QPalette.ColorRole.WindowText: "#eef4f3" if dark else "#202b42",
        QPalette.ColorRole.Base: "#20262a" if dark else "#ffffff",
        QPalette.ColorRole.AlternateBase: "#1c2226" if dark else "#f8f9fc",
        QPalette.ColorRole.Text: "#eef4f3" if dark else "#202b42",
        QPalette.ColorRole.Button: "#282f34" if dark else "#ffffff",
        QPalette.ColorRole.ButtonText: "#eef4f3" if dark else "#202b42",
        QPalette.ColorRole.Highlight: "#29554b" if dark else "#fce6e7",
        QPalette.ColorRole.HighlightedText: "#ffffff" if dark else "#972e38",
        QPalette.ColorRole.PlaceholderText: "#93a3aa" if dark else "#798397",
    }
    for role, value in colors.items():
        palette.setColor(role, QColor(value))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


HOME_STYLE = """
QWidget#FocusHome { background: #f3f5fa; color: #202b42; }
QWidget#FocusHome QLabel { background: transparent; color: #202b42; }
QWidget#FocusHome QLabel[role="muted"] { color: #728099; }
QWidget#FocusHome QLabel#HeroTitle { font-size: 32px; font-weight: 700; }
QWidget#FocusHome QLabel#Brand { font-size: 23px; font-weight: 700; }
QWidget#FocusHome QLabel[role="heading"] { font-size: 19px; font-weight: 600; }
QWidget#FocusHome QFrame#ImportCard, QWidget#FocusHome QFrame#RecentCard {
 background: white; border: 1px solid #dde2ed; border-radius: 16px;
}
QWidget#FocusHome QFrame#TopNav { border-bottom: 1px solid #dde2ed; }
QWidget#FocusHome QPushButton, QWidget#FocusHome QToolButton {
 color: #38445a; background: #ffffff; border: 1px solid #dce1ec;
 border-radius: 8px; padding: 8px 15px; min-height: 20px;
}
QWidget#FocusHome QPushButton:hover, QWidget#FocusHome QToolButton:hover { background: #edf1f8; }
QWidget#FocusHome QPushButton:focus, QWidget#FocusHome QLineEdit:focus,
QWidget#FocusHome QComboBox:focus { border: 2px solid #d76a70; }
QWidget#FocusHome QPushButton:checked { color: #a52e3b; background: #fbe5e7; border-color: #f3d2d6; }
QWidget#FocusHome QPushButton#StartButton { color: white; background: #d65e69; border: 0; font-weight: 600; padding: 12px; }
QWidget#FocusHome QPushButton#StartButton:hover { background: #c94d5b; }
QWidget#FocusHome QPushButton:disabled { color: #98a0ad; background: #eef0f5; }
QWidget#FocusHome QLineEdit, QWidget#FocusHome QComboBox {
 background: #fafbfe; color: #26324a; border: 1px solid #dce1ec;
 border-radius: 8px; padding: 9px 12px; min-height: 22px;
}
QWidget#FocusHome QComboBox QAbstractItemView { background: white; color: #26324a; selection-background-color: #fbe5e7; }
QWidget#FocusHome QScrollArea, QWidget#FocusHome QWidget#HomeScrollContent { background: #f3f5fa; border: 0; }
QWidget#FocusHome QProgressBar { border: 0; background: #e9edf5; border-radius: 3px; min-height: 6px; max-height: 6px; }
QWidget#FocusHome QProgressBar::chunk { background: #d65e69; border-radius: 3px; }
QWidget#FocusHome QTableView { background: white; color: #26324a; border: 1px solid #dde2ed; border-radius: 10px; gridline-color: #edf0f6; selection-background-color: #fbe5e7; selection-color: #782833; }
QWidget#FocusHome QHeaderView::section { background: #edf1f8; color: #526078; padding: 10px; border: 0; }
QWidget#FocusHome QScrollBar:vertical { width: 9px; background: transparent; }
QWidget#FocusHome QScrollBar::handle:vertical { background: #cbd3e1; border-radius: 4px; min-height: 30px; }
QWidget#FocusHome QScrollBar::add-line:vertical, QWidget#FocusHome QScrollBar::sub-line:vertical { height: 0; }
"""


STUDIO_STYLE = """
QWidget#TranscriptStudio { background: #171b1e; color: #eef4f3; }
QWidget#TranscriptStudio QLabel { color: #eef4f3; background: transparent; }
QWidget#TranscriptStudio QLabel[role="muted"] { color: #a0aeb5; }
QWidget#TranscriptStudio QLabel[role="heading"] { font-size: 18px; font-weight: 600; }
QWidget#TranscriptStudio QLabel#StudioTitle { font-size: 21px; font-weight: 600; }
QWidget#TranscriptStudio QFrame#StudioPanel { background: #1d2327; border: 1px solid #343e44; border-radius: 12px; }
QWidget#TranscriptStudio QToolBar { background: #171b1e; border: 0; spacing: 7px; padding: 6px 0; }
QWidget#TranscriptStudio QToolButton, QWidget#TranscriptStudio QPushButton {
 background: #252d32; color: #e2eceb; border: 1px solid #3a464d;
 border-radius: 7px; padding: 7px 10px; min-height: 21px;
}
QWidget#TranscriptStudio QToolButton:hover, QWidget#TranscriptStudio QPushButton:hover { background: #34433f; border-color: #5bc7aa; }
QWidget#TranscriptStudio QToolButton:checked, QWidget#TranscriptStudio QPushButton:checked { background: #29554b; color: #ddfff3; }
QWidget#TranscriptStudio QToolButton#StudioExport { background: #57c7a6; color: #10261f; border: 0; font-weight: 600; }
QWidget#TranscriptStudio QLineEdit, QWidget#TranscriptStudio QTextEdit,
QWidget#TranscriptStudio QComboBox { background: #20282d; color: #edf4f2; border: 1px solid #3a464d; border-radius: 7px; padding: 7px; }
QWidget#TranscriptStudio QComboBox QAbstractItemView { background: #20282d; color: #edf4f2; selection-background-color: #29554b; }
QWidget#TranscriptStudio QLineEdit:focus, QWidget#TranscriptStudio QTextEdit:focus { border: 1px solid #57c7a6; }
QWidget#TranscriptStudio QTableView { background: #1d2327; alternate-background-color: #20272b; color: #edf4f2; gridline-color: #354047; border: 0; selection-background-color: #28493f; selection-color: #ffffff; }
QWidget#TranscriptStudio QTableView::item { padding: 14px 10px; border-bottom: 1px solid #354047; }
QWidget#TranscriptStudio QTableView::item:selected { background: #28493f; color: white; }
QWidget#TranscriptStudio QHeaderView::section { background: #20272b; color: #a6b8bc; padding: 10px; border: 0; }
QWidget#TranscriptStudio QScrollArea { border: 0; background: transparent; }
QWidget#TranscriptStudio QWidget#StudioLibraryContent { background: #1d2327; }
QWidget#TranscriptStudio QScrollBar:vertical { width: 8px; background: #1d2327; }
QWidget#TranscriptStudio QScrollBar::handle:vertical { background: #4b5a60; border-radius: 4px; min-height: 30px; }
QWidget#TranscriptStudio QScrollBar::add-line:vertical, QWidget#TranscriptStudio QScrollBar::sub-line:vertical { height: 0; }
QWidget#TranscriptStudio QSplitter::handle { background: #171b1e; }
QWidget#TranscriptStudio QSlider::groove:horizontal { height: 5px; background: #3d4a50; border-radius: 2px; }
QWidget#TranscriptStudio QSlider::sub-page:horizontal { background: #57c7a6; border-radius: 2px; }
QWidget#TranscriptStudio QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: #bbf4df; }
QWidget#TranscriptStudio QCheckBox { color: #d5e2e0; spacing: 7px; }
"""
