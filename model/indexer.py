import fitz  # PyMuPDF
import re
import unicodedata
from collections import defaultdict
from PyQt6.QtCore import QThread, pyqtSignal

class IndexingThread(QThread):
    progress_updated = pyqtSignal(int)
    indexing_finished = pyqtSignal(dict, dict) # formatted_results, raw_results
    error_occurred = pyqtSignal(str)

    def __init__(self, pdf_path, keywords, page_numbering_strategy, offset=0):
        super().__init__()
        self.pdf_path = pdf_path
        self.keywords = keywords
        self.strategy = page_numbering_strategy  # 'logical' or 'physical'
        self.offset = offset
        self._is_running = True

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)
            # Store (page_index, page_label) for each keyword
            raw_results = defaultdict(list) 
            
            keyword_map = {} 
            regex_map = {} 
            
            for kw in self.keywords:
                if not kw.strip():
                    continue
                norm_kw = unicodedata.normalize('NFKC', kw.strip())
                keyword_map[norm_kw] = kw.strip()
                escaped_kw = re.escape(norm_kw)
                # Word boundary check
                pattern = re.compile(rf'\b{escaped_kw}\b', re.IGNORECASE)
                regex_map[norm_kw] = pattern

            for i in range(total_pages):
                if not self._is_running:
                    break
                
                page = doc.load_page(i)
                text = page.get_text("text")
                norm_text = unicodedata.normalize('NFKC', text)
                
                page_label = ""
                if self.strategy == 'logical':
                    page_label = page.get_label()
                    if not page_label:
                        page_label = str(i + 1)
                else: 
                    # Physical Page Index + Offset
                    page_label = str(i + self.offset)

                for norm_kw, pattern in regex_map.items():
                    if pattern.search(norm_text):
                        original_kw = keyword_map[norm_kw]
                        # Avoid duplicates for same page?
                        # Check last entry to see if it's the same page index
                        if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
                            raw_results[original_kw].append((i, page_label))
                
                progress = int((i + 1) / total_pages * 100)
                self.progress_updated.emit(progress)
            
            doc.close()
            
            if self._is_running:
                formatted_results = self.process_results(raw_results)
                self.indexing_finished.emit(formatted_results, raw_results)

        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self._is_running = False

    def process_results(self, raw_results, capitalize_keys=False):
        # formatted_results: sorted keyword -> string of pages (e.g. "1, 5-7, 10")
        output = {}
        sorted_keys = sorted(raw_results.keys(), key=lambda x: x.lower())
        
        for kw in sorted_keys:
            pages = raw_results[kw] # List of (index, label)
            # Sort by physical index just in case (though we appended in order)
            pages.sort(key=lambda x: x[0])
            
            if not pages:
                continue

            display_kw = kw
            if capitalize_keys and kw:
                display_kw = kw[0].upper() + kw[1:]

            # Range compression
            ranges = []
            if not pages:
                continue
                
            current_range = [pages[0]]
            
            for i in range(1, len(pages)):
                prev_idx, _ = pages[i-1]
                curr_idx, curr_lbl = pages[i]
                
                if curr_idx == prev_idx + 1:
                    current_range.append(pages[i])
                else:
                    ranges.append(current_range)
                    current_range = [pages[i]]
            ranges.append(current_range)
            
            range_strings = []
            for r in ranges:
                if len(r) == 1:
                    range_strings.append(r[0][1])
                elif len(r) == 2:
                    range_strings.append(f"{r[0][1]}-{r[-1][1]}")
                else:
                    range_strings.append(f"{r[0][1]}-{r[-1][1]}")
            
            output[display_kw] = ", ".join(range_strings)
            
        return output
