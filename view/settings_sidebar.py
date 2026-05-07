"""Right-hand settings sidebar with all index-creation controls.

Owns every checkbox/radio/spin previously housed at the top of
ControlsOutput. Toggleable via the cog button in the main window header.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)


class SettingsSidebar(QWidget):
    create_index_requested = pyqtSignal()

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

        self.surname_first_chk = QCheckBox("Surname First")
        self.surname_first_chk.setChecked(False)
        self.surname_first_chk.setEnabled(False)
        layout.addWidget(self.surname_first_chk)

        # Sub-options only enabled when Name Indexing is on.
        self.name_indexing_chk.toggled.connect(self.surname_first_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.index_capitalised_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.index_italic_chk.setEnabled)
        self.name_indexing_chk.toggled.connect(self.bold_indexing_chk.setEnabled)

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
        self.surname_first_chk.setChecked(config.get("surname_first", False))
        self.separate_style_files_chk.setChecked(
            config.get("separate_style_files", True)
        )
