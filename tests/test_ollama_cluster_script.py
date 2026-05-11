import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import run_ollama_cluster as cluster  # noqa: E402


def test_detect_primary_ip_falls_back_to_localhost_on_lookup_failure(monkeypatch):
    def raise_gaierror(name):
        raise socket.gaierror("no DNS")
    monkeypatch.setattr(socket, "gethostbyname_ex", raise_gaierror)
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
