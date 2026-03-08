from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PyQt6.QtCore import pyqtSignal, Qt


class CollapsiblePanel(QWidget):
    """A wrapper that adds a collapsible toggle header to any child widget."""

    toggled = pyqtSignal(object, bool)  # (self, expanded)

    def __init__(self, title, content_widget, expanded=True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._title = title
        self.content_widget = content_widget

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        # Toggle header button
        arrow = "▼" if expanded else "▶"
        self.toggle_btn = QPushButton(f"{arrow} {title}")
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet(
            "text-align: left; font-weight: bold; padding: 4px;"
        )
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.toggle_btn.clicked.connect(self._on_click)
        layout.addWidget(self.toggle_btn)

        # Child content
        content_widget.setVisible(expanded)
        layout.addWidget(content_widget, 1)

    # ------------------------------------------------------------------

    def _on_click(self):
        self.set_expanded(not self._expanded)
        self.toggled.emit(self, self._expanded)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.content_widget.setVisible(expanded)
        arrow = "▼" if expanded else "▶"
        self.toggle_btn.setText(f"{arrow} {self._title}")

    def is_expanded(self):
        return self._expanded
