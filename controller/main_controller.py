import os
import shutil
import string
from view.main_window import MainWindow
from model.indexer import IndexingThread
from model.app_config import AppConfigManager
from model.tag_cloud import TagCloudThread, recolor_wordcloud
from model.name_indexer import NameIndexingThread
from PyQt6.QtWidgets import QFileDialog, QApplication

class MainController:
    def __init__(self):
        self.view = MainWindow()
        self.project_path = None
        self.current_pdf_path = None
        self.indexing_thread = None
        self.name_indexing_thread = None
        self.tag_cloud_thread = None
        self._cached_wordcloud = None  # Cached WordCloud for fast recolor

        # Dual-thread merge state
        self._keyword_indexing_done = True
        self._name_indexing_done = True
        self._pending_keyword_raw = None
        self._pending_name_raw = None

        # Connect signals
        self.view.action_new_project.triggered.connect(self.create_project)
        self.view.action_open_project.triggered.connect(self.open_project)
        self.view.action_import_pdf.triggered.connect(self.import_pdf)
        
        # Keyword Editor
        self.view.keyword_editor.save_requested.connect(self.save_keywords)
        
        # PDF Viewer
        self.view.pdf_viewer.add_keyword_requested.connect(self.add_keyword_from_selection)
        
        # Controls & Output
        self.view.controls_output.create_index_requested.connect(self.start_indexing)
        # Format toggles + Active View + Capitalize
        bg = self.view.controls_output.format_bg
        bg.buttonToggled.connect(self.update_output_display)
        self.view.controls_output.view_source_chk.toggled.connect(self.update_output_display)
        self.view.controls_output.capitalize_chk.toggled.connect(self.update_output_display_toggle)
        
        # Autosave UI changes
        self.view.controls_output.radio_physical.toggled.connect(lambda: self.save_current_config())
        self.view.controls_output.radio_logical.toggled.connect(lambda: self.save_current_config())
        self.view.controls_output.offset_spin.valueChanged.connect(lambda: self.save_current_config())
        self.view.pdf_viewer.fit_width_chk.toggled.connect(lambda: self.save_current_config())
        self.view.controls_output.name_indexing_chk.toggled.connect(lambda: self.save_current_config())
        self.view.controls_output.bold_indexing_chk.toggled.connect(lambda: self.save_current_config())

        # Exclude Editor
        self.view.exclude_editor.save_requested.connect(self.save_excludes)
        self.view.controls_output.exclude_entry_requested.connect(self.exclude_entry)

        # Active Link Click / Cloud Click
        self.view.controls_output.active_link_clicked.connect(self.on_active_link_clicked)
        self.view.controls_output.cloud_word_clicked.connect(self.on_cloud_word_clicked)

        # Store last results to allow cheap format switching
        self.last_raw_results = None
        self.last_formatted_results = None

    def start(self):
        self.view.show()
        
        # Auto-load last project
        last_proj = AppConfigManager.get_last_project()
        if last_proj and os.path.exists(last_proj):
            print(f"Auto-loading last project: {last_proj}")
            self.setup_project(last_proj)

    def create_project(self):
        dir_path = QFileDialog.getExistingDirectory(self.view, "Select Directory for New Project")
        if dir_path:
            self.setup_project(dir_path)

    def open_project(self):
        dir_path = QFileDialog.getExistingDirectory(self.view, "Open Project Directory")
        if dir_path:
            self.setup_project(dir_path)

    def setup_project(self, dir_path):
        from model.config import ConfigManager

        self._cached_wordcloud = None  # Invalidate on project change

        # Update App Config (Recent History)
        AppConfigManager.add_recent_project(dir_path)
        
        self.project_path = dir_path
        self.view.setWindowTitle(f"PDF Indexer - {os.path.basename(dir_path)}")
        self.load_keywords()
        self.load_excludes()

        # Load Config
        config = ConfigManager.load_config(dir_path)
        
        # Set UI State
        self.view.controls_output.set_state(config)
        self.view.pdf_viewer.set_fit_width(config.get("fit_width", True))
        
        # Load PDF
        pdf_name = config.get("pdf_filename")
        if pdf_name:
            pdf_path = os.path.join(dir_path, pdf_name)
            if os.path.exists(pdf_path):
                self.current_pdf_path = pdf_path
                self.view.pdf_viewer.load_document(pdf_path)
            else:
                self.current_pdf_path = None
                self.view.pdf_viewer.close_document()
        else:
            self.current_pdf_path = None
            self.view.pdf_viewer.close_document()
            
        # Ensure config is freshly saved
        self.save_current_config()

        # If loading directly into cloud view, trigger it
        if config.get("view_mode") == "tag_cloud":
            self.generate_tag_cloud()

    def save_current_config(self):
        if not self.project_path:
            return
            
        ctrl = self.view.controls_output
        viewer = self.view.pdf_viewer
        
        strat = ctrl.get_strategy()
        offset = ctrl.get_offset()
        
        mode = "markdown"
        if ctrl.radio_txt.isChecked(): mode = "text"
        elif ctrl.radio_html.isChecked(): mode = "html"
        elif ctrl.radio_active.isChecked(): mode = "active"
        elif ctrl.radio_cloud.isChecked(): mode = "tag_cloud"
        
        config = {
            "pdf_filename": os.path.basename(self.current_pdf_path) if self.current_pdf_path else None,
            "strategy": strat,
            "offset": offset,
            "view_mode": mode,
            "capitalize": ctrl.capitalize_chk.isChecked(),
            "view_source": ctrl.view_source_chk.isChecked(),
            "fit_width": viewer.fit_width_chk.isChecked(),
            "name_indexing": ctrl.name_indexing_chk.isChecked(),
            "bold_indexing": ctrl.bold_indexing_chk.isChecked()
        }
        
        from model.config import ConfigManager
        ConfigManager.save_config(self.project_path, config)

    def import_pdf(self):
        if not self.project_path:
            self.view.show_error("Please create or open a project first.")
            return

        file_path, _ = QFileDialog.getOpenFileName(self.view, "Select PDF", "", "PDF Files (*.pdf)")
        if file_path:
            filename = os.path.basename(file_path)
            dest_path = os.path.join(self.project_path, filename)
            
            if os.path.abspath(file_path) != os.path.abspath(dest_path):
                try:
                    shutil.copy2(file_path, dest_path)
                    file_path = dest_path 
                except Exception as e:
                    self.view.show_error(f"Failed to copy PDF: {e}")
                    return

            self.current_pdf_path = file_path
            self._cached_wordcloud = None  # Invalidate on PDF change
            self.view.pdf_viewer.load_document(self.current_pdf_path)

            # Save config immediately to persist PDF reference
            self.save_current_config()

    def save_keywords(self, text):
        if not self.project_path:
            return

        kw_path = os.path.join(self.project_path, "keywords.txt")
        try:
            with open(kw_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            print(f"Error saving keywords: {e}")

        # If in cloud mode, refresh colors (green vs black)
        if self.view.controls_output.radio_cloud.isChecked():
            if self._cached_wordcloud is not None:
                self._recolor_cached_cloud()
            else:
                self.generate_tag_cloud()

    def load_keywords(self):
        if not self.project_path:
            return
        kw_path = os.path.join(self.project_path, "keywords.txt")
        if os.path.exists(kw_path):
            try:
                with open(kw_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    self.view.keyword_editor.set_keywords(text)
            except Exception as e:
                print(f"Error loading keywords: {e}")

    def save_excludes(self, text):
        if not self.project_path:
            return
        exc_path = os.path.join(self.project_path, "excludes.txt")
        try:
            with open(exc_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            print(f"Error saving excludes: {e}")

    def load_excludes(self):
        if not self.project_path:
            return
        exc_path = os.path.join(self.project_path, "excludes.txt")
        if os.path.exists(exc_path):
            try:
                with open(exc_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    self.view.exclude_editor.set_text(text)
            except Exception as e:
                print(f"Error loading excludes: {e}")
        else:
            # Migrate from old comma-separated config
            from model.config import ConfigManager
            config = ConfigManager.load_config(self.project_path)
            old_list = config.get("name_exclude_list", "")
            if old_list:
                words = [w.strip() for w in old_list.split(",") if w.strip()]
                text = "\n".join(words)
                self.view.exclude_editor.set_text(text)
                self.save_excludes(text)
            else:
                self.view.exclude_editor.set_text("")

    def exclude_entry(self, keyword):
        self.view.exclude_editor.add_word(keyword)

    def add_keyword_from_selection(self, text):
        # Strip trailing punctuation
        text = text.rstrip(string.punctuation)
        
        # Append to keyword editor
        current_text = self.view.keyword_editor.editor.toPlainText()
        if current_text:
            new_text = current_text + "\n" + text
        else:
            new_text = text
        self.view.keyword_editor.set_keywords(new_text)
        self.view.keyword_editor.emit_save() # Save immediately

    def start_indexing(self):
        if not self.current_pdf_path:
            self.view.show_error("No PDF loaded.")
            return

        keywords = self.view.keyword_editor.get_keywords()
        name_indexing_enabled = self.view.controls_output.name_indexing_chk.isChecked()
        has_keywords = bool([k for k in keywords if k.strip()])

        if not has_keywords and not name_indexing_enabled:
            self.view.show_error("No keywords defined and name indexing is off.")
            return

        strategy = self.view.controls_output.get_strategy()
        offset = self.view.controls_output.get_offset()

        self.view.controls_output.create_btn.setEnabled(False)
        self.view.controls_output.progress_bar.setValue(0)
        self.view.controls_output.progress_bar.setVisible(True)

        # Reset merge state
        self._pending_keyword_raw = None
        self._pending_name_raw = None
        self._keyword_indexing_done = not has_keywords
        self._name_indexing_done = not name_indexing_enabled

        # Start keyword indexing (if keywords exist)
        if has_keywords:
            self.indexing_thread = IndexingThread(
                self.current_pdf_path, keywords, strategy, offset
            )
            self.indexing_thread.progress_updated.connect(
                self.view.controls_output.set_progress
            )
            self.indexing_thread.indexing_finished.connect(
                self._on_keyword_indexing_finished
            )
            self.indexing_thread.error_occurred.connect(self.on_indexing_error)
            self.indexing_thread.start()

        # Start name indexing (if enabled)
        if name_indexing_enabled:
            bold_enabled = self.view.controls_output.bold_indexing_chk.isChecked()
            exclude_words = {w.lower() for w in self.view.exclude_editor.get_words()}

            self.name_indexing_thread = NameIndexingThread(
                self.current_pdf_path, strategy, offset,
                include_bold=bold_enabled, exclude_words=exclude_words,
            )
            # Only connect progress if keyword thread is not also running
            if not has_keywords:
                self.name_indexing_thread.progress_updated.connect(
                    self.view.controls_output.set_progress
                )
            self.name_indexing_thread.indexing_finished.connect(
                self._on_name_indexing_finished
            )
            self.name_indexing_thread.error_occurred.connect(self.on_indexing_error)
            self.name_indexing_thread.start()

    def on_indexing_error(self, message):
        self.view.show_error(f"Indexing failed: {message}")
        self.view.controls_output.create_btn.setEnabled(True)
        self.view.controls_output.progress_bar.setVisible(False)

    def _on_keyword_indexing_finished(self, formatted_results, raw_results):
        self._pending_keyword_raw = raw_results
        self._keyword_indexing_done = True
        self._try_merge_results()

    def _on_name_indexing_finished(self, formatted_results, raw_results):
        self._pending_name_raw = raw_results
        self._name_indexing_done = True
        self._try_merge_results()

    def _try_merge_results(self):
        """Merge keyword and name results once both threads are done."""
        if not self._keyword_indexing_done or not self._name_indexing_done:
            return

        merged_raw = {}

        if self._pending_keyword_raw:
            for key, pages in self._pending_keyword_raw.items():
                merged_raw[key] = list(pages)

        if self._pending_name_raw:
            for key, pages in self._pending_name_raw.items():
                if key in merged_raw:
                    # Merge page lists, deduplicate by page index
                    existing_indices = {p[0] for p in merged_raw[key]}
                    for page in pages:
                        if page[0] not in existing_indices:
                            merged_raw[key].append(page)
                    merged_raw[key].sort(key=lambda x: x[0])
                else:
                    merged_raw[key] = list(pages)

        self.view.controls_output.create_btn.setEnabled(True)
        self.last_raw_results = merged_raw
        self.process_and_display_results()

    def update_output_display_toggle(self, _):
        # Called when capitalization toggled
        self.save_current_config()
        self.process_and_display_results()

    def process_and_display_results(self):
        if not self.last_raw_results:
            return

        # Re-process based on capitalization setting
        capitalize = self.view.controls_output.capitalize_chk.isChecked()
        
        # Using IndexingThread.process_results logic
        formatted = IndexingThread.process_results(None, self.last_raw_results, capitalize_keys=capitalize)
        self.last_formatted_results = formatted
        self.view.controls_output.entry_count_label.setText(f"{len(formatted)} entries")
        
        # Save files
        if self.project_path:
            self.save_results_to_files(formatted)
            
        # Update Display
        self.update_output_display()

    def save_results_to_files(self, results):
        md_content = self.generate_markdown(results)
        txt_content = self.generate_text(results)
        html_content = self.generate_html(results)
        
        base = os.path.join(self.project_path, "index")
        with open(base + ".md", 'w', encoding='utf-8') as f:
            f.write(md_content)
        with open(base + ".txt", 'w', encoding='utf-8') as f:
            f.write(txt_content)
        with open(base + ".html", 'w', encoding='utf-8') as f:
            f.write(html_content)

    def update_output_display(self):
        ctrl = self.view.controls_output
        self.save_current_config()
        
        is_cloud = ctrl.radio_cloud.isChecked()
        if is_cloud:
            self.generate_tag_cloud()
            return
            
        if not self.last_formatted_results:
            return

        content = ""
        format_type = 'text'
        
        if ctrl.radio_md.isChecked():
            content = self.generate_markdown(self.last_formatted_results)
            format_type = 'markdown'
        elif ctrl.radio_txt.isChecked():
            content = self.generate_text(self.last_formatted_results)
            format_type = 'text'
        elif ctrl.radio_html.isChecked():
            content = self.generate_html(self.last_formatted_results)
            format_type = 'html'
        elif ctrl.radio_active.isChecked():
            content = self.generate_active_html(self.last_formatted_results)
            format_type = 'active'
            
        ctrl.set_output(content, format_type)

    def generate_tag_cloud(self):
        if not self.current_pdf_path:
             self.view.controls_output.set_output("<h3>No PDF loaded.</h3>", "tag_cloud")
             return

        keywords = self.view.keyword_editor.get_keywords()
        
        self.view.controls_output.progress_bar.setVisible(True)
        self.view.controls_output.progress_bar.setValue(0) # Pulse
        
        self.tag_cloud_thread = TagCloudThread(self.current_pdf_path, keywords)
        self.tag_cloud_thread.finished.connect(self.on_cloud_generated)
        self.tag_cloud_thread.error.connect(self.on_cloud_error)
        self.tag_cloud_thread.start()

    def on_cloud_generated(self, image, layout, wc):
        self._cached_wordcloud = wc
        self.view.controls_output.progress_bar.setVisible(False)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(image, layout)

    def on_cloud_error(self, err):
        self.view.controls_output.progress_bar.setVisible(False)
        self.view.show_error(f"Error generating tag cloud: {err}")

    def _recolor_cached_cloud(self):
        """Recolor the cached WordCloud without regenerating layout."""
        if self._cached_wordcloud is None:
            return
        keywords = self.view.keyword_editor.get_keywords()
        q_img, layout_data = recolor_wordcloud(self._cached_wordcloud, keywords)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(q_img, layout_data)

    def on_cloud_word_clicked(self, word):
        # Toggle: Add or Remove
        # Case insensitive check
        word_clean = word.rstrip(string.punctuation)
        current_keywords = self.view.keyword_editor.get_keywords()
        current_lower = {k.lower(): k for k in current_keywords}
        
        if word_clean.lower() in current_lower:
            # Remove
            print(f"Removing keyword: {word_clean}")
            # Which exact string to remove? match case insensitive
            to_remove = current_lower[word_clean.lower()]
            current_keywords = [k for k in current_keywords if k != to_remove]
        else:
            # Add
            print(f"Adding keyword: {word_clean}")
            current_keywords.append(word_clean)
            
        text = "\n".join(current_keywords)
        self.view.keyword_editor.set_keywords(text)
        self.view.keyword_editor.emit_save() # Triggers save then update_output_display if connected?
        # Helper: emit_save connects to save_keywords
        # save_keywords saves to file AND regenerates cloud if mode is cloud.

    def on_active_link_clicked(self, link_str):
        try:
            parts = link_str.split("|", 1)
            page_idx = int(parts[0])
            keyword = parts[1] if len(parts) > 1 else None
            self.view.pdf_viewer.jump_to_page(page_idx, highlight_term=keyword)
        except ValueError:
            pass

    def generate_markdown(self, results):
        count = len(results)
        lines = [f"# Index ({count} entries)\n"]
        for kw, pages in results.items():
            lines.append(f"**{kw}**: {pages}  ")
        return "\n".join(lines)

    def generate_text(self, results):
        count = len(results)
        lines = [f"Index ({count} entries)\n"]
        for kw, pages in results.items():
            lines.append(f"{kw}: {pages}")
        return "\n".join(lines)

    def generate_html(self, results):
        count = len(results)
        lines = [f"<html><body><h1>Index ({count} entries)</h1>"]
        for kw, pages in results.items():
            lines.append(f"<div><b>{kw}</b>: {pages}</div>")
        lines.append("</body></html>")
        return "\n".join(lines)

    def generate_active_html(self, results):
        if not self.last_raw_results:
             return ""

        capitalize = self.view.controls_output.capitalize_chk.isChecked()
        sorted_keys = sorted(self.last_raw_results.keys(), key=lambda x: x.lower())
        
        count = len(sorted_keys)
        lines = [f'<html><head><style>a {{ text-decoration: none; color: blue; }} a:hover {{ text-decoration: underline; }}</style></head><body><h1>Active Index ({count} entries)</h1>']
        
        for kw in sorted_keys:
            pages = self.last_raw_results[kw] # list of (index, label)
            pages.sort(key=lambda x: x[0])
            
            if not pages: 
                continue

            display_kw = kw
            if capitalize and kw:
                display_kw = kw[0].upper() + kw[1:]

            ranges = []
            if not pages: continue
            current_range = [pages[0]]
            for i in range(1, len(pages)):
                if pages[i][0] == pages[i-1][0] + 1:
                    current_range.append(pages[i])
                else:
                    ranges.append(current_range)
                    current_range = [pages[i]]
            ranges.append(current_range)
            
            link_strings = []
            for r in ranges:
                # r is list of (idx, lbl)
                start_idx, start_lbl = r[0]
                end_idx, end_lbl = r[-1]
                
                # Format: <a href="#IDX|KEYWORD">LBL</a>
                s_link = f'<a href="#{start_idx}|{kw}">{start_lbl}</a>'

                if len(r) == 1:
                    link_strings.append(s_link)
                else:
                    e_link = f'<a href="#{end_idx}|{kw}">{end_lbl}</a>'
                    link_strings.append(f"{s_link}-{e_link}")
            
            lines.append(f"<div><b>{display_kw}</b>: {', '.join(link_strings)}</div>")
            
        lines.append("</body></html>")
        return "\n".join(lines)
