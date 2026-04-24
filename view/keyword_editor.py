from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QLabel, QPushButton
from PyQt6.QtCore import QTimer, pyqtSignal

class KeywordEditor(QWidget):
    keywords_changed = pyqtSignal() # When text changes
    save_requested = pyqtSignal(str) # Emits current text to be saved

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        self.label = QLabel("Include list (one per line):")
        self.layout.addWidget(self.label)
        
        self.sort_btn = QPushButton("Sort Alphabetically")
        self.sort_btn.clicked.connect(self.sort_keywords)
        self.layout.addWidget(self.sort_btn)
        
        self.editor = QPlainTextEdit()
        self.layout.addWidget(self.editor)
        
        # Autosave timer
        self.autosave_timer = QTimer()
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(2000) # 2 seconds
        self.autosave_timer.timeout.connect(self.emit_save)
        
        self.editor.textChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        self.autosave_timer.start()
        self.keywords_changed.emit()

    def sort_keywords(self):
        text = self.editor.toPlainText()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Deduplicate (Case-Insensitive)
        seen = set()
        unique_lines = []
        for line in lines:
            normalized = line.lower()
            if normalized not in seen:
                seen.add(normalized)
                unique_lines.append(line)
        
        sorted_lines = sorted(unique_lines, key=lambda s: s.lower())
        self.editor.setPlainText("\n".join(sorted_lines))
        self.emit_save()

    def emit_save(self):
        self.save_requested.emit(self.editor.toPlainText())

    def set_keywords(self, text):
        self.editor.setPlainText(text)

    def get_keywords(self):
        return self.editor.toPlainText().splitlines()
