"""Spawn multiple Ollama instances on a single machine for parallel LLM
enrichment. Each instance binds to a different port and shares the same
on-disk models directory.

See docs/superpowers/specs/2026-05-11-multi-host-llm-enrichment-design.md
for the architecture rationale (memory-bandwidth utilisation on
unified-memory GPUs).
"""

from __future__ import annotations

import argparse
import ipaddress
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
            try:
                parsed = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if parsed.version == 4 and not parsed.is_loopback:
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
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def format_summary(ip: str, ports: List[int]) -> str:
    """Format the copy-paste-ready summary block printed when the cluster
    is ready. Tested for stability so a UI screenshot in docs doesn't
    drift silently."""
    lines = ["Cluster ready. Add these to LLM Enrichment → Hosts:"]
    for port in ports:
        lines.append(f"  http://{ip}:{port}")
    return "\n".join(lines)


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
    except (urllib.error.URLError, TimeoutError, OSError):
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
