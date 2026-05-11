"""Modal dialog that runs the LLM setup flow on a worker thread.

Drives :func:`model.llm_setup.run_setup` and streams each ``SetupEvent`` into
a read-only log view so the user can watch model pulls, smoke-test results,
and any failure hints.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from model import llm_setup


class _SetupWorker(QThread):
    """Runs the setup generator on a background thread.

    Emits *event_received* per SetupEvent and *finished_setup* when the
    generator terminates. Never raises into the UI thread — failures are
    represented as SetupEvents.
    """

    event_received = pyqtSignal(object)   # SetupEvent
    finished_setup = pyqtSignal(bool, str)  # ok, hint

    def __init__(self, host, model):
        super().__init__()
        self._host = host
        self._model = model

    def run(self):
        ok = False
        hint = ""
        try:
            for event in llm_setup.run_setup(self._host, self._model):
                self.event_received.emit(event)
                if event.done:
                    ok = event.ok
                    hint = event.hint
                    break
        except Exception as exc:
            self.event_received.emit(llm_setup.SetupEvent(
                message=f"Unexpected error: {exc}",
                done=True,
                ok=False,
                hint="",
            ))
        self.finished_setup.emit(ok, hint)


class LLMSetupDialog(QDialog):
    def __init__(self, parent, host, model):
        super().__init__(parent)
        self.setWindowTitle("LLM Setup")
        self.setMinimumSize(560, 360)
        self._host = host
        self._model = model
        self._worker = None
        self._final_ok = False
        self._final_hint = ""

        layout = QVBoxLayout(self)

        title = QLabel(
            f"Configuring LLM enrichment.\n"
            f"Host: {host}\n"
            f"Model: {model}"
        )
        layout.addWidget(title)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            "font-family: Menlo, Consolas, monospace; font-size: 12px;"
        )
        layout.addWidget(self.log, 1)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #b00; font-size: 12px;")
        layout.addWidget(self.hint_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.close_btn = QPushButton("Close")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

    def start(self):
        self._append("Starting setup...")
        self._worker = _SetupWorker(self._host, self._model)
        self._worker.event_received.connect(self._on_event)
        self._worker.finished_setup.connect(self._on_finished)
        self._worker.start()

    # ---- private ------------------------------------------------------

    def _append(self, text):
        self.log.appendPlainText(text)

    def _on_event(self, event):
        self._append(event.message)
        if event.done:
            if event.ok:
                self._append("--- Setup OK ---")
            else:
                self._append("--- Setup failed ---")

    def _on_finished(self, ok, hint):
        self._final_ok = bool(ok)
        self._final_hint = hint or ""
        if not ok and hint:
            self.hint_label.setText(hint)
        self.close_btn.setEnabled(True)

    # ---- public API ---------------------------------------------------

    def succeeded(self):
        return self._final_ok

    def hint(self):
        return self._final_hint
