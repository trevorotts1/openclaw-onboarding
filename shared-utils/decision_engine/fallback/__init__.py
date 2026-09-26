#!/usr/bin/env python3
"""D08 no-JEV fallback selection (JEV spec 1.1, ss 3.6/4.5/9.8).

Assignment-only, read-only lexical/rule/catalog selection for the four
caller-supplied skip reasons: jev_unavailable, not_authorized,
data_not_permitted, budget_exhausted. Stdlib only. Reads caller-supplied
data, writes nothing, calls nothing, needs no keys.

Contract:
  * Caller supplies everything: catalog, query, configured mode, skip
    reason, policy/config revisions, and optionally a client-approved
    ``fallback_model`` name. No ``fallback_model`` means pure rule
    ranking; its presence only annotates the result (noted, never
    invoked, never needs a credential).
  * Ranking is mode-independent: ``legacy`` and ``off`` return
    byte-identical normalized decisions; only mode/diagnostic labels
    differ (spec 3.6: same engine, operational intent differs).
  * This module never emits JEV/probe/shadow traffic: counters stay 0
    in every mode, including ``legacy``/``off``.
  * Validators return ``(ok, errors)`` and never raise; ``select`` and
    ``route_capability`` raise ValueError on bad input (never a silent
    guess).
"""

from __future__ import annotations

import copy
import json
import re

POLICY_VERSION = "decision-policy-v1"
DEFAULT_CONFIG_REVISION = "cfgrev-1"

CONFIGURED_MODES = ("auto", "shadow", "legacy", "off")
SKIP_REASONS = (
    "jev_unavailable",
    "not_authorized",
    "data_not_permitted",
    "budget_exhausted",
)

EFFECTIVE_PATH_NOJEV = "non_jev"
EFFECTIVE_PATH_JEV = "jev"

# Spec 9.8 capability-combination catalog.
PATH_JEV_HYBRID = "jev_hybrid"  # JEV + embeddings: hybrid retrieval -> JEV
PATH_JEV_LEXICAL = "jev_lexical"  # JEV, no embeddings: catalog + lexical -> JEV
PATH_NOJEV_SEMANTIC = "nojev_semantic"  # no JEV + embeddings: semantic + rules
PATH_NOJEV_CATALOG_RULE = "nojev_catalog_rule"  # neither: catalog/lexical/rule

# Labels stripped by normalized_decision (mode/diagnostic only).
_LABEL_FIELDS = ("configuredMode", "skipReason")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _is_nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def route_capability(jev_available: bool, embeddings_available: bool) -> str:
    """Map the spec 9.8 capability combination to its expected path."""
    if not isinstance(jev_available, bool) or not isinstance(
        embeddings_available, bool
    ):
        raise ValueError(
            "jev_available/embeddings_available must be bool, got "
            f"{jev_available!r}/{embeddings_available!r}"
        )
    if jev_available:
        return PATH_JEV_HYBRID if embeddings_available else PATH_JEV_LEXICAL
    return PATH_NOJEV_SEMANTIC if embeddings_available else PATH_NOJEV_CATALOG_RULE


def validate_config(config) -> tuple[bool, list[str]]:
    """Validate caller config. Returns ``(ok, errors)``; never raises.

    No key is required: ``{}`` is valid (defaults apply). A
    ``fallback_model`` name, when present, needs no credential.
    """
    try:
        if not isinstance(config, dict):
            return False, [f"config is not an object (got {type(config).__name__})"]
        errors: list[str] = []
        if "configuredMode" in config and config["configuredMode"] not in CONFIGURED_MODES:
            errors.append(
                f"'configuredMode': {config['configuredMode']!r} "
                f"not in {list(CONFIGURED_MODES)}"
            )
        for key in ("policy_version", "configRevision"):
            if key in config and not _is_nonempty_str(config[key]):
                errors.append(f"{key!r}: required non-empty string, got {config[key]!r}")
        if "fallback_model" in config and config["fallback_model"] is not None:
            if not _is_nonempty_str(config["fallback_model"]):
                errors.append(
                    "'fallback_model': required non-empty string or null, "
                    f"got {config['fallback_model']!r}"
                )
        if "skip_reason" in config and config["skip_reason"] is not None:
            if config["skip_reason"] not in SKIP_REASONS:
                errors.append(
                    f"'skip_reason': {config['skip_reason']!r} "
                    f"not in {list(SKIP_REASONS)}"
                )
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def validate_catalog(catalog) -> tuple[bool, list[str]]:
    """Validate a caller-supplied candidate catalog. Never raises."""
    try:
        if not isinstance(catalog, list):
            return False, [f"catalog is not a list (got {type(catalog).__name__})"]
        errors: list[str] = []
        seen: set[str] = set()
        for i, cand in enumerate(catalog):
            if not isinstance(cand, dict):
                errors.append(f"catalog[{i}]: required object")
                continue
            cid = cand.get("id")
            if not _is_nonempty_str(cid):
                errors.append(f"catalog[{i}].id: required non-empty string")
            elif cid in seen:
                errors.append(f"catalog[{i}].id: duplicate id {cid!r}")
            else:
                seen.add(cid)
            text = cand.get("text", "")
            if text is not None and not isinstance(text, str):
                errors.append(f"catalog[{i}].text: required string or null")
            topics = cand.get("topics", [])
            if topics is not None and (
                not isinstance(topics, list)
                or any(not isinstance(t, str) for t in topics)
            ):
                errors.append(f"catalog[{i}].topics: required string list or null")
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def _lexical_rank(entries: list[dict], query: str) -> list[dict]:
    """Deterministic overlap rank. Pure function; inputs untouched."""
    qset = set(_TOKEN_RE.findall(query.lower()))
    ranked = []
    for pos, entry in enumerate(entries):
        hay = entry["text"] + " " + " ".join(entry["topics"])
        overlap = len(qset & set(_TOKEN_RE.findall(hay.lower())))
        score = (overlap / len(qset)) if qset else 0.0
        ranked.append({"id": entry["id"], "score": score, "overlap": overlap})
    ranked.sort(key=lambda r: -r["score"])  # stable: ties keep catalog order
    return ranked


def select(
    catalog: list,
    query: str,
    config: dict | None = None,
    *,
    jev_available: bool = False,
    embeddings_available: bool = False,
    skip_reason: str | None = "jev_unavailable",
) -> dict:
    """Read-only no-JEV assignment over a caller-supplied catalog.

    Never mutates ``catalog``/``config``. Ranking depends only on catalog
    content + query (mode-independent); mode/skip reason surface as labels.
    Counters ``jevCalls``/``probeCalls``/``shadowRemoteCalls`` are always 0:
    the fallback emits no JEV/probe/shadow traffic in any mode.
    """
    ok, errs = validate_catalog(catalog)
    if not ok:
        raise ValueError(f"invalid catalog: {errs}")
    if not _is_nonempty_str(query):
        raise ValueError(f"query: required non-empty string, got {query!r}")
    cfg = {} if config is None else config
    ok, errs = validate_config(cfg)
    if not ok:
        raise ValueError(f"invalid config: {errs}")
    if not isinstance(jev_available, bool) or not isinstance(
        embeddings_available, bool
    ):
        raise ValueError("jev_available/embeddings_available must be bool")
    if jev_available:
        if skip_reason is not None:
            raise ValueError("skip_reason must be None when JEV is available")
    elif skip_reason not in SKIP_REASONS:
        raise ValueError(
            f"skip_reason {skip_reason!r} not in {list(SKIP_REASONS)}"
        )

    mode = cfg.get("configuredMode", "auto")
    policy_version = cfg.get("policy_version", POLICY_VERSION)
    config_revision = cfg.get("configRevision", DEFAULT_CONFIG_REVISION)
    fallback_model = cfg.get("fallback_model")

    entries = [
        {
            "id": c["id"],
            "text": c.get("text") or "",
            "topics": list(c.get("topics") or []),
        }
        for c in catalog
    ]
    ranking = _lexical_rank(entries, query)
    selected = ranking[0]["id"] if ranking else None

    capability_path = route_capability(jev_available, embeddings_available)
    reason_codes = ["nojev_lexical_rule_rank"]
    if not ranking:
        reason_codes.append("empty_catalog_truthful_fallback")
    elif ranking[0]["score"] == 0.0:
        reason_codes.append("zero_overlap_truthful_rank")
    if fallback_model is not None:
        reason_codes.append("caller_fallback_model_noted")

    evidence = [
        {
            "source": "catalog",
            "detail": f"{len(entries)} candidate(s) read-only, catalog order kept",
        },
    ]
    if ranking:
        evidence.append(
            {
                "source": "lexical",
                "detail": (
                    f"winner {selected!r}: {ranking[0]['overlap']} "
                    "overlapping token(s)"
                ),
            }
        )

    return {
        "configuredMode": mode,
        "effectivePath": EFFECTIVE_PATH_JEV if jev_available else EFFECTIVE_PATH_NOJEV,
        "capabilityPath": capability_path,
        "policyVersion": policy_version,
        "configRevision": config_revision,
        "skipReason": skip_reason,
        "jevCalls": 0,
        "probeCalls": 0,
        "shadowRemoteCalls": 0,
        "catalogSize": len(entries),
        "selectedId": selected,
        "ranking": ranking,
        "retrievalEvidence": evidence,
        "reasonCodes": reason_codes,
        "fallbackModelUsed": fallback_model,
    }


def normalized_decision(result: dict) -> dict:
    """Copy of ``result`` minus mode/diagnostic labels.

    Byte-identical normalized decisions across ``legacy``/``off`` prove the
    shared-engine rule (spec 3.6).
    """
    out = copy.deepcopy(result)
    for key in _LABEL_FIELDS:
        out.pop(key, None)
    return out


def canonical_result_json(result: dict) -> str:
    """Deterministic canonical JSON: sorted keys, compact separators."""
    return (
        json.dumps(
            copy.deepcopy(result),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )
