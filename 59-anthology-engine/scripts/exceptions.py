#!/usr/bin/env python3
# =============================================================================
# SKILL 59 - ANTHOLOGY ENGINE :: exceptions.py
# THE EXCEPTIONS QUEUE: capture, list, resolve-and-replay through S0
# (SPEC 3.4 script #20; SPEC 3.7 module map; data-model-design.md Table Exceptions;
#  dashboard-design.md "EXCEPTIONS SURFACING"; pipeline-design.md event source (f))
# -----------------------------------------------------------------------------
# WHAT THIS IS
#   The operator-side tool for the Exceptions queue. Three verbs (SPEC row 20):
#     capture              record an unresolvable / mismatched / legacy submission
#                          into the Exceptions queue with the RAW payload and a
#                          TYPED reason -- NEVER dropped, NEVER guessed (SPEC S0).
#     list                 project the open / resolved queue for the operator.
#     resolve-and-replay   attach the corrected contact_id / anthology_id (and any
#                          other hidden fields), RE-RUN the submission through S0
#                          (intake_router.py), and, if it now routes, mark the
#                          exception resolved with the created participant_key
#                          (dashboard-design.md: "attach the correct contact_id and
#                          anthology_id, replay through S0").
#   Plus two convenience wrappers over the same core: `reconcile` (batch replay of
#   every OPEN exception, optionally filtered by reason -- the "dashboard
#   reconciliation" of the SPEC failure-mode table) and `show` (one row, redacted).
#
# THE legacy_reconciliation ENTRY TYPE (PRD Section 18; data-model-design.md 39;
# deprecation-plan.md; n8n-integration-design.md)
#   legacy_reconciliation is the ONLY sanctioned legacy-migration entry point: a
#   MANUAL, operator-initiated capture of one legacy participant, brought into the
#   engine by the standard replay-through-S0 path. There is NO bridge tooling and
#   NO migration wave; the legacy n8n system stays ALIVE and UNTOUCHED. Anything a
#   legacy record carries is DATA, never instructions. `capture --reason
#   legacy_reconciliation` (with the participant's fields, or a raw JSON body)
#   opens the row; `resolve-and-replay` then creates the ledger participant.
#
# STATE ONLY VIA anthology_state.py (the sole ledger writer; SPEC 7.4)
#   exceptions.py holds NO independent write path to the base or the mirror. Every
#   WRITE is a subprocess call to anthology_state.py (exception-open,
#   exception-resolve); the participant a replay creates is written by
#   intake_router.py, which itself shells anthology_state.py upsert-participant.
#   Every READ goes through anthology_state.Ledger (its own read layer). The only
#   non-ledger store this module touches is intake_router.py's PRIVATE S0
#   idempotency cache (state_dir/intake/dedup.db): resolve-and-replay resets the
#   claim for the exact submission so routing genuinely re-runs after the operator
#   fixed the underlying condition (e.g. registered the missing anthology). The
#   ledger write stays idempotent through the sole writer, so a reset replay never
#   duplicates a participant or an artifact. The fingerprint is computed with
#   intake_router.py's OWN compute_fingerprint so it can never drift from S0.
#
# EXIT CODES (SPEC 3.4 row 20 pins 0 and 3; the rest reuse the engine convention)
#   0  success (captured; listed; replay routed and the exception resolved;
#      an already-resolved replay no-op; a reconcile batch with nothing left open)
#   1  unexpected error / usage (house; fail-closed, never a silent pass)
#   3  unknown exception id (SPEC row 20)
#   4  the sole writer / ledger could not durably persist a capture or a resolution
#   5  the replay ran deterministically but the submission STILL does not route
#      (the exception remains OPEN; operator attention required)
#
# DOCTRINE: move in silence (operator-verbose on stderr, no client surface); never
# print a secret value (secret-shaped fields are REDACTED before an exception
# preserves the raw body); Convert and Flow is the platform name; keying is
# contact_id, never email; nothing Anthropic ships here (this module makes no model
# call); config / state writes run as the node user, never root.
#
# STDLIB ONLY (subprocess + sqlite3 via the sibling modules). No third-party deps.
# =============================================================================
"""exceptions.py - capture, list, and resolve-and-replay the Anthology Engine
exceptions queue through S0. State only ever via anthology_state.py."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout (siblings in the same scripts/ directory)
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"      # the sole ledger writer
INTAKE_ROUTER = SCRIPTS / "intake_router.py"       # the S0 deterministic front door
PY = sys.executable or "python3"

# ---------------------------------------------------------------------------
# Exit codes (SPEC 3.4 row 20 pins 0 and 3; 1/4/5 reuse the engine convention)
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNKNOWN_ID = 3
EXIT_WRITER_UNREACHABLE = 4
EXIT_REPLAY_UNROUTED = 5

# The five typed reasons (SPEC 7.1 / data-model-design.md Table Exceptions). The
# canonical source is anthology_state.EXCEPTION_REASONS; this fallback mirrors it
# byte-for-byte and the self-test cross-checks the two can never drift.
_FALLBACK_EXCEPTION_REASONS = (
    "unroutable_missing_ids", "unknown_anthology", "stage_mismatch",
    "tenant_mismatch", "legacy_reconciliation",
)

# Leaf key names that may carry the route secret (mirrors intake_router.py's
# route_secret candidates). Redacted before any raw payload is preserved so a
# secret value is never written to the ledger (defense in depth; a legacy or
# operator-supplied body should never carry one).
_SECRET_LEAVES = {
    "route_secret", "_route_secret", "hook_token", "_hook_token",
    "x-anthology-secret", "x_anthology_secret", "authorization",
    "x-openclaw-token", "x_openclaw_token",
}

# The operator-supplyable hidden fields, used both to CONSTRUCT a capture payload
# (legacy_reconciliation / manual) and to ATTACH corrections at resolve-and-replay.
# Keys are the exact top-level names intake_router.py's field_candidates resolve.
_FIELD_FLAGS = (
    ("contact_id", "contact_id"), ("anthology_id", "anthology_id"),
    ("stage", "stage"), ("location_id", "location_id"),
    ("first_name", "first_name"), ("last_name", "last_name"),
    ("email", "email"), ("phone", "phone"),
    ("ideal_avatar", "ideal_avatar"), ("niche", "niche"),
    ("primary_goal", "primary_goal"), ("chapter_about", "chapter_about"),
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Operator-verbose diagnostics on stderr (never a client surface, never a secret)."""
    sys.stderr.write("[exceptions] %s\n" % msg)


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _loads(raw, default=None):
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default


def redact(obj):
    """Mask secret-shaped leaf values before a raw payload is preserved."""
    if isinstance(obj, dict):
        return {k: ("<REDACTED>" if isinstance(k, str) and k.lower() in _SECRET_LEAVES
                    else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def resolve_state_dir(args) -> Path:
    """Single source of truth for the engine state path, AGREED with the siblings:
    --state-dir > ANTHOLOGY_STATE_DIR > OPENCLAW_DATA_DIR/anthology-engine/state > ~."""
    if getattr(args, "state_dir", None):
        return Path(args.state_dir).expanduser()
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def db_path_for(state_dir: Path) -> Path:
    """The mirror path both siblings agree on: <state_dir>/anthology_state.db."""
    return Path(state_dir) / "anthology_state.db"


# ---------------------------------------------------------------------------
# Sibling imports (READ layer + fingerprint). Lazy so --help / arg errors never
# depend on them; a missing sibling degrades gracefully with a clear operator note.
# ---------------------------------------------------------------------------
def _ensure_scripts_on_path():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))


def _import_state():
    _ensure_scripts_on_path()
    import anthology_state as _as  # noqa: E402
    return _as


def _import_intake():
    _ensure_scripts_on_path()
    import intake_router as _ir  # noqa: E402
    return _ir


def exception_reasons() -> tuple:
    """The canonical typed-reason vocabulary from the sole writer, or the mirrored
    fallback if it cannot be imported (the self-test proves the two never drift)."""
    try:
        return tuple(_import_state().EXCEPTION_REASONS)
    except Exception as exc:  # noqa: BLE001
        _log("using fallback EXCEPTION_REASONS (sole writer not importable: %s)" % exc)
        return _FALLBACK_EXCEPTION_REASONS


# ---------------------------------------------------------------------------
# READS: go through anthology_state.Ledger (its own read layer). exceptions.py
# never opens a second write path to the stores.
# ---------------------------------------------------------------------------
def _fetch_exception(db_path: Path, exc_id: str):
    _as = _import_state()
    led = _as.Ledger(Path(db_path))
    try:
        row = led.exception(exc_id)
        return dict(row) if row is not None else None
    finally:
        led.close()


def _query_exceptions(db_path: Path, *, status: str, reason, limit: int):
    _as = _import_state()
    led = _as.Ledger(Path(db_path))
    try:
        where, params = [], []
        if status and status != "all":
            where.append("status=?")
            params.append(status)
        if reason:
            where.append("reason=?")
            params.append(reason)
        sql = "SELECT * FROM exceptions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC, exception_id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in led.conn.execute(sql, params).fetchall()]
    finally:
        led.close()


# ---------------------------------------------------------------------------
# WRITES: subprocess the sole writer / the S0 router (the ONLY write path)
# ---------------------------------------------------------------------------
def _run(argv, timeout):
    """Run a subprocess; return (rc, parsed_json_or_None, stderr_text)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, None, "timeout after %ss" % timeout
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except Exception:  # noqa: BLE001
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def _writer(subcmd_args, state_dir, timeout=30):
    """anthology_state.py <subcmd> --state-dir DIR --json ... (the sole ledger writer)."""
    if not STATE_WRITER.exists():
        raise RuntimeError("sole writer missing: %s" % STATE_WRITER)
    argv = [PY, str(STATE_WRITER), subcmd_args[0],
            "--state-dir", str(state_dir), "--json"] + list(subcmd_args[1:])
    return _run(argv, timeout)


def _intake(payload_json, state_dir, *, trusted=True, spawn=False,
            secret_mode=None, timeout=45):
    """intake_router.py replay: --trusted skips the route-secret check (operator
    replay); --no-spawn keeps the CLI deterministic (the ledger holds the cursor)."""
    if not INTAKE_ROUTER.exists():
        raise RuntimeError("intake router missing: %s" % INTAKE_ROUTER)
    argv = [PY, str(INTAKE_ROUTER), "--payload-json", payload_json,
            "--state-dir", str(state_dir), "--json"]
    if trusted:
        argv.append("--trusted")
    if not spawn:
        argv.append("--no-spawn")
    if secret_mode:
        argv.extend(["--secret-mode", secret_mode])
    return _run(argv, timeout)


def _writer_ok(rc: int) -> bool:
    """The sole writer's durable-write outcomes: 0 committed, 4 mirror committed +
    base queued (still durable). Anything else means the write did not persist."""
    return rc in (0, EXIT_WRITER_UNREACHABLE)


# ---------------------------------------------------------------------------
# S0 idempotency reset (intake_router.py's PRIVATE cache, not the ledger). Lets a
# resolve-and-replay genuinely re-route after the operator fixed the condition.
# Uses intake_router.py's OWN fingerprint so the key can never drift from S0.
# ---------------------------------------------------------------------------
def _clear_intake_dedup(payload: dict, state_dir: Path) -> bool:
    try:
        ir = _import_intake()
        cfg = ir.load_config()
        cid = ir.extract(payload, "contact_id", cfg)
        aid = ir.extract(payload, "anthology_id", cfg)
        stg = ir.extract(payload, "stage", cfg)
        fp = ir.compute_fingerprint(cid, aid, stg, payload, cfg)
    except Exception as exc:  # noqa: BLE001 - best-effort; the attach-ids path still re-keys
        _log("S0 idempotency reset skipped (intake_router unavailable: %s)" % exc)
        return False
    db = Path(state_dir) / "intake" / "dedup.db"
    if not db.exists():
        return False
    try:
        con = sqlite3.connect(str(db), timeout=10)
        con.execute("DELETE FROM intake_seen WHERE fingerprint=?", (fp,))
        con.commit()
        con.close()
        return True
    except sqlite3.Error as exc:
        _log("S0 idempotency reset failed (non-fatal): %s" % exc)
        return False


# ---------------------------------------------------------------------------
# Payload construction (legacy / manual capture) and correction (replay attach)
# ---------------------------------------------------------------------------
def build_payload_from_fields(args, *, default_stage=True) -> dict:
    payload = {}
    for attr, key in _FIELD_FLAGS:
        val = getattr(args, attr, None)
        if val is not None and str(val).strip() != "":
            payload[key] = val
    if default_stage and "stage" not in payload:
        payload["stage"] = "intake"      # constructed intake body (legacy/manual)
    return payload


def collect_overrides(args) -> dict:
    """Only the fields the operator EXPLICITLY set (no default stage injection)."""
    ov = {}
    for attr, key in _FIELD_FLAGS:
        val = getattr(args, attr, None)
        if val is not None and str(val).strip() != "":
            ov[key] = val
    return ov


# ---------------------------------------------------------------------------
# CORE: replay one exception row through S0 -> (exit_code, result_dict)
# ---------------------------------------------------------------------------
def _replay_row(row: dict, state_dir: Path, *, overrides, resolved_by,
                spawn, secret_mode, enforce_secret):
    exc_id = row["exception_id"]
    action = "resolve-and-replay"
    if row.get("status") == "resolved":
        return EXIT_OK, {"ok": True, "action": action, "exception_id": exc_id,
                         "noop": True, "note": "already resolved"}

    obj = _loads(row.get("raw_submission"), {})
    payload = dict(obj) if isinstance(obj, dict) else {}
    if overrides:
        payload.update(overrides)     # attach the corrected contact_id / anthology_id / ...
    payload_json = json.dumps(payload, ensure_ascii=False)

    # reset the S0 idempotency claim so routing genuinely re-runs after the fix
    _clear_intake_dedup(payload, state_dir)

    try:
        rc, ack, err = _intake(payload_json, state_dir, trusted=(not enforce_secret),
                               spawn=spawn, secret_mode=secret_mode)
    except RuntimeError as exc:
        return EXIT_WRITER_UNREACHABLE, {"ok": False, "action": action,
                                         "exception_id": exc_id, "error": str(exc)}
    ack = ack or {}
    pkey = ack.get("participant_key")

    # SUCCESS iff the router created/confirmed a participant (routed, or an
    # intake_confirm no-op that carries the key). A bare exit-0 duplicate with NO
    # participant_key is a prior-exception replay and is NOT routed.
    if rc == 0 and pkey:
        rargs = ["exception-resolve", "--exception-id", exc_id,
                 "--resolved-participant-key", pkey]
        if resolved_by:
            rargs.extend(["--resolved-by", resolved_by])
        wrc, _wp, werr = _writer(rargs, state_dir)
        if _writer_ok(wrc):
            return EXIT_OK, {"ok": True, "action": action, "exception_id": exc_id,
                             "resolved": True, "participant_key": pkey,
                             "routed_action": ack.get("action"),
                             "base_deferred": wrc == EXIT_WRITER_UNREACHABLE}
        return EXIT_WRITER_UNREACHABLE, {
            "ok": False, "action": action, "exception_id": exc_id,
            "error": "routed but the resolution write did not persist",
            "writer_rc": wrc, "detail": werr or None, "participant_key": pkey}

    # NOT routed. If the router opened a fresh transient exception (its exit 3),
    # resolve that artifact so the operator queue count is unchanged; the ORIGINAL
    # stays open for the operator to fix and retry.
    transient = ack.get("exception_id")
    still_reason = ack.get("reason")
    if rc == 3 and transient and transient != exc_id:
        _writer(["exception-resolve", "--exception-id", transient,
                 "--resolved-by", "exceptions.py:replay-artifact-of:%s" % exc_id],
                state_dir)
    if rc == EXIT_WRITER_UNREACHABLE:
        return EXIT_WRITER_UNREACHABLE, {
            "ok": False, "action": action, "exception_id": exc_id,
            "error": "ledger unreachable during replay", "intake_rc": rc}
    return EXIT_REPLAY_UNROUTED, {
        "ok": False, "action": action, "exception_id": exc_id, "resolved": False,
        "still_reason": still_reason or "unrouted", "intake_rc": rc,
        "intake_action": ack.get("action"), "detail": err or None}


# ---------------------------------------------------------------------------
# SUBCOMMAND HANDLERS
# ---------------------------------------------------------------------------
def cmd_capture(args, state_dir, db_path):
    reasons = exception_reasons()
    reason = args.reason
    if reason not in reasons:
        _log("unknown reason %r; must be one of %s" % (reason, ", ".join(reasons)))
        return EXIT_ERROR, {"ok": False, "action": "capture",
                            "error": "unknown reason %r" % reason}

    if args.raw_submission is not None:
        raw_text = args.raw_submission
    elif args.raw_file:
        raw_text = Path(args.raw_file).read_text(encoding="utf-8")
    else:
        raw_text = None

    if raw_text is not None:
        obj = _loads(raw_text, None)
        if obj is None:
            # preserve an unparseable body verbatim; nothing lost, nothing guessed
            stored = {"_raw_unparsed": raw_text, "_captured_utc": _iso()}
        else:
            stored = redact(obj)
    else:
        payload = build_payload_from_fields(args)
        if not [k for k in payload if k != "stage"]:
            _log("nothing to capture: supply --raw-submission/--raw-file or at least "
                 "one field (--contact-id / --anthology-id / --first-name / ...)")
            return EXIT_ERROR, {"ok": False, "action": "capture",
                                "error": "empty capture payload"}
        stored = redact(payload)
    raw_json = json.dumps(stored, ensure_ascii=False)

    wargs = ["exception-open", "--reason", reason, "--raw-submission", raw_json]
    if args.exception_id:
        wargs.extend(["--exception-id", args.exception_id])
    if args.participant_key:
        wargs.extend(["--participant-key", args.participant_key])
    try:
        rc, parsed, err = _writer(wargs, state_dir)
    except RuntimeError as exc:
        return EXIT_WRITER_UNREACHABLE, {"ok": False, "action": "capture",
                                         "error": str(exc)}
    if _writer_ok(rc):
        exc_id = (parsed or {}).get("exception_id")
        return EXIT_OK, {"ok": True, "action": "capture", "exception_id": exc_id,
                         "reason": reason,
                         "base_deferred": rc == EXIT_WRITER_UNREACHABLE}
    return EXIT_WRITER_UNREACHABLE, {"ok": False, "action": "capture",
                                     "error": "capture did not persist",
                                     "writer_rc": rc, "detail": err or None}


def cmd_list(args, state_dir, db_path):
    rows = _query_exceptions(db_path, status=args.status, reason=args.reason,
                             limit=args.limit)
    out = []
    for r in rows:
        item = {"exception_id": r.get("exception_id"), "reason": r.get("reason"),
                "status": r.get("status"), "created_at": r.get("created_at"),
                "resolved_at": r.get("resolved_at"),
                "resolved_participant_key": r.get("resolved_participant_key"),
                "resolved_by": r.get("resolved_by")}
        if args.show_raw:
            item["raw_submission"] = r.get("raw_submission")
        out.append(item)
    return EXIT_OK, {"ok": True, "action": "list", "count": len(out),
                     "status_filter": args.status, "reason_filter": args.reason,
                     "exceptions": out}


def cmd_show(args, state_dir, db_path):
    row = _fetch_exception(db_path, args.exception_id)
    if row is None:
        _log("unknown exception id %r" % args.exception_id)
        return EXIT_UNKNOWN_ID, {"ok": False, "action": "show",
                                 "error": "unknown exception id %r" % args.exception_id}
    return EXIT_OK, {"ok": True, "action": "show", "exception": row}


def cmd_resolve_and_replay(args, state_dir, db_path):
    row = _fetch_exception(db_path, args.exception_id)
    if row is None:
        _log("unknown exception id %r" % args.exception_id)
        return EXIT_UNKNOWN_ID, {"ok": False, "action": "resolve-and-replay",
                                 "error": "unknown exception id %r" % args.exception_id}
    overrides = collect_overrides(args)
    return _replay_row(row, state_dir, overrides=overrides,
                       resolved_by=args.resolved_by, spawn=args.spawn,
                       secret_mode=args.secret_mode, enforce_secret=args.enforce_secret)


def cmd_reconcile(args, state_dir, db_path):
    rows = _query_exceptions(db_path, status="open", reason=args.reason,
                             limit=args.limit)
    results, still_open = [], 0
    for row in rows:
        code, res = _replay_row(row, state_dir, overrides=None,
                                resolved_by=args.resolved_by, spawn=args.spawn,
                                secret_mode=args.secret_mode,
                                enforce_secret=args.enforce_secret)
        results.append(res)
        if code != EXIT_OK:
            still_open += 1
    resolved = len(rows) - still_open
    code = EXIT_OK if still_open == 0 else EXIT_REPLAY_UNROUTED
    return code, {"ok": still_open == 0, "action": "reconcile",
                  "attempted": len(rows), "resolved": resolved,
                  "still_open": still_open, "reason_filter": args.reason,
                  "results": results}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    action = result.get("action", "?")
    if action == "list":
        items = result.get("exceptions", [])
        if not items:
            print("(no exceptions match)")
            return
        for it in items:
            print("%-30s  %-22s  %-9s  %-20s  %s"
                  % (it.get("exception_id") or "-", it.get("reason") or "-",
                     it.get("status") or "-", it.get("created_at") or "-",
                     it.get("resolved_participant_key") or ""))
        print("-- %d exception(s)" % len(items))
        return
    if action == "show":
        print(json.dumps(result.get("exception", {}), indent=2, ensure_ascii=False))
        return
    ok = result.get("ok", True)
    extra = {k: v for k, v in result.items()
             if k not in ("ok", "action", "exceptions", "exception", "results")}
    print("%s [%s] %s" % ("OK" if ok else "ATTENTION", action, extra))
    if action == "reconcile":
        for r in result.get("results", []):
            print("   - %s: %s" % (r.get("exception_id"),
                                   "resolved" if r.get("resolved") else
                                   ("noop" if r.get("noop") else
                                    "OPEN (%s)" % r.get("still_reason"))))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="exceptions.py",
        description="The Anthology Engine exceptions queue: capture, list, and "
                    "resolve-and-replay through S0. State only via anthology_state.py.")
    p.add_argument("--state-dir", help="engine state dir (default: ANTHOLOGY_STATE_DIR "
                   "/ OPENCLAW_DATA_DIR / node home)")
    p.add_argument("--json", action="store_true", help="emit the result as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(_fn=fn, _name=name)
        # accept the global flags AFTER the subcommand too (SUPPRESS so an absent
        # flag never clobbers a value set at the parent level; mirrors anthology_state.py)
        sp.add_argument("--state-dir", dest="state_dir",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    def add_field_flags(sp):
        sp.add_argument("--contact-id", dest="contact_id")
        sp.add_argument("--anthology-id", dest="anthology_id")
        sp.add_argument("--stage")
        sp.add_argument("--location-id", dest="location_id")
        sp.add_argument("--first-name", dest="first_name")
        sp.add_argument("--last-name", dest="last_name")
        sp.add_argument("--email")
        sp.add_argument("--phone")
        sp.add_argument("--ideal-avatar", dest="ideal_avatar")
        sp.add_argument("--niche")
        sp.add_argument("--primary-goal", dest="primary_goal")
        sp.add_argument("--chapter-about", dest="chapter_about")

    s = add("capture", cmd_capture, "capture a submission into the exceptions queue "
            "(typed reason; incl. the legacy_reconciliation entry type)")
    s.add_argument("--reason", required=True,
                   help="one of: %s" % ", ".join(_FALLBACK_EXCEPTION_REASONS))
    s.add_argument("--raw-submission", dest="raw_submission",
                   help="raw payload JSON to preserve verbatim (redacted)")
    s.add_argument("--raw-file", dest="raw_file",
                   help="path to a raw payload file to preserve (redacted)")
    s.add_argument("--participant-key", dest="participant_key",
                   help="optional: mark a KNOWN participant into the exception state")
    s.add_argument("--exception-id", dest="exception_id",
                   help="optional deterministic id (idempotent capture)")
    add_field_flags(s)

    s = add("list", cmd_list, "list exceptions (open / resolved / all)")
    s.add_argument("--status", choices=["open", "resolved", "all"], default="open")
    s.add_argument("--reason", help="filter by typed reason")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--show-raw", dest="show_raw", action="store_true",
                   help="include the stored (redacted) raw payload")

    s = add("show", cmd_show, "show one exception row (redacted)")
    s.add_argument("--exception-id", required=True)

    s = add("resolve-and-replay", cmd_resolve_and_replay,
            "attach corrected ids and replay one exception through S0")
    s.add_argument("--exception-id", required=True)
    s.add_argument("--resolved-by", dest="resolved_by",
                   help="operator label recorded on the resolution")
    s.add_argument("--spawn", action="store_true",
                   help="fire the detached stage job on a successful route "
                        "(default: no-spawn; the ledger holds the cursor)")
    s.add_argument("--secret-mode", dest="secret_mode",
                   choices=["verify_if_present", "required", "off"],
                   help="override the S0 route-secret mode (default: trusted replay)")
    s.add_argument("--enforce-secret", dest="enforce_secret", action="store_true",
                   help="do NOT trust the replay: run the S0 secret check")
    add_field_flags(s)

    s = add("reconcile", cmd_reconcile,
            "batch resolve-and-replay every OPEN exception (dashboard reconciliation)")
    s.add_argument("--reason", help="only replay exceptions with this typed reason")
    s.add_argument("--resolved-by", dest="resolved_by")
    s.add_argument("--spawn", action="store_true")
    s.add_argument("--secret-mode", dest="secret_mode",
                   choices=["verify_if_present", "required", "off"])
    s.add_argument("--enforce-secret", dest="enforce_secret", action="store_true")
    s.add_argument("--limit", type=int, default=1000)

    add("selftest", None, "run the in-process acceptance battery (temp state dir)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args._name == "selftest":
        return run_selftest()
    state_dir = resolve_state_dir(args)
    db_path = db_path_for(state_dir)
    as_json = bool(getattr(args, "json", False))
    try:
        code, result = args._fn(args, state_dir, db_path)
    except FileNotFoundError as exc:
        _log("file not found: %s" % exc)
        print(json.dumps({"ok": False, "error": "%s" % exc}, ensure_ascii=False))
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - top-level fail-closed, never a silent pass
        _log("unexpected error: %s: %s" % (type(exc).__name__, exc))
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return EXIT_ERROR
    _emit(result, as_json)
    return code


# ===========================================================================
# SELFTEST - the in-process acceptance battery (temp state dir; really shells the
# sole writer AND intake_router). Exercises: legacy_reconciliation capture +
# replay; unroutable capture + attach-ids replay; unknown_anthology replay stays
# open (transient artifact cleaned up); unknown-id -> exit 3; reconcile batch
# before and after the operator registers the missing anthology; list filters.
# ===========================================================================
def run_selftest():
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="exceptions_selftest_"))
    state = tmp / "state"
    state.mkdir(parents=True, exist_ok=True)
    db = db_path_for(state)
    checks = []

    def record(label, cond):
        checks.append((label, bool(cond)))
        _log("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    class NS:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def field_defaults(**over):
        base = dict(reason=None, raw_submission=None, raw_file=None,
                    participant_key=None, exception_id=None,
                    resolved_by=None, spawn=False, secret_mode=None,
                    enforce_secret=False, status="open", reason_filter=None,
                    limit=1000, show_raw=False)
        for attr, _ in _FIELD_FLAGS:
            base[attr] = None
        base.update(over)
        return NS(**base)

    # -- provision an anthology with a location binding via the sole writer -------
    rc, _, err = _writer(
        ["upsert-anthology", "--anthology-id", "ANTH1",
         "--caf-location-binding", "LOC-AAA", "--name", "Synthetic Anthology"], state)
    record("provision anthology ANTH1 (writer rc=0)", rc == 0)

    # -- 1. legacy_reconciliation capture (constructed payload) + replay ----------
    a = field_defaults(reason="legacy_reconciliation", exception_id="excLEG1",
                       contact_id="LEG1", anthology_id="ANTH1", stage="intake",
                       location_id="LOC-AAA", first_name="Ada", email="ada@syn.test")
    code, res = cmd_capture(a, state, db)
    record("legacy_reconciliation capture -> exit 0", code == EXIT_OK
           and res.get("exception_id") == "excLEG1")

    a = field_defaults(exception_id="excLEG1", resolved_by="op:selftest")
    code, res = cmd_resolve_and_replay(a, state, db)
    record("legacy replay routes -> exit 0 + resolved", code == EXIT_OK
           and res.get("resolved") and res.get("participant_key") == "LEG1::ANTH1")

    # the participant now exists in the ledger (read through the Ledger)
    _as = _import_state()
    led = _as.Ledger(db)
    try:
        prow = led.participant("LEG1::ANTH1")
        erow = led.exception("excLEG1")
    finally:
        led.close()
    record("legacy participant persisted by the sole writer", prow is not None)
    record("legacy exception now resolved w/ participant_key",
           erow is not None and erow["status"] == "resolved"
           and erow["resolved_participant_key"] == "LEG1::ANTH1")

    # -- 2. unroutable capture (no ids) then ATTACH ids at replay -----------------
    a = field_defaults(reason="unroutable_missing_ids", exception_id="excU1",
                       raw_submission=json.dumps({"stage": "intake",
                                                  "location_id": "LOC-AAA"}))
    code, res = cmd_capture(a, state, db)
    record("unroutable capture -> exit 0", code == EXIT_OK)

    # replay WITHOUT ids still fails (stays open, transient cleaned up) -> exit 5
    a = field_defaults(exception_id="excU1")
    code, res = cmd_resolve_and_replay(a, state, db)
    record("replay w/o ids -> exit 5 still-open", code == EXIT_REPLAY_UNROUTED
           and res.get("resolved") is False)

    # replay WITH corrected ids -> routes -> resolved
    a = field_defaults(exception_id="excU1", contact_id="C2", anthology_id="ANTH1",
                       location_id="LOC-AAA", resolved_by="op:selftest")
    code, res = cmd_resolve_and_replay(a, state, db)
    record("replay w/ attached ids -> exit 0 routed", code == EXIT_OK
           and res.get("resolved") and res.get("participant_key") == "C2::ANTH1")

    # only the ORIGINAL id was ever the operator's tracked row (stable across replays)
    led = _as.Ledger(db)
    try:
        record("attach-ids participant persisted", led.participant("C2::ANTH1") is not None)
        record("excU1 resolved", led.exception("excU1")["status"] == "resolved")
    finally:
        led.close()

    # -- 3. unknown_anthology stays OPEN until the operator registers it ----------
    a = field_defaults(reason="unknown_anthology", exception_id="excK1",
                       raw_submission=json.dumps({"contact_id": "C3",
                                                  "anthology_id": "NOPE",
                                                  "stage": "intake",
                                                  "location_id": "LOC-BBB"}))
    code, res = cmd_capture(a, state, db)
    record("unknown_anthology capture -> exit 0", code == EXIT_OK)

    a = field_defaults(exception_id="excK1")
    code, res = cmd_resolve_and_replay(a, state, db)
    record("replay unknown anthology -> exit 5 still-open",
           code == EXIT_REPLAY_UNROUTED and res.get("still_reason") == "unknown_anthology")

    led = _as.Ledger(db)
    try:
        record("excK1 still open after failed replay",
               led.exception("excK1")["status"] == "open")
        open_rows = led.conn.execute(
            "SELECT COUNT(*) c FROM exceptions WHERE status='open'").fetchone()["c"]
    finally:
        led.close()
    # only excK1 remains open (LEG1 + U1 resolved; every transient artifact resolved)
    record("exactly one exception left open (transients cleaned up)", open_rows == 1)

    # -- 4. unknown exception id -> exit 3 (SPEC row 20) --------------------------
    a = field_defaults(exception_id="does-not-exist")
    code, res = cmd_resolve_and_replay(a, state, db)
    record("resolve-and-replay unknown id -> exit 3", code == EXIT_UNKNOWN_ID)

    a = field_defaults(exception_id="does-not-exist")
    code, res = cmd_show(a, state, db)
    record("show unknown id -> exit 3", code == EXIT_UNKNOWN_ID)

    # -- 5. reconcile batch: fails while NOPE is unknown, succeeds once registered -
    a = field_defaults(reason="unknown_anthology")
    code, res = cmd_reconcile(a, state, db)
    record("reconcile before fix -> exit 5 (1 still open)",
           code == EXIT_REPLAY_UNROUTED and res.get("still_open") == 1)

    rc, _, _ = _writer(["upsert-anthology", "--anthology-id", "NOPE",
                        "--caf-location-binding", "LOC-BBB", "--name", "Late Anthology"], state)
    record("operator registers NOPE (writer rc=0)", rc == 0)

    a = field_defaults(reason="unknown_anthology")
    code, res = cmd_reconcile(a, state, db)
    record("reconcile after fix -> exit 0 (routed)",
           code == EXIT_OK and res.get("still_open") == 0 and res.get("resolved") == 1)

    led = _as.Ledger(db)
    try:
        record("C3::NOPE participant now exists", led.participant("C3::NOPE") is not None)
        record("excK1 resolved after reconcile",
               led.exception("excK1")["status"] == "resolved")
    finally:
        led.close()

    # -- 6. list filters ---------------------------------------------------------
    _c, res = cmd_list(field_defaults(status="open"), state, db)
    record("list open -> empty", res.get("count") == 0)
    _c, res = cmd_list(field_defaults(status="resolved"), state, db)
    record("list resolved -> non-empty", res.get("count") >= 3)

    # -- 7. vocab + fingerprint drift cross-checks against the siblings -----------
    record("EXCEPTION_REASONS match the sole writer",
           set(exception_reasons()) == set(_FALLBACK_EXCEPTION_REASONS))
    try:
        ir = _import_intake()
        cfg = ir.load_config()
        pay = {"contact_id": "Z", "anthology_id": "ANTH1", "stage": "intake"}
        fp = ir.compute_fingerprint(ir.extract(pay, "contact_id", cfg),
                                    ir.extract(pay, "anthology_id", cfg),
                                    ir.extract(pay, "stage", cfg), pay, cfg)
        record("intake fingerprint computable (S0 idempotency reset wired)",
               isinstance(fp, str) and len(fp) == 64)
    except Exception as exc:  # noqa: BLE001
        record("intake fingerprint computable (S0 idempotency reset wired)", False)
        _log("  (fingerprint cross-check error: %s)" % exc)

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)   # a well-behaved test leaves no litter
    passed = sum(1 for _, c in checks if c)
    _log("self-test: %d/%d passed" % (passed, len(checks)))
    if passed == len(checks):
        _log("== exceptions.py selftest: ALL ASSERTIONS PASSED (%d checks) ==" % len(checks))
        return EXIT_OK
    _log("== exceptions.py selftest: FAILURES PRESENT ==")
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
