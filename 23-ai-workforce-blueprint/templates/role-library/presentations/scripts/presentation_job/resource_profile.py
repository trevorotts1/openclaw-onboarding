#!/usr/bin/env python3
"""resource_profile.py -- THE per-client resource profile (FIX 8, presentation rev2).

WHAT THIS IS
------------
The single persistent record of which providers/plans/models A CLIENT has,
how much they can run at once, and what they have consented to. FIX 9's
provider probes, FIX 7's router, FIX 12's credit preflight, FIX 14's judge
and FIX 11's modes all consume THIS; its schema lands before every consumer.

WHY IT EXISTS
-------------
Before this module there was no persistent record of which providers,
plans and models a client has. capacity.py detects capacity per-run from
configuration, but never stores the richer account picture (wired models,
creative prefs, consent flags), and the plan-tier answer for a provider
whose concurrency cannot be detected (Ollama Cloud $20 vs $100) lived only
in a per-run override file. A client's account facts deserve one durable,
never-printed home.

THE STORE (binding)
-------------------
`resource_profile.json` lives SECRETS-ADJACENT -- `~/.openclaw/state/
presentation/` (sibling of `~/.openclaw/secrets/` -- openclaw-owned state,
NEVER in-repo, NEVER printed). It is never written into the department
tree by default: a git leak of the repo must not also leak the client's
account picture. Overridable, in order: explicit `config_dir=` argument
(tests, probes), $PRESENTATION_RESOURCE_PROFILE_DIR, then
$PRESENTATION_CAPACITY_CONFIG_DIR (when the operator already points
capacity at a directory, the profile follows it). Its content names
providers and plan tiers, never credential values (see REDACTION).

SCHEMA (version 1)
------------------
{
  ".schema_version": 1,
  "profile_version": "<uuid-ish timestamp token>",
  "updated_at": "<ISO8601>",
  "created_at": "<ISO8601>",
  "providers": {
    "<provider-id>": {
      "provider":       "ollama-cloud",
      "plan_tier":      "$100/month" | null,     # non-detectable -> asked ONCE
      "concurrency_ceiling": 10 | "UNBOUNDED" | null,
      "ceiling_source": "cap-table" | "declared" | "interview" | "probe",
      "consented":      true/false,
      "wired_models":   ["deepseek-v4-flash", ...],   # probed (FIX 9)
      "detected":       true/false,
      "plan_known":     true/false,
      "creative_prefs": {...},                        # free-form, redacted
      "notes":          "..."
    }
  },
  "creative_prefs": {...},
  "consent": {"add_models": true/false, ...}
}

FIELD CLASSES
-------------
    DETECTABLE   -- auto-probed on every probe refresh, never asked:
                    provider presence, wired models, detected concurrency.
    NON-DETECTABLE (ask-ONCE) -- ollama-cloud's plan tier ($20 vs $100): no
                    probe can read a price tag, so the intake asks ONCE and
                    the answer is LOCKED: subsequent runs never re-ask
                    (pending_questions() goes empty), and the ceiling is
                    derived from capacity.CAP_TABLE for the life of the lock.
    REFRESHABLE  -- anything a probe can observe is refreshed BY THE PROBE,
                    never by re-interviewing (apply_probe_refresh()).

ASK-ONCE / LOCK-IN CONTRACT
---------------------------
    record_plan_answer(provider, plan)   -- the ONE interview answer;
                                           persists to the profile and LOCKS:
    is_plan_locked(provider)             -- True once an answer is recorded;
    pending_questions(profile/detection) -- [] once locked (asked ONCE,
                                            never again);
    apply_probe_refresh(detection)       -- updates detectable fields WITHOUT
                                           a question and WITHOUT unsettling
                                           a locked plan.

REDACTION CONTRACT (binding -- every exit path)
-----------------------------------------------
No credential value ever leaves this module, and no secret-named key is
ever serialized into the store or into any summary it emits. Every value
that passes through redact_record()/redacted_summary() is filtered by the
SAME secret-key rule capacity.py uses; anything whose key looks like a
credential (api key/token/secret/password/auth/credential/cookie/bearer)
is DROPPED, not masked -- a masked secret still says a secret exists. The
summary emitted for the FIX 30 intake question (`resource_plan`) names
providers and "plan detected/unknown" ONLY. Redaction is per-section and
runs on every write and every read-export; the raw store on disk is
written already-redacted, so a leak of the FILE is not a leak of secrets.

CAPACITY INTEROPERATION
-----------------------
The profile NEVER bypasses capacity.py's doctrine. is_plan_locked() and
intake questions consult capacity.CAP_TABLE; capacity.probe() remains the
dispatch-path authority. FIX 8 adds persistence and the ask-once lock --
it does not move the gate.

Rollout flag
------------
PRESENTATION_RESOURCE_PROFILE=1 (default ON; behavior change per rollback
doctrine). PRESENTATION_RESOURCE_PROFILE=0 is the documented rollback: it
selects the explicitly-documented safe path -- every profile call is a
no-op returning empty structures, no profile file is written, and
capacity.py's existing behavior is untouched. It never silently skips a
gate: with the flag off, profile consumers get {} and MUST fall back to
the existing capacity probe, exactly as before this fix.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Feature flag (rollback path = explicitly-documented safe path)
# ---------------------------------------------------------------------------
FLAG_ENV = "PRESENTATION_RESOURCE_PROFILE"
FLAG_DEFAULT = "1"

DIR_ENV = "PRESENTATION_RESOURCE_PROFILE_DIR"

#: The secrets-adjacent store: under the openclaw state root, sibling of
#: ~/.openclaw/secrets/ -- the same ownership boundary the operator's
#: secrets already live behind. Never inside any repository checkout.
DEFAULT_STORE_DIR = Path.home() / ".openclaw" / "state" / "presentation"


def flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_RESOURCE_PROFILE=0.

    Default ON per the rev2 rollback doctrine. `=0` is the documented
    rollback: profile persistence becomes a no-op (loads return an empty
    profile, saves are refused), and consumers fall back to capacity.py's
    existing per-run detection -- the pre-fix behavior, explicitly."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


# ---------------------------------------------------------------------------
# Paths -- secrets-adjacent, never in-repo
# ---------------------------------------------------------------------------
PROFILE_FILENAME = "resource_profile.json"

# Reuse capacity.py's directory resolution verbatim (one config dir for the
# whole capability: the override file and the profile live side by side, in
# the same $PRESENTATION_CAPACITY_CONFIG_DIR the operator already controls).
try:
    from . import capacity as _capacity  # package-relative (python3 -m)
except ImportError:  # pragma: no cover - direct file run
    try:
        import capacity as _capacity  # direct file run from presentation_job/
    except ImportError:  # standalone import of this module only
        _capacity = None  # type: ignore[assignment]


def department_config_dir() -> Path:
    """The profile's store directory: explicit config_dir= argument (via
    profile_path), then $PRESENTATION_RESOURCE_PROFILE_DIR, then
    $PRESENTATION_CAPACITY_CONFIG_DIR (follow the operator's capacity
    redirect when one exists), then the secrets-adjacent default
    (~/.openclaw/state/presentation/ -- sibling of secrets/, never in-repo)."""
    env = os.environ.get(DIR_ENV)
    if env:
        return Path(env).expanduser()
    if os.environ.get("PRESENTATION_CAPACITY_CONFIG_DIR"):
        if _capacity is not None:
            return _capacity.department_config_dir()
        return Path(os.environ["PRESENTATION_CAPACITY_CONFIG_DIR"]).expanduser()
    return DEFAULT_STORE_DIR


def profile_path(config_dir: Optional[Path] = None) -> Path:
    return Path(config_dir or department_config_dir()) / PROFILE_FILENAME


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 1


def new_profile() -> Dict[str, Any]:
    """An empty, valid profile document."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        ".schema_version": SCHEMA_VERSION,
        "profile_version": now.replace(":", "").replace("-", "").replace("+", "Z"),
        "created_at": now,
        "updated_at": now,
        "providers": {},
        "creative_prefs": {},
        "consent": {},
        "interview": {},
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Redaction contract (per-section, on every write and every read-export)
# ---------------------------------------------------------------------------
_SECRET_KEY_RE = re.compile(
    r"(api[-_]?key|key|token|secret|password|passwd|auth|credential|cookie|bearer)",
    re.IGNORECASE,
)

# Values that, by content alone, look like credential material even under an
# innocuous key: long base64/hex blobs and the sk- family.
_SECRET_VALUE_RE = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{20,}|[A-Fa-f0-9]{40,})\b"
)


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(str(key)))


def redact_record(record: Any) -> Any:
    """Recursively REDACT (drop, never mask) every secret-named key and every
    credential-shaped value. Per-section: applied to the whole document on
    write and to any export (summary, probe payload, intake surface) on read.
    A dropped field leaves no trace that a secret existed."""
    if isinstance(record, dict):
        out = {}
        for key, value in record.items():
            if _is_secret_key(key):
                continue  # dropped, not masked
            out[key] = redact_record(value)
        return out
    if isinstance(record, list):
        return [redact_record(item) for item in record]
    if isinstance(record, str):
        if _SECRET_VALUE_RE.search(record):
            return "[redacted]"
        return record
    return record


def redacted_summary(source: Any, max_providers: int = 8) -> Dict[str, Any]:
    """THE redacted detected summary named in the FIX 30 intake question 10
    (`resource_plan`): "I detected these presentation providers and plans:
    [...]" Names providers, plan tiers and detected/unknown ONLY -- never a
    credential, never an endpoint, never a key-presence claim beyond what
    the intake needs to confirm a tier."""
    raw = source if isinstance(source, dict) else {}
    providers_raw = raw.get("providers") if isinstance(raw.get("providers"), dict) else {}
    summary: Dict[str, Any] = {"providers": []}
    for provider_id, pdef in list(providers_raw.items())[:max_providers]:
        if not isinstance(pdef, dict):
            continue
        summary["providers"].append({
            "provider": pdef.get("provider", provider_id),
            "plan_tier": pdef.get("plan_tier"),
            "plan_known": bool(pdef.get("plan_known")),
            "concurrency_ceiling": pdef.get("concurrency_ceiling"),
            "detected": bool(pdef.get("detected")),
        })
    return redact_record(summary)


# ---------------------------------------------------------------------------
# Store I/O (write-through redaction; atomic; never printed)
# ---------------------------------------------------------------------------
def load_profile(config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load the profile, or an empty valid profile when absent/flag-off/broken.

    Never raises on a broken store's way out of the capability -- a
    corrupt profile is reported in `.error` and behaves like absent, never
    like "no providers configured" dressed up as a real answer."""
    if not flag_enabled():
        return {"error": "flag-disabled", **new_profile()}
    path = profile_path(config_dir)
    if not path.is_file():
        return new_profile()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"error": f"profile unreadable: {exc.__class__.__name__}", **new_profile()}
    if not isinstance(raw, dict):
        return {"error": "profile-not-an-object", **new_profile()}
    return redact_record(raw)


def save_profile(profile: Dict[str, Any],
                 config_dir: Optional[Path] = None) -> Optional[Path]:
    """Redact, then atomically write the profile. Returns the written path.

    Refused (returns None) when the flag is off -- the documented rollback
    selects the no-persistence safe path."""
    if not flag_enabled():
        return None
    cleaned = redact_record(profile)
    cleaned["updated_at"] = _now()
    cleaned.setdefault(".schema_version", SCHEMA_VERSION)
    path = profile_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Provider entries
# ---------------------------------------------------------------------------
def upsert_provider(profile: Dict[str, Any], provider: str, **fields: Any) -> Dict[str, Any]:
    """Create-or-update one provider entry in-place; returns THE ENTRY (never
    the profile dict -- callers mutate the entry through this return value,
    and returning the profile would silently scatter those mutations onto
    the document root instead)."""
    providers = profile.setdefault("providers", {})
    entry = providers.get(provider) or {"provider": provider}
    entry.update(fields)
    providers[provider] = entry
    return entry


def get_provider(profile: Dict[str, Any], provider: str) -> Optional[Dict[str, Any]]:
    entry = (profile.get("providers") or {}).get(provider)
    return entry if isinstance(entry, dict) else None


# ---------------------------------------------------------------------------
# THE ask-once / lock-in contract
# ---------------------------------------------------------------------------
def _normalize(provider: str, plan: str):
    """Delegate normalization to capacity.py so the profile and the cap table
    can never disagree about what a provider/plan id IS."""
    if _capacity is None:
        return provider, plan
    return (_capacity.normalize_provider(provider),
            _capacity.normalize_plan(plan, provider))


def record_plan_answer(provider: str, plan: str,
                       config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """THE one intake answer for the plan-tier question -- persisted ONCE,
    then LOCKED.

    Raises ValueError on a provider/plan pair the cap table does not know --
    an unknown tier is never silently persisted as if it were measured. The
    intake's other choice, "use conservative default", is NOT an answer about
    the account and never reaches this function: pass plan=None through
    record_conservative_default() for that. The gate-side projection is
    written too: capacity.persist_plan_answer() writes capacity_override.json
    (the file dispatch's detection chain reads at step (a)), so the SECOND
    run does not merely skip the question -- it DISPATCHES against the
    locked ceiling. The profile stays the richer store; the override stays
    the gate's projection of it. A NO_CAP_PROVIDERS plan (deepseek-direct's
    v4-pro/v4-flash metadata labels) records into the profile WITHOUT
    writing an override file -- there is no ceiling left to project."""
    norm_provider, norm_plan = _normalize(provider, plan)
    if not norm_provider or not norm_plan:
        raise ValueError(
            f"refusing to record an unknown plan answer (provider={provider!r}, "
            f"plan={plan!r}); normalize to a known pair first")
    # Validation first: a pair NEITHER on the Structural cap table NOR a
    # normalized NO_CAP provider (whose plan labels are metadata per the
    # cap-table doctrine) refuses BEFORE anything is written, so a bad
    # answer never half-lands in the profile.
    structural = bool(_capacity and (norm_provider, norm_plan) in _capacity.CAP_TABLE)
    byok = bool(_capacity and norm_provider in _capacity.NO_CAP_PROVIDERS)
    if not structural and not byok:
        known = sorted(_capacity.CAP_TABLE) if _capacity else []
        raise ValueError(
            f"refusing to record a plan for ({norm_provider!r}, {norm_plan!r}) -- "
            f"not a cap-table row and not a NO_CAP_PROVIDERS entry; known: {known}")
    # The gate-side projection: capacity_override.json (the file dispatch's
    # detection chain reads at step (a)), so the SECOND run does not merely
    # skip the question -- it DISPATCHES against the locked ceiling.
    if structural and _capacity is not None:
        _capacity.persist_plan_answer(norm_provider, norm_plan, config_dir)
    profile = load_profile(config_dir)
    entry = upsert_provider(
        profile, norm_provider,
        plan_tier=norm_plan,
        plan_known=True,
        ceiling_source="interview",
    )
    if _capacity is not None and (norm_provider, norm_plan) in _capacity.CAP_TABLE:
        entry["concurrency_ceiling"] = _capacity.CAP_TABLE[(norm_provider, norm_plan)]
        entry["ceiling_source"] = "cap-table"
    interview = profile.setdefault("interview", {})
    log = interview.setdefault("resource_plan", [])
    # Idempotent ask-once: the FIRST answer decides; later calls with a
    # DIFFERENT answer are appended to the audit log but do NOT unset the
    # lock (re-interviewing is a job for an explicit operator action, never
    # a second intake prompt).
    if not log:
        entry["answered_at"] = _now()
        entry["locked"] = True
    log.append({"provider": norm_provider, "plan": norm_plan, "answered_at": _now()})
    save_profile(profile, config_dir)
    return profile


def record_conservative_default(provider: str,
                                config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The intake question's OTHER choice: "use conservative default."

    Locks the question ask-once exactly like record_plan_answer (the client
    was still asked exactly once) but records a DECLINE, not a tier: the
    ceiling stays None and consumers fall through to capacity.py's existing
    behavior (DEFAULT_CONSERVATIVE when the probe cannot resolve, cap-table
    when it can). Never invents a ceiling the client did not confirm."""
    norm_provider = (_capacity.normalize_provider(provider)
                     if _capacity is not None else provider)
    if not norm_provider:
        raise ValueError(f"refusing to record a decline for an unknown provider "
                         f"(provider={provider!r})")
    profile = load_profile(config_dir)
    entry = upsert_provider(
        profile, norm_provider,
        plan_tier=None,
        plan_known=False,
        concurrency_ceiling=None,
        ceiling_source="conservative-default",
        locked=True,
        locked_choice="use conservative default",
        answered_at=_now(),
    )
    interview = profile.setdefault("interview", {})
    interview.setdefault("resource_plan", []).append(
        {"provider": norm_provider, "plan": None,
         "answered_at": _now(), "choice": "use conservative default"})
    save_profile(profile, config_dir)
    return profile


def is_plan_locked(provider: str, profile: Optional[Dict[str, Any]] = None,
                   config_dir: Optional[Path] = None) -> bool:
    """True once the plan-tier interview answer has been recorded and locked.

    Reads the on-disk profile when none is passed, so this is the one call
    the intake driver makes to decide ask-vs-skip."""
    prof = profile if profile is not None else load_profile(config_dir)
    entry = get_provider(prof, provider)
    return bool(entry and entry.get("locked"))


def pending_questions(profile: Optional[Dict[str, Any]] = None,
                      detection: Optional[Dict[str, Any]] = None,
                      config_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The questions the intake still owes the client.

    THE ask-once contract in one function: a provider whose concurrency
    cannot be detected (known structural-cap-table provider, plan unknown)
    yields exactly one question -- resource_plan -- UNTIL it is answered and
    locked; after record_plan_answer() it is NEVER pending again, whatever
    probes report. Fully detected profiles yield nothing."""
    prof = profile if profile is not None else load_profile(config_dir)
    if prof.get("error") and not prof.get("providers"):
        prof = new_profile()
    pending: List[Dict[str, Any]] = []

    def _needs_plan(provider_id: str) -> bool:
        entry = get_provider(prof, provider_id) or {}
        if entry.get("locked") or entry.get("plan_known"):
            return False  # ASKED ONCE and locked -- never re-asked
        if _capacity is not None:
            norm = _capacity.normalize_provider(provider_id)
            if norm in _capacity.CAP_TABLE_PROVIDERS:
                return True  # structural table: plan is interview-only
            if norm in _capacity.NO_CAP_PROVIDERS:
                return False  # BYOK: no plan-dependent ceiling to ask about
        return False

    # From the stored profile: providers recorded without a known plan
    seen_providers = prof.get("providers") or {}
    for provider_id, entry in seen_providers.items():
        if isinstance(entry, dict) and _needs_plan(provider_id):
            pending.append({
                "id": "resource_plan",
                "provider": entry.get("provider", provider_id),
                "question": _intake_question_text(entry.get("provider", provider_id)),
                "asked_once_then_locked": True,
            })

    # From live detection (when a caller supplies it): a detected provider
    # arriving with no plan yet also owes its one-time answer.
    if isinstance(detection, dict):
        det_provider = detection.get("provider")
        if det_provider and det_provider not in seen_providers and _needs_plan(det_provider):
            pending.append({
                "id": "resource_plan",
                "provider": det_provider,
                "question": _intake_question_text(det_provider),
                "asked_once_then_locked": True,
            })
    return pending


def _intake_question_text(provider: str) -> str:
    """Question 10's prompt text (redacted detected summary + confirm/tier
    choice), folded into FIX 30's reduced schema as `resource_plan`."""
    detected = redacted_summary(load_profile())
    plans = ()
    if _capacity is not None:
        plans = _capacity.PLANS_BY_PROVIDER.get(provider, ())
    tier_hint = ""
    if plans:
        rows = ", ".join(
            f"{p} -> {_capacity.CAP_TABLE.get((provider, p), '?')}"
            for p in plans)
        tier_hint = f" ({rows})"
    return (
        "I detected these presentation providers and plans: "
        f"{json.dumps(detected.get('providers', []))}. "
        f"Confirm the plan/tier for {provider}{tier_hint}, or choose "
        "'use conservative default.'"
    )


def apply_probe_refresh(detection: Dict[str, Any],
                        profile: Optional[Dict[str, Any]] = None,
                        config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Refresh DETECTABLE fields from a probe result -- WITHOUT a question.

    The FIX 9 probe (live provider/model discovery) calls this with its
    detection dict: what got updated is recorded on the provider entry, the
    updated_at stamp moves, and the ask-once lock is untouched -- a refresh
    never unsettles a locked plan and never re-arms an interview."""
    prof = profile if profile is not None else load_profile(config_dir)
    if prof.get("error") and not prof.get("providers"):
        prof = new_profile()
    provider = detection.get("provider")
    if isinstance(provider, str) and provider.strip():
        fields: Dict[str, Any] = {"detected": True}
        if detection.get("plan") is not None:
            fields["plan_tier"] = detection["plan"]
            fields["plan_known"] = True
        if detection.get("max_concurrent") is not None:
            fields["concurrency_ceiling"] = detection["max_concurrent"]
            fields["ceiling_source"] = "probe"
        if detection.get("wired_models") is not None:
            fields["wired_models"] = detection["wired_models"]
        entry = upsert_provider(prof, provider, **fields)
        # LOCK PRESERVED: only stamp that a refresh happened.
        entry["last_probe_refresh"] = _now()
        # Locked plans stay locked: a probe that reports no plan does not
        # unset an interview answer.
        if entry.get("locked") and not detection.get("plan"):
            entry["plan_known"] = True
        save_profile(prof, config_dir)
    return prof


# ---------------------------------------------------------------------------
# FIX 9: provider probe storage (wired inventory into the profile)
# ---------------------------------------------------------------------------
def store_provider_probes(probe_result: Dict[str, Any],
                          profile: Optional[Dict[str, Any]] = None,
                          config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Persist FIX 9's provider inventory into the profile.

    `probe_result` is capacity.probe_providers()' dict: {"probes": {provider:
    {present, key_source, probed, http_status, models, ...}},
    "ninerouter": {"providers": {prefix: {"label","models"}}}}.

    What lands per provider entry (all redacted by the write path):
      detected / detected_at   -- the probe ran
      presence                 -- bool (key present; never the value, never
                                  the source path -- named to survive the
                                  redaction contract's secret-key rule)
      wired_models             -- the exact unlocked model ids from the
                                  list/models call (sorted); kept across runs
                                  when a later probe cannot resolve them
                                  (absence of a reading is never deletion)
      probed_at                -- last successful inventory stamp
      probe_error              -- the last failure reason, names never values
    The 9Router lineup lands under `providers["_9router"]` -- its per-node
    model lineups are the "which models does 9Router have wired locally"
    answer (non-secret columns only, per the capacity probe's contract).

    Ask-once contract untouched: this refreshes DETECTABLE fields only, never
    plan tiers, never locks. Skipped entirely (stores nothing) when the flag
    is off -- the documented rollback."""
    prof = profile if profile is not None else load_profile(config_dir)
    if prof.get("error") and not prof.get("providers"):
        prof = new_profile()
    if not flag_enabled():
        return prof
    probes = probe_result.get("probes") if isinstance(probe_result, dict) else None
    if isinstance(probes, dict):
        for provider_id, verdict in probes.items():
            if not isinstance(verdict, dict):
                continue
            fields: Dict[str, Any] = {
                "detected": bool(verdict.get("present") or
                                 verdict.get("models")),
            }
            if verdict.get("probed") is not None:
                fields["probe_attempted"] = bool(verdict.get("probed"))
            # NOTE the field name: `presence`, not `key_present` -- the write
            # path's redact_record() drops any secret-named key, and "key_*"
            # IS a secret-named key by the binding regex. The profile records
            # presence-of-key as `presence`; the capacity.py probe_verdicts
            # keep `present` (a boolean assertion, never a value).
            fields["presence"] = bool(verdict.get("present"))
            if verdict.get("probed"):
                fields["probe_http_status"] = verdict.get("http_status")
            if verdict.get("models"):
                fields["wired_models"] = sorted(verdict["models"])
                fields["probed_at"] = probe_result.get("probed_at")
                # a successful reading replaces any stale inventory error
                fields.pop("probe_error", None)
            elif verdict.get("models_error"):
                fields["probe_error"] = str(verdict["models_error"])
                existing = get_provider(prof, provider_id) or {}
                if existing.get("wired_models"):
                    # keep the last good inventory -- an unresolvable call is
                    # never evidence the models disappeared
                    fields["wired_models"] = existing["wired_models"]
            entry = upsert_provider(prof, provider_id, **fields)
            entry.setdefault("provider", provider_id)
    lineup = probe_result.get("ninerouter") if isinstance(probe_result, dict) else None
    if isinstance(lineup, dict) and lineup.get("hit"):
        nine = {}
        for prefix, info in (lineup.get("providers") or {}).items():
            nine[prefix] = {"label": info.get("label"),
                            "models": sorted(info.get("models") or [])}
        profile_entry = upsert_provider(prof, "_9router_lineup",
                                        detected=True,
                                        wired=nine,
                                        total_models=lineup.get("total_models", 0),
                                        probed_at=probe_result.get("probed_at"))
        _ = profile_entry
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return prof

def wired_models(provider: str,
                 profile: Optional[Dict[str, Any]] = None,
                 config_dir: Optional[Path] = None) -> List[str]:
    """The stored wired model ids for one provider (FIX 7/FIX 10/FIX 13's
    read side). Empty list when absent -- an absent inventory is never
    claimed as 'nothing wired' by this accessor; callers that must
    distinguish stale/never-probed consult get_provider() themselves."""
    prof = profile if profile is not None else load_profile(config_dir)
    entry = get_provider(prof, provider)
    models = (entry or {}).get("wired_models")
    return sorted(models) if isinstance(models, list) else []

# ---------------------------------------------------------------------------
# Intake-surface helper (the ONE question, FIX 30 shape)
# ---------------------------------------------------------------------------
def intake_question(detection: Optional[Dict[str, Any]] = None,
                    config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The resource_profile intake turn for FIX 30's reduced schema -- or
    None when everything detectable was detected. The driver asks only when
    probe data is incomplete, exactly once, then never again."""
    pend = pending_questions(detection=detection, config_dir=config_dir)
    if not pend:
        return None
    return pend[0]