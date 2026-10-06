#!/usr/bin/env python3
"""JEV-021 cache-identity + single-flight tests (JEV spec 1.1, sections 9.3/9.5/9.6).

Proves, against the REAL cache_identity.py implementation (no reimplemented
logic): all six 9.5 key builders carry their spec fields; vector-space gates
refuse fake/corrupt/wrong-version/zero-norm rows and cross-model reuse;
bounded LRU/TTL caches are per-instance (never process-global); concurrent
identical queries cost exactly 1 embed call; different purposes never reuse;
cross-model is refused without spending a call; one failed embed is shared by
all waiters with no per-waiter retry; requested-vs-unique counters hold.

Stdlib only, offline. Run: python3 -m pytest tests/unit/test_cache_identity.py -q
"""

from __future__ import annotations

import importlib.util
import math
import sys
import threading
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MOD = _REPO_ROOT / "shared-utils" / "decision_engine" / "retrieval" / "cache_identity.py"

_spec = importlib.util.spec_from_file_location("jev021_cache_identity", _MOD)
ci = importlib.util.module_from_spec(_spec)
sys.modules["jev021_cache_identity"] = ci
_spec.loader.exec_module(ci)


def _space(**kw):
    base = dict(
        provider="gemini",
        model="gemini-embedding-2",
        dim=3,
        task_type="retrieval_query",
        preprocessing_version="v1",
    )
    base.update(kw)
    return ci.VectorSpace(**base)


def _qkey(purpose="audience-fit", **kw):
    base = dict(
        company="acme",
        query_text="best persona for launch",
        purpose=purpose,
        provider="gemini",
        model="gemini-embedding-2",
        dim=3072,
    )
    base.update(kw)
    return ci.query_key(**base)


# --- 9.5: all six builders carry their spec fields ---------------------------


def test_six_builders_deterministic():
    kw_shared = dict(
        content_hash="h1", provider="gemini", model="gemini-embedding-2",
        dim=3072, preprocessing_version="v1", asset_generation="g7",
    )
    kw_dept = dict(
        company="acme", department="sales", name="Sales", purpose="close",
        keywords=["a", "b"], content_hash="h1", provider="gemini",
        model="gemini-embedding-2", dim=3072,
    )
    kw_align = dict(
        company="acme", mission_version="m1", values_version="v1",
        persona_content_hash="h1", rubric_version="r1", model_version="mm1",
    )
    kw_task = dict(
        task_id="t1", scope_id="s1", input_revision=2, preferences_hash="p1",
        audience_version="a1", sop_version="s1", catalog_version="c1",
        policy_version="po1", model_version="mo1",
    )
    kw_health = dict(
        company="acme", provider="gemini", credential_version="k1",
        config_version="c1",
    )
    assert ci.shared_doc_key(**kw_shared) == ci.shared_doc_key(**kw_shared)
    assert ci.department_key(**kw_dept) == ci.department_key(**kw_dept)
    assert _qkey() == _qkey()
    assert ci.alignment_evidence_key(**kw_align) == ci.alignment_evidence_key(**kw_align)
    assert ci.same_task_decision_key(**kw_task) == ci.same_task_decision_key(**kw_task)
    assert ci.provider_health_key(**kw_health) == ci.provider_health_key(**kw_health)
    kinds = {
        ci.shared_doc_key(**kw_shared).split(".")[1],
        ci.department_key(**kw_dept).split(".")[1],
        _qkey().split(".")[1],
        ci.alignment_evidence_key(**kw_align).split(".")[1],
        ci.same_task_decision_key(**kw_task).split(".")[1],
        ci.provider_health_key(**kw_health).split(".")[1],
    }
    assert len(kinds) == 6  # one namespace per 9.5 table row


def test_each_spec_field_invalidates_its_key():
    assert ci.shared_doc_key(asset_generation="g1", content_hash="h", provider="p",
                              model="m", dim=1, preprocessing_version="v") != \
        ci.shared_doc_key(asset_generation="g2", content_hash="h", provider="p",
                          model="m", dim=1, preprocessing_version="v")
    d = dict(company="c", department="d", name="n", purpose="p", keywords=["k"],
             content_hash="h", provider="p", model="m", dim=1)
    assert ci.department_key(**d) != ci.department_key(**{**d, "company": "other"})
    assert ci.department_key(**d) != ci.department_key(**{**d, "purpose": "other"})
    assert ci.department_key(**d) != ci.department_key(**{**d, "keywords": ["z"]})
    assert _qkey() != _qkey(purpose="topic-retrieval")  # purpose partitions
    assert _qkey() != _qkey(company="other")  # privacy boundary partitions
    assert _qkey() != _qkey(query_text="different text")  # exact text partitions
    assert _qkey() != _qkey(model="text-embedding-3-small", provider="openai")
    a = dict(company="c", mission_version="m", values_version="v",
             persona_content_hash="h", rubric_version="r", model_version="mm")
    assert ci.alignment_evidence_key(**a) != ci.alignment_evidence_key(**{**a, "mission_version": "m2"})
    t = dict(task_id="t", scope_id="s", input_revision=1, preferences_hash="p",
             audience_version="a", sop_version="s", catalog_version="c",
             policy_version="po", model_version="mo")
    assert ci.same_task_decision_key(**t) != ci.same_task_decision_key(**{**t, "input_revision": 2})
    h = dict(company="c", provider="p", credential_version="k", config_version="c")
    assert ci.provider_health_key(**h) != ci.provider_health_key(**{**h, "credential_version": "k2"})


def test_query_key_hides_raw_text():
    key = ci.query_key(company="acme", query_text="super secret launch plan",
                       purpose="p", provider="gemini", model="m", dim=3072)
    assert "super secret launch plan" not in key
    assert "acme" not in key  # digest only: no request text in process maps


def test_builders_reject_missing_fields():
    with pytest.raises(ValueError):
        ci.shared_doc_key(content_hash="", provider="p", model="m", dim=1,
                          preprocessing_version="v", asset_generation="g")
    with pytest.raises(ValueError):
        ci.query_key(company="c", query_text="  ", purpose="p",
                     provider="p", model="m", dim=1)
    with pytest.raises(ValueError):
        ci.department_key(company="c", department="d", name="n", purpose="p",
                          keywords="not-a-list", content_hash="h",
                          provider="p", model="m", dim=1)
    with pytest.raises(ValueError):
        ci.same_task_decision_key(task_id="t", scope_id="s", input_revision=-1,
                                  preferences_hash="p", audience_version="a",
                                  sop_version="s", catalog_version="c",
                                  policy_version="po", model_version="mo")


# --- 9.3: vector-space gates --------------------------------------------------


def test_spaces_compatible_matrix():
    a = _space()
    assert ci.spaces_compatible(a, _space())
    assert not ci.spaces_compatible(a, _space(provider="openai"))  # never cross-provider
    assert not ci.spaces_compatible(a, _space(model="gemini-embedding-2-preview"))  # wrong-version
    assert not ci.spaces_compatible(a, _space(dim=1536))  # dim alone never suffices
    assert not ci.spaces_compatible(a, _space(preprocessing_version="v2"))
    assert ci.spaces_compatible(a, _space(task_type="retrieval_document"))  # legit query/doc pair
    assert not ci.spaces_compatible(a, _space(task_type="classification"))
    assert ci.space_mismatch_reason(a, _space()) == "compatible"
    assert "provider" in ci.space_mismatch_reason(a, _space(provider="openai"))
    with pytest.raises(ci.IncompatibleVectorSpaceError):
        ci.require_compatible(a, _space(provider="openai"), what="test")


def test_validate_vector_rejections():
    ok, _ = ci.validate_vector([1.0, 0.0, 0.0], expected_dim=3)
    assert ok
    for bad in (
        None,  # missing row
        [1.0, 0.0],  # fake: wrong-dim
        [1.0, 0.0, 0.0, 0.0],  # fake: wrong-dim
        [1.0, float("nan"), 0.0],  # corrupt
        [1.0, float("inf"), 0.0],  # corrupt
        [1.0, "x", 0.0],  # corrupt: non-numeric
        [0.0, 0.0, 0.0],  # zero-norm
    ):
        assert ci.validate_vector(bad, expected_dim=3)[0] is False, bad
    with pytest.raises(ci.InvalidVectorError):
        ci.require_valid_vector([0.0, 0.0, 0.0], expected_dim=3)


def test_checked_cosine_gates():
    qa = _space(task_type="retrieval_query")
    doc = _space(task_type="retrieval_document")
    assert ci.checked_cosine([1.0, 0.0, 0.0], qa, [1.0, 0.0, 0.0], doc) == pytest.approx(1.0)
    with pytest.raises(ci.IncompatibleVectorSpaceError):  # never OpenAI query vs Gemini doc
        ci.checked_cosine([1.0, 0.0, 0.0], _space(),
                          [1.0, 0.0, 0.0], _space(provider="openai", model="x"))
    with pytest.raises(ci.InvalidVectorError):  # zero-norm never served
        ci.checked_cosine([0.0, 0.0, 0.0], qa, [1.0, 0.0, 0.0], doc)


# --- 9.5: bounded LRU/TTL, never process-global --------------------------------


def test_bounded_cache_lru_evicts_oldest():
    c = ci.BoundedCache(maxsize=2, ttl_s=60.0)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1  # refresh a; b now oldest
    c.set("c", 3)
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3
    assert len(c) == 2


def test_bounded_cache_ttl_expires():
    c = ci.BoundedCache(maxsize=8, ttl_s=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(0.08)
    assert c.get("k") is None


def test_caches_are_per_instance_not_process_global():
    c1 = ci.QueryEmbeddingCache()
    c2 = ci.QueryEmbeddingCache()
    space = _space(dim=3072)
    calls = []
    c1.embed(key=_qkey(), space=space,
             embed_fn=lambda: calls.append(1) or [1.0] * 3072)
    assert c1.counters == {"requested": 1, "unique": 1}
    assert c2.counters == {"requested": 0, "unique": 0}  # no shared state
    c2.embed(key=_qkey(), space=space,
             embed_fn=lambda: calls.append(1) or [1.0] * 3072)
    assert len(calls) == 2  # second instance re-embeds


# --- 9.6: single-flight ---------------------------------------------------------


def _run_threads(n, fn):
    errors, out = [], [None] * n

    def _w(i):
        try:
            out[i] = fn()
        except Exception as e:  # noqa: BLE001 — shared-failure path under test
            errors.append(e)

    ts = [threading.Thread(target=_w, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in ts)
    return out, errors


def test_singleflight_concurrent_identical_query_one_call():
    cache = ci.QueryEmbeddingCache()
    space = _space(dim=3)
    key = "sf-same"
    calls = []
    lock = threading.Lock()

    def _embed():
        with lock:
            calls.append(1)
        time.sleep(0.2)
        return [1.0, 0.0, 0.0]

    out, errors = _run_threads(8, lambda: cache.embed(key=key, space=space, embed_fn=_embed))
    assert errors == []
    assert len(calls) == 1  # one in-flight embed serves all 8 waiters
    assert all(v == [1.0, 0.0, 0.0] for v in out)
    assert cache.counters == {"requested": 8, "unique": 1}


def test_singleflight_different_purpose_no_reuse():
    cache = ci.QueryEmbeddingCache()
    space = _space(dim=3072)
    calls = []
    for purpose in ("audience-fit", "topic-retrieval"):
        cache.embed(key=_qkey(purpose=purpose), space=space,
                    embed_fn=lambda: calls.append(1) or [1.0] * 3072)
    assert len(calls) == 2


def test_singleflight_cross_model_refused_without_spending_call():
    cache = ci.QueryEmbeddingCache()
    gemini = _space(provider="gemini", model="gemini-embedding-2", dim=3)
    openai = _space(provider="openai", model="text-embedding-3-small", dim=3)
    calls = []
    with pytest.raises(ci.IncompatibleVectorSpaceError):
        cache.embed(key="sf-x", space=openai,
                    embed_fn=lambda: calls.append(1),
                    index_space=gemini)
    assert calls == []  # refused before spending an embed call
    cache.embed(key="sf-x", space=gemini, embed_fn=lambda: [1.0, 0.0, 0.0])
    with pytest.raises(ci.IncompatibleVectorSpaceError):  # cached space differs: no reuse
        cache.embed(key="sf-x", space=openai, embed_fn=lambda: [1.0, 0.0, 0.0])


def test_singleflight_failure_one_attempt_n_waiters():
    cache = ci.QueryEmbeddingCache()
    space = _space(dim=3)
    calls = []
    lock = threading.Lock()

    def _boom():
        with lock:
            calls.append(1)
        time.sleep(0.1)
        raise RuntimeError("embedder down")

    out, errors = _run_threads(
        5, lambda: cache.embed(key="sf-fail", space=space, embed_fn=_boom))
    assert len(calls) == 1  # never one retry per waiter
    assert len(errors) == 5  # every waiter sees the single shared failure
    assert all("embedder down" in str(e) for e in errors)
    assert cache.counters == {"requested": 5, "unique": 1}

    def _fake_dim():
        return [1.0, 0.0]  # fake row: refused, never cached

    with pytest.raises(ci.InvalidVectorError):
        cache.embed(key="sf-fake", space=space, embed_fn=_fake_dim)
    with pytest.raises(ci.InvalidVectorError):  # not cached as a value: re-attempts
        cache.embed(key="sf-fake", space=space, embed_fn=_fake_dim)


def test_counters_requested_vs_unique():
    cache = ci.QueryEmbeddingCache()
    space = _space(dim=2)
    cache.embed(key="c1", space=space, embed_fn=lambda: [1.0, 0.0])
    cache.embed(key="c1", space=space, embed_fn=lambda: [9.0, 9.0])  # hit: no new call
    cache.embed(key="c2", space=space, embed_fn=lambda: [0.0, 1.0])
    assert cache.counters == {"requested": 3, "unique": 2}
