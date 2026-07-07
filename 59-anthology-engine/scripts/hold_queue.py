#!/usr/bin/env python3
"""hold_queue.py -- durable credit-out / callback holds, daily age tick, resume-to-cursor.

WHAT THIS IS (SPEC 3.4 row 19; ENGINE-MANIFEST.json script #19; SPEC 5 failure
table "Insufficient credits" / "Kie.ai callback lost"; SPEC 2.2 execution model):
The manager of the Anthology Engine's durable HOLD queue. A stage runner or the
model router HOLDS a participant when a provider runs out of credits (credit_out)
or a Kie.ai cover callback is lost after the bounded re-poll (callback_lost); the
ledger then carries that participant at stage_cursor `held`, at ZERO cost, for
weeks or months. Once a day the smoke test (anthology-smoke-test.py, W1.22) probes
funded-reachability of the five providers and calls this module's AGE TICK, which
re-attempts every clearable hold and RESUMES it to its EXACT recorded pre-hold
cursor. This is the exact failure class that killed the legacy system twice, on
record (SPEC 5); here a credit outage or a six-month pause loses nothing.

THE STATE LAW (binding): this module holds NO durable state of its own and NEVER
writes the ledger or the mirror directly. Every state transition -- placing a hold
and resuming to the recorded cursor -- goes THROUGH the sole ledger writer
anthology_state.py (SPEC 7.4: "NO other code path writes to either store"). This
module only READS the local SQLite mirror (read-only) to enumerate the queue and
compute ages, and SHELLS the sole writer for `hold` and `resume`. A tiny local
progress sidecar (_hold_tick_cursor.json, underscore-prefixed, in the state dir,
NOT ledger domain data) lets a killed daily tick resume from its exact cursor; it
is an optimization only -- correctness rests on the writer's idempotent resume
(a resume of an already-running participant is an acknowledged no-op).

THE CLEARANCE POLICY (SPEC 8.1 chain + SPEC 5):
  credit_out    -> clearable when ANY model-chain provider is funded/reachable
                   (ollama-cloud | openrouter | gemini | minimax); the router will
                   walk the chain, so one funded tier justifies the retry.
  callback_lost -> clearable when the cover callback provider (kie.ai) is reachable.
  strike_out    -> NEVER auto-resumed. A content strike-out is a human decision;
                   standards are never relaxed (SPEC 5). It stays held and surfaced
                   until an operator explicitly clears it (--clear-reasons strike_out).
When the caller passes NO funded set and NO explicit clear list, the tick is
CONSERVATIVE: it ages and reports, and resumes nothing (no blind thrashing).

EXIT CODES (SPEC 3.4 row 19 documents "0; 3 still held"; the rest are the house
convention, applied so a caller never confuses "held" with "failed"):
  0  clean: a resume succeeded, or a tick / list found NOTHING still held
  1  unexpected error (fail-closed; never a silent pass)
  2  validation / guard refusal -- bad reason, unknown participant_key, illegal
     resume target; NOTHING changed
  3  one or more participants remain HELD (a hold was placed; a tick left holds;
     a non-empty queue was listed) -- the "still held" signal
  4  the sole writer or the mirror is unreachable (a dependency, not a held job)

DOCTRINE (binding): move in silence -- operator-verbose on stderr, never a
client-facing message (founder alerts ride alert-dedup.py -> the OpenClaw gateway
only, fail-soft); NOTHING Anthropic anywhere; Convert and Flow is the platform
name in every surface; keying is contact_id, never email; never print a secret
value; config/state writes run as the node user, never root. STDLIB ONLY
(subprocess + sqlite3 + json): zero third-party deps, calls NO model and NO
delivery provider. Runs identically on the operator canary and every client box.

BOUNDARIES / OWNERSHIP: this unit (W1.20) authors ONLY this file. It SHELLS OUT to
the sibling sole-writer anthology_state.py for every ledger WRITE (hold, resume);
it performs side-effect-free READS of the local mirror through a read-only
connection; it never writes either store. Re-dispatch of a resumed stage job is
OPTIONAL and fail-soft (--dispatch-cmd); by default a resume only restores the
cursor and reports it, leaving the actual re-run to the entry orchestrator.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout / sibling contract
# ---------------------------------------------------------------------------
SCRIPTS = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS.parent
STATE_WRITER = SCRIPTS / "anthology_state.py"          # the SOLE ledger writer
ALERT_DEDUP = SCRIPTS / "alert-dedup.py"               # W2.4; optional, fail-soft
DB_FILENAME = "anthology_state.db"
TICK_CURSOR_FILE = "_hold_tick_cursor.json"            # local sidecar, NOT ledger data

# ---------------------------------------------------------------------------
# Exit codes (documented above; keep stable -- callers read these).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_VALIDATION = 2
EX_HELD = 3
EX_LEDGER = 4

# The typed holds (mirror of anthology_state.HOLD_REASONS; SPEC 7.3 / 7.1).
HOLD_REASONS = ("credit_out", "callback_lost", "strike_out")

# Reasons the daily tick may auto-resume once a blocker clears. strike_out is
# DELIBERATELY excluded: content strike-out is a human decision, standards never
# relaxed (SPEC 5). It clears only on an explicit operator override.
AUTO_RESUMABLE = ("credit_out", "callback_lost")

# Provider-role -> the funded providers that clear a hold of that reason. IDs match
# the W0.9 balance-endpoint pins / SPEC 8.1 router chain. Comparison is
# case-insensitive and dot/dash/underscore-insensitive (see _norm_provider).
DEFAULT_MODEL_PROVIDERS = ("ollama-cloud", "openrouter", "gemini", "minimax")
DEFAULT_CALLBACK_PROVIDERS = ("kie", "kie.ai", "kie-ai", "kie_ai", "kieai")

# Which model/callback role clears which hold reason.
_REASON_ROLE = {
    "credit_out": "model",
    "callback_lost": "callback",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Operator-verbose, client-silent: everything human lands on stderr so stdout
    stays a clean JSON channel (doctrine: move in silence)."""
    sys.stderr.write("[hold_queue] %s\n" % msg)


def now_utc() -> str:
    """ISO-8601 UTC, second precision, explicit offset -- byte-identical to
    anthology_state.now_utc so held_at values round-trip."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_ts(raw):
    """Parse an ISO-8601 ledger timestamp to an aware datetime, or None."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_fields(held_at, now_dt):
    """Return (age_seconds, age_days) for a held_at string relative to now_dt.
    Unknown timestamps age to 0 rather than crashing the tick."""
    ts = _parse_ts(held_at)
    if ts is None:
        return 0, 0.0
    secs = max(0, int((now_dt - ts).total_seconds()))
    return secs, round(secs / 86400.0, 4)


def _norm_provider(name):
    """Normalize a provider id for tolerant matching: lowercase, strip, and drop
    '.', '-', '_' so 'Kie.ai', 'kie-ai', 'kie_ai' all collapse to 'kieai'."""
    s = (name or "").strip().lower()
    for ch in (".", "-", "_", " "):
        s = s.replace(ch, "")
    return s


def _norm_set(names):
    return {_norm_provider(n) for n in (names or ()) if _norm_provider(n)}


def _split_csv(raw):
    """A comma/space-separated CLI list -> a clean list (order preserved, no blanks)."""
    if not raw:
        return []
    out = []
    for part in str(raw).replace(",", " ").split():
        p = part.strip()
        if p:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# State path resolution (single source of truth, agreed with anthology_state and
# intake_router: --db > --state-dir > ANTHOLOGY_STATE_DIR > OPENCLAW_DATA_DIR > ~).
# Returns (mirror_db_path, writer_global_argv) so the read side and the write side
# always target the SAME store.
# ---------------------------------------------------------------------------
def resolve_store(state_dir=None, db=None):
    if db:
        db_path = Path(db).expanduser()
        return db_path, ["--db", str(db_path)]
    if state_dir:
        sd = Path(state_dir).expanduser()
    else:
        env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
        if env:
            sd = Path(env).expanduser()
        else:
            data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
            if data:
                sd = Path(data).expanduser() / "anthology-engine" / "state"
            else:
                home = os.environ.get("HOME") or os.path.expanduser("~")
                sd = Path(home) / ".anthology-engine" / "state"
    return sd / DB_FILENAME, ["--state-dir", str(sd)]


def _state_dir_of(db_path: Path) -> Path:
    return Path(db_path).expanduser().parent


# ---------------------------------------------------------------------------
# Read-only mirror access (enumerate the queue + ages). Pure reads: the
# sole-writer contract governs WRITES only.
# ---------------------------------------------------------------------------
class LedgerUnreachable(Exception):
    """The mirror exists but cannot be read (corruption / lock) -> exit 4."""


def _mirror_ro(db_path: Path):
    """Open the mirror READ-ONLY. Returns a connection, or None when the DB does
    not exist yet (an un-provisioned box -> an empty hold queue)."""
    db = Path(db_path)
    if not db.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as exc:
        raise LedgerUnreachable("mirror open failed: %s" % exc)


# The recorded pre-hold cursor + hold metadata for every currently-held
# participant. held_from / held_at / reason come from the LATEST open _holds row
# (resumed_at IS NULL) -- the exact row anthology_state.resume will consume.
_LIST_SQL = """
SELECT
  p.participant_key AS participant_key,
  p.anthology_id    AS anthology_id,
  p.stage_cursor    AS stage_cursor,
  p.hold_reason     AS hold_reason,
  (SELECT h.held_from FROM _holds h
     WHERE h.participant_key = p.participant_key AND h.resumed_at IS NULL
     ORDER BY h.rowid DESC LIMIT 1) AS held_from,
  (SELECT h.reason    FROM _holds h
     WHERE h.participant_key = p.participant_key AND h.resumed_at IS NULL
     ORDER BY h.rowid DESC LIMIT 1) AS hold_row_reason,
  (SELECT h.held_at   FROM _holds h
     WHERE h.participant_key = p.participant_key AND h.resumed_at IS NULL
     ORDER BY h.rowid DESC LIMIT 1) AS held_at
FROM participants p
WHERE p.stage_cursor = 'held'
ORDER BY held_at IS NULL, held_at, p.participant_key
"""


def list_holds(state_dir=None, db=None, now=None):
    """Read-only enumeration of the current hold queue with ages. Each entry:
      participant_key, anthology_id, reason, recorded_cursor (held_from),
      held_at, age_seconds, age_days, anomaly (bool -- held with no recorded
      pre-hold cursor, so it cannot be safely resumed).
    An un-provisioned or empty box returns []."""
    db_path, _ = resolve_store(state_dir=state_dir, db=db)
    now_dt = now or datetime.now(timezone.utc)
    con = _mirror_ro(db_path)
    if con is None:
        return []
    try:
        try:
            rows = con.execute(_LIST_SQL).fetchall()
        except sqlite3.Error as exc:
            # An un-bootstrapped mirror (no participants/_holds tables) has an
            # empty queue by definition; anything else is a genuine read fault.
            msg = str(exc).lower()
            if "no such table" in msg:
                return []
            raise LedgerUnreachable("mirror read failed: %s" % exc)
    finally:
        con.close()

    out = []
    for r in rows:
        reason = r["hold_reason"] or r["hold_row_reason"]
        recorded = r["held_from"]
        age_secs, age_days = _age_fields(r["held_at"], now_dt)
        out.append({
            "participant_key": r["participant_key"],
            "anthology_id": r["anthology_id"],
            "reason": reason,
            "recorded_cursor": recorded,
            "held_at": r["held_at"],
            "age_seconds": age_secs,
            "age_days": age_days,
            "anomaly": recorded is None,
        })
    return out


# ---------------------------------------------------------------------------
# Sole-writer subprocess calls (the ONLY write path to base + mirror).
# ---------------------------------------------------------------------------
def _run_writer(subcmd, writer_globals, extra_args, timeout=25):
    """Invoke anthology_state.py <subcmd> <globals> --json <extra>.
    Returns (rc, parsed_json_or_None, stderr_text). Raises LedgerUnreachable when
    the writer is missing or the transport fails."""
    if not STATE_WRITER.exists():
        raise LedgerUnreachable("sole writer missing: %s" % STATE_WRITER)
    argv = [sys.executable or "python3", str(STATE_WRITER), subcmd] \
        + list(writer_globals) + ["--json"] + list(extra_args)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LedgerUnreachable("sole writer timed out (%ss): %s" % (timeout, subcmd))
    except OSError as exc:
        raise LedgerUnreachable("sole writer spawn failed: %s" % exc)
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


# anthology_state exit codes we interpret (SPEC 3.4 row 1).
_W_OK = 0
_W_ILLEGAL = 2
_W_UNKNOWN = 3
_W_BASE_DEFERRED = 4      # mirror write COMMITTED, base op queued -> locally durable
_W_VALIDATION = 5


# ---------------------------------------------------------------------------
# Optional, fail-soft re-dispatch of a resumed stage job.
# ---------------------------------------------------------------------------
def _dispatch(dispatch_cmd, participant_key, stage, db_path):
    """Best-effort detached re-run of a resumed stage job. dispatch_cmd is a
    template string with {python} {scripts} {skill_dir} {participant_key} {stage}
    {state_dir} placeholders. A dispatch failure NEVER fails the resume (the ledger
    already holds the restored cursor; the next tick or event re-runs it)."""
    if not dispatch_cmd:
        return False
    subst = {
        "python": sys.executable or "python3",
        "scripts": str(SCRIPTS),
        "skill_dir": str(SKILL_DIR),
        "participant_key": participant_key,
        "stage": stage or "",
        "state_dir": str(_state_dir_of(db_path)),
    }
    try:
        argv = [tok.format(**subst) for tok in shlex.split(dispatch_cmd)]
    except (KeyError, ValueError) as exc:
        _log("dispatch template invalid (non-fatal): %s" % exc)
        return False
    if not argv:
        return False
    try:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True, cwd=str(SKILL_DIR))
        return True
    except OSError as exc:  # a spawn failure must not fail the resume
        _log("dispatch spawn failed (non-fatal; ledger holds the cursor): %s" % exc)
        return False


# ---------------------------------------------------------------------------
# Optional, fail-soft founder alert (ONE deduped alert at hold time). The real
# alert path is alert-dedup.py -> the OpenClaw gateway (W2.4). Until that ships,
# this is a silent no-op; it never blocks a hold and never prints a secret.
# ---------------------------------------------------------------------------
def _alert_hold(participant_key, reason, db_path):
    if not ALERT_DEDUP.exists():
        return False
    dedup_key = "anthology_hold::%s::%s" % (reason, participant_key)
    summary = ("Anthology hold placed: %s (reason %s). Daily tick will retry from "
               "the recorded cursor." % (participant_key, reason))
    argv = [sys.executable or "python3", str(ALERT_DEDUP),
            "--dedup-key", dedup_key, "--message", summary,
            "--state-dir", str(_state_dir_of(db_path))]
    try:
        subprocess.run(argv, capture_output=True, text=True, timeout=15)
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        _log("founder alert path unavailable (non-fatal): %s" % exc)
        return False


# ---------------------------------------------------------------------------
# PLACE A HOLD  (ANY -> held, typed) -- state via anthology_state.py hold.
# ---------------------------------------------------------------------------
def place_hold(participant_key, reason, state_dir=None, db=None,
               alert=True, writer_timeout=25):
    """Durably HOLD a participant with a typed reason. Returns (result, exit_code).
    A successful hold exits 3 ("still held") -- the participant IS now held, which
    is the intended, correct outcome (mirrors model_router / the stage runners:
    a held job is signalled by a nonzero 'held' code, not by failure)."""
    if not participant_key:
        return {"ok": False, "action": "hold", "error": "participant_key required"}, EX_VALIDATION
    if reason not in HOLD_REASONS:
        return ({"ok": False, "action": "hold", "participant_key": participant_key,
                 "error": "reason must be one of %s" % (HOLD_REASONS,)}, EX_VALIDATION)
    db_path, wglobals = resolve_store(state_dir=state_dir, db=db)
    try:
        rc, payload, stderr = _run_writer(
            "hold", wglobals,
            ["--participant-key", participant_key, "--reason", reason],
            timeout=writer_timeout)
    except LedgerUnreachable as exc:
        return ({"ok": False, "action": "hold", "participant_key": participant_key,
                 "error": str(exc)}, EX_LEDGER)

    if rc in (_W_OK, _W_BASE_DEFERRED):
        if alert:
            _alert_hold(participant_key, reason, db_path)
        res = {"ok": True, "action": "hold", "participant_key": participant_key,
               "hold_reason": reason, "held": True,
               "noop": bool(payload and payload.get("noop"))}
        if rc == _W_BASE_DEFERRED:
            res["base_deferred"] = True
        return res, EX_HELD
    if rc in (_W_UNKNOWN, _W_ILLEGAL, _W_VALIDATION):
        return ({"ok": False, "action": "hold", "participant_key": participant_key,
                 "error": (payload or {}).get("error") or stderr or "writer refused",
                 "writer_code": rc}, EX_VALIDATION)
    return ({"ok": False, "action": "hold", "participant_key": participant_key,
             "error": stderr or "writer error", "writer_code": rc}, EX_LEDGER)


# ---------------------------------------------------------------------------
# RESUME  -- ONLY to the recorded pre-hold cursor (SPEC 7.3). State via
# anthology_state.py resume; the writer refuses any other target.
# ---------------------------------------------------------------------------
def resume_participant(participant_key, state_dir=None, db=None, to=None,
                       dispatch_cmd=None, writer_timeout=25):
    """Resume a held participant to its EXACT recorded cursor. `to`, when given, is
    an assertion the writer must match (it refuses a mismatched target, exit 2).
    Returns (result, exit_code). A successful resume exits 0 (no longer held)."""
    if not participant_key:
        return {"ok": False, "action": "resume", "error": "participant_key required"}, EX_VALIDATION
    db_path, wglobals = resolve_store(state_dir=state_dir, db=db)
    extra = ["--participant-key", participant_key]
    if to:
        extra += ["--to", to]
    try:
        rc, payload, stderr = _run_writer("resume", wglobals, extra, timeout=writer_timeout)
    except LedgerUnreachable as exc:
        return ({"ok": False, "action": "resume", "participant_key": participant_key,
                 "error": str(exc)}, EX_LEDGER)

    if rc in (_W_OK, _W_BASE_DEFERRED):
        target = (payload or {}).get("stage_cursor")
        noop = bool(payload and payload.get("noop"))
        res = {"ok": True, "action": "resume", "participant_key": participant_key,
               "stage_cursor": target, "resumed": not noop, "noop": noop}
        if rc == _W_BASE_DEFERRED:
            res["base_deferred"] = True
        if not noop:
            res["dispatched"] = _dispatch(dispatch_cmd, participant_key, target, db_path)
        return res, EX_OK
    if rc in (_W_ILLEGAL, _W_UNKNOWN, _W_VALIDATION):
        return ({"ok": False, "action": "resume", "participant_key": participant_key,
                 "error": (payload or {}).get("error") or stderr or "writer refused",
                 "writer_code": rc}, EX_VALIDATION)
    return ({"ok": False, "action": "resume", "participant_key": participant_key,
             "error": stderr or "writer error", "writer_code": rc}, EX_LEDGER)


# ---------------------------------------------------------------------------
# Clearance policy
# ---------------------------------------------------------------------------
def _clearable(reason, funded_norm, model_norm, callback_norm, clear_reasons):
    """Is a hold of `reason` eligible to resume on this tick?
      - an explicit --clear-reasons override always wins (operator top-up / drill);
      - strike_out clears ONLY via that explicit override, never from funding;
      - credit_out clears when a model-chain provider is funded;
      - callback_lost clears when the callback provider is reachable;
      - with no funded set and no override, nothing clears (conservative)."""
    if clear_reasons and reason in clear_reasons:
        return True
    if reason == "strike_out":
        return False
    if reason not in AUTO_RESUMABLE:
        return False
    if not funded_norm:
        return False
    role = _REASON_ROLE.get(reason)
    role_set = model_norm if role == "model" else callback_norm
    return bool(funded_norm & role_set)


# ---------------------------------------------------------------------------
# Tick-cursor sidecar (local progress ledger; NOT ledger domain data). Lets a
# killed daily tick resume from its exact cursor. Correctness rests on the
# writer's idempotent resume; this is an efficiency/observability aid.
# ---------------------------------------------------------------------------
def _read_tick_cursor(db_path: Path):
    path = _state_dir_of(db_path) / TICK_CURSOR_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_tick_cursor(db_path: Path, data: dict) -> None:
    sd = _state_dir_of(db_path)
    try:
        sd.mkdir(parents=True, exist_ok=True)
        tmp = sd / (TICK_CURSOR_FILE + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, sd / TICK_CURSOR_FILE)
    except OSError as exc:
        _log("tick-cursor write skipped (non-fatal): %s" % exc)


# ---------------------------------------------------------------------------
# THE DAILY AGE TICK -- the heartbeat substitute. Enumerate the queue, age every
# hold, resume the clearable ones to their exact cursor, leave the rest held.
# ---------------------------------------------------------------------------
def age_tick(state_dir=None, db=None, funded=None, all_funded=False,
             clear_reasons=None, model_providers=DEFAULT_MODEL_PROVIDERS,
             callback_providers=DEFAULT_CALLBACK_PROVIDERS, dispatch_cmd=None,
             resume_from_cursor=False, now=None, writer_timeout=25):
    """Age and (conditionally) resume the hold queue.

    funded         : iterable of funded/reachable provider ids from the smoke test,
                     or None to age-and-report only (resume nothing).
    all_funded     : treat every model+callback provider as funded (post top-up).
    clear_reasons  : iterable of hold reasons to force-clear (operator override /
                     W5.5 drill); the ONLY way strike_out ever auto-resumes.
    dispatch_cmd   : optional fail-soft re-run template (see _dispatch).
    resume_from_cursor : skip participants a prior interrupted tick already resumed.

    Returns a result dict. Exit code: 3 if anything remains held, else 0
    (4 is raised to the caller as LedgerUnreachable when the mirror is unreadable)."""
    db_path, _ = resolve_store(state_dir=state_dir, db=db)
    now_dt = now or datetime.now(timezone.utc)
    run_id = now_utc()

    model_norm = _norm_set(model_providers)
    callback_norm = _norm_set(callback_providers)
    if all_funded:
        funded_norm = model_norm | callback_norm
    else:
        funded_norm = _norm_set(funded) if funded is not None else set()
    clear_set = set(clear_reasons or ())

    already_done = set()
    if resume_from_cursor:
        prev = _read_tick_cursor(db_path)
        if prev and isinstance(prev.get("resumed_keys"), list):
            already_done = set(prev["resumed_keys"])

    holds = list_holds(state_dir=state_dir, db=db, now=now_dt)  # may raise LedgerUnreachable
    resumed, still_held, anomalies = [], [], []
    resumed_keys = list(already_done)

    for h in holds:
        key = h["participant_key"]
        reason = h["reason"]
        entry = {"participant_key": key, "anthology_id": h["anthology_id"],
                 "reason": reason, "recorded_cursor": h["recorded_cursor"],
                 "age_days": h["age_days"], "age_seconds": h["age_seconds"]}

        if resume_from_cursor and key in already_done:
            entry["skipped"] = "already_resumed_this_run"
            continue

        # Held with no recorded pre-hold cursor: cannot resume safely. Surface it
        # loudly and leave it held (mirrors the writer refusing a cursor-less resume).
        if h["anomaly"] or not h["recorded_cursor"]:
            entry["error"] = "held with no recorded pre-hold cursor; cannot resume"
            anomalies.append(entry)
            still_held.append(entry)
            _write_tick_cursor(db_path, {
                "run_id": run_id, "last_key": key, "resumed_keys": resumed_keys,
                "updated_at": now_utc(), "note": "anomaly_left_held"})
            continue

        if not _clearable(reason, funded_norm, model_norm, callback_norm, clear_set):
            entry["clearable"] = False
            still_held.append(entry)
            _write_tick_cursor(db_path, {
                "run_id": run_id, "last_key": key, "resumed_keys": resumed_keys,
                "updated_at": now_utc()})
            continue

        # Clearable -> resume to the EXACT recorded cursor via the sole writer.
        res, code = resume_participant(
            key, state_dir=state_dir, db=db, to=h["recorded_cursor"],
            dispatch_cmd=dispatch_cmd, writer_timeout=writer_timeout)
        if code == EX_OK and res.get("ok"):
            entry["resumed_to"] = res.get("stage_cursor")
            entry["dispatched"] = res.get("dispatched", False)
            resumed.append(entry)
            resumed_keys.append(key)
        else:
            # Writer refused / unreachable: leave held, record why, keep going.
            entry["clearable"] = True
            entry["resume_error"] = res.get("error")
            still_held.append(entry)
        _write_tick_cursor(db_path, {
            "run_id": run_id, "last_key": key, "resumed_keys": resumed_keys,
            "updated_at": now_utc()})

    result = {
        "ok": True, "action": "tick", "run_id": run_id,
        "total": len(holds), "resumed_count": len(resumed),
        "still_held_count": len(still_held), "anomaly_count": len(anomalies),
        "funded": sorted(funded_norm), "clear_reasons": sorted(clear_set),
        "resumed": resumed, "still_held": still_held, "anomalies": anomalies,
    }
    _write_tick_cursor(db_path, {
        "run_id": run_id, "completed_at": now_utc(),
        "resumed_keys": resumed_keys, "still_held": len(still_held),
        "total": len(holds), "note": "tick_complete"})
    return result, (EX_HELD if still_held else EX_OK)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    action = result.get("action", "?")
    if not result.get("ok", True):
        print("ERROR [%s] %s" % (action, result.get("error", "")), file=sys.stderr)
        return
    if action == "tick":
        print("OK [tick] total=%d resumed=%d still_held=%d anomalies=%d"
              % (result["total"], result["resumed_count"],
                 result["still_held_count"], result["anomaly_count"]))
    elif action == "list":
        print("OK [list] held=%d" % result["count"])
        for h in result["holds"]:
            print("  %-40s reason=%-13s cursor=%-14s age=%.2fd%s"
                  % (h["participant_key"], h["reason"], h["recorded_cursor"],
                     h["age_days"], "  ANOMALY" if h["anomaly"] else ""))
    else:
        print("OK [%s] %s" % (action, {k: v for k, v in result.items()
                                       if k not in ("ok", "action")}))


def _cmd_hold(a):
    return place_hold(a.participant_key, a.reason, state_dir=a.state_dir, db=a.db,
                      alert=not a.no_alert)


def _cmd_resume(a):
    return resume_participant(a.participant_key, state_dir=a.state_dir, db=a.db,
                              to=a.to, dispatch_cmd=a.dispatch_cmd)


def _cmd_list(a):
    holds = list_holds(state_dir=a.state_dir, db=a.db)
    result = {"ok": True, "action": "list", "count": len(holds), "holds": holds}
    return result, (EX_HELD if holds else EX_OK)


def _cmd_tick(a):
    funded = None
    if a.funded is not None:
        funded = _split_csv(a.funded)   # may be [] meaning "explicitly nothing funded"
    clear_reasons = _split_csv(a.clear_reasons) if a.clear_reasons else None
    model_providers = _split_csv(a.model_providers) if a.model_providers else DEFAULT_MODEL_PROVIDERS
    callback_providers = _split_csv(a.callback_providers) if a.callback_providers \
        else DEFAULT_CALLBACK_PROVIDERS
    return age_tick(
        state_dir=a.state_dir, db=a.db, funded=funded, all_funded=a.all_funded,
        clear_reasons=clear_reasons, model_providers=model_providers,
        callback_providers=callback_providers, dispatch_cmd=a.dispatch_cmd,
        resume_from_cursor=a.resume_from_cursor)


def build_parser():
    p = argparse.ArgumentParser(
        prog="hold_queue.py",
        description="Durable credit-out / callback holds, daily age tick, "
                    "resume-to-exact-cursor. State ONLY via anthology_state.py.")
    p.add_argument("--db", help="explicit SQLite mirror path (overrides state dir)")
    p.add_argument("--state-dir", dest="state_dir",
                   help="engine state directory (default: ANTHOLOGY_STATE_DIR / "
                        "OPENCLAW_DATA_DIR / node home)")
    p.add_argument("--json", action="store_true", help="emit the result as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(_fn=fn, _name=name)
        # Accept the globals AFTER the subcommand too (the natural shelling pattern).
        sp.add_argument("--db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--state-dir", dest="state_dir",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    s = add("hold", _cmd_hold, "durable typed hold (ANY -> held) via the sole writer")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--reason", required=True,
                   help="credit_out | callback_lost | strike_out")
    s.add_argument("--no-alert", action="store_true",
                   help="skip the fail-soft founder alert (default: attempt it)")

    s = add("resume", _cmd_resume, "resume ONLY to the recorded pre-hold cursor")
    s.add_argument("--participant-key", required=True)
    s.add_argument("--to", help="optional assertion; must equal the recorded cursor")
    s.add_argument("--dispatch-cmd", dest="dispatch_cmd",
                   help="optional fail-soft detached re-run template "
                        "({python} {scripts} {skill_dir} {participant_key} {stage} {state_dir})")

    add("list", _cmd_list, "read-only: enumerate the hold queue with ages "
        "(exit 0 empty, 3 holds outstanding)")

    s = add("tick", _cmd_tick, "the daily age tick: age + resume clearable holds")
    s.add_argument("--funded", default=None,
                   help="comma/space list of funded+reachable provider ids from the "
                        "smoke test; omit to age-and-report only (resume nothing)")
    s.add_argument("--all-funded", action="store_true",
                   help="treat every model+callback provider as funded (post top-up)")
    s.add_argument("--clear-reasons", dest="clear_reasons", default=None,
                   help="force-clear these hold reasons regardless of funding "
                        "(operator override / drill; the ONLY way strike_out resumes)")
    s.add_argument("--model-providers", dest="model_providers", default=None,
                   help="override the credit_out model-chain provider set")
    s.add_argument("--callback-providers", dest="callback_providers", default=None,
                   help="override the callback_lost provider set")
    s.add_argument("--dispatch-cmd", dest="dispatch_cmd", default=None,
                   help="optional fail-soft detached re-run template for resumed jobs")
    s.add_argument("--resume-from-cursor", dest="resume_from_cursor",
                   action="store_true",
                   help="skip participants a prior interrupted tick already resumed")

    add("selftest", None, "run the in-process acceptance battery (temp state dir)")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    a = parser.parse_args(argv)
    # Normalize suppressed globals so handlers can read a.db / a.state_dir / a.json.
    for attr, default in (("db", None), ("state_dir", None), ("json", False)):
        if not hasattr(a, attr):
            setattr(a, attr, default)

    if a._name == "selftest":
        return run_selftest()

    try:
        result, code = a._fn(a)
        _emit(result, a.json)
        return code
    except LedgerUnreachable as exc:
        payload = {"ok": False, "action": a._name, "error": str(exc)}
        if a.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("LEDGER-UNREACHABLE: %s" % exc, file=sys.stderr)
        return EX_LEDGER
    except Exception as exc:  # noqa: BLE001 -- top-level fail-closed
        print("ERROR: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return EX_ERR


# ===========================================================================
# SELFTEST -- exercises the W1.20 drills against a REAL sole writer on a temp
# state dir, mirror-only mode (no base credential, no network): place holds,
# list + age, a no-funds tick leaves them held (exit 3), a funded tick resumes
# to the EXACT recorded cursor (exit 0), strike_out NEVER auto-resumes, and an
# explicit override clears it. Returns 0 iff every assertion holds.
# ===========================================================================
def _writer(subcmd, wglobals, extra, env):
    argv = [sys.executable or "python3", str(STATE_WRITER), subcmd] \
        + list(wglobals) + ["--json"] + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, env=env)


def run_selftest():
    import tempfile
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        _log("selftest %-46s %s%s" % (name, status, ("  " + detail) if detail else ""))
        if not cond:
            failures.append(name)

    if not STATE_WRITER.exists():
        _log("selftest CANNOT RUN: sole writer missing at %s" % STATE_WRITER)
        return EX_ERR

    # Scrub any base credential so the writer runs mirror-only (offline, exit 0).
    env = dict(os.environ)
    for k in ("ANTHOLOGY_STATE_BASE_ID", "ANTHOLOGY_STATE_AIRTABLE_KEY",
              "AIRTABLE_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_PAT"):
        env.pop(k, None)

    tmp = tempfile.mkdtemp(prefix="hold_queue_selftest_")
    sd = str(Path(tmp) / "state")
    wg = ["--state-dir", sd]
    A, C = "anth_selftest", "contact"

    try:
        # -- provision a minimal ledger: anthology + two participants ------------
        r = _writer("upsert-anthology", wg, ["--anthology-id", A, "--name", "Selftest"], env)
        check("provision anthology (writer exit 0)", r.returncode == 0, r.stderr.strip())

        keys = {}
        for who in ("credit", "strike"):
            r = _writer("upsert-participant", wg,
                        ["--contact-id", "%s_%s" % (C, who), "--anthology-id", A], env)
            check("provision participant %s" % who, r.returncode == 0, r.stderr.strip())
            keys[who] = "%s_%s::%s" % (C, who, A)
            # move the cursor off s0 so the recorded pre-hold cursor is meaningful
            r = _writer("advance-stage", wg,
                        ["--participant-key", keys[who], "--to", "s1_avatar"], env)
            check("advance %s -> s1_avatar" % who, r.returncode == 0, r.stderr.strip())

        # -- place a credit_out hold and a strike_out hold (via THIS module) -----
        res, code = place_hold(keys["credit"], "credit_out", state_dir=sd)
        check("place credit_out hold -> exit 3 (held)", code == EX_HELD and res.get("held"), str(code))
        res, code = place_hold(keys["strike"], "strike_out", state_dir=sd)
        check("place strike_out hold -> exit 3 (held)", code == EX_HELD, str(code))

        # -- validation: a bogus reason is refused, nothing changes --------------
        res, code = place_hold(keys["credit"], "bogus_reason", state_dir=sd)
        check("bad reason -> exit 2 (validation)", code == EX_VALIDATION, str(code))

        # -- hold is idempotent: re-holding an already-held participant no-ops ----
        res, code = place_hold(keys["credit"], "credit_out", state_dir=sd)
        check("re-hold idempotent (noop, still held)", code == EX_HELD and res.get("noop"), str(code))

        # -- list: both are held, credit_out recorded_cursor == s1_avatar --------
        holds = list_holds(state_dir=sd)
        by = {h["participant_key"]: h for h in holds}
        check("list shows 2 holds", len(holds) == 2, str(len(holds)))
        check("credit hold recorded cursor == s1_avatar",
              by.get(keys["credit"], {}).get("recorded_cursor") == "s1_avatar",
              str(by.get(keys["credit"])))
        check("credit hold reason == credit_out",
              by.get(keys["credit"], {}).get("reason") == "credit_out")

        # -- tick with NO funded info: conservative, nothing resumes, exit 3 -----
        res, code = age_tick(state_dir=sd)
        check("tick(no funds) leaves all held -> exit 3",
              code == EX_HELD and res["resumed_count"] == 0 and res["still_held_count"] == 2,
              str(res.get("resumed_count")))

        # -- tick funded by an UNRELATED provider: still nothing clears ----------
        res, code = age_tick(state_dir=sd, funded=["some-other-provider"])
        check("tick(unrelated funded) resumes nothing -> exit 3",
              code == EX_HELD and res["resumed_count"] == 0, str(res.get("resumed_count")))

        # -- tick funded by a model-chain provider: credit_out resumes, strike stays
        res, code = age_tick(state_dir=sd, funded=["ollama-cloud"])
        resumed_keys = {e["participant_key"] for e in res["resumed"]}
        check("tick(model funded) resumes credit_out only",
              res["resumed_count"] == 1 and keys["credit"] in resumed_keys, str(res))
        check("tick(model funded) restores EXACT cursor s1_avatar",
              res["resumed"] and res["resumed"][0]["resumed_to"] == "s1_avatar",
              str(res["resumed"]))
        check("strike_out NOT auto-resumed -> still held (exit 3)", code == EX_HELD)

        # -- confirm the writer actually moved the credit participant off `held` --
        holds = list_holds(state_dir=sd)
        keys_held = {h["participant_key"] for h in holds}
        check("credit participant no longer in queue", keys["credit"] not in keys_held)
        check("strike participant still in queue", keys["strike"] in keys_held)

        # -- all-funded still must NOT clear strike_out --------------------------
        res, code = age_tick(state_dir=sd, all_funded=True)
        check("all-funded still leaves strike_out held -> exit 3",
              code == EX_HELD and res["resumed_count"] == 0, str(res))

        # -- explicit operator override is the ONLY strike_out clearance ----------
        res, code = age_tick(state_dir=sd, clear_reasons=["strike_out"])
        check("override clear-reasons=strike_out resumes it -> exit 0",
              code == EX_OK and res["resumed_count"] == 1
              and res["resumed"][0]["resumed_to"] == "s1_avatar", str(res))

        # -- empty queue: list exit 0, tick exit 0 -------------------------------
        holds = list_holds(state_dir=sd)
        check("queue now empty", len(holds) == 0, str(len(holds)))
        _, code = _cmd_list(argparse.Namespace(state_dir=sd, db=None))
        check("list(empty) -> exit 0", code == EX_OK, str(code))
        res, code = age_tick(state_dir=sd)
        check("tick(empty) -> exit 0", code == EX_OK, str(code))

        # -- resume idempotency: resuming a running participant is a no-op --------
        res, code = resume_participant(keys["credit"], state_dir=sd)
        check("resume(not-held) idempotent no-op -> exit 0",
              code == EX_OK and res.get("noop"), str(code))

        # -- unprovisioned box: an empty queue, never a crash --------------------
        empty_sd = str(Path(tmp) / "nonexistent-state")
        check("list(unprovisioned) == []", list_holds(state_dir=empty_sd) == [])

    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        _log("SELFTEST FAILED (%d): %s" % (len(failures), ", ".join(failures)))
        return EX_ERR
    _log("SELFTEST PASSED (all assertions)")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main())
