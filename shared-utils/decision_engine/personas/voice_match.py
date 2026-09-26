#!/usr/bin/env python3
"""D18 voice matching (JEV spec 1.1, ss 8.2/8.3/8.4; extends D16, feeds D17).

Ranks voice candidates against explicit audience needs with deterministic
lexical-overlap scoring (stdlib only — no model calls, no network, no state
writes). Consumes the D16 audience foundation (``resolve_audience`` priority:
explicit > prior-confirmed > company-proposal > clarify; stop re-asking once
the owner answered) — it extends, never replaces, that ordering: matching
runs on the resolved audience, and a match never invents confirmation. D17
``five_layer.py`` scores the selected voice downstream; emitted
``evidence_refs`` satisfy the D16 profile shape (validated in tests via the
REAL ``evidence_profiles.make_profile`` — D16 types imported, never
redefined here).

Spec 8.3: voice never chosen from demographic stereotypes. Demographic
tokens (gender/age/ethnicity words) are INERT — stripped before any overlap
is measured, so a demographic word alone can never change a ranking;
documented suitability evidence is the required discriminator (every
candidate must carry non-empty ``suitability_evidence``).

Spec 8.2: matching applies to audience-facing work only; callers gate with
D16 ``assess_blend_applicability`` first (this module never re-decides
blend). Spec 8.4: retrieval unions evidence — scoring reads needs tags,
context tags, brand tags, AND suitability text together, never one
stale filter alone.

Builders raise ValueError on bad input (empty candidates, malformed
candidate, signal-free audience, zero overlap across the field) — never a
silent rank-everything default. Inputs never mutated (assignment-read-only).

ponytail: scoring is lexical overlap, ceiling is vocabulary coverage;
upgrade path is embedding similarity behind the same match-dict schema
(no API change).
"""

from __future__ import annotations

import re
from pathlib import Path

# Provenance basis values for one match.
BASIS_VALUES = ("needs", "context", "brand", "suitability")

# Spec 8.3: demographic words are INERT — stripped before overlap, so they
# can never move a ranking. Gender, age, and ethnicity words only; nothing
# that doubles as a legitimate needs/context/brand term.
DEMOGRAPHIC_TOKENS = frozenset({
    # gender
    "woman", "women", "man", "men", "male", "female", "girl", "boy",
    "girls", "boys", "lady", "ladies", "gentleman", "gentlemen",
    # age
    "young", "old", "youth", "youthful", "elderly", "senior", "seniors",
    "teen", "teens", "teenage", "teenager", "millennial", "millennials",
    "genz", "gen-z", "boomer", "boomers", "middle-aged",
    # ethnicity
    "asian", "black", "white", "latino", "latina", "latinx", "hispanic",
    "african", "european", "caucasian", "arab", "middle-eastern",
})

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
    "is", "are", "be", "by", "at", "as", "it", "this", "that", "from",
    "into", "over", "than", "then", "so", "such", "no", "not", "only",
    "own", "same", "too", "very", "can", "will", "just", "up", "out",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Per-basis overlap weights (deterministic; documented, not tuned).
_BASIS_WEIGHTS = {"needs": 3, "context": 2, "brand": 2, "suitability": 3}
# Tie order when two bases contribute equal weighted overlap.
_BASIS_TIE_ORDER = ("needs", "context", "brand", "suitability")


def _load_d16():
    """Return the REAL D16 evidence_profiles module (file-location load).

    Mirrors the five_layer.py offline test convention: works whether this
    file is imported as a package or loaded standalone. D16 types are
    imported — never redefined (no duplicate dataclasses).
    """
    import importlib.util
    import sys
    here = Path(__file__).resolve()
    personas_dir = here.parent
    mod_name = "d18_evidence"
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        mod_name, personas_dir / "evidence_profiles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_ep = _load_d16()

# D16 types, re-exported — never redefined here.
PersonaEvidenceProfile = _ep.PersonaEvidenceProfile
CONFIDENCE_LEVELS = _ep.CONFIDENCE_LEVELS

__all__ = [
    "BASIS_VALUES",
    "DEMOGRAPHIC_TOKENS",
    "PersonaEvidenceProfile",
    "CONFIDENCE_LEVELS",
    "semantic_voice_match",
    "select_voice",
]


def _tokens(value) -> set[str]:
    """Lexical tokens minus stopwords minus INERT demographic tokens."""
    if isinstance(value, str):
        parts = [value]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return set()
    out: set[str] = set()
    for part in parts:
        if not isinstance(part, str):
            continue
        for tok in _TOKEN_RE.findall(part.lower()):
            if tok and tok not in _STOPWORDS and tok not in DEMOGRAPHIC_TOKENS:
                out.add(tok)
    return out


def _as_text_list(value, field: str, *, required: bool) -> list[str]:
    """Validate a str-or-list-of-str field. Raises ValueError on bad input."""
    if value is None:
        if required:
            raise ValueError(f"{field}: required non-empty evidence")
        return []
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, (list, tuple)) or not items:
        if required:
            raise ValueError(f"{field}: required non-empty list of non-empty strings")
        if not isinstance(items, (list, tuple)):
            raise ValueError(f"{field}: must be a string or list of strings")
        return []
    clean = []
    for entry in items:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError(f"{field}: every entry must be a non-empty string")
        clean.append(entry.strip())
    return clean


def _parse_audience(audience_needs) -> dict[str, set[str]]:
    """Split audience signal into per-basis token sets. Raises ValueError."""
    if isinstance(audience_needs, str):
        audience_needs = {"needs": audience_needs}
    if not isinstance(audience_needs, dict):
        raise ValueError("audience_needs must be a string or an object")
    unknown = set(audience_needs) - {"needs", "context", "brand_prefs"}
    if unknown:
        raise ValueError(
            f"audience_needs: unknown field(s) {sorted(unknown)} "
            "(needs/context/brand_prefs/documented only)"
        )
    parsed = {
        "needs": _tokens(_as_text_list(audience_needs.get("needs"), "needs", required=False)),
        "context": _tokens(_as_text_list(audience_needs.get("context"), "context", required=False)),
        "brand": _tokens(_as_text_list(audience_needs.get("brand_prefs"), "brand", required=False)),
    }
    if not any(parsed.values()):
        raise ValueError(
            "audience_needs carries no usable signal "
            "(needs/context/brand preferences/documented only — "
            "demographic words alone are inert, not signal)"
        )
    return parsed


def _normalize_candidate(candidate, index: int) -> dict:
    """Validate one candidate into normalized token sets. Raises ValueError."""
    where = f"voice_candidates[{index}]"
    if not isinstance(candidate, dict):
        raise ValueError(f"{where}: required object")
    cid = candidate.get("candidate_id")
    if not isinstance(cid, str) or not cid.strip():
        raise ValueError(f"{where}.candidate_id: required non-empty string")
    unknown = set(candidate) - {
        "candidate_id", "needs_tags", "context_tags", "brand_tags",
        "suitability", "suitability_evidence",
    }
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
    needs_tags = _as_text_list(candidate.get("needs_tags"), f"{where}.needs_tags", required=False)
    context_tags = _as_text_list(candidate.get("context_tags"), f"{where}.context_tags", required=False)
    brand_tags = _as_text_list(candidate.get("brand_tags"), f"{where}.brand_tags", required=False)
    suitability = candidate.get("suitability", "")
    if suitability is not None and not isinstance(suitability, str):
        raise ValueError(f"{where}.suitability: must be a string")
    evidence = _as_text_list(
        candidate.get("suitability_evidence"),
        f"{where}.suitability_evidence", required=True,
    )
    return {
        "candidate_id": cid.strip(),
        "needs_tokens": _tokens(needs_tags),
        "context_tokens": _tokens(context_tags),
        "brand_tokens": _tokens(brand_tags),
        "suitability_tokens": _tokens(suitability or ""),
        "suitability_evidence": evidence,
    }


def _score_one(audience: dict[str, set[str]], cand: dict) -> dict:
    """Score one normalized candidate. Pure function; inputs untouched."""
    audience_all = audience["needs"] | audience["context"] | audience["brand"]
    overlaps = {
        "needs": audience["needs"] & cand["needs_tokens"],
        "context": audience["context"] & cand["context_tokens"],
        "brand": audience["brand"] & cand["brand_tokens"],
        "suitability": audience_all & cand["suitability_tokens"],
    }
    weighted = {b: _BASIS_WEIGHTS[b] * len(toks) for b, toks in overlaps.items()}
    score = sum(weighted.values())
    best = max(weighted.values())
    basis = next(b for b in _BASIS_TIE_ORDER if weighted[b] == best)
    refs: list[str] = []
    for b in BASIS_VALUES:
        refs.extend(f"{b}:{t}" for t in sorted(overlaps[b]))
    refs.extend(cand["suitability_evidence"])
    return {
        "candidate_id": cand["candidate_id"],
        "score": score,
        "basis": basis,
        "basis_scores": dict(weighted),
        "evidence_refs": refs,
    }


def semantic_voice_match(audience_needs, voice_candidates, *, top_n=None) -> list[dict]:
    """Rank voice candidates by audience-signal overlap. Raises ValueError.

    ``audience_needs`` is a string (explicit needs) or an object with
    ``needs``/``context``/``brand_prefs`` (each a string or list of
    strings). ``voice_candidates`` is a non-empty list of candidate objects
    (``candidate_id`` + ``needs_tags``/``context_tags``/``brand_tags`` +
    ``suitability`` text + required ``suitability_evidence`` refs).

    Returns matches sorted score-descending, candidate-id-ascending ties,
    each ``{candidate_id, score, basis, basis_scores, evidence_refs}`` where
    ``basis`` names the strongest provenance (needs|context|brand|
    suitability) and ``evidence_refs`` feeds D16 evidence shapes. Raises
    ValueError on empty candidates (never rank-everything), malformed
    candidates, signal-free audience, or zero overlap across the field
    (no documented basis — never a demographic guess).
    """
    if not isinstance(voice_candidates, list) or not voice_candidates:
        raise ValueError("voice_candidates must be a non-empty list (fail-closed: never rank-everything)")
    if top_n is not None and (not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1):
        raise ValueError("top_n must be a positive int or None")
    audience = _parse_audience(audience_needs)
    scored = [
        _score_one(audience, _normalize_candidate(c, i))
        for i, c in enumerate(voice_candidates)
    ]
    if max(s["score"] for s in scored) <= 0:
        raise ValueError(
            "no candidate shares needs/context/brand/suitability overlap "
            "with the audience — documented suitability required, "
            "demographic words alone are inert (fail-closed)"
        )
    scored.sort(key=lambda s: (-s["score"], s["candidate_id"]))
    return scored[:top_n] if top_n is not None else scored


def select_voice(audience_needs, voice_candidates) -> dict:
    """Return the single best voice match. Raises ValueError (never guesses).

    Same input contract and fail-closed rules as ``semantic_voice_match``;
    returns the top-ranked match dict (deterministic; ties break by
    candidate id ascending).
    """
    return semantic_voice_match(audience_needs, voice_candidates, top_n=1)[0]
