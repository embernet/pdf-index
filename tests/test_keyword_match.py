from model.indexer import find_keyword_flags_in_tokens
from model.name_indexer import StyledToken


def _tok(word, *, italic=False, bold=False, caps=False):
    return StyledToken(
        text=word, is_bold=bold, is_italic=italic,
        is_superscript=False, is_all_caps=caps, from_all_caps_line=False,
    )


def test_match_plain_text():
    tokens = [_tok("the"), _tok("piano"), _tok("recital")]
    flags = find_keyword_flags_in_tokens(tokens, "piano")
    assert flags is not None
    assert flags == {"italic": False, "bold": False, "caps": False}


def test_match_italic_keyword():
    tokens = [_tok("the"), _tok("piano", italic=True), _tok("recital")]
    flags = find_keyword_flags_in_tokens(tokens, "piano")
    assert flags["italic"] is True
    assert flags["bold"] is False


def test_match_caps_keyword():
    tokens = [_tok("the"), _tok("NATO", caps=True), _tok("summit")]
    flags = find_keyword_flags_in_tokens(tokens, "nato")
    assert flags["caps"] is True


def test_match_multiword_keyword():
    tokens = [_tok("Sound", italic=True), _tok("of", italic=True), _tok("Music", italic=True)]
    flags = find_keyword_flags_in_tokens(tokens, "Sound of Music")
    assert flags["italic"] is True


def test_no_match():
    tokens = [_tok("the"), _tok("piano")]
    assert find_keyword_flags_in_tokens(tokens, "violin") is None


def test_word_boundary_no_substring():
    tokens = [_tok("Concerto")]  # contains "once"
    assert find_keyword_flags_in_tokens(tokens, "once") is None
