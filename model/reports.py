"""Analysis engine for index quality review reports.

Pure Python — no PyQt6 imports.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PageRef:
    page_idx: int    # 0-based PDF page index
    page_label: str  # logical label, e.g. "xii", "4"
    # physical PDF page number = page_idx + 1


@dataclass
class ReportFinding:
    terms: List[str]
    pages_by_term: Dict[str, List[PageRef]]
    note: str = ""


@dataclass
class ReportSection:
    report_id: str
    title: str
    description: str
    findings: List[ReportFinding]
    run_time_ms: float = 0.0
    not_run: bool = False


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str) -> int:
    """Standard O(n·m) DP Levenshtein distance."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    # Use two rows to keep memory O(min(n,m))
    if la < lb:
        a, b = b, a
        la, lb = lb, la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[lb]


def format_page_ref(page_idx: int, page_label: str) -> str:
    """Return a human-readable page reference string."""
    if str(page_idx + 1) == page_label:
        return page_label
    return f"{page_label} (PDF p.{page_idx + 1})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_page_refs(pages: List[Tuple[int, str]]) -> List[PageRef]:
    """Convert raw (page_idx, page_label) tuples to sorted PageRef list."""
    sorted_pages = sorted(pages, key=lambda t: t[0])
    return [PageRef(page_idx=idx, page_label=label) for idx, label in sorted_pages]


def _word_tokens(term: str) -> set:
    """Lowercase word tokens from a term."""
    return set(re.findall(r'\w+', term.lower()))


def _is_word_subset(a: str, b: str) -> bool:
    """Return True if all words of *a* appear in *b* (case-insensitive) and a != b."""
    if a == b:
        return False
    return _word_tokens(a) <= _word_tokens(b)


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def find_similar_terms(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """Pairs/groups with Levenshtein distance ≤ 3 (case-insensitive), excluding word-subset pairs."""
    report_id = "similar_terms"
    title = "Similar Terms"
    description = (
        "Pairs or groups of entries with small edit distance (≤ 3) — "
        "likely typos or spelling variants."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    terms = list(raw_results.keys())
    n = len(terms)
    lower = [t.casefold() for t in terms]

    # Build adjacency: i-j are close if dist <= 3 and neither is a word-subset of the other
    adj: Dict[int, set] = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if abs(len(lower[i]) - len(lower[j])) > 3:
                continue
            # Skip if one is a word-level subset of the other
            if _is_word_subset(terms[i], terms[j]) or _is_word_subset(terms[j], terms[i]):
                continue
            dist = levenshtein(lower[i], lower[j])
            if dist <= 3:
                adj[i].add(j)
                adj[j].add(i)

    # Connected components
    visited = [False] * n
    for i in range(n):
        if visited[i] or not adj[i]:
            continue
        # DFS
        cluster = []
        queue = [i]
        while queue:
            node = queue.pop()
            if visited[node]:
                continue
            visited[node] = True
            cluster.append(node)
            for nb in adj[node]:
                if not visited[nb]:
                    queue.append(nb)
        if len(cluster) >= 2:
            cluster_terms = [terms[idx] for idx in cluster]
            pages_by_term = {t: _to_page_refs(raw_results[t]) for t in cluster_terms}
            findings.append(ReportFinding(terms=cluster_terms, pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_overlapping_terms(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """Entries where one term's words are a subset of another's."""
    report_id = "overlapping_terms"
    title = "Overlapping Terms"
    description = (
        "Entries where one term’s words are a subset of another’s — "
        "e.g. ‘Smith’ contained in ‘Smith, John’."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    terms = list(raw_results.keys())
    word_sets = {t: _word_tokens(t) for t in terms}

    # For each term that is contained in at least one other term, record its containers
    contained_map: Dict[str, List[str]] = {}  # shorter -> [longer, ...]

    for a in terms:
        a_words = word_sets[a]
        if not a_words:
            continue
        for b in terms:
            if a == b:
                continue
            b_words = word_sets[b]
            if not b_words:
                continue
            # a is contained in b if all words of a appear in b and a != b
            if a_words <= b_words and len(a_words) < len(b_words):
                contained_map.setdefault(a, []).append(b)
            elif a_words <= b_words and len(a_words) == len(b_words) and len(a) < len(b):
                # same word count but different string length (e.g. punctuation diff)
                contained_map.setdefault(a, []).append(b)

    # Build findings: one finding per (shorter, containers) group
    for shorter, containers in sorted(contained_map.items(), key=lambda x: x[0].lower()):
        all_terms = [shorter] + sorted(containers, key=lambda t: (len(word_sets[t]), t.lower()))
        pages_by_term = {t: _to_page_refs(raw_results[t]) for t in all_terms}
        findings.append(ReportFinding(terms=all_terms, pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_capitalization_variants(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """Entries that differ only in capitalisation."""
    report_id = "capitalization_variants"
    title = "Capitalisation Variants"
    description = (
        "Entries that differ only in capitalisation — "
        "likely the same concept indexed inconsistently."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    groups: Dict[str, List[str]] = {}
    for term in raw_results:
        key = term.casefold()
        groups.setdefault(key, []).append(term)

    for key in sorted(groups):
        variants = groups[key]
        if len(set(variants)) >= 2:
            unique = sorted(set(variants))
            pages_by_term = {t: _to_page_refs(raw_results[t]) for t in unique}
            findings.append(ReportFinding(terms=unique, pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_formatting_variants(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """Entries with same words in different order, or differing only in hyphenation/spacing."""
    report_id = "formatting_variants"
    title = "Formatting Variants"
    description = (
        "Entries with the same words in different order, or differing only in hyphenation/spacing."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    terms = list(raw_results.keys())

    # --- Word-order variants (2+ word terms) ---
    word_order_groups: Dict[str, List[str]] = {}
    for term in terms:
        words = re.findall(r'\w+', term.casefold())
        if len(words) >= 2:
            key = ' '.join(sorted(words))
            word_order_groups.setdefault(key, []).append(term)

    # --- Hyphenation/spacing variants ---
    hyph_groups: Dict[str, List[str]] = {}
    for term in terms:
        key = re.sub(r'[-\s]', '', term.casefold())
        if key:
            hyph_groups.setdefault(key, []).append(term)

    # Collect pairs from both criteria
    # Use a set of frozensets to avoid duplicate findings
    seen_pairs: set = set()
    pair_terms: Dict[frozenset, set] = {}

    def _register_group(group_terms: List[str]) -> None:
        unique = list(dict.fromkeys(group_terms))  # preserve order, deduplicate
        if len(unique) < 2:
            return
        fs = frozenset(unique)
        if fs not in seen_pairs:
            seen_pairs.add(fs)
            pair_terms[fs] = set(unique)

    for group in word_order_groups.values():
        if len(set(group)) >= 2:
            _register_group(group)

    for group in hyph_groups.values():
        if len(set(group)) >= 2:
            _register_group(group)

    all_groups = list(pair_terms.keys())
    non_subsets = [fs for fs in all_groups if not any(fs < other for other in all_groups)]
    for fs in sorted(non_subsets, key=lambda s: sorted(s)[0].lower()):
        group_list = sorted(pair_terms[fs])
        pages_by_term = {t: _to_page_refs(raw_results[t]) for t in group_list}
        findings.append(ReportFinding(terms=group_list, pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_unused_include_terms(
    raw_results: Dict[str, List[Tuple[int, str]]],
    include_keywords: List[str],
) -> ReportSection:
    """Keywords from the include list that produced no index entries."""
    report_id = "unused_include_terms"
    title = "Unused Include Terms"
    description = (
        "Keywords from the include list that produced no index entries — "
        "possible typos in the keyword list."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not include_keywords:
        run_time_ms = (time.monotonic() - t0) * 1000
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=run_time_ms)

    # Build a set of casefold keys present in raw_results
    present = {k.casefold() for k in (raw_results or {})}

    for keyword in include_keywords:
        if keyword.casefold() not in present:
            findings.append(ReportFinding(
                terms=[keyword],
                pages_by_term={keyword: []},
            ))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_thin_entries(
    raw_results: Dict[str, List[Tuple[int, str]]],
    threshold: int = 1,
) -> ReportSection:
    """Entries appearing on threshold pages or fewer."""
    report_id = "thin_entries"
    title = "Thin Entries"
    description = (
        f"Entries appearing on {threshold} page(s) or fewer — "
        "may not warrant an index entry."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    thin = [(term, pages) for term, pages in raw_results.items() if len(pages) <= threshold]
    thin.sort(key=lambda x: x[0].lower())

    for term, pages in thin:
        pages_by_term = {term: _to_page_refs(pages)}
        findings.append(ReportFinding(terms=[term], pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_dense_entries(
    raw_results: Dict[str, List[Tuple[int, str]]],
    threshold: int = 20,
) -> ReportSection:
    """Entries appearing on threshold or more pages."""
    report_id = "dense_entries"
    title = "Dense Entries"
    description = (
        f"Entries appearing on {threshold} or more pages — "
        "consider adding sub-entries."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    dense = [(term, pages) for term, pages in raw_results.items() if len(pages) >= threshold]
    dense.sort(key=lambda x: (-len(x[1]), x[0].lower()))

    for term, pages in dense:
        pages_by_term = {term: _to_page_refs(pages)}
        findings.append(ReportFinding(
            terms=[term],
            pages_by_term=pages_by_term,
            note=f"{len(pages)} pages",
        ))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


def find_shared_page_sets(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """Pairs of entries with >= 80% Jaccard similarity on their page-index sets."""
    report_id = "shared_page_sets"
    title = "Shared Page Sets"
    description = (
        "Pairs of entries appearing on nearly identical sets of pages "
        "(≥ 80% Jaccard similarity) — possibly the same concept under different names."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    if len(raw_results) > 2000:
        run_time_ms = (time.monotonic() - t0) * 1000
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=run_time_ms,
                             not_run=True)  # skipped due to size guard

    terms = list(raw_results.keys())
    n = len(terms)
    page_sets = [frozenset(idx for idx, _label in raw_results[t]) for t in terms]

    for i in range(n):
        if not page_sets[i]:
            continue
        for j in range(i + 1, n):
            if not page_sets[j]:
                continue
            # Skip word-subset pairs (covered by overlapping_terms)
            if _is_word_subset(terms[i], terms[j]) or _is_word_subset(terms[j], terms[i]):
                continue
            intersection = len(page_sets[i] & page_sets[j])
            union = len(page_sets[i] | page_sets[j])
            if union == 0:
                continue
            jaccard = intersection / union
            if jaccard >= 0.8:
                pair = [terms[i], terms[j]]
                pages_by_term = {
                    terms[i]: _to_page_refs(raw_results[terms[i]]),
                    terms[j]: _to_page_refs(raw_results[terms[j]]),
                }
                findings.append(ReportFinding(
                    terms=pair,
                    pages_by_term=pages_by_term,
                    note=f"{int(jaccard * 100)}% overlap",
                ))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


_ACRONYM_SKIP_WORDS = frozenset(
    ['the', 'of', 'a', 'an', 'in', 'and', 'or', 'for', 'to', 'with',
     'de', 'la', 'du', 'van', 'von']
)


def find_acronym_pairs(raw_results: Dict[str, List[Tuple[int, str]]]) -> ReportSection:
    """All-caps terms that may be acronyms for longer multi-word entries."""
    report_id = "acronym_pairs"
    title = "Acronym / Expansion Pairs"
    description = (
        "All-caps terms that may be acronyms for longer entries — "
        "e.g. ‘BBC’ matching ‘British Broadcasting Corporation’."
    )
    t0 = time.monotonic()

    findings: List[ReportFinding] = []

    if not raw_results:
        return ReportSection(report_id=report_id, title=title, description=description,
                             findings=findings, run_time_ms=0.0)

    terms = list(raw_results.keys())

    # Find acronym candidates: all-uppercase, 2–6 alpha chars
    acronym_re = re.compile(r'^[A-Z]{2,6}$')
    acronyms = [t for t in terms if acronym_re.match(t)]

    # Find multi-word terms
    multi_word = [t for t in terms if len(re.findall(r'\w+', t)) >= 2]

    for acr in acronyms:
        acr_lower = acr.lower()
        matched_expansions = []
        for mw in multi_word:
            words = re.findall(r'\w+', mw)
            initials = ''.join(
                w[0].lower() for w in words if w.lower() not in _ACRONYM_SKIP_WORDS
            )
            if initials == acr_lower:
                matched_expansions.append(mw)

        for expansion in matched_expansions:
            pair_terms = [acr, expansion]
            pages_by_term = {
                acr: _to_page_refs(raw_results[acr]),
                expansion: _to_page_refs(raw_results[expansion]),
            }
            findings.append(ReportFinding(terms=pair_terms, pages_by_term=pages_by_term))

    run_time_ms = (time.monotonic() - t0) * 1000
    return ReportSection(report_id=report_id, title=title, description=description,
                         findings=findings, run_time_ms=run_time_ms)


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

_REPORT_ORDER = [
    "similar_terms",
    "overlapping_terms",
    "capitalization_variants",
    "formatting_variants",
    "unused_include_terms",
    "thin_entries",
    "dense_entries",
    "shared_page_sets",
    "acronym_pairs",
]

_NOT_RUN_STUBS = {
    "similar_terms": ("Similar Terms",
                      "Pairs or groups of entries with small edit distance (≤ 3) — "
                      "likely typos or spelling variants."),
    "overlapping_terms": ("Overlapping Terms",
                          "Entries where one term’s words are a subset of another’s — "
                          "e.g. ‘Smith’ contained in ‘Smith, John’."),
    "capitalization_variants": ("Capitalisation Variants",
                                "Entries that differ only in capitalisation — "
                                "likely the same concept indexed inconsistently."),
    "formatting_variants": ("Formatting Variants",
                            "Entries with the same words in different order, or differing only "
                            "in hyphenation/spacing."),
    "unused_include_terms": ("Unused Include Terms",
                             "Keywords from the include list that produced no index entries — "
                             "possible typos in the keyword list."),
    "thin_entries": ("Thin Entries",
                     "Entries appearing on 1 page(s) or fewer — "
                     "may not warrant an index entry."),
    "dense_entries": ("Dense Entries",
                      "Entries appearing on 20 or more pages — "
                      "consider adding sub-entries."),
    "shared_page_sets": ("Shared Page Sets",
                         "Pairs of entries appearing on nearly identical sets of pages "
                         "(≥ 80% Jaccard similarity) — possibly the same concept under "
                         "different names."),
    "acronym_pairs": ("Acronym / Expansion Pairs",
                      "All-caps terms that may be acronyms for longer entries — "
                      "e.g. ‘BBC’ matching ‘British Broadcasting Corporation’."),
}


def run_reports(
    raw_results: dict,
    include_keywords: list,
    thin_threshold: int = 1,
    dense_threshold: int = 20,
    report_ids: list = None,
) -> List[ReportSection]:
    """Run selected reports and return them in fixed order.

    If raw_results is None or empty, all reports return not_run=True.
    If report_ids is None, all reports are run.
    """
    sections: List[ReportSection] = []

    empty_input = not raw_results

    for rid in _REPORT_ORDER:
        title, description = _NOT_RUN_STUBS[rid]

        if empty_input or (report_ids is not None and rid not in report_ids):
            if rid == "thin_entries":
                description = (
                    f"Entries appearing on {thin_threshold} page(s) or fewer — "
                    "may not warrant an index entry."
                )
            elif rid == "dense_entries":
                description = (
                    f"Entries appearing on {dense_threshold} or more pages — "
                    "consider adding sub-entries."
                )
            sections.append(ReportSection(
                report_id=rid,
                title=title,
                description=description,
                findings=[],
                not_run=True,
            ))
            continue

        if rid == "similar_terms":
            sections.append(find_similar_terms(raw_results))
        elif rid == "overlapping_terms":
            sections.append(find_overlapping_terms(raw_results))
        elif rid == "capitalization_variants":
            sections.append(find_capitalization_variants(raw_results))
        elif rid == "formatting_variants":
            sections.append(find_formatting_variants(raw_results))
        elif rid == "unused_include_terms":
            sections.append(find_unused_include_terms(raw_results, include_keywords or []))
        elif rid == "thin_entries":
            sections.append(find_thin_entries(raw_results, thin_threshold))
        elif rid == "dense_entries":
            sections.append(find_dense_entries(raw_results, dense_threshold))
        elif rid == "shared_page_sets":
            sections.append(find_shared_page_sets(raw_results))
        elif rid == "acronym_pairs":
            sections.append(find_acronym_pairs(raw_results))

    return sections
