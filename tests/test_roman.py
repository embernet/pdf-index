import pytest
from model.indexer import to_lowercase_roman, looks_like_roman


def test_to_lowercase_roman_basic():
    assert to_lowercase_roman(1) == "i"
    assert to_lowercase_roman(2) == "ii"
    assert to_lowercase_roman(4) == "iv"
    assert to_lowercase_roman(9) == "ix"
    assert to_lowercase_roman(12) == "xii"
    assert to_lowercase_roman(40) == "xl"
    assert to_lowercase_roman(99) == "xcix"


def test_to_lowercase_roman_zero_or_negative():
    # Defensive: front matter is 1-indexed, but guard against bad inputs.
    assert to_lowercase_roman(0) == ""
    assert to_lowercase_roman(-1) == ""


def test_looks_like_roman_positive():
    assert looks_like_roman("iv")
    assert looks_like_roman("IV")
    assert looks_like_roman("xii")
    assert looks_like_roman("MCMLXXXIV")


def test_looks_like_roman_negative():
    assert not looks_like_roman("")
    assert not looks_like_roman("12")
    assert not looks_like_roman("iv1")
    assert not looks_like_roman("hello")
