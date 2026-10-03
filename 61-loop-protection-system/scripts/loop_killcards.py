#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_killcards.py
# The responder's playbook (spec Section 4.2 + 6.3). Each Tier-1 fix class is a
# TESTED, REVERSIBLE, single-blast-radius kill card. The universal quarantine
# ladder (spec 4.1) is the order every fix follows:
#   1 silence the TIMER before the process   2 snapshot before any config touch
#   3 write as the box user, never root       4 restart via the sanctioned path
#   5 verify it STAYS fixed                    6 ledger + report
#
# DRY_RUN IS THE DEFAULT (spec 6.1): with armed=False every kill card PLANS and
# mutates NOTHING (D-DRYRUN proves the filesystem is byte-identical after a tick).
# Tier 2/3 NEVER auto-apply here - they return a prepared proposal for the operator
# / Rescue Rangers. The healer self-breaker is consulted before every apply: a
# target that has already been fixed >3x/24h, or whose last fix failed verify, is
# NOT auto-fixed again (the session-health.sh law).
#
# The mechanical actions are stdlib-only, deterministic, and operate on the paths
# they are handed (so drills exercise REAL mutations on SCRATCH fixtures). NO model
# call, NO network. Config-touching actions hard-refuse root.
# =============================================================================
"""loop_killcards.py - per-class kill cards for the Loop Protection System."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
import loop_breaker as BR  # noqa: E402

# The marker LF-10 stamps into an archived transcript's name. It is a MODULE
# CONSTANT because two places must agree on it and a drift between them is the
# runaway documented in D-POISON-REROLL: the producer (lf10_archive_and_roll_session)
# writes it, and the D5 collector (loop_watchdog._session_files) SKIPS any file
# carrying it. An archive that the collector re-measures is re-rolled every tick
# forever, so this string is the whole idempotence contract.
ARCHIVE_MARKER = ".loop-archive-"

# Longest single path COMPONENT the filesystem will accept, in BYTES (255 on APFS,
# HFS+, ext4, XFS, and every filesystem this skill ships to). A constructed name is
# bounded to this; a write that exceeds it raises OSError ENAMETOOLONG (errno 63 on
# macOS, 36 on Linux), which is a CRASH in a scheduled job, not a refusal.
NAME_MAX_BYTES = 255

# Bytes of the stem's sha256 kept when a name has to be truncated. 12 hex chars is
# 48 bits - collision-free in practice across one session directory - and it makes
# the truncation DETERMINISTIC: the same transcript always yields the same archive
# name, so a re-run is idempotent instead of piling up near-duplicates.
_STEM_DIGEST_CHARS = 12


def _truncate_utf8(text, max_bytes):
    """`text` shortened to at most `max_bytes` BYTES, never splitting a character.
    Deterministic. Byte-bounded (not character-bounded) because the filesystem
    limit is a byte limit - a 255-CHARACTER name of multi-byte characters is
    already too long."""
    raw = text.encode("utf-8")[:max(0, int(max_bytes))]
    return raw.decode("utf-8", "ignore")


def bounded_archive_name(stem, stamp, suffix, name_max=NAME_MAX_BYTES,
                         marker=ARCHIVE_MARKER):
    """The archive filename component for a transcript, BOUNDED to `name_max` bytes.

    A name is only ever rewritten when the natural one would not fit; in that case
    the stem is truncated and a short sha256 of the FULL stem is appended, so the
    result stays (a) inside the filesystem limit, (b) unique per source stem, and
    (c) DETERMINISTIC - the same input always produces the same name, which is what
    makes the roll idempotent rather than a source of near-duplicate archives.

    Returns the name only; the caller owns the directory."""
    tail = "%s%s%s" % (marker, stamp, suffix)
    budget = int(name_max) - len(tail.encode("utf-8"))
    if budget <= 0:
        # Pathological: the stamp+suffix alone will not fit. Emit the digest of the
        # whole intended name so the caller still gets a bounded, deterministic
        # component instead of an OSError.
        return _truncate_utf8(
            hashlib.sha256(("%s%s" % (stem, tail)).encode("utf-8")).hexdigest(),
            name_max)
    if len(stem.encode("utf-8")) <= budget:
        return "%s%s" % (stem, tail)
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:_STEM_DIGEST_CHARS]
    keep = budget - (len(digest) + 1)  # +1 for the '-' joiner
    if keep <= 0:
        return "%s%s" % (_truncate_utf8(digest, budget), tail)
    return "%s-%s%s" % (_truncate_utf8(stem, keep), digest, tail)


def fix_class_for(loop_class):
    """Resolve the fix-class entry (LF-*) whose loop_class field NAMES this loop class.
    Returns the entry dict or None (None => no Tier-1 auto-fix; propose/escalate)."""
    for fc in C.load_skill_config("fix-classes.json")["fix_classes"]:
        names = [n.strip() for n in str(fc.get("loop_class", "")).split("/")]
        if loop_class in names:
            return fc
    return None


def plan(finding, box="box", killcard_cmd=None):
    """Build the prepared kill card for a finding (pure). Returns a plan dict with the
    fix class, tier, the exact action, and the one-line revert. A fix that cannot be
    reverted in one line does not ship (spec 4.2)."""
    lc = finding.get("loop_class")
    fc = fix_class_for(lc)
    fid = finding.get("finding_id")
    revert = C.revert_command_for(fid if fid is not None else "<id>")
    if fc is None:
        return {"loop_class": lc, "fix_class": None, "tier": 3, "action": "propose-and-hold",
                "what": "no Tier-1 kill card for %s; escalate to Rescue Rangers" % lc,
                "revert_cmd": revert}
    return {"loop_class": lc, "fix_class": fc["id"], "tier": fc["tier"],
            "action": fc["title"], "what": fc["title"],
            "reversible_in": fc.get("reversible_in"),
            "revert_cmd": revert,
            "killcard_cmd": killcard_cmd or ("loop-companion.sh fix %s" % (fid if fid is not None else "<id>"))}


# --------------------------------------------------------------------------- #
# Mechanical actions (deterministic; operate on the paths handed to them).
# Each honors DRY_RUN (plan only) and returns a result dict.
# --------------------------------------------------------------------------- #
def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False


def lf1_archive_stale_lock(lock_path, dry_run=True):
    """LF-1: remove a stale lock ONLY after proving (by a REAL JSON parse) that its pid
    is dead. The session-health failure defines the safe version: never treat a JSON
    lock as a bare pid, and NEVER touch a live lock. Returns {applied, reason}."""
    p = Path(lock_path)
    if not p.is_file():
        return {"applied": False, "reason": "no lock file", "dry_run": dry_run}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        pid = data.get("pid") if isinstance(data, dict) else None
    except (ValueError, OSError):
        return {"applied": False, "reason": "lock not JSON-parseable; NOT touched (safe refusal)",
                "dry_run": dry_run}
    if _pid_alive(pid):
        return {"applied": False, "reason": "lock pid %s is ALIVE; never touch a live lock" % pid,
                "dry_run": dry_run}
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would archive dead-pid lock (pid %s)" % pid,
                "dry_run": True}
    archive = p.with_suffix(p.suffix + ".archived")
    shutil.move(str(p), str(archive))
    return {"applied": True, "reason": "archived dead-pid lock to %s" % archive,
            "dry_run": False, "revert": "mv %s %s" % (archive, p)}


def lf4_disable_cron(cron_file, cron_id, dry_run=True):
    """LF-4: disable a cron (enabled:false) - DISABLE, NEVER DELETE. Config-touching =>
    refuses root. Operates on a JSON file of {crons:[{id/name, enabled}]}. Reversible by
    setting enabled:true. Returns {applied, reason}."""
    C.refuse_root_for_config("disable-cron")
    p = Path(cron_file)
    data = json.loads(p.read_text(encoding="utf-8"))
    crons = data.get("crons", data if isinstance(data, list) else [])
    target = None
    for c in crons:
        if c.get("id") == cron_id or c.get("name") == cron_id:
            target = c
            break
    if target is None:
        return {"applied": False, "reason": "cron %s not found" % cron_id, "dry_run": dry_run}
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would set enabled=false on %s (never delete)"
                % cron_id, "dry_run": True}
    target["enabled"] = False
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"applied": True, "reason": "disabled cron %s (enabled=false; not deleted)" % cron_id,
            "dry_run": False,
            "revert": "set enabled=true on cron %s" % cron_id}


def lf2_rewind_offset(offset_file, dry_run=True):
    """LF-2: rewind a corrupted telegram getUpdates offset. When the stored
    lastUpdateId has advanced PAST the oldest pending update (a restart race, deaf
    inbound), rewind stored_offset to oldest_pending_update_id - 1 and record the new
    value. Reversible via the prior offset (snapshotted first). Operates on a JSON file
    {stored_offset, oldest_pending_update_id}. Returns {applied, reason, rewound_to}."""
    p = Path(offset_file)
    data = json.loads(p.read_text(encoding="utf-8"))
    stored = int(data.get("stored_offset", 0))
    oldest = int(data.get("oldest_pending_update_id", 0))
    if stored < oldest:
        return {"applied": False, "reason": "offset not advanced past pending; nothing to rewind",
                "dry_run": dry_run, "rewound_to": stored}
    target = oldest - 1
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would rewind %d -> %d + restart channel"
                % (stored, target), "dry_run": True, "rewound_to": target}
    prior = stored
    data["stored_offset"] = target
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"applied": True, "reason": "rewound offset %d -> %d (channel restart follows)"
            % (prior, target), "dry_run": False, "rewound_to": target,
            "revert": "restore stored_offset=%d" % prior}


def lf10_archive_and_roll_session(session_path, dry_run=True, min_idle_minutes=10,
                                  idle_minutes=None, now=None):
    """LF-10: ARCHIVE a loop-poisoned session transcript so the next turn on that
    session key starts clean. MOVE, NEVER DELETE - the transcript is renamed to a
    timestamped archive beside itself and the one-line revert moves it back.

    This is the STOCK fix. Every other kill card in this file changes the
    environment; this one is the only one that clears the CONTEXT, which is the
    thing that outlived three environment-level fixes during the incident this
    class exists for.

    THE LIVE-SESSION GUARD is the safety property that makes this auto-appliable:
    a transcript still being written is REFUSED outright. The watchdog never yanks
    a file out from under a running gateway - a burning session gets the P1 and the
    prepared abort (LF-9); only a QUIESCENT poisoned transcript is rolled. So the
    unattended tick can clear yesterday's wreckage without ever touching the
    conversation someone is having right now.

    Config-FREE: no client config, no model, no credential, blast radius of one
    file. Returns {applied, reason, archived_to, revert}."""
    p = Path(session_path)
    if not p.is_file():
        return {"applied": False, "reason": "no session transcript at that path",
                "dry_run": dry_run}
    if idle_minutes is None:
        try:
            ref = now if now is not None else datetime.now(timezone.utc).timestamp()
            idle_minutes = (ref - p.stat().st_mtime) / 60.0
        except OSError:
            return {"applied": False, "reason": "cannot stat transcript; refusing",
                    "dry_run": dry_run}
    if idle_minutes < float(min_idle_minutes):
        return {"applied": False,
                "reason": "REFUSED: transcript is LIVE (idle %.1fm < %sm). A running "
                          "session is never rolled from under the gateway; escalate "
                          "the P1 and abort the run instead (LF-9)."
                          % (idle_minutes, min_idle_minutes),
                "dry_run": dry_run}
    # ALREADY-ROLLED GUARD: an archive this kill card produced is never re-rolled.
    # The D5 collector skips these too, so this is the second of two independent
    # stops on the re-archive runaway (D-POISON-REROLL): one bad tick that hands
    # LF-10 an archive path cannot restart the chain.
    if ARCHIVE_MARKER in p.name:
        return {"applied": False,
                "reason": "path is ALREADY a loop archive (%s); refusing to re-archive "
                          "an archive - re-rolling one is the runaway this guard exists "
                          "for" % ARCHIVE_MARKER,
                "dry_run": dry_run}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # BOUNDED name: a long session id must not build a path component past the
    # filesystem's 255-byte limit. An over-long name is an OSError from shutil.move,
    # and an OSError out of an unattended tick kills the scheduled job.
    archive = p.with_name(bounded_archive_name(p.stem, stamp, p.suffix))
    if dry_run:
        return {"applied": False,
                "reason": "DRY_RUN: would archive the poisoned transcript to %s "
                          "(move, never delete) and let the next turn open a fresh one"
                          % archive.name,
                "dry_run": True, "archived_to": str(archive)}
    if archive.exists():
        return {"applied": False, "reason": "archive target already exists; refusing "
                                            "to overwrite", "dry_run": False}
    # A FILESYSTEM REFUSAL IS A REFUSAL, NEVER A CRASH. Read-only mount, vanished
    # parent, permissions, a name the bound still could not satisfy: every one of
    # these must come back as {applied: False} so the tick moves to the next
    # finding. A watchdog that dies on one bad file is worse than no watchdog.
    try:
        shutil.move(str(p), str(archive))
    except OSError as exc:
        return {"applied": False,
                "reason": "filesystem refused the archive move (%s: %s); transcript "
                          "left EXACTLY as found, nothing deleted"
                          % (type(exc).__name__, exc),
                "dry_run": False}
    return {"applied": True,
            "reason": "archived poisoned transcript to %s (moved, NOT deleted); the "
                      "next turn on this session key starts clean" % archive.name,
            "dry_run": False, "archived_to": str(archive),
            "revert": "mv %s %s" % (archive, p)}


def lf6_park_process(unit, ledger, dry_run=True, stop_fn=None):
    """LF-6: respond to a crash-looping process unit on a process-breaker trip.

    WHAT EACH CASE REALLY DOES (SKS-002 / Fix 4 - this card used to report `applied` after
    writing only a ledger flag):
      DRY RUN             executes NOTHING (no pm2, no ledger write).
      the OpenClaw gateway  ALERT-ONLY. Never stopped: October's built-in crash-loop breaker
                          already suppresses channel auto-start after 3 unclean boots in 5
                          minutes. Ledger flag + `parked-flag`, finding stays open.
      other pm2 unit      ARMED run: `pm2 stop <unit>` for real, state `stopped`; the revert
                          (`unpark`) runs `pm2 start <unit>`.
      no real stop worked state `parked-flag`: a ledger flag only, NOTHING stopped.
    Only a really-stopped unit returns applied=True. Never auto-respawns a parked unit.
    Returns {applied, state, stopped, reason}."""
    if dry_run:
        if BR.is_gateway_unit(unit):
            return {"applied": False, "dry_run": True, "state": None, "stopped": False,
                    "reason": "DRY_RUN: '%s' is the OpenClaw gateway - ALERT-ONLY, would never "
                              "stop it (nothing executed)" % unit}
        return {"applied": False, "dry_run": True, "state": None, "stopped": False,
                "reason": "DRY_RUN: would run `pm2 stop %s` (nothing executed)" % unit}
    r = BR.stop_and_park(unit, ledger, stop_fn=stop_fn)
    out = {"applied": bool(r["stopped"]), "dry_run": False, "state": r["state"],
           "stopped": bool(r["stopped"]), "reason": r["reason"]}
    if r["stopped"]:
        out["revert"] = "loop-companion.sh unpark %s" % unit  # runs `pm2 start %s`
    return out


def _agent_id_from_session_key(session_key):
    """Best-effort agentId extraction from a session key of the CONFIRMED
    live-box shape 'agent:<agentId>:<channel>:<mode>:<kind>:<chatId>' (real
    sample: 'agent:dept-master-orchestrator:telegram:default:direct:
    8606145708'). Falls back to the full session key when the shape doesn't
    match (never a crash, never a guess beyond this one documented
    convention) - the gateway RPC's `agentId` param is best-effort exactly
    like the RPC call itself; a wrong agentId degrades to the RPC returning
    an error/no-op, never a crash; the caller then records `parked-flag`
    (a ledger flag only) rather than claiming an abort."""
    parts = str(session_key).split(":")
    if len(parts) >= 2 and parts[0] == "agent":
        return parts[1]
    return str(session_key)


def _sessions_abort_via_gateway_rpc(session_key, timeout=10):
    """The native sessions.abort RPC, called via `openclaw gateway call
    sessions.abort --params '{"key":..., "agentId":...}'`.

    CONFIRMED on a live box (OpenClaw 2026.7.1-2, 2026-08-04): `openclaw
    sessions --help` lists ONLY cleanup / compact / export-trajectory / list -
    there is NO `sessions abort` CLI subcommand. The only real path is the
    generic gateway RPC caller (`openclaw gateway --help` -> `call  Call a
    Gateway method`). This exact form was independently exercised live and,
    against a session with no active run, returned
    {"ok":true,"abortedRunId":null,"status":"no-active-run"} - a documented
    SAFE no-op, so it is safe to call speculatively (the earlier
    `sessions abort` CLI form would have silently returned a non-zero exit on
    EVERY call - a defect that FAILED SOFT into never aborting anything while
    still reporting the fix as applied via the park; that is exactly the
    silent-no-op failure mode this skill exists to prevent, so the wrong
    command is corrected here, not left as a tolerated fallback).

    `LOOP_NO_PROBES=1` (the hermetic-test env seam every other subprocess
    probe in this skill honors) short-circuits to a no-op BEFORE any
    subprocess runs, so a caller that forgets to inject `abort_fn` still
    never touches a real gateway. On ANY OTHER miss (no binary, non-zero
    exit, bad JSON) returns {ok: False} - never a crash, and the caller then
    records `parked-flag` (NOT fixed): nothing was aborted."""
    if os.environ.get("LOOP_NO_PROBES", "") == "1":
        return {"ok": False}
    binpath = os.environ.get("OPENCLAW_BIN") or shutil.which("openclaw")
    if not binpath:
        return {"ok": False}
    # clearQueued is REQUIRED: abort alone leaves queued follow-ups, and a queued resend
    # restarts the work (OpenClaw docs/tools/subagents/operations.md). Boolean, not "true".
    params = json.dumps({"key": str(session_key),
                         "agentId": _agent_id_from_session_key(session_key),
                         "clearQueued": True})
    try:
        proc = subprocess.run(
            [binpath, "gateway", "call", "sessions.abort", "--params", params],
            capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"ok": False}
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return {"ok": False}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"ok": False}


def _rpc_signals_success_or_noop(result):
    """True when the sessions.abort RPC result is either a real success
    (ok:true with an abortedRunId) or the documented SAFE no-op (ok:true,
    abortedRunId:null, status:'no-active-run' - verified live: a session with
    nothing to abort). BOTH are 'the RPC did its job'; NEITHER is a failure,
    and neither should ever read as one downstream (no retry storm, no
    false-failed-fix in the ledger) - only the healer breaker (>3 fixes on
    the same target/24h, or any fix whose verify failed once) governs whether
    LF-12 fires again, never this result. Checks `status` independently of
    `ok` (not just as a fallback) so a differently-shaped future response
    that carries `status:"no-active-run"` without an explicit `ok` still
    reads as the documented safe no-op, never a failure."""
    if not isinstance(result, dict):
        return False
    if str(result.get("status") or "") == "no-active-run":
        return True
    return bool(result.get("ok"))


def lf12_abort_cross_run_resend(source_session_key, ledger, dry_run=True, abort_fn=None):
    """LF-12: abort the resending SOURCE session's in-flight run via the native
    `sessions.abort` RPC (`openclaw gateway call sessions.abort`) with `clearQueued: true`,
    breaking a confirmed cross-run resend loop (LP-A10) at its driver.

    WHAT EACH PART REALLY DOES (SKS-002 / Fix 4 - an earlier version credited the ledger
    park with ending the loop; the park is a visible-red status flag only):
      * `sessions.abort` cancels the session's active run (and its descendants).
      * `clearQueued: true` ALSO discards the session's queued follow-ups. It is REQUIRED:
        without it a queued resend restarts the work right after the abort
        (OpenClaw docs/tools/subagents/operations.md).
      * With NO active run the RPC is a documented safe no-op
        ({ok:true, abortedRunId:null, status:"no-active-run"}); nothing is aborted then.
      * The ledger PARK is a visible-red status flag. It stops nothing and pauses no session.
    The recorded state is `stopped` only when the RPC returned ok:true (it ran, even as the
    no-active-run no-op, and the follow-up queue was cleared). An unreachable/failed RPC is
    state `parked-flag`: a ledger flag only, the finding stays open, NOTHING was aborted.
    NEVER pkill node, NEVER restart the gateway - this touches ONLY the one session named.

    A 600s action cooldown (config/thresholds.json d7_cross_run_resend
    .action_cooldown_seconds) bounds how often this may re-fire on the SAME source: a
    second call inside the window is REFUSED, recorded via the ledger's digest/dedup
    primitive. `abort_fn` is injectable (default: the gateway-RPC probe) so tests never
    touch a real gateway. Returns {applied, state, reason}."""
    cooldown_key = "resend-cooldown|%s" % source_session_key
    cooldown_seconds = C.load_skill_config("thresholds.json")["d7_cross_run_resend"]["action_cooldown_seconds"]
    if dry_run:
        return {"applied": False,
                "reason": "DRY_RUN: would call sessions.abort (clearQueued=true) on '%s' - "
                          "no-op if nothing active; nothing executed" % source_session_key,
                "dry_run": True}
    if ledger.recent_digest(cooldown_key, cooldown_seconds / 3600.0):
        return {"applied": False,
                "reason": "action cooldown active on '%s' (< %ds since the last "
                          "abort; never re-fire the breaker faster than the "
                          "proven-safe cadence)" % (source_session_key, cooldown_seconds),
                "dry_run": False}
    fn = abort_fn or _sessions_abort_via_gateway_rpc
    try:
        result = fn(source_session_key)
    except Exception as exc:  # noqa: BLE001 - an RPC miss is data, never a crash
        result = {"ok": False, "error": str(exc)}
    BR.trip(source_session_key, "resend", ledger, park=True)
    ledger.record_digest("resend-cooldown", cooldown_key, payload="applied")
    if isinstance(result, dict) and str(result.get("status") or "") == "no-active-run":
        rpc_detail = ("no-active-run (documented safe no-op - nothing was running to "
                      "abort; queued follow-ups cleared)")
    elif _rpc_signals_success_or_noop(result):
        rpc_detail = ("aborted runId=%s; queued follow-ups cleared"
                      % (result.get("abortedRunId") if isinstance(result, dict) else None))
    else:
        rpc_detail = None
    if rpc_detail is None:
        return {"applied": False, "dry_run": False, "state": BR.STATE_PARKED_FLAG,
                "reason": "sessions.abort RPC on '%s' unreachable/unexpected: NOTHING was "
                          "aborted and queued follow-ups were NOT cleared. Recorded "
                          "state=parked-flag - a ledger flag only (it stops nothing); the "
                          "finding stays open" % source_session_key}
    return {"applied": True, "dry_run": False, "state": BR.STATE_STOPPED,
            "reason": "sessions.abort (clearQueued=true) on '%s' -> %s. The ledger park on "
                      "the source is a status flag only; it does not stop anything"
                      % (source_session_key, rpc_detail),
            "revert": "loop-companion.sh unpark %s" % source_session_key}


# --------------------------------------------------------------------------- #
# apply dispatch (honors DRY_RUN + the healer self-breaker)
# --------------------------------------------------------------------------- #
def apply(plan_dict, ledger, armed, executors, verify_failed_last=False):
    """Apply a prepared plan. Returns {status, detail, escalate}.
      status: 'planned' (DRY_RUN or tier>1), 'applied', 'refused', 'escalated'
    The healer self-breaker is consulted FIRST: a target fixed too often or whose last
    fix failed verify is NOT auto-fixed again - it escalates (spec 5.1)."""
    br = BR.load_breakers()
    unit = plan_dict.get("unit") or plan_dict.get("loop_class")
    tier = plan_dict.get("tier", 3)
    fc = plan_dict.get("fix_class")

    if tier != 1:
        return {"status": "planned", "detail": "tier %s -> proposal only (%s)"
                % (tier, "operator stamp" if tier == 2 else "propose-and-hold"),
                "escalate": tier == 3}

    tripped, why = BR.healer_breaker_trips(unit, ledger, br, verify_failed=verify_failed_last)
    if tripped:
        return {"status": "escalated", "detail": "healer breaker: %s" % why, "escalate": True}

    if not armed:
        # DRY_RUN observe-only: PLAN, mutate nothing.
        ex = executors.get(fc)
        detail = "DRY_RUN"
        if ex:
            r = ex(dry_run=True)
            detail = "DRY_RUN: %s" % r.get("reason", "")
        return {"status": "planned", "detail": detail, "escalate": False}

    ex = executors.get(fc)
    if ex is None:
        return {"status": "refused", "detail": "no executor wired for %s" % fc, "escalate": True}
    r = ex(dry_run=False)
    if r.get("applied"):
        return {"status": "applied", "detail": r.get("reason"), "escalate": False,
                "revert": r.get("revert"), "state": r.get("state")}
    # not applied (incl. `parked-flag`: a ledger flag only, nothing stopped) => the finding is
    # NOT marked fixed by the caller and stays open.
    return {"status": "refused", "detail": r.get("reason"), "escalate": False,
            "state": r.get("state")}


# --------------------------------------------------------------------------- #
# Operator-commanded execution of a prepared kill card by finding id (spec 9.1).
# An explicit `fix`/`approve` IS the operator's word for THIS finding, so the two
# config-FREE acts execute for real: LF-6 (`pm2 stop` of a looping pm2 unit; the gateway
# is alert-only) and LF-12 (`sessions.abort` with clearQueued=true). A finding is `fixed`
# ONLY when something was really stopped/aborted - a ledger flag alone is `parked-flag`.
# Every config-touching class (LF-1/2/4/5/7) and every Tier-2 config-shape change is
# PREPARED here (exact command + one-line revert) and applied ON-BOX via the maintenance
# path, NEVER auto-applied off-box: an honest hand-off, not a stub that claims success.
# --------------------------------------------------------------------------- #
def _record_response_outcome(ledger, finding_id, fc, unit, kc, r):
    """Ledger + response for an LF-6 / LF-12 result `r`. Three honest outcomes:
      applied (really stopped/aborted) -> fix recorded `applied`, finding `fixed`
      state `parked-flag` (flag only)  -> fix recorded `parked-flag`, finding left OPEN
      refused (cooldown etc.)          -> fix recorded `refused`, finding `escalated`"""
    applied = bool(r.get("applied"))
    flag_only = (not applied) and r.get("state") == BR.STATE_PARKED_FLAG
    outcome = "applied" if applied else (BR.STATE_PARKED_FLAG if flag_only else "refused")
    ledger.record_fix(finding_id, fc, unit=unit, what=kc.get("what"), verify_outcome=outcome,
                      revert_cmd=kc.get("revert_cmd"), dry_run=False)
    if applied:
        ledger.set_finding_state(finding_id, "fixed")
    elif not flag_only:
        ledger.set_finding_state(finding_id, "escalated")
    # flag_only: the finding is deliberately NOT touched - it stays open (never `fixed`).
    return {"ok": applied, "action": "fix", "fix_class": fc, "unit": unit,
            "applied": applied, "state": r.get("state"), "detail": r.get("reason"),
            "revert_cmd": kc.get("revert_cmd")}


def run_fix(ledger, finding_id, box="box", approve=False):
    """Execute (LF-6, LF-12) or prepare (everything else) the kill card for a finding.
    Returns (result_dict, exit_code) with the ledger exit contract (0/2/3)."""
    f = ledger.get_finding(finding_id)
    if not f:
        return {"ok": False, "reason": "finding %s not found in the ledger" % finding_id}, 3
    kc = plan({"loop_class": f.get("loop_class"), "finding_id": finding_id}, box=box)
    kc["unit"] = f.get("unit")
    fc = kc.get("fix_class")
    tier = kc.get("tier")
    if approve and tier != 2:
        return {"ok": False, "action": "reject",
                "reason": "approve is for a Tier-2 proposal; finding %s is tier %s"
                          % (finding_id, tier), "prepared": kc}, 2
    # config-FREE act: respond to the crash-looping process unit (LF-6). A pm2 unit is
    # really stopped; the gateway is alert-only; no real stop => `parked-flag`. The finding
    # is `fixed` ONLY when something was really stopped - NEVER for a ledger flag.
    if fc == "LF-6":
        unit = f.get("unit")
        if not unit:
            return {"ok": False, "reason": "finding %s carries no unit to park" % finding_id}, 2
        r = lf6_park_process(unit, ledger, dry_run=False)
        return _record_response_outcome(ledger, finding_id, fc, unit, kc, r), 0
    # config-FREE act: abort the resending session with clearQueued=true (LF-12, LP-A10).
    if fc == "LF-12":
        unit = f.get("unit")
        if not unit:
            return {"ok": False,
                    "reason": "finding %s carries no unit (source session) to abort" % finding_id}, 2
        r = lf12_abort_cross_run_resend(unit, ledger, dry_run=False)
        return _record_response_outcome(ledger, finding_id, fc, unit, kc, r), 0
    # no Tier-1 kill card at all -> propose-and-hold (Rescue Rangers).
    if fc is None:
        return {"ok": False, "action": "hold", "fix_class": None, "tier": tier,
                "reason": "no Tier-1 kill card for %s; propose-and-hold -> escalate to "
                          "Rescue Rangers" % f.get("loop_class"),
                "prepared": kc, "revert_cmd": kc.get("revert_cmd")}, 0
    # config-touching Tier-1 / Tier-2: PREPARE the exact command + revert; apply ON-BOX.
    verb = "approved-tier2" if approve else "prepared"
    return {"ok": True, "action": verb, "fix_class": fc, "tier": tier, "unit": f.get("unit"),
            "reason": "%s: fix class %s touches box config; apply ON-BOX via the maintenance "
                      "path (docker exec -u node on VPS), never auto-applied off-box. The exact "
                      "command + one-line revert are prepared below." % (verb, fc),
            "prepared": kc, "revert_cmd": kc.get("revert_cmd")}, 0


def self_test():
    # Hermetic: pm2/openclaw are reachable ONLY through injected stubs, whatever the caller's env.
    keys = ("LOOP_NO_PROBES", "LOOP_PM2_BIN", "OPENCLAW_BIN")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["LOOP_NO_PROBES"] = "1"
    os.environ.pop("LOOP_PM2_BIN", None)
    os.environ.pop("OPENCLAW_BIN", None)
    try:
        return _self_test_body()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _self_test_body():
    import tempfile
    print("[loop_killcards] self-test: plan, LF-1 lock, LF-4 cron, DRY_RUN byte-identical, healer breaker")
    from loop_ledger import Ledger

    # plan resolves a Tier-1 fix class for a known loop class
    p = plan({"loop_class": "LP-B1", "finding_id": 7})
    assert p["fix_class"] == "LF-6" and p["tier"] == 1 and "unpark --finding 7" in p["revert_cmd"]
    p3 = plan({"loop_class": "LP-D1", "finding_id": 9})   # empty-prompt cron = propose-and-hold
    assert p3["fix_class"] is None and p3["tier"] == 3
    p4 = plan({"loop_class": "LP-A8", "finding_id": 11})  # D5 transcript poison
    assert p4["fix_class"] == "LF-10" and p4["tier"] == 1
    p5 = plan({"loop_class": "LP-A10", "finding_id": 12})  # cross-run resend = LF-12 tier1
    assert p5["fix_class"] == "LF-12" and p5["tier"] == 1 and "unpark --finding 12" in p5["revert_cmd"]
    print("  plan case: PASS (LP-B1->LF-6 tier1; LP-A8->LF-10 tier1; LP-D1->hold tier3; "
          "LP-A10->LF-12 tier1)")

    with tempfile.TemporaryDirectory() as td:
        # LF-1: a DEAD-pid JSON lock is archived; a LIVE-pid lock is refused; a
        # non-JSON lock is refused (never parsed as a bare pid).
        dead = Path(td) / "dead.lock"
        dead.write_text(json.dumps({"pid": 2147480000}), encoding="utf-8")  # impossible pid
        r = lf1_archive_stale_lock(dead, dry_run=False)
        assert r["applied"] and not dead.exists() and Path(str(dead) + ".archived").exists()
        live = Path(td) / "live.lock"
        live.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        r2 = lf1_archive_stale_lock(live, dry_run=False)
        assert not r2["applied"] and "ALIVE" in r2["reason"] and live.exists()
        bad = Path(td) / "bad.lock"
        bad.write_text("PID=1234 not json", encoding="utf-8")
        r3 = lf1_archive_stale_lock(bad, dry_run=False)
        assert not r3["applied"] and "not JSON" in r3["reason"] and bad.exists()
        print("  LF-1 case: PASS (dead archived; live refused; non-JSON refused)")

        # LF-4: DRY_RUN leaves the cron file BYTE-IDENTICAL; armed sets enabled=false.
        cron = Path(td) / "crons.json"
        cron.write_text(json.dumps({"crons": [{"id": "resume", "enabled": True}]}, indent=2),
                        encoding="utf-8")
        before = cron.read_bytes()
        d = lf4_disable_cron(cron, "resume", dry_run=True)
        assert not d["applied"] and cron.read_bytes() == before  # D-DRYRUN invariant
        a = lf4_disable_cron(cron, "resume", dry_run=False)
        assert a["applied"] and json.loads(cron.read_text())["crons"][0]["enabled"] is False
        print("  LF-4 case: PASS (DRY_RUN byte-identical; armed disables, never deletes)")

        # LF-2: a corrupted (advanced-past-pending) offset rewinds to oldest-1.
        off = Path(td) / "offset.json"
        off.write_text(json.dumps({"stored_offset": 100450, "oldest_pending_update_id": 100400}),
                       encoding="utf-8")
        ob = off.read_bytes()
        assert lf2_rewind_offset(off, dry_run=True)["rewound_to"] == 100399 and off.read_bytes() == ob
        r2 = lf2_rewind_offset(off, dry_run=False)
        assert r2["applied"] and json.loads(off.read_text())["stored_offset"] == 100399
        print("  LF-2 case: PASS (DRY_RUN byte-identical; armed rewinds to oldest-1)")

        # LF-10: DRY_RUN leaves the transcript byte-identical; armed MOVES it (never
        # deletes) and the emitted revert restores it; a LIVE transcript is REFUSED.
        sess = Path(td) / "poisoned.jsonl"
        sess.write_text('{"type":"message"}\n', encoding="utf-8")
        sbefore = sess.read_bytes()
        d10 = lf10_archive_and_roll_session(sess, dry_run=True, idle_minutes=60)
        assert not d10["applied"] and sess.read_bytes() == sbefore  # D-DRYRUN invariant
        live = lf10_archive_and_roll_session(sess, dry_run=False, idle_minutes=0.5,
                                             min_idle_minutes=10)
        assert not live["applied"] and "LIVE" in live["reason"] and sess.is_file()
        a10 = lf10_archive_and_roll_session(sess, dry_run=False, idle_minutes=60)
        arch = Path(a10["archived_to"])
        assert a10["applied"] and not sess.exists() and arch.is_file()
        assert arch.read_bytes() == sbefore          # archived, never truncated
        shutil.move(str(arch), str(sess))            # the emitted one-line revert
        assert sess.is_file() and sess.read_bytes() == sbefore
        missing = lf10_archive_and_roll_session(Path(td) / "nope.jsonl", dry_run=False,
                                                idle_minutes=60)
        assert not missing["applied"]
        print("  LF-10 case: PASS (DRY_RUN byte-identical; LIVE transcript REFUSED; "
              "armed MOVES not deletes; revert restores; missing path safe)")

        # LF-10 IDEMPOTENCE + BOUND + REFUSAL (the D-POISON-REROLL crash, in unit form).
        # 1) An archive is never re-archived. Re-rolling one appends another marker to
        #    the name every tick until the component passes NAME_MAX_BYTES and the move
        #    raises ENAMETOOLONG - which killed the whole scheduled tick.
        already = Path(td) / ("rolled%s20260101T000000Z.jsonl" % ARCHIVE_MARKER)
        already.write_text('{"type":"message"}\n', encoding="utf-8")
        rr = lf10_archive_and_roll_session(already, dry_run=False, idle_minutes=999)
        assert not rr["applied"] and "ALREADY a loop archive" in rr["reason"]
        assert already.is_file()  # untouched
        # 2) The name is bounded in BYTES, deterministically, and a fitting stem is
        #    left byte-identical (no gratuitous rewriting of normal names). 255 is a
        #    LITERAL here on purpose: an assertion that reads its ceiling from
        #    NAME_MAX_BYTES cannot catch NAME_MAX_BYTES being weakened.
        fs_name_max = 255
        long_stem = "s" * 240
        natural = "%s%s20260101T000000Z.jsonl" % (long_stem, ARCHIVE_MARKER)
        bounded = bounded_archive_name(long_stem, "20260101T000000Z", ".jsonl")
        assert len(natural.encode("utf-8")) > fs_name_max        # the crash shape
        assert len(bounded.encode("utf-8")) <= fs_name_max       # bounded
        assert bounded == bounded_archive_name(long_stem, "20260101T000000Z", ".jsonl")
        assert bounded_archive_name("s1", "20260101T000000Z", ".jsonl") == \
            "s1%s20260101T000000Z.jsonl" % ARCHIVE_MARKER
        # a multi-byte stem is bounded on BYTES, never on characters
        assert len(bounded_archive_name("é" * 200, "20260101T000000Z",
                                        ".jsonl").encode("utf-8")) <= fs_name_max
        # and the real roll of an over-long stem SUCCEEDS (helper wired to the caller)
        long_src = Path(td) / (long_stem + ".jsonl")
        long_src.write_text('{"type":"message"}\n', encoding="utf-8")
        lr = lf10_archive_and_roll_session(long_src, dry_run=False, idle_minutes=999)
        assert lr["applied"] and not long_src.exists()
        assert len(Path(lr["archived_to"]).name.encode("utf-8")) <= fs_name_max
        # 3) An OSError from the move is a REFUSAL, never a crash: the transcript is
        #    left exactly as found so the tick can move on to the next unit.
        ref = Path(td) / "refusal.jsonl"
        ref.write_text('{"type":"message"}\n', encoding="utf-8")
        rbytes = ref.read_bytes()
        _real_move = shutil.move
        try:
            shutil.move = lambda *a, **k: (_ for _ in ()).throw(
                OSError(63, "File name too long (injected)"))
            rf = lf10_archive_and_roll_session(ref, dry_run=False, idle_minutes=999)
        finally:
            shutil.move = _real_move
        assert not rf["applied"] and "refused" in rf["reason"]
        assert ref.is_file() and ref.read_bytes() == rbytes
        print("  LF-10 re-roll case: PASS (an archive is NEVER re-archived; the name is "
              "byte-bounded + deterministic; an OSError is a refusal, not a crash)")

        # LF-12: abort-and-park the resending source session (LP-A10, the
        # 2026-08-04 cross-run resend incident). The RPC is INJECTED (abort_fn)
        # so this drill touches no real gateway; the EXACT response shape
        # verified live against a session with no active run -
        # {"ok":true,"abortedRunId":null,"status":"no-active-run"} - must be
        # treated as a SUCCESSFUL no-op, never a failed fix and never a
        # trigger to retry. DRY_RUN mutates nothing. A second call inside the
        # 600s action cooldown is REFUSED, never re-applied.
        led12 = Ledger(Path(td) / "loop-protection-lf12")

        def _fake_abort_noop(key):
            return {"ok": True, "abortedRunId": None, "status": "no-active-run"}

        planned12 = lf12_abort_cross_run_resend("agent:orch:main", led12, dry_run=True,
                                                abort_fn=_fake_abort_noop)
        assert not planned12["applied"] and "DRY_RUN" in planned12["reason"]
        r12 = lf12_abort_cross_run_resend("agent:orch:main", led12, dry_run=False,
                                          abort_fn=_fake_abort_noop)
        assert r12["applied"], "the documented no-active-run no-op must NOT read as a failed fix"
        assert "no-active-run" in r12["reason"] and "safe no-op" in r12["reason"]
        assert any(row["unit"] == "agent:orch:main" for row in led12.parked_units())
        r12b = lf12_abort_cross_run_resend("agent:orch:main", led12, dry_run=False,
                                           abort_fn=_fake_abort_noop)
        assert not r12b["applied"] and "cooldown" in r12b["reason"]
        led12.close()

        # A genuine abort (an active run really gets aborted) is ALSO applied,
        # with the runId surfaced in the detail - a different park unit avoids
        # the cooldown set above.
        led12b = Ledger(Path(td) / "loop-protection-lf12b")

        def _fake_abort_real(key):
            return {"ok": True, "abortedRunId": "run-xyz"}

        r12c = lf12_abort_cross_run_resend("agent:other-orch:main", led12b, dry_run=False,
                                           abort_fn=_fake_abort_real)
        assert r12c["applied"] and "run-xyz" in r12c["reason"]
        led12b.close()

        # An unreachable/failing RPC aborted NOTHING: it is recorded `parked-flag` (a
        # ledger flag only), never applied and never claimed as a successful abort.
        led12c = Ledger(Path(td) / "loop-protection-lf12c")

        def _fake_abort_unreachable(key):
            return {"ok": False}

        r12d = lf12_abort_cross_run_resend("agent:third-orch:main", led12c, dry_run=False,
                                           abort_fn=_fake_abort_unreachable)
        # SKS-002 / Fix 4: an unreachable RPC aborted NOTHING - it is `parked-flag`, never applied
        assert not r12d["applied"] and r12d["state"] == BR.STATE_PARKED_FLAG, r12d
        assert "unreachable" in r12d["reason"] and "NOTHING was aborted" in r12d["reason"]
        assert "actually" not in r12d["reason"] and "breaks the loop" not in r12d["reason"]
        assert r12["state"] == BR.STATE_STOPPED and r12c["state"] == BR.STATE_STOPPED
        assert "status flag only" in r12["reason"]
        led12c.close()

        # THE REAL RPC TRANSPORT (stub `openclaw`): sessions.abort MUST carry clearQueued=true as
        # a JSON BOOLEAN, key + agentId intact, via `gateway call` - never the old CLI form.
        tdr = Path(td) / "rpc"
        tdr.mkdir()
        rpc_log, rpc_stub = str(tdr / "oc.log"), str(tdr / "openclaw")
        BR._selftest_stub_bin(rpc_stub, rpc_log,
                              stdout='{"ok":true,"abortedRunId":"run-9","status":"aborted"}')
        os.environ["OPENCLAW_BIN"] = rpc_stub
        os.environ.pop("LOOP_NO_PROBES", None)   # the real transport must be exercised
        try:
            led_rpc = Ledger(tdr / "loop-protection")
            r_rpc = lf12_abort_cross_run_resend(
                "agent:dept-master-orchestrator:telegram:default:direct:8606145708",
                led_rpc, dry_run=False)
            led_rpc.close()
        finally:
            os.environ["LOOP_NO_PROBES"] = "1"
            os.environ.pop("OPENCLAW_BIN", None)
        calls = BR._selftest_calls(rpc_log)
        assert len(calls) == 1, calls
        argv = calls[0].split(" ", 4)
        assert argv[:3] == ["gateway", "call", "sessions.abort"] and argv[3] == "--params", calls
        sent = json.loads(calls[0].split("--params ", 1)[1])
        assert sent["clearQueued"] is True, sent       # boolean true, REQUIRED
        assert sent["key"].endswith(":8606145708") and sent["agentId"] == "dept-master-orchestrator"
        assert set(sent) == {"key", "agentId", "clearQueued"}, sent
        assert r_rpc["applied"] and r_rpc["state"] == BR.STATE_STOPPED and "run-9" in r_rpc["reason"]
        # DRY RUN executes nothing: the stub is never called again
        led_dry = Ledger(tdr / "loop-protection-dry")
        lf12_abort_cross_run_resend("agent:x:main", led_dry, dry_run=True)
        led_dry.close()
        assert len(BR._selftest_calls(rpc_log)) == 1
        # LOOP_NO_PROBES=1 with no injected abort_fn never reaches a gateway at all
        os.environ["OPENCLAW_BIN"] = rpc_stub
        try:
            assert _sessions_abort_via_gateway_rpc("agent:x:main") == {"ok": False}
        finally:
            os.environ.pop("OPENCLAW_BIN", None)
        assert len(BR._selftest_calls(rpc_log)) == 1

        assert _agent_id_from_session_key(
            "agent:dept-master-orchestrator:telegram:default:direct:8606145708") \
            == "dept-master-orchestrator"
        assert _agent_id_from_session_key("not-agent-shaped") == "not-agent-shaped"
        assert _rpc_signals_success_or_noop({"ok": True, "abortedRunId": "r1"})
        assert _rpc_signals_success_or_noop({"status": "no-active-run"})  # ok absent entirely
        assert not _rpc_signals_success_or_noop({"ok": False})
        assert not _rpc_signals_success_or_noop("not-a-dict")
        print("  LF-12 case: PASS (DRY_RUN executes nothing; the real transport sends "
              "sessions.abort with clearQueued=true (boolean) + key + agentId; no-active-run "
              "no-op reads as done; a real abort surfaces its runId; an UNREACHABLE RPC is "
              "parked-flag, never applied; cooldown refuses a second call)")

        led = Ledger(Path(td) / "loop-protection")
        # DRY_RUN apply mutates nothing and reports planned
        execs = {"LF-4": lambda dry_run: lf4_disable_cron(cron, "resume", dry_run=dry_run)}
        planned = apply({"loop_class": "LP-A4", "fix_class": "LF-4", "tier": 1, "unit": "resume"},
                        led, armed=False, executors=execs)
        assert planned["status"] == "planned" and "DRY_RUN" in planned["detail"]
        # healer breaker: after 3 recorded fixes on a unit, apply escalates instead
        for _ in range(3):
            led.record_fix(None, "LF-6", unit="cc-app", what="park", dry_run=False)
        esc = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "cc-app"},
                    led, armed=True, executors={"LF-6": lambda dry_run: {"applied": True}})
        assert esc["status"] == "escalated" and esc["escalate"] is True
        # verify-failed-last also short-circuits to escalate (never a 2nd auto-attempt)
        esc2 = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "fresh"},
                     led, armed=True, executors={"LF-6": lambda dry_run: {"applied": True}},
                     verify_failed_last=True)
        assert esc2["status"] == "escalated"
        led.close()
        print("  apply case: PASS (DRY_RUN plans; healer breaker escalates >3/24h & verify-fail)")

        # run_fix (SKS-002 / Fix 4): `fix <id>` on an LP-B1 finding. A finding is `fixed` ONLY
        # when something was REALLY stopped. Stub pm2 records every call.
        pm_log, pm_stub = str(Path(td) / "pm2.log"), str(Path(td) / "pm2")
        BR._selftest_stub_bin(pm_stub, pm_log)
        os.environ["LOOP_PM2_BIN"] = pm_stub
        try:
            led = Ledger(Path(td) / "loop-protection-fix")
            # (1) pm2 unit, stop works: exactly one `pm2 stop`, state stopped, finding fixed
            fid = led.record_finding("LP-B1", "P1", unit="cc-app", detail="storm", tier=1)
            res, rc = run_fix(led, fid)
            assert rc == 0 and res["ok"] and res["fix_class"] == "LF-6" and res["state"] == "stopped", res
            assert BR._selftest_calls(pm_log) == ["stop cc-app"], BR._selftest_calls(pm_log)
            assert any(r["unit"] == "cc-app" for r in led.parked_units())
            assert any(r["unit"] == "cc-app" and r["breaker"] == "process"
                       for r in led.tripped_breakers())
            assert "unpark --finding %d" % fid in res["revert_cmd"]
            assert led.get_finding(fid)["state"] == "fixed"
            assert led.list_fixes(1)[0]["verify_outcome"] == "applied"
            # the operator revert: `pm2 start` runs, ledger cleared
            ur = BR.unpark_unit("cc-app", led)
            assert ur["ok"] and ur["restarted"]
            assert BR._selftest_calls(pm_log) == ["stop cc-app", "start cc-app"]
            assert not any(r["unit"] == "cc-app" for r in led.parked_units())
            # (2) pm2 stop FAILS: state parked-flag, finding stays OPEN, NEVER `fixed`
            Path(pm_log + ".rc").write_text("1", encoding="utf-8")
            fid2 = led.record_finding("LP-B1", "P1", unit="ghost-app", detail="storm", tier=1)
            res2, rc2 = run_fix(led, fid2)
            assert rc2 == 0 and res2["ok"] is False and res2["state"] == "parked-flag", res2
            assert led.get_finding(fid2)["state"] == "open", led.get_finding(fid2)["state"]
            assert led.get_finding(fid2)["state"] != "fixed"
            assert led.list_fixes(1)[0]["verify_outcome"] == "parked-flag"
            assert "NOTHING was stopped" in res2["detail"]
            Path(pm_log + ".rc").unlink()
            # (3) the GATEWAY is alert-only: pm2 never runs, finding stays open
            n_before = len(BR._selftest_calls(pm_log))
            fid3 = led.record_finding("LP-B1", "P1", unit="gateway", detail="storm", tier=1)
            res3, rc3 = run_fix(led, fid3)
            assert rc3 == 0 and res3["ok"] is False and res3["state"] == "parked-flag", res3
            assert "ALERT-ONLY" in res3["detail"]
            assert led.get_finding(fid3)["state"] == "open"
            assert len(BR._selftest_calls(pm_log)) == n_before, "pm2 must never run for the gateway"
            # (4) the LF-6 executor honors DRY RUN: nothing executes, ledger untouched
            n_before = len(BR._selftest_calls(pm_log))
            d6 = lf6_park_process("dry-app", led, dry_run=True)
            assert d6["applied"] is False and d6["dry_run"] is True
            assert len(BR._selftest_calls(pm_log)) == n_before
            assert not any(r["unit"] == "dry-app" for r in led.parked_units())
            dg = lf6_park_process("gateway", led, dry_run=True)
            assert dg["applied"] is False and "ALERT-ONLY" in dg["reason"]
            # (5) through apply(): ARMED stops once and reports applied; a flag-only result is
            #     `refused` with state parked-flag so the watchdog never marks it fixed
            ap = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "armed-app"},
                       led, armed=True,
                       executors={"LF-6": lambda dry_run: lf6_park_process("armed-app", led, dry_run=dry_run)})
            assert ap["status"] == "applied" and ap["state"] == "stopped", ap
            assert BR._selftest_calls(pm_log)[-1] == "stop armed-app"
            ap_gw = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "gateway"},
                          led, armed=True,
                          executors={"LF-6": lambda dry_run: lf6_park_process("gateway", led, dry_run=dry_run)})
            assert ap_gw["status"] == "refused" and ap_gw["state"] == "parked-flag", ap_gw
            ap_dry = apply({"loop_class": "LP-B1", "fix_class": "LF-6", "tier": 1, "unit": "dry2"},
                           led, armed=False,
                           executors={"LF-6": lambda dry_run: lf6_park_process("dry2", led, dry_run=dry_run)})
            assert ap_dry["status"] == "planned" and "stop dry2" not in "\n".join(BR._selftest_calls(pm_log))
            # (6) LF-12 via run_fix: unreachable RPC => parked-flag, finding open; real => fixed
            fid12 = led.record_finding("LP-A10", "P1", unit="agent:o:main", detail="resend", tier=1)
            real_rpc = globals()["_sessions_abort_via_gateway_rpc"]
            globals()["_sessions_abort_via_gateway_rpc"] = lambda key, timeout=10: {"ok": False}
            try:
                res12, _ = run_fix(led, fid12)
            finally:
                globals()["_sessions_abort_via_gateway_rpc"] = real_rpc
            assert res12["ok"] is False and res12["state"] == "parked-flag", res12
            assert led.get_finding(fid12)["state"] == "open"
            cid = led.record_finding("LP-A4", "P1", unit="resume", detail="cron", tier=1)
            cres, crc = run_fix(led, cid)   # LF-4 is config-touching -> prepared, not applied
            assert crc == 0 and cres["action"] == "prepared" and cres["fix_class"] == "LF-4"
            hid = led.record_finding("LP-D1", "P2", unit="x", detail="hold", tier=3)
            hres, _ = run_fix(led, hid)     # no Tier-1 kill card -> hold
            assert hres["action"] == "hold" and hres["fix_class"] is None
            miss, mrc = run_fix(led, 999999)  # unknown finding -> not found (rc 3)
            assert mrc == 3 and miss["ok"] is False
            led.close()
        finally:
            os.environ.pop("LOOP_PM2_BIN", None)
        print("  run_fix case: PASS (pm2 unit: stop once + finding fixed + revert starts it; failed "
              "stop => parked-flag + finding OPEN, never fixed; gateway alert-only, pm2 never "
              "run; DRY executes nothing; LF-12 unreachable => parked-flag; config prepared; hold; "
              "not-found=3)")

    print("[loop_killcards] self-test: PASS")
    return 0


# --------------------------------------------------------------------------- #
# CLI: operator `fix` / `approve` / `plan` by finding id (routed via loop-companion.sh).
# --------------------------------------------------------------------------- #
def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection kill cards.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--state-dir",
                    help="override the ledger state dir (default $LOOP_STATE_DIR)")
    sub = ap.add_subparsers(dest="cmd")
    for name, helptext in (
            ("fix", "operator-commanded execution of a prepared kill card by finding id"),
            ("approve", "approve a Tier-2 proposal by finding id (prepares the on-box command)"),
            ("plan", "print the prepared kill card for a finding id (read-only)")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("finding_id", type=int, help="the ledger finding id")

    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.cmd:
        ap.print_help()
        return 0

    from loop_ledger import Ledger  # local import keeps self-test path import-light
    state_dir = Path(a.state_dir) if getattr(a, "state_dir", None) else None
    ledger = Ledger(state_dir)
    try:
        box = ledger.get_meta("box", "box")
        if a.cmd == "plan":
            f = ledger.get_finding(a.finding_id)
            if not f:
                sys.stderr.write("REFUSED [loop_killcards]: finding %s not found\n" % a.finding_id)
                return 3
            kc = plan({"loop_class": f.get("loop_class"), "finding_id": a.finding_id}, box=box)
            kc["unit"] = f.get("unit")
            print(json.dumps(kc, sort_keys=True))
            return 0
        result, rc = run_fix(ledger, a.finding_id, box=box, approve=(a.cmd == "approve"))
        print(json.dumps(result, sort_keys=True))
        return rc
    finally:
        ledger.close()


if __name__ == "__main__":
    sys.exit(_cli())
