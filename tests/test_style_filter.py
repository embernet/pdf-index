from model.indexer import filter_by_style


def _occ(idx, label, **flags):
    return [idx, label, {
        "italic": flags.get("italic", False),
        "bold": flags.get("bold", False),
        "caps": flags.get("caps", False),
    }]


def test_aggregate_returns_full_dict():
    raw = {"alpha": [_occ(1, "1"), _occ(2, "2")]}
    out = filter_by_style(raw, "aggregate")
    assert out == raw


def test_italic_filters_to_italic_pages_only():
    raw = {
        "alpha": [_occ(1, "1", italic=True), _occ(2, "2"), _occ(3, "3", italic=True)],
        "beta": [_occ(5, "5")],
    }
    out = filter_by_style(raw, "italic")
    assert "alpha" in out
    assert len(out["alpha"]) == 2
    assert out["alpha"][0][0] == 1
    assert out["alpha"][1][0] == 3
    assert "beta" not in out  # no italic pages anywhere


def test_other_excludes_styled_pages():
    raw = {"alpha": [_occ(1, "1", italic=True), _occ(2, "2"), _occ(3, "3", caps=True)]}
    out = filter_by_style(raw, "other")
    assert len(out["alpha"]) == 1
    assert out["alpha"][0][0] == 2


def test_entry_dropped_when_no_pages_match():
    raw = {"alpha": [_occ(1, "1", italic=True)]}
    out = filter_by_style(raw, "bold")
    assert out == {}
