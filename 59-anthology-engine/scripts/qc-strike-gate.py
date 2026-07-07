#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: qc-strike-gate.py
# THE STRIKE GATE - TWO COUNTERS, NEVER CONFUSED (SPEC 3.4 row 15; SPEC S5/S6;
# QC-PROTOCOL-AND-MATRIX.md "Instrument 3, the strike cap"; CHECKLIST Part C
# refs 3 and 13).
# -----------------------------------------------------------------------------
# This is Gate B's counter authority. It owns the POLICY for two counters that
# the rest of the engine consults and never re-implements:
#
#   1. PARTICIPANT REWRITE BUDGET = 2, WITH GATE RE-ENTRY (SPEC S6; Part C #3).
#      A participant may Request-rewrite at the S5 chapter gate at most twice.
#      Each rewrite re-enters the same S5 gate. At budget exhaustion the gate
#      offers exactly Approve-as-is OR escalate-to-producer - NEVER a silent
#      third rewrite (a third rewrite is an illegal transition the writer
#      refuses; anthology_state.record-approval enforces the persistence side).
#      This script is the DECISION authority that tells the gate/board which two
#      actions to offer and how much budget remains. It is READ-ONLY for the
#      rewrite counter (the increment is written exactly once, by
#      anthology_state record-approval on s5_participant/request_rewrite, so the
#      count is never double-written).
#
#   2. INTERNAL QC ATTEMPTS = 3 PER DELIVERABLE, THEN HOLD + ONE DEDUPED FOUNDER
#      ALERT (SPEC S5; QC matrix Instrument 3; Part C #13/#18).
#      Each machine-internal deliverable (a chapter draft, a rewrite draft) gets
#      at most three targeted-revision attempts. A failed prover/rubric pass
#      counts one attempt. After the THIRD failed attempt: HOLD the participant
#      (reason strike_out) and notify the founder EXACTLY ONCE through
#      alert-dedup.py, carrying the failing checks and a reference to the best
#      draft. Standards are NEVER relaxed to clear a strike. All attempts share
#      one per-deliverable token budget - that budget lives in
#      anthology-cost-ledger.py / model_router.py, not here; this gate only
#      counts attempts and decides retry-vs-hold.
#
# SOLE-WRITER LAW (SPEC 7.4): this gate NEVER writes the ledger directly. It
# READS the fast SQLite mirror (the sanctioned read path, SPEC 7.2) and persists
# every counter mutation and every hold THROUGH anthology_state.py subcommands
# (set-counter, hold). The founder alert goes THROUGH alert-dedup.py (the single
# deduped gateway-Telegram path, SPEC 3.4 row 21) - never bypassed. Every side
# call is FAIL-SOFT and injectable so this gate is unit-testable with zero
# network and so a not-yet-wired sibling never crashes a running participant.
#
# EXIT CODES (SPEC 3.4 row 15 is normative for 0 and 4; house convention fills
# the standard error classes):
#   0  within budgets - action recorded / decision emitted (incl. idempotent
#      replay and a passing attempt that reset the per-deliverable counter)
#   1  unexpected error
#   2  validation / bad invocation (unknown participant, missing args, no mirror)
#   3  a required sole-writer dependency was unreachable so a counter mutation
#      could NOT be persisted - the gate holds fail-closed rather than loop
#   4  budget OR attempt exhaustion (the hold path): rewrite budget spent (offer
#      Approve-as-is or escalate), or the third QC attempt failed (HOLD + one
#      deduped founder alert)
#
# DOCTRINE: stdlib only (sqlite3 + subprocess + json); calls NO model; move in
# silence (operator-verbose on stderr, NOTHING to any client); zero Anthropic
# identifiers in any runtime file; never print a secret value; standards are
# never relaxed to clear a strike.
# =============================================================================
"""qc-strike-gate.py - the two-counter strike gate for the Anthology Engine."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Exit codes (the S5/S6 runners and the gate engine read these; keep stable).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_VALIDATION = 2
EX_DEP_HELD = 3
EX_EXHAUSTED = 4

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"      # the SOLE ledger writer
ALERT_DEDUP = SCRIPTS / "alert-dedup.py"           # the single deduped alert path

# ---------------------------------------------------------------------------
# The two budgets. These MUST equal anthology_state.py's REWRITE_BUDGET and
# QC_ATTEMPT_CAP; we import them when possible so a future change to the ledger
# constants can never silently diverge, and fall back to the SPEC literals when
# imported in isolation (e.g. a bare unit test of just this file).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised on the real branch where the sibling exists
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import anthology_state as _st  # type: ignore
    REWRITE_BUDGET = int(getattr(_st, "REWRITE_BUDGET", 2))
    QC_ATTEMPT_CAP = int(getattr(_st, "QC_ATTEMPT_CAP", 3))
    _default_state_dir = _st.default_state_dir
    _participant_key = _st.participant_key
except Exception:  # noqa: BLE001 - stay self-sufficient if the sibling is absent
    _st = None
    REWRITE_BUDGET = 2
    QC_ATTEMPT_CAP = 3

    def _default_state_dir() -> Path:
        env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
        if env:
            return Path(env).expanduser()
        data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
        if data:
            return Path(data).expanduser() / "anthology-engine" / "state"
        home = os.environ.get("HOME") or os.path.expanduser("~")
        return Path(home) / ".anthology-engine" / "state"

    def _participant_key(contact_id: str, anthology_id: str) -> str:
        return "%s::%s" % (contact_id, anthology_id)

# The founder alert stays short, single-line, and reference-only (never the
# draft body, never PII beyond the internal composite key, never a secret).
_ALERT_MAX = 900


class StrikeError(Exception):
    """Carries a precise engine exit code."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _warn(msg: str) -> None:
    """Operator-verbose only. NEVER a client-facing surface (silence doctrine)."""
    sys.stderr.write("[qc-strike-gate] %s\n" % msg)


# ---------------------------------------------------------------------------
# READ PATH - the fast SQLite mirror, opened READ-ONLY (SPEC 7.2: reads come
# from the mirror; the writer owns every write). A missing mirror or a missing
# row is a validation error, not a guess.
# ---------------------------------------------------------------------------
def _resolve_db_path(args) -> Path:
    if getattr(args, "db", None):
        return Path(args.db).expanduser()
    if getattr(args, "state_dir", None):
        return Path(args.state_dir).expanduser() / "anthology_state.db"
    return _default_state_dir() / "anthology_state.db"


def _read_participant(db_path: Path, key: str) -> dict:
    if not db_path.exists():
        raise StrikeError(EX_VALIDATION,
                          "no ledger mirror at %s; cannot read strike counters "
                          "for %s" % (db_path, key))
    uri = "file:%s?mode=ro" % db_path
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=15)
    except sqlite3.Error as exc:
        raise StrikeError(EX_VALIDATION, "cannot open mirror read-only: %s" % exc)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT participant_key, contact_id, anthology_id, stage_cursor, "
            "rewrite_count, qc_attempts_current, hold_reason "
            "FROM participants WHERE participant_key=?", (key,)
        ).fetchone()
    except sqlite3.Error as exc:
        raise StrikeError(EX_VALIDATION, "mirror read failed: %s" % exc)
    finally:
        conn.close()
    if not row:
        raise StrikeError(EX_VALIDATION, "unknown participant_key %r" % key)
    return {
        "participant_key": row["participant_key"],
        "contact_id": row["contact_id"],
        "anthology_id": row["anthology_id"],
        "stage_cursor": row["stage_cursor"],
        "rewrite_count": int(row["rewrite_count"] or 0),
        "qc_attempts_current": int(row["qc_attempts_current"] or 0),
        "hold_reason": row["hold_reason"],
    }


# ---------------------------------------------------------------------------
# WRITE PATH - shell the sole ledger writer. Never a direct base/mirror write.
# The db context (--db / --state-dir) is propagated so parent and child hit the
# SAME store. Injectable via `runner` for the self-test.
# ---------------------------------------------------------------------------
def _db_flags(args) -> list:
    flags = []
    if getattr(args, "db", None):
        flags += ["--db", str(Path(args.db).expanduser())]
    elif getattr(args, "state_dir", None):
        flags += ["--state-dir", str(Path(args.state_dir).expanduser())]
    return flags


def _run(argv: list, env=None) -> int:
    return subprocess.call(argv, env=env)


def _set_counter(args, key: str, counter: str, value: int, runner=_run) -> None:
    """Persist a counter THROUGH anthology_state.py set-counter (the sole writer).
    rc 0 = written; rc 4 = mirror committed, base op queued (still effectively
    persisted). Any other rc means the write did NOT land -> raise EX_DEP_HELD so
    the gate holds fail-closed instead of looping on an un-advanced counter."""
    if not STATE_WRITER.is_file():
        raise StrikeError(EX_DEP_HELD,
                          "anthology_state.py (sole ledger writer) absent; cannot "
                          "persist %s for %s" % (counter, key))
    argv = [sys.executable, str(STATE_WRITER), "set-counter",
            "--participant-key", key, "--counter", counter,
            "--value", str(int(value))] + _db_flags(args)
    rc = runner(argv)
    if rc not in (0, 4):
        raise StrikeError(EX_DEP_HELD,
                          "set-counter %s=%d for %s failed (rc=%d); holding "
                          "fail-closed" % (counter, value, key, rc))


def _hold_strike(args, key: str, runner=_run) -> bool:
    """HOLD the participant with reason strike_out via the sole writer. Fail-soft:
    a hold-persistence failure is a loud operator warn but never turns a strike
    into a silent third attempt; the daily reconcile / operator surface catches a
    stuck hold. Returns True iff the mirror hold committed (rc 0 or 4)."""
    if not STATE_WRITER.is_file():
        _warn("anthology_state.py absent; HOLD(strike_out) not persisted for %s "
              "(warn)" % key)
        return False
    argv = [sys.executable, str(STATE_WRITER), "hold",
            "--participant-key", key, "--reason", "strike_out"] + _db_flags(args)
    try:
        rc = runner(argv)
    except Exception as exc:  # noqa: BLE001 - fail-soft
        _warn("hold(strike_out) call failed for %s: %s" % (key, type(exc).__name__))
        return False
    if rc in (0, 4):
        return True
    _warn("hold(strike_out) for %s returned rc=%d; hold may not have persisted "
          "(operator surface)" % (key, rc))
    return False


def _dedupe_key(key: str, deliverable: str) -> str:
    """The STABLE alert key: repeated strike-outs of the SAME deliverable collapse
    to a single founder notification (alert-dedup.py owns the suppression window)."""
    return "content-strike:%s:%s" % (key, deliverable or "deliverable")


def _founder_alert(key: str, deliverable: str, failing: str, best_draft: str,
                   runner=_run) -> bool:
    """ONE deduped founder alert THROUGH alert-dedup.py (gateway Telegram only,
    never bypassed). A STABLE key collapses repeated strike-outs of the same
    deliverable to a single alert. Reference-only message: failing checks + a
    pointer to the best draft, no draft body, no secret. Fail-soft."""
    dedupe_key = _dedupe_key(key, deliverable)
    message = _compose_alert(key, deliverable, failing, best_draft)
    if not ALERT_DEDUP.is_file():
        _warn("alert-dedup.py absent; founder strike alert not sent for %s "
              "(warn). dedupe-key=%s" % (key, dedupe_key))
        return False
    argv = [sys.executable, str(ALERT_DEDUP), "send",
            "--category", "content-strike", "--key", dedupe_key,
            "--message", message]
    try:
        rc = runner(argv)
    except Exception as exc:  # noqa: BLE001 - fail-soft
        _warn("alert-dedup.py call failed for %s: %s" % (key, type(exc).__name__))
        return False
    # rc 3 = gateway unreachable (SPEC 3.4 row 21); dedup owns suppression.
    return rc == 0


def _compose_alert(key: str, deliverable: str, failing: str, best_draft: str) -> str:
    parts = ["ANTHOLOGY STRIKE-OUT: %s QC attempts failed on %s for participant %s."
             % (QC_ATTEMPT_CAP, deliverable or "a deliverable", key)]
    if failing:
        parts.append("Failing checks: %s." % _oneline(failing))
    if best_draft:
        parts.append("Best draft: %s." % _oneline(best_draft))
    parts.append("HELD (strike_out); standards NOT relaxed; needs a human.")
    msg = " ".join(parts)
    if len(msg) > _ALERT_MAX:
        msg = msg[:_ALERT_MAX - 3] + "..."
    return msg


def _oneline(value: str) -> str:
    return " ".join(str(value).split())


# ---------------------------------------------------------------------------
# COUNTER 1 - the participant rewrite budget (READ-ONLY decision).
# ---------------------------------------------------------------------------
def _rewrite_decision(rewrite_count: int) -> dict:
    remaining = max(0, REWRITE_BUDGET - rewrite_count)
    exhausted = remaining <= 0
    if exhausted:
        # No silent third rewrite. The gate offers exactly these two actions.
        actions = ["approve_as_is", "escalate_to_producer"]
    else:
        actions = ["approve_as_is", "request_rewrite"]
    return {
        "counter": "rewrite_count",
        "rewrite_count": rewrite_count,
        "budget": REWRITE_BUDGET,
        "remaining": remaining,
        "exhausted": exhausted,
        "gate_actions": actions,
        "gate_reentry": not exhausted,     # a permitted rewrite re-enters S5
    }


def cmd_rewrite_gate(args) -> int:
    """Report the S5 rewrite-gate decision for a participant. READ-ONLY: the
    increment is owned by anthology_state record-approval (never double-written).
    exit 0 while budget remains; exit 4 at exhaustion (offer approve/escalate)."""
    key = _require_key(args)
    p = _read_participant(_resolve_db_path(args), key)
    dec = _rewrite_decision(p["rewrite_count"])
    result = {"ok": True, "action": "rewrite-gate", "participant_key": key}
    result.update(dec)
    _emit(result, args)
    return EX_EXHAUSTED if dec["exhausted"] else EX_OK


# ---------------------------------------------------------------------------
# COUNTER 2 - the internal QC attempts loop (READ then WRITE through the writer).
# ---------------------------------------------------------------------------
def cmd_begin_deliverable(args, *, set_counter=_set_counter) -> int:
    """Start a fresh deliverable (a new chapter draft, or a rewrite draft): reset
    qc_attempts_current to 0 so each deliverable gets its own three attempts
    (QC matrix Instrument 3: '3 per deliverable'). Idempotent. `set_counter` is
    injectable for the self-test; production uses the real sole-writer channel."""
    key = _require_key(args)
    p = _read_participant(_resolve_db_path(args), key)
    if p["qc_attempts_current"] != 0:
        set_counter(args, key, "qc_attempts_current", 0)
    _emit({"ok": True, "action": "begin-deliverable", "participant_key": key,
           "deliverable": args.deliverable, "qc_attempts_current": 0}, args)
    return EX_OK


def cmd_qc_attempt(args, *, set_counter=_set_counter, hold=_hold_strike,
                   alert=_founder_alert) -> int:
    """Register the outcome of ONE internal QC pass for a deliverable.

      --result pass -> the deliverable cleared Gate B; reset the per-deliverable
                       counter to 0 and exit 0.
      --result fail -> a targeted-revision attempt failed; increment. While
                       fewer than 3 have failed, exit 0 (retry permitted). On the
                       THIRD failure, HOLD(strike_out) + ONE deduped founder alert
                       and exit 4. Standards are never relaxed.

    The three side-effects (set_counter / hold / alert) are injectable so the
    battery can observe the strike path with no ledger base and no gateway;
    production binds them to the real sole-writer and alert-dedup channels."""
    key = _require_key(args)
    result = (args.result or "").strip().lower()
    if result not in ("pass", "fail"):
        raise StrikeError(EX_VALIDATION, "--result must be pass or fail")
    p = _read_participant(_resolve_db_path(args), key)
    current = p["qc_attempts_current"]
    deliverable = args.deliverable or "chapter"

    if result == "pass":
        if current != 0:
            set_counter(args, key, "qc_attempts_current", 0)
        _emit({"ok": True, "action": "qc-attempt", "participant_key": key,
               "result": "pass", "deliverable": deliverable,
               "qc_attempts_current": 0, "held": False}, args)
        return EX_OK

    # result == fail
    # Already at/over the cap on entry -> already struck out: re-affirm the hold
    # (idempotent) and re-send to alert-dedup with the SAME stable key (it
    # collapses to one founder notification), never a 4th attempt.
    if current >= QC_ATTEMPT_CAP:
        held = hold(args, key)
        alert(key, deliverable, args.failing_checks, args.best_draft)
        _emit({"ok": True, "action": "qc-attempt", "participant_key": key,
               "result": "fail", "deliverable": deliverable,
               "qc_attempts_current": current, "attempts_remaining": 0,
               "struck_out": True, "held": held, "standards_relaxed": False,
               "dedupe_key": _dedupe_key(key, deliverable),
               "note": "already at cap; re-affirmed hold, alert deduped"}, args)
        return EX_EXHAUSTED

    new = current + 1
    set_counter(args, key, "qc_attempts_current", new)

    if new < QC_ATTEMPT_CAP:
        remaining = QC_ATTEMPT_CAP - new
        _emit({"ok": True, "action": "qc-attempt", "participant_key": key,
               "result": "fail", "deliverable": deliverable,
               "qc_attempts_current": new, "attempts_remaining": remaining,
               "struck_out": False, "retry": True, "standards_relaxed": False},
              args)
        return EX_OK

    # new == QC_ATTEMPT_CAP -> the third failed attempt -> strike out.
    held = hold(args, key)
    alerted = alert(key, deliverable, args.failing_checks, args.best_draft)
    _emit({"ok": True, "action": "qc-attempt", "participant_key": key,
           "result": "fail", "deliverable": deliverable,
           "qc_attempts_current": new, "attempts_remaining": 0,
           "struck_out": True, "held": held, "founder_alerted": alerted,
           "standards_relaxed": False, "dedupe_key": _dedupe_key(key, deliverable),
           "note": "third QC attempt failed; HELD(strike_out) + one deduped "
                   "founder alert (failing checks + best draft)"}, args)
    return EX_EXHAUSTED


def cmd_status(args) -> int:
    """Emit both counters and both decisions for a participant (READ-ONLY). exit 0
    while both are within budget; exit 4 if EITHER is exhausted."""
    key = _require_key(args)
    p = _read_participant(_resolve_db_path(args), key)
    rewrite = _rewrite_decision(p["rewrite_count"])
    qc_used = p["qc_attempts_current"]
    qc_remaining = max(0, QC_ATTEMPT_CAP - qc_used)
    qc_struck = qc_used >= QC_ATTEMPT_CAP
    result = {
        "ok": True, "action": "status", "participant_key": key,
        "stage_cursor": p["stage_cursor"], "hold_reason": p["hold_reason"],
        "rewrite": rewrite,
        "qc": {"counter": "qc_attempts_current", "attempts_used": qc_used,
               "cap": QC_ATTEMPT_CAP, "remaining": qc_remaining,
               "struck_out": qc_struck},
    }
    _emit(result, args)
    return EX_EXHAUSTED if (rewrite["exhausted"] or qc_struck) else EX_OK


# ---------------------------------------------------------------------------
# CLI plumbing.
# ---------------------------------------------------------------------------
def _require_key(args) -> str:
    key = getattr(args, "participant_key", None)
    if not key or not str(key).strip():
        raise StrikeError(EX_VALIDATION, "--participant-key is required")
    return str(key).strip()


def _emit(result: dict, args) -> None:
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    action = result.get("action", "?")
    slim = {k: v for k, v in result.items() if k not in ("ok", "action")}
    print("OK [%s] %s" % (action, slim))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="qc-strike-gate.py",
        description="The Anthology Engine strike gate: participant rewrite budget "
                    "2 with S5 gate re-entry, and 3 internal QC attempts per "
                    "deliverable then HOLD + one deduped founder alert (SPEC 3.4 "
                    "row 15).")
    p.add_argument("--db", help="explicit SQLite mirror path (overrides state dir)")
    p.add_argument("--state-dir", dest="state_dir",
                   help="engine state directory (default: ANTHOLOGY_STATE_DIR / "
                        "OPENCLAW_DATA_DIR / node home)")
    p.add_argument("--json", action="store_true", help="emit the result as JSON")
    p.add_argument("--self-test", action="store_true",
                   help="run the in-process acceptance battery (temp mirror) and exit")
    sub = p.add_subparsers(dest="cmd")

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(_fn=fn, _name=name)
        sp.add_argument("--db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--state-dir", dest="state_dir",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    s = add("rewrite-gate", cmd_rewrite_gate,
            "report the S5 rewrite-budget decision (READ-ONLY)")
    s.add_argument("--participant-key", dest="participant_key", required=True)

    s = add("qc-attempt", cmd_qc_attempt,
            "register one internal QC attempt (pass resets; 3rd fail = hold+alert)")
    s.add_argument("--participant-key", dest="participant_key", required=True)
    s.add_argument("--result", required=True, help="pass | fail")
    s.add_argument("--deliverable", default="chapter",
                   help="the deliverable under QC (chapter | rewrite | ...)")
    s.add_argument("--failing-checks", dest="failing_checks", default="",
                   help="failing Tier 1 checks / rubric dimensions (alert body)")
    s.add_argument("--best-draft", dest="best_draft", default="",
                   help="reference to the best draft (artifact id / url / path)")

    s = add("begin-deliverable", cmd_begin_deliverable,
            "reset qc_attempts_current to 0 for a fresh deliverable")
    s.add_argument("--participant-key", dest="participant_key", required=True)
    s.add_argument("--deliverable", default="chapter",
                   help="the deliverable beginning its own 3 attempts")

    s = add("status", cmd_status, "emit both counters and both decisions (READ-ONLY)")
    s.add_argument("--participant-key", dest="participant_key", required=True)

    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "self_test", False):
        return run_self_test()
    if not getattr(args, "cmd", None):
        parser.print_help(sys.stderr)
        return EX_VALIDATION
    try:
        return args._fn(args)
    except StrikeError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": exc.message, "code": exc.code},
                             indent=2, ensure_ascii=False))
        else:
            label = {EX_VALIDATION: "VALIDATION", EX_DEP_HELD: "DEPENDENCY-HELD",
                     EX_EXHAUSTED: "EXHAUSTED"}.get(exc.code, "ERROR")
            _warn("%s: %s" % (label, exc.message))
        return exc.code
    except Exception as exc:  # noqa: BLE001 - top-level fail-closed
        _warn("unexpected error: %s: %s" % (type(exc).__name__, exc))
        return EX_ERR


# ===========================================================================
# SELF-TEST - the in-process acceptance battery on a temp mirror (mirror-only;
# zero network; the base env is sanitized so anthology_state runs mirror-only).
# Proves: begin-deliverable resets; three failed attempts step 0->1->2->3 with
# exits 0,0,4; the 3rd failure HOLDs (strike_out) and fires the founder alert
# through a stubbed alert path; a passing attempt resets; the rewrite budget
# decision flips its gate actions and exit code at exhaustion; an unknown
# participant is a clean validation refusal.
# ===========================================================================
def _clean_env() -> dict:
    """A subprocess env with any real base binding removed, so the shelled
    anthology_state.py writes MIRROR-ONLY and never touches a live base."""
    env = dict(os.environ)
    for k in ("ANTHOLOGY_STATE_BASE_ID", "ANTHOLOGY_STATE_AIRTABLE_KEY",
              "AIRTABLE_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_PAT"):
        env.pop(k, None)
    return env


def run_self_test() -> int:  # noqa: C901 - a linear battery reads clearest inline
    if not STATE_WRITER.is_file():
        _warn("self-test SKIPPED: anthology_state.py (sole writer) not present "
              "on this checkout; the strike gate needs it to persist counters.")
        return EX_OK

    tmp = Path(tempfile.mkdtemp(prefix="qc_strike_selftest_"))
    db = tmp / "state.db"
    env = _clean_env()
    checks = []

    def record(label, ok):
        checks.append((label, bool(ok)))

    def st(subargs):
        return subprocess.call(
            [sys.executable, str(STATE_WRITER)] + subargs + ["--db", str(db)],
            env=env)

    # -- seed a producer -> anthology -> participant through the sole writer ----
    contact, anth = "contactSELFTEST01", "anthSELFTEST01"
    key = _participant_key(contact, anth)
    record("seed producer", st(["upsert-producer", "--producer-id", "prodST01"]) == 0)
    record("seed anthology", st(["upsert-anthology", "--anthology-id", anth,
                                 "--producer-id", "prodST01", "--name", "ST"]) == 0)
    record("seed participant", st(["upsert-participant", "--contact-id", contact,
                                   "--anthology-id", anth]) == 0)

    # Build args objects the handlers accept (argparse Namespace-like).
    class A:
        def __init__(self, **kw):
            self.db = str(db)
            self.state_dir = None
            self.json = False
            for k, v in kw.items():
                setattr(self, k, v)

    # A subprocess runner that forces the sanitized (mirror-only) env for the
    # real sole-writer child. Injected into the real _set_counter / _hold_strike.
    def state_runner(argv):
        return subprocess.call(argv, env=env)

    # Injected side-effects: counter + hold hit the REAL sole-writer (mirror-only
    # via the sanitized env); the founder alert is CAPTURED (alert-dedup.py is a
    # separate unit / no gateway here) so we can prove it is invoked exactly once
    # with a stable, reference-only key.
    alert_calls = []

    def inj_set_counter(args_, key_, counter, value):
        return _set_counter(args_, key_, counter, value, runner=state_runner)

    def inj_hold(args_, key_):
        return _hold_strike(args_, key_, runner=state_runner)

    def inj_alert(key_, deliverable, failing, best):
        # capture what the gate WOULD send; prove it carries the stable key and a
        # reference (not the draft body) and no relaxed-standards wording.
        alert_calls.append({"key": key_, "deliverable": deliverable,
                            "dedupe_key": _dedupe_key(key_, deliverable),
                            "message": _compose_alert(key_, deliverable, failing, best)})
        return True

    def qc_fail():
        a = A(result="fail", deliverable="chapter", participant_key=key,
              failing_checks="check5 em-dash; dim4 opening<8",
              best_draft="art_bestdraft_ref_0001")
        return cmd_qc_attempt(a, set_counter=inj_set_counter, hold=inj_hold,
                              alert=inj_alert)

    # -- begin-deliverable resets to 0 -----------------------------------------
    rc = cmd_begin_deliverable(A(deliverable="chapter", participant_key=key),
                               set_counter=inj_set_counter)
    record("begin-deliverable exit 0", rc == EX_OK)
    record("qc reset to 0", _read_participant(db, key)["qc_attempts_current"] == 0)

    # -- three failed attempts: 0->1 (0), 1->2 (0), 2->3 (4, hold+alert) --------
    record("attempt 1 fail -> exit 0", qc_fail() == EX_OK)
    record("counter == 1", _read_participant(db, key)["qc_attempts_current"] == 1)
    record("attempt 2 fail -> exit 0", qc_fail() == EX_OK)
    record("counter == 2", _read_participant(db, key)["qc_attempts_current"] == 2)
    record("attempt 3 fail -> exit 4 (exhausted)", qc_fail() == EX_EXHAUSTED)
    p_after = _read_participant(db, key)
    record("counter == 3 (cap)", p_after["qc_attempts_current"] == 3)
    record("participant HELD(strike_out)",
           p_after["stage_cursor"] == "held" and p_after["hold_reason"] == "strike_out")
    record("founder alert fired exactly once at strike-out", len(alert_calls) == 1)
    record("alert carries stable content-strike key",
           bool(alert_calls) and alert_calls[0]["dedupe_key"]
           == "content-strike:%s:chapter" % key)
    record("alert message carries the best-draft REFERENCE, not the body",
           bool(alert_calls) and "art_bestdraft_ref_0001" in alert_calls[0]["message"])
    record("alert never claims relaxed standards",
           bool(alert_calls) and "NOT relaxed" in alert_calls[0]["message"])

    # a 4th fail must NOT bump the counter past cap; it re-affirms hold and
    # re-sends with the IDENTICAL stable key (alert-dedup collapses to one) ------
    record("4th fail stays exit 4 (no silent 4th attempt)", qc_fail() == EX_EXHAUSTED)
    record("counter still 3 (never exceeds cap)",
           _read_participant(db, key)["qc_attempts_current"] == 3)
    record("repeat strike-out reuses the identical dedupe key",
           len(alert_calls) == 2
           and alert_calls[1]["dedupe_key"] == alert_calls[0]["dedupe_key"])

    # -- a passing attempt resets the per-deliverable counter ------------------
    st(["set-counter", "--participant-key", key, "--counter",
        "qc_attempts_current", "--value", "2"])
    a_pass = A(result="pass", deliverable="rewrite", participant_key=key,
               failing_checks="", best_draft="")
    record("pass -> exit 0",
           cmd_qc_attempt(a_pass, set_counter=inj_set_counter, hold=inj_hold,
                          alert=inj_alert) == EX_OK)
    record("pass reset counter to 0",
           _read_participant(db, key)["qc_attempts_current"] == 0)

    # -- rewrite budget decision flips at exhaustion ---------------------------
    dec0 = _rewrite_decision(0)
    record("rewrite remaining=2 offers request_rewrite",
           dec0["remaining"] == 2 and "request_rewrite" in dec0["gate_actions"]
           and dec0["gate_reentry"] is True)
    dec2 = _rewrite_decision(2)
    record("rewrite exhausted offers escalate, not request_rewrite",
           dec2["exhausted"] and "escalate_to_producer" in dec2["gate_actions"]
           and "request_rewrite" not in dec2["gate_actions"])
    st(["set-counter", "--participant-key", key, "--counter", "rewrite_count",
        "--value", "2"])
    record("rewrite-gate at budget -> exit 4",
           cmd_rewrite_gate(A(participant_key=key)) == EX_EXHAUSTED)

    # -- unknown participant is a clean validation refusal ---------------------
    try:
        cmd_status(A(participant_key="nope::nope"))
        record("unknown participant refused", False)
    except StrikeError as exc:
        record("unknown participant -> validation", exc.code == EX_VALIDATION)

    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    for label, ok in checks:
        print("  [%s] %s" % ("PASS" if ok else "FAIL", label))
    print("qc-strike-gate self-test: %d/%d passed" % (passed, total))
    return EX_OK if passed == total else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
