# Web Bundle Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in HTML+images bundle export that lets a recipient browse an indexed PDF in a browser, with bidirectional click navigation between page highlights and the index sidebar, page/scroll view modes, slideshow, and label-aware Go-To-Page.

**Architecture:** New `model/web_bundle.py` runs a `QThread` after `Create Index` finishes (gated by a new `Generate web view` checkbox, default off). It renders one PNG per page via PyMuPDF, computes term word-rects per page using helpers extracted to `model/web_highlights.py` (and shared with the desktop viewer), and emits a single self-contained `index.html` with embedded JSON payload + inline CSS/JS into `<project>/web/`.

**Tech Stack:** Python 3.10+, PyQt6 (QThread), PyMuPDF (fitz), vanilla HTML/CSS/JS. Pytest for unit + integration tests.

**Spec:** `docs/superpowers/specs/2026-05-25-web-bundle-export-design.md`

---

## Task 1: Extract shared word-match helpers to `model/web_highlights.py`

**Why:** The bundle generator needs the same term→word-indices matching logic the desktop viewer uses (`_search_variants`, `_match_term_at`, `_normalise_word`, `_words_equal`, `_merge_indices_into_spans`). Lifting them into a model module keeps a single source of truth and avoids importing `PyQt6` into the bundle generator.

**Files:**
- Create: `model/web_highlights.py`
- Create: `tests/test_web_highlights.py`
- Modify: `view/pdf_viewer.py` (replace inline helpers with imports from `model.web_highlights`)

### Step 1.1: Write the failing tests first

- [ ] Write `tests/test_web_highlights.py`:

```python
"""Tests for the shared term -> word-index matching helpers used by the
desktop viewer and the web bundle exporter."""
from model.web_highlights import (
    search_variants,
    match_term_at,
    merge_word_indices_to_spans,
    rects_for_term,
)


def _word(text, x=0, y=0):
    # PyMuPDF tuple: (x0, y0, x1, y1, text, block, line, word_no)
    return (float(x), float(y), float(x + len(text)), float(y + 1), text, 0, 0, 0)


def test_search_variants_single():
    assert search_variants("Manchester") == [["Manchester"]]


def test_search_variants_inverted_name():
    variants = search_variants("Smith, John")
    assert ["Smith,", "John"] not in variants
    # Two variants: comma-form split, and natural-order
    assert ["Smith,", "John"] not in variants
    assert ["John", "Smith"] in variants


def test_match_single_word():
    words = [_word("the", 0), _word("Manchester", 4)]
    assert match_term_at(words, 1, ["Manchester"]) == [1]


def test_no_match_returns_none():
    words = [_word("the"), _word("piano")]
    assert match_term_at(words, 0, ["Manchester"]) is None


def test_match_hyphenation_split():
    words = [_word("the"), _word("Manch-"), _word("ester"), _word("historian")]
    assert match_term_at(words, 1, ["Manchester"]) == [1, 2]


def test_match_strips_possessive():
    # "Pemberton's" should match "Pemberton"
    words = [_word("Pemberton's")]
    assert match_term_at(words, 0, ["Pemberton"]) == [0]


def test_match_strips_curly_quotes():
    words = [_word("‘A"), _word("New", x=4), _word("Method’", x=8)]
    assert match_term_at(words, 0, ["A", "New", "Method"]) == [0, 1, 2]


def test_case_aware_uppercase_target_blocks_lowercase_pdf():
    words = [_word("manchester")]
    assert match_term_at(words, 0, ["Manchester"]) is None


def test_case_aware_lowercase_target_matches_anything():
    words = [_word("Polonaise")]
    assert match_term_at(words, 0, ["polonaise"]) == [0]


def test_merge_consecutive_same_line():
    # Three words on the same y-row that all belong to one term
    words = [_word("New", 0, 0), _word("York", 4, 0), _word("City", 9, 0)]
    spans = merge_word_indices_to_spans(words, [0, 1, 2])
    # One span covering all three
    assert len(spans) == 1
    x0, y0, x1, y1 = spans[0]
    assert x0 == 0.0
    assert x1 == 13.0  # right edge of "City"


def test_merge_splits_different_lines():
    words = [_word("foo", 0, 0), _word("bar", 0, 10)]
    spans = merge_word_indices_to_spans(words, [0, 1])
    assert len(spans) == 2


def test_rects_for_term_returns_normalised_rects():
    # "Manchester" appears once at x=4, y=0
    words = [_word("the", 0, 0), _word("Manchester", 4, 0)]
    rects = rects_for_term(words, "Manchester")
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    assert (x0, y0, x1, y1) == (4.0, 0.0, 14.0, 1.0)


def test_rects_for_term_inverted_name_finds_natural_order():
    # PDF contains "John Smith"; index entry is "Smith, John"
    words = [_word("John", 0, 0), _word("Smith", 5, 0)]
    rects = rects_for_term(words, "Smith, John")
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    assert x0 == 0.0
    assert x1 == 10.0  # right edge of "Smith"
```

### Step 1.2: Run the tests to verify they fail

- [ ] Run:
```bash
cd /Users/markburnett/GitHub/pdf-index
pytest tests/test_web_highlights.py -v
```
Expected: `ModuleNotFoundError: No module named 'model.web_highlights'`

### Step 1.3: Create `model/web_highlights.py` with the helpers extracted from `view/pdf_viewer.py`

- [ ] Write the file:

```python
"""Term -> word-index / word-rect matching helpers.

Extracted from view/pdf_viewer.py so the web bundle exporter
(model/web_bundle.py) can reuse the exact same matching rules without
pulling in PyQt6. The desktop viewer continues to call these via thin
wrappers that adapt them to its image_label.words list.
"""
import unicodedata

# Punctuation characters stripped from both edges of a PDF word before
# comparison. Curly quotes are included because PyMuPDF's get_text("words")
# keeps them attached to adjacent words (‘A, Method’).
_STRIP_CHARS = '.,;:!?()[]{}"\'-/‘’'


def _normalise_word(word: str) -> str:
    """Strip surrounding punctuation, curly quotes, and possessive
    suffix ('s/’s) before comparison.
    """
    stripped = word.strip(_STRIP_CHARS)
    if stripped.endswith("'s") or stripped.endswith("’s"):
        stripped = stripped[:-2]
    return stripped


def _words_equal(pdf_word: str, target_word: str) -> bool:
    """Case-aware word equality: an uppercase target requires an
    uppercase PDF word; otherwise compare case-insensitively.
    """
    if target_word and target_word[0].isupper():
        if not pdf_word or not pdf_word[0].isupper():
            return False
    return pdf_word.lower() == target_word.lower()


def search_variants(term: str) -> list[list[str]]:
    """Return word-lists to try matching for *term*.

    For "Smith, John" we also try the natural-order "John Smith".
    """
    term_normalized = unicodedata.normalize("NFKC", term)
    variants = [term_normalized.split()]
    if ", " in term_normalized:
        parts = term_normalized.split(", ", 1)
        variants.append((parts[1] + " " + parts[0]).split())
    return variants


def match_term_at(words, start_idx: int, target_words: list[str]):
    """Try to match *target_words* against *words* starting at *start_idx*.

    Each target word matches either a single PDF word or a
    hyphenation-joined pair (PDF word ending in '-' followed by a PDF
    word starting lowercase). Possessive suffixes are stripped before
    comparison. Returns the list of PDF-word indices consumed by the
    match, or None.
    """
    matched = []
    pdf_pos = start_idx

    for target_word in target_words:
        if pdf_pos >= len(words):
            return None

        target_stripped = _normalise_word(target_word)
        word_text = unicodedata.normalize("NFKC", words[pdf_pos][4])
        word_stripped = _normalise_word(word_text)

        if _words_equal(word_stripped, target_stripped):
            matched.append(pdf_pos)
            pdf_pos += 1
            continue

        # Hyphenation join: '<prev>-' + '<next>' where next starts lowercase.
        if (pdf_pos + 1 < len(words)
                and word_text.endswith("-")
                and words[pdf_pos + 1][4]
                and words[pdf_pos + 1][4][0].islower()):
            joined = (
                word_text[:-1]
                + unicodedata.normalize("NFKC", words[pdf_pos + 1][4])
            )
            joined_stripped = _normalise_word(joined)
            if _words_equal(joined_stripped, target_stripped):
                matched.append(pdf_pos)
                matched.append(pdf_pos + 1)
                pdf_pos += 2
                continue

        return None

    return matched


def merge_word_indices_to_spans(words, indices):
    """Group sorted word indices into rects, merging consecutive
    indices that sit on the same line into a single span. Returns a
    list of (x0, y0, x1, y1) rects in PDF-point coordinates.

    Two indices are on the same line when their y0 coordinates differ
    by less than 1.0 point.
    """
    if not indices:
        return []
    sorted_idx = sorted(set(indices))
    spans = []
    current = [sorted_idx[0]]
    for i in sorted_idx[1:]:
        prev = current[-1]
        same_line = abs(words[i][1] - words[prev][1]) < 1.0
        consecutive = (i == prev + 1)
        if same_line and consecutive:
            current.append(i)
        else:
            spans.append(current)
            current = [i]
    spans.append(current)

    out = []
    for span in spans:
        x0 = min(words[i][0] for i in span)
        y0 = min(words[i][1] for i in span)
        x1 = max(words[i][2] for i in span)
        y1 = max(words[i][3] for i in span)
        out.append((x0, y0, x1, y1))
    return out


def rects_for_term(words, term: str):
    """Return all merged word-rects on a page that match *term*.

    Tries each variant returned by search_variants, dedupes by index
    span, and merges adjacent same-line matches.
    """
    all_indices = set()
    for term_words in search_variants(term):
        if not term_words:
            continue
        for i in range(len(words)):
            matched = match_term_at(words, i, term_words)
            if matched is not None:
                all_indices.update(matched)
    return merge_word_indices_to_spans(words, sorted(all_indices))
```

### Step 1.4: Run the tests to verify they pass

- [ ] Run:
```bash
pytest tests/test_web_highlights.py -v
```
Expected: all 12 tests PASS.

### Step 1.5: Refactor `view/pdf_viewer.py` to import the shared helpers

- [ ] In `view/pdf_viewer.py`, replace the inline `_search_variants`, `_match_term_at`, `_normalise_word`, `_words_equal`, and `_merge_indices_into_spans` (in `ClickableLabel`) with imports/delegating calls. Add at the top of `view/pdf_viewer.py` (with the other imports):

```python
from model.web_highlights import (
    match_term_at as _shared_match_term_at,
    search_variants as _shared_search_variants,
)
```

Then replace the methods `_search_variants` and `_match_term_at` on `PDFViewer` with thin wrappers (keep the same method names so other tests/callers don't break):

```python
    def _search_variants(self, term):
        return _shared_search_variants(term)

    def _match_term_at(self, words, start_idx, target_words):
        return _shared_match_term_at(words, start_idx, target_words)
```

Delete the original method bodies (the longer 50+ line implementations) and the two staticmethods `_normalise_word` and `_words_equal`. The `ClickableLabel._merge_indices_into_spans` method (used for painting) stays where it is — it operates on PyQt drawing coords and is not duplicated by `merge_word_indices_to_spans` (which returns plain rects).

### Step 1.6: Run the existing viewer-side tests to verify no regression

- [ ] Run:
```bash
pytest tests/test_highlight_match.py -v
```
Expected: all existing tests PASS unchanged.

### Step 1.7: Run the full test suite for safety

- [ ] Run:
```bash
pytest tests/ -v
```
Expected: all PASS.

### Step 1.8: Commit

- [ ] Stage and commit:
```bash
git add model/web_highlights.py tests/test_web_highlights.py view/pdf_viewer.py
git commit -m "$(cat <<'EOF'
refactor(highlights): extract term-match helpers to model/web_highlights

Shared between the desktop viewer and the upcoming web bundle exporter.
Behavior unchanged; adds rects_for_term + merge_word_indices_to_spans
for callers that need PDF-point rects rather than word indices.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add the `generate_web_bundle` config default

**Why:** The new setting must be saved/loaded per-project. Defaulting it to `False` ensures the feature is opt-in.

**Files:**
- Modify: `model/config.py`
- Create: `tests/test_config_web_bundle_default.py`

### Step 2.1: Write the failing test

- [ ] Create `tests/test_config_web_bundle_default.py`:

```python
"""Verify the new generate_web_bundle config key defaults to False and
loads correctly for both new and pre-existing project configs."""
import json
import os
import tempfile

from model.config import ConfigManager


def test_default_is_false():
    assert ConfigManager.DEFAULT_CONFIG["generate_web_bundle"] is False


def test_load_returns_default_when_key_missing(tmp_path):
    # Write a config without the new key, simulating an existing project
    cfg = {"pdf_filename": "book.pdf", "offset": 0}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    loaded = ConfigManager.load_config(str(tmp_path))
    assert loaded["generate_web_bundle"] is False


def test_load_preserves_explicit_true(tmp_path):
    cfg = {"generate_web_bundle": True}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    loaded = ConfigManager.load_config(str(tmp_path))
    assert loaded["generate_web_bundle"] is True
```

### Step 2.2: Run the test to verify it fails

- [ ] Run:
```bash
pytest tests/test_config_web_bundle_default.py -v
```
Expected: FAIL — `KeyError: 'generate_web_bundle'`.

### Step 2.3: Add the default to `model/config.py`

- [ ] Open `model/config.py` and add a new line inside `DEFAULT_CONFIG`, immediately after the `"separate_style_files": True,` line (around line 23):

```python
        "generate_web_bundle": False,
```

The full `DEFAULT_CONFIG` should now include the new key alongside the other output options.

### Step 2.4: Run the test to verify it passes

- [ ] Run:
```bash
pytest tests/test_config_web_bundle_default.py -v
```
Expected: all 3 tests PASS.

### Step 2.5: Commit

- [ ] Stage and commit:
```bash
git add model/config.py tests/test_config_web_bundle_default.py
git commit -m "$(cat <<'EOF'
feat(config): add generate_web_bundle option (default off)

New per-project setting gating the upcoming HTML+images bundle export.
Off by default so the feature is strictly opt-in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Build the JSON payload (`build_payload`) — pure logic, fully unit-tested

**Why:** This is the data layer the bundle's JavaScript reads. Keeping it pure (no PyMuPDF calls, no file I/O) makes it trivially testable. The next task plugs PyMuPDF rendering on top.

**Files:**
- Create: `model/web_bundle.py` (initial — pure helpers only)
- Create: `tests/test_web_bundle_payload.py`

### Step 3.1: Write the failing tests

- [ ] Create `tests/test_web_bundle_payload.py`:

```python
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
    # Whitespace at edges trimmed
    assert term_key("  spaced  ") == "spaced"


def test_build_buckets_includes_aggregate_and_all_style_buckets():
    # Two synthetic occurrences: one bold, one italic.
    raw = {
        "BoldTerm": [(0, "1", {"italic": False, "bold": True, "caps": False, "single-quotes": False})],
        "ItalicTerm": [(1, "2", {"italic": True, "bold": False, "caps": False, "single-quotes": False})],
    }
    buckets = build_buckets(raw, capitalize_keys=False)

    # Aggregate has both
    keys = [e["key"] for e in buckets["aggregate"]]
    assert "boldterm" in keys
    assert "italicterm" in keys

    # Bold bucket has only BoldTerm
    assert [e["key"] for e in buckets["bold"]] == ["boldterm"]

    # Italic bucket has only ItalicTerm
    assert [e["key"] for e in buckets["italic"]] == ["italicterm"]

    # Caps/single-quotes/other are present and empty (other should be empty too —
    # both entries have a style flag set).
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
    # key stays lowercase (used for DOM ids/lookups); display gets capitalised
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
```

### Step 3.2: Run the tests to verify they fail

- [ ] Run:
```bash
pytest tests/test_web_bundle_payload.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'model.web_bundle'`.

### Step 3.3: Create `model/web_bundle.py` with the pure helpers

- [ ] Write the file:

```python
"""Web bundle exporter.

Produces a self-contained HTML page plus a folder of per-page PNGs in
``<project>/web/``. The HTML embeds the index data as JSON and includes
inline CSS/JS so the folder can be zipped and shared standalone.

This module is structured in three layers:

1. Pure helpers (build_payload_from_inputs, build_buckets, rect_to_percent,
   term_key) — no I/O, no PyMuPDF. Unit-tested independently.
2. PyMuPDF integration (collect_page_data, render_page_image) — does the
   page-rendering and word-rect computation.
3. The WebBundleThread orchestrator and the render_html entry point.
"""
from __future__ import annotations

from typing import Iterable

from model.indexer import IndexingThread, filter_by_style, STYLE_BUCKETS


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def term_key(term: str) -> str:
    """Stable identifier for a term, used as a DOM id suffix and the
    lookup key from in-page highlights back to the sidebar entry.
    """
    return term.strip().lower()


def rect_to_percent(rect, page_w: float, page_h: float):
    """Convert a (x0, y0, x1, y1) PDF-point rect to a percentage-of-page
    [left, top, width, height] list suitable for absolute CSS positioning.
    """
    x0, y0, x1, y1 = rect
    return [
        (x0 / page_w) * 100.0,
        (y0 / page_h) * 100.0,
        ((x1 - x0) / page_w) * 100.0,
        ((y1 - y0) / page_h) * 100.0,
    ]


def _format_entries(formatted_results, raw_results, capitalize_keys):
    """Build the [{key, display, pages: [{physical, label}]}] list for a
    given formatted_results dict, looking up per-occurrence (physical,
    label) pairs from raw_results.
    """
    entries = []
    # raw_results keys are the un-capitalised originals; formatted_results
    # keys may already be capitalised. Build a reverse map so we can find
    # the right raw entry by the display key.
    if capitalize_keys:
        display_to_original = {}
        for k in raw_results:
            disp = k[0].upper() + k[1:] if k else k
            display_to_original[disp] = k
    else:
        display_to_original = {k: k for k in raw_results}

    for display in formatted_results:
        original = display_to_original.get(display, display)
        occurrences = raw_results.get(original, [])
        # Deduplicate by physical index (occurrences come pre-sorted by
        # IndexingThread.process_results, but a defensive sort is cheap).
        seen = set()
        pages = []
        for occ in sorted(occurrences, key=lambda o: o[0]):
            phys = occ[0]
            label = occ[1]
            if phys in seen:
                continue
            seen.add(phys)
            pages.append({"physical": phys, "label": label})
        entries.append({
            "key": term_key(original),
            "display": display,
            "pages": pages,
        })
    return entries


def build_buckets(raw_results, capitalize_keys: bool):
    """Return a dict ``{bucket_name: [entry, ...]}`` covering every bucket
    in ``STYLE_BUCKETS``. Empty buckets are returned as empty lists.
    """
    buckets = {}
    for bucket in STYLE_BUCKETS:
        filtered_raw = filter_by_style(raw_results, bucket)
        formatted = IndexingThread.process_results(
            None, filtered_raw, capitalize_keys=capitalize_keys,
        )
        buckets[bucket] = _format_entries(
            formatted, filtered_raw, capitalize_keys,
        )
    return buckets


def build_payload_from_inputs(
    pdf_name: str,
    raw_results: dict,
    page_labels: list[str],
    page_dims: list[tuple],
    page_highlights: dict,
    capitalize_keys: bool,
) -> dict:
    """Assemble the JSON payload embedded in the HTML.

    ``page_highlights`` is keyed by physical page index; the returned
    payload uses string keys (JSON requires them).
    """
    return {
        "pdf": {"name": pdf_name, "page_count": len(page_labels)},
        "pageLabels": list(page_labels),
        "pageDims": [{"w": w, "h": h} for (w, h) in page_dims],
        "buckets": build_buckets(raw_results, capitalize_keys),
        "highlights": {str(k): v for k, v in page_highlights.items()},
    }
```

### Step 3.4: Run the tests to verify they pass

- [ ] Run:
```bash
pytest tests/test_web_bundle_payload.py -v
```
Expected: all 8 tests PASS.

### Step 3.5: Commit

- [ ] Stage and commit:
```bash
git add model/web_bundle.py tests/test_web_bundle_payload.py
git commit -m "$(cat <<'EOF'
feat(web-bundle): pure payload builders

build_buckets reuses the existing IndexingThread.process_results +
filter_by_style so the web bundle's per-bucket lists exactly match the
md/txt/html files written by the desktop app.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: PyMuPDF integration — `collect_page_data` and `render_page_image`

**Why:** Wraps the only two PyMuPDF-touching responsibilities the bundle has — rendering a page to PNG and computing the page's `pageLabels`/`pageDims`/`page_highlights` from the document. Keeping them as standalone functions lets the QThread orchestrator chain everything in one pass over the document.

**Files:**
- Modify: `model/web_bundle.py` (append PyMuPDF helpers)
- Create: `tests/test_web_bundle_pdf.py` (integration test using the bundled `test/test.pdf` if it exists; otherwise generates a tiny PDF in-memory)

### Step 4.1: Write the failing test

- [ ] Create `tests/test_web_bundle_pdf.py`:

```python
"""Integration tests for the PyMuPDF-touching helpers in
model/web_bundle.py. Uses a small in-memory PDF rather than the bundled
test.pdf so the test stays hermetic and fast."""
import os
import fitz  # PyMuPDF

from model.web_bundle import collect_page_data, render_page_image


def _make_test_pdf(path):
    """Two-page PDF with the text 'Mozart' on page 1 and 'Beethoven'
    on page 2."""
    doc = fitz.open()
    p1 = doc.new_page(width=200, height=300)
    p1.insert_text((20, 50), "Mozart", fontsize=14)
    p2 = doc.new_page(width=200, height=300)
    p2.insert_text((20, 50), "Beethoven", fontsize=14)
    doc.save(path)
    doc.close()


def test_collect_page_data_labels_and_dims(tmp_path):
    pdf_path = str(tmp_path / "tiny.pdf")
    _make_test_pdf(pdf_path)
    raw_results = {
        "Mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    labels, dims, highlights = collect_page_data(
        pdf_path, raw_results,
        strategy="physical", offset=0, index_front_matter=False,
    )
    assert labels == ["1", "2"]
    assert dims == [(200, 300), (200, 300)]
    # Mozart should be matched on page 0
    assert "0" not in highlights or len(highlights[0]) >= 1
    page0_hls = highlights[0]
    assert any(h["term_key"] == "mozart" for h in page0_hls)
    # rect_pct is left, top, width, height (percentages)
    rect_pct = next(h["rect_pct"] for h in page0_hls if h["term_key"] == "mozart")
    assert all(0 <= v <= 100 for v in rect_pct)
    # Width should be plausibly non-zero
    assert rect_pct[2] > 0


def test_collect_page_data_inverted_name(tmp_path):
    """Index entry 'Smith, John' should still match 'John Smith' in PDF."""
    pdf_path = str(tmp_path / "name.pdf")
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 50), "John Smith", fontsize=14)
    doc.save(pdf_path)
    doc.close()

    raw_results = {
        "Smith, John": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    labels, dims, highlights = collect_page_data(
        pdf_path, raw_results,
        strategy="physical", offset=0, index_front_matter=False,
    )
    assert any(h["term_key"] == "smith, john" for h in highlights.get(0, []))


def test_render_page_image_writes_png(tmp_path):
    pdf_path = str(tmp_path / "tiny.pdf")
    _make_test_pdf(pdf_path)
    out_path = str(tmp_path / "page-0001.png")
    render_page_image(pdf_path, 0, out_path, zoom=1.5)
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100  # not an empty stub
    # PNG magic bytes
    with open(out_path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
```

### Step 4.2: Run the test to verify it fails

- [ ] Run:
```bash
pytest tests/test_web_bundle_pdf.py -v
```
Expected: FAIL — `ImportError: cannot import name 'collect_page_data'`.

### Step 4.3: Append the PyMuPDF helpers to `model/web_bundle.py`

- [ ] At the bottom of `model/web_bundle.py`, add:

```python
# ---------------------------------------------------------------------------
# PyMuPDF integration
# ---------------------------------------------------------------------------

def collect_page_data(
    pdf_path: str,
    raw_results: dict,
    strategy: str,
    offset: int,
    index_front_matter: bool,
):
    """Walk the PDF once and return (page_labels, page_dims, page_highlights).

    page_highlights is a dict ``{physical_page_index: [{term_key, rect_pct}, ...]}``
    keyed by integer indices. The orchestrator converts keys to strings
    when writing JSON.
    """
    import fitz
    from model.indexer import label_for_page
    from model.web_highlights import rects_for_term

    doc = fitz.open(pdf_path)
    page_count = len(doc)

    # Which physical indices fall in the front-matter (roman) region.
    # When index_front_matter is True the front matter is everything
    # before *offset* (matching IndexingThread's start_page semantics);
    # otherwise no page is forced roman.
    front_matter_idx = (
        set(range(0, offset))
        if (index_front_matter and offset > 0) else set()
    )

    # Pre-bucket raw_results by physical page so each page is scanned for
    # the small set of terms that actually occur on it.
    terms_by_page: dict[int, list[str]] = {}
    for term, occurrences in raw_results.items():
        for occ in occurrences:
            phys = occ[0]
            terms_by_page.setdefault(phys, []).append(term)

    page_labels = []
    page_dims = []
    page_highlights: dict[int, list] = {}

    for i in range(page_count):
        page = doc.load_page(i)
        label = label_for_page(
            page, i + 1, strategy,
            offset=offset, force_roman=(i in front_matter_idx),
        )
        page_labels.append(label)

        rect = page.rect
        page_w = float(rect.width)
        page_h = float(rect.height)
        page_dims.append((page_w, page_h))

        terms_on_page = terms_by_page.get(i, [])
        if not terms_on_page:
            continue

        words = page.get_text("words")
        page_hls = []
        for term in terms_on_page:
            for r in rects_for_term(words, term):
                page_hls.append({
                    "term_key": term_key(term),
                    "rect_pct": rect_to_percent(r, page_w, page_h),
                })
        if page_hls:
            page_highlights[i] = page_hls

    doc.close()
    return page_labels, page_dims, page_highlights


def render_page_image(pdf_path: str, page_index: int, out_path: str, zoom: float = 1.5):
    """Render a single page to PNG at the given zoom factor."""
    import fitz

    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_index)
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(out_path)
    finally:
        doc.close()
```

### Step 4.4: Run the test to verify it passes

- [ ] Run:
```bash
pytest tests/test_web_bundle_pdf.py -v
```
Expected: all 3 tests PASS.

### Step 4.5: Commit

- [ ] Stage and commit:
```bash
git add model/web_bundle.py tests/test_web_bundle_pdf.py
git commit -m "$(cat <<'EOF'
feat(web-bundle): PyMuPDF helpers for page rendering and rect collection

collect_page_data walks the PDF once and returns the labels, dims, and
per-page highlight rects (in percent-of-page coords). render_page_image
saves a single page as PNG at the configured zoom.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: HTML/CSS/JS template — `model/web_template.py`

**Why:** Keeping the template as Python string literals avoids a runtime template-loading dependency and makes the bundle truly self-contained. CSS handles layout (page mode vs scroll mode, sidebar toggle, highlight visibility). JS handles slideshow, navigation, click handlers, and the bucket selector.

**Files:**
- Create: `model/web_template.py`
- Create: `tests/test_web_template.py`

### Step 5.1: Write the failing test

- [ ] Create `tests/test_web_template.py`:

```python
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
    # Embedded JSON payload
    m = re.search(r'<script id="bundle-data" type="application/json">(.*?)</script>',
                  html, re.DOTALL)
    assert m is not None
    parsed = json.loads(m.group(1))
    assert parsed["pdf"]["name"] == "test.pdf"


def test_render_html_emits_one_page_card_per_page():
    html = render_html(_minimal_payload())
    # Expect class="page" attribute appearing twice (one per page)
    assert html.count('class="page"') == 2


def test_render_html_emits_image_src_for_each_page():
    html = render_html(_minimal_payload())
    assert "images/page-0001.png" in html
    assert "images/page-0002.png" in html


def test_render_html_uses_index_label_in_page_header():
    html = render_html(_minimal_payload())
    # Page-header should contain "Page i" and "Page 1"
    assert "Page i" in html
    assert "Page 1" in html


def test_render_html_payload_json_escapes_script_tag():
    """Defensive: a term containing </script> must not break out of
    the embedded JSON island."""
    payload = _minimal_payload()
    payload["buckets"]["aggregate"][0]["display"] = "weird </script> term"
    html = render_html(payload)
    # The literal closing tag must not appear in the payload region
    # (it would close our island prematurely). The standard mitigation
    # is to replace </ with <\/ inside JSON content.
    m = re.search(r'<script id="bundle-data" type="application/json">(.*?)</script>',
                  html, re.DOTALL)
    assert m is not None
    # The literal "</script>" must not occur inside the captured group
    assert "</script>" not in m.group(1)
```

### Step 5.2: Run the tests to verify they fail

- [ ] Run:
```bash
pytest tests/test_web_template.py -v
```
Expected: FAIL — module not found.

### Step 5.3: Create `model/web_template.py`

- [ ] Write the file. The template is split into three string constants for readability (`_CSS`, `_JS`, and the body assembled in `render_html`):

```python
"""HTML/CSS/JS template for the web bundle.

Single self-contained document. The render_html function takes the
payload dict produced by web_bundle.build_payload_from_inputs and
returns a complete HTML string.
"""
from __future__ import annotations

import html
import json


_CSS = """
:root {
  --toolbar-h: 56px;
  --sidebar-w: 320px;
  --hl-color: rgba(255, 230, 0, 0.42);
  --hl-active: rgba(255, 140, 0, 0.55);
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  background: #f0f0f0;
  color: #222;
}

#toolbar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 8px 12px;
  background: #fff;
  border-bottom: 1px solid #d0d0d0;
  min-height: var(--toolbar-h);
}
#toolbar button, #toolbar input, #toolbar .group {
  font: inherit;
}
#toolbar .group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
#toolbar button {
  padding: 4px 10px;
  background: #f5f5f5;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
  cursor: pointer;
}
#toolbar button:hover { background: #e8e8e8; }
#toolbar button.active { background: #b3d9ff; border-color: #6fa8dc; }
#toolbar input[type="text"], #toolbar input[type="number"] {
  padding: 4px 6px;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
  width: 70px;
}
#toolbar .total { color: #666; font-size: 0.9em; }

#layout {
  display: flex;
  align-items: stretch;
}

#document {
  flex: 1;
  min-width: 0;
  padding: 12px;
  overflow-y: auto;
  height: calc(100vh - var(--toolbar-h));
}
body.mode-page #document {
  scroll-snap-type: y mandatory;
}

.page {
  margin: 0 auto 16px auto;
  max-width: 95%;
  scroll-snap-align: start;
}
body.mode-page .page {
  height: calc(100vh - var(--toolbar-h) - 24px);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.page-header {
  font-weight: 600;
  font-size: 0.95em;
  color: #555;
  margin: 0 0 6px 2px;
}
.page-canvas {
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  width: 100%;
}
body.mode-page .page-canvas {
  height: 100%;
  width: auto;
}
.page-canvas img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.hl {
  position: absolute;
  background: var(--hl-color);
  cursor: pointer;
  border-radius: 2px;
  transition: background 0.12s;
}
.hl:hover { background: var(--hl-active); }
body.highlights-off .hl { display: none; }

#sidebar {
  width: var(--sidebar-w);
  background: #fafafa;
  border-left: 1px solid #d0d0d0;
  height: calc(100vh - var(--toolbar-h));
  display: flex;
  flex-direction: column;
}
body.sidebar-hidden #sidebar { display: none; }
#sidebar header {
  padding: 10px 12px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
}
#sidebar .filter {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #c0c0c0;
  border-radius: 4px;
}
#sidebar .style-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
#sidebar .style-bar button {
  font-size: 0.85em;
  padding: 2px 8px;
  background: #f0f0f0;
  border: 1px solid #c0c0c0;
  border-radius: 999px;
  cursor: pointer;
}
#sidebar .style-bar button.active {
  background: #b3d9ff;
  border-color: #6fa8dc;
}
#sidebar .entries {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.entry {
  padding: 4px 6px;
  margin: 1px 0;
  border-radius: 3px;
  font-size: 0.9em;
  line-height: 1.35;
}
.entry b { font-weight: 600; }
.entry a {
  color: #0a58ca;
  text-decoration: none;
  margin: 0 1px;
  cursor: pointer;
}
.entry a:hover { text-decoration: underline; }
.entry.pulse {
  animation: pulse-bg 1.5s ease-out;
}
@keyframes pulse-bg {
  0%, 30% { background: #ffe48a; }
  100% { background: transparent; }
}
"""

_JS = """
(function () {
  const payload = JSON.parse(document.getElementById('bundle-data').textContent);
  const doc = document.getElementById('document');
  const entriesEl = document.getElementById('entries');
  const pageInput = document.getElementById('page-input');
  const totalEl = document.getElementById('page-total');
  const intervalEl = document.getElementById('interval-input');
  const playBtn = document.getElementById('play-btn');

  // ----- Build sidebar entries (per bucket) -----
  let currentBucket = 'aggregate';
  function renderEntries() {
    const list = payload.buckets[currentBucket] || [];
    const filter = (document.getElementById('filter').value || '').toLowerCase();
    entriesEl.innerHTML = '';
    for (const entry of list) {
      if (filter && !entry.display.toLowerCase().includes(filter)) continue;
      const row = document.createElement('div');
      row.className = 'entry';
      row.id = 'term-' + entry.key;
      row.dataset.termKey = entry.key;
      const name = document.createElement('b');
      name.textContent = entry.display;
      row.appendChild(name);
      row.appendChild(document.createTextNode(' '));
      entry.pages.forEach((p, i) => {
        if (i > 0) row.appendChild(document.createTextNode(', '));
        const link = document.createElement('a');
        link.textContent = p.label;
        link.dataset.physical = p.physical;
        link.addEventListener('click', () => goToPage(p.physical));
        row.appendChild(link);
      });
      entriesEl.appendChild(row);
    }
  }

  // ----- Bucket selector -----
  document.querySelectorAll('.style-bar button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.style-bar button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentBucket = btn.dataset.bucket;
      renderEntries();
    });
  });

  // ----- Filter input -----
  document.getElementById('filter').addEventListener('input', renderEntries);

  // ----- Page navigation -----
  const pageEls = Array.from(document.querySelectorAll('.page'));
  totalEl.textContent = '/' + payload.pdf.page_count;

  function currentPageIdx() {
    // Find the page card most aligned with the viewport top.
    const scrollTop = doc.scrollTop;
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < pageEls.length; i++) {
      const top = pageEls[i].offsetTop;
      const dist = Math.abs(top - scrollTop);
      if (dist < bestDist) { bestDist = dist; best = i; }
    }
    return best;
  }

  function goToPage(physicalIdx) {
    const el = pageEls[physicalIdx];
    if (!el) return;
    el.scrollIntoView({ behavior: document.body.classList.contains('mode-page') ? 'auto' : 'smooth' });
  }

  document.getElementById('first-btn').addEventListener('click', () => goToPage(0));
  document.getElementById('last-btn').addEventListener('click', () => goToPage(pageEls.length - 1));
  document.getElementById('prev-btn').addEventListener('click', () => goToPage(Math.max(0, currentPageIdx() - 1)));
  document.getElementById('next-btn').addEventListener('click', () => goToPage(Math.min(pageEls.length - 1, currentPageIdx() + 1)));

  pageInput.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const v = pageInput.value.trim().toLowerCase();
    pageInput.value = '';
    if (!v) return;
    const idx = payload.pageLabels.findIndex(lbl => (lbl || '').toLowerCase() === v);
    if (idx >= 0) goToPage(idx);
  });

  // ----- View mode toggle -----
  function setMode(mode) {
    document.body.classList.toggle('mode-page', mode === 'page');
    document.body.classList.toggle('mode-scroll', mode === 'scroll');
    document.getElementById('mode-page-btn').classList.toggle('active', mode === 'page');
    document.getElementById('mode-scroll-btn').classList.toggle('active', mode === 'scroll');
  }
  document.getElementById('mode-page-btn').addEventListener('click', () => setMode('page'));
  document.getElementById('mode-scroll-btn').addEventListener('click', () => setMode('scroll'));

  // ----- Sidebar toggle (persisted) -----
  function setSidebar(visible) {
    document.body.classList.toggle('sidebar-hidden', !visible);
    document.getElementById('sidebar-btn').classList.toggle('active', visible);
    try { localStorage.setItem('pdfix-sidebar', visible ? '1' : '0'); } catch (e) {}
  }
  document.getElementById('sidebar-btn').addEventListener('click', () => {
    setSidebar(document.body.classList.contains('sidebar-hidden'));
  });

  // ----- Highlights toggle (persisted) -----
  function setHighlights(on) {
    document.body.classList.toggle('highlights-off', !on);
    document.getElementById('hl-btn').classList.toggle('active', on);
    try { localStorage.setItem('pdfix-hl', on ? '1' : '0'); } catch (e) {}
  }
  document.getElementById('hl-btn').addEventListener('click', () => {
    setHighlights(document.body.classList.contains('highlights-off'));
  });

  // ----- In-page highlight clicks -> scroll sidebar entry -----
  document.querySelectorAll('.hl').forEach(span => {
    span.addEventListener('click', () => {
      const key = span.dataset.term;
      if (!key) return;
      // If the currently-shown bucket doesn't contain the term, fall
      // back to the aggregate bucket so the click never appears dead.
      const inBucket = (payload.buckets[currentBucket] || []).some(e => e.key === key);
      if (!inBucket) {
        currentBucket = 'aggregate';
        document.querySelectorAll('.style-bar button').forEach(b => {
          b.classList.toggle('active', b.dataset.bucket === 'aggregate');
        });
        renderEntries();
      }
      const target = document.getElementById('term-' + key);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.remove('pulse');
        // Trigger reflow so the animation restarts even on repeat clicks
        void target.offsetWidth;
        target.classList.add('pulse');
      }
    });
  });

  // ----- Slideshow -----
  let timer = null;
  function isPlaying() { return timer !== null; }
  function setPlayBtn(playing) {
    playBtn.textContent = playing ? 'Pause' : 'Play';
    playBtn.classList.toggle('active', playing);
  }
  function stop() {
    if (timer !== null) { clearInterval(timer); timer = null; }
    setPlayBtn(false);
  }
  function start() {
    stop();
    let seconds = parseFloat(intervalEl.value);
    if (!isFinite(seconds) || seconds < 1) seconds = 5;
    if (seconds > 60) seconds = 60;
    timer = setInterval(() => {
      const next = currentPageIdx() + 1;
      if (next >= pageEls.length) { stop(); return; }
      goToPage(next);
    }, seconds * 1000);
    setPlayBtn(true);
  }
  playBtn.addEventListener('click', () => { isPlaying() ? stop() : start(); });

  // ----- Keyboard shortcuts -----
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
      goToPage(Math.max(0, currentPageIdx() - 1));
      e.preventDefault();
    } else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {
      goToPage(Math.min(pageEls.length - 1, currentPageIdx() + 1));
      e.preventDefault();
    } else if (e.key === 'Home') {
      goToPage(0); e.preventDefault();
    } else if (e.key === 'End') {
      goToPage(pageEls.length - 1); e.preventDefault();
    } else if (e.key === '/') {
      document.getElementById('filter').focus(); e.preventDefault();
    } else if (e.key.toLowerCase() === 'i') {
      setSidebar(document.body.classList.contains('sidebar-hidden'));
    } else if (e.key.toLowerCase() === 'h') {
      setHighlights(document.body.classList.contains('highlights-off'));
    }
  });

  // ----- Boot -----
  setMode('page');
  try {
    setSidebar(localStorage.getItem('pdfix-sidebar') !== '0');
    setHighlights(localStorage.getItem('pdfix-hl') !== '0');
  } catch (e) {
    setSidebar(true);
    setHighlights(true);
  }
  renderEntries();
})();
"""


# Escape sequence applied to the embedded payload JSON. JSON itself has
# no </script> rule, so a term containing the literal string </script>
# would break out of the script island. Replacing forward slashes that
# precede a 'script' tag close avoids that without affecting JSON parsing.
def _escape_for_script(text: str) -> str:
    return text.replace("</", "<\\/")


def render_html(payload: dict) -> str:
    """Render the full HTML document for the given payload."""
    page_count = payload["pdf"]["page_count"]
    page_labels = payload["pageLabels"]
    page_dims = payload["pageDims"]
    page_highlights = payload["highlights"]
    title = html.escape(payload["pdf"].get("name", "Index"))

    bucket_buttons = []
    bucket_names = [
        ("aggregate", "Aggregate"),
        ("italic", "Italic"),
        ("bold", "Bold"),
        ("caps", "Caps"),
        ("single-quotes", "Single Quotes"),
        ("other", "Other"),
    ]
    for key, label in bucket_names:
        active = " active" if key == "aggregate" else ""
        bucket_buttons.append(
            f'<button class="bucket{active}" data-bucket="{key}">{label}</button>'
        )

    page_cards = []
    for i in range(page_count):
        label = html.escape(page_labels[i] or str(i + 1))
        dims = page_dims[i]
        aspect = f"{dims['w']}/{dims['h']}"
        img_name = f"images/page-{i+1:04d}.png"

        hls_html_parts = []
        for hl in page_highlights.get(str(i), []):
            left, top, w, h = hl["rect_pct"]
            key = html.escape(hl["term_key"], quote=True)
            hls_html_parts.append(
                f'<span class="hl" data-term="{key}" '
                f'style="left:{left:.3f}%;top:{top:.3f}%;'
                f'width:{w:.3f}%;height:{h:.3f}%"></span>'
            )

        page_cards.append(
            f'<div class="page" data-physical="{i}" data-label="{label}">'
            f'<div class="page-header">Page {label}</div>'
            f'<div class="page-canvas" style="aspect-ratio:{aspect}">'
            f'<img src="{img_name}" alt="Page {label}" loading="lazy">'
            f'{"".join(hls_html_parts)}'
            f'</div>'
            f'</div>'
        )

    payload_json = _escape_for_script(json.dumps(payload, ensure_ascii=False))

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        f"<title>{title} — Index</title>"
        f"<style>{_CSS}</style>"
        "</head><body class=\"mode-page\">"
        '<div id="toolbar">'
        '<div class="group">'
        '<button id="mode-page-btn" class="active">Pages</button>'
        '<button id="mode-scroll-btn">Scroll</button>'
        '</div>'
        '<div class="group">'
        '<button id="sidebar-btn" class="active" title="Toggle sidebar (i)">Sidebar</button>'
        '<button id="hl-btn" class="active" title="Toggle highlights (h)">Highlights</button>'
        '</div>'
        '<div class="group">'
        '<button id="first-btn" title="First page">« First</button>'
        '<button id="prev-btn" title="Previous page (←)">‹ Prev</button>'
        '<input id="page-input" type="text" placeholder="Page" title="Type a page label and press Enter">'
        '<span class="total" id="page-total"></span>'
        '<button id="next-btn" title="Next page (→)">Next ›</button>'
        '<button id="last-btn" title="Last page">Last »</button>'
        '</div>'
        '<div class="group">'
        '<button id="play-btn" title="Play/Pause slideshow">Play</button>'
        '<label>Interval: <input id="interval-input" type="number" min="1" max="60" step="1" value="5"> s</label>'
        '</div>'
        '</div>'
        '<div id="layout">'
        '<div id="document">'
        + "".join(page_cards) +
        '</div>'
        '<aside id="sidebar">'
        '<header>'
        '<input class="filter" id="filter" type="text" placeholder="Filter index...">'
        '<div class="style-bar">' + "".join(bucket_buttons) + '</div>'
        '</header>'
        '<div class="entries" id="entries"></div>'
        '</aside>'
        '</div>'
        f'<script id="bundle-data" type="application/json">{payload_json}</script>'
        f'<script>{_JS}</script>'
        '</body></html>'
    )
```

### Step 5.4: Run the tests to verify they pass

- [ ] Run:
```bash
pytest tests/test_web_template.py -v
```
Expected: all 5 tests PASS.

### Step 5.5: Commit

- [ ] Stage and commit:
```bash
git add model/web_template.py tests/test_web_template.py
git commit -m "$(cat <<'EOF'
feat(web-bundle): inline HTML/CSS/JS template

Single-file HTML with embedded JSON payload, inline CSS, and inline JS.
Supports page/scroll view modes, slideshow, label-aware Go-To-Page,
sidebar + highlights toggles persisted to localStorage, and
bidirectional click navigation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `WebBundleThread` orchestrator + cache sidecar

**Why:** Wires the pure helpers and the PyMuPDF helpers into a `QThread` that's drop-in compatible with the existing controller patterns. Adds a small `.cache.json` sidecar that lets a re-run skip per-page PNG rendering when the source PDF hasn't changed.

**Files:**
- Modify: `model/web_bundle.py` (append the QThread and the top-level `generate_bundle` entry point)
- Create: `tests/test_web_bundle_orchestrator.py`

### Step 6.1: Write the failing test

- [ ] Create `tests/test_web_bundle_orchestrator.py`:

```python
"""End-to-end test for the bundle orchestrator. Generates a tiny PDF,
runs the synchronous entry point, and asserts the expected files and
content end up on disk."""
import json
import os

import fitz

from model.web_bundle import generate_bundle_sync


def _tiny_pdf(path):
    doc = fitz.open()
    p1 = doc.new_page(width=200, height=300)
    p1.insert_text((20, 50), "Mozart", fontsize=14)
    p2 = doc.new_page(width=200, height=300)
    p2.insert_text((20, 50), "Beethoven", fontsize=14)
    doc.save(path)
    doc.close()


def test_generate_bundle_writes_html_and_images(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    raw_results = {
        "Mozart": [(0, "1", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
        "Beethoven": [(1, "2", {"italic": False, "bold": False, "caps": False, "single-quotes": False})],
    }
    out_dir = str(tmp_path / "web")
    generate_bundle_sync(
        pdf_path=pdf,
        raw_results=raw_results,
        out_dir=out_dir,
        strategy="physical",
        offset=0,
        index_front_matter=False,
        capitalize_keys=False,
    )

    assert os.path.exists(os.path.join(out_dir, "index.html"))
    assert os.path.exists(os.path.join(out_dir, "images", "page-0001.png"))
    assert os.path.exists(os.path.join(out_dir, "images", "page-0002.png"))
    assert os.path.exists(os.path.join(out_dir, ".cache.json"))

    with open(os.path.join(out_dir, "index.html"), encoding="utf-8") as f:
        html = f.read()
    assert "Mozart" in html
    assert "Beethoven" in html


def test_generate_bundle_skips_image_regen_when_cache_matches(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    raw_results = {}
    out_dir = str(tmp_path / "web")

    generate_bundle_sync(pdf, raw_results, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)

    # Capture image mtime
    img = os.path.join(out_dir, "images", "page-0001.png")
    first_mtime = os.path.getmtime(img)

    # Re-run; images should NOT be regenerated because cache matches
    import time; time.sleep(0.05)  # ensure mtime resolution
    generate_bundle_sync(pdf, raw_results, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    assert os.path.getmtime(img) == first_mtime


def test_generate_bundle_regenerates_when_pdf_changes(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    out_dir = str(tmp_path / "web")
    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    img = os.path.join(out_dir, "images", "page-0001.png")
    first_mtime = os.path.getmtime(img)

    # Modify PDF mtime
    import time; time.sleep(0.05)
    os.utime(pdf, None)

    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)
    # Image should have been re-rendered (different mtime)
    assert os.path.getmtime(img) != first_mtime


def test_generate_bundle_handles_corrupt_cache(tmp_path):
    pdf = str(tmp_path / "tiny.pdf")
    _tiny_pdf(pdf)
    out_dir = str(tmp_path / "web")
    os.makedirs(out_dir)
    # Write a broken cache file
    with open(os.path.join(out_dir, ".cache.json"), "w") as f:
        f.write("{not valid json")

    # Should not raise
    generate_bundle_sync(pdf, {}, out_dir,
                        strategy="physical", offset=0,
                        index_front_matter=False, capitalize_keys=False)

    # Cache file should be fixed up
    with open(os.path.join(out_dir, ".cache.json")) as f:
        data = json.load(f)
    assert "pdf_mtime" in data
    assert data["page_count"] == 2
```

### Step 6.2: Run the tests to verify they fail

- [ ] Run:
```bash
pytest tests/test_web_bundle_orchestrator.py -v
```
Expected: FAIL — `cannot import name 'generate_bundle_sync'`.

### Step 6.3: Append the orchestrator to `model/web_bundle.py`

- [ ] At the bottom of `model/web_bundle.py`, add:

```python
# ---------------------------------------------------------------------------
# Cache sidecar
# ---------------------------------------------------------------------------

def _read_cache(out_dir: str) -> dict:
    import json, os
    path = os.path.join(out_dir, ".cache.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(out_dir: str, pdf_mtime: float, page_count: int):
    import json, os
    path = os.path.join(out_dir, ".cache.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pdf_mtime": pdf_mtime, "page_count": page_count}, f)


def _cache_matches(cache: dict, pdf_mtime: float, page_count: int) -> bool:
    return (
        cache.get("pdf_mtime") == pdf_mtime
        and cache.get("page_count") == page_count
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_bundle_sync(
    pdf_path: str,
    raw_results: dict,
    out_dir: str,
    *,
    strategy: str,
    offset: int,
    index_front_matter: bool,
    capitalize_keys: bool,
    zoom: float = 1.5,
    progress_callback=None,
) -> None:
    """Synchronously generate the web bundle. Used by tests and by the
    QThread wrapper. progress_callback receives an int 0..100.
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    images_dir = os.path.join(out_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    if progress_callback:
        progress_callback(2)

    # --- Walk PDF once: labels, dims, per-page highlights
    page_labels, page_dims, page_highlights = collect_page_data(
        pdf_path, raw_results,
        strategy=strategy, offset=offset,
        index_front_matter=index_front_matter,
    )
    page_count = len(page_labels)
    if progress_callback:
        progress_callback(10)

    # --- Decide whether to regenerate images
    pdf_mtime = os.path.getmtime(pdf_path)
    cache = _read_cache(out_dir)
    render_images = not _cache_matches(cache, pdf_mtime, page_count)

    if render_images:
        for i in range(page_count):
            out_path = os.path.join(images_dir, f"page-{i+1:04d}.png")
            try:
                render_page_image(pdf_path, i, out_path, zoom=zoom)
            except Exception:
                # Skip a broken page; the HTML's <img> will simply 404.
                continue
            if progress_callback:
                progress_callback(10 + int((i + 1) / page_count * 80))
        _write_cache(out_dir, pdf_mtime, page_count)
    else:
        if progress_callback:
            progress_callback(90)

    # --- Build payload + write HTML
    pdf_name = os.path.basename(pdf_path)
    payload = build_payload_from_inputs(
        pdf_name=pdf_name,
        raw_results=raw_results,
        page_labels=page_labels,
        page_dims=page_dims,
        page_highlights=page_highlights,
        capitalize_keys=capitalize_keys,
    )

    from model.web_template import render_html
    html_str = render_html(payload)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_str)

    if progress_callback:
        progress_callback(100)


# ---------------------------------------------------------------------------
# QThread wrapper
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import QThread, pyqtSignal

    class WebBundleThread(QThread):
        progress_updated = pyqtSignal(int)
        finished_ok = pyqtSignal(str)         # out_dir
        error_occurred = pyqtSignal(str)

        def __init__(self, pdf_path, raw_results, out_dir, *,
                     strategy, offset, index_front_matter, capitalize_keys):
            super().__init__()
            self._args = dict(
                pdf_path=pdf_path,
                raw_results=raw_results,
                out_dir=out_dir,
                strategy=strategy,
                offset=offset,
                index_front_matter=index_front_matter,
                capitalize_keys=capitalize_keys,
            )

        def run(self):
            try:
                generate_bundle_sync(
                    progress_callback=self.progress_updated.emit,
                    **self._args,
                )
                self.finished_ok.emit(self._args["out_dir"])
            except Exception as e:
                self.error_occurred.emit(str(e))
except ImportError:
    # PyQt6 is unavailable in some headless test environments; the
    # synchronous entry point above still works.
    WebBundleThread = None  # type: ignore[assignment]
```

### Step 6.4: Run the tests to verify they pass

- [ ] Run:
```bash
pytest tests/test_web_bundle_orchestrator.py -v
```
Expected: all 4 tests PASS.

### Step 6.5: Run the full test suite to confirm nothing regressed

- [ ] Run:
```bash
pytest tests/ -v
```
Expected: all PASS.

### Step 6.6: Commit

- [ ] Stage and commit:
```bash
git add model/web_bundle.py tests/test_web_bundle_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(web-bundle): orchestrator + cache + QThread wrapper

generate_bundle_sync ties together the page-data collection, image
rendering, payload build, and HTML emit. A .cache.json sidecar keyed
on PDF mtime + page count skips image regeneration when the source
hasn't changed. WebBundleThread provides the QThread entry point
the controller will use.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Settings sidebar checkbox

**Why:** The user-facing opt-in. Lives in the existing Output cluster next to the other format controls.

**Files:**
- Modify: `view/settings_sidebar.py`

### Step 7.1: Add the checkbox to the Output section

- [ ] Open `view/settings_sidebar.py` and locate the Output section. Immediately after the `self.separate_style_files_chk` lines (around line 222–224), insert:

```python
        self.generate_web_bundle_chk = QCheckBox("Generate web view")
        self.generate_web_bundle_chk.setToolTip(
            "Write a self-contained HTML+images bundle to <project>/web/ "
            "alongside the index files. Useful for sharing a browsable "
            "PDF + index with someone who doesn't have this app. "
            "Slow for large PDFs and uses noticeable disk space."
        )
        self.generate_web_bundle_chk.setChecked(False)
        layout.addWidget(self.generate_web_bundle_chk)
```

The new checkbox should appear inside the Output heading block, right below the "Separate index files by style" checkbox.

### Step 7.2: Verify the sidebar still renders by running the app's headless smoke test

- [ ] There is no headless smoke test for the sidebar today, so visual inspection is sufficient. Run:
```bash
pytest tests/ -v
```
Expected: all PASS (no regressions from adding the checkbox).

### Step 7.3: Commit

- [ ] Stage and commit:
```bash
git add view/settings_sidebar.py
git commit -m "$(cat <<'EOF'
feat(ui): Generate web view checkbox in settings sidebar

Opt-in toggle for the new HTML+images bundle export. Lives in the
Output cluster next to 'Separate index files by style'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Controller wiring — persist + launch the thread

**Why:** Connects the sidebar checkbox to the config save/load, and triggers `WebBundleThread` after each indexing run when enabled.

**Files:**
- Modify: `controller/main_controller.py`

### Step 8.1: Persist the checkbox in `save_current_config`

- [ ] Open `controller/main_controller.py` and locate the `save_current_config` method (around line 296). It builds a `config` dict and calls `ConfigManager.save_config`. Inside that builder (before the save call), add:

```python
        config["generate_web_bundle"] = (
            self.view.settings_sidebar.generate_web_bundle_chk.isChecked()
        )
```

Place this near the other `separate_style_files` etc. assignments to keep related options together.

### Step 8.2: Restore the checkbox from config on project open

- [ ] In the same controller, find where other sidebar checkboxes are restored from the config (search for `separate_style_files_chk.setChecked`). Immediately after that line, add:

```python
        self.view.settings_sidebar.generate_web_bundle_chk.setChecked(
            config.get("generate_web_bundle", False)
        )
```

### Step 8.3: Auto-save when toggled

- [ ] In `__init__` of the controller, find where `separate_style_files_chk.toggled.connect(lambda: self.save_current_config())` is wired (around line 79). Add an identical line for the new checkbox:

```python
        self.view.settings_sidebar.generate_web_bundle_chk.toggled.connect(
            lambda: self.save_current_config()
        )
```

### Step 8.4: Launch `WebBundleThread` from `save_results_to_files`

- [ ] Find `save_results_to_files` (around line 890). At the end of the method (after the per-bucket style files loop, before `def _write_format_files`), add:

```python
        # Optional web bundle export. Off by default; controlled by the
        # 'Generate web view' checkbox in the settings sidebar.
        if (
            self.view.settings_sidebar.generate_web_bundle_chk.isChecked()
            and self.last_raw_results is not None
            and self.current_pdf_path
        ):
            self._launch_web_bundle()
```

### Step 8.5: Add the `_launch_web_bundle` helper

- [ ] Just below `save_results_to_files` (and above `_write_format_files`), add the helper:

```python
    def _launch_web_bundle(self):
        from model.web_bundle import WebBundleThread

        if WebBundleThread is None:
            return  # PyQt missing; should never happen in the running app

        out_dir = os.path.join(self.project_path, "web")
        # Pick page-numbering settings from the sidebar, matching the
        # ones that produced the current index.
        sidebar = self.view.settings_sidebar
        strategy = "logical" if sidebar.radio_logical.isChecked() else "physical"
        offset = sidebar.offset_spin.value()
        index_front_matter = sidebar.index_front_matter_chk.isChecked()
        capitalize = sidebar.capitalize_chk.isChecked()

        # Cancel any in-flight bundle thread before starting a new one
        prev = getattr(self, "_web_bundle_thread", None)
        if prev is not None and prev.isRunning():
            prev.wait(50)

        thread = WebBundleThread(
            pdf_path=self.current_pdf_path,
            raw_results=self.last_raw_results,
            out_dir=out_dir,
            strategy=strategy,
            offset=offset,
            index_front_matter=index_front_matter,
            capitalize_keys=capitalize,
        )
        thread.progress_updated.connect(self.view.progress_bar.setValue)
        thread.finished_ok.connect(self._on_web_bundle_finished)
        thread.error_occurred.connect(self._on_web_bundle_error)
        self._web_bundle_thread = thread
        thread.start()

    def _on_web_bundle_finished(self, out_dir):
        # Hide the progress bar (the indexing flow may have already hidden
        # it; this is a defensive call).
        self.view.progress_bar.setVisible(False)

    def _on_web_bundle_error(self, message):
        self.view.progress_bar.setVisible(False)
        print(f"Web bundle generation failed: {message}")
```

### Step 8.6: Initialise the thread holder

- [ ] In the controller's `__init__`, near the other thread holders (e.g. `self.tag_cloud_thread = None`), add:

```python
        self._web_bundle_thread = None
```

### Step 8.7: Manually smoke-test in the app

- [ ] Start the app:
```bash
cd /Users/markburnett/GitHub/pdf-index
python main.py
```
- Open the existing test project (or create one from `test/test.pdf`).
- Tick "Generate web view".
- Click Create Index.
- Confirm `web/index.html` and `web/images/page-0001.png` appear in the project folder.
- Open `web/index.html` in a browser; verify pages render, highlights appear, sidebar clicks navigate, play/pause works.

### Step 8.8: Commit

- [ ] Stage and commit:
```bash
git add controller/main_controller.py
git commit -m "$(cat <<'EOF'
feat(controller): wire the Generate web view checkbox

When the option is enabled, save_results_to_files launches
WebBundleThread after the regular index files are written. Progress
flows into the existing progress bar; errors are surfaced to the
console without disturbing the index outputs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: HELP.md documentation

**Why:** Tells users what the new option does, when to use it, and how the bundle is laid out.

**Files:**
- Modify: `HELP.md`

### Step 9.1: Locate the existing Output section in HELP.md

- [ ] Open `HELP.md`. Find the heading covering output formats / index files (search for "Output" or "index.md" to find the right section).

### Step 9.2: Append a new sub-section about the web view

- [ ] Add the following at the end of that section (preserve the file's existing heading depth — use one extra `#` than the parent):

```markdown
### Web View (optional)

When **Generate web view** is enabled in the Settings sidebar, Create Index
also writes a self-contained browser-friendly bundle to
`<project>/web/`:

```
web/
  index.html        # the whole index in one HTML page
  images/           # one PNG per PDF page
```

Open `web/index.html` in any browser to browse the PDF page by page
with the index in a sidebar. Click a highlighted term in a page to
scroll the sidebar to that term's entry; click a page number in the
sidebar to jump to that page.

Controls in the top toolbar:

- **Pages / Scroll** — fit one page at a time, or continuous scrolling.
- **Sidebar** — show or hide the index sidebar (also `i`).
- **Highlights** — show or hide the indexed-term overlays (also `h`).
- **« First / ‹ Prev / Next › / Last »** — page-by-page navigation
  (also `Home`, `End`, `←`, `→`, `PageUp`, `PageDown`).
- **Page input** — type the printed page label (`iv`, `12`) and press
  Enter to jump.
- **Play / Pause** — auto-advance one page every N seconds (default 5).

The option is **off by default** because rendering page images takes
time and disk space, especially for long books. Re-running Create
Index reuses the existing page images when the PDF hasn't changed.

The bundle is intended to be zipped (the `web/` folder is one
self-contained artifact) and sent to someone who doesn't have the
desktop app — they can browse and audit the index in any browser.
```

### Step 9.3: Commit

- [ ] Stage and commit:
```bash
git add HELP.md
git commit -m "$(cat <<'EOF'
docs(help): document the Generate web view option

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Final verification

**Why:** Ensure the whole feature works end-to-end in a real browser before declaring done. The unit/integration tests catch logic regressions; this catches the JS and CSS.

### Step 10.1: Run the full test suite

- [ ] Run:
```bash
pytest tests/ -v
```
Expected: all PASS, including the new files:
- `tests/test_web_highlights.py`
- `tests/test_config_web_bundle_default.py`
- `tests/test_web_bundle_payload.py`
- `tests/test_web_bundle_pdf.py`
- `tests/test_web_template.py`
- `tests/test_web_bundle_orchestrator.py`

### Step 10.2: Manual end-to-end check against the bundled test PDF

- [ ] Run:
```bash
python main.py
```

- Create or open a project that points at `test/test.pdf`.
- Enable **Name Indexing** + **Generate web view**.
- Click **Create Index**.
- Confirm progress bar shows two phases (indexing, then bundle).
- Confirm `<project>/web/index.html` exists.
- Open the HTML file in Chrome/Safari/Firefox; manually verify:
  - [ ] Page mode shows one full page card at a time.
  - [ ] Scroll mode flows pages continuously.
  - [ ] Page header above each card uses the index's label (`iv`, `1`, ...).
  - [ ] `« First`, `‹ Prev`, `Next ›`, `Last »` all work.
  - [ ] Page-number input accepts `iv` and arabic; invalid input is a no-op.
  - [ ] Highlighted terms appear on the right pages.
  - [ ] Clicking a highlighted term scrolls the sidebar and pulses the entry.
  - [ ] Clicking a sidebar page number jumps to the page.
  - [ ] Filter input narrows the sidebar entries.
  - [ ] Style bucket buttons swap the visible entry list.
  - [ ] `Play` advances pages every 5 s; `Pause` stops; auto-stops at last page.
  - [ ] `Sidebar` button hides/shows the aside; state survives reload.
  - [ ] `Highlights` button hides/shows the overlays; state survives reload.
  - [ ] Keyboard shortcuts `←`, `→`, `Home`, `End`, `/`, `i`, `h` work.

### Step 10.3: Re-run check after PDF edit

- [ ] In the file system, `touch test/test.pdf` to bump its mtime, then re-run Create Index in the app. Confirm the images regenerate (their mtimes change).

### Step 10.4: Re-run check with no PDF change

- [ ] Without modifying the PDF, click Create Index again. Confirm `images/page-0001.png` mtime is unchanged (cache hit).

### Step 10.5: Final test-suite pass + clean commit if needed

- [ ] If any manual tweaks were needed in this task, commit them with a final tidy message; otherwise nothing further to commit. Report the feature as done.

---

## Self-Review Notes

- **Spec coverage:** Every section of the spec maps to a task:
  - Bundle layout → Tasks 6, 8.
  - Default-off opt-in → Tasks 2, 7, 8.
  - Page rendering + word-rect highlights → Tasks 1, 4.
  - Page header label → Task 4 (`collect_page_data`) + Task 5 (template).
  - Sidebar + style-bucket selector → Tasks 3, 5.
  - JSON payload shape → Tasks 3, 5.
  - Toolbar + view modes + slideshow → Task 5.
  - Click behaviors → Task 5 (JS).
  - Cache sidecar → Task 6.
  - Files added/modified list → all tasks.
  - Error handling (skip broken pages, non-fatal failures, `exist_ok`) → Tasks 6, 8.
  - Tests (unit + integration + manual) → Tasks 1, 3, 4, 5, 6, 10.

- **Placeholder scan:** No "TBD", no "add error handling later", every code step has runnable code.

- **Type consistency:** Verified the `key`/`display`/`pages` shape between Task 3 (`build_buckets`) and Task 5 (template JS reads `entry.key`, `entry.display`, `entry.pages`). Page tuple uses `physical`/`label` consistently. `term_key` (the function) returns the same lowercase form used as the DOM id suffix (`term-<key>`) and the data attribute on `.hl` spans.

- **Open questions:** None remaining; all design choices were locked in during brainstorming.
