#!/usr/bin/env python3
"""keepalive_core.py -- one tick of the skill 75 keepalive. Stdlib only.

WHAT THIS IS
  The deterministic program the skill75-keepalive cron runs every 10 minutes.
  It used to live inside timer-artifacts/keepalive-cron-prompt.txt as a
  heredoc; it lives here so the tick can be imported and driven by a fake
  clock, and so the prompt file is an instruction and not a program.

  The supervision duty is a PROGRAM, not a model: observation, fair multi-run
  scheduling, leases, the shared provider/account circuit breaker, envelope
  delivery and reporting keep working when NO model route is available. The
  block never calls a model.

ONE TICK
  1. the shared provider/account circuit breaker (one for the account);
  2. every run's origin record, one canonical registry;
  3. a fair, bounded, persistent cursor over the runs;
  4. one per-run lease, one observation through
     run_watch.py --interval-check, one client message decided by its own
     de-duplication rules, and -- for a stall -- one rate-limited, separately
     authorized, fenced recovery;
  5. the cursor and a tick summary.

MESSAGE RULES (why this file is a program and not prompt text)
  run_watch's envelope carries message_key (a digest of everything the client
  message says) and message_kind (progress, needs_you, problem, done, stopped).
  A message goes out only when the key changed or its own cadence is due:
    progress      at most once every 30 minutes for an unchanged key;
    needs_you     the first message, one nudge 2 hours after it and one
                  reminder 24 hours after it, then KEEPALIVE_CLIENT_SILENT once
                  on the operator lane and nothing more until the key changes;
    problem       once per key;
    done, stopped once per key.
  Quiet hours (9:00 PM to 8:00 AM in the client's own time zone, read from
  control/origin.json key "timezone", default America/New_York) hold a
  progress message and a nudge or reminder until 8:00 AM. A first-time
  needs_you, done or problem message still goes out at once. The tick waits
  for the next 10-minute slot; it never invents a send time.

READ-ONLY WITH RESPECT TO THE RUN
  Never answers a card question, never spends, never submits or resubmits a
  paid job, never authors creative output and never manufactures PASS records.
  A stall is resumed ONLY when the run carries a written recovery
  authorization, and then only through the one supported native control
  (factory.py next) under the run watcher's fence; without that authorization
  recovery is announce-only. It writes its own supervision records (run
  registry, per-run leases, shared breaker, tick summary, per-run recovery
  counters) and delivers the envelope's prewritten text.

CLI
  python3 -B keepalive_core.py --runs-dir <DIR> [--skill-root <DIR>]
      [--now <epoch seconds>]

  --runs-dir    the folder holding every run folder.
  --skill-root  the skill folder (default: this file's own skill root).
  --now         judge "now" by this epoch (tests drive the fake clock).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

HEARTBEAT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HEARTBEAT_DIR)))
DEFAULT_TZ = "America/New_York"

SCHEMA = "blackceo.keepalive-core/v3"
BATCH = 8                  # bounded per-tick batch
LEASE_S = 25 * 60          # per-run lease lifetime
LOCK_STALE = 60            # stale lock takeover
RECOVERY_GAP_S = 30 * 60   # at most ONE recovery attempt per run per 30 min
RECOVERY_MAX_FAILURES = 3  # then stop trying and raise EXHAUSTED

PROGRESS_GAP_S = 30 * 60       # an unchanged progress state: every 30 minutes
NUDGE_AFTER_S = 2 * 60 * 60    # the one nudge, 2 hours after the first send
REMINDER_AFTER_S = 24 * 60 * 60  # the one reminder, 24 hours after the first
MAX_NOTICES = 2                # the nudge and the reminder, then silence
QUIET_FROM_H = 21              # 9:00 PM
QUIET_TO_H = 8                 # 8:00 AM

FINISHED = ("complete", "expired", "canceled")
HARD_CLASSES = ("quota", "credit", "suspension", "authorization", "hard-cap",
                "hard_cap")

#: Set by main() when --now is given: the tick and everything it reports judge
#: time by this instead of the wall clock. None means the real clock.
_NOW = None


def now():
    return int(_NOW) if _NOW is not None else int(time.time())


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                  # noqa: BLE001
        return default


def save(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def note(code, detail):
    line = json.dumps({"ts": now(), "code": code, "detail": detail},
                      sort_keys=True)
    os.makedirs(KA_DIR, exist_ok=True)
    with open(EVENTS, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print("KEEPALIVE_EVENT %s %s" % (code, detail), file=sys.stderr)


# --- quiet hours, in the client's own time zone ------------------------------
def client_timezone(run_dir):
    """The client's time zone, read from control/origin.json; else US Eastern."""
    doc = load(os.path.join(run_dir, "control", "origin.json"), {})
    if isinstance(doc, dict):
        tz = doc.get("timezone")
        if isinstance(tz, str) and tz.strip():
            return tz.strip()
    return DEFAULT_TZ


def client_hour(run_dir, ts):
    """The wall-clock hour at the client (0-23), or None when it cannot be read."""
    name = client_timezone(run_dir)
    try:
        from zoneinfo import ZoneInfo      # stdlib 3.9+
        return datetime.datetime.fromtimestamp(float(ts), ZoneInfo(name)).hour
    except Exception:                      # noqa: BLE001 -- no tzdata, odd name
        try:
            return datetime.datetime.fromtimestamp(float(ts)).hour
        except Exception:                  # noqa: BLE001
            return None


def is_quiet(hour):
    """True between 9:00 PM and 8:00 AM. An unknown hour never silences anyone."""
    if hour is None:
        return False
    return hour >= QUIET_FROM_H or hour < QUIET_TO_H


# --- the message decision (importable; tested with a fake clock) -------------
def message_decision(row, envelope, now_s, hour):
    """Whether this tick sends, and which notice it is.

    row is the registry row (last_message_key, last_sent_at, first_sent_at,
    reminders_sent); envelope is run_watch's one JSON object. Returns
    {send, kind, key, reminder_number, silent, why}.
    """
    key = str(envelope.get("message_key") or "")
    kind = str(envelope.get("message_kind") or "progress")
    last_key = row.get("last_message_key")
    last_sent = int(row.get("last_sent_at") or 0)
    first_sent = int(row.get("first_sent_at") or 0)
    reminders = int(row.get("reminders_sent") or 0)
    quiet = is_quiet(hour)
    out = {"send": False, "kind": kind, "key": key,
           "reminder_number": None, "silent": False, "why": ""}
    if not key:
        out["why"] = "the envelope carries no message key"
        return out
    if key != last_key:
        # A new key is new news. Quiet hours hold only an ordinary progress
        # update; needs_you, done, stopped and problem go out at once.
        if kind == "progress" and quiet:
            out["why"] = "quiet hours: held until 8:00 AM"
            return out
        out.update(send=True, why="the run's state changed")
        return out
    if kind == "progress":
        if quiet:
            out["why"] = "quiet hours: held until 8:00 AM"
            return out
        if not last_sent or now_s - last_sent >= PROGRESS_GAP_S:
            out.update(send=True, why="30 minutes since the last progress message")
        else:
            out["why"] = "not due yet"
        return out
    if kind == "needs_you":
        if reminders >= MAX_NOTICES:
            out.update(silent=True, why="the ladder is spent")
            return out
        anchor = first_sent or last_sent
        due_after = NUDGE_AFTER_S if reminders == 0 else REMINDER_AFTER_S
        if not anchor or now_s - anchor >= due_after:
            if quiet:
                out["why"] = "quiet hours: held until 8:00 AM"
                return out
            out.update(send=True, reminder_number=reminders + 1,
                       why="the nudge is due" if reminders == 0
                       else "the reminder is due")
        else:
            out["why"] = "not due yet"
        return out
    out["why"] = "already sent for this key"
    return out


def reminder_text(envelope, reminder_number):
    """The reminder sentence, produced by run_watch.client_message itself."""
    if HEARTBEAT_DIR not in sys.path:
        sys.path.insert(0, HEARTBEAT_DIR)
    import run_watch as RW                       # noqa: PLC0415
    decisions = envelope.get("decisions_pending") or []
    row = {"stage": envelope.get("stage") or "UNKNOWN",
           "state": envelope.get("stage_state") or "UNKNOWN"}
    return RW.client_message(
        str(envelope.get("run_id") or "run"), row, decisions,
        bool(envelope.get("stalled")), envelope.get("stall_detail") or "",
        bool(envelope.get("expired")),
        str(envelope.get("stage_state")) == "COMPLETE",
        int(envelope.get("elapsed_minutes") or 0),
        int(envelope.get("completed_stages") or 0),
        int(envelope.get("stages_total") or 0), 3.0,
        canceled=bool(envelope.get("canceled")),
        recovery=envelope.get("recovery"),
        reminder_number=int(reminder_number))


# --- supervision records -----------------------------------------------------
def recovery_failed(row, rid, rc):
    """Count one failed recovery attempt; stop for good on the third."""
    row["recovery_failed_attempts"] = \
        int(row.get("recovery_failed_attempts") or 0) + 1
    note("KEEPALIVE_RECOVERY_FAILED", "%s rc=%s" % (rid, rc))
    if row["recovery_failed_attempts"] >= RECOVERY_MAX_FAILURES:
        row["recovery_exhausted_at"] = now()
        note("KEEPALIVE_RECOVERY_EXHAUSTED", rid)


def with_registry_lock():
    os.makedirs(KA_DIR, exist_ok=True)
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if now() - int(os.path.getmtime(LOCK)) > LOCK_STALE:
                    os.unlink(LOCK)
                    continue
            except Exception:                          # noqa: BLE001
                pass
            time.sleep(0.2)
    return False


def migrate_origin(run_dir):
    """ONE canonical origin record first (control/origin.json, written at run
    creation). Legacy recorders are migration sources ONLY when no canonical
    record exists. Never guess: disagreeing destinations isolate the run.
    Two recorded destinations of DIFFERENT kinds (chat + studio) are both real
    -- deliver to each once."""
    canon = load(os.path.join(run_dir, "control", "origin.json"), None)
    legacy = []
    receipt = load(os.path.join(run_dir, "control", "card-receipt.json"), {})
    t = receipt.get("target") if isinstance(receipt, dict) else None
    if t:
        legacy.append({"kind": "chat", "target": str(t),
                       "source": "control/card-receipt.json:target"})
    order = load(os.path.join(run_dir, "control", "studio-order.json"), {})
    if isinstance(order, dict) and order.get("order_id") and order.get("base_url"):
        legacy.append({"kind": "studio", "order_id": order["order_id"],
                       "base_url": order["base_url"],
                       "source": "control/studio-order.json"})
    if isinstance(canon, dict) and (canon.get("target") or canon.get("order_id")):
        c = dict(canon)
        c["source"] = "control/origin.json"
        disagree = [h for h in legacy
                    if h["kind"] == c.get("kind", "chat")
                    and h.get("target") and c.get("target")
                    and h["target"] != c["target"]]
        if disagree:
            return [], ("KEEPALIVE_ORIGIN_CONFLICT:control/origin.json=%s;%s=%s"
                        % (c.get("target"), disagree[0]["source"],
                           disagree[0]["target"]))
        return [c], None
    if not legacy:
        return [], "KEEPALIVE_ORIGIN_UNKNOWN"
    chat_targets = {h["target"] for h in legacy if h["kind"] == "chat"}
    if len(chat_targets) > 1:
        return [], "KEEPALIVE_ORIGIN_CONFLICT:" + ";".join(
            h["source"] + "=" + h.get("target", "") for h in legacy)
    uniq, seen = [], set()
    for h in legacy:
        key = (h["kind"], h.get("target"), h.get("order_id"))
        if key not in seen:
            seen.add(key)
            uniq.append(h)
    return uniq, None


# --- one tick ----------------------------------------------------------------
def tick(runs_dir, skill_root=SKILL_ROOT):
    """One full keepalive pass over the runs; returns the tick summary."""
    global KA_DIR, REGISTRY, BREAKER, EVENTS, LAST_TICK, LOCK
    KA_DIR = os.path.join(runs_dir, ".keepalive")
    REGISTRY = os.path.join(KA_DIR, "run-registry.json")
    BREAKER = os.path.join(KA_DIR, "provider-breaker.json")
    EVENTS = os.path.join(KA_DIR, "events.log")
    LAST_TICK = os.path.join(KA_DIR, "last-tick.json")
    LOCK = os.path.join(KA_DIR, "registry.lock")
    run_watch = os.path.join(skill_root, "scripts", "core", "heartbeat",
                             "run_watch.py")
    channel_send = os.path.join(skill_root, "scripts", "core", "choice_card",
                                "intake_card", "channel_send.py")
    changed = False

    # ---- 1. shared provider/account circuit breaker (one for the account) --
    breaker = load(BREAKER, {"schema": "blackceo.provider-breaker/v1",
                             "state": "closed"})
    breaker_open = breaker.get("state") == "open"
    if breaker_open:
        # Close ONLY on an authoritative recovery observation or a RECORDED
        # operator decision - never on a temporary-reset message, never on a
        # timer that was not the provider's own.
        dec = load(os.path.join(KA_DIR, "provider-breaker.decision.json"), {})
        if dec.get("decision") == "close":
            breaker.update({"state": "closed", "closed_at": now(),
                            "closed_by": "operator-decision"})
            save(BREAKER, breaker)
            breaker_open = False
            note("KEEPALIVE_BREAKER_RESUME", "operator-decision")
        elif (breaker.get("retry_at")
              and breaker.get("retry_at_source") == "provider-response"
              and now() >= int(breaker["retry_at"])):
            breaker.update({"state": "closed", "closed_at": now(),
                            "closed_by": "retry_at-reached"})
            save(BREAKER, breaker)
            breaker_open = False
            note("KEEPALIVE_BREAKER_RESUME", "provider retry_at reached")

    # ---- 2. enumerate EVERY eligible run; one canonical registry ----------
    run_dirs = []
    if os.path.isdir(runs_dir):
        for name in sorted(os.listdir(runs_dir)):
            p = os.path.join(runs_dir, name)
            if os.path.isdir(p) and os.path.isfile(
                    os.path.join(p, "control", "state.sqlite3")):
                run_dirs.append(p)

    reg = load(REGISTRY, {"schema": "blackceo.run-registry/v1", "runs": {},
                          "cursor": {"next_index": 0}})
    reg.setdefault("runs", {})
    reg.setdefault("cursor", {"next_index": 0})

    for run_dir in run_dirs:
        rid = os.path.basename(run_dir)
        row = reg["runs"].get(rid) or {"run_id": rid, "state": "active",
                                       "next_due_at": 0}
        if row.get("state") not in FINISHED:
            if not row.get("origins"):
                origins, err = migrate_origin(run_dir)
                row["origins"] = origins
                row["origin"] = origins[0] if origins else None
                row["origin_error"] = err
                changed = True
                if err:
                    note(err, rid)
            reg["runs"][rid] = row
            changed = True

    # ---- 3. fair order + bounded persistent cursor ------------------------
    active = sorted([r for r in reg["runs"].values()
                     if r.get("state") not in FINISHED],
                    key=lambda r: (r.get("next_due_at") or 0,
                                   r.get("run_id") or ""))
    n = len(active)
    idx = int(reg["cursor"].get("next_index") or 0)
    if idx >= n:
        idx = 0                       # start a fresh full cycle
    batch = active[idx:idx + BATCH]   # bounded pass; no wraparound repeats
    next_index = idx + len(batch)
    cycle_done = bool(n) and next_index >= n
    summary = {"observed": [], "delivered": [], "isolated": [],
               "skipped_leased": [], "suppressed": [], "silent": [],
               "recovered": [],
               "breaker": "open" if breaker_open else "closed"}

    # ---- 4. per-run lease + observe + decide + deliver --------------------
    for row in batch:
        rid = row["run_id"]
        run_dir = os.path.join(runs_dir, rid)
        lease_path = os.path.join(run_dir, "control", "keepalive-lease.json")
        reclaimed_from = None
        try:
            fd = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            lease = load(lease_path, {})
            if (lease.get("expires_at") or 0) > now():
                summary["skipped_leased"].append(rid)
                continue
            reclaimed_from = lease.get("owner")   # reclaim an EXPIRED lease once
        save(lease_path, {"owner": "skill75-keepalive", "acquired_at": now(),
                          "expires_at": now() + LEASE_S,
                          "reclaimed_from": reclaimed_from})
        try:
            watch_argv = [sys.executable, run_watch, "--run-dir", run_dir,
                          "--interval-check"]
            if _NOW is not None:
                watch_argv += ["--now", str(int(_NOW))]
            proc = subprocess.run(watch_argv, cwd=skill_root,
                                  capture_output=True, text=True, timeout=120)
            try:
                envelope = json.loads(proc.stdout)
            except Exception:                          # noqa: BLE001
                envelope = None
            row["last_observed_at"] = now()
            summary["observed"].append(rid)
            if envelope is None:
                row["state"] = "needs-attention"
                row["state_reason"] = "HEARTBEAT_STATE_UNREADABLE"
                summary["isolated"].append(rid)
                note("HEARTBEAT_STATE_UNREADABLE", rid)
                continue
            msg = envelope.get("message_for_client") or ""
            origins = row.get("origins") or (
                [row["origin"]] if row.get("origin") else [])
            decision = message_decision(row, envelope, now(),
                                        client_hour(run_dir, now()))
            if decision.get("silent"):
                # The ladder is spent: say it ONCE on the operator lane, then
                # send nothing more for this key.
                if row.get("client_silent_key") != decision["key"]:
                    row["client_silent_key"] = decision["key"]
                    note("KEEPALIVE_CLIENT_SILENT", rid)
                summary["silent"].append(rid)
            if decision["send"] and msg and origins \
                    and not row.get("origin_error"):
                text = msg
                if decision.get("reminder_number"):
                    try:
                        text = reminder_text(envelope,
                                             decision["reminder_number"])
                    except Exception as e:             # noqa: BLE001
                        note("KEEPALIVE_REMINDER_WORDING_FAILED",
                             "%s %s" % (rid, e))
                delivered = False
                for origin in origins:
                    try:
                        if origin.get("kind") == "studio":
                            send = [sys.executable, channel_send, "send",
                                    "--channel", "studio", "--run-dir", run_dir,
                                    "--message", text]
                        else:
                            send = ["openclaw", "message", "send", "--channel",
                                    "telegram", "--target",
                                    str(origin["target"]), "--message", text]
                        r = subprocess.run(send, capture_output=True, text=True,
                                           timeout=60)
                        if r.returncode == 0:
                            summary["delivered"].append(rid)
                            delivered = True
                        else:
                            note("KEEPALIVE_DELIVERY_FAILED",
                                 "%s rc=%d" % (rid, r.returncode))
                    except Exception as e:             # noqa: BLE001
                        note("KEEPALIVE_DELIVERY_FAILED", "%s %s" % (rid, e))
                if delivered:
                    # Remember what the client was told, so the same news is
                    # never sent twice.
                    if row.get("last_message_key") != decision["key"]:
                        row["reminders_sent"] = 0
                        row["first_sent_at"] = now()
                    if decision.get("reminder_number"):
                        row["reminders_sent"] = \
                            int(row.get("reminders_sent") or 0) + 1
                    row["last_message_key"] = decision["key"]
                    row["last_message_kind"] = decision["kind"]
                    row["last_sent_at"] = now()
            elif decision["send"] and (not origins or row.get("origin_error")):
                note(row.get("origin_error") or "KEEPALIVE_TARGET_MISSING", rid)
            # hard provider/account failure surfaced by the run? OPEN THE
            # BREAKER BEFORE any launch decision below, so this tick already
            # suppresses.
            hard = None
            extras = envelope.get("provider_account_failure")
            if isinstance(extras, dict) and \
                    str(extras.get("class", "")).lower() in HARD_CLASSES:
                hard = extras
            if hard and breaker.get("state") != "open":
                save(BREAKER, {"schema": "blackceo.provider-breaker/v1",
                               "state": "open", "class": hard.get("class"),
                               "provider": hard.get("provider"),
                               "account_ref": hard.get("account_ref"),
                               "opened_at": now(),
                               "retry_at": hard.get("retry_at"),
                               # retry times come from the provider's own
                               # response or stay null. A monthly hard cap is
                               # NOT a short reset.
                               "retry_at_source": ("provider-response"
                                                   if hard.get("retry_at")
                                                   else None),
                               "event_id": hashlib.sha256(
                                   (rid + str(now())).encode()).hexdigest()[:12]})
                breaker_open = True
                note("KEEPALIVE_BREAKER_OPEN", "%s %s"
                     % (hard.get("provider"), hard.get("class")))
            # ---- stall recovery: real, separately authorized, rate-limited --
            # The look above only PRINTS a command. Recovery is a second,
            # FENCED pass under --recovery-act: it executes only when a
            # written authorization exists and runs the one supported native
            # control as an ARGUMENT LIST, never a shell -- a run folder with
            # a space in it stays one argument.
            if envelope.get("stalled"):
                if breaker_open:
                    summary["suppressed"].append(rid)   # breaker open: NO launches
                elif row.get("recovery_exhausted_at"):
                    pass                                # stopped for good
                elif int(row.get("recovery_failed_attempts") or 0) \
                        >= RECOVERY_MAX_FAILURES:
                    row["recovery_exhausted_at"] = now()
                    note("KEEPALIVE_RECOVERY_EXHAUSTED", rid)
                elif now() - int(row.get("last_recovery_attempt_at") or 0) \
                        < RECOVERY_GAP_S:
                    pass                                # one attempt per 30 min
                else:
                    row["last_recovery_attempt_at"] = now()
                    act = None
                    act_argv = [sys.executable, run_watch, "--run-dir", run_dir,
                                "--recovery-act"]
                    if _NOW is not None:
                        act_argv += ["--now", str(int(_NOW))]
                    try:
                        act = subprocess.run(act_argv, cwd=skill_root,
                                             capture_output=True, text=True,
                                             timeout=300)
                    except Exception as e:             # noqa: BLE001
                        recovery_failed(row, rid, e)
                    if act is not None:
                        try:
                            act_env = json.loads(act.stdout)
                        except Exception:              # noqa: BLE001
                            act_env = None
                        rec = (act_env or {}).get("recovery") or {}
                        outcome_rc = (((rec.get("control") or {})
                                       .get("outcome") or {})
                                      .get("returncode"))
                        if rec.get("acted") is True and outcome_rc == 0:
                            row["last_recovery_ok_at"] = now()
                            summary["recovered"].append(rid)
                        elif (rec.get("refused") or {}).get("code") \
                                == "RECOVERY_NOT_AUTHORIZED":
                            # announce-only box: say it ONCE, never per tick
                            if not row.get("recovery_not_authorized_at"):
                                row["recovery_not_authorized_at"] = now()
                                note("KEEPALIVE_RECOVERY_NOT_AUTHORIZED", rid)
                        else:
                            recovery_failed(
                                row, rid, outcome_rc
                                if outcome_rc is not None else act.returncode)
            if proc.returncode == 10:
                row["state"] = ("expired" if envelope.get("expired")
                                else "complete")
            row["last_useful_progress_at"] = max(
                row.get("last_useful_progress_at") or 0,
                int(envelope.get("last_progress_at") or 0))
            row["next_wait_deadline"] = envelope.get("next_wait_deadline")
            reg["runs"][rid] = row
            changed = True
        except Exception as e:                         # noqa: BLE001
            row["state"] = "isolated"
            row["state_reason"] = str(e)[:200]
            summary["isolated"].append(rid)
            note("KEEPALIVE_RUN_ISOLATED", "%s %s" % (rid, e))
        finally:
            try:
                os.unlink(lease_path)
            except OSError:
                pass

    # ---- 5. cursor + tick summary (reports survive any outage) ------------
    reg["cursor"] = {"next_index": 0 if cycle_done else next_index,
                     "last_full_cycle_at": (now() if cycle_done
                                            else reg["cursor"].get(
                                                "last_full_cycle_at"))}
    save(REGISTRY, reg)
    save(LAST_TICK, {"schema": "blackceo.keepalive-tick/v1", "ts": now(),
                     "cursor": reg["cursor"], "summary": summary,
                     "breaker": summary["breaker"]})
    return summary


def main(argv=None):
    global _NOW
    ap = argparse.ArgumentParser(
        description="One tick of the skill 75 keepalive (deterministic).")
    ap.add_argument("--runs-dir", required=True,
                    help="the folder holding every run folder")
    ap.add_argument("--skill-root", default=SKILL_ROOT,
                    help="the skill folder (default: this file's skill root)")
    ap.add_argument("--now", type=float, default=None,
                    help="epoch seconds to judge 'now' by (tests)")
    a = ap.parse_args(argv)
    _NOW = a.now
    summary = tick(a.runs_dir, skill_root=a.skill_root)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
