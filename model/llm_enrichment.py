"""Drive optional LLM enrichment passes over an existing rule-based index.

The single entry point is :func:`run_enrichment`, which dispatches to the
four feature passes guarded by per-feature toggles. Each pass tolerates
malformed model output and isolates failures per-term so one bad call does
not abort the whole run — same convention as the recent
``c5f455f fix: don't abort on slot exceptions`` commit on the rule-based
side.

The output shape is the ``suggestions`` dict consumed by
:mod:`model.enhanced_reports`:

.. code-block:: python

    {
        "subentries": {term: [{"label": str, "pages": str, "page_idxs": [int]}, ...]},
        "aliases":    [{"primary": str, "merged": [str, ...], "pages": str}, ...],
        "categories": {term: str},
        "see_also":   {term: [str, ...]},
    }
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from model import llm_client
from model import llm_run_state
from model.indexer import normalise_occurrence


PROGRESS_CB = Optional[Callable[[str], None]]


# ---------------------------------------------------------------------------
# Plan-and-execute scaffolding
# ---------------------------------------------------------------------------

# Tunable batch sizes — one task per batch. Lower numbers give finer-grained
# progress updates at the cost of more LLM round trips; higher numbers are
# faster but mean the progress bar moves in chunkier steps.
ALIAS_BATCH_SIZE = 100
CATEGORY_BATCH_SIZE = 50
SEEALSO_BATCH_SIZE = 30


@dataclass
class EnrichmentTask:
    """One unit of work in an enrichment plan.

    Each task corresponds to exactly one LLM call (or, in pathological
    cases like a totally empty batch, one trivial no-op). The ``id`` is
    stable for a given ``(raw_results, options, model, host)`` combination
    so resumed runs can recognise which tasks already finished.
    """
    id: str
    kind: str        # "subindex" | "alias" | "category" | "seealso"
    label: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EnrichmentTask":
        return cls(
            id=d.get("id", ""),
            kind=d.get("kind", ""),
            label=d.get("label", ""),
            payload=dict(d.get("payload") or {}),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _occurrences(raw_results: dict, term: str) -> List[tuple]:
    """Return normalised (page_idx, page_label, flags) tuples for *term*."""
    return [normalise_occurrence(o) for o in raw_results.get(term, [])]


def _format_pages_string(occurrences: List[tuple]) -> str:
    """Format a list of (page_idx, page_label, ...) as a comma-separated
    page-label string with simple range compression. Mirrors the format
    produced by ``IndexingThread.process_results`` for consistency."""
    if not occurrences:
        return ""
    occurrences = sorted(occurrences, key=lambda o: o[0])
    ranges: list[list[tuple]] = [[occurrences[0]]]
    for prev, curr in zip(occurrences, occurrences[1:]):
        if curr[0] == prev[0] + 1:
            ranges[-1].append(curr)
        else:
            ranges.append([curr])
    parts = []
    for r in ranges:
        if len(r) == 1:
            parts.append(r[0][1])
        else:
            parts.append(f"{r[0][1]}-{r[-1][1]}")
    return ", ".join(parts)


def _occurrences_with_context(occurrences: List[tuple]) -> List[tuple]:
    """Return only the occurrences that carry a non-empty context string."""
    out = []
    for occ in occurrences:
        flags = occ[2] if len(occ) >= 3 else {}
        if isinstance(flags, dict) and flags.get("context"):
            out.append(occ)
    return out


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SUBINDEX_PROMPT = """You are helping create a back-of-book index for a published book.

The term "{term}" appears on many pages of the book. Below is a short context excerpt for each occurrence, labelled by page.

Group the occurrences into 2 to 6 thematic sub-entries. Each sub-entry must have:
  - a concise label (1 to 5 words, lower-case unless a proper noun)
  - the list of page labels (exactly as given) belonging to that group

Every page must belong to exactly one sub-entry. Do not invent page numbers. Do not add prose, explanation, or any text outside the JSON object.

OCCURRENCES:
{occurrences_block}

Return strict JSON in exactly this shape and nothing else:
{{"subentries": [{{"label": "string", "pages": ["page_label", ...]}}]}}
"""


# ---------------------------------------------------------------------------
# Phase 2: sub-indexing
# ---------------------------------------------------------------------------

def propose_subentries_for_term(
    term: str,
    occurrences: List[tuple],
    host: str,
    model: str,
) -> List[dict]:
    """Cluster *occurrences* of *term* into themed sub-entries.

    Returns a list of dicts with keys ``label``, ``pages`` (already
    range-compressed), and ``page_idxs`` (the matched 0-based page
    indices). Returns an empty list on any failure — never raises.
    """
    occ_with_ctx = _occurrences_with_context(occurrences)
    if len(occ_with_ctx) < 2:
        return []

    label_to_idx = {}
    occurrences_block_lines = []
    for idx, label, flags in occ_with_ctx:
        ctx = flags.get("context", "") if isinstance(flags, dict) else ""
        label_to_idx[label] = idx
        # Truncate very long contexts so the prompt stays small.
        snippet = ctx if len(ctx) <= 240 else ctx[:240].rstrip() + "..."
        occurrences_block_lines.append(f"- Page {label}: {snippet}")

    prompt = SUBINDEX_PROMPT.format(
        term=term,
        occurrences_block="\n".join(occurrences_block_lines),
    )

    response = llm_client.complete(
        prompt=prompt,
        model=model,
        host=host,
        fmt="json",
        timeout=180,
    )
    if not isinstance(response, dict):
        return []
    raw_subs = response.get("subentries")
    if not isinstance(raw_subs, list) or not raw_subs:
        return []

    out: List[dict] = []
    for sub in raw_subs:
        if not isinstance(sub, dict):
            continue
        label = (sub.get("label") or "").strip()
        pages = sub.get("pages") or []
        if not label or not isinstance(pages, list):
            continue
        # Map the page labels back to the original occurrence tuples we
        # know exist; ignore hallucinated labels.
        sub_occurrences = []
        for plabel in pages:
            plabel_str = str(plabel)
            if plabel_str in label_to_idx:
                idx = label_to_idx[plabel_str]
                # Find the original tuple
                for o in occurrences:
                    if o[0] == idx:
                        sub_occurrences.append(o)
                        break
        if not sub_occurrences:
            continue
        out.append({
            "label": label,
            "pages": _format_pages_string(sub_occurrences),
            "page_idxs": sorted({o[0] for o in sub_occurrences}),
        })
    return out


def propose_subentries(
    raw_results: dict,
    host: str,
    model: str,
    threshold: int = 8,
    progress_cb: PROGRESS_CB = None,
) -> Dict[str, List[dict]]:
    """Run sub-indexing across all entries above *threshold* page references.

    Each term is processed independently — a failure on one does not abort
    the run. ``progress_cb(message)`` is called once per term so a UI can
    show live status text.
    """
    out: Dict[str, List[dict]] = {}
    if not raw_results:
        return out

    candidate_terms = [
        t for t, occs in raw_results.items() if len(occs) >= threshold
    ]
    candidate_terms.sort(key=lambda t: -len(raw_results.get(t, [])))

    for term in candidate_terms:
        if progress_cb:
            progress_cb(f"Sub-indexing '{term}' ({len(raw_results[term])} pages)...")
        try:
            occurrences = _occurrences(raw_results, term)
            subs = propose_subentries_for_term(term, occurrences, host, model)
        except Exception as exc:  # pragma: no cover — defensive isolation
            if progress_cb:
                progress_cb(f"  skipped '{term}': {exc}")
            continue
        if subs:
            out[term] = subs
    return out


# ---------------------------------------------------------------------------
# Phase 3: alias / synonym merging  (stub — populated in Phase 3)
# ---------------------------------------------------------------------------

ALIAS_PROMPT = """You are helping deduplicate entries in a back-of-book index.

The list below contains index entries that might refer to the same person, place, or thing under different names (e.g. "Beethoven" and "Ludwig van Beethoven", "Bach" and "J. S. Bach"). For each cluster you find, return one sub-array.

ENTRIES:
{entries_block}

Return strict JSON in this shape and nothing else (an empty array means no aliases were found):
{{"aliases": [{{"primary": "canonical name", "merged": ["alias1", "alias2", ...]}}]}}
"""


def propose_alias_batch(
    entries_batch: List[str],
    raw_results: dict,
    host: str,
    model: str,
) -> List[dict]:
    """Run alias detection on a single batch of entries (one LLM call).

    Returns merge candidates restricted to *entries_batch* — both the
    primary and the merged aliases must come from the batch. Hallucinated
    names are dropped.
    """
    if not entries_batch or len(entries_batch) < 2:
        return []

    block = "\n".join(f"- {e}" for e in entries_batch)
    prompt = ALIAS_PROMPT.format(entries_block=block)
    response = llm_client.complete(
        prompt=prompt, model=model, host=host, fmt="json", timeout=180,
    )
    if not isinstance(response, dict):
        return []
    raw_aliases = response.get("aliases") or []
    if not isinstance(raw_aliases, list):
        return []

    batch_set = set(entries_batch)
    out: List[dict] = []
    for grp in raw_aliases:
        if not isinstance(grp, dict):
            continue
        primary = (grp.get("primary") or "").strip()
        merged = grp.get("merged") or []
        if not primary or not isinstance(merged, list):
            continue
        merged_real = [
            m for m in merged
            if isinstance(m, str) and m in batch_set and m != primary
        ]
        if primary not in batch_set or not merged_real:
            continue
        combined: list[tuple] = []
        seen_idx: set = set()
        for name in [primary] + merged_real:
            for occ in _occurrences(raw_results, name):
                if occ[0] not in seen_idx:
                    seen_idx.add(occ[0])
                    combined.append(occ)
        out.append({
            "primary": primary,
            "merged": merged_real,
            "pages": _format_pages_string(combined),
        })
    return out


def propose_alias_merges(
    raw_results: dict,
    host: str,
    model: str,
    progress_cb: PROGRESS_CB = None,
) -> List[dict]:
    """Suggest entries that are aliases of each other and should be merged.

    Backwards-compatible wrapper: chunks all entries into ``ALIAS_BATCH_SIZE``
    batches and concatenates the results. Used by the legacy synchronous
    code path; the new plan-execute-persist path uses
    :func:`propose_alias_batch` directly.
    """
    if not raw_results:
        return []
    entries = sorted(raw_results.keys(), key=str.lower)
    if len(entries) < 2:
        return []

    out: List[dict] = []
    for start in range(0, len(entries), ALIAS_BATCH_SIZE):
        batch = entries[start:start + ALIAS_BATCH_SIZE]
        if progress_cb:
            progress_cb(
                f"Aliases {start + 1}-{start + len(batch)} of {len(entries)}..."
            )
        out.extend(propose_alias_batch(batch, raw_results, host, model))
    return out


# ---------------------------------------------------------------------------
# Phase 4: per-entry category tagging
# ---------------------------------------------------------------------------

CATEGORY_PROMPT = """You are categorising entries from a back-of-book index.

Choose ONE category per entry from this exact list:
  Person, Place, Work, Concept, Period, Instrument, Organisation, Event, Other

Respond with strict JSON mapping each entry to one category. No prose, no code fences.

ENTRIES:
{entries_block}

Return JSON in this shape:
{{"categories": {{"entry_name": "Person", ...}}}}
"""


CATEGORY_VALID = {
    "Person", "Place", "Work", "Concept", "Period",
    "Instrument", "Organisation", "Event", "Other",
}


def propose_categories_batch(
    entries_batch: List[str],
    raw_results: dict,
    host: str,
    model: str,
) -> Dict[str, str]:
    """One LLM call to categorise *entries_batch*. Invalid or out-of-batch
    entries in the response are silently dropped."""
    if not entries_batch:
        return {}
    block = "\n".join(f"- {e}" for e in entries_batch)
    prompt = CATEGORY_PROMPT.format(entries_block=block)
    response = llm_client.complete(
        prompt=prompt, model=model, host=host, fmt="json", timeout=180,
    )
    if not isinstance(response, dict):
        return {}
    cats = response.get("categories") or {}
    if not isinstance(cats, dict):
        return {}
    out: Dict[str, str] = {}
    batch_set = set(entries_batch)
    for name, cat in cats.items():
        if (name in batch_set and name in raw_results
                and isinstance(cat, str) and cat in CATEGORY_VALID):
            out[name] = cat
    return out


def propose_categories(
    raw_results: dict,
    host: str,
    model: str,
    progress_cb: PROGRESS_CB = None,
    batch_size: int = CATEGORY_BATCH_SIZE,
) -> Dict[str, str]:
    """Tag every index entry with one of the canonical categories."""
    if not raw_results:
        return {}
    entries = sorted(raw_results.keys(), key=str.lower)
    out: Dict[str, str] = {}
    for start in range(0, len(entries), batch_size):
        batch = entries[start:start + batch_size]
        if progress_cb:
            progress_cb(
                f"Categorising entries {start + 1}-{start + len(batch)} of {len(entries)}..."
            )
        out.update(propose_categories_batch(batch, raw_results, host, model))
    return out


# ---------------------------------------------------------------------------
# Phase 5: see-also cross-references
# ---------------------------------------------------------------------------

SEEALSO_PROMPT = """You are suggesting cross-references for a back-of-book index.

For each entry, list up to 3 OTHER entries from the same index that a reader looking up the first might also want to consult. Only suggest entries that already exist in the list. If none are relevant, return an empty array.

ENTRIES:
{entries_block}

Return strict JSON in this shape:
{{"see_also": {{"entry_name": ["other_entry", "..."]}}}}
"""


def propose_see_also_batch(
    entries_batch: List[str],
    all_entries_set: set,
    host: str,
    model: str,
) -> Dict[str, List[str]]:
    """One LLM call to find see-also targets for *entries_batch*. Targets
    are constrained to entries that exist in *all_entries_set*. Self-loops
    and hallucinated targets are dropped."""
    if not entries_batch:
        return {}
    block = "\n".join(f"- {e}" for e in entries_batch)
    prompt = SEEALSO_PROMPT.format(entries_block=block)
    response = llm_client.complete(
        prompt=prompt, model=model, host=host, fmt="json", timeout=180,
    )
    if not isinstance(response, dict):
        return {}
    raw = response.get("see_also") or {}
    if not isinstance(raw, dict):
        return {}
    batch_set = set(entries_batch)
    out: Dict[str, List[str]] = {}
    for name, others in raw.items():
        if name not in batch_set or not isinstance(others, list):
            continue
        cleaned = [
            o for o in others
            if isinstance(o, str) and o != name and o in all_entries_set
        ]
        if cleaned:
            out[name] = cleaned[:3]
    return out


def propose_see_also(
    raw_results: dict,
    host: str,
    model: str,
    progress_cb: PROGRESS_CB = None,
    batch_size: int = SEEALSO_BATCH_SIZE,
) -> Dict[str, List[str]]:
    if not raw_results:
        return {}
    entries = sorted(raw_results.keys(), key=str.lower)
    entry_set = set(entries)
    out: Dict[str, List[str]] = {}
    for start in range(0, len(entries), batch_size):
        batch = entries[start:start + batch_size]
        if progress_cb:
            progress_cb(
                f"See-also for entries {start + 1}-{start + len(batch)} of {len(entries)}..."
            )
        out.update(propose_see_also_batch(batch, entry_set, host, model))
    return out


# ---------------------------------------------------------------------------
# Planner — turns the (raw_results, options) pair into a list of tasks
# ---------------------------------------------------------------------------

def plan_enrichment(
    raw_results: dict,
    options: Optional[dict] = None,
) -> List[EnrichmentTask]:
    """Build a deterministic list of :class:`EnrichmentTask`s for the
    given inputs.

    The list ordering puts the most user-visible work first (sub-indexing
    of the densest terms) so a long run produces useful output early.
    The ordering is also stable so resuming after a pause arrives at the
    same plan ids.
    """
    options = options or {}
    tasks: List[EnrichmentTask] = []
    if not raw_results:
        return tasks

    # 1. Sub-indexing — one task per dense term, sorted from densest first
    if options.get("subindex", True):
        threshold = int(options.get("threshold", 8))
        candidates = [
            (t, len(occs)) for t, occs in raw_results.items() if len(occs) >= threshold
        ]
        candidates.sort(key=lambda x: (-x[1], x[0].lower()))
        for term, page_count in candidates:
            tasks.append(EnrichmentTask(
                id=f"subindex:{term}",
                kind="subindex",
                label=f"Sub-index '{term}' ({page_count} pages)",
                payload={"term": term},
            ))

    sorted_entries = sorted(raw_results.keys(), key=str.lower)
    n = len(sorted_entries)

    # 2. Alias merges — one task per ALIAS_BATCH_SIZE entries
    if options.get("alias", True) and n >= 2:
        for batch_idx, start in enumerate(range(0, n, ALIAS_BATCH_SIZE)):
            batch = sorted_entries[start:start + ALIAS_BATCH_SIZE]
            tasks.append(EnrichmentTask(
                id=f"alias:{batch_idx}",
                kind="alias",
                label=f"Aliases ({start + 1}–{start + len(batch)} of {n})",
                payload={"entries": batch},
            ))

    # 3. Categories — one task per CATEGORY_BATCH_SIZE
    if options.get("category", True) and n >= 1:
        for batch_idx, start in enumerate(range(0, n, CATEGORY_BATCH_SIZE)):
            batch = sorted_entries[start:start + CATEGORY_BATCH_SIZE]
            tasks.append(EnrichmentTask(
                id=f"category:{batch_idx}",
                kind="category",
                label=f"Categorise ({start + 1}–{start + len(batch)} of {n})",
                payload={"entries": batch},
            ))

    # 4. See-also — one task per SEEALSO_BATCH_SIZE
    if options.get("seealso", True) and n >= 2:
        for batch_idx, start in enumerate(range(0, n, SEEALSO_BATCH_SIZE)):
            batch = sorted_entries[start:start + SEEALSO_BATCH_SIZE]
            tasks.append(EnrichmentTask(
                id=f"seealso:{batch_idx}",
                kind="seealso",
                label=f"See-also ({start + 1}–{start + len(batch)} of {n})",
                payload={"entries": batch},
            ))

    return tasks


# ---------------------------------------------------------------------------
# Executor — runs one task at a time and produces a suggestion fragment
# ---------------------------------------------------------------------------

def execute_task(
    task: EnrichmentTask,
    raw_results: dict,
    host: str,
    model: str,
    all_entries_set: Optional[set] = None,
) -> dict:
    """Run *task* against the LLM and return a suggestion fragment.

    The fragment uses the same shape as the accumulating ``suggestions``
    dict, but only contains values produced by *this* task. Failures
    return an empty fragment — callers must merge defensively.
    """
    fragment = {
        "subentries": {},
        "aliases": [],
        "categories": {},
        "see_also": {},
    }

    try:
        if task.kind == "subindex":
            term = task.payload.get("term", "")
            if not term or term not in raw_results:
                return fragment
            occurrences = _occurrences(raw_results, term)
            subs = propose_subentries_for_term(term, occurrences, host, model)
            if subs:
                fragment["subentries"][term] = subs

        elif task.kind == "alias":
            batch = list(task.payload.get("entries") or [])
            fragment["aliases"] = propose_alias_batch(
                batch, raw_results, host, model,
            )

        elif task.kind == "category":
            batch = list(task.payload.get("entries") or [])
            fragment["categories"] = propose_categories_batch(
                batch, raw_results, host, model,
            )

        elif task.kind == "seealso":
            batch = list(task.payload.get("entries") or [])
            entries_set = all_entries_set or set(raw_results.keys())
            fragment["see_also"] = propose_see_also_batch(
                batch, entries_set, host, model,
            )
    except Exception:  # pragma: no cover — defensive isolation
        # Per-task failure must never abort the run. Return an empty
        # fragment; the executor will log it.
        return {
            "subentries": {}, "aliases": [],
            "categories": {}, "see_also": {},
        }

    return fragment


def merge_fragment(accum: dict, fragment: dict) -> None:
    """In-place merge of a task's fragment into the accumulating dict."""
    if not fragment:
        return
    accum.setdefault("subentries", {}).update(fragment.get("subentries") or {})
    accum.setdefault("aliases", []).extend(fragment.get("aliases") or [])
    accum.setdefault("categories", {}).update(fragment.get("categories") or {})
    accum.setdefault("see_also", {}).update(fragment.get("see_also") or {})


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def run_enrichment(
    raw_results: dict,
    formatted: dict,
    host: str,
    model: str,
    options: Optional[dict] = None,
    progress_cb: PROGRESS_CB = None,
) -> dict:
    """Run all toggled enrichment passes and return a ``suggestions`` dict.

    *options* keys (all optional, default True):
      - ``subindex`` — sub-indexing
      - ``alias`` — alias / synonym merging
      - ``category`` — per-entry category tagging
      - ``seealso`` — see-also cross-references
      - ``threshold`` — int, min page-count for sub-indexing (default 8)
    """
    options = options or {}
    suggestions: dict = {
        "subentries": {},
        "aliases": [],
        "categories": {},
        "see_also": {},
    }

    if options.get("subindex", True):
        suggestions["subentries"] = propose_subentries(
            raw_results=raw_results,
            host=host,
            model=model,
            threshold=int(options.get("threshold", 8)),
            progress_cb=progress_cb,
        )

    if options.get("alias", True):
        suggestions["aliases"] = propose_alias_merges(
            raw_results=raw_results,
            host=host,
            model=model,
            progress_cb=progress_cb,
        )

    if options.get("category", True):
        suggestions["categories"] = propose_categories(
            raw_results=raw_results,
            host=host,
            model=model,
            progress_cb=progress_cb,
        )

    if options.get("seealso", True):
        suggestions["see_also"] = propose_see_also(
            raw_results=raw_results,
            host=host,
            model=model,
            progress_cb=progress_cb,
        )

    return suggestions


# ---------------------------------------------------------------------------
# Background thread wrapper
# ---------------------------------------------------------------------------

class LLMEnrichmentThread(QThread):
    """Runs the enrichment plan off the UI thread, one task at a time.

    Emits :attr:`planned` once the plan is built so the UI can size its
    progress bar; emits :attr:`progress` and :attr:`partial_result` after
    every task so the panel re-renders incrementally; emits
    :attr:`finished_with_results` once at the end with the final status
    (``"completed"`` / ``"paused"`` / ``"cancelled"``).

    Pause and cancel are cooperative: the thread checks the flags between
    tasks (never mid-call) so the in-flight LLM call always completes and
    its result is cached / persisted before the thread exits.

    When *project_path* is set the thread persists a :class:`RunState` to
    ``<project>/llm_run.json`` after each task and appends a line to
    ``<project>/llm_run.log``. When *resume_state* is set the thread skips
    tasks already in ``completed_ids`` and starts the partial-suggestions
    accumulator from the saved snapshot.
    """

    planned = pyqtSignal(int)                  # total
    progress = pyqtSignal(int, int, str)       # done, total, label
    partial_result = pyqtSignal(dict)          # current accumulated suggestions
    finished_with_results = pyqtSignal(dict, str)  # suggestions, status

    def __init__(
        self,
        raw_results: dict,
        formatted: dict,
        host: str,
        model: str,
        options: dict,
        project_path: Optional[str] = None,
        resume_state: Optional[llm_run_state.RunState] = None,
    ):
        super().__init__()
        self._raw = raw_results or {}
        self._formatted = formatted or {}
        self._host = host
        self._model = model
        self._options = options or {}
        self._project_path = project_path
        self._resume_state = resume_state
        self._pause_requested = False
        self._cancel_requested = False

    # ---- Cooperative interruption ---------------------------------------

    def request_pause(self):
        """Ask the thread to finish the current task, persist, and stop."""
        self._pause_requested = True

    def request_cancel(self):
        """Ask the thread to finish the current task, mark cancelled, and stop.

        The state file is left intact with ``status=cancelled``; the
        controller deletes it once the user has confirmed (so they can
        still inspect partial results until then).
        """
        self._cancel_requested = True

    # ---- Main loop ------------------------------------------------------

    def run(self):
        # 1. Build / restore the plan and accumulator
        if self._resume_state is not None:
            tasks = [
                EnrichmentTask.from_dict(t) for t in self._resume_state.plan
            ]
            completed_ids = set(self._resume_state.completed_ids)
            suggestions = dict(self._resume_state.suggestions or {
                "subentries": {}, "aliases": [],
                "categories": {}, "see_also": {},
            })
            state = self._resume_state
            state.status = "running"
            llm_run_state.append_log(
                self._project_path,
                f"Resumed from state file at {len(completed_ids)}/{len(tasks)}",
            )
        else:
            tasks = plan_enrichment(self._raw, self._options)
            plan_dicts = [t.to_dict() for t in tasks]
            state = llm_run_state.make_run_state(
                plan=plan_dicts,
                raw_results=self._raw,
                options=self._options,
                model=self._model,
                host=self._host,
            )
            completed_ids = set()
            suggestions = dict(state.suggestions)
            llm_run_state.save(state, self._project_path)
            llm_run_state.append_log(
                self._project_path,
                f"Run started: {len(tasks)} tasks planned (model {self._model})",
            )

        total = len(tasks)
        self.planned.emit(total)

        # If nothing to do, finish immediately
        if total == 0:
            state.status = "completed"
            llm_run_state.save(state, self._project_path)
            self.finished_with_results.emit(suggestions, "completed")
            return

        # Pre-emit current progress (covers the resume case)
        done = sum(1 for t in tasks if t.id in completed_ids)
        self.progress.emit(done, total, "Starting...")
        self.partial_result.emit(dict(suggestions))

        all_entries_set = set(self._raw.keys())

        # 2. Iterate the plan
        for task in tasks:
            if task.id in completed_ids:
                continue

            # Cooperative interruption check — between tasks only.
            if self._cancel_requested:
                state.status = "cancelled"
                state.suggestions = suggestions
                state.completed_ids = sorted(completed_ids)
                llm_run_state.save(state, self._project_path)
                llm_run_state.append_log(
                    self._project_path,
                    f"Cancelled at {done}/{total} by user",
                )
                self.finished_with_results.emit(dict(suggestions), "cancelled")
                return
            if self._pause_requested:
                state.status = "paused"
                state.suggestions = suggestions
                state.completed_ids = sorted(completed_ids)
                llm_run_state.save(state, self._project_path)
                llm_run_state.append_log(
                    self._project_path,
                    f"Paused at {done}/{total} by user",
                )
                self.finished_with_results.emit(dict(suggestions), "paused")
                return

            self.progress.emit(done, total, f"{task.label}")
            t0 = time.monotonic()
            try:
                fragment = execute_task(
                    task=task,
                    raw_results=self._raw,
                    host=self._host,
                    model=self._model,
                    all_entries_set=all_entries_set,
                )
            except Exception as exc:  # pragma: no cover — final safety net
                fragment = None
                llm_run_state.append_log(
                    self._project_path,
                    f"Task {done + 1}/{total} ERROR: {task.id}: {exc}",
                    level="ERR",
                )

            if fragment:
                merge_fragment(suggestions, fragment)

            completed_ids.add(task.id)
            done += 1
            elapsed = time.monotonic() - t0

            # Persist after every task — atomic writes mean closing the
            # app cannot leave a corrupt state file.
            state.suggestions = suggestions
            state.completed_ids = sorted(completed_ids)
            state.status = "running"
            llm_run_state.save(state, self._project_path)
            llm_run_state.append_log(
                self._project_path,
                f"Task {done}/{total} OK: {task.id} ({elapsed:.1f}s)",
            )

            self.progress.emit(done, total, task.label)
            self.partial_result.emit(dict(suggestions))

        # 3. Mark complete
        state.status = "completed"
        state.suggestions = suggestions
        state.completed_ids = sorted(completed_ids)
        llm_run_state.save(state, self._project_path)
        llm_run_state.append_log(
            self._project_path,
            f"Run complete: {done}/{total} tasks",
        )
        self.finished_with_results.emit(dict(suggestions), "completed")
