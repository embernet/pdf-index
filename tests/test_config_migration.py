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


def test_load_config_default_when_neither_key_in_existing_file():
    """A config file that predates llm_host entirely still gets the default
    list — the merge brings in DEFAULT_CONFIG['llm_hosts'] and the
    migration block correctly does nothing."""
    with tempfile.TemporaryDirectory() as project_path:
        with open(os.path.join(project_path, "config.json"), "w") as f:
            json.dump({"strategy": "logical"}, f)
        cfg = ConfigManager.load_config(project_path)
    assert cfg["llm_hosts"] == ["http://localhost:11434"]


def test_load_config_default_when_neither_present():
    """A fresh config (no llm_host, no llm_hosts) gets the default list."""
    with tempfile.TemporaryDirectory() as project_path:
        cfg = ConfigManager.load_config(project_path)
    assert cfg["llm_hosts"] == ["http://localhost:11434"]
