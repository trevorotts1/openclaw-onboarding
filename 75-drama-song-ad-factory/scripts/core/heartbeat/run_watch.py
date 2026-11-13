#!/usr/bin/env python3
"""run_watch.py -- the 10-minute keepalive for one drama run. Stdlib only.

WHAT IT IS
  One look at a run, for a driver that speaks to the client every 10 minutes
  after intake is answered and the run has started:
    (a) the stage and its state, in plain English;
    (b) every pending decision in front of the client (intake outstanding,
        approval gates, a cost fork whose recorded decision is "wait");
    (c) a stall (no durable event for 30 minutes on the current stage, a dead
        lease, or a STALE row) -- and, when separately authorized, a FENCED
        recovery step EXECUTED through the supported native control
        (factory.py next), never an instruction left for a human to invent;
    (d) the supervision cap (the run's own expected duration, from the song
        length it chose and the Agnes answer, anchored on spend_ledger
        runs.created_at; 3 hours when the run records no length): a loud
        escalation that never stops supervision.
        A human wait, a provider wait or elapsed time does NOT end the loop;
        only verified completion or an explicit user cancellation does.

SUPERVISION NEVER SELF-TERMINATES
  The loop runs until the run is verified COMPLETE (every stage COMPLETE) or
  an explicit user cancellation is recorded. Past the cap an unfinished run
  stays supervised: evidence-based recovery runs, or a NAMED legitimate wait
  is reported. There is no false success and no expiry-driven exit 10.

THE FENCED RECOVERY ACTUATOR (separately authorized)
  Recovery executes only when BOTH are true: the driver passes --recovery-act
  AND a written authorization exists (control/recovery-authorization.json,
  written by the orchestrator/operator -- this module never writes it). Every
  recovery claim carries a monotonic generation + token: a replacement claim
  REVOKES the old token before it may write, and a stale token is rejected and
  quarantined at every fenced boundary -- write, evidence, state and
  provider-dispatch. Recovery runs the one supported native control
  (factory.py next --run-dir); it never dispatches provider work, never
  authors creative outputs and never writes PASS/QC records (roles stay
  distinct: observer, orchestrator, builder, independent reviewer).

ACTIVITY AND THE WATCHDOG CLOCK
  The watchdog clock advances ONLY from durable events (the state store's
  events journal: worker progress, provider acknowledgements, heartbeats).
  Copied or touched decision files are never activity, and file mtime is
  never read -- rewriting fork-decisions.json or run-state.json cannot reset
  a watchdog clock. While a stage has recorded no durable event, its recorded
  state stamp is the starting anchor only; once a durable event exists, only
  durable events move the clock. Human-wait time does not consume the
  technical stall timeout.

WHAT IT NEVER DOES (observer role)
  Without --recovery-act it never writes: the state database is opened
  `mode=ro`; fork-decisions.json, run-state.json, song-choices/ and the spend
  ledger are only read. Stall recovery is then a PRINTED command only.

CLI
  python3 scripts/core/heartbeat/run_watch.py --run-dir <RUN>
      [--interval-check] [--max-hours 3] [--now <epoch seconds>]
      [--recovery-act] [--fence-dir <DIR>]

  --interval-check  one tick of the 10-minute driver: exit 10 only when the
                    loop is over (verified COMPLETE or explicit cancellation);
                    an unfinished run keeps looping however long it runs.
  --recovery-act    permit the fenced actuator to EXECUTE recovery (still
                    requires the separate written authorization).

EXIT
  0   envelope printed, loop continues (or, without --interval-check, read ok)
  10  --interval-check only: stop the loop (verified COMPLETE or canceled)
  1   the run state could not be read (loud: HEARTBEAT_STATE_UNREADABLE)

ENVELOPE (one JSON object on stdout)
  {run_id, stage, stage_state, elapsed_minutes, expected_hours,
   decisions_pending, stalled,
   loud, expired, message_for_client, message_key, message_kind, ... extras
   (stall_detail, wait, activity, recovery, supervising, canceled,
   recovery_command, loop_should_stop, completed_stages, schema_version)}

  message_key  a 16-hex digest of everything the client message says (stage,
               stage state, completed steps, the pending decision ids, and the
               stalled/expired/complete/canceled flags). Two looks at the SAME
               situation carry the SAME key, so the keepalive can tell "this is
               the same news again" from "something changed".
  message_kind one of progress, needs_you, problem, done, stopped: what the
               message is about, and therefore which sending cadence applies.

LOUD CODES (loud_failure.py, printed to stderr AND carried in the envelope)
  HEARTBEAT_STATE_UNREADABLE  the state database is missing or unreadable
  HEARTBEAT_STALLED           the current stage made no progress in 30 minutes
  HEARTBEAT_EXPIRED           the supervision cap was reached, job not COMPLETE
  RECOVERY_NOT_AUTHORIZED     actuator asked to run without authorization
  RECOVERY_STALE_TOKEN        a stale claim token touched a fenced boundary
  RECOVERY_CONTROL_FAILED     the supported native control failed to run
  RECOVERY_ACTION_REFUSED     an action outside the recovery scope was asked
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl                                   # POSIX claim CAS locking
except ImportError:                                # pragma: no cover
    fcntl = None

SCHEMA_VERSION = "blackceo.drama-run-watch/v1"
TOOL_VERSION = "1.1.0"
RECOVERY_SCHEMA_VERSION = "blackceo.drama-run-recovery/v1"

STALL_AFTER_S = 30 * 60
DEFAULT_MAX_HOURS = 3.0
TICK_EXIT_STOP = 10

#: The fenced boundaries a claim token must clear before anything lands.
FENCE_BOUNDARIES = ("write", "evidence", "state", "provider-dispatch")
#: The recovery actuator's whole action scope: resume the run through the one
#: supported native control. It can never author creative output, never write
#: PASS/QC records and never dispatch provider work -- those stay with the
#: builder, the independent reviewer and the spend-authorized dispatcher.
RECOVERY_ACTIONS = frozenset({"resume"})

#: batch_mode/batch.py STAGES order, plus the presentation stages the runbook
#: adds in front of delivery. Anything else sorts after these, alphabetically.
STAGE_ORDER = (
    "research", "creative-strategy", "script-lyrics", "music",
    "continuity-bible", "storyboard", "image-keyframes", "video-generation",
    "qc-retakes", "assembly", "final-qc", "delivery",
    "clips", "trailers", "platform-fit",
    "agnes-keyframes", "agnes-video-segment",
)
EXTRA_PHRASES = {
    "clips": "the shorter versions of your ad are being cut",
    "trailers": "the shorter versions of your ad are being cut",
    "platform-fit": "I'm checking your ad fits where it will run",
    "agnes-keyframes": "your ad's pictures are being made",
    "agnes-video-segment": "your ad's video clips are being filmed",
}
STAGE_PHRASES = {
    "research": "your ad's research is being done",
    "creative-strategy": "your ad's story is being shaped",
    "script-lyrics": "your ad's script and lyrics are being written",
    "music": "your ad's music is being created",
    "continuity-bible": "your ad's look and characters are being kept consistent",
    "storyboard": "your ad's storyboard pictures are being drawn",
    "image-keyframes": "your ad's pictures are being made",
    "video-generation": "your ad's video clips are being filmed",
    "qc-retakes": "I'm checking your ad's clips and fixing anything that looks off",
    "assembly": "your ad is being put together",
    "final-qc": "I'm doing a final check of your ad",
    "delivery": "your ad is being packaged for you",
}
STAGE_PHRASES.update(EXTRA_PHRASES)
#: A short noun for a stage, so a sentence reads right ("a problem with the
#: music step", never "with your ad's music is being created").
STAGE_NOUNS = {
    "research": "the research step",
    "creative-strategy": "the story step",
    "script-lyrics": "the script and lyrics step",
    "music": "the music step",
    "continuity-bible": "the look-and-characters step",
    "storyboard": "the storyboard step",
    "image-keyframes": "the picture step",
    "video-generation": "the video clips step",
    "qc-retakes": "the clip check",
    "assembly": "the assembly step",
    "final-qc": "the final check",
    "delivery": "the delivery step",
    "clips": "the short-version step",
    "trailers": "the short-version step",
    "platform-fit": "the placement check",
    "agnes-keyframes": "the picture step",
    "agnes-video-segment": "the video clips step",
}


def stage_noun(stage):
    return STAGE_NOUNS.get(stage, "the %s step" % str(stage).replace("-", " "))

#: The twelve canonical stages (batch_mode/batch.py STAGES), in run order.
#: Only these count in a progress message's "of <total>": the presentation
#: stages the runbook adds in front of delivery are extra work, never extra
#: steps for the client.
CANONICAL_STAGES = STAGE_ORDER[:12]
CANONICAL_STAGE_SET = frozenset(CANONICAL_STAGES)

#: The short noun for the approval a stage asks the client for, so a progress
#: message can say "I'll need your OK on the script next." These are the same
#: gates this module already surfaces as approvals: script, song pick,
#: storyboard.
APPROVAL_THINGS = {
    "script-lyrics": "script",
    "music": "song",
    "storyboard": "storyboard pictures",
}

#: Expected run duration (hours) by the song length the client chose. The
#: Agnes path runs this again at x2. An old run that records no length keeps
#: DEFAULT_MAX_HOURS.
EXPECTED_HOURS_BY_LENGTH = (
    (90, 1.5),       # 60-90 seconds
    (180, 3.0),      # 2-3 minutes
    (360, 6.0),      # 5 minutes
    (660, 10.0),     # 10 minutes (kept even if the card stops offering it)
)


#: A state that still has work coming. COMPLETE is the only finished state.
ACTIVE_STATES = frozenset({"NOT_STARTED", "READY", "RUNNING", "WAITING_PROVIDER",
                           "WAITING_APPROVAL", "QC", "FAILED_RETRYABLE",
                           "FAILED_BLOCKED", "PARKED", "STALE"})

APPROVAL_QUESTIONS = {
    "script-lyrics": ("Your script is ready. Do you approve it, or would you like "
                      "a change?", ["Approve it", "Ask for a change"]),
    "storyboard": ("Your storyboard pictures are ready. Do you approve them, or "
                   "would you like one shot changed?",
                   ["Approve them", "Change one shot"]),
}


# --- loud_failure: the same named-code helper every other stage uses ---------
def _loud():
    core = str(Path(__file__).resolve().parent.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        import loud_failure as LF  # noqa: PLC0415
        return LF
    except Exception:                                # noqa: BLE001
        class _Stub(object):
            """Never silent: an unavailable loud_failure still prints."""

            def __init__(self):
                self.codes = []

            def _add(self, kind, code, detail=""):
                self.codes.append(str(code))
                sys.stderr.write("%s %s: %s\n" % (kind, code, detail))
                return {"kind": kind, "code": str(code), "detail": str(detail)}

            def fail(self, code, detail=""):
                return self._add("FAILURE", code, detail)

            def warn(self, code, detail=""):
                return self._add("WARNING", code, detail)
        return _Stub()


LF = _loud()


def _fail(code, detail):
    LF.fail(code, detail)
    return code


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _ro(db_path):
    """Read-only connection. A run is NEVER mutated by this module.

    A WAL database whose -wal/-shm sidecars are gone cannot be opened
    mode=ro (SQLITE_CANTOPEN), and connect() is lazy, so the failure only
    shows on the first statement. Retry on a private temp copy instead.
    """
    path = Path(db_path).resolve()
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        con.execute("PRAGMA schema_version").fetchone()
        return con
    except sqlite3.Error:
        try:
            con.close()                       # noqa: F821
        except Exception:                     # noqa: BLE001
            pass
    tmp = tempfile.mkdtemp(prefix="run-watch-")
    atexit.register(shutil.rmtree, tmp, True)
    for name in (path.name, path.name + "-wal", path.name + "-shm"):
        src = path.with_name(name)
        if src.is_file():
            shutil.copy2(src, os.path.join(tmp, name))
    con = sqlite3.connect(os.path.join(tmp, path.name), timeout=5)
    con.execute("PRAGMA query_only=ON")
    return con


def _utc_iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


# --- state -------------------------------------------------------------------
def read_state(run_dir):
    """({run_id, stages, events_by_stage, last_event_at}, None) or (None, why)."""
    db = Path(run_dir) / "control" / "state.sqlite3"
    if not db.is_file():
        return None, "no control/state.sqlite3 at %s" % db
    try:
        con = _ro(db)
    except sqlite3.Error as exc:
        return None, "state database not readable: %s" % exc
    try:
        rows = con.execute(
            "SELECT run_id, stage, state, owner, lease_expires, reason, updated_at"
            " FROM stages").fetchall()
        events = con.execute(
            "SELECT run_id, stage, at FROM events").fetchall()
    except sqlite3.Error as exc:
        return None, "state database not readable: %s" % exc
    finally:
        con.close()
    ids = sorted({str(r[0]) for r in rows})
    if len(ids) == 1:
        run_id = ids[0]
    elif ids and (Path(run_dir).name in ids):
        run_id = Path(run_dir).name
    elif ids:
        run_id = ids[0]          # the first row's run answers; named on the envelope
    else:
        run_id = Path(run_dir).name or "run"
    stages, by_stage, last = [], {}, None
    for rid, stage, state, owner, lease, reason, updated in rows:
        if str(rid) != run_id:
            continue
        stages.append({"stage": str(stage), "state": str(state),
                       "owner": owner, "lease_expires": lease,
                       "reason": reason, "updated_at": updated})
    for rid, stage, at in events:
        if str(rid) != run_id or at is None:
            continue
        by_stage[str(stage)] = max(by_stage.get(str(stage), 0.0), float(at))
        last = float(at) if last is None else max(last, float(at))
    return {"run_id": run_id, "stages": stages,
            "events_by_stage": by_stage, "last_event_at": last}, None


def runs_created_at(run_dir, run_id):
    """The run's own start, from spend_ledger runs.created_at (the 3h anchor)."""
    db = Path(run_dir) / "spend.sqlite3"
    if db.is_file():
        try:
            con = _ro(db)
        except sqlite3.Error:
            con = None
        if con is not None:
            try:
                rows = con.execute("SELECT run_id, created_at FROM runs").fetchall()
            except sqlite3.Error:
                rows = []
            finally:
                con.close()
            for rid, created in rows:
                if str(rid) == run_id:
                    stamp = _parse_iso(created)
                    if stamp is not None:
                        return stamp
            if len(rows) == 1:
                stamp = _parse_iso(rows[0][1])
                if stamp is not None:
                    return stamp
    return None


# --- decisions ---------------------------------------------------------------
def _option_list(value):
    if not isinstance(value, list):
        return []
    out = []
    for v in value:
        if isinstance(v, dict):
            label = v.get("label") or v.get("text") or v.get("value") or v.get("id")
            if label:
                out.append(str(label))
        elif isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


def intake_decisions(run_dir):
    """Outstanding intake / resume decisions recorded on the run itself."""
    doc = _json(Path(run_dir) / "control" / "run-state.json")
    if not isinstance(doc, dict):
        return []
    out, seen = [], set()

    def add(qid, question, options=()):
        q = str(question or "").strip()
        if not q or q in seen:
            return
        seen.add(q)
        out.append({"kind": "intake", "id": str(qid), "question": q,
                    "options": list(options)})

    for n, item in enumerate(doc.get("outstanding") or []):
        if isinstance(item, dict):
            add(item.get("id") or "intake-%d" % n,
                item.get("question") or item.get("text"),
                _option_list(item.get("options")))
        else:
            add("intake-%d" % n, item)
    for n, item in enumerate(doc.get("questions") or []):
        if isinstance(item, dict):
            add(item.get("id") or "intake-q-%d" % n, item.get("question"),
                _option_list(item.get("options")))
    return out


def approval_decisions(run_dir, stages):
    """One decision per approval gate that is waiting on the client.

    Gate text comes from the run's own recorded material: the song pick offers
    its labelled versions, the script and storyboard use their own question.
    A stage already answered is NOT surfaced (the song pick is answered when
    song-choices/pick.json exists).
    """
    out = []
    for row in stages:
        if row["state"] != "WAITING_APPROVAL":
            continue
        stage = row["stage"]
        if stage == "music":
            if (Path(run_dir) / "song-choices" / "pick.json").is_file():
                continue
            offered = []
            state_doc = _json(Path(run_dir) / "song-choices" / "state.json")
            if isinstance(state_doc, dict):
                for n in sorted((state_doc.get("offered") or {}), key=str):
                    label = (state_doc["offered"][n] or {}).get("label")
                    offered.append(str(label or ("Version %s" % n)))
            if not offered:
                offered = ["Use this song", "Ask for another one"]
            out.append({"kind": "approval", "id": "song-pick",
                        "question": "Your song is ready. Which version do you want?",
                        "options": offered})
            continue
        question, options = APPROVAL_QUESTIONS.get(
            stage,
            ("Your video is waiting for your OK on %s. Shall I go ahead?"
             % STAGE_PHRASES.get(stage, "the next step"),
             ["Approve", "Ask for a change"]))
        out.append({"kind": "approval", "id": stage, "question": question,
                    "options": list(options)})
    return out


def fork_decisions(run_dir):
    """Cost forks still on the safe default "wait" (latest entry per fork wins)."""
    doc = _json(Path(run_dir) / "control" / "fork-decisions.json")
    if not isinstance(doc, dict):
        return []
    latest = {}
    for rec in doc.get("forks") or []:
        if isinstance(rec, dict) and rec.get("fork_id") is not None:
            latest[str(rec["fork_id"])] = rec
    out = []
    for fork_id, rec in latest.items():
        if str(rec.get("decision")) != "wait":
            continue
        label = str(rec.get("label") or "").strip()
        question = label or ("Should I go ahead with the paid step for %s?" % fork_id)
        cost = rec.get("cost_minor")
        if isinstance(cost, int) and not isinstance(cost, bool) and cost > 0:
            question = "%s (it costs %s)" % (question, _money(cost))
        out.append({"kind": "fork", "id": fork_id, "question": question,
                    "options": ["Go ahead", "Stay with the free option"],
                    "reason": rec.get("reason")})
    return out


def _money(minor):
    return "$%d.%02d" % (minor // 100, minor % 100)


# --- stall / expiry ----------------------------------------------------------
def current_stage(stages):
    """The first stage in runbook order that is not COMPLETE, else the last."""
    order = {s: n for n, s in enumerate(STAGE_ORDER)}
    ordered = sorted(stages, key=lambda r: (order.get(r["stage"], len(order)),
                                            r["stage"]))
    for row in ordered:
        if row["state"] in ACTIVE_STATES:
            return row
    return ordered[-1] if ordered else None


def watchdog_clock(state, row):
    """(last_progress_at, source) -- activity from DURABLE EVENTS only.

    The events journal is the activity signal (worker progress, provider
    acknowledgements, heartbeats). Copied/touched decision files are never
    activity and file mtime is never read, so nothing a copy rewrites can
    reset a watchdog clock. A stage with no durable event yet falls back to
    its recorded state stamp as the STARTING anchor; once a durable event
    exists, only durable events move the clock.
    """
    if row is None:
        return None, "none"
    ev = state["events_by_stage"].get(row["stage"])
    if ev is not None:
        return float(ev), "durable-event"
    stamp = row.get("updated_at")
    if stamp:
        return float(stamp), "state-stamp-anchor"
    return None, "none"


def legitimate_wait(row, decisions):
    """The named wait keeping this run legitimately parked, or None.

    A human wait does not consume the technical stall timeout; a provider
    wait is legitimate only while its lease says someone is still checking
    in. Everything else is work silence, and silence is a stall.
    """
    if row is not None and row["state"] == "WAITING_APPROVAL":
        return {"kind": "client-approval", "on": row["stage"],
                "deadline": None}
    if decisions:
        kinds = sorted({d.get("kind", "decision") for d in decisions})
        return {"kind": "client-decision", "on": ",".join(kinds),
                "deadline": None}
    if row is not None and row["state"] == "WAITING_PROVIDER":
        lease = row.get("lease_expires")
        if isinstance(lease, (int, float)) and lease > 0:
            return {"kind": "provider", "on": row["stage"],
                    "deadline": _utc_iso(lease)}
    return None


#: Plain-words reasons for the client, one per stall path. A FIXED table:
#: never assembled from stored text, never carrying a clock time, a worker
#: name, a state name or a code. The machine-readable `detail` that
#: stall_check also returns is for the operator envelope and the receipt only.
STALL_CLIENT_REASONS = {
    "stale": "that step needs a restart",
    "expired-lease": "the helper working on it stopped answering",
    "quiet": "nothing has moved for a while",
}


def stall_check(state, row, now, decisions=()):
    """(stalled, detail, client_reason). A named wait is not a stall; silence is.

    `detail` is the operator's own sentence (state name, lease stamp, quiet
    minutes). `client_reason` is the plain-words line from the fixed table
    above, and it is the ONLY thing the client message may repeat.
    """
    if row is None:
        return False, "", ""
    stage, st = row["stage"], row["state"]
    if st == "COMPLETE":
        # A finished stage has nothing left to move.
        return False, "", ""
    if st == "STALE":
        return True, ("the run marked %s stale: %s"
                      % (stage, row.get("reason") or "no reason recorded")), \
            STALL_CLIENT_REASONS["stale"]
    lease = row.get("lease_expires")
    if isinstance(lease, (int, float)) and lease > 0 and lease < now \
            and st in ("RUNNING", "WAITING_PROVIDER", "QC"):
        return True, ("the worker on %s stopped checking in and its turn ran out "
                      "at %s" % (stage, _utc_iso(lease))), \
            STALL_CLIENT_REASONS["expired-lease"]
    if legitimate_wait(row, decisions) is not None:
        # a client or live provider owes the next move
        return False, "", ""
    last, source = watchdog_clock(state, row)
    quiet = now - last if last else None
    if quiet is not None and quiet > STALL_AFTER_S:
        return True, ("nothing has moved on %s for %d minutes"
                      % (stage, int(quiet // 60))), \
            STALL_CLIENT_REASONS["quiet"]
    return False, "", ""


def recovery_command(run_dir):
    """The exact command the supported native control runs, as a shell line.

    Printed when the actuator is not separately authorized; the driver runs
    the watcher itself (argument list, no shell) when it is. Both the absolute
    factory path and the run folder are quoted with shlex.quote, so a path
    with a space in it stays ONE argument: `shlex.split(recovery_command(run))`
    round-trips to the argv the actuator uses.
    """
    factory = _factory_control_argv(run_dir)[1]
    return ("python3 %s next --run-dir %s"
            % (shlex.quote(factory), shlex.quote(str(run_dir))))


# --- the fenced recovery actuator -------------------------------------------
class RecoveryFence(object):
    """Monotonic generation tokens for every recovery/worker claim.

    Every claim gets a strictly increasing generation and a fresh token.
    A replacement REVOKES the active token before the new claim is written
    (revocation-before-replacement), claim writes are compare-and-swap under
    a file lock, and a result presented under a token that is no longer the
    active one is rejected at every fenced boundary (write, evidence, state,
    provider-dispatch) and quarantined for inspection.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+b")
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return fh

    def _read(self):
        doc = _json(self.path)
        if not isinstance(doc, dict) or not isinstance(doc.get("generation"), int):
            return {"schema_version": RECOVERY_SCHEMA_VERSION,
                    "generation": 0, "active": None,
                    "claims": [], "quarantine": []}
        doc.setdefault("claims", [])
        doc.setdefault("quarantine", [])
        return doc

    def _write(self, doc):
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(str(tmp), str(self.path))

    def claim(self, reason="", now=None, expected_generation=None):
        """New claim: revoke the old token FIRST, then write generation+1."""
        now = time.time() if now is None else float(now)
        lock = self._locked()
        try:
            doc = self._read()
            if expected_generation is not None \
                    and doc["generation"] != int(expected_generation):
                raise ValueError("CAS mismatch: generation %d != expected %d"
                                 % (doc["generation"], int(expected_generation)))
            old = doc.get("active")
            if old:
                # revocation-before-replacement: recorded before the new claim
                revoked = {"status": "revoked", "revoked_at": now,
                           "revoked_for_generation": doc["generation"] + 1}
                old.update(revoked)
                for rec in doc["claims"]:
                    if rec.get("token") == old.get("token") and \
                            rec.get("generation") == old.get("generation"):
                        rec.update(revoked)
            gen = doc["generation"] + 1
            token = uuid.uuid4().hex
            claim = {"generation": gen, "token": token, "reason": str(reason),
                     "claimed_at": now, "status": "active"}
            doc["generation"] = gen
            doc["active"] = claim
            doc["claims"].append(dict(claim))
            self._write(doc)
            return dict(claim)
        finally:
            lock.close()

    def active(self):
        return self._read().get("active")

    def guard(self, boundary, token, now=None):
        """(ok, detail). Stale tokens are rejected AND quarantined at every
        boundary: write, evidence, state, provider-dispatch."""
        now = time.time() if now is None else float(now)
        if boundary not in FENCE_BOUNDARIES:
            return False, "unknown boundary %r" % (boundary,)
        lock = self._locked()
        try:
            doc = self._read()
            act = doc.get("active")
            ok = bool(act) and act.get("token") == token \
                and act.get("status") == "active"
            if not ok:
                doc["quarantine"].append(
                    {"token": str(token), "boundary": boundary, "at": now,
                     "reason": "stale-or-revoked-token",
                     "active_generation": (act or {}).get("generation")})
                self._write(doc)
                return False, ("stale claim token rejected at the %s boundary"
                               % boundary)
            return True, "current claim generation %d" % act["generation"]
        finally:
            lock.close()

    def record(self, receipt):
        """Persist an actuator receipt (call only under the write boundary)."""
        lock = self._locked()
        try:
            doc = self._read()
            doc.setdefault("receipts", []).append(receipt)
            self._write(doc)
        finally:
            lock.close()


def recovery_authorization(run_dir):
    """(ok, why). The SEPARATE written authorization the actuator needs.

    control/recovery-authorization.json is written by the orchestrator or
    operator, never by this module: {"authorized": true, "scope": ["resume"],
    "by": "<name>", "run_id": "<run>"}.
    """
    doc = _json(Path(run_dir) / "control" / "recovery-authorization.json")
    if not isinstance(doc, dict) or doc.get("authorized") is not True:
        return False, "no written authorization at control/recovery-authorization.json"
    scope = doc.get("scope")
    if not isinstance(scope, list) or "resume" not in scope:
        return False, "authorization scope does not admit resume"
    if not str(doc.get("by") or "").strip():
        return False, "authorization names no authority"
    run_id = doc.get("run_id")
    if run_id is not None and str(run_id) not in ("", Path(run_dir).name):
        return False, "authorization is for run %r" % (run_id,)
    return True, "authorized by %s" % doc["by"]


def _factory_control_argv(run_dir):
    """The one supported native control: factory.py next --run-dir."""
    factory = Path(__file__).resolve().parent.parent \
        / "intake_preflight" / "factory.py"
    return [sys.executable, str(factory), "next", "--run-dir", str(run_dir)]


def _run_control(argv):
    """Run the supported control; capture outcome, never raise."""
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "error": str(exc)}
    return {"returncode": res.returncode,
            "stdout_sha256": hashlib.sha256(
                (res.stdout or "").encode("utf-8", "replace")).hexdigest(),
            "stderr_tail": (res.stderr or "")[-400:]}


def actuate_recovery(run_dir, reason="", action="resume", now=None,
                     runner=None, fence_dir=None):
    """One fenced recovery step, executed through the supported native control.

    Separately authorized only (see recovery_authorization); claims a
    monotonic generation token (revoking any old one first), clears the token
    at each fenced boundary, and records the receipt with loaded source
    hashes. It never dispatches provider work (no spend authority), never
    authors creative output and never writes PASS/QC records -- the observer,
    orchestrator, builder and independent reviewer stay distinct roles.
    """
    now = time.time() if now is None else float(now)
    receipt = {"schema_version": RECOVERY_SCHEMA_VERSION,
               "role": "recovery_actuator", "run_dir": str(run_dir),
               "action": str(action), "reason": str(reason), "at": now,
               "steps": [], "acted": False}
    if action not in RECOVERY_ACTIONS:
        receipt["refused"] = {"code": "RECOVERY_ACTION_REFUSED",
                              "detail": "recovery scope is resume only; %r is "
                                        "not this role's work" % (action,)}
        _fail("RECOVERY_ACTION_REFUSED", "%s: %s" % (run_dir, action))
        return receipt
    ok, why = recovery_authorization(run_dir)
    if not ok:
        receipt["refused"] = {"code": "RECOVERY_NOT_AUTHORIZED", "detail": why}
        return receipt
    fence = RecoveryFence(Path(fence_dir) if fence_dir
                          else Path(run_dir) / "control" / "recovery" / "fence.json")
    claim = fence.claim(reason, now=now)     # revokes any old token first
    receipt["claim"] = {"generation": claim["generation"],
                        "token": claim["token"]}
    stale = "stale claim token rejected"

    ok, detail = fence.guard("state", claim["token"], now=now)
    receipt["steps"].append({"boundary": "state", "ok": ok, "detail": detail})
    if ok:
        argv = _factory_control_argv(run_dir)
        outcome = (runner(argv) if runner is not None else _run_control(argv))
        receipt["control"] = {"argv": list(argv), "outcome": outcome}
        receipt["acted"] = True
        if outcome.get("returncode") not in (0, None) or outcome.get("error"):
            _fail("RECOVERY_CONTROL_FAILED",
                  "%s: %s" % (run_dir, outcome.get("error")
                              or "exit %s" % outcome.get("returncode")))
    elif stale in detail:
        _fail("RECOVERY_STALE_TOKEN", "state boundary: %s" % detail)

    ok, detail = fence.guard("write", claim["token"], now=now)
    receipt["steps"].append({"boundary": "write", "ok": ok, "detail": detail})
    if ok:
        fence.record(receipt)
    elif stale in detail:
        _fail("RECOVERY_STALE_TOKEN", "write boundary: %s" % detail)

    ok, detail = fence.guard("evidence", claim["token"], now=now)
    evidence = {"loaded_source_hashes": {
        "run_watch.py": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "factory.py": hashlib.sha256(
            Path(_factory_control_argv(run_dir)[1]).read_bytes()).hexdigest(),
    }}
    receipt["steps"].append({"boundary": "evidence", "ok": ok, "detail": detail})
    if ok:
        receipt["evidence"] = evidence
        fence.record(receipt)
    elif stale in detail:
        _fail("RECOVERY_STALE_TOKEN", "evidence boundary: %s" % detail)

    ok, detail = fence.guard("provider-dispatch", claim["token"], now=now)
    receipt["steps"].append({"boundary": "provider-dispatch", "ok": ok,
                             "detail": detail})
    receipt["provider_dispatch"] = {
        "attempted": False,
        "refused": "RECOVERY_NO_PROVIDER_DISPATCH",
        "why": "recovery carries no spend authority; provider dispatch stays "
               "with the spend-authorized dispatcher",
    }
    if not ok and stale in detail:
        _fail("RECOVERY_STALE_TOKEN", "provider-dispatch boundary: %s" % detail)
    return receipt


# --- the client message ------------------------------------------------------
def _decision_lines(decisions):
    lines = []
    for d in decisions:
        opts = d.get("options") or []
        suffix = " (%s)" % " / ".join(opts) if opts else ""
        lines.append("- %s%s" % (d["question"], suffix))
    return lines


def message_kind(row, decisions, stalled, expired, complete, canceled):
    """One word for what this message is about: the keepalive's own cadence key.

    stopped  the client asked us to stop;
    done     every stage is COMPLETE;
    problem  a stall or the cap: something needs a person;
    needs_you the run cannot move until the client answers;
    progress anything else: ordinary forward motion.
    """
    if canceled:
        return "stopped"
    if complete:
        return "done"
    if stalled or expired:
        return "problem"
    if decisions:
        return "needs_you"
    return "progress"


def message_key(stage, stage_state, completed, decisions, stalled, expired,
                complete, canceled):
    """A 16-hex digest of everything the client message says.

    The same situation carries the same key on the next look, so an unchanged
    run never repeats its message. Any change the client would notice -- a new
    stage, a finished step, a different question, a stall, the end -- changes
    the key.
    """
    ids = sorted(str(d.get("id") or "") for d in decisions)
    blob = json.dumps([str(stage), str(stage_state), int(completed), ids,
                       bool(stalled), bool(expired), bool(complete),
                       bool(canceled)],
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def recovery_acted_ok(recovery):
    """True only when recovery really acted AND the native control returned 0.

    The client is told the run is being picked back up only on this evidence;
    anything else is a person being asked to look, said plainly.
    """
    if not isinstance(recovery, dict) or recovery.get("acted") is not True:
        return False
    outcome = (recovery.get("control") or {}).get("outcome") or {}
    return outcome.get("returncode") == 0


def expected_hours(length_s, agnes=False):
    """The run's expected duration in hours for the song length it chose.

    The table: 1.5 for 60-90 seconds, 3 for 2-3 minutes, 6 for 5 minutes,
    10 for 10 minutes; doubled on the Agnes path. A run that records no
    length (an old run) keeps DEFAULT_MAX_HOURS. The 10-minute row stays in
    the table even when the card stops offering that length, because old runs
    still carry it.
    """
    hours = DEFAULT_MAX_HOURS
    try:
        length = float(length_s)
    except (TypeError, ValueError):
        length = 0.0
    if length > 0:
        for ceiling, value in EXPECTED_HOURS_BY_LENGTH:
            if length <= ceiling:
                hours = value
                break
        else:
            hours = EXPECTED_HOURS_BY_LENGTH[-1][1]
    return hours * 2.0 if agnes else hours


def run_expected_hours(run_dir):
    """(expected_hours, length_s, agnes) read from the run's own records.

    The length is control/method.json's chosen_length_s; the Agnes path is
    the receipt's agnes.answer == "yes" (the same record factory.py reads).
    """
    method = _json(Path(run_dir) / "control" / "method.json")
    length = method.get("chosen_length_s") if isinstance(method, dict) else None
    receipt = _json(Path(run_dir) / "control" / "card-receipt.json")
    agnes = False
    if isinstance(receipt, dict):
        block = receipt.get("agnes")
        agnes = isinstance(block, dict) and block.get("answer") == "yes"
    return expected_hours(length, agnes), length, agnes


def next_canonical_stage(stage):
    """The canonical stage after this one, or None on the last / off-run stage."""
    try:
        n = CANONICAL_STAGES.index(str(stage))
    except ValueError:
        return None
    return CANONICAL_STAGES[n + 1] if n + 1 < len(CANONICAL_STAGES) else None


def progress_message(row, done, total):
    """The three-line progress message: what now, what next, do you need me.

    Step numbers and the total are the twelve canonical stages only; a
    presentation stage after delivery clamps to the last step. `Next` is
    omitted on the last stage. The third line names the approval waiting at
    the next stage when that stage carries one, otherwise it says plainly
    that the client can leave it with us.
    """
    stage = row["stage"]
    step = min(done + 1, total) if total else done + 1
    lines = ["Step %d of %d: %s."
             % (step, total, STAGE_PHRASES.get(
                 stage, "your video is moving through the process"))]
    nxt = next_canonical_stage(stage)
    if nxt is not None:
        lines.append("Next: %s." % STAGE_PHRASES.get(nxt, "the next step"))
        thing = APPROVAL_THINGS.get(nxt)
        if thing:
            lines.append("I'll need your OK on the %s next." % thing)
        else:
            lines.append("You don't need to do anything right now.")
    else:
        lines.append("You don't need to do anything right now.")
    return "\n".join(lines)


def client_message(run_id, row, decisions, stalled, client_reason, expired,
                   complete, elapsed_minutes, done, total, max_hours,
                   canceled=False, recovery=None, reminder_number=None):
    """Plain, warm, direct. No internal codes, no jargon, never a false 'done'.

    No clock stamp either: no elapsed figure, no time of day, no UTC mark. The
    stall reason is `client_reason` -- the fixed plain-words line stall_check
    returns -- and never the operator's own detail text.

    reminder_number is set only by the keepalive's reminder ladder: the
    second and later sends of a needs_you message are reminders, not the first
    message again.
    """
    if row is None:
        return ("I couldn't read where your video is up to just now, and I'm on "
                "it. I'll come back to you with an update.")
    if reminder_number:
        question = ("\n".join(_decision_lines(decisions)) if decisions
                    else "I'm still waiting on your answer.")
        return ("Just a reminder - your video is paused until you answer:\n"
                "%s\nNo rush. Nothing is being charged while it waits."
                % question)
    phrase = STAGE_PHRASES.get(row["stage"], "your video is moving through the process")
    if complete:
        return ("Your video is finished. All %d steps are done, and the finished "
                "file is in your delivery folder. Thank you for your patience."
                % total)
    if canceled:
        return ("You asked us to stop this run, so I've stopped it exactly where "
                "it was: %d of %d steps are finished, and I was working on %s. "
                "Nothing is lost. Tell me when you'd like to pick it back up."
                % (done, total, stage_noun(row["stage"])))
    if expired:
        if recovery_acted_ok(recovery):
            tail = "I'm picking it back up now."
        else:
            tail = ("I've asked a person to look in on it too. "
                    "You don't need to do anything.")
        head = ("Your video is taking longer than usual, so %s %d of %d "
                "steps are finished and nothing is lost." % (tail, done, total))
        if decisions:
            head += "\n\nStill waiting on you:\n" + "\n".join(_decision_lines(decisions))
        return head
    if not stalled and not decisions:
        # Ordinary forward motion: the three-line progress shape answers
        # "how far, what next, do you need me".
        return progress_message(row, done, total)
    parts = ["Here's where we are in the process: %s." % phrase]
    if stalled:
        reason = client_reason or STALL_CLIENT_REASONS["quiet"]
        # "picking it back up" is a promise only an ACTED, successful recovery
        # can keep. Otherwise say a person has been asked to look.
        if recovery_acted_ok(recovery):
            tail = "I'm picking it back up now."
        else:
            tail = ("I've flagged it for a person to look at, and I'll tell you "
                    "as soon as it moves.")
        parts.append("I hit a problem with %s and I'm on it - here's what "
                     "happened: %s. %s" % (stage_noun(row["stage"]), reason, tail))
    if decisions:
        lead = ("I need one thing from you:" if len(decisions) == 1
                else "I need a few things from you:")
        parts.append(lead + "\n" + "\n".join(_decision_lines(decisions)))
    parts.append("%d of %d steps are finished." % (done, total))
    return "\n\n".join(parts)


# --- the one look ------------------------------------------------------------
def explicit_cancellation(run_dir):
    """True only for an explicit recorded user cancellation.

    The record is read as CONTENT (run-state.json {"canceled": true}), never
    as a file timestamp: a copied or touched decision file is not a decision.
    """
    doc = _json(Path(run_dir) / "control" / "run-state.json")
    return isinstance(doc, dict) and doc.get("canceled") is True


def build(run_dir, max_hours=None, now=None,
          recovery_act=False, fence_dir=None, runner=None):
    now = time.time() if now is None else float(now)
    run_dir = str(run_dir)
    expected, _chosen_length, _agnes = run_expected_hours(run_dir)
    if max_hours is None:
        # The cap is the run's OWN expected duration, not one fixed 3-hour
        # number for a 60-second ad and a 10-minute episode alike.
        max_hours = expected
    loud = []
    state, why = read_state(run_dir)
    if state is None:
        loud.append(_fail("HEARTBEAT_STATE_UNREADABLE",
                          "%s (%s)" % (run_dir, why)))
        env = {
            "schema_version": SCHEMA_VERSION,
            "run_id": Path(run_dir).name or "run",
            "stage": "UNKNOWN", "stage_state": "UNKNOWN",
            "elapsed_minutes": 0, "expected_hours": expected,
            "decisions_pending": [],
            "stalled": False, "loud": loud, "expired": False,
            "loop_should_stop": False, "completed_stages": 0,
            "stages_total": 0, "supervising": True, "canceled": False,
            "message_kind": "problem",
            "message_key": message_key("UNKNOWN", "UNKNOWN", 0, [], False,
                                       False, False, False),
            "wait": None, "activity": {"at": None, "source": "none"},
            "recovery": None,
            "message_for_client": client_message(
                Path(run_dir).name or "run", None, [], False, "", False, False,
                0, 0, 0, max_hours),
        }
        return env
    row = current_stage(state["stages"])
    # Count only the twelve canonical stages: the presentation stages in
    # front of delivery are extra work, never extra steps for the client.
    total = sum(1 for r in state["stages"]
                if r["stage"] in CANONICAL_STAGE_SET)
    done = sum(1 for r in state["stages"]
               if r["state"] == "COMPLETE"
               and r["stage"] in CANONICAL_STAGE_SET)
    # Never a false success: completion is every stage COMPLETE, nothing less.
    complete = bool(row) and total > 0 and row["state"] == "COMPLETE" \
        and done == total
    canceled = explicit_cancellation(run_dir)
    # The cap anchors on the EARLIER of the ledger's own created_at and the
    # state store's first row stamp: a ledger opened an hour into a run must
    # not buy that run an extra hour.
    anchors = [float(r["updated_at"]) for r in state["stages"]
               if r.get("updated_at")]
    ledger_start = runs_created_at(run_dir, state["run_id"])
    if ledger_start is not None:
        anchors.append(ledger_start)
    started = min(anchors) if anchors else now
    elapsed_minutes = max(0, int((now - started) // 60))
    decisions = (intake_decisions(run_dir)
                 + approval_decisions(run_dir, state["stages"])
                 + fork_decisions(run_dir))
    stalled, stall_detail, client_reason = stall_check(state, row, now, decisions)
    wait = None if stalled else legitimate_wait(row, decisions)
    activity_at, activity_source = watchdog_clock(state, row)
    # The cap measures the STUDIO's own delay. A run parked on a client
    # answer is not late: it is waiting, and the clock must not turn that
    # into HEARTBEAT_EXPIRED (the client was being told the run ran out of
    # time while the only missing thing was their own reply).
    waiting_on_client = bool(wait) and str(
        (wait or {}).get("kind", "")).startswith("client")
    expired = (elapsed_minutes >= int(max_hours * 60)
               and not complete and not waiting_on_client)
    if stalled:
        loud.append(_fail("HEARTBEAT_STALLED",
                          "%s/%s: %s" % (state["run_id"], row["stage"],
                                         stall_detail)))
    if expired:
        loud.append(_fail("HEARTBEAT_EXPIRED",
                          "%s: %d minutes elapsed, %d/%d stages COMPLETE"
                          % (state["run_id"], elapsed_minutes, done, total)))
    recovery = None
    if stalled and not canceled:
        if recovery_act:
            recovery = actuate_recovery(
                run_dir, reason=stall_detail, action="resume", now=now,
                fence_dir=fence_dir, runner=runner)
        else:
            recovery = {"schema_version": RECOVERY_SCHEMA_VERSION,
                        "role": "recovery_actuator", "acted": False,
                        "command": recovery_command(run_dir),
                        "why": "read-only observer: recovery executes only "
                               "under --recovery-act with a written "
                               "authorization"}
    env = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "stage": row["stage"] if row else "UNKNOWN",
        "stage_state": row["state"] if row else "UNKNOWN",
        "elapsed_minutes": elapsed_minutes,
        "expected_hours": expected,
        "decisions_pending": decisions,
        "stalled": bool(stalled),
        "stall_detail": stall_detail,
        "message_kind": message_kind(row, decisions, stalled, expired,
                                     complete, canceled),
        "message_key": message_key(row["stage"] if row else "UNKNOWN",
                                   row["state"] if row else "UNKNOWN", done,
                                   decisions, stalled, expired, complete,
                                   canceled),
        "wait": wait,
        "activity": {"at": activity_at, "source": activity_source},
        "loud": loud,
        "expired": bool(expired),
        "canceled": bool(canceled),
        # Supervision ends ONLY on verified completion or an explicit user
        # cancellation. A cap, a human wait or a provider wait never stops it.
        "loop_should_stop": bool(complete or canceled),
        "supervising": not bool(complete or canceled),
        "completed_stages": done,
        "stages_total": total,
        "recovery": recovery,
        "recovery_command": recovery_command(run_dir) if stalled else "",
        "message_for_client": client_message(
            state["run_id"], row, decisions, stalled, client_reason, expired,
            complete, elapsed_minutes, done, total, max_hours,
            canceled=canceled, recovery=recovery),
    }
    return env


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One read-only keepalive look at a drama run.")
    ap.add_argument("--run-dir", required=True, help="the run folder ($RUN)")
    ap.add_argument("--interval-check", action="store_true",
                    help="one tick of the 10-minute driver: exit 10 stops the loop")
    ap.add_argument("--max-hours", type=float, default=None,
                    help="the cap from the run's start (default: the run's own "
                         "expected hours for its song length; 3 when the run "
                         "records no length)")
    ap.add_argument("--now", type=float, default=None,
                    help="epoch seconds to judge 'now' by (tests; default: the clock)")
    ap.add_argument("--recovery-act", action="store_true",
                    help="let the fenced actuator EXECUTE recovery (still "
                         "requires the separate written authorization)")
    ap.add_argument("--fence-dir", default=None,
                    help="where the recovery fence ledger lives "
                         "(default: <run>/control/recovery/fence.json)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.run_dir):
        LF.fail("HEARTBEAT_STATE_UNREADABLE", "not a run folder: %s" % a.run_dir)
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "run_id": Path(a.run_dir).name or "run",
                          "stage": "UNKNOWN", "stage_state": "UNKNOWN",
                          "elapsed_minutes": 0, "decisions_pending": [],
                          "stalled": False,
                          "loud": ["HEARTBEAT_STATE_UNREADABLE"],
                          "expired": False, "loop_should_stop": False,
                          "message_kind": "problem",
                          "message_key": message_key("UNKNOWN", "UNKNOWN", 0,
                                                     [], False, False, False,
                                                     False),
                          "message_for_client":
                              "I couldn't find your video's folder just now, and "
                              "I'm on it. I'll come back with an update."},
                         indent=2, sort_keys=True))
        return 1
    env = build(a.run_dir, max_hours=a.max_hours, now=a.now,
                recovery_act=a.recovery_act, fence_dir=a.fence_dir)
    print(json.dumps(env, indent=2, sort_keys=True))
    if a.interval_check:
        return TICK_EXIT_STOP if env["loop_should_stop"] else 0
    return 1 if "HEARTBEAT_STATE_UNREADABLE" in env["loud"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
