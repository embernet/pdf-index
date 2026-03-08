import fitz
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QHBoxLayout, QPushButton, QCheckBox, QMenu, QApplication, QSlider, QLineEdit
from PyQt6.QtGui import QPixmap, QImage, QAction, QPainter, QPen, QColor, QCursor
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QPoint, QRectF, QTimer, QEvent

class ClickableLabel(QLabel):
    # Signals for selection
    selection_changed = pyqtSignal()
    word_double_clicked = pyqtSignal(str)
    highlighted_word_clicked = pyqtSignal(str)  # emits the index term name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selection_start_index = None
        self.selection_end_index = None
        self.is_selecting = False

        # Word data: list of tuples (x0, y0, x1, y1, word_string, block_no, line_no, word_no)
        # Coordinates are in PDF points (unscaled)
        self.words = []
        self.current_zoom = 1.0

        # Highlight data: list of word indices to highlight (yellow)
        self.highlight_indices = []
        # Maps highlighted word index → index term that caused it
        self.highlight_term_map = {}
        # Accent highlights: word indices drawn in orange (for the focused term)
        self.accent_indices = []

    def set_words(self, words, zoom):
        self.words = words
        self.current_zoom = zoom
        self.selection_start_index = None
        self.selection_end_index = None
        self.highlight_indices = []
        self.update()

    def set_highlights(self, indices, term_map=None):
        self.highlight_indices = indices
        self.highlight_term_map = term_map or {}
        self.accent_indices = []
        self.update()

    def set_accent_highlights(self, indices):
        self.accent_indices = indices
        self.update()

    def get_word_at_pos(self, pos):
        # Convert pos to PDF coords
        # Assumes alignment is Center and pixmap fits or is larger.
        pixmap = self.pixmap()
        if not pixmap: return -1
        
        x_off = (self.width() - pixmap.width()) // 2
        y_off = (self.height() - pixmap.height()) // 2
        
        # Adjust pos relative to pixmap
        x = (pos.x() - x_off) / self.current_zoom
        y = (pos.y() - y_off) / self.current_zoom
        
        # Iterate words to find match
        # Optimized: could use R-tree if slow, but for single page linear scan is OK (<1000 words usually)
        for i, w in enumerate(self.words):
            # w = (x0, y0, x1, y1, text, block, line, word)
            # Add some padding/tolerance?
            if w[0] <= x <= w[2] and w[1] <= y <= w[3]:
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.get_word_at_pos(event.pos())
            if idx != -1:
                self.selection_start_index = idx
                self.selection_end_index = idx
                self.is_selecting = True
                self.update()
            else:
                # Clicked empty space clears selection
                self.selection_start_index = None
                self.selection_end_index = None
                self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            idx = self.get_word_at_pos(event.pos())
            if idx != -1:
                self.selection_end_index = idx
                self.update()

    def mouseReleaseEvent(self, event):
        if self.is_selecting and event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = False
            # If it was a click (not a drag) on a highlighted word, emit the term
            if (self.selection_start_index is not None and
                    self.selection_start_index == self.selection_end_index and
                    self.selection_start_index in self.highlight_term_map):
                self.highlighted_word_clicked.emit(
                    self.highlight_term_map[self.selection_start_index]
                )
            self.selection_changed.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.get_word_at_pos(event.pos())
            if idx != -1:
                # Select the word visualy
                self.selection_start_index = idx
                self.selection_end_index = idx
                self.update()
                
                # Emit signal
                text = self.words[idx][4]
                self.word_double_clicked.emit(text)

    def get_selected_text(self):
        if self.selection_start_index is None or self.selection_end_index is None:
            return ""
        
        start = min(self.selection_start_index, self.selection_end_index)
        end = max(self.selection_start_index, self.selection_end_index)
        
        text_parts = []
        for i in range(start, end + 1):
            text_parts.append(self.words[i][4])
        
        return " ".join(text_parts)

    def paintEvent(self, event):
        super().paintEvent(event)

        pixmap = self.pixmap()
        if not pixmap:
            return

        x_off = (self.width() - pixmap.width()) // 2
        y_off = (self.height() - pixmap.height()) // 2

        painter = QPainter(self)

        # Draw yellow highlights (search term matches)
        accent_set = set(self.accent_indices)
        if self.highlight_indices:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 0, 100))
            for i in self.highlight_indices:
                if i in accent_set:
                    continue  # drawn separately in orange
                w = self.words[i]
                x = w[0] * self.current_zoom + x_off
                y = w[1] * self.current_zoom + y_off
                w_curr = (w[2] - w[0]) * self.current_zoom
                h_curr = (w[3] - w[1]) * self.current_zoom
                painter.drawRect(QRectF(x, y, w_curr, h_curr))

        # Draw orange accent highlights (focused term from index click)
        if self.accent_indices:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 140, 0, 140))
            for i in self.accent_indices:
                w = self.words[i]
                x = w[0] * self.current_zoom + x_off
                y = w[1] * self.current_zoom + y_off
                w_curr = (w[2] - w[0]) * self.current_zoom
                h_curr = (w[3] - w[1]) * self.current_zoom
                painter.drawRect(QRectF(x, y, w_curr, h_curr))

        # Draw blue selection
        if self.selection_start_index is not None and self.selection_end_index is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 120, 215, 80))

            start = min(self.selection_start_index, self.selection_end_index)
            end = max(self.selection_start_index, self.selection_end_index)

            for i in range(start, end + 1):
                w = self.words[i]
                x = w[0] * self.current_zoom + x_off
                y = w[1] * self.current_zoom + y_off
                w_curr = (w[2] - w[0]) * self.current_zoom
                h_curr = (w[3] - w[1]) * self.current_zoom
                painter.drawRect(QRectF(x, y, w_curr, h_curr))


class PDFViewer(QWidget):
    add_keyword_requested = pyqtSignal(str)
    page_changed = pyqtSignal(int)
    index_term_clicked = pyqtSignal(str)  # emits the index term name

    def __init__(self):
        super().__init__()
        self.doc = None
        self.current_page_index = 0
        self.current_zoom = 1.0
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Toolbar
        self.toolbar_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous")
        self.next_btn = QPushButton("Next")
        self.page_label = QLabel("No PDF loaded")
        
        self.page_slider = QSlider(Qt.Orientation.Horizontal)
        self.page_slider.setMinimum(0)
        self.page_slider.setMaximum(0)
        self.page_slider.setEnabled(False)
        self.page_slider.valueChanged.connect(self._on_slider_changed)

        self.fit_width_chk = QCheckBox("Fit Width")
        self.fit_width_chk.setChecked(True)
        self.fit_width_chk.toggled.connect(self.update_view)

        self.toolbar_layout.addWidget(self.prev_btn)
        self.toolbar_layout.addWidget(self.page_label)
        self.toolbar_layout.addWidget(self.next_btn)
        self.toolbar_layout.addWidget(self.page_slider, 1)  # stretch factor
        self.toolbar_layout.addWidget(self.fit_width_chk)
        self.layout.addLayout(self.toolbar_layout)

        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)

        # Second toolbar: highlight toggle + goto page
        self.toolbar2_layout = QHBoxLayout()
        self.highlight_indexed_chk = QCheckBox("Highlight indexed words")
        self.highlight_indexed_chk.setChecked(True)
        self.highlight_indexed_chk.toggled.connect(self._on_highlight_toggled)

        self.goto_edit = QLineEdit()
        self.goto_edit.setPlaceholderText("Page #")
        self.goto_edit.setFixedWidth(70)
        self.goto_edit.returnPressed.connect(self._on_goto_page)

        self.toolbar2_layout.addWidget(self.highlight_indexed_chk)
        self.toolbar2_layout.addStretch()
        goto_label = QLabel("Go to:")
        self.toolbar2_layout.addWidget(goto_label)
        self.toolbar2_layout.addWidget(self.goto_edit)
        self.layout.addLayout(self.toolbar2_layout)

        # Scroll Area for PDF Page
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True) 
        
        self.image_label = ClickableLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # No selection_made signal anymore, we poll state
        self.image_label.setMouseTracking(False) 
        self.image_label.word_double_clicked.connect(self.add_keyword_requested.emit)
        self.image_label.highlighted_word_clicked.connect(self.index_term_clicked.emit)
        
        self.scroll_area.setWidget(self.image_label)
        self.layout.addWidget(self.scroll_area)
        
        # Context Menu
        self.image_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.image_label.customContextMenuRequested.connect(self.show_context_menu)

        # Debounce timer for resize-driven fit-width re-rendering
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        self._last_viewport_width = 0

        # Scroll-past-edge page turning
        self.scroll_area.installEventFilter(self)
        self._page_turn_cooldown = False
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc and self.fit_width_chk.isChecked():
            self._resize_timer.start()

    def _on_resize_timeout(self):
        """Re-render after resize settles, but only if viewport width changed."""
        vp_width = self.scroll_area.viewport().width()
        if vp_width != self._last_viewport_width:
            self._last_viewport_width = vp_width
            self.update_view()

    # ------------------------------------------------------------------
    # Scroll-past-edge → page turn
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.scroll_area and event.type() == QEvent.Type.Wheel:
            if self.doc and not self._page_turn_cooldown:
                vbar = self.scroll_area.verticalScrollBar()
                delta = event.angleDelta().y()
                at_bottom = vbar.value() >= vbar.maximum()
                at_top = vbar.value() <= vbar.minimum()

                if at_bottom and delta < 0 and self.current_page_index < len(self.doc) - 1:
                    self._turn_page(self.current_page_index + 1, scroll_to_top=True)
                    return True  # consume event
                if at_top and delta > 0 and self.current_page_index > 0:
                    self._turn_page(self.current_page_index - 1, scroll_to_top=False)
                    return True

        return super().eventFilter(obj, event)

    def _turn_page(self, new_index, scroll_to_top):
        self._page_turn_cooldown = True
        self.current_page_index = new_index
        self.update_view()
        self.update_controls()
        self.page_changed.emit(self.current_page_index)

        vbar = self.scroll_area.verticalScrollBar()
        if scroll_to_top:
            vbar.setValue(vbar.minimum())
        else:
            vbar.setValue(vbar.maximum())

        QTimer.singleShot(300, self._reset_page_turn_cooldown)

    def _reset_page_turn_cooldown(self):
        self._page_turn_cooldown = False

    # ------------------------------------------------------------------

    def load_document(self, file_path):
        try:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(file_path)
            self.current_page_index = 0
            self.update_view()
            self.update_controls()
            # Deferred re-render: layout may not be settled yet,
            # so viewport width could be wrong on first render.
            QTimer.singleShot(0, self.update_view)
            return True
        except Exception as e:
            print(f"Error loading PDF: {e}")
            self.page_label.setText(f"Error loading PDF")
            return False

    def close_document(self):
        if self.doc:
            self.doc.close()
            self.doc = None
        self.image_label.clear()
        self.image_label.set_words([], 1.0)
        self.page_label.setText("No PDF loaded")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.page_slider.setMaximum(0)
        self.page_slider.setEnabled(False)

    def prev_page(self):
        if self.doc and self.current_page_index > 0:
            self.current_page_index -= 1
            self.update_view()
            self.update_controls()
            self.page_changed.emit(self.current_page_index)

    def next_page(self):
        if self.doc and self.current_page_index < len(self.doc) - 1:
            self.current_page_index += 1
            self.update_view()
            self.update_controls()
            self.page_changed.emit(self.current_page_index)

    def _on_slider_changed(self, value):
        if self.doc and 0 <= value < len(self.doc) and value != self.current_page_index:
            self.current_page_index = value
            self.update_view()
            self.update_controls()
            self.page_changed.emit(self.current_page_index)

    def jump_to_page(self, index, highlight_term=None):
        if self.doc and 0 <= index < len(self.doc):
            self.current_page_index = index
            self.update_view()
            self.update_controls()
            # When auto-highlight is on, let the controller handle all terms;
            # otherwise fall back to single-term highlight from active links
            if highlight_term and not self.highlight_indexed_chk.isChecked():
                self.highlight_term(highlight_term)
            self.page_changed.emit(self.current_page_index)

    def highlight_term(self, term):
        """Highlight all occurrences of term on the current page."""
        import unicodedata

        words = self.image_label.words
        if not words or not term:
            return

        term_normalized = unicodedata.normalize("NFKC", term).lower()

        # Build search variants: original term + reversed "Last, First" → "First Last"
        search_variants = [term_normalized.split()]
        if ", " in term_normalized:
            parts = term_normalized.split(", ", 1)
            reversed_term = parts[1] + " " + parts[0]
            search_variants.append(reversed_term.split())

        indices = set()

        for term_words in search_variants:
            if not term_words:
                continue
            n = len(term_words)
            for i in range(len(words) - n + 1):
                match = True
                for j in range(n):
                    word_text = unicodedata.normalize("NFKC", words[i + j][4]).lower()
                    # Strip punctuation for matching
                    word_stripped = word_text.strip('.,;:!?()[]{}"\'-/')
                    target_stripped = term_words[j].strip('.,;:!?()[]{}"\'-/')
                    if word_stripped != target_stripped:
                        match = False
                        break
                if match:
                    for idx in range(i, i + n):
                        indices.add(idx)

        self.image_label.set_highlights(sorted(indices))

    def _on_highlight_toggled(self, checked):
        if not checked:
            self.image_label.set_highlights([])
        else:
            self.page_changed.emit(self.current_page_index)

    def _on_goto_page(self):
        text = self.goto_edit.text().strip()
        self.goto_edit.clear()
        try:
            page_num = int(text)
            index = page_num - 1  # Convert 1-based display to 0-based index
            if self.doc and 0 <= index < len(self.doc):
                self.current_page_index = index
                self.update_view()
                self.update_controls()
                self.page_changed.emit(self.current_page_index)
        except ValueError:
            pass

    def highlight_multiple_terms(self, terms):
        """Highlight all occurrences of multiple terms on the current page."""
        import unicodedata

        words = self.image_label.words
        if not words or not terms:
            self.image_label.set_highlights([])
            return

        all_indices = set()
        term_map = {}  # word_index -> original term string

        for term in terms:
            term_normalized = unicodedata.normalize("NFKC", term).lower()

            # Build search variants: original + reversed "Last, First" -> "First Last"
            search_variants = [term_normalized.split()]
            if ", " in term_normalized:
                parts = term_normalized.split(", ", 1)
                reversed_term = parts[1] + " " + parts[0]
                search_variants.append(reversed_term.split())

            for term_words in search_variants:
                if not term_words:
                    continue
                n = len(term_words)
                for i in range(len(words) - n + 1):
                    match = True
                    for j in range(n):
                        word_text = unicodedata.normalize("NFKC", words[i + j][4]).lower()
                        word_stripped = word_text.strip('.,;:!?()[]{}"\'-/')
                        target_stripped = term_words[j].strip('.,;:!?()[]{}"\'-/')
                        if word_stripped != target_stripped:
                            match = False
                            break
                    if match:
                        for idx in range(i, i + n):
                            all_indices.add(idx)
                            term_map[idx] = term

        self.image_label.set_highlights(sorted(all_indices), term_map)

    def set_accent_term(self, term):
        """Find all occurrences of a single term on the current page and
        mark them with orange accent highlights (on top of the yellow ones)."""
        import unicodedata

        words = self.image_label.words
        if not words or not term:
            return

        term_normalized = unicodedata.normalize("NFKC", term).lower()

        search_variants = [term_normalized.split()]
        if ", " in term_normalized:
            parts = term_normalized.split(", ", 1)
            reversed_term = parts[1] + " " + parts[0]
            search_variants.append(reversed_term.split())

        indices = []
        for term_words in search_variants:
            if not term_words:
                continue
            n = len(term_words)
            for i in range(len(words) - n + 1):
                match = True
                for j in range(n):
                    word_text = unicodedata.normalize("NFKC", words[i + j][4]).lower()
                    word_stripped = word_text.strip('.,;:!?()[]{}"\'-/')
                    target_stripped = term_words[j].strip('.,;:!?()[]{}"\'-/')
                    if word_stripped != target_stripped:
                        match = False
                        break
                if match:
                    for idx in range(i, i + n):
                        indices.append(idx)

        self.image_label.set_accent_highlights(indices)

    def set_fit_width(self, enabled):
        self.fit_width_chk.setChecked(enabled)

    def update_controls(self):
        if not self.doc:
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.page_slider.setEnabled(False)
            return

        total = len(self.doc)
        self.prev_btn.setEnabled(self.current_page_index > 0)
        self.next_btn.setEnabled(self.current_page_index < total - 1)
        self.page_label.setText(f"Page {self.current_page_index + 1} of {total}")

        self.page_slider.blockSignals(True)
        self.page_slider.setMaximum(total - 1)
        self.page_slider.setValue(self.current_page_index)
        self.page_slider.setEnabled(total > 1)
        self.page_slider.blockSignals(False)

    def update_view(self):
        if not self.doc:
            return

        page = self.doc.load_page(self.current_page_index)
        
        # 1. Render Image
        zoom = 1.5
        if self.fit_width_chk.isChecked():
            available_width = self.scroll_area.viewport().width() - 20 
            if available_width > 0:
                 pdf_width = page.rect.width
                 zoom = available_width / pdf_width
        
        self.current_zoom = zoom
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        fmt = QImage.Format.Format_RGB888
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        self.image_label.setPixmap(QPixmap.fromImage(img))
        
        # 2. Extract Words for Smart Selection
        # get_text("words") returns list of (x0, y0, x1, y1, word, block, line, word)
        words = page.get_text("words")
        self.image_label.set_words(words, zoom)

    def show_context_menu(self, pos):
        selected_text = self.image_label.get_selected_text()
        if not selected_text:
            return

        menu = QMenu(self)
        
        action_copy = QAction("Copy", self)
        action_copy.triggered.connect(lambda: QApplication.clipboard().setText(selected_text))
        
        action_add_kw = QAction("Add to Keywords", self)
        action_add_kw.triggered.connect(lambda: self.add_keyword_requested.emit(selected_text))
        
        menu.addAction(action_copy)
        menu.addAction(action_add_kw)
        
        menu.exec(self.image_label.mapToGlobal(pos))
