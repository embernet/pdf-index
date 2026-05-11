"""Multi-host dispatch tests for LLMEnrichmentThread.

These tests exercise the pure helpers (host pre-flight + parallel
dispatch) without spinning up Qt threads. The thread's `run()` orchestrates
them; the helpers are tested in isolation."""

from dataclasses import dataclass

from model import llm_enrichment


def test_preflight_keeps_only_reachable_hosts(monkeypatch):
    reachable = {"http://a:11434", "http://c:11434"}
    monkeypatch.setattr(
        llm_enrichment.llm_client, "is_available",
        lambda host, timeout=2.0: host in reachable,
    )
    healthy = llm_enrichment.preflight_hosts(
        ["http://a:11434", "http://b:11434", "http://c:11434"]
    )
    assert healthy == ["http://a:11434", "http://c:11434"]


def test_preflight_returns_empty_when_no_hosts_reachable(monkeypatch):
    monkeypatch.setattr(
        llm_enrichment.llm_client, "is_available",
        lambda host, timeout=2.0: False,
    )
    assert llm_enrichment.preflight_hosts(["http://a", "http://b"]) == []


@dataclass
class _RecordingExecution:
    """Stand-in for execute_task that records which host got which task."""
    calls: list

    def __call__(self, *, task, raw_results, host, model, all_entries_set):
        self.calls.append((task.id, host))
        # Return an empty fragment so merge_fragment is a no-op.
        return {}


def _mk_task(idx):
    return llm_enrichment.EnrichmentTask(
        id=f"t{idx}", kind="category", label=f"t{idx}", payload={},
    )


def test_dispatch_round_robins_tasks_across_hosts(monkeypatch):
    """With 6 tasks and 3 healthy hosts, each host gets exactly 2 tasks."""
    rec = _RecordingExecution(calls=[])
    monkeypatch.setattr(llm_enrichment, "execute_task", rec)

    tasks = [_mk_task(i) for i in range(6)]
    hosts = ["http://a", "http://b", "http://c"]

    llm_enrichment.dispatch_tasks_parallel(
        tasks=tasks,
        healthy_hosts=hosts,
        raw_results={},
        model="m",
        all_entries_set=set(),
        on_task_done=lambda task, fragment, host: None,
        on_host_state=lambda host, state: None,
    )
    by_host = {}
    for tid, h in rec.calls:
        by_host.setdefault(h, []).append(tid)
    assert sorted(by_host.keys()) == sorted(hosts)
    for h in hosts:
        assert len(by_host[h]) == 2


def test_dispatch_reassigns_when_host_fails(monkeypatch):
    """If a host returns None (failure) the task is retried on a remaining
    healthy host and the failed host is dropped."""
    state_events = []

    def fake_execute(*, task, raw_results, host, model, all_entries_set):
        # Host 'b' always fails.
        if host == "http://b":
            return None
        return {}

    monkeypatch.setattr(llm_enrichment, "execute_task", fake_execute)

    tasks = [_mk_task(i) for i in range(4)]
    hosts = ["http://a", "http://b"]

    completed = []
    llm_enrichment.dispatch_tasks_parallel(
        tasks=tasks,
        healthy_hosts=hosts,
        raw_results={},
        model="m",
        all_entries_set=set(),
        on_task_done=lambda task, fragment, host: completed.append(task.id),
        on_host_state=lambda host, state: state_events.append((host, state)),
    )
    # All four tasks should complete via host 'a' after 'b' is dropped.
    assert sorted(completed) == ["t0", "t1", "t2", "t3"]
    # Host b should have transitioned through error.
    assert any(e == ("http://b", "error") for e in state_events)
