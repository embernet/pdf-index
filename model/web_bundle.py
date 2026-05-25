"""Web bundle exporter.

Produces a self-contained HTML page plus a folder of per-page PNGs in
``<project>/web/``. The HTML embeds the index data as JSON and includes
inline CSS/JS so the folder can be zipped and shared standalone.

This module is structured in three layers:

1. Pure helpers (build_payload_from_inputs, build_buckets, rect_to_percent,
   term_key) — no I/O, no PyMuPDF. Unit-tested independently.
2. PyMuPDF integration (collect_page_data, render_page_image) — does the
   page-rendering and word-rect computation.
3. The WebBundleThread orchestrator and the generate_bundle_sync entry point.
"""
from __future__ import annotations

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
    page_labels: list,
    page_dims: list,
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

    front_matter_idx = (
        set(range(0, offset))
        if (index_front_matter and offset > 0) else set()
    )

    terms_by_page = {}
    for term, occurrences in raw_results.items():
        for occ in occurrences:
            phys = occ[0]
            terms_by_page.setdefault(phys, []).append(term)

    page_labels = []
    page_dims = []
    page_highlights = {}

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


# ---------------------------------------------------------------------------
# Cache sidecar
# ---------------------------------------------------------------------------

def _read_cache(out_dir: str) -> dict:
    import json
    import os
    path = os.path.join(out_dir, ".cache.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_cache(out_dir: str, pdf_mtime: float, page_count: int):
    import json
    import os
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

    page_labels, page_dims, page_highlights = collect_page_data(
        pdf_path, raw_results,
        strategy=strategy, offset=offset,
        index_front_matter=index_front_matter,
    )
    page_count = len(page_labels)
    if progress_callback:
        progress_callback(10)

    pdf_mtime = os.path.getmtime(pdf_path)
    cache = _read_cache(out_dir)
    render_images = not _cache_matches(cache, pdf_mtime, page_count)

    if render_images:
        for i in range(page_count):
            out_path = os.path.join(images_dir, f"page-{i+1:04d}.png")
            try:
                render_page_image(pdf_path, i, out_path, zoom=zoom)
            except Exception:
                continue
            if progress_callback:
                progress_callback(10 + int((i + 1) / page_count * 80))
        _write_cache(out_dir, pdf_mtime, page_count)
    else:
        if progress_callback:
            progress_callback(90)

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
    WebBundleThread = None  # type: ignore[assignment]
