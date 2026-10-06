#!/usr/bin/env python3
"""REP-032 / A32 regression tests — "Mismatched models/dimensions,
corrupt/fake vectors, zero norms, stale indexes yield truthful fallback."
(JEV spec 1.1, section 9.3 / acceptance row A32.)

Proves against the REAL freshness.py + guarded_retrieval.py (no reimplemented
logic):

  * CONTROL first: a known-good index + known-good query takes the VECTOR path
    and reports ``semantic`` — if this fails the instrument is broken and no
    other assertion here means anything.
  * a stale index (identical declared space, older persona set) never scores a
    cosine and is reported ``lexical``, with the staleness reason carried.
  * mismatched dimension, corrupt/non-finite, zero-norm, and fake
    provider-stamped rows are each demoted with their own reason, and
    ``served_path`` never claims the vector path for any of them.
  * only a PRESENT stamp that DISAGREES is stale: absent/unparseable stamps are
    fresh (legacy/adopting boxes must keep working).

Stdlib only, offline. Run:
  python3 -m pytest tests/unit/test_rep032_truthful_fallback.py -q
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_RET = _REPO_ROOT / "shared-utils" / "decision_engine" / "retrieval"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_fr = _load("rep032_freshness_t", _RET / "freshness.py")
_gr = _load("rep032_guarded_t", _RET / "guarded_retrieval.py")

_Q = [1.0, 0.0, 0.0]
_SPACE = _gr.VectorSpace(provider="gemini", model="gemini-embedding-2", dim=3,
                         task_type="retrieval_query", preprocessing_version="v1")
_DOC = _SPACE._replace(task_type="retrieval_document")


def _good_dir(root: Path, *, live_md5: str | None = None) -> Path:
    """An index dir whose .persona-set-version matches its own live set."""
    d = root / "index"
    d.mkdir(parents=True, exist_ok=True)
    cats = d / "persona-categories.json"
    live = {"sop-coach": {}, "closer": {}}
    cats.write_text(json.dumps({"md5": "n/a", "personas": live}) + "\n")
    md5 = live_md5 or hashlib.md5(cats.read_bytes()).hexdigest()
    (d / ".persona-set-version").write_text(json.dumps(
        {"md5": md5, "persona_count": len(live)}) + "\n")
    return d


def _cats(d: Path) -> Path:
    return d / "persona-categories.json"


def _row(slug="sop-coach", vec=None, space=None):
    return {"slug": slug, "space": space or _DOC,
            "vector": [1.0, 0.0, 0.0] if vec is None else vec}


# ---------------------------------------------------------------------------
# CONTROL — must pass before anything else is meaningful.
# ---------------------------------------------------------------------------
def test_control_known_good_index_and_query_takes_the_vector_path(tmp_path):
    d = _good_dir(tmp_path)
    v = _fr.check_index_freshness(d, _cats(d))
    assert (v.status, v.servable, v.served_path) == ("fresh", True, "semantic"), v

    r = _gr.guarded_persona_retrieval([_row()], query_vector=_Q,
                                      query_space=_SPACE, index_dir=d,
                                      categories_path=_cats(d))
    assert r.served_path == "semantic", r
    assert [e.mode for e in r.entries] == ["vector"], r
    assert r.demotions == {}, r
    assert r.entries[0].score == pytest.approx(1.0), r


# ---------------------------------------------------------------------------
# Stale index — the prep's probe case 6b: identical declared space.
# ---------------------------------------------------------------------------
def test_stale_index_never_scores_and_reports_lexical(tmp_path):
    d = _good_dir(tmp_path, live_md5="0" * 32)  # stamp disagrees with the bytes
    v = _fr.check_index_freshness(d, _cats(d))
    assert v.status == "stale" and v.served_path == "lexical", v

    r = _gr.guarded_persona_retrieval([_row()], query_vector=_Q,
                                      query_space=_SPACE, index_dir=d,
                                      categories_path=_cats(d))
    assert r.served_path == "lexical", r
    assert r.freshness_status == "stale", r
    # a stale vector contributes no cosine: the row is lexical, never vector
    assert [e.mode for e in r.entries] == ["lexical"], r
    assert "stale" in r.demotions["sop-coach"], r


def test_persona_count_disagreement_on_same_bytes_is_stale(tmp_path):
    d = _good_dir(tmp_path)
    p = d / ".persona-set-version"
    p.write_text(json.dumps({"md5": hashlib.md5(_cats(d).read_bytes()).hexdigest(),
                             "persona_count": 99}) + "\n")
    v = _fr.check_index_freshness(d, _cats(d))
    assert v.status == "stale" and v.served_path == "lexical", v


# ---------------------------------------------------------------------------
# The other three fault classes, each demoted with its OWN reason.
# ---------------------------------------------------------------------------
def test_mismatched_dimension_is_demoted_and_named(tmp_path):
    d = _good_dir(tmp_path)
    wide = _SPACE._replace(dim=1536)
    r = _gr.guarded_persona_retrieval([_row()], query_vector=_Q,
                                      query_space=wide, index_dir=d,
                                      categories_path=_cats(d))
    assert r.served_path == "lexical", r
    assert [e.mode for e in r.entries] == ["lexical"], r
    assert "dim" in r.demotions["sop-coach"], r


def test_corrupt_nonfinite_row_is_demoted(tmp_path):
    d = _good_dir(tmp_path)
    r = _gr.guarded_persona_retrieval([_row(vec=[1.0, float("nan"), 0.0])],
                                      query_vector=_Q, query_space=_SPACE,
                                      index_dir=d, categories_path=_cats(d))
    assert r.served_path == "lexical", r
    assert "non-finite" in r.demotions["sop-coach"], r


def test_zero_norm_row_is_demoted(tmp_path):
    d = _good_dir(tmp_path)
    r = _gr.guarded_persona_retrieval([_row(vec=[0.0, 0.0, 0.0])],
                                      query_vector=_Q, query_space=_SPACE,
                                      index_dir=d, categories_path=_cats(d))
    assert r.served_path == "lexical", r
    assert "zero-norm" in r.demotions["sop-coach"], r


def test_fake_provider_stamped_row_is_demoted(tmp_path):
    d = _good_dir(tmp_path)
    row = _row(space=_DOC._replace(provider="fake", model="deterministic-hash-768"))
    r = _gr.guarded_persona_retrieval([row], query_vector=_Q, query_space=_SPACE,
                                      index_dir=d, categories_path=_cats(d))
    assert r.served_path == "lexical", r
    assert "provider" in r.demotions["sop-coach"], r


def test_partial_demotion_is_reported_partial(tmp_path):
    """A good row + a bad row never reports a clean ``semantic`` answer."""
    d = _good_dir(tmp_path)
    r = _gr.guarded_persona_retrieval(
        [_row(), _row("evil", vec=[0.0, 0.0, 0.0])],
        query_vector=_Q, query_space=_SPACE, index_dir=d, categories_path=_cats(d))
    assert r.served_path == "semantic-partial", r
    assert r.counts == {"vector": 1, "lexical": 1}, r
    assert set(r.demotions) == {"evil"}, r


# ---------------------------------------------------------------------------
# Truthfulness: every entry carries a reason; the demoted score is the
# caller's lexical score, never the refused cosine.
# ---------------------------------------------------------------------------
def test_demoted_entries_carry_reasons_and_never_a_cosine(tmp_path):
    d = _good_dir(tmp_path)
    r = _gr.guarded_persona_retrieval(
        [_row("zero", vec=[0.0, 0.0, 0.0]), _row("nan", vec=[float("nan"), 0.0, 0.0])],
        query_vector=_Q, query_space=_SPACE, index_dir=d, categories_path=_cats(d),
        lexical_scores={"zero": 0.4, "nan": 0.9})
    assert r.served_path == "lexical", r
    assert r.entries[0].slug == "nan" and r.entries[0].score == 0.9, r
    assert all(e.reason for e in r.entries), r
    assert all(e.mode == "lexical" for e in r.entries), r


# ---------------------------------------------------------------------------
# Legacy/adopting boxes: absence of a stamp is NOT staleness.
# ---------------------------------------------------------------------------
def test_absent_stamp_is_fresh_not_stale(tmp_path):
    d = _good_dir(tmp_path)
    (d / ".persona-set-version").unlink()
    v = _fr.check_index_freshness(d, _cats(d))
    assert v.status == "fresh" and v.servable and v.served_path == "semantic", v


def test_unparseable_stamp_is_fresh_not_stale(tmp_path):
    d = _good_dir(tmp_path)
    (d / ".persona-set-version").write_text("{ this is not json")
    v = _fr.check_index_freshness(d, _cats(d))
    assert v.status == "fresh" and v.servable, v


def test_no_inputs_is_unknown_and_labelled_unverified(tmp_path):
    v = _fr.check_index_freshness(None, None)
    assert v.status == "unknown" and v.servable, v
    assert v.served_path == "unknown-unverified", v
    assert v.status != "fresh", "UNKNOWN must never be labelled fresh"
