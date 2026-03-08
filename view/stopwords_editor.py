from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import QTimer, pyqtSignal, Qt


class StopwordsEditor(QWidget):
    """Collapsible editor for the stopwords list.

    Shows a header with an expand/collapse toggle and a text editor (one word
    per line).  Changes are auto-saved after a short delay.
    """

    save_requested = pyqtSignal(str)  # Emits current text to be saved

    def __init__(self):
        super().__init__()
        self._expanded = False

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer)

        # Header row with toggle button
        header = QHBoxLayout()
        self.toggle_btn = QPushButton("▶ Stop Words")
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet("text-align: left; font-weight: bold;")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self.toggle_btn)
        header.addStretch()
        outer.addLayout(header)

        # Collapsible body
        self.body = QWidget()
        body_layout = QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        self.body.setLayout(body_layout)

        self.label = QLabel("One word per line:")
        body_layout.addWidget(self.label)

        self.editor = QPlainTextEdit()
        body_layout.addWidget(self.editor)

        self.body.setVisible(False)
        outer.addWidget(self.body)

        # Autosave timer
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(2000)
        self.autosave_timer.timeout.connect(self.emit_save)

        self.editor.textChanged.connect(self.on_text_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_text(self, text):
        self.editor.setPlainText(text)

    def get_words(self):
        """Return list of non-empty stripped lines."""
        return [
            line.strip()
            for line in self.editor.toPlainText().splitlines()
            if line.strip()
        ]

    def add_word(self, word):
        """Add a word if not already present (case-insensitive)."""
        word = word.strip()
        if not word:
            return
        existing = {w.lower() for w in self.get_words()}
        if word.lower() not in existing:
            current = self.editor.toPlainText()
            if current and not current.endswith("\n"):
                current += "\n"
            current += word
            self.editor.setPlainText(current)
            self.emit_save()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _toggle(self):
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        arrow = "▼" if self._expanded else "▶"
        self.toggle_btn.setText(f"{arrow} Stop Words")

    def on_text_changed(self):
        self.autosave_timer.start()

    def emit_save(self):
        self.save_requested.emit(self.editor.toPlainText())
