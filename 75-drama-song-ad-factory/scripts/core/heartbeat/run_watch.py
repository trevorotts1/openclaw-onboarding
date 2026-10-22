#!/usr/bin/env python3
"""run_watch.py -- the 10-minute keepalive for one drama run. Stdlib only.

WHAT IT IS
  One read-only look at a run, for a driver that speaks to the client every
  10 minutes after intake is answered and the run has started:
    (a) the stage and its state, in plain English;
    (b) every pending decision in front of the client (intake outstanding,
        approval gates, a cost fork whose recorded decision is "wait");
    (c) a stall (no event for 30 minutes on the current stage, a dead lease,
        or a STALE row) -- and the exact factory.py command the AGENT runs to
        pick it back up;
    (d) the 3-hour cap, anchored on spend_ledger runs.created_at, with a final
        wrap-up message and a loud FAILURE when the job is not COMPLETE.

WHAT IT NEVER DOES
  It never writes. The state database is opened `mode=ro`; fork-decisions.json,
  run-state.json, song-choices/ and the spend ledger are only read. Stall
  recovery is a PRINTED command, never a mutation run here -- no claim, no
  re-dispatch, no card answer on the client's behalf, no spend.

CLI
  python3 scripts/core/heartbeat/run_watch.py --run-dir <RUN>
      [--interval-check] [--max-hours 3] [--now <epoch seconds>]

  --interval-check  this process is one tick of the 10-minute driver: exit 10
                    means the loop is over (the run is COMPLETE or the 3-hour
                    cap was reached), exit 0 means keep looping.

EXIT
  0   envelope printed, loop continues (or, without --interval-check, read ok)
  10  --interval-check only: stop the loop (COMPLETE or expired)
  1   the run state could not be read (loud: HEARTBEAT_STATE_UNREADABLE)

ENVELOPE (one JSON object on stdout)
  {run_id, stage, stage_state, elapsed_minutes, decisions_pending, stalled,
   loud, expired, message_for_client, ... extras (stall_detail,
   recovery_command, loop_should_stop, completed_stages, schema_version)}

LOUD CODES (loud_failure.py, printed to stderr AND carried in the envelope)
  HEARTBEAT_STATE_UNREADABLE  the state database is missing or unreadable
  HEARTBEAT_STALLED           the current stage made no progress in 30 minutes
  HEARTBEAT_EXPIRED           the 3-hour cap was reached, job not COMPLETE
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "blackceo.drama-run-watch/v1"
TOOL_VERSION = "1.0.0"

STALL_AFTER_S = 30 * 60
DEFAULT_MAX_HOURS = 3.0
TICK_EXIT_STOP = 10

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
    """Read-only connection. A run is NEVER mutated by this module."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


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


_HUMAN_DECISION_FILES = ("control/method.json", "control/card-answers.json",
                         "control/studio-order.json",
                         "music/acceptance/operator-decision.json",
                         "song-choices/fork-decision.json")


def human_decision_at(run_dir):
    """Newest human/operator decision artifact in the run, or None.

    The 3-hour window measures from the LAST HUMAN DECISION, not from intake:
    a client-paced run otherwise expires before the client ever answers, which
    is exactly how a 25-hour stall reported HEARTBEAT_EXPIRED instead of
    continuing the work a person had already approved.
    """
    newest = 0.0
    for rel in _HUMAN_DECISION_FILES:
        p = Path(run_dir) / rel
        try:
            if p.is_file():
                newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    try:
        for p in Path(run_dir).rglob("script-approval.json"):
            try:
                newest = max(newest, p.stat().st_mtime)
            except OSError:
                pass
    except OSError:
        pass
    return newest or None


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


def stall_check(run_dir, state, row, now):
    """(stalled, detail). A client wait is not a stall; silence is."""
    if row is None:
        return False, ""
    stage, st = row["stage"], row["state"]
    if st == "STALE":
        return True, ("the run marked %s stale: %s"
                      % (stage, row.get("reason") or "no reason recorded"))
    lease = row.get("lease_expires")
    if isinstance(lease, (int, float)) and lease > 0 and lease < now \
            and st in ("RUNNING", "WAITING_PROVIDER", "QC"):
        return True, ("the worker on %s stopped checking in and its turn ran out "
                      "at %s" % (stage, _utc_iso(lease)))
    if st == "WAITING_APPROVAL":
        return False, ""           # the client owes an answer, not the run
    last = max(float(row.get("updated_at") or 0),
               state["events_by_stage"].get(stage, 0.0))
    quiet = now - last if last else None
    if quiet is not None and quiet > STALL_AFTER_S:
        return True, ("nothing has moved on %s for %d minutes"
                      % (stage, int(quiet // 60)))
    return False, ""


def recovery_command(run_dir):
    """The exact command the AGENT runs to pick the run back up. Printed only."""
    return ("python3 scripts/core/intake_preflight/factory.py next --run-dir %s"
            % run_dir)


# --- the client message ------------------------------------------------------
def _decision_lines(decisions):
    lines = []
    for d in decisions:
        opts = d.get("options") or []
        suffix = " (%s)" % " / ".join(opts) if opts else ""
        lines.append("- %s%s" % (d["question"], suffix))
    return lines


def client_message(run_id, row, decisions, stalled, stall_detail, expired,
                   complete, elapsed_minutes, done, total, max_hours):
    """Plain, warm, direct. No internal codes, no jargon, never a false 'done'."""
    if row is None:
        return ("I couldn't read where your video is up to just now, and I'm on "
                "it. I'll come back to you with an update.")
    phrase = STAGE_PHRASES.get(row["stage"], "your video is moving through the process")
    if complete:
        return ("Your video is finished. All %d steps are done, and the finished "
                "file is in your delivery folder. Thank you for your patience."
                % total)
    if expired:
        head = ("Time's up for this round (we allow %g hours), so I'm stopping "
                "here and handing this to a person. Here's where your video "
                "stands: %d of %d steps are finished, and I was working on %s. "
                "Nothing is lost and nothing was thrown away."
                % (max_hours, done, total, stage_noun(row["stage"])))
        tail = (" Someone will pick this up from exactly here and come back to "
                "you with the next step.")
        if decisions:
            tail += "\n\nStill waiting on you:\n" + "\n".join(_decision_lines(decisions))
        return head + tail
    parts = ["Here's where we are in the process: %s." % phrase]
    if stalled:
        reason = stall_detail or "it stopped responding"
        parts.append("I hit a problem with %s and I'm on it - here's what "
                     "happened: %s. I'm picking it back up now."
                     % (stage_noun(row["stage"]), reason))
    if decisions:
        lead = ("I need one thing from you:" if len(decisions) == 1
                else "I need a few things from you:")
        parts.append(lead + "\n" + "\n".join(_decision_lines(decisions)))
    parts.append("%d of %d steps are finished." % (done, total))
    return "\n\n".join(parts)


# --- the one look ------------------------------------------------------------
def configured_max_hours(run_dir, fallback=DEFAULT_MAX_HOURS):
    """The run's own cap: config.json "max_hours", else RUN_WATCH_MAX_HOURS,
    else the 3 h default. A human-paced production run needs a longer window
    than the anti-runaway default, and the owner sets it per run."""
    try:
        import json as _json
        with open(Path(run_dir) / "config.json", encoding="utf-8") as fh:
            cfg = _json.load(fh)
        if isinstance(cfg, dict):
            v = cfg.get("max_hours")
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
    except (OSError, ValueError):
        pass
    try:
        import os as _os
        v = float(_os.environ.get("RUN_WATCH_MAX_HOURS", ""))
        if v > 0:
            return v
    except (TypeError, ValueError):
        pass
    return fallback


def build(run_dir, max_hours=None, now=None):
    if max_hours is None:
        max_hours = configured_max_hours(run_dir)
    now = time.time() if now is None else float(now)
    run_dir = str(run_dir)
    loud = []
    state, why = read_state(run_dir)
    if state is None:
        loud.append(_fail("HEARTBEAT_STATE_UNREADABLE",
                          "%s (%s)" % (run_dir, why)))
        env = {
            "schema_version": SCHEMA_VERSION,
            "run_id": Path(run_dir).name or "run",
            "stage": "UNKNOWN", "stage_state": "UNKNOWN",
            "elapsed_minutes": 0, "decisions_pending": [],
            "stalled": False, "loud": loud, "expired": False,
            "loop_should_stop": False, "completed_stages": 0,
            "stages_total": 0,
            "message_for_client": client_message(
                Path(run_dir).name or "run", None, [], False, "", False, False,
                0, 0, 0, max_hours),
        }
        return env
    row = current_stage(state["stages"])
    total = len(state["stages"])
    done = sum(1 for r in state["stages"] if r["state"] == "COMPLETE")
    complete = bool(row) and row["state"] == "COMPLETE" and done == total
    # The cap anchors on the EARLIER of the ledger's own created_at and the
    # state store's first row stamp: a ledger opened an hour into a run must
    # not buy that run an extra hour.
    anchors = [float(r["updated_at"]) for r in state["stages"]
               if r.get("updated_at")]
    ledger_start = runs_created_at(run_dir, state["run_id"])
    if ledger_start is not None:
        anchors.append(ledger_start)
    started = min(anchors) if anchors else now
    human = human_decision_at(run_dir)
    if human is not None and human > started:
        started = human
    elapsed_minutes = max(0, int((now - started) // 60))
    stalled, stall_detail = stall_check(run_dir, state, row, now)
    decisions = (intake_decisions(run_dir)
                 + approval_decisions(run_dir, state["stages"])
                 + fork_decisions(run_dir))
    expired = elapsed_minutes >= int(max_hours * 60) and not complete
    if stalled:
        loud.append(_fail("HEARTBEAT_STALLED",
                          "%s/%s: %s" % (state["run_id"], row["stage"],
                                         stall_detail)))
    if expired:
        loud.append(_fail("HEARTBEAT_EXPIRED",
                          "%s: %d minutes elapsed, %d/%d stages COMPLETE"
                          % (state["run_id"], elapsed_minutes, done, total)))
    env = {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "stage": row["stage"] if row else "UNKNOWN",
        "stage_state": row["state"] if row else "UNKNOWN",
        "elapsed_minutes": elapsed_minutes,
        "decisions_pending": decisions,
        "stalled": bool(stalled),
        "stall_detail": stall_detail,
        "loud": loud,
        "expired": bool(expired),
        "loop_should_stop": bool(complete or expired),
        "completed_stages": done,
        "stages_total": total,
        "recovery_command": recovery_command(run_dir) if stalled else "",
        "message_for_client": client_message(
            state["run_id"], row, decisions, stalled, stall_detail, expired,
            complete, elapsed_minutes, done, total, max_hours),
    }
    return env


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="One read-only keepalive look at a drama run.")
    ap.add_argument("--run-dir", required=True, help="the run folder ($RUN)")
    ap.add_argument("--interval-check", action="store_true",
                    help="one tick of the 10-minute driver: exit 10 stops the loop")
    ap.add_argument("--max-hours", type=float, default=None,
                    help="the hard cap from the run's start (default 3)")
    ap.add_argument("--now", type=float, default=None,
                    help="epoch seconds to judge 'now' by (tests; default: the clock)")
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
                          "message_for_client":
                              "I couldn't find your video's folder just now, and "
                              "I'm on it. I'll come back with an update."},
                         indent=2, sort_keys=True))
        return 1
    env = build(a.run_dir, max_hours=a.max_hours, now=a.now)
    print(json.dumps(env, indent=2, sort_keys=True))
    if a.interval_check:
        return TICK_EXIT_STOP if env["loop_should_stop"] else 0
    return 1 if "HEARTBEAT_STATE_UNREADABLE" in env["loud"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
