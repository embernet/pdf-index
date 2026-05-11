# Multi-host LLM enrichment + sidebar tab restructure

**Date:** 2026-05-11
**Status:** Draft for review

## Goal

Let the user point LLM enrichment at one or more Ollama servers and dispatch
enrichment tasks across them in parallel. Provide a launcher script that runs
multiple Ollama instances on a single machine (useful when the GPU has spare
memory and the user wants independent request queues, or when standing up a
DGX Spark). Restructure the right-hand settings sidebar so indexing settings
and LLM enrichment settings live in separate tabs.

## Out of scope

- Distributing the same prompt across hosts for ensemble responses.
- Routing different feature categories (subindex / alias / category / see-also)
  to different hosts. All hosts are interchangeable workers running the same
  model.
- Per-host model selection. One model, one threshold, applied across the pool.
- Live host health monitoring during idle time. Status updates only on
  explicit setup checks or while a run is in flight.
- Automatic retry of a host that errored during a run. Once red, stays red
  for the rest of that run.

## Why multi-instance helps throughput

Single-model batch-1 inference of a 7B model on a modern unified-memory GPU
(DGX Spark class) is typically memory-bandwidth-bound during decode rather
than compute-bound. A single Ollama instance serialises its KV-cache reads,
prefill, and decode steps against one request stream, leaving the GPU's
bandwidth under-utilised. Running multiple Ollama instances on the same
GPU is therefore the cheap path to higher *aggregate* throughput:

- Each instance has its own KV cache, prefill pipeline, and decode loop.
- The CUDA scheduler interleaves their compute kernels.
- Memory-bandwidth utilisation goes up because independent streams keep
  the bus busier between any single instance's idle gaps.
- Per-request latency may slightly increase under load (compute contention),
  but the enrichment workload cares about completing N tasks, not single-task
  speed.

The same approach scales horizontally: a second DGX Spark with the same
launcher script doubles the instance count and the aggregate throughput.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│ SettingsSidebar                                             │
│   header                                                    │
│   [Create Index]   ← pinned, unchanged                      │
│   ┌─ QTabWidget ────────────────────────────────────────┐   │
│   │ [Settings] [AI Enrichment]                          │   │
│   │ ┌─ scroll area per tab ──────────────────────────┐  │   │
│   │ │ (existing controls, regrouped)                 │  │   │
│   │ └────────────────────────────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

LLMEnrichmentThread.run()
  ├── plan tasks (existing)
  ├── pre-flight: ping every host once, build healthy_hosts set
  ├── ThreadPoolExecutor(max_workers=len(healthy_hosts))
  │     ├── worker(host_A) ──┐
  │     ├── worker(host_B) ──┼── shared task queue (FIFO)
  │     └── worker(host_C) ──┘
  └── on each task completion: persist run state, emit signals

scripts/run_ollama_cluster.py
  spawns N `ollama serve` subprocesses on consecutive ports,
  prints the host URLs the user should paste into the sidebar.
```

## Config schema changes

`model/config.py` adds `llm_hosts: list[str]`, default `["http://localhost:11434"]`.

Migration on load:
- If `llm_hosts` is present, use it as-is.
- Else if legacy `llm_host` (singular) is present, populate
  `llm_hosts = [llm_host]` and write back on next save.
- Else default.

`llm_host` stays in the schema as a deprecated alias for one save cycle, then
is dropped from new writes. Reads of either key produce a one-element list if
that's all there is.

`llm_model` remains a single string — all hosts run the same model.

## Launcher script: `scripts/run_ollama_cluster.py`

CLI:
```
python scripts/run_ollama_cluster.py
    [--instances N]
    [--start-port P]
    [--models-dir PATH]
    [--num-parallel K]
    [--preload MODEL]
```

Defaults: `N=5`, `P=11434`, `PATH=$OLLAMA_MODELS or ~/.ollama/models`,
`K=1`, no preload.

Behaviour:
- For i in 0..N-1, spawn `ollama serve` with env:
  - `OLLAMA_HOST=0.0.0.0:<P+i>`
  - `OLLAMA_MODELS=<PATH>` (shared so all instances see the same model files)
  - `OLLAMA_NUM_PARALLEL=<K>` (intra-instance request batching; default 1
    keeps the simple one-request-per-instance model, raise to stack
    intra-instance batching on top of inter-instance parallelism)
  - `OLLAMA_KEEP_ALIVE=24h` so loaded models stay resident across requests
- Stdout/stderr of each instance redirected to
  `./ollama-cluster-logs/instance-<port>.log`.
- After spawning, the script polls each instance's `/api/tags` with a
  short timeout. Hosts that come up within ~15s are reported as ready;
  the rest are reported as failed-to-start with a pointer to their log.
- When `--preload MODEL` is given, the script sends one trivial
  `/api/generate` (prompt `"hi"`, stream off) to each ready instance to
  force the model into memory before reporting "cluster ready". Without
  preload the first real enrichment request to each instance pays the
  load cost.
- Resolves the machine's primary IP via `socket.gethostname()` then
  `socket.gethostbyname_ex()` (falls back to "localhost" if no
  non-loopback address is found) and prints:
  ```
  Cluster ready. Add these to LLM Enrichment → Hosts:
    http://10.0.0.42:11434
    http://10.0.0.42:11435
    http://10.0.0.42:11436
    http://10.0.0.42:11437
    http://10.0.0.42:11438
  ```
- SIGINT (Ctrl+C) terminates all children cleanly via `terminate()` then
  `kill()` after a 3s grace period.
- If a child dies unexpectedly mid-session, the script logs which one
  and keeps the rest running.

The script is pure stdlib + subprocess — no dependencies beyond Python 3.10.

## Sidebar restructure

`view/settings_sidebar.py` is split visually using a `QTabWidget` placed
between the pinned Create Index button and the bottom edge.

**Settings tab** (existing controls, no logic change):
- Page numbering section
- Indexing strategy & related toggles
- Capitalised / italic / bold / single-quotes
- Separate-style-files, front-matter roman

**AI Enrichment tab**:
- Status label (aggregate, e.g. `Ready (3/3 hosts, qwen2.5:7b)`)
- Master enable checkbox
- **Hosts list** (see below)
- Model field
- Sub-index threshold
- Per-feature toggles (subindex / alias / category / seealso)
- Action buttons: Run setup, Enrich with LLM
- Progress strip
- Resume banner

Tab switching is purely visual. All widgets remain attributes of
`SettingsSidebar` with their current names, so controller wiring is
unaffected. The tab widget holds two `QWidget` containers, and each
existing layout block is moved into the appropriate one.

## Hosts list widget

Replaces the current single `llm_host_edit` `QLineEdit`.

A `QVBoxLayout` named `hosts_layout` containing N `HostRow` widgets and
trailing `[+ Add host]` button. Each `HostRow`:

```
┌────────────────────────────────────────────────────┐
│ ● [http://localhost:11434                  ] [✕]   │
└────────────────────────────────────────────────────┘
```

- Status dot: a fixed-size `QLabel` showing a Unicode `●` with stylesheet
  colour. Width fixed so rows align.
- URL line edit: same validation as the old `llm_host_edit` (auto-prepends
  `http://` if missing scheme).
- Remove button: hidden when there's only one row (prevent empty pool).
- The trailing `+ Add host` button appends a new row with empty URL.

`HostRow.set_state(state: str)` updates the dot colour:
- `unknown` — gray (`#888`), no status check yet this session
- `available` — green (`#0a0`), reachable + model present
- `running` — blue (`#06a`), worker currently dispatching a request to this host
- `error` — red (`#c00`), failed pre-flight OR errored during the current run

`HostRow.url()` returns the trimmed, normalised URL.

`SettingsSidebar.get_llm_hosts()` returns the list of URLs from non-empty rows.
`SettingsSidebar.set_host_state(url, state)` finds the matching row and
updates its dot. If no row matches (user edited URL mid-run), the call is a
no-op.

URL edits during a run don't affect in-flight workers. The new URL becomes
the working set on the next run.

## Status state machine

```
                 user edits URL
unknown ──────────────────────────┐
   │                              ▼
   │   Run setup / aggregate      unknown   (any state → unknown on URL edit)
   ▼   reachability check
   ●─green── available
              │
              │ worker picks task
              ▼
              ●─blue── running
              │
              ├── task ok ──→ available  (green again, ready for next task)
              │
              └── task fails ──→ ●─red── error
                                   │
                                   │ stays red until:
                                   │   - next Run setup, OR
                                   │   - next enrichment run begins
                                   │   - user edits the URL
                                   ▼
                                 unknown / available
```

The "stays red within the current run" rule is implemented in
`LLMEnrichmentThread` by removing the host from `healthy_hosts` after the
first failure on that host. The UI dot follows the thread's truth.

## Parallel dispatch in `LLMEnrichmentThread`

Existing `run()` structure preserved:
1. Build the task plan from raw_results + options (existing logic, no change).
2. Filter out tasks already completed in resume state (existing).
3. **New**: pre-flight: ping every host once via `llm_client.is_available`.
   Build `healthy_hosts: list[str]`. If empty, emit a fatal status and exit.
4. **New**: create `concurrent.futures.ThreadPoolExecutor(max_workers=len(healthy_hosts))`.
5. Round-robin-assign each pending task a `preferred_host` based on its
   stable task key (`hash(task.key) % len(healthy_hosts)`). This keeps
   cache locality predictable across resumes — the same task hits the same
   host as long as the pool doesn't change.
6. Submit each task to the executor with its preferred host. The submitted
   callable:
   - emits `host_state_changed(host, 'running')`
   - calls `llm_client.complete(prompt, model, host=preferred_host, ...)`
   - on success: emits `host_state_changed(host, 'available')` and returns
     the parsed response
   - on `None` (failure): emits `host_state_changed(host, 'error')`,
     removes the host from a thread-safe `healthy_hosts` set, and returns
     `None`
7. Main thread iterates `as_completed(futures)`:
   - On success: persist run state for this task, emit `partial_result` /
     `progress`.
   - On failure: re-submit the same task to any remaining healthy host
     (round-robin again, excluding the failed one). If no healthy hosts
     remain, pause the run with the saved state preserved and emit a
     status indicating the cause.
8. On pause/cancel signal: stop submitting new tasks. Let in-flight
   workers finish their current request (they're stuck in `urlopen`
   anyway; ungraceful kill of the thread isn't supported). Then drain
   and emit final results.

Concurrency safety:
- `healthy_hosts` set: protected by a `threading.Lock`.
- Run-state file writes: serialised on the main run thread (workers return
  results, main thread persists).
- Qt signal emissions from worker threads: `pyqtSignal` is thread-safe;
  signals are queued onto the receiver thread.

## Failure handling matrix

| Event                              | Behaviour                                  |
| ---------------------------------- | ------------------------------------------ |
| Pre-flight: 0 hosts reachable      | Emit fatal status, do not start run        |
| Pre-flight: some hosts unreachable | Use the reachable subset; rest stay red   |
| Mid-run: 1+ hosts fail             | Drop failed host(s), continue on rest      |
| Mid-run: all hosts fail            | Pause with state preserved, status = error|
| Worker times out (urlopen)         | Same as failure — host marked red, task re-queued |
| User pauses                        | Workers finish current call, then halt     |
| User cancels                       | Same as pause but state is cleared after   |

## Run state / resume

No schema change to the run state file. Tasks are persisted on completion
the same way (one entry per completed task). On resume, the existing logic
filters out completed tasks; the remaining ones feed the new pool.

Drift detection (raw_results/options/model changed since the saved run)
unchanged — applies before pre-flight.

## Testing

Unit tests (no Ollama required):

- `tests/test_ollama_cluster_script.py` — verify CLI parsing, port computation,
  no-network IP detection fallback. Spawning real subprocesses is out of
  scope for unit tests; script logic isolated into pure functions so they
  can be tested standalone.
- `tests/test_llm_enrichment_multihost.py`:
  - All-hosts-healthy: each task dispatched to its preferred host;
    completed tasks match expected results.
  - One host fails mid-run: tasks reassigned, no duplicate completions,
    failed host stays red.
  - All hosts fail: run pauses, state preserved.
  - Single-host pool (back-compat with old config): behaves identically
    to the previous sequential implementation.
  - Resume with smaller pool: tasks reassign without losing completed
    work.
- `tests/test_settings_sidebar_hosts.py`:
  - Adding a row appends to `get_llm_hosts()`.
  - Removing a row updates the list.
  - Editing a URL resets that row's status to unknown.
  - `set_host_state` updates the correct row.
  - At most one row → remove button hidden.

Integration smoke (manual): on a single dev box with one local Ollama,
add three host entries (one valid, one wrong port, one unreachable host),
run enrichment, verify two of three go red, valid one carries the run.

## Headless mode

Lets the user run indexing and/or LLM enrichment from the command line
without launching the GUI. Designed for two cases:

1. Indexing a book on a remote / headless machine (no display).
2. Re-running LLM enrichment after the index already exists, e.g. against
   a freshly-spun multi-host cluster.

### CLI

```
python main.py --headless PATH/TO/BOOK.pdf [--index | --indexall] [--enrich]
                                            [--hosts URL1,URL2,...]
                                            [--model NAME]
                                            [--num-parallel-llm N]
```

Required: `--headless` and the PDF path.

Operation flags (at least one required):
- `--index`: run indexing using the project's saved config if a
  `config.json` already exists alongside the PDF, else `DEFAULT_CONFIG`.
- `--indexall`: run indexing with every rule turned ON except
  `surname_first` (which stays at `False` regardless of the saved config).
  Specifically forces:
  `index_capitalised`, `index_italic`, `bold_indexing`,
  `index_single_quotes`, `index_from_offset`, `index_front_matter_roman`
  all to `True`. `--index` and `--indexall` are mutually exclusive.
- `--enrich`: run LLM enrichment. If combined with `--index` /
  `--indexall`, runs after indexing finishes. If used alone, requires an
  existing `index.json` in the project directory.

Override flags (optional, apply only when relevant operation runs):
- `--hosts URL1,URL2,...` — comma-separated LLM hosts. Overrides
  saved `llm_hosts` for this run. Defaults to whatever the config has.
- `--model NAME` — LLM model name. Defaults to saved config.
- `--num-parallel-llm N` — cap on the ThreadPoolExecutor worker count
  (defaults to `len(hosts)`, which is almost always what you want).

Examples the user has flagged as their common cases:
- `python main.py --headless book.pdf --indexall` — index everything,
  no enrichment.
- `python main.py --headless book.pdf --indexall --enrich` — index
  everything, then enrich using configured hosts.
- `python main.py --headless book.pdf --enrich --hosts http://hewie:11434,http://hewie:11435,http://hewie:11436`
  — re-enrich an already-indexed project against an explicit host list.

### Architecture

A new entry point `controller/headless_runner.py` exposes
`run_headless(args)` taking a parsed `argparse.Namespace`. `main.py`
dispatches to it BEFORE constructing the `QApplication` widgets:

```
main():
  args = parse_args()
  if args.headless:
      sys.exit(run_headless(args))
  else:
      app = QApplication(...)
      ...
```

`run_headless` runs under a plain `QCoreApplication` (no GUI), connects
to the existing `IndexingThread` / `LLMEnrichmentThread` signals, and
drives a simple progress printer:

```
def run_headless(args) -> int:
    app = QCoreApplication(sys.argv)
    project_path = os.path.dirname(os.path.abspath(args.pdf))
    config = build_headless_config(args)  # load + apply CLI overrides

    if args.index or args.indexall:
        ok = _run_indexing(app, project_path, config)
        if not ok:
            return 2

    if args.enrich:
        if not os.path.exists(os.path.join(project_path, "index.json")):
            print("error: --enrich requires an existing index.json", file=sys.stderr)
            return 3
        ok = _run_enrichment(app, project_path, config)
        if not ok:
            return 4

    return 0
```

Each `_run_*` helper:
- Instantiates the thread.
- Connects `progress`, `partial_result`, `*_finished` to stdout printers.
- `thread.start()` then `app.exec()`; the helper's `*_finished` slot
  calls `app.quit()` so `exec()` returns cleanly.
- Returns True/False based on the final status.

No widget / view code is touched in headless mode — the threads already
operate on `model/` data only and emit signals.

### Progress output

Plain-text lines on stdout, one per significant event:
```
[indexing] starting (pages 1-342, strategy=book)
[indexing] 10% ...
[indexing] 50% ...
[indexing] 100% — 1284 entries written to index.{md,txt,html,json}
[enrich] planning tasks across 3 hosts (qwen2.5:7b)
[enrich] pre-flight: http://hewie:11434 OK, http://hewie:11435 OK, http://hewie:11436 OK
[enrich] 0/127 ...
[enrich] 23/127 alias suggestion: ...
[enrich] 127/127 done — index.enhanced.{md,txt,html,json} written
```

Errors go to stderr; the script returns non-zero.

### Exit codes

| Code | Meaning                                        |
| ---- | ---------------------------------------------- |
| 0    | All requested operations completed             |
| 1    | Argument parsing / validation error            |
| 2    | Indexing failed (e.g. PDF unreadable)          |
| 3    | --enrich requested but no index.json present   |
| 4    | Enrichment failed (e.g. all hosts unreachable) |

### Tests

- `tests/test_headless_runner.py` — pure-Python tests that mock the
  thread classes (or use minimal real instances on a tiny PDF fixture):
  - `--indexall` produces the expected forced-on config (and
    `surname_first` stays `False` even if the saved config has it on).
  - `--enrich` without an existing index returns exit code 3.
  - `--hosts a,b,c` produces `llm_hosts=[a, b, c]` in the effective
    config.
  - `--index` and `--indexall` together are rejected by argparse.

## Migration notes

- Existing projects with `llm_host` in their config get auto-migrated to
  `llm_hosts` on load. No user action required.
- The README's LLM enrichment section gains a paragraph on the launcher
  script and the multi-host UI.
- A line in HELP.md or the equivalent in-app help mentions the hosts list.

## File changes summary

| File                                                        | Change                  |
| ----------------------------------------------------------- | ----------------------- |
| `scripts/run_ollama_cluster.py`                             | New                     |
| `model/config.py`                                           | `llm_hosts` + migration |
| `model/llm_enrichment.py`                                   | ThreadPoolExecutor dispatch, host-state signals |
| `model/llm_run_state.py`                                    | No change — task identity/completion tracking is unaffected by which host ran a task |
| `view/settings_sidebar.py`                                  | QTabWidget + HostRow + hosts list |
| `view/llm_setup_dialog.py`                                  | Iterate over hosts, per-host result section     |
| `controller/main_controller.py`                             | Wire new signals; reads `get_llm_hosts()`       |
| `tests/test_ollama_cluster_script.py`                       | New                     |
| `tests/test_llm_enrichment_multihost.py`                    | New                     |
| `tests/test_settings_sidebar_hosts.py`                      | New                     |
| `controller/headless_runner.py`                             | New                     |
| `main.py`                                                   | `--headless` dispatch before `QApplication` |
| `tests/test_headless_runner.py`                             | New                     |
| README (LLM section + headless usage) + HELP.md             | New paragraphs          |
