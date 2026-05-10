import json
import os
import shutil
import string
from view.main_window import MainWindow
from model.indexer import IndexingThread, EMPTY_FLAGS, merge_flags, normalise_raw_results
from model.app_config import AppConfigManager
from model.tag_cloud import TagCloudThread, IndexCloudThread, NotInIndexCloudThread, recolor_wordcloud
from model.name_indexer import NameIndexingThread, DEFAULT_STOPWORDS
from model.merge_suggestions import find_containment_suggestions
from model.reports import run_reports
from view.controls_output import TAB_MODES
from PyQt6.QtWidgets import QFileDialog, QApplication
from PyQt6.QtCore import Qt

class MainController:
    def __init__(self):
        self.view = MainWindow()
        self.project_path = None
        self.current_pdf_path = None
        self.indexing_thread = None
        self.name_indexing_thread = None
        self.tag_cloud_thread = None
        self.index_cloud_thread = None
        self.not_in_index_cloud_thread = None
        self._cached_wordcloud = None  # Cached WordCloud for fast recolor
        self._name_type_overrides: dict = {}  # {natural_name: "person"|"place_thing"}

        # Dual-thread merge state
        self._keyword_indexing_done = True
        self._name_indexing_done = True
        self._pending_keyword_raw = None
        self._pending_name_raw = None

        # Connect signals
        self.view.action_new_project.triggered.connect(self.create_project)
        self.view.action_open_project.triggered.connect(self.open_project)
        self.view.action_import_pdf.triggered.connect(self.import_pdf)
        self.view.action_exit.triggered.connect(self.exit_app)
        
        # Keyword Editor
        self.view.keyword_editor.save_requested.connect(self.save_keywords)
        
        # PDF Viewer
        self.view.pdf_viewer.add_keyword_requested.connect(self.add_keyword_from_selection)
        
        # Controls & Output
        self.view.settings_sidebar.create_index_requested.connect(self.start_indexing)
        # View tab toggles + Active View + Capitalize
        self.view.controls_output.view_tabs.currentChanged.connect(self.update_output_display)
        self.view.controls_output.view_source_chk.toggled.connect(self.update_output_display)
        self.view.settings_sidebar.capitalize_chk.toggled.connect(self.update_output_display_toggle)
        
        # Autosave UI changes
        self.view.settings_sidebar.radio_physical.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.radio_logical.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.offset_spin.valueChanged.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.index_from_offset_chk.toggled.connect(lambda: self.save_current_config())
        self.view.pdf_viewer.fit_page_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.name_indexing_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.bold_indexing_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.surname_first_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.index_italic_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.separate_style_files_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.separate_style_files_chk.toggled.connect(
            lambda checked: self.view.controls_output.set_style_selector_enabled(checked)
        )
        self.view.settings_sidebar.separate_style_files_chk.toggled.connect(
            lambda: self.update_output_display()
        )
        self.view.settings_sidebar.index_capitalised_chk.toggled.connect(lambda: self.save_current_config())
        self.view.settings_sidebar.index_front_matter_chk.toggled.connect(lambda: self.save_current_config())

        # Exclude Editor
        self.view.exclude_editor.save_requested.connect(self.save_excludes)
        self.view.controls_output.exclude_entry_requested.connect(self.exclude_entry)

        # Proper Names Editor
        self.view.proper_names_editor.save_requested.connect(self.save_proper_names)
        self.view.controls_output.proper_noun_requested.connect(self.add_proper_noun)
        self.view.controls_output.mark_as_person_requested.connect(self.mark_as_person)

        # Merge entries (right-click context menu)
        self.view.controls_output.merge_entry_requested.connect(self.on_merge_entry_requested)

        # Merge tool tab
        merge_view = self.view.controls_output.merge_view
        merge_view.merge_requested.connect(self._on_merge_tool_merge)
        merge_view.separate_requested.connect(self._on_merge_tool_separate)
        merge_view.revisit_requested.connect(self._on_merge_tool_revisit)

        # Reports tab
        self.view.controls_output.run_reports_requested.connect(self._run_all_reports)
        self.view.controls_output.run_report_requested.connect(self._run_single_report)

        # Stopwords Editor
        self.view.stopwords_editor.save_requested.connect(self.save_stopwords)

        # Active Link Click / Cloud Click / Cloud Sub-mode
        self.view.controls_output.active_link_clicked.connect(self.on_active_link_clicked)
        self.view.controls_output.cloud_word_clicked.connect(self.on_cloud_word_clicked)
        self.view.controls_output.cloud_submode_changed.connect(self.update_output_display)
        self.view.controls_output.style_view_changed.connect(self._on_style_view_changed)

        # Auto-highlight indexed words on page change
        self.view.pdf_viewer.page_changed.connect(self._auto_highlight_current_page)
        self.view.pdf_viewer.highlight_indexed_chk.toggled.connect(lambda: self.save_current_config())

        # Click highlighted word in PDF → scroll index to that term
        self.view.pdf_viewer.index_term_clicked.connect(self._on_index_term_clicked)

        # Store last results to allow cheap format switching
        self.last_raw_results = None
        self.last_formatted_results = None
        self._last_report_sections = None

    def start(self):
        self.view.show()
        QApplication.instance().aboutToQuit.connect(self._cleanup_threads)

        # Auto-load last project
        last_proj = AppConfigManager.get_last_project()
        if last_proj and os.path.exists(last_proj):
            print(f"Auto-loading last project: {last_proj}")
            self.setup_project(last_proj)

    def _cleanup_threads(self):
        for thread in (self.indexing_thread, self.name_indexing_thread,
                       self.tag_cloud_thread, self.index_cloud_thread,
                       self.not_in_index_cloud_thread):
            if thread is not None and thread.isRunning():
                thread.terminate()
                thread.wait()

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
        self._last_report_sections = None  # Clear stale report data on project load

        # Update App Config (Recent History)
        AppConfigManager.add_recent_project(dir_path)
        
        self.project_path = dir_path
        self.view.setWindowTitle(f"pdf-indexer - {os.path.basename(dir_path)}")
        self.load_keywords()
        self.load_excludes()
        self.load_stopwords()
        self.load_proper_names()

        # Load Config
        config = ConfigManager.load_config(dir_path)
        
        # Set UI State
        self.view.controls_output.set_state(config)
        self.view.settings_sidebar.set_state(config)
        self.view.controls_output.set_style_selector_enabled(
            self.view.settings_sidebar.separate_style_files_chk.isChecked()
        )
        self.view.pdf_viewer.set_fit_page(config.get("fit_page", config.get("fit_width", True)))
        self.view.pdf_viewer.highlight_indexed_chk.setChecked(config.get("highlight_indexed", True))
        
        # Load PDF
        pdf_name = config.get("pdf_filename")
        if pdf_name:
            pdf_path = os.path.join(dir_path, pdf_name)
            if os.path.exists(pdf_path):
                self.current_pdf_path = pdf_path
                self.view.pdf_viewer.load_document(pdf_path)
                self.view.set_pdf_name(pdf_name)
            else:
                self.current_pdf_path = None
                self.view.pdf_viewer.close_document()
                self.view.set_pdf_name(None)
        else:
            self.current_pdf_path = None
            self.view.pdf_viewer.close_document()
            self.view.set_pdf_name(None)
            
        # Ensure config is freshly saved
        self.save_current_config()

        # Load existing index if available, otherwise auto-create
        index_path = os.path.join(dir_path, "index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    self._last_report_sections = None  # Clear stale report data before loading
                    self.last_raw_results = json.load(f)
                normalise_raw_results(self.last_raw_results)
                self._apply_merge_mappings()
                self.process_and_display_results()
                self._auto_highlight_current_page()
            except Exception as e:
                print(f"Error loading index: {e}")
                self.last_raw_results = None
        elif self.current_pdf_path:
            # No index yet but a PDF is loaded — auto-create
            self.start_indexing()

        # If loading directly into cloud view, trigger it
        mode = config.get("view_mode")
        if mode in ("tag_cloud", "index_cloud"):
            self._generate_cloud_for_submode()

    def save_current_config(self):
        if not self.project_path:
            return

        ctrl = self.view.controls_output
        sidebar = self.view.settings_sidebar
        viewer = self.view.pdf_viewer

        config = {
            "pdf_filename": os.path.basename(self.current_pdf_path) if self.current_pdf_path else None,
            "strategy": sidebar.get_strategy(),
            "offset": sidebar.get_offset(),
            "view_mode": ctrl.get_view_mode(),
            "capitalize": sidebar.capitalize_chk.isChecked(),
            "view_source": ctrl.view_source_chk.isChecked(),
            "fit_page": viewer.fit_page_chk.isChecked(),
            "name_indexing": sidebar.name_indexing_chk.isChecked(),
            "index_capitalised": sidebar.index_capitalised_chk.isChecked(),
            "bold_indexing": sidebar.bold_indexing_chk.isChecked(),
            "highlight_indexed": viewer.highlight_indexed_chk.isChecked(),
            "index_from_offset": sidebar.index_from_offset_chk.isChecked(),
            "surname_first": sidebar.surname_first_chk.isChecked(),
            "index_italic": sidebar.index_italic_chk.isChecked(),
            "separate_style_files": sidebar.separate_style_files_chk.isChecked(),
            "index_front_matter_roman": sidebar.index_front_matter_chk.isChecked(),
            "style_view": ctrl.get_style_view(),
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
            self.view.set_pdf_name(os.path.basename(self.current_pdf_path))

            # Save config immediately to persist PDF reference
            self.save_current_config()

    def save_keywords(self, text):
        if not self.project_path:
            return

        self._last_report_sections = None  # Clear stale reports when keywords change
        kw_path = os.path.join(self.project_path, "keywords.txt")
        try:
            with open(kw_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            print(f"Error saving keywords: {e}")

        # If in "all" cloud mode, refresh colors (green vs black)
        if self.view.controls_output.get_view_mode() == "tag_cloud":
            submode = self.view.controls_output.get_cloud_submode()
            if submode == "all":
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

    def save_stopwords(self, text):
        if not self.project_path:
            return
        sw_path = os.path.join(self.project_path, "stopwords.txt")
        try:
            with open(sw_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            print(f"Error saving stopwords: {e}")

    def load_stopwords(self):
        if not self.project_path:
            return
        sw_path = os.path.join(self.project_path, "stopwords.txt")
        if os.path.exists(sw_path):
            try:
                with open(sw_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    self.view.stopwords_editor.set_text(text)
            except Exception as e:
                print(f"Error loading stopwords: {e}")
        else:
            # First run: populate with default stopwords
            words = sorted(DEFAULT_STOPWORDS)
            text = "\n".join(words)
            self.view.stopwords_editor.set_text(text)
            self.save_stopwords(text)

    def exclude_entry(self, keyword):
        self.view.exclude_editor.add_word(keyword)

    def _name_types_path(self):
        return os.path.join(self.project_path, "name_types.json") if self.project_path else None

    def save_name_type_overrides(self):
        path = self._name_types_path()
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._name_type_overrides, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving name type overrides: {e}")

    def load_proper_names(self):
        if not self.project_path:
            return
        path = self._name_types_path()
        old_path = os.path.join(self.project_path, "proper_names.txt")

        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._name_type_overrides = {k: v for k, v in data.items()
                                              if v in ("person", "place_thing")}
            except Exception as e:
                print(f"Error loading name_types.json: {e}")
                self._name_type_overrides = {}
        elif os.path.exists(old_path):
            # Migrate legacy proper_names.txt — all entries are place_thing
            try:
                with open(old_path, 'r', encoding='utf-8') as f:
                    names = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
                self._name_type_overrides = {n: "place_thing" for n in names}
                self.save_name_type_overrides()
            except Exception as e:
                print(f"Error migrating proper_names.txt: {e}")
                self._name_type_overrides = {}
        else:
            self._name_type_overrides = {}

        # Populate the editor panel with place_thing names only
        place_names = [n for n, t in self._name_type_overrides.items() if t == "place_thing"]
        self.view.proper_names_editor.set_text("\n".join(sorted(place_names)))

    def save_proper_names(self, text):
        """Called when the user edits the Place/Thing Names panel directly."""
        if not self.project_path:
            return
        new_place_names = [ln.strip() for ln in text.splitlines() if ln.strip()]
        # Remove old place_thing entries, keep person entries
        person_entries = {k: v for k, v in self._name_type_overrides.items() if v == "person"}
        self._name_type_overrides = {**person_entries,
                                      **{n: "place_thing" for n in new_place_names}}
        self.save_name_type_overrides()

    def add_proper_noun(self, natural_form):
        """Mark natural_form as place_thing, save, and re-index."""
        self._name_type_overrides[natural_form] = "place_thing"
        self.save_name_type_overrides()
        # Refresh panel (keep sorted, place_thing entries only)
        place_names = [n for n, t in self._name_type_overrides.items() if t == "place_thing"]
        self.view.proper_names_editor.set_text("\n".join(sorted(place_names)))
        if self.current_pdf_path and self.project_path:
            self.start_indexing()

    def mark_as_person(self, natural_form):
        """Mark natural_form as person (will be inverted), save, and re-index."""
        self._name_type_overrides[natural_form] = "person"
        self.save_name_type_overrides()
        if self.current_pdf_path and self.project_path:
            self.start_indexing()

    # ------------------------------------------------------------------
    # Merge entries
    # ------------------------------------------------------------------

    def _merges_path(self):
        if not self.project_path:
            return None
        return os.path.join(self.project_path, "merges.json")

    def _load_merge_mappings(self) -> dict:
        path = self._merges_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_merge_mappings(self, mappings: dict):
        path = self._merges_path()
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, indent=2)

    def _apply_merge_mappings(self):
        """Apply saved merge mappings to self.last_raw_results in-place."""
        if not self.last_raw_results:
            return
        mappings = self._load_merge_mappings()
        if not mappings:
            return
        for source, target in list(mappings.items()):
            if source not in self.last_raw_results:
                continue
            if target not in self.last_raw_results:
                # Target gone (renamed / excluded) — skip stale mapping
                continue
            # Merge source pages into target, OR-combining flags on collision
            existing_by_idx = {p[0]: i for i, p in enumerate(self.last_raw_results[target])}
            for p in self.last_raw_results[source]:
                if p[0] in existing_by_idx:
                    slot = existing_by_idx[p[0]]
                    old = self.last_raw_results[target][slot]
                    self.last_raw_results[target][slot] = (
                        old[0], old[1],
                        merge_flags(old[2] if len(old) > 2 else dict(EMPTY_FLAGS),
                                    p[2] if len(p) > 2 else dict(EMPTY_FLAGS)),
                    )
                else:
                    self.last_raw_results[target].append(p)
                    existing_by_idx[p[0]] = len(self.last_raw_results[target]) - 1
            self.last_raw_results[target].sort(key=lambda x: x[0])
            del self.last_raw_results[source]

    def on_merge_entry_requested(self, source):
        """Show dialog to pick a target term, then merge *source* into it."""
        from PyQt6.QtWidgets import QInputDialog

        if not self.last_raw_results or source not in self.last_raw_results:
            return

        candidates = sorted(
            [k for k in self.last_raw_results if k != source],
            key=lambda x: x.lower(),
        )
        if not candidates:
            return

        target, ok = QInputDialog.getItem(
            self.view,
            "Merge Entry",
            f'Merge "{source}" into:',
            candidates,
            editable=False,
        )
        if not ok or not target:
            return

        # Perform the merge on live results, OR-combining flags on collision
        existing_by_idx = {p[0]: i for i, p in enumerate(self.last_raw_results[target])}
        for p in self.last_raw_results[source]:
            if p[0] in existing_by_idx:
                slot = existing_by_idx[p[0]]
                old = self.last_raw_results[target][slot]
                self.last_raw_results[target][slot] = (
                    old[0], old[1],
                    merge_flags(old[2] if len(old) > 2 else dict(EMPTY_FLAGS),
                                p[2] if len(p) > 2 else dict(EMPTY_FLAGS)),
                )
            else:
                self.last_raw_results[target].append(p)
                existing_by_idx[p[0]] = len(self.last_raw_results[target]) - 1
        self.last_raw_results[target].sort(key=lambda x: x[0])
        del self.last_raw_results[source]

        # Persist the mapping
        mappings = self._load_merge_mappings()
        mappings[source] = target
        self._save_merge_mappings(mappings)

        # Refresh display
        self._last_report_sections = None
        self.process_and_display_results()
        self._auto_highlight_current_page()

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
        name_indexing_enabled = self.view.settings_sidebar.name_indexing_chk.isChecked()
        has_keywords = bool([k for k in keywords if k.strip()])

        if not has_keywords and not name_indexing_enabled:
            self.view.show_error("No keywords defined and name indexing is off.")
            return

        strategy = self.view.settings_sidebar.get_strategy()
        offset = self.view.settings_sidebar.get_offset()
        index_from_offset = (
            self.view.settings_sidebar.index_from_offset_chk.isChecked()
            and self.view.settings_sidebar.index_from_offset_chk.isEnabled()
        )
        start_page = abs(offset) if (index_from_offset and offset < 0) else 0

        index_front_matter = self.view.settings_sidebar.index_front_matter_chk.isChecked()
        index_italic = self.view.settings_sidebar.index_italic_chk.isChecked()
        index_capitalised = self.view.settings_sidebar.index_capitalised_chk.isChecked()

        self.view.settings_sidebar.create_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.view.show_progress("Creating index...")

        # Reset merge state
        self._pending_keyword_raw = None
        self._pending_name_raw = None
        self._keyword_indexing_done = not has_keywords
        self._name_indexing_done = not name_indexing_enabled

        # Start keyword indexing (if keywords exist)
        if has_keywords:
            self.indexing_thread = IndexingThread(
                self.current_pdf_path, keywords, strategy, offset,
                start_page=start_page, index_front_matter=index_front_matter,
            )
            self.indexing_thread.progress_updated.connect(
                self.view.set_progress
            )
            self.indexing_thread.indexing_finished.connect(
                self._on_keyword_indexing_finished
            )
            self.indexing_thread.error_occurred.connect(self.on_indexing_error)
            self.indexing_thread.start()

        # Start name indexing (if enabled)
        if name_indexing_enabled:
            bold_enabled = self.view.settings_sidebar.bold_indexing_chk.isChecked()
            exclude_words = {w.lower() for w in self.view.exclude_editor.get_words()}
            # Always include DEFAULT_STOPWORDS so that newly added
            # defaults take effect even if the user's stopwords.txt
            # was created from an older version.
            stopwords = DEFAULT_STOPWORDS | {w.lower() for w in self.view.stopwords_editor.get_words()}

            surname_first = self.view.settings_sidebar.surname_first_chk.isChecked()
            self.name_indexing_thread = NameIndexingThread(
                self.current_pdf_path, strategy, offset,
                include_bold=bold_enabled, exclude_words=exclude_words,
                stopwords=stopwords, name_type_overrides=self._name_type_overrides,
                start_page=start_page, surname_first=surname_first,
                index_italic=index_italic,
                index_capitalised=index_capitalised,
                index_front_matter=index_front_matter,
            )
            self.name_indexing_thread.progress_updated.connect(
                self.view.set_progress
            )
            self.name_indexing_thread.indexing_finished.connect(
                self._on_name_indexing_finished
            )
            self.name_indexing_thread.error_occurred.connect(self.on_indexing_error)
            self.name_indexing_thread.start()

    def on_indexing_error(self, message):
        QApplication.restoreOverrideCursor()
        self.view.show_error(f"Indexing failed: {message}")
        self.view.settings_sidebar.create_btn.setEnabled(True)
        self.view.hide_progress()

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
                    existing_by_idx = {p[0]: i for i, p in enumerate(merged_raw[key])}
                    for page in pages:
                        if page[0] in existing_by_idx:
                            slot = existing_by_idx[page[0]]
                            old = merged_raw[key][slot]
                            merged_raw[key][slot] = (
                                old[0], old[1],
                                merge_flags(old[2] if len(old) > 2 else dict(EMPTY_FLAGS),
                                            page[2] if len(page) > 2 else dict(EMPTY_FLAGS)),
                            )
                        else:
                            merged_raw[key].append(page)
                            existing_by_idx[page[0]] = len(merged_raw[key]) - 1
                    merged_raw[key].sort(key=lambda x: x[0])
                else:
                    merged_raw[key] = list(pages)

        # Auto-suppression of single-word entries was removed; see the
        # comment in model.name_indexer.NameIndexingThread.run.

        QApplication.restoreOverrideCursor()
        self.view.hide_progress()
        self.view.settings_sidebar.create_btn.setEnabled(True)
        self.last_raw_results = merged_raw
        self._last_report_sections = None
        # Apply any saved user merges (e.g. "Paul" → "Smith, Paul"). Each
        # post-merge step is wrapped so that a bug in one stage prints a
        # traceback and leaves the index visible rather than aborting the
        # whole app via PyQt6's qFatal-on-slot-exception behaviour.
        try:
            self._apply_merge_mappings()
        except Exception:
            import traceback
            print("error during _apply_merge_mappings:")
            traceback.print_exc()
        try:
            self.process_and_display_results()
        except Exception:
            import traceback
            print("error during process_and_display_results:")
            traceback.print_exc()
        try:
            self._auto_highlight_current_page()
        except Exception:
            import traceback
            print("error during _auto_highlight_current_page:")
            traceback.print_exc()

    def _on_style_view_changed(self, _bucket):
        self.save_current_config()
        self.process_and_display_results()

    def update_output_display_toggle(self, _):
        # Called when capitalization toggled
        self.save_current_config()
        self.process_and_display_results()

    def process_and_display_results(self):
        if not self.last_raw_results:
            return

        capitalize = self.view.settings_sidebar.capitalize_chk.isChecked()
        bucket = self.view.controls_output.get_style_view()

        from model.indexer import filter_by_style
        if (bucket != "aggregate"
                and self.view.settings_sidebar.separate_style_files_chk.isChecked()):
            view_raw = filter_by_style(self.last_raw_results, bucket)
        else:
            view_raw = self.last_raw_results

        formatted = IndexingThread.process_results(None, view_raw, capitalize_keys=capitalize)
        self.last_formatted_results = formatted
        self.view.controls_output._total_entry_count = len(formatted)
        self.view.controls_output.entry_count_label.setText(f"{len(formatted)} entries")

        # Save files (always uses the unfiltered aggregate; per-bucket variants
        # are produced internally by save_results_to_files).
        if self.project_path:
            full_formatted = IndexingThread.process_results(
                None, self.last_raw_results, capitalize_keys=capitalize,
            )
            self.save_results_to_files(full_formatted)

        self.update_output_display()

    def save_results_to_files(self, results):
        """Write the aggregate index in md/txt/html/json. When 'separate style files'
        is enabled, also write per-bucket md/txt/html files; otherwise clean up any
        stale per-bucket files from a previous run.
        """
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

        if self.last_raw_results is not None:
            with open(base + ".json", 'w', encoding='utf-8') as f:
                json.dump(self.last_raw_results, f, indent=2)

        separate = self.view.settings_sidebar.separate_style_files_chk.isChecked()
        style_files = ["italic", "bold", "caps", "other"]
        for bucket in style_files:
            path_base = os.path.join(self.project_path, f"index-{bucket}")
            if separate and self.last_raw_results is not None:
                from model.indexer import filter_by_style
                filtered_raw = filter_by_style(self.last_raw_results, bucket)
                capitalize = self.view.settings_sidebar.capitalize_chk.isChecked()
                filtered_formatted = IndexingThread.process_results(
                    None, filtered_raw, capitalize_keys=capitalize,
                )
                self._write_format_files(path_base, filtered_formatted)
            else:
                for ext in ("md", "txt", "html"):
                    stale = path_base + f".{ext}"
                    if os.path.exists(stale):
                        try:
                            os.remove(stale)
                        except OSError:
                            pass

    def _write_format_files(self, path_base, formatted_results):
        md = self.generate_markdown(formatted_results)
        txt = self.generate_text(formatted_results)
        html = self.generate_html(formatted_results)
        for ext, content in (("md", md), ("txt", txt), ("html", html)):
            with open(path_base + f".{ext}", 'w', encoding='utf-8') as f:
                f.write(content)

    def update_output_display(self, *args):
        ctrl = self.view.controls_output
        self.save_current_config()

        mode = ctrl.get_view_mode()

        if mode == "reports":
            self._update_reports_view()
            return
        if mode == "merge":
            self._update_merge_view()
            return
        if mode == "tag_cloud":
            self._generate_cloud_for_submode()
            return

        if not self.last_formatted_results:
            return

        content = ""
        format_type = 'text'

        if mode == "markdown":
            content = self.generate_markdown(self.last_formatted_results)
            format_type = 'markdown'
        elif mode == "text":
            content = self.generate_text(self.last_formatted_results)
            format_type = 'text'
        elif mode == "html":
            content = self.generate_html(self.last_formatted_results)
            format_type = 'html'
        elif mode == "active":
            ctrl_local = self.view.controls_output
            from model.indexer import filter_by_style
            bucket = ctrl_local.get_style_view()
            if (bucket != "aggregate"
                    and ctrl_local.separate_style_files_chk.isChecked()):
                active_raw = filter_by_style(self.last_raw_results, bucket)
            else:
                active_raw = self.last_raw_results
            content = self._generate_active_html_for(active_raw)
            format_type = 'active'

        ctrl.set_output(content, format_type)

    def generate_tag_cloud(self):
        if not self.current_pdf_path:
             self.view.controls_output.set_output("<h3>No PDF loaded.</h3>", "tag_cloud")
             return

        if self.tag_cloud_thread is not None and self.tag_cloud_thread.isRunning():
            return

        keywords = self.view.keyword_editor.get_keywords()
        exclude_words = {w.lower() for w in self.view.exclude_editor.get_words()}
        stopwords = {w.lower() for w in self.view.stopwords_editor.get_words()}
        custom_stopwords = exclude_words | stopwords

        self.view.progress_bar.setVisible(True)
        self.view.progress_bar.setValue(0) # Pulse

        self.tag_cloud_thread = TagCloudThread(self.current_pdf_path, keywords, custom_stopwords)
        self.tag_cloud_thread.finished.connect(self.on_cloud_generated)
        self.tag_cloud_thread.error.connect(self.on_cloud_error)
        self.tag_cloud_thread.start()

    def on_cloud_generated(self, image, layout, wc):
        self._cached_wordcloud = wc
        self.view.progress_bar.setVisible(False)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(image, layout)

    def on_cloud_error(self, err):
        self.view.progress_bar.setVisible(False)
        self.view.show_error(f"Error generating tag cloud: {err}")

    def generate_index_cloud(self):
        if not self.last_raw_results:
            self.view.controls_output.set_output("", "tag_cloud")
            return

        if self.index_cloud_thread is not None and self.index_cloud_thread.isRunning():
            return

        self.view.progress_bar.setVisible(True)
        self.view.progress_bar.setValue(0)

        self.index_cloud_thread = IndexCloudThread(self.last_raw_results)
        self.index_cloud_thread.finished.connect(self.on_index_cloud_generated)
        self.index_cloud_thread.error.connect(self.on_cloud_error)
        self.index_cloud_thread.start()

    def on_index_cloud_generated(self, image, layout):
        self.view.progress_bar.setVisible(False)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(image, layout)

    def generate_not_in_index_cloud(self):
        if not self.current_pdf_path:
            self.view.controls_output.set_output("", "tag_cloud")
            return

        if self.not_in_index_cloud_thread is not None and self.not_in_index_cloud_thread.isRunning():
            return

        indexed_terms = list(self.last_raw_results.keys()) if self.last_raw_results else []
        exclude_words = {w.lower() for w in self.view.exclude_editor.get_words()}
        stopwords = {w.lower() for w in self.view.stopwords_editor.get_words()}
        custom_stopwords = exclude_words | stopwords

        self.view.progress_bar.setVisible(True)
        self.view.progress_bar.setValue(0)

        self.not_in_index_cloud_thread = NotInIndexCloudThread(
            self.current_pdf_path, indexed_terms, custom_stopwords
        )
        self.not_in_index_cloud_thread.finished.connect(self.on_not_in_index_cloud_generated)
        self.not_in_index_cloud_thread.error.connect(self.on_cloud_error)
        self.not_in_index_cloud_thread.start()

    def on_not_in_index_cloud_generated(self, image, layout):
        self.view.progress_bar.setVisible(False)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(image, layout)

    def _generate_cloud_for_submode(self):
        submode = self.view.controls_output.get_cloud_submode()
        if submode == "in_index":
            self.generate_index_cloud()
        elif submode == "not_in_index":
            self.generate_not_in_index_cloud()
        else:
            self.generate_tag_cloud()

    def _recolor_cached_cloud(self):
        """Recolor the cached WordCloud without regenerating layout."""
        if self._cached_wordcloud is None:
            return
        keywords = self.view.keyword_editor.get_keywords()
        q_img, layout_data = recolor_wordcloud(self._cached_wordcloud, keywords)
        self.view.controls_output.set_output("", "tag_cloud")
        self.view.controls_output.set_cloud_data(q_img, layout_data)

    def on_cloud_word_clicked(self, word):
        word_clean = word.rstrip(string.punctuation)
        submode = self.view.controls_output.get_cloud_submode()

        if submode == "in_index":
            self.view.exclude_editor.add_word(word_clean)
            return

        if submode == "not_in_index":
            current_keywords = self.view.keyword_editor.get_keywords()
            current_lower = {k.lower(): k for k in current_keywords}
            if word_clean.lower() not in current_lower:
                current_keywords.append(word_clean)
                self.view.keyword_editor.set_keywords("\n".join(current_keywords))
                self.view.keyword_editor.emit_save()
            return

        # "all" sub-mode: toggle add/remove from include list
        current_keywords = self.view.keyword_editor.get_keywords()
        current_lower = {k.lower(): k for k in current_keywords}

        if word_clean.lower() in current_lower:
            to_remove = current_lower[word_clean.lower()]
            current_keywords = [k for k in current_keywords if k != to_remove]
        else:
            current_keywords.append(word_clean)

        self.view.keyword_editor.set_keywords("\n".join(current_keywords))
        self.view.keyword_editor.emit_save()

    def on_active_link_clicked(self, link_str):
        try:
            parts = link_str.split("|", 1)
            page_idx = int(parts[0])
            keyword = parts[1] if len(parts) > 1 else None
            self.view.pdf_viewer.jump_to_page(page_idx, highlight_term=keyword)
            # After jump_to_page, all indexed terms are highlighted yellow
            # via _auto_highlight_current_page (triggered by page_changed).
            # Now overlay the specific clicked term in orange.
            if keyword:
                self.view.pdf_viewer.set_accent_term(keyword)
        except ValueError:
            pass

    def _auto_highlight_current_page(self, page_idx=None):
        """Highlight all indexed terms on the current PDF page."""
        viewer = self.view.pdf_viewer
        if not viewer.highlight_indexed_chk.isChecked():
            return
        if not self.last_raw_results:
            return

        if page_idx is None:
            page_idx = viewer.current_page_index

        # Find all keywords that have this page in their results
        terms_on_page = []
        for kw, pages in self.last_raw_results.items():
            for p in pages:
                if p[0] == page_idx:
                    terms_on_page.append(kw)
                    break

        if terms_on_page:
            viewer.highlight_multiple_terms(terms_on_page)
        else:
            viewer.image_label.set_highlights([])

    def _on_index_term_clicked(self, term):
        """Scroll the output index to the clicked term and highlight it."""
        self.view.controls_output.scroll_to_term(term)

    # ------------------------------------------------------------------
    # Merge tool tab
    # ------------------------------------------------------------------

    def _merge_tool_path(self):
        if not self.project_path:
            return None
        return os.path.join(self.project_path, "merge_tool.json")

    def _load_merge_tool(self) -> dict:
        path = self._merge_tool_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_merge_tool(self, data: dict):
        path = self._merge_tool_path()
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

    def _update_merge_view(self):
        """Generate containment suggestions and render the merge tool cards."""
        ctrl = self.view.controls_output

        if not self.last_raw_results:
            ctrl.set_output("", "merge")
            ctrl.merge_view.set_suggestions([], [])
            return

        suggestions = find_containment_suggestions(self.last_raw_results)
        decisions = self._load_merge_tool()

        pending = []
        decided = []

        for s in suggestions:
            key = s["source"]
            if key in decisions:
                decided.append((s, decisions[key]["decision"]))
            else:
                pending.append(s)

        # Also show decisions for entries that were merged away (no longer
        # in raw_results) so the user can revisit them.
        for key, info in decisions.items():
            if info["decision"] == "merged" and key not in self.last_raw_results:
                # Build a minimal suggestion dict for display
                decided.append((
                    {
                        "source": key,
                        "source_pages": len(info.get("original_pages", [])),
                        "containers": [{"entry": info["target"],
                                        "pages": len(self.last_raw_results.get(
                                            info["target"], []))}],
                        "target": info["target"],
                        "target_pages": len(self.last_raw_results.get(
                            info["target"], [])),
                    },
                    "merged",
                ))

        ctrl.set_output("", "merge")
        ctrl.merge_view.set_suggestions(pending, decided)

        # Update entry count label with merge stats
        ctrl.entry_count_label.setText(
            f"{len(pending)} pending, {len(decided)} decided"
        )

    def _on_merge_tool_merge(self, source, target):
        """Handle Merge button click from merge tool."""
        if not self.last_raw_results:
            return
        if source not in self.last_raw_results:
            return
        if target not in self.last_raw_results:
            return

        # Save original pages for undo
        original_pages = list(self.last_raw_results[source])

        # Perform the merge on live results, tracking which pages are new and OR-merging flags
        existing_by_idx = {p[0]: i for i, p in enumerate(self.last_raw_results[target])}
        added_pages = []
        for p in self.last_raw_results[source]:
            if p[0] in existing_by_idx:
                slot = existing_by_idx[p[0]]
                old = self.last_raw_results[target][slot]
                self.last_raw_results[target][slot] = (
                    old[0], old[1],
                    merge_flags(old[2] if len(old) > 2 else dict(EMPTY_FLAGS),
                                p[2] if len(p) > 2 else dict(EMPTY_FLAGS)),
                )
            else:
                self.last_raw_results[target].append(p)
                existing_by_idx[p[0]] = len(self.last_raw_results[target]) - 1
                added_pages.append(p)
        self.last_raw_results[target].sort(key=lambda x: x[0])
        del self.last_raw_results[source]

        # Persist actual merge mapping (same as right-click merge)
        mappings = self._load_merge_mappings()
        mappings[source] = target
        self._save_merge_mappings(mappings)

        # Record decision in merge tool config
        decisions = self._load_merge_tool()
        decisions[source] = {
            "decision": "merged",
            "target": target,
            "original_pages": original_pages,
            "added_pages": added_pages,
        }
        self._save_merge_tool(decisions)

        # Refresh
        self._last_report_sections = None
        self.process_and_display_results()
        self._auto_highlight_current_page()
        # If still on the merge tab, refresh the merge view
        if self.view.controls_output.get_view_mode() == "merge":
            self._update_merge_view()

    def _on_merge_tool_separate(self, source):
        """Handle Keep Separate button click from merge tool."""
        decisions = self._load_merge_tool()
        decisions[source] = {"decision": "separate"}
        self._save_merge_tool(decisions)

        # Refresh the merge view
        if self.view.controls_output.get_view_mode() == "merge":
            self._update_merge_view()

    def _on_merge_tool_revisit(self, source):
        """Handle Revisit button click from merge tool."""
        decisions = self._load_merge_tool()
        info = decisions.pop(source, None)
        self._save_merge_tool(decisions)

        if info and info.get("decision") == "merged":
            # Undo the merge: restore original entry and remove only
            # the pages that were added during merge from the target.
            target = info["target"]
            original_pages = info.get("original_pages", [])
            # added_pages tracks only pages that were new to the target
            added_pages = info.get("added_pages", original_pages)

            if original_pages:
                # Restore source entry
                self.last_raw_results[source] = original_pages

                # Remove only the pages that were added during merge
                if added_pages and target in self.last_raw_results:
                    added_indices = {p[0] for p in added_pages}
                    self.last_raw_results[target] = [
                        p for p in self.last_raw_results[target]
                        if p[0] not in added_indices
                    ]

            # Remove from merges.json
            mappings = self._load_merge_mappings()
            mappings.pop(source, None)
            self._save_merge_mappings(mappings)

            # Refresh display
            self.process_and_display_results()
            self._auto_highlight_current_page()

        # Refresh the merge view
        if self.view.controls_output.get_view_mode() == "merge":
            self._update_merge_view()

    # ------------------------------------------------------------------
    # Reports tab
    # ------------------------------------------------------------------

    def _update_reports_view(self):
        ctrl = self.view.controls_output
        if not self.last_raw_results:
            ctrl.reports_view.set_not_run()
            ctrl.set_output("", "reports")
            return
        # Show cached results if available, else run fresh
        if self._last_report_sections is None:
            self._run_all_reports(
                ctrl.reports_view.thin_spin.value(),
                ctrl.reports_view.dense_spin.value(),
            )
        else:
            ctrl.set_output("", "reports")

    def _run_all_reports(self, thin_threshold, dense_threshold):
        ctrl = self.view.controls_output
        if not self.last_raw_results:
            ctrl.reports_view.set_not_run()
            ctrl.set_output("", "reports")
            return
        include_keywords = self.view.keyword_editor.get_keywords()
        self._last_report_sections = run_reports(
            self.last_raw_results,
            include_keywords,
            thin_threshold=thin_threshold,
            dense_threshold=dense_threshold,
        )
        ctrl.reports_view.set_reports(self._last_report_sections)
        ctrl.set_output("", "reports")

    def _run_single_report(self, report_id, thin_threshold, dense_threshold):
        ctrl = self.view.controls_output
        if not self.last_raw_results:
            return
        include_keywords = self.view.keyword_editor.get_keywords()
        # Run just the one report
        new_sections = run_reports(
            self.last_raw_results,
            include_keywords,
            thin_threshold=thin_threshold,
            dense_threshold=dense_threshold,
            report_ids=[report_id],
        )
        # Merge into cached sections: replace matching report_id, keep others
        if self._last_report_sections is None:
            self._last_report_sections = new_sections
        else:
            new_by_id = {s.report_id: s for s in new_sections if not s.not_run}
            merged = []
            for s in self._last_report_sections:
                if s.report_id in new_by_id:
                    merged.append(new_by_id[s.report_id])
                else:
                    merged.append(s)
            self._last_report_sections = merged
        ctrl.reports_view.set_reports(self._last_report_sections)
        ctrl.set_output("", "reports")

    def generate_markdown(self, results):
        count = len(results)
        lines = [f"# Index ({count} entries)\n"]
        for kw, pages in results.items():
            lines.append(f"**{kw}** {pages}  ")
        return "\n".join(lines)

    def generate_text(self, results):
        count = len(results)
        lines = [f"Index ({count} entries)\n"]
        for kw, pages in results.items():
            lines.append(f"{kw} {pages}")
        return "\n".join(lines)

    def generate_html(self, results):
        count = len(results)
        lines = [f"<html><body><h1>Index ({count} entries)</h1>"]
        for kw, pages in results.items():
            lines.append(f"<div><b>{kw}</b> {pages}</div>")
        lines.append("</body></html>")
        return "\n".join(lines)

    def _generate_active_html_for(self, raw_results):
        if not raw_results:
            return ""

        capitalize = self.view.settings_sidebar.capitalize_chk.isChecked()
        sorted_keys = sorted(raw_results.keys(), key=lambda x: x.lower())

        count = len(sorted_keys)
        lines = [f'<html><head><style>a {{ text-decoration: none; color: blue; }} a:hover {{ text-decoration: underline; }}</style></head><body><h1>Active Index ({count} entries)</h1>']

        for kw in sorted_keys:
            pages = raw_results[kw]  # list of (idx, label, flags)
            pages.sort(key=lambda x: x[0])

            if not pages:
                continue

            display_kw = kw
            if capitalize and kw:
                display_kw = kw[0].upper() + kw[1:]

            ranges = []
            if not pages:
                continue
            from model.indexer import looks_like_roman

            def _label_format(label):
                return "roman" if looks_like_roman(label) else "arabic"

            current_range = [pages[0]]
            for i in range(1, len(pages)):
                same_format = _label_format(pages[i-1][1]) == _label_format(pages[i][1])
                if pages[i][0] == pages[i-1][0] + 1 and same_format:
                    current_range.append(pages[i])
                else:
                    ranges.append(current_range)
                    current_range = [pages[i]]
            ranges.append(current_range)

            link_strings = []
            for r in ranges:
                start_idx, start_lbl = r[0][0], r[0][1]
                end_idx, end_lbl = r[-1][0], r[-1][1]

                s_link = f'<a href="#{start_idx}|{kw}">{start_lbl}</a>'

                if len(r) == 1:
                    link_strings.append(s_link)
                else:
                    e_link = f'<a href="#{end_idx}|{kw}">{end_lbl}</a>'
                    link_strings.append(f"{s_link}-{e_link}")

            lines.append(f"<div><b>{display_kw}</b> {', '.join(link_strings)}</div>")

        lines.append("</body></html>")
        return "\n".join(lines)

    def generate_active_html(self, results):
        """Existing format-switching helper — kept for backwards compatibility."""
        return self._generate_active_html_for(self.last_raw_results)

    def exit_app(self):
        QApplication.quit()
