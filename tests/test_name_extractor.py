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


def test_extract_italic_drops_title_prefix():
    # An italic title prefix (Dr, Mr, Mrs, Sir) is skipped without breaking
    # the run, so "Dr Edmund Crawley" italic yields "Edmund Crawley".
    tokens = _tokens("Dr Edmund Crawley", italic=True)
    out = extract_italic_phrases(tokens)
    assert "Edmund Crawley" in out
    assert "Dr Edmund Crawley" not in out


def test_extract_italic_drops_lone_stop_word():
    # A single-token italic run that is just a stop word is dropped.
    tokens = _tokens("the", italic=True)
    out = extract_italic_phrases(tokens)
    assert out == []


def test_extract_italic_keeps_stop_word_in_phrase():
    # Stop words inside a multi-token italic phrase are preserved.
    tokens = _tokens("the polonaise", italic=True)
    out = extract_italic_phrases(tokens)
    assert "the polonaise" in out


def _bold_tokens(text: str):
    """Like _tokens but with bold styling instead of italic."""
    out = []
    for word in text.split():
        is_caps = word.isupper() and len(word) > 1
        out.append(StyledToken(
            text=word,
            is_bold=True,
            is_italic=False,
            is_superscript=False,
            is_all_caps=is_caps,
            from_all_caps_line=False,
        ))
    return out


def test_extract_bold_phrase_captures_multi_word_run():
    from model.name_indexer import extract_bold_phrases
    # "A note on proximity" entirely bold — captured as one phrase even
    # though it starts with a stop word.
    tokens = _bold_tokens("A note on proximity")
    out = extract_bold_phrases(tokens)
    assert "A note on proximity" in out


def test_extract_bold_phrase_drops_lone_stop_word():
    from model.name_indexer import extract_bold_phrases
    tokens = _bold_tokens("the")
    out = extract_bold_phrases(tokens)
    assert out == []


def test_extract_bold_phrase_skips_non_bold():
    from model.name_indexer import extract_bold_phrases
    tokens = _tokens("plain text only", italic=False)
    out = extract_bold_phrases(tokens)
    assert out == []


def test_styled_bypass_single_word_dropped():
    """A single capitalised word admitted via the styled-bypass at
    sentence-start (italic 'Piano' alone) is dropped on flush. Without
    this rule, the word would seed the vocabulary and find_known_names
    would then match every plain 'Piano' elsewhere in the document.
    """
    # Italic "Piano" at sentence-start, followed by a lowercase italic
    # word that ends the n-gram. With the old behaviour the n-gram
    # ['Piano'] would be emitted via styled bypass.
    tokens = (
        _tokens("Piano", italic=True)        # styled-bypass admit
        + _tokens("notes", italic=False)     # lowercase: ends the n-gram
    )
    names = extract_names_from_tokens(tokens)
    assert not any(n == "Piano" for n, _ in names)


def test_italic_only_mid_sentence_word_emits_with_italic_flag():
    """A capitalised word that only ever appears italic mid-sentence
    (e.g. an italicised publication name 'Piano') is still emitted by
    extract_names_from_tokens — but with italic=True in its flag dict
    so the controller can route it to italic_vocab instead of cap_vocab.
    """
    # "the journal Piano covers" — Piano italic, mid-sentence.
    tokens = (
        _tokens("the journal", italic=False)
        + _tokens("Piano", italic=True)
        + _tokens("covers everything", italic=False)
    )
    names = extract_names_from_tokens(tokens)
    by_text = dict(names)
    assert "Piano" in by_text
    assert by_text["Piano"]["italic"] is True
    assert by_text["Piano"]["bold"] is False


def test_styled_bypass_multi_word_kept():
    """Multi-word styled n-grams admitted via styled-bypass are kept —
    the bypass exists precisely so titles like 'The Sound of Music'
    starting at a paragraph break don't get filtered.
    """
    # Italic "Pride and Prejudice" at sentence-start.
    tokens = _tokens("Pride and Prejudice", italic=True)
    names = extract_names_from_tokens(tokens)
    assert any(n == "Pride and Prejudice" for n, _ in names)
