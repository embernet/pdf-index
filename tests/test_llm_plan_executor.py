"""Tests for the plan-and-execute machinery in llm_enrichment.

Verifies:
* the planner produces the expected number / order of tasks for known inputs
* execute_task dispatches to the right per-batch helper for each kind
* the merge_fragment accumulator is associative
* the LLMEnrichmentThread persists state after each task and supports
  resume from a saved state with completed_ids skipped
"""
from __future__ import annotations

import time

import pytest

from model import llm_enrichment as enrich
from model import llm_run_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _occ(idx, ctx="ctx"):
    return (idx, str(idx + 1), {
        "italic": False, "bold": False, "caps": False,
        "single-quotes": False, "context": ctx,
    })


def _raw_with(terms_and_pages):
    """terms_and_pages = [("Chopin", 12), ("Bach", 3), ...]"""
    return {term: [_occ(i) for i in range(n)] for term, n in terms_and_pages}


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

def test_plan_includes_subindex_only_for_dense_terms():
    raw = _raw_with([("Chopin", 12), ("Bach", 3), ("Beethoven", 9)])
    tasks = enrich.plan_enrichment(raw, {
        "subindex": True, "alias": False, "category": False,
        "seealso": False, "threshold": 8,
    })
    sub_terms = [t.payload["term"] for t in tasks if t.kind == "subindex"]
    assert "Chopin" in sub_terms
    assert "Beethoven" in sub_terms
    assert "Bach" not in sub_terms


def test_plan_orders_subindex_by_density():
    raw = _raw_with([("Sparse", 8), ("Dense", 50), ("Mid", 20)])
    tasks = enrich.plan_enrichment(raw, {
        "subindex": True, "alias": False, "category": False,
        "seealso": False, "threshold": 5,
    })
    sub_kind = [t for t in tasks if t.kind == "subindex"]
    assert [t.payload["term"] for t in sub_kind] == ["Dense", "Mid", "Sparse"]


def test_plan_chunks_categories_into_batches():
    # 120 entries, batch size 50 -> 3 tasks
    raw = {f"Entry{i:03d}": [_occ(i)] for i in range(120)}
    tasks = enrich.plan_enrichment(raw, {
        "subindex": False, "alias": False, "category": True,
        "seealso": False, "threshold": 100,
    })
    cat_tasks = [t for t in tasks if t.kind == "category"]
    assert len(cat_tasks) == 3
    # Batch sizes 50, 50, 20
    sizes = [len(t.payload["entries"]) for t in cat_tasks]
    assert sizes == [50, 50, 20]


def test_plan_is_deterministic():
    raw = _raw_with([("Chopin", 30), ("Bach", 5), ("Mozart", 12)])
    options = {
        "subindex": True, "alias": True,
        "category": True, "seealso": True, "threshold": 8,
    }
    plan_a = enrich.plan_enrichment(raw, options)
    plan_b = enrich.plan_enrichment(raw, options)
    assert [t.id for t in plan_a] == [t.id for t in plan_b]


def test_plan_respects_toggles():
    raw = _raw_with([("X", 20)])
    tasks = enrich.plan_enrichment(raw, {
        "subindex": False, "alias": False, "category": False,
        "seealso": False, "threshold": 1,
    })
    assert tasks == []


def test_plan_skips_alias_when_too_few_entries():
    raw = {"Solo": [_occ(0)]}
    tasks = enrich.plan_enrichment(raw, {
        "subindex": False, "alias": True, "category": False,
        "seealso": False, "threshold": 100,
    })
    assert all(t.kind != "alias" for t in tasks)


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

def test_execute_task_subindex_delegates_to_term_helper(monkeypatch):
    raw = {"Chopin": [_occ(i, ctx=f"c{i}") for i in range(10)]}
    captured = {}

    def fake(term, occurrences, host, model):
        captured["term"] = term
        captured["count"] = len(occurrences)
        return [{"label": "x", "pages": "1", "page_idxs": [0]}]

    monkeypatch.setattr(enrich, "propose_subentries_for_term", fake)
    task = enrich.EnrichmentTask(
        id="subindex:Chopin", kind="subindex", label="...",
        payload={"term": "Chopin"},
    )
    fragment = enrich.execute_task(task, raw, host="x", model="m")
    assert captured["term"] == "Chopin"
    assert "Chopin" in fragment["subentries"]


def test_execute_task_unknown_kind_returns_empty():
    fragment = enrich.execute_task(
        enrich.EnrichmentTask(id="foo:0", kind="foo", label="x"),
        raw_results={}, host="x", model="m",
    )
    assert fragment == {
        "subentries": {}, "aliases": [],
        "categories": {}, "see_also": {},
    }


def test_merge_fragment_accumulates():
    accum = {
        "subentries": {}, "aliases": [],
        "categories": {}, "see_also": {},
    }
    enrich.merge_fragment(accum, {
        "subentries": {"A": [{"label": "x"}]},
        "categories": {"A": "Person"},
    })
    enrich.merge_fragment(accum, {
        "aliases": [{"primary": "A", "merged": ["a"]}],
        "see_also": {"A": ["B"]},
    })
    assert "A" in accum["subentries"]
    assert accum["categories"]["A"] == "Person"
    assert len(accum["aliases"]) == 1
    assert accum["see_also"]["A"] == ["B"]


# ---------------------------------------------------------------------------
# Thread persistence and resume
# ---------------------------------------------------------------------------

@pytest.fixture
def qapp():
    """Minimal QApplication for QThread testing."""
    from PyQt6.QtWidgets import QApplication
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _drive_thread(thread):
    """Run the thread synchronously by calling .run() directly.

    QThread.run() is the body — we don't need event-loop dispatch in the
    test since the signals fire as direct Qt-emit calls and we connect
    plain Python receivers.
    """
    captured = {
        "planned": [], "progress": [], "partial": [], "finished": [],
    }
    thread.planned.connect(lambda n: captured["planned"].append(n))
    thread.progress.connect(
        lambda done, total, label: captured["progress"].append((done, total, label))
    )
    thread.partial_result.connect(
        lambda s: captured["partial"].append(dict(s))
    )
    thread.finished_with_results.connect(
        lambda s, status: captured["finished"].append((dict(s), status))
    )
    thread.run()
    return captured


def test_thread_persists_state_after_each_task(qapp, tmp_path, monkeypatch):
    raw = {f"E{i}": [_occ(0)] for i in range(60)}
    # Simple complete: returns a category for the first entry of each batch
    monkeypatch.setattr(
        enrich.llm_client, "complete",
        lambda **kw: {"categories": {"E0": "Person", "E50": "Place"}},
    )
    options = {
        "subindex": False, "alias": False,
        "category": True, "seealso": False, "threshold": 100,
    }
    thread = enrich.LLMEnrichmentThread(
        raw_results=raw, formatted={}, hosts=["x"], model="m",
        options=options, project_path=str(tmp_path),
    )
    captured = _drive_thread(thread)

    # Plan: 60 entries / 50 = 2 category tasks
    assert captured["planned"] == [2]
    # progress fires (start hint + 2 starts + 2 ends) — final reaches 2/2
    assert captured["progress"][-1][:2] == (2, 2)
    # finished status is "completed"
    assert captured["finished"][-1][1] == "completed"

    state = llm_run_state.load(str(tmp_path))
    assert state is not None
    assert state.status == "completed"
    assert state.total() == 2
    assert state.done() == 2


def test_thread_resumes_from_saved_state(qapp, tmp_path, monkeypatch):
    # Use fixed-width keys so string-sort and numeric-sort agree.
    raw = {f"E{i:03d}": [_occ(0)] for i in range(60)}
    options = {
        "subindex": False, "alias": False,
        "category": True, "seealso": False, "threshold": 100,
    }
    plan = enrich.plan_enrichment(raw, options)
    assert len(plan) == 2
    plan_dicts = [t.to_dict() for t in plan]

    # Pretend the first task already finished previously
    state = llm_run_state.make_run_state(
        plan=plan_dicts, raw_results=raw, options=options,
        model="m", host="x",
    )
    state.completed_ids = [plan[0].id]
    state.suggestions = {
        "subentries": {}, "aliases": [],
        "categories": {"E000": "Person"},
        "see_also": {},
    }
    state.status = "paused"
    llm_run_state.save(state, str(tmp_path))

    # Track which tasks call complete — only the *second* one should
    call_count = {"n": 0}

    def fake_complete(**kw):
        call_count["n"] += 1
        # The second batch starts at index 50 → "E050" (sorted entries)
        return {"categories": {"E050": "Place"}}

    monkeypatch.setattr(enrich.llm_client, "complete", fake_complete)
    thread = enrich.LLMEnrichmentThread(
        raw_results=raw, formatted={}, hosts=["x"], model="m",
        options=options, project_path=str(tmp_path),
        resume_state=state,
    )
    captured = _drive_thread(thread)

    # Only one task ran (the second one)
    assert call_count["n"] == 1
    final_suggestions, status = captured["finished"][-1]
    assert status == "completed"
    # Both categories survived — the resumed one and the new one
    assert final_suggestions["categories"]["E000"] == "Person"
    assert final_suggestions["categories"]["E050"] == "Place"


def test_thread_pause_halts_after_current_task(qapp, tmp_path, monkeypatch):
    raw = {f"E{i}": [_occ(0)] for i in range(150)}
    options = {
        "subindex": False, "alias": False,
        "category": True, "seealso": False, "threshold": 100,
    }
    # 3 tasks total. We'll pause after the first.
    call_count = {"n": 0}

    def fake_complete(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # request pause as soon as the first task completes
            thread.request_pause()
        return {"categories": {}}

    monkeypatch.setattr(enrich.llm_client, "complete", fake_complete)
    thread = enrich.LLMEnrichmentThread(
        raw_results=raw, formatted={}, hosts=["x"], model="m",
        options=options, project_path=str(tmp_path),
    )
    captured = _drive_thread(thread)

    final_status = captured["finished"][-1][1]
    assert final_status == "paused"
    # Only the first task ran before pause kicked in
    assert call_count["n"] == 1
    state = llm_run_state.load(str(tmp_path))
    assert state.status == "paused"
    assert state.done() == 1


def test_thread_cancel_halts_after_current_task(qapp, tmp_path, monkeypatch):
    raw = {f"E{i}": [_occ(0)] for i in range(150)}
    options = {
        "subindex": False, "alias": False,
        "category": True, "seealso": False, "threshold": 100,
    }
    call_count = {"n": 0}

    def fake_complete(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            thread.request_cancel()
        return {"categories": {}}

    monkeypatch.setattr(enrich.llm_client, "complete", fake_complete)
    thread = enrich.LLMEnrichmentThread(
        raw_results=raw, formatted={}, hosts=["x"], model="m",
        options=options, project_path=str(tmp_path),
    )
    captured = _drive_thread(thread)

    assert captured["finished"][-1][1] == "cancelled"
    assert call_count["n"] == 1
    state = llm_run_state.load(str(tmp_path))
    # State file is left intact with "cancelled" status; controller decides to delete.
    assert state.status == "cancelled"


def test_thread_writes_log_lines(qapp, tmp_path, monkeypatch):
    raw = {f"E{i}": [_occ(0)] for i in range(10)}
    options = {
        "subindex": False, "alias": False,
        "category": True, "seealso": False, "threshold": 100,
    }
    monkeypatch.setattr(enrich.llm_client, "complete", lambda **kw: {})
    thread = enrich.LLMEnrichmentThread(
        raw_results=raw, formatted={}, hosts=["x"], model="m",
        options=options, project_path=str(tmp_path),
    )
    _drive_thread(thread)

    log_text = open(llm_run_state.log_path(str(tmp_path))).read()
    assert "Run started" in log_text
    assert "Task 1/1" in log_text
    assert "Run complete" in log_text
