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


def notice_text(day: dt.date) -> str:
    """The exact client notice. On the spring-forward Sunday the start really is 3:30 AM, so the text says so."""
    shown = "3:30 AM" if day_shift(day) else "2:30 AM"
    return NOTICE_TEXT.replace("(2:30 AM)", f"({shown})")


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
    n = day_state.get("notice", {})
    # Noticed = it was sent, or this box has no owner chat to send to. A failed send to a chat that WAS found
    # is retried every tick until 2:30 and otherwise means no unannounced update.
    notice_done = bool(n.get("attempted")) and (bool(n.get("sent")) or not n.get("chat_found", True))
    start = run_start_local(box, local)
    at_ms = day_state.get("notice", {}).get("at_ms")
    if at_ms:
        # The notice promises "in 15 minutes": a notice that went out late pushes the start later, never earlier.
        sent_local = to_eastern(dt.datetime.fromtimestamp(float(at_ms) / 1000, tz=dt.timezone.utc))
        start = max(start, sent_local + dt.timedelta(minutes=15))
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
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timeout")
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
    if r.returncode == 124:
        # The send may well have been delivered: count it as sent so it is never repeated (no duplicate notices).
        return True, "openclaw message send timed out (delivery unknown; not resent)"
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


def owner_session_keys(root: Path, chat: str = "") -> list[str]:
    """Sessions whose messages may cancel. Every candidate agent is searched (a direct-peer binding that routes
    someone else to another agent never hides the owner's agent). First choice: the owner's own Telegram DM
    session (peer id == the chat the notice went to). When no per-peer session matches the owner, fall back to
    the collapsed agent:<id>:main sessions, where the owner's DMs land under dmScope main."""
    owner_dms: list[str] = []
    mains: list[str] = []
    for agent in _owner_agent_ids(root):
        r = _run(["openclaw", "sessions", "list", "--agent", agent, "--json", "--limit", "all"], 90)
        try:
            rows = (json.loads(r.stdout) or {}).get("sessions") or []
        except ValueError:
            rows = []
        dm = re.compile(rf"^agent:{re.escape(agent)}:telegram:(?:[^:]+:)?direct:(\d+)$")
        found = sorted((x for x in rows if isinstance(x, dict) and x.get("key")),
                       key=lambda x: float(x.get("updatedAt") or 0), reverse=True)
        for x in found:
            m = dm.match(x["key"])
            if m and chat and m.group(1) == chat:
                owner_dms.append(x["key"])
            elif x["key"] == f"agent:{agent}:main":
                mains.append(x["key"])
    return list(dict.fromkeys(owner_dms or mains))


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
    for key in owner_session_keys(root, resolve_owner_chat()):
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


_999_CANDIDATES = ("999-setup", "Documents/999-setup")     # the same search auto-update-mac.sh does


def find_999_checkout() -> Path | None:
    """The 999-setup git checkout, only where it is already installed (never installed here)."""
    home = Path(os.environ.get("AUTO_UPDATE_HOME") or Path.home())
    cands = []
    env = os.environ.get("NINE_999_CHECKOUT", "").strip()
    if env:
        cands.append(Path(env).expanduser())
    cands += [home / c for c in _999_CANDIDATES]
    for d in cands:
        if (d / ".git").exists() and (d / "VERSION").is_file():
            return d
    return None


def installed_999() -> str | None:
    """The checkout's own VERSION file is the source of truth (the repo's tags lag it)."""
    d = find_999_checkout()
    return norm_version(_first_line(d / "VERSION")) if d else None


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
    """VERSION on 999-setup main (the same file the checkout's VERSION is compared with)."""
    return norm_version(_first_line_text(http_get("https://raw.githubusercontent.com/trevorotts1/999-setup/main/VERSION")))


def installed_openclaw() -> str | None:
    r = _run(["openclaw", "--version"], 30)
    m = re.search(r"(\d{4}\.\d+\.\d+)", r.stdout if r.returncode == 0 else "")
    return norm_version(m.group(1)) if m else None


def latest_openclaw() -> str | None:
    """What npm publishes as openclaw latest (oc-atomic-upgrade.sh still applies any pin on its own)."""
    r = _run(["npm", "view", "openclaw", "version"], 40)
    return norm_version(r.stdout.strip()) if r.returncode == 0 else None


def in_container() -> bool:
    """The same markers oc-atomic-upgrade.sh _running_in_container uses (it refuses, exit 79, in a container)."""
    if any(os.path.exists(m) for m in ("/.dockerenv", "/.containerenv", "/run/.containerenv")):
        return True
    try:
        return bool(re.search(r"docker|kubepods|containerd|libpod", Path("/proc/1/cgroup").read_text()))
    except OSError:
        return False


def npm_pin(root: Path) -> str | None:
    v = os.environ.get("OPENCLAW_APPROVED_NPM_VERSION", "").strip() or \
        str(read_json(root / "fleet-refresh" / "release-pin.json", {}).get("approved_npm_version") or "").strip()
    return norm_version(v)


def openclaw_blocked_reason(root: Path) -> str:
    """Why the OpenClaw CLI upgrade cannot run on this box right now ('' = it can). OpenClaw counts as behind
    only where the upgrade can actually run, so a blocked box does not get a full update every scheduled day."""
    if in_container():
        return "container: the atomic upgrade tool refuses to run in a container (host-managed)"
    marker = skills_dir(root) / ".openclaw-upgrade-blocked"
    if marker.exists():
        return "blocked by the pre-upgrade gate (see skills/.openclaw-upgrade-blocked)"
    cfg = read_json(root / "openclaw.json", {})
    agents = cfg.get("agents") or {}
    if isinstance(agents, dict) and "list" in agents and "entries" not in agents \
            and not (root / "scripts" / "oc-atomic-upgrade.sh").is_file():
        return "legacy agents.list config and the atomic upgrade tool is not on this box"
    return ""


def check_versions(root: Path) -> dict:
    """{repo: {installed, latest, behind}} for onboarding, command_center and (macOS only) 999."""
    ref = pinned_ref(root)
    rows = {"onboarding": {"installed": installed_onboarding(root), "fetch": lambda: latest_onboarding(ref)},
            "command_center": {"installed": installed_cc(root), "fetch": lambda: latest_cc(ref)}}
    if is_mac():
        rows["999"] = {"installed": installed_999(), "fetch": latest_999}
    rows["openclaw"] = {"installed": installed_openclaw(), "fetch": latest_openclaw}
    fixture = os.environ.get("AUTO_UPDATE_LATEST_JSON", "").strip()    # tests only: latest versions from a file
    if fixture:
        fx = read_json(Path(fixture), {})
        for name, row in rows.items():
            row["fetch"] = (lambda n=name: norm_version(fx.get(n)) if fx.get(n) else (_ for _ in ()).throw(OSError("fixture")))
    pinned_npm = npm_pin(root)
    if pinned_npm:                           # an approved npm version is the target, not npm latest
        rows["openclaw"]["fetch"] = lambda: pinned_npm
    out = {}
    for name, row in rows.items():
        if name == "999" and find_999_checkout() is None:
            continue                      # 999 is only ever refreshed where it is already installed
        if name == "command_center" and find_cc_dir(root) is None:
            continue                      # no Command Center on this box: nothing to update
        if name == "openclaw" and row["installed"] is None:
            continue                      # no openclaw CLI to update
        try:
            latest = row["fetch"]()
        except (OSError, ValueError, urllib.error.URLError, KeyError) as e:
            latest, err = None, f"{type(e).__name__}"
        else:
            err = None
        out[name] = {"installed": row["installed"], "latest": latest,
                     "behind": is_behind(row["installed"], latest), "error": err}
        if name == "openclaw":
            blocked = openclaw_blocked_reason(root)
            if blocked:
                out[name]["blocked"] = blocked
                out[name]["behind"] = False
    return out


# --------------------------------------------------------------- beacon ------

def build_beacon(root: Path, result: str, versions_before: dict, versions_after: dict, *, run_id: str,
                 day: str, failing: str | None = None, model: str | None = None, notice_sent: bool = False,
                 openclaw_blocked: str = "") -> dict:
    assert result in RESULTS, result
    vers = {}
    vers["openclaw"] = {"before": versions_before.get("openclaw"), "after": versions_after.get("openclaw", versions_before.get("openclaw"))}

    for n in ("onboarding", "command_center", "999"):
        if n == "999" and not is_mac():
            vers[n] = None          # never on Linux/VPS/Contabo
            continue
        if n == "999" and "999" not in versions_before:
            vers[n] = {"before": None, "after": None, "status": "NOT_INSTALLED"}    # a Mac without 999-setup: not a failure
            continue
        vers[n] = {"before": versions_before.get(n), "after": versions_after.get(n, versions_before.get(n))}
    extra = {"openclaw_upgrade": "blocked", "openclaw_upgrade_reason": openclaw_blocked} if openclaw_blocked else {}
    return {**extra, "schema": SCHEMA, "scheduler": read_json(install_path(root), {}).get("scheduler"), "box": box_id(root), "run_at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    snap = {"onboarding": installed_onboarding(root), "command_center": installed_cc(root), "openclaw": installed_openclaw()}
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
    # The OpenClaw CLI is judged on its own: an unreadable npm answer never blocks the repos.
    unreadable = [k for k, v in versions.items() if v["behind"] is None and k != "openclaw"]
    if unreadable:
        return build_beacon(root, "DEFERRED", before, before, run_id=run_id, day=day, notice_sent=notice_sent,
                            failing=f"could not read the latest {', '.join(sorted(unreadable))} version")
    behind = sorted(k for k, v in versions.items() if v["behind"])
    oc_blocked = (versions.get("openclaw") or {}).get("blocked", "")
    if not behind:
        return build_beacon(root, "CURRENT", before, before, run_id=run_id, day=day, notice_sent=notice_sent,
                            openclaw_blocked=oc_blocked)
    log(f"behind: {', '.join(behind)}; running the update")
    cc_file = skills_dir(root) / f".cc-update-result-{os.getpid()}.json"
    cc_file.unlink(missing_ok=True)
    env = dict(os.environ, CC_UPDATE_RESULT_FILE=str(cc_file), AUTO_UPDATE="1", AUTO_UPDATE_BEHIND=",".join(behind),
               AUTO_UPDATE_OPENCLAW="1" if "openclaw" in behind else "0",
               AUTO_UPDATE_REPAIR="1", AUTO_UPDATE_RUN_ID=run_id)
    t0 = time.time()
    try:
        rc = subprocess.run(update_command(root), env=env, timeout=7200).returncode
    except (OSError, subprocess.SubprocessError) as e:
        rc = 127
        log(f"update could not run: {type(e).__name__}")
    after = installed_snapshot(root)
    row = latest_summary(t0 - 5) or {}
    cc = read_json(cc_file, {})                 # Command Center update.sh result (schema cc-update-result/1)
    cc_file.unlink(missing_ok=True)
    cc_status = str(cc.get("status") or "")
    if cc.get("before") or cc.get("after"):
        for k, side in (("before", before), ("after", after)):
            v = norm_version((cc.get(k) or {}).get("version") if isinstance(cc.get(k), dict) else cc.get(k))
            if v:
                side["command_center"] = v
    nine = row.get("update_999") or {}
    if nine.get("before") or nine.get("after"):            # from the AUTO-UPDATE-999 result line
        if "999" in before and norm_version(nine.get("before")):
            before["999"] = norm_version(nine["before"])
        if "999" in before and norm_version(nine.get("after")):
            after["999"] = norm_version(nine["after"])
    outcome = str(row.get("outcome") or "")
    steps = row.get("steps") or {}
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
    elif outcome == "PENDING":
        # a container's gateway restart was handed to the host: updated, restart pending (CONTRACT.md section 9)
        result, failing = "UPDATED", "restart-pending: the host restarts this container's gateway"
    else:
        result = "FAILED"
        failing = failing or (row.get("outcome_detail") or f"update exited {rc}")[:200]
    if result == "UPDATED" and cc_status == "FAILED":
        result, failing = "FAILED", failing or "Command Center update reported FAILED"
    elif result == "UPDATED" and cc_status == "DEFERRED":
        result, failing = "DEFERRED", "Command Center update deferred (box lock busy)"
    if result == "UPDATED" and behind == ["openclaw"] and str(steps.get("openclaw-update", "")).startswith("skip:"):
        # only the CLI was behind and its upgrade refused: nothing changed, so it is not an update
        result = "CURRENT"
        oc_blocked = oc_blocked or str(steps["openclaw-update"])[5:160]
    if result == "UPDATED":
        s999, soc = str(steps.get("update-999", "")), str(steps.get("openclaw-update", ""))
        if s999.startswith("failed"):
            result, failing = "FAILED", f"999 update failed: {s999[7:150]}"
        elif s999.startswith("skip:DEFERRED"):
            result, failing = "DEFERRED", "999 update deferred (box lock busy); onboarding and Command Center updated"
        elif "999" in after and "999" in versions and is_behind(after.get("999"), versions["999"]["latest"]) \
                and not s999.startswith("skip:"):
            result, failing = "FAILED", "999 is still behind after the update"
        elif soc.startswith("failed"):
            result, failing = "FAILED", f"OpenClaw CLI update failed: {soc[7:150]}"
    if result in ("ROLLED_BACK", "FAILED") and repair.get("no_model"):
        result = "NO_DEEPSEEK"
        failing = failing or (row.get("outcome_detail") or "")[:200]
    return build_beacon(root, result, before, after, run_id=run_id, day=day, failing=failing, model=model,
                        notice_sent=notice_sent, openclaw_blocked=oc_blocked)


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
        (skills_dir(root) / ".auto-update-heartbeat").write_text(str(int(now_utc().timestamp() * 1000)) + "\n")
        finish_migration(root)             # proves the new schedule fires, then (and only then) retires the old jobs
        return _tick_locked(root)
    finally:
        guard.close()                      # closing releases the flock


def _tick_locked(root: Path) -> str:
    utc = now_utc()
    local = to_eastern(utc)
    day = local.date().isoformat()
    box = box_id(root)
    st = _state(root, day)
    if st.get("settled") == "RUNNING":
        # A previous tick died mid-run (the flock is free, so nobody is running): say so, never re-run silently.
        st["settled"] = "CRASHED"
        write_json_atomic(state_path(root), st)
        snap = installed_snapshot(root)
        emit_beacon(root, build_beacon(root, "FAILED", snap, snap, run_id=f"auto-update-{utc:%Y%m%dT%H%M%SZ}-{os.getpid()}",
                                       day=day, failing="the update run did not finish (the process ended mid-run)",
                                       notice_sent=bool(st.get("notice", {}).get("sent"))))
        return "crashed"
    act = decide(local, box, st)
    if act == "idle":
        return "idle"
    if act == "notice":
        sent, detail = send_owner_message(notice_text(local.date()))
        now_ms = int(utc.timestamp() * 1000)
        prev_n = st.get("notice") or {}
        # first_ms: when the first attempt began (a cancel typed after it counts, even if a retry delivered later);
        # at_ms: when the notice actually went out (the 15 minutes run from it).
        st["notice"] = {"attempted": True, "sent": sent, "detail": detail,
                        "chat_found": detail != "no client owner chat resolved",
                        "first_ms": prev_n.get("first_ms") or now_ms, "at_ms": now_ms}
        write_json_atomic(state_path(root), st)
        log(f"notice {'sent' if sent else 'NOT sent (' + detail + ')'}")
        return "notice"
    if act in ("watch", "run"):
        since = int(st.get("notice", {}).get("first_ms") or st.get("notice", {}).get("at_ms") or 0)
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
    migration = False
    if act == "missed_notice" and st.get("notice", {}).get("attempted"):
        reason = "notice-undeliverable"      # CONTRACT.md section 10: the 6 AM report surfaces this box
    elif act == "missed_notice":
        reason = "missed notice window"
        meta = read_json(install_path(root), {})
        installed_at = meta.get("installed_at_ms") or 0
        if meta.get("migration_day") == day and \
                installed_at >= int(eastern_to_utc(_at(local.date(), NOTICE_AT)).timestamp() * 1000):
            # The schedule was installed after today's notice window (the last run of the old Sunday path
            # installed it): nothing was missed by a working schedule.
            migration = True
            reason = "MIGRATION: schedule installed after today's notice window; the old path already ran today"
    else:
        reason = "missed run window"
    st["settled"] = "MISSED"
    write_json_atomic(state_path(root), st)
    before = installed_snapshot(root)
    b = build_beacon(root, "DEFERRED", before, before, run_id=f"auto-update-{utc:%Y%m%dT%H%M%SZ}-{os.getpid()}",
                     day=day, failing=reason, notice_sent=bool(st.get("notice", {}).get("sent")))
    if migration:
        b["migration"] = True
    emit_beacon(root, b)
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


def install_path(root: Path | None = None) -> Path:
    return skills_dir(root) / ".auto-update-install.json"


def cron_daemon_running() -> bool:
    """Whether a cron daemon will actually fire a crontab line. macOS cron is launchd-managed, so the crontab
    command is enough there. On Linux the crontab BINARY can exist in a container with no daemon at all (the
    gateway is PID 1), so look for a running cron/crond process."""
    if shutil.which(_crontab_bin()) is None:
        return False
    if is_mac():
        return True
    if shutil.which("pgrep"):
        return any(_run(["pgrep", "-x", name], 10).returncode == 0 for name in ("cron", "crond", "cronie"))
    for comm in Path("/proc").glob("[0-9]*/comm"):          # no pgrep (minimal image): scan /proc
        try:
            if comm.read_text().strip() in ("cron", "crond", "cronie"):
                return True
        except OSError:
            continue
    return False


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
            tmp = d.with_name(d.name + f".new{os.getpid()}")
            shutil.copy2(s, tmp)
            os.replace(tmp, d)          # atomic: a copy of this file that is running right now keeps its old inode
            changed.append(name)
        if not os.access(d, os.X_OK):
            d.chmod(0o755)
    return changed


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


def old_jobs() -> list[dict] | None:
    """[{id, kind}] for every weekly-onboarding-update job; kind 'command' is the silent 2:00 AM updater, any
    other kind (agentTurn, systemEvent) is the agent 'ask first' job."""
    jobs = _cron_jobs()
    if jobs is None:
        return None
    return [{"id": str(j["id"]), "kind": str((j.get("payload") or {}).get("kind") or "")}
            for j in jobs if j.get("name") == OLD_CRON_NAME and j.get("id")]


def old_job_ids() -> list[str] | None:
    jobs = old_jobs()
    return None if jobs is None else [j["id"] for j in jobs]


def retire_cron_jobs(only_ask: bool = False) -> list[str]:
    """Remove openclaw cron jobs named weekly-onboarding-update by id (with retries on a busy box). only_ask
    removes just the agent 'ask first' jobs and keeps the silent command job as the safety net until a tick has
    proven the new schedule. Unreadable list = nothing removed, retried next time."""
    removed = []
    for j in old_jobs() or []:
        if only_ask and j["kind"] == "command":
            continue
        for _ in range(int(os.environ.get("AUTO_UPDATE_RM_TRIES", "3"))):
            if _run(["openclaw", "cron", "rm", j["id"]], 60).returncode == 0:
                removed.append(j["id"])
                break
            time.sleep(float(os.environ.get("AUTO_UPDATE_RM_DELAY", "5")))
    return removed


def remove_jobs_named(name: str) -> list[str]:
    out = []
    for j in _cron_jobs() or []:
        if j.get("name") == name and j.get("id") and _run(["openclaw", "cron", "rm", str(j["id"])], 60).returncode == 0:
            out.append(str(j["id"]))
    return out


TICK_JOB_NAME = "auto-update-tick"


def _tick_job_present(root: Path) -> bool:
    cmd = f"/bin/bash '{root}/scripts/auto-update-tick.sh'"
    return any(j.get("name") == TICK_JOB_NAME and (j.get("payload") or {}).get("argv") == ["sh", "-lc", cmd]
               and j.get("enabled", True) is not False for j in (_cron_jobs() or []))


SELF_JOB_NAME = "auto-update-selfcheck"
AGENT_TICK_PROMPT = ("Silent maintenance task. Run exactly this one command and nothing else: bash '{root}/scripts/auto-update-tick.sh'. "
                     "Never send any message to the owner or anyone, never ask a question, never start any other task. "
                     "When it finishes reply with the single word OK.")


def _commands_supported() -> bool:
    h = _run(["openclaw", "cron", "add", "--help"], 30)
    return h.returncode != 0 or bool(re.search(r"^\s*--command[\s<]", h.stdout + h.stderr, re.M))


def ensure_selfcheck_job(root: Path) -> str:
    """A real timer for the 15-minute proof: a silent OpenClaw command job that runs `selfcheck` every 15
    minutes until selfcheck itself removes it (proven or fallen back)."""
    jobs = _cron_jobs()
    if jobs is None or not _commands_supported():
        return "unavailable"
    if any(j.get("name") == SELF_JOB_NAME for j in jobs):
        return "present"
    cmd = f"python3 '{root}/scripts/auto_update.py' selfcheck"
    r = _run(["openclaw", "cron", "add", "--name", SELF_JOB_NAME, "--cron", "*/15 * * * *", "--tz", "America/New_York",
              "--exact", "--description", "Auto-update schedule self-check (silent; removes itself once the tick is proven)",
              "--command", cmd, "--timeout-seconds", "600", "--no-deliver"], 90)
    return "created" if r.returncode == 0 else "unavailable"


def ensure_agent_tick_job(root: Path) -> str:
    """Last resort for an OpenClaw with no command jobs and no cron daemon: a SILENT agent job whose only
    instruction is to run the tick script and never message the owner (replaces the old ask-first job)."""
    jobs = _cron_jobs()
    if jobs is None:
        return "unavailable"
    if any(j.get("name") == TICK_JOB_NAME for j in jobs):
        return "present"
    agent = ""
    ra = _run(["openclaw", "agents", "list", "--json"], 30)
    try:
        raw = ra.stdout
        data = json.loads(raw[min([x for x in (raw.find("{"), raw.find("[")) if x >= 0] or [0]):])
        lst = data if isinstance(data, list) else data.get("agents", [])
        agent = next((x.get("id") for x in lst if isinstance(x, dict) and (x.get("default") or x.get("isDefault"))), "") or ""
    except ValueError:
        pass
    agent = agent or "main"
    prompt = AGENT_TICK_PROMPT.format(root=root)
    h = _run(["openclaw", "cron", "add", "--help"], 30)
    modern = bool(re.search(r"^\s*--session[\s<]", h.stdout + h.stderr, re.M))
    base = ["openclaw", "cron", "add", "--name", TICK_JOB_NAME, "--agent", agent, "--cron", "*/5 * * * *",
            "--tz", "America/New_York", "--exact", "--light-context", "--no-deliver"]
    tries = ([base + ["--session", "main", "--system-event", prompt], base + ["--session-target", "main", "--message", prompt]]
             if modern else [base + ["--session-target", "main", "--message", prompt], base + ["--session", "main", "--system-event", prompt]])
    for cmd in tries:
        if _run(cmd, 90).returncode == 0 and any(j.get("name") == TICK_JOB_NAME for j in _cron_jobs() or []):
            return "created"
    return "unavailable"


def ensure_openclaw_tick_job(root: Path, dry_run: bool = False) -> str:
    """'present' | 'created' | 'unavailable'. Idempotent, and VERIFIED by reading the job list back."""
    cmd = f"/bin/bash '{root}/scripts/auto-update-tick.sh'"
    if _cron_jobs() is None:
        return "unavailable"
    if _tick_job_present(root):
        return "present"
    if dry_run:
        return "created"
    help_txt = _run(["openclaw", "cron", "add", "--help"], 30)
    if help_txt.returncode == 0 and not re.search(r"^\s*--command[\s<]", help_txt.stdout + help_txt.stderr, re.M):
        return "unavailable"                  # this OpenClaw has no command jobs
    r = _run(["openclaw", "cron", "add", "--name", TICK_JOB_NAME, "--cron", "*/5 * * * *", "--tz", "America/New_York",
              "--exact", "--description", "Tue/Fri/Sun auto-update tick (silent; keeps its own Eastern clock)",
              "--command", cmd, "--timeout-seconds", "7200", "--no-deliver"], 90)
    return "created" if r.returncode == 0 and _tick_job_present(root) else "unavailable"


def _install_crontab(root: Path, res: dict) -> bool:
    """One write that adds the tick line and drops the retired lines, then read back and verify; on any
    doubt put the previous crontab back (the old schedule survives a failed install)."""
    cur = _run([_crontab_bin(), "-l"], 30)
    current = cur.stdout if cur.returncode == 0 else ""
    want = desired_crontab(current, root)
    if want.strip() == current.strip():
        return True
    bak = skills_dir(root) / f".crontab.bak-auto-update-{now_utc():%Y%m%d-%H%M%S}"
    try:
        bak.parent.mkdir(parents=True, exist_ok=True)
        bak.write_text(current)
        res["crontab_backup"] = str(bak)
    except OSError:
        pass
    p = subprocess.run([_crontab_bin(), "-"], input=want, text=True, capture_output=True)
    back = _run([_crontab_bin(), "-l"], 30)
    ok = p.returncode == 0 and back.returncode == 0 and want.strip() == back.stdout.strip()
    if not ok:
        subprocess.run([_crontab_bin(), "-"], input=current, text=True, capture_output=True)    # restore
        res["error"] = "crontab install could not be verified; the previous crontab was kept"
        return False
    res["crontab_changed"] = True
    return True


def install(root: Path | None = None, src: Path | None = None, dry_run: bool = False) -> dict:
    """Idempotent. The old schedule is retired ONLY after the new one is installed and verified, and a box is
    never left without one: a failed install keeps every old entry and reports an error (non-zero exit)."""
    root = root or oc_root()
    src = src or SCRIPT_DIR
    res = {"scripts_changed": [], "crontab_changed": False, "old_files_removed": [], "cron_jobs_removed": [],
           "retire_pending": False}
    if not dry_run:
        res["scripts_changed"] = ensure_scripts(root, src)
    use_crontab = cron_daemon_running()
    res["scheduler"] = "crontab" if use_crontab else "openclaw-job"
    old = old_jobs() or []
    had_old = bool(old) or any((skills_dir(root) / f).exists() for f in (".update-restart-if-needed", ".openclaw-self-update"))
    if dry_run:
        res["old_files_removed"] = [f for f in (".update-restart-if-needed", ".openclaw-self-update") if (skills_dir(root) / f).exists()]
        return res
    if use_crontab:
        if not _install_crontab(root, res):
            return res
        remove_jobs_named(TICK_JOB_NAME)       # one scheduler only: a leftover fallback tick job would double-tick
        # The agent "ask first" jobs go NOW (the new schedule is verified written). The silent command job stays
        # as the safety net until a tick has run; selfcheck (a real 15-minute timer job) retires it or falls back.
        res["cron_jobs_removed"] = retire_cron_jobs(only_ask=True)
        res["retire_pending"] = any(j["kind"] == "command" for j in old)
        res["selfcheck_job"] = ensure_selfcheck_job(root)
    else:
        res["tick_job"] = ensure_openclaw_tick_job(root)
        if res["tick_job"] == "unavailable":
            res["tick_job"] = ensure_agent_tick_job(root)
            if res["tick_job"] != "unavailable":
                res["scheduler"] = "agent-fallback"        # flagged in every beacon so the 6 AM report shows it
        if res["tick_job"] == "unavailable":
            res["error"] = "no cron daemon is running and no openclaw cron job could be created; the old schedule was kept"
            return res
        res["cron_jobs_removed"] = retire_cron_jobs()
        cur = _run([_crontab_bin(), "-l"], 30) if shutil.which(_crontab_bin()) else None
        if cur is not None and cur.returncode == 0:
            _install_crontab_retire_only(root, cur.stdout, res)
    for old in (".update-restart-if-needed", ".openclaw-self-update"):
        f = skills_dir(root) / old
        if f.exists():
            res["old_files_removed"].append(old)
            f.unlink()
    prev = read_json(install_path(root), {})
    migration_day = prev.get("migration_day") or (to_eastern(now_utc()).date().isoformat() if had_old else None)
    same = prev.get("scheduler") == res["scheduler"] and not res["crontab_changed"] and not res["scripts_changed"]
    write_json_atomic(install_path(root), {
        "installed_at_ms": prev.get("installed_at_ms") if same and prev.get("installed_at_ms") else int(now_utc().timestamp() * 1000),
        "scheduler": res["scheduler"], "migration_day": migration_day,
        "retire_pending": bool(res["retire_pending"] or prev.get("retire_pending") and same)})
    return res


def _install_crontab_retire_only(root: Path, current: str, res: dict) -> None:
    """On an openclaw-job box that still has retired crontab lines (no daemon fires them): drop them."""
    keep = [l for l in current.splitlines() if not any(p.search(l) for p in OLD_CRON_PATTERNS) and CRON_TAG not in l]
    if len(keep) != len(current.splitlines()):
        subprocess.run([_crontab_bin(), "-"], input="\n".join(keep) + "\n", text=True, capture_output=True)


def finish_migration(root: Path) -> list[str]:
    """Called by every tick: the tick running IS the proof the crontab schedule fires, so the old openclaw
    jobs are retired now (never earlier). Returns the ids removed."""
    meta = read_json(install_path(root), {})
    if not meta.get("retire_pending"):
        return []
    removed = retire_cron_jobs()
    if not old_job_ids():                      # gone (or none left): done; unreadable list keeps it pending
        meta["retire_pending"] = False
        write_json_atomic(install_path(root), meta)
    return removed


def selfcheck(root: Path | None = None) -> dict:
    """Run by setup-weekly-update.sh and update-skills.sh. If the crontab schedule was installed more than
    15 minutes ago and no tick has run since, the cron line is not firing: fall back to the openclaw cron job
    (verified), and only then retire the old jobs. If a tick has run, finish retiring the old jobs."""
    root = root or oc_root()
    meta = read_json(install_path(root), {})
    out = {"state": "no-install-record"}
    if not meta:
        return out
    hb = skills_dir(root) / ".auto-update-heartbeat"
    installed = meta.get("installed_at_ms") or 0
    try:
        beat = int(hb.read_text().strip())
    except (OSError, ValueError):
        beat = 0
    if meta.get("scheduler") in ("openclaw-job", "agent-fallback"):
        out["state"] = meta["scheduler"] if any(j.get("name") == TICK_JOB_NAME for j in _cron_jobs() or []) else "tick-job-missing"
        remove_jobs_named(SELF_JOB_NAME)
        return out
    if beat >= installed:
        out["state"] = "proven"
        out["retired"] = finish_migration(root)
        remove_jobs_named(SELF_JOB_NAME)             # the timer has done its job
        return out
    if int(now_utc().timestamp() * 1000) - installed < 15 * 60 * 1000:
        out["state"] = "waiting-for-first-tick"
        return out
    job = ensure_openclaw_tick_job(root)
    sched = "openclaw-job"
    if job == "unavailable":
        job = ensure_agent_tick_job(root)
        sched = "agent-fallback"
    out["state"], out["tick_job"] = "fallback-to-openclaw-job", job
    if job in ("present", "created"):
        remove_jobs_named(SELF_JOB_NAME)
        meta["scheduler"] = sched
        write_json_atomic(install_path(root), meta)
        out["retired"] = retire_cron_jobs()
        meta["retire_pending"] = bool(old_job_ids())
        write_json_atomic(install_path(root), meta)
    return out


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
    sub.add_parser("selfcheck")
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
        res = install(root, dry_run=a.dry_run)
        print(json.dumps(res, indent=2))
        return 1 if res.get("error") else 0
    elif a.cmd == "selfcheck":
        print(json.dumps(selfcheck(root), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
