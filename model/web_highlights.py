"""Term -> word-index / word-rect matching helpers.

Extracted from view/pdf_viewer.py so the web bundle exporter
(model/web_bundle.py) can reuse the exact same matching rules without
pulling in PyQt6. The desktop viewer continues to call these via thin
wrappers that adapt them to its image_label.words list.
"""
import unicodedata

# Punctuation characters stripped from both edges of a PDF word before
# comparison. Curly quotes are included because PyMuPDF's get_text("words")
# keeps them attached to adjacent words (‘A, Method’).
_STRIP_CHARS = '.,;:!?()[]{}"\'-/‘’'


def _normalise_word(word: str) -> str:
    """Strip surrounding punctuation, curly quotes, and possessive
    suffix ('s/’s) before comparison.
    """
    stripped = word.strip(_STRIP_CHARS)
    if stripped.endswith("'s") or stripped.endswith("’s"):
        stripped = stripped[:-2]
    return stripped


def _words_equal(pdf_word: str, target_word: str) -> bool:
    """Case-aware word equality: an uppercase target requires an
    uppercase PDF word; otherwise compare case-insensitively.
    """
    if target_word and target_word[0].isupper():
        if not pdf_word or not pdf_word[0].isupper():
            return False
    return pdf_word.lower() == target_word.lower()


def search_variants(term: str) -> list[list[str]]:
    """Return word-lists to try matching for *term*.

    For "Smith, John" we also try the natural-order "John Smith".
    """
    term_normalized = unicodedata.normalize("NFKC", term)
    variants = [term_normalized.split()]
    if ", " in term_normalized:
        parts = term_normalized.split(", ", 1)
        variants.append((parts[1] + " " + parts[0]).split())
    return variants


def match_term_at(words, start_idx: int, target_words: list[str]):
    """Try to match *target_words* against *words* starting at *start_idx*.

    Each target word matches either a single PDF word or a
    hyphenation-joined pair (PDF word ending in '-' followed by a PDF
    word starting lowercase). Possessive suffixes are stripped before
    comparison. Returns the list of PDF-word indices consumed by the
    match, or None.
    """
    matched = []
    pdf_pos = start_idx

    for target_word in target_words:
        if pdf_pos >= len(words):
            return None

        target_stripped = _normalise_word(target_word)
        word_text = unicodedata.normalize("NFKC", words[pdf_pos][4])
        word_stripped = _normalise_word(word_text)

        if _words_equal(word_stripped, target_stripped):
            matched.append(pdf_pos)
            pdf_pos += 1
            continue

        # Hyphenation join: '<prev>-' + '<next>' where next starts lowercase.
        if (pdf_pos + 1 < len(words)
                and word_text.endswith("-")
                and words[pdf_pos + 1][4]
                and words[pdf_pos + 1][4][0].islower()):
            joined = (
                word_text[:-1]
                + unicodedata.normalize("NFKC", words[pdf_pos + 1][4])
            )
            joined_stripped = _normalise_word(joined)
            if _words_equal(joined_stripped, target_stripped):
                matched.append(pdf_pos)
                matched.append(pdf_pos + 1)
                pdf_pos += 2
                continue

        return None

    return matched


def merge_word_indices_to_spans(words, indices):
    """Group sorted word indices into rects, merging consecutive
    indices that sit on the same line into a single span. Returns a
    list of (x0, y0, x1, y1) rects in PDF-point coordinates.

    Two indices are on the same line when their y0 coordinates differ
    by less than 1.0 point.
    """
    if not indices:
        return []
    sorted_idx = sorted(set(indices))
    spans = []
    current = [sorted_idx[0]]
    for i in sorted_idx[1:]:
        prev = current[-1]
        same_line = abs(words[i][1] - words[prev][1]) < 1.0
        consecutive = (i == prev + 1)
        if same_line and consecutive:
            current.append(i)
        else:
            spans.append(current)
            current = [i]
    spans.append(current)

    out = []
    for span in spans:
        x0 = min(words[i][0] for i in span)
        y0 = min(words[i][1] for i in span)
        x1 = max(words[i][2] for i in span)
        y1 = max(words[i][3] for i in span)
        out.append((x0, y0, x1, y1))
    return out


def rects_for_term(words, term: str):
    """Return all merged word-rects on a page that match *term*.

    Tries each variant returned by search_variants, dedupes by index
    span, and merges adjacent same-line matches.
    """
    all_indices = set()
    for term_words in search_variants(term):
        if not term_words:
            continue
        for i in range(len(words)):
            matched = match_term_at(words, i, term_words)
            if matched is not None:
                all_indices.update(matched)
    return merge_word_indices_to_spans(words, sorted(all_indices))
