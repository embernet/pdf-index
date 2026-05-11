"""Tests for the per-occurrence context window helper used by LLM enrichment."""
from model.name_indexer import StyledToken, extract_context_window


def _tok(word):
    return StyledToken(
        text=word, is_bold=False, is_italic=False,
        is_superscript=False, is_all_caps=False, from_all_caps_line=False,
    )


def _toks(sentence):
    return [_tok(w) for w in sentence.split()]


def test_returns_window_around_match():
    tokens = _toks("the famous composer Chopin wrote many nocturnes during his lifetime")
    ctx = extract_context_window(tokens, "Chopin", window_chars=80)
    assert "Chopin" in ctx
    assert "composer" in ctx or "wrote" in ctx
    # The full sentence is shorter than the window so we get most of it
    assert len(ctx) > 20


def test_returns_empty_when_no_match():
    tokens = _toks("the famous composer wrote many nocturnes")
    assert extract_context_window(tokens, "Chopin") == ""


def test_handles_empty_inputs():
    assert extract_context_window([], "Chopin") == ""
    assert extract_context_window(_toks("Chopin works"), "") == ""


def test_window_is_bounded():
    long_text = " ".join(["padding"] * 200 + ["TARGET"] + ["padding"] * 200)
    tokens = _toks(long_text)
    ctx = extract_context_window(tokens, "TARGET", window_chars=120)
    assert "TARGET" in ctx
    # Window should be roughly window_chars long, not the full 2000+ chars
    assert len(ctx) < 300


def test_match_is_case_insensitive():
    tokens = _toks("the piano was a marvel")
    ctx = extract_context_window(tokens, "PIANO")
    assert "piano" in ctx
