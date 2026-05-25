# PDF Indexer Help

## Getting Started

1. **Create or open a project** via the File menu.
2. **Import a PDF** into the project.
3. **Add keywords** in the Keywords panel (one per line), or select text in the PDF viewer and right-click to add as keywords. Double-click individual words to add them immediately.
4. **Click "Create Index"** to search the PDF and generate the index.
5. **Browse the Active Index** — click any page number to jump to that page in the PDF with the term highlighted in orange.
6. **Enable Name Indexing** to automatically discover proper nouns without manually adding them as keywords. Add false positives to the Exclude List.
7. **Use the Tag Cloud** to discover frequent terms and click them to toggle keywords, then re-index.

---

## Keyword Indexing

Define keywords in the Keywords panel (one per line). The entire PDF is searched for each keyword using whole-word, case-insensitive matching. Consecutive pages are collapsed into ranges (e.g. "5–8").

**Capitalize Entries** — optionally capitalise the first letter of each keyword index entry.

**Index Italic** — capture italic phrases as separate index entries, even when they are not capitalised (e.g., italic book titles or foreign-language phrases). Default on.

**Index Bold Text** — capture bold phrases as separate index entries (parallel to italic capture). Bold-styled words also bypass the sentence-initial filter for capitalised n-grams. Default off.

**Index Single Quotes** — capture phrases enclosed in matched single curly quotes (`‘…’`) as separate index entries. The opening curly `‘` starts a run; the closing curly `’` ends it. Apostrophes inside individual word tokens (e.g. `Pemberton’s`, `O’Donnell`) do NOT close the run because the rule only fires when `’` appears as a standalone punctuation token between word tokens. Default on.

**Max chars caps (Italic / Bold / Single Quotes)** — each of the three style rules above has a configurable character ceiling, default 100, shown as a *Max chars* spinbox indented under the style's checkbox. The ceiling applies to the **entire continuous run** of that style: a continuous italic span, a continuous bold span, or the text enclosed by a matched pair of `‘ … ’`. When the joined length of the words in a single run exceeds the cap, that *whole* run is treated as if the style rule did not apply — no fragments are kept, and the underlying tokens are still processed by the other extractors (capitalised name detection in particular). This stops multi-line italic blockquotes, long bold prose paragraphs, and decorative quote enclosures around schedules or lists from polluting the index, while letting short stylistic emphases through. Set the cap to `0` to disable it entirely for that style.

**Separate index files by style** — when on, generates `index-italic`, `index-bold`, `index-caps`, `index-single-quotes`, and `index-other` files alongside the aggregate `index` files. Each per-style file lists only entries (and only the page numbers) that matched that style. The aggregate `index.json` carries every flag and is the source of truth — the per-style markdown/text/html files are derived from it on each save. A radio bar above the index output (`Aggregate | Italic | Bold | Caps | Single Quotes | Other`) lets you view any single bucket in the Active / Markdown / Text / HTML tabs; reports, the merge tool, and the tag cloud always operate on the aggregate.

**Aggregate index with rule indicators** — `index-rules.txt` is written alongside the other format files. It lists every entry with the rules that produced it tagged in square brackets after the term: `Beatrice Halloway [capitals] 1, 2`, `Piano [italic] 3`, `A New Method [single-quotes] 2`, `Edmund Crawley [bold] [capitals] 1, 2, 3`. The rule names are *italic*, *bold*, *single-quotes*, and *capitals*; an entry gets *capitals* if any of its occurrences was a plain capitalised n-gram or an all-caps acronym (NATO-style).

**Index front matter (roman)** — when offset is negative and *Index only from offset* is on, this option also indexes the front-matter pages (1 .. offset) using lowercase roman numerals (i, ii, iii, ...). The PDF's own page label is used when it is itself roman; otherwise the physical page number is converted. Default on.

---

## Name Indexing

Name Indexing automatically discovers proper nouns — people, places, organisations, and titles — without you having to list them manually. It runs as two passes over the PDF.

### Pass 1 — Discovery

Every page is scanned in discovery mode:

- A word is a **name candidate** if its first character is uppercase.
- **Sentence-initial words are skipped** in pass 1 unless they are italic (or bold, when *Index Bold Text* is on). This prevents sentence-starting capitals like "The" or "After" from polluting the index. Only names confirmed by a mid-sentence appearance enter the vocabulary.
- The result is a vocabulary of candidate names to search for in pass 2.

### Pass 2 — Indexing

Every page is scanned for all occurrences of vocabulary names, **including at the start of sentences**. Each name is recorded against every page where it appears.

### Term boundary rules

The following rules govern how word sequences are assembled into candidate names during both passes:

| Rule | Effect |
|---|---|
| **Possessive suffix** | Stripped before classification: "Gorb's" → "Gorb". |
| **Title prefixes** | *Dr, Mr, Mrs, Ms, Prof, Rev, St, Sir, Dame, Lord, Lady, Hon, Sr, Jr* — skipped but do **not** break the sequence. "Dr John Smith" yields "John Smith". |
| **Connector words** | *and, of, to, from, in, by, …* normally break the sequence. **Exception:** an italic connector inside an entirely italic sequence is kept, so "The Sound of Music" or "War and Peace" (set in italics) is captured as one term. |
| **Italic phrases** | Independent of the capitalisation rules: a contiguous run of italic-styled tokens is captured as an index entry, with connectors kept ("The Sound of Music"). Punctuation or a non-italic word ends the run. Each captured entry is tagged with the *italic* style. |
| **Bold phrases** | Same idea as italic capture: when *Index Bold Text* is on, contiguous runs of bold-styled tokens are captured as their own entries (e.g. a bold annotation like `**A note on proximity**` becomes its own entry). |
| **Single-quote phrases** | When *Index Single Quotes* is on, text enclosed in matched single curly quotes (`‘…’`) is captured as its own entry, tagged with the *single-quotes* style. Apostrophes inside word tokens (`Pemberton’s`, `O’Donnell`) do not close the run — the rule only fires on a standalone curly `’` between word tokens. |
| **Style break** | When a token's italic status differs from the rest of the current sequence, the sequence is flushed and a new one begins. For example, if "Adam Gorb's" is in plain text and "Absinthe" is in italics, the result is two separate entries: "Adam Gorb" and "Absinthe". |
| **All-caps words** | Single all-caps tokens like *NATO* and *CERN* on a mixed-case line are admitted as name candidates and tagged with the *caps* style. Tokens on a fully all-caps line (*INTRODUCTION*, *CHAPTER 3*) are skipped — those are headings. |
| **Structural words** | *Chapter, Section, Figure, Table, Introduction, Conclusion, Appendix, Index, Note, References, Bibliography, …* always break the sequence. |
| **Roman numerals** | Always break the sequence. |
| **Superscript footnote markers** | Digit-only or symbol tokens (†, ‡, §, ¶, *) in superscript spans are skipped without breaking the sequence. Real words that happen to appear in a superscript span are kept. |
| **Stop words** | Can **extend** an existing sequence (e.g. "The Guardian", "Council of Europe") but cannot **start** one. |
| **Exclude words** | Cannot start a sequence. If encountered mid-sequence with an uppercase first letter they extend it; standalone excluded entries are removed from the final index. |
| **Lowercase words** | Non-connector, non-stop, non-excluded lowercase words break the sequence. |

### Name Indexing options

- **Index Bold Text** — bold-styled words bypass the sentence-initial filter in pass 1, just as italic words do. Useful when the PDF uses bold for names rather than italics.
- **Surname First** — when enabled, two-word names classified as person names are inverted for display: "John Smith" → "Smith, John". Classification priority is: user override (via right-click) → spaCy NER (if installed) → word-pattern heuristic. Names containing geographic or organisational words are classified as place/thing and kept in natural order. Single-word names and names of three or more words are never inverted.

### Substring-duplicate suppression

After the keyword and name indexes have been merged, an entry whose words form a contiguous sub-sequence of one or more longer entries (case-insensitive) is dropped if every page it appears on is also covered by those longer entries. This catches:

- Greedy-match leftovers — `Fisher` and `Norma Fisher` both ending up with the same page list because the surname was matched both alone and inside the full name.
- Partial captures — `Chopin Sonata in B-flat` and `Chopin Sonata in B-flat minor` both showing on the same page when the partial form was admitted at one occurrence and the longer form at another.
- Inverted forms — `Halloway` whose pages are all covered by `Halloway, Beatrice`.

Entries with at least one page **not** covered by any longer match are kept intact. So `Manchester` on pages 1 and 3 alongside `Manchester Free Trade Hall` only on page 3 stays in the index because page 1 has no covering compound.

### Managing the index

- **Exclude List** — add words here to prevent them from appearing as standalone index entries. Right-click any entry in the Active Index and choose *Exclude* to add it instantly.
- **Stop Words** — customisable list of common English words filtered from name indexing results. Extend this for domain-specific words that should never start a name entry.
- **Merge** — right-click any index entry and choose *Merge into…* to combine it with another entry. Use this to consolidate name variants (e.g. "Smith" into "John Smith").
- **Mark as person / place/thing** — right-click an entry to override automatic classification and control whether a two-word name is inverted (Surname First mode only).

---

## Output Formats

Index files are automatically saved in the project folder when generated.

- **Active** — interactive HTML with clickable page numbers that jump to the page in the PDF viewer and highlight the term in orange. Default view.
- **Markdown** — standard Markdown formatted index.
- **Text** — plain text output.
- **HTML** — formatted HTML index.
- **Tag Cloud** — visual word cloud of the PDF text. Existing keywords are highlighted. Click a word to add or remove it as a keyword.
- **Merge** — tool for combining index entries.
- **Reports** — nine index quality reports: similar terms, overlapping entries, capitalisation variants, and more. See the Reports section below.
- **View Source** — toggle to see the raw markup of any text-based output format.
- **Filter bar** — type to filter the displayed index entries; shows a filtered/total count.
- **Style selector** — `Aggregate | Italic | Bold | Caps | Single Quotes | Other` radio bar above the index output (visible when *Separate index files by style* is on). Filters the displayed entries to those that have at least one occurrence in the selected style; page numbers within the filtered entries also restrict to that style.

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

---

## Reports

The Reports tab generates nine different analyses of your index to help identify quality issues, consistency problems, and potential improvements. Use these reports to spot typos, discover name variants, find under- or over-indexed terms, and consolidate entries more effectively.

### Using Reports

- **Run All Reports** — click the button to generate all reports at once (execution time depends on index size).
- **Individual Re-run** — each report has a ↺ button to re-run just that report without regenerating the others.
- **Thin and Dense thresholds** — two spinboxes let you adjust the page count cutoffs: *Thin* (default 1 page) identifies low-frequency entries, and *Dense* (default 20 pages) identifies high-frequency entries.
- **Click-to-Navigate** — click any page reference in a report to navigate the PDF to that page and highlight the term in orange.
- **Page References** — show both the logical page label (as defined in the PDF metadata) and the physical PDF page number when they differ (e.g. "iv (PDF p.4)").

### The 9 Reports

**Similar Terms** — entries with an edit distance of ≤ 3 operations. Highlights potential typos or spelling variants; useful when combined with the Merge tab to consolidate near-duplicates.

**Overlapping Terms** — entries where one term's words are a subset of another's (e.g. "Smith" and "Smith, John"). Complements the Merge tab; helps you decide whether to keep both entries or consolidate them.

**Capitalisation Variants** — entries that differ only in capitalisation (e.g. "new york" and "New York"). Typically these should be merged or standardised to one form.

**Formatting Variants** — entries with the same words but in different order, or differing only in hyphenation or spacing. Indicates inconsistent data entry or PDF extraction issues that may warrant consolidation.

**Unused Include Terms** — keywords from your include list that produced no index entries. Usually indicates a typo in your keyword list, but may also mean the term genuinely doesn't appear in the PDF.

**Thin Entries** — entries appearing on a small number of pages (configurable via the *Thin* threshold, default 1). Low-frequency entries may not warrant an index entry and could be removed to keep the index focused.

**Dense Entries** — entries appearing on many pages (configurable via the *Dense* threshold, default 20). High-frequency entries may benefit from creating sub-entries to provide more granular indexing.

**Shared Page Sets** — pairs of entries appearing on nearly identical page sets (≥ 80% overlap). Indicates the entries may refer to the same concept under different names and could be merged. *Note: this report is skipped automatically when the index has more than 2000 entries.*

**Acronym / Expansion Pairs** — all-caps terms (e.g. "BBC") that may be acronyms for longer entries (e.g. "British Broadcasting Corporation"). Useful for discovering whether acronyms and their expansions should be merged or cross-referenced.

---

## PDF Viewer

- **Fit-Width Rendering** — pages automatically scale to fill the viewer width. Responds to window resizing.
- **Page Navigation** — Previous/Next buttons, page slider, and a Go To page field. Scrolling past the top or bottom of a page automatically advances to the adjacent page.
- **Term Highlighting** — all indexed terms on the current page are highlighted in yellow. Clicking a page number in the Active Index highlights the specific term in orange.
- **Click-to-Lookup** — click any highlighted word in the PDF to scroll the index output to that term and highlight it.
- **Add Keywords from PDF** — double-click a word or select a phrase and right-click to add it as a keyword.
- **Resizable Panes** — drag the splitter bars to adjust the width of the PDF viewer and side panels.

---

## Workspace

- **Project Management** — organise work into project folders. Each project stores its PDF, keywords, exclude list, stop words, configuration, and generated output files. The last project is automatically reopened on launch.
- **Collapsible Panels** — the Keywords, Exclude List, and Stop Words editors are collapsible. A maximum of two panels can be open at once; opening a third automatically closes the oldest.
- **Page Numbering** — supports *Logical Label* (page labels as defined in the PDF metadata) or *Physical Page* numbering with an optional offset for front matter. When a negative offset is set, *Index only from offset* restricts indexing to pages from the logical page 1 onwards, skipping unnumbered front matter.
- **Autosave** — keywords, exclude list, stop words, and all settings are saved automatically as you type.
