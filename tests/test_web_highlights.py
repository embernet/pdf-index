"""Tests for the shared term -> word-index matching helpers used by the
desktop viewer and the web bundle exporter."""
from model.web_highlights import (
    search_variants,
    match_term_at,
    merge_word_indices_to_spans,
    rects_for_term,
)


def _word(text, x=0, y=0):
    # PyMuPDF tuple: (x0, y0, x1, y1, text, block, line, word_no)
    return (float(x), float(y), float(x + len(text)), float(y + 1), text, 0, 0, 0)


def test_search_variants_single():
    assert search_variants("Manchester") == [["Manchester"]]


def test_search_variants_inverted_name():
    variants = search_variants("Smith, John")
    # Comma form is preserved as-is, plus a natural-order variant
    assert ["John", "Smith"] in variants


def test_match_single_word():
    words = [_word("the", 0), _word("Manchester", 4)]
    assert match_term_at(words, 1, ["Manchester"]) == [1]


def test_no_match_returns_none():
    words = [_word("the"), _word("piano")]
    assert match_term_at(words, 0, ["Manchester"]) is None


def test_match_hyphenation_split():
    words = [_word("the"), _word("Manch-"), _word("ester"), _word("historian")]
    assert match_term_at(words, 1, ["Manchester"]) == [1, 2]


def test_match_strips_possessive():
    # "Pemberton's" should match "Pemberton"
    words = [_word("Pemberton's")]
    assert match_term_at(words, 0, ["Pemberton"]) == [0]


def test_match_strips_curly_quotes():
    words = [_word("‘A"), _word("New", x=4), _word("Method’", x=8)]
    assert match_term_at(words, 0, ["A", "New", "Method"]) == [0, 1, 2]


def test_match_strips_trailing_footnote_digit():
    # PDF: "Gift7" where 7 is a footnote marker glued to "Gift".
    # Target: just "Gift" should still match.
    words = [_word("Gift7")]
    assert match_term_at(words, 0, ["Gift"]) == [0]


def test_match_multiword_with_trailing_footnote_on_last_word():
    # The reported bug: "Alicia's Gift" followed by footnote 7 →
    # PDF tokens "Alicia's", "Gift7". Full phrase must still match.
    words = [_word("Alicia's"), _word("Gift7", x=10)]
    assert match_term_at(words, 0, ["Alicia's", "Gift"]) == [0, 1]


def test_match_strips_trailing_asterisk_footnote():
    # Some PDFs use asterisk-style footnote markers.
    words = [_word("Gift*")]
    assert match_term_at(words, 0, ["Gift"]) == [0]


def test_match_preserves_digit_only_token():
    # "1980" must still match itself — don't strip when the word is
    # all digits (would lose the content).
    words = [_word("1980")]
    assert match_term_at(words, 0, ["1980"]) == [0]


def test_match_preserves_trailing_digit_when_target_also_has_it():
    # "USB2" target against "USB2" PDF word must match directly.
    words = [_word("USB2")]
    assert match_term_at(words, 0, ["USB2"]) == [0]


def test_case_aware_uppercase_target_blocks_lowercase_pdf():
    words = [_word("manchester")]
    assert match_term_at(words, 0, ["Manchester"]) is None


def test_case_aware_lowercase_target_matches_anything():
    words = [_word("Polonaise")]
    assert match_term_at(words, 0, ["polonaise"]) == [0]


def test_merge_consecutive_same_line():
    # Three words on the same y-row that all belong to one term
    words = [_word("New", 0, 0), _word("York", 4, 0), _word("City", 9, 0)]
    spans = merge_word_indices_to_spans(words, [0, 1, 2])
    # One span covering all three
    assert len(spans) == 1
    x0, y0, x1, y1 = spans[0]
    assert x0 == 0.0
    assert x1 == 13.0  # right edge of "City"


def test_merge_splits_different_lines():
    words = [_word("foo", 0, 0), _word("bar", 0, 10)]
    spans = merge_word_indices_to_spans(words, [0, 1])
    assert len(spans) == 2


def test_rects_for_term_returns_normalised_rects():
    # "Manchester" appears once at x=4, y=0
    words = [_word("the", 0, 0), _word("Manchester", 4, 0)]
    rects = rects_for_term(words, "Manchester")
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    assert (x0, y0, x1, y1) == (4.0, 0.0, 14.0, 1.0)


def test_rects_for_term_inverted_name_finds_natural_order():
    # PDF contains "John Smith"; index entry is "Smith, John"
    words = [_word("John", 0, 0), _word("Smith", 5, 0)]
    rects = rects_for_term(words, "Smith, John")
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    assert x0 == 0.0
    assert x1 == 10.0  # right edge of "Smith"
