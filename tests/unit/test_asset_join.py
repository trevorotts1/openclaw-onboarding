#!/usr/bin/env python3
"""JEV-022 role-vector asset join tests (JEV spec 1.1, sections 7.4/9.3/9.4).

Proves, against the REAL asset_join.py implementation (no reimplemented
logic): exact (slug, version) joins — no fuzzy match, version bump is a
miss; role-library-import regression lock — shared roles never embed,
rerun over unchanged roles plans zero embeds; tenant shadowing a shared
slug raises; pool completeness — deferred/missing vectors stay in the
pool via the lexical path; every comparison runs through the D21
vector-space guard (cross-provider/model/dim reuse rejected, corrupt
rows rejected).

Stdlib only, offline. Run: python3 -m pytest tests/unit/test_asset_join.py -q
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MOD = _REPO_ROOT / "shared-utils" / "decision_engine" / "retrieval" / "asset_join.py"

_spec = importlib.util.spec_from_file_location("jev022_asset_join", _MOD)
aj = importlib.util.module_from_spec(_spec)
sys.modules["jev022_asset_join"] = aj
_spec.loader.exec_module(aj)


def _space(**kw):
    base = dict(
        provider="gemini",
        model="gemini-embedding-2",
        dim=3,
        task_type="retrieval_document",
        preprocessing_version="v1",
    )
    base.update(kw)
    return aj.VectorSpace(**base)


def _asset(slug, ver="[SECURITY_DATA]", vec=(1.0, 0.0, 0.0), **kw):
    row = dict(slug=slug, content_version=ver, space=_space(), vector=list(vec))
    row.update(kw)
    return row


def _role(slug, ver="[SECURITY_DATA]", **kw):
    role = dict(slug=slug, content_version=ver)
    role.update(kw)
    return role


# --- exact join ---------------------------------------------------------------


def test_exact_hit_returns_both_dicts():
    idx = aj.index_asset_rows([_asset("closer", "v3")])
    out = aj.join_roles([_role("closer", "v3")], idx)
    assert out.hits["closer"]["role"]["slug"] == "closer"
    assert out.hits["closer"]["asset"]["content_version"] == "v3"
    assert out.misses == []


def test_version_bump_is_miss_not_near_hit():
    idx = aj.index_asset_rows([_asset("closer", "v3")])
    out = aj.join_roles([_role("closer", "v4")], idx)
    assert out.hits == {}
    assert out.misses == [{"slug": "closer", "reason": "no-asset-row"}]


def test_no_case_folding_no_trim():
    idx = aj.index_asset_rows([_asset("Closer", "v1")])
    out = aj.join_roles([_role("closer", "v1"), _role(" Closer", "v1")], idx)
    assert out.hits == {}
    assert [m["slug"] for m in out.misses] == ["closer", " Closer"]


def test_missing_version_is_miss():
    idx = aj.index_asset_rows([_asset("closer", "v1")])
    out = aj.join_roles([{"slug": "closer"}], idx)
    assert out.misses == [{"slug": "closer", "reason": "missing-content-version"}]


def test_default_content_version_applies():
    idx = aj.index_asset_rows([_asset("closer", "v9")])
    out = aj.join_roles([{"slug": "closer"}], idx, default_content_version="v9")
    assert "closer" in out.hits


def test_duplicate_role_slug_raises():
    idx = aj.index_asset_rows([_asset("closer", "v1")])
    with pytest.raises(aj.AssetJoinError):
        aj.join_roles([_role("closer", "v1"), _role("closer", "v1")], idx)


def test_slugless_role_raises():
    with pytest.raises(aj.AssetJoinError):
        aj.join_roles([{"content_version": "v1"}], {})


def test_duplicate_asset_key_raises():
    with pytest.raises(aj.DuplicateAssetError):
        aj.index_asset_rows([_asset("closer", "v1"), _asset("closer", "v1")])


def test_corrupt_asset_vector_rejected_at_index():
    bad = _asset("closer", "v1", vec=(1.0, float("nan"), 0.0))
    with pytest.raises(aj.InvalidVectorError):
        aj.index_asset_rows([bad])


def test_zero_norm_asset_vector_rejected_at_index():
    bad = _asset("closer", "v1", vec=(0.0, 0.0, 0.0))
    with pytest.raises(aj.InvalidVectorError):
        aj.index_asset_rows([bad])


# --- import regression lock: shared never embeds ------------------------------


def test_shared_roles_always_skip_rerun_plans_zero_embeds():
    roles = [_role("closer", "v3"), _role("setter", "v3")]
    out = aj.plan_delta_embeds(roles, provisioned={}, shared_slugs=["closer", "setter"])
    assert out["embed"] == []
    assert {s["slug"] for s in out["skip"]} == {"closer", "setter"}


def test_import_rerun_zero_calls_after_change_then_stable():
    roles = [_role("blog-writer", "v2", origin="custom")]
    first = aj.plan_delta_embeds(roles, provisioned={}, shared_slugs=[])
    assert [e["slug"] for e in first["embed"]] == ["blog-writer"]
    second = aj.plan_delta_embeds(
        roles, provisioned={"blog-writer": "v2"}, shared_slugs=[]
    )
    assert second["embed"] == []
    assert second["skip"] == [{"slug": "blog-writer", "reason": "unchanged"}]


def test_changed_tenant_version_embeds_tenant_local_scope():
    roles = [_role("blog-writer", "v3", origin="custom")]
    out = aj.plan_delta_embeds(
        roles, provisioned={"blog-writer": "v2"}, shared_slugs=[]
    )
    assert out["embed"] == [
        {"slug": "blog-writer", "content_version": "v3", "scope": "tenant-local"}
    ]


def test_tenant_shadowing_shared_slug_raises():
    roles = [_role("closer", "v9", origin="custom")]
    with pytest.raises(aj.SharedRoleEmbedError):
        aj.plan_delta_embeds(roles, provisioned={}, shared_slugs=["closer"])


def test_module_has_no_embed_callback_param():
    import inspect

    sig = inspect.signature(aj.plan_delta_embeds)
    names = {p.lower() for p in sig.parameters}
    assert not ({"embed_fn", "embedfn", "callback", "embedder"} & names)


def test_unknown_origin_raises():
    with pytest.raises(aj.AssetJoinError):
        aj.plan_delta_embeds(
            [_role("x", "v1", origin="mystery")], provisioned={}, shared_slugs=[]
        )


# --- pool completeness: misses stay via lexical path --------------------------


def test_miss_stays_in_pool_via_lexical_path():
    idx = aj.index_asset_rows([_asset("closer", "v3")])
    joined = aj.join_roles([_role("closer", "v3"), _role("setter", "v9")], idx)
    pool = aj.build_pool(
        joined,
        query_vector=[1.0, 0.0, 0.0],
        query_space=_space(task_type="retrieval_query"),
        lexical_scores={"setter": 0.42},
    )
    by_slug = {e.slug: e for e in pool}
    assert by_slug["closer"].mode == "vector"
    assert by_slug["closer"].score == pytest.approx(1.0)
    assert by_slug["setter"].mode == "lexical"
    assert by_slug["setter"].score == pytest.approx(0.42)


def test_miss_without_lexical_score_defaults_zero():
    joined = aj.JoinResult(hits={}, misses=[{"slug": "ghost", "reason": "no-asset-row"}])
    pool = aj.build_pool(
        joined, query_vector=[1.0, 0.0, 0.0], query_space=_space()
    )
    assert pool == [aj.PoolEntry(slug="ghost", mode="lexical", score=0.0)]


def test_pool_sorted_score_desc_slug_asc():
    joined = aj.JoinResult(
        hits={},
        misses=[
            {"slug": "b-role", "reason": "no-asset-row"},
            {"slug": "a-role", "reason": "no-asset-row"},
        ],
    )
    pool = aj.build_pool(
        joined,
        query_vector=[1.0, 0.0, 0.0],
        query_space=_space(),
        lexical_scores={"b-role": 0.5, "a-role": 0.5},
    )
    assert [e.slug for e in pool] == ["a-role", "b-role"]


def test_nonfinite_lexical_score_raises():
    joined = aj.JoinResult(
        hits={}, misses=[{"slug": "x", "reason": "no-asset-row"}]
    )
    with pytest.raises(aj.AssetJoinError):
        aj.build_pool(
            joined,
            query_vector=[1.0, 0.0, 0.0],
            query_space=_space(),
            lexical_scores={"x": float("inf")},
        )
    with pytest.raises(aj.AssetJoinError):
        aj.build_pool(
            joined,
            query_vector=[1.0, 0.0, 0.0],
            query_space=_space(),
            lexical_scores={"x": "high"},
        )


# --- D21 vector-space guard reuse ---------------------------------------------


def test_cross_provider_comparison_raises():
    idx = aj.index_asset_rows(
        [_asset("closer", "v3", space=_space(provider="openai", model="text-ada"))]
    )
    joined = aj.join_roles([_role("closer", "v3")], idx)
    with pytest.raises(aj.IncompatibleVectorSpaceError):
        aj.build_pool(
            joined, query_vector=[1.0, 0.0, 0.0], query_space=_space()
        )


def test_cross_model_same_dim_raises():
    idx = aj.index_asset_rows([_asset("closer", "v3", space=_space(model="other"))])
    joined = aj.join_roles([_role("closer", "v3")], idx)
    with pytest.raises(aj.IncompatibleVectorSpaceError):
        aj.build_pool(
            joined, query_vector=[1.0, 0.0, 0.0], query_space=_space()
        )


def test_dim_mismatch_raises():
    idx = aj.index_asset_rows(
        [_asset("closer", "v3", space=_space(dim=4), vec=(1.0, 0.0, 0.0, 0.0))]
    )
    joined = aj.join_roles([_role("closer", "v3")], idx)
    with pytest.raises((aj.IncompatibleVectorSpaceError, aj.InvalidVectorError)):
        aj.build_pool(
            joined, query_vector=[1.0, 0.0, 0.0], query_space=_space()
        )


def test_query_document_pair_allowed():
    idx = aj.index_asset_rows(
        [_asset("closer", "v3", space=_space(task_type="retrieval_document"))]
    )
    joined = aj.join_roles([_role("closer", "v3")], idx)
    pool = aj.build_pool(
        joined,
        query_vector=[1.0, 0.0, 0.0],
        query_space=_space(task_type="retrieval_query"),
    )
    assert pool[0].score == pytest.approx(1.0)


def test_incompatible_task_type_raises():
    idx = aj.index_asset_rows(
        [_asset("closer", "v3", space=_space(task_type="classification"))]
    )
    joined = aj.join_roles([_role("closer", "v3")], idx)
    with pytest.raises(aj.IncompatibleVectorSpaceError):
        aj.build_pool(
            joined,
            query_vector=[1.0, 0.0, 0.0],
            query_space=_space(task_type="retrieval_query"),
        )


def test_corrupt_query_vector_raises():
    idx = aj.index_asset_rows([_asset("closer", "v3")])
    joined = aj.join_roles([_role("closer", "v3")], idx)
    with pytest.raises(aj.InvalidVectorError):
        aj.build_pool(
            joined,
            query_vector=[1.0, float("nan"), 0.0],
            query_space=_space(),
        )


def test_no_db_no_network_markers():
    src = _MOD.read_text()
    for token in ("sqlite", "open(", "socket", "urllib", "requests", "http"):
        assert token not in src, token
