# Style-Aware Indexing — Design

Date: 2026-05-06

## Goals

Six related changes to the PDF indexer, all centred on capturing more context (style and page coverage) for each indexed entry and exposing that context in the UI and on disk:

1. Index italic phrases (regardless of capitalisation), default on.
2. Fix the line-break heuristic so that contiguous-capitalised phrases that wrap across a line are no longer split.
3. Reconstruct hyphenated split words (`Bridge-\nwater Hall` → `Bridgewater Hall`).
4. Optionally index front-matter (pre-offset) pages using roman numerals, default on.
5. Tag every indexed occurrence with its style (italic / bold / all-caps / none) and write per-style index files alongside the aggregate, default on.
6. Add a style selector (Aggregate / Italic / Bold / Caps / Other) that scopes the displayed index in the Active / Markdown / Text / HTML tabs.

These changes apply to both the keyword indexer and the name indexer so the buckets are consistent across all entries.

## Non-goals

- No change to the merge tool, reports, or tag-cloud behaviour. They continue to work off the aggregate raw results regardless of style selection.
- No new persistent JSON files per style — the aggregate `index.json` carries all flags; per-style markdown/text/html files are derived from it on each save.
- No promotion of bold-only-lowercase or caps-only-lowercase tokens to name candidates beyond what the existing rules already do. The new italic capture is the only path that promotes lowercase styled text.

## Data model

`raw_results` (in-memory and on disk in `index.json`) changes from:

```python
{ entry: [(page_idx, page_label), ...] }
```

to:

```python
{ entry: [(page_idx, page_label, style_flags), ...] }
```

where `style_flags` is a dict with three boolean fields: `italic`, `bold`, `caps`. An entry whose flags are all `False` falls into the "other" bucket.

JSON serialisation: tuples become 3-element arrays, with the third element being `{"italic": bool, "bold": bool, "caps": bool}`. Loading must tolerate the legacy 2-tuple shape (treat missing flags as all-false).

A single occurrence can carry multiple flags (e.g., italic + caps); it then appears in each matching per-style bucket and once in the aggregate.

## Tokenizer changes (`extract_styled_tokens`)

Three changes:

1. **Lexical override at line and block boundaries.** Before inserting the synthetic `"."` separator that the column-width heuristic currently produces, peek at the last non-punctuation token added and the first word of the next line. If both are capitalised (Unicode-aware) and there is no real punctuation between them, suppress the separator. The heuristic remains in place for short lines that follow lowercase or punctuation.
2. **Hyphenation join.** When a line's last word ends with `-` AND the first word of the next line starts with a lowercase letter, fuse the two tokens: drop the trailing `-`, concatenate, and emit a single `StyledToken` whose styling inherits from the first half. The fused token replaces the two halves; no separator is inserted between them.
3. **All-caps surfacing.** `StyledToken` gets a new field `is_all_caps: bool`, computed at construction time using the existing `_is_all_caps_word`. No new tokenization logic — just plumbing so downstream code can read it without re-checking the string.

The two pre-existing line/block-end break paths share the same lexical-override check via a small helper.

## Name extractor changes (`extract_names_from_tokens`)

- All-caps single tokens (`NATO`, `CERN`) are admitted as name candidates instead of being unconditionally skipped. The existing line-level `_get_all_caps_line_indices` still suppresses entire all-caps lines (`INTRODUCTION`, `CHAPTER 3`) so headings do not pollute the index. Implementation: pass `all_caps_line_set` into the extractor and skip tokens whose source line is fully all-caps; admit all-caps tokens otherwise. The `is_all_caps` flag is propagated to the n-gram so the eventual occurrence record carries it.
- Italic n-gram capture (new). After the main capitalised-word pass, a second walk over the same tokens collects runs of italic-styled tokens (any case), broken by punctuation or by the italic flag turning off. Connector words (`of`, `and`, `the`, ...) do **not** break italic runs — italic typically marks titles, which legitimately contain connectors (e.g., *The Sound of Music*). Structural words (`Chapter`, `Section`, ...) still break the run since they only appear in italic by accident. Each run produces an entry tagged `italic=True`. Possessive-stripping and `clean_name` apply as in the main pass. Roman numerals, footnote refs, and pure-number tokens are skipped as before.
- N-gram results carry style flags. Each captured n-gram returns not just its text but the OR of styling flags across its constituent tokens. The threading layer uses these flags when building occurrence tuples.

## Keyword indexer changes (`IndexingThread`)

The keyword indexer is rewritten to operate on the styled-token stream instead of `page.get_text("text")`:

- Build the page's token list via `extract_styled_tokens` (same call the name indexer makes).
- Reconstruct the page's plain text by joining token texts with a single space, while keeping a parallel `(start_offset, end_offset, token_index)` mapping.
- Run the existing `\b<keyword>\b` regex (case-insensitive) against the reconstructed text.
- For each match, find the tokens whose offsets overlap the match span and OR their style flags. Record an occurrence `(page_idx, page_label, flags)`.
- The "first match per page only" rule is preserved.

This means a keyword like `piano` found inside an italic span on page 12 lands in the italic bucket; found in plain text on page 5 it lands in "other". Roman/hyphen/lexical-override changes apply automatically because they live in the tokenizer.

## Front-matter (roman) indexing

- New checkbox in `controls_output.py`: **"Index front matter (roman)"**, placed next to "Index only from offset". Default ON. Enabled only when offset is negative and "Index only from offset" is on; otherwise hidden/disabled.
- When enabled, the indexers run a first pass over pages `[0, abs(offset))` before the main pass. The page-label producer for the front-matter pass is:
  1. Call `page.get_label()`.
  2. If the result is non-empty and looks like a roman numeral (`^[ivxlcdm]+$`, case-insensitive), use it.
  3. Otherwise, generate a lowercase roman numeral from the physical page number (1-based).
- Both indexers (keyword and name) accept a list of page-index ranges plus a per-range label-strategy callback so we don't duplicate looping logic.
- Range compression in `process_results` is keyed on physical page index so roman and arabic numbers in the same entry stay in document order: e.g., `iv, vi, 12, 14-16`. Adjacent-page detection still works across the boundary (e.g., physical page 12 follows physical page 11), but the printed labels stay in their respective numbering schemes.

## File output (`save_results_to_files`)

When `separate_style_files` is on:

- Always write the aggregate `index.md`, `index.txt`, `index.html`, `index.json` (the JSON now carries flags, but its contents are otherwise unchanged in structure).
- Additionally write `index-italic.{md,txt,html}`, `index-bold.{md,txt,html}`, `index-caps.{md,txt,html}`, `index-other.{md,txt,html}`. Each file shows only entries with at least one occurrence in that bucket, and only the page numbers from those occurrences.
- Empty buckets still produce a file with a header showing zero entries — keeps file presence stable so downstream scripts don't surprise on missing files.

When `separate_style_files` is off, only the aggregate files are written, and any pre-existing per-style files in the project directory are deleted (clean output).

## Style selector UI

A new horizontal radio-button bar lives directly above the index output area (in `controls_output.py`), styled like the existing cloud sub-mode bar:

```
Aggregate  Italic  Bold  Caps  Other
```

- Visible only when `separate_style_files` is on AND the current tab is `active`/`markdown`/`text`/`html`.
- Hidden for `tag_cloud`, `merge`, `reports`. Those always operate on aggregate.
- Default: Aggregate.
- Selection persists in `config.json` as `style_view`.

When a non-Aggregate option is selected, the controller filters `last_raw_results` down to the matching subset (entries with at least one occurrence whose flags include the selected style; pages within an entry are filtered to those occurrences). The filtered dict is then run through the same `process_and_display_results` path so the search filter, entry-count label, active-link-click navigation, and source-view all work unchanged.

The "Other" bucket is the set of occurrences whose flags are all false. Aggregate is the unfiltered set.

## Controls layout summary

Two new controls and one new selector. Existing layout reorganises only enough to fit them:

Row 1 (existing): `Page Strategy: Physical / Logical | Offset: [n] | [x] Index only from offset | [x] Index front matter (roman) | [x] Capitalize Entries`

Row 2 (existing options + new): `[x] Name Indexing | [x] Index Italic | [x] Index Bold Text | [x] Surname first | [x] Separate index files by style | [Create Index] | <count>`

Row 3 (output area): tab bar (unchanged), then the new style selector bar (when applicable), then search filter, then output.

## Persistence

`ConfigManager.DEFAULT_CONFIG` gains:

- `index_italic`: True
- `index_front_matter_roman`: True
- `separate_style_files`: True
- `style_view`: `"aggregate"`

`set_state` and `save_current_config` serialise/restore these alongside the existing keys.

## Backwards compatibility

- `index.json` files written by the previous version use 2-tuples. The loader normalises to 3-tuples by appending an empty flag dict, so all such occurrences land in "other". No migration required; the next index run regenerates with full flags.
- Projects that have no `index_italic` / `separate_style_files` config keys default to true on first load — same behaviour as a fresh project. Existing `name_indexing`, `bold_indexing`, etc. keys are unchanged.
- The existing `_suppress_covered_components` step in the name indexer continues to work; it only inspects entry keys, not the per-occurrence flag tuples.

## Testing notes

The repo currently has no automated tests. The features can be exercised against `data/2601.12538v1.pdf` (and any project the user has on disk):

- Italic capture: confirm an italic phrase that does not start with a capital letter (e.g., a Latin phrase or italic article title) appears in `index-italic.md` and not in `index-other.md`.
- Line-break join: confirm a phrase like "Bridgewater Hall" with a wrap between the two words is now indexed as a single entry rather than being missed.
- Hyphenation: confirm `Bridge-\nwater Hall` produces an entry `Bridgewater Hall`, not `Bridge- Hall` or two separate entries.
- Front matter: confirm an offset of `-12` with the new option on produces entries with roman page references for content in pages 1–12.
- Style selector: confirm switching to Italic shows only italic occurrences and that page navigation from those entries still works; confirm `index-italic.md` on disk matches what the UI shows.
- Mixed-style entry: confirm an entry that appears in italic on one page and plain on another shows up in both `index-italic.md` (italic page only) and `index-other.md` (plain page only), and once with combined pages in the aggregate.
