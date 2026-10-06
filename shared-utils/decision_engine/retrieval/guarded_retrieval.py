#!/usr/bin/env python3
"""Guarded persona retrieval — A32's four fault classes yield a TRUTHFUL
FALLBACK (unit REP-032, JEV spec 1.1 ss 9.3 + A32).

`cache_identity` refuses: it raises on a mismatched space, a corrupt/fake
vector, or a zero norm. A refusal is a correct detector but it is not a
fallback — probe case 6b showed the two failure halves of A32:

  * a stale index with an identical declared space is served silently
    (the declared-space gate cannot see it), and
  * a refusal raised into a caller with no fallback path is a hard stop,
    not a fallback, and its provenance never reaches the answer.

This module is the disposition layer: it composes the SAME `cache_identity`
gates, but a rejected row is DEMOTED to the lexical path instead of aborting
the retrieval, and the rejection reason is carried into the result. The caller
therefore never gets a silent success, never gets a crash, and never gets a
result that claims a path which did not produce it.

Truthfulness rules enforced here:
  * A row that fails a gate is never scored and never silently dropped: it
    appears in the pool as a lexical entry with its reason attached.
  * ``served_path`` describes the WHOLE answer: ``semantic`` only when every
    candidate scored on the vector path, ``lexical`` when the index is stale
    (all candidates), ``semantic-partial`` when some rows were demoted,
    ``unknown-unverified`` when no freshness verdict could be read.
  * A stale index short-circuits BEFORE scoring, so a stale vector can never
    contribute a cosine to a served answer.

Stdlib only. No network, no provider keys, no writes.
"""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple

try:  # packaged layout
    from .cache_identity import (
        VectorSpace,
        spaces_compatible,
        space_mismatch_reason,
        validate_vector,
    )
    from .freshness import check_index_freshness
except ImportError:  # direct file load (unit tests / probes): load siblings by path
    import importlib.util as _ilu
    import sys as _sys
    from pathlib import Path as _Path

    def _sibling(name):
        p = _Path(__file__).with_name(name)
        spec = _ilu.spec_from_file_location(f"rep032_{name[:-3]}_sib", p)
        mod = _ilu.module_from_spec(spec)
        _sys.modules[f"rep032_{name[:-3]}_sib"] = mod
        spec.loader.exec_module(mod)
        return mod

    _ci = _sibling("cache_identity.py")
    _fr = _sibling("freshness.py")
    VectorSpace = _ci.VectorSpace
    spaces_compatible = _ci.spaces_compatible
    space_mismatch_reason = _ci.space_mismatch_reason
    validate_vector = _ci.validate_vector
    check_index_freshness = _fr.check_index_freshness

__version__ = "1.0.0"
__all__ = ["GuardedEntry", "GuardedRetrieval", "guarded_persona_retrieval"]

SERVED_SEMANTIC = "semantic"
SERVED_LEXICAL = "lexical"
SERVED_PARTIAL = "semantic-partial"
SERVED_UNVERIFIED = "unknown-unverified"


class GuardedEntry(NamedTuple):
    slug: str
    mode: str  # "vector" | "lexical"
    score: float
    reason: str  # why this path produced this score — never empty


class GuardedRetrieval(NamedTuple):
    entries: list  # ranked GuardedEntry, score desc then slug asc
    served_path: str  # what actually produced the answer
    freshness_status: str
    freshness_reason: str
    demotions: dict  # slug -> rejection reason, for every demoted row
    counts: dict


def _as_space(space: Any, *, what: str) -> VectorSpace:
    # Duck-typed on purpose: a caller may hand over a VectorSpace from a
    # separately-loaded copy of cache_identity (CLI wrapper, probe, or a
    # worktree that loaded the file by path), and isinstance would then be
    # False for an object that is field-for-field identical.
    if all(hasattr(space, f) for f in ("provider", "model", "dim")):
        return VectorSpace(
            provider=space.provider,
            model=space.model,
            dim=space.dim,
            task_type=getattr(space, "task_type", ""),
            preprocessing_version=getattr(space, "preprocessing_version", "v1"),
        )
    if isinstance(space, Mapping):
        return VectorSpace(
            provider=space["provider"],
            model=space["model"],
            dim=space["dim"],
            task_type=space.get("task_type", ""),
            preprocessing_version=space.get("preprocessing_version", "v1"),
        )
    raise TypeError(f"{what}: space must be a vector-space or mapping")


def _plain(vec: Any) -> list:
    """numpy float32 -> python float.

    ``cache_identity.validate_vector`` tests ``isinstance(v, float)``, and
    ``isinstance(np.float32(1.0), float)`` is False — a real numpy index row
    handed over unconverted would be rejected as corrupt. Convert at this
    boundary; the gate's own strictness is not relaxed.
    """
    return [float(v) for v in vec]


def guarded_persona_retrieval(
    candidates: Any,
    *,
    query_vector: Any,
    query_space: Any,
    index_dir: Any = None,
    categories_path: Any = None,
    lexical_scores: Any = None,
) -> GuardedRetrieval:
    """Rank caller-supplied candidates, demoting every rejected row to lexical.

    ``candidates`` is an iterable of ``{"slug", "space", "vector"}`` mappings
    (an index's rows as the caller read them). ``index_dir``/``categories_path``
    feed :func:`freshness.check_index_freshness`. Never raises on a bad row:
    a row that fails any gate lands in ``entries`` as a lexical entry whose
    ``reason`` names the gate that rejected it. A malformed input (non-mapping
    row, non-finite query) still raises — that is a caller bug, not a fault
    class, and A32 is about data faults.
    """
    qspace = _as_space(query_space, what="query_space")
    lex = dict(lexical_scores) if lexical_scores is not None else {}
    try:
        rows = list(candidates)
    except TypeError:
        raise TypeError(f"candidates: required iterable, got {type(candidates).__name__}")

    verdict = check_index_freshness(index_dir, categories_path)
    demotions: dict[str, str] = {}
    entries: list[GuardedEntry] = []

    stale = verdict.status == "stale"
    if stale:
        for row in rows:
            slug = row.get("slug") if isinstance(row, Mapping) else None
            if slug is None:
                continue
            demotions[slug] = f"stale-index: {verdict.reason}"
            entries.append(GuardedEntry(slug, "lexical",
                                        float(lex.get(slug, 0.0)),
                                        "stale-index (index is not current)"))
        served = SERVED_LEXICAL
    else:
        try:
            q_ok, q_reason = validate_vector(_plain(query_vector),
                                             expected_dim=qspace.dim)
        except TypeError:
            q_ok, q_reason = False, "query vector is not a sequence"
        for row in rows:
            if not isinstance(row, Mapping):
                raise TypeError(f"candidate row: required mapping, got {type(row).__name__}")
            slug = row.get("slug")
            if not isinstance(slug, str) or not slug:
                raise ValueError(f"candidate row: required non-empty 'slug', got {slug!r}")
            reason = ""
            if not q_ok:
                reason = f"query rejected: {q_reason}"
            else:
                row_space = row.get("space")
                row_vec = row.get("vector")
                if row_space is None or row_vec is None:
                    reason = "row carries no space/vector (unembedded or deferred)"
                else:
                    rspace = _as_space(row_space, what=f"space for {slug!r}")
                    if not spaces_compatible(qspace, rspace):
                        reason = ("incompatible vector space: "
                                  + space_mismatch_reason(qspace, rspace))
                    else:
                        ok, why = validate_vector(_plain(row_vec),
                                                  expected_dim=rspace.dim)
                        if not ok:
                            reason = f"invalid vector: {why}"
            if reason:
                demotions[slug] = reason
                entries.append(GuardedEntry(slug, "lexical",
                                            float(lex.get(slug, 0.0)), reason))
                continue
            rspace = _as_space(row["space"], what=f"space for {slug!r}")
            qa, ra = _plain(query_vector), _plain(row["vector"])
            dot = sum(x * y for x, y in zip(qa, ra))
            import math
            na = math.sqrt(sum(x * x for x in qa))
            nb = math.sqrt(sum(y * y for y in ra))
            entries.append(GuardedEntry(slug, "vector", dot / (na * nb),
                                        "scored on the vector path"))

        modes = {e.mode for e in entries}
        if modes == {"vector"}:
            served = SERVED_SEMANTIC
        elif modes == {"lexical"}:
            served = SERVED_LEXICAL
        elif modes:
            served = SERVED_PARTIAL
        else:
            served = SERVED_LEXICAL
        if verdict.status == "unknown" and served != SERVED_LEXICAL:
            served = SERVED_UNVERIFIED

    entries.sort(key=lambda e: (-e.score, e.slug))
    counts = {
        "vector": sum(1 for e in entries if e.mode == "vector"),
        "lexical": sum(1 for e in entries if e.mode == "lexical"),
    }
    return GuardedRetrieval(
        entries=entries,
        served_path=served,
        freshness_status=verdict.status,
        freshness_reason=verdict.reason,
        demotions=demotions,
        counts=counts,
    )
