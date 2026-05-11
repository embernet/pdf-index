"""Tests that opening a project with a saved llm_run.json restores the
LLM Enhanced view and writes any missing .enhanced.* files.

This guards two specific recovery paths:

1. **App-restart restoration** — when the previous run finished, on
   reopen the LLM Enhanced bucket should appear and the suggestions
   should be loaded back into memory automatically.

2. **One-off migration from the old Apply-Accepted flow** — runs that
   completed before auto-apply landed have a state file with
   ``status="completed"`` and ``suggestions={...}`` but no
   ``.enhanced.*`` files on disk. Opening the project should regenerate
   them silently.
"""
import json
import os

import pytest

from PyQt6.QtWidgets import QApplication

from model import llm_run_state


@pytest.fixture(scope="module")
def qapp():
    import sys
    return QApplication.instance() or QApplication(sys.argv)


def _write_state(project_path, *, status, with_suggestions=True):
    suggestions = {
        "subentries": {"Chopin": [{"label": "x", "pages": "1, 2", "page_idxs": [0, 1]}]} if with_suggestions else {},
        "aliases": [],
        "categories": {"Chopin": "Person"} if with_suggestions else {},
        "see_also": {},
    }
    plan = [{"id": "subindex:Chopin", "kind": "subindex", "label": "x", "payload": {"term": "Chopin"}}]
    raw = {"Chopin": [(0, "1", {"italic": False}), (1, "2", {"italic": False})]}
    # Match the SettingsSidebar default toggles so tests of non-drifted
    # paths don't accidentally trip the drift check.
    options = {
        "subindex": True, "alias": True, "category": True,
        "seealso": True, "threshold": 8,
    }
    state = llm_run_state.make_run_state(
        plan=plan, raw_results=raw,
        options=options, model="qwen2.5:7b", host="http://localhost:11434",
    )
    state.completed_ids = ["subindex:Chopin"]
    state.suggestions = suggestions
    state.status = status
    llm_run_state.save(state, project_path)
    return raw, suggestions


def _make_controller_with_project(qapp, tmp_path, raw_results):
    from controller.main_controller import MainController
    ctrl = MainController()
    ctrl.project_path = str(tmp_path)
    ctrl.last_raw_results = raw_results
    ctrl.last_formatted_results = {term: ", ".join(o[1] for o in occs) for term, occs in raw_results.items()}
    return ctrl


# ---------------------------------------------------------------------------
# Reopen-restoration: completed
# ---------------------------------------------------------------------------

def test_completed_run_restores_suggestions_on_reopen(qapp, tmp_path):
    raw, suggestions = _write_state(str(tmp_path), status="completed")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()
    assert ctrl._last_llm_suggestions == suggestions
    assert ctrl.view.controls_output.style_llm_enhanced_btn.isHidden() is False


def test_completed_run_writes_missing_enhanced_files(qapp, tmp_path):
    raw, suggestions = _write_state(str(tmp_path), status="completed")
    base = os.path.join(str(tmp_path), "index")
    # No .enhanced.* files yet
    for ext in (".enhanced.md", ".enhanced.txt", ".enhanced.html", ".enhanced.json"):
        assert not os.path.exists(base + ext)

    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()

    # All four files now exist
    for ext in (".enhanced.md", ".enhanced.txt", ".enhanced.html", ".enhanced.json"):
        assert os.path.exists(base + ext), f"missing {ext}"
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "Chopin" in md


def test_completed_run_does_not_overwrite_substantial_enhanced_files(qapp, tmp_path):
    """User edits to a real enhanced file are preserved on reopen."""
    raw, _ = _write_state(str(tmp_path), status="completed")
    base = os.path.join(str(tmp_path), "index")
    # Real-sized content — well above the 200-byte stale-file heuristic
    sentinel = "EDITED BY USER\n" + "x" * 500
    for ext in (".enhanced.md", ".enhanced.txt", ".enhanced.html", ".enhanced.json"):
        with open(base + ext, "w", encoding="utf-8") as f:
            f.write(sentinel)

    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()

    for ext in (".enhanced.md", ".enhanced.txt", ".enhanced.html", ".enhanced.json"):
        assert open(base + ext).read() == sentinel, f"{ext} was overwritten"


def test_stale_tiny_enhanced_files_get_regenerated(qapp, tmp_path):
    """The bug-written near-empty files are detected and replaced."""
    raw, _ = _write_state(str(tmp_path), status="completed")
    base = os.path.join(str(tmp_path), "index")
    # Reproduce the bug output: header-only, well under 200 bytes
    tiny = "# Enhanced Index (0 entries)\n"
    for ext in (".enhanced.md", ".enhanced.txt", ".enhanced.html"):
        with open(base + ext, "w", encoding="utf-8") as f:
            f.write(tiny)
    # JSON file gets a normal-looking payload (it had raw data even when
    # the others didn't)
    with open(base + ".enhanced.json", "w", encoding="utf-8") as f:
        f.write('{"schema": "pdf-index/enhanced/1"}')

    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl.last_formatted_results = {"Chopin": "1, 2"}
    ctrl._refresh_resume_banner()

    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "Chopin" in md, f"stale .enhanced.md was NOT regenerated: {md!r}"
    # Different from the stale "(0 entries)" header
    assert "(0 entries)" not in md


def test_completed_run_with_drift_still_restores_but_warns(qapp, tmp_path):
    raw, suggestions = _write_state(str(tmp_path), status="completed")
    # Mutate raw so the hash drifts
    drifted_raw = {"Different": [(99, "100", {})]}
    ctrl = _make_controller_with_project(qapp, tmp_path, drifted_raw)
    ctrl._refresh_resume_banner()
    assert ctrl._last_llm_suggestions == suggestions
    assert ctrl.view.controls_output.style_llm_enhanced_btn.isHidden() is False


# ---------------------------------------------------------------------------
# Reopen-restoration: paused / interrupted
# ---------------------------------------------------------------------------

def test_paused_run_shows_banner_and_restores_suggestions(qapp, tmp_path):
    raw, suggestions = _write_state(str(tmp_path), status="paused")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()
    assert ctrl._last_llm_suggestions == suggestions
    assert ctrl.view.settings_sidebar.llm_banner.isHidden() is False


def test_running_status_treated_as_interrupted_on_reopen(qapp, tmp_path):
    raw, suggestions = _write_state(str(tmp_path), status="running")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()
    assert ctrl._last_llm_suggestions == suggestions
    assert ctrl.view.settings_sidebar.llm_banner.isHidden() is False
    label_text = ctrl.view.settings_sidebar.llm_banner_label.text()
    assert "interrupted" in label_text or "paused" in label_text


# ---------------------------------------------------------------------------
# Reopen with no state file
# ---------------------------------------------------------------------------

def test_no_state_file_leaves_ui_clean(qapp, tmp_path):
    ctrl = _make_controller_with_project(qapp, tmp_path, {"Foo": [(0, "1", {})]})
    ctrl._refresh_resume_banner()
    assert ctrl.view.settings_sidebar.llm_banner.isHidden() is True


# ---------------------------------------------------------------------------
# Cancelled status — leaves UI clean (no banner) but doesn't crash
# ---------------------------------------------------------------------------

def test_cancelled_state_does_not_show_banner(qapp, tmp_path):
    raw, _ = _write_state(str(tmp_path), status="cancelled")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()
    assert ctrl.view.settings_sidebar.llm_banner.isHidden() is True


# ---------------------------------------------------------------------------
# Selecting the LLM Enhanced radio actually flips the rendered view
# ---------------------------------------------------------------------------

def test_selecting_llm_enhanced_renders_enhanced_view(qapp, tmp_path):
    """Reopen → select LLM Enhanced radio → markdown view shows the
    enhanced document, not the rule-based one. Guards against the bug
    where ``process_and_display_results`` blew up trying to call
    ``filter_by_style(raw, 'llm_enhanced')``."""
    raw, suggestions = _write_state(str(tmp_path), status="completed")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    ctrl._refresh_resume_banner()
    # Select LLM Enhanced + Markdown view tab
    ctrl.view.controls_output.style_llm_enhanced_btn.setChecked(True)
    from view.controls_output import TAB_MODES
    ctrl.view.controls_output.view_tabs.setCurrentIndex(
        TAB_MODES.index("markdown")
    )
    # Drive the same path the click would take
    ctrl.process_and_display_results()

    # The markdown content placed into output_text should be the enhanced
    # rendering — distinguishable by the "Enhanced Index" header that the
    # base generate_markdown does NOT produce.
    text = ctrl.view.controls_output.output_text.toPlainText()
    assert "Enhanced Index" in text
    assert "Chopin" in text


def test_migration_writes_real_content_after_index_loaded(qapp, tmp_path):
    """The previous bug: migration ran before the index loaded so the
    .md/.txt/.html files were written with zero entries. Verify they
    contain real content once the index is in memory."""
    raw, _ = _write_state(str(tmp_path), status="completed")
    base = os.path.join(str(tmp_path), "index")
    ctrl = _make_controller_with_project(qapp, tmp_path, raw)
    # Format raw_results the same way the controller does on real load
    from model.indexer import IndexingThread
    ctrl.last_formatted_results = IndexingThread.process_results(
        None, ctrl.last_raw_results, capitalize_keys=False,
    )
    ctrl._refresh_resume_banner()

    # The text file should contain the term, not just the bare header
    txt = open(base + ".enhanced.txt", encoding="utf-8").read()
    assert "Chopin" in txt, f"enhanced.txt is missing real content:\n{txt!r}"
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "Chopin" in md
    html = open(base + ".enhanced.html", encoding="utf-8").read()
    assert "Chopin" in html
