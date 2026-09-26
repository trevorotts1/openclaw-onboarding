#!/usr/bin/env python3
"""JEV 1.1 sections 7.4/9.4 — central role-vector asset join (unit JEV-022).

Joins centrally shipped Command Center role-library SOP vectors to local
role rows by EXACT (role/SOP slug, content version). Pure data join over
caller-supplied mappings: this module performs zero embedding calls and
accepts no embed callbacks, so rerunning role-library import or converge
over unchanged shared roles can never trigger embedding (regression lock
for the reviewed role-library-import fix).

Rules (spec 7.4 + 9.3/9.4):
  * Exact key only: slug and content version compare with ``==`` — no case
    folding, no trimming, no fuzzy match. A version bump is a miss, not a
    near-hit; the caller installs the newer central asset instead.
  * Shared roles never embed: canonical vectors ship with the asset and its
    manifest. Only new-or-changed tenant-local (custom/client) roles are
    ever listed for delta embedding — and only as a plan. This module never
    embeds; it returns lists.
  * Pool completeness: roles whose vectors are deferred or missing join as
    misses yet stay in the candidate pool through the lexical path with a
    caller-supplied lexical score. Missing never means disappeared.
  * Every comparison runs through the D21 vector-space guard
    (``cache_identity``): cross-provider/model/dim/preprocessing/task reuse
    raises; fake, corrupt, wrong-version, and zero-norm rows raise.
  * Install ordering: callers provision central vectors only after the local
    SOP/role rows exist. Every input here is caller-supplied; nothing is
    read from a client database, the network, or a provider.

Stdlib only. Offline. No state writes.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, NamedTuple

try:  # packaged layout
    from .cache_identity import (
        IncompatibleVectorSpaceError,
        InvalidVectorError,
        VectorSpace,
        checked_cosine,
        require_valid_vector,
    )
except ImportError:  # direct file load (unit tests): load sibling by path
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _Path

    _SIB = _Path(__file__).with_name("cache_identity.py")
    _spec = _ilu.spec_from_file_location("jev022_cache_identity_sib", _SIB)
    _ci = _ilu.module_from_spec(_spec)
    _sys.modules["jev022_cache_identity_sib"] = _ci
    _spec.loader.exec_module(_ci)
    IncompatibleVectorSpaceError = _ci.IncompatibleVectorSpaceError
    InvalidVectorError = _ci.InvalidVectorError
    VectorSpace = _ci.VectorSpace
    checked_cosine = _ci.checked_cosine
    require_valid_vector = _ci.require_valid_vector

__version__ = "1.0.0"
__all__ = [
    "IncompatibleVectorSpaceError",
    "InvalidVectorError",
    "AssetJoinError",
    "DuplicateAssetError",
    "SharedRoleEmbedError",
    "JoinResult",
    "PoolEntry",
    "index_asset_rows",
    "join_roles",
    "plan_delta_embeds",
    "build_pool",
]

SHARED = "shared"
_TENANT_ORIGINS = frozenset({"custom", "tenant-local", "tenant_local", "client", "private"})


class AssetJoinError(ValueError):
    """Malformed join input; fail-closed, never a silent drop."""


class DuplicateAssetError(AssetJoinError):
    """Two central-asset rows claim one exact (slug, content version) key."""


class SharedRoleEmbedError(AssetJoinError):
    """A shared-asset slug was asked to embed or got shadowed by tenant material."""


class JoinResult(NamedTuple):
    hits: dict  # slug -> {"role": dict, "asset": dict}
    misses: list  # [{"slug": str, "reason": str}] — stay in pool via lexical path


class PoolEntry(NamedTuple):
    slug: str
    mode: str  # "vector" | "lexical"
    score: float


def _need_slug(row: Mapping, *, what: str) -> str:
    slug = row.get("slug")
    if not isinstance(slug, str) or not slug:
        raise AssetJoinError(f"{what}: required non-empty str 'slug', got {slug!r}")
    return slug


def _as_space(space: Any, *, what: str) -> VectorSpace:
    if isinstance(space, VectorSpace):
        return space
    if isinstance(space, Mapping):
        try:
            return VectorSpace(
                provider=space["provider"],
                model=space["model"],
                dim=space["dim"],
                task_type=space.get("task_type", ""),
                preprocessing_version=space.get("preprocessing_version", "v1"),
            )
        except KeyError as exc:
            raise AssetJoinError(f"{what}: space missing {exc}") from exc
    raise AssetJoinError(
        f"{what}: space must be VectorSpace or mapping, got {type(space).__name__}"
    )


def index_asset_rows(rows: Any) -> dict:
    """Index central-asset rows by exact (slug, content version).

    Raises :class:`DuplicateAssetError` on two rows sharing one key and
    :class:`InvalidVectorError` on a fake/corrupt/zero-norm row that ships
    with a space (deferred rows carry no vector and validate at use).
    """
    try:
        items = list(rows)
    except TypeError:
        raise AssetJoinError(f"rows: required iterable, got {type(rows).__name__}")
    index: dict[tuple[str, str], dict] = {}
    for i, row in enumerate(items):
        what = f"asset row {i}"
        if not isinstance(row, Mapping):
            raise AssetJoinError(f"{what}: required mapping, got {type(row).__name__}")
        slug = _need_slug(row, what=what)
        ver = row.get("content_version")
        if not isinstance(ver, str) or not ver:
            raise AssetJoinError(
                f"{what}: required non-empty str 'content_version', got {ver!r}"
            )
        key = (slug, ver)
        if key in index:
            raise DuplicateAssetError(f"{what}: duplicate asset key {key!r}")
        space = row.get("space")
        vector = row.get("vector")
        if space is not None and vector is not None:
            aspace = _as_space(space, what=what)
            require_valid_vector(vector, expected_dim=aspace.dim, what=f"{what} vector")
        index[key] = dict(row)
    return index


def join_roles(
    roles: Any, asset_index: Mapping, *, default_content_version: Any = None
) -> JoinResult:
    """Join local role rows to the central asset by exact (slug, version).

    Hits carry both dicts; misses carry a reason (``no-asset-row`` covers a
    version bump — install the newer asset, never fuzzy-match) and stay
    pool-eligible through :func:`build_pool`. Duplicate role slugs and
    slugless rows raise; a versionless row is a miss, not an error.
    """
    try:
        items = list(roles)
    except TypeError:
        raise AssetJoinError(f"roles: required iterable, got {type(roles).__name__}")
    if not isinstance(asset_index, Mapping):
        raise AssetJoinError("asset_index: required mapping from index_asset_rows()")
    hits: dict[str, dict] = {}
    misses: list[dict] = []
    seen: set[str] = set()
    for i, role in enumerate(items):
        what = f"role {i}"
        if not isinstance(role, Mapping):
            raise AssetJoinError(f"{what}: required mapping, got {type(role).__name__}")
        slug = _need_slug(role, what=what)
        if slug in seen:
            raise AssetJoinError(f"{what}: duplicate role slug {slug!r}")
        seen.add(slug)
        ver = role.get("content_version", default_content_version)
        if not isinstance(ver, str) or not ver:
            misses.append({"slug": slug, "reason": "missing-content-version"})
            continue
        asset = asset_index.get((slug, ver))
        if asset is None:
            misses.append({"slug": slug, "reason": "no-asset-row"})
            continue
        hits[slug] = {"role": dict(role), "asset": asset}
    return JoinResult(hits=hits, misses=misses)


def plan_delta_embeds(
    roles: Any, *, provisioned: Mapping, shared_slugs: Any = ()
) -> dict:
    """Plan delta-only embedding after a role-library import or converge.

    ``provisioned`` maps slug -> already-installed content version.
    ``shared_slugs`` holds slugs owned by the central asset. Returns
    ``{"embed": [...], "skip": [...]}``; embed entries are scoped
    ``tenant-local``. Shared roles always skip — unchanged or not — so a
    rerun over unchanged shared roles plans zero embedding calls
    (role-library-import regression lock). A tenant-origin role shadowing a
    shared slug raises :class:`SharedRoleEmbedError`; unknown origins raise.
    This function lists; it never embeds.
    """
    try:
        items = list(roles)
    except TypeError:
        raise AssetJoinError(f"roles: required iterable, got {type(roles).__name__}")
    if not isinstance(provisioned, Mapping):
        raise AssetJoinError("provisioned: required slug->version mapping")
    try:
        shared = set(shared_slugs)
    except TypeError:
        raise AssetJoinError("shared_slugs: required iterable of slugs")
    embed: list[dict] = []
    skip: list[dict] = []
    for i, role in enumerate(items):
        what = f"role {i}"
        if not isinstance(role, Mapping):
            raise AssetJoinError(f"{what}: required mapping, got {type(role).__name__}")
        slug = _need_slug(role, what=what)
        origin = role.get("origin", SHARED)
        if origin != SHARED and origin not in _TENANT_ORIGINS:
            raise AssetJoinError(f"{what}: unknown origin {origin!r}")
        if origin == SHARED or slug in shared:
            if slug in shared and origin != SHARED:
                raise SharedRoleEmbedError(
                    f"{what}: slug {slug!r} is a shared-asset slug; "
                    "tenant-local material must not shadow it"
                )
            skip.append({"slug": slug, "reason": "shared-asset"})
            continue
        ver = role.get("content_version")
        if not isinstance(ver, str) or not ver:
            raise AssetJoinError(
                f"{what}: tenant-local role needs non-empty str "
                f"'content_version', got {ver!r}"
            )
        if provisioned.get(slug) == ver:
            skip.append({"slug": slug, "reason": "unchanged"})
        else:
            embed.append(
                {"slug": slug, "content_version": ver, "scope": "tenant-local"}
            )
    return {"embed": embed, "skip": skip}


def build_pool(
    joined: JoinResult,
    *,
    query_vector: Any,
    query_space: Any,
    lexical_scores: Any = None,
    asset_space: Any = None,
) -> list:
    """Build one ranked candidate pool from a :func:`join_roles` result.

    Hits score by D21-guarded cosine (``checked_cosine`` — cross-space reuse
    and corrupt rows raise). Misses stay in the pool as ``lexical`` entries
    with caller-supplied scores (default 0.0), so deferred/missing vectors
    never disappear. Sorted by score desc, slug asc.
    """
    if not isinstance(joined, JoinResult):
        raise AssetJoinError("joined: required JoinResult from join_roles()")
    qspace = _as_space(query_space, what="query_space")
    require_valid_vector(query_vector, expected_dim=qspace.dim, what="query vector")
    lex = dict(lexical_scores) if lexical_scores is not None else {}
    if not isinstance(lex, dict):
        raise AssetJoinError("lexical_scores: required mapping slug->number")
    pool: list[PoolEntry] = []
    for slug, hit in joined.hits.items():
        asset = hit["asset"]
        raw_space = asset.get("space", asset_space)
        if raw_space is None:
            raise AssetJoinError(f"hit {slug!r}: no asset space and no asset_space")
        if "vector" not in asset or asset["vector"] is None:
            raise AssetJoinError(f"hit {slug!r}: asset row carries no vector")
        aspace = _as_space(raw_space, what=f"asset space for {slug!r}")
        score = checked_cosine(query_vector, qspace, asset["vector"], aspace)
        pool.append(PoolEntry(slug=slug, mode="vector", score=score))
    for miss in joined.misses:
        slug = miss["slug"]
        score = lex.get(slug, 0.0)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise AssetJoinError(
                f"lexical score for {slug!r}: required number, got {score!r}"
            )
        if not math.isfinite(score):
            raise AssetJoinError(
                f"lexical score for {slug!r}: non-finite {score!r}"
            )
        pool.append(PoolEntry(slug=slug, mode="lexical", score=float(score)))
    # ponytail: single score-desc sort mixes cosine (-1..1) with the caller
    # lexical scale; split vector-first ranking when scales prove incomparable.
    pool.sort(key=lambda e: (-e.score, e.slug))
    return pool
