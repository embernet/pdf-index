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


def test_style_aware_break_at_block_boundary():
    """A bold heading block followed by a plain-styled paragraph block
    must be split by a synthetic break, even though both adjacent words
    are capitalised. Without the style-mismatch override, the lexical
    rule would suppress the break and merge "James Crow" with "Gosh".
    """
    from model.name_indexer import extract_styled_tokens

    class FakePage:
        def __init__(self, data):
            self._data = data
        def get_text(self, mode):
            assert mode == "dict"
            return self._data

    data = {
        "blocks": [
            {
                "type": 0,
                "lines": [{
                    "bbox": (0.0, 0.0, 50.0, 10.0),  # short heading line
                    "spans": [{"text": "James Crow", "flags": 16}],  # bold
                }],
            },
            {
                "type": 0,
                "lines": [{
                    "bbox": (0.0, 12.0, 200.0, 22.0),  # full-width paragraph line
                    "spans": [{
                        "text": "Gosh wanted to test the indexer.",
                        "flags": 0,
                    }],
                }],
            },
        ],
    }

    tokens = extract_styled_tokens(FakePage(data))
    texts = [t.text for t in tokens]
    crow_idx = texts.index("Crow")
    gosh_idx = texts.index("Gosh")
    between = texts[crow_idx + 1:gosh_idx]
    assert "." in between, (
        f"expected synthetic '.' separator between bold heading and "
        f"plain paragraph; got: {texts}"
    )


def test_hyphenation_join_across_block_boundary():
    """When the two halves of a line-wrapped word land in DIFFERENT
    PyMuPDF blocks (e.g. 'avail-' ending one block and 'able' starting
    the next), the join must still fire so styled-phrase capture
    doesn't later emit them as 'avail- able' or 'avail able'.
    """
    from model.name_indexer import extract_styled_tokens

    class FakePage:
        def __init__(self, data):
            self._data = data
        def get_text(self, mode):
            return self._data

    data = {
        "blocks": [
            {
                "type": 0,
                "lines": [{
                    "bbox": (0.0, 0.0, 200.0, 10.0),
                    "spans": [{
                        "text": "the value is avail-",
                        "flags": 0,
                    }],
                }],
            },
            {
                "type": 0,
                "lines": [{
                    "bbox": (0.0, 12.0, 200.0, 22.0),
                    "spans": [{
                        "text": "able to everyone now.",
                        "flags": 0,
                    }],
                }],
            },
        ],
    }

    tokens = extract_styled_tokens(FakePage(data))
    texts = [t.text for t in tokens]
    assert "available" in texts, (
        f"expected the cross-block hyphenation to fuse 'avail-' + "
        f"'able' into 'available'; got: {texts}"
    )
    assert "avail-" not in texts and "avail" not in texts and "able" not in texts


def test_style_aware_break_suppressed_when_styles_match():
    """If both lines share the same style (e.g. plain prose wrapping),
    the lexical rule still suppresses the break so a wrapped name like
    'Beatrice Halloway' is preserved.
    """
    from model.name_indexer import extract_styled_tokens

    class FakePage:
        def __init__(self, data):
            self._data = data
        def get_text(self, mode):
            return self._data

    data = {
        "blocks": [{
            "type": 0,
            "lines": [
                {
                    "bbox": (0.0, 0.0, 50.0, 10.0),  # short line
                    "spans": [{"text": "...wrote Beatrice", "flags": 0}],
                },
                {
                    "bbox": (0.0, 12.0, 200.0, 22.0),  # next line
                    "spans": [{"text": "Halloway later that week.", "flags": 0}],
                },
            ],
        }],
    }

    tokens = extract_styled_tokens(FakePage(data))
    texts = [t.text for t in tokens]
    bea_idx = texts.index("Beatrice")
    hall_idx = texts.index("Halloway")
    between = texts[bea_idx + 1:hall_idx]
    assert "." not in between, (
        f"plain-styled wrapping should not get a synthetic '.'; "
        f"got: {texts}"
    )
