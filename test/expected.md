# The Indexer's Apprentice

*A short test corpus for the pdf-index program.*
*The story body is the input; the appendix is the expected index.*

---

## INTRODUCTION

In the spring of 1987 Beatrice Halloway accepted a fellowship at Cambridge to work on a peculiar problem: how to teach a machine to build the index of a book. Her mentor, Dr Edmund Crawley, had spent thirty years cataloguing musicology archives at the Royal Conservatory and was sceptical that any program could replace a careful human reader. "Indexing is taste," he liked to say, "not arithmetic." Beatrice disagreed, but politely.

Her first subject was a thin volume of essays by Alistair Pemberton, the Manchester historian, called *Echoes of the Bridgewater Hall*. The book ran to three hundred pages and dealt mostly with twentieth-century chamber music in the north of England. Pemberton's prose was dense, his footnotes copious, and his refusal to use indexes himself almost a point of pride. "Pemberton would say," Edmund warned her, "that an index is a confession of failure on the part of the writer."

She set the book on her desk and began.

## CHAPTER ONE: A FIRST PASS

The indexer Beatrice had written — she called it Cygnus, after the constellation — read each page in two passes. The first pass was suspicious. It treated every capitalised word at the start of a sentence as guilty until proven innocent. *The Guardian* might be a newspaper or it might just be the first word of a paragraph; only when Cygnus saw "the Guardian" appearing in the middle of a sentence elsewhere would it admit "Guardian" as a real entry. Edmund found this charmingly paranoid.

The second pass was generous. Once a name had been confirmed in the vocabulary, Cygnus tracked every occurrence on every page, even at the start of sentences. So a place like the Bridgewater
Hall, if it had been seen mid-sentence as a contiguous capitalised pair, would be recorded faithfully on page after page; and if the typesetter had cut a name like Bridge-
water into two halves with a hyphen at the line break, Cygnus stitched it silently back together.

Connector words gave Cygnus its first real test. In ordinary prose, a phrase like "Crawley and Halloway" would not be one entry; the *and* would break the sequence and force two separate names. But Pemberton had a habit, common to musicologists, of typing the names of works in italics. *The Sound of Music* and *War and Peace* were not to be split at every connector. Cygnus had a rule: an italic connector inside an italic n-gram extended the run; a plain connector broke it.

She tested the rule on a footnote.<sup>3</sup> Pemberton, true to form, had buried the most interesting bit on page xiv of the front matter, in a note that read: "See also *in vino veritas*, the Latin proverb cited by Bertrand on the eve of the BBC broadcast." Cygnus picked out *in vino veritas* as an italic phrase even though no word was capitalised. The footnote marker — the tiny superscript digit after "footnote" — was correctly skipped, since digit-only superscript tokens were not real words.

## CHAPTER TWO: ACRONYMS AND TITLES

It was Dr Margaret O'Donnell, visiting from CERN that week, who suggested Beatrice add acronyms to the test. "You need NATO and CERN and the BBC in there. Run-of-the-mill all-caps. Single tokens, mid-sentence." Beatrice obliged. Cygnus admitted them under a careful rule: a single all-caps token sitting on a mixed-case line was a name candidate; an entire line set in capitals — like the heading INTRODUCTION at the top of a chapter — was a heading and was discarded.

Title prefixes posed a different problem. The book was full of *Dr Edmund Crawley* and *Mrs Beatrice Halloway* and even a stray *Sir Thomas Beecham*. Cygnus dropped the prefixes ("Dr", "Mr", "Mrs", "Prof", "Sir") so the indexer would treat *Dr Crawley* and *Crawley* as the same entity. Possessive suffixes were trimmed too: Crawley's notes became Crawley.

"What about the stop list?" Margaret asked. Beatrice explained: certain words were forbidden from starting a name on their own — *the*, *a*, *every*, *some* — but were permitted to extend a name already in progress. So *The Guardian* worked, because *The* could extend the existing name once *Guardian* had been seen mid-sentence. *The* alone could not start one.

Margaret laughed. "It's all very Anglican."

## CHAPTER THREE: PLACES AND TECHNIQUES

By the third week Beatrice had run Cygnus on a longer piece: a draft chapter Pemberton had sent her for review, called "Northern Modernists at the BBC, 1950–1970". The chapter mentioned the Bridgewater Hall, the Royal Northern College, and the Manchester Free Trade Hall. It mentioned Adam Gorb and John McCabe and Anthony Burgess (yes, the novelist, who composed). It cited works in italics: *Absinthe*, *Cloudcatcher Fells*, *A Clockwork Orange*, *Concerto for Orchestra*. It cited a French technique, *col legno*, and a dance, *the polonaise*, both of which Pemberton typed in italics.

Cygnus produced an index. Beatrice read down the page slowly, looking for mistakes. There was *Absinthe*, set off in italics in the index just as in the book; there was Bridgewater Hall, recovered correctly even though the line break in chapter one had cut it in two; there was Edmund Crawley listed in natural order (Cygnus's surname-first option had been left off for this run); and there was a separate entry for *Crawley* alone, where Cygnus had noticed the surname unattached to a first name.

"Look here," she pointed. "It split *Halle Orchestra* and *Halle Choir* into two entries, but the standalone *Halle* — which you used twice as shorthand — has been quietly suppressed because every page where Halle appears alone is also a page where Halle Orchestra or Halle Choir appears. Cygnus refused to print a redundant entry."

Edmund peered at the printout. "That's the part I would have done by hand," he admitted. "You've spared me an afternoon."

## CONCLUSION

In the spring of 1989 Beatrice published her dissertation, titled *Cygnus: A Style-Aware Indexer for Long-Form Scholarly Prose*. The book was indexed by Cygnus itself, of course — a small joke at the end. The Royal Conservatory adopted the program for their archive. Pemberton, characteristically, refused to use it.

But that, as Edmund observed, was Pemberton's affair.

---

# Appendix: Expected Index

This appendix lists the entries Cygnus should produce when the story above is fed to the indexer with default settings (Name Indexing on, Index Italic on, Index Bold off, Capitalize Entries off, Surname First off, Separate index files by style on, Index front matter (roman) on if a negative offset is set). Page numbers will vary with PDF rendering; the table groups entries by the rule each one exercises.

## Aggregate index — entries (sorted, case-insensitive)

| Entry | Style flags | Rule it tests |
|---|---|---|
| *A Clockwork Orange* | italic | Italic phrase capture; connector *A* extends italic n-gram |
| *Absinthe* | italic | Italic phrase capture (single italic word) |
| Adam Gorb | — | Plain capitalised n-gram |
| Alistair Pemberton | — | Plain capitalised n-gram |
| Anthony Burgess | — | Plain capitalised n-gram |
| BBC | caps | Single all-caps token on mixed-case line |
| Beatrice Halloway | — | Plain capitalised n-gram |
| Bertrand | — | Single capitalised name mid-sentence |
| Bridgewater Hall | — | Cross-line capitalised pair (also tested as the hyphenated "Bridge-water" form, which should be reconstructed) |
| Cambridge | — | Plain place name |
| CERN | caps | Single all-caps token on mixed-case line |
| *Cloudcatcher Fells* | italic | Italic phrase capture |
| *col legno* | italic | Lowercase italic phrase (no capitalisation) |
| *Concerto for Orchestra* | italic | Italic phrase; connector *for* extends italic run |
| *Cygnus: A Style-Aware Indexer for Long-Form Scholarly Prose* | italic | Italic title; connectors *for* extend italic run; punctuation inside the title note: capture stops at the colon |
| Cygnus | — | Repeated name from main prose (program name) |
| Echoes of the Bridgewater Hall | italic | Italic title; *of* and *the* extend italic run |
| Edmund Crawley | — | Plain capitalised n-gram (also tested with the *Dr* prefix dropped, e.g., "Dr Edmund Crawley" → Edmund Crawley) |
| Halle Choir | — | Capitalised pair |
| Halle Orchestra | — | Capitalised pair |
| *in vino veritas* | italic | Lowercase italic phrase (no capitalisation) |
| John McCabe | — | Plain capitalised n-gram |
| Manchester | — | Single capitalised place mid-sentence |
| Manchester Free Trade Hall | — | Multi-word capitalised place |
| Margaret O'Donnell | — | Plain n-gram with apostrophe (should be preserved inside the token) |
| NATO | caps | Single all-caps token on mixed-case line |
| Northern Modernists at the BBC | — | Mixed-case multi-word phrase from a quoted chapter title; *at the* extend the run if all caught between capitalised words. Actual indexer behaviour: connectors break a non-italic n-gram, so this should NOT appear as one entry. Listed here as a known break point — see "Negative cases" below |
| Pemberton | — | Surname appearing alone (after possessive *Pemberton's* trimmed) |
| *the polonaise* | italic | Lowercase italic phrase |
| Royal Conservatory | — | Capitalised place |
| Royal Northern College | — | Multi-word capitalised place |
| *The Guardian* | italic | Italic title with stop word *The* extending the n-gram (newspaper name) |
| *The Sound of Music* | italic | Italic title; connectors *of* extend italic run |
| Thomas Beecham | — | Plain n-gram (after *Sir* prefix dropped) |
| *War and Peace* | italic | Italic title; connector *and* extends italic run |

## Per-style files

When *Separate index files by style* is on, four extra files appear alongside the aggregate `index.{md,txt,html}`:

- **`index-italic.{md,txt,html}`** — every entry whose style flags include `italic`. From the table above: *A Clockwork Orange*, *Absinthe*, *Cloudcatcher Fells*, *col legno*, *Concerto for Orchestra*, *Cygnus: A Style-Aware Indexer …*, *Echoes of the Bridgewater Hall*, *in vino veritas*, *the polonaise*, *The Guardian*, *The Sound of Music*, *War and Peace*.
- **`index-caps.{md,txt,html}`** — entries whose style flags include `caps`: BBC, CERN, NATO. The headings INTRODUCTION, CHAPTER ONE, CHAPTER TWO, CHAPTER THREE, CONCLUSION must NOT appear here — those lines are entirely all-caps and are filtered as headings.
- **`index-bold.{md,txt,html}`** — empty (the corpus has no bold styling).
- **`index-other.{md,txt,html}`** — entries whose flags are all false: Adam Gorb, Alistair Pemberton, Anthony Burgess, Beatrice Halloway, Bertrand, Bridgewater Hall, Cambridge, Cygnus, Edmund Crawley, Halle Choir, Halle Orchestra, John McCabe, Manchester, Manchester Free Trade Hall, Margaret O'Donnell, Pemberton, Royal Conservatory, Royal Northern College, Thomas Beecham.

## Negative cases — what should NOT appear

These are deliberate; if any of them shows up in the output the indexer has misbehaved.

- **All-caps section headings** — INTRODUCTION, CHAPTER ONE, CHAPTER TWO, CHAPTER THREE, CONCLUSION. Whole-line all-caps is treated as a heading.
- **Sentence-initial capitals that never appear mid-sentence** — *Edmund* (the standalone first name without surname, when only used at sentence starts) does not get a vocabulary entry of its own. *Edmund Crawley* is the canonical entry.
- **Stop words alone** — *The*, *A*, *Every*, *Some*. None should appear as standalone entries. *The Guardian* is fine because *the* is extending an existing italic name.
- **Title prefixes alone** — *Dr*, *Mr*, *Mrs*, *Sir*. They are skipped without breaking the n-gram, so they never appear as entries.
- **Footnote markers** — the superscript `3` after "footnote" in chapter one. The indexer should not record `3` as an entry.
- **Possessive form** — *Pemberton's* and *Crawley's* should be normalised to *Pemberton* and *Crawley* respectively.
- **Connector-broken phrases** — "Crawley and Halloway" produces two entries (*Edmund Crawley*, *Beatrice Halloway*), not one combined entry. Likewise "Northern Modernists at the BBC" should NOT appear as a single non-italic n-gram.
- **Hyphenated line break** — *Bridge-* (with trailing hyphen) and *water* (lowercase continuation) must NOT appear as separate entries when the typesetter splits *Bridgewater* across a line break. The reconstructed form *Bridgewater* (or, in context, *Bridgewater Hall*) is the only correct entry.
- **Suppressed redundant standalone** — *Halle* on its own should not appear as a separate entry on any page where *Halle Orchestra* or *Halle Choir* already covers that page.

## How to run this test

1. Convert `test/test.md` to a PDF (e.g., via `pandoc test/test.md -o test/test.pdf`).
2. Open the project in pdf-index and import the resulting PDF.
3. Click **Create Index** with the default settings (Name Indexing on, Index Italic on, Separate index files by style on).
4. Compare the generated `index.md` against the **Aggregate index** table above; compare each per-style file against its corresponding sub-section.
5. Spot-check the **Negative cases**: confirm none of the listed phrases appears in any output file.

Some entries depend on PDF layout (notably *Bridgewater Hall* split across a line, and the deliberate hyphenated *Bridge-water* form). Different PDF renderers may wrap lines differently; if those particular cases do not exercise as intended in the rendered PDF, the rule is still validated by the other capitalised pairs in the corpus.
