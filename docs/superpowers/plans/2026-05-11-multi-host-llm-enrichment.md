# Multi-host LLM Enrichment + Headless Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user dispatch LLM enrichment in parallel across multiple Ollama hosts, with a launcher script that spawns N Ollama instances on a single GPU machine for higher aggregate throughput. Restructure the sidebar into Settings / AI Enrichment tabs, and add a headless CLI mode.

**Architecture:** `LLMEnrichmentThread` gains a `ThreadPoolExecutor` that fans tasks out to a healthy-host pool with stable hash-based assignment for cache locality; failed hosts drop out for the rest of the run. The sidebar gets a `QTabWidget` with a hosts list of `HostRow` widgets (URL + status dot + remove button). A new `controller/headless_runner.py` drives the same threads under a `QCoreApplication` (no GUI) when `--headless` is passed to `main.py`.

**Tech Stack:** Python 3.10, PyQt6 (Qt threads + QTabWidget), `concurrent.futures.ThreadPoolExecutor`, `argparse`, `subprocess` (launcher), `pytest`.

**Spec:** `docs/superpowers/specs/2026-05-11-multi-host-llm-enrichment-design.md`

---

## Task 1: Config — `llm_hosts` field + migration

**Files:**
- Modify: `model/config.py`
- Test: `tests/test_config_migration.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_migration.py
import json
import os
import tempfile

from model.config import ConfigManager


def test_load_config_migrates_singular_host_to_list():
    """A config saved before multi-host support has 'llm_host' (str) but no
    'llm_hosts'. Loading it must populate 'llm_hosts' with that single value
    so the rest of the code can rely on the list form."""
    with tempfile.TemporaryDirectory() as project_path:
        with open(os.path.join(project_path, "config.json"), "w") as f:
            json.dump({"llm_host": "http://hewie:11434"}, f)
        cfg = ConfigManager.load_config(project_path)
    assert cfg["llm_hosts"] == ["http://hewie:11434"]


def test_load_config_preserves_existing_hosts_list():
    """When 'llm_hosts' is already present it must be returned as-is, even
    if a legacy 'llm_host' string is also present."""
    with tempfile.TemporaryDirectory() as project_path:
        with open(os.path.join(project_path, "config.json"), "w") as f:
            json.dump({
                "llm_host": "http://stale:11434",
                "llm_hosts": ["http://a:11434", "http://b:11434"],
            }, f)
        cfg = ConfigManager.load_config(project_path)
    assert cfg["llm_hosts"] == ["http://a:11434", "http://b:11434"]


def test_load_config_default_when_neither_present():
    """A fresh config (no llm_host, no llm_hosts) gets the default list."""
    with tempfile.TemporaryDirectory() as project_path:
        cfg = ConfigManager.load_config(project_path)
    assert cfg["llm_hosts"] == ["http://localhost:11434"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config_migration.py -v`
Expected: FAIL — `KeyError: 'llm_hosts'` or assertion failures.

- [ ] **Step 3: Add `llm_hosts` default + migration**

Replace the `DEFAULT_CONFIG` dict in `model/config.py`:

```python
DEFAULT_CONFIG = {
    "pdf_filename": None,
    "strategy": "logical",
    "offset": 0,
    "view_mode": "active",
    "capitalize": False,
    "view_source": False,
    "fit_page": True,
    "name_indexing": True,
    "index_capitalised": True,
    "bold_indexing": False,
    "index_single_quotes": True,
    "index_from_offset": True,
    "surname_first": False,
    "index_italic": True,
    "separate_style_files": True,
    "index_front_matter_roman": True,
    "style_view": "aggregate",
    "llm_enrichment_enabled": False,
    "llm_host": "http://localhost:11434",
    "llm_hosts": ["http://localhost:11434"],
    "llm_model": "qwen2.5:7b",
    "llm_subindex_threshold": 8,
    "llm_subindex_enabled": True,
    "llm_alias_enabled": True,
    "llm_category_enabled": True,
    "llm_seealso_enabled": True,
}
```

Replace `ConfigManager.load_config` with:

```python
@staticmethod
def load_config(project_path):
    config_path = os.path.join(project_path, "config.json")
    if not os.path.exists(config_path):
        return ConfigManager.DEFAULT_CONFIG.copy()
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return ConfigManager.DEFAULT_CONFIG.copy()
    config = ConfigManager.DEFAULT_CONFIG.copy()
    config.update(data)
    # Migrate legacy singular llm_host → llm_hosts list when the new
    # key was absent from the on-disk file. Keep llm_host populated
    # too for one-cycle back-compat in case anything still reads it.
    if "llm_hosts" not in data and "llm_host" in data:
        config["llm_hosts"] = [data["llm_host"]]
    return config
```

- [ ] **Step 4: Run all config tests**

Run: `python -m pytest tests/test_config_migration.py tests/ -k config -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add model/config.py tests/test_config_migration.py
git commit -m "feat(config): llm_hosts list + migration from singular llm_host"
```

---

## Task 2: Launcher script — pure helpers and tests

**Files:**
- Create: `scripts/run_ollama_cluster.py`
- Test: `tests/test_ollama_cluster_script.py` (new)

- [ ] **Step 1: Create the skeleton file with the helpers under test**

```python
# scripts/run_ollama_cluster.py
"""Spawn multiple Ollama instances on a single machine for parallel LLM
enrichment. Each instance binds to a different port and shares the same
on-disk models directory.

See docs/superpowers/specs/2026-05-11-multi-host-llm-enrichment-design.md
for the architecture rationale (memory-bandwidth utilisation on
unified-memory GPUs).
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import List, Tuple

DEFAULT_INSTANCES = 5
DEFAULT_START_PORT = 11434
DEFAULT_NUM_PARALLEL = 1
HEALTH_TIMEOUT_S = 15
SHUTDOWN_GRACE_S = 3


def detect_primary_ip() -> str:
    """Return the host's primary non-loopback IPv4 address, or 'localhost'
    if no external address can be resolved. Used so the launcher can print
    URLs the user can paste into the GUI from another machine.
    """
    try:
        hostname = socket.gethostname()
        _, _, addrs = socket.gethostbyname_ex(hostname)
        for addr in addrs:
            if not addr.startswith("127."):
                return addr
    except (socket.gaierror, OSError):
        pass
    return "localhost"


def build_instance_env(port: int, models_dir: str, num_parallel: int) -> dict:
    """Construct the per-instance environment dict for `ollama serve`.

    OLLAMA_KEEP_ALIVE is set to 24h so once a model is loaded it stays
    resident for the duration of the enrichment session. NUM_PARALLEL
    controls intra-instance request batching.
    """
    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"0.0.0.0:{port}"
    env["OLLAMA_MODELS"] = models_dir
    env["OLLAMA_NUM_PARALLEL"] = str(num_parallel)
    env["OLLAMA_KEEP_ALIVE"] = "24h"
    return env


def is_port_ready(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if `GET http://host:port/api/tags` responds with 2xx."""
    url = f"http://{host}:{port}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def format_summary(ip: str, ports: List[int]) -> str:
    """Format the copy-paste-ready summary block printed when the cluster
    is ready. Tested for stability so a UI screenshot in docs doesn't
    drift silently."""
    lines = ["Cluster ready. Add these to LLM Enrichment → Hosts:"]
    for port in ports:
        lines.append(f"  http://{ip}:{port}")
    return "\n".join(lines)
```

- [ ] **Step 2: Write tests for the pure helpers**

```python
# tests/test_ollama_cluster_script.py
import sys
import os
import socket

# Add scripts/ to path so we can import the module under test.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import run_ollama_cluster as cluster


def test_detect_primary_ip_falls_back_to_localhost_on_lookup_failure(monkeypatch):
    def raise_gaierror(name):
        raise socket.gaierror("no DNS")
    monkeypatch.setattr(socket, "gethostbyname_ex", lambda h: (_ for _ in ()).throw(socket.gaierror))
    assert cluster.detect_primary_ip() == "localhost"


def test_detect_primary_ip_skips_loopback_addresses(monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "fakehost")
    monkeypatch.setattr(socket, "gethostbyname_ex",
                        lambda h: ("fakehost", [], ["127.0.0.1", "10.0.0.42"]))
    assert cluster.detect_primary_ip() == "10.0.0.42"


def test_detect_primary_ip_returns_localhost_when_only_loopback(monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "fakehost")
    monkeypatch.setattr(socket, "gethostbyname_ex",
                        lambda h: ("fakehost", [], ["127.0.0.1"]))
    assert cluster.detect_primary_ip() == "localhost"


def test_build_instance_env_sets_required_vars():
    env = cluster.build_instance_env(11436, "/path/to/models", num_parallel=4)
    assert env["OLLAMA_HOST"] == "0.0.0.0:11436"
    assert env["OLLAMA_MODELS"] == "/path/to/models"
    assert env["OLLAMA_NUM_PARALLEL"] == "4"
    assert env["OLLAMA_KEEP_ALIVE"] == "24h"


def test_format_summary_lists_each_port():
    out = cluster.format_summary("10.0.0.42", [11434, 11435, 11436])
    assert "http://10.0.0.42:11434" in out
    assert "http://10.0.0.42:11435" in out
    assert "http://10.0.0.42:11436" in out
    assert out.startswith("Cluster ready.")
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_ollama_cluster_script.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_ollama_cluster.py tests/test_ollama_cluster_script.py
git commit -m "feat(scripts): launcher helpers for Ollama cluster (pure logic + tests)"
```

---

## Task 3: Launcher script — spawning, health checks, main loop

**Files:**
- Modify: `scripts/run_ollama_cluster.py`

- [ ] **Step 1: Append the runtime functions**

Add to the bottom of `scripts/run_ollama_cluster.py`:

```python
def spawn_instance(port: int, models_dir: str, num_parallel: int,
                   log_dir: str) -> subprocess.Popen:
    """Start one `ollama serve` subprocess, redirecting its stdout/stderr
    to a per-port log file. Caller is responsible for terminating the
    returned Popen on shutdown."""
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"instance-{port}.log")
    log_file = open(log_path, "ab", buffering=0)
    return subprocess.Popen(
        ["ollama", "serve"],
        env=build_instance_env(port, models_dir, num_parallel),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def wait_for_ready(ip: str, port: int, timeout_s: float = HEALTH_TIMEOUT_S) -> bool:
    """Poll /api/tags until success or timeout. Returns True on success."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_port_ready(ip, port, timeout=1.0):
            return True
        time.sleep(0.5)
    return False


def preload_model(ip: str, port: int, model: str, timeout_s: float = 600.0) -> bool:
    """Force a model load by sending one trivial /api/generate request.

    Returns True if the request completed successfully (status 200), else
    False. Used to pay the model-load cost during cluster start instead
    of on the user's first real enrichment call.
    """
    import json
    url = f"http://{ip}:{port}/api/generate"
    body = json.dumps({"model": model, "prompt": "hi", "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Spawn multiple Ollama instances on this machine for "
                    "parallel LLM enrichment.",
    )
    p.add_argument("--instances", type=int, default=DEFAULT_INSTANCES,
                   help=f"Number of Ollama instances to start (default {DEFAULT_INSTANCES}).")
    p.add_argument("--start-port", type=int, default=DEFAULT_START_PORT,
                   help=f"Lowest port; consecutive ports are used (default {DEFAULT_START_PORT}).")
    p.add_argument("--models-dir", type=str,
                   default=os.environ.get("OLLAMA_MODELS",
                                          os.path.expanduser("~/.ollama/models")),
                   help="Shared OLLAMA_MODELS directory for all instances.")
    p.add_argument("--num-parallel", type=int, default=DEFAULT_NUM_PARALLEL,
                   help=f"OLLAMA_NUM_PARALLEL per instance (default {DEFAULT_NUM_PARALLEL}).")
    p.add_argument("--preload", type=str, default=None,
                   help="Optional model name; warms each instance with a "
                        "trivial request before reporting ready.")
    p.add_argument("--log-dir", type=str, default="./ollama-cluster-logs",
                   help="Directory for per-instance stdout/stderr logs.")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    ports = [args.start_port + i for i in range(args.instances)]
    ip = detect_primary_ip()
    procs: List[Tuple[int, subprocess.Popen]] = []

    print(f"Starting {args.instances} Ollama instance(s) on ports "
          f"{ports[0]}..{ports[-1]} (NUM_PARALLEL={args.num_parallel})...")

    for port in ports:
        proc = spawn_instance(port, args.models_dir, args.num_parallel, args.log_dir)
        procs.append((port, proc))

    # Install a SIGINT handler so children are killed cleanly on Ctrl+C.
    shutdown_requested = {"value": False}

    def _shutdown(signum, frame):
        shutdown_requested["value"] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    ready_ports: List[int] = []
    failed_ports: List[int] = []
    for port, _ in procs:
        if shutdown_requested["value"]:
            break
        if wait_for_ready(ip, port):
            ready_ports.append(port)
            print(f"  http://{ip}:{port} ready")
        else:
            failed_ports.append(port)
            log_path = os.path.join(args.log_dir, f"instance-{port}.log")
            print(f"  http://{ip}:{port} FAILED to come up — see {log_path}",
                  file=sys.stderr)

    if args.preload and ready_ports and not shutdown_requested["value"]:
        print(f"Preloading model '{args.preload}' on {len(ready_ports)} instances...")
        for port in ready_ports:
            ok = preload_model(ip, port, args.preload)
            status = "OK" if ok else "FAILED"
            print(f"  http://{ip}:{port} preload {status}")

    if ready_ports:
        print()
        print(format_summary(ip, ready_ports))
        print()
        print("Press Ctrl+C to stop the cluster.")

    try:
        while not shutdown_requested["value"]:
            time.sleep(1.0)
            # Detect & report unexpected child deaths without aborting.
            for port, proc in procs:
                if proc.poll() is not None and port not in failed_ports:
                    failed_ports.append(port)
                    log_path = os.path.join(args.log_dir, f"instance-{port}.log")
                    print(f"WARNING: http://{ip}:{port} exited unexpectedly — "
                          f"see {log_path}", file=sys.stderr)
    finally:
        print("Shutting down cluster...")
        for _, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        deadline = time.monotonic() + SHUTDOWN_GRACE_S
        for _, proc in procs:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()

    return 0 if ready_ports else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Verify the script parses help without crashing**

Run: `python scripts/run_ollama_cluster.py --help`
Expected: argparse help text including `--instances`, `--start-port`, `--num-parallel`, `--preload`.

- [ ] **Step 3: Add a smoke test that the script imports cleanly**

Append to `tests/test_ollama_cluster_script.py`:

```python
def test_parse_args_defaults():
    args = cluster.parse_args([])
    assert args.instances == cluster.DEFAULT_INSTANCES
    assert args.start_port == cluster.DEFAULT_START_PORT
    assert args.num_parallel == cluster.DEFAULT_NUM_PARALLEL
    assert args.preload is None


def test_parse_args_overrides():
    args = cluster.parse_args([
        "--instances", "3", "--start-port", "11500",
        "--num-parallel", "2", "--preload", "qwen2.5:7b",
    ])
    assert args.instances == 3
    assert args.start_port == 11500
    assert args.num_parallel == 2
    assert args.preload == "qwen2.5:7b"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ollama_cluster_script.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_ollama_cluster.py tests/test_ollama_cluster_script.py
git commit -m "feat(scripts): full Ollama cluster launcher with health checks and preload"
```

---

## Task 4: LLMEnrichmentThread accepts hosts list (back-compat preserved)

This is a refactor-only step: the thread still runs sequentially against one effective host, but its interface changes from `host: str` to `hosts: list[str]`. Lets us land the API change with all existing tests still green before introducing parallelism.

**Files:**
- Modify: `model/llm_enrichment.py`
- Modify: `controller/main_controller.py:enrich_with_llm`

- [ ] **Step 1: Change `LLMEnrichmentThread.__init__` to take a hosts list**

In `model/llm_enrichment.py` replace the `__init__` signature and body:

```python
    def __init__(
        self,
        raw_results: dict,
        formatted: dict,
        hosts: List[str],
        model: str,
        options: dict,
        project_path: Optional[str] = None,
        resume_state: Optional[llm_run_state.RunState] = None,
    ):
        super().__init__()
        self._raw = raw_results or {}
        self._formatted = formatted or {}
        self._hosts = list(hosts) if hosts else []
        self._model = model
        self._options = options or {}
        self._project_path = project_path
        self._resume_state = resume_state
        self._pause_requested = False
        self._cancel_requested = False
```

Then in `run()`, replace any reference to `self._host` with `self._hosts[0]` for the moment (the existing sequential code keeps using a single host — pre-flight + pool comes in Task 6/7):

```python
        # Temporary single-host execution until parallel dispatch lands.
        # See Task 6 for the ThreadPoolExecutor replacement.
        primary_host = self._hosts[0] if self._hosts else ""
```

…and update the `execute_task(host=…)` call inside the loop to use `primary_host`. Also pass `host=primary_host` to `llm_run_state.make_run_state(...)`.

- [ ] **Step 2: Update the controller call site**

In `controller/main_controller.py`, find `enrich_with_llm`. Replace the `host=...` argument to `LLMEnrichmentThread(...)` with a single-element list derived from the existing sidebar field. (The sidebar still has only `llm_host_edit` at this point — we replace it in Task 10.)

```python
        thread = LLMEnrichmentThread(
            raw_results=self.last_raw_results,
            formatted=self.last_formatted_results or {},
            hosts=[host],
            model=model,
            options=options,
            project_path=self.project_path,
            resume_state=resume_state,
        )
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `python -m pytest tests/ -q`
Expected: all green (existing single-host tests pass against the new signature because we now wrap the host in a one-element list).

- [ ] **Step 4: Commit**

```bash
git add model/llm_enrichment.py controller/main_controller.py
git commit -m "refactor(llm): LLMEnrichmentThread takes hosts list (single-host behaviour unchanged)"
```

---

## Task 5: LLMEnrichmentThread pre-flight host check

Land the helper that pings every host and filters to the healthy ones. Still sequential dispatch; the helper just feeds the existing loop.

**Files:**
- Modify: `model/llm_enrichment.py`
- Test: `tests/test_llm_enrichment_multihost.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_enrichment_multihost.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_enrichment_multihost.py -v`
Expected: FAIL — `AttributeError: module 'model.llm_enrichment' has no attribute 'preflight_hosts'`.

- [ ] **Step 3: Implement the helper**

Add to `model/llm_enrichment.py`, just below the `_format_pages_string` helper near the top:

```python
def preflight_hosts(hosts: List[str], timeout: float = 2.0) -> List[str]:
    """Return the subset of *hosts* that respond to a /api/tags ping.

    Order is preserved so downstream assignment is deterministic. Hosts
    that fail this check are excluded from the parallel pool and shown
    in red in the UI for the duration of the run.
    """
    return [h for h in hosts if llm_client.is_available(h, timeout=timeout)]
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_llm_enrichment_multihost.py tests/ -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add model/llm_enrichment.py tests/test_llm_enrichment_multihost.py
git commit -m "feat(llm): preflight_hosts filters to reachable Ollama endpoints"
```

---

## Task 6: Parallel dispatch extracted as a pure function

Extract the task-execution loop into a testable pure function that takes a healthy-host list and an executor. This is the most code-heavy task; the thread's `run()` orchestrates it in Task 7.

**Files:**
- Modify: `model/llm_enrichment.py`
- Modify: `tests/test_llm_enrichment_multihost.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_enrichment_multihost.py`:

```python
from dataclasses import dataclass


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

    results = llm_enrichment.dispatch_tasks_parallel(
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_enrichment_multihost.py::test_dispatch_round_robins_tasks_across_hosts -v`
Expected: FAIL — `AttributeError: module 'model.llm_enrichment' has no attribute 'dispatch_tasks_parallel'`.

- [ ] **Step 3: Implement `dispatch_tasks_parallel`**

Add to `model/llm_enrichment.py` (just after `preflight_hosts`):

```python
import threading
from concurrent.futures import ThreadPoolExecutor, Future


def _stable_host_index(task_id: str, n_hosts: int) -> int:
    """Map a task to a host slot via a stable hash so resumed runs hit
    the same host (preserving llm_client's on-disk response cache)."""
    if n_hosts <= 0:
        return 0
    # Python's hash() is process-randomised; use a simple stable digest
    # so the same task_id maps to the same slot across runs.
    h = 0
    for ch in task_id:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h % n_hosts


def dispatch_tasks_parallel(
    tasks: List[EnrichmentTask],
    healthy_hosts: List[str],
    raw_results: dict,
    model: str,
    all_entries_set: set,
    on_task_done: Callable[[EnrichmentTask, Optional[dict], str], None],
    on_host_state: Callable[[str, str], None],
    should_stop: Optional[Callable[[], bool]] = None,
) -> None:
    """Run *tasks* across *healthy_hosts* in parallel.

    on_task_done is invoked once per task with (task, fragment_or_None, host).
    on_host_state is invoked when a host's UI state changes:
        'running' before each task on that host
        'available' after a successful task
        'error' when the host returns None

    A host that errors is removed from rotation for the rest of this run.
    Errored tasks are retried on a remaining host; if none remain, the
    remaining tasks are completed with fragment=None so the caller can
    decide how to handle a fully-failed run.

    should_stop, if provided, is polled between submissions to allow
    cooperative pause/cancel. In-flight calls are not interrupted.
    """
    if not healthy_hosts:
        for task in tasks:
            on_task_done(task, None, "")
        return

    healthy = list(healthy_hosts)
    lock = threading.Lock()

    def pick_host(task_id: str, exclude: set) -> Optional[str]:
        """Pick the preferred host for *task_id*, skipping any in *exclude*."""
        with lock:
            pool = [h for h in healthy if h not in exclude]
            if not pool:
                return None
            return pool[_stable_host_index(task_id, len(pool))]

    def drop_host(host: str) -> None:
        with lock:
            if host in healthy:
                healthy.remove(host)

    def run_task(task: EnrichmentTask, host: str) -> Tuple[EnrichmentTask, Optional[dict], str]:
        on_host_state(host, "running")
        try:
            fragment = execute_task(
                task=task, raw_results=raw_results,
                host=host, model=model,
                all_entries_set=all_entries_set,
            )
        except Exception:
            fragment = None
        if fragment is None:
            on_host_state(host, "error")
            drop_host(host)
        else:
            on_host_state(host, "available")
        return task, fragment, host

    with ThreadPoolExecutor(max_workers=len(healthy_hosts)) as ex:
        pending: Dict[Future, EnrichmentTask] = {}

        def submit(task: EnrichmentTask, excluded: set) -> bool:
            host = pick_host(task.id, excluded)
            if host is None:
                return False
            fut = ex.submit(run_task, task, host)
            pending[fut] = task
            return True

        # Initial dispatch
        for task in tasks:
            if should_stop and should_stop():
                break
            ok = submit(task, excluded=set())
            if not ok:
                on_task_done(task, None, "")

        # Drain completions, retrying failed tasks on a different host.
        while pending:
            from concurrent.futures import as_completed
            for fut in as_completed(list(pending.keys())):
                task = pending.pop(fut)
                _, fragment, host = fut.result()
                if fragment is None:
                    # Retry on any other healthy host
                    retried = submit(task, excluded={host})
                    if not retried:
                        on_task_done(task, None, host)
                else:
                    on_task_done(task, fragment, host)
                break  # restart loop so newly-submitted futures join `pending`
```

Note: the `from concurrent.futures import as_completed` is repeated inside the loop to keep the helper self-contained at the call site; move it to the file's import block during cleanup.

- [ ] **Step 4: Hoist the import to the top of the file**

Move the `from concurrent.futures import as_completed` to the file's top imports (next to `ThreadPoolExecutor, Future`).

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_llm_enrichment_multihost.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add model/llm_enrichment.py tests/test_llm_enrichment_multihost.py
git commit -m "feat(llm): dispatch_tasks_parallel with host failover and stable hashing"
```

---

## Task 7: Wire the parallel dispatcher into `LLMEnrichmentThread.run()`

Replace the sequential `for task in tasks:` loop with a call to `dispatch_tasks_parallel`. Add the `host_state_changed` signal so the UI can colour status dots.

**Files:**
- Modify: `model/llm_enrichment.py`

- [ ] **Step 1: Add the new signal**

In `class LLMEnrichmentThread(QThread):` near the existing signals:

```python
    host_state_changed = pyqtSignal(str, str)  # host, state ('running'|'available'|'error')
```

- [ ] **Step 2: Replace the task loop**

In `run()`, replace the block from `for task in tasks:` through to `self.partial_result.emit(dict(suggestions))` (inclusive) with:

```python
        # Pre-flight: filter to reachable hosts.
        healthy = preflight_hosts(self._hosts)
        for h in self._hosts:
            self.host_state_changed.emit(h, "available" if h in healthy else "error")

        if not healthy:
            state.status = "paused"
            state.suggestions = suggestions
            state.completed_ids = sorted(completed_ids)
            llm_run_state.save(state, self._project_path)
            llm_run_state.append_log(
                self._project_path,
                "No hosts reachable; run paused with no progress",
                level="ERR",
            )
            self.finished_with_results.emit(dict(suggestions), "paused")
            return

        # Filter out completed tasks before dispatch.
        pending_tasks = [t for t in tasks if t.id not in completed_ids]

        # Lock so on_task_done's mutation of shared state is safe across
        # the executor's worker threads.
        persist_lock = threading.Lock()
        run_done = {"value": done}

        def on_task_done(task, fragment, host):
            with persist_lock:
                if fragment:
                    merge_fragment(suggestions, fragment)
                completed_ids.add(task.id)
                run_done["value"] += 1
                state.suggestions = suggestions
                state.completed_ids = sorted(completed_ids)
                state.status = "running"
                llm_run_state.save(state, self._project_path)
                llm_run_state.append_log(
                    self._project_path,
                    f"Task {run_done['value']}/{total} OK: {task.id} [{host}]"
                    if fragment else
                    f"Task {run_done['value']}/{total} FAILED: {task.id} [{host}]",
                )
            self.progress.emit(run_done["value"], total, task.label)
            self.partial_result.emit(dict(suggestions))

        def on_host_state(host, st):
            self.host_state_changed.emit(host, st)

        def should_stop():
            return self._pause_requested or self._cancel_requested

        dispatch_tasks_parallel(
            tasks=pending_tasks,
            healthy_hosts=healthy,
            raw_results=self._raw,
            model=self._model,
            all_entries_set=all_entries_set,
            on_task_done=on_task_done,
            on_host_state=on_host_state,
            should_stop=should_stop,
        )

        done = run_done["value"]

        if self._cancel_requested:
            state.status = "cancelled"
            llm_run_state.save(state, self._project_path)
            self.finished_with_results.emit(dict(suggestions), "cancelled")
            return
        if self._pause_requested:
            state.status = "paused"
            llm_run_state.save(state, self._project_path)
            self.finished_with_results.emit(dict(suggestions), "paused")
            return
```

- [ ] **Step 3: Remove the now-unused `primary_host` helper**

Delete the `primary_host = self._hosts[0] if self._hosts else ""` line introduced in Task 4.

- [ ] **Step 4: Verify `threading` is imported at file top**

If not already there, add to imports: `import threading`.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: all green. The pre-existing `test_llm_plan_executor.py` tests should continue to pass because they target the planning + per-task helpers, not the orchestration loop.

- [ ] **Step 6: Commit**

```bash
git add model/llm_enrichment.py
git commit -m "feat(llm): LLMEnrichmentThread runs tasks in parallel across hosts"
```

---

## Task 8: HostRow widget

A small focused widget: status dot + URL line edit + remove button.

**Files:**
- Create: `view/host_row.py`
- Test: `tests/test_settings_sidebar_hosts.py` (new — first test goes here)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings_sidebar_hosts.py
import pytest
from PyQt6.QtWidgets import QApplication

from view.host_row import HostRow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_host_row_reports_trimmed_url(qapp):
    row = HostRow("  http://hewie:11434  ")
    assert row.url() == "http://hewie:11434"


def test_host_row_state_initially_unknown(qapp):
    row = HostRow("http://localhost:11434")
    assert row.state() == "unknown"


def test_host_row_state_changes_propagate_to_dot(qapp):
    row = HostRow("http://localhost:11434")
    row.set_state("available")
    assert row.state() == "available"
    row.set_state("error")
    assert row.state() == "error"


def test_host_row_editing_url_resets_state_to_unknown(qapp):
    row = HostRow("http://a:11434")
    row.set_state("available")
    row.url_edit.setText("http://b:11434")
    # Simulate the editingFinished signal firing
    row.url_edit.editingFinished.emit()
    assert row.state() == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings_sidebar_hosts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'view.host_row'`.

- [ ] **Step 3: Implement HostRow**

```python
# view/host_row.py
"""Single-host row used inside the AI Enrichment tab's hosts list.

Owns a small status dot, a URL line edit, and a remove button. Status
transitions are driven externally (by the controller, in response to
LLMEnrichmentThread.host_state_changed). Editing the URL resets the
state to 'unknown' because the previous reachability check no longer
applies.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget,
)


_STATE_COLOURS = {
    "unknown": "#888",
    "available": "#0a0",
    "running": "#06a",
    "error": "#c00",
}


class HostRow(QWidget):
    remove_requested = pyqtSignal(object)  # emits self for the parent's removal handler
    url_edited = pyqtSignal()              # the user finished editing the URL

    def __init__(self, url: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._state = "unknown"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(14)
        layout.addWidget(self.status_dot)

        self.url_edit = QLineEdit((url or "").strip())
        self.url_edit.setPlaceholderText("http://hostname:11434")
        self.url_edit.editingFinished.connect(self._on_url_edited)
        layout.addWidget(self.url_edit, 1)

        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedWidth(24)
        self.remove_btn.setToolTip("Remove this host")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_btn)

        self._apply_dot_colour()

    def url(self) -> str:
        return self.url_edit.text().strip()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state not in _STATE_COLOURS:
            state = "unknown"
        self._state = state
        self._apply_dot_colour()

    def set_remove_enabled(self, enabled: bool) -> None:
        self.remove_btn.setVisible(enabled)

    def _apply_dot_colour(self) -> None:
        colour = _STATE_COLOURS[self._state]
        self.status_dot.setStyleSheet(f"color: {colour}; font-size: 14px;")

    def _on_url_edited(self) -> None:
        # Any URL change invalidates the previous reachability check.
        self.set_state("unknown")
        self.url_edited.emit()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_settings_sidebar_hosts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add view/host_row.py tests/test_settings_sidebar_hosts.py
git commit -m "feat(view): HostRow widget with status dot and remove button"
```

---

## Task 9: SettingsSidebar — introduce QTabWidget

Pure restructure: wrap the existing scrollable body in a two-tab QTabWidget. **No** functional change — every widget keeps its name and attribute path so the controller's existing wiring continues to work.

**Files:**
- Modify: `view/settings_sidebar.py`

- [ ] **Step 1: Wrap the body in a tab widget**

In `SettingsSidebar.__init__`, replace the block that builds `scroll`, `body`, and the single `layout` with:

```python
        # Two-tab body: Settings / AI Enrichment. Each tab owns its own
        # scroll area so a long tab doesn't push the other tab's first
        # widgets off-screen.
        from PyQt6.QtWidgets import QTabWidget
        self.tabs = QTabWidget()

        # ---- Settings tab ----
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_body = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        settings_body.setLayout(layout)
        settings_scroll.setWidget(settings_body)
        self.tabs.addTab(settings_scroll, "Settings")

        # ---- AI Enrichment tab ----
        enrich_scroll = QScrollArea()
        enrich_scroll.setWidgetResizable(True)
        enrich_scroll.setFrameShape(QFrame.Shape.NoFrame)
        enrich_body = QWidget()
        enrich_layout = QVBoxLayout()
        enrich_layout.setContentsMargins(10, 8, 10, 8)
        enrich_body.setLayout(enrich_layout)
        enrich_scroll.setWidget(enrich_body)
        self.tabs.addTab(enrich_scroll, "AI Enrichment")

        outer.addWidget(self.tabs, 1)
```

- [ ] **Step 2: Move the existing LLM block to the AI Enrichment tab**

Find the `# ---- LLM Enrichment (optional) ----` section in `SettingsSidebar.__init__`. Everywhere it currently calls `layout.addWidget(...)` / `layout.addLayout(...)` / `layout.addSpacing(...)`, change `layout` to `enrich_layout`.

The separator + `_heading` block at the top of that section can be removed (the tab title makes it redundant):

```python
        # Remove these three lines:
        # layout.addSpacing(8)
        # layout.addWidget(self._sep())
        # layout.addSpacing(4)
        # layout.addWidget(self._heading("LLM Enrichment (optional)"))
```

Add a stretch at the very end of the AI tab so its content is top-aligned:

```python
        enrich_layout.addStretch(1)
```

- [ ] **Step 3: Manual smoke test**

Run: `python main.py`
Expected: app starts; right sidebar now shows "Settings" and "AI Enrichment" tabs above the scroll area. Settings tab has all the existing indexing controls; AI Enrichment tab has the LLM controls. Create Index button stays pinned at the very top.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add view/settings_sidebar.py
git commit -m "refactor(view): split SettingsSidebar into Settings / AI Enrichment tabs"
```

---

## Task 10: SettingsSidebar — replace single host edit with hosts list

Swap the single `llm_host_edit` QLineEdit for a vertical list of `HostRow` widgets plus a `+ Add host` button. Expose `get_llm_hosts()` and `set_host_state(url, state)` so the controller can drive it.

**Files:**
- Modify: `view/settings_sidebar.py`
- Test: extend `tests/test_settings_sidebar_hosts.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings_sidebar_hosts.py`:

```python
from view.settings_sidebar import SettingsSidebar


def test_sidebar_returns_single_default_host(qapp):
    sb = SettingsSidebar()
    assert sb.get_llm_hosts() == ["http://localhost:11434"]


def test_sidebar_add_host_appends_row(qapp):
    sb = SettingsSidebar()
    sb.add_host_row("http://hewie:11434")
    sb.add_host_row("http://hewie:11435")
    assert sb.get_llm_hosts() == [
        "http://localhost:11434",
        "http://hewie:11434",
        "http://hewie:11435",
    ]


def test_sidebar_set_host_state_updates_matching_row(qapp):
    sb = SettingsSidebar()
    sb.add_host_row("http://hewie:11434")
    sb.set_host_state("http://hewie:11434", "running")
    rows = sb._host_rows  # internal accessor for the test
    assert rows[1].state() == "running"
    assert rows[0].state() == "unknown"


def test_sidebar_remove_button_hidden_when_only_one_row(qapp):
    sb = SettingsSidebar()
    assert sb._host_rows[0].remove_btn.isVisible() is False
    sb.add_host_row("http://hewie:11434")
    assert sb._host_rows[0].remove_btn.isVisible() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_settings_sidebar_hosts.py -v`
Expected: FAIL — `AttributeError: 'SettingsSidebar' object has no attribute 'get_llm_hosts'`.

- [ ] **Step 3: Add the hosts list to SettingsSidebar**

In `view/settings_sidebar.py`, at the top of the file add:

```python
from view.host_row import HostRow
```

Find the existing `host_row = QHBoxLayout()` block that builds the single `llm_host_edit`. Replace the whole `host_row` + `model_row` (keep `model_row` as-is) section's host part with:

```python
        # Hosts list
        enrich_layout.addWidget(QLabel("Hosts:"))
        self._hosts_container = QWidget()
        self._hosts_layout = QVBoxLayout(self._hosts_container)
        self._hosts_layout.setContentsMargins(0, 0, 0, 0)
        self._hosts_layout.setSpacing(2)
        enrich_layout.addWidget(self._hosts_container)

        self._host_rows: list[HostRow] = []
        self.add_host_row("http://localhost:11434")

        add_host_row = QHBoxLayout()
        self.add_host_btn = QPushButton("+ Add host")
        self.add_host_btn.clicked.connect(lambda: self.add_host_row(""))
        add_host_row.addWidget(self.add_host_btn)
        add_host_row.addStretch()
        enrich_layout.addLayout(add_host_row)
```

Delete the now-orphan `self.llm_host_edit = QLineEdit(...)` block, its tooltip, and the `host_row.addWidget(self.llm_host_edit, 1)` line.

- [ ] **Step 4: Implement the new public API**

Add these methods to `SettingsSidebar`:

```python
    # ---- Hosts list public API ------------------------------------------

    def get_llm_hosts(self) -> list[str]:
        return [r.url() for r in self._host_rows if r.url()]

    def set_llm_hosts(self, hosts: list[str]) -> None:
        # Remove every existing row; add fresh ones for the provided list.
        for r in list(self._host_rows):
            self._remove_host_row(r)
        for h in hosts or ["http://localhost:11434"]:
            self.add_host_row(h)

    def add_host_row(self, url: str) -> HostRow:
        row = HostRow(url)
        row.remove_requested.connect(self._remove_host_row)
        row.url_edited.connect(self._on_any_host_edited)
        self._host_rows.append(row)
        self._hosts_layout.addWidget(row)
        self._update_remove_buttons()
        return row

    def set_host_state(self, url: str, state: str) -> None:
        for row in self._host_rows:
            if row.url() == url:
                row.set_state(state)

    def _remove_host_row(self, row: HostRow) -> None:
        if len(self._host_rows) <= 1:
            return  # never delete the last row — empty pool isn't useful
        self._host_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._update_remove_buttons()
        self._on_any_host_edited()

    def _update_remove_buttons(self) -> None:
        only_one = len(self._host_rows) == 1
        for row in self._host_rows:
            row.set_remove_enabled(not only_one)

    def _on_any_host_edited(self) -> None:
        # Hook for the controller to save_current_config(). Wiring done
        # in main_controller.py.
        if hasattr(self, "_hosts_changed_callback") and self._hosts_changed_callback:
            self._hosts_changed_callback()
```

- [ ] **Step 5: Update `apply_config` to populate the hosts list**

Find the `apply_config` method (it reads from a dict to populate widgets). Replace the line `self.llm_host_edit.setText(config.get("llm_host", "http://localhost:11434"))` with:

```python
        self.set_llm_hosts(config.get("llm_hosts") or [config.get("llm_host", "http://localhost:11434")])
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_settings_sidebar_hosts.py -v`
Expected: PASS.

- [ ] **Step 7: Run full suite**

Run: `python -m pytest tests/ -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add view/settings_sidebar.py tests/test_settings_sidebar_hosts.py
git commit -m "feat(view): hosts list with + add button replaces single host edit"
```

---

## Task 11: LLMSetupDialog — iterate hosts

When the user clicks "Run setup", the dialog now runs the setup flow once per host and prints a section per host in the log view.

**Files:**
- Modify: `view/llm_setup_dialog.py`
- Modify: `controller/main_controller.py:run_llm_setup`

- [ ] **Step 1: Change the dialog to accept a list**

In `view/llm_setup_dialog.py`, change `LLMSetupDialog.__init__` to accept `hosts: list[str]` instead of `host: str`. Update the worker thread to iterate:

```python
class _SetupWorker(QThread):
    event_received = pyqtSignal(object)
    finished_setup = pyqtSignal(bool, str)

    def __init__(self, hosts: list[str], model: str):
        super().__init__()
        self._hosts = list(hosts)
        self._model = model

    def run(self):
        overall_ok = True
        last_hint = ""
        for idx, host in enumerate(self._hosts):
            self.event_received.emit(llm_setup.SetupEvent(
                message=f"\n=== Host {idx + 1}/{len(self._hosts)}: {host} ==="
            ))
            host_ok = False
            host_hint = ""
            try:
                for event in llm_setup.run_setup(host, self._model):
                    self.event_received.emit(event)
                    if event.done:
                        host_ok = event.ok
                        host_hint = event.hint
                        break
            except Exception as exc:
                self.event_received.emit(llm_setup.SetupEvent(
                    message=f"Unexpected error: {exc}", done=True, ok=False, hint="",
                ))
            if not host_ok:
                overall_ok = False
                last_hint = host_hint
        self.finished_setup.emit(overall_ok, last_hint)
```

Update `LLMSetupDialog.__init__` accordingly:

```python
class LLMSetupDialog(QDialog):
    def __init__(self, parent, hosts: list[str], model: str):
        super().__init__(parent)
        self.setWindowTitle("LLM Setup")
        self.setMinimumSize(560, 360)
        self._hosts = list(hosts)
        self._model = model
        ...
        title = QLabel(
            f"Configuring LLM enrichment.\n"
            f"Hosts: {len(self._hosts)} configured\n"
            f"Model: {model}"
        )
```

And `start()`:

```python
    def start(self):
        self._append(f"Starting setup for {len(self._hosts)} host(s)...")
        self._worker = _SetupWorker(self._hosts, self._model)
        ...
```

- [ ] **Step 2: Update the controller call site**

In `controller/main_controller.py`, find `run_llm_setup`. Replace the `host = ...` lookup with:

```python
        hosts = self.view.settings_sidebar.get_llm_hosts()
        if not hosts:
            sidebar.set_llm_status("No hosts configured.", colour="#b00")
            return
        dlg = LLMSetupDialog(self.view, hosts, model)
```

And keep the rest of the method as-is.

- [ ] **Step 3: Manual smoke test**

Run: `python main.py`
Click "Run setup" with 2-3 hosts (one valid, one invalid) and verify each gets a section in the log.

- [ ] **Step 4: Commit**

```bash
git add view/llm_setup_dialog.py controller/main_controller.py
git commit -m "feat(view): LLMSetupDialog iterates over all configured hosts"
```

---

## Task 12: Wire controller for hosts + host-state signals

Connect `get_llm_hosts()` into the enrichment call, save the list to config on edits, and route `host_state_changed` signals from the thread to the sidebar.

**Files:**
- Modify: `controller/main_controller.py`

- [ ] **Step 1: Pass the hosts list to LLMEnrichmentThread**

In `enrich_with_llm`, replace the existing `host = sidebar.llm_host_edit.text().strip()...` block with:

```python
        hosts = self.view.settings_sidebar.get_llm_hosts()
        if not hosts:
            sidebar.set_llm_status("No hosts configured.", colour="#a60")
            return
        host = hosts[0]  # legacy single-host alias for status messages
        model = sidebar.llm_model_edit.text().strip() or "qwen2.5:7b"
        ...
        thread = LLMEnrichmentThread(
            raw_results=self.last_raw_results,
            formatted=self.last_formatted_results or {},
            hosts=hosts,
            model=model,
            options=options,
            project_path=self.project_path,
            resume_state=resume_state,
        )
        thread.host_state_changed.connect(sidebar.set_host_state)
```

- [ ] **Step 2: Save config when hosts change**

In `MainController.__init__`, just after the LLM signal connections, add:

```python
        # Persist hosts list whenever a row is added/removed/edited.
        self.view.settings_sidebar._hosts_changed_callback = self.save_current_config
```

- [ ] **Step 3: Update `save_current_config` to write `llm_hosts`**

In `save_current_config`, find the dict-building section and replace the `"llm_host": ...` line with:

```python
            "llm_hosts": self.view.settings_sidebar.get_llm_hosts(),
```

- [ ] **Step 4: Update `check_llm_status` to use the hosts list**

Find `check_llm_status`. Replace the single-host check with a multi-host aggregate:

```python
    def check_llm_status(self):
        sidebar = self.view.settings_sidebar
        hosts = sidebar.get_llm_hosts()
        model = sidebar.llm_model_edit.text().strip()
        try:
            from model import llm_client
        except Exception as exc:
            sidebar.set_llm_status(f"client unavailable: {exc}", colour="#b00")
            sidebar.set_llm_enrich_enabled(False)
            self._llm_setup_ok = False
            return
        if not hosts:
            sidebar.set_llm_status("No hosts configured.", colour="#a60")
            sidebar.set_llm_enrich_enabled(False)
            self._llm_setup_ok = False
            return
        reachable = []
        for h in hosts:
            ok = llm_client.is_available(h)
            sidebar.set_host_state(h, "available" if ok else "error")
            if ok:
                reachable.append(h)
        if not reachable:
            sidebar.set_llm_status(
                f"None of {len(hosts)} hosts reachable. Click Run setup.",
                colour="#b00",
            )
            sidebar.set_llm_enrich_enabled(False)
            self._llm_setup_ok = False
            return
        # Verify the model is present on at least one reachable host.
        if model and not any(llm_client.model_present(model, h) for h in reachable):
            sidebar.set_llm_status(
                f"{len(reachable)}/{len(hosts)} hosts up, model '{model}' "
                f"missing on all. Click Run setup.",
                colour="#a60",
            )
            sidebar.set_llm_enrich_enabled(False)
            self._llm_setup_ok = False
            return
        sidebar.set_llm_status(
            f"Ready ({len(reachable)}/{len(hosts)} hosts, {model}).",
            colour="#080",
        )
        sidebar.set_llm_enrich_enabled(self.last_raw_results is not None)
        self._llm_setup_ok = True
```

- [ ] **Step 5: Remove obsolete `llm_host_edit.editingFinished` wiring**

In `MainController.__init__`, remove or comment out:

```python
        # self.view.settings_sidebar.llm_host_edit.editingFinished.connect(
        #     self._on_llm_endpoint_changed
        # )
```

This is now handled by the `_hosts_changed_callback` set up in Step 2.

- [ ] **Step 6: Run full suite + manual smoke test**

Run: `python -m pytest tests/ -q` → all green.
Run: `python main.py` → set hosts; the dots should update on Run setup.

- [ ] **Step 7: Commit**

```bash
git add controller/main_controller.py
git commit -m "feat(controller): wire hosts list + host_state signal end-to-end"
```

---

## Task 13: `main.py` — argparse + headless dispatch shim

Add CLI parsing that distinguishes GUI vs headless mode. Headless mode dispatches to a new `controller/headless_runner.py` (created in Task 14).

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace `main()` with argparse-aware version**

```python
# main.py
import argparse
import os
import sys
import traceback


def _excepthook(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="pdf-index",
        description="PDF indexer with optional LLM enrichment.",
    )
    p.add_argument("--headless", action="store_true",
                   help="Run without launching the GUI.")
    p.add_argument("pdf", nargs="?", default=None,
                   help="Path to the PDF (required in --headless mode).")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--index", action="store_true",
                       help="Run indexing with the project's saved config "
                            "(or defaults). Headless mode only.")
    group.add_argument("--indexall", action="store_true",
                       help="Run indexing with all rule toggles ON except "
                            "surname-first. Headless mode only.")
    p.add_argument("--enrich", action="store_true",
                   help="Run LLM enrichment. With --index/--indexall, runs "
                        "after indexing; alone, requires an existing index.json.")
    p.add_argument("--hosts", type=str, default=None,
                   help="Comma-separated Ollama host URLs (overrides config).")
    p.add_argument("--model", type=str, default=None,
                   help="Ollama model name (overrides config).")
    return p.parse_args(argv)


def main():
    args = _parse_args(sys.argv[1:])

    if args.headless:
        if not args.pdf:
            print("error: --headless requires a PDF path", file=sys.stderr)
            sys.exit(1)
        if not (args.index or args.indexall or args.enrich):
            print("error: --headless requires at least one of "
                  "--index, --indexall, --enrich", file=sys.stderr)
            sys.exit(1)
        from controller.headless_runner import run_headless
        sys.exit(run_headless(args))

    # GUI mode
    print(f"Python Executable: {sys.executable}")
    print(f"Current Working Directory: {os.getcwd()}")
    try:
        import numpy
        print(f"Numpy Version: {numpy.__version__}")
    except ImportError as e:
        print("CRITICAL: Numpy not found. Please run 'pip install -r requirements.txt'")
        print(f"Error details: {e}")
        input("Press Enter to exit...")
        return

    try:
        from PyQt6.QtWidgets import QApplication
        from controller.main_controller import MainController
    except ImportError as e:
        print(f"CRITICAL: Failed to import Dependencies: {e}")
        return

    app = QApplication(sys.argv)
    controller = MainController()
    controller.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify GUI mode still works**

Run: `python main.py`
Expected: GUI launches normally.

- [ ] **Step 3: Verify the argparse error paths**

Run: `python main.py --headless`
Expected: stderr `error: --headless requires a PDF path`, exit code 1.

Run: `python main.py --headless book.pdf`
Expected: stderr `error: --headless requires at least one of --index, --indexall, --enrich`, exit code 1.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(main): argparse for headless mode dispatch"
```

---

## Task 14: `controller/headless_runner.py` — indexing path

**Files:**
- Create: `controller/headless_runner.py`
- Test: `tests/test_headless_runner.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_headless_runner.py
"""Tests for the headless CLI runner.

The full thread orchestration isn't exercised here — we test the pure
helpers that compute the effective config and validate the arg set."""

import argparse
import os
import tempfile

from controller import headless_runner


def _args(**kwargs):
    """Build an argparse.Namespace with default values."""
    defaults = dict(
        headless=True, pdf="dummy.pdf", index=False, indexall=False,
        enrich=False, hosts=None, model=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_indexall_forces_all_rules_on_except_surname_first(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"")
    # Pre-existing config with surname_first ON to prove indexall does not toggle it.
    import json
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"surname_first": True, "index_italic": False}, f)

    cfg = headless_runner.build_headless_config(_args(pdf=str(pdf), indexall=True))
    assert cfg["index_capitalised"] is True
    assert cfg["index_italic"] is True
    assert cfg["bold_indexing"] is True
    assert cfg["index_single_quotes"] is True
    assert cfg["surname_first"] is False  # NEVER toggled by indexall


def test_hosts_override_replaces_config_list(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"")
    cfg = headless_runner.build_headless_config(_args(
        pdf=str(pdf), enrich=True,
        hosts="http://hewie:11434,http://hewie:11435",
    ))
    assert cfg["llm_hosts"] == ["http://hewie:11434", "http://hewie:11435"]


def test_index_uses_saved_config(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"")
    import json
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"index_italic": False}, f)

    cfg = headless_runner.build_headless_config(_args(pdf=str(pdf), index=True))
    assert cfg["index_italic"] is False  # respects saved config


def test_enrich_without_index_returns_error_when_no_index_json(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"")
    exit_code = headless_runner.run_headless(_args(
        pdf=str(pdf), enrich=True,
    ))
    assert exit_code == 3
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m pytest tests/test_headless_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'controller.headless_runner'`.

- [ ] **Step 3: Implement build_headless_config + indexing path**

The GUI's indexing flow uses `NameIndexingThread` (automatic name
discovery) when name-indexing is enabled — which is the default and the
mode most headless users will want. The thread emits
`indexing_finished(formatted_results, raw_results)`; the controller then
writes `index.{md,txt,html,json}` to the project directory. We replicate
the relevant parts of that flow here.

```python
# controller/headless_runner.py
"""Run indexing and/or LLM enrichment from the command line, without a GUI.

Driven by `main.py` when `--headless` is passed. Uses a plain
`QCoreApplication` so QThread signal/slot plumbing still works, but no
widgets are created.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from model.config import ConfigManager


_INDEXALL_FORCED_ON = (
    "index_capitalised",
    "index_italic",
    "bold_indexing",
    "index_single_quotes",
    "index_from_offset",
    "index_front_matter_roman",
)


def build_headless_config(args: argparse.Namespace) -> dict:
    """Build the effective config for this headless run.

    Starts from the project's saved config.json (or DEFAULT_CONFIG if
    none), then applies --indexall (force all rules ON except
    surname_first) and CLI overrides for hosts / model.
    """
    project_path = os.path.dirname(os.path.abspath(args.pdf))
    cfg = ConfigManager.load_config(project_path)

    if args.indexall:
        for key in _INDEXALL_FORCED_ON:
            cfg[key] = True
        cfg["surname_first"] = False  # ALWAYS off, regardless of saved config

    if args.hosts:
        cfg["llm_hosts"] = [h.strip() for h in args.hosts.split(",") if h.strip()]
    if args.model:
        cfg["llm_model"] = args.model

    return cfg


def run_headless(args: argparse.Namespace) -> int:
    if not os.path.exists(args.pdf):
        print(f"error: PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    project_path = os.path.dirname(os.path.abspath(args.pdf))
    cfg = build_headless_config(args)

    # --enrich alone requires an existing index.
    if args.enrich and not (args.index or args.indexall):
        if not os.path.exists(os.path.join(project_path, "index.json")):
            print("error: --enrich without --index/--indexall requires an "
                  "existing index.json in the project directory",
                  file=sys.stderr)
            return 3

    # PyQt is needed even in headless mode for QThread signal delivery.
    from PyQt6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    if args.index or args.indexall:
        if not _run_indexing(app, args.pdf, project_path, cfg):
            return 2

    if args.enrich:
        if not _run_enrichment(app, project_path, cfg):
            return 4

    return 0


def _format_results(raw_results: dict, capitalize: bool) -> dict:
    """Turn the per-page raw_results into the pages-string form using the
    same range-compression that the GUI uses."""
    from model.indexer import IndexingThread
    return IndexingThread.process_results(None, raw_results,
                                          capitalize_keys=capitalize)


def _write_index_files(project_path: str, raw_results: dict,
                       formatted_results: dict) -> None:
    """Write index.{md,txt,html,json} to *project_path*.

    Mirrors MainController.generate_markdown / generate_text /
    generate_html — those methods don't depend on Qt state, so we inline
    the same shape here to avoid pulling MainController in headless.
    """
    count = len(formatted_results)
    md_lines = [f"# Index ({count} entries)\n"]
    txt_lines = [f"Index ({count} entries)\n"]
    html_lines = [f"<html><body><h1>Index ({count} entries)</h1>"]
    for kw, pages in formatted_results.items():
        md_lines.append(f"**{kw}** {pages}  ")
        txt_lines.append(f"{kw} {pages}")
        html_lines.append(f"<div><b>{kw}</b> {pages}</div>")
    html_lines.append("</body></html>")

    path_base = os.path.join(project_path, "index")
    with open(path_base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    with open(path_base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines))
    with open(path_base + ".html", "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))
    with open(path_base + ".json", "w", encoding="utf-8") as f:
        json.dump(raw_results, f, ensure_ascii=False, indent=2)


def _run_indexing(app, pdf_path: str, project_path: str, cfg: dict) -> bool:
    """Drive NameIndexingThread under a QCoreApplication and write outputs.

    Mirrors the GUI's automatic-name-discovery path (the default mode).
    Keyword-based indexing is intentionally out of scope for headless —
    use the GUI when you need it.
    """
    from model.name_indexer import NameIndexingThread, DEFAULT_STOPWORDS

    print(f"[indexing] starting: {pdf_path}")

    offset = cfg.get("offset", 0)
    index_from_offset = cfg.get("index_from_offset", True)
    start_page = abs(offset) if (index_from_offset and offset < 0) else 0

    thread = NameIndexingThread(
        pdf_path=pdf_path,
        page_numbering_strategy=cfg.get("strategy", "logical"),
        offset=offset,
        include_bold=cfg.get("bold_indexing", False),
        exclude_words=set(),
        stopwords=DEFAULT_STOPWORDS,
        name_type_overrides={},
        start_page=start_page,
        surname_first=cfg.get("surname_first", False),  # locked OFF by indexall
        index_italic=cfg.get("index_italic", True),
        index_capitalised=cfg.get("index_capitalised", True),
        index_single_quotes=cfg.get("index_single_quotes", True),
        index_front_matter=cfg.get("index_front_matter_roman", True),
    )

    result = {"ok": False, "raw": None, "formatted": None}

    def on_progress(p):
        print(f"[indexing] {p}%")

    def on_finished(formatted_results, raw_results):
        result["ok"] = True
        result["raw"] = raw_results
        result["formatted"] = formatted_results
        app.quit()

    def on_error(msg):
        print(f"[indexing] error: {msg}", file=sys.stderr)
        result["ok"] = False
        app.quit()

    thread.progress_updated.connect(on_progress)
    thread.indexing_finished.connect(on_finished)
    thread.error_occurred.connect(on_error)
    thread.start()
    app.exec()

    if result["ok"] and result["raw"] is not None:
        _write_index_files(project_path, result["raw"], result["formatted"])
        print(f"[indexing] done — index.{{md,txt,html,json}} written "
              f"({len(result['formatted'])} entries)")

    return result["ok"]
```

- [ ] **Step 4: Run the targeted unit tests**

Run: `python -m pytest tests/test_headless_runner.py::test_indexall_forces_all_rules_on_except_surname_first tests/test_headless_runner.py::test_hosts_override_replaces_config_list tests/test_headless_runner.py::test_index_uses_saved_config -v`
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

If you have a small test PDF, run:
```bash
python main.py --headless path/to/small.pdf --indexall
```
Expected: progress prints, `index.{md,txt,html,json}` written next to the PDF, exit code 0.

- [ ] **Step 6: Commit**

```bash
git add controller/headless_runner.py tests/test_headless_runner.py
git commit -m "feat(controller): headless indexing runner"
```

---

## Task 15: `controller/headless_runner.py` — enrichment path

**Files:**
- Modify: `controller/headless_runner.py`

- [ ] **Step 1: Implement `_run_enrichment`**

Append to `controller/headless_runner.py`:

```python
def _run_enrichment(app, project_path: str, cfg: dict) -> bool:
    """Drive LLMEnrichmentThread headlessly.

    Loads raw_results from index.json (since we may be running enrich-only
    without having just produced them in-memory).
    """
    import json
    from model.llm_enrichment import LLMEnrichmentThread

    index_path = os.path.join(project_path, "index.json")
    if not os.path.exists(index_path):
        print(f"error: {index_path} missing — run indexing first",
              file=sys.stderr)
        return False
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            raw_results = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {index_path}: {exc}", file=sys.stderr)
        return False

    hosts = cfg.get("llm_hosts") or ["http://localhost:11434"]
    model = cfg.get("llm_model", "qwen2.5:7b")
    options = {
        "subindex": cfg.get("llm_subindex_enabled", True),
        "alias":    cfg.get("llm_alias_enabled", True),
        "category": cfg.get("llm_category_enabled", True),
        "seealso":  cfg.get("llm_seealso_enabled", True),
        "threshold": cfg.get("llm_subindex_threshold", 8),
    }

    print(f"[enrich] planning tasks across {len(hosts)} host(s) ({model})")
    thread = LLMEnrichmentThread(
        raw_results=raw_results,
        formatted={},  # not needed for headless run
        hosts=hosts,
        model=model,
        options=options,
        project_path=project_path,
        resume_state=None,
    )

    state = {"ok": False, "status": ""}

    def on_planned(total):
        print(f"[enrich] {total} tasks planned")

    def on_progress(done, total, label):
        print(f"[enrich] {done}/{total} {label}")

    def on_host_state(host, st):
        print(f"[enrich] host {host} → {st}")

    def on_finished(suggestions, status):
        state["ok"] = (status == "completed")
        state["status"] = status
        state["suggestions"] = suggestions
        app.quit()

    thread.planned.connect(on_planned)
    thread.progress.connect(on_progress)
    thread.host_state_changed.connect(on_host_state)
    thread.finished_with_results.connect(on_finished)
    thread.start()
    app.exec()

    if state["ok"]:
        # Write the enhanced files to the project directory.
        from model import enhanced_reports
        path_base = os.path.join(project_path, "index")
        enhanced_reports.write_enhanced_files(
            path_base=path_base,
            formatted={},
            raw_results=raw_results,
            suggestions=state.get("suggestions") or {},
        )
        print(f"[enrich] complete — index.enhanced.* written")
    else:
        print(f"[enrich] {state['status']}", file=sys.stderr)

    return state["ok"]
```

- [ ] **Step 2: Run the headless-runner test that exercises the no-index-json path**

Run: `python -m pytest tests/test_headless_runner.py::test_enrich_without_index_returns_error_when_no_index_json -v`
Expected: PASS.

- [ ] **Step 3: Manual smoke test with a real cluster**

```bash
# Terminal 1
python scripts/run_ollama_cluster.py --instances 2 --preload qwen2.5:7b

# Terminal 2
python main.py --headless path/to/small.pdf --enrich \
    --hosts http://localhost:11434,http://localhost:11435
```
Expected: `[enrich] host ... → running` / `available` lines stream by; `index.enhanced.*` written; exit code 0.

- [ ] **Step 4: Commit**

```bash
git add controller/headless_runner.py
git commit -m "feat(controller): headless enrichment runner with multi-host dispatch"
```

---

## Task 16: README + HELP updates

**Files:**
- Modify: `README.md`
- Modify: `HELP.md` (if present)

- [ ] **Step 1: Add a "Headless mode" section near the top**

Append to `README.md`:

```markdown
## Headless mode

Run indexing and/or LLM enrichment from the command line without
launching the GUI:

```bash
# Index a book with all rules enabled (except Surname First)
python main.py --headless path/to/book.pdf --indexall

# Index + run LLM enrichment afterwards
python main.py --headless path/to/book.pdf --indexall --enrich

# Re-run enrichment on an already-indexed project against an explicit
# cluster of Ollama hosts
python main.py --headless path/to/book.pdf --enrich \
    --hosts http://hewie:11434,http://hewie:11435,http://hewie:11436
```

Exit codes:

| Code | Meaning                                |
| ---- | -------------------------------------- |
| 0    | All requested operations completed     |
| 1    | Argument validation error              |
| 2    | Indexing failed                        |
| 3    | --enrich requires an existing index.json |
| 4    | Enrichment failed (no hosts reachable) |

## Multi-host LLM enrichment

The "AI Enrichment" tab in the sidebar accepts multiple Ollama hosts.
Click "+ Add host" for each endpoint. Status dots show per-host state
during a run: gray (unchecked), green (available), blue (running a
request), red (failed pre-flight or errored mid-run). A host that goes
red stays red for the rest of the current run.

### Running a multi-instance Ollama cluster on one machine

For machines with sufficient GPU memory (e.g. DGX Spark with 128GB
unified memory), running multiple Ollama instances on the same GPU
extracts more aggregate throughput than a single instance handling the
same requests sequentially — each instance has its own KV cache and
prefill pipeline, and the CUDA scheduler interleaves them to keep
memory bandwidth utilised.

```bash
python scripts/run_ollama_cluster.py --instances 5 --preload qwen2.5:7b
```

The script prints the host URLs to paste into the sidebar:

```
Cluster ready. Add these to LLM Enrichment → Hosts:
  http://10.0.0.42:11434
  http://10.0.0.42:11435
  http://10.0.0.42:11436
  http://10.0.0.42:11437
  http://10.0.0.42:11438
```

Per-instance logs go to `./ollama-cluster-logs/`. Press Ctrl+C to stop
the cluster cleanly.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: headless mode + multi-host Ollama cluster usage"
```

---

## Self-review

After completing all tasks:

1. **Spec coverage**: every section of `docs/superpowers/specs/2026-05-11-multi-host-llm-enrichment-design.md` is covered by at least one task above. The launcher script → Tasks 2-3. Config schema → Task 1. Sidebar restructure → Tasks 8-10. Parallel dispatch → Tasks 4-7. LLMSetupDialog multi-host → Task 11. Headless mode → Tasks 13-15. Docs → Task 16.

2. **No placeholders**: no TBDs; every code block is concrete; every test is runnable.

3. **Type consistency**: `LLMEnrichmentThread.__init__` takes `hosts: List[str]` throughout (Tasks 4 onward); `HostRow.set_state` accepts strings matching `_STATE_COLOURS` keys; `get_llm_hosts()` returns `list[str]` in both the sidebar and the controller.
