from model.name_indexer import (
    StyledToken,
    extract_names_from_tokens,
)


def _tokens(text: str, *, italic=False, all_caps_line=False, all_caps=None):
    """Tiny helper: build a list of StyledToken from whitespace-split text."""
    out = []
    for word in text.split():
        is_caps = all_caps if all_caps is not None else word.isupper() and len(word) > 1
        out.append(StyledToken(
            text=word,
            is_bold=False,
            is_italic=italic,
            is_superscript=False,
            is_all_caps=is_caps,
            from_all_caps_line=all_caps_line,
        ))
    return out


def test_admits_single_all_caps_token_in_mixed_line():
    # NATO sits in mid-sentence with normal-case neighbours.
    tokens = _tokens("the NATO summit")
    names = extract_names_from_tokens(tokens)
    assert "NATO" in names


def test_skips_all_caps_line():
    # Whole line is all caps — heading, not names.
    tokens = _tokens("INTRODUCTION", all_caps_line=True)
    names = extract_names_from_tokens(tokens)
    assert names == []


def test_admits_all_caps_inside_capitalised_run():
    # "European NATO Summit" — all three capitalised, NATO is all-caps.
    tokens = _tokens("European NATO Summit")
    names = extract_names_from_tokens(tokens)
    # The whole run is one entry.
    assert "European NATO Summit" in names
