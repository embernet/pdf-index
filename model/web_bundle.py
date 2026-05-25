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
