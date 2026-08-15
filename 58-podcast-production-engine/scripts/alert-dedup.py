#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: FOUNDER ALERT DEDUP (Furnace Guardrail 7)
# -----------------------------------------------------------------------------
# The ONE and ONLY path to the founder's alert channel for this skill. Pipeline
# code NEVER sends Telegram directly; it calls this script, which decides whether
# to send and, when it does, routes THROUGH the OpenClaw gateway
# (openclaw message send --channel telegram), never around it, and never by
# hitting the Telegram bot HTTP API directly. Every send targets the FOUNDER /
# OPERATOR channel only; a client chat target is structurally never used.
# MOVE IN SILENCE.
#
# Design source: project-prds/podcast-engine/design/furnace-design.md, Guardrail 7.
#
# WHAT IT ENFORCES (all from the design):
#   * Keying: every alert is keyed client + service + failure_class (decision
#     class also adds episode, so it dedups per episode).
#   * Dedup window: repeats of the same key inside alerts.dedup_window_hours
#     (default 6) are SUPPRESSED; the counter and affected-episode list update in
#     place. A downed Fish Audio with 20 queued jobs produces ONE alert, not 20.
#   * Window expiry while still failing: ONE updated digest per key ("still down,
#     now N episodes queued, oldest X days").
#   * Recovery: ONE recovery message when the service flips back to PASS and the
#     queue drains, then the key clears.
#   * Storm cap: alerts.max_founder_alerts_per_client_per_day (default 4). Beyond
#     the cap, STATUS-class alerts collapse into a single end-of-day digest per
#     client. DECISION-class (QC three-strike, cost_hold) ALWAYS send (they are
#     decision requests, not status) but still dedup per episode.
#   * Digest-class (aged-out drops, daily-cap deferrals, soft-ceiling warnings)
#     never send immediately; they accumulate and flush once per day.
#   * NOTIFY-RETRY: a failed gateway send is CLASSIFIED AT THE DISPATCH SITE from
#     the gateway detail string only: transport-down (timeout, connection
#     refused, binary absent) keeps retrying with capped exponential backoff and
#     is NEVER discarded - a BLOCKED alert is wanted when infrastructure breaks.
#     A POISONED payload (application-layer rejection: bad target, chat not
#     found, malformed content) is parked to state_dir/alert-park/parked.jsonl
#     with its FULL content preserved and surfaced; it is never re-dispatched.
#     No distinguishing evidence -> UNDETERMINED -> the safe default: unbounded
#     retry with backoff. There is NO terminal retry cap anywhere: an alert is
#     retried forever or parked, never dropped. Parking is automatic (no human
#     flag) and a parked key can never re-enter the retry loop via cron.
#
# STDLIB ONLY. No network except the gateway CLI subprocess. No model turn, no
# MCP, no third-party imports. Runs identically on operator and client boxes.
#
# EXIT CODE CONTRACT:
#   0  OK              - alert processed (sent, suppressed, deferred, parked,
#                        recovered, flushed, or noop). The decision JSON is on
#                        stdout.
#   2  SEND_FAILED     - a send was warranted but the gateway invocation failed
#                        (nonzero rc or the openclaw binary is absent). State is
#                        still recorded; the alert is retry-pending (capped
#                        exponential backoff) or parked, never lost. Never
#                        crashes the pipeline.
#   3  USAGE/IO        - bad arguments, or the state directory is unreadable /
#                        unwritable (fail-closed, still emits JSON where possible).
#   4  NO_FOUNDER      - a send was warranted but NO founder/operator target is
#                        configured. Nothing was sent to anyone (a client chat is
#                        never a fallback). Flagged so the canary catches the
#                        misconfiguration.
# =============================================================================
"""Founder alert dedup for the Podcast Production Engine (furnace Guardrail 7)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:  # POSIX advisory locking so concurrent pipeline steps do not race the state
    import fcntl
    _HAVE_FCNTL = True
except Exception:  # pragma: no cover - non-POSIX fallback
    _HAVE_FCNTL = False

# ---- exit codes -------------------------------------------------------------
EXIT_OK = 0
EXIT_SEND_FAILED = 2
EXIT_USAGE = 3
EXIT_NO_FOUNDER = 4

# ---- design defaults (furnace-design.md Section 8; per-client overridable) ---
DEFAULT_DEDUP_WINDOW_HOURS = 6
DEFAULT_MAX_FOUNDER_ALERTS_PER_CLIENT_PER_DAY = 4

# ---- failure classification + retry semantics --------------------------------
# A founder alert is NEVER silently dropped. When the gateway send fails, the
# failure is classified from the evidence the dispatch site actually has (the
# gateway detail string) into one of three classes:
#   * transport-down     - the network/gateway/CLI layer refused the attempt
#     (connection refused, timeout, binary absent, etc.). The alert is BLOCKED,
#     and a blocked alert is exactly the condition the founder wants to hear
#     about: keep retrying with exponential backoff, NEVER discard, NEVER a
#     terminal cap that loses the alert.
#   * poisoned           - the payload itself was rejected at the application
#     layer (a 4xx-class gateway response, a bad/unroutable target, malformed
#     content). Retrying can never change the verdict, so the message is parked:
#     its full content is kept, it is surfaced to an operator-facing park file,
#     and it is NEVER re-dispatched (no retry, not recoverable into an unbounded
#     retry loop by any cron).
#   * undetermined       - no distinguishing evidence either way. The safe
#     default is RETRY with backoff forever; a terminal cap that loses alerts is
#     structurally impossible here.
#
# Backoff is exponential with a cap on the DELAY (never a cap on attempts):
#   delay = BACKOFF_BASE_SECONDS * 2^(attempt-1), capped at BACKOFF_MAX_SECONDS.
# Defaults: 60s, 120s, 240s, 480s, then 900s forever after (cap 15 minutes).
# NOTIFY_RETRY_BASE_SECONDS exists only so the test harness can shrink the
# delays; unset in production the shipped values above stand.
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 900

# Detail substrings that identify TRANSPORT-layer failures (retry forever).
# Everything here is evidence the SEND never got a verdict from the gateway.
_TRANSPORT_EVIDENCE = (
    "gateway send timed out",
    "gateway send failed:",          # OSError/SubprocessError subclasses
    "openclaw binary not found",
    "openclaw binary not executable",
    "connection refused",
    "network is unreachable",
    "getaddrinfo failed",
    "name or service not known",
    "temporary failure in name resolution",
)
# Detail substrings that identify POISONED messages (application-layer rejection
# that no retry can fix). rc>=4xx alone is not enough: the gateway returns rc=1
# for ordinary send failures, so only explicit application-layer rejection text
# parks. A plain gateway error with no such text is UNDETERMINED (retry).
_POISONED_EVIDENCE = (
    "chat not found",
    "chat_id not found",
    "user not found",
    "bad request",
    "bad target",
    "invalid target",
    "unauthorized",
    "forbidden",
    "cannot parse entities",
    "message is too long",
    "rejected message",
    "invalid message",
)

PARK_DIRNAME = "alert-park"            # operator-facing park surface under the state dir
PARK_LOCK_FILENAME = "alerts-park.lock"  # advisory lock guarding the park file
PARK_FILENAME = "parked.jsonl"         # lossless park ledger: one JSON row per message

# ---- severities -------------------------------------------------------------
SEV_STATUS = "status"      # service failures; window + storm cap apply
SEV_DECISION = "decision"  # QC three-strike, cost_hold; ALWAYS send, per-episode dedup
SEV_DIGEST = "digest"      # aged-out, daily-cap deferral, soft-ceiling; batched to daily flush
VALID_SEVERITIES = (SEV_STATUS, SEV_DECISION, SEV_DIGEST)

# Only these env names may ever resolve a target, and every one of them is an
# OPERATOR / FOUNDER channel. A client chat id is never consulted here.
FOUNDER_TARGET_ENV = (
    "PODCAST_FOUNDER_ALERT_CHAT",
    "OPERATOR_TELEGRAM_CHAT_ID",
    "FOUNDER_TELEGRAM_CHAT_ID",
)

# The SENDING channel account is pinned to the operator bot so that on a client
# box the founder alert never rides (or leaks through) the client's own default
# channel account. This mirrors the canonical operator-routed pattern
# (force-update.sh notify_operator: message send --channel telegram --account
# operator ...). Overridable for boxes that name the operator account
# differently, but it defaults to the fleet-standard "operator".
DEFAULT_FOUNDER_ALERT_ACCOUNT = "operator"
FOUNDER_ACCOUNT_ENV = "PODCAST_FOUNDER_ALERT_ACCOUNT"


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    if not s:
        return _now()
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return _now()


def _local_date_str() -> str:
    # Local calendar day governs the per-client daily storm cap (the client's own
    # day, as the box is configured). Naive local date is intentional.
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------
def _load_config(path: str | None) -> dict:
    """Read alerts.dedup_window_hours / max_founder_alerts_per_client_per_day from
    an optional config file. Supports JSON always; YAML only if PyYAML is present.
    Missing file or missing keys fall back to the design defaults. This script
    NEVER writes the shared config; it only reads it if a sibling slice shipped
    one."""
    cfg = {
        "dedup_window_hours": DEFAULT_DEDUP_WINDOW_HOURS,
        "max_founder_alerts_per_client_per_day": DEFAULT_MAX_FOUNDER_ALERTS_PER_CLIENT_PER_DAY,
    }
    if not path:
        return cfg
    p = Path(path)
    if not p.is_file():
        return cfg
    data = None
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text)
        except Exception:
            sys.stderr.write(
                "WARN: config is YAML but PyYAML is unavailable or unparseable; using defaults\n"
            )
            return cfg
    else:
        try:
            data = json.loads(text)
        except Exception:
            sys.stderr.write("WARN: config JSON unparseable; using defaults\n")
            return cfg
    if not isinstance(data, dict):
        return cfg
    alerts = {}
    pe = data.get("podcast_engine")
    if isinstance(pe, dict) and isinstance(pe.get("alerts"), dict):
        alerts = pe["alerts"]
    elif isinstance(data.get("alerts"), dict):
        alerts = data["alerts"]
    for k in ("dedup_window_hours", "max_founder_alerts_per_client_per_day"):
        v = alerts.get(k)
        if isinstance(v, (int, float)) and v > 0:
            cfg[k] = v
    for k in ("retry_backoff_base_seconds", "retry_backoff_max_seconds"):
        v = alerts.get(k)
        if isinstance(v, (int, float)) and v > 0:
            cfg[k] = int(v)
    return cfg


# ---------------------------------------------------------------------------
# state persistence (atomic, locked)
# ---------------------------------------------------------------------------
def _default_state_dir() -> Path:
    env = os.environ.get("PODCAST_ENGINE_STATE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".openclaw" / "state" / "podcast-engine"


def _empty_state() -> dict:
    # keys:         {alert_key: {...}}  active service / decision alerts
    # daily:        {client: {date, sent_count}}  storm-cap counters
    # digest_queue: {client: [ {ts, kind, text}, ... ]}  pending daily-digest lines
    return {"version": 1, "keys": {}, "daily": {}, "digest_queue": {}}


def _lock_path(state_dir: Path) -> Path:
    return state_dir / "alerts.lock"


def _state_path(state_dir: Path) -> Path:
    return state_dir / "alerts.json"


class _StateLock:
    """Advisory exclusive lock for the whole read, mutate, send, write cycle."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self._fh = None

    def __enter__(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if _HAVE_FCNTL:
            self._fh = open(_lock_path(self.state_dir), "w")
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                if _HAVE_FCNTL:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None
        return False


def _load_state(state_dir: Path) -> dict:
    p = _state_path(state_dir)
    if not p.is_file():
        return _empty_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        # Corrupt state must never wedge the pipeline; start clean but keep the
        # old file aside for the operator to inspect.
        try:
            p.rename(p.with_suffix(".json.corrupt"))
        except Exception:
            pass
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    for fld in ("keys", "daily", "digest_queue"):
        if not isinstance(data.get(fld), dict):
            data[fld] = {}
    data.setdefault("version", 1)
    return data


def _save_state(state_dir: Path, state: dict) -> None:
    p = _state_path(state_dir)
    fd, tmp = tempfile.mkstemp(prefix=".alerts.", suffix=".tmp", dir=str(state_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# failure classification + retry / park semantics (NOTIFY-RETRY)
# ---------------------------------------------------------------------------
def _empty_retry() -> dict:
    return {"attempt": 0, "next_attempt_at": None, "last_failure": None}


def _get_retry(rec: dict) -> dict:
    r = rec.get("retry")
    if not isinstance(r, dict):
        r = {}
    if "attempt" not in r:
        r["attempt"] = 0
    if "next_attempt_at" not in r:
        r["next_attempt_at"] = None
    if "last_failure" not in r:
        r["last_failure"] = None
    return r


def _backoff_delay(attempt: int, cfg: dict | None = None) -> int:
    """Exponential backoff delay for a 1-based attempt number, capped on the
    DELAY only (attempts are never capped - an alert is never given up on).
    Override order: config alerts.retry_backoff_base_seconds >
    NOTIFY_RETRY_BASE_SECONDS (test hook) > BACKOFF_BASE_SECONDS (60)."""
    cfg = cfg or {}
    base = float(
        cfg.get("retry_backoff_base_seconds")
        or os.environ.get("NOTIFY_RETRY_BASE_SECONDS")
        or BACKOFF_BASE_SECONDS
    )
    try:
        d = int(base * (2 ** (max(attempt, 1) - 1)))
    except (OverflowError, ValueError):
        d = BACKOFF_MAX_SECONDS
    cap = int(cfg.get("retry_backoff_max_seconds") or BACKOFF_MAX_SECONDS)
    return min(d, cap)


def classify_failure(detail: str) -> str:
    """Classify a failed gateway send from the dispatch-site evidence ONLY:
    the detail string _gateway_send returned. Returns 'transport', 'poisoned',
    or 'undetermined'. The detail may be None/empty (rc-only) - that is
    undetermined. Matching is case-insensitive; the evidence strings are long
    enough that accidental prefix collisions are not a practical concern."""
    if not detail:
        return "undetermined"
    hay = str(detail).lower()
    for token in _POISONED_EVIDENCE:
        if token.lower() in hay:
            return "poisoned"
    for token in _TRANSPORT_EVIDENCE:
        if token.lower() in hay:
            return "transport"
    return "undetermined"


def _park_path(state_dir: Path) -> Path:
    return state_dir / PARK_DIRNAME / PARK_FILENAME


def _park_lock_path(state_dir: Path) -> Path:
    return state_dir / PARK_DIRNAME / PARK_LOCK_FILENAME


def _park_message(state_dir: Path, key: str, rec: dict, text: str,
                  detail: str, ts: str) -> dict:
    """Park a poisoned message: keep its FULL content, surface it in an
    operator-facing park file (state_dir/alert-park/parked.jsonl), and stamp the
    key so it is NEVER re-dispatched. Park rows are append-only and lossless;
    nothing here is ever deleted by the engine. Returns the parked row."""
    row = {
        "parked_at": ts,
        "key": key,
        "client": rec.get("client"),
        "service": rec.get("service"),
        "failure_class": rec.get("failure_class"),
        "severity": rec.get("severity"),
        "detail": detail,
        "message": text,
    }
    d = state_dir / PARK_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    lock_fh = None
    if _HAVE_FCNTL:
        try:
            lock_fh = open(_park_lock_path(state_dir), "w")
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            lock_fh = None
    try:
        with open(_park_path(state_dir), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        if lock_fh is not None:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                lock_fh.close()
    return row


# ---------------------------------------------------------------------------
# daily storm-cap counter
# ---------------------------------------------------------------------------
def _daily(state: dict, client: str) -> dict:
    today = _local_date_str()
    d = state["daily"].get(client)
    if not isinstance(d, dict) or d.get("date") != today:
        d = {"date": today, "sent_count": 0}
        state["daily"][client] = d
    return d


# ---------------------------------------------------------------------------
# gateway send (the ONLY egress; founder/operator target only)
# ---------------------------------------------------------------------------
def _resolve_founder_target(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for name in FOUNDER_TARGET_ENV:
        v = os.environ.get(name)
        if v:
            return v
    return None


def _mask_target(target: str | None) -> str:
    if not target:
        return "UNSET"
    s = str(target)
    if len(s) <= 4:
        return "***"
    return "***" + s[-4:]


def _founder_account() -> str:
    """The operator/founder channel account id the gateway sends AS. Env override,
    else the fleet-standard default. Pinned so a client box never routes founder
    alerts through the client's own default channel account."""
    v = os.environ.get(FOUNDER_ACCOUNT_ENV)
    return v if v else DEFAULT_FOUNDER_ALERT_ACCOUNT


def _build_send_argv(openclaw: str, target: str, text: str, account: str) -> list:
    """Build the exact `openclaw message send` argv for one founder alert.

    Uses -m/--message, the real (and required) body flag on the installed
    gateway; there is NO --file or --text option (the gateway rejects them with
    rc=1 and sends nothing). The alert body is operator text, never a secret, so
    it rides the argv directly rather than a nonexistent flag. --account pins the
    operator bot so founder delivery on a client box never depends on the
    client's own channel account. Kept pure so the contract test can assert the
    argv is a valid invocation (and drive `--dry-run` against the real CLI)
    without ever sending anything."""
    return [
        openclaw, "message", "send",
        "--channel", "telegram",
        "--account", str(account),
        "--target", str(target),
        "--message", text,
    ]


def _gateway_send(target: str, text: str) -> tuple[bool, str]:
    """Send THROUGH the OpenClaw gateway CLI (the one and only egress). Never
    contacts the Telegram bot HTTP API directly. Returns (ok, detail)."""
    openclaw = os.environ.get("OPENCLAW_BIN") or _which("openclaw")
    if not openclaw:
        return False, "openclaw binary not found on PATH (set OPENCLAW_BIN)"
    cmd = _build_send_argv(openclaw, target, text, _founder_account())
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=45, check=False
        )
    except FileNotFoundError:
        return False, "openclaw binary not executable"
    except subprocess.TimeoutExpired:
        return False, "gateway send timed out"
    if proc.returncode == 0:
        return True, "sent via gateway"
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, "gateway rc=%d %s" % (
        proc.returncode, detail[-1] if detail else ""
    )


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


# ---------------------------------------------------------------------------
# message builders (operator-verbose, never client-facing)
# ---------------------------------------------------------------------------
def _affected_count(rec: dict, queued_count: int | None) -> int:
    if queued_count is not None:
        return queued_count
    n = len(rec.get("affected_episodes", []))
    return n if n > 0 else 1


def _msg_first(client, service, message, n) -> str:
    return (
        "[PODCAST ALERT] client=%s service=%s\n%s\n%d episode(s) affected."
        % (client, service, message, n)
    )


def _msg_still_down(client, service, message, n, oldest_days) -> str:
    return (
        "[PODCAST ALERT: STILL DOWN] client=%s service=%s\n%s\n"
        "still down, now %d episode(s) queued, oldest %d day(s)."
        % (client, service, message, n, oldest_days)
    )


def _msg_recovery(client, service, message, n) -> str:
    return (
        "[PODCAST RECOVERY] client=%s service=%s\n%s\n"
        "%d queued episode(s) resuming." % (client, service, message, n)
    )


def _msg_decision(client, service, episode, message) -> str:
    return (
        "[PODCAST DECISION] client=%s service=%s episode=%s\n%s"
        % (client, service, episode or "n/a", message)
    )


def _msg_digest(client, lines) -> str:
    body = "\n".join("- " + ln for ln in lines)
    return (
        "[PODCAST DIGEST] client=%s (%d deferred/batched item(s) today):\n%s"
        % (client, len(lines), body)
    )


# ---------------------------------------------------------------------------
# decision helper
# ---------------------------------------------------------------------------
def _decision(action, reason, key, severity, sent, send_ok, target,
              affected, daily_sent, capped, dry_run):
    return {
        "action": action,
        "reason": reason,
        "key": key,
        "severity": severity,
        "sent": sent,
        "send_ok": send_ok,
        "target": _mask_target(target),
        "affected_count": affected,
        "daily_sent_count": daily_sent,
        "capped": capped,
        "dry_run": dry_run,
    }


def _perform_send(target, text, dry_run):
    """Returns (sent, send_ok, detail, exit_hint). Never raises."""
    if dry_run:
        return False, None, "dry-run (no gateway call)", EXIT_OK
    if not target:
        return False, False, "no founder/operator target configured", EXIT_NO_FOUNDER
    ok, detail = _gateway_send(target, text)
    return True, ok, detail, (EXIT_OK if ok else EXIT_SEND_FAILED)


def _send_with_retry_policy(state, rec, state_dir, key, target, text,
                            dry_run, cfg=None):
    """Dispatch one send and apply the NOTIFY-RETRY policy to a FAILED send.
    Returns (sent, send_ok, detail, exit_hint, retry_state). Preserves the
    legacy exit-code contract: a real send that fails returns EXIT_SEND_FAILED
    (the caller may retry, and now the alert is also durably retry-pending or
    parked); a missing target returns EXIT_NO_FOUNDER; dry-run returns EXIT_OK.
    Sent-or-dry-run leaves retry state untouched (a clean send clears nothing;
    the next failure restarts the backoff clock). On failure the failure class
    decides:
      * transport   - retry state advances (attempt+1, next_attempt_at with
        capped exponential backoff). NEVER discarded, NEVER capped: the alert is
        BLOCKED and stays blocked until infrastructure returns.
      * poisoned    - the message is parked to the operator-facing park file
        with its full content; the key is stamped parked and never re-dispatched.
      * undetermined- the safe default: same unbounded retry as transport.
    """
    sent, send_ok, send_detail, hint = _perform_send(target, text, dry_run)
    if (sent and send_ok) or dry_run:
        return sent, send_ok, send_detail, hint, None
    if hint == EXIT_NO_FOUNDER:
        # No target configured: nothing was attempted, nothing to retry.
        return sent, send_ok, send_detail, hint, None
    # Failed send: classify from the dispatch-site evidence (the detail string).
    cls = classify_failure(send_detail)
    retry = _get_retry(rec)
    ts = _iso(_now())
    if cls == "poisoned":
        retry["attempt"] = int(retry.get("attempt") or 0) + 1
        retry["parked"] = True
        retry["parked_at"] = ts
        retry["next_attempt_at"] = None  # parked: never re-dispatched
        retry["last_failure"] = send_detail
        _park_message(state_dir, key, rec, text, send_detail, ts)
        # sent stays True: the legacy decision contract reports "attempted, not
        # ok" for a send that was made and failed. The action field ("parked")
        # carries the NOTIFY-RETRY verdict.
        return True, False, "poisoned; parked", EXIT_SEND_FAILED, retry
    # transport + undetermined share the same policy: keep retrying with
    # capped exponential backoff, never a terminal cap that loses the alert.
    attempt = int(retry.get("attempt") or 0) + 1
    retry["attempt"] = attempt
    delay = _backoff_delay(attempt, cfg)
    next_ts = _now().timestamp() + delay
    from datetime import datetime as _dt
    retry["next_attempt_at"] = _iso(_dt.fromtimestamp(next_ts, tz=timezone.utc))
    retry["last_failure"] = send_detail
    retry.pop("parked", None)
    retry.pop("parked_at", None)
    return True, False, "%s; retry pending" % cls, EXIT_SEND_FAILED, retry


# ---------------------------------------------------------------------------
# command: raise
# ---------------------------------------------------------------------------
def cmd_raise(args) -> int:
    severity = args.severity
    if severity not in VALID_SEVERITIES:
        _emit_error("invalid --severity %r" % severity)
        return EXIT_USAGE
    if severity == SEV_DECISION and not args.episode:
        # Decision class dedups PER EPISODE; without an episode it cannot key
        # correctly. Fail-closed to usage rather than send an unkeyable decision.
        _emit_error("--severity decision requires --episode (per-episode dedup)")
        return EXIT_USAGE

    cfg = _load_config(args.config)
    window_hours = cfg["dedup_window_hours"]
    max_per_day = cfg["max_founder_alerts_per_client_per_day"]
    state_dir = Path(args.state_dir) if args.state_dir else _default_state_dir()
    target = _resolve_founder_target(args.founder_chat)
    now = _now()

    _root_warn()

    try:
        with _StateLock(state_dir):
            state = _load_state(state_dir)
            daily = _daily(state, args.client)

            if severity == SEV_DIGEST:
                return _raise_digest(state, state_dir, args, daily)
            if severity == SEV_DECISION:
                return _raise_decision(state, state_dir, args, daily, target)
            return _raise_status(
                state, state_dir, args, daily, target, now, window_hours,
                max_per_day, cfg
            )
    except OSError as exc:
        _emit_error("state IO error: %s" % exc)
        return EXIT_USAGE


def _raise_status(state, state_dir, args, daily, target, now, window_hours,
                  max_per_day, cfg=None):
    key = "%s|%s|%s" % (args.client, args.service, args.failure_class)
    rec = state["keys"].get(key)
    window_secs = window_hours * 3600.0
    capped = daily["sent_count"] >= max_per_day

    if rec is None:
        rec = {
            "severity": SEV_STATUS,
            "first_seen": _iso(now),
            "last_sent": None,
            "count": 0,
            "affected_episodes": [],
            "client": args.client,
            "service": args.service,
            "failure_class": args.failure_class,
        }
        state["keys"][key] = rec
        _track_episode(rec, args.episode)
        rec["count"] += 1
        n = _affected_count(rec, args.queued_count)
        text = _msg_first(args.client, args.service, args.message, n)
        return _finalize_status_send(
            state, state_dir, args, daily, target, rec, key, n, text,
            capped, "first_occurrence", cfg
        )

    # existing key
    _track_episode(rec, args.episode)
    rec["count"] += 1
    n = _affected_count(rec, args.queued_count)
    last_sent = _parse_iso(rec["last_sent"]) if rec.get("last_sent") else None
    within_window = last_sent is not None and (now - last_sent).total_seconds() < window_secs
    retry = _get_retry(rec)

    if rec.get("retry", {}).get("parked"):
        # POISONED and parked: the message content is preserved in the
        # operator-facing park file; this key is NEVER re-dispatched. Still
        # acknowledge the fire (a parked alert is a parked alert) so nothing
        # silently spins, but the state transition is terminal for dispatch.
        # This check is deliberately FIRST: it must hold regardless of the
        # dedup window, so no cron re-fire can ever route a parked key back
        # into the retry loop.
        _save_state(state_dir, state)
        _emit(_decision(
            "parked", "poisoned payload; parked to alert-park (never re-dispatched)",
            key, SEV_STATUS, False, None, target, n, daily["sent_count"],
            capped, args.dry_run
        ))
        return EXIT_OK

    next_attempt = retry.get("next_attempt_at")
    retry_pending = bool(next_attempt) and _now() < _parse_iso(next_attempt)
    if within_window or retry_pending:
        # SUPPRESS: counter and affected list already updated in place. A retry
        # pending key is suppressed until its backoff deadline - the alert is
        # not discarded, it is being retried on schedule, and a blocked alert
        # deliberately does NOT hammer the gateway while the backoff clock runs.
        _save_state(state_dir, state)
        _emit(_decision(
            "suppressed", "within %gh dedup window" % window_hours, key, SEV_STATUS,
            False, None, target, n, daily["sent_count"], capped, args.dry_run
        ))
        return EXIT_OK

    # window expired while still failing -> one UPDATED "still down" digest
    oldest_days = max((now - _parse_iso(rec["first_seen"])).days, 0)
    if args.oldest_age_days is not None:
        oldest_days = args.oldest_age_days
    text = _msg_still_down(args.client, args.service, args.message, n, oldest_days)
    return _finalize_status_send(
        state, state_dir, args, daily, target, rec, key, n, text,
        capped, "window_expired_still_failing", cfg
    )


def _finalize_status_send(state, state_dir, args, daily, target, rec, key, n, text,
                          capped, reason, cfg=None):
    """Shared tail for status sends: honor the storm cap, send or defer, persist."""
    if capped and not args.dry_run:
        # Storm cap reached: collapse into the per-client end-of-day digest
        # instead of sending. The key state is still recorded.
        line = "%s/%s: %s (%d episode(s))" % (
            args.service, args.failure_class, args.message, n
        )
        _queue_digest(state, args.client, "deferred_status", line)
        _save_state(state_dir, state)
        _emit(_decision(
            "deferred", "storm cap reached; deferred to daily digest", key, SEV_STATUS,
            False, None, target, n, daily["sent_count"], True, args.dry_run
        ))
        return EXIT_OK

    sent, send_ok, detail, exit_hint, retry = _send_with_retry_policy(
        state, rec, state_dir, key, target, text, args.dry_run, cfg
    )
    if sent and send_ok:
        rec["last_sent"] = _iso(_now())
        daily["sent_count"] += 1
    if retry is not None:
        rec["retry"] = retry
    _save_state(state_dir, state)
    action = "sent" if sent else ("would_send" if args.dry_run else "send_skipped")
    if retry is not None and retry.get("parked"):
        action = "parked"
    elif retry is not None:
        action = "retry_pending"
    _emit(_decision(
        action, "%s; %s" % (reason, detail), key, SEV_STATUS,
        sent, send_ok, target, n, daily["sent_count"], capped, args.dry_run
    ))
    return exit_hint


def _raise_decision(state, state_dir, args, daily, target):
    # Decision class: ALWAYS send (bypasses the storm cap), but dedup per episode
    # so one message per episode per event, never repeats.
    key = "%s|%s|%s|%s" % (args.client, args.service, args.failure_class, args.episode)
    rec = state["keys"].get(key)
    if rec and rec.get("sent_once"):
        _save_state(state_dir, state)
        _emit(_decision(
            "suppressed", "decision already sent for this episode+event", key,
            SEV_DECISION, False, None, target, 1, daily["sent_count"], False, args.dry_run
        ))
        return EXIT_OK
    if rec is None:
        rec = {
            "severity": SEV_DECISION,
            "first_seen": _iso(_now()),
            "sent_once": False,
            "episode": args.episode,
        }
        state["keys"][key] = rec
    text = _msg_decision(args.client, args.service, args.episode, args.message)
    sent, send_ok, detail, exit_hint = _perform_send(target, text, args.dry_run)
    if sent and send_ok:
        rec["sent_once"] = True
        rec["last_sent"] = _iso(_now())
        # Decision-class always-sends and is exempt from the storm cap, so it must
        # NOT consume the per-client status budget; otherwise a burst of decisions
        # would push legitimate status first-occurrences into the digest early.
    _save_state(state_dir, state)
    _emit(_decision(
        "sent" if sent else ("would_send" if args.dry_run else "send_skipped"),
        "decision-class always-send; %s" % detail, key, SEV_DECISION,
        sent, send_ok, target, 1, daily["sent_count"], False, args.dry_run
    ))
    return exit_hint


def _raise_digest(state, state_dir, args, daily):
    # Digest class: never immediate. Accumulate for the daily flush.
    line = "%s/%s: %s" % (args.service, args.failure_class, args.message)
    if args.episode:
        line += " (episode %s)" % args.episode
    _queue_digest(state, args.client, "digest", line)
    _save_state(state_dir, state)
    _emit(_decision(
        "queued_digest", "digest-class batched to daily flush", None, SEV_DIGEST,
        False, None, None, 1, daily["sent_count"], False, args.dry_run
    ))
    return EXIT_OK


# ---------------------------------------------------------------------------
# command: recover
# ---------------------------------------------------------------------------
def cmd_recover(args) -> int:
    state_dir = Path(args.state_dir) if args.state_dir else _default_state_dir()
    target = _resolve_founder_target(args.founder_chat)
    _root_warn()
    try:
        with _StateLock(state_dir):
            state = _load_state(state_dir)
            daily = _daily(state, args.client)
            # Match the status key(s) for this client+service. If a failure_class
            # is given, clear just that key; otherwise clear every status key for
            # the client+service pair.
            prefix = "%s|%s|" % (args.client, args.service)
            matched = []
            for key, rec in list(state["keys"].items()):
                if rec.get("severity") != SEV_STATUS:
                    continue
                if args.failure_class:
                    if key == "%s%s" % (prefix, args.failure_class):
                        matched.append(key)
                elif key.startswith(prefix):
                    matched.append(key)
            if not matched:
                _save_state(state_dir, state)
                _emit(_decision(
                    "noop", "no active status alert to recover", None, SEV_STATUS,
                    False, None, target, 0, daily["sent_count"], False, args.dry_run
                ))
                return EXIT_OK
            n = args.resumed_count
            if n is None:
                n = sum(len(state["keys"][k].get("affected_episodes", [])) for k in matched)
            msg = args.message or ("%s restored" % args.service)
            text = _msg_recovery(args.client, args.service, msg, n)
            sent, send_ok, detail, exit_hint = _perform_send(target, text, args.dry_run)
            if (sent and send_ok) or args.dry_run:
                # Clear the recovered keys either way in dry-run so a canary can
                # observe the transition; real runs clear only on a good send.
                if not args.dry_run:
                    for k in matched:
                        state["keys"].pop(k, None)
                    # Recovery is not a status-failure storm; it does not consume
                    # the per-client status budget (only status sends do).
            _save_state(state_dir, state)
            _emit(_decision(
                "recovered" if (sent and send_ok) else (
                    "would_recover" if args.dry_run else "recover_send_failed"),
                detail, matched[0] if len(matched) == 1 else "|".join(matched),
                SEV_STATUS, sent, send_ok, target, n, daily["sent_count"],
                False, args.dry_run
            ))
            return exit_hint
    except OSError as exc:
        _emit_error("state IO error: %s" % exc)
        return EXIT_USAGE


# ---------------------------------------------------------------------------
# command: flush-digest
# ---------------------------------------------------------------------------
def cmd_flush_digest(args) -> int:
    state_dir = Path(args.state_dir) if args.state_dir else _default_state_dir()
    target = _resolve_founder_target(args.founder_chat)
    _root_warn()
    try:
        with _StateLock(state_dir):
            state = _load_state(state_dir)
            daily = _daily(state, args.client)
            queue = state["digest_queue"].get(args.client) or []
            if not queue:
                _save_state(state_dir, state)
                _emit(_decision(
                    "noop", "no pending digest items", None, SEV_DIGEST,
                    False, None, target, 0, daily["sent_count"], False, args.dry_run
                ))
                return EXIT_OK
            lines = [item.get("text", "") for item in queue]
            text = _msg_digest(args.client, lines)
            sent, send_ok, detail, exit_hint = _perform_send(target, text, args.dry_run)
            if sent and send_ok and not args.dry_run:
                state["digest_queue"][args.client] = []
                # The digest IS the storm-cap collapse target; sending it does not
                # itself consume the per-client status budget.
            _save_state(state_dir, state)
            _emit(_decision(
                "flushed" if (sent and send_ok) else (
                    "would_flush" if args.dry_run else "flush_send_failed"),
                "%d item(s); %s" % (len(lines), detail), None, SEV_DIGEST,
                sent, send_ok, target, len(lines), daily["sent_count"],
                False, args.dry_run
            ))
            return exit_hint
    except OSError as exc:
        _emit_error("state IO error: %s" % exc)
        return EXIT_USAGE


# ---------------------------------------------------------------------------
# command: status (operator inspection; no send)
# ---------------------------------------------------------------------------
def cmd_status(args) -> int:
    state_dir = Path(args.state_dir) if args.state_dir else _default_state_dir()
    try:
        with _StateLock(state_dir):
            state = _load_state(state_dir)
    except OSError as exc:
        _emit_error("state IO error: %s" % exc)
        return EXIT_USAGE
    view = {"client": args.client, "keys": {}, "daily": {}, "digest_pending": 0}
    for key, rec in state["keys"].items():
        if key.startswith(args.client + "|"):
            r = dict(rec)
            r.pop("affected_episodes", None)  # keep the view compact and PII-light
            r["affected_count"] = len(rec.get("affected_episodes", []))
            view["keys"][key] = r
    view["daily"] = state["daily"].get(args.client, {})
    view["digest_pending"] = len(state["digest_queue"].get(args.client, []))
    _emit(view)
    return EXIT_OK


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _track_episode(rec, episode):
    if not episode:
        return
    eps = rec.setdefault("affected_episodes", [])
    if episode not in eps:
        eps.append(episode)


def _queue_digest(state, client, kind, text):
    q = state["digest_queue"].setdefault(client, [])
    q.append({"ts": _iso(_now()), "kind": kind, "text": text})


def _root_warn():
    # Config/state written as root leaves root-owned files the node user then
    # cannot rewrite, which is how the gateway gets frozen. Warn loudly; do not
    # hard-block (container uid maps vary), but the doctrine is: run as node.
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            sys.stderr.write(
                "WARN: running as root. Alert state should be written by the node "
                "user (root-owned files under ~/.openclaw freeze the gateway).\n"
            )
    except Exception:
        pass


def _emit(obj) -> None:
    # Always machine-readable JSON on stdout. No triple backticks, ever.
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _emit_error(msg) -> None:
    sys.stderr.write("ERROR: %s\n" % msg)
    sys.stdout.write(json.dumps({"action": "error", "reason": msg}) + "\n")


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alert-dedup.py",
        description=(
            "Founder alert dedup for the Podcast Production Engine (furnace "
            "Guardrail 7). The sole path to the founder channel; routes through "
            "the OpenClaw gateway only; never client-facing."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    def _common(sp):
        sp.add_argument("--state-dir", help="override alert state dir "
                        "(default $PODCAST_ENGINE_STATE_DIR or "
                        "~/.openclaw/state/podcast-engine)")
        sp.add_argument("--config", help="optional JSON/YAML config with "
                        "podcast_engine.alerts overrides")
        sp.add_argument("--founder-chat", help="explicit founder/operator target "
                        "(else $PODCAST_FOUNDER_ALERT_CHAT / "
                        "$OPERATOR_TELEGRAM_CHAT_ID / $FOUNDER_TELEGRAM_CHAT_ID)")
        sp.add_argument("--dry-run", action="store_true",
                        help="run all dedup logic and print the decision but never "
                        "invoke the gateway")

    sp = sub.add_parser("raise", help="route a failure alert through dedup")
    _common(sp)
    sp.add_argument("--client", required=True)
    sp.add_argument("--service", required=True,
                    help="e.g. fish_audio, kie, ollama_cloud, openrouter, podbean")
    sp.add_argument("--failure-class", required=True, dest="failure_class",
                    help="e.g. insufficient_credits, http_5xx, timeout, auth_failed")
    sp.add_argument("--message", required=True, help="operator-facing description")
    sp.add_argument("--episode", help="affected episode id")
    sp.add_argument("--severity", default=SEV_STATUS, choices=VALID_SEVERITIES,
                    help="status (default), decision (always-send, per-episode), "
                    "or digest (batched to daily flush)")
    sp.add_argument("--queued-count", type=int, dest="queued_count",
                    help="override affected episode count in the message")
    sp.add_argument("--oldest-age-days", type=int, dest="oldest_age_days",
                    help="oldest queued age for the still-down message")
    sp.set_defaults(func=cmd_raise)

    sp = sub.add_parser("recover", help="service restored; send one recovery then clear")
    _common(sp)
    sp.add_argument("--client", required=True)
    sp.add_argument("--service", required=True)
    sp.add_argument("--failure-class", dest="failure_class",
                    help="clear just this failure class; omit to clear all for the service")
    sp.add_argument("--message", help="operator-facing recovery note")
    sp.add_argument("--resumed-count", type=int, dest="resumed_count")
    sp.set_defaults(func=cmd_recover)

    sp = sub.add_parser("flush-digest",
                        help="send the per-client end-of-day digest and reset it")
    _common(sp)
    sp.add_argument("--client", required=True)
    sp.set_defaults(func=cmd_flush_digest)

    sp = sub.add_parser("status", help="print current alert state for a client (no send)")
    sp.add_argument("--state-dir")
    sp.add_argument("--client", required=True)
    sp.set_defaults(func=cmd_status)

    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
