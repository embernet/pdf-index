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
