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


def _quote_token(text):
    """Build a single-character punctuation token for a curly quote."""
    return StyledToken(
        text=text, is_bold=False, is_italic=False, is_superscript=False,
        is_all_caps=False, from_all_caps_line=False,
    )


def test_extract_quoted_captures_phrase_between_curly_quotes():
    from model.name_indexer import extract_quoted_phrases
    # 'A New Method' wrapped in matched curly single quotes.
    tokens = (
        _tokens("Beatrice labelled it", italic=False)
        + [_quote_token("‘")]
        + _tokens("A New Method", italic=False)
        + [_quote_token("’")]
        + _tokens("today", italic=False)
    )
    out = extract_quoted_phrases(tokens)
    assert "A New Method" in out


def test_extract_quoted_does_not_capture_outside_quotes():
    from model.name_indexer import extract_quoted_phrases
    tokens = _tokens("just plain prose with no quotes", italic=False)
    out = extract_quoted_phrases(tokens)
    assert out == []


def test_extract_quoted_does_not_split_on_apostrophe_inside_word():
    from model.name_indexer import extract_quoted_phrases
    # "O’Donnell" is one token with a curly apostrophe; the quoted run
    # should NOT end on it because the closing-quote token must appear
    # standalone to terminate the run.
    tokens = (
        [_quote_token("‘")]
        + [StyledToken(text="O’Donnell", is_bold=False, is_italic=False,
                       is_superscript=False, is_all_caps=False,
                       from_all_caps_line=False)]
        + _tokens("Method", italic=False)
        + [_quote_token("’")]
    )
    out = extract_quoted_phrases(tokens)
    assert "O’Donnell Method" in out


def test_extract_quoted_drops_lone_stop_word():
    from model.name_indexer import extract_quoted_phrases
    tokens = (
        [_quote_token("‘")]
        + _tokens("the", italic=False)
        + [_quote_token("’")]
    )
    out = extract_quoted_phrases(tokens)
    assert out == []


def test_extract_quoted_handles_span_split_apostrophe():
    """When a style change splits 'Chetham’s' into separate spans, the
    second span starts with the curly apostrophe ’ which the per-span
    tokenizer can't fold back into the preceding word. Without merging,
    the standalone ’ token would close the quote prematurely and capture
    only 'Chetham' instead of the full title.
    """
    from model.name_indexer import extract_styled_tokens, extract_quoted_phrases

    class FakePage:
        def __init__(self, data):
            self._data = data
        def get_text(self, mode):
            return self._data

    # Mimic PyMuPDF emitting "Chetham" and "’s piano summer school" as
    # adjacent spans (e.g. an italicised name followed by plain prose).
    data = {
        "blocks": [{
            "type": 0,
            "lines": [{
                "bbox": (0.0, 0.0, 400.0, 10.0),
                "spans": [
                    {"text": "Joe was at ‘", "flags": 0},
                    {"text": "Chetham", "flags": 2},          # italic
                    {"text": "’s piano summer school’ last week.", "flags": 0},
                ],
            }],
        }],
    }
    tokens = extract_styled_tokens(FakePage(data))
    out = extract_quoted_phrases(tokens)
    assert "Chetham’s piano summer school" in out, (
        f"expected the full title to be captured despite the span split "
        f"at the apostrophe; got {out!r}"
    )


def test_extract_quoted_preserves_possessive_in_title():
    """Titles enclosed in single quotes are literal proper names whose
    possessive 's is part of the name. Stripping the possessive would
    mangle real institutions like 'Chetham's Piano Summer School'.
    """
    from model.name_indexer import extract_quoted_phrases

    tokens = (
        [_quote_token("‘")]
        + [StyledToken(text="Chetham’s", is_bold=False, is_italic=False,
                       is_superscript=False, is_all_caps=False,
                       from_all_caps_line=False)]
        + _tokens("Piano School", italic=False)
        + [_quote_token("’")]
    )
    out = extract_quoted_phrases(tokens)
    assert "Chetham’s Piano School" in out


def test_possessive_stripped_when_phrase_ends_at_possessive():
    """'Adam Gorb’s book was released' — Gorb’s is followed by a common
    word, so the proper-noun phrase ended at Gorb. The 's must be stripped.
    """
    tokens = [
        StyledToken(text=w, is_bold=False, is_italic=False, is_superscript=False,
                    is_all_caps=False, from_all_caps_line=False)
        for w in ("Then", "Adam", "Gorb’s", "book", "was", "released", ".")
    ]
    names = [n for n, _ in extract_names_from_tokens(tokens)]
    assert "Adam Gorb" in names
    assert "Adam Gorb’s" not in names


def test_possessive_preserved_when_phrase_continues():
    """'Adam Gorb’s Ballade was played' — Ballade is also a capitalised
    name word, so Gorb’s is mid-phrase and the apostrophe is part of the
    title. The captured entry must be 'Adam Gorb’s Ballade'.
    """
    tokens = [
        StyledToken(text=w, is_bold=False, is_italic=False, is_superscript=False,
                    is_all_caps=False, from_all_caps_line=False)
        for w in ("Then", "Adam", "Gorb’s", "Ballade", "was", "played", ".")
    ]
    names = [n for n, _ in extract_names_from_tokens(tokens)]
    assert "Adam Gorb’s Ballade" in names
    assert "Adam Gorb Ballade" not in names


def test_match_finds_internal_possessive_title():
    """find_known_names_in_tokens must be able to locate a vocab entry
    that contains a mid-phrase possessive."""
    from model.name_indexer import find_known_names_in_tokens
    tokens = [
        StyledToken(text=w, is_bold=False, is_italic=False, is_superscript=False,
                    is_all_caps=False, from_all_caps_line=False)
        for w in ("Then", "Adam", "Gorb’s", "Ballade", "was", "played", ".")
    ]
    vocab = {"Adam Gorb’s Ballade"}
    vocab_lower = {"adam gorb’s ballade": "Adam Gorb’s Ballade"}
    found = [n for n, _ in find_known_names_in_tokens(tokens, vocab, vocab_lower, 5)]
    assert "Adam Gorb’s Ballade" in found


def test_match_finds_canonical_name_through_terminal_possessive():
    """find_known_names_in_tokens must still match 'Adam Gorb' inside
    text where it appears as 'Adam Gorb’s book' — the trailing possessive
    is what was stripped when the vocab entry was discovered, so the
    matcher needs to mirror that stripping here."""
    from model.name_indexer import find_known_names_in_tokens
    tokens = [
        StyledToken(text=w, is_bold=False, is_italic=False, is_superscript=False,
                    is_all_caps=False, from_all_caps_line=False)
        for w in ("Then", "Adam", "Gorb’s", "book", "was", "released", ".")
    ]
    vocab = {"Adam Gorb"}
    vocab_lower = {"adam gorb": "Adam Gorb"}
    found = [n for n, _ in find_known_names_in_tokens(tokens, vocab, vocab_lower, 5)]
    assert "Adam Gorb" in found


def test_extract_quoted_still_closes_on_real_closing_quote():
    """A closing ’ followed by a normal-length capitalised word (the next
    sentence) is NOT a contraction — it must still close the run."""
    from model.name_indexer import extract_quoted_phrases
    tokens = (
        [_quote_token("‘")]
        + _tokens("Title Here", italic=False)
        + [_quote_token("’")]
        + _tokens("Other words follow", italic=False)
    )
    out = extract_quoted_phrases(tokens)
    assert "Title Here" in out
    # Importantly, "Other" must NOT have been absorbed into the run.
    assert not any("Other" in p for p in out)


def _occ(idx, label="x", flags=None):
    if flags is None:
        flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
    return (idx, label, flags)


def test_suppress_substring_duplicates_drops_subset_match():
    """Fisher pages ⊆ Norma Fisher pages → Fisher dropped."""
    from model.name_indexer import _suppress_substring_duplicates
    raw = {
        "Fisher": [_occ(7), _occ(43), _occ(46)],
        "Norma Fisher": [_occ(7), _occ(43), _occ(46)],
    }
    _suppress_substring_duplicates(raw)
    assert "Norma Fisher" in raw
    assert "Fisher" not in raw


def test_suppress_substring_duplicates_keeps_partial_overlap():
    """Manchester appears on a page Manchester Free Trade Hall doesn't —
    keep the standalone entry intact."""
    from model.name_indexer import _suppress_substring_duplicates
    raw = {
        "Manchester": [_occ(1), _occ(3)],
        "Manchester Free Trade Hall": [_occ(2), _occ(3)],
    }
    _suppress_substring_duplicates(raw)
    assert "Manchester" in raw
    assert "Manchester Free Trade Hall" in raw


def test_suppress_substring_duplicates_multi_word_substring():
    """Chopin Sonata in B-flat is a substring of Chopin Sonata in B-flat
    minor; both on page 196 → shorter dropped.
    """
    from model.name_indexer import _suppress_substring_duplicates
    raw = {
        "Chopin Sonata in B-flat": [_occ(196)],
        "Chopin Sonata in B-flat minor": [_occ(196)],
    }
    _suppress_substring_duplicates(raw)
    assert "Chopin Sonata in B-flat minor" in raw
    assert "Chopin Sonata in B-flat" not in raw


def test_suppress_substring_duplicates_union_coverage():
    """Fisher's pages spread across two longer entries that together
    cover them all → Fisher is dropped."""
    from model.name_indexer import _suppress_substring_duplicates
    raw = {
        "Fisher": [_occ(1), _occ(5), _occ(10)],
        "Norma Fisher": [_occ(1), _occ(5)],
        "Smith Fisher": [_occ(10)],
    }
    _suppress_substring_duplicates(raw)
    assert "Fisher" not in raw
    assert "Norma Fisher" in raw
    assert "Smith Fisher" in raw


def test_suppress_substring_duplicates_inverted_form():
    """Halloway pages ⊆ "Halloway, Beatrice" pages → drop the standalone."""
    from model.name_indexer import _suppress_substring_duplicates
    raw = {
        "Halloway": [_occ(1), _occ(2)],
        "Halloway, Beatrice": [_occ(1), _occ(2), _occ(3)],
    }
    _suppress_substring_duplicates(raw)
    assert "Halloway" not in raw
    assert "Halloway, Beatrice" in raw


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
