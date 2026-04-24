from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QTextBrowser, QButtonGroup, QRadioButton, QCheckBox, QSpinBox, QLabel, QScrollArea, QTabBar, QLineEdit
from PyQt6.QtCore import pyqtSignal, Qt, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QAction, QTextCursor
from view.merge_view import MergeView

TAB_MODES = ["active", "markdown", "text", "html", "tag_cloud", "merge"]
TAB_LABELS = ["Active", "Markdown", "Text", "HTML", "Tag Cloud", "Merge"]
SOURCE_TABS = {"markdown", "text", "html", "active"}

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
    cloud_submode_changed = pyqtSignal(str)  # "all", "in_index", "not_in_index"
    exclude_entry_requested = pyqtSignal(str)
    proper_noun_requested = pyqtSignal(str)  # natural-order name to mark as place/thing
    mark_as_person_requested = pyqtSignal(str)  # name (natural order) to mark as person
    merge_entry_requested = pyqtSignal(str)   # source keyword to merge

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

        # Output Area
        self.output_layout = QVBoxLayout()
        
        # View Tabs
        self.view_tabs = QTabBar()
        self.view_tabs.setExpanding(False)
        for label in TAB_LABELS:
            self.view_tabs.addTab(label)
        self.view_tabs.setCurrentIndex(0)
        self.view_tabs.currentChanged.connect(self._on_tab_changed)

        self.view_source_chk = QCheckBox("View Source")

        tab_layout = QHBoxLayout()
        tab_layout.addWidget(self.view_tabs, 1)
        tab_layout.addWidget(self.view_source_chk)

        self.output_layout.addLayout(tab_layout)

        # Search / filter bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter index...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._apply_filter)
        self.output_layout.addWidget(self.search_input)

        # Stored content for filtering
        self._raw_content = ""
        self._raw_format = "text"
        self._total_entry_count = 0

        # Stacked widgets manually managed via visibility
        self.output_text = QTextBrowser()
        self.output_text.setOpenExternalLinks(False)
        self.output_text.setOpenLinks(False)
        self.output_text.anchorClicked.connect(self.handle_link_click)
        self.output_text.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.output_text.customContextMenuRequested.connect(self.show_output_context_menu)
        self.output_layout.addWidget(self.output_text)
        
        # Cloud sub-mode bar (All / In Index / Not in Index)
        self.cloud_submode_bar = QWidget()
        submode_layout = QHBoxLayout()
        submode_layout.setContentsMargins(0, 2, 0, 2)
        self.cloud_submode_bar.setLayout(submode_layout)

        self.submode_bg = QButtonGroup(self)
        self.submode_all_btn = QRadioButton("All")
        self.submode_in_index_btn = QRadioButton("In Index")
        self.submode_not_in_index_btn = QRadioButton("Not in Index")
        self.submode_all_btn.setChecked(True)

        for btn in (self.submode_all_btn, self.submode_in_index_btn, self.submode_not_in_index_btn):
            self.submode_bg.addButton(btn)
            submode_layout.addWidget(btn)
        submode_layout.addStretch()

        self.submode_bg.buttonClicked.connect(self._on_submode_changed)
        self.cloud_submode_bar.setVisible(False)
        self.output_layout.addWidget(self.cloud_submode_bar)

        self.cloud_hint_label = QLabel("")
        self.cloud_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cloud_hint_label.setStyleSheet("color: #666; font-style: italic;")
        self.cloud_hint_label.setVisible(False)
        self.output_layout.addWidget(self.cloud_hint_label)

        self.cloud_label = CloudLabel()
        self.cloud_label.setVisible(False)
        self.cloud_label.word_clicked.connect(self.cloud_word_clicked.emit)

        # Scroll area for cloud if large
        self.cloud_scroll = QScrollArea()
        self.cloud_scroll.setWidget(self.cloud_label)
        self.cloud_scroll.setWidgetResizable(True)
        self.cloud_scroll.setVisible(False)
        self.output_layout.addWidget(self.cloud_scroll)

        # Merge tool view
        self.merge_view = MergeView()
        self.merge_view.setVisible(False)
        self.output_layout.addWidget(self.merge_view)

        self.layout.addLayout(self.output_layout)

    def set_output(self, content, format_type='text'):
        # Hide all first
        self.output_text.setVisible(False)
        self.cloud_scroll.setVisible(False)
        self.cloud_submode_bar.setVisible(False)
        self.cloud_hint_label.setVisible(False)
        self.merge_view.setVisible(False)

        if format_type == 'merge':
            self.merge_view.setVisible(True)
            self.search_input.setVisible(False)
            return

        if format_type == 'tag_cloud':
            self.cloud_scroll.setVisible(True)
            self.search_input.setVisible(False)
            self.cloud_submode_bar.setVisible(True)
            self._update_cloud_hint()
            self.cloud_hint_label.setVisible(True)
            return

        self.search_input.setVisible(True)
        self._raw_content = content
        self._raw_format = format_type
        self._apply_filter()

    def _render_content(self, content, format_type):
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

    def _apply_filter(self):
        """Filter the displayed index to lines containing the search text."""
        query = self.search_input.text().strip().lower()
        if not query:
            self._render_content(self._raw_content, self._raw_format)
            self._update_entry_count_label()
            return

        content = self._raw_content
        fmt = self._raw_format
        filtered_count = 0

        if fmt in ('html', 'active'):
            # Filter <div> lines; keep header and wrapper lines
            filtered = []
            for line in content.split('\n'):
                lower = line.lower()
                if '<div>' in lower:
                    if query in lower:
                        filtered.append(line)
                        filtered_count += 1
                else:
                    filtered.append(line)
            self._render_content('\n'.join(filtered), fmt)
        elif fmt == 'markdown':
            # First line is the header; remaining are entry lines
            lines = content.split('\n')
            filtered = [lines[0]] if lines else []
            for line in lines[1:]:
                if query in line.lower():
                    filtered.append(line)
                    filtered_count += 1
            self._render_content('\n'.join(filtered), fmt)
        else:
            # Plain text
            lines = content.split('\n')
            filtered = [lines[0]] if lines else []
            for line in lines[1:]:
                if query in line.lower():
                    filtered.append(line)
                    filtered_count += 1
            self._render_content('\n'.join(filtered), fmt)

        self._update_entry_count_label(filtered_count)

    def _update_entry_count_label(self, filtered_count=None):
        """Update the entry count label, showing filtered/total when filtering."""
        total = self._total_entry_count
        if filtered_count is not None and total > 0:
            self.entry_count_label.setText(f"{filtered_count}/{total} entries")
        elif total > 0:
            self.entry_count_label.setText(f"{total} entries")

    def set_cloud_data(self, image, layout):
        self.cloud_label.set_cloud_data(image, layout)
        # Ensure sizing
        self.cloud_label.adjustSize()

    def get_cloud_submode(self):
        """Return current cloud sub-mode: 'all', 'in_index', or 'not_in_index'."""
        if self.submode_in_index_btn.isChecked():
            return "in_index"
        if self.submode_not_in_index_btn.isChecked():
            return "not_in_index"
        return "all"

    def _update_cloud_hint(self):
        submode = self.get_cloud_submode()
        if submode == "in_index":
            self.cloud_hint_label.setText("Click a word to add it to the exclude list")
        elif submode == "not_in_index":
            self.cloud_hint_label.setText("Click a word to add it to the include list")
        else:
            self.cloud_hint_label.setText("Click a word to toggle it in the include list")

    def _on_submode_changed(self, btn):
        self._update_cloud_hint()
        self.cloud_submode_changed.emit(self.get_cloud_submode())

    def get_strategy(self):
        return "physical" if self.radio_physical.isChecked() else "logical"

    def get_offset(self):
        return self.offset_spin.value()

    def get_view_mode(self):
        idx = self.view_tabs.currentIndex()
        return TAB_MODES[idx] if 0 <= idx < len(TAB_MODES) else "markdown"

    def _on_tab_changed(self, index):
        mode = TAB_MODES[index] if 0 <= index < len(TAB_MODES) else "markdown"
        self.view_source_chk.setVisible(mode in SOURCE_TABS)

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

            merge_action = QAction(f'Merge "{keyword}" into…', self)
            merge_action.triggered.connect(
                lambda checked, k=keyword: self.merge_entry_requested.emit(k)
            )
            exclude_action = QAction(f'Exclude "{keyword}"', self)
            exclude_action.triggered.connect(
                lambda checked, k=keyword: self.exclude_entry_requested.emit(k)
            )

            actions_to_insert = [merge_action, exclude_action]

            # Inverted entry ("Surname, Firstname") → offer to flip to place/thing
            if ", " in keyword:
                parts = keyword.split(", ", 1)
                natural_form = f"{parts[1].strip()} {parts[0].strip()}"
                proper_noun_action = QAction(
                    f'Mark "{natural_form}" as place/thing name (not a person)', self
                )
                proper_noun_action.triggered.connect(
                    lambda checked, n=natural_form: self.proper_noun_requested.emit(n)
                )
                actions_to_insert.append(proper_noun_action)
            # 2-word natural-order entry (no comma) → offer to flip to person
            elif " " in keyword and "," not in keyword and keyword.count(" ") == 1:
                mark_person_action = QAction(
                    f'Mark "{keyword}" as person name (will be inverted)', self
                )
                mark_person_action.triggered.connect(
                    lambda checked, n=keyword: self.mark_as_person_requested.emit(n)
                )
                actions_to_insert.append(mark_person_action)

            if first:
                for action in actions_to_insert:
                    menu.insertAction(first, action)
                menu.insertSeparator(first)
            else:
                for action in actions_to_insert:
                    menu.addAction(action)

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
        
        # Set View Mode (migrate legacy "index_cloud" to "tag_cloud")
        mode = config.get("view_mode", "markdown")
        if mode == "index_cloud":
            mode = "tag_cloud"
        if mode in TAB_MODES:
            self.view_tabs.setCurrentIndex(TAB_MODES.index(mode))
        else:
            self.view_tabs.setCurrentIndex(0)
            
        # Set Options
        self.capitalize_chk.setChecked(config.get("capitalize", False))
        self.name_indexing_chk.setChecked(config.get("name_indexing", False))
        self.bold_indexing_chk.setChecked(config.get("bold_indexing", False))
        self.view_source_chk.setChecked(config.get("view_source", False))

    def scroll_to_term(self, term):
        """Scroll the output view to the given index term and highlight it.

        The index is rendered as lines of the form ``<b>Term</b>: pages``
        (Active/HTML) or ``**Term**: pages`` (Markdown/Text).  We need to
        match the *bold heading* for the term, not an accidental substring
        inside another entry (e.g. searching for "Once" must not land on
        "C**once**rto").

        Strategy: first try an exact bold-tag match in the underlying HTML
        (``<b>Term</b>``), falling back to a whole-word plain-text search,
        and finally a plain substring search as a last resort.
        """
        if not self.output_text.isVisible():
            return

        # Clear any previous extra selections
        self.output_text.setExtraSelections([])

        from PyQt6.QtGui import QTextCharFormat, QTextDocument

        # Move cursor to start so we search the whole document
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.output_text.setTextCursor(cursor)

        found = False

        # Strategy 1: search the raw HTML for <b>Term</b> and position
        # the cursor at that text so the view scrolls to it.
        html = self.output_text.toHtml()
        import re
        # Match the bold entry heading — case-insensitive
        pattern = re.compile(
            r'<b>' + re.escape(term) + r'</b>',
            re.IGNORECASE,
        )
        m = pattern.search(html)
        if m:
            # Use QTextEdit.find with the exact term text — but first
            # jump close to the right position using a plain-text cursor
            # search so the visual scroll lands correctly.
            # QTextEdit.find with FindWholeWords avoids substring hits.
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.output_text.setTextCursor(cursor)
            flags = QTextDocument.FindFlag.FindWholeWords
            found = self.output_text.find(term, flags)

        # Strategy 2: whole-word search (no HTML introspection needed)
        if not found:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.output_text.setTextCursor(cursor)
            flags = QTextDocument.FindFlag.FindWholeWords
            found = self.output_text.find(term, flags)

        # Strategy 3: plain substring (last resort)
        if not found:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.output_text.setTextCursor(cursor)
            found = self.output_text.find(term)

        if found:
            # find() already selected the text and scrolled to it.
            # Apply a persistent gold highlight so it stays visible
            # after the user clicks elsewhere.
            sel = QTextEdit.ExtraSelection()
            sel.cursor = self.output_text.textCursor()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 200, 50))
            sel.format = fmt
            self.output_text.setExtraSelections([sel])
