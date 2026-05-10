import fitz
import re
import string
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from PyQt6.QtCore import QThread, pyqtSignal
from model.indexer import EMPTY_FLAGS, merge_flags, label_for_page


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

# Punctuation that flushes an italic/bold phrase run. Includes terminal
# punctuation but not commas, parentheses, or dashes — those appear
# naturally inside long bolded or italicised passages and should not
# fragment the captured phrase.
TERMINAL_PUNCT_CHARS = set('.?!;:')

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
# but are NOT plausible surnames.  Used by _auto_classify_name to avoid
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
    # Architectural / historical style adjectives — almost never person names
    "baronial", "gothic", "medieval", "colonial", "baroque", "classical",
    "neoclassical", "byzantine", "renaissance",
    # Building types rarely used as surnames
    "abbey", "barracks", "barn", "cottage", "estate", "farm",
    "hamlet", "inn", "priory", "rectory", "vicarage",
}

# Regex for detecting Roman numerals.
_ROMAN_RE = re.compile(r'^[IVXLCDM]+$')

# Word/punctuation tokenizer.
#
# A word starts with \w and may contain internal hyphens, plus internal
# apostrophes (straight ' or curly U+2019) when the apostrophe is
# followed by another word character \u2014 so "Pemberton's" / "O'Donnell"
# stay as single tokens. A TRAILING apostrophe is NOT absorbed into the
# word; it becomes a standalone punctuation token. That lets the curly
# U+2019 that closes a 'single-quoted phrase' be detected as the
# quote-close marker rather than being silently glued onto the last
# word inside the quotes (e.g. "Method\u2019"). Trailing hyphens stay
# attached so the line-break hyphenation reconstruction can fire.
_TOKEN_RE = re.compile(
    r"[\w](?:[\w-]+|['\u2019](?=\w))*|[^\s\w]",
    re.UNICODE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StyledToken:
    text: str
    is_bold: bool
    is_italic: bool
    is_superscript: bool
    is_all_caps: bool = False           # True if the token alone is all-caps (>=2 letters)
    from_all_caps_line: bool = False    # True if the line containing this token is fully all-caps


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


def _strip_possessive(word: str) -> str:
    """Strip a trailing possessive 's (ASCII or curly apostrophe) from a token."""
    if word.endswith("'s") or word.endswith("’s"):
        return word[:-2]
    return word


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


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

def _peek_first_word(block) -> str:
    """Return the first word-like token in the first line of *block*, or ''."""
    info = _peek_first_styled_word(block)
    return info[0] if info else ""


def _peek_first_word_of_line(line) -> str:
    info = _peek_first_styled_word_of_line(line)
    return info[0] if info else ""


def _peek_first_styled_word(block):
    """Return (word, is_bold, is_italic) for the first non-punctuation token
    in the first line of *block*, or None if no such token exists.
    """
    for line in block.get("lines", []):
        result = _peek_first_styled_word_of_line(line)
        if result is not None:
            return result
    return None


def _peek_first_styled_word_of_line(line):
    """Return (word, is_bold, is_italic) for the first non-punctuation token
    in *line*, or None if no such token exists.
    """
    for span in line.get("spans", []):
        flags = span.get("flags", 0)
        is_bold = bool(flags & 16)
        is_italic = bool(flags & 2)
        for match in _TOKEN_RE.finditer(span.get("text", "")):
            w = match.group()
            if not _is_punctuation(w):
                return (w, is_bold, is_italic)
    return None


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
        # Between blocks: insert a synthetic sentence-end whenever the previous
        # block's last line does NOT fill the column width.  A full-width last
        # line means the paragraph was still wrapping into the next block, so
        # a name n-gram may legitimately span the boundary (e.g. "Dublin
        # International" / "Piano Competition" in a reflowed PDF).  A short
        # last line means the block is a heading, list entry, or paragraph end
        # — it cannot be mid-sentence, so we always break the n-gram.
        # Cross-block hyphenation join. PyMuPDF often puts the two
        # halves of a line-wrapped word in different blocks, so the
        # within-block join below isn't enough — "avail-" can end one
        # block and "able" start the next. If the last token of the
        # previous block ends in "-" and this block's first word starts
        # lowercase, fuse them so the styled-phrase capture passes
        # don't emit "avail- able" as two space-separated tokens.
        cross_block_join_skip = None
        if tokens and prev_block is not None:
            next_info = _peek_first_styled_word(block)
            if next_info:
                joined = try_hyphenation_join(tokens[-1].text, next_info[0])
                if joined is not None:
                    old = tokens[-1]
                    tokens[-1] = StyledToken(
                        text=joined,
                        is_bold=old.is_bold,
                        is_italic=old.is_italic,
                        is_superscript=old.is_superscript,
                        is_all_caps=_is_all_caps_word(joined),
                        from_all_caps_line=old.from_all_caps_line,
                    )
                    cross_block_join_skip = next_info[0]

        # Synthetic separator decision (skipped if hyphenation joined
        # across the block boundary — the words are now a single token).
        if cross_block_join_skip is None and tokens and prev_block is not None:
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
                next_info = _peek_first_styled_word(block)
                next_word = next_info[0] if next_info else ""
                if should_suppress_break(prev_word, next_word):
                    # Style mismatch overrides the lexical suppress: a bold
                    # heading line followed by a plain-styled paragraph
                    # word must NOT be merged into a single phrase.
                    if (next_info is None
                            or (tokens[-1].is_bold == next_info[1]
                                and tokens[-1].is_italic == next_info[2])):
                        insert_sep = False

            if insert_sep:
                tokens.append(StyledToken(
                    text=".", is_bold=False, is_italic=False,
                    is_superscript=False,
                ))

        block_lines = block.get("lines", [])
        for line_idx, line in enumerate(block_lines):
            # Hyphenation join: if the previous line left a token ending
            # in "-" and the first word of this line starts lowercase,
            # fuse them (drop the hyphen) instead of emitting both halves.
            # Two sources for pending_join_skip: a same-block within-line
            # join (line_idx > 0), or a cross-block join we made just
            # above (only relevant on this block's first line).
            pending_join_skip = None
            if line_idx == 0 and cross_block_join_skip is not None:
                pending_join_skip = cross_block_join_skip
                cross_block_join_skip = None
            if line_idx > 0 and tokens:
                first_word = _peek_first_word_of_line(line)
                joined = try_hyphenation_join(tokens[-1].text, first_word)
                if joined is not None:
                    pending_join_skip = first_word
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
                    if pending_join_skip is not None and word == pending_join_skip:
                        pending_join_skip = None
                        continue
                    tokens.append(StyledToken(
                        text=word,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        is_superscript=is_superscript,
                        is_all_caps=_is_all_caps_word(word),
                        from_all_caps_line=line_is_caps,
                    ))

            # Within a block, insert a separator after any non-final line that
            # does not fill the column.  Wrapped paragraph lines fill the column
            # on every line but the last, so only short lines (headings, list
            # entries, paragraph-final lines) trigger a break.  This prevents
            # names from spanning across a newline boundary within one block.
            # Lexical override: if the last word emitted and the first word of
            # the next line are both capitalised, the phrase is wrapping —
            # keep them together.
            is_last_line = (line_idx == len(block_lines) - 1)
            if not is_last_line and tokens and col_width > 0:
                line_bbox = line.get("bbox")
                if line_bbox:
                    line_w = line_bbox[2] - line_bbox[0]
                    if line_w < col_width * 0.9:
                        prev_word = tokens[-1].text
                        next_info = _peek_first_styled_word_of_line(
                            block_lines[line_idx + 1]
                        )
                        next_word = next_info[0] if next_info else ""
                        # Suppress the synthetic break only if the lexical
                        # rule says so AND the next line's first word
                        # shares the previous word's bold/italic styling.
                        # A style change (e.g. bold heading → plain body)
                        # is a strong signal these are different contexts.
                        suppress = should_suppress_break(prev_word, next_word)
                        if suppress and next_info is not None:
                            if (tokens[-1].is_bold != next_info[1]
                                    or tokens[-1].is_italic != next_info[2]):
                                suppress = False
                        if not suppress:
                            tokens.append(StyledToken(
                                text=".", is_bold=False, is_italic=False,
                                is_superscript=False,
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
) -> List[Tuple[str, dict]]:
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

    Returns a list of (name, flags) tuples where flags is a dict with keys
    'italic', 'bold', 'caps' — OR'd across the constituent tokens.
    """
    if exclude_words is None:
        exclude_words = set()
    if stopwords is None:
        stopwords = set()

    names: List[Tuple[str, dict]] = []
    current_ngram: List[str] = []
    current_flags: dict = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
    current_ngram_italic: Optional[bool] = None  # italic status of the first token in the n-gram
    after_sentence_end = True  # Start of page is effectively a sentence boundary
    # True when this n-gram's FIRST word was admitted via the styled
    # bypass at sentence-start (italic/bold-styled capitalised word that
    # would otherwise have been filtered as sentence-initial). If the
    # n-gram only ever has one word, that bypass is the sole reason for
    # its existence — so we drop it on flush. Without this guard a
    # single italic publication name like "Piano" at the start of a
    # sentence would seed the vocabulary and pull in every plain
    # "Piano" elsewhere in the document.
    started_with_styled_bypass = False

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
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            continue

        # Punctuation handling
        if _is_punctuation(word):
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            if word in SENTENCE_END_CHARS:
                after_sentence_end = True
            continue

        # Strip possessive suffix ("Hall's" → "Hall") before any further processing.
        word = _strip_possessive(word)
        if not word:
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
                if token.is_italic:
                    current_flags["italic"] = True
                if token.is_bold:
                    current_flags["bold"] = True
                if token.is_all_caps:
                    current_flags["caps"] = True
            else:
                if current_ngram:
                    names.append((" ".join(current_ngram), dict(current_flags)))
                    current_ngram = []
                    current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                    current_ngram_italic = None
            after_sentence_end = False
            continue

        # Filter: structural words (Chapter, Section, ...) — unconditional
        if word_lower in STRUCTURAL_WORDS:
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            after_sentence_end = False
            continue

        # Filter: Roman numerals — unconditional.
        # Do NOT reset after_sentence_end: a Roman numeral (e.g. a
        # chapter/section marker) between a period and the next word is
        # not real sentence content.
        if _is_roman_numeral(word):
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            continue

        # Filter: number-like tokens.
        # Do NOT reset after_sentence_end: a number sitting between a
        # sentence-ending period and the next word is almost always a
        # footnote reference (e.g. "…something.75 Once upon a time").
        # Clearing the flag here would make "Once" look mid-sentence.
        if _is_number_like(word):
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
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
            if current_ngram and token.is_italic and current_ngram_italic:
                current_ngram.append(word)
                # token.is_italic is guaranteed by the enclosing condition.
                current_flags["italic"] = True
                if token.is_bold:
                    current_flags["bold"] = True
                if token.is_all_caps:
                    current_flags["caps"] = True
                after_sentence_end = False
                continue
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            after_sentence_end = False
            continue

        # Determine if this is a "name word"
        is_name_word = False

        admitted_via_styled_bypass = False
        if word[0].isupper():
            # Sentence-initial capitalisation check
            if after_sentence_end:
                if is_styled:
                    # Styled words bypass the sentence-initial filter,
                    # but if this is the first word of a new n-gram we
                    # mark the n-gram so a single-word bypass admission
                    # gets dropped at flush time.
                    admitted_via_styled_bypass = True
                elif discovery_mode or word_lower in SENTENCE_START_IGNORE:
                    # In discovery mode skip ALL sentence-initial caps;
                    # otherwise only skip common starters.
                    after_sentence_end = False
                    if current_ngram:
                        if not (len(current_ngram) == 1 and started_with_styled_bypass):
                            names.append((" ".join(current_ngram), dict(current_flags)))
                        current_ngram = []
                        current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                        current_ngram_italic = None
                        started_with_styled_bypass = False
                    continue
            is_name_word = True

        # Note: bold/italic ONLY helps capitalised words bypass the sentence-
        # initial filter; lowercase styled text is NOT promoted to name words
        # (prevents bold paragraphs from polluting the index).

        after_sentence_end = False

        # Tokens on a fully all-caps line (section titles like "INTRODUCTION"
        # or "THE INDEXER'S APPRENTICE") — skip the whole token regardless of
        # whether it is itself all-caps; apostrophe-containing words such as
        # "INDEXER'S" are not flagged is_all_caps but are still part of the
        # heading and must not be indexed.
        # Single all-caps tokens inside a mixed-case line ("NATO", "CERN")
        # are admitted as name candidates and proceed to the is_name_word
        # block below.
        if token.from_all_caps_line:
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            continue

        if is_name_word:
            # Stopwords may extend an existing n-gram but never start one.
            if word_lower in stopwords and not current_ngram:
                continue
            # Style break: flush the n-gram when italic status changes mid-sequence
            # (e.g. "Adam Gorb's" in plain text followed by italic "Absinthe").
            if current_ngram and token.is_italic != current_ngram_italic:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False
            if not current_ngram:
                current_ngram_italic = token.is_italic
                started_with_styled_bypass = admitted_via_styled_bypass
            current_ngram.append(word)
            if token.is_italic:
                current_flags["italic"] = True
            if token.is_bold:
                current_flags["bold"] = True
            if token.is_all_caps:
                current_flags["caps"] = True
        else:
            # Lowercase non-styled, non-connector word: breaks n-gram
            if current_ngram:
                if not (len(current_ngram) == 1 and started_with_styled_bypass):
                    names.append((" ".join(current_ngram), dict(current_flags)))
                current_ngram = []
                current_flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
                current_ngram_italic = None
                started_with_styled_bypass = False

    # Flush any remaining n-gram
    if current_ngram:
        if not (len(current_ngram) == 1 and started_with_styled_bypass):
            names.append((" ".join(current_ngram), dict(current_flags)))

    return names


def extract_bold_phrases(tokens: List[StyledToken]) -> List[str]:
    """Walk *tokens* and emit runs of bold-styled tokens as phrases.

    Mirrors extract_italic_phrases but is more permissive about word
    membership. Bold annotations are typically body emphasis (e.g.
    '**A note on proximity**' inside the prose) rather than structural
    headings, so the STRUCTURAL_WORDS filter that the italic pass uses
    is dropped here — words like 'note', 'index', 'see' should not
    break a bold run when used in their everyday sense.

    A bold run is broken by punctuation, by the bold flag turning off,
    by footnote references, by roman numerals, and by number-like
    tokens. Title prefixes (Dr, Mr, Mrs, Sir, ...) are skipped without
    breaking the run. Lone single-token runs that are just stop words
    are dropped on flush.

    Used when the 'Index Bold Text' option is on, so that a bold
    annotation like '**A note on proximity**' becomes its own entry
    rather than only contributing flag information to capitalised words.
    """
    phrases: List[str] = []
    current: List[str] = []

    def flush():
        if current:
            if len(current) == 1 and current[0].lower() in DEFAULT_STOPWORDS:
                current.clear()
                return
            phrases.append(" ".join(current))
            current.clear()

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        if not token.is_bold:
            flush()
            continue

        # Skip whole all-caps lines (chapter headings rendered in bold).
        if token.from_all_caps_line:
            flush()
            continue

        if token.is_superscript and _is_footnote_ref(word):
            flush()
            continue

        if _is_punctuation(word):
            # Only terminal punctuation breaks the run; commas, parens,
            # and dashes stay inside.
            if any(ch in TERMINAL_PUNCT_CHARS for ch in word):
                flush()
            continue

        word = _strip_possessive(word)
        if not word:
            continue

        if word.lower().rstrip('.') in TITLE_PREFIXES:
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
    - Title prefixes (Dr, Mr, Mrs, Sir, ...) are skipped without breaking
      the run, mirroring extract_names_from_tokens. This prevents
      "*Dr Edmund Crawley*" from producing a separate italic entry that
      duplicates the name pass's "Edmund Crawley".
    - Roman numerals, footnote refs, and pure-number tokens are skipped
      without breaking the run (mirrors extract_names_from_tokens behaviour).
    - Possessive suffixes are stripped before adding to the run.
    - A captured run consisting of a single token that is itself a stop
      word ("the", "a", "every", "some", ...) is dropped, since lone
      italic stop words are almost never legitimate index entries.
    """
    phrases: List[str] = []
    current: List[str] = []

    def flush():
        if current:
            # Drop a single-token run that is just a stop word.
            if len(current) == 1 and current[0].lower() in DEFAULT_STOPWORDS:
                current.clear()
                return
            phrases.append(" ".join(current))
            current.clear()

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        if not token.is_italic:
            flush()
            continue

        # Skip whole all-caps lines (e.g. an italic-styled chapter heading).
        if token.from_all_caps_line:
            flush()
            continue

        if token.is_superscript and _is_footnote_ref(word):
            flush()
            continue

        if _is_punctuation(word):
            # Only terminal punctuation breaks the run; commas, parens,
            # and dashes stay inside.
            if any(ch in TERMINAL_PUNCT_CHARS for ch in word):
                flush()
            continue

        word = _strip_possessive(word)
        if not word:
            continue

        if word.lower() in STRUCTURAL_WORDS:
            flush()
            continue

        # Title prefixes (Dr, Mr, Mrs, ...) are skipped without breaking
        # the run, so an italic "Dr Edmund Crawley" yields "Edmund Crawley".
        if word.lower().rstrip('.') in TITLE_PREFIXES:
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


def extract_quoted_phrases(tokens: List[StyledToken]) -> List[str]:
    """Walk *tokens* and emit phrases enclosed in single curly quotes
    (U+2018 ... U+2019).

    The opening curly single-quote (U+2018, ‘) starts a run; the closing
    curly single-quote (U+2019, ’) ends it. Apostrophes inside individual
    word tokens (e.g. "O’Donnell") are part of those tokens and do NOT
    end the run, because the rule only fires when ’ appears as a standalone
    punctuation token between word tokens.

    Within a quoted run, the same filters as the italic/bold passes apply:
    structural-word, footnote-ref, roman-numeral, and number-like tokens
    flush the run; commas/parentheses stay inside; terminal punctuation
    (.?!;:) flushes; title prefixes (Dr, Mr, ...) are skipped without
    breaking. Tokens on a fully all-caps line are skipped — a heading
    rendered with quoted text is unusual but possible.

    A single-token run that is just a stop word is dropped on flush.
    """
    phrases: List[str] = []
    current: List[str] = []
    in_quote = False

    def flush():
        if current:
            if len(current) == 1 and current[0].lower() in DEFAULT_STOPWORDS:
                current.clear()
                return
            phrases.append(" ".join(current))
            current.clear()

    for token in tokens:
        word = token.text.strip()
        if not word:
            continue

        # Open / close detection. Both curly variants act as paired
        # delimiters; a stray closing quote without an open is ignored.
        if word == "‘":
            flush()
            in_quote = True
            continue
        if word == "’":
            flush()
            in_quote = False
            continue

        if not in_quote:
            continue

        if token.from_all_caps_line:
            flush()
            continue

        if token.is_superscript and _is_footnote_ref(word):
            flush()
            continue

        if _is_punctuation(word):
            if any(ch in TERMINAL_PUNCT_CHARS for ch in word):
                flush()
            continue

        word = _strip_possessive(word)
        if not word:
            continue

        if word.lower() in STRUCTURAL_WORDS:
            flush()
            continue

        if word.lower().rstrip('.') in TITLE_PREFIXES:
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


# ---------------------------------------------------------------------------
# Known-name search (pass 2)
# ---------------------------------------------------------------------------

def find_known_names_in_tokens(
    tokens: List[StyledToken],
    known_names: Set[str],
    known_names_lower: Dict[str, str],
    max_ngram_len: int,
) -> List[Tuple[str, dict]]:
    """Find all occurrences of *known_names* in *tokens*, regardless of
    sentence position.  Returns a list of (name, flags) tuples where name
    uses the original casing from the vocabulary and flags is a dict with
    keys 'italic', 'bold', 'caps' OR'd across the spanned tokens."""

    # Build parallel lists of "word" tokens and their per-token flags
    # (skip punct / footnote refs / structural)
    word_tokens: List[str] = []
    word_flags: List[dict] = []  # parallel to word_tokens; entry is None at punctuation sentinels
    for token in tokens:
        word = token.text.strip()
        if not word:
            continue
        if token.is_superscript and _is_footnote_ref(word):
            continue
        if _is_punctuation(word):
            # Insert a sentinel to prevent cross-sentence matching
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

    found: List[Tuple[str, dict]] = []
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
                flags = {"italic": False, "bold": False, "caps": False, "single-quotes": False}
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
        orphan_pages: Dict[int, tuple] = {}
        for occ in occurrences:
            page_idx = occ[0]
            if page_idx not in longest_page_indices:
                orphan_pages[page_idx] = occ
        if orphan_pages:
            result[variation] = [orphan_pages[k] for k in sorted(orphan_pages.keys())]

    return result


def _auto_classify_name(name: str) -> str:
    """Return 'place_thing' or 'person' based on the words in the name.

    Only two-word names are ever inverted, so classification matters mainly
    for those.  Single-word and three-plus-word names are returned as-is
    regardless of this value.
    """
    words = name.split()
    if len(words) == 2 and any(w.lower() in NON_PERSON_NAME_WORDS for w in words):
        return "place_thing"
    return "person"


def _try_spacy_classify(
    page_texts: List[str],
    name_vocabulary: Set[str],
    progress_callback=None,
    progress_start: int = 0,
    progress_end: int = 100,
) -> Dict[str, str]:
    """Use spaCy NER to classify multi-word names as 'person' or 'place_thing'.

    *page_texts* is the pre-collected plain text for each page.  Runs entity
    recognition over every page and counts how often each name in
    *name_vocabulary* is labelled as PERSON vs a place/organisation type.
    Returns {name: type} for names where a clear majority (>=60%) of mentions
    agree.

    *progress_callback*, if provided, is called with an int in
    [progress_start, progress_end] as each page is processed.

    Returns {} silently if spaCy is not installed or no English model is found.
    """
    try:
        import spacy  # noqa: PLC0415
    except ImportError:
        return {}

    nlp = None
    for model_name in (
        "en_core_web_sm", "en_core_web_md",
        "en_core_web_lg", "en_core_web_trf",
    ):
        try:
            nlp = spacy.load(model_name, disable=["parser", "lemmatizer"])
            break
        except OSError:
            continue
    if nlp is None:
        return {}

    # NER labels that indicate a place/organisation, not a person
    PLACE_LABELS = {
        "ORG", "GPE", "FAC", "LOC", "NORP",
        "WORK_OF_ART", "EVENT", "PRODUCT", "LAW",
    }

    # Only classify multi-word names — single words are handled by _auto_classify_name
    name_lower_map: Dict[str, str] = {
        n.lower(): n for n in name_vocabulary if " " in n
    }
    if not name_lower_map:
        return {}

    votes: Dict[str, Counter] = defaultdict(Counter)
    total = len(page_texts)

    for i, spacy_doc in enumerate(nlp.pipe(page_texts, batch_size=10)):
        for ent in spacy_doc.ents:
            key = ent.text.strip().lower()
            if key in name_lower_map:
                name = name_lower_map[key]
                if ent.label_ in PLACE_LABELS:
                    votes[name]["place_thing"] += 1
                elif ent.label_ == "PERSON":
                    votes[name]["person"] += 1
        if progress_callback and total:
            pct = progress_start + int((i + 1) / total * (progress_end - progress_start))
            progress_callback(pct)

    result: Dict[str, str] = {}
    for name, counter in votes.items():
        total = sum(counter.values())
        if total == 0:
            continue
        best, count = counter.most_common(1)[0]
        if count / total >= 0.6:
            result[name] = best

    return result


def format_name_entry(name: str, name_type: Optional[str] = None) -> str:
    """Format a name for index display.

    name_type: 'person'      → invert two-word names ("John Smith" → "Smith, John")
               'place_thing' → keep natural word order
               None          → auto-classify via _auto_classify_name()
    """
    if name_type is None:
        name_type = _auto_classify_name(name)
    words = name.split()
    if len(words) == 2 and name_type == "person":
        return f"{words[1]}, {words[0]}"
    return name


def _entry_words(name: str) -> List[str]:
    """Split an entry name into words for subsequence comparison.

    Handles whitespace and commas (so "Halloway, Beatrice" → ["Halloway",
    "Beatrice"]). Returned words are NOT lower-cased — case-insensitive
    comparisons are done by the caller.
    """
    return [w for w in re.split(r'[\s,]+', name) if w]


def _suppress_substring_duplicates(raw_results: dict) -> None:
    """Drop entries that are substring duplicates of longer entries.

    An entry A is treated as a substring duplicate of entries B1, B2, …
    when A's words form a contiguous sub-sequence of each B's words
    (case-insensitive) AND every page A appears on is also covered by
    one of those longer entries. In that case A only ever appears as a
    sub-form of a longer indexed name and contributes no independent
    information, so it is dropped.

    Examples this catches:

    - "Fisher" / "Norma Fisher" with identical page lists — the bare
      surname appears only when the full name appears on the same page,
      so "Fisher" is removed.
    - "Chopin Sonata in B-flat" / "Chopin Sonata in B-flat minor" both
      on page 196 — the partial form is dropped.

    Examples preserved:

    - "Manchester" appearing on pages {1, 3} alongside "Manchester Free
      Trade Hall" on pages {2, 3} — page 1 of "Manchester" has no
      covering longer entry, so the standalone is kept intact.
    - "Beatrice" on pages {1, 5} when "Beatrice Halloway" is only on
      page 1 — page 5 isn't covered, so "Beatrice" is kept.

    Applied in-place to *raw_results*.
    """
    keys = list(raw_results.keys())
    key_words = {k: _entry_words(k) for k in keys}
    key_pages = {k: {p[0] for p in raw_results[k]} for k in keys}

    to_remove = set()
    for a in keys:
        if a in to_remove:
            continue
        a_words = key_words[a]
        if not a_words:
            continue
        a_pages = key_pages[a]
        # Union of pages from every longer entry that contains a as a
        # contiguous subsequence.
        covering_pages: set = set()
        for b in keys:
            if b == a:
                continue
            b_words = key_words[b]
            if len(b_words) <= len(a_words):
                continue
            if not is_contiguous_subsequence(a_words, b_words):
                continue
            covering_pages |= key_pages[b]
        if covering_pages and a_pages.issubset(covering_pages):
            to_remove.add(a)

    for k in to_remove:
        del raw_results[k]


# Kept for backwards compatibility; older code paths and tests may still
# refer to the old name. The implementation now delegates.
_suppress_covered_components = _suppress_substring_duplicates


# ---------------------------------------------------------------------------
# Threading wrapper
# ---------------------------------------------------------------------------

class NameIndexingThread(QThread):
    progress_updated = pyqtSignal(int)
    indexing_finished = pyqtSignal(dict, dict)  # formatted_results, raw_results
    error_occurred = pyqtSignal(str)

    def __init__(self, pdf_path, page_numbering_strategy, offset=0,
                 include_bold=False, exclude_words=None, stopwords=None,
                 name_type_overrides=None, start_page=0, surname_first=False,
                 index_italic=True, index_capitalised=True,
                 index_single_quotes=True, index_front_matter=False):
        super().__init__()
        self.pdf_path = pdf_path
        self.strategy = page_numbering_strategy
        self.offset = offset
        self.include_bold = include_bold
        self.exclude_words = exclude_words or set()
        self.stopwords = stopwords or set()
        self._overrides = {k.lower(): v for k, v in (name_type_overrides or {}).items()}
        self._start_page = start_page
        self._surname_first = surname_first
        self._is_running = True
        self.index_italic = index_italic
        self.index_capitalised = index_capitalised
        self.index_single_quotes = index_single_quotes
        self.index_front_matter = index_front_matter

    def run(self):
        try:
            doc = fitz.open(self.pdf_path)
            total_pages = len(doc)

            front_range = (range(0, self._start_page)
                           if self.index_front_matter and self._start_page > 0 else range(0, 0))
            main_range = range(self._start_page, total_pages)
            combined_iter = list(front_range) + list(main_range)
            roman_set = set(front_range)
            indexable = len(combined_iter)

            # ----------------------------------------------------------
            # Pass 1 – Discovery  (0-30 %)
            # Build three vocabularies: capitalised (the "regular" set
            # used by find_known_names_in_tokens to match plain prose),
            # italic-only (entries that ONLY appeared as italic phrases),
            # and bold-only (entries that ONLY appeared as bold phrases).
            # The latter two are NOT given to find_known_names so that a
            # single italic publication name like "Piano" does not pull
            # in every plain "Piano" elsewhere in the document.
            # ----------------------------------------------------------
            cap_vocab: Set[str] = set()
            italic_vocab: Set[str] = set()
            bold_vocab: Set[str] = set()
            quoted_vocab: Set[str] = set()
            # For each capitalised-pass observation we record the flag
            # dict so that — after pass 1 finishes — we can decide
            # whether a single-word entry deserves a place in cap_vocab.
            # A single word that was ONLY ever observed italic (or
            # bold) is routed to italic_vocab / bold_vocab so that
            # find_known_names_in_tokens does not later match plain
            # occurrences of it elsewhere in the document.
            cap_observations: Dict[str, List[dict]] = defaultdict(list)
            page_texts: List[str] = []

            for loop_idx, i in enumerate(combined_iter):
                if not self._is_running:
                    break

                page = doc.load_page(i)
                page_texts.append(page.get_text("text"))
                tokens = extract_styled_tokens(page)

                if self.index_capitalised:
                    raw_named = extract_names_from_tokens(
                        tokens, discovery_mode=True,
                        include_bold=self.include_bold,
                        exclude_words=self.exclude_words,
                        stopwords=self.stopwords,
                    )
                    for name, flags in raw_named:
                        cleaned = clean_name(name)
                        if not cleaned or len(cleaned) <= 1 or cleaned.isdigit():
                            continue
                        cap_observations[cleaned].append(flags)

                if self.index_italic:
                    italic_raw = extract_italic_phrases(tokens)
                    italic_vocab.update(filter_names(italic_raw))

                if self.include_bold:
                    bold_raw = extract_bold_phrases(tokens)
                    bold_vocab.update(filter_names(bold_raw))

                if self.index_single_quotes:
                    quoted_raw = extract_quoted_phrases(tokens)
                    quoted_vocab.update(filter_names(quoted_raw))

                progress = int((loop_idx + 1) / max(indexable, 1) * 30)
                self.progress_updated.emit(progress)

            # Decide cap_vocab membership using the aggregated observations.
            # Multi-word entries always join cap_vocab (the multi-word
            # context is specific enough that over-matching is unlikely).
            # Single-word entries join cap_vocab only if at least one
            # mid-sentence observation was PLAIN (no italic, no bold).
            # Otherwise they're routed to italic_vocab / bold_vocab —
            # so a single italic publication name like "Piano" cannot
            # later match plain "Piano" via find_known_names_in_tokens.
            for cleaned, observations in cap_observations.items():
                is_multi_word = " " in cleaned
                if is_multi_word:
                    cap_vocab.add(cleaned)
                    continue
                has_plain = any(
                    not o.get("italic") and not o.get("bold")
                    for o in observations
                )
                if has_plain:
                    cap_vocab.add(cleaned)
                    continue
                # All observations were styled — route to the matching
                # style vocab. Most observations will agree; if mixed,
                # admit to whichever style appeared in any observation.
                if any(o.get("italic") for o in observations):
                    italic_vocab.add(cleaned)
                if any(o.get("bold") for o in observations):
                    bold_vocab.add(cleaned)

            if not self._is_running:
                doc.close()
                return

            # Drop standalone stopwords from every vocab. Multi-word
            # names containing a stopword (e.g. "The Guardian") are kept;
            # only single-word entries that are stopwords are purged.
            if self.stopwords:
                stopword_filter = lambda v: {
                    n for n in v
                    if " " in n or n.lower() not in self.stopwords
                }
                cap_vocab = stopword_filter(cap_vocab)
                italic_vocab = stopword_filter(italic_vocab)
                bold_vocab = stopword_filter(bold_vocab)
                quoted_vocab = stopword_filter(quoted_vocab)

            # The full vocabulary is the union, used for spaCy
            # classification only. find_known_names_in_tokens uses just
            # cap_vocab so italic-only / bold-only / quoted-only entries
            # don't match at non-styled positions.
            name_vocabulary = (
                cap_vocab | italic_vocab | bold_vocab | quoted_vocab
            )

            if not name_vocabulary:
                doc.close()
                self.progress_updated.emit(100)
                self.indexing_finished.emit({}, {})
                return

            # ----------------------------------------------------------
            # Pass 1.5 – spaCy NER classification  (30-55 %)
            # ----------------------------------------------------------
            if self._surname_first:
                spacy_types = _try_spacy_classify(
                    page_texts, name_vocabulary,
                    progress_callback=self.progress_updated.emit,
                    progress_start=30,
                    progress_end=55,
                )
            else:
                spacy_types = {}
                self.progress_updated.emit(55)

            # Build lookup structures for pass 2 — cap_vocab only.
            known_names_lower: Dict[str, str] = {}
            max_ngram_len = 1
            for name in cap_vocab:
                known_names_lower[name.lower()] = name
                max_ngram_len = max(max_ngram_len, len(name.split()))

            # ----------------------------------------------------------
            # Pass 2 – Indexing  (55-80 %)
            # Search every page for ALL occurrences of known names,
            # including those at the start of sentences.
            # ----------------------------------------------------------
            all_occurrences: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

            for loop_idx, i in enumerate(combined_iter):
                if not self._is_running:
                    break

                page = doc.load_page(i)
                page_label = label_for_page(
                    page, i + 1, self.strategy,
                    offset=self.offset, force_roman=(i in roman_set),
                )
                tokens = extract_styled_tokens(page)

                found_names = find_known_names_in_tokens(
                    tokens, cap_vocab, known_names_lower, max_ngram_len,
                )

                # Collect flags per name on this page, OR-merging on duplicates.
                seen_flags_by_name: dict = {}

                for name, flags in found_names:
                    if name not in seen_flags_by_name:
                        seen_flags_by_name[name] = dict(flags)
                    else:
                        seen_flags_by_name[name] = merge_flags(seen_flags_by_name[name], flags)

                if self.index_italic:
                    italic_phrases = extract_italic_phrases(tokens)
                    italic_clean = filter_names(italic_phrases)
                    for phrase in italic_clean:
                        italic_flags = {
                            "italic": True, "bold": False,
                            "caps": False, "single-quotes": False,
                        }
                        if phrase in seen_flags_by_name:
                            seen_flags_by_name[phrase] = merge_flags(
                                seen_flags_by_name[phrase], italic_flags,
                            )
                        else:
                            seen_flags_by_name[phrase] = italic_flags

                if self.include_bold:
                    bold_phrases = extract_bold_phrases(tokens)
                    bold_clean = filter_names(bold_phrases)
                    for phrase in bold_clean:
                        bold_flags = {
                            "italic": False, "bold": True,
                            "caps": False, "single-quotes": False,
                        }
                        if phrase in seen_flags_by_name:
                            seen_flags_by_name[phrase] = merge_flags(
                                seen_flags_by_name[phrase], bold_flags,
                            )
                        else:
                            seen_flags_by_name[phrase] = bold_flags

                if self.index_single_quotes:
                    quoted_phrases = extract_quoted_phrases(tokens)
                    quoted_clean = filter_names(quoted_phrases)
                    for phrase in quoted_clean:
                        quoted_flags = {
                            "italic": False, "bold": False,
                            "caps": False, "single-quotes": True,
                        }
                        if phrase in seen_flags_by_name:
                            seen_flags_by_name[phrase] = merge_flags(
                                seen_flags_by_name[phrase], quoted_flags,
                            )
                        else:
                            seen_flags_by_name[phrase] = quoted_flags

                for name, flags in seen_flags_by_name.items():
                    all_occurrences[name].append((i, page_label, flags))

                progress = 55 + int((loop_idx + 1) / max(indexable, 1) * 25)
                self.progress_updated.emit(progress)

            doc.close()

            if not self._is_running:
                return

            # ----------------------------------------------------------
            # Phase 3 – Format entries  (75-90 %)
            # Auto-consolidation removed; users can manually merge
            # related terms via the right-click context menu.
            # ----------------------------------------------------------
            self.progress_updated.emit(80)

            raw_results: Dict[str, List[Tuple[int, str]]] = {}
            for name, occurrences in all_occurrences.items():
                if not self._surname_first:
                    name_type = "place_thing"  # keep natural order for all names
                else:
                    # Priority: user override > spaCy NER > word-pattern heuristic
                    auto_type = spacy_types.get(name, _auto_classify_name(name))
                    name_type = self._overrides.get(name.lower(), auto_type)
                display_key = format_name_entry(name, name_type)
                # Deduplicate by page index
                seen: set = set()
                deduped: list = []
                for p in occurrences:
                    if p[0] not in seen:
                        seen.add(p[0])
                        deduped.append(p)
                deduped.sort(key=lambda x: x[0])
                # If display-key collision, merge page lists
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
                            existing_by_idx[p[0]] = len(raw_results[display_key]) - 1
                    raw_results[display_key].sort(key=lambda x: x[0])
                else:
                    raw_results[display_key] = deduped

            # Auto-suppression of single-word entries that are covered by
            # compound entries was previously applied here. It removed
            # legitimately independent mentions (e.g. "Manchester" being
            # discussed alongside "Manchester Free Trade Hall") and was
            # too aggressive overall. The merge tool exists for the user
            # to consolidate variants manually; the PDF viewer's proximity
            # highlighter shows when a bare first/last name belongs with
            # a compound entry on the same page even when both are kept.

            self.progress_updated.emit(85)

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
