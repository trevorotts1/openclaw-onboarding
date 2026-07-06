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
#
# STDLIB ONLY. No network except the gateway CLI subprocess. No model turn, no
# MCP, no third-party imports. Runs identically on operator and client boxes.
#
# EXIT CODE CONTRACT:
#   0  OK              - alert processed (sent, suppressed, deferred, recovered,
#                        flushed, or noop). The decision JSON is on stdout.
#   2  SEND_FAILED     - a send was warranted but the gateway invocation failed
#                        (nonzero rc or the openclaw binary is absent). State is
#                        still recorded; the caller may retry. Never crashes the
#                        pipeline.
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


def _gateway_send(target: str, text: str) -> tuple[bool, str]:
    """Send THROUGH the OpenClaw gateway CLI. Returns (ok, detail). The message
    body goes via a 0600 temp file, never on the command line, so it is not
    exposed in the process table. Never contacts the Telegram bot HTTP API
    directly; the gateway CLI is the one and only egress."""
    openclaw = os.environ.get("OPENCLAW_BIN") or _which("openclaw")
    if not openclaw:
        return False, "openclaw binary not found on PATH (set OPENCLAW_BIN)"
    fd, tmp = tempfile.mkstemp(prefix=".alertmsg.", suffix=".txt")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        cmd = [
            openclaw, "message", "send",
            "--channel", "telegram",
            "--target", str(target),
            "--file", tmp,
        ]
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
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


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
                state, state_dir, args, daily, target, now, window_hours, max_per_day
            )
    except OSError as exc:
        _emit_error("state IO error: %s" % exc)
        return EXIT_USAGE


def _raise_status(state, state_dir, args, daily, target, now, window_hours, max_per_day):
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
        }
        state["keys"][key] = rec
        _track_episode(rec, args.episode)
        rec["count"] += 1
        n = _affected_count(rec, args.queued_count)
        text = _msg_first(args.client, args.service, args.message, n)
        return _finalize_status_send(
            state, state_dir, args, daily, target, rec, key, n, text,
            capped, "first_occurrence"
        )

    # existing key
    _track_episode(rec, args.episode)
    rec["count"] += 1
    n = _affected_count(rec, args.queued_count)
    last_sent = _parse_iso(rec["last_sent"]) if rec.get("last_sent") else None
    within_window = last_sent is not None and (now - last_sent).total_seconds() < window_secs

    if within_window:
        # SUPPRESS: counter and affected list already updated in place.
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
        capped, "window_expired_still_failing"
    )


def _finalize_status_send(state, state_dir, args, daily, target, rec, key, n, text,
                          capped, reason):
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

    sent, send_ok, detail, exit_hint = _perform_send(target, text, args.dry_run)
    if sent and send_ok:
        rec["last_sent"] = _iso(_now())
        daily["sent_count"] += 1
    _save_state(state_dir, state)
    _emit(_decision(
        "sent" if sent else ("would_send" if args.dry_run else "send_skipped"),
        "%s; %s" % (reason, detail), key, SEV_STATUS,
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
        daily["sent_count"] += 1
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
                    daily["sent_count"] += 1
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
                daily["sent_count"] += 1
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
