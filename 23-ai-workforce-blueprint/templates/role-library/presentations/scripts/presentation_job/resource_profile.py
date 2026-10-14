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
      "concurrency_ceiling": 8 | "UNBOUNDED" | null,   # 8, not 10: see below
      "ceiling_source": "cap-table" | "declared" | "interview" | "probe",
      "consented":      true/false,
      "wired_models":   ["deepseek-flash", ...],   # probed (FIX 9)
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

CAPACITY INTEROPERATION (per provider -- do not "simplify" this back)
----------------------------------------------------------------------
The profile NEVER bypasses capacity.py's doctrine. is_plan_locked() and
intake questions consult capacity.CAP_TABLE; capacity.probe() remains the
dispatch-path authority. FIX 8 adds persistence and the ask-once lock --
it does not move the gate.

F2 (2026-09-07): this profile is THE store for the plan answer, per
provider. record_plan_answer() no longer projects the answer into
capacity_override.json -- capacity.detect() reads the locked entry from
here (capacity._plan_from_profile) for the provider it was asked about.
capacity_override.json survives only as a per-provider operator
self-throttle (schema 2), honoured for the provider it names. Two stores
encoding "the client answered once" is exactly how ONE provider's tier
came to cap a multi-provider client's whole run.

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

import threading  # noqa: F401 -- [PRES-044] unique tmp naming in save_profile

import contextlib
import errno
import fnmatch
import json
import os
import re
import sys
import threading
import time
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
#: secrets/ -- the same ownership boundary the operator's secrets already
#: live behind. Never inside any repository checkout.
#: FIX 68/B3: the root resolves through presentation_job/oc_paths.py
#: (state_dir() is exactly this path, platform-aware: /data/.openclaw/state/
#: presentation on the docker VPS, ~/.openclaw/state/presentation on a Mac),
#: degrading to the legacy Mac path when oc_paths is not deployed beside this
#: module (a partial deploy keeps the pre-FIX-68 behavior, never a hard
#: break). The override envs below still win, in the documented order.
def _default_store_dir() -> Path:
    try:
        try:
            from . import oc_paths as _op  # package-relative (python3 -m)
        except ImportError:  # pragma: no cover - direct file run
            import oc_paths as _op  # type: ignore[no-redef]
        return Path(_op.state_dir())
    except Exception:  # noqa: BLE001 -- partial deploy keeps the Mac default
        return Path.home() / ".openclaw" / "state" / "presentation"

DEFAULT_STORE_DIR = _default_store_dir()


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

#: [PRES-044] Monotonic suffix for profile_version tokens: two saves inside
#: the same wall-clock second must never mint the same token (the token IS
#: the store revision -- see save_profile's expected_profile_version lock).
_PROFILE_VERSION_SEQ = 0

def _profile_version_token() -> str:
    """A distinct-per-write optimistic-lock token: UTC timestamp (the
    pre-existing format, kept for operator readability) plus a monotonic
    sequence counter so two writes in one second still differ."""
    global _PROFILE_VERSION_SEQ
    _PROFILE_VERSION_SEQ += 1
    return (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            + f"Z{_PROFILE_VERSION_SEQ:04d}")


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


class StoreRevisionConflict(RuntimeError):
    """[PRES-044] A caller's expected_profile_version no longer matches the
    store -- another writer's update is on disk and is preserved. Raised
    instead of silently overwriting their fields; the caller may re-read,
    re-merge and retry."""


class StoreWriteError(RuntimeError):
    """[PRES-044] The profile could not be written durably (disk full,
    un-renameable tmp, ...). The previous file is untouched and the failure
    is VISIBLE -- never a success claim over a lost write."""


def _store_lock(path: Path):
    """[PRES-044] One lock per store path spanning the whole
    read -> validate -> merge -> write transaction: a re-entrant
    process-local mutex layered under a cross-process fcntl.flock on
    `<name>.lock`. flock() is per-open-file-description, so two threads of
    one process do NOT exclude each other without the mutex; a crashed
    writer never wedges the advisory lock (the OS drops it with the
    process)."""
    from . import capacity as _cap_locks
    try:
        return _cap_locks._store_lock(path)
    except Exception:  # noqa: BLE001 -- standalone module, no capacity
        with threading.Lock():
            pass

        @contextlib.contextmanager
        def _locked():
            yield
        return _locked


def _atomic_write_locked(path: Path, payload: dict) -> None:
    """[PRES-044] The durable profile write, called WITH the store lock held.

    Unique tmp (pid + thread + monotonic counter), fsync of the file, atomic
    os.replace, fsync of the directory. Any failure removes the tmp and
    re-raises as StoreWriteError with the previous file intact -- the old
    data stays recoverable on disk and no success is ever claimed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(
        f".json.tmp-{os.getpid()}-{threading.get_ident()}-{time.monotonic_ns()}")
    try:
        with open(str(tmp), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:  # pragma: no cover - best effort on exotic filesystems
            pass
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:  # pragma: no cover
            pass
        raise StoreWriteError(
            f"{path}: durable profile write failed: {exc.__class__.__name__}: "
            f"{exc}") from exc


def save_profile(profile: Dict[str, Any],
                 config_dir: Optional[Path] = None,
                 expected_profile_version: Optional[Any] = None) -> Optional[Path]:
    """Redact, then transactionally write the profile. Returns the written path.

    Refused (returns None) when the flag is off -- the documented rollback
    selects the no-persistence safe path.

    [PRES-044] TRANSACTIONAL: the write is a unique tmp (pid+thread) +
    fsync + atomic os.replace + directory fsync, all inside ONE lock
    (`resource_profile.json.lock`, process-local mutex + cross-process
    flock) that every load-modify-save caller must hold across its read
    AND write -- use `with profile_transaction(config_dir) as prof:` so
    concurrent writers for different providers serialise and BOTH persist
    instead of last-write-wins. A write failure raises StoreWriteError with
    the old file intact -- a visible, durable configuration error, never a
    silent success over a lost write. Pass `expected_profile_version` (the
    `profile_version` string read earlier) to have a stale writer REJECTED
    with StoreRevisionConflict instead of clobbering a concurrent update.

    `read of legacy state must not rewrite it` holds unchanged: load_profile
    never writes; only save_profile does, under the lock."""
    if not flag_enabled():
        return None
    cleaned = redact_record(profile)
    cleaned["updated_at"] = _now()
    cleaned.setdefault(".schema_version", SCHEMA_VERSION)
    # [PRES-044] ROTATE the optimistic-lock token on every successful save.
    # The token is the store's revision (save_profile's
    # expected_profile_version compares against it); a token that never
    # moved would make every stale writer's expectation match forever and
    # the conflict would never fire. Monotonic within the second so two
    # writes inside the same wall-clock second still get distinct tokens.
    cleaned["profile_version"] = _profile_version_token()
    path = profile_path(config_dir)
    with _store_lock(path):
        if expected_profile_version is not None:
            current_version = None
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    current_version = raw.get("profile_version")
            except (OSError, ValueError):
                pass
            if current_version != expected_profile_version:
                raise StoreRevisionConflict(
                    f"{path} changed under us: expected profile_version "
                    f"{expected_profile_version!r}, found "
                    f"{current_version!r} -- another writer's update is on "
                    f"disk and is preserved; re-load, re-merge, retry. "
                    f"Refusing to clobber their fields.")
        _atomic_write_locked(path, cleaned)
    return path


@contextlib.contextmanager
def profile_transaction(config_dir: Optional[Path] = None):
    """[PRES-044] The one sanctioned read-modify-write shape for callers that
    need read-merge-write atomicity on the profile:

        with resource_profile.profile_transaction() as prof:
            resource_profile.upsert_provider(prof, "ollama-cloud", plan_tier="$100/month")
        # released: saved under the lock automatically

    The lock (`resource_profile.json.lock`: process-local mutex +
    cross-process flock) spans the whole read -> modify -> write, so two
    simultaneous transactions serialise and BOTH persist. The profile dict
    handed out is redacted-on-save as always; a StoreWriteError propagates
    with the old file intact. Read-only consumers (load_profile, get_provider)
    need no lock: the atomic replace guarantees they see either the old or
    the new complete document, never a torn one."""
    if not flag_enabled():
        yield load_profile(config_dir)
        return
    path = profile_path(config_dir)
    with _store_lock(path):
        prof = load_profile(config_dir)
        yield prof
        save_profile(prof, config_dir)


def migrate_profile_schema(profile: Dict[str, Any],
                           target_version: int = SCHEMA_VERSION,
                           config_dir: Optional[Path] = None) -> Path:
    """[PRES-044] Explicit, backup-first schema migration.

    A profile written by an OLDER `.schema_version` is migrated to
    `target_version` ONLY through this function: it copies the current bytes
    to `resource_profile.json.pre-schema<m>.bak` BEFORE writing, refuses the
    migration when the backup cannot be written, and stamps the migration in
    the document (`schema_migration_history`). load_profile never rewrites
    legacy state -- the read of an old file must stay a read."""
    path = profile_path(config_dir)
    with _store_lock(path):
        current_version = None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                current_version = raw.get(".schema_version")
        except (OSError, ValueError):
            pass
        if current_version is None or current_version >= target_version:
            # nothing to migrate (absent / current / newer-than-code)
            return path
        backup = path.with_suffix(f".json.pre-schema{current_version}.bak")
        try:
            backup.write_bytes(path.read_bytes())
        except OSError as exc:
            raise StoreWriteError(
                f"{path}: refusing .schema_version {current_version} -> "
                f"{target_version} migration: pre-migration backup "
                f"{backup} could not be written: {exc}") from exc
        history = profile.setdefault("schema_migration_history", [])
        history.append({"from": current_version, "to": target_version,
                        "backup": str(backup), "migrated_at": _now()})
        profile[".schema_version"] = target_version
        _atomic_write_locked(path, redact_record(profile))
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
    then LOCKED. THIS PROFILE IS THE STORE.

    Raises ValueError on a provider/plan pair the cap table does not know --
    an unknown tier is never silently persisted as if it were measured. The
    intake's other choice, "use conservative default", is NOT an answer about
    the account and never reaches this function: pass plan=None through
    record_conservative_default() for that.

    F2 -- WHAT WAS REMOVED AND WHY. This function used to ALSO project the
    answer into capacity.persist_plan_answer() -> capacity_override.json,
    "the gate's projection of the profile". That projection was the defect.
    The override file was step (a) of a detection chain that answered ONE
    question for the whole box, so a client answering "ollama-cloud,
    $100/month" pinned their DeepSeek and OpenRouter routes to 8 as well --
    a plan answer about one account wearing the whole client's clothes. Two
    stores encoding one fact ("the client answered once") is the same drift
    class the governor's tier-map-vs-cap-table fix removed; the second store
    was single-provider, and its mere existence was misread as "measured for
    every provider". So: ONE store (this profile), ONE lock
    (pending_questions / is_plan_locked), per provider.

    The concurrency_ceiling write below STAYS -- the governor's operator
    reserve reads it (governor._plan_tier_inflight / _plan_tier_rps), and
    that is a per-provider read, not a global cap.

    The ONE case that still needs a durable declaration is the documented
    rollback PRESENTATION_RESOURCE_PROFILE=0: with the profile switched off
    nothing here persists, so the answer is written through
    capacity.declare_capacity() as a per-provider schema-2 record instead --
    honoured only for the provider it names."""
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
    # F2: NO projection into capacity_override.json. The profile below is the
    # store; capacity.detect() reads THIS provider's locked entry directly
    # (capacity._plan_from_profile), so the second run dispatches against the
    # locked ceiling without a second file having to agree with this one.
    #
    # The single exception is the documented rollback: with the profile
    # switched off every write below is a no-op, so the answer would have no
    # durable home at all. Then -- and only then -- declare it, scoped to the
    # one provider it is about.
    if structural and _capacity is not None and not flag_enabled():
        _capacity.declare_capacity(norm_provider, plan=norm_plan,
                                   config_dir=config_dir)
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


# ---------------------------------------------------------------------------
# FIX 10: model gap-analysis + consent-based add/suggest
# ---------------------------------------------------------------------------
# WHAT THIS IS
# ------------
# The system used to never notice that a client who owns Ollama/OpenRouter
# may lack GLM 5.3 / GLM 5.3 Flash / DeepSeek V4 Flash 0731-class models for
# presentation work. This section compares the profile's wired inventory
# (FIX 9 probes -> apply_probe_refresh/store_provider_probes) against a
# RECOMMENDED SET for presentation workloads and produces one of two
# outcomes per gap, exactly as the spec binds it:
#
#   ADD      -- where the platform ALLOWS the addition (a detected, present,
#               bring-your-own-key provider can carry the model) AND STANDING
#               CONSENT exists (consent.add_models, recorded once through
#               record_model_consent). The addition is recorded in
#               profile["model_additions"] as status "added_pending_probe"
#               and flagged for a re-probe; confirm_added_models() flips it
#               to "confirmed" when a later probe refresh shows the model
#               wired.
#   SUGGEST  -- anything else (no standing consent, no provider that can
#               carry it, or an operator-provisioning-only platform). A
#               plain-language suggestion record -- what it unlocks and its
#               cost -- lands in profile["model_suggestions"], and
#               approve_model_suggestion() adds it ON APPROVAL only.
#
# BINDING: this NEVER rewrites client configuration. An "add" here is a
# durable, consent-backed INTENT RECORD inside the (secrets-adjacent)
# profile plus a re-probe request; rows carry config_written: False as
# proof the writer never touched provider config. Actual wiring happens
# through the operator's provisioning flow only.
#
# CATALOG INTERFACE (FIX 13 dependency): recommended entries are expressed
# as catalog ALIASES, not literal provider model ids -- FIX 13 forbids
# literal model IDs in dept code paths, and its aliases feed this matcher.
# Pass FIX 13's catalog into analyze_model_gaps(catalog=...) as any of:
#   - a callable alias -> iterable of match patterns,
#   - an object exposing resolve_alias(alias) -> iterable,
#   - a dict {alias: [pattern, ...]} (optionally under an "aliases" key).
# When no catalog is passed, an optional import of a sibling `model_catalog`
# module (FIX 13's landing spot) is attempted; if it is absent -- FIX 13 may
# land after this fix -- each recommendation's built-in matching metadata is
# used. That metadata is matching-only: it never sends a model id anywhere.
#
# Rollout flag: PRESENTATION_MODEL_GAP=1 default ON; =0 is the documented
# rollback -- analyze_model_gaps() returns [], record/apply/approve/confirm
# calls are refused no-ops, and nothing in this section writes anything.

GAP_FLAG_ENV = "PRESENTATION_MODEL_GAP"
GAP_FLAG_DEFAULT = "1"

#: The recommended set for presentation workloads (spec FIX 10: the GLM 5.3
#: / GLM 5.3 Flash / DeepSeek V4 Flash 0731 class, "etc." -- extend through
#: the catalog, not by editing matcher code). `alias` is the FIX 13 catalog
#: key; `patterns` are normalized-shape match metadata for wired-id
#: inventories; `excludes` stops a more specific sibling from falsely
#: covering a less specific alias (a box with only GLM 5.3 Flash wired must
#: still see a GLM 5.3 gap). `unlocks`/`cost` are the plain-language halves
#: of a suggestion record.
RECOMMENDED_PRESENTATION_MODELS: List[Dict[str, Any]] = [
    {
        "alias": "glm-5.3",
        "label": "GLM 5.3",
        "providers": ("openrouter", "ollama-cloud"),
        "patterns": ("glm-5.3", "glm5.3"),
        "excludes": ("flash", "lite", "air"),
        "unlocks": ("strong long-form reasoning for deck narrative and "
                    "research synthesis -- sharper section arguments and "
                    "speaker tracks"),
        "cost": ("usage-billed (per-token on OpenRouter; a full deck costs "
                 "a few dollars at typical pricing)"),
    },
    {
        "alias": "glm-5.3-flash",
        "label": "GLM 5.3 Flash",
        "providers": ("openrouter", "ollama-cloud"),
        "patterns": ("glm-5.3-flash", "glm5.3flash", "glm-5.3f"),
        "excludes": (),
        "unlocks": ("fast first-draft slide copy and layout variants at low "
                    "cost -- the throughput model for per-slide waves"),
        "cost": ("usage-billed at flash-tier rates (well under a dollar per "
                 "slide batch at typical pricing)"),
    },
    {
        "alias": "deepseek-flash",
        "label": "DeepSeek V4.1 Flash",
        "providers": ("deepseek-direct", "openrouter", "ollama-cloud"),
        "patterns": ("deepseek-flash", "deepseekflash", "deepseek-v4-flash", "deepseekv4flash"),
        "excludes": ("pro", "reasoner"),
        "unlocks": ("the department's workhorse authoring tier -- parallel "
                    "slide waves and QC passes run fastest and cheapest on "
                    "it"),
        "cost": ("usage-billed on the client's own DeepSeek/OpenRouter "
                 "account (no extra platform fee)"),
    },
]

#: Provider ids where an addition can be applied by wiring the model into
#: the client's OWN account (the BYOK-class providers FIX 9 resolves). Any
#: other provider is operator-provisioning-only -> suggest, never add.
_ADD_APPLICABLE_PROVIDERS = ("openrouter", "ollama-cloud", "deepseek-direct")


def gap_flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_MODEL_GAP=0 (the
    documented rollback for this section; see the header comment)."""
    return os.environ.get(GAP_FLAG_ENV, GAP_FLAG_DEFAULT) != "0"


def _norm_model_id(text: Any) -> str:
    """Normalization for model-id matching: lowercase, every non-alphanumeric
    run collapsed to a single dash. 'zai/glm-5.3-flash:free', 'GLM 5.3 Flash'
    and 'glm_5_3_flash' all land on one comparable shape."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


# ---------------------------------------------------------------------------
# THE CLIENT MODEL PLAN (operator requirement 2026-09-04, verbatim):
#   "whatever is forcing this thing to use DeepSeek V4.1 Flash, I don't want to be
#    forced to do anything. So as a client should be able to choose whatever
#    they want to be their primary workhorse or authoring model."
#
# The plan lives HERE, in the profile, and nowhere else. It is the only store
# every consumer already reaches: model_router.resolve_route() loads the
# profile on every call, and the P4-PROMPT fan-out children re-resolve in a
# SEPARATE process (parallel_prompt_worker) that inherits the env-resolved
# profile path but has no run_dir -- a run-directory sidecar would be
# invisible to exactly the phase that fans out widest.
#
# KEY NAMING (binding): redact_record() above DROPS every key matching
# (api[-_]?key|key|token|secret|password|passwd|auth|credential|cookie|bearer)
# on every save AND every load. "auth" is a substring of "authoring", so a slot
# named "authoring_model" would silently vanish from the store. The slot is
# named "workhorse"; "model_plan", "workhorse", "reasoning", "judge",
# "thinking", "floor_waivers", "provider", "model" all survive the filter, and
# tests/test_model_plan.py pins that with a real save/load round trip.
# ---------------------------------------------------------------------------

#: The client-choosable slots. Mirrors model_router.SLOT_CLASSES; used only as
#: the fallback vocabulary when the router module is not importable beside this
#: one (a partial deploy), never as a second source of truth for the mapping.
MODEL_PLAN_SLOTS: tuple = ("workhorse", "reasoning", "judge")

#: The thinking-level vocabulary the intake offers. Recorded now; wiring it
#: into per-call reasoning_effort is deliberately NOT part of this change.
THINKING_LEVELS: tuple = ("max", "high", "medium", "low", "off")


def _model_router_module():
    """The router module, or None. Its SLOT_CLASSES/floor_verdict are the one
    definition of what a slot governs and what a class demands; this module
    never re-implements them."""
    try:
        from . import model_router as _mr  # package-relative
        return _mr
    except ImportError:  # pragma: no cover - direct file run
        try:
            import model_router as _mr  # type: ignore[no-redef]
            return _mr
        except ImportError:
            return None


def parse_model_spec(text: Any) -> Optional[Dict[str, str]]:
    """Parse the intake's `model@provider` vocabulary into {provider, model}.

    Returns None for an empty answer (an omitted slot keeps the department
    default -- silence is not a declaration). Raises ValueError on anything
    that is not exactly one model id, one '@' and one provider id, naming the
    shape instead of guessing which half is which. Trailing separators are
    tolerated because the merged-turn label parser hands values through with
    the client's own punctuation attached ("...@deepseek-direct; qc: ...").

    The provider is folded through the ONE provider-id canon
    (model_router._norm_provider -> capacity.normalize_provider), so
    `ollama_cloud`, `Ollama Cloud` and `ollama-cloud` are one provider and
    `deepseek` resolves to `deepseek-direct`. Folding a name is never evidence
    the provider exists -- record_model_plan checks that separately."""
    raw = str(text or "").strip().strip(";,.").strip()
    if not raw:
        return None
    if raw.count("@") != 1:
        raise ValueError(
            f"model choice {raw!r} is not in the required 'model@provider' "
            f"shape (exactly one '@'), for example "
            f"'deepseek-flash@deepseek-direct' (legacy deepseek-v4-flash still accepted via the catalog compat shim)")
    model, provider = raw.rsplit("@", 1)
    model = model.strip().strip(";,.").strip()
    provider = provider.strip().strip(";,.").strip()
    if not model or not provider:
        raise ValueError(
            f"model choice {raw!r} is missing its "
            f"{'model' if not model else 'provider'} half; the shape is "
            f"'model@provider', for example 'glm-5.3-flash@ollama-cloud'")
    mr = _model_router_module()
    if mr is not None:
        provider = mr._norm_provider(provider) or provider
    elif _capacity is not None:
        provider = _capacity.normalize_provider(provider) or provider
    return {"provider": provider, "model": model}


def _wired_match(model: str, wired: List[Any]) -> bool:
    """Is `model` in this provider's wired inventory? Same comparison
    model_router._eligible uses: exact match on the folded shape, plus
    fnmatch either way so a probe's explicit family wildcard is honored.
    Folding spelling drift is never a family/prefix inference."""
    nm = _norm_model_id(model)
    for w in wired:
        ws = str(w)
        if nm and nm == _norm_model_id(ws):
            return True
        if fnmatch.fnmatch(model, ws) or fnmatch.fnmatch(ws, model):
            return True
    return False


def model_plan(profile: Optional[Dict[str, Any]] = None,
               config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The client's declared model plan, or {} when none is declared."""
    prof = profile if profile is not None else load_profile(config_dir)
    plan = (prof or {}).get("model_plan")
    return plan if isinstance(plan, dict) else {}


def _adopt_declared_providers(profile: Dict[str, Any],
                              declared: Dict[str, Dict[str, str]]) -> List[str]:
    """F17: adopt a provider THIS BUILD has never heard of onto the profile
    when the client NAMED it in their model plan. Returns the ids adopted.

    WHY. `model_router._eligible` routes only to a provider the profile
    CARRIES, and nothing but the capacity/provider probe ever put one there
    -- and that probe only knows the handful of providers it was written for
    (openrouter, ollama-cloud, agnes, deepseek, kie). So adopting a model on
    any other provider required a code change, which is exactly what the
    standing operator ruling forbids: nobody is forced onto a model, and a
    new one must work WITHOUT one. For a provider no probe can discover, the
    client naming {provider, model} IS the ownership evidence.

    NOT a relaxation of the gates that matter -- all three still stand:
      * a provider this build DOES know (a cap-table id, or a token the table
        deliberately refuses such as a local Ollama) is never adopted here.
        The probe can find those, so the profile's silence about one is
        evidence, and the existing "does not carry provider X" refusal below
        still fires -- a typo can never mint a provider;
      * a plan on a profile with NO providers at all is still refused (the
        empty-profile check runs after this, on the adopted result);
      * `_eligible` still requires a RESOLVABLE, plausible key (FIX 114)
        before anything routes to an adopted provider, so one with no
        credential parks with the key gate named, exactly as before.

    The entry records WHERE the evidence came from (`client_declared`,
    `detection_source: client-declaration`) so nothing downstream can mistake
    a declaration for a probe reading."""
    adopted: List[str] = []
    for slot, spec in sorted(declared.items()):
        raw = str(spec.get("provider") or "")
        if not raw:
            continue
        if _capacity is not None and _capacity.is_known_provider(raw):
            continue  # the probe owns this one -- its absence is evidence
        token = raw
        if _capacity is not None:
            token = _capacity.canonical_provider_token(raw) or raw
        spec["provider"] = token  # plan and profile key can never disagree
        existing = profile.get("providers")
        if isinstance(existing, dict) and token in existing:
            continue
        entry = upsert_provider(
            profile, token,
            presence=True,
            client_declared=True,
            declared_in="model_plan",
            declared_slot=slot,
            declared_at=_now(),
            detection_source="client-declaration",
        )
        entry.setdefault("provider", token)
        adopted.append(token)
    return adopted


def record_model_plan(plan: Dict[str, Any], *,
                      source: str = "interview",
                      config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Persist ONE client model plan. Validates BEFORE anything is written.

    `plan` accepts each slot as {"provider","model"}, as a "model@provider"
    string, or as None/"" (omitted -- keeps the department default), plus
    optional "thinking" and "floor_waivers".

    REFUSES (ValueError, nothing written) when:
      * the profile carries no providers at all -- a plan on a profile with no
        providers is INVISIBLE, not merely unused: resolve_route reports
        profile_state "absent" for an empty providers map and the dispatcher
        falls back to its pre-router DeepSeek default, so the client would be
        told "recorded" and then silently overridden on every call. The
        message names the capacity probe that fixes it;
      * the declared provider is one this build KNOWS (a cap-table id) and
        the profile does not carry it -- the probe can find those, so its
        silence is evidence (the message names the providers that DO exist).
        F17: a provider this build has NEVER heard of is ADOPTED instead of
        refused (see _adopt_declared_providers) -- no probe could ever have
        found it, so refusing would mean no new provider without a code
        change. The FIX 114 key gate in _eligible still stands over it;
      * the provider HAS a wired inventory and the declared model is not in it
        (the message names the inventory it was checked against);
      * the declared model's MODALITY cannot do the slot's job (a vision or
        image model in a text slot). Modality is physics, not preference, and
        is the one floor no waiver crosses;
      * "thinking" is outside THINKING_LEVELS.

    HONOURS, with a recorded waiver (Trevor: not forced), a model whose
    CONTEXT class falls short of a class floor -- e.g. a standard-window
    model named explicitly for the reasoning slot. The class is appended to
    floor_waivers, the reason is written into the audit row, and
    model_router.resolve_route stamps floor="waived" on the decision so the
    launcher banner and the client report both say it out loud.

    A later, different answer UPDATES the plan and appends another audit row:
    a client changing their workhorse never needs an operator. UPDATE means
    exactly that -- an answer that names only one slot (the intake asks each
    subfield in its own turn) overlays that slot and PRESERVES every other
    declared slot already in the store. It never nulls a slot this answer did
    not mention; see the PRESERVE-BEFORE-OVERLAY note at the write below."""
    if not flag_enabled():
        return load_profile(config_dir)

    profile = load_profile(config_dir)

    mr = _model_router_module()
    slot_classes = getattr(mr, "SLOT_CLASSES", None) if mr is not None else None
    if not isinstance(slot_classes, dict):
        slot_classes = {s: () for s in MODEL_PLAN_SLOTS}

    declared: Dict[str, Dict[str, str]] = {}
    for slot in slot_classes:
        raw = (plan or {}).get(slot)
        if raw is None or raw == "":
            continue
        if isinstance(raw, dict):
            spec = parse_model_spec(f"{raw.get('model', '')}@{raw.get('provider', '')}") \
                if raw.get("model") and raw.get("provider") else None
            if spec is None:
                raise ValueError(
                    f"refusing to record the {slot!r} slot: a declaration needs "
                    f"BOTH a model and a provider (got {raw!r})")
        else:
            spec = parse_model_spec(raw)
        if spec is None:
            continue
        # Saved-config compat: an older stored Flash id folds to the live id
        # at the door, so a client plan saved before the V4.1 rename validates
        # against the CURRENT probe inventory instead of breaking. The stored
        # plan keeps what the client declared; only the check folds.
        try:
            from . import model_catalog as _mc_compat  # package-relative
        except ImportError:  # pragma: no cover - direct file run
            try:
                import model_catalog as _mc_compat  # type: ignore[no-redef]
            except ImportError:
                _mc_compat = None  # type: ignore[assignment]
        if _mc_compat is not None:
            fold = getattr(_mc_compat, "fold_legacy_flash_model_id", None)
            if callable(fold):
                try:
                    spec = dict(spec)
                    spec["model"] = fold(spec.get("model"))
                except Exception:  # noqa: BLE001 -- a fold failure never records
                    pass
        declared[slot] = spec

    unknown_slots = [s for s in (plan or {})
                     if s not in slot_classes
                     and s not in ("thinking", "floor_waivers", "source",
                                   "declared_at", "openrouter_model")]
    if unknown_slots:
        raise ValueError(
            f"refusing to record a model plan: unknown slot(s) "
            f"{sorted(unknown_slots)}; the client-choosable slots are "
            f"{sorted(slot_classes)}")

    # F17: adopt any provider this build has never heard of that the client
    # NAMED here, BEFORE the provider checks below -- otherwise the only way
    # to reach a new provider is a code change (see the helper's docstring).
    adopted = _adopt_declared_providers(profile, declared)

    providers = profile.get("providers")
    providers = providers if isinstance(providers, dict) else {}
    if not providers:
        raise ValueError(
            "refusing to record a model plan: this profile carries NO "
            "providers, and a plan on a provider-less profile is invisible -- "
            "model_router.resolve_route reports profile_state 'absent' and the "
            "dispatcher falls back to its default model on every call. Run the "
            "capacity/provider probe first "
            "('python3 -m presentation_job --capacity'), then record the plan.")

    thinking = (plan or {}).get("thinking")
    thinking = str(thinking).strip().lower() if thinking not in (None, "") else None
    # FIX 61.2: the client's OpenRouter model pick rides the plan.
    openrouter_model = (plan or {}).get("openrouter_model")
    openrouter_model = str(openrouter_model).strip() if openrouter_model not in (None, "") else None
    if thinking is not None and thinking not in THINKING_LEVELS:
        raise ValueError(
            f"refusing to record thinking level {thinking!r}: the vocabulary is "
            f"{list(THINKING_LEVELS)}")

    # --- validation, all of it, before a single byte is written ------------
    waivers = {str(w).strip() for w in ((plan or {}).get("floor_waivers") or [])
               if str(w).strip()}
    waiver_reasons: List[Dict[str, str]] = []
    for slot, spec in declared.items():
        provider, model = spec["provider"], spec["model"]
        entry = providers.get(provider)
        if not isinstance(entry, dict):
            raise ValueError(
                f"refusing to record the {slot!r} slot: this profile does not "
                f"carry provider {provider!r}. Providers on this profile: "
                f"{sorted(providers)}. Run the capacity/provider probe first, "
                f"or name one of those.")
        if entry.get("consented") is False:
            raise ValueError(
                f"refusing to record the {slot!r} slot: provider {provider!r} "
                f"is recorded as NOT consented on this profile.")
        alias_def = None
        if mr is not None:
            alias_def, _src = mr.declared_alias_def(spec)
        wired = entry.get("wired_models")
        if isinstance(wired, list) and wired:
            # Check the declared id AND the id this provider's endpoint would
            # actually be sent. A client may legitimately name a catalog alias
            # ("glm-flash") whose served id on openrouter is
            # "z-ai/glm-5.3-flash" -- that is the id the wired inventory holds,
            # and the id _eligible() will judge at route time. Comparing only
            # the alias would refuse a declaration that routes perfectly.
            served = (mr._served_model(alias_def, provider)
                      if (mr is not None and alias_def) else "")
            # Saved-config compat: the live Flash id is accepted when the
            # inventory still carries the older id, and vice versa -- a probe
            # inventory taken before the V4.1 rename must not refuse the live
            # id the router now sends, and an older saved plan must not break
            # against a refreshed inventory. Both spellings name one model.
            compat_ids = [model]
            if _mc_compat is not None:
                fold = getattr(_mc_compat, "fold_legacy_flash_model_id", None)
                legacy = getattr(_mc_compat, "LEGACY_FLASH_MODEL_IDS", ())
                if callable(fold):
                    try:
                        compat_ids.append(fold(model))
                    except Exception:  # noqa: BLE001 -- fold never validates
                        pass
                try:
                    if model == fold(model) if callable(fold) else False:
                        compat_ids.extend(str(m) for m in (legacy or ()))
                except Exception:  # noqa: BLE001 -- compat never validates
                    pass
            if not any(_wired_match(m, wired) for m in compat_ids) and not (
                    served and _wired_match(served, wired)):
                raise ValueError(
                    f"refusing to record the {slot!r} slot: model {model!r} is "
                    f"not in {provider}'s wired inventory"
                    + (f" (nor its served id {served!r})"
                       if served and served != model else "")
                    + f". Checked against "
                    f"{sorted(str(w) for w in wired)} ({len(wired)} wired).")
        # Floors. Modality is refused; context is honoured with a waiver.
        if mr is None or not alias_def:
            continue
        for capability in slot_classes.get(slot, ()):  # noqa: B007
            verdict = mr.floor_verdict(alias_def, capability)
            if verdict["ok"]:
                continue
            if verdict["modality"] != verdict["required"].get("modality"):
                raise ValueError(
                    f"refusing to record the {slot!r} slot: {model!r} is a "
                    f"{verdict['modality']} model and capability "
                    f"{capability!r} requires a "
                    f"{verdict['required'].get('modality')} model. Modality is "
                    f"a capability, not a preference -- no waiver crosses it.")
            # Context-class shortfall on an EXPLICITLY named slot: honour it.
            waivers.add(capability)
            waiver_reasons.append({"capability": capability, "slot": slot,
                                   "detail": verdict["reason"]})

    # --- write --------------------------------------------------------------
    # PRESERVE-BEFORE-OVERLAY (PD-TEST-064). A model plan arrives one subfield
    # at a time -- the intake asks `workhorse_model`, `reasoning_model`,
    # `qc_model` and `thinking_mode` as SEPARATE answers, and the real driver
    # calls here once per answer -- so most calls declare exactly ONE slot.
    #
    # This block used to be built from scratch with every undeclared slot
    # pinned to None, which made the two halves of this function disagree: the
    # PARSE loop above skips an omitted slot ("an omitted slot keeps the
    # department default -- silence is not a declaration", parse_model_spec),
    # while the WRITE loop below nulled that same slot IN THE STORE. The result
    # was that answering the judge subfield one second after declaring a
    # workhorse ERASED the workhorse: `model_plan.workhorse` went null, the
    # Command Center operator-contract re-dispatch path then failed closed
    # against the profile's workhorse slot (intake_bridge.
    # _verified_operator_model_plan), and the client's declared authoring
    # route stopped driving model selection.
    #
    # Silence must not ERASE a declaration either, so the block now starts from
    # what is already stored and this answer overlays only the slots it
    # actually declared. A first-ever declaration is unaffected: with no prior
    # block the result is byte-for-byte the document the old code wrote.
    prior_plan = profile.get("model_plan")
    prior_plan = prior_plan if isinstance(prior_plan, dict) else {}
    block: Dict[str, Any] = dict(prior_plan)
    for slot in slot_classes:
        block.setdefault(slot, None)
    # An omitted slot is carried over, so its floor waivers must be carried too:
    # model_router.client_plan_for() honours a declared model only while its
    # capability appears in THIS list (`waived`), so dropping them would
    # silently un-honour a declaration this answer never touched. Waivers
    # belonging to a slot re-declared HERE are dropped -- they are recomputed
    # below against the new declaration.
    redeclared_capabilities = {capability for slot in declared
                               for capability in slot_classes.get(slot, ())}
    prior_waivers = {str(w).strip() for w in (prior_plan.get("floor_waivers") or [])
                     if str(w).strip()}
    waivers |= {w for w in prior_waivers if w not in redeclared_capabilities}
    # Same rule for the recorded thinking level: "off" is a real, explicit
    # choice in THINKING_LEVELS, so only an OMITTED answer leaves the stored
    # one standing.
    block["thinking"] = thinking if thinking is not None else block.get("thinking")
    # FIX 61.2: record the OpenRouter model alongside thinking.
    if openrouter_model is not None:
        block["openrouter_model"] = openrouter_model
    block["floor_waivers"] = sorted(waivers)
    block["source"] = str(source or "interview")
    block["declared_at"] = _now()
    for slot, spec in declared.items():
        block[slot] = dict(spec)
    profile["model_plan"] = block

    interview = profile.setdefault("interview", {})
    log = interview.setdefault("model_plan", [])
    log.append({
        "declared": {s: dict(v) for s, v in declared.items()},
        "thinking": thinking,
        "floor_waivers": sorted(waivers),
        "waiver_reasons": waiver_reasons,
        # F17: providers this build had never heard of, adopted from THIS
        # declaration. Named in the audit row so an adopted provider is never
        # indistinguishable from one a probe actually found.
        "adopted_providers": adopted,
        "source": str(source or "interview"),
        "answered_at": _now(),
    })
    save_profile(profile, config_dir)
    return profile


def _catalog_alias_resolver(catalog: Any):
    """Coerce FIX 13's catalog (any of the accepted shapes above, or None)
    into a callable alias -> tuple of match patterns, or None when no
    catalog is reachable. With no argument, an optional sibling
    `model_catalog` import is attempted (FIX 13's landing spot); its absence
    is normal -- this fix lands in the same wave and must import cleanly
    either way."""
    resolve = None
    if catalog is not None:
        if callable(catalog):
            resolve = catalog
        elif hasattr(catalog, "resolve_alias"):
            resolve = catalog.resolve_alias
        elif isinstance(catalog, dict):
            table = catalog.get("aliases") if "aliases" in catalog else catalog
            def resolve(alias, _t=table):  # noqa: ANN001,E306
                v = _t.get(alias) if isinstance(_t, dict) else None
                if isinstance(v, str):
                    return (v,)
                return tuple(v or ())
    else:
        try:
            try:
                from . import model_catalog as _mc  # package-relative
            except ImportError:
                import model_catalog as _mc  # type: ignore[no-redef]
            if hasattr(_mc, "resolve_alias"):
                resolve = _mc.resolve_alias
        except ImportError:
            resolve = None
    if resolve is None:
        return None

    def _wrapped(alias):  # noqa: ANN001
        try:
            v = resolve(alias)
        except Exception:  # noqa: BLE001 -- a broken alias row must not kill gap analysis
            return None
        if not v:
            return None
        if isinstance(v, str):
            return (v,)
        return tuple(v)
    return _wrapped


def recommended_models() -> List[Dict[str, Any]]:
    """The recommended presentation model set (copies; callers never mutate
    the module table)."""
    return [dict(r, providers=tuple(r["providers"]),
                 patterns=tuple(r["patterns"]),
                 excludes=tuple(r.get("excludes") or ()))
            for r in RECOMMENDED_PRESENTATION_MODELS]


def _wired_covers(wired_norm: List[str], patterns_norm: List[str],
                  excludes_norm: List[str]) -> bool:
    """True when a wired id matches a catalog pattern (containment either
    way on the normalized shapes -- provider ids, display labels and
    catalog aliases are written differently: 'glm-5-3-flash' covers
    'zai-glm-5-3-flash-free' and vice versa) AND is not excluded. The
    exclusion half is what stops 'GLM 5.3 Flash' from posing as base
    'GLM 5.3' coverage."""
    for w in wired_norm:
        if any(x and x in w for x in excludes_norm):
            continue
        for p in patterns_norm:
            if not p:
                continue
            # p-in-w is the normal direction (a catalog fragment inside a
            # longer provider id). w-in-p is allowed only for substantial
            # wired ids -- a bare "glm-5" must NOT pose as covering the
            # "glm-5.3" alias just because it is a substring of it.
            if p in w or (len(w) >= 8 and w in p):
                return True
    return False


def _provider_present(prof: Dict[str, Any], provider_id: str) -> bool:
    """Whether FIX 9's probes found this provider on the box: the entry is
    stored, detected, and (when recorded) presence is not False.
    Deliberately conservative -- a provider never probed is NOT present,
    and absence of evidence is never evidence a platform can carry an
    addition."""
    entry = get_provider(prof, provider_id)
    if not entry:
        return False
    if entry.get("presence") is False:
        return False
    return bool(entry.get("detected"))


def record_model_consent(granted: bool, source: str = "intake",
                         profile: Optional[Dict[str, Any]] = None,
                         config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Record the client's STANDING consent (or refusal) for adding
    recommended presentation models. The refusal is persisted too -- a
    refusal is an answer, not an absence, and gap-analysis treats the two
    differently: an unanswered consent only ever suggests; a refusal only
    ever suggests; only a granted answer unlocks the add path."""
    if not gap_flag_enabled():
        return profile if profile is not None else load_profile(config_dir)
    prof = profile if profile is not None else load_profile(config_dir)
    consent = prof.setdefault("consent", {})
    consent["add_models"] = bool(granted)
    consent["add_models_source"] = str(source)
    consent["add_models_answered_at"] = _now()
    save_profile(prof, config_dir)
    return prof


def has_model_add_consent(profile: Optional[Dict[str, Any]] = None,
                          config_dir: Optional[Path] = None) -> Optional[bool]:
    """True / False / None: consent given, consent refused, or never asked.
    None means the intake still owes the question -- callers surface it as a
    pending consent turn, never assume it."""
    prof = profile if profile is not None else load_profile(config_dir)
    v = (prof.get("consent") or {}).get("add_models")
    return None if v is None else bool(v)


def _addition_rows(prof: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in (prof.get("model_additions") or []) if isinstance(r, dict)]


def _suggestion_rows(prof: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in (prof.get("model_suggestions") or []) if isinstance(r, dict)]


def _record_addition(prof: Dict[str, Any], *, alias: str, label: str,
                     providers: List[str], approved_by: str) -> Dict[str, Any]:
    """Create one addition intent row (never provider config). Idempotent
    per alias: a pending or confirmed row for the alias is returned as-is."""
    additions = prof.setdefault("model_additions", [])
    for row in additions:
        if isinstance(row, dict) and row.get("alias") == alias:
            return row
    row = {
        "alias": alias,
        "label": label,
        "providers": list(providers),
        "status": "added_pending_probe",
        "approved_by": str(approved_by),
        "approved_at": _now(),
        "reprobe_required": True,
        "config_written": False,
    }
    additions.append(row)
    # the suggestion for this alias, if open, is now closed by the add
    prof["model_suggestions"] = [s for s in _suggestion_rows(prof)
                                 if s.get("alias") != alias]
    return row


def analyze_model_gaps(profile: Optional[Dict[str, Any]] = None,
                       catalog: Any = None,
                       config_dir: Optional[Path] = None,
                       persist: bool = True) -> List[Dict[str, Any]]:
    """Compare the profile's wired inventory to the recommended presentation
    set; return one record per gap. With persist=True (and no profile
    object handed in) the outcomes are written back to the profile store:
    suggestions into model_suggestions, and -- when standing consent plus a
    present add-applicable platform say so -- addition intents into
    model_additions with their suggestion closed.

    Per recommendation:
      already wired (any provider, exclusion-checked)   -> skipped
      platform allows + standing consent True           -> action "add"
      everything else                                   -> action "suggest"

    An older "suggest" record whose consent has since been granted is
    re-classified to "add" here -- consent flipping is exactly what the
    standing-consent half of the spec means to act on. Nothing in this
    function ever writes client configuration.
    """
    prof = profile if profile is not None else load_profile(config_dir)
    if prof.get("error") and not prof.get("providers"):
        prof = new_profile()
    records: List[Dict[str, Any]] = []
    if not gap_flag_enabled():
        return records
    resolve = _catalog_alias_resolver(catalog)
    all_norm: List[str] = []
    for entry in (prof.get("providers") or {}).values():
        if isinstance(entry, dict) and isinstance(entry.get("wired_models"), list):
            all_norm.extend(_norm_model_id(m) for m in entry["wired_models"])
    open_add = {r.get("alias"): r for r in _addition_rows(prof)}
    open_sug = {r.get("alias"): r for r in _suggestion_rows(prof)}
    consent = has_model_add_consent(profile=prof)
    changed = False
    for rec in recommended_models():
        alias = rec["alias"]
        patterns = list(rec["patterns"])
        if resolve:
            extra = resolve(alias)
            if extra:
                patterns = list(extra)
            # an unresolvable alias keeps the built-in matching metadata: a
            # catalog that cannot answer is never evidence of a gap and
            # never evidence of a match -- matching falls back, it does not
            # invent either.
        patterns_norm = [_norm_model_id(p) for p in patterns]
        excludes_norm = [_norm_model_id(x) for x in rec["excludes"]]
        if alias in open_add:
            continue  # an addition intent already exists (pending/confirmed)
        if _wired_covers(all_norm, patterns_norm, excludes_norm):
            continue  # satisfied somewhere -- not a gap
        providers_ok = [p for p in rec["providers"] if _provider_present(prof, p)]
        addable = (consent is True
                   and any(p in _ADD_APPLICABLE_PROVIDERS for p in providers_ok))
        record: Dict[str, Any] = {
            "alias": alias,
            "label": rec["label"],
            "evaluated_at": _now(),
            "providers_available": providers_ok,
            "consent_add_models": consent,
            "action": "add" if addable else "suggest",
            "what_it_unlocks": rec["unlocks"],
            "cost": rec["cost"],
        }
        record["suggestion_text"] = (
            f"You don't have {rec['label']} wired. {rec['unlocks']}. "
            f"Cost: {rec['cost']}. "
            + ("You gave standing consent to add recommended models: it is "
               "recorded for addition and the next probe will confirm it."
               if addable else
               "If you want it, approve the suggestion and it will be added "
               "and re-probed.")
        )
        if addable:
            row = _record_addition(
                prof, alias=alias, label=rec["label"],
                providers=[p for p in providers_ok
                           if p in _ADD_APPLICABLE_PROVIDERS],
                approved_by=f"standing consent ({(prof.get('consent') or {}).get('add_models_source', 'recorded')})")
            record["addition"] = dict(row)
            open_add[alias] = row
            changed = True
        elif alias not in open_sug:
            if persist:
                prof.setdefault("model_suggestions", []).append(record)
                open_sug[alias] = record
                changed = True
        records.append(redact_record(record))
    if persist and changed and profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return records


def apply_model_additions(alias: Optional[str] = None,
                          approved_by: str = "client approval",
                          profile: Optional[Dict[str, Any]] = None,
                          catalog: Any = None,
                          config_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The explicit approval entry: record addition intents now for gap
    aliases the analysis says are add-eligible (optionally narrowed to one
    alias), carrying WHO approved. Requires standing consent -- without it
    there is nothing "add where standing consent exists" to act on, and
    this raises rather than inventing consent. NEVER touches client
    configuration: rows are intent records with config_written False."""
    prof = profile if profile is not None else load_profile(config_dir)
    if not gap_flag_enabled():
        return []
    if has_model_add_consent(profile=prof) is not True:
        raise PermissionError(
            "refusing to add models: no standing consent on this profile "
            "(consent.add_models is not True); record_model_consent() must "
            "carry an explicit client answer first")
    # re-evaluate with the approval recorded as the audit source
    analyze_model_gaps(profile=prof, catalog=catalog, persist=True)
    applied: List[Dict[str, Any]] = []
    for row in _addition_rows(prof):
        if row.get("status") != "added_pending_probe":
            continue
        if alias is not None and row.get("alias") != alias:
            continue
        row["approved_at"] = _now()
        row["approved_by"] = f"{row.get('approved_by', 'standing consent')} + {approved_by}"
        applied.append(redact_record(dict(row)))
    if applied and profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return applied


def approve_model_suggestion(alias: str, approved_by: str = "client",
                             profile: Optional[Dict[str, Any]] = None,
                             catalog: Any = None,
                             config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """On approval of ONE suggestion: add it (the spec's "add on approval").
    The approval covers that alias only -- it never flips the standing
    consent flag. A suggestion whose platform is NOT present cannot be
    wired into the client's own account at all: approving it records an
    operator-provisioning hand-off row instead of pretending an add was
    possible. Returns the addition row, or None when no such suggestion is
    open."""
    prof = profile if profile is not None else load_profile(config_dir)
    if not gap_flag_enabled():
        return None
    sug = next((r for r in _suggestion_rows(prof) if r.get("alias") == alias), None)
    if sug is None:
        return None
    prof["model_suggestions"] = [s for s in _suggestion_rows(prof)
                                 if s.get("alias") != alias]
    present_ok = [p for p in (sug.get("providers_available") or [])
                  if p in _ADD_APPLICABLE_PROVIDERS]
    if not present_ok:
        row = {
            "alias": alias, "label": sug.get("label"),
            "providers": [],
            "status": "approved_needs_provisioning",
            "approved_by": str(approved_by), "approved_at": _now(),
            "reprobe_required": True, "config_written": False,
            "note": ("approved, but no detected account can carry this "
                     "model -- operator provisioning required"),
        }
        prof.setdefault("model_additions", []).append(row)
    else:
        row = _record_addition(prof, alias=alias,
                               label=sug.get("label") or alias,
                               providers=present_ok,
                               approved_by=f"approval of suggestion ({approved_by})")
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return redact_record(dict(row))


def confirm_added_models(probe_result: Optional[Dict[str, Any]] = None,
                         detection: Optional[Dict[str, Any]] = None,
                         catalog: Any = None,
                         profile: Optional[Dict[str, Any]] = None,
                         config_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The re-probe half of the add path: after FIX 9 probes run again,
    flip "added_pending_probe" rows to "confirmed" once the fresh inventory
    shows the alias wired (accepts the raw probe_providers() result, a
    single apply_probe_refresh-style detection dict, or the already-
    refreshed profile -- all three update the same store first). Returns
    the rows that are now confirmed."""
    prof = profile if profile is not None else load_profile(config_dir)
    if not gap_flag_enabled():
        return []
    if probe_result is not None:
        prof = store_provider_probes(probe_result, profile=prof)
    if detection is not None:
        prof = apply_probe_refresh(detection, profile=prof)
    resolve = _catalog_alias_resolver(catalog)
    all_norm: List[str] = []
    for entry in (prof.get("providers") or {}).values():
        if isinstance(entry, dict) and isinstance(entry.get("wired_models"), list):
            all_norm.extend(_norm_model_id(m) for m in entry["wired_models"])
    confirmed: List[Dict[str, Any]] = []
    for row in _addition_rows(prof):
        if row.get("status") not in ("added_pending_probe",
                                     "approved_needs_provisioning"):
            continue
        rec = next((r for r in RECOMMENDED_PRESENTATION_MODELS
                    if r["alias"] == row.get("alias")), None)
        if rec is None:
            continue
        patterns = list(rec["patterns"])
        if resolve:
            patterns = list(resolve(rec["alias"]) or patterns)
        excludes = [_norm_model_id(x) for x in (rec.get("excludes") or ())]
        # a needs-provisioning row confirms only when a model showed up on
        # a provider it previously had none of -- same matcher, either way
        if _wired_covers(all_norm, [_norm_model_id(p) for p in patterns],
                         excludes):
            row["status"] = "confirmed"
            row["confirmed_at"] = _now()
            row["reprobe_required"] = False
            confirmed.append(redact_record(dict(row)))
    if confirmed and profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return confirmed


def open_gap_records(profile: Optional[Dict[str, Any]] = None,
                     config_dir: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """The intake/notification surface for FIX 10: every open suggestion
    and every addition still awaiting its re-probe, so the agent can ask
    once in plain language instead of inventing a second interview."""
    prof = profile if profile is not None else load_profile(config_dir)
    return {
        "suggestions": [r for r in _suggestion_rows(prof)
                        if isinstance(r, dict)],
        "additions_pending_probe": [r for r in _addition_rows(prof)
                                    if r.get("reprobe_required")],
    }


# ---------------------------------------------------------------------------
# PRES-015 -- profile reconciliation: DECLARED facts vs DERIVED facts.
# Spec step 4: "version client declarations, entitlements, reserves and
# derived provider facts separately; reconcile only derived facts."
#
# The classes, on one provider entry:
#   DECLARED (client/operator statements -- reconciliation NEVER touches):
#       provider, plan_tier, plan_known, consented, locked, answered_at,
#       locked_choice, ceiling_source in {"interview", "declared",
#       "conservative-default"}, max_concurrent (the explicit allocation),
#       model_plan, creative_prefs, notes, wired_models.
#   DERIVED (machine projections of the current cap table / probes --
#       reconciliation may refresh these, and ONLY these):
#       concurrency_ceiling when ceiling_source is "cap-table" or "probe"
#       (derived FROM plan_tier by CAP_TABLE), plus the reconciliation
#       stamp itself.
# A tier change that used to drop an explicit max_concurrent (the PRES-044
# defect class) cannot happen here: max_concurrent is a DECLARED field and
# the derived write below merges around it.
# ---------------------------------------------------------------------------

#: Entry keys whose values are CLIENT/OPERATOR statements. Reconciliation
#: never writes them; unknown root keys and unknown provider keys are
#: preserved the same way (the merge is additive, never a rebuild).
_DECLARED_ENTRY_KEYS = frozenset({
    "provider", "plan_tier", "plan_known", "consented", "locked",
    "locked_choice", "answered_at", "max_concurrent",
    "ceiling_source_declared", "model_plan", "creative_prefs", "notes",
})

#: ceiling_source values that mark concurrency_ceiling as DERIVED (safe to
#: refresh from the current cap table). "interview"/"declared"/
#: "conservative-default" ceilings are statements -- never overwritten.
_DERIVED_CEILING_SOURCES = frozenset({"cap-table", "probe"})

#: The reconciliation marker stamped on the entry (not a decision field:
#: diagnostics only).
RECONCILE_SOURCE = "reconcile"


def _entry_declared_keys(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of one provider entry that reconciliation must preserve
    verbatim -- every key that is NOT a known derived projection. Unknown
    keys (operator metadata, future fields) land here too: preservation is
    the default, overwriting needs a reason."""
    derived = {"ceiling_source", "concurrency_ceiling", "detected"}
    out = {}
    for key, value in entry.items():
        if key in derived and key in ("ceiling_source",):
            # ceiling_source IS the classifier -- keep it (it says whether the
            # ceiling beside it is a statement or a projection) but do not
            # count it as an untouchable declaration when it marks a derived
            # ceiling.
            if value in _DERIVED_CEILING_SOURCES:
                continue
            out[key] = value
        elif key in derived:
            continue
        else:
            out[key] = value
    return out


def reconcile_profile(declarations: Dict[str, Any],
                      config_dir: Optional[Path] = None,
                      *,
                      profile: Optional[Dict[str, Any]] = None,
                      ) -> Dict[str, Any]:
    """Fold DERIVED provider facts (cap-table ceilings for the CURRENT
    plan_tier) into the store WITHOUT touching any declared field.

    `declarations` is the one-revision client picture reconcile callers
    hold (the same shape load_profile() returns: {"providers": {...}}).
    Only entries whose ceiling_source marks the ceiling DERIVED are
    refreshed, and only to what the CURRENT CAP_TABLE says for the entry's
    CURRENT (provider, plan_tier) -- a tier change flows through, an
    explicit max_concurrent does not.

    Idempotent by construction: running it twice over the same inputs
    yields the same document (the second run refreshes the same derived
    values to the same numbers and re-stamps reconcile_at). Explicit
    reserve/allocation fields (`max_concurrent`) and unknown fields
    (`operator_notes`, future keys) survive untouched -- the PRES-044
    acceptance, asserted by the PRES-015 tests. Never raises on a broken
    store: a read error degrades to "reconciled nothing" with the reason.

    With `profile` given, THAT dict is reconciled and returned WITHOUT
    persisting (the pure half a caller with its own transaction uses);
    without it, the on-disk store is read, reconciled and saved under the
    store's own process lock (the PRES-044 single-lock contract)."""
    try:
        base = profile if profile is not None else load_profile(config_dir)
    except Exception as exc:  # noqa: BLE001 -- a broken store never blocks
        return {"reconciled": False, "reason": f"load failed: "
                f"{exc.__class__.__name__}: {exc}"}
    if not isinstance(base, dict) or base.get("error"):
        return {"reconciled": False,
                "reason": str(base.get("error") or "profile-not-a-dict")}
    if not flag_enabled() and profile is None:
        return {"reconciled": False, "reason": "flag-disabled"}
    changed: List[str] = []
    providers = base.setdefault("providers", {})
    decl_providers = (declarations or {}).get("providers") or {}
    for provider_id, decl in decl_providers.items():
        if not isinstance(decl, dict):
            continue
        entry = providers.get(provider_id)
        if not isinstance(entry, dict):
            # A declared provider the store has never heard of is NOT
            # invented here: reconciliation folds derived facts INTO
            # existing entries, it does not create clients.
            continue
        # Preserve EVERY declared/unknown key verbatim.
        preserved = _entry_declared_keys(entry)
        source = entry.get("ceiling_source")
        if source not in _DERIVED_CEILING_SOURCES:
            # The ceiling on this entry is a statement (or there is none):
            # nothing derived to refresh. Preserve the entry whole.
            continue
        norm_provider = (_capacity.normalize_provider(provider_id)
                         if _capacity is not None else provider_id)
        norm_plan = (decl.get("plan_tier") or entry.get("plan_tier"))
        if _capacity is not None and norm_provider:
            norm_plan = _capacity.normalize_plan(norm_plan, norm_provider)
        if _capacity is not None and norm_provider and norm_plan \
                and (norm_provider, norm_plan) in _capacity.CAP_TABLE:
            derived_ceiling = _capacity.CAP_TABLE[(norm_provider, norm_plan)]
            if entry.get("concurrency_ceiling") != derived_ceiling:
                entry["concurrency_ceiling"] = derived_ceiling
                changed.append(f"{provider_id}: ceiling -> {derived_ceiling}")
        # ceiling_source stays "cap-table"; the entry keeps every declared
        # field (plan_tier included) from BEFORE the fold.
        for key, value in preserved.items():
            entry.setdefault(key, value)
        entry[RECONCILE_SOURCE] = {
            "reconciled_at": _now(),
            "changed": bool(provider_id in changed
                            or any(c.startswith(f"{provider_id}:") for c in changed)),
        }
    if changed:
        base["reconcile_log"] = list(base.get("reconcile_log") or [])[-7:] + [
            {"at": _now(), "changes": changed}]
    if profile is not None:
        return {"reconciled": True, "persisted": False,
                "changes": changed, "profile": base}
    if not changed:
        # Nothing moved: still stamp diagnostics on the in-memory copy, but
        # skip the write (an idempotent no-op does not dirty the store).
        return {"reconciled": True, "persisted": False, "changes": []}
    try:
        save_profile(base, config_dir)
    except Exception as exc:  # noqa: BLE001 -- a failed write is visible, never silent
        return {"reconciled": True, "persisted": False,
                "write_error": f"{exc.__class__.__name__}: {exc}",
                "changes": changed}
    return {"reconciled": True, "persisted": True, "changes": changed}


# ---------------------------------------------------------------------------
# FIX-PLAN Item 17: fleet shapes as first-class profile values, the
# remembered system gauge, and the model-choice record.
#
# THREE additions, all additive (schema stays version 1; a profile written
# before this section simply lacks the new keys, and every reader below
# treats absence as "not recorded yet", never as a claim):
#
#   1. THE FLEET SHAPE (profile["fleet"]). The install's fleet shape is a
#      first-class remembered value with the EXACT labels Trevor's fleet
#      operates by -- fleet-mac, fleet-hostinger, fleet-contabo -- never
#      renamed. It is remembered the way the existing profile answers are:
#      asked ONCE, then locked (record_fleet_shape), and per decision D8
#      it is an account-level fact that carries over between runs. What
#      detection can settle on its own (fleet-mac on a Mac) is recorded as
#      a DETECTED, refreshable value; what it cannot (a Linux container is
#      fleet-hostinger OR fleet-contabo and nothing inside the container
#      says which) stays unrecorded until the one question is answered --
#      hardware_budget.detect_fleet_shape() returns the candidates and the
#      evidence, and this section never guesses between them.
#
#   2. THE SYSTEM GAUGE (profile["system_gauge"]). Gauging results --
#      MEASURED, from hardware_budget's snapshot and the capacity refresh
#      -- persist into the profile with the measurement date, so a second
#      run on the same box starts from measured truth instead of re-deriving
#      (or worse, re-asserting) it. A gauge is trusted only while it is
#      FRESH: gauge_status() reports missing / stale-age / shape-changed /
#      hardware-changed / fresh, and a stale or superseded gauge is
#      re-gauged, never trusted (record_system_gauge() overwrites it; the
#      locked fleet-shape answer is never touched by a re-gauge).
#
#   3. THE MODEL-CHOICE RECORD (profile["model_choices"]). Per provider
#      family, the profile records the client's SELECTED model or their
#      CONFIGURED DEFAULT (owner decision 4, 2026-10-13: select-or-default),
#      and separately every RECOMMENDATION the system showed, with its
#      reason and the client's response (offered / accepted / declined --
#      the record Item 18's honesty layer writes and Item 31's freshness
#      check reads). A recommendation is recorded as a recommendation
#      shown, NEVER as the selection: record_recommendation_shown() has
#      no code path that writes the selection field, and
#      effective_model_choice() reads the selection field only.
#
# Writers follow this module's store convention: hand a profile dict in
# and it is mutated in place (the caller's transaction saves); omit it and
# the function loads, writes and saves itself. All keys below were chosen
# to survive redact_record() (no secret-named substring anywhere -- see
# the KEY NAMING note on the model plan), and model_choices is a LIST of
# per-family rows, never a dict keyed by family, so a family name can
# never be dropped by the redaction filter either.
# ---------------------------------------------------------------------------

#: The fleet shapes, with Trevor's exact labels, in fleet order. Never
#: renamed, never extended silently: a fourth shape is an owner decision.
FLEET_SHAPES: tuple = ("fleet-mac", "fleet-hostinger", "fleet-contabo")

#: The install-time declaration channel for the shape (an installer or the
#: client states it once; the gauge records it as a declared answer). An
#: invalid value is ignored and noted in the gauge, never recorded.
FLEET_SHAPE_ENV = "PRESENTATION_FLEET_SHAPE"

#: Per-shape gauging defaults: what the shape MEANS for gauging, derived
#: from the code's existing per-environment behavior (hardware_budget's
#: readers and capacity's account model), not invented numbers.
#:   fleet-mac       -- native hardware read; live memory-pressure
#:                      monitoring matters most here (the Mac has no
#:                      cgroup to hide behind), so pressure is a live
#:                      signal, re-read every run, never a stored number.
#:                      The workflow expectation is Trevor's verified
#:                      reference profile for the shape (Mac Mini M4,
#:                      24 GB), recorded AS a reference -- it is an
#:                      expectation to gauge against, never a cap any
#:                      dispatch path consumes.
#:   fleet-hostinger -- container limits (cgroup) ARE the box budget:
#:                      single-tenant VPS, so no host ceiling is recorded
#:                      (there is no shared host to slice from).
#:   fleet-contabo   -- per-container budget under a SHARED host ceiling:
#:                      the gauge records BOTH the container budget and
#:                      the host ceiling it was sliced from, because
#:                      sibling containers contend for the same host.
#: Where the code cannot supply a shape's numbers (workflow expectations
#: for the container shapes), the value is None -- unknown, gauged live --
#: never an asserted number.
FLEET_SHAPE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "fleet-mac": {
        "memory_model": "native-hardware",
        "budget_derivation": ("native hardware read (total RAM, cores, "
                              "live memory pressure)"),
        "concurrency_posture": ("hardware-budget classes against the "
                                "box's own RAM and cores"),
        "pressure_monitoring": ("live: memory pressure is re-read every "
                                "run on a Mac; a stored pressure reading "
                                "is never trusted"),
        "workflow_expectations": {
            "reference_box": "Mac Mini M4, 24 GB",
            "agents_per_workflow": 10,
            "concurrent_workflows": 50,
            "basis": ("owner reference profile (Trevor, verified): a "
                      "reference to gauge against, not a dispatch cap"),
        },
    },
    "fleet-hostinger": {
        "memory_model": "container-cgroup",
        "budget_derivation": ("container limits (cgroup memory.max / "
                              "cpu.max) are the box budget"),
        "concurrency_posture": ("hardware-budget classes against the "
                                "container limit"),
        "pressure_monitoring": ("cgroup pressure (PSI) where the host "
                                "exposes it"),
        "workflow_expectations": None,
    },
    "fleet-contabo": {
        "memory_model": "container-under-shared-host",
        "budget_derivation": ("per-container budget (cgroup) under a "
                              "shared host ceiling; both recorded"),
        "concurrency_posture": ("hardware-budget classes against the "
                                "container limit; the host ceiling is "
                                "recorded because sibling containers "
                                "share it"),
        "pressure_monitoring": ("cgroup pressure (PSI) where the host "
                                "exposes it"),
        "workflow_expectations": None,
    },
}

#: The unknown-shape defaults block: every field says unknown, and the
#: gauge's job is to measure live instead of asserting. Returned (as a
#: copy) for an unrecorded or unrecognized shape.
_UNKNOWN_SHAPE_DEFAULTS: Dict[str, Any] = {
    "memory_model": "unknown",
    "budget_derivation": ("unknown shape: budgets come from the live "
                          "hardware reading alone"),
    "concurrency_posture": "unknown: gauge live",
    "pressure_monitoring": "unknown: gauge live",
    "workflow_expectations": None,
}


def fleet_shape_defaults(shape: Optional[str]) -> Dict[str, Any]:
    """The gauging defaults for one fleet shape (a copy). None or an
    unrecognized label yields the honest unknown block -- this function
    never asserts a shape's numbers the code cannot support."""
    known = FLEET_SHAPE_DEFAULTS.get(shape or "")
    if known is None:
        return dict(_UNKNOWN_SHAPE_DEFAULTS)
    out = dict(known)
    if isinstance(out.get("workflow_expectations"), dict):
        out["workflow_expectations"] = dict(out["workflow_expectations"])
    return out


def _hardware_module():
    """The hardware_budget module, or None (partial deploy). Its readers
    are the one definition of what this box measures; this section never
    re-implements a reading."""
    try:
        from . import hardware_budget as _hb  # package-relative
        return _hb
    except ImportError:  # pragma: no cover - direct file run
        try:
            import hardware_budget as _hb  # type: ignore[no-redef]
            return _hb
        except ImportError:
            return None


def _fleet_record(profile: Dict[str, Any]) -> Dict[str, Any]:
    rec = (profile or {}).get("fleet")
    return rec if isinstance(rec, dict) else {}


def fleet_shape(profile: Optional[Dict[str, Any]] = None,
                config_dir: Optional[Path] = None) -> Optional[str]:
    """The recorded fleet shape, or None when none is recorded. A recorded
    shape is a statement (an answer or a certain detection); None means
    the profile honestly does not know yet -- callers gauge live and, at
    the install/gauge moment, ask the one question."""
    prof = profile if profile is not None else load_profile(config_dir)
    shape = _fleet_record(prof).get("shape")
    return shape if shape in FLEET_SHAPES else None


def record_fleet_shape(shape: str, *, source: str = "interview",
                       config_dir: Optional[Path] = None,
                       profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """THE one fleet-shape answer -- persisted ONCE, then LOCKED, exactly
    like record_plan_answer.

    Raises ValueError on a label that is not one of the three fleet
    shapes: the labels are Trevor's, exact, and never renamed, so a
    near-miss spelling is refused rather than folded into a shape it is
    not. The FIRST answer decides and locks; a later call with a
    different shape is appended to the interview audit log
    (interview["fleet_shape"]) as an explicit re-record and DOES update
    the stored shape -- that later call is the operator/client action,
    never something a probe or a gauge performs on its own (detection
    refresh writes through record_system_gauge's detected path, which
    never overwrites a locked record)."""
    if shape not in FLEET_SHAPES:
        raise ValueError(
            f"refusing to record fleet shape {shape!r}: the fleet shapes "
            f"are {list(FLEET_SHAPES)} (exact labels, never renamed)")
    prof = profile if profile is not None else load_profile(config_dir)
    existing = _fleet_record(prof)
    record = dict(existing)
    record["shape"] = shape
    record["source"] = str(source or "interview")
    record["recorded_at"] = _now()
    if not existing.get("locked"):
        record["locked"] = True
        record["answered_at"] = _now()
    prof["fleet"] = record
    interview = prof.setdefault("interview", {})
    interview.setdefault("fleet_shape", []).append(
        {"shape": shape, "source": record["source"], "answered_at": _now()})
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return prof


def fleet_shape_question(profile: Optional[Dict[str, Any]] = None,
                         detection: Optional[Dict[str, Any]] = None,
                         config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The one fleet-shape question the install still owes, or None.

    None when a shape is already recorded (asked once, never again) and
    None when detection settles the shape on its own (fleet-mac on a
    Mac). A question exists exactly when the box is a Linux container:
    detection proves the container, cannot prove WHICH container shape,
    and says so in the question text itself."""
    prof = profile if profile is not None else load_profile(config_dir)
    if fleet_shape(prof) is not None:
        return None
    det = detection
    if det is None:
        hb = _hardware_module()
        if hb is not None:
            try:
                det = hb.detect_fleet_shape()
            except Exception:  # noqa: BLE001 -- detection never breaks intake
                det = None
    if isinstance(det, dict) and det.get("certain") and det.get("shape"):
        return None  # detection settles it; the gauge records it
    candidates = []
    if isinstance(det, dict):
        candidates = [c for c in (det.get("candidates") or [])
                      if c in FLEET_SHAPES]
    if not candidates:
        candidates = list(FLEET_SHAPES)
    if len(candidates) == len(FLEET_SHAPES):
        text = ("Which fleet shape is this install? fleet-mac (your own "
                "Mac, OpenClaw running natively), fleet-hostinger (your "
                "own Hostinger VPS, OpenClaw in Docker), or fleet-contabo "
                "(a container on the shared Contabo host). Detection "
                "could not settle it from this box.")
    else:
        text = ("This install runs in a Linux container, which is one of "
                "two fleet shapes, and nothing readable from inside the "
                "container says which: fleet-hostinger (your own "
                "Hostinger VPS, OpenClaw in Docker) or fleet-contabo (a "
                "container sliced from the shared Contabo host). Which "
                "one is this?")
    return {
        "id": "fleet_shape",
        "question": text,
        "candidates": candidates,
        "asked_once_then_locked": True,
        "detection": redact_record(det) if isinstance(det, dict) else None,
    }


# ---------------------------------------------------------------------------
# The remembered system gauge
# ---------------------------------------------------------------------------
#: How long a persisted gauge stays trustworthy. The codebase's own
#: convention for a persisted measurement window is the rolling 24h used
#: by the heal budget and the forever-state flag (24h windows in heal.py
#: and auto_resume.py): long enough that a second run the next day starts
#: from measured truth, short enough that a quietly changed box is
#: re-measured within a day. The in-process caches are a different axis
#: (capacity.INVENTORY_TTL_S bounds a models list in memory;
#: hardware_budget.SNAPSHOT_TTL_S bounds a live snapshot) and are NOT
#: reused here: neither was ever a persisted-record window.
GAUGE_MAX_AGE_S = 24 * 3600.0


def _gauge_fingerprint(snap: Optional[Dict[str, Any]],
                       det: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The stable hardware facts a gauge is cut against. A later gauge
    check re-reads these live; any difference means the hardware changed
    and the old gauge describes a different box. Instantaneous readings
    (available RAM, load, pressure) are deliberately NOT fingerprint
    fields: they move minute to minute on the same box."""
    snap = snap if isinstance(snap, dict) else {}
    det = det if isinstance(det, dict) else {}
    signals = det.get("signals") if isinstance(det.get("signals"), dict) else {}
    return {
        "platform": snap.get("platform") or det.get("platform"),
        "ram_total_bytes": snap.get("ram_total_bytes"),
        "host_ram_bytes": det.get("host_ceiling_bytes") or signals.get("host_ram_bytes"),
        "cgroup_limit_bytes": det.get("container_budget_bytes")
        if det.get("container_budget_bytes") is not None
        else signals.get("cgroup_limit_bytes"),
        "cores": snap.get("cores"),
    }


def _normalize_capacity_reading(reading: Any) -> Optional[Dict[str, Any]]:
    """One capacity reading (a capacity.resolve_capacity()/probe()-shaped
    dict) -> the compact row the gauge persists. `available` keeps
    capacity's UNBOUNDED sentinel as the string "UNBOUNDED" (the profile
    is JSON; the sentinel itself is not serializable, and a magic integer
    would be a lie). Returns None for a reading that names no provider."""
    if not isinstance(reading, dict):
        return None
    provider = reading.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        return None
    available = reading.get("available", reading.get("dispatchable"))
    if _capacity is not None and _capacity.is_unbounded(available):
        available = "UNBOUNDED"
    elif isinstance(available, bool) or not isinstance(available, int):
        available = None
    factors = reading.get("account_factors") or {}
    row: Dict[str, Any] = {
        "provider": provider,
        "plan": reading.get("plan"),
        "status": reading.get("status"),
        "available": available,
    }
    if isinstance(factors, dict):
        if factors.get("account_limit") is not None:
            row["account_limit"] = factors["account_limit"]
        if factors.get("reserve") is not None:
            row["reserve"] = factors["reserve"]
    return row


def record_system_gauge(config_dir: Optional[Path] = None, *,
                        profile: Optional[Dict[str, Any]] = None,
                        capacity_readings: Optional[Any] = None,
                        snap: Optional[Dict[str, Any]] = None,
                        detection: Optional[Dict[str, Any]] = None,
                        measured_at: Optional[str] = None) -> Dict[str, Any]:
    """Measure this box once and REMEMBER the measurement in the profile.

    The gauge moment is install/gauge time (the resource_plan moment):
    hardware from hardware_budget.snapshot(), capacity from the capacity
    refresh (capacity_readings: one resolve_capacity()/probe() result or
    a list of them; omitted, the primary route's pure resolve_capacity()
    reading is taken -- zero discovery, per PRES-015). The fleet shape
    resolves in this order, and the order is the doctrine:

      1. a shape already recorded on the profile (an answer or an
         earlier gauge) -- a re-gauge NEVER unsettles it;
      2. an install-time declaration ($PRESENTATION_FLEET_SHAPE with a
         valid exact label) -- recorded as a declared, locked answer;
      3. a CERTAIN detection (fleet-mac) -- recorded as detected;
      4. otherwise the shape stays unrecorded (None): the gauge carries
         the detection candidates and fleet_shape_question() still owes
         the client its one question.

    Per-shape budget derivation (Item 17): fleet-mac records the native
    totals and no container budget; fleet-hostinger records the
    container (cgroup) budget as the box budget and no host ceiling
    (single-tenant); fleet-contabo records BOTH the container budget and
    the host ceiling it was sliced from. An unmeasured reading records
    None (unknown), never a filled-in number. Returns the gauge record
    (also persisted at profile["system_gauge"])."""
    prof = profile if profile is not None else load_profile(config_dir)
    hb = _hardware_module()
    det = detection
    if det is None and hb is not None:
        try:
            det = hb.detect_fleet_shape()
        except Exception:  # noqa: BLE001 -- measurement must never raise here
            det = None
    det = det if isinstance(det, dict) else {}
    snapshot = snap
    if snapshot is None and hb is not None:
        try:
            snapshot = hb.snapshot()
        except Exception:  # noqa: BLE001
            snapshot = None
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    notes: List[str] = []

    # --- the fleet shape, in doctrine order -------------------------------
    shape = fleet_shape(prof)
    shape_source = _fleet_record(prof).get("source") if shape else None
    if shape is None:
        env_shape = (os.environ.get(FLEET_SHAPE_ENV) or "").strip()
        if env_shape:
            if env_shape in FLEET_SHAPES:
                record_fleet_shape(env_shape, source="declared",
                                   profile=prof)
                shape = env_shape
                shape_source = "declared"
            else:
                notes.append(
                    f"{FLEET_SHAPE_ENV}={env_shape!r} is not one of "
                    f"{list(FLEET_SHAPES)}; ignored, never recorded")
    if shape is None and det.get("certain") and det.get("shape") in FLEET_SHAPES:
        record = {
            "shape": det["shape"],
            "source": "detected",
            "locked": False,
            "recorded_at": _now(),
            "candidates": list(det.get("candidates") or [det["shape"]]),
            "evidence": list(det.get("evidence") or []),
        }
        prof["fleet"] = record
        shape = det["shape"]
        shape_source = "detected"

    # --- per-shape budget derivation --------------------------------------
    cgroup_limit = det.get("container_budget_bytes")
    host_total = det.get("host_ceiling_bytes")
    ram_total = snapshot.get("ram_total_bytes")
    container_budget: Optional[int] = None
    host_ceiling: Optional[int] = None
    if shape == "fleet-mac":
        host_ceiling = ram_total if ram_total is not None else host_total
    elif shape == "fleet-contabo":
        container_budget = cgroup_limit
        host_ceiling = host_total
        if container_budget is None:
            notes.append("fleet-contabo recorded but no cgroup container "
                         "limit was readable: container budget unknown, "
                         "gauged live, never filled in from the host total")
    elif shape == "fleet-hostinger":
        container_budget = cgroup_limit if cgroup_limit is not None else ram_total
        # single-tenant: no shared host ceiling exists to record (Item 17
        # names the both-numbers record for fleet-contabo only)
        host_ceiling = None
    else:
        # unknown shape: record the raw readings, assert no derivation
        container_budget = cgroup_limit
        host_ceiling = host_total

    budgets: Dict[str, Any] = {}
    raw_budgets = snapshot.get("budgets") or {}
    if isinstance(raw_budgets, dict):
        for cls, row in raw_budgets.items():
            if isinstance(row, dict) and isinstance(row.get("budget"), int):
                budgets[cls] = row["budget"]

    readings: List[Dict[str, Any]] = []
    if capacity_readings is None:
        if _capacity is not None:
            try:
                primary = _capacity.resolve_capacity(config_dir=config_dir)
                row = _normalize_capacity_reading(primary)
                if row is not None:
                    readings.append(row)
            except Exception:  # noqa: BLE001 -- a broken capacity read is a note
                notes.append("capacity reading unavailable at gauge time")
    else:
        items = capacity_readings if isinstance(capacity_readings, list) \
            else [capacity_readings]
        for item in items:
            row = _normalize_capacity_reading(item)
            if row is not None:
                readings.append(row)

    gauge: Dict[str, Any] = {
        "fleet_shape": shape,
        "shape_source": shape_source,
        "shape_candidates": ([] if shape else
                             [c for c in (det.get("candidates") or [])
                              if c in FLEET_SHAPES]),
        "measured_at": measured_at or _now(),
        "max_age_s": GAUGE_MAX_AGE_S,
        "fingerprint": _gauge_fingerprint(snapshot, det),
        "hardware": {
            "status": snapshot.get("status"),
            "ram_total_bytes": ram_total,
            "ram_available_bytes_at_measure": snapshot.get("ram_available_bytes"),
            "cores": snapshot.get("cores"),
            "cgroup": snapshot.get("cgroup"),
            "container_budget_bytes": container_budget,
            "host_ceiling_bytes": host_ceiling,
        },
        "budgets": budgets,
        "providers": readings,
        "defaults_applied": fleet_shape_defaults(shape),
        "notes": notes,
    }
    prof["system_gauge"] = gauge
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return redact_record(gauge)


def system_gauge(profile: Optional[Dict[str, Any]] = None,
                 config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The persisted gauge record, or {} when this box was never gauged."""
    prof = profile if profile is not None else load_profile(config_dir)
    gauge = (prof or {}).get("system_gauge")
    return gauge if isinstance(gauge, dict) else {}


def _parse_iso_epoch(text: Any) -> Optional[float]:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def gauge_status(profile: Optional[Dict[str, Any]] = None,
                 config_dir: Optional[Path] = None, *,
                 live_fingerprint: Optional[Dict[str, Any]] = None,
                 now_s: Optional[float] = None) -> Dict[str, Any]:
    """Is the persisted gauge still trustworthy? One of:

      missing          -- no gauge (or no measurement date) on the profile;
      shape-changed    -- the recorded fleet shape no longer matches the
                          shape the gauge was cut under;
      hardware-changed -- a fingerprint field (platform, host RAM, cgroup
                          limit, cores) now reads differently live: the
                          gauge describes a different box;
      stale-age        -- older than GAUGE_MAX_AGE_S;
      fresh            -- same shape, same hardware, inside the window:
                          a run may start from this measured truth.

    Only fields BOTH sides actually measured are compared -- an unreadable
    live value never proves a change (the verify-before-asserting rule).
    `live_fingerprint` is injectable so the check is testable without a
    second box; omitted, it is read live from hardware_budget."""
    prof = profile if profile is not None else load_profile(config_dir)
    gauge = system_gauge(prof)
    if not gauge or not gauge.get("measured_at"):
        return {"state": "missing", "gauge_present": False, "age_s": None,
                "max_age_s": GAUGE_MAX_AGE_S,
                "detail": "no system gauge recorded on this profile"}
    measured_epoch = _parse_iso_epoch(gauge.get("measured_at"))
    now_epoch = now_s if now_s is not None else datetime.now(timezone.utc).timestamp()
    age_s = (now_epoch - measured_epoch) if measured_epoch is not None else None

    recorded_shape = fleet_shape(prof)
    gauge_shape = gauge.get("fleet_shape")
    if recorded_shape and gauge_shape and recorded_shape != gauge_shape:
        return {"state": "shape-changed", "gauge_present": True,
                "age_s": age_s, "max_age_s": GAUGE_MAX_AGE_S,
                "detail": (f"gauge was cut under {gauge_shape!r} but the "
                           f"profile now records {recorded_shape!r}: "
                           "re-gauge")}

    live = live_fingerprint
    if live is None:
        hb = _hardware_module()
        if hb is not None:
            try:
                live = _gauge_fingerprint(hb.cached_snapshot(),
                                          hb.detect_fleet_shape())
            except Exception:  # noqa: BLE001 -- an unreadable box is not a change
                live = None
    if isinstance(live, dict):
        stored_fp = gauge.get("fingerprint") or {}
        changed = [field for field in ("platform", "host_ram_bytes",
                                       "cgroup_limit_bytes", "cores")
                   if stored_fp.get(field) is not None
                   and live.get(field) is not None
                   and stored_fp.get(field) != live.get(field)]
        if changed:
            return {"state": "hardware-changed", "gauge_present": True,
                    "age_s": age_s, "max_age_s": GAUGE_MAX_AGE_S,
                    "detail": ("fingerprint field(s) changed since the "
                               f"gauge: {changed}: re-gauge")}

    if age_s is None or age_s > GAUGE_MAX_AGE_S:
        return {"state": "stale-age", "gauge_present": True,
                "age_s": age_s, "max_age_s": GAUGE_MAX_AGE_S,
                "detail": ("gauge is older than the persisted-measurement "
                           "window (GAUGE_MAX_AGE_S): re-gauge, do not "
                           "trust it as measured truth")}
    return {"state": "fresh", "gauge_present": True, "age_s": age_s,
            "max_age_s": GAUGE_MAX_AGE_S,
            "detail": "gauge is fresh: same shape, same hardware, inside "
                      "the window"}


def needs_regauge(profile: Optional[Dict[str, Any]] = None,
                  config_dir: Optional[Path] = None, **kwargs: Any) -> bool:
    """True unless gauge_status says "fresh". A missing, stale, or
    superseded gauge is re-gauged, not trusted."""
    return gauge_status(profile, config_dir, **kwargs)["state"] != "fresh"


# ---------------------------------------------------------------------------
# The model-choice record (per provider family)
# ---------------------------------------------------------------------------
#: Where a recorded selection came from: the client selected the model,
#: or their configured default applies. There is no third value -- in
#: particular there is no "recommended" source, because a recommendation
#: is guidance, never a selection (owner decision 4).
MODEL_CHOICE_SOURCES: tuple = ("selected", "configured-default")

#: The response vocabulary on a recommendation row (Item 18 records the
#: recommendation as offered / accepted / declined in the profile).
RECOMMENDATION_RESPONSES: tuple = ("offered", "accepted", "declined")


def _family_token(provider_family: Any) -> str:
    """Fold a provider-family spelling onto the one canonical token
    (capacity.canonical_provider_token when the sibling module is
    importable), so 'OpenRouter' and 'openrouter' are one family."""
    if _capacity is not None:
        token = _capacity.canonical_provider_token(provider_family)
        if token:
            return token
    text = str(provider_family or "").strip().lower()
    return text.replace("_", "-").replace(" ", "-")


def _model_choice_rows(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = (profile or {}).get("model_choices")
    return rows if isinstance(rows, list) else []


def _find_choice_row(profile: Dict[str, Any],
                     family: str) -> Optional[Dict[str, Any]]:
    for row in _model_choice_rows(profile):
        if isinstance(row, dict) and row.get("provider_family") == family:
            return row
    return None


def record_model_choice(provider_family: str, model: str, *,
                        source: str = "selected",
                        config_dir: Optional[Path] = None,
                        profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record THE selection for one provider family: the model the client
    selected, or their configured default when source="configured-default".

    This is the ONLY writer of a row's selection. It refuses (ValueError)
    an empty model, an empty family, or a source outside
    MODEL_CHOICE_SOURCES -- a recommendation can never be written here,
    because "recommended" is not a source this function accepts. Any
    recommendations already shown for the family are preserved verbatim:
    recording a selection does not rewrite the guidance history."""
    family = _family_token(provider_family)
    model = str(model or "").strip()
    if not family:
        raise ValueError("refusing to record a model choice with no "
                         "provider family")
    if not model:
        raise ValueError(
            f"refusing to record an empty model as the {family} "
            "selection: silence is not a selection")
    if source not in MODEL_CHOICE_SOURCES:
        raise ValueError(
            f"refusing to record a model choice with source {source!r}: "
            f"a selection is the client's own ({MODEL_CHOICE_SOURCES[0]}) "
            f"or their configured default ({MODEL_CHOICE_SOURCES[1]}); a "
            "recommendation is guidance and is recorded with "
            "record_recommendation_shown(), never as a selection")
    prof = profile if profile is not None else load_profile(config_dir)
    row = _find_choice_row(prof, family)
    if row is None:
        row = {"provider_family": family, "selection": None,
               "recommendations_shown": []}
        prof.setdefault("model_choices", []).append(row)
    row["selection"] = {"model": model, "source": source,
                       "recorded_at": _now()}
    row["updated_at"] = _now()
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return redact_record(row)


def record_recommendation_shown(provider_family: str, model: str,
                                reason: str, *,
                                config_dir: Optional[Path] = None,
                                profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record that the system SHOWED a recommendation, with its reason.

    Appends to the family's recommendations_shown log with response
    "offered". This function has NO path to the row's selection: showing
    guidance never changes what the client selected, and a family with
    no selection yet keeps selection None with the recommendation
    recorded beside it."""
    family = _family_token(provider_family)
    model = str(model or "").strip()
    if not family or not model:
        raise ValueError("refusing to record a recommendation with no "
                         "provider family or no model")
    prof = profile if profile is not None else load_profile(config_dir)
    row = _find_choice_row(prof, family)
    if row is None:
        row = {"provider_family": family, "selection": None,
               "recommendations_shown": []}
        prof.setdefault("model_choices", []).append(row)
    shown = row.setdefault("recommendations_shown", [])
    entry = {"model": model, "reason": str(reason or ""),
             "shown_at": _now(), "response": "offered"}
    shown.append(entry)
    row["updated_at"] = _now()
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return redact_record(entry)


def record_recommendation_response(provider_family: str, model: str,
                                   response: str, *,
                                   config_dir: Optional[Path] = None,
                                   profile: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Record the client's response to a shown recommendation
    ("accepted" or "declined" -- Item 18's offered/accepted/declined
    record). Returns the updated recommendation row, or None when no
    matching recommendation was ever shown.

    Accepting a recommendation does NOT write the selection: the client's
    acceptance reaches the selection only through record_model_choice()
    when they actually select the model. Keeping the two writes separate
    is what makes "a recommendation never becomes a hidden prescription"
    a property of the code, not a promise."""
    if response not in ("accepted", "declined"):
        raise ValueError(
            f"refusing to record recommendation response {response!r}: "
            "the vocabulary is 'accepted' or 'declined' ('offered' is the "
            "state a recommendation starts in)")
    family = _family_token(provider_family)
    model = str(model or "").strip()
    prof = profile if profile is not None else load_profile(config_dir)
    row = _find_choice_row(prof, family)
    if row is None:
        return None
    target = None
    for entry in row.get("recommendations_shown") or []:
        if isinstance(entry, dict) and entry.get("model") == model:
            target = entry  # the LATEST showing of this model wins
    if target is None:
        return None
    target["response"] = response
    target["responded_at"] = _now()
    row["updated_at"] = _now()
    if profile is None and flag_enabled():
        save_profile(prof, config_dir)
    return redact_record(target)


def model_choice_row(provider_family: str,
                     profile: Optional[Dict[str, Any]] = None,
                     config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The full model-choice row for one provider family (selection plus
    the recommendations-shown log), or None when the family has no
    record at all."""
    prof = profile if profile is not None else load_profile(config_dir)
    row = _find_choice_row(prof, _family_token(provider_family))
    return redact_record(row) if row is not None else None


def effective_model_choice(provider_family: str,
                           profile: Optional[Dict[str, Any]] = None,
                           config_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The model that APPLIES for one provider family: the recorded
    selection ({model, source, recorded_at}) or None.

    Reads the selection field ONLY. A family whose record carries
    recommendations but no selection returns None -- the honest answer
    that no selection exists -- never the recommended model dressed up
    as one. This is the accessor Item 31's freshness check and Item 18's
    honesty layer read."""
    row = model_choice_row(provider_family, profile=profile,
                           config_dir=config_dir)
    if not row:
        return None
    selection = row.get("selection")
    return selection if isinstance(selection, dict) else None
