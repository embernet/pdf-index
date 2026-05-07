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
        # Search highlights: rects in PDF coords as (x0, y0, x1, y1) tuples
        self.search_rects = []
        self.current_search_rect = None

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

    def set_search_highlights(self, rects, current_rect=None):
        self.search_rects = rects
        self.current_search_rect = current_rect
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

    def _merge_indices_into_spans(self, indices, term_map):
        """Group sorted word indices into contiguous spans where each span
        is (a) consecutive indices, (b) sharing the same owning term in
        *term_map*, and (c) sitting on the same line (matching y-coord).
        Returns a list of lists of word indices.
        """
        sorted_idx = sorted(set(indices))
        spans = []
        current = []
        for i in sorted_idx:
            if not current:
                current = [i]
                continue
            prev = current[-1]
            same_term = (term_map.get(i) == term_map.get(prev))
            same_line = abs(self.words[i][1] - self.words[prev][1]) < 1.0
            consecutive = (i == prev + 1)
            if same_term and same_line and consecutive:
                current.append(i)
            else:
                spans.append(current)
                current = [i]
        if current:
            spans.append(current)
        return spans

    def _draw_span_rect(self, painter, span, x_off, y_off):
        """Draw a single rect covering all words in *span*, including the
        spaces between them.
        """
        first = self.words[span[0]]
        last = self.words[span[-1]]
        x = first[0] * self.current_zoom + x_off
        y = min(self.words[i][1] for i in span) * self.current_zoom + y_off
        right = last[2] * self.current_zoom + x_off
        bottom = max(self.words[i][3] for i in span) * self.current_zoom + y_off
        painter.drawRect(QRectF(x, y, right - x, bottom - y))

    def paintEvent(self, event):
        super().paintEvent(event)

        pixmap = self.pixmap()
        if not pixmap:
            return

        x_off = (self.width() - pixmap.width()) // 2
        y_off = (self.height() - pixmap.height()) // 2

        painter = QPainter(self)

        # Draw yellow highlights (search term matches). Merge consecutive
        # word indices that belong to the same indexed term and sit on the
        # same line into a single rect — this fills the inter-word spaces
        # so a multi-word term like "Beatrice Halloway" reads as one
        # continuous highlight rather than two adjacent boxes.
        accent_set = set(self.accent_indices)
        if self.highlight_indices:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 0, 100))
            spans = self._merge_indices_into_spans(
                [i for i in self.highlight_indices if i not in accent_set],
                self.highlight_term_map,
            )
            for span in spans:
                self._draw_span_rect(painter, span, x_off, y_off)

        # Draw orange accent highlights (focused term from index click).
        if self.accent_indices:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 140, 0, 140))
            spans = self._merge_indices_into_spans(
                self.accent_indices, self.highlight_term_map,
            )
            for span in spans:
                self._draw_span_rect(painter, span, x_off, y_off)

        # Draw search result highlights (light cyan)
        if self.search_rects:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 200, 255, 80))
            for r in self.search_rects:
                if r == self.current_search_rect:
                    continue
                x = r[0] * self.current_zoom + x_off
                y = r[1] * self.current_zoom + y_off
                w_r = (r[2] - r[0]) * self.current_zoom
                h_r = (r[3] - r[1]) * self.current_zoom
                painter.drawRect(QRectF(x, y, w_r, h_r))

        # Draw current search match (orange, more prominent)
        if self.current_search_rect:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 140, 0, 150))
            r = self.current_search_rect
            x = r[0] * self.current_zoom + x_off
            y = r[1] * self.current_zoom + y_off
            w_r = (r[2] - r[0]) * self.current_zoom
            h_r = (r[3] - r[1]) * self.current_zoom
            painter.drawRect(QRectF(x, y, w_r, h_r))

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

        # Page label widget: physical number + optional logical label below
        self._page_label_widget = QWidget()
        _plw_layout = QVBoxLayout()
        _plw_layout.setContentsMargins(0, 0, 0, 0)
        _plw_layout.setSpacing(0)
        self._page_label_widget.setLayout(_plw_layout)
        self.page_label = QLabel("No PDF loaded")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_logical_label = QLabel("")
        self.page_logical_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_logical_label.setStyleSheet("color: gray; font-size: 10px;")
        self.page_logical_label.setVisible(False)
        _plw_layout.addWidget(self.page_label)
        _plw_layout.addWidget(self.page_logical_label)

        self.page_slider = QSlider(Qt.Orientation.Horizontal)
        self.page_slider.setMinimum(0)
        self.page_slider.setMaximum(0)
        self.page_slider.setEnabled(False)
        self.page_slider.valueChanged.connect(self._on_slider_changed)

        self.fit_page_chk = QCheckBox("Fit Page")
        self.fit_page_chk.setChecked(True)
        self.fit_page_chk.toggled.connect(self.update_view)

        self.toolbar_layout.addWidget(self.prev_btn)
        self.toolbar_layout.addWidget(self._page_label_widget)
        self.toolbar_layout.addWidget(self.next_btn)
        self.toolbar_layout.addWidget(self.page_slider, 1)  # stretch factor
        self.toolbar_layout.addWidget(self.fit_page_chk)
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

        self.selection_count_label = QLabel()
        self.selection_count_label.setStyleSheet("color: gray;")
        self.toolbar2_layout.addWidget(self.selection_count_label)

        self.toolbar2_layout.addStretch()
        goto_label = QLabel("Go to:")
        self.toolbar2_layout.addWidget(goto_label)
        self.toolbar2_layout.addWidget(self.goto_edit)
        self.layout.addLayout(self.toolbar2_layout)

        # Search bar
        self.search_bar_layout = QHBoxLayout()
        self.pdf_search_input = QLineEdit()
        self.pdf_search_input.setPlaceholderText("Search in PDF...")
        self.pdf_search_input.setClearButtonEnabled(True)
        self.pdf_search_input.returnPressed.connect(self._do_search)
        self.pdf_search_input.textChanged.connect(self._on_search_text_changed)

        self.search_count_label = QLabel("")
        self.search_count_label.setStyleSheet("color: gray;")

        self.search_prev_btn = QPushButton("\u25b2")
        self.search_prev_btn.setToolTip("Previous match")
        self.search_prev_btn.setFixedWidth(28)
        self.search_prev_btn.setEnabled(False)
        self.search_prev_btn.clicked.connect(self._search_prev)

        self.search_next_btn = QPushButton("\u25bc")
        self.search_next_btn.setToolTip("Next match")
        self.search_next_btn.setFixedWidth(28)
        self.search_next_btn.setEnabled(False)
        self.search_next_btn.clicked.connect(self._search_next)

        self.search_bar_layout.addWidget(self.pdf_search_input)
        self.search_bar_layout.addWidget(self.search_count_label)
        self.search_bar_layout.addWidget(self.search_prev_btn)
        self.search_bar_layout.addWidget(self.search_next_btn)
        self.layout.addLayout(self.search_bar_layout)

        # Search state
        self._search_matches = []  # list of (page_idx, (x0, y0, x1, y1))
        self._search_current_idx = -1
        self._search_text = ""

        # Scroll Area for PDF Page
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True) 
        
        self.image_label = ClickableLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # No selection_made signal anymore, we poll state
        self.image_label.setMouseTracking(False) 
        self.image_label.word_double_clicked.connect(self.add_keyword_requested.emit)
        self.image_label.highlighted_word_clicked.connect(self.index_term_clicked.emit)
        self.image_label.selection_changed.connect(self._on_selection_changed)
        
        self.scroll_area.setWidget(self.image_label)
        self.layout.addWidget(self.scroll_area)
        
        # Context Menu
        self.image_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.image_label.customContextMenuRequested.connect(self.show_context_menu)

        # Debounce timer for resize-driven fit-page re-rendering
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._on_resize_timeout)
        self._last_viewport_size = (0, 0)

        # Scroll-past-edge page turning
        self.scroll_area.installEventFilter(self)
        self._page_turn_cooldown = False
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.doc and self.fit_page_chk.isChecked():
            self._resize_timer.start()

    def _on_resize_timeout(self):
        """Re-render after resize settles, but only if viewport size changed."""
        vp = self.scroll_area.viewport()
        vp_size = (vp.width(), vp.height())
        if vp_size != self._last_viewport_size:
            self._last_viewport_size = vp_size
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
            self._clear_search()
            self.pdf_search_input.clear()
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
        self._clear_search()
        self.pdf_search_input.clear()
        self.image_label.clear()
        self.image_label.set_words([], 1.0)
        self.page_label.setText("No PDF loaded")
        self.page_logical_label.setVisible(False)
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

    def _search_variants(self, term):
        """Return list of word-tuples to try matching for *term*.

        For "Smith, John" we also try the natural-order "John Smith".
        """
        import unicodedata
        term_normalized = unicodedata.normalize("NFKC", term)
        variants = [term_normalized.split()]
        if ", " in term_normalized:
            parts = term_normalized.split(", ", 1)
            variants.append((parts[1] + " " + parts[0]).split())
        return variants

    def _match_term_at(self, words, start_idx, target_words):
        """Try to match *target_words* against *words* starting at *start_idx*.

        Each target word is matched against either a single PDF word or a
        hyphenation-joined pair (PDF word ending in '-' followed by a PDF
        word starting with a lowercase letter — the same rule the indexer
        applies to reconstruct line-break-split words like 'Manch-' +
        'ester' = 'Manchester'). Possessive suffixes ('s, ’s) on the PDF
        word are stripped before comparison so 'Pemberton's' matches
        'Pemberton'.

        Returns the list of PDF-word indices consumed by the match, or
        None if no match is possible.
        """
        import unicodedata
        matched = []
        pdf_pos = start_idx

        for target_word in target_words:
            if pdf_pos >= len(words):
                return None

            target_stripped = self._normalise_word(target_word)

            word_text = unicodedata.normalize("NFKC", words[pdf_pos][4])
            word_stripped = self._normalise_word(word_text)

            if self._words_equal(word_stripped, target_stripped):
                matched.append(pdf_pos)
                pdf_pos += 1
                continue

            # Hyphenation join: '<prev>-' + '<next>' where next starts lowercase.
            if (pdf_pos + 1 < len(words)
                    and word_text.endswith("-")
                    and words[pdf_pos + 1][4]
                    and words[pdf_pos + 1][4][0].islower()):
                joined = (word_text[:-1]
                          + unicodedata.normalize("NFKC", words[pdf_pos + 1][4]))
                joined_stripped = self._normalise_word(joined)
                if self._words_equal(joined_stripped, target_stripped):
                    matched.append(pdf_pos)
                    matched.append(pdf_pos + 1)
                    pdf_pos += 2
                    continue

            return None

        return matched

    @staticmethod
    def _normalise_word(word: str) -> str:
        """Strip surrounding punctuation and possessive suffix ('s/’s)
        before comparison.
        """
        stripped = word.strip('.,;:!?()[]{}"\'-/')
        # Possessive: trailing 's or ’s. Apostrophes inside a word
        # (e.g. O'Donnell) don't count as possessives.
        if stripped.endswith("'s") or stripped.endswith("’s"):
            stripped = stripped[:-2]
        return stripped

    @staticmethod
    def _words_equal(pdf_word, target_word):
        """Case-aware word equality: an uppercase target requires an
        uppercase PDF word, otherwise we compare case-insensitively.
        """
        if target_word and target_word[0].isupper():
            if not pdf_word or not pdf_word[0].isupper():
                return False
        return pdf_word.lower() == target_word.lower()

    def highlight_term(self, term):
        """Highlight all occurrences of term on the current page."""
        words = self.image_label.words
        if not words or not term:
            return

        indices = set()
        for term_words in self._search_variants(term):
            if not term_words:
                continue
            for i in range(len(words)):
                matched = self._match_term_at(words, i, term_words)
                if matched is not None:
                    indices.update(matched)

        self.image_label.set_highlights(sorted(indices))

    def _on_highlight_toggled(self, checked):
        if not checked:
            self.image_label.set_highlights([])
        else:
            self.page_changed.emit(self.current_page_index)

    def _on_selection_changed(self):
        text = self.image_label.get_selected_text().strip()
        if not text or not self.doc:
            self.selection_count_label.setText("")
            return
        count = 0
        for page in self.doc:
            count += len(page.search_for(text))
        self.selection_count_label.setText(f"Selected text occurs {count} time{'s' if count != 1 else ''}")

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

    # ------------------------------------------------------------------
    # PDF text search
    # ------------------------------------------------------------------

    def _do_search(self):
        """Search the PDF for the entered text (triggered on Return)."""
        text = self.pdf_search_input.text().strip()
        if not text or not self.doc:
            self._clear_search()
            return

        if text != self._search_text:
            # New search – collect all matches across all pages
            self._search_text = text
            self._search_matches = []
            for page_idx in range(len(self.doc)):
                page = self.doc.load_page(page_idx)
                rects = page.search_for(text)
                for rect in rects:
                    self._search_matches.append(
                        (page_idx, (rect.x0, rect.y0, rect.x1, rect.y1))
                    )

            if not self._search_matches:
                self.search_count_label.setText("No matches")
                self.search_prev_btn.setEnabled(False)
                self.search_next_btn.setEnabled(False)
                self.image_label.set_search_highlights([], None)
                return

            # Start from first match on or after the current page
            self._search_current_idx = 0
            for i, (pg, _) in enumerate(self._search_matches):
                if pg >= self.current_page_index:
                    self._search_current_idx = i
                    break

            self._go_to_search_match()
        else:
            # Same text, advance to next match
            self._search_next()

    def _search_next(self):
        if not self._search_matches:
            return
        self._search_current_idx = (self._search_current_idx + 1) % len(self._search_matches)
        self._go_to_search_match()

    def _search_prev(self):
        if not self._search_matches:
            return
        self._search_current_idx = (self._search_current_idx - 1) % len(self._search_matches)
        self._go_to_search_match()

    def _go_to_search_match(self):
        idx = self._search_current_idx
        page_idx, rect = self._search_matches[idx]

        self.search_count_label.setText(
            f"{idx + 1} of {len(self._search_matches)}"
        )
        self.search_prev_btn.setEnabled(True)
        self.search_next_btn.setEnabled(True)

        if page_idx != self.current_page_index:
            self.current_page_index = page_idx
            self.update_view()
            self.update_controls()
            self.page_changed.emit(self.current_page_index)
        else:
            self._update_search_highlights()

        # Scroll to make the match visible
        y_pixel = rect[1] * self.current_zoom
        vbar = self.scroll_area.verticalScrollBar()
        viewport_height = self.scroll_area.viewport().height()
        vbar.setValue(max(0, int(y_pixel - viewport_height / 3)))

    def _update_search_highlights(self):
        """Set search highlights for the current page."""
        if not self._search_matches:
            self.image_label.set_search_highlights([], None)
            return

        page_rects = []
        current_rect = None
        for i, (pg, rect) in enumerate(self._search_matches):
            if pg == self.current_page_index:
                page_rects.append(rect)
                if i == self._search_current_idx:
                    current_rect = rect

        self.image_label.set_search_highlights(page_rects, current_rect)

    def _clear_search(self):
        self._search_text = ""
        self._search_matches = []
        self._search_current_idx = -1
        self.search_count_label.setText("")
        self.search_prev_btn.setEnabled(False)
        self.search_next_btn.setEnabled(False)
        self.image_label.set_search_highlights([], None)

    def _on_search_text_changed(self, text):
        if not text:
            self._clear_search()

    # ------------------------------------------------------------------

    def highlight_multiple_terms(self, terms):
        """Highlight all occurrences of multiple terms on the current page.

        Also performs proximity highlighting: when a multi-word indexed
        term (e.g. 'Beatrice Halloway') is found on the page, standalone
        occurrences of any of its constituent capitalised words on the
        same page are also highlighted and attributed to the multi-word
        term. This mirrors the indexer's suppression rule, which assumes
        a bare first name or surname near its full form refers to the
        same person.
        """
        words = self.image_label.words
        if not words or not terms:
            self.image_label.set_highlights([])
            return

        all_indices = set()
        term_map = {}  # word_index -> original term string

        # Pass 1: direct matches for each indexed term.
        multi_word_owners = {}  # word -> term that contains this word
        # Stop-word and title-prefix constituents that should NOT trigger
        # proximity highlighting on their own (e.g. "The" inside "The
        # Guardian" should not light up every "the" or "THE" on the page).
        from model.name_indexer import DEFAULT_STOPWORDS, TITLE_PREFIXES
        skip_constituents = DEFAULT_STOPWORDS | TITLE_PREFIXES

        for term in terms:
            for term_words in self._search_variants(term):
                if not term_words:
                    continue
                for i in range(len(words)):
                    matched = self._match_term_at(words, i, term_words)
                    if matched is not None:
                        for idx in matched:
                            all_indices.add(idx)
                            term_map[idx] = term
                # Record constituent words from any multi-word variant for
                # the proximity pass below. Skip stop words and title
                # prefixes since they appear ubiquitously on a page and
                # would highlight themselves indiscriminately.
                if len(term_words) > 1:
                    for w in term_words:
                        if not w or not w[0].isupper():
                            continue
                        if w.lower() in skip_constituents:
                            continue
                        multi_word_owners.setdefault(w, term)

        # Pass 2: proximity highlights — for any constituent capitalised
        # word of a multi-word term that's been matched on the page, also
        # highlight bare standalone occurrences and attribute them to the
        # owning compound term.
        for constituent, owning_term in multi_word_owners.items():
            for i in range(len(words)):
                if i in all_indices:
                    continue  # already highlighted as part of the full term
                matched = self._match_term_at(words, i, [constituent])
                if matched is not None:
                    for idx in matched:
                        all_indices.add(idx)
                        term_map[idx] = owning_term

        self.image_label.set_highlights(sorted(all_indices), term_map)

    def set_accent_term(self, term):
        """Find all occurrences of a single term on the current page and
        mark them with orange accent highlights (on top of the yellow ones).

        Occurrences that are already claimed by a *different* indexed term
        (visible in the highlight_term_map built by highlight_multiple_terms)
        are skipped so that, e.g., clicking "Sound" does not also accent-
        highlight the "Sound" inside "Sound of Music".
        """
        words = self.image_label.words
        if not words or not term:
            return

        # term_map maps word-index → owning term (set by
        # highlight_multiple_terms).  If a word position already belongs to
        # a different, longer term we must not accent-highlight it.
        term_map = getattr(self.image_label, 'highlight_term_map', {})
        term_lower = term.lower()

        indices = []
        for term_words in self._search_variants(term):
            if not term_words:
                continue
            for i in range(len(words)):
                matched = self._match_term_at(words, i, term_words)
                if matched is None:
                    continue
                owned_by_other = any(
                    (term_map.get(idx, '')
                     and term_map.get(idx, '').lower() != term_lower)
                    for idx in matched
                )
                if not owned_by_other:
                    indices.extend(matched)

        self.image_label.set_accent_highlights(indices)

    def set_fit_page(self, enabled):
        self.fit_page_chk.setChecked(enabled)

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

        logical = self.doc.load_page(self.current_page_index).get_label()
        if logical and logical != str(self.current_page_index + 1):
            self.page_logical_label.setText(logical)
            self.page_logical_label.setVisible(True)
        else:
            self.page_logical_label.setVisible(False)

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
        if self.fit_page_chk.isChecked():
            vp = self.scroll_area.viewport()
            available_width = vp.width() - 20
            available_height = vp.height() - 20
            if available_width > 0 and available_height > 0:
                zoom_w = available_width / page.rect.width
                zoom_h = available_height / page.rect.height
                zoom = min(zoom_w, zoom_h)
        
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

        # Re-apply search highlights for this page
        if self._search_matches:
            self._update_search_highlights()

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
