import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog, QMenuBar,
    QLabel, QVBoxLayout, QSizePolicy, QPushButton, QTextBrowser,
    QProgressBar, QFrame
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from view.keyword_editor import KeywordEditor
from view.exclude_editor import ExcludeEditor
from view.stopwords_editor import StopwordsEditor
from view.proper_names_editor import ProperNamesEditor
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

        self.pdf_name_label = QLabel("")
        self.pdf_name_label.setStyleSheet("color: #555;")
        header_layout.addWidget(self.pdf_name_label)

        header_layout.addStretch()

        self.progress_label = QLabel("Creating index...")
        self.progress_label.setVisible(False)
        header_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setFixedHeight(16)
        header_layout.addWidget(self.progress_bar)

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

        # Left pane: collapsible panels for keywords, excludes, stopwords, proper names
        self.keyword_editor = KeywordEditor()
        self.exclude_editor = ExcludeEditor()
        self.stopwords_editor = StopwordsEditor()
        self.proper_names_editor = ProperNamesEditor()

        self.keyword_panel = CollapsiblePanel("Include List", self.keyword_editor, expanded=True)
        self.exclude_panel = CollapsiblePanel("Exclude List", self.exclude_editor, expanded=True)
        self.stopwords_panel = CollapsiblePanel("Stop Words", self.stopwords_editor, expanded=False)
        self.proper_names_panel = CollapsiblePanel("Place/Thing Names", self.proper_names_editor, expanded=False)

        self._panels = [self.keyword_panel, self.exclude_panel, self.stopwords_panel, self.proper_names_panel]
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

        # Help panel (hidden by default) — QWidget wrapper with close button
        self.help_widget = QWidget()
        self.help_widget.setVisible(False)
        help_widget_layout = QVBoxLayout()
        help_widget_layout.setContentsMargins(0, 0, 0, 0)
        help_widget_layout.setSpacing(0)
        self.help_widget.setLayout(help_widget_layout)

        # Title bar
        help_title_bar = QWidget()
        help_title_bar.setStyleSheet("background: #e8e8e8;")
        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(6, 3, 6, 3)
        help_title_bar.setLayout(title_bar_layout)
        help_title_label = QLabel("Help")
        help_title_label.setStyleSheet("font-weight: bold;")
        help_close_btn = QPushButton("✕")
        help_close_btn.setFlat(True)
        help_close_btn.setFixedSize(20, 20)
        help_close_btn.setStyleSheet("font-size: 11px;")
        help_close_btn.clicked.connect(self._close_help)
        title_bar_layout.addWidget(help_title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(help_close_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)

        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)

        help_widget_layout.addWidget(help_title_bar)
        help_widget_layout.addWidget(sep)
        help_widget_layout.addWidget(self.help_browser)

        self._load_help_content()

        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.pdf_viewer)
        self.splitter.addWidget(self.controls_output)
        self.splitter.addWidget(self.help_widget)

        # Set stretch factors (approx 20%, 50%, 30%)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setStretchFactor(3, 6)

        # Menu Bar
        self.menu_bar = self.menuBar()
        self.file_menu = self.menu_bar.addMenu("File")

        self.action_new_project = QAction("Create Project...", self)
        self.action_open_project = QAction("Open Project Folder...", self)
        self.action_import_pdf = QAction("Import PDF...", self)

        self.file_menu.addAction(self.action_new_project)
        self.file_menu.addAction(self.action_open_project)
        self.file_menu.addAction(self.action_import_pdf)
        self.file_menu.addSeparator()
        self.action_exit = QAction("Exit", self)
        self.file_menu.addAction(self.action_exit)

        # Use a zero-width space in the menu title so macOS does not identify
        # it as the system Help menu (which would inject its own search bar).
        self.help_menu = self.menu_bar.addMenu("Help​")
        self.action_help_contents = QAction("Show/Hide Help", self)
        self.action_help_contents.triggered.connect(self._toggle_help)
        self.help_menu.addAction(self.action_help_contents)

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
                self.help_browser.setMarkdown(f.read())
        except FileNotFoundError:
            self.help_browser.setPlainText("HELP.md not found.")

    def set_pdf_name(self, filename: str | None):
        self.pdf_name_label.setText(f"—  {filename}" if filename else "")

    def _toggle_help(self):
        self.help_widget.setVisible(not self.help_widget.isVisible())

    def _close_help(self):
        self.help_widget.setVisible(False)

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

    def show_progress(self, text="Creating index..."):
        self.progress_label.setText(text)
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def hide_progress(self):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

    def set_progress(self, value):
        self.progress_bar.setValue(value)

    def show_error(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error", message)

    def show_info(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", message)
