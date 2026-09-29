#!/usr/bin/env python3
"""
fleet_refresh_runner.py — PRD item 1.11 per-box state machine.

Called by scripts/fleet-refresh.sh (the bash wrapper handles fan-out across
boxes; this module handles the per-box logic).  When running against a real box
over SSH the wrapper invokes this via:

    python3 fleet_refresh_runner.py --shared-utils <path> --repo-root <path> [flags]

When running in --local mode (fixture tests or local box), the wrapper invokes
it directly without SSH.

Emits a SINGLE JSON object to stdout.  All diagnostics go to stderr.

Exit codes:
    0  success / dry-run completed
    1  fatal (platform detection failure, missing required args)
    2  partial (at least one step failed but run continued)
    3  retry-then-mark-UNKNOWN (transient error; caller retries; on repeated
       failure marks box UNKNOWN — NEVER destructive)

PRD 1.11 — v11.15.0 (B.6 embedding-health wired in v11.16.0)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from departments_payload import (  # noqa: E402  (same-dir shared helper)
    MalformedDepartmentsError,
    normalize_departments,
)

# The exact token run_box's verdict test keys on — see _scrub_gating_token().
_GATING_TOKEN_RE = re.compile("failed", re.IGNORECASE)

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
NC     = "\033[0m"

def _err(msg: str) -> None:  print(f"{RED}[fleet-refresh] {msg}{NC}", file=sys.stderr)
def _warn(msg: str) -> None: print(f"{YELLOW}[fleet-refresh] {msg}{NC}", file=sys.stderr)
def _info(msg: str) -> None: print(f"{CYAN}[fleet-refresh] {msg}{NC}", file=sys.stderr)
def _ok(msg: str) -> None:   print(f"{GREEN}[fleet-refresh] {msg}{NC}", file=sys.stderr)


# ── Wave 5 deploy preflight (FAIL-CLOSED — NO BYPASS) ────────────────────────

_WAVE5_CC_REPO = "trevorotts1/blackceo-command-center"
# Each entry: (label, path) — B.3 uses a candidate list (see wave5_deploy_preflight).
_WAVE5_REQUIRED_FILES = [
    ("B.1", "scripts/cc-health-check.sh"),
    ("B.2", "scripts/atomic-deploy.sh"),
]
# B.3 duck-test: probe duck-test.ts first (TypeScript source), fall back to
# duck-test (extensionless/shell).  First 200 wins.  Both absent = BLOCKED.
_WAVE5_B3_CANDIDATES = [
    "tests/e2e/duck-test.ts",
    "tests/e2e/duck-test",
]

def wave5_deploy_preflight() -> None:
    """
    Fail-closed preflight that MUST pass before ANY Wave-5 Command Center
    deploy proceeds.

    Checks that ALL THREE of the following paths exist on origin/main of
    trevorotts1/blackceo-command-center:

        scripts/cc-health-check.sh      (B.1 — must be merged to main)
        scripts/atomic-deploy.sh        (B.2 — must be merged to main)
        tests/e2e/duck-test.ts          (B.3 — TypeScript duck CI test; falls
                                          back to tests/e2e/duck-test if the
                                          .ts form is absent.  Either extension
                                          satisfies the gate.)

    B.3 is a duck-test on the path itself: we do not require a specific
    extension, only that some form of the duck-test file exists on main.

    Uses the GitHub Contents API (unauthenticated or via GITHUB_TOKEN) to
    check each path authoritatively against the main branch HEAD.
    A 200 response means the path is present; 404 means absent.

    If ANY required item is missing this function prints a FATAL message and
    exits non-zero immediately.  There is NO env-var, NO flag, and NO code
    path that bypasses this check.  It runs unconditionally and is
    PRESERVED UNWEAKENED at the top of both step_build_cc and step_restart_cc.
    """
    import urllib.request
    import urllib.error

    global _WAVE5_PASSED
    if _WAVE5_PASSED:   # same check, same run, minutes earlier: re-asking GitHub only adds flake
        return

    _info("Wave-5 deploy preflight: checking B.1 + B.2 + B.3 on origin/main of blackceo-command-center ...")

    missing: list[tuple[str, str]] = []
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    def _probe(label: str, path: str) -> bool:
        """Return True if path returns 200 on origin/main; False otherwise."""
        url = (
            f"https://api.github.com/repos/{_WAVE5_CC_REPO}/contents/{path}"
            f"?ref=main"
        )
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    _ok(f"  {label} PRESENT on main: {path}")
                    return True
                # Non-200/non-404 — treat as missing (fail-closed)
                _err(f"  {label} UNEXPECTED status {resp.status} for: {path} — treating as MISSING")
                return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            _err(f"  {label} HTTP error {e.code} for: {path} — treating as MISSING (fail-closed)")
            return False
        except Exception as exc:
            _err(f"  {label} check failed ({exc.__class__.__name__}: {exc}) — treating as MISSING (fail-closed)")
            return False

    # B.1 and B.2: single-path checks
    for label, path in _WAVE5_REQUIRED_FILES:
        if not _probe(label, path):
            missing.append((label, path))
            _err(f"  {label} MISSING on main (404): {path}")

    # B.3: duck-test path probe — accept duck-test.ts OR duck-test
    b3_found = False
    for candidate in _WAVE5_B3_CANDIDATES:
        if _probe("B.3", candidate):
            b3_found = True
            break
    if not b3_found:
        missing.append(("B.3", "tests/e2e/duck-test{.ts,}"))
        _err("  B.3 MISSING on main (checked duck-test.ts AND duck-test)")

    if missing:
        _err("")
        _err("╔══════════════════════════════════════════════════════════════════╗")
        _err("║  FATAL: Wave-5 deploy BLOCKED — B.1+B.2+B.3 preflight FAILED    ║")
        _err("╠══════════════════════════════════════════════════════════════════╣")
        for lbl, m in missing:
            _err(f"║  MISSING from trevorotts1/blackceo-command-center @ main:         ║")
            _err(f"║    [{lbl}] {m:<54}║")
        _err("╠══════════════════════════════════════════════════════════════════╣")
        _err("║  Wave 5 is BLOCKED until ALL three paths are merged to main:     ║")
        _err("║    B.1  scripts/cc-health-check.sh                               ║")
        _err("║    B.2  scripts/atomic-deploy.sh                                 ║")
        _err("║    B.3  tests/e2e/duck-test.ts  (or duck-test)                   ║")
        _err("║                                                                  ║")
        _err("║  Merge B.1 + B.2 + B.3 to main in blackceo-command-center,      ║")
        _err("║  then retry.                                                     ║")
        _err("╚══════════════════════════════════════════════════════════════════╝")
        sys.exit(1)

    _ok("Wave-5 deploy preflight PASSED — B.1 + B.2 + B.3 all present on origin/main.")
    _WAVE5_PASSED = True


_WAVE5_PASSED = False


# ── Box result schema ─────────────────────────────────────────────────────────

class BoxResult:
    def __init__(self, box: str, dry_run: bool):
        self.box = box
        self.dry_run = dry_run
        self.platform: str = "unknown"
        self.onboarding_version: str = "unknown"
        self.cc_version: str = "unknown"
        self.merged_sha: Optional[str] = None
        self.deployed: dict = {"ok": False}
        self.loaded: dict = {"loaded_confidence": "unknown", "present": False}
        self.board: dict = {"cc_healthy": False}
        self.steps: dict = {}
        self.result: str = "dry-run" if dry_run else "failed"
        self.errors: list[str] = []
        # Roll-safety record: what the box was before we touched it, what the
        # health gate saw, and what (if anything) was undone.
        self.snapshot: dict = {}
        self.health: dict = {}
        self.rollback: dict = {}
        self.update_999: dict = {}
        self.heal: dict = {}
        # One-word verdict for the fleet summary:
        # UPDATED | ROLLED_BACK | FAILED | SKIPPED  (+ outcome_detail).
        self.outcome: str = "SKIPPED" if dry_run else "FAILED"
        self.outcome_detail: str = "dry-run" if dry_run else ""

    def step_ok(self, name: str) -> None:
        self.steps[name] = "ok"
        _ok(f"  step {name}: ok")

    def step_skip(self, name: str, reason: str = "dry-run") -> None:
        self.steps[name] = f"skip:{reason}"
        _info(f"  step {name}: SKIP ({reason})")

    def step_fail(self, name: str, reason: str) -> None:
        self.steps[name] = f"failed:{reason}"
        self.errors.append(f"{name}: {reason}")
        _err(f"  step {name}: FAILED — {reason}")

    def to_dict(self) -> dict:
        return {
            "box":                 self.box,
            "platform":            self.platform,
            "dry_run":             self.dry_run,
            "merged_sha":          self.merged_sha,
            "deployed":            self.deployed,
            "loaded":              self.loaded,
            "board":               self.board,
            "steps":               self.steps,
            "result":              self.result,
            "errors":              self.errors,
            "onboarding_version":  self.onboarding_version,
            "cc_version":          self.cc_version,
            "snapshot":            self.snapshot,
            "health":              self.health,
            "rollback":            self.rollback,
            "update_999":          self.update_999,
            "heal":                self.heal,
            "outcome":             self.outcome,
            "outcome_detail":      self.outcome_detail,
        }


# ── Platform detection ────────────────────────────────────────────────────────

def _load_paths(shared_utils: Path) -> dict:
    """
    Load platform paths using detect_platform.get_openclaw_paths().
    Honors FLEET_REFRESH_ROOT env var for fixture tests.
    """
    sys.path.insert(0, str(shared_utils))
    try:
        # FLEET_REFRESH_ROOT: redirect root in fixture tests
        env_root = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
        if env_root:
            # Build a synthetic paths dict for fixture mode
            root = Path(env_root)
            platform_marker = root / "data" / ".openclaw"
            if platform_marker.exists():
                _root = platform_marker
                platform = "vps"
                workspace = _root / "workspace"
                master_files = root / "data" / "openclaw-master-files"
                cc_dir = root / "data" / "projects" / "command-center"
            else:
                _root = root / "home" / ".openclaw"
                platform = "mac"
                workspace = _root / "workspace"
                master_files = root / "home" / "Downloads" / "openclaw-master-files"
                cc_dir = root / "home" / "projects" / "command-center"
            return {
                "platform":     platform,
                "root":         _root,
                "workspace":    workspace,
                "master_files": master_files,
                "company_root": master_files / "zero-human-company",
                "dashboard_db": None,
                "cc_dir":       cc_dir,
            }

        from detect_platform import get_openclaw_paths  # type: ignore
        p = get_openclaw_paths()
        p["cc_dir"], p["cc_dir_how"] = find_cc_dir(Path(p["root"]))
        return p
    except SystemExit:
        _err("Cannot detect OpenClaw platform (no /data/.openclaw, ~/.openclaw, ~/clawd).")
        sys.exit(1)


# ── Command Center checkout discovery ─────────────────────────────────────────
#
# Every box has its OWN Command Center in its own place (a Mac under the
# client's home, a container's /data volume, ~/.openclaw/command-center on
# Contabo, ...). This runs ON the box and finds the git checkout of the code
# that box is actually serving: the process listening on the CC port, then
# pm2's app, then update-skills.sh's validated candidate list. It only ever
# READS: a folder that holds the live mission-control.db but is not the code
# checkout (e.g. ~/projects/command-center on the operator Mac) is simply not
# chosen -- never moved, cleaned or deleted. The database is located separately
# through resolve_db.py.

CC_NOT_FOUND = "Command Center not found on this box"
_CC_PM2_NAMES = ("blackceo-command-center", "mission-control", "command-center")
# update-skills.sh cc_resolve_existing_dir() / U6d, plus <openclaw root>/command-center
# (a Contabo container layout).
_CC_CANDIDATES = ("{home}/projects/command-center", "/data/projects/command-center",
                  "{home}/projects/blackceo-command-center", "/data/projects/blackceo-command-center",
                  "{home}/projects/mission-control", "{home}/blackceo-command-center",
                  "{root}/command-center", "/opt/mission-control", "/app")


def cc_is_valid_checkout(d: Path) -> bool:
    """update-skills.sh's cc_is_valid_checkout: a git checkout of the
    blackceo-command-center repo that carries a package.json."""
    if not ((d / ".git").exists() and (d / "package.json").is_file()):
        return False
    return "blackceo-command-center" in (_git(d, "remote", "get-url", "origin") or "")


def _cc_checkout_of(path: Optional[Path]) -> Optional[Path]:
    """The checkout containing `path` (a server's cwd can be .next/standalone)."""
    for d in ([path, *list(path.parents)[:4]] if path else []):
        if cc_is_valid_checkout(d):
            return d
    return None


def _run_out(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _port_pids(port: int) -> list[int]:
    out = _run_out(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    if not out:   # no lsof in most containers: ss names the owning process
        out = " ".join(re.findall(r"pid=(\d+)", _run_out(["ss", "-ltnpH", f"sport = :{port}"])))
    pids = [int(x) for x in out.split() if x.isdigit()]
    return pids or _proc_listen_pids(port)


def _proc_listen_pids(port: int) -> list[int]:
    """Linux without lsof/ss (a slim container): the listening socket's inode
    from /proc/net/tcp{,6}, then the process holding that inode."""
    inodes = set()
    for f in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in Path(f).read_text().splitlines()[1:]:
                c = line.split()
                if len(c) > 9 and c[3] == "0A" and int(c[1].rsplit(":", 1)[1], 16) == port:
                    inodes.add(f"socket:[{c[9]}]")
        except (OSError, ValueError, IndexError):
            continue
    pids = []
    for fd_dir in Path("/proc").glob("[0-9]*/fd") if inodes else []:
        try:
            if any(os.readlink(fd) in inodes for fd in fd_dir.iterdir()):
                pids.append(int(fd_dir.parent.name))
        except OSError:
            continue
    return pids


def _proc_cwd(pid: int) -> Optional[Path]:
    try:
        return Path(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        pass
    m = re.search(r"^n(/.*)$", _run_out(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]), re.M)
    return Path(m.group(1)) if m else None


def _cc_pm2_ancestor() -> Optional[str]:
    """Command line of the pm2 process among the ancestors of whatever serves
    the Command Center port; "" when it is not under pm2, None when nothing
    serves the port."""
    pids = _port_pids(int(os.environ.get("CC_PORT") or 4000))
    if not pids:
        return None
    for pid in pids:
        cur = str(pid)
        for _ in range(8):
            out = _run_out(["ps", "-o", "ppid=,command=", "-p", cur]).strip()
            if not out:
                break
            ppid, _, cmd = out.partition(" ")
            if re.search(r"\bPM2\b|pm2", cmd):
                return cmd.strip()
            cur = ppid.strip()
            if cur in ("", "0", "1"):
                break
    return ""


def cc_pm2_managed() -> Optional[bool]:
    """Whether the process serving the Command Center port runs under pm2 (a
    pm2 daemon among its ancestors). None when nothing serves the port.
    atomic-deploy.sh / update.sh restart the app through pm2: a Command Center
    started some other way cannot be deployed, and used to fail half way through
    the deploy ("Required dependency missing: pm2") instead of up front."""
    cmd = _cc_pm2_ancestor()
    return None if cmd is None else bool(cmd)


def _pm2_home_daemon_alive() -> bool:
    """Whether this shell's PM2_HOME has a running daemon. Checked from its pid
    file: any pm2 command against an empty home would itself spawn the stray
    second daemon this preflight exists to catch."""
    home = Path(os.environ.get("PM2_HOME") or Path.home() / ".pm2")
    try:
        os.kill(int((home / "pm2.pid").read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def cc_pm2_problem() -> Optional[str]:
    """Why the deploy could not restart this box's Command Center through pm2,
    or None. Checked before anything changes, instead of failing mid-deploy."""
    managed = cc_pm2_managed()
    if managed is None:
        return None   # nothing serves the port: the deploy starts it
    if managed is False:
        return ("Command Center not under pm2: the process serving its port was not started by pm2, "
                "and the deploy restarts it through pm2")
    if not shutil.which("pm2"):
        return ("Command Center runs under pm2, but pm2 is not on this shell's PATH "
                "(the deploy could not restart it)")
    # The daemon that runs the Command Center names its home: "God Daemon (<home>)".
    here = Path(os.environ.get("PM2_HOME") or Path.home() / ".pm2")
    m = re.search(r"God Daemon \((.+)\)", _cc_pm2_ancestor() or "")
    if m and Path(m.group(1)).resolve() != here.resolve():
        return (f"Command Center runs under the pm2 daemon of {m.group(1)}, but this shell's PM2_HOME is "
                f"{here} (a split PM2_HOME: the deploy would restart nothing)")
    if not _pm2_home_daemon_alive() or not any(
            p.isdigit() and p != "0" for n in _CC_PM2_NAMES for p in _run_out(["pm2", "pid", n]).split()):
        return ("Command Center runs under pm2, but this shell's pm2 (PM2_HOME) does not list it "
                f"as any of {', '.join(_CC_PM2_NAMES)} (the deploy could not restart it)")
    return None


def find_cc_dir(root: Path) -> tuple[Optional[Path], str]:
    """(code checkout, how it was found) or (None, why not)."""
    for var in ("CC_APP_DIR", "BLACKCEO_COMMAND_CENTER_ROOT"):
        v = os.environ.get(var, "").strip()
        if v:
            d = Path(v).expanduser()
            return (d, f"{var}") if cc_is_valid_checkout(d) else (None, f"{var}={v} is not a Command Center checkout")
    port = int(os.environ.get("CC_PORT") or 4000)
    for pid in _port_pids(port):
        d = _cc_checkout_of(_proc_cwd(pid))
        if d:
            return d, f"the process serving port {port}"
    for name in _CC_PM2_NAMES:
        for pid in _run_out(["pm2", "pid", name]).split():
            if pid.isdigit() and pid != "0":
                d = _cc_checkout_of(_proc_cwd(int(pid)))
                if d:
                    return d, f"pm2 app {name}"
    for c in _CC_CANDIDATES:
        d = Path(c.format(home=Path.home(), root=root))
        if cc_is_valid_checkout(d):
            return d, "candidate list"
    return None, CC_NOT_FOUND


# ── Session key resolution ────────────────────────────────────────────────────

def _owner_agent_ids(paths: dict) -> list[str]:
    """The agent the owner talks to: the one the owner's own (default-account)
    Telegram bot is bound to -- many client boxes have no agent named "main" at
    all, their CEO is e.g. dept-master-orchestrator -- then "main"."""
    direct, catch_all = [], []
    try:
        cfg = json.loads((Path(paths["root"]) / "openclaw.json").read_text())
        for b in cfg.get("bindings") or []:
            m = (b.get("match") or {}) if isinstance(b, dict) else {}
            # the owner's own bot: the default account ("*"/"default"/unset); a
            # binding for a named extra bot (rescue, operator...) is not the owner's
            if m.get("channel") != "telegram" or m.get("accountId") not in (None, "*", "default") \
                    or not b.get("agentId"):
                continue
            kind = (m.get("peer") or {}).get("kind")
            if kind == "direct":          # the owner's DM, bound explicitly
                direct.append(b["agentId"])
            elif kind is None:            # every chat of the bot (group bindings are not the owner)
                catch_all.append(b["agentId"])
    except (OSError, ValueError, KeyError):
        pass
    return list(dict.fromkeys(direct + catch_all + ["main"]))


def _owner_workspace(paths: dict) -> Optional[Path]:
    """The owner agent's own workspace when its config names one (e.g.
    ~/.openclaw/workspace-nova), else None."""
    try:
        agents = json.loads((Path(paths["root"]) / "openclaw.json").read_text()).get("agents") or {}
        entries = agents.get("entries") or {a.get("id"): a for a in agents.get("list") or [] if isinstance(a, dict)}
        for agent in _owner_agent_ids(paths):
            ws = (entries.get(agent) or {}).get("workspace")
            if ws:
                return Path(os.path.expanduser(ws))
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return None


def _agent_session_keys(paths: dict, agent: str) -> list[tuple[str, float]]:
    """(key, updatedAt) of one agent's sessions. OpenClaw before 2026.8 kept
    them in agents/<id>/sessions/sessions.json; later releases keep them in the
    agent's SQLite store, read through `openclaw sessions list`."""
    legacy = Path(paths["root"]) / "agents" / agent / "sessions" / "sessions.json"
    if legacy.is_file():
        try:
            data = json.loads(legacy.read_text())
            return [(k, float(v.get("updatedAt") or 0) if isinstance(v, dict) else 0.0) for k, v in data.items()]
        except (OSError, ValueError) as e:
            _warn(f"Could not parse {legacy}: {e}")
    if os.environ.get("FLEET_REFRESH_ROOT", "").strip():
        return []   # fixture mode: never the test machine's gateway
    out = _run_out(["openclaw", "sessions", "list", "--agent", agent, "--json", "--limit", "all"], timeout=90)
    try:
        rows = (json.loads(out) or {}).get("sessions") or []
    except ValueError:
        return []
    return [(r["key"], float(r.get("updatedAt") or 0)) for r in rows if isinstance(r, dict) and r.get("key")]


def _resolve_ceo_session_key(paths: dict) -> Optional[str]:
    """
    The owner agent's owner-facing session: a Telegram direct session
    (agent:<id>:telegram[:<account>]:direct:<n>) or, where DMs collapse into it
    (session.dmScope "main", the default), agent:<id>:main. The owner agent is
    the Telegram-bound agent, else "main"; the most recently used session wins.
    None when neither exists.
    (Never docker logs or ownerAllowFrom -- per memory rules.)
    """
    for agent in _owner_agent_ids(paths):
        dm = re.compile(rf"^agent:{re.escape(agent)}:telegram:(?:[^:]+:)?direct:\d+$")
        keys = [(k, t) for k, t in _agent_session_keys(paths, agent) if dm.match(k) or k == f"agent:{agent}:main"]
        if keys:
            return max(keys, key=lambda kt: kt[1])[0]
    _warn(f"No owner session (agent:<id>:telegram:...:direct:<n> or agent:<id>:main) found for agents "
          f"{', '.join(_owner_agent_ids(paths))}")
    return None


# ── Version helpers ───────────────────────────────────────────────────────────

def _read_onboarding_version(repo_root: Path) -> str:
    v_file = repo_root / ".onboarding-version"
    if v_file.is_file():
        return v_file.read_text().strip()
    # Try the version file directly (if this is the skills dir)
    for candidate in ["version", "VERSION"]:
        vf = repo_root / candidate
        if vf.is_file():
            return vf.read_text().strip()
    return "unknown"


def _read_cc_version(cc_dir: Path) -> str:
    pkg = cc_dir / "package.json"
    if not pkg.is_file():
        return "unknown"
    try:
        d = json.loads(pkg.read_text())
        return d.get("version", "unknown")
    except Exception:
        return "unknown"


# ── Deployed verifier ─────────────────────────────────────────────────────────

def _check_deployed(
    paths: dict,
    compat: dict,
    pinned_onboarding_tag: str,
    res: BoxResult,
) -> None:
    """Step 7 sub-check: verify version + board state."""
    from cc_compat import assert_min_version  # type: ignore

    onboarding_ok = (res.onboarding_version == pinned_onboarding_tag)
    cc_ver = res.cc_version

    cc_ok = True
    cc_min = compat["commandCenter"]["minVersion"]
    if cc_ver != "unknown":
        try:
            assert_min_version(f"v{cc_ver}" if not cc_ver.startswith("v") else cc_ver, compat)
        except ValueError as e:
            cc_ok = False
            res.errors.append(str(e))
    else:
        cc_ok = False

    res.deployed = {
        "onboarding":         res.onboarding_version,
        "onboarding_expected":pinned_onboarding_tag,
        "onboarding_ok":      onboarding_ok,
        "cc":                 cc_ver,
        "min_cc":             cc_min,
        "cc_ok":              cc_ok,
        "ok":                 onboarding_ok and cc_ok,
    }


# ── Loaded verifier ───────────────────────────────────────────────────────────

LOADED_MARKER = "CEO_ORCHESTRATOR_RULE_V2"
LOADED_MARKER_COMMENT = "<!-- CEO_ORCHESTRATOR_RULE_V2 -->"

def _verify_loaded(
    paths: dict,
    shared_utils: Path,
    ceo_session_key: Optional[str],
    res: BoxResult,
) -> None:
    """
    Step 7: The loaded-marker verifier.

    Primary path: query the gateway's systemPromptReport for the live injected
    prompt and grep for the CEO_ORCHESTRATOR_RULE_V2 marker.

    Fallback (proxy): if no systemPromptReport RPC exists on this gateway
    version, fall back to:
        - disk: workspace/SOUL.md contains the marker (Layer-3 proof)
        - session: sessions.json lastSystemPromptTs > sessions.reset ts (Layer-2 proxy)

    IMPORTANT: per the no-guessing rule the exact RPC method is discovered at
    runtime via `openclaw gateway call --help` (or introspection) rather than
    hardcoded. We try the most likely candidates in order and use the first that
    succeeds. The method used is recorded in the JSON.
    """
    # ── Discover available gateway call methods ──────────────────────────────
    system_prompt_method = _discover_system_prompt_method()

    marker_present = False
    method_used = None
    confidence = "unknown"

    if ceo_session_key and system_prompt_method:
        # Primary path: ask the live gateway
        marker_present, method_used = _query_gateway_prompt(
            ceo_session_key, system_prompt_method
        )
        if method_used:
            confidence = "authoritative"

    if not method_used or confidence != "authoritative":
        # Fallback: disk + session proxy
        _info("Falling back to disk+session proxy for loaded verification")
        marker_present, confidence = _proxy_verify_loaded(paths, shared_utils, ceo_session_key)
        method_used = method_used or "proxy"

    # ── Board state ──────────────────────────────────────────────────────────
    cc_healthy = _check_cc_health(paths)
    res.board = {
        "cc_healthy":   cc_healthy,
        # dept_floor checks are informational in 1.11 (live box needed for full check)
        "dept_floor_note": "full dept-floor check requires live box; run department-floor.py --json",
    }

    res.loaded = {
        "method":            method_used,
        "marker":            LOADED_MARKER,
        "present":           marker_present,
        "loaded_confidence": confidence,
        "ceo_session_key":   ceo_session_key or "unresolved",
    }

    if marker_present:
        _ok(f"  loaded marker present (confidence={confidence}, method={method_used})")
    else:
        _warn(f"  loaded marker NOT present (confidence={confidence}, method={method_used})")
        _warn("  The CEO PRIME DIRECTIVE is not in the live system prompt.")
        _warn("  Run fleet-refresh.sh --apply to deploy and reset the session.")


def _discover_system_prompt_method() -> Optional[str]:
    """
    Discover the gateway RPC method that returns the injected system prompt
    for a session key.

    Per the no-guessing rule: we do NOT hardcode a method name that hasn't been
    doc-confirmed. Instead we probe the gateway's help/introspection output and
    try likely candidates in order, recording which one succeeds.

    Returns the method name string if discovered, or None.
    """
    # Check if openclaw is available
    openclaw_bin = shutil.which("openclaw")
    if not openclaw_bin:
        _warn("openclaw not on PATH; skipping gateway method discovery")
        return None

    # Probe available methods via --help
    candidates = [
        "sessions.systemPromptReport",
        "sessions.getSystemPrompt",
        "agents.systemPromptReport",
        "sessions.systemPrompt",
    ]

    # First: try to list available methods from gateway call --help
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "call", "--help"],
            capture_output=True, text=True, timeout=10
        )
        help_text = result.stdout + result.stderr
        for candidate in candidates:
            # Check if the candidate (or at least its base name) appears in help
            base = candidate.split(".")[-1]
            if candidate in help_text or base in help_text:
                _info(f"Gateway method {candidate!r} found in --help output")
                return candidate
    except Exception as e:
        _warn(f"openclaw gateway call --help failed: {e}")

    # Second: try each candidate with a dummy key to see which one responds
    # (not errors with "unknown method", just errors with "session not found" etc.)
    for candidate in candidates:
        try:
            result = subprocess.run(
                ["openclaw", "gateway", "call", candidate,
                 "--params", json.dumps({"key": "__probe__"})],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout + result.stderr
            # If it's NOT "unknown method" or similar, the method exists
            unknown_patterns = ["unknown method", "unknown command", "method not found",
                                 "not supported", "invalid method"]
            is_unknown = any(p in output.lower() for p in unknown_patterns)
            if not is_unknown:
                _info(f"Gateway method {candidate!r} appears available (probe returned non-unknown)")
                return candidate
        except Exception:
            continue

    _warn("Could not discover a systemPromptReport-style gateway method; will use proxy fallback")
    return None


def _query_gateway_prompt(session_key: str, method: str) -> tuple[bool, Optional[str]]:
    """
    Call `openclaw gateway call <method> --params {"key": <session_key>}` and
    grep the response for the CEO_ORCHESTRATOR_RULE_V2 marker.

    Returns (marker_present: bool, method_used: str | None).
    """
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "call", method,
             "--params", json.dumps({"key": session_key})],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout

        # Check for error conditions
        error_patterns = ["unknown method", "session not found", "error:", "failed:"]
        if any(p in (result.stdout + result.stderr).lower() for p in error_patterns):
            _warn(f"Gateway call {method} returned an error; marker check not possible")
            return False, None

        # Attempt JSON parse; fall back to raw text grep
        prompt_text = output
        try:
            resp = json.loads(output)
            # Various possible structures
            prompt_text = (
                resp.get("systemPrompt") or
                resp.get("prompt") or
                resp.get("content") or
                resp.get("text") or
                (json.dumps(resp) if isinstance(resp, dict) else str(resp))
            )
        except Exception:
            pass  # Use raw text

        present = LOADED_MARKER in str(prompt_text)
        return present, method

    except subprocess.TimeoutExpired:
        _warn(f"Gateway call {method} timed out")
        return False, None
    except Exception as e:
        _warn(f"Gateway call {method} failed: {e}")
        return False, None


def _proxy_verify_loaded(
    paths: dict,
    shared_utils: Path,
    ceo_session_key: Optional[str],
) -> tuple[bool, str]:
    """
    Fallback proxy verification when no systemPromptReport RPC is available.

    Two-part check:
        1. workspace/SOUL.md contains the marker (Layer-3: right file)
        2. sessions.json CEO session's systemSent state (Layer-2 proxy)

    Returns (marker_present: bool, confidence: str)
    """
    # Part 1: resolve workspace via the shared helper and check the file
    sys.path.insert(0, str(shared_utils))
    try:
        from resolve_injected_core_files import resolve_injected_core_files  # type: ignore
    except ImportError:
        _warn("resolve_injected_core_files not available; using path fallback")
        workspace = paths["workspace"]
        soul_md = workspace / "SOUL.md"
    else:
        resolved = resolve_injected_core_files("main")
        soul_md = resolved["soul_md"]
        _info(f"Proxy: checking {soul_md} (resolved via {resolved['resolved_from']})")

    disk_ok = False
    if soul_md.is_file():
        content = soul_md.read_text(errors="replace")
        disk_ok = LOADED_MARKER in content
        if disk_ok:
            _ok(f"  Proxy Layer-3: marker found in {soul_md}")
        else:
            _warn(f"  Proxy Layer-3: marker NOT in {soul_md}")
    else:
        _warn(f"  Proxy Layer-3: {soul_md} does not exist")

    # Part 2: check session state (Layer-2 proxy)
    session_ok = False
    if ceo_session_key:
        sessions_path = paths["root"] / "agents" / "main" / "sessions" / "sessions.json"
        try:
            sessions_data = json.loads(sessions_path.read_text())
            sess = sessions_data.get(ceo_session_key, {})
            # Look for fields that suggest a fresh session rebuild
            # (The exact schema varies; we look for any reset/rebuild indicator)
            system_sent = sess.get("systemSent", None)
            last_prompt_ts = sess.get("lastSystemPromptTs") or sess.get("systemPromptTs")
            if system_sent is False:
                # systemSent=false means the session was reset and next message rebuilds
                session_ok = True
                _ok("  Proxy Layer-2: session systemSent=false (session was reset)")
            elif last_prompt_ts:
                _info(f"  Proxy Layer-2: lastSystemPromptTs={last_prompt_ts} (session has a recorded build)")
                session_ok = True
            else:
                _warn("  Proxy Layer-2: cannot confirm session rebuild from sessions.json schema")
        except Exception as e:
            _warn(f"  Proxy Layer-2: sessions.json read failed: {e}")

    # Confidence is always "proxy" in this path
    marker_present = disk_ok  # disk is the best we can do in proxy mode
    return marker_present, "proxy"


def _check_cc_health(paths: dict) -> bool:
    """Check if the Command Center responds to a health check (read-only)."""
    cc_dir = paths.get("cc_dir")
    if not cc_dir or not Path(cc_dir).exists():
        return False

    # Try pm2 status
    try:
        result = subprocess.run(
            ["pm2", "jlist"], capture_output=True, text=True, timeout=10
        )
        pm2_list = json.loads(result.stdout)
        cc_running = any(
            p.get("name") == "command-center" and p.get("pm2_env", {}).get("status") == "online"
            for p in pm2_list
        )
        return cc_running
    except Exception:
        pass

    # Fallback: check if the CC process port responds (default 3000)
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:3000/api/health", timeout=5)
        return True
    except Exception:
        pass

    return False


# ── Steps ─────────────────────────────────────────────────────────────────────

def step_detect(paths: dict, repo_root: Path, compat: dict, res: BoxResult) -> None:
    """Step 0: detect platform, read versions."""
    res.platform = paths.get("platform", "unknown")
    # D1: read the ACTIVE skills-dir stamp (paths["skills"]), not repo_root —
    # update-skills.sh writes <skills-dir>/.onboarding-version, never
    # repo_root/.onboarding-version. Matches step_pull_onboarding's read-path
    # so detect/verify never disagree with the actual roll outcome.
    skills_dir = Path(paths.get("skills") or Path(paths["root"]) / "skills")
    res.onboarding_version = _read_onboarding_version(skills_dir)
    res.cc_version = _read_cc_version(paths.get("cc_dir") or Path("/nonexistent"))
    res.step_ok("detect")
    _info(f"  platform: {res.platform}  onboarding: {res.onboarding_version}  CC: {res.cc_version}")


def step_pin_resolve(paths: dict, repo_root: Path, compat: dict, res: BoxResult) -> str:
    """Step 1: resolve pinned cc_tag from cc-compat.json."""
    from cc_compat import resolve_cc_tag  # type: ignore

    # Get available CC tags (if cc dir exists and has git)
    available_tags = []
    cc_dir = paths.get("cc_dir")
    if cc_dir and Path(cc_dir).is_dir():
        try:
            tag_result = subprocess.run(
                ["git", "-C", str(cc_dir), "tag", "--sort=-version:refname"],
                capture_output=True, text=True, timeout=15
            )
            available_tags = [t.strip() for t in tag_result.stdout.splitlines() if t.strip()]
        except Exception:
            pass

    cc_tag = resolve_cc_tag(compat, available_tags or None)
    res.step_ok("pin-resolve")
    _info(f"  resolved cc_tag: {cc_tag}")
    return cc_tag


# update-skills.sh walks every skill folder and hashes the content: ~55 min on a
# Hostinger container. The old 20-minute cap failed healthy updates mid-way.
UPDATE_SKILLS_TIMEOUT = 5400
# update-skills.sh's fleet standing gate: "Update held -- account not current".
UPDATE_HELD_MARK = "Update held -- account not current"
UPDATE_HELD = "update held -- account not current on payments (fleet standing gate); nothing changed"


def _run_tree(cmd: list[str], timeout: int, **kw) -> subprocess.CompletedProcess:
    """subprocess.run in its own process group; on timeout the whole group is
    killed (subprocess.run alone kills only the direct child, and an orphaned
    updater kept changing a box while it was being rolled back)."""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          start_new_session=True, **kw) as proc:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, 9)
            except OSError:
                pass
            proc.communicate()
            raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def step_pull_onboarding(paths: dict, repo_root: Path, pinned_tag: str, res: BoxResult, dry_run: bool) -> str:
    """Step 2: run update-skills.sh to sync onboarding skills to the pinned tag.

    D1: consumes update-skills.sh's unified stamp-gate contract. That script
    writes <skills-dir>/.onboarding-version ONLY when its own internal gate
    (A3 content-gate + persona/D2-refresh/shared-core/D5-activation latches)
    all pass; on any incompletion it exits 1 and never stamps. A bare
    `returncode == 0` is therefore NEVER treated as done on its own — we
    double-gate on the ACTIVE skills-dir stamp actually equalling pinned_tag
    post-run. force-update.sh is left untouched as the manual "machine was
    off" notifier; it is no longer the autonomous skill-sync entry point.
    """
    if dry_run:
        res.step_skip("pull-onboarding")
        return pinned_tag

    update_skills = repo_root / "update-skills.sh"
    if not update_skills.is_file():
        res.step_fail("pull-onboarding", f"update-skills.sh not found at {update_skills}")
        return pinned_tag

    skills_dir = Path(paths.get("skills") or Path(paths["root"]) / "skills")
    stamp_file = skills_dir / ".onboarding-version"

    try:
        result = _run_tree(
            ["bash", str(update_skills)],
            timeout=UPDATE_SKILLS_TIMEOUT,
            # SECURITY/PRIVACY (v20.0.9): the fleet roll is MAINTENANCE — export
            # OPENCLAW_MAINTENANCE_SILENT=1 into the updater's environment so it
            # (and every subprocess it spawns: migrate-existing-workforce.sh and
            # the embedded qc-completeness.sh) HARD-suppresses any QC Telegram to a
            # client chat, independent of the box's chat/account config. This runner
            # executes ON the target box, so the var reaches the remote updater.
            env={**os.environ, "OPENCLAW_UPDATE_AUTO_SYNC": "1",
                 "OPENCLAW_MAINTENANCE_SILENT": "1",
                 # The runner's clone is already where the roll wants it: the roll copy
                 # held at the roll's commit, or the operator's own clone (--local).
                 # Self-syncing it to main mid-roll mixed releases across boxes, and
                 # on the operator box reset the clone the roll itself runs from.
                 "OPENCLAW_UPDATE_SKIP_SELF_SYNC": "1"},
        )
        post_stamp = stamp_file.read_text().strip() if stamp_file.is_file() else None
        # update-skills.sh self-syncs THIS clone to origin/main before it runs
        # (OPENCLAW_UPDATE_AUTO_SYNC=1), so the version it stamps is the one in
        # the clone's cc-compat.json AFTER the run, not the stale copy loaded
        # before it. Comparing against the stale copy failed every box whose
        # clone was behind.
        try:
            from cc_compat import load_cc_compat  # type: ignore
            pinned_tag = load_cc_compat(repo_root).get("onboardingVersion", pinned_tag)
        except Exception:
            pass
        if result.returncode == 0 and UPDATE_HELD_MARK in result.stdout:
            # The fleet standing gate held this box (account not current on
            # payments): nothing was changed, by design. Not a failure to fix.
            res.step_skip("pull-onboarding", UPDATE_HELD)
        elif result.returncode == 0 and post_stamp == pinned_tag:
            res.onboarding_version = post_stamp
            res.step_ok("pull-onboarding")
        elif result.returncode == 2 and post_stamp == pinned_tag:
            # update-skills.sh exit 2 = skills content current and stamped, some
            # infrastructure needs attention (advisory, not a half-applied run).
            res.onboarding_version = post_stamp
            res.steps["pull-onboarding"] = ("ok:advisory: update-skills.sh exit 2 (content current; "
                                            f"infrastructure needs attention): {result.stdout[-160:].strip()}")
            _warn("  step pull-onboarding: ok (advisory) -- update-skills.sh exit 2: content current, "
                  "infrastructure needs attention")
        else:
            res.step_fail(
                "pull-onboarding",
                f"update-skills.sh exited {result.returncode}; stamp={post_stamp!r} "
                f"expected={pinned_tag!r}: {(result.stderr.strip() or result.stdout.strip())[-300:]}"
            )
    except subprocess.TimeoutExpired:
        res.step_fail("pull-onboarding", f"update-skills.sh timed out after {UPDATE_SKILLS_TIMEOUT}s "
                                         "(it and everything it started were stopped)")
    except Exception as e:
        res.step_fail("pull-onboarding", str(e))
    return pinned_tag


def load_warning(res: BoxResult) -> None:
    """A box whose CPU is saturated (a days-old agent-browser Chrome at ~940%
    on a 10-core Mac) cannot answer the deploy's health check in time; say so
    before the deploy rather than after the outage."""
    load, cores = os.getloadavg()[0], os.cpu_count() or 1
    if load > 2 * cores:
        msg = (f"load {load:.1f} on {cores} cores is over 2x: the Command Center deploy's health check may "
               "time out; look for a runaway process (e.g. a days-old agent-browser Chrome) first")
        _warn(f"  {msg}")
        res.steps["load"] = f"ok:advisory: {msg}"


def step_pull_cc(paths: dict, cc_tag: str, res: BoxResult, dry_run: bool, force_cc: bool = False) -> None:
    """Step 3: converge the Command Center checkout to latest origin/main.

    The compatibility tag remains an input to the minimum-version contract, but
    it is not a deployment target. Checking out that historical tag here used to
    undo the root updater's successful main refresh and leave every fleet roll
    detached on stale code. The Command Center's own update.sh is the canonical
    state-preserving branch/build/health path, so invoke it only when the root
    updater has not already completed convergence, then independently assert the
    post-condition.
    """
    if dry_run:
        res.step_skip("pull-cc")
        return

    cc_dir = paths.get("cc_dir")
    if not cc_dir:   # reported by client name; the box's other steps still run
        res.step_skip("pull-cc", CC_NOT_FOUND)
        return
    if not Path(cc_dir).is_dir():
        res.step_fail("pull-cc", f"CC dir not found: {cc_dir}")
        return
    try:
        from cc_runtime_preflight import check_node, assert_cc_package, check_checkout
        check_node()
        why = None if os.environ.get("FLEET_REFRESH_ROOT", "").strip() else cc_pm2_problem()
        if why:
            res.step_fail("pull-cc", f"{why}. Nothing was changed.")
            return
        load_warning(res)
        subprocess.run(
            # Explicit refspec: a clone whose configured refspec names only a tag
            # (seen on client boxes) leaves origin/main stale on a bare `fetch origin main`.
            ["git", "-C", str(cc_dir), "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main"],
            check=True, capture_output=True, timeout=60,
        )

        # CC_UPDATE_TARGET: the roll's Command Center commit, resolved once by
        # fleet-refresh.sh, so a merge landing mid-roll never reaches the boxes
        # that update after it. Exported, so update.sh honours it too.
        target_ref = os.environ.get("CC_UPDATE_TARGET", "").strip() or "origin/main"
        target = subprocess.run(
            ["git", "-C", str(cc_dir), "show", f"{target_ref}:package.json"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        assert_cc_package(json.loads(target.stdout))

        def current_on_main() -> bool:
            branch = subprocess.run(
                ["git", "-C", str(cc_dir), "symbolic-ref", "--quiet", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if branch.returncode != 0 or branch.stdout.strip() != "main":
                return False
            ancestry = subprocess.run(
                ["git", "-C", str(cc_dir), "merge-base", "--is-ancestor", target_ref, "HEAD"],
                capture_output=True, timeout=10,
            )
            return ancestry.returncode == 0

        if not current_on_main():
            updater = Path(cc_dir) / "update.sh"
            if not updater.is_file():
                res.step_fail(
                    "pull-cc",
                    f"Command Center checkout is not current on main and canonical updater is missing: {updater}",
                )
                return
            update_env = {**os.environ, "CC_APP_DIR": str(cc_dir)}
            # Run origin/main's updater, not the live checkout's: the target's
            # update.sh builds beside the running release and promotes it
            # (zero-downtime), so the live tree is never moved before the build.
            target = subprocess.run(["git", "-C", str(cc_dir), "show", f"{target_ref}:update.sh"],
                                    capture_output=True, text=True, timeout=30)
            with tempfile.NamedTemporaryFile("w", suffix="-cc-update.sh", delete=False) as fh:
                fh.write(target.stdout if target.returncode == 0 and target.stdout else updater.read_text())
            try:
                update_result = subprocess.run(
                    ["bash", fh.name], cwd=str(cc_dir), env=update_env,
                    capture_output=True, text=True, timeout=ATOMIC_DEPLOY_TIMEOUT + 600,
                )
            finally:
                os.unlink(fh.name)
            if update_result.returncode != 0:
                detail = (update_result.stdout + update_result.stderr).strip()[-300:]
                res.step_fail(
                    "pull-cc",
                    f"canonical Command Center update failed (exit {update_result.returncode}): {detail}",
                )
                return

        if not current_on_main():
            res.step_fail(
                "pull-cc",
                f"post-update assertion failed: checkout is not main with latest origin/main (compatibility tag {cc_tag} is not a deploy target)",
            )
            return
        check_checkout(Path(cc_dir))
        res.step_ok("pull-cc")
    except subprocess.CalledProcessError as e:
        res.step_fail("pull-cc", f"git failed (exit {e.returncode}): {e.stderr[:200] if e.stderr else ''}")
    except subprocess.TimeoutExpired:
        res.step_fail("pull-cc", "git operation timed out")
    except Exception as e:
        res.step_fail("pull-cc", str(e))


def _cc_node(cc_dir: Path) -> str:
    """The node that can load this Command Center's native modules. The PATH
    node is often the OpenClaw runtime's (a newer ABI): better-sqlite3 built
    for the Command Center's node then fails to load and the duck test dies in
    its first setup step on a perfectly healthy box. Prefer the node of the
    process serving the Command Center, then pm2's, then PATH."""
    cands = []
    for pid in _port_pids(int(os.environ.get("CC_PORT") or 4000)):
        try:
            cands.append(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            m = re.search(r"^n(/\S*/node)$", _run_out(["lsof", "-a", "-p", str(pid), "-d", "txt", "-Fn"]), re.M)
            if m:
                cands.append(m.group(1))
    for name in _CC_PM2_NAMES:
        for pid in _run_out(["pm2", "pid", name]).split():
            try:
                cands.append(os.readlink(f"/proc/{pid}/exe"))
            except OSError:
                pass
    cands += [shutil.which("node") or "node"]
    for node in dict.fromkeys(cands):
        try:
            if subprocess.run([node, "-e", "require('better-sqlite3')"], cwd=str(cc_dir),
                              capture_output=True, timeout=30).returncode == 0:
                return node
        except (OSError, subprocess.SubprocessError):
            continue
    return cands[-1]


def _run_duck_ci_test(cc_dir: Path, box: str) -> tuple[bool, str]:
    """
    Run the duck CI test (tests/e2e/duck-test.ts) in mock mode from the deployed
    CC checkout.  Returns (passed: bool, detail: str).

    duck-test.ts is a node:test + tsx test (NOT a bash script), and its own
    header documents the canonical invocation:

        node --import tsx --test tests/e2e/duck-test.ts

    This is the same harness the repo's package.json "test:unit" script uses
    (`node --import tsx --test tests/unit/*.test.ts`).  Mock mode is the DEFAULT
    behaviour of the test (real KIE is opt-in via DUCK_E2E_USE_REAL_KIE=1), so
    there is NO `--mock` flag to pass — passing one is rejected by node:test.

    Exit 0 = green.  Any non-zero exit = red (blocks deploy).
    stdout+stderr are captured and the first 200 chars returned as detail.

    The test stands up a Next.js server (next start if a .next build exists,
    else next dev) and runs the full pipeline, so the timeout is generous.
    """
    duck_test = cc_dir / "tests" / "e2e" / "duck-test.ts"
    if not duck_test.is_file():
        return False, f"duck-test.ts not found at {duck_test} (B.3 preflight should have caught this)"

    node = _cc_node(cc_dir)
    try:
        result = subprocess.run(
            [node, "--import", "tsx", "--test", str(duck_test)],
            cwd=str(cc_dir),
            capture_output=True, text=True, timeout=300,
            env={**os.environ, "PATH": f"{Path(node).parent}{os.pathsep}{os.environ.get('PATH', '')}"},
        )
        detail = (result.stdout + result.stderr).strip()[:200]
        if result.returncode == 0:
            return True, detail or "duck-test.ts passed"
        else:
            return False, f"duck-test.ts exited {result.returncode}: {detail}"
    except subprocess.TimeoutExpired:
        return False, "duck-test.ts timed out after 300s"
    except Exception as exc:
        return False, f"duck-test.ts failed to launch: {exc}"


# atomic-deploy.sh refuses bash < 4 (exit 2) and macOS /bin/bash is 3.2, which
# is what a non-login SSH PATH resolves. Same resolution as the Command Center's
# own update.sh.
_BASH4_CANDIDATES = ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", "bash")
# atomic-deploy.sh's own health window is up to ~18 min (36 x 30s); a shorter
# outer timeout would kill it mid-promotion.
ATOMIC_DEPLOY_TIMEOUT = 1800


def _bash4() -> Optional[str]:
    for cand in _BASH4_CANDIDATES:
        exe = shutil.which(cand)
        if not exe:
            continue
        try:
            v = subprocess.run([exe, "-c", 'echo "${BASH_VERSINFO[0]:-0}"'],
                               capture_output=True, text=True, timeout=10)
            if int((v.stdout or "0").strip() or 0) >= 4:
                return exe
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return None


def _run_atomic_deploy(cc_dir: Path, revision: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run the Command Center's atomic-deploy.sh against cc_dir.

    Exit contract (from atomic-deploy.sh): 0 green; 1 health failed and the
    prior build was restored; 2 pre-flight/build failed with the live build
    untouched (still serving); 3 health indeterminate, not rolled back.
    """
    bash = _bash4()
    if not bash:
        return subprocess.CompletedProcess([], 2, "", "no bash 4+ found for atomic-deploy.sh "
                                           f"(tried {', '.join(_BASH4_CANDIDATES)})")
    cmd = [bash, str(cc_dir / "scripts" / "atomic-deploy.sh"), "--app-dir", str(cc_dir)]
    if revision:
        cmd += ["--revision", revision]
    return subprocess.run(cmd, cwd=str(cc_dir), capture_output=True, text=True,
                          timeout=ATOMIC_DEPLOY_TIMEOUT,
                          env={**os.environ, "CC_APP_DIR": str(cc_dir)})


def _served_build_current(cc_dir: Path) -> bool:
    """The Command Center's own build-inventory.sh --verify (the check cc-start
    and atomic-deploy use): the served .next was built from this checkout."""
    inv = cc_dir / "scripts" / "lib" / "build-inventory.sh"
    if not inv.is_file():
        return False
    try:
        return subprocess.run([_bash4() or "bash", str(inv), "--verify", str(cc_dir)],
                              capture_output=True, timeout=180).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def step_build_cc(paths: dict, res: BoxResult, dry_run: bool, local: bool = False) -> None:
    """
    Step 4: invoke scripts/atomic-deploy.sh from the deployed CC checkout.

    atomic-deploy.sh owns the full build+serve sequence (npm ci / npm install,
    npm run build, pm2 restart).  This step calls it synchronously and checks
    its exit code.  After atomic-deploy.sh reports success the duck CI test
    (node --import tsx --test tests/e2e/duck-test.ts) is run as a post-deploy
    green requirement; failure of the duck test fails this step.

    REMOVED: the detached Popen / npm-run-build-into-live-.next path is gone.
    That code path is not reachable.  atomic-deploy.sh is the ONLY deploy
    mechanism from this function.

    WAVE-5 SAFETY GATE is PRESERVED UNWEAKENED at the top of this function.
    """
    # WAVE-5 SAFETY GATE — runs unconditionally (before dry_run skip).
    # Blocks Command Center deploy until B.1+B.2+B.3 are merged to origin/main.
    wave5_deploy_preflight()

    if dry_run:
        res.step_skip("build-cc")
        res.step_skip("build-cc-duck-test")
        return

    cc_dir = paths.get("cc_dir")
    if not cc_dir:   # reported by client name; the box's other steps still run
        res.step_skip("build-cc", CC_NOT_FOUND)
        return
    if not Path(cc_dir).is_dir():
        res.step_fail("build-cc", f"CC dir not found: {cc_dir}")
        return

    cc_dir = Path(cc_dir)

    try:
        from cc_runtime_preflight import check_node, check_checkout
        check_node()
        check_checkout(cc_dir)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        res.step_fail("build-cc", f"CC compatibility preflight failed: {exc}")
        return

    # Already serving a build of exactly this checkout (update.sh / the installer
    # deployed it minutes ago): another full rebuild + restart gains nothing and
    # risks the Command Center (a spare redeploy failed its health check on a
    # client Mac and had to roll back).
    if _served_build_current(cc_dir) and hc_cc_health({"cc_dir": cc_dir}, times=1)["status"] == "pass":
        _info("  Command Center already serves a build of this checkout -- no rebuild")
        res.step_ok("build-cc")
        duck_passed, duck_detail = _run_duck_ci_test(cc_dir, res.box)
        res.steps["build-cc-duck-test"] = "pass" if duck_passed else f"fail: {duck_detail}"
        if not duck_passed:
            res.step_fail("build-cc", f"duck CI test FAILED: {duck_detail}")
        return

    # Resolve atomic-deploy.sh from the deployed CC checkout (CC main).
    atomic_deploy = cc_dir / "scripts" / "atomic-deploy.sh"
    if not atomic_deploy.is_file():
        res.step_fail(
            "build-cc",
            f"atomic-deploy.sh not found at {atomic_deploy}. "
            f"B.2 preflight should have blocked this deploy — check wave5_deploy_preflight().",
        )
        return

    # Invoke atomic-deploy.sh synchronously.
    # Exit contract honoured:
    #   0  → success
    #   1  → fail this box (step_fail)
    #   3  → transient; caller should retry then mark UNKNOWN (never destructive)
    try:
        deploy_result = _run_atomic_deploy(cc_dir)
        deploy_detail = (deploy_result.stdout + deploy_result.stderr).strip()[:300]

        if deploy_result.returncode == 1:
            res.step_fail("build-cc", f"atomic-deploy.sh exited 1 (deploy failed): {deploy_detail}")
            return

        if deploy_result.returncode == 3:
            # Transient error: surface via step_fail with a marker the caller
            # can detect; never destructive.  Exit code 3 propagates to the
            # box result so fleet-refresh.sh can retry then mark UNKNOWN.
            res.step_fail("build-cc", f"[exit-3] atomic-deploy.sh transient error: {deploy_detail}")
            return

        if deploy_result.returncode == 2:
            # Built in a private candidate dir; the live build was never touched.
            res.step_fail("build-cc", "atomic-deploy.sh exited 2 (pre-flight/build failed; "
                                      f"previous build left serving): {deploy_detail}")
            return

        if deploy_result.returncode != 0:
            res.step_fail("build-cc", f"atomic-deploy.sh exited {deploy_result.returncode}: {deploy_detail}")
            return

    except subprocess.TimeoutExpired:
        res.step_fail("build-cc", f"atomic-deploy.sh timed out after {ATOMIC_DEPLOY_TIMEOUT}s")
        return
    except Exception as exc:
        res.step_fail("build-cc", f"atomic-deploy.sh failed to launch: {exc}")
        return

    # Post-deploy green requirement: duck CI test in mock mode.
    duck_passed, duck_detail = _run_duck_ci_test(cc_dir, res.box)
    res.steps["build-cc-duck-test"] = "pass" if duck_passed else f"fail: {duck_detail}"
    if not duck_passed:
        res.step_fail("build-cc", f"duck CI test (post-deploy) FAILED: {duck_detail}")
        return

    _ok(f"  duck CI test passed: {duck_detail}")
    res.step_ok("build-cc")


def step_restart_cc(paths: dict, res: BoxResult, dry_run: bool) -> None:
    """
    Step 5: ensure the Command Center is running after the build step.

    Delegates to scripts/atomic-deploy.sh from the deployed CC checkout.
    atomic-deploy.sh is idempotent: if the CC is already running from the
    build step it confirms the process is healthy; if it is not running it
    starts it.

    Exit contract (honoured identically to step_build_cc):
        0  → success (CC is up and healthy)
        1  → fail this box
        3  → transient; caller retries then marks UNKNOWN — never destructive

    REMOVED: raw pm2 restart / pm2 start calls that bypassed atomic-deploy.sh.
    REMOVED: build-running / build-failed marker checks (detached build is gone).

    Safety guard: NEVER issue `openclaw gateway restart` — this step only
    touches the Command Center process via atomic-deploy.sh, not the OpenClaw
    gateway process (Mac err 125 guard).

    WAVE-5 SAFETY GATE is PRESERVED UNWEAKENED at the top of this function.
    """
    # WAVE-5 SAFETY GATE — runs unconditionally (before dry_run skip).
    # Blocks Command Center restart until B.1+B.2+B.3 are merged to origin/main.
    wave5_deploy_preflight()

    if dry_run:
        res.step_skip("restart-cc")
        return

    cc_dir = paths.get("cc_dir")
    if not cc_dir:   # reported by client name; the box's other steps still run
        res.step_skip("restart-cc", CC_NOT_FOUND)
        return
    if not Path(cc_dir).is_dir():
        res.step_fail("restart-cc", f"CC dir not found: {cc_dir}")
        return

    cc_dir = Path(cc_dir)

    try:
        from cc_runtime_preflight import check_node, check_checkout
        check_node()
        check_checkout(cc_dir)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        res.step_fail("restart-cc", f"CC compatibility preflight failed: {exc}")
        return

    # Serving a build of this checkout and healthy: nothing to restart.
    if _served_build_current(cc_dir) and hc_cc_health({"cc_dir": cc_dir}, times=1)["status"] == "pass":
        _info("  Command Center already serves a build of this checkout and is healthy -- no restart")
        res.step_ok("restart-cc")
        return

    # Resolve atomic-deploy.sh from the deployed CC checkout (CC main).
    atomic_deploy = cc_dir / "scripts" / "atomic-deploy.sh"
    if not atomic_deploy.is_file():
        res.step_fail(
            "restart-cc",
            f"atomic-deploy.sh not found at {atomic_deploy}. "
            f"B.2 preflight should have blocked this deploy — check wave5_deploy_preflight().",
        )
        return

    # Invoke atomic-deploy.sh synchronously.
    try:
        restart_result = _run_atomic_deploy(cc_dir)
        restart_detail = (restart_result.stdout + restart_result.stderr).strip()[:300]

        if restart_result.returncode == 1:
            res.step_fail("restart-cc", f"atomic-deploy.sh exited 1 (restart failed): {restart_detail}")
            return

        if restart_result.returncode == 3:
            # Transient error: never destructive.  Surface for retry logic.
            res.step_fail("restart-cc", f"[exit-3] atomic-deploy.sh transient error: {restart_detail}")
            return

        if restart_result.returncode != 0:
            res.step_fail("restart-cc", f"atomic-deploy.sh exited {restart_result.returncode}: {restart_detail}")
            return

    except subprocess.TimeoutExpired:
        res.step_fail("restart-cc", f"atomic-deploy.sh timed out after {ATOMIC_DEPLOY_TIMEOUT}s")
        return
    except Exception as exc:
        res.step_fail("restart-cc", f"atomic-deploy.sh failed to launch: {exc}")
        return

    res.step_ok("restart-cc")


# Each reset wipes the owner's live Telegram conversation. It used to run before
# the health gate, again inside every fix attempt and again on rollback: one
# owner's chat was reset 10 times in 3.5 hours. Now: once per roll, after the
# gate has settled, and never within RESET_MIN_INTERVAL of the last one.
RESET_MIN_INTERVAL = 30 * 60


def reset_ceo_once(paths: dict, res: BoxResult, dry_run: bool) -> None:
    if "sessions-reset-CEO" in res.steps:
        return   # already decided this run
    key = _resolve_ceo_session_key(paths)
    marker = Path(paths["root"]) / "fleet-refresh" / ".ceo-session-reset.json"
    try:
        last = json.loads(marker.read_text())
    except (OSError, ValueError):
        last = {}
    if key and not dry_run and time.time() - float(last.get(key) or 0) < RESET_MIN_INTERVAL:
        mins = int((time.time() - float(last[key])) // 60)
        res.steps["sessions-reset-CEO"] = f"ok:skipped -- this session was reset {mins} min ago"
        return
    step_sessions_reset_ceo(key, res, dry_run)
    if key and res.steps.get("sessions-reset-CEO") == "ok":
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({**last, key: time.time()}))
        except OSError:
            pass


def step_sessions_reset_ceo(
    ceo_session_key: Optional[str],
    res: BoxResult,
    dry_run: bool,
) -> None:
    """
    Step 6: reset the CEO/main session so the next message rebuilds from disk.

    Uses `openclaw gateway call sessions.reset` — a gateway CALL, never a
    gateway process restart (Mac err 125 guard: see the spec).

    Bug-fix (v11.18.1): the public sessions.reset RPC params schema
    (SessionsResetParamsSchema in openclaw/openclaw
    packages/gateway-protocol/src/schema/sessions.ts) is
    `reason?: 'new' | 'reset'` with additionalProperties:false. The old
    `reason: "fleet-refresh"` failed TypeBox validation, so the gateway
    rejected the call and every box's CEO reset fails-closed on 2026.6.1.
    `reason` is OPTIONAL, so we omit it. We also parse the stdout envelope
    FIRST so a harmless plugin-blocked warning (exit 1, `ok:true`) does not
    false-fail the step; a genuine `ok:false` / unparseable stdout on a
    non-zero exit still fails.
    """
    if dry_run:
        res.step_skip("sessions-reset-CEO")
        return

    # SAFETY GUARD: explicit assertion that we never call gateway restart
    # (the spec requires this guard in code, not just docs)
    _info("  Issuing sessions.reset (gateway call — NOT gateway restart)")

    if not ceo_session_key:
        res.steps["sessions-reset-CEO"] = ("ok:no owner session yet on the Telegram-bound agent or main "
                                          "-- nothing stale to reset")
        return

    try:
        result = subprocess.run(
            ["openclaw", "gateway", "call", "sessions.reset",
             "--params", json.dumps({"key": ceo_session_key})],
            capture_output=True, text=True, timeout=30
        )
        if result.stderr.strip():
            _warn(f"  sessions.reset stderr: {result.stderr[:200]}")

        # Parse stdout FIRST — the JSON-RPC envelope is authoritative.
        stdout = (result.stdout or "").strip()
        resp = None
        if stdout:
            try:
                resp = json.loads(stdout)
            except Exception:
                resp = None

        if isinstance(resp, dict) and "ok" in resp:
            if resp.get("ok") is True and "error" not in resp:
                res.step_ok("sessions-reset-CEO")
                return
            res.step_fail("sessions-reset-CEO", f"gateway call returned error: {resp}")
            return

        # No parseable ok envelope: trust the exit code only here.
        if result.returncode != 0:
            res.step_fail("sessions-reset-CEO",
                f"sessions.reset failed (exit {result.returncode}, no ok=true envelope): "
                f"{result.stderr[:200]}")
            return

        # exit 0 with a non-JSON response is OK (older gateways).
        res.step_ok("sessions-reset-CEO")
    except subprocess.TimeoutExpired:
        res.step_fail("sessions-reset-CEO", "sessions.reset timed out")
    except FileNotFoundError:
        res.step_fail("sessions-reset-CEO", "openclaw not on PATH")
    except Exception as e:
        res.step_fail("sessions-reset-CEO", str(e))


def step_embedding_health(
    paths: dict,
    shared_utils: Path,
    res: BoxResult,
) -> dict:
    """
    Step 8 (B.6): Run the per-box embedding-health check across all three indexes.

    Covers:
      Index 1 — OpenClaw memory search (agents.defaults.memorySearch + sqlite stamp)
      Index 2 — Persona gemini-index  (gemini-embedding-2 @3072)
      Index 3 — CC SOP embeddings     (mission-control.db)

    For each index three legs are checked:
      (a) Embedding-capable provider configured + key present + cheap smoke embed.
          Ollama Cloud is NEVER embedding-capable — hard rule with no exceptions.
      (b) Stamped provider/model/dim matches current config; mismatch = FLAG RE-INDEX.
      (c) Generative provider is NOT assumed to serve embeddings.

    Also verifies memorySearch fallback config (PRD 2.6).

    This step is READ-ONLY (no mutations).  It runs in EVERY mode:
      - Wave-5 apply pass (per-box in fleet_refresh_runner.py)
      - Sunday cron --verify-only pass (fleet-refresh.sh)
      - Standalone:  python3 shared-utils/embedding_health.py [--json]

    Returns the embedding-health result dict.  Always records the result in
    res.steps["embedding-health"] so the fleet summary reflects the outcome.

    N32 rule: a model-provider change is NOT complete until this step passes.
    """
    sys.path.insert(0, str(shared_utils))
    try:
        from embedding_health import run_embedding_health, load_openclaw_json  # type: ignore
    except ImportError as exc:
        msg = f"embedding_health.py not found in shared-utils: {exc}"
        res.step_fail("embedding-health", msg)
        return {"overall": "fail", "errors": [msg]}

    openclaw_root = paths.get("root", Path("/nonexistent"))
    cc_dir        = paths.get("cc_dir")

    # Load openclaw.json
    openclaw_json: dict = {}
    try:
        openclaw_json = load_openclaw_json(openclaw_root)
    except Exception as e:
        _warn(f"embedding-health: could not load openclaw.json: {e}")

    try:
        emb_result = run_embedding_health(
            openclaw_root=Path(openclaw_root),
            openclaw_json=openclaw_json,
            cc_dir=Path(cc_dir) if cc_dir else None,
        )
    except Exception as exc:
        msg = f"embedding_health.run_embedding_health raised: {exc}"
        res.step_fail("embedding-health", msg)
        return {"overall": "fail", "errors": [msg]}

    overall = emb_result.get("overall", "fail")

    if overall == "pass":
        res.steps["embedding-health"] = "pass"
        _ok(f"  embedding-health: PASS (all 3 indexes, 3 legs each)")
    elif overall == "warn":
        res.steps["embedding-health"] = f"warn:{'; '.join(emb_result.get('warnings', []))[:120]}"
        _warn(f"  embedding-health: WARN — {len(emb_result.get('warnings', []))} warning(s)")
    else:
        errs = emb_result.get("errors", [])
        summary = "; ".join(errs[:2])
        res.steps["embedding-health"] = f"failed:{summary[:200]}"
        for e in errs:
            res.errors.append(f"embedding-health: {e}")
        _err(f"  embedding-health: FAIL — {len(errs)} error(s)")
        for e in errs:
            _err(f"    {e}")

    return emb_result


def step_persona_embedding_drift(
    paths: dict,
    shared_utils: Path,
    res: BoxResult,
) -> dict:
    """
    Step 8b (A-U8): scheduled live drift check — personas/ directory count on
    disk vs. indexed-persona count in gemini-index.sqlite, on the operator's
    own box. A persona carrying an honest embedding-receipt.json (status
    'deferred' — written by 22-.../pipeline/orchestrator.py Phase 5 when this
    box's own Gemini key is absent/invalid) is NOT drift; only an UNEXPLAINED
    disk-vs-index gap is flagged. Emits exactly ONE advisory record per run
    (never one per persona) — res.steps["persona-embedding-drift"] is what the
    fleet summary / operator card ingestion reads.

    READ-ONLY (no mutations). Runs alongside step_embedding_health in EVERY
    mode (Wave-5 apply pass + Sunday cron --verify-only pass). NON-GATING: a
    divergence is surfaced as an advisory ("degraded:...", never containing
    the substring "failed") — it never marks the box refresh itself failed
    (mirrors A-U12's non-gating posture for persona-observability advisories).
    """
    sys.path.insert(0, str(shared_utils))
    try:
        from persona_embedding_drift_probe import run_drift_check  # type: ignore
    except ImportError as exc:
        msg = f"persona_embedding_drift_probe.py not found in shared-utils: {exc}"
        res.steps["persona-embedding-drift"] = f"skip:{msg}"
        _warn(f"  persona-embedding-drift: SKIP — {msg}")
        return {"verdict": "n/a", "reason": msg}

    workspace = paths.get("workspace")
    if not workspace:
        msg = "no workspace path resolved for this box"
        res.steps["persona-embedding-drift"] = f"skip:{msg}"
        _warn(f"  persona-embedding-drift: SKIP — {msg}")
        return {"verdict": "n/a", "reason": msg}

    personas_dir = Path(workspace) / "data" / "coaching-personas" / "personas"
    db_path = Path(workspace) / "data" / "coaching-personas" / "gemini-index.sqlite"

    try:
        result = run_drift_check(personas_dir=personas_dir, db_path=db_path, box=res.box)
    except Exception as exc:
        msg = f"persona_embedding_drift_probe.run_drift_check raised: {exc}"
        res.steps["persona-embedding-drift"] = f"skip:{msg}"
        _warn(f"  persona-embedding-drift: SKIP — {msg}")
        return {"verdict": "n/a", "reason": msg}

    verdict = result.get("verdict", "n/a")
    if verdict == "healthy":
        res.steps["persona-embedding-drift"] = "pass"
        _ok(f"  persona-embedding-drift: PASS — {result.get('message', '')}")
    elif verdict == "degraded":
        # Advisory, non-gating: intentionally NOT "failed:..." — see docstring.
        res.steps["persona-embedding-drift"] = f"degraded:{result.get('message', '')[:200]}"
        _warn(f"  persona-embedding-drift: DEGRADED (operator card) — {result.get('message', '')}")
    else:
        res.steps["persona-embedding-drift"] = f"n/a:{result.get('reason', '')[:200]}"
        _info(f"  persona-embedding-drift: N/A — {result.get('reason', '')}")

    return result


def _scrub_gating_token(text: str) -> str:
    """Strip the one token that would turn an ADVISORY step value into a
    GATING one.

    run_box decides the box's verdict with a plain SUBSTRING test —
    `any("failed" in str(v) for v in res.steps.values())` — over every step
    value, with no notion of which steps are advisory. A-U12's non-gating
    contract (ACCEPT (a): "the box's health status is UNCHANGED by any value
    of it") therefore cannot rest on wording discipline upstream: this step's
    reason text is FREE-FORM and interpolates arbitrary exception messages
    (e.g. the probe's own "selector module unavailable/could not load: {exc}",
    where {exc} is whatever Python raised). Any reason that merely MENTIONS
    the word would flip the box to partial/failed — a false failure fleet-wide
    on every box where the probe degrades for a reason worded that way.

    So scrub at the boundary that writes res.steps, where the guarantee is
    actually enforceable. Case-insensitive for future-proofing; run_box's
    current test is lowercase-exact, so lowercase alone is what gates today.
    """
    return _GATING_TOKEN_RE.sub("errored", text)


def step_persona_grounding_health(
    paths: dict,
    shared_utils: Path,
    res: BoxResult,
) -> dict:
    """
    Step 8c (A-U12, master id U12): "Blend observability" ONB probe — reads
    persona_blend.py's match-score-distribution log (previously had NO
    reader — this closes that gap) and detects the 5-layer selector's
    grounding layers falling back to their neutral floor (company-config.json
    absent, or the semantic_task_fit / llm_score modules not importable).
    Emits exactly ONE advisory record per run — res.steps[
    "persona-grounding-health"] is what the fleet summary / Command Center's
    deep-health check reads (this is the "(+ ONB probe)" half of the
    both-repo unit; the Command Center owns the deep-health RESPONSE shape
    and the persona_grounding_degraded board chip/event on its own train).

    READ-ONLY (no mutations). Runs alongside step_persona_embedding_drift.
    NON-GATING BY DESIGN (see persona_grounding_health_probe.py's own
    ADVISORY DOCTRINE): a degraded grounding verdict is surfaced as an
    advisory ("degraded:...", never containing the substring "failed") — it
    never marks the box refresh itself failed.
    """
    sys.path.insert(0, str(shared_utils))
    try:
        from persona_grounding_health_probe import run_probe  # type: ignore
    except ImportError as exc:
        msg = f"persona_grounding_health_probe.py not found in shared-utils: {exc}"
        res.steps["persona-grounding-health"] = f"skip:{msg}"
        _warn(f"  persona-grounding-health: SKIP — {msg}")
        return {"grounding": {"degraded": False}, "reason": msg}

    try:
        result = run_probe(paths=paths, box=res.box)
    except Exception as exc:
        msg = f"persona_grounding_health_probe.run_probe raised: {exc}"
        res.steps["persona-grounding-health"] = f"skip:{msg}"
        _warn(f"  persona-grounding-health: SKIP — {msg}")
        return {"grounding": {"degraded": False}, "reason": msg}

    grounding = result.get("grounding", {})
    if grounding.get("degraded"):
        # Advisory, non-gating: intentionally NOT "failed:..." — see docstring.
        reasons = "; ".join(grounding.get("reasons", []))[:200]
        res.steps["persona-grounding-health"] = f"degraded:{_scrub_gating_token(reasons)}"
        _warn(f"  persona-grounding-health: DEGRADED (advisory) — {reasons}")
    else:
        res.steps["persona-grounding-health"] = "pass"
        pm = result.get("persona_match", {})
        _ok(f"  persona-grounding-health: PASS — persona_match count={pm.get('count', 0)}")

    return result


# ── Provisioning-completeness gate (false-success closer) ─────────────────────
#
# run_box marks a box "ok" (PASS) when NO step string contains "failed". Before
# this gate the substantive per-box checks were CC serving (build/restart+duck),
# SOP coverage (embedding-health, Index-3), and the loaded-marker verify. NONE
# verified that provisioning actually LANDED: a box could carry the full SOP
# corpus yet ship PLACEHOLDER branding, a STALE/MISSING onboarding version stamp,
# an EMPTY departments.json, and ZERO personas — and still report PASS. This step
# closes that hole. It is GATING and reads LIVE box state through the SAME path
# authority every consumer uses (get_openclaw_paths via _load_paths), honoring
# the fixture redirect (FLEET_REFRESH_ROOT) so it is testable without a box.

# Literal placeholder company names shipped by the provisioning templates —
# rejected SPECIFICALLY so a legitimately-named client is never falsely failed:
#   "Your Company"       — Command Center config/company-config.json default
#                          (blackceo-command-center) + Skill-37 closeout defaults
#   "Your Company Name"  — 23-ai-workforce-blueprint/scripts/workforce-config.json
#                          non-interactive build template (company_name)
# Compared case-insensitively after trimming. An empty/whitespace name is also a
# FAIL (the unprovisioned state) but is reported distinctly from a placeholder.
PLACEHOLDER_COMPANY_NAMES = frozenset({"your company", "your company name"})

# The checks that GATE the verdict. SOP + CC-SERVE are REPORTED in the
# breakdown but stay gated where they already were (embedding-health / build-cc)
# — this ADDS verification, it never removes a gate.
_PROVISIONING_HARD_CHECKS = ("VERSION", "BRANDING", "DEPARTMENTS", "PERSONAS",
                             "ROLE-FLOOR")

# ── ROLE-FLOOR: the live departments workspace ────────────────────────────────
# DEPARTMENTS reads departments.json, which lives in the ZHC company dir
# (master_files/zero-human-company/<slug>/). The role folders it promises live in
# a COMPLETELY DIFFERENT tree — the live departments workspace. Verifying only the
# JSON is why a box could lose every role folder on disk and still be recorded as
# a clean, completed roll.
#
# Fallback candidate list, probed only AFTER the runner's own path authority
# (paths["workspace"]) — same set the fleet floor-prover probes, because those are
# the layouts that actually exist on the fleet. Measured 2026-07-21 across the 30
# reachable boxes, every one resolves to one of:
#     ~/.openclaw/workspace/departments      /data/.openclaw/workspace/departments
#     ~/clawd/departments                    /data/clawd/departments
# The two /data/clawd + ~/clawd forms are LEGACY trees that paths["workspace"]
# does NOT derive, so omitting them here would false-FAIL real, healthy boxes.
_DEPT_WS_CANDIDATES = (
    "~/clawd/departments",
    "~/.openclaw/workspace/departments",
    "~/.openclaw/workspace/zero-human-company/departments",
    "/data/.openclaw/workspace/departments",
    "/data/.openclaw/workspace/zero-human-company/departments",
    "/data/clawd/departments",
)

# Hard ceiling on the role scan so an enormous / looped tree cannot stall a roll.
_ROLE_SCAN_MAX_ENTRIES = 20000

# Files that live at DEPARTMENT level and are therefore NOT a role. Everything
# else is counted, deliberately: role markers are NOT uniform across the fleet
# (canonical boxes use IDENTITY.md, others how-to.md, and at least one build uses
# governing-personas.md + numbered How-to-NN.md), so this check is convention-
# AGNOSTIC on purpose. A marker-specific test would false-FAIL a real workforce.
_DEPT_LEVEL_MD = frozenset({
    "governing-personas.md", "readme.md", "agents.md", "heartbeat.md",
    "memory.md", "soul.md", "tools.md", "identity.md", "how-to.md",
    "org-chart.md", "_sops.md",
})


def _resolve_departments_workspace(paths: dict, pp: dict) -> Optional[Path]:
    """
    Resolve the LIVE departments workspace — the tree that actually holds role
    folders. Never raises; returns None only when NO candidate exists on disk.

    Order: the runner's own path authority first (so the gate reads the same tree
    every other check in this module reads), then the company dir, then the fleet
    fallback layouts. Path.is_dir() FOLLOWS symlinks by design — on several fleet
    boxes `departments` IS a symlink (e.g. -> workspaces/command-center, or ->
    zero-human-company/<brand>/departments), and a non-following probe reports
    those healthy boxes as empty.

    In fixture mode (FLEET_REFRESH_ROOT set) the absolute ~ and /data candidates
    are SKIPPED so a test can never accidentally resolve — and pass against — the
    real live workspace of the machine running the test.
    """
    workspace = Path(paths.get("workspace") or "/nonexistent")
    ordered: list[Path] = [
        workspace / "departments",
        workspace / "zero-human-company" / "departments",
    ]
    company_dir = pp.get("company_dir")
    if company_dir:
        ordered.append(Path(company_dir) / "departments")
    if not os.environ.get("FLEET_REFRESH_ROOT", "").strip():
        ordered += [Path(os.path.expanduser(c)) for c in _DEPT_WS_CANDIDATES]

    seen: set[str] = set()
    for cand in ordered:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        try:
            if cand.is_dir():
                return cand
        except OSError:
            continue
    return None


def _count_role_artifacts(ws: Path) -> tuple[int, int]:
    """
    Count (department_dirs, role_artifacts) under the live departments workspace.

    A ROLE ARTIFACT is either:
      * a sub-directory of <dept>/ (or <dept>/roles/) holding at least one .md
        file — covers <dept>/<role>/IDENTITY.md, <dept>/<role>/how-to.md,
        <dept>/NN-<role>/governing-personas.md, and <dept>/roles/<role>/*.md; or
      * a .md file directly under <dept>/ whose name is not a department-level
        marker — covers the flat <dept>/<role>.md layout.

    Deliberately PERMISSIVE. This is a floor-LOSS detector, not a completeness
    audit: completeness is what qc-completeness.sh and the floor-prover measure.
    Erring permissive is what keeps it from false-failing the many legitimate
    on-fleet layouts. Never raises.
    """
    dept_dirs = 0
    roles = 0
    budget = _ROLE_SCAN_MAX_ENTRIES
    try:
        entries = sorted(ws.iterdir())
    except OSError:
        return 0, 0
    for dept in entries:
        try:
            if not dept.is_dir():
                continue
        except OSError:
            continue
        dept_dirs += 1
        for base in (dept, dept / "roles"):
            try:
                if base is not dept and not base.is_dir():
                    continue
                children = sorted(base.iterdir())
            except OSError:
                continue
            for child in children:
                budget -= 1
                if budget <= 0:
                    return dept_dirs, roles
                try:
                    if child.is_dir():
                        for grand in child.iterdir():
                            budget -= 1
                            if grand.name.lower().endswith(".md") and grand.is_file():
                                roles += 1
                                break
                            if budget <= 0:
                                return dept_dirs, roles
                    elif (base is dept
                          and child.name.lower().endswith(".md")
                          and child.name.lower() not in _DEPT_LEVEL_MD):
                        roles += 1
                except OSError:
                    continue
    return dept_dirs, roles


def _prov_read_json(path) -> Optional[Any]:
    """Read+parse a JSON file. Returns None on any absence/parse error."""
    try:
        if path and Path(path).is_file():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _existing_or_owner(paths: dict, p: Path) -> Path:
    """p, or the same file in the owner agent's own workspace when only that one
    exists (a box whose CEO agent runs from workspace-nova, not workspace)."""
    if p.exists() or "root" not in paths:
        return p
    ows = _owner_workspace(paths)
    alt = (ows / p.name) if ows else None
    return alt if alt and alt.exists() else p


def _resolve_provisioning_paths(paths: dict) -> dict:
    """
    Resolve the on-box provisioning artifacts the completeness gate reads.

    Works in BOTH modes:
      * real mode    — `paths` came from get_openclaw_paths(), which already
        carries departments_json / company_config / coaching_personas / build_state.
      * fixture mode — _load_paths() built a MINIMAL synthetic dict (via
        FLEET_REFRESH_ROOT); those artifact keys are ABSENT, so we derive them
        from the base roots exactly as detect_platform does.

    Never raises. Returned Paths are not guaranteed to exist on disk.
    """
    workspace = Path(paths.get("workspace", "/nonexistent"))
    company_root = Path(paths.get("company_root") or (workspace / "zero-human-company"))

    # company_dir: the active <slug>/ under company_root. Prefer an explicit key;
    # else pick the first child dir that actually carries a company-config.json or
    # departments.json (mirrors resolve_active_company_dir's "real workforce" pick).
    # A box can keep its workforce under workspace/zero-human-company/<slug>/
    # while get_openclaw_paths() points at a flat workspace/departments.json
    # that does not exist (DEPARTMENTS then failed falsely on a box with 30).
    # Prefer a <slug>/ that carries both files, then one carrying either.
    company_dir = paths.get("company_dir")
    if company_dir:
        company_dir = Path(company_dir)
    else:
        company_dir = None
        children = []
        for root in dict.fromkeys((company_root, workspace / "zero-human-company")):
            try:
                if root.is_dir():
                    children += [c for c in sorted(root.iterdir()) if c.is_dir()]
            except OSError:
                pass
        def has(c, n):
            return (c / n).is_file()
        for need in (2, 1):
            company_dir = next((c for c in children
                                if has(c, "company-config.json") + has(c, "departments.json") >= need), None)
            if company_dir:
                break

    def _pick(key: str, rel: str) -> Path:
        v = paths.get(key)
        if v and Path(v).exists():
            return Path(v)
        if company_dir:
            return company_dir / rel
        return Path(v) if v else (workspace / rel)

    coaching_personas = Path(
        paths.get("coaching_personas") or (workspace / "data" / "coaching-personas")
    )
    cc_dir = paths.get("cc_dir")
    cc_dir = Path(cc_dir) if cc_dir else None

    return {
        "company_dir":        company_dir,
        "departments_json":   _pick("departments_json", "departments.json"),
        "zhc_company_config": _pick("company_config", "company-config.json"),
        "coaching_personas":  coaching_personas,
        "personas_dir":       coaching_personas / "personas",
        "build_state":        _existing_or_owner(paths, Path(paths.get("build_state")
                                                         or (workspace / ".workforce-build-state.json"))),
        "cc_dir":             cc_dir,
        "cc_company_config":  (cc_dir / "config" / "company-config.json") if cc_dir else None,
        "cc_logo_config":     (cc_dir / "public" / "logo-config.json") if cc_dir else None,
    }


def _resolve_company_name(pp: dict) -> tuple[str, str]:
    """
    Resolve the box's company name from the strongest available live source.
    Returns (name, source_label); name is "" when NO source yields one.

    Order (first non-empty wins) — a real box has a real name in at least one:
      1. Command Center config/company-config.json  -> companyName
      2. ZHC <company_dir>/company-config.json       -> companyName|company_name|name
      3. workspace/.workforce-build-state.json       -> companyName
    """
    cc = _prov_read_json(pp.get("cc_company_config"))
    if isinstance(cc, dict):
        v = str(cc.get("companyName", "") or "").strip()
        if v:
            return v, "cc-config"
    zhc = _prov_read_json(pp.get("zhc_company_config"))
    if isinstance(zhc, dict):
        for k in ("companyName", "company_name", "name"):
            v = str(zhc.get(k, "") or "").strip()
            if v:
                return v, f"zhc-config.{k}"
    bs = _prov_read_json(pp.get("build_state"))
    if isinstance(bs, dict):
        v = str(bs.get("companyName", "") or "").strip()
        if v:
            return v, "build-state"
    return "", "none"


def step_provisioning_completeness(
    paths: dict,
    res: BoxResult,
    pinned_onboarding_tag: str,
) -> dict:
    """
    Step 8d: the provisioning-completeness gate (false-success closer).

    HARD-GATES the box on five provisioning invariants SOP coverage never proved,
    and REPORTS the two already-gated-elsewhere signals so the operator sees a
    full per-check breakdown:

      VERSION   (GATE)  — onboarding stamp present AND == the version being rolled
                          (cc-compat.onboardingVersion). Stale / missing / unknown
                          = FAIL, never a pass.
      BRANDING  (GATE)  — resolved company name is non-empty AND not a shipped
                          placeholder. When the CC config is present at the
                          resolved path, its logo-config.json must also be
                          present — but an EMPTY logoUrl is the DESIGNED text-SVG
                          fallback (useLogoUrl renders the company name) and is
                          NOT failed; only a missing/broken logo file fails.
      DEPTS     (GATE)  — departments.json exists and is a well-formed array. An
                          EMPTY array is the intended fresh-box default (PASS); the
                          authoritative completeness signal is ROLE-FLOOR, not the
                          array length.
      ROLE-FLOOR(GATE)  — when departments.json declares >=1 department, the LIVE
                          departments workspace must exist on disk AND hold >=1
                          role artifact. departments.json lives in the ZHC company
                          dir; the role folders live in a different tree, so DEPTS
                          alone let a box lose EVERY role folder and still record a
                          clean roll. Zero declared departments = n/a (the fresh-box
                          default), never a second failure on top of DEPTS.
      PERSONAS  (GATE)  — coaching-personas/personas holds >=1 persona dir with a
                          persona-blueprint.md (same definition the drift probe uses).
      SOP       (report)— mirrors res.steps["embedding-health"] (Index-3 CC SOP
                          coverage is gated there; kept, not weakened).
      CC-SERVE  (report)— mirrors res.board["cc_healthy"] (CC serving is gated by
                          build-cc / restart-cc + the post-deploy duck test; kept).

    READ-ONLY. Returns a per-check outcome dict. On ANY hard-check failure it
    records res.step_fail("provisioning-completeness", <breakdown>), which flips
    the box off "ok" via run_box's existing has_failures test — so no future roll
    can green-light an incompletely-provisioned box.
    """
    pp = _resolve_provisioning_paths(paths)
    checks: list[tuple[str, bool, str]] = []   # (name, ok, detail)

    # ── VERSION (gate) ────────────────────────────────────────────────────────
    stamp = str(res.onboarding_version or "unknown").strip()
    want = str(pinned_onboarding_tag or "unknown").strip()
    if stamp in ("", "unknown"):
        checks.append(("VERSION", False, f"stamp missing/unknown (want {want})"))
    elif stamp != want:
        checks.append(("VERSION", False, f"{stamp} != {want}"))
    else:
        checks.append(("VERSION", True, stamp))

    # ── BRANDING (gate) ───────────────────────────────────────────────────────
    name, src = _resolve_company_name(pp)
    norm = name.strip().lower()
    if not name:
        branding_ok, bdetail = False, "company name empty/unprovisioned (no config or build-state)"
    elif norm in PLACEHOLDER_COMPANY_NAMES:
        branding_ok, bdetail = False, f"placeholder company name {name!r} (src={src})"
    else:
        branding_ok, bdetail = True, f"{name!r} (src={src})"
    # Logo: only judged when the CC config is present at the resolved path (proof
    # the CC is provisioned THERE). Absent CC config -> logo is n/a (never a
    # false-FAIL when the CC checkout lives at a path we did not resolve).
    cc_cfg = pp.get("cc_company_config")
    if branding_ok and cc_cfg and Path(cc_cfg).is_file():
        logo = _prov_read_json(pp.get("cc_logo_config"))
        if not isinstance(logo, dict) or "logoUrl" not in logo:
            branding_ok = False
            bdetail += "; logo-config.json missing/invalid at provisioned CC"
        else:
            bdetail += ("; logo=set" if str(logo.get("logoUrl", "")).strip()
                        else "; logo=text-svg-fallback(ok)")
    checks.append(("BRANDING", branding_ok, bdetail))

    # ── DEPARTMENTS (gate) ────────────────────────────────────────────────────
    # An EMPTY departments.json is the INTENDED shipped default on a fresh box —
    # the same state ROLE-FLOOR treats as n/a. Keying this gate on emptiness
    # rejected a correctly provisioned fresh box, while a non-empty array satisfied
    # it without a single workspace being materialized. The authoritative
    # completeness signal is ROLE-FLOOR (the floor-prover result + the live
    # departments workspace on disk), not the length of this JSON array. So
    # DEPARTMENTS gates only on the file being a well-formed list; an empty array
    # is a valid fresh-box state, never a failure.
    # departments.json legitimately ships as a bare LIST *or* as an object
    # wrapping that list under "departments" (retire-confirmed-decline.sh's
    # {removedWithProvenance, departments}; a build envelope adding company /
    # total_departments / total_roles). Unwrap through the ONE shared normalizer
    # so the object shape is not scored "missing/not-a-list" on a valid artifact.
    # A MISSING file still yields None, and a malformed object still yields a
    # non-list — both keep failing this gate exactly as before.
    depts = _prov_read_json(pp.get("departments_json"))
    if isinstance(depts, dict):
        try:
            depts = normalize_departments(depts, path=pp.get("departments_json"))
        except MalformedDepartmentsError as _dept_exc:
            print(f"  [departments.json] MALFORMED: {_dept_exc}", file=sys.stderr)
            depts = None  # stays non-list -> this gate fails it, exactly as before
    if not isinstance(depts, list):
        checks.append(("DEPARTMENTS", False,
                       f"departments.json missing/not-a-list ({pp.get('departments_json')})"))
    elif len(depts) == 0:
        checks.append(("DEPARTMENTS", True,
                       "empty array (fresh-box default; completeness gated by ROLE-FLOOR)"))
    else:
        checks.append(("DEPARTMENTS", True, f"{len(depts)} departments"))

    # ── ROLE-FLOOR (gate) — the DEPARTMENTS claim, measured against DISK ───────
    # DEPARTMENTS above proves only that a JSON file LISTS departments. It reads
    # the ZHC company dir; the role folders it promises live in a different tree
    # entirely. Without this check a box whose every role folder is GONE still
    # records a clean, completed roll, because the JSON still lists them.
    #
    # Scoped as a floor-LOSS detector, on purpose:
    #   * declared_departments == 0  -> n/a. An empty/absent departments.json is
    #     the INTENDED shipped default on a fresh box; that state is DEPARTMENTS'
    #     to judge, and this check must never pile a second failure onto it.
    #   * workspace unresolvable, or zero role artifacts anywhere -> FAIL.
    #   * >= 1 role artifact -> PASS, and the count is reported so erosion is
    #     VISIBLE without being gated here (per-department completeness belongs to
    #     the floor-prover / qc-completeness, which measure the manifest floor).
    # It looks ONLY at role folders: never at packages (the presentation-deps
    # failures are a different defect) and never at a hardcoded department or file
    # count (the floor manifest is regenerated as the floor legitimately changes).
    declared = len(depts) if isinstance(depts, list) else 0
    if declared == 0:
        checks.append(("ROLE-FLOOR", True,
                       "n/a — no departments declared (fresh box default)"))
    else:
        dept_ws = _resolve_departments_workspace(paths, pp)
        if dept_ws is None:
            checks.append(("ROLE-FLOOR", False,
                           "NO live departments workspace on disk — "
                           f"{declared} departments declared in departments.json"))
        else:
            on_disk, role_count = _count_role_artifacts(dept_ws)
            if role_count == 0:
                checks.append(("ROLE-FLOOR", False,
                               f"FLOOR GONE — 0 role artifacts under {dept_ws} "
                               f"({on_disk} department dirs on disk, "
                               f"{declared} declared in departments.json)"))
            else:
                checks.append(("ROLE-FLOOR", True,
                               f"{role_count} role artifacts across {on_disk} "
                               f"department dirs ({dept_ws})"))

    # ── PERSONAS (gate) ───────────────────────────────────────────────────────
    pdir = pp.get("personas_dir")
    persona_count = 0
    try:
        if pdir and Path(pdir).is_dir():
            persona_count = sum(
                1 for c in Path(pdir).iterdir()
                if c.is_dir() and (c / "persona-blueprint.md").is_file()
            )
    except OSError:
        persona_count = 0
    if persona_count == 0:
        checks.append(("PERSONAS", False, f"no personas under {pdir}"))
    else:
        checks.append(("PERSONAS", True, f"{persona_count} personas"))

    # ── SOP (report — gated in step_embedding_health) ─────────────────────────
    emb = str(res.steps.get("embedding-health", "not-run"))
    sop_ok = emb == "pass" or emb.startswith("ok")
    checks.append(("SOP", sop_ok, emb[:60]))

    # ── CC-SERVE (report — gated by build-cc/restart-cc + duck test) ──────────
    cc_serving = bool(res.board.get("cc_healthy", False))
    checks.append(("CC-SERVE", cc_serving,
                   "healthy" if cc_serving else "no local /api/health (informational)"))

    # ── Emit the full per-check breakdown (operator sees exactly what is off) ──
    breakdown = "  ".join(
        f"{n}:{'ok' if ok else 'FAIL'}" + ("" if ok else f"({d})")
        for (n, ok, d) in checks
    )
    _info(f"  provisioning-completeness: {breakdown}")
    for (n, ok, d) in checks:
        (_ok if ok else _err)(f"    {n}: {'ok' if ok else 'FAIL'} — {d}")

    # ── Verdict: the FIVE hard gates only (SOP + CC-SERVE are reported) ───────
    failed = [(n, d) for (n, ok, d) in checks
              if n in _PROVISIONING_HARD_CHECKS and not ok]
    result = {
        "checks":    {n: {"ok": ok, "detail": d} for (n, ok, d) in checks},
        "breakdown": breakdown,
        "failed":    [n for (n, _d) in failed],
    }
    if failed:
        res.step_fail(
            "provisioning-completeness",
            "; ".join(f"{n} FAIL {d}" for (n, d) in failed)[:300],
        )
    else:
        res.step_ok("provisioning-completeness")
    return result


def step_log(paths: dict, res: BoxResult, dry_run: bool,
             pinned_onboarding_tag: str, cc_tag: str) -> None:
    """Step 9: append result to .fleet-refresh-log.json."""
    if dry_run:
        res.step_skip("log", "dry-run")
        return

    log_dir = paths.get("master_files")
    if not log_dir:
        res.step_skip("log", "master_files not found")
        return

    log_path = Path(log_dir) / "zero-human-company" / ".fleet-refresh-log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "box":             res.box,
        "onboarding_tag":  pinned_onboarding_tag,
        "cc_tag":          cc_tag,
        "run_ts":          int(time.time()),
        "result":          res.result,
        "loaded_present":  res.loaded.get("present"),
        "deployed_ok":     res.deployed.get("ok"),
    }

    log_list = []
    if log_path.is_file():
        try:
            log_list = json.loads(log_path.read_text())
        except Exception:
            log_list = []

    # Idempotent: skip if same box+tags+result already logged in the last run
    key = (res.box, pinned_onboarding_tag, cc_tag)
    existing = [
        e for e in log_list
        if (e.get("box"), e.get("onboarding_tag"), e.get("cc_tag")) == key
    ]
    if existing and res.result in ("ok", "dry-run"):
        _info(f"  Log: same box/tags already logged ({len(existing)} entries) — appending new ts")

    log_list.append(entry)
    log_path.write_text(json.dumps(log_list, indent=2))
    res.step_ok("log")


# ── 999-setup refresh (conditional, never a fresh install) ────────────────────
#
# 999-setup (github.com/trevorotts1/999-setup) is installed by Claude Code per
# its AGENT_INSTALL.md: cloned (or archive-extracted as 999-setup-main) into the
# user's Documents folder, and its bundled skills are LINKED from
# ~/.claude/skills/<skill> (and ~/.claude-nine/skills when that root exists) back
# into the checkout. Real boxes do not all follow the doc (the operator Mac keeps
# it in ~/Downloads), so the checkout is FOUND, never assumed: first by following
# an installed skill link back to its repo, then by probing known locations.
_999_SKILL_LINKS = (".claude/skills/nine-router-setup", ".claude-nine/skills/nine-router-setup")
_999_CANDIDATES = (
    "Documents/999-setup", "Documents/999-setup-main",
    "Downloads/999-setup", "Downloads/999-setup-main",
    "999-setup", "999-setup-main", "Desktop/999-setup",
    "clawd/999-setup", "projects/999-setup", "Projects/999-setup",
)
_999_INSTALLER = ".claude/skills/nine-router-setup/scripts/setup-macos.sh"

# Runs ONLY the installer's own skill-install routine (link_skills_into_root,
# against the same one-or-two config roots its main() uses). The full
# orchestrator is deliberately NOT run on a roll: it ends with a live
# `claude-nine -p` model call (AI tokens) and rewires 9Router providers from the
# client's API docs.md. The function is loaded from the installer itself (minus
# its trailing `main "$@"` line) so the link logic is never re-implemented here.
_999_LINK_SCRIPT = r'''
set -euo pipefail
R="$1"; S="$R/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
[ "$(tail -n 1 "$S")" = 'main "$@"' ] || { echo "installer entrypoint changed: last line of $S is not main \"\$@\"" >&2; exit 3; }
T="$(mktemp)"; trap 'rm -f "$T"' EXIT
sed '$d' "$S" > "$T"
. "$T"
declare -F link_skills_into_root >/dev/null || { echo "installer has no link_skills_into_root" >&2; exit 3; }
REPO_ROOT="$R"; REPO_SKILL_DIR="$R/.claude/skills/nine-router-setup"
PRIMARY="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ROOTS="$PRIMARY"
if [ -f "$HOME/.claude-nine/settings.json" ] && [ "$HOME/.claude-nine" != "$PRIMARY" ]; then
  ROOTS="$ROOTS $HOME/.claude-nine"
fi
# A bundled skill that is a real directory (not the installer's link) is a
# hand-managed copy; relinking would swap it out. Leave the links alone then.
hand=""
for root in $ROOTS; do
  while IFS= read -r s; do
    [ -n "$s" ] && [ -e "$root/skills/$s" ] && [ ! -L "$root/skills/$s" ] && hand="$hand $root/skills/$s"
  done < <(bundled_skills)
done
if [ -n "$hand" ]; then echo "HAND-MANAGED:$hand"; exit 0; fi
rc=0
for root in $ROOTS; do link_skills_into_root "$root" || rc=$((rc + $?)); done
exit "$rc"
'''


def _999_home() -> Path:
    # Fixture mode resolves inside the fixture, never the test machine's home.
    fx = os.environ.get("FLEET_REFRESH_ROOT", "").strip()
    return Path(fx) / "home" if fx else Path.home()


def _find_999_checkout() -> Optional[Path]:
    home = _999_home()
    seen: list[Path] = []
    for link in _999_SKILL_LINKS:
        p = home / link
        if p.is_symlink():
            try:
                seen.append(p.resolve().parents[2])   # <repo>/.claude/skills/<skill>
            except (OSError, IndexError):
                pass
    seen += [home / c for c in _999_CANDIDATES]
    for cand in seen:
        # A real checkout carries the repo's own install doc + skill manifest;
        # an installed skill copy under ~/.claude does not.
        if all((cand / f).is_file() for f in (_999_INSTALLER, "AGENT_INSTALL.md", "CONTROL/bundled-skills.txt")):
            return cand
    return None


def step_update_999(res: BoxResult, dry_run: bool) -> None:
    """Refresh 999-setup ONLY where it is already installed; never install it."""
    repo = _find_999_checkout()
    if repo is None:
        res.step_skip("update-999", "999 not installed")
        return
    res.update_999 = {"path": str(repo)}
    if not (repo / ".git").exists():
        res.step_skip("update-999", f"999 at {repo} is an archive extract, not a git clone; not refreshed")
        return
    origin = _git(repo, "remote", "get-url", "origin") or ""
    if "trevorotts1/999-setup" not in origin:
        res.step_skip("update-999", f"{repo} origin is not trevorotts1/999-setup; not touched")
        return
    before = _git(repo, "rev-parse", "HEAD")
    res.update_999["from_sha"] = before
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        res.step_skip("update-999", "999 has local changes, not updated")   # the owner's work is never overwritten
        return
    if dry_run:
        res.step_skip("update-999", f"dry-run (999 at {repo})")
        return
    pull = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only", "--quiet"],
                          capture_output=True, text=True, timeout=180)
    if pull.returncode != 0:
        res.step_fail("update-999", f"git pull --ff-only failed in {repo}: {(pull.stderr or pull.stdout).strip()[:200]}")
        return
    res.update_999["to_sha"] = _git(repo, "rev-parse", "HEAD")
    bash = _bash4() or "bash"
    link = subprocess.run([bash, "-c", _999_LINK_SCRIPT, "update-999", str(repo)],
                          capture_output=True, text=True, timeout=300,
                          env={**os.environ, "HOME": str(_999_home())})
    res.update_999["installer"] = (link.stdout + link.stderr).strip()[-400:]
    if link.returncode != 0:
        res.step_fail("update-999", f"installer skill step exited {link.returncode}: {link.stderr.strip()[-200:]}")
        return
    if "HAND-MANAGED:" in link.stdout:
        res.steps["update-999"] = ("ok:pulled; skill links left alone (hand-managed copies:"
                                   + link.stdout.split("HAND-MANAGED:", 1)[1].strip()[:200] + ")")
        return
    res.step_ok("update-999")


# ── Snapshot / health gate / rollback ─────────────────────────────────────────
#
# Before a box is touched we record what it was (onboarding stamp + clone SHA,
# Command Center SHA/tag, a tarball of the onboarding-managed skill trees) and
# how healthy it was. After the update a read-only health probe runs; any check
# that passed before and fails now -- or any failed mutating step -- rolls the
# box back to the snapshot. The probe never sends a chat turn: Telegram is
# checked with getMe only (a read), and no agent is prompted.

# Mutating steps whose failure leaves a half-updated box (-> rollback).
_MUTATING_STEPS = ("pull-onboarding", "pull-cc", "build-cc", "restart-cc")
# Stamp/state files update-skills.sh writes next to the skill trees.
_SKILLS_STATE_FILES = (".onboarding-version", ".onboarding-content-manifest.json",
                       ".installed-versions", ".command-center-state")
_SNAPSHOT_KEEP = 3
_GATEWAY_PROC_RE = re.compile(r"openclaw.*gateway")


def _git(repo: Path, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _skills_dir(paths: dict) -> Path:
    return Path(paths.get("skills") or Path(paths["root"]) / "skills")


def _managed_skill_entries(skills_dir: Path, repo_root: Path) -> list[str]:
    """Entries of the skills dir that the onboarding repo ships (never the
    client's own or third-party skills that merely live beside them)."""
    try:
        shipped = {p.name for p in repo_root.iterdir() if p.name != ".git"}
        present = {p.name for p in skills_dir.iterdir()}
    except OSError:
        return []
    return sorted((shipped & present) | (set(_SKILLS_STATE_FILES) & present))


def _tree_bytes(base: Path, names: list[str]) -> int:
    total = 0
    for n in names:
        p = base / n
        if p.is_file():
            total += p.stat().st_size
            continue
        for dirpath, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += os.lstat(os.path.join(dirpath, f)).st_size
                except OSError:
                    pass
    return total


def take_snapshot(paths: dict, repo_root: Path, res: BoxResult) -> bool:
    """Record the pre-update state. Returns False when no restorable snapshot
    could be made -- the caller must then NOT update the box."""
    skills_dir = _skills_dir(paths)
    cc_dir = Path(paths["cc_dir"]) if paths.get("cc_dir") else None
    onb_sha = os.environ.get("FLEET_PREV_ONBOARDING_SHA", "").strip() or _git(repo_root, "rev-parse", "HEAD")
    snap: dict = {
        "ts": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        "onboarding": {
            "stamp": _read_onboarding_version(skills_dir),
            "sha": onb_sha,
            "tag": _git(repo_root, "describe", "--tags", "--abbrev=0", onb_sha or "HEAD"),
            "repo_root": str(repo_root),
        },
        "cc": None,
    }
    if cc_dir and (cc_dir / ".git").exists():
        snap["cc"] = {
            "dir": str(cc_dir),
            "sha": _git(cc_dir, "rev-parse", "HEAD"),
            "tag": _git(cc_dir, "describe", "--tags", "--abbrev=0"),
            "version": _read_cc_version(cc_dir),
        }
    res.snapshot = snap

    entries = _managed_skill_entries(skills_dir, repo_root)
    backups = Path(paths["root"]) / "backups" / "fleet-refresh"
    dest = backups / snap["ts"]
    try:
        dest.mkdir(parents=True, exist_ok=True)
        os.chmod(dest, 0o700)
        need = _tree_bytes(skills_dir, entries)
        free = shutil.disk_usage(dest).free
        if free < 2 * need + 512 * 1024 * 1024:
            raise OSError(f"only {free // 2**20} MB free, need ~{(2 * need) // 2**20 + 512} MB for the skills snapshot")
        archive = dest / "skills.tgz"
        if entries:
            t = subprocess.run(["tar", "-czf", str(archive), "-C", str(skills_dir), *entries],
                               capture_output=True, text=True, timeout=900)
            if t.returncode != 0:
                raise OSError(f"tar exited {t.returncode}: {t.stderr.strip()[:200]}")
        oc_json = Path(paths["root"]) / "openclaw.json"
        if oc_json.is_file():   # kept for a human; never auto-restored under a live gateway
            shutil.copy2(oc_json, dest / "openclaw.json")
            os.chmod(dest / "openclaw.json", 0o600)
    except (OSError, subprocess.SubprocessError) as exc:
        res.snapshot["error"] = f"skills snapshot failed: {exc}"
        shutil.rmtree(dest, ignore_errors=True)
        return False
    snap["backup_dir"] = str(dest)
    snap["skills_entries"] = entries
    snap["skills_archive"] = str(archive) if entries else None
    # Retention: keep the newest few snapshots only.
    try:
        olds = sorted(p for p in backups.iterdir() if p.is_dir())[:-_SNAPSHOT_KEEP]
        for old in olds:
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass
    return True


# -- health probes (all read-only) --------------------------------------------

def _hc(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _http_get(url: str, timeout: int = 10) -> tuple[int, str]:
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(4096).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001 -- network errors are a probe result
        return 0, f"{e.__class__.__name__}: {getattr(e, 'reason', e)}"


def _read_openclaw_json(paths: dict) -> dict:
    try:
        return json.loads((Path(paths["root"]) / "openclaw.json").read_text())
    except (OSError, ValueError, KeyError):
        return {}


def hc_gateway_process() -> dict:
    proc = Path("/proc")
    if proc.is_dir():
        me = str(os.getpid())
        for d in proc.iterdir():
            if not d.name.isdigit() or d.name == me:
                continue
            try:
                cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if _GATEWAY_PROC_RE.search(cmd) and " call " not in cmd:
                return _hc("pass", f"gateway process pid {d.name}")
        return _hc("fail", "no openclaw gateway process in /proc")
    try:
        r = subprocess.run(["pgrep", "-f", "openclaw.*gateway"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return _hc("n/a", f"cannot list processes: {e}")
    if r.returncode == 0:
        return _hc("pass", f"gateway process pid {r.stdout.split()[0]}")
    if r.returncode == 1:
        return _hc("fail", "no openclaw gateway process (pgrep)")
    return _hc("n/a", f"pgrep exited {r.returncode}")


def hc_gateway_health(paths: dict, tries: int = 3, wait: float = 5.0) -> dict:
    port = (_read_openclaw_json(paths).get("gateway") or {}).get("port") or 18789
    url = f"http://127.0.0.1:{port}/health"
    code, body = 0, ""
    for i in range(tries):
        code, body = _http_get(url)
        if code == 200:
            return _hc("pass", f"{url} 200")
        if i + 1 < tries:
            time.sleep(wait)
    return _hc("fail", f"{url} -> {code or body}")


def _config_hashes() -> Optional[tuple[str, str]]:
    """(config file revision, config the running gateway applied) from the
    gateway's own config.get, or None when it cannot tell. Reads only those two
    fields: the payload is never printed or kept."""
    out = _run_out(["openclaw", "gateway", "call", "config.get", "--json"], timeout=30)
    try:
        d = json.loads(out)
    except ValueError:
        return None
    d = d.get("payload") or d.get("result") or d if isinstance(d, dict) else {}
    a, b = d.get("configRevisionHash"), d.get("appliedConfigHash")
    return (a, b) if a and b else None


def hc_config_applied(paths: dict, wait: float = 60.0) -> dict:
    """Whether the running gateway applied the config file as it stands now.
    Back-to-back openclaw.json writes during an update can supersede a reload
    ("GatewayConfigReloadSupersededError"): the file then says one thing and the
    live gateway runs another until some later restart. A reload in flight gets
    `wait` seconds to land."""
    deadline = time.time() + wait
    while True:
        h = _config_hashes()
        if h is None:
            return _hc("n/a", "gateway does not report its applied config (older gateway or unreachable)")
        if h[0] == h[1]:
            return _hc("pass", "the running gateway applied the current config")
        if time.time() >= deadline:
            return _hc("fail", "config on disk is not what the running gateway applied (a reload was "
                               "superseded or deferred); the gateway needs a restart")
        time.sleep(5)


def _telegram_tokens(cfg: dict) -> list[str]:
    tg = (cfg.get("channels") or {}).get("telegram") or {}
    if not isinstance(tg, dict) or tg.get("enabled") is False:
        return []
    env_vars = (cfg.get("env") or {}).get("vars") or {}
    raw: list[str] = []
    if isinstance(tg.get("botToken"), str):
        raw.append(tg["botToken"])
    for acc in (tg.get("accounts") or {}).values():
        if isinstance(acc, dict) and acc.get("enabled") is not False and isinstance(acc.get("botToken"), str):
            raw.append(acc["botToken"])
    out: list[str] = []
    for t in raw:
        m = re.fullmatch(r"\$\{(\w+)\}", t.strip())
        if m:
            t = os.environ.get(m.group(1)) or str(env_vars.get(m.group(1)) or "")
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


def hc_telegram_getme(paths: dict, tries: int = 3, wait: float = 5.0) -> dict:
    """Bot API getMe for every configured bot token. A READ -- never sendMessage.
    Token values never appear in the result."""
    tokens = _telegram_tokens(_read_openclaw_json(paths))
    if not tokens:
        return _hc("n/a", "no telegram bot token configured")
    names, bad = [], []
    for i, tok in enumerate(tokens, 1):
        code, body = 0, ""
        for attempt in range(tries):
            code, body = _http_get(f"https://api.telegram.org/bot{tok}/getMe")
            if code in (200, 401, 404):
                break
            if attempt + 1 < tries:
                time.sleep(wait)
        body = body.replace(tok, "<token>")
        try:
            me = json.loads(body) if code == 200 else {}
        except ValueError:
            me = {}
        if me.get("ok"):
            names.append("@" + str((me.get("result") or {}).get("username", f"bot{i}")))
        else:
            bad.append(f"token#{i}: HTTP {code}" + ("" if code else f" ({body[:80]})"))
    if bad:
        return _hc("fail", "; ".join(bad))
    return _hc("pass", "getMe ok " + " ".join(names))


def hc_cc_health(paths: dict, times: int = 3, wait: float = 2.0) -> dict:
    cc_dir = paths.get("cc_dir")
    if not cc_dir or not Path(cc_dir).is_dir():
        return _hc("n/a", "no Command Center on this box")
    url = f"http://127.0.0.1:{os.environ.get('CC_PORT') or 4000}/api/health"
    for i in range(times):
        code, body = _http_get(url)
        if code != 200:
            return _hc("fail", f"{url} attempt {i + 1}/{times} -> {code or body}")
        if i + 1 < times:
            time.sleep(wait)
    return _hc("pass", f"{url} 200 x{times}")


def hc_session_reset(res: BoxResult) -> dict:
    v = str(res.steps.get("sessions-reset-CEO", "not-run"))
    if v.startswith("ok"):
        return _hc("pass", v if v != "ok" else "sessions.reset ok")
    if "session key unresolved" in v:
        return _hc("n/a", "no main-agent Telegram session to reset")
    if "openclaw not on PATH" in v:   # the probe could not run: undetermined, not a regression
        return _hc("n/a", "undetermined: openclaw not on PATH")
    if v.startswith("failed"):
        return _hc("fail", v[len("failed:"):][:200])
    return _hc("n/a", v[:80])


def probe_health(paths: dict, res: Optional[BoxResult] = None) -> dict:
    """Platform-aware, read-only box health. `res` given = post-update probe,
    which also judges the main agent's session reset."""
    if os.environ.get("FLEET_REFRESH_ROOT", "").strip():
        # Fixture mode: never probe the live services of the machine running a test.
        names = ["gateway-process", "gateway-health", "telegram-getme", "cc-health"]
        return {n: _hc("n/a", "fixture mode") for n in names}
    checks = {
        "gateway-process":  hc_gateway_process(),
        "gateway-health":   hc_gateway_health(paths),
        "telegram-getme":   hc_telegram_getme(paths),
        "cc-health":        hc_cc_health(paths),
        "config-applied":   hc_config_applied(paths, wait=60.0 if res is not None else 0.0),
    }
    if res is not None:
        checks["session-reset"] = hc_session_reset(res)
    return checks


def health_regressions(baseline: dict, post: dict) -> list[str]:
    """Checks failing now that were NOT already failing before the update.
    A check that was broken before we arrived is reported, never blamed on
    (or 'fixed' by rolling back) this update."""
    return [n for n, c in post.items()
            if c.get("status") == "fail" and (baseline.get(n) or {}).get("status") != "fail"]


def rollback_box(paths: dict, repo_root: Path, res: BoxResult, reasons: list[str]) -> bool:
    """Restore the snapshot: onboarding clone SHA + skill trees + stamps,
    Command Center SHA (rebuilt and restarted through atomic-deploy.sh), then
    reset the main session so it reloads the restored files. Returns True when
    every restore action succeeded."""
    snap = res.snapshot
    rb: dict = {"reasons": reasons, "actions": [], "errors": [],
                "not_restored": "workspace files update-skills.sh rewrote (AGENTS.md etc.), openclaw.json "
                                "(pre-update copy kept in backup_dir), cron scripts, 999-setup"}
    res.rollback = rb
    _warn(f"  ROLLBACK: {'; '.join(reasons)}")

    # Onboarding clone back to its previous SHA.
    # (update-skills.sh already hard-syncs this managed clone to origin/main on
    # every run; this puts it back where the snapshot found it.)
    onb_sha = snap["onboarding"]["sha"]
    if onb_sha and _git(repo_root, "rev-parse", "HEAD") != onb_sha:
        r = subprocess.run(["git", "-C", str(repo_root), "reset", "--hard", "--quiet", onb_sha],
                           capture_output=True, text=True, timeout=120)
        (rb["actions"] if r.returncode == 0 else rb["errors"]).append(
            f"onboarding clone -> {onb_sha[:12]}" + ("" if r.returncode == 0 else f": {r.stderr.strip()[:160]}"))

    # Skill trees: move the current managed entries aside, extract the
    # snapshot, and only then discard the aside copy (put it back on failure).
    skills_dir = _skills_dir(paths)
    entries = snap.get("skills_entries") or []
    archive = snap.get("skills_archive")
    if archive:
        aside = Path(snap["backup_dir"]) / "rolled-forward"
        try:
            aside.mkdir(exist_ok=True)
            moved = []
            for n in entries:
                if (skills_dir / n).exists() or (skills_dir / n).is_symlink():
                    shutil.move(str(skills_dir / n), str(aside / n))
                    moved.append(n)
            t = subprocess.run(["tar", "-xzf", archive, "-C", str(skills_dir)],
                               capture_output=True, text=True, timeout=900)
            if t.returncode != 0:
                for n in moved:   # put the rolled-forward trees back as they were
                    target = skills_dir / n
                    if target.is_dir() and not target.is_symlink():
                        shutil.rmtree(target, ignore_errors=True)
                    elif target.exists() or target.is_symlink():
                        target.unlink()
                    shutil.move(str(aside / n), str(target))
                raise OSError(f"tar -x exited {t.returncode}: {t.stderr.strip()[:160]}")
            shutil.rmtree(aside, ignore_errors=True)
            rb["actions"].append(f"skills restored ({len(entries)} entries, stamp {snap['onboarding']['stamp']})")
        except (OSError, shutil.Error, subprocess.SubprocessError) as exc:
            rb["errors"].append(f"skills restore failed: {exc}")

    # Command Center back to its previous SHA, rebuilt + restarted atomically.
    cc = snap.get("cc") or {}
    if cc.get("sha"):
        cc_dir = Path(cc["dir"])
        now = _git(cc_dir, "rev-parse", "HEAD")
        if now != cc["sha"]:
            # A modified tracked file (the updater rewrites scripts/watchdog-cc.sh
            # in place) must never block the rollback: its changes are saved
            # beside the snapshot first, then the reset is forced.
            saved = _save_local_changes(cc_dir, Path(snap.get("backup_dir") or cc_dir.parent))
            if saved:
                rb["actions"].append(f"Command Center local changes saved to {saved}")
            k = subprocess.run(["git", "-C", str(cc_dir), "reset", "--hard", "--quiet", cc["sha"]],
                               capture_output=True, text=True, timeout=120)
            if k.returncode != 0:
                rb["errors"].append(f"Command Center reset to {cc['sha'][:12]} failed: {k.stderr.strip()[:160]}")
            else:
                try:
                    d = _run_atomic_deploy(cc_dir, revision=cc["sha"])
                    if d.returncode == 0:
                        rb["actions"].append(f"Command Center -> {cc.get('tag') or cc['sha'][:12]} rebuilt + restarted")
                    else:
                        rb["errors"].append(f"Command Center rebuild at {cc['sha'][:12]} exited {d.returncode}: "
                                            f"{(d.stdout + d.stderr).strip()[-200:]}")
                except subprocess.TimeoutExpired:
                    rb["errors"].append(f"Command Center rebuild timed out after {ATOMIC_DEPLOY_TIMEOUT}s")
        else:
            rb["actions"].append("Command Center unchanged (same SHA); no rebuild")

    # The one CEO session reset of the roll runs after the gate (reset_ceo_once),
    # so it reloads the restored files too.
    return not rb["errors"]


def _save_local_changes(repo: Path, dest_dir: Path) -> Optional[str]:
    """Copy every modified tracked file of `repo`, plus the diff, into
    dest_dir/cc-local-changes-<ts>/ . Returns that path, or None when clean."""
    changed = (_git(repo, "diff", "--name-only", "HEAD") or "").splitlines()
    if not changed:
        return None
    out = dest_dir / f"cc-local-changes-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "changes.diff").write_text((_git(repo, "diff", "HEAD") or "") + "\n")
    for rel in changed:
        if (repo / rel).is_file():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, out / rel)
    return str(out)


class _BoxLock:
    """One fleet-refresh per box at a time (the operator roll and the box's own
    Sunday run must never interleave)."""

    def __init__(self, root: Path):
        self.path = Path(root) / ".fleet-refresh.lock"
        self.held = False

    def acquire(self) -> Optional[str]:
        for _ in range(2):
            try:
                self.path.mkdir()
                (self.path / "pid").write_text(str(os.getpid()))
                self.held = True
                return None
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    try:
                        pid = int((self.path / "pid").read_text().strip())
                    except (OSError, ValueError):
                        if age < 60:   # the other run is between mkdir and writing its pid
                            return "another fleet-refresh is starting on this box"
                        raise
                    os.kill(pid, 0)
                    if age < 4 * 3600:
                        return f"another fleet-refresh (pid {pid}) is running on this box"
                except (OSError, ValueError):
                    pass
                shutil.rmtree(self.path, ignore_errors=True)   # stale
            except OSError as e:
                return f"cannot create lock {self.path}: {e}"
        return f"cannot acquire {self.path}"

    def release(self) -> None:
        if self.held:
            shutil.rmtree(self.path, ignore_errors=True)
            self.held = False


# ── Content integrity (post-update) ───────────────────────────────────────────
#
# "Updated" must mean the box HAS the release content, not that a script exited
# 0. Each check compares what is installed against the release manifest the
# update just delivered, using the SAME signals update-skills.sh's own gates
# use:
#   persona-index      .prebuilt-index-version sentinel == INDEX-MANIFEST release_tag
#                      (U6b's D3 completion re-assertion / _persona_index_currency_probe)
#   persona-embeddings COUNT(DISTINCT persona_id) in gemini-index.sqlite >= the
#                      manifest's embedded_persona_count
#   sop-library        `sops` rows >= SOP-LIBRARY-MANIFEST canonical_sop_count   } _sop_library_currency_probe,
#   sop-embeddings     sops WITH an embedding >= SOP-EMBEDDINGS-MANIFEST sop_count} same DB (resolve_db) and queries
#   role-library       scripts/skill-content-hash.sh digest of the installed
#                      23-ai-workforce-blueprint (which carries templates/role-library)
#                      == the digest update-skills.sh recorded from the release source
#   departments        refresh-dept-intake.py's own post-write verification receipt
#                      from THIS run, and role folders present for every declared
#                      department (the ROLE-FLOOR measure)
# The two SOP checks are a Python port of _sop_library_currency_probe (that
# bash function needs the sqlite3 CLI, which the Docker images do not ship);
# tests/unit/fleet-refresh-roll-safety.test.py holds the parity test.
# Everything here is read-only. "n/a" = not applicable / not measurable here,
# never a pass by assumption and never a failure by assumption.

INTEGRITY_CHECKS = ("persona-index", "persona-embeddings", "sop-library",
                    "sop-embeddings", "role-library", "departments")


def _json_file(p: Path) -> Optional[dict]:
    try:
        d = json.loads(Path(p).read_text())
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _sqlite_ro(db: Path, sql: str) -> Optional[int]:
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        try:
            return int(con.execute(sql).fetchone()[0])
        finally:
            con.close()
    except (sqlite3.Error, TypeError, ValueError):
        return None


def _dashboard_db(paths: dict, skills_dir: Path) -> Optional[Path]:
    if os.environ.get("FLEET_REFRESH_ROOT", "").strip():   # fixture: never the test machine's DB
        cand = Path(paths.get("cc_dir") or "/nonexistent") / "mission-control.db"
        return cand if cand.is_file() else None
    for su in (skills_dir / "shared-utils", Path(__file__).resolve().parent):
        try:
            sys.path.insert(0, str(su))
            from resolve_db import find_dashboard_db, is_db_found  # type: ignore
            p = find_dashboard_db()
            return Path(p) if is_db_found(p) else None
        except Exception:
            continue
        finally:
            sys.path.remove(str(su))
    return None


def ic_persona_index(skills_dir: Path, workspace: Path) -> dict:
    man = _json_file(skills_dir / "shared-utils/prebuilt-index/INDEX-MANIFEST.json")
    tag = (man or {}).get("release_tag")
    if not tag:
        return _hc("n/a", "no persona INDEX-MANIFEST release_tag on this box")
    try:
        sentinel = (workspace / "data/coaching-personas/.prebuilt-index-version").read_text().strip()
    except OSError:
        sentinel = ""
    if sentinel == tag:
        return _hc("pass", f"sentinel == release_tag ({tag})")
    return _hc("fail", f"persona index sentinel {sentinel or '<missing>'} != release_tag {tag}")


def ic_persona_embeddings(skills_dir: Path, workspace: Path) -> dict:
    man = _json_file(skills_dir / "shared-utils/prebuilt-index/INDEX-MANIFEST.json") or {}
    want = man.get("embedded_persona_count") or man.get("persona_count")
    if not want:
        return _hc("n/a", "manifest carries no persona count")
    db = workspace / "data/coaching-personas/gemini-index.sqlite"
    if not db.is_file():
        return _hc("fail", f"persona embeddings database missing ({db.name})")
    have = _sqlite_ro(db, "SELECT COUNT(DISTINCT persona_id) FROM embeddings")
    if have is None:
        return _hc("n/a", "persona embeddings database unreadable")
    try:   # an honest embedding-receipt.json deferral (spend gate / no key) is not a gap
        from persona_embedding_drift_probe import _deferred_slugs  # type: ignore
        deferred = len(_deferred_slugs(workspace / "data/coaching-personas/personas"))
    except Exception:
        deferred = 0
    if have + deferred >= int(want):
        return _hc("pass", f"{have} personas embedded, {deferred} deferred (manifest {want})")
    return _hc("fail", f"only {have} personas embedded ({deferred} deferred), manifest says {want}")


def ic_sop(paths: dict, skills_dir: Path) -> tuple[dict, dict]:
    db = _dashboard_db(paths, skills_dir)
    if db is None:
        na = _hc("n/a", "no Command Center database on this box")
        return na, na
    lib = _json_file(skills_dir / "shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json") or {}
    canon = int(lib.get("canonical_sop_count") or 0)
    rows = _sqlite_ro(db, "SELECT COUNT(*) FROM sops")
    if not canon or rows is None:
        lib_hc = _hc("n/a", "SOP library manifest or sops table unreadable")
    elif rows >= canon:
        lib_hc = _hc("pass", f"{rows}/{canon} SOPs")
    else:
        lib_hc = _hc("fail", f"SOP library has {rows} of {canon} SOPs")
    emb = _json_file(skills_dir / "shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json") or {}
    want = int(emb.get("sop_count") or 0)
    has_table = _sqlite_ro(db, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sop_embeddings'")
    if not want or has_table is None:
        emb_hc = _hc("n/a", "SOP embeddings manifest or database unreadable")
    else:
        # COVERAGE, not raw rows -- an all-orphan embeddings table is not "current".
        cov = _sqlite_ro(db, "SELECT COUNT(*) FROM sops s WHERE EXISTS "
                             "(SELECT 1 FROM sop_embeddings e WHERE e.sop_id = s.id)") if has_table else 0
        if cov is None:
            emb_hc = _hc("n/a", "SOP embeddings coverage unreadable")
        elif cov >= want:
            emb_hc = _hc("pass", f"{cov} SOPs embedded (manifest {want})")
        else:
            emb_hc = _hc("fail", f"only {cov} SOPs embedded, manifest says {want}")
    return lib_hc, emb_hc


def ic_role_library(skills_dir: Path, repo_root: Path, want_version: str) -> dict:
    man = _json_file(skills_dir / ".onboarding-content-manifest.json")
    rec = ((man or {}).get("skills") or {}).get("23-ai-workforce-blueprint")
    if not rec:
        return _hc("n/a", "no recorded release digest for the role library")
    if want_version and man.get("version") != want_version:
        return _hc("fail", f"content manifest is for {man.get('version')}, not {want_version}")
    hasher = repo_root / "scripts/skill-content-hash.sh"
    if not hasher.is_file():
        return _hc("n/a", "skill-content-hash.sh not in this clone")
    try:
        r = subprocess.run(["bash", str(hasher), str(skills_dir)], capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as e:
        return _hc("n/a", f"content hash could not run: {e}")
    got = next((ln.split("|", 1)[1] for ln in r.stdout.splitlines()
                if ln.startswith("23-ai-workforce-blueprint|")), None)
    if r.returncode != 0 or got is None:
        return _hc("n/a", f"content hash exited {r.returncode}")
    if got == rec:
        return _hc("pass", "installed role library matches the release digest")
    return _hc("fail", "installed role library differs from the release (skill 23 digest mismatch)")


def ic_departments(paths: dict, since: float) -> dict:
    workspace = Path(paths.get("workspace") or "/nonexistent")
    notes = []
    rc = _json_file(workspace / ".dept-intake-refresh-receipt.json")
    if rc and rc.get("apply"):
        try:
            from datetime import datetime
            at = datetime.fromisoformat(str(rc.get("at")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            at = 0
        if at >= since:
            if not rc.get("ok"):
                bad = [d.get("dept") for d in rc.get("depts") or [] if d.get("status") != "ok"
                       and d.get("status") != "skipped_not_materialized"]
                return _hc("fail", f"department intake files not current: {', '.join(map(str, bad))[:160]}")
            notes.append("intake files verified")
    pp = _resolve_provisioning_paths(paths)
    depts = _prov_read_json(pp.get("departments_json"))
    if isinstance(depts, dict):
        try:
            depts = normalize_departments(depts, path=pp.get("departments_json"))
        except MalformedDepartmentsError:
            depts = None
    declared = len(depts) if isinstance(depts, list) else 0
    if declared:
        ws = _resolve_departments_workspace(paths, pp)
        roles = _count_role_artifacts(ws)[1] if ws else 0
        if not roles:
            return _hc("fail", f"{declared} departments declared but no role folders on disk")
        notes.append(f"{declared} departments, {roles} role artifacts")
    if not notes:
        return _hc("n/a", "no departments materialized and no intake receipt from this run")
    return _hc("pass", "; ".join(notes))


def probe_integrity(paths: dict, repo_root: Path, since: float, want_version: str) -> dict:
    skills_dir = _skills_dir(paths)
    workspace = Path(paths.get("workspace") or "/nonexistent")
    sop_lib, sop_emb = ic_sop(paths, skills_dir)
    return {
        "persona-index":      ic_persona_index(skills_dir, workspace),
        "persona-embeddings": ic_persona_embeddings(skills_dir, workspace),
        "sop-library":        sop_lib,
        "sop-embeddings":     sop_emb,
        "role-library":       ic_role_library(skills_dir, repo_root, want_version),
        "departments":        ic_departments(paths, since),
    }


# ── Fix first, then roll back ─────────────────────────────────────────────────
#
# A failed post-update check is first FIXED, up to HEAL_ATTEMPTS times. Each
# attempt picks its actions from what is failing right now:
#   gateway-process / gateway-health / telegram-getme -> restart the gateway
#       Mac: launchctl kickstart -k (fallback: launchctl stop; KeepAlive restarts it)
#       Hostinger: docker compose up -d --force-recreate   } run on the HOST by
#       Contabo:   docker restart <container>              } fleet-refresh.sh
#   a failed update step                -> run that step again
#   cc-health                           -> rebuild + restart the Command Center
#   any content-integrity mismatch      -> run update-skills.sh again
#   session-reset                       -> reset the main session again
# then everything is re-checked. Only when every attempt fails is the box rolled
# back to its snapshot. Every attempt is recorded in res.heal["attempts"].

HEAL_ATTEMPTS = 3
# Fix attempts are budgeted per check per ROLL, not per pass: the counts live in
# <root>/fleet-refresh/heal-budget.json, keyed by the release being rolled and
# forgotten after HEAL_BUDGET_TTL or once the gate passes. A rerun of the same
# roll no longer starts again at 1/3 -- one box re-entered the same 3-attempt
# role-library cycle three times in two hours. config-applied gets ONE gateway
# restart per roll (a restart applies any config); if the gateway still runs an
# older config after it, the box is reported, never rolled back for that.
HEAL_BUDGET_TTL = 24 * 3600
GATEWAY_CHECKS = ("gateway-process", "gateway-health", "telegram-getme", "config-applied")
_GATEWAY_LABEL = "ai.openclaw.gateway"
_HEAL_ORDER = ("rerun:pull-onboarding", "rerun:pull-cc", "rebuild-cc", "rerun:restart-cc",
               "restart-gateway")


def _heal_cap(name: str) -> int:
    return 1 if name == "config-applied" else HEAL_ATTEMPTS


def _heal_budget_file(paths: dict) -> Path:
    return Path(paths["root"]) / "fleet-refresh" / "heal-budget.json"


def _load_heal_budget(paths: dict, release: str) -> dict:
    try:
        b = json.loads(_heal_budget_file(paths).read_text())
    except (OSError, ValueError):
        b = {}
    if not isinstance(b, dict) or b.get("release") != release \
            or time.time() - float(b.get("started") or 0) > HEAL_BUDGET_TTL:
        b = {"release": release, "started": time.time(), "checks": {}}
    return b


def _save_heal_budget(paths: dict, budget: Optional[dict]) -> None:
    f = _heal_budget_file(paths)
    try:
        if budget is None:
            f.unlink(missing_ok=True)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(budget))
    except OSError as e:
        _warn(f"  could not record the fix budget in {f}: {e}")


def _in_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        return any(k in Path("/proc/1/cgroup").read_text() for k in ("docker", "containerd", "kubepods"))
    except OSError:
        return False


def _wait_gateway(paths: dict, seconds: int = 90) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if hc_gateway_health(paths, tries=1)["status"] == "pass":
            return True
        time.sleep(5)
    return False


def _wait_cc(paths: dict, seconds: int) -> Optional[bool]:
    """None when there is no Command Center; else whether /api/health answered."""
    if hc_cc_health(paths, times=1)["status"] == "n/a":
        return None
    deadline = time.time() + seconds
    while time.time() < deadline:
        if hc_cc_health(paths, times=1)["status"] == "pass":
            return True
        time.sleep(10)
    return False


def restart_gateway_mac() -> str:
    """launchd kickstart, the same way platform/mac/service-selfheal/
    gateway-health-watchdog.sh heals it: a booted-out label (a stalled upgrade
    leaves it that way; kickstart then does nothing) is bootstrapped from its
    plist first. Some Macs answer 125/126 ('Domain does not support specified
    action') over SSH, so fall back to stop and let KeepAlive restart it."""
    uid = os.getuid()
    target = f"gui/{uid}/{_GATEWAY_LABEL}"
    plist = Path.home() / "Library/LaunchAgents" / f"{_GATEWAY_LABEL}.plist"
    note = ""
    if subprocess.run(["launchctl", "print", target], capture_output=True, timeout=30).returncode != 0 \
            and plist.is_file():
        b = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
                           capture_output=True, text=True, timeout=60)
        note = f"bootstrapped booted-out label (exit {b.returncode}); "
    k = subprocess.run(["launchctl", "kickstart", "-k", target],
                       capture_output=True, text=True, timeout=60)
    if k.returncode == 0:
        return note + "launchctl kickstart ok"
    s = subprocess.run(["launchctl", "stop", _GATEWAY_LABEL], capture_output=True, text=True, timeout=60)
    if s.returncode == 0:
        return note + f"kickstart exited {k.returncode}; launchctl stop ok (KeepAlive restarts it)"
    raise RuntimeError(f"kickstart exited {k.returncode}, stop exited {s.returncode}: {s.stderr.strip()[:120]}")


def gate_problems(res: BoxResult, baseline: dict, post: dict, integrity: dict) -> dict:
    """name -> detail for everything the gate will not accept. A content check
    that was already failing before the update is a pre-existing gap: recorded
    in res.health["content_gaps_preexisting"] and alerted, not gated."""
    probs = {n: post[n]["detail"] for n in health_regressions(baseline, post)}
    cfg = post.get("config-applied") or {}
    if cfg.get("status") == "fail":
        # Whatever the baseline said: a roll ends on the config it wrote. (A
        # backlog that was already pending before the update is applied too.)
        probs["config-applied"] = cfg["detail"]
    before = res.health.get("integrity_baseline") or {}
    pre = {}
    for n, c in integrity.items():
        if c["status"] != "fail":
            continue
        if (before.get(n) or {}).get("status") == "fail":
            pre[n] = c["detail"]
        else:
            probs[n] = c["detail"]
    res.health["content_gaps_preexisting"] = pre
    snap_cc = (res.snapshot.get("cc") or {}).get("sha")
    cc_moved = bool(snap_cc) and _git(Path(res.snapshot["cc"]["dir"]), "rev-parse", "HEAD") != snap_cc
    for step in _MUTATING_STEPS:
        v = str(res.steps.get(step, ""))
        if not v.startswith("failed") or "[exit-3]" in v:
            continue
        if step != "pull-onboarding" and not cc_moved:
            continue   # a Command Center step failed while nothing of it changed
        probs[step] = v[len("failed:"):][:200]
    return probs


def heal_actions(probs: dict) -> list[str]:
    acts = set()
    for name in probs:
        if name in GATEWAY_CHECKS:
            acts.add("restart-gateway")
        elif name == "cc-health":
            acts.add("rebuild-cc")
        elif name in INTEGRITY_CHECKS:
            acts.add("rerun:pull-onboarding")
        elif name in ("build-cc",):
            acts.add("rebuild-cc")
        elif name in _MUTATING_STEPS:
            acts.add(f"rerun:{name}")
    return [a for a in _HEAL_ORDER if a in acts]


def _run_heal_action(act: str, paths: dict, repo_root: Path, res: BoxResult, ctx: dict) -> str:
    if act == "rerun:pull-onboarding":
        ctx["pinned"] = step_pull_onboarding(paths, repo_root, ctx["pinned"], res, dry_run=False)
        return res.steps.get("pull-onboarding", "?")
    if act == "rerun:pull-cc":
        step_pull_cc(paths, ctx["cc_tag"], res, dry_run=False, force_cc=ctx.get("force_cc", False))
        return res.steps.get("pull-cc", "?")
    if act in ("rebuild-cc", "rerun:restart-cc"):
        step = "build-cc" if act == "rebuild-cc" else "restart-cc"
        try:
            (step_build_cc if step == "build-cc" else step_restart_cc)(paths, res, False)
        except SystemExit:
            res.step_fail(step, "Wave-5 preflight blocked the Command Center deploy")
        return res.steps.get(step, "?")
    if act == "restart-gateway":
        if sys.platform == "darwin":
            out = restart_gateway_mac()
            return out + ("; gateway healthy" if _wait_gateway(paths) else "; gateway NOT healthy after 90s")
        return "needs-host"   # a container's gateway can only be restarted from the host
    return "unknown action"


def heal_and_gate(paths: dict, repo_root: Path, res: BoxResult, baseline: dict, ctx: dict) -> str:
    """Returns "done" (gate settled: healthy, healed, rolled back or failed) or
    "needs-host-restart" (state saved; fleet-refresh.sh restarts the container
    and resumes with --continue-heal)."""
    heal = res.heal
    attempts = heal.setdefault("attempts", [])
    budget = _load_heal_budget(paths, str(ctx.get("release") or ctx["pinned"]))
    used = budget["checks"]
    while True:
        post = probe_health(paths, res)
        integ = probe_integrity(paths, repo_root, heal.get("run_start", 0), ctx["pinned"])
        res.health["post"], res.health["integrity"] = post, integ
        probs = gate_problems(res, baseline, post, integ)
        if "config-applied" in probs and used.get("config-applied", 0) >= _heal_cap("config-applied"):
            heal["config_pending"] = probs.pop("config-applied")
        res.health["regressions"] = sorted(probs)
        if not probs:
            res.step_ok("health-gate")
            if attempts:
                heal["healed"] = True
                res.steps["health-gate"] = f"ok:healed after {len(attempts)} fix attempt(s)"
            _save_heal_budget(paths, None)
            return "done"
        fixable = {n: d for n, d in probs.items() if used.get(n, 0) < _heal_cap(n)}
        if not fixable:
            heal["budget_spent"] = {n: used.get(n, 0) for n in sorted(probs)}
            _warn(f"  no fix attempts left in this roll for: {', '.join(sorted(probs))}")
            break
        if len(attempts) >= HEAL_ATTEMPTS:
            break
        acts = heal_actions(fixable)
        prev = attempts[-1] if attempts else None
        if prev and prev["failing"] == probs:
            # The last attempt changed nothing. A full update-skills pass
            # (20-55 min) that already finished ok will not either: do not
            # repeat it; stop when nothing else is left to try.
            acts = [a for a in acts
                    if not (a == "rerun:pull-onboarding" and str(prev["actions"].get(a, "")).startswith("ok"))]
            if not acts:
                _warn("  the last fix attempt changed nothing and nothing else is left to try")
                break
        attempt = {"n": len(attempts) + 1, "failing": dict(probs), "fixing": sorted(fixable), "actions": {}}
        attempts.append(attempt)
        for n in fixable:
            used[n] = used.get(n, 0) + 1
        _save_heal_budget(paths, budget)
        _warn(f"  FIX ATTEMPT {attempt['n']}/{HEAL_ATTEMPTS}: {', '.join(sorted(fixable))}"
              + (f" (no attempts left in this roll for: {', '.join(sorted(set(probs) - set(fixable)))})"
                 if set(probs) - set(fixable) else ""))
        for act in acts:
            try:
                out = _run_heal_action(act, paths, repo_root, res, ctx)
            except Exception as e:   # an attempt that errors is still an attempt
                out = f"error: {e}"
            if out == "needs-host":
                if ctx.get("host_restart"):
                    attempt["actions"][act] = "requested from host"
                    heal["pending_host_restart"] = True
                    save_heal_state(res, baseline, ctx)
                    return "needs-host-restart"
                out = "skipped: running inside the container with no host access"
            attempt["actions"][act] = str(out)[:240]

    # Every fix attempt failed.
    reasons = [f"{n}: {d}" for n, d in sorted(probs.items())]
    res.steps["health-gate"] = "failed:" + "; ".join(reasons)[:300]
    restored = rollback_box(paths, repo_root, res, reasons)
    after = probe_health(paths)
    res.health["after_rollback"] = after
    still = health_regressions(baseline, after)
    res.rollback["health_restored"] = not still
    tried = f"{len(attempts)} fix attempt(s) failed" + (
        "; this roll's fix attempts for it were already used" if heal.get("budget_spent") else "")
    if restored and not still:
        res.steps["rollback"] = "ok"
        res.outcome = "ROLLED_BACK"
        res.outcome_detail = f"{tried}; rolled back. Failing: {'; '.join(reasons)}"[:400]
    else:
        why = res.rollback["errors"] + [f"still failing: {n}" for n in still]
        res.steps["rollback"] = "failed:" + "; ".join(why)[:300]
        res.outcome = "FAILED"
        res.outcome_detail = (f"{tried}; ROLLBACK INCOMPLETE ({'; '.join(why)[:200]}) "
                              f"after: {'; '.join(reasons)[:200]}")
    _err(f"  {res.outcome}: {res.outcome_detail}")
    try:
        from cc_compat import load_cc_compat  # type: ignore
        ctx["pinned"] = load_cc_compat(repo_root).get("onboardingVersion", ctx["pinned"])
    except Exception:
        pass
    return "done"


def _heal_state_path(res: BoxResult) -> Path:
    return Path(res.snapshot.get("backup_dir") or "/tmp") / "heal-state.json"


def save_heal_state(res: BoxResult, baseline: dict, ctx: dict) -> None:
    p = _heal_state_path(res)
    res.heal["state_path"] = str(p)
    p.write_text(json.dumps({"res": res.to_dict(), "baseline": baseline, "ctx": ctx}, default=str))
    os.chmod(p, 0o600)


def load_heal_state(path: Path) -> tuple[BoxResult, dict, dict]:
    st = json.loads(Path(path).read_text())
    d = st["res"]
    res = BoxResult(d["box"], dry_run=False)
    for k, v in d.items():
        if hasattr(res, k) and k not in ("box", "dry_run"):
            setattr(res, k, v)
    return res, st["baseline"], st["ctx"]


# ── Main per-box run ──────────────────────────────────────────────────────────

def run_box(
    box: str,
    shared_utils: Path,
    repo_root: Path,
    dry_run: bool,
    verify_only: bool,
    local: bool,
    force_cc: bool,
    expected_sha: Optional[str],
    host_restart: bool = False,
    continue_heal: Optional[Path] = None,
    host_restart_result: str = "",
) -> BoxResult:
    """
    Execute all 8 steps for a single box.  Returns a BoxResult regardless of
    per-step failures (failure isolation).

    SAFETY: this function NEVER calls `openclaw gateway restart` (over SSH on
    a Mac that fails with LaunchAgent err 125 and brings the box down). The
    gateway is restarted only as a fix attempt after a failed health check,
    through launchd on a Mac (restart_gateway_mac) or from the host for a
    container (fleet-refresh.sh, via --host-restart / --continue-heal).
    """
    res = BoxResult(box=box, dry_run=dry_run)
    res.merged_sha = expected_sha

    # Load cc-compat.json
    try:
        sys.path.insert(0, str(shared_utils))
        from cc_compat import load_cc_compat  # type: ignore
        compat = load_cc_compat(repo_root)
    except Exception as e:
        res.result = "failed"
        res.errors.append(f"cc-compat.json load failed: {e}")
        _err(str(e))
        return res

    pinned_onboarding_tag = compat.get("onboardingVersion", "unknown")

    # Load platform paths
    try:
        paths = _load_paths(shared_utils)
    except OSError as e:
        # e.g. macOS refusing ~/Downloads to the SSH process ("Interrupted system call").
        res.result, res.outcome = "failed", "FAILED"
        res.outcome_detail = (f"cannot read {e.filename or 'the OpenClaw folders'} ({e.strerror}); "
                              "on a Mac, give sshd-keygen-wrapper Full Disk Access. Nothing was changed.")
        res.errors.append(res.outcome_detail)
        return res

    lock = None
    if not dry_run and not verify_only:
        lock = _BoxLock(paths["root"])
        busy = lock.acquire()
        if busy:
            res.result, res.outcome, res.outcome_detail = "skipped", "SKIPPED", busy
            return res
    try:
        if continue_heal:
            return _continue_heal(Path(continue_heal), host_restart_result, compat, paths,
                                  shared_utils, repo_root)
        return _run_box_body(res, compat, pinned_onboarding_tag, paths, shared_utils,
                             repo_root, dry_run, verify_only, local, force_cc, host_restart)
    finally:
        if lock:
            lock.release()


def _continue_heal(state: Path, host_result: str, compat: dict, paths: dict,
                   shared_utils: Path, repo_root: Path) -> BoxResult:
    """Resume after fleet-refresh.sh restarted this box's container from the host."""
    res, baseline, ctx = load_heal_state(state)
    heal = res.heal
    heal.pop("pending_host_restart", None)
    last = (heal.get("attempts") or [{}])[-1]
    ok = _wait_gateway(paths, 120)
    # The Command Center comes back after the gateway (pm2 resurrect waits ~45s
    # on Hostinger); judging it any sooner burns a fix attempt on a healthy box.
    cc_ok = _wait_cc(paths, 240)
    last.setdefault("actions", {})["restart-gateway"] = (
        f"host: {host_result or 'done'}; gateway {'healthy' if ok else 'NOT healthy after 120s'}"
        + ("" if cc_ok is None else f"; Command Center {'healthy' if cc_ok else 'NOT healthy after 240s'}"))
    if heal_and_gate(paths, repo_root, res, baseline, ctx) == "needs-host-restart":
        return _pending(res)
    try:
        reset_ceo_once(paths, res, False)
    except Exception as e:
        res.step_fail("sessions-reset-CEO", str(e))
    return _finish_run(res, compat, ctx["pinned"], paths, shared_utils, repo_root,
                       False, False, ctx["cc_tag"], _resolve_ceo_session_key(paths))


def _pending(res: BoxResult) -> BoxResult:
    res.result, res.outcome = "pending_host_restart", "PENDING"
    res.outcome_detail = "container gateway restart requested from the host"
    return res


def _run_box_body(res: BoxResult, compat: dict, pinned_onboarding_tag: str, paths: dict,
                  shared_utils: Path, repo_root: Path, dry_run: bool, verify_only: bool,
                  local: bool, force_cc: bool, host_restart: bool = False) -> BoxResult:

    # Step 0: detect
    try:
        step_detect(paths, repo_root, compat, res)
    except Exception as e:
        res.step_fail("detect", str(e))

    # Step 1: pin-resolve
    cc_tag = "unknown"
    try:
        cc_tag = step_pin_resolve(paths, repo_root, compat, res)
    except Exception as e:
        res.step_fail("pin-resolve", str(e))
        cc_tag = compat["commandCenter"].get("pinnedTag", "unknown")

    # Baseline health: read-only, so it runs in every mode (a dry-run shows the
    # box's health before anyone decides to roll it).
    baseline = probe_health(paths)
    res.health = {"baseline": baseline,
                  "preexisting_failures": [n for n, c in baseline.items() if c["status"] == "fail"]}
    res.heal = {"run_start": time.time()}
    # The installed content's integrity BEFORE the update (against the manifests
    # it was installed from). A gap that was already there is reported and
    # alerted, never blamed on -- or rolled back by -- this update.
    res.health["integrity_baseline"] = probe_integrity(paths, repo_root, 0, res.onboarding_version)

    if not verify_only:
        # The Wave-5 gate would otherwise sys.exit() from inside build-cc, AFTER
        # onboarding was already applied (a half-updated box, no result JSON).
        # Check it before the first change instead: blocked = box untouched.
        if not dry_run:
            try:
                wave5_deploy_preflight()
            except SystemExit:
                res.result, res.outcome = "skipped", "SKIPPED"
                res.outcome_detail = "not updated: Wave-5 Command Center preflight blocked (GitHub API unreachable or files missing)"
                return res

        # Snapshot BEFORE the first change. No restorable snapshot = no update.
        if not dry_run and not take_snapshot(paths, repo_root, res):
            res.result, res.outcome = "skipped", "SKIPPED"
            res.outcome_detail = f"not updated: {res.snapshot.get('error')}"
            return res

        # Step 2: pull-onboarding
        try:
            pinned_onboarding_tag = step_pull_onboarding(paths, repo_root, pinned_onboarding_tag, res, dry_run)
        except Exception as e:
            res.step_fail("pull-onboarding", str(e))

        # Held by the fleet standing gate (account not current): nothing else changes.
        if res.steps.get("pull-onboarding") == f"skip:{UPDATE_HELD}":
            for step in ("update-999", "pull-cc", "build-cc", "restart-cc", "sessions-reset-CEO"):
                res.step_skip(step, "update held")
            res.result, res.outcome, res.outcome_detail = "skipped", "SKIPPED", UPDATE_HELD
            return res

        # Step 2b: 999-setup, only where it is already installed
        try:
            step_update_999(res, dry_run)
        except Exception as e:
            res.step_fail("update-999", str(e))

        # Step 3: pull-cc
        try:
            step_pull_cc(paths, cc_tag, res, dry_run, force_cc)
        except Exception as e:
            res.step_fail("pull-cc", str(e))

        # Step 4: build-cc (ONLY if pull-cc succeeded or was skipped)
        if "failed" not in str(res.steps.get("pull-cc", "")):
            try:
                step_build_cc(paths, res, dry_run, local)
            except SystemExit:
                res.step_fail("build-cc", "Wave-5 preflight blocked the Command Center deploy")
            except Exception as e:
                res.step_fail("build-cc", str(e))

        # Step 5: restart-cc (ONLY if build-cc succeeded or was skipped)
        if "failed" not in str(res.steps.get("build-cc", "")):
            try:
                step_restart_cc(paths, res, dry_run)
            except SystemExit:
                res.step_fail("restart-cc", "Wave-5 preflight blocked the Command Center restart")
            except Exception as e:
                res.step_fail("restart-cc", str(e))

        # Step 6: health + content gate -> fix up to 3 times -> roll back
        if not dry_run:
            ctx = {"pinned": pinned_onboarding_tag, "cc_tag": cc_tag, "force_cc": force_cc,
                   "host_restart": host_restart,
                   "release": compat.get("onboardingVersion") or pinned_onboarding_tag}
            if heal_and_gate(paths, repo_root, res, baseline, ctx) == "needs-host-restart":
                return _pending(res)
            pinned_onboarding_tag = ctx["pinned"]

        # Step 6b: reset the CEO session ONCE, on the files the box ends up with.
        try:
            reset_ceo_once(paths, res, dry_run)
        except Exception as e:
            res.step_fail("sessions-reset-CEO", str(e))
        ceo_session_key = _resolve_ceo_session_key(paths)
    else:
        ceo_session_key = _resolve_ceo_session_key(paths)
        for step in ["pull-onboarding", "pull-cc", "build-cc", "restart-cc", "sessions-reset-CEO"]:
            res.step_skip(step, "verify-only")

    return _finish_run(res, compat, pinned_onboarding_tag, paths, shared_utils, repo_root,
                       dry_run, verify_only, cc_tag, ceo_session_key)


def _finish_run(res: BoxResult, compat: dict, pinned_onboarding_tag: str, paths: dict,
                shared_utils: Path, repo_root: Path, dry_run: bool, verify_only: bool,
                cc_tag: str, ceo_session_key: Optional[str]) -> BoxResult:
    # Step 7: verify (always runs — reports current state in dry-run mode)
    try:
        _check_deployed(paths, compat, pinned_onboarding_tag, res)
        _verify_loaded(paths, shared_utils, ceo_session_key if not verify_only else _resolve_ceo_session_key(paths), res)
        res.step_ok("verify")
    except Exception as e:
        res.step_fail("verify", str(e))

    # Step 8 (B.6): embedding-health — always runs (read-only; Wave-5 pass + Sunday cron)
    # N32: a model-provider change is NOT complete until this passes on the box.
    try:
        step_embedding_health(paths, shared_utils, res)
    except Exception as e:
        res.step_fail("embedding-health", str(e))

    # Step 8b (A-U8): persona-embedding-drift — always runs (read-only, NON-
    # GATING advisory; Wave-5 pass + Sunday cron --verify-only pass). Never
    # raises the box's overall result to "failed" (see docstring).
    try:
        step_persona_embedding_drift(paths, shared_utils, res)
    except Exception as e:
        # Deliberately step_skip (not step_fail) — this is a NON-GATING
        # advisory probe; a probe-internal exception must never fail the box.
        res.step_skip("persona-embedding-drift", f"probe raised: {e}")

    # Step 8c (A-U12): persona-grounding-health — always runs (read-only,
    # NON-GATING advisory; Wave-5 pass + Sunday cron --verify-only pass).
    # Never raises the box's overall result to "failed" (see docstring).
    try:
        step_persona_grounding_health(paths, shared_utils, res)
    except Exception as e:
        # Deliberately step_skip (not step_fail) — this is a NON-GATING
        # advisory probe; a probe-internal exception must never fail the box.
        res.step_skip("persona-grounding-health", f"probe raised: {e}")

    # Step 8d (false-success closer): provisioning-completeness — always runs
    # (read-only; reflects LIVE box state). GATING: VERSION + BRANDING +
    # DEPARTMENTS + ROLE-FLOOR + PERSONAS must all be present, else the box is
    # flipped off "ok" with a per-check breakdown. SOP + CC-serving are reported but
    # stay gated where they already were (embedding-health / build-cc). A gate-
    # internal exception is FAIL-CLOSED — an unverifiable box must never look
    # PASS.
    try:
        step_provisioning_completeness(paths, res, pinned_onboarding_tag)
    except Exception as e:
        res.step_fail("provisioning-completeness", f"gate raised (fail-closed): {e}")

    # Step 9: log (skipped in verify-only as it's read-only mode)
    if not verify_only:
        try:
            step_log(paths, res, dry_run, pinned_onboarding_tag, cc_tag)
        except Exception as e:
            res.step_fail("log", str(e))  # noqa: PERF203

    # Determine final result
    has_failures = any("failed" in str(v) for v in res.steps.values())
    if dry_run:
        res.result = "dry-run"
    elif res.rollback:
        res.result = "rolled_back" if res.outcome == "ROLLED_BACK" else "failed"
    elif has_failures:
        total_steps = len(res.steps)
        failed_steps = sum(1 for v in res.steps.values() if "failed" in str(v))
        res.result = "failed" if failed_steps == total_steps else "partial"
    else:
        res.result = "ok"

    if dry_run or verify_only:
        res.outcome, res.outcome_detail = "SKIPPED", "dry-run" if dry_run else "verify-only"
    elif not res.rollback:
        broken = [s for s in _MUTATING_STEPS if str(res.steps.get(s, "")).startswith("failed")]
        if broken:   # un-rolled-back: [exit-3], or a Command Center step that changed nothing
            res.outcome = "FAILED"
            why = "; ".join(f"{s}: {res.steps[s][7:120]}" for s in broken)
            if "pull-onboarding" not in broken and str(res.steps.get("pull-onboarding", "")).startswith("ok"):
                cc_health = ((res.health.get("post") or {}).get("cc-health") or {}).get("status")
                why = (f"onboarding updated to {res.onboarding_version}, Command Center NOT updated "
                       f"(still v{(res.snapshot.get('cc') or {}).get('version') or res.cc_version}"
                       f"{', healthy' if cc_health == 'pass' else ''}): {why}")
            res.outcome_detail = why
        else:
            res.outcome = "UPDATED"
            warn = [k for k, v in res.steps.items() if str(v).startswith("failed")]
            # ok:advisory = the step succeeded with a note (e.g. update-skills.sh exit 2:
            # content current and stamped). It is not a failing check.
            advisory = [k for k, v in res.steps.items() if str(v).startswith("ok:advisory")]
            pre = res.health.get("preexisting_failures") or []
            healed = len(res.heal.get("attempts") or [])
            gaps = res.health.get("content_gaps_preexisting") or {}
            cfg = res.heal.get("config_pending")
            if gaps or cfg:
                res.heal["needs_attention"] = True
            res.outcome_detail = "; ".join(filter(None, [
                f"NEEDS ATTENTION - content gaps that were already there before this update: "
                + "; ".join(f"{k}: {v}" for k, v in gaps.items()) if gaps else "",
                f"NEEDS ATTENTION - the gateway still runs an older config after its restart: {cfg}"
                if cfg else "",
                f"fixed after {healed} attempt(s)" if healed else "",
                f"checks failing: {', '.join(warn)}" if warn else "",
                f"succeeded with advisories: {', '.join(advisory)}" if advisory else "",
                f"already unhealthy before update: {', '.join(pre)}" if pre else "",
            ]))

    return res


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="fleet_refresh_runner.py — per-box fleet-refresh state machine (PRD 1.11)"
    )
    parser.add_argument("--box",            default="local", help="Box name (for logging)")
    parser.add_argument("--shared-utils",   required=True,   help="Path to shared-utils/")
    parser.add_argument("--repo-root",      required=True,   help="Path to onboarding repo root")
    parser.add_argument("--apply",          action="store_true", help="Perform mutations (default: dry-run)")
    parser.add_argument("--verify-only",    action="store_true", help="Read-only verify only")
    parser.add_argument("--local",          action="store_true", help="Local mode (no SSH, sync build)")
    parser.add_argument("--force-cc",       action="store_true", help="Stash CC dirty tree instead of aborting")
    parser.add_argument("--expected-sha",   default=None,    help="Expected onboarding main SHA (informational)")
    parser.add_argument("--host-restart",   action="store_true",
                        help="fleet-refresh.sh can restart this box's container from the host")
    parser.add_argument("--continue-heal",  default=None, metavar="STATE",
                        help="resume the fix loop after a host-side container restart")
    parser.add_argument("--host-restart-result", default="", help="what the host restart did")
    args = parser.parse_args()

    shared_utils = Path(args.shared_utils).resolve()
    repo_root = Path(args.repo_root).resolve()

    if not shared_utils.is_dir():
        print(json.dumps({"box": args.box, "result": "failed",
                          "errors": [f"shared-utils not found: {shared_utils}"]}))
        sys.exit(1)

    dry_run = not args.apply

    result = run_box(
        box=args.box,
        shared_utils=shared_utils,
        repo_root=repo_root,
        dry_run=dry_run,
        verify_only=args.verify_only,
        local=args.local,
        force_cc=args.force_cc,
        expected_sha=args.expected_sha,
        host_restart=args.host_restart,
        continue_heal=Path(args.continue_heal) if args.continue_heal else None,
        host_restart_result=args.host_restart_result,
    )

    # Emit JSON to stdout
    print(json.dumps(result.to_dict(), default=str))

    # Exit code
    # 0  success / dry-run
    # 1  fatal (platform detection failure, missing required args)
    # 2  partial (at least one step failed but run continued)
    # 3  transient error (step emitted [exit-3] marker) — caller retries,
    #    then marks box UNKNOWN on repeated failure; NEVER destructive
    if result.result in ("ok", "dry-run"):
        sys.exit(0)
    elif result.result == "pending_host_restart":
        sys.exit(4)
    elif result.result in ("rolled_back", "skipped"):
        sys.exit(2)
    elif result.result == "partial":
        # Check if any step failed with the [exit-3] transient marker.
        transient = any(
            "[exit-3]" in str(v)
            for v in result.steps.values()
        )
        if transient:
            sys.exit(3)
        sys.exit(2)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
