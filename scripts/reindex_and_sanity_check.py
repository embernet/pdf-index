"""Re-run the name indexer on the Schools In PREPUB V03 project, save a
fresh index.json, then run the sanity-check report against it.

Runs the existing NameIndexingThread synchronously (call run() directly,
not start()) under a headless QCoreApplication so PyQt signal emission
works without requiring a display.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.config import ConfigManager  # noqa: E402
from model.name_indexer import (  # noqa: E402
    NameIndexingThread, DEFAULT_STOPWORDS,
)
from model.reports import find_missing_capitalised_names  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1] / "Data" / "Schools In PREPUB V03"


def main() -> int:
    cfg = ConfigManager.load_config(str(PROJECT))
    pdf_path = str(PROJECT / cfg["pdf_filename"])
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return 1

    offset = cfg.get("offset", 0)
    index_from_offset = cfg.get("index_from_offset", True)
    start_page = abs(offset) if (index_from_offset and offset < 0) else 0

    excludes_file = PROJECT / "excludes.txt"
    exclude_words = set()
    if excludes_file.exists():
        exclude_words = {
            line.strip().lower()
            for line in excludes_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    stopwords_file = PROJECT / "stopwords.txt"
    extra_stopwords = set()
    if stopwords_file.exists():
        extra_stopwords = {
            line.strip().lower()
            for line in stopwords_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    stopwords = DEFAULT_STOPWORDS | extra_stopwords

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    print(f"Indexing {pdf_path!r}")
    print(f"  strategy={cfg['strategy']} offset={offset} start_page={start_page}")
    print(f"  excludes={len(exclude_words)} stopwords={len(stopwords)}")

    results = {}

    def on_finished(formatted, raw):
        results["formatted"] = formatted
        results["raw"] = raw

    def on_progress(p):
        sys.stdout.write(f"\r  progress: {p}%   ")
        sys.stdout.flush()

    def on_error(msg):
        results["error"] = msg

    t0 = time.monotonic()
    thread = NameIndexingThread(
        pdf_path=pdf_path,
        page_numbering_strategy=cfg["strategy"],
        offset=offset,
        include_bold=cfg.get("bold_indexing", False),
        exclude_words=exclude_words,
        stopwords=stopwords,
        name_type_overrides={},
        start_page=start_page,
        surname_first=cfg.get("surname_first", False),
        index_italic=cfg.get("index_italic", True),
        index_capitalised=cfg.get("index_capitalised", True),
        index_single_quotes=cfg.get("index_single_quotes", True),
        index_front_matter=cfg.get("index_front_matter_roman", True),
        single_quote_max_chars=cfg.get("single_quote_max_chars", 100),
        italic_max_chars=cfg.get("italic_max_chars", 100),
        bold_max_chars=cfg.get("bold_max_chars", 100),
    )
    thread.indexing_finished.connect(on_finished)
    thread.progress_updated.connect(on_progress)
    thread.error_occurred.connect(on_error)
    thread.run()  # synchronous — runs in this thread, not a worker
    t1 = time.monotonic()
    print()  # newline after progress
    print(f"Indexer finished in {t1 - t0:.1f}s")

    if "error" in results:
        print(f"Indexer error: {results['error']}")
        return 2
    if "raw" not in results:
        print("Indexer produced no results.")
        return 3

    raw = results["raw"]

    # Mirror the UI's post-processing: drop substring-duplicate entries
    # whose pages are fully covered by a longer entry. main_controller
    # does this after merging keyword + name results
    # (_try_merge_results -> _suppress_substring_duplicates). Without
    # this step the standalone script produces ~7% more entries than
    # the UI, all of them subform noise (e.g. "Adam" beneath "Adam
    # Gorb").
    try:
        from model.name_indexer import _suppress_substring_duplicates
        _suppress_substring_duplicates(raw)
    except Exception as e:
        print(f"WARN: substring-duplicate suppression failed: {e}")

    print(f"Index has {len(raw)} entries.")

    # Save new index.json
    out = PROJECT / "index.json"
    backup = PROJECT / "index.json.pre-eraworth-fix.json"
    if out.exists() and not backup.exists():
        out.rename(backup)
        print(f"Backed up old index.json -> {backup.name}")

    with open(out, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    print(f"Wrote new index.json ({out.stat().st_size:,} bytes).")

    # Sanity check against the fresh index
    pdf_context = {
        "pdf_path": pdf_path,
        "strategy": cfg["strategy"],
        "offset": offset,
        "start_page": start_page,
        "index_front_matter": cfg.get("index_front_matter_roman", True),
        "exclude_words": exclude_words,
        "stopwords": stopwords,
    }
    t2 = time.monotonic()
    section = find_missing_capitalised_names(raw, pdf_context)
    t3 = time.monotonic()
    print(f"\nSanity check ran in {(t3 - t2) * 1000:.0f}ms")
    print(f"Missing capitalised candidates: {len(section.findings)}")

    # Save full missing list
    out_md = PROJECT / "sanity-check-missing-caps.md"
    lines = [
        "# Sanity check — missing capitalised names",
        "",
        f"_{len(section.findings)} candidates found in the PDF that are NOT in the index._",
        "",
        "Each entry shows the candidate, the page labels where it appears, and the two index entries it falls between alphabetically.",
        "",
    ]
    for f in section.findings:
        cand = f.terms[0]
        pages = f.pages_by_term[cand]
        page_labels = ", ".join(p.page_label for p in pages)
        lines.append(f"- **{cand}** — pages: {page_labels}  ")
        lines.append(f"  _{f.note}_")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_md.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
