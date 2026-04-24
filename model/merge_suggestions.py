"""Find containment relationships between index entries for merge suggestions."""
import re


def _extract_words(text):
    """Extract lowercase word tokens from text."""
    return set(re.findall(r'\w+', text.lower()))


def find_containment_suggestions(raw_results):
    """Find entries where one is contained in another.

    An entry A is "contained in" entry B if:
    1. A appears as a whole-word substring of B (case-insensitive), OR
    2. Every word in A appears in B's word set (strict subset, case-insensitive)

    Returns a list of suggestion dicts sorted by source name:
    [
        {
            "source": "shorter entry name",
            "source_pages": <int>,
            "containers": [
                {"entry": "longer entry", "pages": <int>},
                ...
            ],
            "target": "longest container entry name",
            "target_pages": <int>,
        },
        ...
    ]
    """
    if not raw_results:
        return []

    entries = list(raw_results.keys())

    # Pre-compute lowercase and word sets
    entry_data = {}
    for e in entries:
        lower = e.lower().strip()
        words = _extract_words(e)
        entry_data[e] = (lower, words)

    suggestions = {}  # source -> list of container entries

    for a in entries:
        a_lower, a_words = entry_data[a]
        if not a_words:
            continue

        for b in entries:
            if a == b:
                continue
            b_lower, b_words = entry_data[b]
            if not b_words:
                continue

            # A must be strictly "smaller" than B
            if len(a_words) > len(b_words):
                continue
            if len(a_words) == len(b_words) and len(a) >= len(b):
                continue

            is_contained = False

            # 1. Whole-string containment with word boundaries
            #    Prevents "Well" matching in "Farewell"
            pattern = r'\b' + re.escape(a_lower) + r'\b'
            if re.search(pattern, b_lower):
                is_contained = True

            # 2. Word element containment (strict subset)
            if not is_contained and a_words < b_words:
                is_contained = True

            if is_contained:
                if a not in suggestions:
                    suggestions[a] = []
                suggestions[a].append(b)

    result = []
    for source, containers in suggestions.items():
        # Sort containers by length descending (longest first = merge target)
        containers.sort(key=lambda x: (-len(x), x.lower()))
        target = containers[0]
        result.append({
            "source": source,
            "source_pages": len(raw_results.get(source, [])),
            "containers": [
                {"entry": c, "pages": len(raw_results.get(c, []))}
                for c in containers
            ],
            "target": target,
            "target_pages": len(raw_results.get(target, [])),
        })

    result.sort(key=lambda x: x["source"].lower())
    return result
