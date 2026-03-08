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
    "once", "then", "now", "still", "also", "just", "even",
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

# Default stopwords – common English words that should never appear as
# standalone entries in a name index.  They may still appear as PART of a
# multi-word name (e.g. "The Guardian", "The Hague") but will never start
# a new n-gram on their own.
DEFAULT_STOPWORDS = {
    # Articles
    "the", "a", "an",
    # Pronouns
    "he", "she", "it", "we", "they", "i", "you",
    "his", "her", "its", "our", "their", "my", "your",
    "him", "them", "us", "me",
    "himself", "herself", "itself", "themselves", "ourselves",
    # Demonstratives
    "this", "that", "these", "those",
    # Common verbs / auxiliaries
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did",
    "will", "would", "shall", "should",
    "can", "could", "may", "might", "must",
    "need", "ought",
    # Prepositions
    "in", "on", "at", "to", "for", "from", "by", "with",
    "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "under", "over", "up", "down",
    "out", "off", "near", "around", "against", "along", "across",
    "behind", "beyond", "within", "without", "upon", "toward",
    "towards", "among", "amongst", "beside", "besides",
    # Conjunctions
    "and", "but", "or", "nor", "yet", "so",
    "although", "though", "because", "since", "while", "when",
    "where", "if", "unless", "until", "whether", "than",
    # Adverbs / common sentence starters
    "however", "therefore", "moreover", "furthermore",
    "nevertheless", "nonetheless", "meanwhile", "consequently",
    "subsequently", "accordingly", "alternatively", "additionally",
    "specifically", "particularly", "generally", "typically",
    "essentially", "basically", "obviously", "clearly",
    "certainly", "undoubtedly", "indeed", "naturally",
    "apparently", "presumably", "arguably", "significantly",
    "importantly", "notably", "interestingly", "surprisingly",
    "unfortunately", "fortunately", "ultimately", "eventually",
    "initially", "finally", "perhaps", "maybe", "probably",
    "possibly", "definitely", "surely",
    # Determiners / quantifiers
    "some", "any", "many", "much", "few", "several",
    "each", "every", "all", "both", "no", "none",
    "other", "another", "either", "neither",
    "most", "more", "less", "least",
    # Common adjectives / adverbs
    "such", "same", "own", "only", "very",
    "also", "just", "even", "still", "already",
    "always", "never", "sometimes", "often", "usually",
    "quite", "rather", "too",
    # Locative / temporal
    "there", "here", "then", "now", "today", "yesterday",
    "tomorrow", "ago",
    # Interrogatives
    "how", "why", "what", "which", "who", "whom", "whose",
    # Other common words
    "not", "yes", "no",
    "one", "two", "three", "first", "second", "third",
    "new", "old", "good", "great", "last", "next",
    "early", "late",
    "once", "twice", "again", "away", "back", "much",
    "long", "far", "near", "soon", "later", "earlier",
    "almost", "enough", "together", "alone", "apart",
}

# Common English words that appear in organisation / place / event names
# but are NOT plausible surnames.  Used by format_name_entry to avoid
# inverting names like "Dublin International" → "International, Dublin".
NON_PERSON_NAME_WORDS = {
    # Geographic / directional
    "north", "south", "east", "west", "northern", "southern",
    "eastern", "western", "central", "upper", "lower", "greater",
    "new", "old", "grand", "great", "little", "big",
    "saint", "mount", "lake", "river", "island", "bay",
    "cape", "fort", "point", "springs", "falls", "valley",
    "hills", "heights", "forest", "beach", "harbor", "harbour",
    # Organisational / institutional
    "international", "national", "federal", "royal", "general",
    "united", "american", "british", "european", "african", "asian",
    "university", "institute", "foundation", "association",
    "corporation", "committee", "commission", "council",
    "department", "ministry", "academy", "society", "organization",
    "organisation", "company", "group", "club", "museum", "library",
    "hospital", "church", "school", "college", "centre", "center",
    "theatre", "theater", "gallery", "stadium", "memorial",
    "monument", "prize", "award", "festival", "competition",
    "conference", "congress", "summit", "forum", "olympic",
    # Infrastructure
    "street", "road", "avenue", "boulevard", "square", "bridge",
    "station", "airport", "port", "building", "tower", "palace",
    "castle", "cathedral", "park",
    # Political / administrative
    "state", "city", "county", "district", "republic", "kingdom",
    "empire", "province", "territory",
    # Academic / professional titles and roles
    "professor", "lecturer", "dean", "chancellor", "provost",
    "director", "president", "chairman", "chairwoman",
    "secretary", "minister", "ambassador", "governor",
}

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


# Regex matching footnote-reference-like tokens: digits and/or common
# footnote symbols (†, ‡, §, ¶, *).  Only these should be skipped when
# they carry the superscript flag — real words that happen to share a
# superscript span (common in footnote body text) must be kept.
_FOOTNOTE_REF_RE = re.compile(r'^[\d†‡§¶*]+$')


def _is_footnote_ref(text: str) -> bool:
    """Return True if *text* looks like a footnote reference number/symbol."""
    return bool(_FOOTNOTE_REF_RE.match(text))


def _last_text_char(block) -> str:
    """Return the last non-whitespace character in a text block, or ''."""
    for line in reversed(block.get("lines", [])):
        for span in reversed(line.get("spans", [])):
            text = span.get("text", "").rstrip()
            if text:
                return text[-1]
    return ''


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

    text_blocks = [b for b in data.get("blocks", [])
                   if b.get("type", 0) == 0]

    # Estimate the text column width from bounding boxes of all lines.
    # A line whose width fills the column is a wrapped line (text continues
    # in the next block), NOT the end of a paragraph.  This lets names like
    # "Ben Powell" be detected even when the PDF splits them across blocks.
    min_left = float('inf')
    max_right = 0.0
    for blk in text_blocks:
        for ln in blk.get("lines", []):
            bbox = ln.get("bbox")
            if bbox:
                min_left = min(min_left, bbox[0])
                max_right = max(max_right, bbox[2])
    col_width = (max_right - min_left) if max_right > min_left else 0

    prev_block = None

    for block in text_blocks:
        # Between blocks, decide whether to insert a synthetic sentence-end.
        # If the previous block's last line fills the column width, the text
        # is wrapping (not ending a paragraph) and we should NOT break any
        # name n-gram that spans the boundary.
        if tokens and prev_block is not None:
            insert_sep = True
            if col_width > 0:
                prev_lines = prev_block.get("lines", [])
                if prev_lines:
                    last_bbox = prev_lines[-1].get("bbox")
                    if last_bbox:
                        line_w = last_bbox[2] - last_bbox[0]
                        if line_w >= col_width * 0.9:
                            insert_sep = False

            # Only insert a synthetic sentence-end when the previous
            # block's text actually ends with sentence-ending punctuation.
            # Many PDFs split a single sentence or phrase across blocks
            # (e.g. "Dublin International" / "Piano Competition"); blindly
            # inserting "." would break legitimate multi-word names.
            if insert_sep:
                last_ch = _last_text_char(prev_block)
                if last_ch and last_ch not in SENTENCE_END_CHARS:
                    insert_sep = False

            if insert_sep:
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

        prev_block = block

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
    stopwords: Set[str] | None = None,
) -> List[str]:
    """Scan token sequence and build n-grams of consecutive 'name words'.

    Rules:
    - A word qualifies if its first char is uppercase (Unicode-aware).
    - Bold/italic styling (when *include_bold* is True for bold) only helps
      capitalised words bypass the sentence-initial filter; it does NOT
      promote lowercase words to name candidates.
    - Connector words (and, of, to, ...) always break the n-gram.
    - Superscript tokens (footnote numbers) are skipped.
    - Punctuation flushes and breaks the current n-gram.
    - Structural words (Chapter, Section, ...) always break the n-gram.
    - Stopwords never *start* a new n-gram but may extend an existing one
      (to allow multi-word names like "The Guardian").

    When *discovery_mode* is True (pass 1), ALL sentence-initial capitalised
    words are skipped (unless styled) so that only names confirmed by
    mid-sentence usage enter the vocabulary.  When False, only common
    sentence-starters in SENTENCE_START_IGNORE are skipped.

    *exclude_words* is a set of lowercased words the user wants excluded from
    the index.  An excluded word may still appear INSIDE a multi-word name
    (e.g. "piano" excluded, but "Dublin International Piano Competition"
    stays intact).  Standalone excluded entries are removed later.

    *stopwords* is a set of lowercased words that are prevented from starting
    a new n-gram (but may extend an existing one).
    """
    if exclude_words is None:
        exclude_words = set()
    if stopwords is None:
        stopwords = set()

    names: List[str] = []
    current_ngram: List[str] = []
    after_sentence_end = True  # Start of page is effectively a sentence boundary

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        # Skip superscript footnote reference numbers (e.g. "75", "†").
        # Real words that happen to be in a superscript span (common when
        # the PDF groups footnote body text with the reference marker) are
        # kept so that names in footnotes are indexed correctly.
        if token.is_superscript and _is_footnote_ref(word):
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

        # Filter: user-excluded words.
        # Excluded words may still appear INSIDE multi-word names (e.g.
        # "piano" is excluded but "Dublin International Piano Competition"
        # should stay as one entry).  So excluded words extend an existing
        # n-gram (like stopwords) but never start one.  Standalone
        # excluded entries are removed after consolidation.
        if word_lower in exclude_words:
            if current_ngram and word[0].isupper():
                # Mid-name: keep building (will be filtered later if standalone)
                current_ngram.append(word)
            else:
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

        # Filter: Roman numerals — unconditional.
        # Do NOT reset after_sentence_end: a Roman numeral (e.g. a
        # chapter/section marker) between a period and the next word is
        # not real sentence content.
        if _is_roman_numeral(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            continue

        # Filter: number-like tokens.
        # Do NOT reset after_sentence_end: a number sitting between a
        # sentence-ending period and the next word is almost always a
        # footnote reference (e.g. "…something.75 Once upon a time").
        # Clearing the flag here would make "Once" look mid-sentence.
        if _is_number_like(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            continue

        # Title prefixes: skip the word but keep building the n-gram
        if word_lower.rstrip('.') in TITLE_PREFIXES:
            after_sentence_end = False
            continue

        # Connector words normally break the n-gram.  However, when the
        # connector is *italic* and is extending an existing italic n-gram
        # it is kept — this preserves titles like "The Sound of Music" or
        # "War and Peace" which are typically set in italics.
        if word_lower in CONNECTOR_WORDS:
            if current_ngram and token.is_italic:
                current_ngram.append(word)
                after_sentence_end = False
                continue
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
                if is_styled:
                    pass  # Styled words bypass sentence-initial filter
                elif discovery_mode or word_lower in SENTENCE_START_IGNORE:
                    # In discovery mode skip ALL sentence-initial caps;
                    # otherwise only skip common starters.
                    after_sentence_end = False
                    if current_ngram:
                        names.append(" ".join(current_ngram))
                        current_ngram = []
                    continue
            is_name_word = True

        # Note: bold/italic ONLY helps capitalised words bypass the sentence-
        # initial filter; lowercase styled text is NOT promoted to name words
        # (prevents bold paragraphs from polluting the index).

        after_sentence_end = False

        # All-caps words (section titles like "INTRODUCTION") — always skip.
        if _is_all_caps_word(word):
            if current_ngram:
                names.append(" ".join(current_ngram))
                current_ngram = []
            continue

        if is_name_word:
            # Stopwords may extend an existing n-gram but never start one.
            if word_lower in stopwords and not current_ngram:
                continue
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

    # Build a list of "word" tokens (skip punct / footnote refs / structural)
    word_tokens: List[str] = []
    for token in tokens:
        word = token.text.strip()
        if not word:
            continue
        if token.is_superscript and _is_footnote_ref(word):
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
        # Only consider positions where the first word is capitalised;
        # this prevents matching purely lowercase text like "around the
        # world" when only "Around The World" is in the vocabulary.
        if not word_tokens[i][0].isupper():
            continue
        # Try n-grams from longest to shortest for greedy matching
        for length in range(min(max_ngram_len, n_tokens - i), 0, -1):
            # Check no sentinel in span — skip this length but keep
            # trying shorter ones (a shorter span may not cross the
            # punctuation boundary).
            span = word_tokens[i:i + length]
            if None in span:
                continue
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


def _should_consolidate(short_words: List[str], long_words: List[str]) -> bool:
    """Decide whether the shorter n-gram should be consolidated under the
    longer one.

    Consolidation makes sense when the short form is a component of a
    proper name that the long form spells out more fully, e.g.:

        "Smith"  →  "John Smith"      (surname → full name)
        "Ben"    →  "Ben Powell"      (first name → full name)

    It does NOT make sense when the short form is an independent place or
    entity that merely appears next to a generic descriptor, e.g.:

        "Cambridge" should NOT be absorbed by "Cambridge Professor"
        "Dublin"    should NOT be absorbed by "Dublin International"

    Heuristic: a single-word short form is consolidated only if it appears
    as the LAST word of the long form (surname position) OR if none of the
    OTHER words in the long form are generic descriptors found in
    NON_PERSON_NAME_WORDS / CONNECTOR_WORDS / common lowercase-origin words.
    Multi-word short forms (≥2 words) are always consolidated when they are
    contiguous subsequences, as they are specific enough to be true
    variations (e.g. "Jenny Macmillan" inside "Dr Jenny Macmillan").
    """
    if len(short_words) >= 2:
        # Multi-word short forms are specific enough to consolidate
        return True

    # Single-word short form: find where it sits in the long form
    short_lower = short_words[0].lower()
    for idx, lw in enumerate(long_words):
        if lw.lower() == short_lower:
            if idx == len(long_words) - 1:
                # Last word (surname position) — always consolidate
                return True
            # First or middle word — only consolidate if the remaining
            # words look like parts of a proper name, NOT generic titles
            # or descriptors.
            other_words = [w for j, w in enumerate(long_words) if j != idx]
            if any(w.lower() in NON_PERSON_NAME_WORDS for w in other_words):
                return False
            return True

    # Shouldn't reach here if is_contiguous_subsequence was True, but
    # fall back to not consolidating.
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
            if is_contiguous_subsequence(other_words, term_words) and \
               _should_consolidate(other_words, term_words):
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
    """Format for index display.

    Two-word names that look like person names become 'Surname, Firstname'.
    Names containing common organisational / geographical words (e.g.
    "Dublin International", "National Museum") are left in natural order.
    """
    words = name.split()
    if len(words) == 2:
        if any(w.lower() in NON_PERSON_NAME_WORDS for w in words):
            return name
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
                 include_bold=False, exclude_words=None, stopwords=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.strategy = page_numbering_strategy
        self.offset = offset
        self.include_bold = include_bold
        self.exclude_words = exclude_words or set()
        self.stopwords = stopwords or set()
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
                    stopwords=self.stopwords,
                )
                names = filter_names(raw_names)
                name_vocabulary.update(names)

                progress = int((i + 1) / total_pages * 40)
                self.progress_updated.emit(progress)

            if not self._is_running:
                doc.close()
                return

            # Remove standalone stopwords from the vocabulary.
            # Multi-word names containing a stopword (e.g. "The Guardian")
            # are kept; only single-word entries that are stopwords are purged.
            if self.stopwords:
                name_vocabulary = {
                    name for name in name_vocabulary
                    if " " in name or name.lower() not in self.stopwords
                }

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
