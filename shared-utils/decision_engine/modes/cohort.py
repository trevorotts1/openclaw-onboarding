#!/usr/bin/env python3
"""D34 cross-repo release-cohort validator (JEV spec 1.1, ss 14.8/17.2-17.4).

Pure helpers over a release-cohort manifest tying the tested ONB + CC
SHAs/versions (14.8). No git, no network, no disk, no environment. Stdlib
only (copy). Caller supplies the manifest dict and the candidate SHAs;
exact string equality is the only match — a changed SHA invalidates
approval (A50/A53), never fuzzy-matches.

Pairing semantics (14.8):
  * new CC + old ONB: no-JEV fallback preserved, truthful capability state.
  * new ONB + old CC: compatible legacy output, no required new fields.
  * new + new: full tested contract only after capability/version
    handshake on the EXACT tested pair.
  * anything untested: compatible fallback, never activation.
"""

from __future__ import annotations

import copy

PAIR_NEW_NEW = "new_new"
PAIR_NEW_OLD = "new_old"
PAIR_OLD_NEW = "old_new"
PAIRINGS = (PAIR_NEW_NEW, PAIR_NEW_OLD, PAIR_OLD_NEW)

BEHAVIOR_FULL_CONTRACT = "full_contract"
BEHAVIOR_COMPAT_FALLBACK = "compat_fallback"

CAPABILITY_READY = "decision_ready"
CAPABILITY_CORE_INCOMPATIBLE = "core_unavailable_incompatible"
CAPABILITY_NOT_CONFIGURED = "jev_not_configured"

__all__ = [
    "BEHAVIOR_COMPAT_FALLBACK",
    "BEHAVIOR_FULL_CONTRACT",
    "CAPABILITY_CORE_INCOMPATIBLE",
    "CAPABILITY_NOT_CONFIGURED",
    "CAPABILITY_READY",
    "PAIRINGS",
    "PAIR_NEW_NEW",
    "PAIR_NEW_OLD",
    "PAIR_OLD_NEW",
    "check_rollback_compat",
    "evaluate_pairing",
    "is_hex_sha",
    "validate_cohort",
]


def is_hex_sha(value):
    """40-char lowercase hex git SHA. Exact shape only."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower() and all(
        c in "0123456789abcdef" for c in value)


def validate_cohort(manifest):
    """Check a release-cohort manifest. Returns (ok, errors list).

    Required keys: onb_sha, cc_sha (exact 40-hex), onb_version,
    cc_version, contract (non-empty strings). Unknown extra keys are
    preserved, never rejected (additive contracts, 14.8/17.2).
    """
    errors = []
    if not isinstance(manifest, dict):
        return False, ["manifest must be a dict"]
    for key in ("onb_sha", "cc_sha"):
        if not is_hex_sha(manifest.get(key)):
            errors.append("bad %s: must be exact 40-char hex SHA" % key)
    for key in ("onb_version", "cc_version", "contract"):
        val = manifest.get(key)
        if not isinstance(val, str) or not val:
            errors.append("bad %s: must be a non-empty string" % key)
    return (len(errors) == 0), errors


def evaluate_pairing(*, pairing, onb_sha, cc_sha, tested_pairs,
                     handshake_ok=False):
    """Decide behavior for one repo pairing against tested exact pairs.

    ``tested_pairs`` is an iterable of (onb_sha, cc_sha) exact tuples from
    the cohort manifest. Returns a dict with behavior + capability +
    reason. Full contract requires pairing new_new AND exact tested match
    AND handshake_ok; every other case is compat fallback with a typed
    reason. A half-promoted pair never activates (A53).
    """
    if pairing not in PAIRINGS:
        raise ValueError("unknown pairing: %r (expected one of %r)"
                         % (pairing, PAIRINGS))
    tested = set()
    for entry in tested_pairs or ():
        try:
            tested.add((str(entry[0]), str(entry[1])))
        except (TypeError, IndexError):
            raise ValueError("tested_pairs entries must be (onb, cc) pairs")
    exact = (str(onb_sha), str(cc_sha)) in tested
    if pairing == PAIR_NEW_NEW and exact and bool(handshake_ok):
        return {"behavior": BEHAVIOR_FULL_CONTRACT,
                "capability": CAPABILITY_READY,
                "reason": "exact_tested_pair_handshake_ok",
                "exact_match": True}
    if pairing == PAIR_NEW_NEW and exact:
        reason = "handshake_failed"
    elif pairing == PAIR_NEW_NEW:
        reason = "untested_pair"
    elif pairing == PAIR_NEW_OLD:
        reason = "old_command_center_legacy_output"
    else:
        reason = "old_onboarding_no_jev_fallback"
    return {"behavior": BEHAVIOR_COMPAT_FALLBACK,
            "capability": CAPABILITY_CORE_INCOMPATIBLE
            if pairing == PAIR_OLD_NEW else CAPABILITY_NOT_CONFIGURED
            if pairing == PAIR_NEW_OLD else CAPABILITY_CORE_INCOMPATIBLE,
            "reason": reason, "exact_match": exact}


def _major(version):
    if not isinstance(version, str) or not version:
        return None
    head = version.strip().split(".")[0]
    return head if head.isdigit() else None


def check_rollback_compat(current_version, target_version):
    """Schema gate for a release-code rollback (17.4).

    Same major: compatible (old-compatible fields retained). Different
    or unparsable major: incompatible — rollback must prove owner +
    execution compatibility separately, not force through. Returns
    (compatible_bool, reason).
    """
    cur = _major(current_version)
    tgt = _major(target_version)
    if cur is None or tgt is None:
        return False, "unparsable_version"
    if cur == tgt:
        return True, "same_major"
    return False, "major_change_requires_compat_proof"


def cohort_summary(manifest):
    """Small copy-safe summary for evidence records. No secrets exist here."""
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a dict")
    out = copy.deepcopy(manifest)
    return {"onb_sha": out.get("onb_sha"), "cc_sha": out.get("cc_sha"),
            "onb_version": out.get("onb_version"),
            "cc_version": out.get("cc_version"),
            "contract": out.get("contract")}
