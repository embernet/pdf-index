import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog, QMenuBar,
    QMenu, QLabel, QVBoxLayout, QSizePolicy, QPushButton, QTextBrowser,
    QProgressBar
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from view.keyword_editor import KeywordEditor
from view.exclude_editor import ExcludeEditor
from view.stopwords_editor import StopwordsEditor
from view.pdf_viewer import PDFViewer
from view.controls_output import ControlsOutput
from view.collapsible_panel import CollapsiblePanel
from version import __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf-indexer")
        self.resize(1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(4, 2, 4, 4)
        self.central_widget.setLayout(main_layout)

        # Header row: version label + help button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.version_label = QLabel(f"pdf-indexer  v{__version__}")
        self.version_label.setStyleSheet("font-weight: bold; color: #555;")
        header_layout.addWidget(self.version_label)
        header_layout.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setFixedHeight(16)
        header_layout.addWidget(self.progress_bar)

        self.help_btn = QPushButton("? Help")
        self.help_btn.setCheckable(True)
        self.help_btn.setFixedWidth(70)
        self.help_btn.clicked.connect(self._toggle_help)
        header_layout.addWidget(self.help_btn)

        header_widget = QWidget()
        header_widget.setLayout(header_layout)
        header_widget.setFixedHeight(header_widget.sizeHint().height())
        header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(header_widget)

        # Splitter to hold the 3 panes
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter, 1)  # stretch=1 so splitter gets all remaining space

        # Left pane: collapsible panels for keywords, excludes, stopwords
        self.keyword_editor = KeywordEditor()
        self.exclude_editor = ExcludeEditor()
        self.stopwords_editor = StopwordsEditor()

        self.keyword_panel = CollapsiblePanel("Keywords", self.keyword_editor, expanded=True)
        self.exclude_panel = CollapsiblePanel("Exclude List", self.exclude_editor, expanded=True)
        self.stopwords_panel = CollapsiblePanel("Stop Words", self.stopwords_editor, expanded=False)

        self._panels = [self.keyword_panel, self.exclude_panel, self.stopwords_panel]
        # Track expansion order (most-recently-expanded last)
        self._expand_order = [self.keyword_panel, self.exclude_panel]

        self.left_pane = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)
        self.left_pane.setLayout(self.left_layout)

        for panel in self._panels:
            self.left_layout.addWidget(panel)
            panel.toggled.connect(self._on_panel_toggled)

        self._update_panel_stretches()

        self.pdf_viewer = PDFViewer()
        self.controls_output = ControlsOutput()

        # Allow the user to drag the PDF pane much wider by setting
        # small minimum widths on the flanking panes.
        self.left_pane.setMinimumWidth(120)
        self.controls_output.setMinimumWidth(150)

        # Help panel (hidden by default)
        self.help_panel = QTextBrowser()
        self.help_panel.setOpenExternalLinks(True)
        self.help_panel.setVisible(False)
        self._load_help_content()

        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.pdf_viewer)
        self.splitter.addWidget(self.controls_output)
        self.splitter.addWidget(self.help_panel)

        # Set stretch factors (approx 20%, 50%, 30%)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setStretchFactor(3, 3)

        # Menu Bar
        self.menu_bar = self.menuBar()
        self.file_menu = self.menu_bar.addMenu("File")

        self.action_new_project = QAction("Create Project...", self)
        self.action_open_project = QAction("Open Project Folder...", self)
        self.action_import_pdf = QAction("Import PDF...", self)

        self.file_menu.addAction(self.action_new_project)
        self.file_menu.addAction(self.action_open_project)
        self.file_menu.addAction(self.action_import_pdf)

    # ------------------------------------------------------------------
    # Help panel
    # ------------------------------------------------------------------

    def _load_help_content(self):
        help_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "HELP.md",
        )
        try:
            with open(help_path, "r", encoding="utf-8") as f:
                self.help_panel.setMarkdown(f.read())
        except FileNotFoundError:
            self.help_panel.setPlainText("HELP.md not found.")

    def _toggle_help(self, checked):
        self.help_panel.setVisible(checked)

    # ------------------------------------------------------------------
    # Collapsible panel management (max 2 open at once)
    # ------------------------------------------------------------------

    def _on_panel_toggled(self, panel, expanded):
        if expanded:
            self._expand_order.append(panel)
            # If more than 2 are now open, close the oldest
            while len(self._expand_order) > 2:
                oldest = self._expand_order.pop(0)
                oldest.set_expanded(False)
        else:
            if panel in self._expand_order:
                self._expand_order.remove(panel)

        self._update_panel_stretches()

    def _update_panel_stretches(self):
        for i, panel in enumerate(self._panels):
            stretch = 1 if panel.is_expanded() else 0
            self.left_layout.setStretchFactor(panel, stretch)

    # ------------------------------------------------------------------

    def set_progress(self, value):
        self.progress_bar.setValue(value)
        if value >= 100:
            self.progress_bar.setVisible(False)

    def show_error(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error", message)

    def show_info(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", message)
