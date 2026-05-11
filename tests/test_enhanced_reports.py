"""Tests for the enhanced-output writer.

The hard rules to defend:

1. Files written must include ``.enhanced.`` in their names.
2. The base files (``index.md`` etc.) must not be modified by the writer.
3. The writer must run with no suggestions (Phase 1 plumbing) and produce
   files structurally similar to the base output.
"""
import json
import os

from model import enhanced_reports


SAMPLE_FORMATTED = {
    "Chopin": "12, 14-17, 22, 79",
    "Debussy": "44, 56",
    "Bach": "3, 5, 9-11",
}


def test_enhanced_filenames_contain_enhanced_token(tmp_path):
    base = str(tmp_path / "index")
    written = enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
    )
    assert len(written) == 4
    for path in written:
        assert ".enhanced." in os.path.basename(path), path


def test_writer_does_not_touch_base_files(tmp_path):
    base = str(tmp_path / "index")
    base_files = {
        f"{base}.md": "BASE MARKDOWN",
        f"{base}.html": "<html>BASE</html>",
        f"{base}.txt": "BASE TEXT",
        f"{base}.json": '{"base": true}',
    }
    for path, content in base_files.items():
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
    )

    for path, expected in base_files.items():
        with open(path, "r", encoding="utf-8") as f:
            assert f.read() == expected, f"base file {path} was modified!"


def test_runs_with_no_suggestions(tmp_path):
    base = str(tmp_path / "index")
    written = enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
        suggestions=None,
    )
    assert len(written) == 4
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "Chopin" in md
    assert "Debussy" in md
    assert "Enhanced Index" in md


def test_subentries_render_in_markdown(tmp_path):
    base = str(tmp_path / "index")
    suggestions = {
        "subentries": {
            "Chopin": [
                {"label": "compositional style", "pages": "14, 22"},
                {"label": "late works", "pages": "79"},
            ],
        },
    }
    enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
        suggestions=suggestions,
    )
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "compositional style" in md
    assert "late works" in md
    # Sub-entries should be indented under the parent
    assert "  - " in md


def test_categories_drive_section_headers(tmp_path):
    base = str(tmp_path / "index")
    suggestions = {
        "categories": {
            "Chopin": "Composer",
            "Debussy": "Composer",
            "Bach": "Composer",
        },
    }
    enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
        suggestions=suggestions,
    )
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "## Composer" in md


def test_see_also_renders_in_markdown(tmp_path):
    base = str(tmp_path / "index")
    suggestions = {
        "see_also": {"Chopin": ["Romantic period", "Sand, George"]},
    }
    enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
        suggestions=suggestions,
    )
    md = open(base + ".enhanced.md", encoding="utf-8").read()
    assert "see also" in md
    assert "Romantic period" in md


def test_json_payload_has_stable_schema(tmp_path):
    base = str(tmp_path / "index")
    enhanced_reports.write_enhanced_files(
        path_base=base,
        formatted=SAMPLE_FORMATTED,
        raw_results={"Chopin": [(11, "12", {"italic": False})]},
    )
    payload = json.loads(open(base + ".enhanced.json", encoding="utf-8").read())
    assert payload["schema"] == "pdf-index/enhanced/1"
    for key in ("raw_results", "subentries", "aliases", "categories", "see_also"):
        assert key in payload
