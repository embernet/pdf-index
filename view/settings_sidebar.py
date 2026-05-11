"""Right-hand settings sidebar with all index-creation controls.

Owns every checkbox/radio/spin previously housed at the top of
ControlsOutput. Toggleable via the cog button in the main window header.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QRadioButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)


class SettingsSidebar(QWidget):
    create_index_requested = pyqtSignal()
    llm_setup_requested = pyqtSignal()
    llm_enrich_requested = pyqtSignal()
    llm_status_check_requested = pyqtSignal()
    llm_pause_requested = pyqtSignal()
    llm_cancel_requested = pyqtSignal()
    llm_resume_requested = pyqtSignal()
    llm_discard_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(220)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setLayout(outer)

        # Header bar
        header = QWidget()
        header.setStyleSheet("background: #e8e8e8;")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 4, 4, 4)
        header.setLayout(header_layout)
        title = QLabel("Settings")
        title.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        outer.addWidget(header)
        outer.addWidget(self._sep())

        # Create Index button — pinned at the top of the sidebar so the
        # primary action is always one click away regardless of which
        # section the user is scrolled to.
        top_button_row = QWidget()
        top_button_layout = QHBoxLayout()
        top_button_layout.setContentsMargins(10, 8, 10, 8)
        top_button_row.setLayout(top_button_layout)
        self.create_btn = QPushButton("Create Index")
        self.create_btn.setStyleSheet(
            "QPushButton { background: #b3d9ff; border: 1px solid #6fa8dc; "
            "border-radius: 4px; padding: 8px 16px; font-weight: bold; "
            "color: #1a1a1a; }"
            "QPushButton:hover { background: #c4e1ff; }"
            "QPushButton:pressed { background: #9bc7f0; }"
            "QPushButton:disabled { background: #e0e0e0; color: #888; "
            "border-color: #ccc; }"
        )
        self.create_btn.clicked.connect(self.create_index_requested.emit)
        top_button_layout.addWidget(self.create_btn)
        outer.addWidget(top_button_row)
        outer.addWidget(self._sep())

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        body.setLayout(layout)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # ---- Page numbering ------------------------------------------------
        layout.addWidget(self._heading("Page Numbering"))

        self.strategy_bg = QButtonGroup(self)
        self.radio_physical = QRadioButton("Physical Page")
        self.radio_logical = QRadioButton("Logical Label")
        self.strategy_bg.addButton(self.radio_physical)
        self.strategy_bg.addButton(self.radio_logical)
        self.radio_logical.setChecked(True)
        layout.addWidget(self.radio_physical)
        layout.addWidget(self.radio_logical)

        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("Offset:"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-500, 500)
        self.offset_spin.setValue(0)
        offset_row.addWidget(self.offset_spin)
        offset_row.addStretch()
        layout.addLayout(offset_row)

        self.index_from_offset_chk = QCheckBox("Index only from offset")
        self.index_from_offset_chk.setChecked(True)
        layout.addWidget(self.index_from_offset_chk)

        self.index_front_matter_chk = QCheckBox("Index front matter (roman)")
        self.index_front_matter_chk.setChecked(True)
        self.index_front_matter_chk.setEnabled(False)
        layout.addWidget(self.index_front_matter_chk)

        layout.addSpacing(8)
        layout.addWidget(self._sep())
        layout.addSpacing(4)

        # ---- Indexing -----------------------------------------------------
        layout.addWidget(self._heading("Indexing"))

        self.name_indexing_chk = QCheckBox("Name Indexing")
        self.name_indexing_chk.setChecked(False)
        layout.addWidget(self.name_indexing_chk)

        self.index_capitalised_chk = QCheckBox("Index Capitalised")
        self.index_capitalised_chk.setChecked(True)
        layout.addWidget(self.index_capitalised_chk)

        self.index_italic_chk = QCheckBox("Index Italic")
        self.index_italic_chk.setChecked(True)
        layout.addWidget(self.index_italic_chk)

        self.bold_indexing_chk = QCheckBox("Index Bold Text")
        self.bold_indexing_chk.setChecked(False)
        layout.addWidget(self.bold_indexing_chk)

        self.index_single_quotes_chk = QCheckBox("Index Single Quotes")
        self.index_single_quotes_chk.setChecked(True)
        layout.addWidget(self.index_single_quotes_chk)

        self.surname_first_chk = QCheckBox("Surname First")
        self.surname_first_chk.setChecked(False)
        self.surname_first_chk.setEnabled(False)
        layout.addWidget(self.surname_first_chk)

        # Sub-options only enabled when Name Indexing is on.
        self.name_indexing_chk.toggled.connect(self.surname_first_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.index_capitalised_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.index_italic_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.bold_indexing_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.index_single_quotes_chk.setEnabled)

        layout.addSpacing(8)
        layout.addWidget(self._sep())
        layout.addSpacing(4)

        # ---- Output -------------------------------------------------------
        layout.addWidget(self._heading("Output"))

        self.capitalize_chk = QCheckBox("Capitalize Entries")
        self.capitalize_chk.setChecked(False)
        layout.addWidget(self.capitalize_chk)

        self.separate_style_files_chk = QCheckBox("Separate index files by style")
        self.separate_style_files_chk.setChecked(True)
        layout.addWidget(self.separate_style_files_chk)

        layout.addSpacing(8)
        layout.addWidget(self._sep())
        layout.addSpacing(4)

        # ---- LLM Enrichment (optional) ------------------------------------
        layout.addWidget(self._heading("LLM Enrichment (optional)"))

        # Status indicator + master toggle
        self.llm_status_label = QLabel("Status: not checked")
        self.llm_status_label.setStyleSheet("color: #777; font-size: 11px;")
        self.llm_status_label.setWordWrap(True)
        layout.addWidget(self.llm_status_label)

        self.llm_enrichment_chk = QCheckBox("Enable LLM enrichment")
        self.llm_enrichment_chk.setChecked(False)
        layout.addWidget(self.llm_enrichment_chk)

        self.llm_help_label = QLabel(
            "Outputs go to separate <book>.enhanced.* files. The current "
            "rule-based index is never modified."
        )
        self.llm_help_label.setStyleSheet("color: #777; font-size: 11px;")
        self.llm_help_label.setWordWrap(True)
        layout.addWidget(self.llm_help_label)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Host:"))
        self.llm_host_edit = QLineEdit("http://localhost:11434")
        self.llm_host_edit.setMinimumWidth(140)
        host_row.addWidget(self.llm_host_edit, 1)
        layout.addLayout(host_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.llm_model_edit = QLineEdit("qwen2.5:7b")
        self.llm_model_edit.setMinimumWidth(140)
        model_row.addWidget(self.llm_model_edit, 1)
        layout.addLayout(model_row)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Sub-index threshold:"))
        self.llm_threshold_spin = QSpinBox()
        self.llm_threshold_spin.setRange(2, 200)
        self.llm_threshold_spin.setValue(8)
        threshold_row.addWidget(self.llm_threshold_spin)
        threshold_row.addStretch()
        layout.addLayout(threshold_row)

        # Per-feature toggles
        self.llm_subindex_chk = QCheckBox("Sub-index dense entries")
        self.llm_subindex_chk.setChecked(True)
        layout.addWidget(self.llm_subindex_chk)

        self.llm_alias_chk = QCheckBox("Suggest alias / synonym merges")
        self.llm_alias_chk.setChecked(True)
        layout.addWidget(self.llm_alias_chk)

        self.llm_category_chk = QCheckBox("Tag entries with categories")
        self.llm_category_chk.setChecked(True)
        layout.addWidget(self.llm_category_chk)

        self.llm_seealso_chk = QCheckBox("Suggest see-also cross-references")
        self.llm_seealso_chk.setChecked(True)
        layout.addWidget(self.llm_seealso_chk)

        # Action buttons
        button_row = QHBoxLayout()
        self.llm_setup_btn = QPushButton("Run setup")
        self.llm_setup_btn.setToolTip(
            "Check Ollama is running, pull the configured model, and verify "
            "with a smoke test."
        )
        self.llm_setup_btn.clicked.connect(self.llm_setup_requested.emit)
        button_row.addWidget(self.llm_setup_btn)

        self.llm_enrich_btn = QPushButton("Enrich with LLM")
        self.llm_enrich_btn.setToolTip(
            "Run LLM enrichment over the current index. Writes to "
            "<book>.enhanced.* files."
        )
        self.llm_enrich_btn.setEnabled(False)
        self.llm_enrich_btn.clicked.connect(self.llm_enrich_requested.emit)
        button_row.addWidget(self.llm_enrich_btn)
        layout.addLayout(button_row)

        # Progress strip — only visible while a run is in flight.
        self.llm_progress_strip = QFrame()
        progress_layout = QVBoxLayout(self.llm_progress_strip)
        progress_layout.setContentsMargins(0, 4, 0, 4)
        self.llm_progress_bar = QProgressBar()
        self.llm_progress_bar.setRange(0, 1)
        self.llm_progress_bar.setValue(0)
        self.llm_progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.llm_progress_bar)
        self.llm_progress_label = QLabel("")
        self.llm_progress_label.setWordWrap(True)
        self.llm_progress_label.setStyleSheet("color: #444; font-size: 11px;")
        progress_layout.addWidget(self.llm_progress_label)
        run_action_row = QHBoxLayout()
        self.llm_pause_btn = QPushButton("Pause")
        self.llm_pause_btn.setToolTip("Stop after current task; resume later.")
        self.llm_pause_btn.clicked.connect(self.llm_pause_requested.emit)
        run_action_row.addWidget(self.llm_pause_btn)
        self.llm_cancel_btn = QPushButton("Cancel")
        self.llm_cancel_btn.setToolTip("Stop and discard run state.")
        self.llm_cancel_btn.clicked.connect(self.llm_cancel_requested.emit)
        run_action_row.addWidget(self.llm_cancel_btn)
        progress_layout.addLayout(run_action_row)
        self.llm_progress_strip.setVisible(False)
        layout.addWidget(self.llm_progress_strip)

        # Resume banner — only visible when a paused / interrupted run is
        # detected on disk.
        self.llm_banner = QFrame()
        self.llm_banner.setStyleSheet(
            "background: #fff7d6; border: 1px solid #d9b900; padding: 4px;"
        )
        banner_layout = QVBoxLayout(self.llm_banner)
        banner_layout.setContentsMargins(6, 4, 6, 4)
        self.llm_banner_label = QLabel("")
        self.llm_banner_label.setWordWrap(True)
        self.llm_banner_label.setStyleSheet("color: #5a4400; font-size: 11px;")
        banner_layout.addWidget(self.llm_banner_label)
        banner_btn_row = QHBoxLayout()
        self.llm_resume_btn = QPushButton("Resume")
        self.llm_resume_btn.clicked.connect(self.llm_resume_requested.emit)
        banner_btn_row.addWidget(self.llm_resume_btn)
        self.llm_discard_btn = QPushButton("Discard")
        self.llm_discard_btn.clicked.connect(self.llm_discard_requested.emit)
        banner_btn_row.addWidget(self.llm_discard_btn)
        banner_layout.addLayout(banner_btn_row)
        self.llm_banner.setVisible(False)
        layout.addWidget(self.llm_banner)

        # Sub-feature toggles only meaningful when master toggle is on.
        for chk in (
            self.llm_subindex_chk, self.llm_alias_chk,
            self.llm_category_chk, self.llm_seealso_chk,
            self.llm_threshold_spin, self.llm_host_edit,
            self.llm_model_edit, self.llm_setup_btn,
        ):
            chk.setEnabled(False)
        self.llm_enrichment_chk.toggled.connect(self._on_llm_master_toggled)

        layout.addStretch(1)

        # Wiring
        self.offset_spin.valueChanged.connect(self._on_offset_changed)
        self.index_from_offset_chk.toggled.connect(
            lambda _: self._on_offset_changed(self.offset_spin.value())
        )
        self._on_offset_changed(self.offset_spin.value())

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _heading(text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "font-weight: bold; color: #555; text-transform: uppercase; "
            "font-size: 11px; margin-bottom: 2px;"
        )
        return lbl

    @staticmethod
    def _sep():
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _on_offset_changed(self, value):
        self.index_from_offset_chk.setEnabled(value < 0)
        self.index_front_matter_chk.setEnabled(
            value < 0 and self.index_from_offset_chk.isChecked()
        )

    def _on_llm_master_toggled(self, checked):
        for w in (
            self.llm_subindex_chk, self.llm_alias_chk,
            self.llm_category_chk, self.llm_seealso_chk,
            self.llm_threshold_spin, self.llm_host_edit,
            self.llm_model_edit, self.llm_setup_btn,
        ):
            w.setEnabled(checked)
        if not checked:
            self.llm_enrich_btn.setEnabled(False)
            self.set_llm_status("LLM enrichment off.", colour="#777")
        else:
            self.llm_status_check_requested.emit()

    # ---- LLM status / gating -------------------------------------------

    def set_llm_status(self, text, colour="#777"):
        self.llm_status_label.setText(f"Status: {text}")
        self.llm_status_label.setStyleSheet(
            f"color: {colour}; font-size: 11px;"
        )

    def set_llm_enrich_enabled(self, enabled):
        self.llm_enrich_btn.setEnabled(bool(enabled))

    # ---- LLM run-state UI -----------------------------------------------

    def show_llm_progress(self, total):
        self.llm_progress_bar.setRange(0, max(int(total), 1))
        self.llm_progress_bar.setValue(0)
        self.llm_progress_label.setText(f"0 / {total} — starting...")
        self.llm_progress_strip.setVisible(True)
        self.llm_pause_btn.setEnabled(True)
        self.llm_cancel_btn.setEnabled(True)

    def update_llm_progress(self, done, total, label):
        if total > 0 and self.llm_progress_bar.maximum() != total:
            self.llm_progress_bar.setRange(0, total)
        self.llm_progress_bar.setValue(min(done, max(total, 1)))
        self.llm_progress_label.setText(
            f"{done} / {total} — {label}" if label else f"{done} / {total}"
        )

    def hide_llm_progress(self):
        self.llm_progress_strip.setVisible(False)

    def set_llm_progress_buttons_enabled(self, enabled):
        self.llm_pause_btn.setEnabled(bool(enabled))
        self.llm_cancel_btn.setEnabled(bool(enabled))

    def show_llm_resume_banner(self, message, allow_resume=True):
        self.llm_banner_label.setText(message)
        self.llm_resume_btn.setVisible(bool(allow_resume))
        self.llm_banner.setVisible(True)

    def hide_llm_resume_banner(self):
        self.llm_banner.setVisible(False)

    def set_llm_enrich_button_label(self, text):
        self.llm_enrich_btn.setText(text)

    # ---- public API used by the controller --------------------------------

    def get_strategy(self):
        return "physical" if self.radio_physical.isChecked() else "logical"

    def get_offset(self):
        return self.offset_spin.value()

    def set_state(self, config):
        if config.get("strategy") == "physical":
            self.radio_physical.setChecked(True)
        else:
            self.radio_logical.setChecked(True)
        self.offset_spin.setValue(config.get("offset", 0))
        self.index_from_offset_chk.setChecked(config.get("index_from_offset", True))
        self.index_front_matter_chk.setChecked(
            config.get("index_front_matter_roman", True)
        )
        self.capitalize_chk.setChecked(config.get("capitalize", False))
        self.name_indexing_chk.setChecked(config.get("name_indexing", False))
        self.index_capitalised_chk.setChecked(config.get("index_capitalised", True))
        self.index_italic_chk.setChecked(config.get("index_italic", True))
        self.bold_indexing_chk.setChecked(config.get("bold_indexing", False))
        self.index_single_quotes_chk.setChecked(config.get("index_single_quotes", True))
        self.surname_first_chk.setChecked(config.get("surname_first", False))
        self.separate_style_files_chk.setChecked(
            config.get("separate_style_files", True)
        )
        self.llm_enrichment_chk.setChecked(config.get("llm_enrichment_enabled", False))
        self.llm_host_edit.setText(config.get("llm_host", "http://localhost:11434"))
        self.llm_model_edit.setText(config.get("llm_model", "qwen2.5:7b"))
        self.llm_threshold_spin.setValue(config.get("llm_subindex_threshold", 8))
        self.llm_subindex_chk.setChecked(config.get("llm_subindex_enabled", True))
        self.llm_alias_chk.setChecked(config.get("llm_alias_enabled", True))
        self.llm_category_chk.setChecked(config.get("llm_category_enabled", True))
        self.llm_seealso_chk.setChecked(config.get("llm_seealso_enabled", True))
        # Re-fire master toggle to enforce sub-control enabled state.
        self._on_llm_master_toggled(self.llm_enrichment_chk.isChecked())
