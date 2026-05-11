"""Tests for the optional Ollama client.

These tests never touch a real network. Each scenario monkey-patches the
private ``_http_*`` helpers so we can assert behaviour around caching,
graceful-unavailability, and JSON parsing without depending on the
environment.
"""
import json
import os

import pytest

from model import llm_client


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Redirect the on-disk cache into a tmp dir for each test."""
    fake_dir = tmp_path / "cache"
    fake_dir.mkdir()
    monkeypatch.setattr(llm_client, "_cache_dir", lambda: str(fake_dir))
    yield


def test_is_available_true(monkeypatch):
    monkeypatch.setattr(llm_client, "_http_get_json",
                        lambda host, path, timeout: {"models": []})
    assert llm_client.is_available("http://x") is True


def test_is_available_false_on_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "_http_get_json",
                        lambda host, path, timeout: None)
    assert llm_client.is_available("http://x") is False


def test_model_present_exact_match(monkeypatch):
    monkeypatch.setattr(
        llm_client, "_http_get_json",
        lambda host, path, timeout: {
            "models": [{"name": "qwen2.5:7b"}, {"name": "llama3.1:8b"}],
        },
    )
    assert llm_client.model_present("qwen2.5:7b") is True
    assert llm_client.model_present("does-not-exist") is False


def test_model_present_implicit_latest_suffix(monkeypatch):
    monkeypatch.setattr(
        llm_client, "_http_get_json",
        lambda host, path, timeout: {"models": [{"name": "mistral:latest"}]},
    )
    assert llm_client.model_present("mistral") is True


def test_complete_returns_none_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(llm_client, "_http_post_json",
                        lambda host, path, body, timeout: None)
    assert llm_client.complete("hello", "qwen2.5:7b") is None


def test_complete_parses_json_response(monkeypatch):
    monkeypatch.setattr(
        llm_client, "_http_post_json",
        lambda host, path, body, timeout: {"response": '{"verdict": "ok"}'},
    )
    result = llm_client.complete("hi", "m")
    assert result == {"verdict": "ok"}


def test_complete_returns_none_for_invalid_json(monkeypatch):
    monkeypatch.setattr(
        llm_client, "_http_post_json",
        lambda host, path, body, timeout: {"response": "not json"},
    )
    assert llm_client.complete("hi", "m") is None


def test_complete_caches_response(monkeypatch):
    calls = {"n": 0}

    def fake_post(host, path, body, timeout):
        calls["n"] += 1
        return {"response": '{"x": 1}'}

    monkeypatch.setattr(llm_client, "_http_post_json", fake_post)
    a = llm_client.complete("p", "m")
    b = llm_client.complete("p", "m")
    assert a == b == {"x": 1}
    assert calls["n"] == 1, "second call must be served from cache"


def test_complete_can_disable_cache(monkeypatch):
    calls = {"n": 0}

    def fake_post(host, path, body, timeout):
        calls["n"] += 1
        return {"response": '{"x": 1}'}

    monkeypatch.setattr(llm_client, "_http_post_json", fake_post)
    llm_client.complete("p", "m", use_cache=False)
    llm_client.complete("p", "m", use_cache=False)
    assert calls["n"] == 2


def test_pull_model_streams_progress(monkeypatch):
    events = [
        {"status": "pulling manifest"},
        {"status": "downloading", "completed": 50, "total": 100},
        {"status": "success"},
    ]

    def fake_stream(host, path, body, timeout):
        yield from events

    monkeypatch.setattr(llm_client, "_http_post_stream", fake_stream)

    log = []
    ok = llm_client.pull_model("qwen2.5:7b", progress_cb=log.append)
    assert ok is True
    assert any("pulling manifest" in m for m in log)
    assert any("50%" in m for m in log)


def test_pull_model_returns_false_on_error_event(monkeypatch):
    def fake_stream(host, path, body, timeout):
        yield {"error": "no internet"}

    monkeypatch.setattr(llm_client, "_http_post_stream", fake_stream)
    ok = llm_client.pull_model("qwen2.5:7b")
    assert ok is False
