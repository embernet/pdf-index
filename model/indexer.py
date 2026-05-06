import fitz  # PyMuPDF
import re
import unicodedata
from collections import defaultdict
from PyQt6.QtCore import QThread, pyqtSignal

_ROMAN_LOOKS_LIKE = re.compile(r'^[IVXLCDMivxlcdm]+$')


def to_lowercase_roman(n: int) -> str:
    """Convert a 1-based positive integer to lowercase roman numerals.

    Returns "" for n <= 0 (defensive guard for callers that mishandle offsets).
    Supports values up to 3999, which is well beyond any real PDF front matter.
    """
    if n <= 0:
        return ""
    pairs = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]
    out = []
    for value, symbol in pairs:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def looks_like_roman(label: str) -> bool:
    """Return True if *label* is a non-empty string of only roman numeral letters."""
    return bool(label) and bool(_ROMAN_LOOKS_LIKE.match(label))


def label_for_page(page, physical_page_number: int, strategy: str,
                   offset: int = 0, force_roman: bool = False) -> str:
    """Produce the printable label for a page given indexing strategy.

    *physical_page_number* is 1-based.

    When *force_roman* is True (front-matter pass), prefer the PDF's own label
    if it looks roman; otherwise generate a lowercase roman from the physical
    page number.
    """
    if force_roman:
        try:
            label = page.get_label()
        except Exception:
            label = ""
        if looks_like_roman(label):
            return label.lower()
        return to_lowercase_roman(physical_page_number)

    if strategy == 'logical':
        try:
            label = page.get_label()
        except Exception:
            label = ""
        return label if label else str(physical_page_number)
    return str(physical_page_number + offset)


EMPTY_FLAGS = {"italic": False, "bold": False, "caps": False}


def make_flags(italic: bool = False, bold: bool = False, caps: bool = False) -> dict:
    return {"italic": italic, "bold": bold, "caps": caps}


def merge_flags(a: dict, b: dict) -> dict:
    """OR-combine two flag dicts."""
    return {
        "italic": a.get("italic", False) or b.get("italic", False),
        "bold": a.get("bold", False) or b.get("bold", False),
        "caps": a.get("caps", False) or b.get("caps", False),
    }


def normalise_occurrence(occ) -> tuple:
    """Accept a 2-tuple or 3-tuple and always return a 3-tuple with a flag dict.

    Used at every load boundary (in-memory merges, JSON load) to tolerate the
    legacy 2-element occurrence shape.
    """
    if len(occ) == 3:
        idx, label, flags = occ
        if not isinstance(flags, dict):
            flags = dict(EMPTY_FLAGS)
        else:
            flags = {
                "italic": bool(flags.get("italic", False)),
                "bold": bool(flags.get("bold", False)),
                "caps": bool(flags.get("caps", False)),
            }
        return (idx, label, flags)
    if len(occ) == 2:
        idx, label = occ
        return (idx, label, dict(EMPTY_FLAGS))
    raise ValueError(f"Unexpected occurrence shape: {occ!r}")


def normalise_raw_results(raw_results: dict) -> dict:
    """Apply normalise_occurrence over every entry in *raw_results* in place."""
    for key, occurrences in list(raw_results.items()):
        raw_results[key] = [normalise_occurrence(o) for o in occurrences]
    return raw_results


def find_keyword_flags_in_tokens(tokens, keyword: str):
    """Search *tokens* for a whole-word, case-insensitive match of *keyword*.

    Returns the OR'd style flag dict from the spanning tokens, or None if
    no match.

    The reconstructed page string joins token texts with single spaces; the
    regex uses Python's standard ``\\b`` word boundaries against that
    reconstruction. Multi-word keywords work because spaces in *keyword*
    line up with the joiner.
    """
    if not keyword.strip():
        return None

    parts = []
    spans = []  # parallel list of (start, end) char offsets in the joined string
    cursor = 0
    word_tokens = []  # only the word-like tokens we kept
    for tok in tokens:
        text = tok.text
        if not text:
            continue
        # Pure-punctuation tokens (including the synthetic "." sentence-end
        # tokens emitted by extract_styled_tokens) are emitted into the
        # reconstruction so multi-word matches do not span sentence boundaries,
        # but no associated word_token is recorded — flags only come from
        # real word tokens.
        if all(unicodedata.category(ch).startswith('P') for ch in text):
            parts.append(text)
            spans.append((cursor, cursor + len(text)))
            cursor += len(text)
            word_tokens.append(None)
            parts.append(" ")
            cursor += 1
            continue
        parts.append(text)
        spans.append((cursor, cursor + len(text)))
        cursor += len(text)
        word_tokens.append(tok)
        parts.append(" ")
        cursor += 1

    joined = "".join(parts).rstrip()
    pattern = re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE)
    m = pattern.search(joined)
    if not m:
        return None

    match_start, match_end = m.span()
    flags = {"italic": False, "bold": False, "caps": False}
    for tok, (s, e) in zip(word_tokens, spans):
        if tok is None:
            continue
        if e <= match_start or s >= match_end:
            continue
        if tok.is_italic:
            flags["italic"] = True
        if tok.is_bold:
            flags["bold"] = True
        if tok.is_all_caps:
            flags["caps"] = True
    return flags


class IndexingThread(QThread):
    progress_updated = pyqtSignal(int)
    indexing_finished = pyqtSignal(dict, dict) # formatted_results, raw_results
    error_occurred = pyqtSignal(str)

    def __init__(self, pdf_path, keywords, page_numbering_strategy, offset=0, start_page=0,
                 index_front_matter=False):
        super().__init__()
        self.pdf_path = pdf_path
        self.keywords = keywords
        self.strategy = page_numbering_strategy  # 'logical' or 'physical'
        self.offset = offset
        self.start_page = start_page
        self._is_running = True
        self.index_front_matter = index_front_matter

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

            from model.name_indexer import extract_styled_tokens

            front_start = 0 if self.index_front_matter and self.start_page > 0 else self.start_page
            front_end = self.start_page  # exclusive
            main_start = self.start_page
            main_end = total_pages

            for kind, page_range in (("front", range(front_start, front_end)),
                                      ("main", range(main_start, main_end))):
                if not self._is_running:
                    break
                if not page_range:
                    continue
                force_roman = (kind == "front")
                for i in page_range:
                    if not self._is_running:
                        break
                    page = doc.load_page(i)
                    tokens = extract_styled_tokens(page)
                    page_label = label_for_page(
                        page, i + 1, self.strategy,
                        offset=self.offset, force_roman=force_roman,
                    )

                    for norm_kw in regex_map.keys():
                        original_kw = keyword_map[norm_kw]
                        flags = find_keyword_flags_in_tokens(tokens, norm_kw)
                        if flags is not None:
                            if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
                                raw_results[original_kw].append((i, page_label, flags))

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
                prev_idx = pages[i-1][0]
                curr_idx = pages[i][0]
                
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
