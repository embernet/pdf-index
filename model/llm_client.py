"""Thin Ollama HTTP client used by the optional LLM enrichment layer.

This module is intentionally dependency-free (stdlib only) so the app keeps
running unchanged when no LLM is installed. Every public function tolerates
an unreachable server and returns a sentinel rather than raising into
caller code — the single rule is that importing or calling this module
must never destabilise the rest of the app.

Public surface:

* :func:`is_available`  - cheap GET /api/tags ping
* :func:`model_present` - returns True iff *model* is in the local /api/tags list
* :func:`pull_model`    - streams POST /api/pull, calling *progress_cb* with status text
* :func:`complete`      - JSON-mode POST /api/generate with on-disk caching

The cache lives under ``Data/.llm_cache/`` next to the project files. It is
keyed by sha256 of (host, model, prompt, format) so re-runs over the same
book are free.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable, Optional

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120  # seconds; pulls can stream much longer (handled separately)
PULL_TIMEOUT = 60 * 30  # 30 minutes for model pulls

# Sentinel returned by complete() when the server is unreachable, the call
# times out, or the response can't be parsed. Callers check `is None`.
UNAVAILABLE: None = None


# ---------------------------------------------------------------------------
# Low-level HTTP
# ---------------------------------------------------------------------------

def _normalise_host(host: str) -> str:
    h = (host or DEFAULT_HOST).strip().rstrip("/")
    if not h.startswith(("http://", "https://")):
        h = "http://" + h
    return h


def _http_get_json(host: str, path: str, timeout: float) -> Optional[dict]:
    url = _normalise_host(host) + path
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError):
        return None


def _http_post_json(host: str, path: str, body: dict, timeout: float) -> Optional[dict]:
    url = _normalise_host(host) + path
    try:
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, json.JSONDecodeError):
        return None


def _http_post_stream(host: str, path: str, body: dict, timeout: float) -> Iterable[dict]:
    """Yield JSON objects from an Ollama streaming endpoint.

    Ollama streaming endpoints emit one JSON object per line. If the request
    fails we yield nothing — callers must tolerate an empty stream.
    """
    url = _normalise_host(host) + path
    try:
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError):
        return
    try:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
    finally:
        try:
            resp.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available(host: str = DEFAULT_HOST, timeout: float = 2.0) -> bool:
    """True if the Ollama server at *host* responds to GET /api/tags."""
    return _http_get_json(host, "/api/tags", timeout) is not None


def list_models(host: str = DEFAULT_HOST, timeout: float = 5.0) -> list[str]:
    """Return list of model names present on the server, or [] on failure."""
    data = _http_get_json(host, "/api/tags", timeout)
    if not data:
        return []
    models = data.get("models") or []
    out = []
    for m in models:
        name = m.get("name") if isinstance(m, dict) else None
        if name:
            out.append(name)
    return out


def model_present(model: str, host: str = DEFAULT_HOST, timeout: float = 5.0) -> bool:
    """True if *model* (exact name match) is present on the server."""
    if not model:
        return False
    names = list_models(host, timeout)
    if model in names:
        return True
    # Be lenient about the implicit ":latest" suffix
    if ":" not in model and any(n.split(":", 1)[0] == model for n in names):
        return True
    return False


def pull_model(
    model: str,
    host: str = DEFAULT_HOST,
    progress_cb: Optional[Callable[[str], None]] = None,
    timeout: float = PULL_TIMEOUT,
) -> bool:
    """Pull *model* via POST /api/pull, streaming status to *progress_cb*.

    Returns True on success, False on any failure. Safe to call repeatedly —
    Ollama will short-circuit if the model is already present.
    """
    saw_success = False
    saw_any_event = False
    for event in _http_post_stream(host, "/api/pull", {"name": model, "stream": True}, timeout):
        saw_any_event = True
        if not isinstance(event, dict):
            continue
        if "error" in event:
            if progress_cb:
                progress_cb(f"error: {event['error']}")
            return False
        status = event.get("status") or ""
        total = event.get("total")
        completed = event.get("completed")
        msg = status
        if isinstance(total, int) and isinstance(completed, int) and total > 0:
            pct = int(100 * completed / total)
            msg = f"{status} ({pct}%)"
        if progress_cb and msg:
            progress_cb(msg)
        if status == "success":
            saw_success = True
    return saw_success or (saw_any_event and model_present(model, host))


def _cache_dir() -> str:
    base = os.path.join(os.getcwd(), "Data", ".llm_cache")
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        pass
    return base


def _cache_key(host: str, model: str, prompt: str, fmt: str) -> str:
    h = hashlib.sha256()
    h.update(_normalise_host(host).encode("utf-8"))
    h.update(b"\x1f")
    h.update((model or "").encode("utf-8"))
    h.update(b"\x1f")
    h.update((fmt or "").encode("utf-8"))
    h.update(b"\x1f")
    h.update((prompt or "").encode("utf-8"))
    return h.hexdigest()


def _cache_load(key: str) -> Optional[Any]:
    path = os.path.join(_cache_dir(), key + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _cache_store(key: str, value: Any) -> None:
    path = os.path.join(_cache_dir(), key + ".json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
    except OSError:
        pass


def complete(
    prompt: str,
    model: str,
    host: str = DEFAULT_HOST,
    fmt: str = "json",
    timeout: float = DEFAULT_TIMEOUT,
    use_cache: bool = True,
    options: Optional[dict] = None,
) -> Optional[Any]:
    """Send *prompt* to Ollama /api/generate and return the parsed response.

    When *fmt* is "json", returns the parsed JSON object (or None on failure).
    When *fmt* is empty/None, returns the raw response string (or None).

    Failures are returned as None — never raised. Callers must check.
    """
    if not prompt or not model:
        return UNAVAILABLE

    key = _cache_key(host, model, prompt, fmt or "")
    if use_cache:
        cached = _cache_load(key)
        if cached is not None:
            return cached

    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if fmt == "json":
        body["format"] = "json"
    if options:
        body["options"] = options

    resp = _http_post_json(host, "/api/generate", body, timeout)
    if resp is None:
        return UNAVAILABLE

    raw_text = resp.get("response") if isinstance(resp, dict) else None
    if raw_text is None:
        return UNAVAILABLE

    if fmt == "json":
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return UNAVAILABLE
        if use_cache:
            _cache_store(key, parsed)
        return parsed

    if use_cache:
        _cache_store(key, raw_text)
    return raw_text
