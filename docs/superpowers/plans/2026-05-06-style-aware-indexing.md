# Style-Aware Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture italic phrases as index entries, fix line-break and hyphenation handling, optionally index front matter with roman numerals, tag every occurrence with its style, write per-style index files, and add a UI selector to view per-style subsets.

**Architecture:** Extend the per-occurrence data shape from `(page_idx, page_label)` to `(page_idx, page_label, {italic, bold, caps})`. Plumb style flags through the styled-token tokenizer, the name extractor, and the keyword indexer (which is rewritten to operate on styled tokens). Add a roman-numeral page-label producer and a front-matter indexing pass. Add a small style-filter helper that derives per-bucket views and per-bucket output files from the aggregate `raw_results`. Wire two new checkboxes and a style selector radio bar into the UI.

**Tech Stack:** Python 3.10+, PyMuPDF (fitz), PyQt6, pytest (added in this plan).

**Spec:** `docs/superpowers/specs/2026-05-06-style-aware-indexing-design.md`

---

## File Structure

**Create:**
- `tests/__init__.py` — empty marker
- `tests/conftest.py` — pytest path setup
- `tests/test_roman.py` — tests for roman numeral helper
- `tests/test_tokenizer_helpers.py` — tests for hyphenation + lexical override + caps
- `tests/test_name_extractor.py` — tests for italic capture and all-caps admission
- `tests/test_keyword_match.py` — tests for keyword styled-token matching
- `tests/test_style_filter.py` — tests for the style-bucket filter

**Modify:**
- `model/indexer.py` — rewrite `IndexingThread` to use styled tokens, propagate flags, support front-matter pass; add roman helper, style filter helper, occurrence tuple normaliser
- `model/name_indexer.py` — add `is_all_caps` to `StyledToken`, integrate hyphenation + lexical override, admit single all-caps tokens, add italic capture pass, propagate flags through n-grams
- `model/config.py` — new default keys
- `view/controls_output.py` — new checkboxes + style selector bar
- `controller/main_controller.py` — wire new options, apply style filter, write per-style files
- `HELP.md` — document new features
- `requirements.txt` — add pytest

**Add:** `pytest.ini` with `pythonpath = .` so tests can import the project modules without packaging.

---

## Task 1: Test scaffold

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Modify: `requirements.txt`

- [ ] **Step 1: Create `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 4: Add pytest to `requirements.txt`**

Append the line `pytest` to `requirements.txt`.

- [ ] **Step 5: Install pytest and verify**

Run: `pip install pytest`
Run: `pytest tests/ -v`
Expected: `no tests ran in 0.01s` (no failures, just no tests yet).

- [ ] **Step 6: Commit**

```bash
git add tests/__init__.py tests/conftest.py pytest.ini requirements.txt
git commit -m "test: add pytest scaffold"
```

---

## Task 2: Roman numeral page-label helper

**Files:**
- Modify: `model/indexer.py` (add helper near top of file, before class definition)
- Create: `tests/test_roman.py`

- [ ] **Step 1: Write the failing test**

`tests/test_roman.py`:

```python
import pytest
from model.indexer import to_lowercase_roman, looks_like_roman


def test_to_lowercase_roman_basic():
    assert to_lowercase_roman(1) == "i"
    assert to_lowercase_roman(2) == "ii"
    assert to_lowercase_roman(4) == "iv"
    assert to_lowercase_roman(9) == "ix"
    assert to_lowercase_roman(12) == "xii"
    assert to_lowercase_roman(40) == "xl"
    assert to_lowercase_roman(99) == "xcix"


def test_to_lowercase_roman_zero_or_negative():
    # Defensive: front matter is 1-indexed, but guard against bad inputs.
    assert to_lowercase_roman(0) == ""
    assert to_lowercase_roman(-1) == ""


def test_looks_like_roman_positive():
    assert looks_like_roman("iv")
    assert looks_like_roman("IV")
    assert looks_like_roman("xii")
    assert looks_like_roman("MCMLXXXIV")


def test_looks_like_roman_negative():
    assert not looks_like_roman("")
    assert not looks_like_roman("12")
    assert not looks_like_roman("iv1")
    assert not looks_like_roman("hello")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_roman.py -v`
Expected: ImportError — `to_lowercase_roman` not defined.

- [ ] **Step 3: Add helper to `model/indexer.py`**

At the top of `model/indexer.py`, after the existing imports and before `class IndexingThread`, add:

```python
_ROMAN_LOOKS_LIKE = re.compile(r'^[IVXLCDMivxlcdm]+$')


def to_lowercase_roman(n: int) -> str:
    """Convert a 1-based positive integer to lowercase roman numerals.

    Returns "" for n <= 0 (defensive guard for callers that mishandle offsets).
    Supports values up to 3999, which is well beyond any real PDF front matter.
    """
    if n <= 0:
        return ""
    pairs = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]
    out = []
    for value, symbol in pairs:
        while n >= value:
            out.append(symbol)
            n -= value
    return "".join(out)


def looks_like_roman(label: str) -> bool:
    """Return True if *label* is a non-empty string of only roman numeral letters."""
    return bool(label) and bool(_ROMAN_LOOKS_LIKE.match(label))
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_roman.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add model/indexer.py tests/test_roman.py
git commit -m "feat(indexer): add roman numeral helpers for front-matter labels"
```

---

## Task 3: Lexical override + hyphenation pure helpers

These two helpers will be used inside `extract_styled_tokens`. Pull the logic into pure functions so we can unit-test it without mocking PyMuPDF pages.

**Files:**
- Modify: `model/name_indexer.py`
- Create: `tests/test_tokenizer_helpers.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tokenizer_helpers.py`:

```python
from model.name_indexer import (
    should_suppress_break,
    try_hyphenation_join,
)


def test_suppress_break_both_capitalised():
    # Last word of previous line and first word of next line both capitalised
    # → no break, treat as continued phrase.
    assert should_suppress_break("Bridgewater", "Hall") is True


def test_suppress_break_lowercase_after():
    # Continuation looks like prose, not a phrase. Keep the break.
    assert should_suppress_break("ended", "with") is False


def test_suppress_break_lowercase_before():
    # Previous line ended in lowercase: it was prose, not a phrase ending.
    assert should_suppress_break("said", "John") is False


def test_suppress_break_empty():
    assert should_suppress_break("", "Hall") is False
    assert should_suppress_break("Hall", "") is False
    assert should_suppress_break("", "") is False


def test_hyphenation_join_lowercase_continuation():
    # Bridge- + water = Bridgewater (continuation lowercase)
    assert try_hyphenation_join("Bridge-", "water") == "Bridgewater"


def test_hyphenation_join_uppercase_continuation_is_real_compound():
    # Anglo- + Saxon stays as two separate tokens (real hyphenated compound).
    assert try_hyphenation_join("Anglo-", "Saxon") is None


def test_hyphenation_join_no_trailing_hyphen():
    assert try_hyphenation_join("Bridge", "water") is None


def test_hyphenation_join_empty():
    assert try_hyphenation_join("", "water") is None
    assert try_hyphenation_join("Bridge-", "") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tokenizer_helpers.py -v`
Expected: ImportError — helpers not defined.

- [ ] **Step 3: Add helpers to `model/name_indexer.py`**

Insert these helpers near the top of `model/name_indexer.py`, after the constants and before `extract_styled_tokens`:

```python
def should_suppress_break(prev_word: str, next_word: str) -> bool:
    """Return True if a synthetic line/block-end break should be suppressed
    because both adjacent words are capitalised (the phrase is wrapping).

    A capitalised word is one whose first character is uppercase (Unicode-aware).
    Empty strings on either side return False — we cannot know what is happening.
    """
    if not prev_word or not next_word:
        return False
    return prev_word[0].isupper() and next_word[0].isupper()


def try_hyphenation_join(prev_word: str, next_word: str) -> Optional[str]:
    """If *prev_word* ends in '-' and *next_word* starts with a lowercase letter,
    return the joined word (hyphen removed). Otherwise return None.

    The lowercase-continuation rule distinguishes mid-syllable line wraps
    ("Bridge-water") from real hyphenated compounds ("Anglo-Saxon").
    """
    if not prev_word or not next_word:
        return None
    if not prev_word.endswith("-"):
        return None
    if not next_word[0].islower():
        return None
    return prev_word[:-1] + next_word
```

`Optional` is already imported at the top of the file.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tokenizer_helpers.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add model/name_indexer.py tests/test_tokenizer_helpers.py
git commit -m "feat(name_indexer): add lexical override and hyphenation join helpers"
```

---

## Task 4: Add `is_all_caps` and `from_all_caps_line` to `StyledToken`; integrate into tokenizer

The current tokenizer drops all all-caps tokens via `_is_all_caps_word` filtering inside the extractor. We want to admit single all-caps tokens like "NATO" but still suppress entire all-caps lines like "INTRODUCTION". Add two flags so the extractor can distinguish.

**Files:**
- Modify: `model/name_indexer.py`

- [ ] **Step 1: Update the `StyledToken` dataclass**

Find the existing dataclass:

```python
@dataclass
class StyledToken:
    text: str
    is_bold: bool
    is_italic: bool
    is_superscript: bool
```

Replace with:

```python
@dataclass
class StyledToken:
    text: str
    is_bold: bool
    is_italic: bool
    is_superscript: bool
    is_all_caps: bool = False           # True if the token alone is all-caps (>=2 letters)
    from_all_caps_line: bool = False    # True if the line containing this token is fully all-caps
```

- [ ] **Step 2: Set the flags in `extract_styled_tokens`**

In `extract_styled_tokens`, the inner loop currently looks like:

```python
for span in line.get("spans", []):
    flags = span.get("flags", 0)
    is_bold = bool(flags & 16)
    is_italic = bool(flags & 2)
    is_superscript = bool(flags & 1)
    text = span.get("text", "")

    for match in _TOKEN_RE.finditer(text):
        word = match.group()
        tokens.append(StyledToken(
            text=word,
            is_bold=is_bold,
            is_italic=is_italic,
            is_superscript=is_superscript,
        ))
```

Replace with:

```python
line_is_caps = _line_is_all_caps(line.get("spans", []))
for span in line.get("spans", []):
    flags = span.get("flags", 0)
    is_bold = bool(flags & 16)
    is_italic = bool(flags & 2)
    is_superscript = bool(flags & 1)
    text = span.get("text", "")

    for match in _TOKEN_RE.finditer(text):
        word = match.group()
        tokens.append(StyledToken(
            text=word,
            is_bold=is_bold,
            is_italic=is_italic,
            is_superscript=is_superscript,
            is_all_caps=_is_all_caps_word(word),
            from_all_caps_line=line_is_caps,
        ))
```

- [ ] **Step 3: Apply the lexical override at line and block boundaries**

In `extract_styled_tokens`, the existing block-boundary separator block looks like:

```python
if tokens and prev_block is not None:
    insert_sep = True
    if col_width > 0:
        prev_lines = prev_block.get("lines", [])
        if prev_lines:
            last_bbox = prev_lines[-1].get("bbox")
            if last_bbox:
                line_w = last_bbox[2] - last_bbox[0]
                if line_w >= col_width * 0.9:
                    insert_sep = False  # wrapped paragraph text

    if insert_sep:
        tokens.append(StyledToken(
            text=".", is_bold=False, is_italic=False,
            is_superscript=False,
        ))
```

Replace with (lexical override added — peek at the first capitalised word of the upcoming block):

```python
if tokens and prev_block is not None:
    insert_sep = True
    if col_width > 0:
        prev_lines = prev_block.get("lines", [])
        if prev_lines:
            last_bbox = prev_lines[-1].get("bbox")
            if last_bbox:
                line_w = last_bbox[2] - last_bbox[0]
                if line_w >= col_width * 0.9:
                    insert_sep = False  # wrapped paragraph text

    if insert_sep:
        prev_word = tokens[-1].text if tokens else ""
        next_word = _peek_first_word(block)
        if should_suppress_break(prev_word, next_word):
            insert_sep = False

    if insert_sep:
        tokens.append(StyledToken(
            text=".", is_bold=False, is_italic=False,
            is_superscript=False,
        ))
```

Similarly, the existing within-block line-end separator:

```python
is_last_line = (line_idx == len(block_lines) - 1)
if not is_last_line and tokens and col_width > 0:
    line_bbox = line.get("bbox")
    if line_bbox:
        line_w = line_bbox[2] - line_bbox[0]
        if line_w < col_width * 0.9:
            tokens.append(StyledToken(
                text=".", is_bold=False, is_italic=False,
                is_superscript=False,
            ))
```

Replace with:

```python
is_last_line = (line_idx == len(block_lines) - 1)
if not is_last_line and tokens and col_width > 0:
    line_bbox = line.get("bbox")
    if line_bbox:
        line_w = line_bbox[2] - line_bbox[0]
        if line_w < col_width * 0.9:
            prev_word = tokens[-1].text
            next_word = _peek_first_word_of_line(block_lines[line_idx + 1])
            if not should_suppress_break(prev_word, next_word):
                tokens.append(StyledToken(
                    text=".", is_bold=False, is_italic=False,
                    is_superscript=False,
                ))
```

- [ ] **Step 4: Add the peek helpers**

Insert above `extract_styled_tokens`:

```python
def _peek_first_word(block) -> str:
    """Return the first word-like token in the first line of *block*, or ''."""
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            for match in _TOKEN_RE.finditer(span.get("text", "")):
                w = match.group()
                if not _is_punctuation(w):
                    return w
        # Empty first line: keep looking
    return ""


def _peek_first_word_of_line(line) -> str:
    for span in line.get("spans", []):
        for match in _TOKEN_RE.finditer(span.get("text", "")):
            w = match.group()
            if not _is_punctuation(w):
                return w
    return ""
```

- [ ] **Step 5: Apply hyphenation join when reaching the next line**

Inside the per-line span loop, after the line iteration finishes (just before the line-break-separator decision), if the previous in-block line ended with a `-` token and the next line begins with a lowercase word, fuse them. Implement at the start of each non-first line iteration:

Find the existing structure:

```python
block_lines = block.get("lines", [])
for line_idx, line in enumerate(block_lines):
    for span in line.get("spans", []):
        ...
```

Replace the outer loop with:

```python
block_lines = block.get("lines", [])
for line_idx, line in enumerate(block_lines):
    # Hyphenation join: if the previous line in this block left a token
    # ending in "-" and the first word of this line starts lowercase,
    # fuse them (drop the hyphen) instead of emitting both halves.
    pending_join = None
    if line_idx > 0 and tokens:
        first_word = _peek_first_word_of_line(line)
        joined = try_hyphenation_join(tokens[-1].text, first_word)
        if joined is not None:
            pending_join = (joined, first_word)
            # Replace the last token's text with the joined form. The
            # styling (bold/italic/etc) is inherited from the first half.
            old = tokens[-1]
            tokens[-1] = StyledToken(
                text=joined,
                is_bold=old.is_bold,
                is_italic=old.is_italic,
                is_superscript=old.is_superscript,
                is_all_caps=_is_all_caps_word(joined),
                from_all_caps_line=old.from_all_caps_line,
            )

    line_is_caps = _line_is_all_caps(line.get("spans", []))
    for span in line.get("spans", []):
        flags = span.get("flags", 0)
        is_bold = bool(flags & 16)
        is_italic = bool(flags & 2)
        is_superscript = bool(flags & 1)
        text = span.get("text", "")

        for match in _TOKEN_RE.finditer(text):
            word = match.group()
            # If this is the first word of the line and we just consumed
            # it via hyphenation join, skip emitting it as a separate token.
            if pending_join is not None and word == pending_join[1]:
                pending_join = None
                continue
            tokens.append(StyledToken(
                text=word,
                is_bold=is_bold,
                is_italic=is_italic,
                is_superscript=is_superscript,
                is_all_caps=_is_all_caps_word(word),
                from_all_caps_line=line_is_caps,
            ))

    # ... existing line-end separator logic continues here ...
```

- [ ] **Step 6: Manual smoke check**

Run the app, open the existing project at `Data/`, click Create Index. Verify it still produces a non-empty index with no exceptions. (Style flags on `StyledToken` default to false everywhere downstream of this task, so nothing else should change yet.)

```bash
python main.py
```

- [ ] **Step 7: Commit**

```bash
git add model/name_indexer.py
git commit -m "feat(tokenizer): integrate lexical override and hyphenation join"
```

---

## Task 5: Migrate occurrence shape to 3-tuples (data model)

Every place that builds, reads, or persists `raw_results` must accept tuples shaped as `(page_idx, page_label, flags)` where `flags` is a `dict[str, bool]` with keys `italic`, `bold`, `caps`. Pre-existing code that builds 2-tuples is updated to emit 3-tuples with all-false flags (a no-op for behaviour but a step the rest of the plan requires).

**Files:**
- Modify: `model/indexer.py` (build helper + range compression)
- Modify: `model/name_indexer.py` (occurrence builders + `_suppress_covered_components`)
- Modify: `controller/main_controller.py` (load/save, merging)

- [ ] **Step 1: Add a flags helper at the top of `model/indexer.py`** (after the imports, before the roman helpers added in Task 2)

```python
EMPTY_FLAGS = {"italic": False, "bold": False, "caps": False}


def make_flags(italic: bool = False, bold: bool = False, caps: bool = False) -> dict:
    return {"italic": italic, "bold": bold, "caps": caps}


def merge_flags(a: dict, b: dict) -> dict:
    """OR-combine two flag dicts."""
    return {
        "italic": a.get("italic", False) or b.get("italic", False),
        "bold": a.get("bold", False) or b.get("bold", False),
        "caps": a.get("caps", False) or b.get("caps", False),
    }


def normalise_occurrence(occ) -> tuple:
    """Accept a 2-tuple or 3-tuple and always return a 3-tuple with a flag dict.

    Used at every load boundary (in-memory merges, JSON load) to tolerate the
    legacy 2-element occurrence shape.
    """
    if len(occ) == 3:
        idx, label, flags = occ
        if not isinstance(flags, dict):
            flags = dict(EMPTY_FLAGS)
        else:
            flags = {
                "italic": bool(flags.get("italic", False)),
                "bold": bool(flags.get("bold", False)),
                "caps": bool(flags.get("caps", False)),
            }
        return (idx, label, flags)
    if len(occ) == 2:
        idx, label = occ
        return (idx, label, dict(EMPTY_FLAGS))
    raise ValueError(f"Unexpected occurrence shape: {occ!r}")


def normalise_raw_results(raw_results: dict) -> dict:
    """Apply normalise_occurrence over every entry in *raw_results* in place."""
    for key, occurrences in list(raw_results.items()):
        raw_results[key] = [normalise_occurrence(o) for o in occurrences]
    return raw_results
```

- [ ] **Step 2: Update the keyword indexer to emit 3-tuples**

In `model/indexer.py`, the existing `IndexingThread.run` builds occurrences as 2-tuples:

```python
if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
    raw_results[original_kw].append((i, page_label))
```

Change the appended value to a 3-tuple with empty flags (the keyword indexer will be rewritten in Task 9 to compute real flags; this step just keeps the data shape consistent so the rest of the plan can proceed):

```python
if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
    raw_results[original_kw].append((i, page_label, dict(EMPTY_FLAGS)))
```

- [ ] **Step 3: Update `process_results` to handle 3-tuples**

In `model/indexer.py`, the existing `process_results` does:

```python
for i in range(1, len(pages)):
    prev_idx, _ = pages[i-1]
    curr_idx, curr_lbl = pages[i]
```

Replace with tuple-shape-tolerant unpacking (we only need idx and label here, not flags):

```python
for i in range(1, len(pages)):
    prev_idx = pages[i-1][0]
    curr_idx = pages[i][0]
```

The downstream lines that read `r[0][1]` (label of first item) and `r[-1][1]` (label of last) continue to work — index 1 is still the label.

- [ ] **Step 4: Update `_suppress_covered_components` in `model/name_indexer.py`**

It already only reads index 0 (`{p[0] for p in pages}`), so it works unchanged. No edit needed for this file in this task — but verify by re-reading the function and confirming.

- [ ] **Step 5: Update name indexer occurrence construction**

In `model/name_indexer.py`, `NameIndexingThread.run`, change every place that builds an occurrence tuple:

```python
all_occurrences[name].append((i, page_label))
```

becomes:

```python
all_occurrences[name].append((i, page_label, dict(EMPTY_FLAGS)))
```

There are similar lines inside the per-name dedup blocks. Add `from model.indexer import EMPTY_FLAGS` at the top of `name_indexer.py`. Each occurrence stays empty-flagged for now; Task 8 will populate real flags.

Also update the dedup loop:

```python
seen: set = set()
deduped: list = []
for p in occurrences:
    if p[0] not in seen:
        seen.add(p[0])
        deduped.append(p)
```

This already works for 3-tuples (index 0 is still the page index). No edit needed beyond construction.

The merge-collision branch:

```python
if display_key in raw_results:
    existing_indices = {p[0] for p in raw_results[display_key]}
    for p in deduped:
        if p[0] not in existing_indices:
            raw_results[display_key].append(p)
    raw_results[display_key].sort(key=lambda x: x[0])
```

Update so a colliding occurrence merges flags rather than dropping them:

```python
if display_key in raw_results:
    existing_by_idx = {p[0]: idx for idx, p in enumerate(raw_results[display_key])}
    for p in deduped:
        if p[0] in existing_by_idx:
            slot = existing_by_idx[p[0]]
            old = raw_results[display_key][slot]
            raw_results[display_key][slot] = (
                old[0], old[1], merge_flags(old[2], p[2]),
            )
        else:
            raw_results[display_key].append(p)
    raw_results[display_key].sort(key=lambda x: x[0])
```

Add `from model.indexer import EMPTY_FLAGS, merge_flags` at the top of `name_indexer.py`.

- [ ] **Step 6: Update `resolve_group_pages`**

In `model/name_indexer.py`, this function currently does:

```python
seen = set()
deduped = []
for p in longest_pages:
    if p[0] not in seen:
        seen.add(p[0])
        deduped.append(p)
```

Already 3-tuple safe. No edit needed.

The orphan-page branch:

```python
orphan_pages: Dict[int, str] = {}
for page_idx, page_label in occurrences:
    if page_idx not in longest_page_indices:
        orphan_pages[page_idx] = page_label
if orphan_pages:
    result[variation] = sorted(orphan_pages.items(), key=lambda x: x[0])
```

This drops flags. Replace with:

```python
orphan_pages: Dict[int, tuple] = {}
for occ in occurrences:
    page_idx = occ[0]
    if page_idx not in longest_page_indices:
        orphan_pages[page_idx] = occ
if orphan_pages:
    result[variation] = [orphan_pages[k] for k in sorted(orphan_pages.keys())]
```

- [ ] **Step 7: Update controller load/save and merging**

In `controller/main_controller.py`, the JSON load is:

```python
with open(index_path, 'r', encoding='utf-8') as f:
    self._last_report_sections = None
    self.last_raw_results = json.load(f)
```

Add normalisation immediately after:

```python
with open(index_path, 'r', encoding='utf-8') as f:
    self._last_report_sections = None
    self.last_raw_results = json.load(f)
from model.indexer import normalise_raw_results
normalise_raw_results(self.last_raw_results)
```

Inside the existing JSON-loaded entries, `json.load` produces lists not tuples — that's fine; downstream code uses `p[0]` / `p[1]` / `p[2]` which work the same.

The merge-mappings application currently does:

```python
existing_indices = {p[0] for p in self.last_raw_results[target]}
for p in self.last_raw_results[source]:
    if p[0] not in existing_indices:
        self.last_raw_results[target].append(p)
        existing_indices.add(p[0])
self.last_raw_results[target].sort(key=lambda x: x[0])
del self.last_raw_results[source]
```

Update to merge flags on collision:

```python
existing_by_idx = {p[0]: i for i, p in enumerate(self.last_raw_results[target])}
for p in self.last_raw_results[source]:
    if p[0] in existing_by_idx:
        slot = existing_by_idx[p[0]]
        old = self.last_raw_results[target][slot]
        self.last_raw_results[target][slot] = (
            old[0], old[1],
            merge_flags(old[2] if len(old) > 2 else dict(EMPTY_FLAGS),
                        p[2] if len(p) > 2 else dict(EMPTY_FLAGS)),
        )
    else:
        self.last_raw_results[target].append(p)
        existing_by_idx[p[0]] = len(self.last_raw_results[target]) - 1
self.last_raw_results[target].sort(key=lambda x: x[0])
del self.last_raw_results[source]
```

Add `from model.indexer import EMPTY_FLAGS, merge_flags` at the top of `main_controller.py`.

The same pattern applies to `_try_merge_results`, `on_merge_entry_requested`, and `_on_merge_tool_merge` — each has an `existing_indices` block. Update each one to use `existing_by_idx` and `merge_flags` as above.

- [ ] **Step 8: Manual smoke check**

```bash
python main.py
```

Open the existing project. Confirm the existing index loads, indexing runs, the JSON file written has 3-tuples (`[idx, "label", {"italic": false, "bold": false, "caps": false}]`).

- [ ] **Step 9: Commit**

```bash
git add model/indexer.py model/name_indexer.py controller/main_controller.py
git commit -m "refactor: migrate occurrence tuples to 3-tuples with style flags"
```

---

## Task 6: Name extractor admits single all-caps tokens

Currently `extract_names_from_tokens` skips any all-caps word, treating it as a heading. The new rule: skip only when the token is on a line that is fully all-caps. Single all-caps tokens like "NATO" inside a mixed line are admitted as name candidates and propagate `caps=True` through.

**Files:**
- Modify: `model/name_indexer.py`
- Create: `tests/test_name_extractor.py`

- [ ] **Step 1: Write the failing test**

`tests/test_name_extractor.py`:

```python
from model.name_indexer import (
    StyledToken,
    extract_names_from_tokens,
)


def _tokens(text: str, *, italic=False, all_caps_line=False, all_caps=None):
    """Tiny helper: build a list of StyledToken from whitespace-split text."""
    out = []
    for word in text.split():
        is_caps = all_caps if all_caps is not None else word.isupper() and len(word) > 1
        out.append(StyledToken(
            text=word,
            is_bold=False,
            is_italic=italic,
            is_superscript=False,
            is_all_caps=is_caps,
            from_all_caps_line=all_caps_line,
        ))
    return out


def test_admits_single_all_caps_token_in_mixed_line():
    # NATO sits in mid-sentence with normal-case neighbours.
    tokens = _tokens("the NATO summit")
    names = extract_names_from_tokens(tokens)
    assert "NATO" in names


def test_skips_all_caps_line():
    # Whole line is all caps — heading, not names.
    tokens = _tokens("INTRODUCTION", all_caps_line=True)
    names = extract_names_from_tokens(tokens)
    assert names == []


def test_admits_all_caps_inside_capitalised_run():
    # "European NATO Summit" — all three capitalised, NATO is all-caps.
    tokens = _tokens("European NATO Summit")
    names = extract_names_from_tokens(tokens)
    # The whole run is one entry.
    assert "European NATO Summit" in names
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_name_extractor.py -v`
Expected: failures — current code skips all all-caps tokens unconditionally.

- [ ] **Step 3: Update the all-caps filter in `extract_names_from_tokens`**

In `model/name_indexer.py`, find the all-caps block:

```python
# All-caps words (section titles like "INTRODUCTION") — always skip.
if _is_all_caps_word(word):
    if current_ngram:
        names.append(" ".join(current_ngram))
        current_ngram = []
        current_ngram_italic = None
    continue
```

Replace with:

```python
# All-caps words on an all-caps line (section titles like "INTRODUCTION") — skip.
# Single all-caps tokens inside a mixed-case line ("NATO", "CERN") are admitted
# as name candidates and proceed to the is_name_word block below.
if token.is_all_caps and token.from_all_caps_line:
    if current_ngram:
        names.append(" ".join(current_ngram))
        current_ngram = []
        current_ngram_italic = None
    continue
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_name_extractor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add model/name_indexer.py tests/test_name_extractor.py
git commit -m "feat(name_indexer): admit single all-caps tokens as name candidates"
```

---

## Task 7: Italic n-gram capture pass

Add a separate pass over the tokens that captures runs of italic-styled tokens regardless of capitalisation. Connectors do **not** break italic runs (titles like *The Sound of Music* contain them); structural words still do.

**Files:**
- Modify: `model/name_indexer.py`
- Modify: `tests/test_name_extractor.py`

- [ ] **Step 1: Add italic-capture tests**

Append to `tests/test_name_extractor.py`:

```python
from model.name_indexer import extract_italic_phrases


def test_extract_italic_phrase_lowercase():
    # Italic Latin phrase — no word capitalised.
    tokens = _tokens("in vino veritas", italic=True)
    out = extract_italic_phrases(tokens)
    assert "in vino veritas" in out


def test_extract_italic_phrase_with_connectors():
    # Connectors (of, and) do not break italic runs — preserve titles.
    tokens = _tokens("The Sound of Music", italic=True)
    out = extract_italic_phrases(tokens)
    assert "The Sound of Music" in out


def test_extract_italic_skips_non_italic():
    # Plain text is not captured by the italic pass.
    tokens = _tokens("plain text only", italic=False)
    out = extract_italic_phrases(tokens)
    assert out == []


def test_extract_italic_break_on_non_italic_word():
    # Italic phrase ends when italic flag turns off; restarts when it returns.
    tokens = (
        _tokens("Pride and Prejudice", italic=True)
        + _tokens("interrupted", italic=False)
        + _tokens("Sense and Sensibility", italic=True)
    )
    out = extract_italic_phrases(tokens)
    assert "Pride and Prejudice" in out
    assert "Sense and Sensibility" in out
    assert "interrupted" not in out
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_name_extractor.py -v`
Expected: ImportError on `extract_italic_phrases`.

- [ ] **Step 3: Implement `extract_italic_phrases`**

Add to `model/name_indexer.py` after `extract_names_from_tokens`:

```python
def extract_italic_phrases(tokens: List[StyledToken]) -> List[str]:
    """Walk *tokens* and emit runs of italic-styled tokens as phrases.

    Rules:
    - A run starts at the first italic-styled word token and continues
      while subsequent tokens are also italic.
    - Punctuation flushes the run.
    - Structural words (Chapter, Section, ...) flush the run — they only
      appear in italic by accident.
    - Connector words (and, of, to, ...) extend the run, since titles
      legitimately contain them ("The Sound of Music").
    - Roman numerals, footnote refs, and pure-number tokens are skipped
      without breaking the run (mirrors extract_names_from_tokens behaviour).
    - Possessive suffixes are stripped before adding to the run.
    """
    phrases: List[str] = []
    current: List[str] = []

    def flush():
        if current:
            phrases.append(" ".join(current))
            current.clear()

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        if not token.is_italic:
            flush()
            continue

        if token.is_superscript and _is_footnote_ref(word):
            flush()
            continue

        if _is_punctuation(word):
            flush()
            continue

        word = _strip_possessive(word)
        if not word:
            continue

        if word.lower() in STRUCTURAL_WORDS:
            flush()
            continue

        if _is_roman_numeral(word):
            flush()
            continue

        if _is_number_like(word):
            flush()
            continue

        current.append(word)

    flush()
    return phrases
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_name_extractor.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add model/name_indexer.py tests/test_name_extractor.py
git commit -m "feat(name_indexer): add italic n-gram capture pass"
```

---

## Task 8: Name indexer propagates style flags through occurrences

Now that all-caps and italic are first-class, every occurrence record produced by `NameIndexingThread` should reflect the styles of the tokens that produced the match.

**Files:**
- Modify: `model/name_indexer.py`

- [ ] **Step 1: Change `extract_names_from_tokens` to also return style flags**

Update the function signature and behaviour. The current return is `List[str]`; change it to `List[Tuple[str, dict]]` — each n-gram comes paired with the OR'd flags of its constituent tokens.

In the current function body, replace the `current_ngram: List[str] = []` line with:

```python
current_ngram: List[str] = []
current_flags: dict = {"italic": False, "bold": False, "caps": False}
```

In every place where the function flushes the n-gram (search for `names.append(" ".join(current_ngram))`), replace each occurrence with:

```python
names.append((" ".join(current_ngram), dict(current_flags)))
current_ngram = []
current_flags = {"italic": False, "bold": False, "caps": False}
```

Wherever a token is appended to `current_ngram`, also OR its flags into `current_flags`. The append site looks like:

```python
if not current_ngram:
    current_ngram_italic = token.is_italic
current_ngram.append(word)
```

Replace with:

```python
if not current_ngram:
    current_ngram_italic = token.is_italic
current_ngram.append(word)
if token.is_italic:
    current_flags["italic"] = True
if token.is_bold:
    current_flags["bold"] = True
if token.is_all_caps:
    current_flags["caps"] = True
```

The exclude-mid-sequence branch (`current_ngram.append(word)` when an excluded word extends the run) and the connector-italic-extend branch (`current_ngram.append(word)`) need the same flag merging — add the same three `if`s after each.

The final flush at end of function:

```python
if current_ngram:
    names.append(" ".join(current_ngram))
return names
```

becomes:

```python
if current_ngram:
    names.append((" ".join(current_ngram), dict(current_flags)))
return names
```

Update the type annotation to `List[Tuple[str, dict]]` and adjust the docstring accordingly.

- [ ] **Step 2: Update existing tests for the new return shape**

In `tests/test_name_extractor.py`, the helpers `extract_names_from_tokens` calls now return `[(name, flags), ...]`. Replace the assertions:

```python
assert "NATO" in names
```

with:

```python
assert any(n == "NATO" for n, _ in names)
```

and similarly for the other `extract_names_from_tokens` assertions in `test_admits_all_caps_inside_capitalised_run`, `test_skips_all_caps_line`, etc.

For `test_admits_all_caps_inside_capitalised_run`, also assert flag propagation:

```python
def test_admits_all_caps_inside_capitalised_run():
    tokens = _tokens("European NATO Summit")
    names = extract_names_from_tokens(tokens)
    by_text = dict(names)
    assert "European NATO Summit" in by_text
    assert by_text["European NATO Summit"]["caps"] is True
```

- [ ] **Step 3: Run name extractor tests**

Run: `pytest tests/test_name_extractor.py -v`
Expected: 7 passed.

- [ ] **Step 4: Update `NameIndexingThread.run` to consume the new shape**

In `model/name_indexer.py`, the existing pass 1 builds the vocabulary like:

```python
raw_names = extract_names_from_tokens(
    tokens, discovery_mode=True,
    include_bold=self.include_bold,
    exclude_words=self.exclude_words,
    stopwords=self.stopwords,
)
names = filter_names(raw_names)
name_vocabulary.update(names)
```

`filter_names` and `clean_name` operate on strings. Adapt:

```python
raw_named = extract_names_from_tokens(
    tokens, discovery_mode=True,
    include_bold=self.include_bold,
    exclude_words=self.exclude_words,
    stopwords=self.stopwords,
)
# raw_named is List[Tuple[str, dict]]; vocabulary only needs the strings
raw_names = [n for n, _flags in raw_named]
names = filter_names(raw_names)
name_vocabulary.update(names)
```

- [ ] **Step 5: Add italic capture inside the same loop**

Right after the existing pass-1 line above, insert italic phrase capture so italic-only entries enter the vocabulary too:

```python
if getattr(self, 'index_italic', True):
    italic_raw = extract_italic_phrases(tokens)
    italic_clean = filter_names(italic_raw)
    name_vocabulary.update(italic_clean)
```

Add the `index_italic` parameter to `NameIndexingThread.__init__` (default True):

```python
def __init__(self, pdf_path, page_numbering_strategy, offset=0,
             include_bold=False, exclude_words=None, stopwords=None,
             name_type_overrides=None, start_page=0, surname_first=False,
             index_italic=True):
    super().__init__()
    ...
    self.index_italic = index_italic
```

- [ ] **Step 6: Augment pass 2 to also record style flags from styled tokens**

The existing pass-2 result-building block:

```python
found_names = find_known_names_in_tokens(
    tokens, name_vocabulary, known_names_lower, max_ngram_len,
)

seen_on_page: Set[str] = set()
for name in found_names:
    if name not in seen_on_page:
        seen_on_page.add(name)
        all_occurrences[name].append((i, page_label))
```

Change `find_known_names_in_tokens` to return `List[Tuple[str, dict]]` so the caller can record flags. Update its body so that when it greedily matches an n-gram starting at index `i`, it OR's the styling flags of the spanned word tokens.

The current loop in `find_known_names_in_tokens`:

```python
word_tokens: List[str] = []
for token in tokens:
    word = token.text.strip()
    ...
    word_tokens.append(word)
```

Replace `word_tokens` with two parallel lists, one of strings and one of flag dicts, both with `None` sentinels at punctuation:

```python
word_tokens: List[str] = []
word_flags: List[dict] = []  # parallel; entry is None where word_tokens is None
for token in tokens:
    word = token.text.strip()
    if not word:
        continue
    if token.is_superscript and _is_footnote_ref(word):
        continue
    if _is_punctuation(word):
        word_tokens.append(None)
        word_flags.append(None)
        continue
    word = _strip_possessive(word)
    if not word:
        continue
    word_tokens.append(word)
    word_flags.append({
        "italic": bool(token.is_italic),
        "bold": bool(token.is_bold),
        "caps": bool(token.is_all_caps),
    })
```

Inside the match loop, after `if canon is not None:`, OR the flags across the matched span:

```python
flags = {"italic": False, "bold": False, "caps": False}
for fj in word_flags[i:i + length]:
    if fj is None:
        continue
    if fj["italic"]:
        flags["italic"] = True
    if fj["bold"]:
        flags["bold"] = True
    if fj["caps"]:
        flags["caps"] = True
found.append((canon, flags))
break
```

Change the function's return type to `List[Tuple[str, dict]]`.

- [ ] **Step 7: Replace the pass-2 emission block with a unified per-page block**

Back in `NameIndexingThread.run`, find the existing emission:

```python
seen_on_page: Set[str] = set()
for name in found_names:
    if name not in seen_on_page:
        seen_on_page.add(name)
        all_occurrences[name].append((i, page_label))
```

Replace with the unified block that:
1. Collects flags for `find_known_names_in_tokens` matches (multiple matches on the same page collapse into one merged-flags occurrence).
2. Adds italic phrases captured on this page (when `index_italic` is on), OR-merging into any existing entry.
3. Emits one occurrence per (name, page).

```python
seen_flags_by_name: dict = {}

for name, flags in found_names:
    if name not in seen_flags_by_name:
        seen_flags_by_name[name] = dict(flags)
    else:
        seen_flags_by_name[name] = merge_flags(seen_flags_by_name[name], flags)

if getattr(self, 'index_italic', True):
    italic_phrases = extract_italic_phrases(tokens)
    italic_clean = filter_names(italic_phrases)
    for phrase in italic_clean:
        italic_flags = {"italic": True, "bold": False, "caps": False}
        if phrase in seen_flags_by_name:
            seen_flags_by_name[phrase] = merge_flags(seen_flags_by_name[phrase], italic_flags)
        else:
            seen_flags_by_name[phrase] = italic_flags

for name, flags in seen_flags_by_name.items():
    all_occurrences[name].append((i, page_label, flags))
```

- [ ] **Step 8: Manual smoke check**

Run the app on the existing `Data/` project. Confirm: the output index is non-empty, JSON contains flag dicts with at least *some* non-zero flags (e.g., italic=true entries from pages where italic phrases occur), no exceptions.

```bash
python main.py
```

- [ ] **Step 9: Commit**

```bash
git add model/name_indexer.py tests/test_name_extractor.py
git commit -m "feat(name_indexer): propagate style flags through occurrences and add italic capture"
```

---

## Task 9: Keyword indexer rewrite — operate on styled tokens with flag propagation

Replace `IndexingThread.run`'s text-based regex with a styled-token-aware version. The keyword regex still uses `\b...\b` semantics; we just run it against a reconstructed string built from styled tokens, and look up the flags of the spanning tokens for each match.

**Files:**
- Modify: `model/indexer.py`
- Create: `tests/test_keyword_match.py`

- [ ] **Step 1: Write the failing test**

`tests/test_keyword_match.py`:

```python
from model.indexer import find_keyword_flags_in_tokens
from model.name_indexer import StyledToken


def _tok(word, *, italic=False, bold=False, caps=False):
    return StyledToken(
        text=word, is_bold=bold, is_italic=italic,
        is_superscript=False, is_all_caps=caps, from_all_caps_line=False,
    )


def test_match_plain_text():
    tokens = [_tok("the"), _tok("piano"), _tok("recital")]
    flags = find_keyword_flags_in_tokens(tokens, "piano")
    assert flags is not None
    assert flags == {"italic": False, "bold": False, "caps": False}


def test_match_italic_keyword():
    tokens = [_tok("the"), _tok("piano", italic=True), _tok("recital")]
    flags = find_keyword_flags_in_tokens(tokens, "piano")
    assert flags["italic"] is True
    assert flags["bold"] is False


def test_match_caps_keyword():
    tokens = [_tok("the"), _tok("NATO", caps=True), _tok("summit")]
    flags = find_keyword_flags_in_tokens(tokens, "nato")
    assert flags["caps"] is True


def test_match_multiword_keyword():
    tokens = [_tok("Sound", italic=True), _tok("of", italic=True), _tok("Music", italic=True)]
    flags = find_keyword_flags_in_tokens(tokens, "Sound of Music")
    assert flags["italic"] is True


def test_no_match():
    tokens = [_tok("the"), _tok("piano")]
    assert find_keyword_flags_in_tokens(tokens, "violin") is None


def test_word_boundary_no_substring():
    tokens = [_tok("Concerto")]  # contains "once"
    assert find_keyword_flags_in_tokens(tokens, "once") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_keyword_match.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `find_keyword_flags_in_tokens`**

Add to `model/indexer.py`:

```python
def find_keyword_flags_in_tokens(tokens, keyword: str):
    """Search *tokens* for a whole-word, case-insensitive match of *keyword*.

    Returns the OR'd style flag dict from the spanning tokens, or None if
    no match.

    The reconstructed page string joins token texts with single spaces; the
    regex uses Python's standard `\\b` word boundaries against that
    reconstruction. Multi-word keywords work because spaces in *keyword*
    line up with the joiner.
    """
    if not keyword.strip():
        return None

    parts = []
    spans = []  # parallel list of (start, end) char offsets in the joined string
    cursor = 0
    word_tokens = []  # only the word-like tokens we kept
    for tok in tokens:
        text = tok.text
        if not text:
            continue
        # Skip pure-punctuation synthetic separators (".", etc.) — they
        # would create unwanted match boundaries between adjacent words.
        # We keep real punctuation by including it; only the synthetic "." token
        # we appended in the tokenizer is the one we suppress here.
        if all(unicodedata.category(ch).startswith('P') for ch in text):
            # Treat as a hard break — emit a sentinel character so \b works
            # naturally and multi-word matches do not span the punctuation.
            parts.append(".")
            spans.append((cursor, cursor + 1))
            cursor += 1
            word_tokens.append(None)
            cursor += 1  # for the joiner space below
            parts.append(" ")
            continue
        parts.append(text)
        spans.append((cursor, cursor + len(text)))
        cursor += len(text)
        word_tokens.append(tok)
        # Joiner space (one between every emitted token)
        cursor += 1
        parts.append(" ")

    joined = "".join(parts).rstrip()
    pattern = re.compile(rf'\b{re.escape(keyword)}\b', re.IGNORECASE)
    m = pattern.search(joined)
    if not m:
        return None

    match_start, match_end = m.span()
    flags = {"italic": False, "bold": False, "caps": False}
    for tok, (s, e) in zip(word_tokens, spans):
        if tok is None:
            continue
        if e <= match_start or s >= match_end:
            continue
        if tok.is_italic:
            flags["italic"] = True
        if tok.is_bold:
            flags["bold"] = True
        if tok.is_all_caps:
            flags["caps"] = True
    return flags
```

Add `import unicodedata` to `model/indexer.py` (already imported — verify).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_keyword_match.py -v`
Expected: 6 passed.

- [ ] **Step 5: Rewrite `IndexingThread.run` to use styled tokens**

In `model/indexer.py`, replace the body of `IndexingThread.run` so it builds tokens via the name_indexer's tokenizer and calls `find_keyword_flags_in_tokens` per keyword. The page-iteration shape stays the same; only the per-page work changes.

Replace:

```python
page = doc.load_page(i)
text = page.get_text("text")
norm_text = unicodedata.normalize('NFKC', text)

page_label = ""
if self.strategy == 'logical':
    page_label = page.get_label()
    if not page_label:
        page_label = str(i + 1)
else:
    page_label = str(i + 1 + self.offset)

for norm_kw, pattern in regex_map.items():
    if pattern.search(norm_text):
        original_kw = keyword_map[norm_kw]
        if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
            raw_results[original_kw].append((i, page_label, dict(EMPTY_FLAGS)))
```

with:

```python
page = doc.load_page(i)
from model.name_indexer import extract_styled_tokens
tokens = extract_styled_tokens(page)

page_label = ""
if self.strategy == 'logical':
    page_label = page.get_label()
    if not page_label:
        page_label = str(i + 1)
else:
    page_label = str(i + 1 + self.offset)

for norm_kw in regex_map.keys():
    original_kw = keyword_map[norm_kw]
    flags = find_keyword_flags_in_tokens(tokens, norm_kw)
    if flags is not None:
        if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
            raw_results[original_kw].append((i, page_label, flags))
```

The `regex_map` dict and the keyword normalisation step can stay where they are — `find_keyword_flags_in_tokens` does its own regex compilation per call. (If profiling shows this matters, future work can hoist the compiled patterns.)

- [ ] **Step 6: Manual smoke check**

```bash
python main.py
```

Confirm: keyword index entries land on the expected pages; an italic-styled keyword match (e.g., add a known italic phrase as a keyword) shows up with `"italic": true` in the JSON.

- [ ] **Step 7: Commit**

```bash
git add model/indexer.py tests/test_keyword_match.py
git commit -m "feat(indexer): keyword indexer uses styled tokens and propagates flags"
```

---

## Task 10: Front-matter (roman) indexing pass

When offset < 0 and "Index only from offset" is on, the existing code skips pages `[0, abs(offset))`. Add an option to also index those pages first, with roman-numeral labels.

**Files:**
- Modify: `model/indexer.py`
- Modify: `model/name_indexer.py`
- Modify: `controller/main_controller.py`

- [ ] **Step 1: Add a label-producer helper to `model/indexer.py`**

```python
def label_for_page(page, physical_page_number: int, strategy: str,
                   offset: int = 0, force_roman: bool = False) -> str:
    """Produce the printable label for a page given indexing strategy.

    *physical_page_number* is 1-based.

    When *force_roman* is True (front-matter pass), prefer the PDF's own label
    if it looks roman; otherwise generate a lowercase roman from the physical
    page number.
    """
    if force_roman:
        try:
            label = page.get_label()
        except Exception:
            label = ""
        if looks_like_roman(label):
            return label.lower()
        return to_lowercase_roman(physical_page_number)

    if strategy == 'logical':
        try:
            label = page.get_label()
        except Exception:
            label = ""
        return label if label else str(physical_page_number)
    return str(physical_page_number + offset)
```

- [ ] **Step 2: Rework `IndexingThread.run` to support a front-matter pass**

Add to the constructor:

```python
def __init__(self, pdf_path, keywords, page_numbering_strategy, offset=0,
             start_page=0, index_front_matter=False):
    super().__init__()
    ...
    self.index_front_matter = index_front_matter
```

Inside `run`, restructure the page loop. After the existing setup (regex_map, doc, etc.), do:

```python
front_start = 0 if self.index_front_matter and self.start_page > 0 else self.start_page
front_end = self.start_page  # exclusive
main_start = self.start_page
main_end = total_pages

for kind, page_range in (("front", range(front_start, front_end)),
                          ("main", range(main_start, main_end))):
    if not self._is_running:
        break
    if not page_range:
        continue
    force_roman = (kind == "front")
    for i in page_range:
        if not self._is_running:
            break
        page = doc.load_page(i)
        from model.name_indexer import extract_styled_tokens
        tokens = extract_styled_tokens(page)
        page_label = label_for_page(
            page, i + 1, self.strategy,
            offset=self.offset, force_roman=force_roman,
        )

        for norm_kw in regex_map.keys():
            original_kw = keyword_map[norm_kw]
            flags = find_keyword_flags_in_tokens(tokens, norm_kw)
            if flags is not None:
                if not raw_results[original_kw] or raw_results[original_kw][-1][0] != i:
                    raw_results[original_kw].append((i, page_label, flags))

        progress = int((i + 1) / total_pages * 100)
        self.progress_updated.emit(progress)
```

The previous `indexable = total_pages - self.start_page` block (and its progress fraction using it) is replaced by the simpler `(i + 1) / total_pages` shown above so the progress bar covers both passes smoothly.

- [ ] **Step 3: Same for `NameIndexingThread`**

Add to its constructor:

```python
def __init__(self, pdf_path, page_numbering_strategy, offset=0,
             include_bold=False, exclude_words=None, stopwords=None,
             name_type_overrides=None, start_page=0, surname_first=False,
             index_italic=True, index_front_matter=False):
    super().__init__()
    ...
    self.index_front_matter = index_front_matter
```

Replace the helper method `_compute_label` with `label_for_page` calls. The two passes (discovery + indexing) and the spaCy text collection all need to iterate the same combined range. Define `combined_range` once at the top of `run`:

```python
front_range = (range(0, self._start_page)
               if self.index_front_matter and self._start_page > 0 else range(0, 0))
main_range = range(self._start_page, total_pages)
combined_iter = list(front_range) + list(main_range)
roman_set = set(front_range)
```

In every loop that iterates pages, replace `for i in range(self._start_page, total_pages):` with `for i in combined_iter:` and replace the label call with:

```python
page_label = label_for_page(
    page, i + 1, self.strategy,
    offset=self.offset, force_roman=(i in roman_set),
)
```

The `_compute_label` method can be deleted.

The `page_texts` accumulator that supports spaCy must follow `combined_iter` order so its indexing matches the combined range. (spaCy classification only runs on the main range today; you can keep that behaviour by extending `page_texts` only for `i in main_range` and rebuilding the iterator order accordingly. For simplicity: collect `page_texts` for every page in `combined_iter`, and feed the same list to `_try_spacy_classify` — adds a marginal cost, no correctness impact.)

- [ ] **Step 4: Wire the option in the controller**

In `controller/main_controller.py`, `start_indexing` reads the option from a new checkbox `ctrl.index_front_matter_chk` (added in Task 14). Add it now in stub form so this task's code compiles:

```python
index_front_matter = (
    self.view.controls_output.index_front_matter_chk.isChecked()
    if hasattr(self.view.controls_output, 'index_front_matter_chk')
    else False
)
```

Pass `index_front_matter=index_front_matter` to both `IndexingThread(...)` and `NameIndexingThread(...)` constructors.

Pass `index_italic=ctrl.index_italic_chk.isChecked()` similarly (with `hasattr` guard) to `NameIndexingThread`.

- [ ] **Step 5: Manual smoke check**

This task's UI checkbox does not exist yet — verify with the controller default of False that nothing regresses. Run the app, create the index for an existing project. Confirm the entry count matches what it was before.

```bash
python main.py
```

- [ ] **Step 6: Commit**

```bash
git add model/indexer.py model/name_indexer.py controller/main_controller.py
git commit -m "feat(indexer): support front-matter (roman) indexing pass"
```

---

## Task 11: Range compression with mixed roman + arabic labels

`process_results` currently builds ranges by physical page index but prints labels as-is. Mixed roman/arabic labels in the same entry need to display in document order, and the range printer needs to keep them in their respective formats.

**Files:**
- Modify: `model/indexer.py`

- [ ] **Step 1: Verify the existing behaviour is already correct**

Read the current `process_results`:

```python
ranges.append(range_strings.append(f"{r[0][1]}-{r[-1][1]}"))
```

It prints `r[0][1]-r[-1][1]` — the labels of the first and last entries in the range. Since each entry now is a 3-tuple, index 1 is still the label, so the printer is correct. The range builder uses `prev_idx` / `curr_idx` (page indices) — also correct.

The only edge case: a contiguous range that spans the front-matter / main boundary (physical page i = front-matter end and i+1 = main start). Today this is treated as a single range `iv-7` which mixes formats inside one range. Decide: either suppress the merge, or accept the mixed display.

Recommendation: split the range at the format boundary so the display reads `iv, 7` rather than `iv-7`. Less ambiguous to readers.

- [ ] **Step 2: Update `process_results` to split at format boundary**

Replace the existing range-building loop:

```python
current_range = [pages[0]]

for i in range(1, len(pages)):
    prev_idx = pages[i-1][0]
    curr_idx = pages[i][0]

    if curr_idx == prev_idx + 1:
        current_range.append(pages[i])
    else:
        ranges.append(current_range)
        current_range = [pages[i]]
ranges.append(current_range)
```

with:

```python
def _label_format(label: str) -> str:
    return "roman" if looks_like_roman(label) else "arabic"

current_range = [pages[0]]

for i in range(1, len(pages)):
    prev_idx = pages[i-1][0]
    curr_idx = pages[i][0]
    prev_fmt = _label_format(pages[i-1][1])
    curr_fmt = _label_format(pages[i][1])

    if curr_idx == prev_idx + 1 and prev_fmt == curr_fmt:
        current_range.append(pages[i])
    else:
        ranges.append(current_range)
        current_range = [pages[i]]
ranges.append(current_range)
```

- [ ] **Step 3: Manual verification**

If you have access to a PDF with a known offset, run an index with `Index front matter (roman)` enabled (Task 14 will add the UI; for now this code path is exercised when the controller passes `index_front_matter=True`). Confirm a mixed entry reads `iv, vi, 12, 14-16` and not `iv-vi-12-...`.

- [ ] **Step 4: Commit**

```bash
git add model/indexer.py
git commit -m "feat(indexer): split ranges at roman/arabic format boundary"
```

---

## Task 12: Style-filter helper

A pure helper that takes the aggregate `raw_results` and a bucket name (`"italic"`, `"bold"`, `"caps"`, `"other"`, or `"aggregate"`) and returns a filtered raw_results dict. Used by both the file-output and the UI selector.

**Files:**
- Modify: `model/indexer.py`
- Create: `tests/test_style_filter.py`

- [ ] **Step 1: Write failing test**

`tests/test_style_filter.py`:

```python
from model.indexer import filter_by_style


def _occ(idx, label, **flags):
    return [idx, label, {
        "italic": flags.get("italic", False),
        "bold": flags.get("bold", False),
        "caps": flags.get("caps", False),
    }]


def test_aggregate_returns_full_dict():
    raw = {"alpha": [_occ(1, "1"), _occ(2, "2")]}
    out = filter_by_style(raw, "aggregate")
    assert out == raw


def test_italic_filters_to_italic_pages_only():
    raw = {
        "alpha": [_occ(1, "1", italic=True), _occ(2, "2"), _occ(3, "3", italic=True)],
        "beta": [_occ(5, "5")],
    }
    out = filter_by_style(raw, "italic")
    assert "alpha" in out
    assert len(out["alpha"]) == 2
    assert out["alpha"][0][0] == 1
    assert out["alpha"][1][0] == 3
    assert "beta" not in out  # no italic pages anywhere


def test_other_excludes_styled_pages():
    raw = {"alpha": [_occ(1, "1", italic=True), _occ(2, "2"), _occ(3, "3", caps=True)]}
    out = filter_by_style(raw, "other")
    assert len(out["alpha"]) == 1
    assert out["alpha"][0][0] == 2


def test_entry_dropped_when_no_pages_match():
    raw = {"alpha": [_occ(1, "1", italic=True)]}
    out = filter_by_style(raw, "bold")
    assert out == {}
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_style_filter.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `filter_by_style`**

Add to `model/indexer.py`:

```python
STYLE_BUCKETS = ("aggregate", "italic", "bold", "caps", "other")


def filter_by_style(raw_results: dict, bucket: str) -> dict:
    """Return a copy of *raw_results* filtered to occurrences matching *bucket*.

    bucket must be one of STYLE_BUCKETS.
    - "aggregate": returns raw_results unchanged.
    - "italic" / "bold" / "caps": keep only occurrences whose flag is True.
    - "other": keep only occurrences whose flags are all False.

    Entries with no matching occurrences are omitted from the result.
    """
    if bucket == "aggregate":
        return raw_results
    if bucket not in STYLE_BUCKETS:
        raise ValueError(f"Unknown bucket: {bucket}")

    out = {}
    for entry, occurrences in raw_results.items():
        kept = []
        for occ in occurrences:
            occ = normalise_occurrence(occ)
            flags = occ[2]
            if bucket == "other":
                if not (flags["italic"] or flags["bold"] or flags["caps"]):
                    kept.append(occ)
            else:
                if flags.get(bucket, False):
                    kept.append(occ)
        if kept:
            out[entry] = kept
    return out
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_style_filter.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add model/indexer.py tests/test_style_filter.py
git commit -m "feat(indexer): add filter_by_style helper for per-bucket views"
```

---

## Task 13: Per-style file output

When "Separate index files by style" is on, write `index-italic.{md,txt,html}`, `index-bold.{md,txt,html}`, `index-caps.{md,txt,html}`, `index-other.{md,txt,html}` alongside the aggregate `index.{md,txt,html,json}`. When off, delete any pre-existing per-style files.

**Files:**
- Modify: `controller/main_controller.py`

- [ ] **Step 1: Update `save_results_to_files`**

Replace the existing function with:

```python
def save_results_to_files(self, results):
    """Write the aggregate index in md/txt/html/json. When 'separate style files'
    is enabled, also write per-bucket md/txt/html files; otherwise clean up any
    stale per-bucket files from a previous run.
    """
    md_content = self.generate_markdown(results)
    txt_content = self.generate_text(results)
    html_content = self.generate_html(results)

    base = os.path.join(self.project_path, "index")
    with open(base + ".md", 'w', encoding='utf-8') as f:
        f.write(md_content)
    with open(base + ".txt", 'w', encoding='utf-8') as f:
        f.write(txt_content)
    with open(base + ".html", 'w', encoding='utf-8') as f:
        f.write(html_content)

    if self.last_raw_results is not None:
        with open(base + ".json", 'w', encoding='utf-8') as f:
            json.dump(self.last_raw_results, f, indent=2)

    separate = self.view.controls_output.separate_style_files_chk.isChecked() \
        if hasattr(self.view.controls_output, 'separate_style_files_chk') else False
    style_files = ["italic", "bold", "caps", "other"]
    for bucket in style_files:
        path_base = os.path.join(self.project_path, f"index-{bucket}")
        if separate and self.last_raw_results is not None:
            from model.indexer import filter_by_style, IndexingThread
            filtered_raw = filter_by_style(self.last_raw_results, bucket)
            capitalize = self.view.controls_output.capitalize_chk.isChecked()
            filtered_formatted = IndexingThread.process_results(
                None, filtered_raw, capitalize_keys=capitalize,
            )
            self._write_format_files(path_base, filtered_formatted)
        else:
            for ext in ("md", "txt", "html"):
                stale = path_base + f".{ext}"
                if os.path.exists(stale):
                    try:
                        os.remove(stale)
                    except OSError:
                        pass


def _write_format_files(self, path_base, formatted_results):
    md = self.generate_markdown(formatted_results)
    txt = self.generate_text(formatted_results)
    html = self.generate_html(formatted_results)
    for ext, content in (("md", md), ("txt", txt), ("html", html)):
        with open(path_base + f".{ext}", 'w', encoding='utf-8') as f:
            f.write(content)
```

- [ ] **Step 2: Manual smoke check**

```bash
python main.py
```

Open an indexed project. Re-index. Confirm the project directory now contains `index-italic.md`, `index-bold.md`, `index-caps.md`, `index-other.md`. Open one and verify it lists only entries with that style.

(The checkbox doesn't exist yet — the `hasattr` guard means `separate=False`, so per-style files won't be written until Task 14 lands. Confirm at minimum that the aggregate output is still produced.)

- [ ] **Step 3: Commit**

```bash
git add controller/main_controller.py
git commit -m "feat(controller): write per-style index files when option is enabled"
```

---

## Task 14: UI — new checkboxes

Add the three new checkboxes: `Index Italic`, `Index front matter (roman)`, `Separate index files by style`. Wire them to the autosave config persistence pipe.

**Files:**
- Modify: `view/controls_output.py`
- Modify: `controller/main_controller.py`
- Modify: `model/config.py`

- [ ] **Step 1: Add `Index front matter (roman)` checkbox**

In `view/controls_output.py`, in `__init__`, after the existing offset row:

```python
self.index_from_offset_chk = QCheckBox("Index only from offset")
self.index_from_offset_chk.setChecked(True)
self.controls_layout.addWidget(self.index_from_offset_chk)
```

Add right after:

```python
self.index_front_matter_chk = QCheckBox("Index front matter (roman)")
self.index_front_matter_chk.setChecked(True)
self.controls_layout.addWidget(self.index_front_matter_chk)
self.index_front_matter_chk.setEnabled(False)
```

Update the existing `_on_offset_changed` to also enable `index_front_matter_chk` only when offset < 0 AND `index_from_offset_chk` is on:

```python
def _on_offset_changed(self, value):
    """Enable front-matter related controls only when offset is negative."""
    self.index_from_offset_chk.setEnabled(value < 0)
    self.index_front_matter_chk.setEnabled(
        value < 0 and self.index_from_offset_chk.isChecked()
    )
```

Also re-evaluate when "Index only from offset" toggles:

```python
self.index_from_offset_chk.toggled.connect(
    lambda _: self._on_offset_changed(self.offset_spin.value())
)
```

- [ ] **Step 2: Add `Index Italic` and `Separate index files by style` checkboxes**

In the existing options row (where `Name Indexing` / `Index Bold Text` / `Surname First` already live), insert:

```python
self.index_italic_chk = QCheckBox("Index Italic")
self.index_italic_chk.setChecked(True)
self.name_options_layout.addWidget(self.index_italic_chk)
```

after `Index Bold Text` (i.e., between `bold_indexing_chk` and `surname_first_chk`).

After `surname_first_chk`:

```python
self.separate_style_files_chk = QCheckBox("Separate index files by style")
self.separate_style_files_chk.setChecked(True)
self.name_options_layout.addWidget(self.separate_style_files_chk)
```

- [ ] **Step 3: Persist new checkboxes in `set_state`**

In `set_state`, append:

```python
self.index_italic_chk.setChecked(config.get("index_italic", True))
self.separate_style_files_chk.setChecked(config.get("separate_style_files", True))
self.index_front_matter_chk.setChecked(config.get("index_front_matter_roman", True))
```

- [ ] **Step 4: Persist new checkboxes in controller config**

In `controller/main_controller.py`, `save_current_config`, add to the config dict:

```python
"index_italic": ctrl.index_italic_chk.isChecked(),
"separate_style_files": ctrl.separate_style_files_chk.isChecked(),
"index_front_matter_roman": ctrl.index_front_matter_chk.isChecked(),
```

Connect autosave for the new checkboxes (alongside the other `.toggled.connect(lambda: self.save_current_config())` lines):

```python
self.view.controls_output.index_italic_chk.toggled.connect(lambda: self.save_current_config())
self.view.controls_output.separate_style_files_chk.toggled.connect(lambda: self.save_current_config())
self.view.controls_output.index_front_matter_chk.toggled.connect(lambda: self.save_current_config())
```

When `separate_style_files_chk` toggles, also re-display the index (so the style selector bar shows/hides):

```python
self.view.controls_output.separate_style_files_chk.toggled.connect(
    lambda: self.update_output_display()
)
```

- [ ] **Step 5: Update `model/config.py`**

In `ConfigManager.DEFAULT_CONFIG`, add:

```python
"index_italic": True,
"separate_style_files": True,
"index_front_matter_roman": True,
"style_view": "aggregate",
```

- [ ] **Step 6: Replace stub guards in start_indexing/save_results_to_files**

Now that `index_italic_chk`, `separate_style_files_chk`, `index_front_matter_chk` exist, remove the `hasattr` guards added in earlier tasks:

In `start_indexing`:

```python
index_front_matter = self.view.controls_output.index_front_matter_chk.isChecked()
index_italic = self.view.controls_output.index_italic_chk.isChecked()
```

In `save_results_to_files`:

```python
separate = self.view.controls_output.separate_style_files_chk.isChecked()
```

- [ ] **Step 7: Manual smoke check**

```bash
python main.py
```

Confirm the new checkboxes appear, default ON, persist across project reload, and re-indexing with `Separate index files by style` ON now writes `index-italic.md` etc.

- [ ] **Step 8: Commit**

```bash
git add view/controls_output.py controller/main_controller.py model/config.py
git commit -m "feat(ui): add italic, front-matter, and separate-files checkboxes"
```

---

## Task 15: UI — style selector bar

Add a horizontal radio bar `Aggregate | Italic | Bold | Caps | Other` above the index output, visible only when `Separate index files by style` is on AND the current tab is one of `active`/`markdown`/`text`/`html`.

**Files:**
- Modify: `view/controls_output.py`

- [ ] **Step 1: Build the bar**

In `view/controls_output.py`, in `__init__`, near the existing `cloud_submode_bar` block, add:

```python
self.style_selector_bar = QWidget()
style_layout = QHBoxLayout()
style_layout.setContentsMargins(0, 2, 0, 2)
self.style_selector_bar.setLayout(style_layout)

self.style_bg = QButtonGroup(self)
self.style_aggregate_btn = QRadioButton("Aggregate")
self.style_italic_btn = QRadioButton("Italic")
self.style_bold_btn = QRadioButton("Bold")
self.style_caps_btn = QRadioButton("Caps")
self.style_other_btn = QRadioButton("Other")
self.style_aggregate_btn.setChecked(True)

for btn in (self.style_aggregate_btn, self.style_italic_btn,
            self.style_bold_btn, self.style_caps_btn, self.style_other_btn):
    self.style_bg.addButton(btn)
    style_layout.addWidget(btn)
style_layout.addStretch()

self.style_bg.buttonClicked.connect(self._on_style_changed)
self.style_selector_bar.setVisible(False)

# Place between the tab/source row and the search bar.
# The current insertion order in __init__ is:
#   0: tab_layout (addLayout)
#   1: search_input (addWidget)
#   2: output_text
#   ...
# So insertWidget(1, ...) puts the selector right above the search bar.
self.output_layout.insertWidget(1, self.style_selector_bar)
```

- [ ] **Step 2: Add a signal for selector changes**

Near the other `pyqtSignal` declarations:

```python
style_view_changed = pyqtSignal(str)  # "aggregate", "italic", "bold", "caps", "other"
```

And the slot:

```python
def _on_style_changed(self, btn):
    self.style_view_changed.emit(self.get_style_view())

def get_style_view(self) -> str:
    if self.style_italic_btn.isChecked():
        return "italic"
    if self.style_bold_btn.isChecked():
        return "bold"
    if self.style_caps_btn.isChecked():
        return "caps"
    if self.style_other_btn.isChecked():
        return "other"
    return "aggregate"
```

- [ ] **Step 3: Show/hide the bar based on tab + checkbox**

In `set_output`, add the visibility logic at the same point where other widgets are toggled:

```python
def set_output(self, content, format_type='text'):
    self.output_text.setVisible(False)
    self.cloud_scroll.setVisible(False)
    self.cloud_submode_bar.setVisible(False)
    self.cloud_hint_label.setVisible(False)
    self.merge_view.setVisible(False)
    self.reports_view.setVisible(False)
    self.style_selector_bar.setVisible(False)  # default hidden

    ...

    # The text-output formats (active/markdown/text/html):
    self.search_input.setVisible(True)
    if self.separate_style_files_chk.isChecked():
        self.style_selector_bar.setVisible(True)
    self._raw_content = content
    self._raw_format = format_type
    self._apply_filter()
```

- [ ] **Step 4: Persist selector state**

In `set_state`:

```python
mode_view = config.get("style_view", "aggregate")
btn = {
    "aggregate": self.style_aggregate_btn,
    "italic": self.style_italic_btn,
    "bold": self.style_bold_btn,
    "caps": self.style_caps_btn,
    "other": self.style_other_btn,
}.get(mode_view, self.style_aggregate_btn)
btn.setChecked(True)
```

- [ ] **Step 5: Commit**

```bash
git add view/controls_output.py
git commit -m "feat(ui): add style selector bar above the index output"
```

---

## Task 16: Controller — apply style filter to display

The selector should drive what the Active / Markdown / Text / HTML tabs show. Filter `last_raw_results` through `filter_by_style` before rendering, recompute the entry count, and keep the existing search-filter / page-jump behaviour intact.

**Files:**
- Modify: `controller/main_controller.py`

- [ ] **Step 1: Add a wiring connection**

In `MainController.__init__`, add:

```python
self.view.controls_output.style_view_changed.connect(self._on_style_view_changed)
```

- [ ] **Step 2: Add the slot and refactor display generation**

```python
def _on_style_view_changed(self, _bucket):
    self.save_current_config()
    self.process_and_display_results()
```

Update `save_current_config` to persist the selector:

```python
"style_view": ctrl.get_style_view(),
```

Update `process_and_display_results` to filter:

```python
def process_and_display_results(self):
    if not self.last_raw_results:
        return

    capitalize = self.view.controls_output.capitalize_chk.isChecked()
    bucket = self.view.controls_output.get_style_view()

    from model.indexer import filter_by_style
    if (bucket != "aggregate"
            and self.view.controls_output.separate_style_files_chk.isChecked()):
        view_raw = filter_by_style(self.last_raw_results, bucket)
    else:
        view_raw = self.last_raw_results

    formatted = IndexingThread.process_results(None, view_raw, capitalize_keys=capitalize)
    self.last_formatted_results = formatted
    self.view.controls_output._total_entry_count = len(formatted)
    self.view.controls_output.entry_count_label.setText(f"{len(formatted)} entries")

    # Save files (always uses the unfiltered aggregate; filter_by_style is applied
    # internally per bucket inside save_results_to_files).
    if self.project_path:
        full_formatted = IndexingThread.process_results(
            None, self.last_raw_results, capitalize_keys=capitalize,
        )
        self.save_results_to_files(full_formatted)

    self.update_output_display()
```

The `last_formatted_results` now tracks the *currently displayed* (possibly filtered) view, while files-on-disk always reflect the aggregate plus the per-bucket variants. Active-link clicks (which read `last_raw_results`, not `last_formatted_results`) continue to navigate to the right pages because page indices in the filtered view are the original ones.

`update_output_display` regenerates the displayed content from `last_formatted_results`. It needs the filtered raw_results too when generating Active HTML:

```python
elif mode == "active":
    capitalize = ctrl.capitalize_chk.isChecked()
    bucket = ctrl.get_style_view()
    from model.indexer import filter_by_style
    if (bucket != "aggregate"
            and ctrl.separate_style_files_chk.isChecked()):
        active_raw = filter_by_style(self.last_raw_results, bucket)
    else:
        active_raw = self.last_raw_results
    content = self._generate_active_html_for(active_raw)
    format_type = 'active'
```

Refactor `generate_active_html` to take a raw_results dict:

```python
def generate_active_html(self, results):
    """Existing format-switching helper — keep for backwards compatibility."""
    return self._generate_active_html_for(self.last_raw_results)


def _generate_active_html_for(self, raw_results):
    if not raw_results:
        return ""
    # Body is identical to the existing generate_active_html, but parameterised
    # on raw_results instead of self.last_raw_results.
    ... (existing body, swap self.last_raw_results for raw_results)
```

- [ ] **Step 3: Manual smoke check**

```bash
python main.py
```

Re-index. Switch the style selector through Aggregate / Italic / Bold / Caps / Other — confirm the displayed entries change, the count label updates, clicking a page number still jumps to the right page, and the search-filter still works on the filtered subset.

- [ ] **Step 4: Commit**

```bash
git add controller/main_controller.py
git commit -m "feat(controller): apply style selector to displayed index"
```

---

## Task 17: HELP.md updates

**Files:**
- Modify: `HELP.md`

- [ ] **Step 1: Update the Keyword Indexing section**

Below the existing `Capitalize Entries` line, add:

```markdown
**Index Italic** — capture italic phrases as separate index entries, even when they are not capitalised (e.g., italic book titles or foreign-language phrases). Default on.

**Separate index files by style** — when on, generates `index-italic`, `index-bold`, `index-caps`, and `index-other` files alongside the aggregate `index` files. Each per-style file lists only entries (and only the page numbers) that matched that style. The aggregate `index.json` carries every flag and is the source of truth — the per-style markdown/text/html files are derived from it on each save. A radio bar above the index output (`Aggregate | Italic | Bold | Caps | Other`) lets you view any single bucket in the Active / Markdown / Text / HTML tabs; reports, the merge tool, and the tag cloud always operate on the aggregate.

**Index front matter (roman)** — when offset is negative and *Index only from offset* is on, this option also indexes the front-matter pages (1 .. offset) using lowercase roman numerals (i, ii, iii, ...). The PDF's own page label is used when it is itself roman; otherwise the physical page number is converted. Default on.
```

- [ ] **Step 2: Update the Name Indexing rules table**

Replace this row in the rules table:

```markdown
| **All-caps words** | *INTRODUCTION*, *CHAPTER*, etc. always break the sequence (treated as section-header text, not names). |
```

with:

```markdown
| **All-caps words** | Single all-caps tokens like *NATO* and *CERN* on a mixed-case line are admitted as name candidates and tagged with the *caps* style. Tokens on a fully all-caps line (*INTRODUCTION*, *CHAPTER 3*) are skipped — those are headings. |
```

Add a new row for italic capture below the existing `Connector words` row:

```markdown
| **Italic phrases** | Independent of the capitalisation rules: a contiguous run of italic-styled tokens is captured as an index entry, with connectors kept ("The Sound of Music"). Punctuation or a non-italic word ends the run. Each captured entry is tagged with the *italic* style. |
```

- [ ] **Step 3: Update the Output Formats list**

Add to the bullet list:

```markdown
- **Style selector** — `Aggregate | Italic | Bold | Caps | Other` radio bar above the index output (visible when *Separate index files by style* is on). Filters the displayed entries to those that have at least one occurrence in the selected style; page numbers within the filtered entries also restrict to that style.
```

- [ ] **Step 4: Commit**

```bash
git add HELP.md
git commit -m "docs: document style-aware indexing options and behaviour"
```

---

## Self-Review Checklist (run before declaring done)

- [ ] All seven test files exist and `pytest tests/ -v` reports all green.
- [ ] Indexing an existing project loads with no exceptions, the JSON file contains 3-tuple occurrences with `italic`/`bold`/`caps` flags.
- [ ] Toggling `Index Italic` off no longer captures pure-italic phrases on re-index.
- [ ] A negative offset with `Index only from offset` on AND `Index front matter (roman)` on produces entries with roman labels for content in the front matter.
- [ ] `Separate index files by style` produces five sets of files (aggregate + four buckets); toggling off deletes the per-bucket files and only the aggregate remains.
- [ ] The style selector bar shows when separate-files is on and a text tab is active; toggling Aggregate / Italic / Bold / Caps / Other changes the displayed entries; clicking a page number still navigates the PDF correctly.
- [ ] An entry that appears italic on one page and plain on another shows both pages in Aggregate, only the italic page in Italic, and only the plain page in Other.
- [ ] HELP.md describes the three new checkboxes and the selector bar.

---

## Spec Coverage

| Spec requirement | Implementing task |
|---|---|
| 3-tuple data model with italic/bold/caps flags | Task 5 |
| Lexical override at line/block boundaries | Task 4 |
| Hyphenation join | Task 4 |
| All-caps surfacing on `StyledToken` | Task 4 |
| Single all-caps tokens admitted as candidates | Task 6 |
| Italic n-gram capture | Task 7 |
| Name indexer flag propagation | Task 8 |
| Keyword indexer rewrite using styled tokens + flag propagation | Task 9 |
| Front-matter (roman) pass for both indexers | Task 10 |
| Range compression with mixed roman/arabic labels | Task 11 |
| `filter_by_style` helper | Task 12 |
| Per-style file output | Task 13 |
| New checkboxes (italic, front-matter, separate-files) | Task 14 |
| Style selector radio bar | Task 15 |
| Controller wiring and active-tab filtering | Task 16 |
| Config persistence keys | Task 14 |
| HELP.md updates | Task 17 |
| Backwards compatibility (legacy 2-tuple JSON load) | Task 5 |
