"""Render and write LLM-enhanced index outputs.

The existing rule-based pipeline writes its files at ``<project>/index.{md,txt,html,json}``.
This module writes a parallel set at ``<project>/index.enhanced.{md,txt,html,json}``
so the rule-based output is *never* mutated when the user runs LLM enrichment.

The four enhancement types from ``model.llm_enrichment`` plug in here:

* sub-entries  — break a dense entry into themed children with concise labels
* aliases      — merged page lists for synonym groups
* categories   — per-entry tag (Composer / Place / Work / ...)
* see-also     — cross-references between related entries

When ``suggestions`` is None or empty, the enhanced output is structurally
identical to the base output but written under the ``.enhanced.`` filename so
the user always gets a separate copy they can compare side by side.
"""

from __future__ import annotations

import html as html_mod
import json
import os
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Suggestion data shapes (kept loose dicts — populated by llm_enrichment)
# ---------------------------------------------------------------------------
#
# suggestions = {
#     "subentries": {term: [{"label": str, "pages": "1, 4-7", "page_idxs": [...]}, ...], ...},
#     "aliases":    [{"primary": str, "merged": [str, ...], "pages": "..."}, ...],
#     "categories": {term: "Composer"},
#     "see_also":   {term: ["term1", "term2"]},
# }
#
# All four are optional — renderers tolerate missing keys.


def _categorised_groups(formatted: Dict[str, str], categories: Dict[str, str]) -> Dict[str, List[str]]:
    """Group entries by category. Entries with no category land in 'Uncategorised'."""
    groups: Dict[str, List[str]] = {}
    for term in formatted.keys():
        cat = categories.get(term, "") or "Uncategorised"
        groups.setdefault(cat, []).append(term)
    return groups


def render_enhanced_markdown(formatted: Dict[str, str], suggestions: Optional[dict] = None) -> str:
    """Markdown rendering of the enhanced index.

    Format mirrors :py:meth:`MainController.generate_markdown` so users can
    diff the base and enhanced files. Sub-entries appear as indented child
    bullets under the parent. Categories drive section headers when present.
    See-also appears as italic trailing text.
    """
    s = suggestions or {}
    subentries: Dict[str, list] = s.get("subentries") or {}
    categories: Dict[str, str] = s.get("categories") or {}
    see_also: Dict[str, list] = s.get("see_also") or {}

    count = len(formatted)
    lines = [f"# Enhanced Index ({count} entries)\n"]

    if categories:
        groups = _categorised_groups(formatted, categories)
        for cat in sorted(groups.keys()):
            lines.append(f"\n## {cat}\n")
            for term in sorted(groups[cat], key=str.lower):
                lines.extend(_md_entry(term, formatted[term], subentries.get(term), see_also.get(term)))
    else:
        for term in sorted(formatted.keys(), key=str.lower):
            lines.extend(_md_entry(term, formatted[term], subentries.get(term), see_also.get(term)))

    return "\n".join(lines)


def _md_entry(term: str, pages: str, subs, see_also_list) -> list:
    out = [f"**{term}** {pages}  "]
    if subs:
        for sub in subs:
            label = (sub.get("label") or "").strip()
            sub_pages = (sub.get("pages") or "").strip()
            if not label:
                continue
            out.append(f"  - *{label}* {sub_pages}".rstrip())
    if see_also_list:
        targets = ", ".join(t for t in see_also_list if t)
        if targets:
            out.append(f"  - *see also* {targets}".rstrip())
    return out


def render_enhanced_text(formatted: Dict[str, str], suggestions: Optional[dict] = None) -> str:
    s = suggestions or {}
    subentries: Dict[str, list] = s.get("subentries") or {}
    categories: Dict[str, str] = s.get("categories") or {}
    see_also: Dict[str, list] = s.get("see_also") or {}

    count = len(formatted)
    lines = [f"Enhanced Index ({count} entries)\n"]

    if categories:
        groups = _categorised_groups(formatted, categories)
        for cat in sorted(groups.keys()):
            lines.append(f"\n[{cat}]")
            for term in sorted(groups[cat], key=str.lower):
                lines.extend(_text_entry(term, formatted[term], subentries.get(term), see_also.get(term)))
    else:
        for term in sorted(formatted.keys(), key=str.lower):
            lines.extend(_text_entry(term, formatted[term], subentries.get(term), see_also.get(term)))

    return "\n".join(lines)


def _text_entry(term, pages, subs, see_also_list) -> list:
    out = [f"{term} {pages}"]
    if subs:
        for sub in subs:
            label = (sub.get("label") or "").strip()
            sub_pages = (sub.get("pages") or "").strip()
            if not label:
                continue
            out.append(f"    {label}: {sub_pages}".rstrip(": "))
    if see_also_list:
        targets = ", ".join(t for t in see_also_list if t)
        if targets:
            out.append(f"    see also: {targets}")
    return out


def render_enhanced_html(formatted: Dict[str, str], suggestions: Optional[dict] = None) -> str:
    s = suggestions or {}
    subentries: Dict[str, list] = s.get("subentries") or {}
    categories: Dict[str, str] = s.get("categories") or {}
    see_also: Dict[str, list] = s.get("see_also") or {}

    esc = html_mod.escape
    count = len(formatted)
    lines = [
        "<html><head><meta charset=\"utf-8\"><style>",
        "body { font-family: sans-serif; }",
        "h1 { margin-bottom: 0.4em; }",
        "h2 { margin-top: 1.2em; color: #444; }",
        ".entry { margin: 4px 0; }",
        ".sub { margin-left: 20px; color: #333; font-style: italic; }",
        ".see-also { margin-left: 20px; color: #666; font-style: italic; }",
        "</style></head><body>",
        f"<h1>Enhanced Index ({count} entries)</h1>",
    ]

    def _html_entry(term, pages, subs, see_also_list) -> list:
        out = [f"<div class=\"entry\"><b>{esc(term)}</b> {esc(pages)}</div>"]
        if subs:
            for sub in subs:
                label = (sub.get("label") or "").strip()
                sub_pages = (sub.get("pages") or "").strip()
                if not label:
                    continue
                out.append(
                    f"<div class=\"sub\">{esc(label)} &mdash; {esc(sub_pages)}</div>"
                )
        if see_also_list:
            targets = ", ".join(esc(t) for t in see_also_list if t)
            if targets:
                out.append(f"<div class=\"see-also\">see also {targets}</div>")
        return out

    if categories:
        groups = _categorised_groups(formatted, categories)
        for cat in sorted(groups.keys()):
            lines.append(f"<h2>{esc(cat)}</h2>")
            for term in sorted(groups[cat], key=str.lower):
                lines.extend(_html_entry(term, formatted[term], subentries.get(term), see_also.get(term)))
    else:
        for term in sorted(formatted.keys(), key=str.lower):
            lines.extend(_html_entry(term, formatted[term], subentries.get(term), see_also.get(term)))

    lines.append("</body></html>")
    return "\n".join(lines)


def render_enhanced_json(raw_results: dict, suggestions: Optional[dict] = None) -> str:
    """Self-describing JSON containing the raw aggregate plus all suggestions.

    The shape is intentionally ergonomic for downstream tooling: a stable
    top-level schema with empty stubs when a suggestion type wasn't
    requested.
    """
    s = suggestions or {}
    payload = {
        "schema": "pdf-index/enhanced/1",
        "raw_results": raw_results or {},
        "subentries": s.get("subentries") or {},
        "aliases": s.get("aliases") or [],
        "categories": s.get("categories") or {},
        "see_also": s.get("see_also") or {},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Top-level writer
# ---------------------------------------------------------------------------

def write_enhanced_files(
    path_base: str,
    formatted: Dict[str, str],
    raw_results: Optional[dict] = None,
    suggestions: Optional[dict] = None,
) -> List[str]:
    """Write the four ``.enhanced.{md,txt,html,json}`` files.

    *path_base* is the same prefix the existing writer uses
    (e.g. ``<project>/index``). Returns the list of absolute paths written.

    Never modifies the base ``<path_base>.{md,txt,html,json}`` files. If a
    write fails for one extension, the function still attempts the others
    and surfaces the error path-list to the caller for logging.
    """
    md_content = render_enhanced_markdown(formatted, suggestions)
    txt_content = render_enhanced_text(formatted, suggestions)
    html_content = render_enhanced_html(formatted, suggestions)
    json_content = render_enhanced_json(raw_results or {}, suggestions)

    written: List[str] = []
    for ext, content in (
        (".enhanced.md", md_content),
        (".enhanced.txt", txt_content),
        (".enhanced.html", html_content),
        (".enhanced.json", json_content),
    ):
        full = path_base + ext
        try:
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            written.append(os.path.abspath(full))
        except OSError:
            continue
    return written
