from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel
from PyQt6.QtCore import QTimer, pyqtSignal


class ExcludeEditor(QWidget):
    save_requested = pyqtSignal(str)  # Emits current text to be saved

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.label = QLabel("Exclude from name indexing (one per line):")
        self.layout.addWidget(self.label)

        self.editor = QPlainTextEdit()
        self.layout.addWidget(self.editor)

        # Autosave timer
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(2000)
        self.autosave_timer.timeout.connect(self.emit_save)

        self.editor.textChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        self.autosave_timer.start()

    def emit_save(self):
        self.save_requested.emit(self.editor.toPlainText())

    def set_text(self, text):
        self.editor.setPlainText(text)

    def get_words(self):
        """Return list of non-empty stripped lines."""
        return [line.strip() for line in self.editor.toPlainText().splitlines()
                if line.strip()]

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
