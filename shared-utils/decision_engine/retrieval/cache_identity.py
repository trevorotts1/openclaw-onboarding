#!/usr/bin/env python3
"""JEV 1.1 section 9 — vector-cache identity + single-flight (unit JEV-021).

Implements spec 9.3 (vector-space compatibility), 9.5 (cache identity /
invalidation), and 9.6 (single-flight query reuse + requested-vs-unique
counters). Additive module: does not touch ``embedding_engine.py`` or
``semantic_task_fit.py``; wiring lands in later units.

Stdlib only (``threading`` allowed). No network, no provider access, no live
DB, no global mutable state — every cache is an explicit instance.

Rules enforced here:
  * Six cache-key builders, one per 9.5 table row. Keys are ``sha256`` digests
    over canonical field JSON, so raw request/company text is never retained
    in a key or a process map.
  * Vector-space gate (9.3): same dimension alone never implies compatibility.
    provider, model, dim, and preprocessing version must match exactly; task
    types must match except the one legitimate pair below. Fake (wrong-dim),
    corrupt (non-finite / non-numeric), wrong-version, and zero-norm rows are
    rejected and never cached.
  * Single-flight (9.6): one in-flight ``embed_fn`` call per key serves all
    concurrent waiters via a per-key event. No global embedding lock is held
    while embedding, so unrelated keys never serialize. A failed embed costs
    exactly one attempt shared by all waiters (never one retry per waiter);
    failures are never cached as values.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, NamedTuple, Optional

__version__ = "1.0.0"
__all__ = [
    "IncompatibleVectorSpaceError",
    "InvalidVectorError",
    "VectorSpace",
    "spaces_compatible",
    "space_mismatch_reason",
    "require_compatible",
    "validate_vector",
    "require_valid_vector",
    "checked_cosine",
    "shared_doc_key",
    "department_key",
    "query_key",
    "alignment_evidence_key",
    "same_task_decision_key",
    "provider_health_key",
    "BoundedCache",
    "QueryEmbeddingCache",
]

_KEY_NS = "jev1"
_KEY_VERSION = "v1"


class IncompatibleVectorSpaceError(ValueError):
    """Two vector spaces must not be compared or reused (spec 9.3/9.6)."""


class InvalidVectorError(ValueError):
    """A vector row is fake/corrupt/wrong-dim/zero-norm and unusable."""


class VectorSpace(NamedTuple):
    """Identity of one vector space (spec 9.3)."""

    provider: str  # e.g. "gemini" | "openai" — never compare across these
    model: str  # exact model slug, e.g. "gemini-embedding-2"
    dim: int  # pinned output dimensionality (3072 / 1536)
    task_type: str = ""  # e.g. "retrieval_query" | "retrieval_document"
    preprocessing_version: str = "v1"


# The single legitimate cross-task-type comparison: the query/document pair
# produced by the same model for retrieval. Anything else (classification vs
# retrieval, etc.) is a different space even at equal dims.
_QUERY_DOC_PAIR = frozenset({"retrieval_query", "retrieval_document"})


def _task_types_compatible(a: str, b: str) -> bool:
    la, lb = a.lower(), b.lower()
    if la == lb:
        return True
    return {la, lb} == _QUERY_DOC_PAIR


def spaces_compatible(a: VectorSpace, b: VectorSpace) -> bool:
    """True only if two spaces may share cosine similarity (spec 9.3)."""
    return (
        a.provider == b.provider
        and a.model == b.model
        and a.dim == b.dim
        and a.preprocessing_version == b.preprocessing_version
        and _task_types_compatible(a.task_type, b.task_type)
    )


def space_mismatch_reason(a: VectorSpace, b: VectorSpace) -> str:
    """First field that makes two spaces incompatible (for error messages)."""
    if a.provider != b.provider:
        return f"provider {a.provider!r} != {b.provider!r} (never reuse across providers)"
    if a.model != b.model:
        return f"model {a.model!r} != {b.model!r} (wrong-version vectors are garbage)"
    if a.dim != b.dim:
        return f"dim {a.dim!r} != {b.dim!r} (same dim alone never implies compatibility)"
    if a.preprocessing_version != b.preprocessing_version:
        return (
            f"preprocessing {a.preprocessing_version!r} != {b.preprocessing_version!r}"
        )
    if not _task_types_compatible(a.task_type, b.task_type):
        return f"task_type {a.task_type!r} != {b.task_type!r}"
    return "compatible"


def require_compatible(a: VectorSpace, b: VectorSpace, *, what: str = "vector use") -> None:
    """Fail-closed gate: raise unless two spaces may be compared/reused."""
    if not spaces_compatible(a, b):
        raise IncompatibleVectorSpaceError(
            f"{what}: incompatible vector spaces: {space_mismatch_reason(a, b)}"
        )


def validate_vector(vec: Any, *, expected_dim: int) -> tuple[bool, str]:
    """Check one vector row. Returns ``(ok, reason)``; never raises.

    Rejects: missing rows, wrong-dim rows (fake / wrong-version), non-numeric
    or non-finite entries (corrupt), and zero-norm rows (cosine undefined).
    """
    if vec is None:
        return False, "vector is None (missing row)"
    if isinstance(vec, (bytes, bytearray, str)):
        return False, f"vector has non-numeric container type {type(vec).__name__}"
    try:
        vals = list(vec)
    except TypeError:
        return False, f"vector is not a sequence (got {type(vec).__name__})"
    if len(vals) != expected_dim:
        return (
            False,
            f"vector is {len(vals)}-dim, expected {expected_dim}-dim "
            "(fake / wrong-version row; refuse, never persist)",
        )
    norm_sq = 0.0
    for i, v in enumerate(vals):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False, f"vector[{i}] is not a number (got {type(v).__name__})"
        f = float(v)
        if not math.isfinite(f):
            return False, f"vector[{i}] is non-finite ({v!r}; corrupt row)"
        norm_sq += f * f
    if norm_sq == 0.0:
        return False, "zero-norm vector (no direction; cosine undefined)"
    return True, "ok"


def require_valid_vector(vec: Any, *, expected_dim: int, what: str = "vector") -> None:
    """Fail-closed gate: raise unless a vector row is real and usable."""
    ok, reason = validate_vector(vec, expected_dim=expected_dim)
    if not ok:
        raise InvalidVectorError(f"{what}: rejected: {reason}")


def checked_cosine(
    a: Any, space_a: VectorSpace, b: Any, space_b: VectorSpace
) -> float:
    """Cosine similarity after the 9.3 gates. Raises on any rejection."""
    require_compatible(space_a, space_b, what="cosine similarity")
    require_valid_vector(a, expected_dim=space_a.dim, what="left vector")
    require_valid_vector(b, expected_dim=space_b.dim, what="right vector")
    la = [float(v) for v in a]
    lb = [float(v) for v in b]
    dot = sum(x * y for x, y in zip(la, lb))
    na = math.sqrt(sum(x * x for x in la))
    nb = math.sqrt(sum(y * y for y in lb))
    return dot / (na * nb)  # norms nonzero: require_valid_vector proved it


# ---------------------------------------------------------------------------
# Cache keys (spec 9.5). One builder per table row; every builder hashes its
# canonical fields so unbounded request text never lands in a process map.
# ---------------------------------------------------------------------------


def _canon(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(fields: dict) -> str:
    return hashlib.sha256(_canon(fields).encode("utf-8")).hexdigest()


def _key(kind: str, fields: dict) -> str:
    return f"{_KEY_NS}.{kind}.{_KEY_VERSION}.{_digest(fields)}"


def _need_str(name: str, v: Any) -> str:
    if not isinstance(v, str) or not v:
        raise ValueError(f"{name}: required non-empty string, got {v!r}")
    return v


def _need_dim(dim: Any) -> int:
    if isinstance(dim, bool) or not isinstance(dim, int) or dim <= 0:
        raise ValueError(f"dim: required int > 0, got {dim!r}")
    return dim


def _need_revision(name: str, v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ValueError(f"{name}: required int >= 0, got {v!r}")
    return v


def shared_doc_key(
    *,
    content_hash: str,
    provider: str,
    model: str,
    dim: int,
    preprocessing_version: str,
    asset_generation: str,
) -> str:
    """Shared persona/SOP document vectors: source-content hash, embedding
    provider/model/dimensions/preprocessing version, asset generation."""
    return _key(
        "shared-doc",
        {
            "content_hash": _need_str("content_hash", content_hash),
            "provider": _need_str("provider", provider),
            "model": _need_str("model", model),
            "dim": _need_dim(dim),
            "preprocessing_version": _need_str(
                "preprocessing_version", preprocessing_version
            ),
            "asset_generation": _need_str("asset_generation", asset_generation),
        },
    )


def department_key(
    *,
    company: str,
    department: str,
    name: str,
    purpose: str,
    keywords: list | tuple,
    content_hash: str,
    provider: str,
    model: str,
    dim: int,
) -> str:
    """Client department vectors: company, department, effective
    name/purpose/keywords/content hash, provider/model/dimensions."""
    if not isinstance(keywords, (list, tuple)) or any(
        not isinstance(k, str) for k in keywords
    ):
        raise ValueError(f"keywords: required list of strings, got {keywords!r}")
    effective_hash = _digest(
        {
            "name": _need_str("name", name),
            "purpose": _need_str("purpose", purpose),
            "keywords": list(keywords),
            "content_hash": _need_str("content_hash", content_hash),
        }
    )
    return _key(
        "dept",
        {
            "company": _need_str("company", company),
            "department": _need_str("department", department),
            "effective_hash": effective_hash,
            "provider": _need_str("provider", provider),
            "model": _need_str("model", model),
            "dim": _need_dim(dim),
        },
    )


def query_key(
    *,
    company: str,
    query_text: str,
    purpose: str,
    provider: str,
    model: str,
    dim: int,
) -> str:
    """Query vectors: company/privacy boundary, exact effective query text
    hash, retrieval purpose/task type, provider/model/dimensions. The raw
    text is hashed and never appears in the key."""
    if not isinstance(query_text, str) or not query_text.strip():
        raise ValueError("query_text: required non-empty effective text")
    return _key(
        "query",
        {
            "company": _need_str("company", company),
            "text_hash": hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
            "purpose": _need_str("purpose", purpose),
            "provider": _need_str("provider", provider),
            "model": _need_str("model", model),
            "dim": _need_dim(dim),
        },
    )


def alignment_evidence_key(
    *,
    company: str,
    mission_version: str,
    values_version: str,
    persona_content_hash: str,
    rubric_version: str,
    model_version: str,
) -> str:
    """Static persona alignment evidence: company mission/value versions,
    persona content hash, rubric/model versions."""
    return _key(
        "align",
        {
            "company": _need_str("company", company),
            "mission_version": _need_str("mission_version", mission_version),
            "values_version": _need_str("values_version", values_version),
            "persona_content_hash": _need_str(
                "persona_content_hash", persona_content_hash
            ),
            "rubric_version": _need_str("rubric_version", rubric_version),
            "model_version": _need_str("model_version", model_version),
        },
    )


def same_task_decision_key(
    *,
    task_id: str,
    scope_id: str,
    input_revision: int,
    preferences_hash: str,
    audience_version: str,
    sop_version: str,
    catalog_version: str,
    policy_version: str,
    model_version: str,
) -> str:
    """Same-task decision: task/scope/input revision, explicit preferences,
    audience/SOP/catalog/policy/model versions."""
    return _key(
        "task",
        {
            "task_id": _need_str("task_id", task_id),
            "scope_id": _need_str("scope_id", scope_id),
            "input_revision": _need_revision("input_revision", input_revision),
            "preferences_hash": _need_str("preferences_hash", preferences_hash),
            "audience_version": _need_str("audience_version", audience_version),
            "sop_version": _need_str("sop_version", sop_version),
            "catalog_version": _need_str("catalog_version", catalog_version),
            "policy_version": _need_str("policy_version", policy_version),
            "model_version": _need_str("model_version", model_version),
        },
    )


def provider_health_key(
    *,
    company: str,
    provider: str,
    credential_version: str,
    config_version: str,
) -> str:
    """Provider health/circuit: company and provider plus non-secret
    credential/config version. Never pass secret material here — versions
    only, so key rotation invalidates without leaking."""
    return _key(
        "health",
        {
            "company": _need_str("company", company),
            "provider": _need_str("provider", provider),
            "credential_version": _need_str(
                "credential_version", credential_version
            ),
            "config_version": _need_str("config_version", config_version),
        },
    )


# ---------------------------------------------------------------------------
# Bounded LRU/TTL cache (spec 9.5: bounded, never unbounded request text).
# ---------------------------------------------------------------------------


class BoundedCache:
    """Thread-safe bounded LRU map with TTL expiry."""

    def __init__(self, *, maxsize: int = 512, ttl_s: float = 300.0):
        if isinstance(maxsize, bool) or not isinstance(maxsize, int) or maxsize <= 0:
            raise ValueError(f"maxsize: required int > 0, got {maxsize!r}")
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)) or ttl_s <= 0:
            raise ValueError(f"ttl_s: required number > 0, got {ttl_s!r}")
        self._maxsize = maxsize
        self._ttl = float(ttl_s)
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._items[key]
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = (time.monotonic() + self._ttl, value)
            while len(self._items) > self._maxsize:
                self._items.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._items),
                "maxsize": self._maxsize,
                "ttl_s": self._ttl,
                "hits": self.hits,
                "misses": self.misses,
            }


class _Inflight:
    __slots__ = ("event", "vector", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.vector: Any = None
        self.error: Optional[BaseException] = None


class QueryEmbeddingCache:
    """Per-key single-flight query-embedding cache (spec 9.5/9.6).

    Identity comes from :func:`query_key` (company + text hash + purpose +
    provider/model/dim). One in-flight ``embed_fn`` call per key serves all
    concurrent waiters; the lock is never held while embedding, so unrelated
    keys never serialize behind each other. A failed embed costs exactly one
    attempt shared by every waiter and is never cached as a value. Cache hits
    whose stored space differs from the requested space are refused loudly
    instead of reused (never cross-provider).
    """

    def __init__(
        self,
        *,
        maxsize: int = 512,
        ttl_s: float = 300.0,
        failure_cooldown_s: float = 0.0,
        wait_timeout_s: float = 60.0,
    ):
        self._cache = BoundedCache(maxsize=maxsize, ttl_s=ttl_s)
        # ponytail: in-memory only; swap BoundedCache for durable cache infra
        # when persistence needed. Failure latch is per-key cooldown, not a
        # cross-key shared circuit; add one when failure storms observed.
        self._latch = (
            BoundedCache(maxsize=maxsize, ttl_s=failure_cooldown_s)
            if failure_cooldown_s > 0
            else None
        )
        if not isinstance(wait_timeout_s, (int, float)) or wait_timeout_s <= 0:
            raise ValueError(
                f"wait_timeout_s: required number > 0, got {wait_timeout_s!r}"
            )
        self._wait_timeout = float(wait_timeout_s)
        self._lock = threading.Lock()
        self._inflight: dict[str, _Inflight] = {}
        self._requested = 0
        self._unique = 0

    @property
    def counters(self) -> dict:
        """Requested (every caller) vs unique (real ``embed_fn`` calls)."""
        with self._lock:
            return {"requested": self._requested, "unique": self._unique}

    def cache_stats(self) -> dict:
        return self._cache.stats()

    def embed(
        self,
        *,
        key: str,
        space: VectorSpace,
        embed_fn: Callable[[], Any],
        index_space: Optional[VectorSpace] = None,
    ) -> Any:
        """Return the query vector for ``key``, embedding at most once.

        Raises :class:`IncompatibleVectorSpaceError` without spending an
        embed call when ``space`` is incompatible with ``index_space`` or a
        cached vector's space differs. Raises :class:`InvalidVectorError`
        (shared by all waiters, uncached) when ``embed_fn`` returns a
        fake/corrupt/zero-norm row.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"key: required non-empty string, got {key!r}")
        if index_space is not None:
            # Fail fast before spending an embed call (9.6: never reuse an
            # OpenAI query vector against a Gemini document index).
            require_compatible(space, index_space, what="query-vs-index")
        with self._lock:
            self._requested += 1
            hit = self._cache.get(key)
            if hit is not None:
                stored_space, vector = hit
                if stored_space != space:
                    raise IncompatibleVectorSpaceError(
                        f"cached query vector for key refused: stored space "
                        f"{stored_space!r} != requested {space!r}"
                    )
                return vector
            inflight = self._inflight.get(key)
            if inflight is None:
                if self._latch is not None:
                    latched = self._latch.get(key)
                    if latched is not None:
                        raise latched
                inflight = _Inflight()
                self._inflight[key] = inflight
                leader = True
                self._unique += 1
            else:
                leader = False
        if not leader:
            if not inflight.event.wait(self._wait_timeout):
                raise TimeoutError(f"single-flight wait timed out for key {key!r}")
            if inflight.error is not None:
                raise inflight.error
            return inflight.vector
        try:
            vector = embed_fn()
        except Exception as exc:  # single shared failure, no per-waiter retry
            with self._lock:
                if self._latch is not None:
                    self._latch.set(key, exc)
                inflight.error = exc
                inflight.event.set()
                del self._inflight[key]
            raise
        try:
            require_valid_vector(vector, expected_dim=space.dim, what="embed_fn result")
        except InvalidVectorError as exc:
            with self._lock:
                if self._latch is not None:
                    self._latch.set(key, exc)
                inflight.error = exc
                inflight.event.set()
                del self._inflight[key]
            raise
        with self._lock:
            self._cache.set(key, (space, vector))
            inflight.vector = vector
            inflight.event.set()
            del self._inflight[key]
        return vector
