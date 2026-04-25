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
| **Style break** | When a token's italic status differs from the rest of the current sequence, the sequence is flushed and a new one begins. For example, if "Adam Gorb's" is in plain text and "Absinthe" is in italics, the result is two separate entries: "Adam Gorb" and "Absinthe". |
| **All-caps words** | *INTRODUCTION*, *CHAPTER*, etc. always break the sequence (treated as section-header text, not names). |
| **Structural words** | *Chapter, Section, Figure, Table, Introduction, Conclusion, Appendix, Index, Note, References, Bibliography, …* always break the sequence. |
| **Roman numerals** | Always break the sequence. |
| **Superscript footnote markers** | Digit-only or symbol tokens (†, ‡, §, ¶, *) in superscript spans are skipped without breaking the sequence. Real words that happen to appear in a superscript span are kept. |
| **Stop words** | Can **extend** an existing sequence (e.g. "The Guardian", "Council of Europe") but cannot **start** one. |
| **Exclude words** | Cannot start a sequence. If encountered mid-sequence with an uppercase first letter they extend it; standalone excluded entries are removed from the final index. |
| **Lowercase words** | Non-connector, non-stop, non-excluded lowercase words break the sequence. |

### Name Indexing options

- **Index Bold Text** — bold-styled words bypass the sentence-initial filter in pass 1, just as italic words do. Useful when the PDF uses bold for names rather than italics.
- **Surname First** — when enabled, two-word names classified as person names are inverted for display: "John Smith" → "Smith, John". Classification priority is: user override (via right-click) → spaCy NER (if installed) → word-pattern heuristic. Names containing geographic or organisational words are classified as place/thing and kept in natural order. Single-word names and names of three or more words are never inverted.

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
- **View Source** — toggle to see the raw markup of any text-based output format.
- **Filter bar** — type to filter the displayed index entries; shows a filtered/total count.

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
