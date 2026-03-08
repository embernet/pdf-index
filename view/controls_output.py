from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QProgressBar, QTextEdit, QTextBrowser, QButtonGroup, QRadioButton, QCheckBox, QSpinBox, QLabel, QScrollArea
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QAction, QTextCursor

class CloudLabel(QLabel):
    word_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.layout_data = [] # List of dicts {word, rect, orientation}
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # self.setScaledContents(False) # We want exact pixels for hit testing

    def set_cloud_data(self, q_image, layout_data):
        self.setPixmap(QPixmap.fromImage(q_image))
        self.layout_data = layout_data
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            # Map pos to pixmap coords if centered?
            # Alignment is center.
            pix = self.pixmap()
            if not pix: return
            
            x_off = (self.width() - pix.width()) // 2
            y_off = (self.height() - pix.height()) // 2
            
            img_x = pos.x() - x_off
            img_y = pos.y() - y_off
            
            # Hit test
            for item in self.layout_data:
                x, y, w, h = item['rect']
                orientation = item['orientation']
                
                # Simple box check
                # If rotated, we should swap w/h for detection logic roughly
                if orientation is not None:
                     # Assume 90 deg rotation for now if simple
                     # Pivot is usually top-left or bottom-left depending on lib.
                     # Let's try flexible hit: (x, y) is insertion point.
                     # Rotated text goes UP usually in PIL? Or Down?
                     # WordCloud draws on mask.
                     
                     # Let's just assume generous padding.
                     # If click is near (x,y) within size*len?
                     # Better: Check both variants (vertical/horizontal) to be safe or debug.
                     
                     # Simple hack: check distance to center.
                     center_x = x + w/2
                     center_y = y + h/2
                     # Check radius?
                     pass
                
                # Strict check for unrotated
                if x <= img_x <= x + w and y <= img_y <= y + h:
                    self.word_clicked.emit(item['word'])
                    return
                    
                # Loose check for rotated (swap dims)
                if orientation is not None:
                     if x <= img_x <= x + h and y <= img_y <= y + w:
                          self.word_clicked.emit(item['word'])
                          return

class ControlsOutput(QWidget):
    create_index_requested = pyqtSignal()
    active_link_clicked = pyqtSignal(str) # Emits page number string or cloud action
    cloud_word_clicked = pyqtSignal(str)
    exclude_entry_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Controls Group
        self.controls_layout = QHBoxLayout()
        
        # Strategy
        self.strategy_bg = QButtonGroup(self)
        self.radio_physical = QRadioButton("Physical Page")
        self.radio_logical = QRadioButton("Logical Label")
        self.strategy_bg.addButton(self.radio_physical)
        self.strategy_bg.addButton(self.radio_logical)
        self.radio_logical.setChecked(True)
        
        self.controls_layout.addWidget(QLabel("Page Strategy:"))
        self.controls_layout.addWidget(self.radio_physical)
        self.controls_layout.addWidget(self.radio_logical)
        
        # Offset
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-50, 50)
        self.offset_spin.setValue(1)
        self.controls_layout.addWidget(QLabel("Offset:"))
        self.controls_layout.addWidget(self.offset_spin)
        
        # Options
        self.capitalize_chk = QCheckBox("Capitalize Entries")
        self.capitalize_chk.setChecked(False)
        self.controls_layout.addWidget(self.capitalize_chk)

        self.layout.addLayout(self.controls_layout)

        # Second row: name indexing options, create button, entry count
        self.name_options_layout = QHBoxLayout()

        self.name_indexing_chk = QCheckBox("Name Indexing")
        self.name_indexing_chk.setChecked(False)
        self.name_options_layout.addWidget(self.name_indexing_chk)

        self.bold_indexing_chk = QCheckBox("Index Bold Text")
        self.bold_indexing_chk.setChecked(False)
        self.name_options_layout.addWidget(self.bold_indexing_chk)

        self.create_btn = QPushButton("Create Index")
        self.create_btn.clicked.connect(self.create_index_requested.emit)
        self.name_options_layout.addWidget(self.create_btn)

        self.entry_count_label = QLabel("")
        self.name_options_layout.addWidget(self.entry_count_label)

        self.layout.addLayout(self.name_options_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)
        
        # Output Area
        self.output_layout = QVBoxLayout()
        
        # Format Options
        self.format_layout = QHBoxLayout()
        self.format_bg = QButtonGroup(self)
        self.radio_md = QRadioButton("Markdown")
        self.radio_txt = QRadioButton("Text")
        self.radio_html = QRadioButton("HTML")
        self.radio_active = QRadioButton("Active")
        self.radio_cloud = QRadioButton("Tag Cloud")
        
        self.format_bg.addButton(self.radio_md)
        self.format_bg.addButton(self.radio_txt)
        self.format_bg.addButton(self.radio_html)
        self.format_bg.addButton(self.radio_active)
        self.format_bg.addButton(self.radio_cloud)
        
        self.radio_md.setChecked(True)
        
        self.format_layout.addWidget(QLabel("View As:"))
        self.format_layout.addWidget(self.radio_md)
        self.format_layout.addWidget(self.radio_txt)
        self.format_layout.addWidget(self.radio_html)
        self.format_layout.addWidget(self.radio_active)
        self.format_layout.addWidget(self.radio_cloud)
        
        self.view_source_chk = QCheckBox("View Source")
        self.format_layout.addStretch()
        self.format_layout.addWidget(self.view_source_chk)
        
        self.output_layout.addLayout(self.format_layout)
        
        # Stacked widgets manually managed via visibility
        self.output_text = QTextBrowser()
        self.output_text.setOpenExternalLinks(False)
        self.output_text.setOpenLinks(False)
        self.output_text.anchorClicked.connect(self.handle_link_click)
        self.output_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.output_text.customContextMenuRequested.connect(self.show_output_context_menu)
        self.output_layout.addWidget(self.output_text)
        
        self.cloud_label = CloudLabel()
        self.cloud_label.setVisible(False)
        self.cloud_label.word_clicked.connect(self.cloud_word_clicked.emit)
        
        # Scroll area for cloud if large
        self.cloud_scroll = QScrollArea()
        self.cloud_scroll.setWidget(self.cloud_label)
        self.cloud_scroll.setWidgetResizable(True)
        self.cloud_scroll.setVisible(False)
        self.output_layout.addWidget(self.cloud_scroll)
        
        self.layout.addLayout(self.output_layout)

    def set_progress(self, value):
        self.progress_bar.setValue(value)
        if value >= 100:
            self.progress_bar.setVisible(False)

    def set_output(self, content, format_type='text'):
        # Hide all first
        self.output_text.setVisible(False)
        self.cloud_scroll.setVisible(False)
        
        if format_type == 'tag_cloud':
            # content is ignored here, confusing api but okay for now
            # Actually we expect set_cloud_data to have been called?
            # Or we pass special content?
            # Let's assume controller handles data passing.
            self.cloud_scroll.setVisible(True)
            return

        self.output_text.setVisible(True)
        self.output_text.clear()
        
        if self.view_source_chk.isChecked():
             self.output_text.setPlainText(content)
             return

        if format_type == 'html' or format_type == 'active':
            self.output_text.setHtml(content)
        elif format_type == 'markdown':
             self.output_text.setMarkdown(content)
        else:
            self.output_text.setPlainText(content)

    def set_cloud_data(self, image, layout):
        self.cloud_label.set_cloud_data(image, layout)
        # Ensure sizing
        self.cloud_label.adjustSize()

    def get_strategy(self):
        return "physical" if self.radio_physical.isChecked() else "logical"

    def get_offset(self):
        return self.offset_spin.value()

    def show_output_context_menu(self, pos):
        cursor = self.output_text.cursorForPosition(pos)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        line = cursor.selectedText().strip()

        keyword = None
        if not self.view_source_chk.isChecked() and ":" in line:
            keyword = line.split(":", 1)[0].strip()

        menu = self.output_text.createStandardContextMenu()

        if keyword:
            first = menu.actions()[0] if menu.actions() else None
            exclude_action = QAction(f'Exclude "{keyword}"', self)
            exclude_action.triggered.connect(
                lambda checked, k=keyword: self.exclude_entry_requested.emit(k)
            )
            if first:
                menu.insertAction(first, exclude_action)
                menu.insertSeparator(first)
            else:
                menu.addAction(exclude_action)

        menu.exec(self.output_text.mapToGlobal(pos))

    def handle_link_click(self, url):
        # url is QUrl – use fragment() to get the decoded anchor text
        # (toString() percent-encodes characters like |)
        fragment = url.fragment()
        if fragment:
            self.active_link_clicked.emit(fragment)
             
    def set_state(self, config):
        # Set Strategy
        if config.get("strategy") == "physical":
            self.radio_physical.setChecked(True)
        else:
            self.radio_logical.setChecked(True)
            
        # Set Offset
        self.offset_spin.setValue(config.get("offset", 1))
        
        # Set View Mode
        mode = config.get("view_mode", "markdown")
        if mode == "text":
            self.radio_txt.setChecked(True)
        elif mode == "html":
            self.radio_html.setChecked(True)
        elif mode == "active":
            self.radio_active.setChecked(True)
        elif mode == "tag_cloud":
            self.radio_cloud.setChecked(True)
        else:
            self.radio_md.setChecked(True)
            
        # Set Options
        self.capitalize_chk.setChecked(config.get("capitalize", False))
        self.name_indexing_chk.setChecked(config.get("name_indexing", False))
        self.bold_indexing_chk.setChecked(config.get("bold_indexing", False))
        self.view_source_chk.setChecked(config.get("view_source", False))

    def scroll_to_term(self, term):
        """Scroll the output view to the given index term and highlight it."""
        if not self.output_text.isVisible():
            return

        # Clear any previous extra selections
        self.output_text.setExtraSelections([])

        # Move cursor to start so we search the whole document
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.output_text.setTextCursor(cursor)

        # Search for the term (case-insensitive by default)
        if self.output_text.find(term):
            # find() already selected the text and scrolled to it.
            # Apply a persistent gold highlight so it stays visible
            # after the user clicks elsewhere.
            from PyQt6.QtGui import QTextCharFormat
            sel = QTextEdit.ExtraSelection()
            sel.cursor = self.output_text.textCursor()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 200, 50))
            sel.format = fmt
            self.output_text.setExtraSelections([sel])
