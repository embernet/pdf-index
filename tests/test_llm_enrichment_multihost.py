"""Multi-host dispatch tests for LLMEnrichmentThread.

These tests exercise the pure helpers (host pre-flight + parallel
dispatch) without spinning up Qt threads. The thread's `run()` orchestrates
them; the helpers are tested in isolation."""

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
