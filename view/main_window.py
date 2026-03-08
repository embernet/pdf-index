from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog, QMenuBar,
    QMenu, QLabel, QVBoxLayout
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from view.keyword_editor import KeywordEditor
from view.exclude_editor import ExcludeEditor
from view.stopwords_editor import StopwordsEditor
from view.pdf_viewer import PDFViewer
from view.controls_output import ControlsOutput
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

        # Version / app-name header
        self.version_label = QLabel(f"pdf-indexer  v{__version__}")
        self.version_label.setStyleSheet("font-weight: bold; color: #555;")
        main_layout.addWidget(self.version_label)

        # Splitter to hold the 3 panes
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter)

        # Left pane: vertical splitter with keywords, excludes, stopwords
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setHandleWidth(6)
        self.left_splitter.setChildrenCollapsible(False)
        self.keyword_editor = KeywordEditor()
        self.exclude_editor = ExcludeEditor()
        self.stopwords_editor = StopwordsEditor()
        self.left_splitter.addWidget(self.keyword_editor)
        self.left_splitter.addWidget(self.exclude_editor)
        self.left_splitter.addWidget(self.stopwords_editor)
        self.left_splitter.setStretchFactor(0, 3)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.setStretchFactor(2, 1)

        self.pdf_viewer = PDFViewer()
        self.controls_output = ControlsOutput()

        self.splitter.addWidget(self.left_splitter)
        self.splitter.addWidget(self.pdf_viewer)
        self.splitter.addWidget(self.controls_output)

        # Set stretch factors (approx 20%, 50%, 30%)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setStretchFactor(2, 3)

        # Menu Bar
        self.menu_bar = self.menuBar()
        self.file_menu = self.menu_bar.addMenu("File")

        self.action_new_project = QAction("Create Project...", self)
        self.action_open_project = QAction("Open Project Folder...", self)
        self.action_import_pdf = QAction("Import PDF...", self)

        self.file_menu.addAction(self.action_new_project)
        self.file_menu.addAction(self.action_open_project)
        self.file_menu.addAction(self.action_import_pdf)

    def show_error(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error", message)

    def show_info(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", message)
