import platform
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QWidget, QSizePolicy


class LineEdit(QLineEdit):
    def __init__(self, default_text: str = "", parent: Optional[QWidget] = None):
        super().__init__(default_text, parent)
        if platform.system() == "Darwin":
            self.setStyleSheet("QLineEdit { padding: 4px }")
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_technical_text(self):
        """Keep URLs, keys and identifiers readable inside an RTL form."""
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
