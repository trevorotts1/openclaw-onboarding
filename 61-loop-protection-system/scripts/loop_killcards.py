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


def lf6_park_process(unit, ledger, dry_run=True):
    """LF-6: park a crash-looping process unit on a process-breaker trip. STOP + park
    (visible-red; never silently respawns). Reversible via unpark. Returns
    {applied, reason}."""
    if dry_run:
        return {"applied": False, "reason": "DRY_RUN: would STOP + park unit '%s'" % unit,
                "dry_run": True}
    BR.trip(unit, "process", ledger, park=True)
    return {"applied": True, "reason": "parked unit '%s' (visible-red; no auto-respawn)" % unit,
            "dry_run": False, "revert": "loop-companion.sh unpark %s" % unit}


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
                "revert": r.get("revert")}
    return {"status": "refused", "detail": r.get("reason"), "escalate": False}


# --------------------------------------------------------------------------- #
# Operator-commanded execution of a prepared kill card by finding id (spec 9.1).
# An explicit `fix`/`approve` IS the operator's word for THIS finding, so the one
# config-FREE, deterministic act - the process-unit park (LF-6) - executes for real
# against the ledger. Every config-touching class (LF-1/2/4/5/7) and every Tier-2
# config-shape change is PREPARED here (exact command + one-line revert) and applied
# ON-BOX via the maintenance path, NEVER auto-applied off-box: an honest hand-off,
# not a stub that claims success.
# --------------------------------------------------------------------------- #
def run_fix(ledger, finding_id, box="box", approve=False):
    """Execute (LF-6) or prepare (everything else) the kill card for a finding.
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
    # config-FREE, deterministic act: park the crash-looping process unit (LF-6).
    if fc == "LF-6":
        unit = f.get("unit")
        if not unit:
            return {"ok": False, "reason": "finding %s carries no unit to park" % finding_id}, 2
        r = lf6_park_process(unit, ledger, dry_run=False)
        applied = bool(r.get("applied"))
        ledger.record_fix(finding_id, fc, unit=unit, what=kc.get("what"),
                          verify_outcome="applied" if applied else "refused",
                          revert_cmd=kc.get("revert_cmd"), dry_run=False)
        ledger.set_finding_state(finding_id, "fixed" if applied else "escalated")
        return {"ok": applied, "action": "fix", "fix_class": fc, "unit": unit,
                "applied": applied, "detail": r.get("reason"),
                "revert_cmd": kc.get("revert_cmd")}, 0
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
    print("  plan case: PASS (LP-B1->LF-6 tier1; LP-A8->LF-10 tier1; LP-D1->hold tier3)")

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

        # run_fix: `fix <id>` on an LP-B1 finding PARKS the unit for real (config-free
        # LF-6) and records a one-line revert; a config-touching class is PREPARED, not
        # applied; a Tier-3 class holds. This is the operator `fix`/`approve` path.
        led = Ledger(Path(td) / "loop-protection-fix")
        fid = led.record_finding("LP-B1", "P1", unit="cc-app", detail="storm", tier=1)
        res, rc = run_fix(led, fid)
        assert rc == 0 and res["ok"] and res["fix_class"] == "LF-6"
        assert any(r["unit"] == "cc-app" for r in led.parked_units())
        assert any(r["unit"] == "cc-app" and r["breaker"] == "process"
                   for r in led.tripped_breakers())
        assert "unpark --finding %d" % fid in res["revert_cmd"]
        assert led.get_finding(fid)["state"] == "fixed"
        cid = led.record_finding("LP-A4", "P1", unit="resume", detail="cron", tier=1)
        cres, crc = run_fix(led, cid)   # LF-4 is config-touching -> prepared, not applied
        assert crc == 0 and cres["action"] == "prepared" and cres["fix_class"] == "LF-4"
        hid = led.record_finding("LP-D1", "P2", unit="x", detail="hold", tier=3)
        hres, _ = run_fix(led, hid)     # no Tier-1 kill card -> hold
        assert hres["action"] == "hold" and hres["fix_class"] is None
        miss, mrc = run_fix(led, 999999)  # unknown finding -> not found (rc 3)
        assert mrc == 3 and miss["ok"] is False
        led.close()
        print("  run_fix case: PASS (LF-6 parks for real+revertible; config prepared; hold; not-found=3)")

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
