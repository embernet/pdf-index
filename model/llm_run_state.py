"""Persistence for an in-progress LLM enrichment run.

The state file ``<project>/llm_run.json`` lets a long-running enrichment
survive app restarts: each completed task is recorded, along with the
accumulated suggestions, so the user can pause / close the app / reopen
and resume from where they left off.

A second file, ``<project>/llm_run.log``, is an append-only timestamped
trail of activity for human inspection. It is *not* used for recovery —
the JSON state file is authoritative.

The module is dependency-free (stdlib only) and safe to import on any
platform.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


STATE_FILENAME = "llm_run.json"
LOG_FILENAME = "llm_run.log"


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    """Snapshot of a single LLM enrichment run.

    ``status`` is one of ``"running"``, ``"paused"``, ``"completed"``,
    ``"cancelled"``. A status of ``"running"`` in a state file loaded from
    disk indicates the previous session was interrupted (the app closed or
    crashed mid-run); the controller treats it as ``"paused"`` for UI
    purposes.
    """
    run_id: str
    raw_results_hash: str
    options_hash: str
    model: str
    host: str
    plan: List[dict] = field(default_factory=list)
    completed_ids: List[str] = field(default_factory=list)
    suggestions: dict = field(default_factory=lambda: {
        "subentries": {}, "aliases": [], "categories": {}, "see_also": {},
    })
    status: str = "running"
    started_at: str = ""
    updated_at: str = ""

    def total(self) -> int:
        return len(self.plan)

    def done(self) -> int:
        # Cap at total — a malformed file might list completed_ids no longer in plan.
        completed_set = set(self.completed_ids)
        plan_ids = {t.get("id") for t in self.plan if isinstance(t, dict)}
        return len(completed_set & plan_ids)

    def remaining_tasks(self) -> List[dict]:
        completed_set = set(self.completed_ids)
        return [t for t in self.plan if t.get("id") not in completed_set]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        # Tolerate older / partial state files by filling missing fields with
        # safe defaults rather than raising.
        return cls(
            run_id=data.get("run_id", ""),
            raw_results_hash=data.get("raw_results_hash", ""),
            options_hash=data.get("options_hash", ""),
            model=data.get("model", ""),
            host=data.get("host", ""),
            plan=list(data.get("plan") or []),
            completed_ids=list(data.get("completed_ids") or []),
            suggestions=dict(data.get("suggestions") or {
                "subentries": {}, "aliases": [],
                "categories": {}, "see_also": {},
            }),
            status=data.get("status", "running"),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
        )


# ---------------------------------------------------------------------------
# Hashing — used to detect drift in the underlying index or options
# ---------------------------------------------------------------------------

def _stable_json(value: Any) -> str:
    """JSON-serialise *value* with stable ordering, tuples-as-lists,
    sorted keys. Used as the hashable canonical form."""
    def default(o):
        if isinstance(o, tuple):
            return list(o)
        if isinstance(o, set):
            return sorted(o)
        return str(o)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=default)


def hash_raw_results(raw_results: Optional[dict]) -> str:
    canonical = {}
    for term, occurrences in (raw_results or {}).items():
        canonical[term] = [list(occ) if isinstance(occ, tuple) else occ
                           for occ in occurrences]
    payload = _stable_json(canonical)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_options(options: Optional[dict], model: str = "", host: str = "") -> str:
    payload = _stable_json({
        "options": options or {},
        "model": model or "",
        "host": host or "",
    })
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# State file persistence
# ---------------------------------------------------------------------------

def state_path(project_path: str) -> str:
    return os.path.join(project_path, STATE_FILENAME)


def log_path(project_path: str) -> str:
    return os.path.join(project_path, LOG_FILENAME)


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def save(state: RunState, project_path: str) -> None:
    """Atomically persist *state* to ``<project>/llm_run.json``.

    Uses ``os.replace`` so a power loss mid-write leaves either the old or
    new file intact, never a partial one.
    """
    if not project_path:
        return
    state.updated_at = now_iso()
    path = state_path(project_path)
    tmp = path + ".tmp"
    payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False, default=str)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    except OSError:
        # Best effort — if we can't persist we still want the run to continue
        # in memory. The controller will surface the failure to the user.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def load(project_path: str) -> Optional[RunState]:
    """Return the RunState at ``<project>/llm_run.json`` or None if absent
    or unreadable."""
    if not project_path:
        return None
    path = state_path(project_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RunState.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None


def clear(project_path: str) -> None:
    """Remove the state file. The log file is left in place as an
    historical record."""
    if not project_path:
        return
    path = state_path(project_path)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def append_log(project_path: str, message: str, level: str = "INFO") -> None:
    """Append a timestamped line to the run log. Silent on failure."""
    if not project_path or not message:
        return
    line = f"{now_iso()} [{level}] {message}\n"
    try:
        with open(log_path(project_path), "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def has_drifted(state: RunState, raw_results: dict, options: dict,
                model: str, host: str) -> bool:
    """True if the current inputs no longer match the snapshotted ones —
    i.e. the user has re-run the rule-based index, changed toggles, or
    switched model/host since the run was paused."""
    if not state:
        return False
    return (
        hash_raw_results(raw_results) != state.raw_results_hash
        or hash_options(options, model, host) != state.options_hash
    )


# ---------------------------------------------------------------------------
# Construction helper
# ---------------------------------------------------------------------------

def make_run_state(
    plan: List[dict],
    raw_results: dict,
    options: dict,
    model: str,
    host: str,
) -> RunState:
    """Build a fresh RunState ready to persist before execution starts."""
    now = now_iso()
    return RunState(
        run_id=now,
        raw_results_hash=hash_raw_results(raw_results),
        options_hash=hash_options(options, model, host),
        model=model or "",
        host=host or "",
        plan=plan or [],
        completed_ids=[],
        suggestions={
            "subentries": {}, "aliases": [],
            "categories": {}, "see_also": {},
        },
        status="running",
        started_at=now,
        updated_at=now,
    )
