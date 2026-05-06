from model.name_indexer import (
    StyledToken,
    extract_names_from_tokens,
    extract_italic_phrases,
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
    assert any(n == "NATO" for n, _ in names)


def test_skips_all_caps_line():
    # Whole line is all caps — heading, not names.
    tokens = _tokens("INTRODUCTION", all_caps_line=True)
    names = extract_names_from_tokens(tokens)
    assert names == []


def test_admits_all_caps_inside_capitalised_run():
    # "European NATO Summit" — all three capitalised, NATO is all-caps.
    tokens = _tokens("European NATO Summit")
    names = extract_names_from_tokens(tokens)
    by_text = dict(names)
    assert "European NATO Summit" in by_text
    assert by_text["European NATO Summit"]["caps"] is True


def test_extract_italic_phrase_lowercase():
    # Italic Latin phrase — no word capitalised.
    tokens = _tokens("in vino veritas", italic=True)
    out = extract_italic_phrases(tokens)
    assert "in vino veritas" in out


def test_extract_italic_phrase_with_connectors():
    # Connectors (of, and) do not break italic runs — preserve titles.
    tokens = _tokens("The Sound of Music", italic=True)
    out = extract_italic_phrases(tokens)
    assert "The Sound of Music" in out


def test_extract_italic_skips_non_italic():
    # Plain text is not captured by the italic pass.
    tokens = _tokens("plain text only", italic=False)
    out = extract_italic_phrases(tokens)
    assert out == []


def test_extract_italic_break_on_non_italic_word():
    # Italic phrase ends when italic flag turns off; restarts when it returns.
    tokens = (
        _tokens("Pride and Prejudice", italic=True)
        + _tokens("interrupted", italic=False)
        + _tokens("Sense and Sensibility", italic=True)
    )
    out = extract_italic_phrases(tokens)
    assert "Pride and Prejudice" in out
    assert "Sense and Sensibility" in out
    assert "interrupted" not in out
