#!/usr/bin/env python3
"""Build the test PDF, run the name indexer headlessly, and compare the
generated output against the expected entries documented in test/expected.md.

Usage:
    python test/check_index.py [<project-directory>]

If <project-directory> is omitted, the test/ folder itself is used as the
project. The script will:
  1. Run pandoc to convert test/test.md to test/test.pdf (skipped if the
     PDF already exists and is newer than the source).
  2. Run NameIndexingThread on the PDF (no GUI required) and write
     index.json, index.md, and the per-style index-*.md files into the
     project directory.
  3. Compare the entries against the EXPECTED and FORBIDDEN lists below.
  4. Print a pass/fail report and exit non-zero on any required failure.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Expected entries — keyed by entry text, value is the minimum set of style
# flags the indexer is required to record on at least one occurrence.
# ---------------------------------------------------------------------------

EXPECTED = {
    "A Clockwork Orange":              {"italic"},
    "A note on proximity":             {"bold"},
    "Absinthe":                        {"italic"},
    "Adam Gorb":                       set(),
    "Alistair Pemberton":              set(),
    "Anthony Burgess":                 set(),
    "BBC":                             {"caps"},
    "Beatrice":                        set(),       # standalone references on page 1
    "Beatrice Halloway":               set(),
    "Bertrand":                        set(),
    "Bridgewater Hall":                set(),
    "Cambridge":                       set(),
    "CERN":                            {"caps"},
    "Cloudcatcher Fells":              {"italic"},
    "col legno":                       {"italic"},
    "Concerto for Orchestra":          {"italic"},
    "Crawley":                         set(),       # in "Crawley and Halloway" example
    "Cygnus":                          set(),
    "Echoes of the Bridgewater Hall":  {"italic"},
    # Commas are skipped during phrase capture so the entry text omits them.
    "An index she felt was the most generous thing a writer could leave behind": {"bold"},
    "Edmund Crawley":                  {"bold"},    # bolded once in chapter intro
    "Halle Choir":                     set(),
    "Halle Orchestra":                 set(),
    "Halloway":                        set(),       # in "Crawley and Halloway" example
    "in vino veritas":                 {"italic"},
    "John McCabe":                     set(),
    "Manchester":                      set(),       # appears on page 1 AND page 3
    "Manchester Free Trade Hall":      set(),
    # pandoc smart-quotes converts ' to U+2019 in the PDF; match that.
    "Margaret O’Donnell":         set(),
    "NATO":                            {"caps"},
    "Pemberton":                       set(),
    "Royal Conservatory":              set(),
    "Royal Northern College":          set(),
    "the polonaise":                   {"italic"},
    "The Guardian":                    {"italic"},
    "The Sound of Music":              {"italic"},
    "Thomas Beecham":                  set(),
    "War and Peace":                   {"italic"},
}

# Entries that must NOT appear anywhere in the index.
FORBIDDEN = {
    # All-caps headings — should be filtered as headings.
    "INTRODUCTION", "CONCLUSION",
    "CHAPTER ONE", "CHAPTER TWO", "CHAPTER THREE",
    # Stop words alone — never start an n-gram.
    "The", "A", "An", "Every", "Some",
    # Title prefixes alone — skipped without breaking the n-gram.
    "Dr", "Mr", "Mrs", "Sir", "Prof",
    # Footnote reference number — superscript digit must not be admitted.
    "3",
    # Half-words from hyphenation split — must reconstruct as "Bridgewater".
    "Bridge", "Bridge-",
    # Possessive forms — should be normalised to base name.
    "Crawley's", "Pemberton's",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\* ', re.MULTILINE)


def collect_flags(occurrences):
    """OR all per-occurrence flags across an entry's pages."""
    flags = set()
    for occ in occurrences:
        if len(occ) >= 3 and isinstance(occ[2], dict):
            for k, v in occ[2].items():
                if v:
                    flags.add(k)
    return flags


def parse_md_entries(path):
    """Extract entry names from a generated index .md file."""
    if not path.exists():
        return None
    with open(path) as f:
        text = f.read()
    return set(ENTRY_RE.findall(text))


def expected_per_bucket():
    """Group EXPECTED entries by the per-style file each one should land in.

    Each entry appears in every bucket whose flag is in its expected flags
    (italic / bold / caps), and additionally in the "other" bucket only if
    its expected flags are empty.
    """
    buckets = {"italic": set(), "bold": set(), "caps": set(), "other": set()}
    for entry, flags in EXPECTED.items():
        if not flags:
            buckets["other"].add(entry)
        else:
            for flag in flags:
                buckets[flag].add(entry)
    return buckets


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_name_indexer(pdf_path: Path, project: Path) -> bool:
    """Run the name indexer on *pdf_path* and write index files into *project*.

    Returns True on success, False on failure.
    """
    # The script lives in test/, the model lives in ../model. Make the project
    # root importable.
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from PyQt6.QtWidgets import QApplication
        from model.indexer import IndexingThread, filter_by_style
        from model.name_indexer import NameIndexingThread, DEFAULT_STOPWORDS
    except ImportError as e:
        print(f"error: failed to import indexer modules: {e}")
        print("Run `pip install -r requirements.txt` from the repo root.")
        return False

    # A QApplication is required for QThread internals even though we never
    # show a window.
    _ = QApplication.instance() or QApplication([])

    print(f"running name indexer on {pdf_path.name}...")

    thread = NameIndexingThread(
        str(pdf_path),
        "logical",
        0,
        include_bold=True,
        exclude_words=set(),
        stopwords=DEFAULT_STOPWORDS,
        name_type_overrides={},
        start_page=0,
        surname_first=False,
        index_italic=True,
        index_capitalised=True,
        index_front_matter=False,
    )

    captured = {}

    def _on_finished(_formatted, raw):
        captured.update(raw)

    thread.indexing_finished.connect(_on_finished)
    # .run() executes synchronously in this thread; .start() would spawn a real
    # OS thread and we'd have to wait on the event loop.
    thread.run()

    if not captured:
        print("error: name indexer produced no entries")
        return False

    # Write the aggregate index.json.
    base = project / "index"
    with open(str(base) + ".json", "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)

    # Write index.md, index.txt, index.html, and per-style files.
    formatted = IndexingThread.process_results(None, captured)
    _write_format_files(base, formatted)

    for bucket in ("italic", "bold", "caps", "other"):
        filtered_raw = filter_by_style(captured, bucket)
        filtered_formatted = IndexingThread.process_results(None, filtered_raw)
        _write_format_files(project / f"index-{bucket}", filtered_formatted)

    print(f"  wrote index.json with {len(captured)} entries")
    return True


def _write_format_files(path_base: Path, results: dict) -> None:
    count = len(results)
    md_lines = [f"# Index ({count} entries)\n"]
    txt_lines = [f"Index ({count} entries)\n"]
    html_lines = [f"<html><body><h1>Index ({count} entries)</h1>"]
    for kw, pages in results.items():
        md_lines.append(f"**{kw}** {pages}  ")
        txt_lines.append(f"{kw} {pages}")
        html_lines.append(f"<div><b>{kw}</b> {pages}</div>")
    html_lines.append("</body></html>")
    with open(str(path_base) + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    with open(str(path_base) + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))
    with open(str(path_base) + ".html", "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))


def build_pdf(source_md: Path, target_pdf: Path) -> bool:
    """Run pandoc to convert *source_md* to *target_pdf*.

    Returns True if the PDF is fresh (built or already up to date), False on
    pandoc failure. Skips the build when the PDF is newer than the source.
    """
    if not source_md.exists():
        print(f"error: source file {source_md} not found")
        return False

    if (target_pdf.exists()
            and target_pdf.stat().st_mtime >= source_md.stat().st_mtime):
        return True

    if shutil.which("pandoc") is None:
        print("error: pandoc not found on PATH")
        print("Install pandoc (https://pandoc.org/) and re-run this script.")
        return False

    print(f"building {target_pdf.name} from {source_md.name}...")
    try:
        result = subprocess.run(
            ["pandoc", str(source_md), "-o", str(target_pdf)],
            capture_output=True, text=True, check=False,
        )
    except OSError as e:
        print(f"error: failed to invoke pandoc: {e}")
        return False

    if result.returncode != 0:
        print(f"error: pandoc exited {result.returncode}")
        if result.stderr:
            print(result.stderr)
        return False

    return True


def main():
    test_dir = Path(__file__).resolve().parent
    source_md = test_dir / "test.md"
    target_pdf = test_dir / "test.pdf"

    if len(sys.argv) >= 2:
        arg = Path(sys.argv[1]).expanduser().resolve()
        if arg.is_file() and arg.name == "index.json":
            index_path = arg
            project = arg.parent
        else:
            project = arg
            index_path = project / "index.json"
    else:
        # Default: use the test/ folder itself as the project directory.
        project = test_dir
        index_path = project / "index.json"

    # Step 1: ensure the PDF exists (rebuild if source is newer).
    if not build_pdf(source_md, target_pdf):
        sys.exit(2)

    # Step 2: run the indexer if no index.json exists, or if the PDF is newer.
    needs_run = (not index_path.exists()
                 or index_path.stat().st_mtime < target_pdf.stat().st_mtime)
    if needs_run and project == test_dir:
        if not run_name_indexer(target_pdf, project):
            sys.exit(2)
    elif not index_path.exists():
        print(f"error: index.json not found at {index_path}")
        print()
        print("Open the pdf-index app, create or open a project at the path")
        print("above, import test/test.pdf, click *Create Index*, then re-run")
        print("this script. Or omit the project argument to use test/ as the")
        print("project (the script will run the indexer for you):")
        print("    python test/check_index.py")
        sys.exit(2)

    with open(index_path) as f:
        raw = json.load(f)

    actual = {entry: collect_flags(occs) for entry, occs in raw.items()}

    passed = 0
    failed = 0
    warnings = 0
    failures = []
    flag_warnings = []

    # 1. Every expected entry must appear in the aggregate index.
    for entry, expected_flags in EXPECTED.items():
        if entry not in actual:
            failures.append(f"  missing entry: {entry!r}")
            failed += 1
            continue
        passed += 1
        if expected_flags and not expected_flags.issubset(actual[entry]):
            missing_flags = expected_flags - actual[entry]
            flag_warnings.append(
                f"  {entry!r}: expected flags {sorted(expected_flags)}, "
                f"got {sorted(actual[entry])}, missing {sorted(missing_flags)}"
            )
            warnings += 1

    # 2. Forbidden entries must not appear.
    for entry in FORBIDDEN:
        if entry in actual:
            failures.append(f"  forbidden entry present: {entry!r}")
            failed += 1
        else:
            passed += 1

    # 3. Per-style files (only checked when the .md files exist on disk).
    bucket_results = []
    expected_buckets = expected_per_bucket()
    for bucket, expected_set in expected_buckets.items():
        path = project / f"index-{bucket}.md"
        found = parse_md_entries(path)
        if found is None:
            bucket_results.append(
                (bucket, None, None, f"file not present: {path.name}")
            )
            continue
        missing_in_file = expected_set - found
        if missing_in_file:
            for m in sorted(missing_in_file, key=str.lower):
                failures.append(
                    f"  index-{bucket}.md: missing entry {m!r}"
                )
                failed += 1
        else:
            passed += 1
        bucket_results.append((bucket, sorted(found, key=str.lower),
                               sorted(missing_in_file, key=str.lower), None))

    # (Bold file is no longer required to be empty — the test corpus now
    # contains a few bolded names so the bold bucket is exercised.)

    # 5. Extras (informational only).
    expected_or_forbidden = set(EXPECTED) | FORBIDDEN
    extras = sorted(
        (e for e in actual if e not in expected_or_forbidden),
        key=str.lower,
    )

    # ----- Report ------------------------------------------------------------
    print("=== pdf-index test report ===")
    print(f"project:    {project}")
    print(f"index.json: {len(actual)} entries\n")

    if failures:
        print("FAILURES:")
        for line in failures:
            print(line)
        print()

    if flag_warnings:
        print("WARNINGS (entry present but expected style flag missing):")
        for line in flag_warnings:
            print(line)
        print()

    print("PER-STYLE FILES:")
    for bucket, found, _missing, note in bucket_results:
        if note:
            print(f"  index-{bucket}.md: {note}")
        else:
            print(f"  index-{bucket}.md: {len(found)} entries")
    print()

    if extras:
        print(f"INFORMATIONAL — {len(extras)} extra entries (not in the "
              f"appendix; may be legitimate names the indexer found):")
        for e in extras:
            flag_set = actual[e]
            label = " [" + ",".join(sorted(flag_set)) + "]" if flag_set else ""
            print(f"  - {e}{label}")
        print()

    total_required = len(EXPECTED) + len(FORBIDDEN)
    print("--- summary ---")
    print(f"  required checks: {total_required}")
    print(f"  passed:          {passed}")
    print(f"  failed:          {failed}")
    print(f"  warnings:        {warnings}")
    print(f"  extras:          {len(extras)}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
