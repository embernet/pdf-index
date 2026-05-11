"""Tests for the LLM enrichment dispatcher and feature passes.

Every test patches ``model.llm_client.complete`` so we never hit a network
or depend on a model being available.
"""
import pytest

from model import llm_enrichment


def _make_raw(term, page_idxs, contexts=None):
    """Build a raw_results dict for *term* with one occurrence per page idx."""
    contexts = contexts or {}
    occurrences = []
    for idx in page_idxs:
        flags = {
            "italic": False, "bold": False, "caps": False, "single-quotes": False,
        }
        ctx = contexts.get(idx, "")
        if ctx:
            flags["context"] = ctx
        occurrences.append((idx, str(idx + 1), flags))
    return {term: occurrences}


# ---------------------------------------------------------------------------
# Sub-indexing
# ---------------------------------------------------------------------------

def test_subindex_skips_terms_below_threshold(monkeypatch):
    raw = _make_raw("Bach", [0, 1])  # only 2 pages
    monkeypatch.setattr(llm_enrichment.llm_client, "complete",
                        lambda **kw: pytest.fail("should not call LLM"))
    out = llm_enrichment.propose_subentries(raw, host="x", model="m", threshold=8)
    assert out == {}


def test_subindex_clusters_pages_into_subentries(monkeypatch):
    raw = _make_raw(
        "Chopin",
        [11, 13, 21, 78, 101, 102, 103],
        contexts={
            11: "discusses Chopin's compositional style",
            13: "Chopin's harmonic language explored",
            21: "more on Chopin's use of rubato",
            78: "Chopin's late nocturnes",
            101: "Chopin and George Sand",
            102: "Chopin's relationship with Sand",
            103: "their breakup",
        },
    )

    fake_response = {
        "subentries": [
            {"label": "compositional style", "pages": ["12", "14", "22"]},
            {"label": "late works", "pages": ["79"]},
            {"label": "relationship with Sand", "pages": ["102", "103", "104"]},
        ],
    }
    monkeypatch.setattr(llm_enrichment.llm_client, "complete",
                        lambda **kw: fake_response)

    out = llm_enrichment.propose_subentries(raw, host="x", model="m", threshold=4)
    assert "Chopin" in out
    subs = out["Chopin"]
    labels = {s["label"] for s in subs}
    assert "compositional style" in labels
    assert "late works" in labels
    assert "relationship with Sand" in labels
    # Page strings should be range-compressed where contiguous
    style_sub = next(s for s in subs if s["label"] == "compositional style")
    assert "12" in style_sub["pages"]


def test_subindex_ignores_hallucinated_page_labels(monkeypatch):
    raw = _make_raw(
        "Chopin",
        [11, 13],
        contexts={11: "context A", 13: "context B"},
    )
    fake_response = {
        "subentries": [
            {"label": "real cluster", "pages": ["12", "14"]},
            {"label": "fake cluster", "pages": ["999", "1000"]},
        ],
    }
    monkeypatch.setattr(llm_enrichment.llm_client, "complete",
                        lambda **kw: fake_response)
    # Threshold of 1 forces the LLM call
    out = llm_enrichment.propose_subentries(raw, host="x", model="m", threshold=1)
    if "Chopin" in out:
        labels = {s["label"] for s in out["Chopin"]}
        assert "fake cluster" not in labels


def test_subindex_returns_empty_on_unavailable_llm(monkeypatch):
    raw = _make_raw(
        "Chopin",
        list(range(20)),
        contexts={i: "ctx" for i in range(20)},
    )
    monkeypatch.setattr(llm_enrichment.llm_client, "complete",
                        lambda **kw: None)
    out = llm_enrichment.propose_subentries(raw, host="x", model="m", threshold=8)
    assert out == {}


def test_subindex_skips_terms_with_no_context(monkeypatch):
    # Term has many pages but no context strings
    raw = _make_raw("Chopin", list(range(20)))
    called = []
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: called.append(kw) or None,
    )
    out = llm_enrichment.propose_subentries(raw, host="x", model="m", threshold=8)
    assert out == {}
    assert called == [], "should not call LLM when no contexts available"


# ---------------------------------------------------------------------------
# Alias merging
# ---------------------------------------------------------------------------

def test_alias_merging_groups_synonyms(monkeypatch):
    raw = _make_raw("Beethoven", [10, 12])
    raw.update(_make_raw("Ludwig van Beethoven", [10, 50]))
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"aliases": [
            {"primary": "Ludwig van Beethoven", "merged": ["Beethoven"]},
        ]},
    )
    out = llm_enrichment.propose_alias_merges(raw, host="x", model="m")
    assert len(out) == 1
    grp = out[0]
    assert grp["primary"] == "Ludwig van Beethoven"
    assert "Beethoven" in grp["merged"]
    # Combined pages (10, 12, 50) deduped on idx 10
    assert "11" in grp["pages"]
    assert "13" in grp["pages"]
    assert "51" in grp["pages"]


def test_alias_merging_drops_hallucinated_entries(monkeypatch):
    raw = _make_raw("Beethoven", [1])
    raw.update(_make_raw("Mozart", [2]))
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"aliases": [
            {"primary": "Beethoven", "merged": ["Schubert"]},  # Schubert not in index
        ]},
    )
    out = llm_enrichment.propose_alias_merges(raw, host="x", model="m")
    assert out == []  # primary exists but merged set is empty after filtering


# ---------------------------------------------------------------------------
# Category tagging
# ---------------------------------------------------------------------------

def test_categories_assigns_canonical_tags(monkeypatch):
    raw = _make_raw("Chopin", [1])
    raw.update(_make_raw("Paris", [2]))
    raw.update(_make_raw("piano", [3]))
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"categories": {
            "Chopin": "Person",
            "Paris": "Place",
            "piano": "Instrument",
        }},
    )
    out = llm_enrichment.propose_categories(raw, host="x", model="m")
    assert out["Chopin"] == "Person"
    assert out["Paris"] == "Place"
    assert out["piano"] == "Instrument"


def test_categories_rejects_invalid_category(monkeypatch):
    raw = _make_raw("Chopin", [1])
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"categories": {"Chopin": "NotARealCategory"}},
    )
    out = llm_enrichment.propose_categories(raw, host="x", model="m")
    assert "Chopin" not in out


# ---------------------------------------------------------------------------
# See-also
# ---------------------------------------------------------------------------

def test_see_also_keeps_only_existing_entries(monkeypatch):
    raw = _make_raw("Chopin", [1])
    raw.update(_make_raw("Sand, George", [2]))
    raw.update(_make_raw("Romantic period", [3]))
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"see_also": {
            "Chopin": ["Sand, George", "Romantic period", "Hallucinated entry"],
        }},
    )
    out = llm_enrichment.propose_see_also(raw, host="x", model="m")
    assert "Chopin" in out
    assert "Sand, George" in out["Chopin"]
    assert "Romantic period" in out["Chopin"]
    assert "Hallucinated entry" not in out["Chopin"]


def test_see_also_drops_self_references(monkeypatch):
    raw = _make_raw("Chopin", [1])
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete",
        lambda **kw: {"see_also": {"Chopin": ["Chopin"]}},
    )
    out = llm_enrichment.propose_see_also(raw, host="x", model="m")
    assert out == {}


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def test_run_enrichment_respects_toggles(monkeypatch):
    raw = _make_raw("Chopin", [1])
    calls = {"complete": 0}

    def _fake_complete(**kw):
        calls["complete"] += 1
        return None

    monkeypatch.setattr(llm_enrichment.llm_client, "complete", _fake_complete)

    suggestions = llm_enrichment.run_enrichment(
        raw_results=raw,
        formatted={"Chopin": "2"},
        host="x",
        model="m",
        options={
            "subindex": False,
            "alias": False,
            "category": False,
            "seealso": False,
        },
    )
    assert calls["complete"] == 0
    assert suggestions == {
        "subentries": {}, "aliases": [], "categories": {}, "see_also": {},
    }


def test_run_enrichment_returns_stable_schema_when_llm_unavailable(monkeypatch):
    raw = _make_raw("Chopin", [1])
    monkeypatch.setattr(
        llm_enrichment.llm_client, "complete", lambda **kw: None
    )
    suggestions = llm_enrichment.run_enrichment(
        raw_results=raw, formatted={"Chopin": "2"}, host="x", model="m",
    )
    assert set(suggestions) == {"subentries", "aliases", "categories", "see_also"}
