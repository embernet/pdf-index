import fitz
import re
import string
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from PyQt6.QtCore import QThread, pyqtSignal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Lowercase connector words that break capitalized n-gram sequences.
# "The" is intentionally NOT here because it commonly starts proper nouns.
CONNECTOR_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from",
    "if", "in", "into", "is", "it", "no", "nor", "not", "of",
    "on", "or", "so", "than", "that", "to", "up", "with",
    "was", "were", "are", "be", "been", "being", "do", "does",
    "did", "has", "have", "had", "go", "goes", "went", "will",
    "would", "could", "should", "may", "might", "can", "shall",
    "this", "these", "those", "there", "here", "where", "when",
    "which", "who", "whom", "whose", "what", "how", "then",
    "very", "also", "just", "about", "over", "under", "between",
    "through", "during", "before", "after", "above", "below",
    "each", "every", "all", "both", "few", "more", "most",
    "other", "some", "such", "only", "own", "same",
}

# Common words that are often capitalised only because they start a sentence.
SENTENCE_START_IGNORE = {
    "the", "a", "an", "this", "these", "those", "it", "its",
    "he", "she", "we", "they", "his", "her", "our", "their",
    "there", "here", "however", "although", "because", "since",
    "while", "when", "after", "before", "such", "many", "most",
    "some", "several", "few", "other", "another", "any", "each",
    "every", "no", "not", "if", "but", "yet", "so", "or",
    "for", "nor", "as", "at", "by", "from", "in", "into",
    "on", "to", "with", "that", "what", "which", "who",
}

# Document-structural words that look like proper nouns but aren't names.
STRUCTURAL_WORDS = {
    "chapter", "section", "figure", "table", "part", "volume",
    "introduction", "conclusion", "abstract", "references",
    "bibliography", "appendix", "index", "contents", "preface",
    "foreword", "acknowledgements", "acknowledgments", "glossary",
    "note", "notes", "see", "also", "ibid", "op", "cit",
    "et", "al", "ed", "eds", "trans", "rev", "vol", "no",
    "pp", "pg",
}

# Title prefixes: skip these tokens but do NOT break the n-gram.
TITLE_PREFIXES = {
    "dr", "mr", "mrs", "ms", "prof", "rev", "st", "sir", "dame",
    "lord", "lady", "hon", "sr", "jr",
}

# Sentence-ending punctuation characters.
SENTENCE_END_CHARS = {'.', '?', '!'}

# Regex for detecting Roman numerals.
_ROMAN_RE = re.compile(r'^[IVXLCDM]+$')

# Regex to split span text into word tokens and punctuation.
# Matches: word chars (including hyphens/apostrophes inside), OR single punctuation.
_TOKEN_RE = re.compile(r"[\w][\w'\u2019-]*[\w]|[\w]|[^\s\w]", re.UNICODE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StyledToken:
    text: str
    is_bold: bool
    is_italic: bool
    is_superscript: bool


@dataclass
class NameGroup:
    longest_form: str
    variations: Set[str] = field(default_factory=set)
    occurrences_by_variation: Dict[str, List[Tuple[int, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_punctuation(text: str) -> bool:
    """Return True if *text* consists entirely of punctuation characters."""
    return all(unicodedata.category(ch).startswith('P') or ch in '()[]{}' for ch in text)


def _is_all_caps_word(word: str) -> bool:
    """True if word is >=2 alpha chars and entirely uppercase."""
    return len(word) > 1 and word.isalpha() and word == word.upper()


def _is_roman_numeral(word: str) -> bool:
    return bool(_ROMAN_RE.match(word)) and len(word) <= 8


def _is_number_like(word: str) -> bool:
    """True for pure digits or digit-heavy tokens like '2nd', '3rd'."""
    return word.isdigit() or (len(word) <= 4 and any(ch.isdigit() for ch in word))


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

def extract_styled_tokens(page) -> List[StyledToken]:
    """Extract word-level tokens with bold/italic/superscript flags from a page.

    Uses ``page.get_text("dict")`` so we get per-span font-flag info.
    PyMuPDF span flags: bit 0 = superscript, bit 1 = italic, bit 4 = bold.
    """
    data = page.get_text("dict")
    tokens: List[StyledToken] = []

    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:  # skip image blocks
            continue

        # Insert a synthetic sentence-end token between blocks so that
        # the first word of a new paragraph/heading is recognised as
        # sentence-initial (e.g. "Chapter" at the top of a page).
        if tokens:
            tokens.append(StyledToken(
                text=".", is_bold=False, is_italic=False,
                is_superscript=False,
            ))

        for line in block.get("lines", []):
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

    return tokens


# ---------------------------------------------------------------------------
# Detecting all-caps lines
# ---------------------------------------------------------------------------

def _line_is_all_caps(line_spans) -> bool:
    """Return True if every alphabetic word in a line dict is fully uppercase."""
    words = []
    for span in line_spans:
        for m in _TOKEN_RE.finditer(span.get("text", "")):
            w = m.group()
            if w.isalpha():
                words.append(w)
    if not words:
        return False
    return all(w == w.upper() for w in words)


def _get_all_caps_line_indices(page) -> Set[int]:
    """Return set of line indices (block_idx, line_idx) whose text is all-caps."""
    data = page.get_text("dict")
    all_caps = set()
    line_counter = 0
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            if _line_is_all_caps(line.get("spans", [])):
                all_caps.add(line_counter)
            line_counter += 1
    return all_caps


# ---------------------------------------------------------------------------
# Name candidate identification
# ---------------------------------------------------------------------------

def extract_names_from_tokens(
    tokens: List[StyledToken],
    discovery_mode: bool = False,
    include_bold: bool = False,
    exclude_words: Set[str] | None = None,
) -> List[str]:
    """Scan token sequence and build n-grams of consecutive 'name words'.

    Rules:
    - A word qualifies if its first char is uppercase (Unicode-aware) OR it is
      styled (bold when *include_bold* is True, or italic).
    - Connector words (and, of, to, ...) in lowercase break the n-gram unless
      the word is styled.
    - Superscript tokens (footnote numbers) are skipped.
    - Punctuation flushes and breaks the current n-gram.
    - Structural words (Chapter, Section, ...) always break the n-gram
      regardless of styling.

    When *discovery_mode* is True (pass 1), ALL sentence-initial capitalised
    words are skipped so that only names confirmed by mid-sentence usage
    enter the vocabulary.  When False (legacy behaviour), only common
    sentence-starters in SENTENCE_START_IGNORE are skipped.

    *exclude_words* is a set of lowercased words that always break the n-gram
    (user-supplied exclusion list).
    """
    if exclude_words is None:
        exclude_words = set()

    names: List[str] = []
    current_ngram: List[str] = []
    after_sentence_end = False

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        # Skip superscript (footnote numbers)
        if token.is_superscript:
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            continue

        # Punctuation handling
        if _is_punctuation(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            if word in SENTENCE_END_CHARS:
                after_sentence_end = True
            continue

        word_lower = word.lower()
        is_styled = (token.is_bold and include_bold) or token.is_italic

        # Filter: user-excluded words (always break n-gram)
        if word_lower in exclude_words:
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            after_sentence_end = False
            continue

        # Filter: structural words (Chapter, Section, ...) — unconditional
        if word_lower in STRUCTURAL_WORDS:
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            after_sentence_end = False
            continue

        # Filter: Roman numerals — unconditional
        if _is_roman_numeral(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            after_sentence_end = False
            continue

        # Filter: number-like tokens
        if _is_number_like(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            after_sentence_end = False
            continue

        # Title prefixes: skip the word but keep building the n-gram
        if word_lower.rstrip('.') in TITLE_PREFIXES:
            after_sentence_end = False
            continue

        # Connector words always break the n-gram
        if word_lower in CONNECTOR_WORDS:
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            after_sentence_end = False
            continue

        # Determine if this is a "name word"
        is_name_word = False

        if word[0].isupper():
            # Sentence-initial capitalisation check
            if after_sentence_end:
                if discovery_mode or word_lower in SENTENCE_START_IGNORE:
                    # In discovery mode skip ALL sentence-initial caps;
                    # otherwise only skip common starters.
                    after_sentence_end = False
                    if current_ngram:
                        names.append(" ".join(current_ngram))
                        current_ngram = []
                    continue
            is_name_word = True

        if is_styled:
            is_name_word = True

        after_sentence_end = False

        # All-caps words (section titles like "INTRODUCTION") — always skip.
        if _is_all_caps_word(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            continue

        if is_name_word:
            current_ngram.append(word)
        else:
            # Lowercase non-styled, non-connector word: breaks n-gram
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []

    # Flush any remaining n-gram
    if current_ngram:
        names.append(" ".join(current_ngram))

    return names


# ---------------------------------------------------------------------------
# Known-name search (pass 2)
# ---------------------------------------------------------------------------

def find_known_names_in_tokens(
    tokens: List[StyledToken],
    known_names: Set[str],
    known_names_lower: Dict[str, str],
    max_ngram_len: int,
) -> List[str]:
    """Find all occurrences of *known_names* in *tokens*, regardless of
    sentence position.  Returns a list of matched names (original casing
    from the vocabulary)."""

    # Build a list of "word" tokens (skip punct / superscript / structural)
    word_tokens: List[str] = []
    for token in tokens:
        word = token.text.strip()
        if not word:
            continue
        if token.is_superscript:
            continue
        if _is_punctuation(word):
            # Insert a sentinel to prevent cross-sentence matching
            word_tokens.append(None)
            continue
        word_tokens.append(word)

    found: List[str] = []
    n_tokens = len(word_tokens)

    for i in range(n_tokens):
        if word_tokens[i] is None:
            continue
        # Try n-grams from longest to shortest for greedy matching
        for length in range(min(max_ngram_len, n_tokens - i), 0, -1):
            # Check no sentinel in span
            span = word_tokens[i:i + length]
            if None in span:
                break
            candidate = " ".join(span)
            canon = known_names_lower.get(candidate.lower())
            if canon is not None:
                found.append(canon)
                break  # greedy: take longest match starting at i

    return found


# ---------------------------------------------------------------------------
# Cleaning / filtering
# ---------------------------------------------------------------------------

def clean_name(name: str) -> str:
    name = unicodedata.normalize('NFKC', name)
    name = name.strip()
    # Strip leading/trailing punctuation (but not apostrophes inside names)
    name = name.strip(string.punctuation + '\u2018\u2019\u201c\u201d')
    return name


def filter_names(names: List[str]) -> List[str]:
    filtered = []
    for name in names:
        name = clean_name(name)
        if not name:
            continue
        if len(name) <= 1:
            continue
        if name.isdigit():
            continue
        filtered.append(name)
    return filtered


# ---------------------------------------------------------------------------
# N-gram consolidation
# ---------------------------------------------------------------------------

def is_contiguous_subsequence(short_words: List[str], long_words: List[str]) -> bool:
    """Check if short_words appears as a contiguous sub-sequence in long_words
    (case-insensitive)."""
    s_len = len(short_words)
    l_len = len(long_words)
    for start in range(l_len - s_len + 1):
        if all(
            short_words[j].lower() == long_words[start + j].lower()
            for j in range(s_len)
        ):
            return True
    return False


def build_ngram_groups(
    all_occurrences: Dict[str, List[Tuple[int, str]]]
) -> List[NameGroup]:
    """Group terms where shorter terms are contiguous sub-n-grams of longer ones."""
    terms = list(all_occurrences.keys())
    # Sort by word count descending so longest forms are processed first
    terms.sort(key=lambda t: (-len(t.split()), t.lower()))

    assigned: Dict[str, str] = {}  # term -> group leader
    groups: Dict[str, NameGroup] = {}

    for term in terms:
        if term in assigned:
            continue

        term_words = term.split()
        group = NameGroup(
            longest_form=term,
            variations={term},
            occurrences_by_variation=defaultdict(list),
        )
        group.occurrences_by_variation[term] = all_occurrences[term]
        assigned[term] = term

        # Find shorter terms that are sub-n-grams
        for other in terms:
            if other == term or other in assigned:
                continue
            other_words = other.split()
            if len(other_words) >= len(term_words):
                continue
            if is_contiguous_subsequence(other_words, term_words):
                group.variations.add(other)
                group.occurrences_by_variation[other] = all_occurrences[other]
                assigned[other] = term

        groups[term] = group

    return list(groups.values())


def resolve_group_pages(
    group: NameGroup,
) -> Dict[str, List[Tuple[int, str]]]:
    """Determine display entries and their page lists for a single NameGroup.

    - The longest form entry gets all pages where it appears directly.
    - A shorter variation gets its own entry only for pages where it appears
      but the longest form does NOT appear on that same page.
    """
    longest = group.longest_form
    longest_page_indices = {
        p[0] for p in group.occurrences_by_variation.get(longest, [])
    }

    result: Dict[str, List[Tuple[int, str]]] = {}

    # Longest form entry
    longest_pages = group.occurrences_by_variation.get(longest, [])
    if longest_pages:
        display_key = format_name_entry(longest)
        # Deduplicate by page index
        seen = set()
        deduped = []
        for p in longest_pages:
            if p[0] not in seen:
                seen.add(p[0])
                deduped.append(p)
        result[display_key] = sorted(deduped, key=lambda x: x[0])

    # Shorter variations: orphan pages only
    for variation, occurrences in group.occurrences_by_variation.items():
        if variation == longest:
            continue
        orphan_pages: Dict[int, str] = {}
        for page_idx, page_label in occurrences:
            if page_idx not in longest_page_indices:
                orphan_pages[page_idx] = page_label
        if orphan_pages:
            result[variation] = sorted(orphan_pages.items(), key=lambda x: x[0])

    return result


def format_name_entry(name: str) -> str:
    """Format for index display.  Two-word names become 'Surname, Firstname'."""
    words = name.split()
    if len(words) == 2:
        return f"{words[1]}, {words[0]}"
    return name


# ---------------------------------------------------------------------------
# Threading wrapper
# ---------------------------------------------------------------------------

class NameIndexingThread(QThread):
    progress_updated = pyqtSignal(int)
    indexing_finished = pyqtSignal(dict, dict)  # formatted_results, raw_results
    error_occurred = pyqtSignal(str)

    def __init__(self, pdf_path, page_numbering_strategy, offset=0,
                 include_bold=False, exclude_words=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.strategy = page_numbering_strategy
        self.offset = offset
        self.include_bold = include_bold
        self.exclude_words = exclude_words or set()
        self._is_running = True

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)

            # ----------------------------------------------------------
            # Pass 1 – Discovery  (0-40 %)
            # Extract names using strict sentence-initial filtering so
            # only names confirmed by mid-sentence usage enter the vocab.
            # ----------------------------------------------------------
            name_vocabulary: Set[str] = set()

            for i in range(total_pages):
                if not self._is_running:
                    break

                page = doc.load_page(i)
                tokens = extract_styled_tokens(page)
                raw_names = extract_names_from_tokens(
                    tokens, discovery_mode=True,
                    include_bold=self.include_bold,
                    exclude_words=self.exclude_words,
                )
                names = filter_names(raw_names)
                name_vocabulary.update(names)

                progress = int((i + 1) / total_pages * 40)
                self.progress_updated.emit(progress)

            if not self._is_running:
                doc.close()
                return

            if not name_vocabulary:
                doc.close()
                self.progress_updated.emit(100)
                self.indexing_finished.emit({}, {})
                return

            # Build lookup structures for pass 2
            known_names_lower: Dict[str, str] = {}
            max_ngram_len = 1
            for name in name_vocabulary:
                known_names_lower[name.lower()] = name
                max_ngram_len = max(max_ngram_len, len(name.split()))

            # ----------------------------------------------------------
            # Pass 2 – Indexing  (40-75 %)
            # Search every page for ALL occurrences of known names,
            # including those at the start of sentences.
            # ----------------------------------------------------------
            all_occurrences: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

            for i in range(total_pages):
                if not self._is_running:
                    break

                page = doc.load_page(i)
                page_label = self._compute_label(page, i)
                tokens = extract_styled_tokens(page)

                found_names = find_known_names_in_tokens(
                    tokens, name_vocabulary, known_names_lower, max_ngram_len,
                )

                seen_on_page: Set[str] = set()
                for name in found_names:
                    if name not in seen_on_page:
                        seen_on_page.add(name)
                        all_occurrences[name].append((i, page_label))

                progress = 40 + int((i + 1) / total_pages * 35)
                self.progress_updated.emit(progress)

            doc.close()

            if not self._is_running:
                return

            # ----------------------------------------------------------
            # Phase 3 – N-gram consolidation  (75-90 %)
            # ----------------------------------------------------------
            self.progress_updated.emit(80)
            groups = build_ngram_groups(all_occurrences)

            self.progress_updated.emit(85)

            raw_results: Dict[str, List[Tuple[int, str]]] = {}
            for group in groups:
                entries = resolve_group_pages(group)
                raw_results.update(entries)

            # Remove any entries matching user-excluded words
            if self.exclude_words:
                raw_results = {
                    k: v for k, v in raw_results.items()
                    if k.lower() not in self.exclude_words
                }

            self.progress_updated.emit(90)

            # Phase 4: format using the existing range-compression helper
            from model.indexer import IndexingThread
            formatted_results = IndexingThread.process_results(
                None, raw_results, capitalize_keys=False
            )

            self.progress_updated.emit(100)
            self.indexing_finished.emit(formatted_results, raw_results)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))

    def stop(self):
        self._is_running = False

    def _compute_label(self, page, index):
        if self.strategy == 'logical':
            label = page.get_label()
            return label if label else str(index + 1)
        return str(index + self.offset)
