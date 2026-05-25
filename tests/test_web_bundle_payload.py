"""Unit tests for the pure payload-building helpers in
model/web_bundle.py. PyMuPDF calls are tested separately."""
from model.web_bundle import (
    rect_to_percent,
    term_key,
    build_buckets,
    build_payload_from_inputs,
)


def test_rect_to_percent_basic():
    # rect (10, 20, 30, 40) on a 100x200 page -> 10%, 10%, 20%, 10%
    pct = rect_to_percent((10, 20, 30, 40), page_w=100, page_h=200)
    assert pct == [10.0, 10.0, 20.0, 10.0]


def test_rect_to_percent_full_page():
    pct = rect_to_percent((0, 0, 100, 200), page_w=100, page_h=200)
    assert pct == [0.0, 0.0, 100.0, 100.0]


def test_term_key_lowercases_and_strips():
    assert term_key("Mozart") == "mozart"
    assert term_key("Smith, John") == "smith, john"
    assert term_key("  spaced  ") == "spaced"


def test_build_buckets_includes_aggregate_and_all_style_buckets():
    raw = {
        "BoldTerm": [(0, "1", {"italic": False, "bold": True, "caps": False, "single-quotes": False})],
        "ItalicTerm": [(1, "2", {"italic": True, "bold": False, "caps": False, "single-quotes": False})],
    }
    buckets = build_buckets(raw, capitalize_keys=False)

    keys = [e["key"] for e in buckets["aggregate"]]
    assert "boldterm" in keys
    assert "italicterm" in keys

    assert [e["key"] for e in buckets["bold"]] == ["boldterm"]
    assert [e["key"] for e in buckets["italic"]] == ["italicterm"]

    assert buckets["caps"] == []
    assert buckets["single-quotes"] == []
    assert buckets["other"] == []


def test_build_buckets_other_bucket_holds_unstyled_entries():
    raw = {
        "Plain": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    buckets = build_buckets(raw, capitalize_keys=False)
    assert [e["key"] for e in buckets["other"]] == ["plain"]


def test_build_buckets_entry_shape():
    raw = {
        "Mozart": [
            (3, "iv", {"italic": False, "bold": False, "caps": False, "single-quotes": False}),
            (16, "12", {"italic": False, "bold": False, "caps": False, "single-quotes": False}),
        ],
    }
    buckets = build_buckets(raw, capitalize_keys=False)
    entry = buckets["aggregate"][0]
    assert entry["key"] == "mozart"
    assert entry["display"] == "Mozart"
    assert entry["pages"] == [
        {"physical": 3, "label": "iv"},
        {"physical": 16, "label": "12"},
    ]


def test_build_buckets_capitalize_keys_changes_display_only():
    raw = {"mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})]}
    buckets = build_buckets(raw, capitalize_keys=True)
    entry = buckets["aggregate"][0]
    assert entry["key"] == "mozart"
    assert entry["display"] == "Mozart"


def test_build_payload_from_inputs_assembles_everything():
    raw_results = {
        "Mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    page_labels = ["1", "2"]
    page_dims = [(612, 792), (612, 792)]
    page_highlights = {
        0: [{"term_key": "mozart", "rect_pct": [10.0, 20.0, 5.0, 2.0]}],
    }

    payload = build_payload_from_inputs(
        pdf_name="book.pdf",
        raw_results=raw_results,
        page_labels=page_labels,
        page_dims=page_dims,
        page_highlights=page_highlights,
        capitalize_keys=False,
    )

    assert payload["pdf"]["name"] == "book.pdf"
    assert payload["pdf"]["page_count"] == 2
    assert payload["pageLabels"] == ["1", "2"]
    assert payload["pageDims"] == [
        {"w": 612, "h": 792}, {"w": 612, "h": 792},
    ]
    assert payload["buckets"]["aggregate"][0]["key"] == "mozart"
    assert payload["highlights"]["0"][0]["term_key"] == "mozart"
