"""Verify the new generate_web_bundle config key defaults to False and
loads correctly for both new and pre-existing project configs."""
import json

from model.config import ConfigManager


def test_default_is_false():
    assert ConfigManager.DEFAULT_CONFIG["generate_web_bundle"] is False


def test_load_returns_default_when_key_missing(tmp_path):
    cfg = {"pdf_filename": "book.pdf", "offset": 0}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    loaded = ConfigManager.load_config(str(tmp_path))
    assert loaded["generate_web_bundle"] is False


def test_load_preserves_explicit_true(tmp_path):
    cfg = {"generate_web_bundle": True}
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    loaded = ConfigManager.load_config(str(tmp_path))
    assert loaded["generate_web_bundle"] is True
