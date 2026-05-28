"""Reconcile fubar1.csv index entries against index.txt.

Each CSV entry has page numbers that are +20 relative to index.txt.
For each row: subtract 20 from arabic pages, lookup against index, and
append a final column with "matched" / "unmatched".
"""
import csv
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1] / "Data" / "Schools In PREPUB V03"
INDEX_PATH = PROJECT / "index.txt"
# Output filename derived from the input: fubar1.csv -> unfubar1.csv,
# fubar2.csv -> unfubar2.csv, etc. Override either path on the command
# line: `python scripts/unfubar.py <input.csv> <output.csv>`.
INPUT_CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "fubar1.csv"
if len(sys.argv) > 2:
    OUTPUT_CSV = Path(sys.argv[2])
else:
    OUTPUT_CSV = INPUT_CSV.parent / (
        INPUT_CSV.name.replace("fubar", "unfubar", 1)
        if "fubar" in INPUT_CSV.name and not INPUT_CSV.name.startswith("unfubar")
        else INPUT_CSV.stem + ".unfubar.csv"
    )
DELTA = -20

ARABIC_RANGE = re.compile(r"^\d+-\d+$")
ARABIC_PAGE = re.compile(r"^\d+$")
# Page-list tail: a comma-separated run of page tokens at the end of the
# entry. Requiring the comma between tokens avoids consuming name words
# that happen to look like single roman numerals (e.g. "Friday a m 325-326"
# — 'm' is part of the name, not roman 1000; "Kenneth Weir c 407" — 'c'
# is part of the name).
_PAGE_TOKEN = r"(?:[ivxlcdm]+|\d+(?:-\d+)?)"
PAGES_TAIL = re.compile(r" (" + _PAGE_TOKEN + r"(?:,\s+" + _PAGE_TOKEN + r")*)$")


def split_entry(entry: str):
    """Split 'Name a, b-c, d' into ('Name', 'a, b-c, d').

    The page list is whatever trailing run matches PAGES_TAIL — a
    comma-separated sequence of arabic pages, arabic ranges, and
    lowercase-roman tokens. Anything before is the name.
    """
    m = PAGES_TAIL.search(entry)
    if not m:
        return entry, ""
    return entry[: m.start()], m.group(1)


def shift_pages(pages_str: str, delta: int = DELTA) -> str:
    if not pages_str:
        return pages_str
    items = [item.strip() for item in pages_str.split(",")]
    out = []
    for item in items:
        if ARABIC_RANGE.match(item):
            a, b = item.split("-")
            out.append(f"{int(a) + delta}-{int(b) + delta}")
        elif ARABIC_PAGE.match(item):
            out.append(str(int(item) + delta))
        else:
            out.append(item)
    return ", ".join(out)


def load_index(path: Path) -> set[str]:
    entries: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("Index ("):
                continue
            entries.add(s)
    return entries


def load_index_entries(path: Path) -> list[str]:
    """Return index.txt entries in their original (alphabetical) order."""
    entries: list[str] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("Index ("):
                continue
            entries.append(s)
    return entries


def main() -> int:
    # ------------------------------------------------------------------
    # 1) Read the fubar CSV: index it by the term (name) part of each
    #    row so we can look the user's category up by name when
    #    emitting the new index. Also remember the page-shifted form so
    #    we can tell "matched exactly" from "same entry but pages
    #    changed".
    # ------------------------------------------------------------------
    fubar_by_name: dict[str, dict] = {}
    fubar_header: list[str] = []
    with INPUT_CSV.open(encoding="utf-8", newline="") as fin:
        reader = csv.reader(fin)
        fubar_header = next(reader)
        for row in reader:
            entry = row[1] if len(row) >= 2 else ""
            if not entry:
                continue
            name, pages = split_entry(entry)
            shifted_entry = (
                f"{name} {shift_pages(pages)}".strip() if pages else name.strip()
            )
            key = name.strip().casefold()
            if not key:
                continue
            # If the same name appears twice in fubar, prefer the first
            # occurrence (alphabetical order keeps that stable).
            fubar_by_name.setdefault(key, {
                "category": row[0] if len(row) >= 1 else "",
                "row": list(row),
                "shifted_entry": shifted_entry,
            })

    # ------------------------------------------------------------------
    # 2) Walk the new index in order and emit one row per entry,
    #    preserving the user's category from fubar by name match.
    # ------------------------------------------------------------------
    index_entries = load_index_entries(INDEX_PATH)
    fubar_keys_used: set[str] = set()
    counts = {"matched": 0, "updated": 0, "new": 0}

    # Pad header to 3 columns (category, entry, trailing) like fubar1
    # and append a status column. In side-by-side mode the trailing
    # column holds the original fubar entry text.
    padded_header = list(fubar_header)
    while len(padded_header) < 3:
        padded_header.append("")
    if OUTPUT_CSV.name.endswith("+.csv"):
        padded_header[2] = "fubar entry"
    out_header = padded_header + ["status"]

    # Side-by-side mode: when the output filename ends in "+.csv",
    # column 3 holds the fubar row's entry text (after -20 page shift)
    # so the user can see the index entry next to their original
    # categorised version. Without +, column 3 is left blank to match
    # the existing fubar1 layout.
    side_by_side = OUTPUT_CSV.name.endswith("+.csv")

    rows_out: list[list[str]] = []
    for entry in index_entries:
        name, _pages = split_entry(entry)
        key = name.strip().casefold()
        fubar = fubar_by_name.get(key)
        if fubar is None:
            category = ""
            fubar_entry_text = ""
            status = "new"
        else:
            fubar_keys_used.add(key)
            category = fubar["category"]
            fubar_entry_text = fubar["shifted_entry"]
            if fubar["shifted_entry"] == entry:
                status = "matched"
            else:
                status = "updated"
        counts[status] += 1
        col3 = fubar_entry_text if side_by_side else ""
        rows_out.append([category, entry, col3, status])

    # ------------------------------------------------------------------
    # 3) Append any fubar rows whose name is NOT in the new index —
    #    these are user edits or entries dropped by the indexer. Mark
    #    them so the user can review them separately rather than
    #    silently dropping them.
    # ------------------------------------------------------------------
    orphans = []
    for key, fubar in fubar_by_name.items():
        if key in fubar_keys_used:
            continue
        original_row = fubar["row"]
        category = original_row[0] if len(original_row) >= 1 else ""
        if side_by_side:
            # No new-index entry; fubar text goes in column 3 and the
            # index column is left blank so the user can scan the gaps.
            orphans.append([category, "", fubar["shifted_entry"], "orphan_from_fubar"])
        else:
            # Without side-by-side: corrects pages in the index column.
            orphans.append([category, fubar["shifted_entry"], "", "orphan_from_fubar"])
    orphans.sort(key=lambda r: (r[1].casefold(), r[2].casefold()))

    # ------------------------------------------------------------------
    # 4) Write
    # ------------------------------------------------------------------
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(out_header)
        for r in rows_out:
            writer.writerow(r)
        for r in orphans:
            writer.writerow(r)

    print(f"Wrote {OUTPUT_CSV}")
    print(f"  Index entries:        {len(index_entries)}")
    print(f"    matched (exact):    {counts['matched']}")
    print(f"    updated (pages or text changed): {counts['updated']}")
    print(f"    new (no fubar row): {counts['new']}")
    print(f"  Orphan fubar rows:    {len(orphans)}")
    print(f"  Total rows in output: {len(rows_out) + len(orphans)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
