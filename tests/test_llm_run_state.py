"""Tests for the LLM enrichment run-state persistence module."""
import json
import os

import pytest

from model import llm_run_state as rs


SAMPLE_RAW = {
    "Chopin": [(11, "12", {"italic": False, "context": "ctx"})],
    "Beethoven": [(20, "21", {"italic": False})],
}

SAMPLE_OPTIONS = {"subindex": True, "alias": True, "threshold": 8}


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_raw_hash_is_stable_across_dict_orderings():
    a = {"A": [(1, "1", {})], "B": [(2, "2", {})]}
    b = {"B": [(2, "2", {})], "A": [(1, "1", {})]}
    assert rs.hash_raw_results(a) == rs.hash_raw_results(b)


def test_raw_hash_changes_when_pages_change():
    a = {"Chopin": [(1, "1", {})]}
    b = {"Chopin": [(1, "1", {}), (2, "2", {})]}
    assert rs.hash_raw_results(a) != rs.hash_raw_results(b)


def test_raw_hash_treats_tuples_and_lists_consistently():
    a = {"Chopin": [(1, "1", {"italic": False})]}
    b = {"Chopin": [[1, "1", {"italic": False}]]}
    assert rs.hash_raw_results(a) == rs.hash_raw_results(b)


def test_options_hash_changes_when_model_changes():
    h1 = rs.hash_options(SAMPLE_OPTIONS, model="qwen2.5:7b", host="x")
    h2 = rs.hash_options(SAMPLE_OPTIONS, model="llama3.1:8b", host="x")
    assert h1 != h2


def test_options_hash_changes_when_threshold_changes():
    h1 = rs.hash_options({"threshold": 8}, "m", "h")
    h2 = rs.hash_options({"threshold": 12}, "m", "h")
    assert h1 != h2


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def _make_state():
    plan = [
        {"id": "subindex:Chopin", "kind": "subindex", "label": "...", "payload": {}},
        {"id": "category:0", "kind": "category", "label": "...", "payload": {}},
    ]
    return rs.make_run_state(
        plan=plan,
        raw_results=SAMPLE_RAW,
        options=SAMPLE_OPTIONS,
        model="qwen2.5:7b",
        host="http://localhost:11434",
    )


def test_save_and_load_round_trip(tmp_path):
    state = _make_state()
    rs.save(state, str(tmp_path))
    loaded = rs.load(str(tmp_path))
    assert loaded is not None
    assert loaded.run_id == state.run_id
    assert loaded.plan == state.plan
    assert loaded.status == "running"


def test_load_returns_none_if_no_file(tmp_path):
    assert rs.load(str(tmp_path)) is None


def test_load_returns_none_for_corrupt_file(tmp_path):
    path = rs.state_path(str(tmp_path))
    with open(path, "w") as f:
        f.write("{not valid json")
    assert rs.load(str(tmp_path)) is None


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    state = _make_state()
    rs.save(state, str(tmp_path))
    children = os.listdir(str(tmp_path))
    assert "llm_run.json" in children
    assert all(not c.endswith(".tmp") for c in children)


def test_clear_removes_state_file(tmp_path):
    state = _make_state()
    rs.save(state, str(tmp_path))
    rs.clear(str(tmp_path))
    assert not os.path.exists(rs.state_path(str(tmp_path)))


def test_clear_is_idempotent(tmp_path):
    rs.clear(str(tmp_path))   # no file yet — must not raise


# ---------------------------------------------------------------------------
# Done / remaining accounting
# ---------------------------------------------------------------------------

def test_done_count_only_counts_ids_in_plan():
    state = _make_state()
    state.completed_ids = ["subindex:Chopin", "ghost:not-in-plan"]
    assert state.done() == 1
    assert state.total() == 2


def test_remaining_tasks_skips_completed():
    state = _make_state()
    state.completed_ids = ["subindex:Chopin"]
    remaining = state.remaining_tasks()
    assert len(remaining) == 1
    assert remaining[0]["id"] == "category:0"


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def test_drift_false_when_inputs_match():
    state = _make_state()
    assert rs.has_drifted(state, SAMPLE_RAW, SAMPLE_OPTIONS,
                          model="qwen2.5:7b",
                          host="http://localhost:11434") is False


def test_drift_true_when_raw_results_change():
    state = _make_state()
    new_raw = dict(SAMPLE_RAW)
    new_raw["NewEntry"] = [(99, "100", {})]
    assert rs.has_drifted(state, new_raw, SAMPLE_OPTIONS,
                          "qwen2.5:7b", "http://localhost:11434") is True


def test_drift_true_when_options_change():
    state = _make_state()
    changed = dict(SAMPLE_OPTIONS)
    changed["threshold"] = 4
    assert rs.has_drifted(state, SAMPLE_RAW, changed,
                          "qwen2.5:7b", "http://localhost:11434") is True


def test_drift_true_when_model_changes():
    state = _make_state()
    assert rs.has_drifted(state, SAMPLE_RAW, SAMPLE_OPTIONS,
                          "llama3.1:8b", "http://localhost:11434") is True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def test_log_appends_lines_with_timestamp(tmp_path):
    rs.append_log(str(tmp_path), "First message")
    rs.append_log(str(tmp_path), "Second message")
    log_text = open(rs.log_path(str(tmp_path))).read()
    lines = [l for l in log_text.splitlines() if l.strip()]
    assert len(lines) == 2
    assert "First message" in lines[0]
    assert "Second message" in lines[1]
    # Each line begins with an ISO-ish timestamp
    assert lines[0][:4].isdigit()


def test_clear_does_not_delete_log_file(tmp_path):
    rs.append_log(str(tmp_path), "log line")
    state = _make_state()
    rs.save(state, str(tmp_path))
    rs.clear(str(tmp_path))
    assert os.path.exists(rs.log_path(str(tmp_path)))
