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
