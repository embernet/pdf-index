from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel
from PyQt6.QtCore import QTimer, pyqtSignal


class ProperNamesEditor(QWidget):
    """List of place/thing names that must not be inverted in the index."""

    save_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.label = QLabel("Place/thing names — kept in natural order (one per line):")
        self.layout.addWidget(self.label)

        self.editor = QPlainTextEdit()
        self.layout.addWidget(self.editor)

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

    def get_names(self):
        return [line.strip() for line in self.editor.toPlainText().splitlines()
                if line.strip()]

    def add_name(self, name):
        name = name.strip()
        if not name:
            return
        existing = {n.lower() for n in self.get_names()}
        if name.lower() not in existing:
            current = self.editor.toPlainText()
            if current and not current.endswith("\n"):
                current += "\n"
            current += name
            self.editor.setPlainText(current)
            self.emit_save()
