#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE (Skill 58) :: DAILY CREDIT SMOKE TEST
# Furnace design Guardrail 1 (dirt-cheap daily credit smoke test) and the
# Guardrail 6 in-run duties (credit-out queue age check and drain trigger).
# -----------------------------------------------------------------------------
# THE ONLY recurring job this skill ships (one cron per client, 6:00 AM client
# time with jitter). Its entire run must cost AT MOST smoke_test.max_cost_usd
# (default 0.01 dollars). It NEVER generates an image, NEVER synthesizes audio,
# NEVER writes an episode, NEVER takes a model turn, NEVER runs the pipeline.
#
# It probes ONLY the pinned balance and reachability endpoints in
# config/smoke-endpoints.json. The runtime never guesses an endpoint: a provider
# with no pinned endpoint is marked UNKNOWN and skipped rather than spent on.
# Every probe is a bounded free GET or HEAD. A provider that exposes no balance
# endpoint uses a reachability probe (host answered = reachable), still free.
#
# The same single run also:
#   - self-meters its own cost to the daily ledger (the overspend canary fires
#     to the OPERATOR, never the client, if a run ever crosses the run budget:
#     that is the signal that someone wired a paid call into the health check);
#   - performs the credit-out queue AGE CHECK (auto age-out at queue_max_hold_days
#     with a deduped founder notice) so no second cron is ever needed;
#   - fires the DRAIN TRIGGER when a previously failing paid service flips back
#     to reachable, so held jobs can resume.
#
# DOCTRINE HELD BY THIS SCRIPT:
#   - MOVE IN SILENCE. Zero client-facing output. Every founder-facing notice is
#     handed to alert-dedup (the sole founder-alert path); this script never
#     sends a chat message itself and never sends around the gateway.
#   - Never prints or echoes a secret value. Credentials are used in a request
#     header only and reported as SET or NOT SET, never by value.
#   - Single-writer respect: it reads episode records read-only and hands state
#     changes to podcast_state.py (or a durable queue-event spool) rather than
#     writing episode records itself.
#   - Writes STATE as the invoking (node) user; refuses to write as root.
#   - No em dash characters anywhere; no triple-backtick fences in any output.
#   - Build-time reasoning models never ship here; this file names no such
#     provider and takes no model turn.
#
# EXIT CODES:
#    0  ran (health computed and written); provider health is DATA, routed via
#       alert-dedup, not signalled by the exit code, so the cron stays green.
#    3  usage or hard input error.
#    5  overspend canary tripped (run cost estimate crossed the run budget).
# =============================================================================

"""Podcast Production Engine daily credit smoke test - bounded, self-metered."""

import argparse
import datetime as _dt
import json
import os
import socket
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request

EXIT_OK = 0
EXIT_USAGE = 3
EXIT_OVERSPEND = 5

# Embedded fallbacks so the run is always bounded even before the per-client
# config lands. The skill config overrides these.
DEFAULT_MAX_COST_USD = 0.01
DEFAULT_QUEUE_MAX_HOLD_DAYS = 60

VALID_STATUS = ("PASS", "FAIL", "UNKNOWN")

# Held-episode stage vocabulary that means "waiting in the credit-out queue".
HELD_STAGES = ("queued", "cost_hold", "credit_out", "credit_hold", "held")

# ---------------------------------------------------------------------------
# E8: stuck non-terminal-job detection (furnace Guardrail 6 extension).
# podcast_state.py (the SOLE writer) owns the real job table: podcast_jobs, with
# columns job_id / client_id / status / updated_at. Its own taxonomy (kept in
# lockstep here on purpose -- a small, self-contained duplication, matching how
# HELD_STAGES above is already this file's own copy of a vocabulary podcast_state.py
# also owns, so this read-only sweep never needs to import the sole-writer module):
#   TERMINAL_STATES = {"complete", "failed"}
#   HOLDING_STATES  = {"queued_credit_out"}   (already age-checked above, and by
#                                              podcast_state.py sweep-aged-out)
# Every OTHER status (received, researching, writing, in_qc, generating_art,
# producing_audio, publishing, enrolling) is a MACHINE-DRIVEN pipeline step: a
# stage runner is expected to move it along within a run, so a row that has not
# had its updated_at touched in stale_job_alert_hours is a crashed/hung stage
# runner, never a legitimate long wait (podcast has no producer/participant gate
# concept -- unlike the Anthology Engine, nothing here is SUPPOSED to sit idle).
# -----------------------------------------------------------------------------
_JOB_TERMINAL_STATES = frozenset({"complete", "failed"})
_JOB_HOLDING_STATES = frozenset({"queued_credit_out"})
DEFAULT_STALE_JOB_ALERT_HOURS = 24


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _eprint(msg):
    sys.stderr.write(str(msg).rstrip("\n") + "\n")


def _now():
    return _dt.datetime.now().astimezone()


def _now_iso():
    return _now().isoformat(timespec="seconds")


def _script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _skill_root():
    return os.path.dirname(_script_dir())


def _default_state_dir():
    env = os.environ.get("PODCAST_ENGINE_STATE_DIR")
    if env:
        return os.path.expanduser(env)
    return os.path.expanduser("~/.openclaw/podcast-engine/state")


def _default_client():
    env = os.environ.get("PODCAST_CLIENT")
    if env:
        return env
    try:
        return socket.gethostname().split(".")[0] or "default"
    except Exception:
        return "default"


def _refuse_root_write(state_dir):
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            _eprint(
                "smoke-test: refusing to write state as root (euid 0). "
                "Run as the node user so the gateway user owns podcast state."
            )
            sys.exit(EXIT_USAGE)
    except Exception:
        pass


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (ValueError, OSError) as exc:
        _eprint("smoke-test: could not read %s (%s)" % (path, exc))
        return default


def _atomic_write_json(path, obj):
    _ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _append_jsonl(path, obj):
    _ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True) + "\n")


def _key_is_set(key_env_names):
    for name in key_env_names or []:
        val = os.environ.get(name)
        if val:  # presence only; the value is never read into output
            return True
    return False


def _resolve_key(key_env_names):
    # Returns the secret for use in a request header ONLY. Never logged.
    for name in key_env_names or []:
        val = os.environ.get(name)
        if val:
            return val
    return None


# ---------------------------------------------------------------------------
# Config and endpoint loading
# ---------------------------------------------------------------------------
def _load_mapping(path):
    if not path or not os.path.exists(path):
        return None
    lower = path.lower()
    if lower.endswith((".yaml", ".yml")):
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh)
        except Exception as exc:  # pragma: no cover
            _eprint("smoke-test: could not parse YAML %s (%s)" % (path, exc))
            return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError) as exc:
        _eprint("smoke-test: could not parse %s (%s)" % (path, exc))
        return None


def _find_skill_config(explicit):
    if explicit:
        return explicit
    env = os.environ.get("PODCAST_ENGINE_CONFIG")
    if env:
        return env
    root = _skill_root()
    for name in ("podcast-engine.yaml", "podcast-engine.yml",
                 "podcast-engine.json", "config.yaml", "config.json"):
        candidate = os.path.join(root, "config", name)
        if os.path.exists(candidate):
            return candidate
    return None


def load_run_config(config_path):
    max_cost = DEFAULT_MAX_COST_USD
    hold_days = DEFAULT_QUEUE_MAX_HOLD_DAYS
    stale_hours = DEFAULT_STALE_JOB_ALERT_HOURS
    stale_hours_by_status = {}
    cfg = _load_mapping(_find_skill_config(config_path))
    if isinstance(cfg, dict):
        node = cfg.get("podcast_engine", cfg)
        if isinstance(node, dict):
            smoke = node.get("smoke_test", {})
            if isinstance(smoke, dict) and "max_cost_usd" in smoke:
                max_cost = float(smoke["max_cost_usd"])
            if isinstance(smoke, dict) and "stale_job_alert_hours" in smoke:
                stale_hours = float(smoke["stale_job_alert_hours"])
            if isinstance(smoke, dict) and isinstance(
                smoke.get("stale_job_alert_hours_by_status"), dict
            ):
                stale_hours_by_status = {
                    str(k): float(v)
                    for k, v in smoke["stale_job_alert_hours_by_status"].items()
                }
            limits = node.get("limits", {})
            if isinstance(limits, dict) and "queue_max_hold_days" in limits:
                hold_days = int(limits["queue_max_hold_days"])
    return {
        "max_cost_usd": max_cost,
        "queue_max_hold_days": hold_days,
        "stale_job_alert_hours": stale_hours,
        "stale_job_alert_hours_by_status": stale_hours_by_status,
    }


def _resolve_podcast_db_path(explicit=None):
    """Mirrors podcast_state.py's resolve_db_path (PODCAST_DB_PATH env, else
    ~/.openclaw/podcast-engine/podcast-engine.db). Duplicated locally, deliberately,
    so this read-only sweep never imports the sole-writer module."""
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    env = os.environ.get("PODCAST_DB_PATH")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(
        os.path.expanduser("~"), ".openclaw", "podcast-engine", "podcast-engine.db"
    )


def load_endpoints(endpoints_path):
    path = endpoints_path or os.path.join(_skill_root(), "config", "smoke-endpoints.json")
    data = _load_mapping(path)
    if not isinstance(data, dict):
        return None, path
    providers = data.get("providers", data)
    if not isinstance(providers, dict):
        return None, path
    return providers, path


# ---------------------------------------------------------------------------
# Probing (free GET or HEAD only; never a model turn)
# ---------------------------------------------------------------------------
def _http_probe(url, method, headers, timeout_s):
    """Return an int HTTP status if the host answered, else None (unreachable)."""
    req = urllib.request.Request(url, method=method.upper())
    for hk, hv in (headers or {}).items():
        req.add_header(hk, hv)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.getcode())
    except urllib.error.HTTPError as exc:
        # The host answered with an HTTP error; that still proves reachability.
        return int(exc.code)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return None
    except Exception:  # pragma: no cover - defensive
        return None


def probe_provider(name, spec, offline=False):
    """Probe one provider. Never takes a model turn, never logs the secret."""
    probe_type = str(spec.get("probe", "balance")).lower()
    url = spec.get("url") or spec.get("balance_url") or spec.get("reachability_url")
    method = str(spec.get("method", "GET")).upper()
    key_env = spec.get("key_env", [])
    auth = str(spec.get("auth", "none")).lower()
    ok_status = spec.get("ok_status", [200])
    timeout_s = float(spec.get("timeout_s", 15))

    result = {"status": "UNKNOWN", "checked_at": _now_iso(), "detail": ""}

    if not url:
        result["detail"] = "no url pinned"
        return result

    # An auth-bearing balance probe needs a key. Report SET or NOT SET only.
    needs_key = auth in ("bearer", "header", "token")
    if needs_key and not _key_is_set(key_env):
        result["detail"] = "key not set"
        return result

    if offline:
        result["detail"] = "offline (skipped)"
        return result

    headers = {"Accept": "application/json"}
    if needs_key:
        secret = _resolve_key(key_env)
        if auth == "bearer":
            headers["Authorization"] = "Bearer " + secret
        elif auth == "token":
            headers["Authorization"] = secret
        elif auth == "header":
            header_name = spec.get("header_name", "Authorization")
            headers[header_name] = secret

    code = _http_probe(url, method, headers, timeout_s)

    if probe_type == "reachability":
        if code is not None:
            result["status"] = "PASS"
            result["detail"] = "reachable (http %d)" % code
        else:
            result["status"] = "FAIL"
            result["detail"] = "unreachable"
        return result

    # balance probe: an explicit ok_status is authoritative
    if code is None:
        result["status"] = "FAIL"
        result["detail"] = "unreachable"
    elif code in ok_status:
        result["status"] = "PASS"
        result["detail"] = "balance ok (http %d)" % code
    else:
        result["status"] = "FAIL"
        result["detail"] = "http %d" % code
    return result


def _apply_force_status(services, force_status):
    for item in force_status or []:
        if "=" not in item:
            continue
        name, status = item.split("=", 1)
        status = status.strip().upper()
        if status in VALID_STATUS and name in services:
            services[name]["status"] = status
            services[name]["detail"] = "forced " + status


# ---------------------------------------------------------------------------
# Self-metering through the cost ledger (single source of price truth)
# ---------------------------------------------------------------------------
def self_meter(state_dir, client, probe_count, config_path):
    ledger = os.path.join(_script_dir(), "podcast-cost-ledger.py")
    if not os.path.exists(ledger):
        return 0.0
    cmd = [sys.executable, ledger, "--state-dir", state_dir]
    if config_path:
        cmd += ["--config", config_path]
    cmd += ["record", "--client", client, "--kind", "smoke_probe",
            "--units", str(probe_count), "--note", "daily smoke test"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode in (0, 2):  # ok or advisory soft
            data = json.loads(out.stdout or "{}")
            return float(data.get("recorded_usd", 0.0))
        _eprint("smoke-test: ledger record returned %d" % out.returncode)
        return 0.0
    except Exception as exc:
        _eprint("smoke-test: could not self-meter (%s)" % exc)
        return 0.0


# ---------------------------------------------------------------------------
# Alert routing (sole founder path is alert-dedup; we enqueue, never send)
# ---------------------------------------------------------------------------
# Map this script's alert vocabulary onto alert-dedup.py's REAL contract.
# alert-dedup.py exposes subcommands {raise, recover, flush-digest, status} and,
# for `raise`, severities (status, decision, digest) ONLY. The historical
# `notify` subcommand and the 'canary'/'recovery' severities never existed
# there, so those invocations died at argparse (exit 2, "invalid choice") and
# every founder alert -- overspend, new_fail, recovered, aged-out digest, and
# any future stale-job notice -- was spooled but NEVER pushed to the gateway.
# This table restores live delivery while the spool stays the source of truth:
#   status   -> raise  --severity status    service outage; 6h window + storm cap
#   digest   -> raise  --severity digest    aged-out/batched; daily flush
#   canary   -> raise  --severity decision  overspend safety alert; always-send
#   recovery -> recover                     service restored; one note, clears key
_ALERT_SEVERITY_MAP = {
    "status": ("raise", "status"),
    "digest": ("raise", "digest"),
    "canary": ("raise", "decision"),
    "decision": ("raise", "decision"),
    "recovery": ("recover", None),
    "recover": ("recover", None),
}


def _dedup_argv(python_exe, dedup_path, state_dir, client, service,
                failure_class, severity, message, episodes=None, dry_run=False):
    """Build the exact alert-dedup.py argv for one founder alert.

    Pure and side-effect free so the contract test can assert the invocation is
    one alert-dedup.py actually accepts (a real subcommand + severity, never the
    dead `notify`/`--class`) and drive it against the REAL script. Always pins
    --state-dir to the caller's engine state dir so alert dedup state is
    per-client and never leaks into the shared default dir."""
    subcommand, mapped_sev = _ALERT_SEVERITY_MAP.get(severity, ("raise", "status"))
    eps = list(episodes or [])
    argv = [python_exe, dedup_path, subcommand,
            "--state-dir", state_dir,
            "--client", client, "--service", service,
            "--failure-class", failure_class,
            "--message", message]
    if subcommand == "raise":
        argv += ["--severity", mapped_sev]
        if mapped_sev == "decision" and not eps:
            # decision-class dedups per episode and alert-dedup.py requires an
            # --episode; a client-wide safety alert (overspend) has none, so key
            # it by its failure class -> one always-send alert per event.
            eps = [failure_class]
        for ep in eps:
            argv += ["--episode", ep]
    if dry_run:
        argv += ["--dry-run"]
    return argv


def route_alert(state_dir, client, service, failure_class, severity, message,
                episodes=None, dry_run=False):
    """Enqueue a founder notice. Durable spool is the source of truth; if
    alert-dedup is present it is invoked best-effort so the alert also delivers
    live. This NEVER sends a chat message and NEVER goes around the gateway.

    Returns the alert-dedup subprocess result (or None when the script is absent
    or the invocation could not run) so callers/tests can observe delivery."""
    alert = {
        "at": _now_iso(),
        "client": client,
        "service": service,
        "failure_class": failure_class,
        "severity": severity,          # status | recovery | digest | canary
        "message": message,
        "episodes": episodes or [],
        "dedup_key": "%s+%s+%s" % (client, service, failure_class),
    }
    spool = os.path.join(state_dir, "alerts-pending",
                         "%s.jsonl" % _now().date().isoformat())
    try:
        _append_jsonl(spool, alert)
    except Exception as exc:  # pragma: no cover
        _eprint("smoke-test: could not spool alert (%s)" % exc)

    dedup = os.path.join(_script_dir(), "alert-dedup.py")
    if not os.path.exists(dedup):
        return None
    cmd = _dedup_argv(sys.executable, dedup, state_dir, client, service,
                      failure_class, severity, message,
                      episodes=episodes, dry_run=dry_run)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:  # pragma: no cover
        _eprint("smoke-test: alert-dedup invocation failed (%s); alert is "
                "spooled for its next drain" % exc)
        return None
    if proc.returncode != 0:
        # Delivery could not complete (e.g. no founder target configured, or the
        # gateway rejected the send). The alert is already spooled, so the next
        # drain retries it; surface the code rather than swallow it silently.
        tail = (proc.stderr or "").strip().splitlines()
        _eprint("smoke-test: alert-dedup rc=%d for %s/%s; alert stays spooled%s"
                % (proc.returncode, service, failure_class,
                   (" (%s)" % tail[-1]) if tail else ""))
    return proc


# ---------------------------------------------------------------------------
# Queue duties: age check and drain trigger (single-writer respectful)
# ---------------------------------------------------------------------------
def _iter_episode_records(state_dir):
    ep_dir = os.path.join(state_dir, "episodes")
    if not os.path.isdir(ep_dir):
        return
    for name in sorted(os.listdir(ep_dir)):
        if not name.endswith(".json"):
            continue
        rec = _read_json(os.path.join(ep_dir, name), None)
        if isinstance(rec, dict):
            yield rec


def _held_since(rec):
    q = rec.get("queue", {}) if isinstance(rec.get("queue"), dict) else {}
    ts = (q.get("held_since")
          or rec.get("timestamps", {}).get("received")
          or rec.get("opened"))
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(ts)
    except ValueError:
        return None


def _age_days(rec):
    since = _held_since(rec)
    if not since:
        return 0
    if since.tzinfo is None:
        now = _dt.datetime.now()
    else:
        now = _now()
    return max(0, (now - since).days)


def _is_held(rec):
    stage = str(rec.get("stage", "")).lower()
    if stage in HELD_STAGES:
        return True
    q = rec.get("queue", {})
    return bool(isinstance(q, dict) and q.get("held"))


def _hold_reason(rec):
    q = rec.get("queue", {})
    if isinstance(q, dict) and q.get("reason"):
        return str(q.get("reason")).lower()
    return ""


def _norm(token):
    # Separator-insensitive compare so a hold reason of "fish_audio" still
    # matches a service pinned as "fish-audio".
    return "".join(c for c in str(token).lower() if c.isalnum())


def _emit_queue_event(state_dir, action, episode_id, service, detail):
    """Record a queue action for the sole state writer to apply. Also invoke
    podcast_state.py best-effort if present, but never write episode records
    from here."""
    event = {"at": _now_iso(), "action": action, "episode_id": episode_id,
             "service": service, "detail": detail}
    spool = os.path.join(state_dir, "queue-events",
                         "%s.jsonl" % _now().date().isoformat())
    _append_jsonl(spool, event)

    for writer_name in ("podcast_state.py", "podcast-episode-state.py"):
        writer = os.path.join(_script_dir(), writer_name)
        if not os.path.exists(writer):
            continue
        if action == "age_out":
            cmd = [sys.executable, writer, "--state-dir", state_dir,
                   "set-stage", "--episode-id", episode_id, "--stage", "aged_out"]
        else:  # drain: release the hold so the pipeline can resume
            cmd = [sys.executable, writer, "--state-dir", state_dir,
                   "set-queue", "--episode-id", episode_id, "--held", "false",
                   "--reason", "drain:" + service]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as exc:  # pragma: no cover
            _eprint("smoke-test: state writer invocation failed (%s); queue "
                    "event is spooled" % exc)
        break


def run_queue_duties(state_dir, client, hold_days, recovered_services):
    aged = []
    drained = []
    for rec in _iter_episode_records(state_dir):
        if not _is_held(rec):
            continue
        episode_id = rec.get("episode_id") or rec.get("id")
        if not episode_id:
            continue
        age = _age_days(rec)
        reason = _hold_reason(rec)

        # Age-out at the 60-day maximum: never dropped silently, founder noticed.
        if age >= hold_days:
            _emit_queue_event(state_dir, "age_out", episode_id, reason,
                              "held %d days (max %d)" % (age, hold_days))
            aged.append(episode_id)
            continue

        # Drain trigger: a service this job waited on is reachable again.
        reason_n = _norm(reason)
        for svc in recovered_services:
            svc_n = _norm(svc)
            if svc_n and reason_n and (svc_n in reason_n or reason_n in svc_n):
                _emit_queue_event(state_dir, "drain", episode_id, svc,
                                  "service %s reachable again" % svc)
                drained.append(episode_id)
                break

    if aged:
        route_alert(state_dir, client, "queue", "aged_out", "digest",
                    "%d episode(s) aged out at the %d-day maximum."
                    % (len(aged), hold_days), episodes=aged)
    return {"aged_out": aged, "drained": drained}


# ---------------------------------------------------------------------------
# E8: stuck non-terminal-job sweep (read-only; alert-only, never auto-fail/resume)
# ---------------------------------------------------------------------------
def find_stale_jobs(db_path, default_hours, by_status_hours=None, now=None):
    """Read-only SELECT over podcast_jobs for rows sitting in a non-terminal,
    non-held status past their (possibly per-status) age threshold. Returns a
    list of dicts; never raises on a missing/corrupt/absent DB (fail-soft: an
    unprovisioned or not-yet-created DB is not a stale-job finding)."""
    by_status_hours = by_status_hours or {}
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if not db_path or not os.path.exists(db_path):
        return []
    stale = []
    try:
        uri = "file:%s?mode=ro" % urllib.request.pathname2url(db_path)
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT job_id, client_id, status, updated_at FROM podcast_jobs"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        _eprint("smoke-test: stale-job sweep could not read %s (%s)" % (db_path, exc))
        return []

    for row in rows:
        status = row["status"]
        if status in _JOB_TERMINAL_STATES or status in _JOB_HOLDING_STATES:
            continue
        updated_at = row["updated_at"]
        if not updated_at:
            continue
        try:
            since = _dt.datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=_dt.timezone.utc
            )
        except ValueError:
            continue
        age_hours = (now - since).total_seconds() / 3600.0
        threshold = float(by_status_hours.get(status, default_hours))
        if age_hours >= threshold:
            stale.append({
                "job_id": row["job_id"],
                "client_id": row["client_id"],
                "status": status,
                "updated_at": updated_at,
                "age_hours": round(age_hours, 2),
                "threshold_hours": threshold,
            })
    return stale


def run_stale_job_sweep(state_dir, client, db_path, default_hours, by_status_hours=None):
    """Alert-only: a stale job never gets auto-failed or auto-resumed here (SKILL.md
    forbids per-job watchers/actuation outside the sole writer). Each finding routes
    exactly ONE deduped operator alert through alert-dedup (dedup key includes the
    job_id, so a still-stuck job reminds again only after alert-dedup's own window;
    a resolved job simply stops matching the SELECT on the next daily run)."""
    stale = find_stale_jobs(db_path, default_hours, by_status_hours)
    for job in stale:
        route_alert(
            state_dir, client, "pipeline_stall", job["job_id"], "status",
            "Job %s has sat in status '%s' for %.1fh (threshold %.0fh). Possible "
            "crashed/hung stage runner; the job has not been touched."
            % (job["job_id"], job["status"], job["age_hours"], job["threshold_hours"]),
        )
    return {"stale_count": len(stale), "stale_jobs": [j["job_id"] for j in stale]}


# ---------------------------------------------------------------------------
# Health transition analysis
# ---------------------------------------------------------------------------
def analyze_transitions(prev_health, new_services):
    prev = (prev_health or {}).get("services", {})
    recovered = []   # was not-PASS, now PASS  -> drain candidates
    new_fail = []    # was PASS/absent, now FAIL -> new outage
    still_fail = []  # FAIL now (was FAIL before) -> deduped repeat
    for name, cur in new_services.items():
        cur_status = cur.get("status")
        prev_status = prev.get(name, {}).get("status")
        if cur_status == "PASS" and prev_status not in (None, "PASS"):
            recovered.append(name)
        elif cur_status == "FAIL" and prev_status != "FAIL":
            new_fail.append(name)
        elif cur_status == "FAIL" and prev_status == "FAIL":
            still_fail.append(name)
    return recovered, new_fail, still_fail


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------
def do_run(args):
    _refuse_root_write(args.state_dir)
    state_dir = args.state_dir
    client = args.client
    run_cfg = load_run_config(args.config)
    max_cost = run_cfg["max_cost_usd"]
    hold_days = run_cfg["queue_max_hold_days"]
    stale_hours = run_cfg["stale_job_alert_hours"]
    stale_hours_by_status = run_cfg["stale_job_alert_hours_by_status"]

    providers, endpoints_path = load_endpoints(args.endpoints)
    health_path = os.path.join(state_dir, "health.json")
    prev_health = _read_json(health_path, None)

    services = {}
    probe_count = 0
    if providers is None:
        _eprint("smoke-test: no pinned endpoints at %s; nothing probed (this is "
                "a provisioning gap, not a spend)" % endpoints_path)
        route_alert(state_dir, client, "smoke_test", "endpoints_missing", "status",
                    "Smoke test found no pinned balance endpoints. Provision "
                    "config/smoke-endpoints.json.")
    else:
        for name in sorted(providers.keys()):
            spec = providers[name]
            if not isinstance(spec, dict):
                continue
            services[name] = probe_provider(name, spec, offline=args.offline)
            # A probe only counts as spend-relevant when it actually goes out.
            if services[name]["detail"] not in ("key not set", "no url pinned",
                                                 "offline (skipped)"):
                probe_count += 1
        _apply_force_status(services, args.force_status)

    # Self-meter to the daily ledger (price truth lives in the ledger).
    run_cost = self_meter(state_dir, client, probe_count, args.config)

    # Write health BEFORE alerting so the dashboard always reflects the latest.
    health = {
        "checked_at": _now_iso(),
        "client": client,
        "services": services,
        "run_cost_usd_estimate": round(run_cost, 6),
        "probes": probe_count,
    }
    _atomic_write_json(health_path, health)

    # Overspend canary: fire to the OPERATOR, never the client.
    overspend = run_cost > max_cost
    if overspend:
        route_alert(state_dir, client, "smoke_test", "smoke_test_overspend",
                    "canary",
                    "Smoke test run cost estimate %.4f crossed the run budget "
                    "%.2f. Something wired a paid call into the health check."
                    % (run_cost, max_cost))

    # Transition analysis for outage and drain routing.
    recovered, new_fail, still_fail = analyze_transitions(prev_health, services)

    for name in new_fail:
        route_alert(state_dir, client, name, "unreachable_or_unfunded", "status",
                    "%s check failed: %s." % (name, services[name]["detail"]))
    for name in recovered:
        route_alert(state_dir, client, name, "unreachable_or_unfunded", "recovery",
                    "%s reachable again; held episodes for %s may resume."
                    % (name, name))

    # Queue duties: age-out and drain, in the SAME run (no second cron).
    queue_result = run_queue_duties(state_dir, client, hold_days, recovered)

    # E8: stuck non-terminal-job sweep, in the SAME run (no second cron). Read-only;
    # never fails the smoke-test run itself (a DB read error degrades to "no findings").
    try:
        db_path = _resolve_podcast_db_path(args.db_path)
        stale_result = run_stale_job_sweep(
            state_dir, client, db_path, stale_hours, stale_hours_by_status
        )
    except Exception as exc:  # pragma: no cover - defensive, never crash the tick
        _eprint("smoke-test: stale-job sweep failed (%s)" % exc)
        stale_result = {"stale_count": 0, "stale_jobs": [], "error": str(exc)}

    summary = {
        "checked_at": health["checked_at"],
        "client": client,
        "run_cost_usd_estimate": round(run_cost, 6),
        "run_budget_usd": max_cost,
        "overspend_canary": overspend,
        "services": {n: s["status"] for n, s in services.items()},
        "recovered": recovered,
        "new_failures": new_fail,
        "still_failing": still_fail,
        "queue": queue_result,
        "stale_jobs": stale_result,
        "endpoints_source": endpoints_path,
    }
    sys.stdout.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return EXIT_OVERSPEND if overspend else EXIT_OK


# ---------------------------------------------------------------------------
# Self test (deterministic, offline, temp state dir; no network, no secrets)
# ---------------------------------------------------------------------------
def do_self_test(_args):
    import tempfile

    passed = []
    failed = []

    def check(name, cond):
        (passed if cond else failed).append(name)

    tmp = tempfile.mkdtemp(prefix="podcast-smoke-selftest-")
    state_dir = os.path.join(tmp, "state")
    _ensure_dir(state_dir)

    endpoints_path = os.path.join(tmp, "smoke-endpoints.json")
    _atomic_write_json(endpoints_path, {"providers": {
        "ollama-cloud": {"probe": "balance", "method": "GET",
                         "url": "https://example.invalid/credits",
                         "auth": "bearer", "key_env": ["SELFTEST_KEY_UNSET"],
                         "ok_status": [200], "timeout_s": 5},
        "fish-audio": {"probe": "balance", "method": "GET",
                       "url": "https://example.invalid/wallet",
                       "auth": "bearer", "key_env": ["SELFTEST_KEY_UNSET2"],
                       "ok_status": [200], "timeout_s": 5},
    }})

    # Seed a previous health where fish-audio was FAILing (for the drain test).
    _atomic_write_json(os.path.join(state_dir, "health.json"), {
        "checked_at": "2026-07-05T06:00:00-04:00",
        "services": {"fish-audio": {"status": "FAIL"},
                     "ollama-cloud": {"status": "PASS"}},
    })

    # A very old held episode (age-out) tied to fish-audio.
    _ensure_dir(os.path.join(state_dir, "episodes"))
    _atomic_write_json(os.path.join(state_dir, "episodes", "old.json"), {
        "episode_id": "old", "client": "selftest", "stage": "cost_hold",
        "queue": {"held": True, "reason": "fish-audio",
                  "held_since": "2026-01-01T00:00:00"},
    })
    # A recently held episode tied to fish-audio (drain candidate on recovery).
    # Reason uses an underscore to prove separator-insensitive drain matching
    # against the "fish-audio" service name.
    _atomic_write_json(os.path.join(state_dir, "episodes", "recent.json"), {
        "episode_id": "recent", "client": "selftest", "stage": "credit_out",
        "queue": {"held": True, "reason": "fish_audio:insufficient_credits",
                  "held_since": _now_iso()},
    })

    class NS(object):
        pass

    ns = NS()
    ns.state_dir = state_dir
    ns.config = None
    ns.endpoints = endpoints_path
    ns.client = "selftest"
    ns.db_path = os.path.join(tmp, "no-such.db")  # E8 sweep: absent DB -> no findings
    ns.offline = True
    # Force fish-audio to PASS to deterministically exercise the drain trigger
    # (offline yields UNKNOWN otherwise; there is no network in a self test).
    ns.force_status = ["fish-audio=PASS"]

    real_stdout = sys.stdout
    devnull = open(os.devnull, "w")
    sys.stdout = devnull
    try:
        rc = do_run(ns)
    finally:
        sys.stdout = real_stdout
        devnull.close()

    check("run exits ok (no overspend on free probes)", rc == EXIT_OK)

    health = _read_json(os.path.join(state_dir, "health.json"), {})
    check("health.json written with services",
          isinstance(health.get("services"), dict) and health["services"])
    check("unset-key provider marked UNKNOWN",
          health.get("services", {}).get("ollama-cloud", {}).get("status") == "UNKNOWN")
    check("run cost estimate is zero on free probes",
          float(health.get("run_cost_usd_estimate", 1)) == 0.0)

    # Queue events: expect an age_out for 'old' and a drain for 'recent'.
    qdir = os.path.join(state_dir, "queue-events")
    events = []
    if os.path.isdir(qdir):
        for fn in os.listdir(qdir):
            with open(os.path.join(qdir, fn), "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
    actions = {(e["episode_id"], e["action"]) for e in events}
    check("old held episode aged out", ("old", "age_out") in actions)
    check("recovered service drains recent held episode",
          ("recent", "drain") in actions)

    # Alerts spooled (aged-out digest and fish-audio recovery), never sent.
    adir = os.path.join(state_dir, "alerts-pending")
    alerts = []
    if os.path.isdir(adir):
        for fn in os.listdir(adir):
            with open(os.path.join(adir, fn), "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        alerts.append(json.loads(line))
    severities = {a["severity"] for a in alerts}
    check("recovery alert enqueued", "recovery" in severities)
    check("aged-out digest alert enqueued", "digest" in severities)

    # Self-meter recorded a smoke_probe line into the daily ledger.
    ledger_dir = os.path.join(state_dir, "ledger")
    metered = os.path.isdir(ledger_dir) and any(
        f.endswith(".json") for f in os.listdir(ledger_dir))
    check("self-metered to the daily ledger", metered)

    # Runtime model router (E6): its own hermetic battery must pass, and a denied
    # id must be refused with exit 2 (deny-pattern refusal is never a fallback).
    router = os.path.join(_script_dir(), "model_router.py")
    if os.path.exists(router):
        try:
            rr = subprocess.run([sys.executable, router, "self-test"],
                                capture_output=True, text=True, timeout=60)
            check("model_router self-test passes", rr.returncode == 0)
            dd = subprocess.run([sys.executable, router, "deny-check", "vendor-opus-preview"],
                                capture_output=True, text=True, timeout=30)
            check("model_router refuses a denied id (exit 2)", dd.returncode == 2)
        except Exception as exc:
            check("model_router self-test invocable (%s)" % exc, False)
    else:
        check("model_router.py present", False)

    # Required-outputs gate (E7): a producing stage may not advance past a missing
    # deliverable, and --force-waiver overrides it. Drive podcast_state.py against a
    # throwaway DB entirely inside the self-test tmp dir (no network, no live DB).
    pstate = os.path.join(_script_dir(), "podcast_state.py")
    if os.path.exists(pstate):
        gate_db = os.path.join(tmp, "gate.db")
        payload = os.path.join(tmp, "gate-payload.json")
        with open(payload, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"preset": "interview"}))
        env = dict(os.environ)
        env["PODCAST_DB_PATH"] = gate_db

        def _ps(*a):
            return subprocess.run([sys.executable, pstate, *a],
                                  capture_output=True, text=True, timeout=30, env=env)

        try:
            _ps("create", "--client-id", "st", "--location-id", "l", "--contact-id", "ct",
                "--mode", "interview_style_podcast", "--style", "vulnerable",
                "--payload-file", payload, "--job-key", "gatek")
            import sqlite3 as _sq
            jid = _sq.connect(gate_db).execute(
                "SELECT job_id FROM podcast_jobs").fetchone()[0]
            for st in ("researching", "writing", "in_qc", "generating_art"):
                _ps("advance", "--job-id", jid, "--to", st)
            _ps("output", "--job-id", jid, "--field", "cover_image_url", "--value", "https://x/c.png")
            _ps("advance", "--job-id", jid, "--to", "producing_audio")
            _ps("advance", "--job-id", jid, "--to", "publishing")
            blocked = _ps("advance", "--job-id", jid, "--to", "enrolling")
            check("required-outputs gate blocks advance on a missing artifact (exit 3)",
                  blocked.returncode == 3)
            waived = _ps("advance", "--job-id", jid, "--to", "enrolling", "--force-waiver")
            check("--force-waiver overrides the required-outputs gate", waived.returncode == 0)
            waiver_events = _sq.connect(gate_db).execute(
                "SELECT count(*) FROM podcast_job_events WHERE note LIKE '%WAIVED%'").fetchone()[0]
            check("waived advance writes an audit event", waiver_events >= 1)
        except Exception as exc:
            check("required-outputs gate drivable (%s)" % exc, False)
    else:
        check("podcast_state.py present", False)

    # E8: stuck non-terminal-job sweep. Deterministic, offline, throwaway DB (never
    # the live DB). A stale row is fabricated by writing updated_at directly with
    # sqlite3 -- this is TEST FIXTURE SETUP, mirroring how this same self-test already
    # seeds episodes/*.json fixtures directly rather than through a "real" writer.
    if os.path.exists(pstate):
        stale_db = os.path.join(tmp, "stale.db")
        payload2 = os.path.join(tmp, "stale-payload.json")
        with open(payload2, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"preset": "interview"}))
        try:
            env2 = dict(os.environ)
            env2["PODCAST_DB_PATH"] = stale_db

            def _ps2(*a):
                return subprocess.run([sys.executable, pstate, *a],
                                      capture_output=True, text=True, timeout=30, env=env2)

            _ps2("create", "--client-id", "st2", "--location-id", "l", "--contact-id", "ct-stale",
                 "--mode", "interview_style_podcast", "--style", "vulnerable",
                 "--payload-file", payload2, "--job-key", "gatek-stale")
            _ps2("create", "--client-id", "st2", "--location-id", "l", "--contact-id", "ct-fresh",
                 "--mode", "interview_style_podcast", "--style", "vulnerable",
                 "--payload-file", payload2, "--job-key", "gatek-fresh")

            import sqlite3 as _sq2
            conn2 = _sq2.connect(stale_db)
            rows = conn2.execute(
                "SELECT job_id, contact_id FROM podcast_jobs ORDER BY created_at"
            ).fetchall()
            job_ids = {contact_id: job_id for job_id, contact_id in rows}
            stale_job_id = job_ids.get("ct-stale")
            fresh_job_id = job_ids.get("ct-fresh")
            # Push the stale job past received into a genuinely non-terminal,
            # non-held, machine-driven status.
            _ps2("advance", "--job-id", stale_job_id, "--to", "researching")
            # Backdate ONLY the stale job's updated_at 30h into the past (> the 24h
            # default). The fresh job is left exactly as `create` wrote it.
            old_ts = (_now() - _dt.timedelta(hours=30)).astimezone(_dt.timezone.utc) \
                .strftime("%Y-%m-%d %H:%M:%S")
            conn2.execute("UPDATE podcast_jobs SET updated_at = ? WHERE job_id = ?",
                         (old_ts, stale_job_id))
            conn2.commit()
            conn2.close()

            stale_state_dir = os.path.join(tmp, "stale-state")
            _ensure_dir(stale_state_dir)
            findings = find_stale_jobs(stale_db, DEFAULT_STALE_JOB_ALERT_HOURS)
            found_ids = {f["job_id"] for f in findings}
            check("stale job (30h, researching) detected", stale_job_id in found_ids)
            check("fresh job (just created) NOT flagged", fresh_job_id not in found_ids)

            sweep_result = run_stale_job_sweep(
                stale_state_dir, "st2", stale_db, DEFAULT_STALE_JOB_ALERT_HOURS
            )
            check("sweep reports exactly one stale job", sweep_result["stale_count"] == 1)

            sdir = os.path.join(stale_state_dir, "alerts-pending")
            alerts2 = []
            if os.path.isdir(sdir):
                for fn in os.listdir(sdir):
                    with open(os.path.join(sdir, fn), "r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if line:
                                alerts2.append(json.loads(line))
            pstall = [a for a in alerts2 if a.get("service") == "pipeline_stall"]
            check("exactly one pipeline_stall alert enqueued", len(pstall) == 1)
            check("pipeline_stall alert keyed to the stale job_id",
                  bool(pstall) and pstall[0].get("failure_class") == stale_job_id)

            # Absent DB -> no findings, never a crash (already exercised by the main
            # do_run() call above via ns.db_path pointing at a nonexistent file).
            check("absent DB yields zero findings, not an error",
                  find_stale_jobs(os.path.join(tmp, "no-such.db"), 24) == [])
        except Exception as exc:
            check("stale-job sweep drivable (%s)" % exc, False)
    else:
        check("podcast_state.py present (stale-job sweep)", False)

    total = len(passed) + len(failed)
    report = {
        "self_test": "podcast-smoke-test",
        "passed": len(passed),
        "total": total,
        "failed_checks": failed,
        "state_dir": state_dir,
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return EXIT_OK if not failed else EXIT_USAGE


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="Podcast Production Engine daily credit smoke test - the "
                    "single cron, bounded at or under 1 cent, self-metered "
                    "(furnace Guardrails 1 and 6).")
    p.add_argument("--state-dir", default=_default_state_dir())
    p.add_argument("--config", default=None, help="skill config path")
    p.add_argument("--endpoints", default=None,
                   help="pinned smoke-endpoints.json path")
    p.add_argument("--client", default=_default_client())
    p.add_argument("--db-path", default=None,
                   help="override the podcast_jobs SQLite DB path for the E8 stale-job "
                        "sweep (default $PODCAST_DB_PATH or "
                        "~/.openclaw/podcast-engine/podcast-engine.db)")
    p.add_argument("--offline", action="store_true",
                   help="skip all network probes (CI and dry runs)")
    p.add_argument("--force-status", action="append", default=[],
                   metavar="NAME=STATUS",
                   help="manually set a service status (PASS/FAIL/UNKNOWN); "
                        "operator and test seam, not a network call")
    p.add_argument("--self-test", action="store_true",
                   help="run the deterministic offline self test")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "self_test", False):
        return do_self_test(args)
    return do_run(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # pragma: no cover
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(EXIT_OK)
    except KeyboardInterrupt:  # pragma: no cover
        os._exit(130)
