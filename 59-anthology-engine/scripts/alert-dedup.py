#!/usr/bin/env python3
"""alert-dedup.py -- the single deduped founder-alert path (gateway Telegram only).

WHAT THIS IS (SPEC 3.4 row 21; ENGINE-MANIFEST.json script #21; SPEC 5 failure
table "Insufficient credits"; SPEC 8.1 chain-exhausted; SPEC 9 no-search-tool;
SPEC 12 strike-out): the ONE choke point through which the engine tells the
founder that something needs a human -- a provider ran out of credits and a job
is durably HELD, a stage struck out after its QC attempts, or web search is
unavailable on the box. It exists because the legacy system was killed TWICE, on
record, by an ALERT STORM: one failing condition fired the same notification over
and over until the channel (and the operator's attention) was buried. This module
is the fix. It collapses repeated alerts of the SAME condition (keying + a time
window) and caps the total volume of DISTINCT alerts in a rolling window (the
storm cap), then hands the survivor to the OpenClaw gateway -- and ONLY the
gateway -- for Telegram delivery. The gateway is NEVER bypassed; this module makes
no direct Telegram API call, holds no bot token, and knows no chat id.

THE THREE MECHANISMS (SPEC "single deduped founder alert"):
  1. KEYING: every caller passes a STABLE dedup key that identifies the CONDITION
     (e.g. "anthology_hold::credit_out::<participant>", "content-strike:<key>",
     "search_detect:no_search_tool"). Repeated fires of the same key collapse.
  2. TIME WINDOW: within the per-key window (default one day -- "one per failure
     per day", SPEC 5 / smoke-test) a repeat of a key that already delivered is
     SUPPRESSED (a correct, silent no-op; exit 0). A key whose delivery FAILED is
     NOT suppressed, so a gateway blip never loses an alert.
  3. STORM CAP: at most N DISTINCT alerts are delivered per rolling storm window
     (default 8 per hour). Beyond the cap, further alerts are suppressed and a
     single "storm cap reached" notice is delivered (itself deduped to one per
     window) so the founder knows to look at the operator surface. Only SUCCESSFUL
     deliveries count toward the cap.

NEVER-LOSE-AN-ALERT: every fire -- delivered, window-suppressed, storm-suppressed,
or gateway-failed -- is appended to a durable local spool (JSONL) in the state
dir. The gateway carries the deduped signal; the spool is the operator's complete,
lossless record. Nothing an operator needs is ever silently dropped.

EXIT CODES (SPEC 3.4 row 21 documents "0 sent or correctly suppressed; 3 gateway
unreachable"; 1/2 are the house convention, applied so a caller never confuses a
deliberate suppression with a delivery failure):
  0  sent, OR correctly suppressed (dedup window / storm cap), OR a dry-run render,
     OR an idempotent no-op
  1  unexpected error (fail-closed; never a silent pass)
  2  validation / guard refusal -- a send with no dedup key or no message body
  3  the gateway path did not deliver: no configured gateway command, a malformed
     command template, a command error, a timeout, or a nonzero return -- i.e.
     "gateway unreachable" (SPEC row 21). The alert is spooled; the caller may
     retry and the key is NOT recorded as delivered, so the retry goes through.

DOCTRINE (binding): move in silence -- operator-verbose on stderr, clean JSON on
stdout; the founder alert is the sanctioned operator signal, never a client
message (client surfaces stay silent). Delivery rides the OpenClaw gateway ONLY,
never a direct Telegram call and never any other bypass. Convert and Flow is the
platform name in every surface. No forbidden model identifiers of any kind appear
in this file. Never print a secret value: this module handles none, resolves the
gateway command by configured template only, and never logs a delivery payload's
contents beyond the reference-only summary the caller already sanitized. State
writes run as the node user, never root. STDLIB ONLY (subprocess + json + fcntl):
zero third-party deps; calls NO model and NO delivery provider directly.

BOUNDARIES / OWNERSHIP: this unit (W2.4) authors ONLY this file. It writes NO
ledger and NO mirror -- its only durable state is two underscore-prefixed sidecars
in the engine state dir (the dedup window/cap state and the append-only spool),
which are operational data, never ledger domain data. Callers (hold_queue.py,
model_router.py, anthology-smoke-test.py, qc-strike-gate.py, search_detect.py)
invoke it fail-soft: a nonzero return never blocks a hold, a stage, or a run.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl  # POSIX advisory lock (darwin / linux -- the target platforms)
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None
    _HAVE_FCNTL = False

# ---------------------------------------------------------------------------
# Layout / sidecar contract.
# ---------------------------------------------------------------------------
SCRIPTS = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS.parent
STATE_FILENAME = "_alert_dedup.json"      # durable dedup window/cap state (NOT ledger data)
SPOOL_FILENAME = "_alert_spool.jsonl"     # append-only, lossless operator record
LOCK_FILENAME = "_alert_dedup.lock"       # advisory lock guarding read-modify-write
STATE_SCHEMA = 1

# ---------------------------------------------------------------------------
# Exit codes (documented above; keep stable -- callers read these).
# ---------------------------------------------------------------------------
EX_OK = 0
EX_ERR = 1
EX_VALIDATION = 2
EX_GATEWAY = 3        # SPEC 3.4 row 21: gateway unreachable / delivery did not land

# ---------------------------------------------------------------------------
# Defaults (all overridable per box via config `founder_alert` block, env, or CLI).
# ---------------------------------------------------------------------------
DEFAULT_WINDOW_SECONDS = 86400            # one alert per key per day (SPEC "one per failure/day")
DEFAULT_STORM_CAP = 8                     # max DISTINCT deliveries per storm window
DEFAULT_STORM_WINDOW_SECONDS = 3600       # rolling storm window (one hour)
DELIVERY_TIMEOUT_SECONDS = 20             # bounded gateway handoff

STORM_NOTICE_KEY = "__storm_cap__"        # reserved key for the meta storm-cap notice
STORM_NOTICE_MARK = "[STORM-CAP]"         # body prefix so the notice is identifiable

SUB_COMMANDS = ("send", "selftest", "status", "purge")


# ===========================================================================
# Small utilities.
# ===========================================================================
def _log(msg: str) -> None:
    """Operator-verbose, client-silent: human output lands on stderr so stdout is a
    clean JSON channel (doctrine: move in silence)."""
    sys.stderr.write("[alert-dedup] %s\n" % msg)


def now_ts() -> float:
    return time.time()


def now_iso() -> str:
    """ISO-8601 UTC, second precision -- matches anthology_state.now_utc formatting so
    spool timestamps round-trip with the ledger's."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _split_cmd(raw):
    """A delivery command as a shell string OR an already-split list -> a clean argv
    list (or None). Uses shlex so a quoted `openclaw notify --to "..."` survives."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        toks = [str(t) for t in raw if str(t) != ""]
        return toks or None
    s = str(raw).strip()
    if not s:
        return None
    try:
        toks = shlex.split(s)
    except ValueError:
        return None
    return toks or None


# ===========================================================================
# State-dir resolution (single source of truth, agreed with anthology_state /
# hold_queue / intake_router: --db > --state-dir > ANTHOLOGY_STATE_DIR >
# OPENCLAW_DATA_DIR > node home). This module needs only the DIRECTORY.
# ===========================================================================
def resolve_state_dir(state_dir=None, db=None) -> Path:
    if db:
        return Path(db).expanduser().parent
    if state_dir:
        return Path(state_dir).expanduser()
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


# ===========================================================================
# Locking + durable state (dedup window/cap sidecar).
# ===========================================================================
@contextmanager
def _locked(sd: Path):
    """Exclusive advisory lock over the state dir for the whole read-deliver-write.
    Serializing across a genuine concurrent storm is DESIRABLE here: it makes the
    storm cap exact. On a platform without fcntl the block still runs (best-effort;
    the target platforms are POSIX)."""
    sd.mkdir(parents=True, exist_ok=True)
    lock_path = sd / LOCK_FILENAME
    fh = open(lock_path, "a+")
    try:
        if _HAVE_FCNTL:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if _HAVE_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _empty_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "keys": {},                 # dedup_key -> {last_sent, last_seen, seen, sent, category, severity}
        "delivered_log": [],        # epoch ts of SUCCESSFUL deliveries (storm-cap window)
        "storm_notice_last": 0.0,   # epoch ts the last storm-cap notice was delivered
        "totals": {"sent": 0, "suppressed_window": 0, "suppressed_storm": 0,
                   "gateway_unreachable": 0, "dry_run": 0},
    }


def _load_state(sd: Path) -> dict:
    path = sd / STATE_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return _empty_state()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # A corrupt sidecar is operational, not ledger data: start clean rather than
        # crash the fail-soft alert path (never lose the ABILITY to alert).
        _log("dedup state unreadable; starting a fresh window (non-fatal)")
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    base = _empty_state()
    base.update({k: data.get(k, base[k]) for k in base})
    if not isinstance(base.get("keys"), dict):
        base["keys"] = {}
    if not isinstance(base.get("delivered_log"), list):
        base["delivered_log"] = []
    if not isinstance(base.get("totals"), dict):
        base["totals"] = _empty_state()["totals"]
    return base


def _save_state(sd: Path, state: dict) -> None:
    """Atomic replace: write a temp sibling then os.replace, so a killed write never
    leaves a half-file. Written as the invoking (node) user."""
    sd.mkdir(parents=True, exist_ok=True)
    path = sd / STATE_FILENAME
    fd, tmp = tempfile.mkstemp(prefix="._alert_dedup.", dir=str(sd))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _spool(sd: Path, entry: dict) -> None:
    """Append one JSONL record to the lossless operator spool. Best-effort: a spool
    write failure must never mask the delivery outcome."""
    try:
        sd.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with open(sd / SPOOL_FILENAME, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        _log("spool append failed (non-fatal): %s" % type(exc).__name__)


def _prune_delivered(state: dict, now: float, storm_window: float) -> None:
    cutoff = now - storm_window
    state["delivered_log"] = [t for t in state.get("delivered_log", [])
                              if isinstance(t, (int, float)) and t >= cutoff]


# ===========================================================================
# Config (optional; the box may wire a `founder_alert` block, but defaults +
# env make this module fully functional WITHOUT one).
# ===========================================================================
def load_config(config_path=None) -> dict:
    candidates = []
    if config_path:
        candidates.append(Path(config_path).expanduser())
    env = os.environ.get("ANTHOLOGY_ENGINE_CONFIG", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    candidates.append(SKILL_DIR / "config" / "engine-config.json")
    candidates.append(SKILL_DIR / "config" / "engine-config.template.json")
    for cand in candidates:
        try:
            if cand.is_file():
                return json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _founder_cfg(config: dict) -> dict:
    fa = (config or {}).get("founder_alert")
    return fa if isinstance(fa, dict) else {}


# ===========================================================================
# Gateway delivery (the ONLY sanctioned path: a configured gateway command that
# hands the message to the OpenClaw gateway Telegram notifier). Resolution order,
# highest first: --delivery-cmd > env ANTHOLOGY_ALERT_DELIVERY_CMD >
# env FOUNDER_ALERT_CMD > config founder_alert.delivery_cmd. No path -> the
# gateway is unreachable (exit 3), never a silent success.
# ===========================================================================
def resolve_delivery_cmd(delivery_cmd=None, config=None):
    cmd = _split_cmd(delivery_cmd)
    if cmd:
        return cmd
    cmd = _split_cmd(os.environ.get("ANTHOLOGY_ALERT_DELIVERY_CMD"))
    if cmd:
        return cmd
    cmd = _split_cmd(os.environ.get("FOUNDER_ALERT_CMD"))
    if cmd:
        return cmd
    cmd = _split_cmd(_founder_cfg(config or {}).get("delivery_cmd"))
    if cmd:
        return cmd
    return None


def _deliver(cmd, *, subject, category, severity, key, source, body,
             timeout=DELIVERY_TIMEOUT_SECONDS):
    """Hand the message to the gateway command. The BODY rides on stdin; argv tokens
    may reference {subject}/{category}/{severity}/{key}/{source}. Returns
    (ok, detail). Any non-delivery -> (False, reason) -> the caller maps to exit 3.
    NEVER a direct Telegram call: cmd is the box's gateway notifier, full stop."""
    if not cmd:
        return False, "no_delivery_path"
    slots = {"subject": subject or "", "category": category or "",
             "severity": severity or "", "key": key or "", "source": source or ""}
    try:
        argv = [str(tok).format(**slots) for tok in cmd]
    except (KeyError, IndexError, ValueError):
        return False, "bad_delivery_template"
    try:
        proc = subprocess.run(argv, input=body, text=True,
                              capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "delivery_timeout"
    except (subprocess.SubprocessError, OSError) as exc:
        return False, "delivery_error:%s" % type(exc).__name__
    if proc.returncode != 0:
        return False, "delivery_rc:%d" % proc.returncode
    return True, "delivered"


def _compose_subject(subject, category, source, severity) -> str:
    if subject:
        return subject
    tag = category or source or "alert"
    return "Anthology Engine founder alert: %s" % tag


def _compose_body(message, subject, category, source, severity, payload_file) -> str:
    """The delivered body is operator-facing and REFERENCE-ONLY. Callers guarantee no
    draft body and no secret rides in `message`; we add only routing context and a
    pointer to the durable spool -- never a payload's contents."""
    lines = [message.strip() if message else _compose_subject(subject, category, source, severity)]
    meta = []
    if category:
        meta.append("category=%s" % category)
    if source:
        meta.append("source=%s" % source)
    if severity:
        meta.append("severity=%s" % severity)
    if payload_file:
        meta.append("detail=%s" % payload_file)  # a PATH reference, never contents
    if meta:
        lines.append("(" + "; ".join(meta) + ")")
    return "\n".join(lines)


# ===========================================================================
# CORE: send one founder alert through the dedup window + storm cap to the gateway.
# Returns (result_dict, exit_code). Callable in-process (the selftest uses it).
# ===========================================================================
def do_send(*, dedup_key, message=None, subject=None, category=None, source=None,
            severity="warning", payload_file=None, state_dir=None, db=None,
            window_seconds=None, storm_cap=None, storm_window_seconds=None,
            delivery_cmd=None, force=False, dry_run=False, config=None):
    # ---- validation (house exit 2) --------------------------------------------
    key = (dedup_key or "").strip()
    if not key:
        return {"ok": False, "error": "missing_dedup_key"}, EX_VALIDATION
    body_src = message if (message and message.strip()) else None
    if body_src is None and not dry_run:
        return {"ok": False, "error": "missing_message"}, EX_VALIDATION

    if config is None:
        config = load_config()
    fa = _founder_cfg(config)
    window = int(window_seconds if window_seconds is not None
                 else fa.get("window_seconds", DEFAULT_WINDOW_SECONDS))
    cap = int(storm_cap if storm_cap is not None
              else fa.get("storm_cap", DEFAULT_STORM_CAP))
    storm_window = int(storm_window_seconds if storm_window_seconds is not None
                       else fa.get("storm_window_seconds", DEFAULT_STORM_WINDOW_SECONDS))
    window = max(0, window)
    cap = max(1, cap)
    storm_window = max(1, storm_window)

    sd = resolve_state_dir(state_dir=state_dir, db=db)
    cmd = resolve_delivery_cmd(delivery_cmd=delivery_cmd, config=config)
    subject_r = _compose_subject(subject, category, source, severity)
    body = _compose_body(body_src, subject, category, source, severity, payload_file)

    # ---- dry-run: render + validate, deliver NOTHING (exit 0) ------------------
    if dry_run:
        result = {"ok": True, "outcome": "dry_run", "dedup_key": key,
                  "subject": subject_r, "delivery_path_configured": bool(cmd),
                  "window_seconds": window, "storm_cap": cap,
                  "storm_window_seconds": storm_window}
        with _locked(sd):
            state = _load_state(sd)
            state["totals"]["dry_run"] = state["totals"].get("dry_run", 0) + 1
            _save_state(sd, state)
            _spool(sd, {"ts": now_iso(), "outcome": "dry_run", "dedup_key": key,
                        "category": category, "source": source, "severity": severity,
                        "subject": subject_r, "payload_file": payload_file,
                        "message": (body_src or "")[:2000],
                        "delivery_path_configured": bool(cmd)})
        return result, EX_OK

    # ---- the guarded read-decide-deliver-write --------------------------------
    with _locked(sd):
        now = now_ts()
        state = _load_state(sd)
        _prune_delivered(state, now, storm_window)
        entry = state["keys"].get(key) or {
            "last_sent": 0.0, "last_seen": 0.0, "seen": 0, "sent": 0,
            "category": category, "severity": severity}
        entry["seen"] = int(entry.get("seen", 0)) + 1
        entry["last_seen"] = now
        entry["category"] = category or entry.get("category")
        entry["severity"] = severity or entry.get("severity")

        def _finish(outcome, exit_code, detail=None, extra=None):
            state["keys"][key] = entry
            _save_state(sd, state)
            _spool(sd, {"ts": now_iso(), "outcome": outcome, "dedup_key": key,
                        "category": category, "source": source, "severity": severity,
                        "subject": subject_r, "payload_file": payload_file,
                        "message": (body_src or "")[:2000], "detail": detail})
            result = {"ok": exit_code == EX_OK, "outcome": outcome, "dedup_key": key,
                      "subject": subject_r, "seen": entry["seen"], "sent": entry["sent"],
                      "storm_delivered_in_window": len(state["delivered_log"]),
                      "storm_cap": cap, "window_seconds": window}
            if detail:
                result["detail"] = detail
            if extra:
                result.update(extra)
            return result, exit_code

        # (1) KEY + TIME WINDOW: a key that already DELIVERED within the window is
        #     a correct silent no-op. A key whose last attempt FAILED (last_sent==0)
        #     is not suppressed, so a prior gateway blip never buries the alert.
        if not force and entry.get("last_sent", 0) > 0 \
                and window > 0 and (now - entry["last_sent"]) < window:
            state["totals"]["suppressed_window"] = state["totals"].get("suppressed_window", 0) + 1
            _log("suppressed (dedup window) key=%s age=%ds < %ds"
                 % (key, int(now - entry["last_sent"]), window))
            return _finish("suppressed_window", EX_OK, detail="within_dedup_window")

        # (2) STORM CAP: too many DISTINCT deliveries already landed this window.
        #     Suppress, and emit ONE storm-cap notice (deduped) so the founder knows.
        if not force and len(state["delivered_log"]) >= cap:
            state["totals"]["suppressed_storm"] = state["totals"].get("suppressed_storm", 0) + 1
            notice = _maybe_storm_notice(state, now, cmd, cap, storm_window, sd)
            _log("suppressed (storm cap) key=%s delivered_in_window=%d cap=%d notice=%s"
                 % (key, len(state["delivered_log"]), cap, notice))
            return _finish("suppressed_storm", EX_OK, detail="storm_cap_reached",
                           extra={"storm_notice": notice})

        # (3) DELIVER through the gateway (the only sanctioned path).
        ok, detail = _deliver(cmd, subject=subject_r, category=category,
                              severity=severity, key=key, source=source, body=body)
        if ok:
            entry["last_sent"] = now
            entry["sent"] = int(entry.get("sent", 0)) + 1
            state["delivered_log"].append(now)
            state["totals"]["sent"] = state["totals"].get("sent", 0) + 1
            _log("sent key=%s (delivered_in_window=%d/%d)"
                 % (key, len(state["delivered_log"]), cap))
            return _finish("sent", EX_OK, detail=detail)

        # Gateway did NOT deliver: exit 3, key left un-sent so a retry goes through.
        state["totals"]["gateway_unreachable"] = state["totals"].get("gateway_unreachable", 0) + 1
        _log("GATEWAY UNREACHABLE key=%s (%s); alert spooled, caller may retry"
             % (key, detail))
        return _finish("gateway_unreachable", EX_GATEWAY, detail=detail)


def _maybe_storm_notice(state, now, cmd, cap, storm_window, sd) -> str:
    """Deliver ONE 'storm cap reached' notice, deduped to once per storm window. The
    notice does NOT count toward the cap (it is a meta-signal, not an alert). Returns
    a short status string. Best-effort: a failed notice never changes the caller's
    exit code (the underlying alert is already, correctly, suppressed)."""
    last = state.get("storm_notice_last", 0) or 0
    if (now - last) < storm_window:
        return "deduped"
    body = ("%s Founder-alert storm cap reached: %d alerts already delivered in the "
            "last %d minutes; further alerts are being SUPPRESSED and spooled. Review "
            "the operator surface (spool: %s)."
            % (STORM_NOTICE_MARK, cap, max(1, storm_window // 60), sd / SPOOL_FILENAME))
    ok, _detail = _deliver(cmd, subject="Anthology Engine: founder-alert storm cap reached",
                          category="storm-cap", severity="warning",
                          key=STORM_NOTICE_KEY, source="alert-dedup", body=body)
    _spool(sd, {"ts": now_iso(), "outcome": ("storm_notice_sent" if ok else "storm_notice_failed"),
                "dedup_key": STORM_NOTICE_KEY, "category": "storm-cap",
                "severity": "warning", "subject": "storm cap reached"})
    if ok:
        state["storm_notice_last"] = now
        return "sent"
    return "gateway_unreachable"


# ===========================================================================
# status / purge (operability).
# ===========================================================================
def do_status(state_dir=None, db=None, config=None) -> dict:
    sd = resolve_state_dir(state_dir=state_dir, db=db)
    if config is None:
        config = load_config()
    fa = _founder_cfg(config)
    with _locked(sd):
        state = _load_state(sd)
    return {
        "ok": True, "state_dir": str(sd),
        "delivery_path_configured": bool(resolve_delivery_cmd(config=config)),
        "distinct_keys": len(state.get("keys", {})),
        "delivered_in_current_log": len(state.get("delivered_log", [])),
        "totals": state.get("totals", {}),
        "window_seconds": int(fa.get("window_seconds", DEFAULT_WINDOW_SECONDS)),
        "storm_cap": int(fa.get("storm_cap", DEFAULT_STORM_CAP)),
        "storm_window_seconds": int(fa.get("storm_window_seconds", DEFAULT_STORM_WINDOW_SECONDS)),
        "spool": str(sd / SPOOL_FILENAME),
    }


def do_purge(state_dir=None, db=None, purge_all=False, storm_window_seconds=None,
             config=None) -> dict:
    """Prune expired storm-window deliveries (default) or reset ALL dedup state
    (--all; the spool is never touched -- it is the lossless record). Idempotent."""
    sd = resolve_state_dir(state_dir=state_dir, db=db)
    if config is None:
        config = load_config()
    fa = _founder_cfg(config)
    storm_window = int(storm_window_seconds if storm_window_seconds is not None
                       else fa.get("storm_window_seconds", DEFAULT_STORM_WINDOW_SECONDS))
    with _locked(sd):
        if purge_all:
            _save_state(sd, _empty_state())
            return {"ok": True, "purged": "all", "state_dir": str(sd)}
        state = _load_state(sd)
        before = len(state.get("delivered_log", []))
        _prune_delivered(state, now_ts(), max(1, storm_window))
        _save_state(sd, state)
        return {"ok": True, "purged": "expired", "state_dir": str(sd),
                "delivered_pruned": before - len(state["delivered_log"])}


# ===========================================================================
# CLI wiring.
# ===========================================================================
def _emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif result is not None:
        outcome = result.get("outcome") or ("ok" if result.get("ok") else "error")
        extra = result.get("error") or result.get("detail") or ""
        print("%s %s%s" % (outcome, result.get("dedup_key", ""),
                           ("  " + str(extra)) if extra else ""))


def _add_send_flags(sp) -> None:
    # Key aliases (--dedup-key from hold_queue / smoke-test / search_detect; --key
    # from model_router / qc-strike-gate). Message aliases (--message / --summary /
    # --body). --subject and --source/--severity are optional routing context.
    sp.add_argument("--dedup-key", "--key", dest="dedup_key",
                    help="STABLE dedup key identifying the CONDITION (required)")
    sp.add_argument("--message", "--summary", "--body", dest="message",
                    help="reference-only alert body (no draft body, no secret)")
    sp.add_argument("--subject", dest="subject", help="optional subject line")
    sp.add_argument("--category", dest="category", help="alert category tag")
    sp.add_argument("--source", dest="source", help="originating script/source tag")
    sp.add_argument("--severity", dest="severity", default="warning",
                    help="severity tag (info|warning|critical); default warning")
    sp.add_argument("--payload-file", dest="payload_file",
                    help="path to a durable operator record (a PATH reference only)")
    sp.add_argument("--window-seconds", dest="window_seconds", type=int, default=None,
                    help="per-key dedup window override (default %d)" % DEFAULT_WINDOW_SECONDS)
    sp.add_argument("--storm-cap", dest="storm_cap", type=int, default=None,
                    help="max distinct deliveries per storm window (default %d)" % DEFAULT_STORM_CAP)
    sp.add_argument("--storm-window-seconds", dest="storm_window_seconds", type=int,
                    default=None, help="rolling storm window override (default %d)"
                    % DEFAULT_STORM_WINDOW_SECONDS)
    sp.add_argument("--delivery-cmd", dest="delivery_cmd", default=None,
                    help="explicit gateway delivery command (overrides env/config)")
    sp.add_argument("--force", action="store_true",
                    help="operator override: bypass dedup window + storm cap")
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="render + validate, deliver nothing (exit 0)")
    sp.add_argument("--config", dest="config", default=None,
                    help="engine-config.json path (optional)")
    sp.add_argument("--state-dir", dest="state_dir", default=None,
                    help="engine state directory (default: ANTHOLOGY_STATE_DIR / "
                         "OPENCLAW_DATA_DIR / node home)")
    sp.add_argument("--db", dest="db", default=None,
                    help="ledger db path (its parent is the state dir)")
    sp.add_argument("--json", action="store_true", help="emit JSON on stdout")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alert-dedup.py",
        description="Single deduped founder alert -> OpenClaw gateway Telegram only.")
    sub = p.add_subparsers(dest="_name")

    sp_send = sub.add_parser("send", help="deliver one deduped founder alert")
    _add_send_flags(sp_send)

    sp_status = sub.add_parser("status", help="show dedup window / storm-cap state")
    sp_status.add_argument("--state-dir", dest="state_dir", default=None)
    sp_status.add_argument("--db", dest="db", default=None)
    sp_status.add_argument("--config", dest="config", default=None)
    sp_status.add_argument("--json", action="store_true")

    sp_purge = sub.add_parser("purge", help="prune expired storm window (or --all)")
    sp_purge.add_argument("--all", dest="purge_all", action="store_true",
                          help="reset ALL dedup state (the spool is never touched)")
    sp_purge.add_argument("--storm-window-seconds", dest="storm_window_seconds",
                          type=int, default=None)
    sp_purge.add_argument("--state-dir", dest="state_dir", default=None)
    sp_purge.add_argument("--db", dest="db", default=None)
    sp_purge.add_argument("--config", dest="config", default=None)
    sp_purge.add_argument("--json", action="store_true")

    sub.add_parser("selftest", help="in-process storm/dedup/cap battery (temp state dir)")
    return p


def _normalize_argv(argv):
    """The flag-style callers (hold_queue / anthology-smoke-test / search_detect)
    invoke with NO subcommand -- the first token is an option like --dedup-key. The
    subcommand callers (model_router / qc-strike-gate) lead with `send`. Default to
    `send` unless the first token is an explicit subcommand or a help flag."""
    argv = list(argv)
    if not argv:
        return ["send"]
    first = argv[0]
    if first in ("-h", "--help", "help"):
        return argv if first != "help" else ["-h"]
    if first in SUB_COMMANDS:
        return argv
    return ["send"] + argv


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    argv = _normalize_argv(raw)
    parser = build_parser()
    a = parser.parse_args(argv)
    name = getattr(a, "_name", None)
    as_json = bool(getattr(a, "json", False))

    try:
        if name == "selftest":
            return run_selftest()
        if name == "status":
            _emit(do_status(state_dir=a.state_dir, db=a.db, config=a.config), as_json)
            return EX_OK
        if name == "purge":
            _emit(do_purge(state_dir=a.state_dir, db=a.db,
                           purge_all=getattr(a, "purge_all", False),
                           storm_window_seconds=a.storm_window_seconds,
                           config=a.config), as_json)
            return EX_OK
        if name == "send":
            result, code = do_send(
                dedup_key=a.dedup_key, message=a.message, subject=a.subject,
                category=a.category, source=a.source, severity=a.severity,
                payload_file=a.payload_file, state_dir=a.state_dir, db=a.db,
                window_seconds=a.window_seconds, storm_cap=a.storm_cap,
                storm_window_seconds=a.storm_window_seconds,
                delivery_cmd=a.delivery_cmd, force=a.force, dry_run=a.dry_run,
                config=a.config)
            _emit(result, as_json)
            return code
        parser.print_help(sys.stderr)
        return EX_VALIDATION
    except Exception as exc:  # noqa: BLE001 - top-level fail-closed
        sys.stderr.write("[alert-dedup] ERROR: %s: %s\n" % (type(exc).__name__, exc))
        return EX_ERR


# ===========================================================================
# SELFTEST -- FORCES a storm and force-observes every failure mode against a temp
# state dir with a STUB gateway sink (never a real gateway, never Telegram):
#   * dedup window collapses N fires of ONE key to a single delivery;
#   * the storm cap delivers at most K DISTINCT alerts and suppresses the rest,
#     emitting exactly one storm-cap notice;
#   * a gateway-unreachable send returns exit 3, spools the alert, and does NOT
#     record the key as delivered, so a later good send goes through;
#   * a failing gateway command also returns exit 3;
#   * --force bypasses the window; --dry-run renders without delivering;
#   * purge --all resets the window so the key delivers again;
#   * the spool is lossless (every fire recorded).
# Returns 0 iff every assertion holds.
# ===========================================================================
def _sink_cmd(sink_path: str):
    """A STUB gateway that appends each delivered body (one line) to sink_path. This
    stands in for the box's real OpenClaw gateway notifier; the point of the test is
    the dedup/cap arithmetic, not the transport."""
    code = ("import sys\n"
            "data = sys.stdin.read().replace(chr(10), ' ')\n"
            "open(sys.argv[1], 'a', encoding='utf-8').write(data + chr(10))\n")
    return [sys.executable or "python3", "-c", code, sink_path]


def _fail_cmd():
    return [sys.executable or "python3", "-c", "import sys; sys.exit(7)"]


def run_selftest() -> int:  # noqa: C901 - a linear battery reads clearest inline
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        _log("selftest %-52s %s%s" % (name, status, ("  " + str(detail)) if detail else ""))
        if not cond:
            failures.append(name)

    def sink_lines(path):
        try:
            return [ln for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln]
        except OSError:
            return []

    def spool_entries(sd):
        try:
            return [json.loads(ln) for ln in
                    (sd / SPOOL_FILENAME).read_text(encoding="utf-8").splitlines() if ln]
        except OSError:
            return []

    tmp = tempfile.mkdtemp(prefix="alert_dedup_selftest_")
    try:
        # -- 1) DEDUP WINDOW: 5 fires of ONE key -> exactly 1 delivery ------------
        sd1 = Path(tmp) / "dedup"
        sink1 = str(sd1 / "sink.log")
        sd1.mkdir(parents=True, exist_ok=True)
        outcomes, codes = [], []
        for _ in range(5):
            r, c = do_send(dedup_key="cond:A", message="credit_out on box; job held",
                           category="credit-hold", state_dir=str(sd1),
                           window_seconds=86400, storm_cap=100,
                           delivery_cmd=_sink_cmd(sink1))
            outcomes.append(r.get("outcome"))
            codes.append(c)
        sent = outcomes.count("sent")
        supp = outcomes.count("suppressed_window")
        check("dedup: 1 sent of 5 same-key fires", sent == 1, "sent=%d" % sent)
        check("dedup: 4 window-suppressed", supp == 4, "suppressed=%d" % supp)
        check("dedup: all fires exit 0", all(c == EX_OK for c in codes), str(codes))
        check("dedup: gateway got exactly 1 line", len(sink_lines(sink1)) == 1,
              str(len(sink_lines(sink1))))
        check("dedup: spool recorded all 5 fires", len(spool_entries(sd1)) == 5,
              str(len(spool_entries(sd1))))

        # -- 1b) --force bypasses the window (same key delivers again) -----------
        r, c = do_send(dedup_key="cond:A", message="forced repeat",
                       category="credit-hold", state_dir=str(sd1),
                       window_seconds=86400, storm_cap=100, force=True,
                       delivery_cmd=_sink_cmd(sink1))
        check("force: bypasses window -> sent (exit 0)",
              r.get("outcome") == "sent" and c == EX_OK, r.get("outcome"))
        check("force: gateway now has 2 lines", len(sink_lines(sink1)) == 2,
              str(len(sink_lines(sink1))))

        # -- 1c) purge --all resets state; same key delivers again ---------------
        do_purge(state_dir=str(sd1), purge_all=True)
        r, c = do_send(dedup_key="cond:A", message="after purge",
                       category="credit-hold", state_dir=str(sd1),
                       window_seconds=86400, storm_cap=100,
                       delivery_cmd=_sink_cmd(sink1))
        check("purge --all: key delivers again -> sent",
              r.get("outcome") == "sent" and c == EX_OK, r.get("outcome"))

        # -- 2) STORM CAP: force a storm of 10 DISTINCT keys, cap=3 --------------
        sd2 = Path(tmp) / "storm"
        sink2 = str(sd2 / "sink.log")
        sd2.mkdir(parents=True, exist_ok=True)
        st_out, st_codes, notices = [], [], []
        for i in range(10):
            r, c = do_send(dedup_key="storm:key:%d" % i,
                           message="distinct condition %d" % i,
                           category="credit-hold", state_dir=str(sd2),
                           window_seconds=86400, storm_cap=3,
                           storm_window_seconds=3600,
                           delivery_cmd=_sink_cmd(sink2))
            st_out.append(r.get("outcome"))
            st_codes.append(c)
            if r.get("storm_notice"):
                notices.append(r["storm_notice"])
        st_sent = st_out.count("sent")
        st_supp = st_out.count("suppressed_storm")
        check("storm: exactly cap=3 delivered", st_sent == 3, "sent=%d" % st_sent)
        check("storm: remaining 7 storm-suppressed", st_supp == 7, "suppressed=%d" % st_supp)
        check("storm: every fire exit 0 (correctly suppressed)",
              all(c == EX_OK for c in st_codes), str(st_codes))
        # sink holds 3 alert lines + exactly 1 storm-cap notice line
        lines2 = sink_lines(sink2)
        alert_lines = [ln for ln in lines2 if STORM_NOTICE_MARK not in ln]
        notice_lines = [ln for ln in lines2 if STORM_NOTICE_MARK in ln]
        check("storm: gateway got exactly 3 alert lines", len(alert_lines) == 3,
              str(len(alert_lines)))
        check("storm: exactly ONE storm-cap notice delivered", len(notice_lines) == 1,
              str(len(notice_lines)))
        check("storm: notice deduped after first (sent once, then deduped)",
              notices.count("sent") == 1 and "deduped" in notices, str(notices))
        # spool is lossless: 10 caller fires recorded (notice entries excluded)
        caller_spool = [e for e in spool_entries(sd2)
                        if e.get("dedup_key") != STORM_NOTICE_KEY]
        check("storm: spool recorded all 10 caller fires", len(caller_spool) == 10,
              str(len(caller_spool)))

        # -- 3) GATEWAY UNREACHABLE: no delivery path -> exit 3, not recorded ----
        sd3 = Path(tmp) / "gw"
        sd3.mkdir(parents=True, exist_ok=True)
        env_saved = {k: os.environ.pop(k, None)
                     for k in ("ANTHOLOGY_ALERT_DELIVERY_CMD", "FOUNDER_ALERT_CMD")}
        try:
            r, c = do_send(dedup_key="cond:GW", message="held; no gateway wired",
                           category="credit-hold", state_dir=str(sd3),
                           delivery_cmd=None, config={})
            check("gateway: no path -> exit 3", c == EX_GATEWAY, "code=%d" % c)
            check("gateway: outcome gateway_unreachable",
                  r.get("outcome") == "gateway_unreachable", r.get("outcome"))
            check("gateway: alert still spooled (never lost)",
                  len(spool_entries(sd3)) == 1, str(len(spool_entries(sd3))))
            # a failing gateway COMMAND is also exit 3
            r, c = do_send(dedup_key="cond:GW2", message="held; gateway errors",
                           category="credit-hold", state_dir=str(sd3),
                           delivery_cmd=_fail_cmd(), config={})
            check("gateway: failing command -> exit 3", c == EX_GATEWAY, "code=%d" % c)
            # the un-sent key is NOT suppressed: a later GOOD send goes through
            sink3 = str(sd3 / "sink.log")
            r, c = do_send(dedup_key="cond:GW", message="gateway back; retry",
                           category="credit-hold", state_dir=str(sd3),
                           window_seconds=86400, storm_cap=100,
                           delivery_cmd=_sink_cmd(sink3), config={})
            check("gateway: retry after failure delivers -> sent (exit 0)",
                  r.get("outcome") == "sent" and c == EX_OK, r.get("outcome"))
            check("gateway: retry actually reached the gateway",
                  len(sink_lines(sink3)) == 1, str(len(sink_lines(sink3))))
        finally:
            for k, v in env_saved.items():
                if v is not None:
                    os.environ[k] = v

        # -- 4) VALIDATION + DRY-RUN --------------------------------------------
        sd4 = Path(tmp) / "val"
        r, c = do_send(dedup_key="", message="no key", state_dir=str(sd4))
        check("validation: missing key -> exit 2", c == EX_VALIDATION, "code=%d" % c)
        r, c = do_send(dedup_key="cond:V", message=None, state_dir=str(sd4))
        check("validation: missing message -> exit 2", c == EX_VALIDATION, "code=%d" % c)
        r, c = do_send(dedup_key="cond:DRY", message="would alert", state_dir=str(sd4),
                       delivery_cmd=None, dry_run=True, config={})
        check("dry-run: renders without delivering -> exit 0",
              r.get("outcome") == "dry_run" and c == EX_OK, r.get("outcome"))
        check("dry-run: reports no delivery path configured",
              r.get("delivery_path_configured") is False, str(r.get("delivery_path_configured")))

        # -- 5) CLI SURFACE: the flag-style caller contract parses (no subcommand)-
        sd5 = Path(tmp) / "cli"
        sink5 = str(sd5 / "sink.log")
        sd5.mkdir(parents=True, exist_ok=True)
        # hold_queue.py style: bare --dedup-key/--message/--state-dir (no `send`)
        rc = main(["--dedup-key", "cli:hold", "--message", "held via CLI",
                   "--state-dir", str(sd5), "--delivery-cmd", shlex.join(_sink_cmd(sink5))])
        check("cli: hold_queue-style flags (no subcommand) -> exit 0", rc == EX_OK, "rc=%d" % rc)
        # model_router.py style: `send --category --key --message`
        rc = main(["send", "--category", "credit-hold", "--key", "cli:router",
                   "--message", "chain exhausted", "--state-dir", str(sd5),
                   "--delivery-cmd", shlex.join(_sink_cmd(sink5))])
        check("cli: model_router-style `send --key` -> exit 0", rc == EX_OK, "rc=%d" % rc)
        # search_detect.py style: --dedup-key/--subject/--body/--severity
        rc = main(["--dedup-key", "cli:search", "--subject", "search unavailable",
                   "--body", "no search tool", "--severity", "warning",
                   "--state-dir", str(sd5), "--delivery-cmd", shlex.join(_sink_cmd(sink5))])
        check("cli: search_detect-style --subject/--body -> exit 0", rc == EX_OK, "rc=%d" % rc)
        check("cli: three distinct keys reached the gateway", len(sink_lines(sink5)) == 3,
              str(len(sink_lines(sink5))))
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
