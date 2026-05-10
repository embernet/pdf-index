"""Unit tests for the PDF viewer's highlight matching helper.

Exercises _match_term_at with synthetic PyMuPDF-style word tuples so we don't
need a real PDF or a Qt event loop. Each tuple is (x0, y0, x1, y1, text,
block, line, word_no) — only index 4 (text) matters here.
"""
from PyQt6.QtWidgets import QApplication

# A QApplication must exist before we instantiate any QWidget subclass.
_app = QApplication.instance() or QApplication([])

from view.pdf_viewer import PDFViewer


def _word(text, x=0):
    return (float(x), 0.0, float(x + len(text)), 1.0, text, 0, 0, 0)


def _viewer():
    """Build a PDFViewer instance just to call its matching helpers."""
    return PDFViewer()


def test_match_single_word():
    v = _viewer()
    words = [_word("the", 0), _word("Manchester", 4), _word("historian", 15)]
    assert v._match_term_at(words, 1, ["Manchester"]) == [1]


def test_no_match_returns_none():
    v = _viewer()
    words = [_word("the"), _word("piano")]
    assert v._match_term_at(words, 0, ["Manchester"]) is None


def test_match_hyphenation_split():
    # "Manch-" + "ester" should match "Manchester" via the hyphenation join.
    v = _viewer()
    words = [_word("the"), _word("Manch-"), _word("ester"), _word("historian")]
    assert v._match_term_at(words, 1, ["Manchester"]) == [1, 2]


def test_no_hyphenation_join_when_continuation_uppercase():
    # "Anglo-" + "Saxon" must not join because Saxon starts uppercase
    # (real hyphenated compound, not a line-break split).
    v = _viewer()
    words = [_word("Anglo-"), _word("Saxon")]
    assert v._match_term_at(words, 0, ["AngloSaxon"]) is None


def test_match_multiword_term_with_hyphenated_first_word():
    # "Manch-" + "ester" + "Free" + "Trade" + "Hall" matches
    # "Manchester Free Trade Hall" — first target word spans two PDF words.
    v = _viewer()
    words = [
        _word("Manch-"), _word("ester"),
        _word("Free"), _word("Trade"), _word("Hall"),
    ]
    target = ["Manchester", "Free", "Trade", "Hall"]
    assert v._match_term_at(words, 0, target) == [0, 1, 2, 3, 4]


def test_match_multiword_term_with_hyphenated_middle_word():
    # Hyphenation split inside a multi-word phrase ("Royal North-ern College").
    v = _viewer()
    words = [_word("Royal"), _word("North-"), _word("ern"), _word("College")]
    target = ["Royal", "Northern", "College"]
    assert v._match_term_at(words, 0, target) == [0, 1, 2, 3]


def test_case_aware_match_blocks_lowercase_pdf_for_uppercase_target():
    # Target "Manchester" requires the PDF word to start uppercase.
    v = _viewer()
    words = [_word("manchester")]
    assert v._match_term_at(words, 0, ["Manchester"]) is None


def test_case_aware_match_allows_lowercase_target():
    # Lowercase target word matches any case (case-insensitive comparison).
    v = _viewer()
    words = [_word("Polonaise")]
    assert v._match_term_at(words, 0, ["polonaise"]) == [0]


def test_match_strips_curly_quotes_from_pdf_word():
    # PyMuPDF's get_text("words") keeps the opening curly quote attached
    # to the next word ("‘A") and the closing curly quote attached to
    # the previous word ("Method’"). Single-quotes-rule entries like
    # "A New Method" need to highlight across ‘A New Method’ on the page.
    v = _viewer()
    words = [_word("‘A"), _word("New", x=4), _word("Method’", x=8)]
    assert v._match_term_at(words, 0, ["A", "New", "Method"]) == [0, 1, 2]
