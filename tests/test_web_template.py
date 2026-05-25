"""Smoke tests for the HTML template renderer. Confirms that
render_html produces an HTML document containing the embedded payload,
the inline CSS, the inline JS, and one .page card per page."""
import json
import re

from model.web_template import render_html


def _minimal_payload():
    return {
        "pdf": {"name": "test.pdf", "page_count": 2},
        "pageLabels": ["i", "1"],
        "pageDims": [{"w": 612, "h": 792}, {"w": 612, "h": 792}],
        "buckets": {
            "aggregate": [
                {"key": "mozart", "display": "Mozart",
                 "pages": [{"physical": 1, "label": "1"}]},
            ],
            "italic": [], "bold": [], "caps": [],
            "single-quotes": [], "other": [],
        },
        "highlights": {
            "1": [{"term_key": "mozart", "rect_pct": [10.0, 20.0, 5.0, 2.0]}],
        },
    }


def test_render_html_contains_doctype_and_payload():
    html = render_html(_minimal_payload())
    assert html.startswith("<!doctype html>") or html.startswith("<!DOCTYPE html>")
    m = re.search(r'<script id="bundle-data" type="application/json">(.*?)</script>',
                  html, re.DOTALL)
    assert m is not None
    parsed = json.loads(m.group(1).replace("<\\/", "</"))
    assert parsed["pdf"]["name"] == "test.pdf"


def test_render_html_emits_one_page_card_per_page():
    html = render_html(_minimal_payload())
    assert html.count('class="page"') == 2


def test_render_html_emits_image_src_for_each_page():
    html = render_html(_minimal_payload())
    assert "images/page-0001.png" in html
    assert "images/page-0002.png" in html


def test_render_html_uses_index_label_in_page_header():
    html = render_html(_minimal_payload())
    assert "Page i" in html
    assert "Page 1" in html


def test_render_html_payload_json_escapes_script_tag():
    """Defensive: a term containing </script> must not break out of
    the embedded JSON island."""
    payload = _minimal_payload()
    payload["buckets"]["aggregate"][0]["display"] = "weird </script> term"
    html = render_html(payload)
    m = re.search(r'<script id="bundle-data" type="application/json">(.*?)</script>',
                  html, re.DOTALL)
    assert m is not None
    assert "</script>" not in m.group(1)
