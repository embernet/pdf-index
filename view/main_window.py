from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog, QMenuBar, QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt

from view.keyword_editor import KeywordEditor
from view.exclude_editor import ExcludeEditor
from view.pdf_viewer import PDFViewer
from view.controls_output import ControlsOutput

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Indexer")
        self.resize(1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QHBoxLayout()
        self.central_widget.setLayout(self.layout)

        # Splitter to hold the 3 panes
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout.addWidget(self.splitter)

        # Left pane: vertical splitter with keywords (2/3) and excludes (1/3)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.keyword_editor = KeywordEditor()
        self.exclude_editor = ExcludeEditor()
        self.left_splitter.addWidget(self.keyword_editor)
        self.left_splitter.addWidget(self.exclude_editor)
        self.left_splitter.setStretchFactor(0, 2)
        self.left_splitter.setStretchFactor(1, 1)

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
        # Could use MessageBox standard dialog
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Error", message)

    def show_info(self, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", message)
