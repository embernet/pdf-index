"""Tests for the Go-To-Page label resolver.

The resolver maps a user-entered printed-page label (e.g. 'iii', '5',
'-19') to the 0-based physical index of the PDF page bearing that label
under the active strategy + offset. Labels are pre-computed by
``label_for_page`` so the resolver itself is strategy-agnostic.
"""

from model.indexer import resolve_label_to_index


def test_exact_match_returns_physical_index():
    labels = ["i", "ii", "iii", "iv", "1", "2", "3"]
    assert resolve_label_to_index("iii", labels) == 2
    assert resolve_label_to_index("2", labels) == 5


def test_case_insensitive_roman_match():
    # User may type 'iii' or 'III' — both resolve.
    labels = ["I", "II", "III", "IV"]
    assert resolve_label_to_index("iii", labels) == 2
    assert resolve_label_to_index("IV", labels) == 3


def test_no_match_returns_none():
    labels = ["1", "2", "3"]
    assert resolve_label_to_index("99", labels) is None
    assert resolve_label_to_index("iii", labels) is None


def test_whitespace_is_trimmed():
    labels = ["1", "2", "3"]
    assert resolve_label_to_index("  2  ", labels) == 1


def test_empty_input_returns_none():
    labels = ["1", "2"]
    assert resolve_label_to_index("", labels) is None
    assert resolve_label_to_index("   ", labels) is None
    assert resolve_label_to_index(None, labels) is None


def test_first_match_wins_on_duplicate_labels():
    # In physical strategy with offset, duplicate labels are impossible;
    # in logical strategy with weird embedded labels, two pages might
    # share a label. Resolver returns the first.
    labels = ["1", "2", "2", "3"]
    assert resolve_label_to_index("2", labels) == 1


def test_offset_label_mapping():
    """Physical strategy + offset = -20 means physical 21 displays as
    '1'. The resolver, given the precomputed labels, must return
    physical index 20 (0-based) for input '1'.
    """
    # Simulate label_for_page(strategy='physical', offset=-20) over
    # physical pages 1..25 → labels are '-19'..'5'.
    labels = [str(p + (-20)) for p in range(1, 26)]
    assert labels[0] == "-19"
    assert labels[20] == "1"
    assert resolve_label_to_index("1", labels) == 20
    assert resolve_label_to_index("5", labels) == 24
    # A label that maps to a sub-zero printed page is still resolvable.
    assert resolve_label_to_index("-19", labels) == 0
