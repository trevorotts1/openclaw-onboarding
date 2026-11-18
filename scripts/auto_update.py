#!/usr/bin/env python3
"""auto_update.py -- a box's own Tuesday / Friday / Sunday update (stdlib only).

One system crontab line runs scripts/auto-update-tick.sh every 5 minutes. That
tick calls `auto_update.py tick`, which does the whole job deterministically
(no model decides anything about timing, locking, versions or rollback):

  2:15 AM Eastern   one notice in the owner's main chat, once per scheduled day
  2:15 - run start  a client "cancel" (whole word, any case) skips THIS run only
  2:30 AM + jitter  the update run: lock, version check, snapshot + update +
                    health gate + repair + rollback (the existing fleet-refresh
                    machinery), status beacon

Time is computed here, in America/New_York with the US daylight saving rules
written out below, so it never depends on the box time zone or on tzdata being
installed. Contract (lock path, beacon format): CONTRACT.md in the PR.

Subcommands: tick, notice, run, defer, check, install, status, next
Every function that touches the outside world takes its tools from the
environment (PATH for `openclaw`, `crontab`, `git`, `curl`-free urllib) so the
tests run against stubs and fixtures, never a real box.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCHEMA = "auto-update-beacon/1"
SCHEDULED_WEEKDAYS = (1, 4, 6)          # Monday=0: Tuesday, Friday, Sunday
NOTICE_AT = (2, 15)
START_AT = (2, 30)
CUTOFF_AT = (5, 30)                      # catch-up window for a missed tick
JITTER_SECONDS = 15 * 60
LOCK_WAIT_SECONDS = 30 * 60
CRON_TAG = "# openclaw-auto-update"
OLD_CRON_NAME = "weekly-onboarding-update"
NOTICE_TEXT = ("Heads up: I'll start updating your system in 15 minutes (2:30 AM). "
               "Type cancel if you want to skip this update.")
CANCEL_ACK_TEXT = "OK, I skipped this update. I'll try again at the next scheduled time."
CANCEL_RE = re.compile(r"\bcancel\b", re.IGNORECASE)
RESULTS = ("CURRENT", "UPDATED", "CANCELLED", "DEFERRED", "ROLLED_BACK", "FAILED", "NO_DEEPSEEK")
ALERT_RESULTS = ("ROLLED_BACK", "FAILED", "NO_DEEPSEEK")
SCRIPT_DIR = Path(__file__).resolve().parent
# Files the box must hold under <openclaw root>/scripts for the schedule to work.
DELIVERED = ("auto_update.py", "auto-update-tick.sh", "auto-update-run.sh", "box-update-lock.sh",
             "weekly-full-update.sh", "openclaw-cli-update.sh")


# ---------------------------------------------------------------- paths -----

def oc_root() -> Path:
    env = os.environ.get("OPENCLAW_ROOT", "").strip()
    if env:
        return Path(env)
    if Path("/data/.openclaw").is_dir():
        return Path("/data/.openclaw")
    return Path.home() / ".openclaw"


def skills_dir(root: Path | None = None) -> Path:
    return (root or oc_root()) / "skills"


def state_path(root: Path | None = None) -> Path:
    return skills_dir(root) / ".auto-update-state.json"


def status_path(root: Path | None = None) -> Path:
    return skills_dir(root) / ".auto-update-status.json"


def history_path(root: Path | None = None) -> Path:
    return skills_dir(root) / ".auto-update-history.jsonl"


def cancel_flag_path(root: Path | None = None) -> Path:
    return skills_dir(root) / ".auto-update-cancel"


def log(msg: str) -> None:
    print(f"[auto-update {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}", flush=True)


def now_utc() -> dt.datetime:
    forced = os.environ.get("AUTO_UPDATE_NOW_UTC", "").strip()    # tests only
    if forced:
        return dt.datetime.strptime(forced, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def write_json_atomic(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, p)


def box_id(root: Path | None = None) -> str:
    """Same chain update-skills.sh fleet_standing_resolve_slug uses: env, openclaw.json env.vars, host name."""
    v = os.environ.get("FLEET_STANDING_BOX_SLUG", "").strip()
    if v:
        return v
    cfg = read_json((root or oc_root()) / "openclaw.json", {})
    v = str(((cfg.get("env") or {}).get("vars") or {}).get("FLEET_STANDING_BOX_SLUG") or "").strip()
    if v:
        return v
    return os.uname().nodename.split(".")[0] or "unknown-box"


# ------------------------------------------------- Eastern time, no tzdata ---

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def eastern_offset(utc: dt.datetime) -> dt.timedelta:
    """UTC-4 from 2:00 AM local on the second Sunday of March until 2:00 AM local
    on the first Sunday of November (the US rule since 2007), UTC-5 otherwise."""
    y = utc.year
    start = dt.datetime.combine(_nth_weekday(y, 3, 6, 2), dt.time(7, 0), tzinfo=dt.timezone.utc)   # 2:00 EST
    end = dt.datetime.combine(_nth_weekday(y, 11, 6, 1), dt.time(6, 0), tzinfo=dt.timezone.utc)    # 2:00 EDT
    return dt.timedelta(hours=-4) if start <= utc < end else dt.timedelta(hours=-5)


def to_eastern(utc: dt.datetime) -> dt.datetime:
    """Naive Eastern wall-clock datetime for an aware UTC one."""
    return (utc.astimezone(dt.timezone.utc) + eastern_offset(utc)).replace(tzinfo=None)


def eastern_to_utc(local: dt.datetime) -> dt.datetime:
    """Aware UTC instant of a naive Eastern wall-clock time (the 2 AM hour is unambiguous on
    scheduled days except the fall-back Sunday, where the first occurrence is used)."""
    for off in (dt.timedelta(hours=-4), dt.timedelta(hours=-5)):
        cand = (local - off).replace(tzinfo=dt.timezone.utc)
        if eastern_offset(cand) == off:
            return cand
    return (local - dt.timedelta(hours=-5)).replace(tzinfo=dt.timezone.utc)


def is_scheduled_day(local: dt.datetime) -> bool:
    return local.weekday() in SCHEDULED_WEEKDAYS


def jitter_seconds(box: str, day: str) -> int:
    """Deterministic 0..899 s offset per box and day, so a fleet does not start in the same second."""
    return int(hashlib.sha256(f"{box}|{day}".encode()).hexdigest()[:8], 16) % JITTER_SECONDS


def day_shift(day: dt.date) -> dt.timedelta:
    """One hour on the spring-forward Sunday (2:00 jumps to 3:00, so 2:15 and 2:30 never happen),
    otherwise nothing: the notice, the start and the cutoff all move to the same wall-clock times plus one hour."""
    return dt.timedelta(hours=1) if day == _nth_weekday(day.year, 3, 6, 2) else dt.timedelta(0)


def _at(day: dt.date, hm: tuple) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(*hm)) + day_shift(day)


def run_start_local(box: str, local: dt.datetime) -> dt.datetime:
    return _at(local.date(), START_AT) + dt.timedelta(seconds=jitter_seconds(box, local.date().isoformat()))


def next_runs(utc: dt.datetime, box: str, count: int = 3) -> list[str]:
    out, local = [], to_eastern(utc)
    day = local.date()
    for _ in range(60):
        base = dt.datetime.combine(day, dt.time(*START_AT))
        if base.weekday() in SCHEDULED_WEEKDAYS:
            start = run_start_local(box, base)
            if eastern_to_utc(start) > utc:
                out.append(start.strftime("%Y-%m-%d %I:%M:%S %p Eastern"))
                if len(out) == count:
                    break
        day += dt.timedelta(days=1)
    return out


def decide(local: dt.datetime, box: str, day_state: dict) -> str:
    """What this tick must do. Pure function of the Eastern time and today's state.

    idle           not a scheduled day, or before 2:15, or today is already settled
    notice         send the 2:15 notice
    watch          notice is out, run not due yet: look for a cancel
    run            start the update
    missed_notice  it is past the notice window and no notice went out: do not update unannounced
    missed_run     past the catch-up cutoff and the run never started
    """
    if not is_scheduled_day(local) or day_state.get("settled"):
        return "idle"
    d = local.date()
    if local < _at(d, NOTICE_AT):
        return "idle"
    notice_done = bool(day_state.get("notice", {}).get("attempted"))
    start = run_start_local(box, local)
    if not notice_done:
        if local < _at(d, START_AT):
            return "notice"
        return "missed_notice"
    if local >= _at(d, CUTOFF_AT):
        return "missed_run"
    if local >= start:
        return "run"
    return "watch"


# --------------------------------------------------------------- messaging ---

def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def resolve_owner_chat() -> str:
    """The CLIENT owner chat, operator ids rejected (shared-utils/resolve-owner-chat.sh, which also
    honours OPENCLAW_OWNER_CHAT_ID and rejects an operator id there)."""
    cands = [skills_dir() / "shared-utils" / "resolve-owner-chat.sh",
             SCRIPT_DIR.parent / "shared-utils" / "resolve-owner-chat.sh"]
    for helper in cands:
        if helper.is_file():
            r = _run(["bash", "-c", f'. "{helper}"; resolve_owner_chat_id'])
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip().splitlines()[-1].strip()
    return ""      # nothing resolved: never fall back to a raw env value (the operator id could be in it)


def send_owner_message(text: str) -> tuple[bool, str]:
    """(sent, detail). Only ever the resolved client owner chat; never the operator."""
    chat = resolve_owner_chat()
    if not chat:
        return False, "no client owner chat resolved"
    r = _run(["openclaw", "message", "send", "--channel", "telegram", "--target", chat, "--message", text], 90)
    return (r.returncode == 0), f"openclaw message send rc={r.returncode}"


def _owner_agent_ids(root: Path) -> list[str]:
    direct, catch_all = [], []
    for b in (read_json(root / "openclaw.json", {}).get("bindings") or []):
        m = (b.get("match") or {}) if isinstance(b, dict) else {}
        if m.get("channel") != "telegram" or m.get("accountId") not in (None, "*", "default") or not b.get("agentId"):
            continue
        kind = (m.get("peer") or {}).get("kind")
        (direct if kind == "direct" else catch_all if kind is None else []).append(b["agentId"])
    return list(dict.fromkeys(direct + catch_all + ["main"]))


def owner_session_keys(root: Path) -> list[str]:
    """The owner-facing sessions: Telegram direct sessions of the owner agent, or agent:<id>:main."""
    keys: list[str] = []
    for agent in _owner_agent_ids(root):
        r = _run(["openclaw", "sessions", "list", "--agent", agent, "--json", "--limit", "all"], 90)
        try:
            rows = (json.loads(r.stdout) or {}).get("sessions") or []
        except ValueError:
            rows = []
        dm = re.compile(rf"^agent:{re.escape(agent)}:telegram:(?:[^:]+:)?direct:\d+$")
        found = sorted((x for x in rows if isinstance(x, dict) and x.get("key")
                        and (dm.match(x["key"]) or x["key"] == f"agent:{agent}:main")),
                       key=lambda x: float(x.get("updatedAt") or 0), reverse=True)
        keys += [x["key"] for x in found]
        if keys:
            break
    return list(dict.fromkeys(keys))


def _message_text(msg: dict) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(p.get("text") or "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def cancel_requested(root: Path, since_ms: int) -> bool:
    """True when the owner typed the whole word 'cancel' after the notice.

    Source 1 is the owner session transcript through the gateway (`chat.history`), user
    messages only, newer than the notice. Source 2 is the flag file
    <root>/skills/.auto-update-cancel, newer than the notice (anything may write it)."""
    flag = cancel_flag_path(root)
    try:
        if flag.is_file() and flag.stat().st_mtime * 1000 >= since_ms:
            return True
    except OSError:
        pass
    for key in owner_session_keys(root):
        r = _run(["openclaw", "gateway", "call", "chat.history", "--params",
                  json.dumps({"sessionKey": key, "limit": 60}), "--json"], 60)
        try:
            msgs = (json.loads(r.stdout) or {}).get("messages") or []
        except ValueError:
            continue
        for m in msgs:
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            if float(m.get("timestamp") or 0) < since_ms:
                continue
            if CANCEL_RE.search(_message_text(m)):
                return True
    return False


# ------------------------------------------------------------ versions -------

def parse_version(v) -> tuple | None:
    m = re.match(r"^\s*v?(\d+)\.(\d+)\.(\d+)", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def norm_version(v) -> str | None:
    t = parse_version(v)
    return "v%d.%d.%d" % t if t else None


def is_behind(installed, latest) -> bool | None:
    """True installed < latest, False current/ahead, None when the latest cannot be judged.
    An installed version that cannot be read counts as behind (the update is what repairs it)."""
    lt = parse_version(latest)
    if lt is None:
        return None
    it = parse_version(installed)
    return True if it is None else it < lt


def is_mac() -> bool:
    return (os.environ.get("AUTO_UPDATE_PLATFORM") or sys.platform) == "darwin"


def _first_line(p: Path) -> str:
    try:
        return p.read_text().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def installed_onboarding(root: Path) -> str | None:
    s = skills_dir(root)
    for name in (".onboarding-version", "version", "VERSION"):
        v = norm_version(_first_line(s / name))
        if v:
            return v
    return None


_CC_CANDIDATES = ("projects/command-center", "projects/blackceo-command-center", "projects/mission-control",
                  "blackceo-command-center")


def find_cc_dir(root: Path) -> Path | None:
    for var in ("CC_APP_DIR", "BLACKCEO_COMMAND_CENTER_ROOT"):
        v = os.environ.get(var, "").strip()
        if v and (Path(v).expanduser() / "package.json").is_file():
            return Path(v).expanduser()
    cands = [Path.home() / c for c in _CC_CANDIDATES] + [Path("/data") / c for c in _CC_CANDIDATES[:2]]
    cands.append(root / "command-center")
    for d in cands:
        if (d / "package.json").is_file():
            return d
    return None


def installed_cc(root: Path) -> str | None:
    d = find_cc_dir(root)
    return norm_version(read_json(d / "package.json", {}).get("version")) if d else None


_999_CANDIDATES = ("Documents/999-setup", "Documents/999-setup-main", "Downloads/999-setup",
                   "Downloads/999-setup-main", "999-setup", "999-setup-main", "Desktop/999-setup",
                   "clawd/999-setup", "projects/999-setup", "Projects/999-setup")


def find_999_checkout() -> Path | None:
    home = Path(os.environ.get("AUTO_UPDATE_HOME") or Path.home())
    for c in _999_CANDIDATES:
        d = home / c
        if (d / ".git").exists() and (d / "AGENT_INSTALL.md").is_file():
            return d
    return None


def _git(repo: Path, *args: str) -> str:
    r = _run(["git", "-C", str(repo), *args], 60)
    return r.stdout.strip() if r.returncode == 0 else ""


def installed_999() -> str | None:
    d = find_999_checkout()
    return norm_version(_git(d, "describe", "--tags", "--abbrev=0")) if d else None


def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-box-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def pinned_ref(root: Path) -> str:
    """The approved release ref when a pin is configured (tag or 40-hex), else main."""
    ref = os.environ.get("OPENCLAW_APPROVED_RELEASE", "").strip() or \
        str(read_json(root / "fleet-refresh" / "release-pin.json", {}).get("approved_ref") or "").strip()
    return ref if re.fullmatch(r"[A-Za-z0-9._-]+", ref or "") and ref not in ("main", "master", "HEAD") else "main"


def latest_onboarding(ref: str) -> str | None:
    base = f"https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/{ref}"
    return norm_version(_first_line_text(http_get(f"{base}/VERSION")))


def _first_line_text(s: str) -> str:
    s = (s or "").strip()
    return s.splitlines()[0].strip() if s else ""


def latest_cc(ref: str) -> str | None:
    """The Command Center release the onboarding release pins (cc-compat.json), which is what the
    fleet roll deploys; falls back to the Command Center main package.json version."""
    try:
        pin = (json.loads(http_get(f"https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/{ref}/cc-compat.json"))
               .get("commandCenter") or {}).get("pinnedTag")
        if norm_version(pin):
            return norm_version(pin)
    except (OSError, ValueError, urllib.error.URLError):
        pass
    pkg = json.loads(http_get("https://raw.githubusercontent.com/trevorotts1/blackceo-command-center/main/package.json"))
    return norm_version(pkg.get("version"))


def latest_999() -> str | None:
    r = _run(["git", "ls-remote", "--tags", "--refs", "https://github.com/trevorotts1/999-setup.git"], 60)
    tags = [parse_version(line.rsplit("/", 1)[-1]) for line in r.stdout.splitlines()]
    tags = [t for t in tags if t]
    return "v%d.%d.%d" % max(tags) if tags else None


def check_versions(root: Path) -> dict:
    """{repo: {installed, latest, behind}} for onboarding, command_center and (macOS only) 999."""
    ref = pinned_ref(root)
    rows = {"onboarding": {"installed": installed_onboarding(root), "fetch": lambda: latest_onboarding(ref)},
            "command_center": {"installed": installed_cc(root), "fetch": lambda: latest_cc(ref)}}
    if is_mac():
        rows["999"] = {"installed": installed_999(), "fetch": latest_999}
    fixture = os.environ.get("AUTO_UPDATE_LATEST_JSON", "").strip()    # tests only: latest versions from a file
    if fixture:
        fx = read_json(Path(fixture), {})
        for name, row in rows.items():
            row["fetch"] = (lambda n=name: norm_version(fx.get(n)) if fx.get(n) else (_ for _ in ()).throw(OSError("fixture")))
    out = {}
    for name, row in rows.items():
        if name == "999" and find_999_checkout() is None:
            continue                      # 999 is only ever refreshed where it is already installed
        if name == "command_center" and find_cc_dir(root) is None:
            continue                      # no Command Center on this box: nothing to update
        try:
            latest = row["fetch"]()
        except (OSError, ValueError, urllib.error.URLError, KeyError) as e:
            latest, err = None, f"{type(e).__name__}"
        else:
            err = None
        out[name] = {"installed": row["installed"], "latest": latest,
                     "behind": is_behind(row["installed"], latest), "error": err}
    return out


# --------------------------------------------------------------- beacon ------

def build_beacon(root: Path, result: str, versions_before: dict, versions_after: dict, *, run_id: str,
                 day: str, failing: str | None = None, model: str | None = None, notice_sent: bool = False) -> dict:
    assert result in RESULTS, result
    vers = {}
    for n in ("onboarding", "command_center", "999"):
        if n == "999" and not (is_mac() and "999" in versions_before):
            vers[n] = None          # never on Linux/VPS/Contabo, and not on a Mac without a 999-setup checkout
            continue
        vers[n] = {"before": versions_before.get(n), "after": versions_after.get(n, versions_before.get(n))}
    return {"schema": SCHEMA, "box": box_id(root), "run_at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scheduled_day": day, "result": result, "versions": vers, "failing_check": failing,
            "model_used": model, "notice_sent": bool(notice_sent), "run_id": run_id}


def beacon_url() -> tuple[str, str, str]:
    cfg = read_json(oc_root() / "openclaw.json", {})
    envv = (cfg.get("env") or {}).get("vars") or {}
    get = lambda k: os.environ.get(k) or str(envv.get(k) or "")
    url = get("FLEET_AUTO_UPDATE_BEACON_URL")
    gate = get("FLEET_STANDING_GATE_URL").rstrip("/")
    if not url and gate.endswith("/fleet-standing-check"):
        url = gate[: -len("fleet-standing-check")] + "fleet-update-beacon"
    return url, get("FLEET_STANDING_GATE_HEADER") or "X-Fleet-Standing-Secret", get("FLEET_STANDING_GATE_SECRET")


def installed_snapshot(root: Path) -> dict:
    snap = {"onboarding": installed_onboarding(root), "command_center": installed_cc(root)}
    if is_mac() and find_999_checkout() is not None:
        snap["999"] = installed_999()
    return snap


def emit_beacon(root: Path, beacon: dict) -> dict:
    """Local file first (always), then the operator collection point. Returns delivery facts."""
    write_json_atomic(status_path(root), beacon)
    hp = history_path(root)
    lines = []
    try:
        lines = hp.read_text().splitlines()[-199:]
    except OSError:
        pass
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text("\n".join(lines + [json.dumps(beacon, sort_keys=True)]) + "\n")
    delivered, alerted = False, False
    url, header, secret = beacon_url()
    if url and secret:
        req = urllib.request.Request(url, data=json.dumps(beacon).encode(), method="POST",
                                     headers={"Content-Type": "application/json", header: secret})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                delivered = 200 <= r.status < 300
        except (OSError, urllib.error.URLError):
            delivered = False
    if beacon["result"] in ALERT_RESULTS:
        alerted = _alert_operator(beacon)
    log(f"beacon {beacon['result']} written; collection point {'ok' if delivered else 'not reached'}")
    return {"delivered": delivered, "alerted": alerted}


def _alert_operator(beacon: dict) -> bool:
    try:
        sys.path.insert(0, str(skills_dir() / "shared-utils"))
        sys.path.insert(0, str(SCRIPT_DIR.parent / "shared-utils"))
        import fleet_notify  # type: ignore
        text = (f"Auto-update {beacon['result']} on box {beacon['box']}: "
                f"{beacon.get('failing_check') or 'see status file'} (model {beacon.get('model_used') or 'none'})")
        return bool(fleet_notify.send_telegram(fleet_notify.scrub(text))[0])
    except Exception:       # an alert that cannot be sent never blocks the beacon
        return False


# ------------------------------------------------------------------ run ------

def latest_summary(since: float) -> dict | None:
    """The fleet-refresh summary written by THIS run (newest summary.json after `since`)."""
    best, best_t = None, since
    for base in {Path.home() / ".openclaw" / "fleet" / "runs", oc_root() / "fleet" / "runs"}:
        for p in base.glob("*/summary.json") if base.is_dir() else []:
            try:
                t = p.stat().st_mtime
            except OSError:
                continue
            if t >= best_t:
                best, best_t = p, t
    rows = read_json(best, []) if best else []
    return rows[0] if isinstance(rows, list) and rows else None


def update_command(root: Path) -> list[str]:
    local = root / "scripts" / "weekly-full-update.sh"
    if local.is_file():
        return ["bash", str(local)]
    return ["bash", str(SCRIPT_DIR / "weekly-full-update.sh")]


def run_update(root: Path, day: str, run_id: str, notice_sent: bool) -> dict:
    """The locked part of a run. The caller (auto-update-run.sh) already holds the shared lease."""
    versions = check_versions(root)
    before = {k: v["installed"] for k, v in versions.items()}
    unreadable = [k for k, v in versions.items() if v["behind"] is None]
    if unreadable:
        return build_beacon(root, "DEFERRED", before, before, run_id=run_id, day=day, notice_sent=notice_sent,
                            failing=f"could not read the latest {', '.join(sorted(unreadable))} version")
    behind = sorted(k for k, v in versions.items() if v["behind"])
    if not behind:
        return build_beacon(root, "CURRENT", before, before, run_id=run_id, day=day, notice_sent=notice_sent)
    log(f"behind: {', '.join(behind)}; running the update")
    env = dict(os.environ, AUTO_UPDATE="1", AUTO_UPDATE_BEHIND=",".join(behind), AUTO_UPDATE_OPENCLAW="1",
               AUTO_UPDATE_REPAIR="1", AUTO_UPDATE_RUN_ID=run_id)
    t0 = time.time()
    try:
        rc = subprocess.run(update_command(root), env=env, timeout=7200).returncode
    except (OSError, subprocess.SubprocessError) as e:
        rc = 127
        log(f"update could not run: {type(e).__name__}")
    after = installed_snapshot(root)
    row = latest_summary(t0 - 5) or {}
    outcome = str(row.get("outcome") or "")
    repair = (row.get("heal") or {}).get("repair_agent") or {}
    model = repair.get("model") or None
    failing = None
    regress = (row.get("health") or {}).get("regressions") or []
    if regress:
        failing = ", ".join(regress)[:200]
    if rc == 78 and not outcome:
        result, failing = "DEFERRED", "the release-pin gate refused this run (no approved release identity); nothing changed"
    elif rc == 75 or outcome == "SKIPPED":
        result, failing = "DEFERRED", (row.get("outcome_detail") or "another updater owns this box")[:200]
    elif outcome == "UPDATED" or (not outcome and rc == 0 and all(
            not is_behind(after.get(k), versions[k]["latest"]) for k in behind if k in after)):
        result = "UPDATED"
    elif outcome == "ROLLED_BACK":
        result = "ROLLED_BACK"
    else:
        result = "FAILED"
        failing = failing or (row.get("outcome_detail") or f"update exited {rc}")[:200]
    if result in ("ROLLED_BACK", "FAILED") and repair.get("no_model"):
        result = "NO_DEEPSEEK"
        failing = failing or (row.get("outcome_detail") or "")[:200]
    return build_beacon(root, result, before, after, run_id=run_id, day=day, failing=failing, model=model,
                        notice_sent=notice_sent)


# ----------------------------------------------------------------- tick ------

def _state(root: Path, day: str) -> dict:
    st = read_json(state_path(root), {})
    return st if st.get("day") == day else {"day": day}


def tick(root: Path | None = None) -> str:
    """One cron tick. Returns the action taken (for the log and the tests)."""
    root = root or oc_root()
    skills_dir(root).mkdir(parents=True, exist_ok=True)
    guard = open(skills_dir(root) / ".auto-update-tick.flock", "a+")
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        guard.close()
        return "busy"                      # another tick (or a run) holds the box's auto-update guard
    try:
        return _tick_locked(root)
    finally:
        guard.close()                      # closing releases the flock


def _tick_locked(root: Path) -> str:
    utc = now_utc()
    local = to_eastern(utc)
    day = local.date().isoformat()
    box = box_id(root)
    st = _state(root, day)
    act = decide(local, box, st)
    if act == "idle":
        return "idle"
    if act == "notice":
        sent, detail = send_owner_message(NOTICE_TEXT)
        st["notice"] = {"attempted": True, "sent": sent, "detail": detail, "at_ms": int(utc.timestamp() * 1000)}
        write_json_atomic(state_path(root), st)
        log(f"notice {'sent' if sent else 'NOT sent (' + detail + ')'}")
        return "notice"
    if act in ("watch", "run"):
        since = int(st.get("notice", {}).get("at_ms") or 0)
        if not st.get("cancel") and cancel_requested(root, since):
            ok, _ = send_owner_message(CANCEL_ACK_TEXT)
            st["cancel"] = {"acked": ok, "at_ms": int(utc.timestamp() * 1000)}
            st["settled"] = "CANCELLED"
            write_json_atomic(state_path(root), st)
            snap = installed_snapshot(root)
            emit_beacon(root, build_beacon(root, "CANCELLED", snap, snap, run_id=f"auto-update-{utc:%Y%m%dT%H%M%SZ}-{os.getpid()}",
                                           day=day, notice_sent=bool(st.get("notice", {}).get("sent"))))
            return "cancelled"
        if act == "watch":
            return "watch"
        st["settled"] = "RUNNING"
        write_json_atomic(state_path(root), st)
        run_id = f"auto-update-{utc:%Y%m%dT%H%M%SZ}-{os.getpid()}"
        runner = root / "scripts" / "auto-update-run.sh"
        if not runner.is_file():
            runner = SCRIPT_DIR / "auto-update-run.sh"
        env = dict(os.environ, AUTO_UPDATE_RUN_ID=run_id, AUTO_UPDATE_DAY=day,
                   AUTO_UPDATE_NOTICE_SENT="1" if st.get("notice", {}).get("sent") else "0")
        rc = subprocess.run(["bash", str(runner)], env=env).returncode
        st["settled"] = "DONE"
        st["run_rc"] = rc
        write_json_atomic(state_path(root), st)
        return "run"
    reason = "missed notice window" if act == "missed_notice" else "missed run window"
    st["settled"] = "MISSED"
    write_json_atomic(state_path(root), st)
    before = installed_snapshot(root)
    emit_beacon(root, build_beacon(root, "DEFERRED", before, before, run_id=f"auto-update-{utc:%Y%m%dT%H%M%SZ}-{os.getpid()}",
                                   day=day, failing=reason, notice_sent=bool(st.get("notice", {}).get("sent"))))
    return act


# -------------------------------------------------------------- install ------

OLD_CRON_PATTERNS = (re.compile(r"update-restart-if-needed"), re.compile(r"\.openclaw-self-update"))


def cron_lines(raw: str) -> list[str]:
    return [l for l in raw.splitlines()]


def desired_crontab(current: str, root: Path) -> str:
    keep = [l for l in cron_lines(current)
            if not any(p.search(l) for p in OLD_CRON_PATTERNS) and CRON_TAG not in l]
    entry = f"*/5 * * * * /bin/bash '{root}/scripts/auto-update-tick.sh' {CRON_TAG}"
    return "\n".join(keep + [entry]) + "\n"


def _crontab_bin() -> str:
    return os.environ.get("AUTO_UPDATE_CRONTAB", "crontab")


def ensure_scripts(root: Path, src: Path) -> list[str]:
    """Copy the runtime files into <root>/scripts when they are missing or differ (idempotent)."""
    changed = []
    dst = root / "scripts"
    dst.mkdir(parents=True, exist_ok=True)
    for name in DELIVERED:
        s, d = src / name, dst / name
        if not s.is_file() or (s.resolve() == d.resolve() if d.exists() else False):
            continue
        if not d.is_file() or d.read_bytes() != s.read_bytes():
            shutil.copy2(s, d)
            changed.append(name)
        if not os.access(d, os.X_OK):
            d.chmod(0o755)
    return changed


def retire_cron_jobs() -> list[str]:
    """Remove every openclaw cron job named weekly-onboarding-update (the old agent 'ask first' job and
    the 2:00 AM command job). Returns the ids removed. Unreadable list = nothing removed, retried next time."""
    r = _run(["openclaw", "cron", "list", "--json"], 60)
    if r.returncode != 0:
        return []
    raw = r.stdout
    try:
        i = min([x for x in (raw.find("{"), raw.find("[")) if x >= 0] or [0])
        data = json.loads(raw[i:])
    except ValueError:
        return []
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    ids = [j["id"] for j in jobs if isinstance(j, dict) and j.get("name") == OLD_CRON_NAME and j.get("id")]
    removed = []
    for jid in ids:
        for _ in range(int(os.environ.get("AUTO_UPDATE_RM_TRIES", "3"))):
            if _run(["openclaw", "cron", "rm", str(jid)], 60).returncode == 0:
                removed.append(str(jid))
                break
            time.sleep(float(os.environ.get("AUTO_UPDATE_RM_DELAY", "5")))
    return removed


TICK_JOB_NAME = "auto-update-tick"


def _cron_jobs() -> list[dict] | None:
    r = _run(["openclaw", "cron", "list", "--json"], 60)
    if r.returncode != 0:
        return None
    raw = r.stdout
    try:
        i = min([x for x in (raw.find("{"), raw.find("[")) if x >= 0] or [0])
        data = json.loads(raw[i:])
    except ValueError:
        return None
    return [j for j in (data if isinstance(data, list) else data.get("jobs", [])) if isinstance(j, dict)]


def ensure_openclaw_tick_job(root: Path, dry_run: bool = False) -> str:
    """'present' | 'created' | 'unavailable'. Idempotent: an existing job with the same command is left alone."""
    cmd = f"/bin/bash '{root}/scripts/auto-update-tick.sh'"
    jobs = _cron_jobs()
    if jobs is None:
        return "unavailable"
    for j in jobs:
        if j.get("name") == TICK_JOB_NAME and (j.get("payload") or {}).get("argv") == ["sh", "-lc", cmd] \
                and j.get("enabled", True) is not False:
            return "present"
    if dry_run:
        return "created"
    r = _run(["openclaw", "cron", "add", "--name", TICK_JOB_NAME, "--cron", "*/5 * * * *", "--tz", "America/New_York",
              "--exact", "--description", "Tue/Fri/Sun auto-update tick (silent; keeps its own Eastern clock)",
              "--command", cmd, "--timeout-seconds", "7200", "--no-deliver"], 90)
    return "created" if r.returncode == 0 else "unavailable"


def install(root: Path | None = None, src: Path | None = None, dry_run: bool = False) -> dict:
    """Idempotent: retire the old schedule, install the new one exactly once. A second call changes nothing."""
    root = root or oc_root()
    src = src or SCRIPT_DIR
    res = {"scripts_changed": [], "crontab_changed": False, "old_files_removed": [], "cron_jobs_removed": []}
    if not dry_run:
        res["scripts_changed"] = ensure_scripts(root, src)
    if shutil.which(_crontab_bin()) is None:
        # Containers without cron: the same tick runs as an OpenClaw command job instead (every 5 minutes).
        res["scheduler"] = "openclaw-cron"
        res["tick_job"] = ensure_openclaw_tick_job(root, dry_run)
        current, want = "", ""
    else:
        res["scheduler"] = "crontab"
        cur = _run([_crontab_bin(), "-l"], 30)
        current = cur.stdout if cur.returncode == 0 else ""
        want = desired_crontab(current, root)
    if want.strip() != current.strip():
        res["crontab_changed"] = True
        if not dry_run:
            bak = skills_dir(root) / f".crontab.bak-auto-update-{now_utc():%Y%m%d-%H%M%S}"
            try:
                bak.parent.mkdir(parents=True, exist_ok=True)
                bak.write_text(current)
                res["crontab_backup"] = str(bak)
            except OSError:
                pass
            p = subprocess.run([_crontab_bin(), "-"], input=want, text=True, capture_output=True)
            if p.returncode != 0:
                res["error"] = "crontab install failed"
                res["crontab_changed"] = False
    for old in (".update-restart-if-needed", ".openclaw-self-update"):
        f = skills_dir(root) / old
        if f.exists():
            res["old_files_removed"].append(old)
            if not dry_run:
                f.unlink()
    if not dry_run:
        res["cron_jobs_removed"] = retire_cron_jobs()
    return res


# ------------------------------------------------------------------ cli ------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="auto_update.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tick")
    sub.add_parser("run", help="locked run body (called by auto-update-run.sh)")
    sub.add_parser("defer", help="record DEFERRED because the lock stayed busy")
    sub.add_parser("check")
    sub.add_parser("status")
    sub.add_parser("next")
    pi = sub.add_parser("install")
    pi.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    root = oc_root()
    run_id = os.environ.get("AUTO_UPDATE_RUN_ID") or f"auto-update-{now_utc():%Y%m%dT%H%M%SZ}-{os.getpid()}"
    day = os.environ.get("AUTO_UPDATE_DAY") or to_eastern(now_utc()).date().isoformat()
    notice_sent = os.environ.get("AUTO_UPDATE_NOTICE_SENT") == "1"
    if a.cmd == "tick":
        print(tick(root))
    elif a.cmd == "run":
        emit_beacon(root, run_update(root, day, run_id, notice_sent))
    elif a.cmd == "defer":
        before = installed_snapshot(root)
        emit_beacon(root, build_beacon(root, "DEFERRED", before, before, run_id=run_id, day=day, notice_sent=notice_sent,
                                       failing="another updater held the box lock for 30 minutes"))
    elif a.cmd == "check":
        print(json.dumps(check_versions(root), indent=2))
    elif a.cmd == "status":
        print(json.dumps(read_json(status_path(root), {}), indent=2))
    elif a.cmd == "next":
        print("\n".join(next_runs(now_utc(), box_id(root))))
    elif a.cmd == "install":
        print(json.dumps(install(root, dry_run=a.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
