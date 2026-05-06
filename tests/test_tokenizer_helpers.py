from model.name_indexer import (
    should_suppress_break,
    try_hyphenation_join,
)


def test_suppress_break_both_capitalised():
    # Last word of previous line and first word of next line both capitalised
    # → no break, treat as continued phrase.
    assert should_suppress_break("Bridgewater", "Hall") is True


def test_suppress_break_lowercase_after():
    # Continuation looks like prose, not a phrase. Keep the break.
    assert should_suppress_break("ended", "with") is False


def test_suppress_break_lowercase_before():
    # Previous line ended in lowercase: it was prose, not a phrase ending.
    assert should_suppress_break("said", "John") is False


def test_suppress_break_empty():
    assert should_suppress_break("", "Hall") is False
    assert should_suppress_break("Hall", "") is False
    assert should_suppress_break("", "") is False


def test_hyphenation_join_lowercase_continuation():
    # Bridge- + water = Bridgewater (continuation lowercase)
    assert try_hyphenation_join("Bridge-", "water") == "Bridgewater"


def test_hyphenation_join_uppercase_continuation_is_real_compound():
    # Anglo- + Saxon stays as two separate tokens (real hyphenated compound).
    assert try_hyphenation_join("Anglo-", "Saxon") is None


def test_hyphenation_join_no_trailing_hyphen():
    assert try_hyphenation_join("Bridge", "water") is None


def test_hyphenation_join_empty():
    assert try_hyphenation_join("", "water") is None
    assert try_hyphenation_join("Bridge-", "") is None
