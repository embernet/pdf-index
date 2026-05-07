#!/usr/bin/env python3
"""Compare a generated pdf-index output against the expected entries
documented in the appendix of test/test.md.

Usage:
    python test/check_index.py <project-directory>

Where <project-directory> is the pdf-index project folder containing the
generated index.json and (optionally) the per-style files index-italic.md,
index-bold.md, index-caps.md, index-other.md.

Exit code is 0 when all required checks pass, 1 if any FAIL is reported.
Extras (entries the indexer found that the appendix did not anticipate)
are printed as informational and do not cause a failure — proper-noun
detection legitimately picks up words beyond the curated list.
"""

import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Expected entries — keyed by entry text, value is the minimum set of style
# flags the indexer is required to record on at least one occurrence.
# ---------------------------------------------------------------------------

EXPECTED = {
    "A Clockwork Orange":              {"italic"},
    "Absinthe":                        {"italic"},
    "Adam Gorb":                       set(),
    "Alistair Pemberton":              set(),
    "Anthony Burgess":                 set(),
    "BBC":                             {"caps"},
    "Beatrice Halloway":               set(),
    "Bertrand":                        set(),
    "Bridgewater Hall":                set(),
    "Cambridge":                       set(),
    "CERN":                            {"caps"},
    "Cloudcatcher Fells":              {"italic"},
    "col legno":                       {"italic"},
    "Concerto for Orchestra":          {"italic"},
    "Cygnus":                          set(),
    "Echoes of the Bridgewater Hall":  {"italic"},
    "Edmund Crawley":                  set(),
    "Halle Choir":                     set(),
    "Halle Orchestra":                 set(),
    "in vino veritas":                 {"italic"},
    "John McCabe":                     set(),
    "Manchester":                      set(),
    "Manchester Free Trade Hall":      set(),
    "Margaret O'Donnell":              set(),
    "NATO":                            {"caps"},
    "Pemberton":                       set(),
    "Royal Conservatory":              set(),
    "Royal Northern College":          set(),
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

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\*:', re.MULTILINE)


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

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    project = Path(sys.argv[1]).expanduser().resolve()
    index_path = project / "index.json"
    if not index_path.exists():
        print(f"error: {index_path} not found")
        print("Has the indexer been run on this project?")
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

    # 4. Bold file must be empty (no bold styling in the corpus).
    bold_path = project / "index-bold.md"
    if bold_path.exists():
        bold_entries = parse_md_entries(bold_path)
        if bold_entries:
            failures.append(
                f"  index-bold.md should be empty but contains: "
                f"{sorted(bold_entries, key=str.lower)}"
            )
            failed += 1
        else:
            passed += 1

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
