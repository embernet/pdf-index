# Web Bundle Export — Design

**Date:** 2026-05-25
**Status:** Approved

## Summary

Add a new output format to the PDF index app: a self-contained HTML+images
bundle in `<project>/web/` that lets someone without the desktop app
browse the indexed PDF in a browser. The page is shown on the left, an
active index on the right, with two-way click navigation: clicking a
highlighted term in the page jumps the sidebar to that term's entry;
clicking a page link in an index entry jumps the document to that page.

The bundle is generated as one folder containing a single `index.html`
and an `images/` subfolder of per-page PNGs, designed to be zipped and
shared as a single artifact.

## Goals

- Quick "do I have all the terms indexed?" review by someone without the
  app — they scroll the document, see what's highlighted, and check the
  index sidebar.
- One-folder, zippable artifact. No external CDN, no build step.
- Bundle generation is opt-in. The desktop app's normal output flow is
  unchanged when the feature is off.

## Non-Goals

- The LLM Enhanced bucket. Web bundle uses the rule-based index only.
- Embedding the Merge tool, Reports, or Tag Cloud views.
- Annotation/markup tools in the web page.
- Multi-PDF projects (none exist in the app today).
- Server-rendered or interactive editing. The bundle is read-only.

## Bundle Layout

```
<project>/web/
  index.html       single-file HTML with inline CSS, inline JS,
                   and an embedded <script type="application/json">
                   payload carrying terms, pageLabels, and highlights
  images/
    page-0001.png  PNG @ 1.5x zoom (~150 DPI), one per physical page
    page-0002.png
    ...
  .cache.json      best-effort sidecar: { "pdf_mtime": ..., "page_count": ... }
                   Used to skip image regeneration when the source PDF
                   hasn't changed. Index HTML always rewrites.
```

A single self-contained `index.html` was preferred over splitting CSS/JS
into separate files so the bundle has no asset-loading dependency
beyond the `images/` folder.

## Generation Trigger

A new checkbox in the settings sidebar — `Generate web view` — gates the
feature. **Default: off.** When on, the bundle is regenerated
automatically whenever `Create Index` completes, alongside the existing
`index.md/.txt/.html/.json` writes. When off, no `web/` folder is
touched; existing `web/` folders from prior runs are preserved (no
surprise deletes).

Image rendering is the slow part for large PDFs. A new
`WebBundleThread(QThread)` runs after indexing finishes so the UI stays
responsive; it emits progress to the existing progress bar.

## Re-Render Policy

- Index HTML rewrites every run.
- Page images skip regeneration when `web/.cache.json` reports the same
  `pdf_mtime` and `page_count` as the current PDF.
- Corrupt or missing cache → re-render all images.

## Page Rendering & Highlights

### Per-page card structure

```
<div class="page" data-physical="4" data-label="iv">
  <header class="page-header">Page iv</header>
  <div class="page-canvas" style="aspect-ratio:612/792">
    <img src="images/page-0004.png" alt="Page iv">
    <span class="hl" data-term="Mozart"
          style="left:32.4%;top:18.1%;width:6.2%;height:1.8%"></span>
    ...
  </div>
</div>
```

The page header sits outside the page canvas so the label is visible
regardless of what the page itself prints. `.page-canvas` is a
percentage-positioned containing block; each `.hl` span is absolutely
positioned in percent-of-page coordinates so the image and highlights
scale together at any zoom or fit level.

### Page header labels

Reuse `model.indexer.label_for_page` exactly as the index does. Roman
numerals appear for front-matter pages when "Index front matter (roman)"
is on and the page falls before the offset; otherwise the logical PDF
label, falling back to physical-page + offset.

### Word-position computation

At bundle-generation time:

1. For each physical page, call `page.get_text("words")` (the same call
   the desktop viewer uses) → `[(x0,y0,x1,y1,word,block,line,word_no), ...]`.
2. For each `(term, [physical_page_index, ...])` in `raw_results`,
   compute word indices on the matching pages via the existing
   `_search_variants` / `_match_term_at` helpers (handling
   `"Smith, John"` ↔ `"John Smith"` natural-order, hyphenation joins,
   and possessive-`s` stripping).
3. Merge consecutive same-line word bboxes belonging to the same term
   into a single rect (matching the desktop viewer's
   `_merge_indices_into_spans` rule).
4. Convert PDF-point rects to percent-of-page using the page's
   `mediabox` so the HTML scales correctly at any zoom.

These helpers live in a new shared `model/web_highlights.py`. The PDF
viewer is refactored to import them from there — no behavior change.

## Sidebar (Index)

```
<aside id="index-sidebar">
  <header>
    <input class="filter" placeholder="Filter index..." />
    <div class="style-bar">
      [Aggregate] [Italic] [Bold] [Caps] [Single-Quotes] [Other]
    </div>
  </header>
  <div class="entries">
    <div class="entry" id="term-mozart" data-term-key="mozart">
      <b>Mozart</b>
      <a data-page="3">iv</a>,
      <a data-page="16">12</a>–<a data-page="18">14</a>
    </div>
    ...
  </div>
</aside>
```

Style buckets are pre-computed server-side via `filter_by_style` and
shipped in the JSON payload, one list per bucket. Toggling a bucket
swaps the visible entry list. The filter input does client-side
substring matching against entry terms.

LLM Enhanced bucket is intentionally excluded.

## Embedded Data Payload

Single `<script id="bundle-data" type="application/json">` block. Shape:

```json
{
  "pdf": { "name": "book.pdf", "page_count": 248 },
  "pageLabels": ["i", "ii", "iii", "iv", "1", "2", ...],
  "pageDims":   [{"w":612,"h":792}, ...],
  "buckets": {
    "aggregate": [
      {"key":"mozart","display":"Mozart",
       "pages":[{"physical":3,"label":"iv"},{"physical":16,"label":"12"}]},
      ...
    ],
    "italic": [...], "bold": [...], "caps": [...],
    "single-quotes": [...], "other": [...]
  },
  "highlights": {
    "3": [{"term_key":"mozart","rect":[0.324,0.181,0.062,0.018]}],
    ...
  }
}
```

`term_key` is the lower-cased term used as DOM `id` suffix; `display`
is what's shown to the reader.

## Top Toolbar

Sticky top bar, single row, wraps gracefully:

```
[Pages | Scroll]   [Sidebar ☰]   [Highlights ✓]
[« First] [‹ Prev] [Page ___ /248] [Next ›] [Last »]
[▶ Play] [⏸] [Interval: 5 s]
```

### View modes

- **Page mode (default):** one page card fills the viewport. CSS
  `scroll-snap-type: y mandatory` plus `scroll-snap-align: start` on
  cards so wheel/PageDown lands cleanly on one page. Image inside the
  card uses `object-fit: contain` to fit any aspect ratio.
- **Scroll mode:** snap disabled, cards lose viewport-height constraint
  and flow at intrinsic width (capped at 95vw).

### Navigation

- **« First / Last »** — scroll to first/last page card.
- **‹ Prev / Next ›** — ±1 page.
- **Page input** — accepts displayed *label* (`iv`, `12`),
  case-insensitive, matched against `pageLabels` (client-side
  equivalent of `resolve_label_to_index`). Enter commits; empty/invalid
  is a no-op.
- **Keyboard:** ← / → and PageUp/PageDown step pages; Home / End jump
  to first/last; `/` focuses sidebar filter; `i` toggles sidebar; `h`
  toggles highlights.

### Slideshow

- ▶ Play advances one page every N seconds (default 5, min 1, max 60).
- ⏸ Pause stops the timer.
- The play button visually flips to pause while running; pressing again
  resumes/pauses.
- Reaching the last page auto-stops the timer. No wraparound.

### Persistent toggles

`sidebar-visible` and `highlights-on` states are saved to
`localStorage` so the bundle remembers its view between visits in the
same browser.

## Click Behaviors

- **Highlighted span in page clicked** → look up `term_key` from
  `data-term`, scroll the sidebar to `#term-<key>`, apply a `.pulse`
  class for ~1500ms.
- **Page link in sidebar clicked** → scroll to that `.page` card
  (page mode: snap-jump; scroll mode: smooth scroll).
- **Filter input** → hides `.entry` rows whose display text doesn't
  contain the filter substring (case-insensitive).

When one term appears multiple times on a page, all of its highlighted
occurrences jump the sidebar to the same entry. No accent-cycling
within a page (matches the simpler-is-better answer from brainstorming).

## Files Added / Modified

- `model/web_highlights.py` (new) — shared word-match helpers extracted
  from `view/pdf_viewer.py`:
  - `find_term_word_rects(page_words, term) -> list[tuple]`
  - `merge_word_rects_to_spans(words, indices) -> list[(x,y,w,h)]`
- `model/web_bundle.py` (new) — `WebBundleThread(QThread)` and pure
  helpers `build_payload(...)` and `render_html(payload)`.
- `model/web_template.py` (new) — Python string literals for the HTML
  shell, inline CSS, and inline JS.
- `view/pdf_viewer.py` (modified) — import shared helpers from
  `web_highlights.py`. No behavior change.
- `view/settings_sidebar.py` (modified) — adds the `Generate web view`
  checkbox in the Output cluster.
- `model/config.py` (modified) — adds `generate_web_bundle: False`
  default.
- `controller/main_controller.py` (modified) — wires the checkbox,
  launches `WebBundleThread` after indexing finishes when enabled.
- `HELP.md` (modified) — documents the feature.

## Error Handling

- Bundle generation runs on its own thread; failure surfaces as a
  non-fatal status message. The existing `index.*` files are unaffected.
- `os.makedirs(..., exist_ok=True)` for directory creation.
- Per-page rendering errors (rare) skip that page with a placeholder
  comment; the rest of the bundle continues.
- Corrupt or missing `.cache.json` → re-render all images.
- Bundle never deletes existing files outside `web/`.

## Testing

### Unit tests (under `tests/`, matching existing style)

- `model/web_highlights.py`:
  - `find_term_word_rects` against synthetic word lists for: single
    word, multi-word, inverted `"Smith, John"`, hyphenation join,
    possessive `'s`, no-match.
- `model/web_bundle.py`:
  - `build_payload(raw_results, pdf_path, config)` returns the expected
    bucket shape, page count, and `term_key` lowercasing.
  - Rect-to-percent conversion uses the page mediabox correctly.
  - Label assignment for front-matter offset pages uses roman numerals
    when configured.

### Integration test

- Build the existing `test/test.md` → PDF (already part of
  `test/check_index.py`).
- Run `WebBundleThread` headlessly against it.
- Assert: `web/index.html` exists; contains expected term anchors;
  `web/images/page-0001.png` exists and is non-empty; highlight rect
  count for a known page matches expected occurrences.

### Manual verification (part of implementation plan)

- Open `web/index.html` in a real browser. Confirm:
  - Page mode fits one page at a time, scroll-snap works.
  - Scroll mode flows continuously.
  - Slideshow ▶ / ⏸, interval edit, auto-stop at last page.
  - Sidebar toggle hides/shows the aside; persists across reload.
  - Highlights toggle hides/shows `.hl` spans; persists across reload.
  - Clicking a highlight scrolls the sidebar and pulses the entry.
  - Clicking a sidebar page link jumps to the page card.
  - Style bucket selector swaps visible entries.
  - Filter input narrows entries live.
  - Page-number input accepts roman labels (`iv`) and arabic.
  - Keyboard shortcuts work.

## Open Questions / Future Work

- LLM Enhanced bucket export (deferred).
- Per-style highlight colors (currently all yellow). Trivial CSS swap
  if requested later.
- Configurable image format / resolution (currently fixed at PNG @
  1.5x). Configurable via UI if size becomes a real concern.
