#!/usr/bin/env python3
"""D34 explicit mode preservation + revision fencing (JEV spec 1.1, ss 3.6/17.4).

Canonical ONB home for configured-mode semantics. Reuses the D23
single-writer fence (commit.py ``check_fence``) — this module never owns a
store, lock, budget, or clock. Every function here is pure: caller-supplied
dicts in, new dicts out. Stdlib only (copy). No network, no disk, no
environment reads, no key material.

Spec rules encoded:
  * 3.6: explicit client off/legacy/shadow survives install/update; a
    release default applies only with no explicit override. off/legacy
    share the SAME improved no-JEV engine; both emit ZERO JEV/probe
    traffic. shadow's authoritative decision is no-JEV; JEV is sampled
    comparison only and can never commit.
  * 3.6/10.3: a mode/policy change fences uncommitted recommendations
    from the old revision; committed decisions and running snapshots are
    never rewritten by a fence or a rollback.
  * 17.4: rollback is ``mode=off`` on the installed version (not a
    downgrade to pre-project routing); uncommitted JEV/shadow/probe work
    is fenced, history retained.
  * A59/A63: unapproved auto reports the true no-JEV effective path;
    denial reasons stay typed (never "missing credentials").
"""

from __future__ import annotations

import copy

# Mirrors D02 CONFIGURED_MODE_ENUM (contracts/schema.py). Parity is locked
# by test; this module stays import-standalone for the offline convention.
MODES = ("auto", "shadow", "legacy", "off")

# Effective-path values. "jev" means the ladder may attempt eligible JEV
# routes; provider choice among them stays the ladder's job (D07).
EFFECTIVE_JEV = "jev"
EFFECTIVE_NO_JEV = "no_jev"

# Typed skip reasons mirror D07 ladder SKIP_* values.
REASON_MODE_OFF = "mode_off"
REASON_MODE_LEGACY = "mode_legacy"
REASON_MODE_SHADOW = "mode_shadow_authoritative_no_jev"
REASON_NOT_AUTHORIZED = "not_authorized"
REASON_DATA_NOT_PERMITTED = "data_not_permitted"
REASON_ELIGIBLE = "eligible"

# Diagnostic-only labels stripped before off/legacy equivalence compare
# (A62: identical inputs/policy must yield equivalent normalized decisions
# apart from mode/diagnostic labels).
_NORMALIZED_STRIP_KEYS = frozenset({
    "configuredMode",
    "configured_mode",
    "mode",
    "effectivePath",
    "effective_path",
    "skipReason",
    "skip_reason",
    "diagnostics",
})

__all__ = [
    "EFFECTIVE_JEV",
    "EFFECTIVE_NO_JEV",
    "MODES",
    "ShadowCommitError",
    "bump_fence",
    "fence_reason",
    "is_fenced",
    "jev_traffic_permitted",
    "normalize_no_jev",
    "decisions_equivalent",
    "preserve_explicit_mode",
    "refuse_shadow_commit",
    "resolve_effective_path",
    "rollback_to_off",
    "shadow_dedup_key",
    "shadow_sample_allowed",
]


class ShadowCommitError(Exception):
    """A shadow recommendation was offered as an assignment. Always refused."""

    def __init__(self, detail="shadow results are diagnostic only"):
        super().__init__("shadow commit refused: %s" % (detail,))


def _check_mode(mode):
    if mode not in MODES:
        raise ValueError("unknown mode: %r (expected one of %r)"
                         % (mode, MODES))
    return mode


def preserve_explicit_mode(release_default, stored_mode=None,
                           stored_explicit=False):
    """Install/update mode merge. Explicit client setting always wins.

    ``release_default`` (usually "auto") applies only when there is no
    stored mode or the stored one is not an explicit operator choice.
    Returns the mode to persist. Raises ValueError on an unknown mode in
    either slot — a corrupt config fails loudly, never silently resets.
    """
    _check_mode(release_default)
    if stored_mode is None:
        return release_default
    _check_mode(stored_mode)
    if stored_explicit:
        return stored_mode
    return release_default


def resolve_effective_path(mode, *, spend_ok, transmit_ok):
    """Honest configured-vs-effective path (A59/A63).

    legacy/off always resolve to no-JEV. shadow resolves authoritative
    no-JEV (samples are diagnostic, never assignments). auto resolves to
    JEV-eligible only when BOTH spend and transmit permission hold;
    otherwise the true no-JEV path with the typed denial reason — never
    "JEV active", never mislabeled missing credentials.
    """
    _check_mode(mode)
    spend = bool(spend_ok)
    transmit = bool(transmit_ok)
    if mode == "off":
        return {"configured_mode": mode, "effective_path": EFFECTIVE_NO_JEV,
                "reason": REASON_MODE_OFF}
    if mode == "legacy":
        return {"configured_mode": mode, "effective_path": EFFECTIVE_NO_JEV,
                "reason": REASON_MODE_LEGACY}
    if mode == "shadow":
        return {"configured_mode": mode, "effective_path": EFFECTIVE_NO_JEV,
                "reason": REASON_MODE_SHADOW}
    if not spend:
        return {"configured_mode": mode, "effective_path": EFFECTIVE_NO_JEV,
                "reason": REASON_NOT_AUTHORIZED}
    if not transmit:
        return {"configured_mode": mode, "effective_path": EFFECTIVE_NO_JEV,
                "reason": REASON_DATA_NOT_PERMITTED}
    return {"configured_mode": mode, "effective_path": EFFECTIVE_JEV,
            "reason": REASON_ELIGIBLE}


def jev_traffic_permitted(mode, *, sampled=False):
    """Whether JEV evaluation/probe traffic may be sent at all.

    legacy/off: never. shadow: sampled comparison only (authoritative
    sends always False). auto: eligible-route attempts only — the ladder
    still gates each send on credentials, permission, budget, deadline.
    """
    _check_mode(mode)
    if mode in ("legacy", "off"):
        return False
    if mode == "shadow":
        return bool(sampled)
    return True


def normalize_no_jev(decision):
    """Strip mode/diagnostic labels for off/legacy equivalence (A62)."""
    if not isinstance(decision, dict):
        raise ValueError("decision must be a dict")
    return {k: copy.deepcopy(v) for k, v in decision.items()
            if k not in _NORMALIZED_STRIP_KEYS}


def normalized_key(decision):
    """Hashable normalized form for dedup/equality without label noise."""
    norm = normalize_no_jev(decision)
    return repr(sorted(norm.items(), key=lambda kv: kv[0]))


def decisions_equivalent(first, second):
    """True when two no-JEV decisions match apart from mode labels."""
    return normalized_key(first) == normalized_key(second)


def bump_fence(fence, *, mode_changed=False, policy_changed=False):
    """New fence dict with bumped generations. Pure; D23 store unaffected.

    The caller writes the result into the D23 store fence (under its lock);
    old ``issue_fence_token`` snapshots then fail ``check_fence`` with the
    matching FencedError — the single-writer fence stays the one authority.
    """
    if not isinstance(fence, dict):
        raise ValueError("fence must be a dict")
    out = copy.deepcopy(fence)
    out["mode_revision"] = int(out.get("mode_revision", 0)) + (
        1 if mode_changed else 0)
    out["policy_revision"] = int(out.get("policy_revision", 0)) + (
        1 if policy_changed else 0)
    return out


def fence_reason(token, fence, *, now_s=None):
    """Pure twin of D23 ``check_fence``: None when valid, else the reason.

    ``root_expired`` / ``mode_changed`` / ``policy_changed`` — same strings
    D23 raises as FencedError reasons. Deadline needs an explicit ``now_s``;
    omitted means "do not evaluate expiry here" (D23 store remains the
    expiry authority via its own clock).
    """
    if not isinstance(token, dict) or not isinstance(fence, dict):
        raise ValueError("token and fence must both be dicts")
    deadline = fence.get("deadline_s")
    if deadline is not None and now_s is not None:
        if float(now_s) > float(deadline):
            return "root_expired"
    if token.get("mode_revision") != fence.get("mode_revision"):
        return "mode_changed"
    if token.get("policy_revision") != fence.get("policy_revision"):
        return "policy_changed"
    return None


def is_fenced(token, fence, *, now_s=None):
    """True when an uncommitted recommendation is invalidated."""
    return fence_reason(token, fence, now_s=now_s) is not None


def rollback_to_off(config, fence):
    """17.4 rollback: installed version, mode off, fence bumped.

    Returns ``(new_config, new_fence, previous_mode)`` as fresh copies.
    Only the mode label changes; policy, budgets, catalog versions, and —
    by construction, untouched — every committed decision, bundle, and
    running snapshot stay exactly as they were.
    """
    if not isinstance(config, dict) or not isinstance(fence, dict):
        raise ValueError("config and fence must both be dicts")
    previous = config.get("mode", "auto")
    _check_mode(previous)
    new_config = copy.deepcopy(config)
    new_config["mode"] = "off"
    new_config["previous_mode"] = previous
    return new_config, bump_fence(fence, mode_changed=True), previous


def refuse_shadow_commit(result=None):
    """Shadow results can never become assignments (A61/A63). Always raises."""
    raise ShadowCommitError()


def shadow_dedup_key(*, company, scope, input_hash, stage,
                     candidate_version, policy_version, model_version, epoch):
    """Stable sample identity (3.9). A repeated sweep is not another sample.

    Pure string key over company, scope, input, stage, candidate/policy/
    model versions, and sample epoch. Empty epoch component never collides
    with a real one (epoch is required).
    """
    parts = [company, scope, input_hash, stage, candidate_version,
             policy_version, model_version, epoch]
    if any(p is None or (isinstance(p, str) and not p) for p in parts):
        raise ValueError("all dedup components required, got %r" % (parts,))
    return "shadow:" + "|".join(str(p) for p in parts)


def shadow_sample_allowed(*, sample_rate, draw, quota_remaining,
                          in_flight, max_in_flight, permission_ok,
                          deadline_ms=None):
    """Pure sample gate predicate (3.9). Reads caller-owned quota numbers.

    This is NOT a budget engine: quotas live with existing accounting
    (D07/D30); here only the admission decision. ``draw`` is the caller's
    [0,1) draw for ``sample_rate``. ``deadline_ms`` is the evaluation's own
    remaining allowance (spec 3.6 ``evaluation_deadline_ms``); omit it when
    the caller holds no evaluation clock — a supplied deadline that has run
    out denies with ``deadline_expired`` and the sample skips with that
    recorded reason, exactly like the other typed denials. Returns
    ``(allowed, reason)`` with typed reasons; any denial skips with a
    recorded reason, never a retry.
    """
    try:
        rate = float(sample_rate)
    except (TypeError, ValueError):
        return False, "bad_sample_rate"
    if not 0.0 <= rate <= 1.0:
        return False, "bad_sample_rate"
    if not bool(permission_ok):
        return False, "not_authorized"
    try:
        remaining = int(quota_remaining)
    except (TypeError, ValueError):
        return False, "quota_exhausted"
    if remaining <= 0:
        return False, "quota_exhausted"
    try:
        flying = int(in_flight)
        cap = int(max_in_flight)
    except (TypeError, ValueError):
        return False, "in_flight_capped"
    if flying >= cap:
        return False, "in_flight_capped"
    if deadline_ms is not None:
        try:
            left = float(deadline_ms)
        except (TypeError, ValueError):
            return False, "deadline_expired"
        if left <= 0.0:
            return False, "deadline_expired"
    try:
        draw_f = float(draw)
    except (TypeError, ValueError):
        return False, "not_sampled"
    if not 0.0 <= draw_f < 1.0:
        return False, "not_sampled"
    if draw_f >= rate:
        return False, "not_sampled"
    return True, "sampled"
