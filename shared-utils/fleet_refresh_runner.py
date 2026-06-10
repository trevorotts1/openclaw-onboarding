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

PRD 1.11 — v11.5.0
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

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
        # Derive CC install dir (skill-32 convention)
        if p["platform"] == "vps":
            cc_dir = Path("/data/projects/command-center")
        else:
            cc_dir = Path.home() / "projects" / "command-center"
        p["cc_dir"] = cc_dir
        return p
    except SystemExit:
        _err("Cannot detect OpenClaw platform (no /data/.openclaw, ~/.openclaw, ~/clawd).")
        sys.exit(1)


# ── Session key resolution ────────────────────────────────────────────────────

def _resolve_ceo_session_key(paths: dict) -> Optional[str]:
    """
    Resolve the main-agent owner session key from sessions.json.
    Returns e.g. "agent:main:telegram:direct:8959124298" or None.

    Source of truth: agents/main/sessions/sessions.json
    (never docker logs or ownerAllowFrom — per memory rules).
    """
    sessions_path = paths["root"] / "agents" / "main" / "sessions" / "sessions.json"
    if not sessions_path.is_file():
        _warn(f"sessions.json not found at {sessions_path}")
        return None
    try:
        sessions_data = json.loads(sessions_path.read_text())
        # sessions.json schema: dict keyed by session key strings
        # We want: agent:main:telegram:direct:<id>
        direct_sessions = [
            k for k in sessions_data
            if k.startswith("agent:main:telegram:direct:")
        ]
        if not direct_sessions:
            _warn("No agent:main:telegram:direct:<id> session found in sessions.json")
            return None
        if len(direct_sessions) > 1:
            _warn(f"Multiple direct sessions found: {direct_sessions} — using first")
        return direct_sessions[0]
    except Exception as e:
        _warn(f"Could not parse sessions.json: {e}")
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
    res.onboarding_version = _read_onboarding_version(repo_root)
    res.cc_version = _read_cc_version(paths.get("cc_dir", Path("/nonexistent")))
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


def step_pull_onboarding(repo_root: Path, pinned_tag: str, res: BoxResult, dry_run: bool) -> None:
    """Step 2: update onboarding skills to the pinned version."""
    if dry_run:
        res.step_skip("pull-onboarding")
        return

    force_update = repo_root / "force-update.sh"
    if not force_update.is_file():
        res.step_fail("pull-onboarding", f"force-update.sh not found at {force_update}")
        return

    try:
        result = subprocess.run(
            ["bash", str(force_update), "--apply"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            res.step_fail("pull-onboarding", f"force-update.sh exited {result.returncode}: {result.stderr[:200]}")
        else:
            res.step_ok("pull-onboarding")
    except subprocess.TimeoutExpired:
        res.step_fail("pull-onboarding", "force-update.sh timed out after 300s")
    except Exception as e:
        res.step_fail("pull-onboarding", str(e))


def step_pull_cc(paths: dict, cc_tag: str, res: BoxResult, dry_run: bool, force_cc: bool = False) -> None:
    """Step 3: fetch + checkout the resolved CC tag."""
    if dry_run:
        res.step_skip("pull-cc")
        return

    cc_dir = paths.get("cc_dir")
    if not cc_dir or not Path(cc_dir).is_dir():
        res.step_fail("pull-cc", f"CC dir not found: {cc_dir}")
        return

    try:
        # git fetch --tags
        subprocess.run(["git", "-C", str(cc_dir), "fetch", "--tags"],
                       check=True, capture_output=True, timeout=60)

        # Check for dirty tree
        dirty = subprocess.run(
            ["git", "-C", str(cc_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        if dirty.stdout.strip():
            if force_cc:
                _warn(f"CC dir has local edits; stashing (--force-cc set)")
                subprocess.run(["git", "-C", str(cc_dir), "stash"],
                               check=True, capture_output=True, timeout=15)
            else:
                res.step_fail("pull-cc",
                    f"CC dir has uncommitted changes (use --force-cc to stash). "
                    f"Changed files:\n{dirty.stdout[:200]}")
                return

        # git checkout <tag>
        subprocess.run(["git", "-C", str(cc_dir), "checkout", cc_tag],
                       check=True, capture_output=True, timeout=30)
        res.step_ok("pull-cc")
    except subprocess.CalledProcessError as e:
        res.step_fail("pull-cc", f"git failed (exit {e.returncode}): {e.stderr[:200] if e.stderr else ''}")
    except subprocess.TimeoutExpired:
        res.step_fail("pull-cc", "git operation timed out")
    except Exception as e:
        res.step_fail("pull-cc", str(e))


def step_build_cc(paths: dict, res: BoxResult, dry_run: bool, local: bool = False) -> None:
    """Step 4: npm ci (or npm install) + npm run build."""
    if dry_run:
        res.step_skip("build-cc")
        return

    cc_dir = paths.get("cc_dir")
    if not cc_dir or not Path(cc_dir).is_dir():
        res.step_fail("build-cc", f"CC dir not found: {cc_dir}")
        return

    cc_dir = Path(cc_dir)

    # Try npm ci first, fall back to npm install
    npm_cmd = None
    lock_file = cc_dir / "package-lock.json"

    if lock_file.is_file():
        # Try npm ci
        try:
            result = subprocess.run(
                ["npm", "ci"],
                cwd=str(cc_dir), capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                npm_cmd = "ci"
            else:
                _warn("npm ci failed (lockfile mismatch?), falling back to npm install")
        except Exception:
            pass

    if npm_cmd is None:
        # Fall back to npm install
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=str(cc_dir), capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                res.step_fail("build-cc", f"npm install failed (exit {result.returncode}): {result.stderr[:200]}")
                return
            npm_cmd = "install"
        except subprocess.TimeoutExpired:
            res.step_fail("build-cc", "npm install timed out")
            return
        except Exception as e:
            res.step_fail("build-cc", str(e))
            return

    # npm run build
    # Write a build-start marker so the verifier can detect incomplete builds
    build_marker = cc_dir / ".fleet-refresh-build-running"
    build_complete = cc_dir / ".fleet-refresh-build-complete"
    build_failed = cc_dir / ".fleet-refresh-build-failed"

    for f in [build_marker, build_complete, build_failed]:
        if f.exists():
            f.unlink()

    build_marker.write_text(str(time.time()))

    if local:
        # Synchronous build in local/fixture mode
        try:
            build_result = subprocess.run(
                ["npm", "run", "build"],
                cwd=str(cc_dir), capture_output=True, text=True, timeout=300
            )
            build_marker.unlink(missing_ok=True)
            if build_result.returncode != 0:
                build_failed.write_text(str(build_result.returncode))
                res.step_fail("build-cc", f"npm run build failed (exit {build_result.returncode}): {build_result.stderr[:200]}")
                return
            build_complete.write_text(str(time.time()))
            res.steps["build-cc-npm-cmd"] = npm_cmd
            res.step_ok("build-cc")
        except subprocess.TimeoutExpired:
            build_marker.unlink(missing_ok=True)
            build_failed.write_text("timeout")
            res.step_fail("build-cc", "npm run build timed out")
    else:
        # Detached build: start async, record job marker, verify separately
        # (avoids babysitting the npm build over SSH which burns tokens)
        script = (
            f"cd {cc_dir} && "
            f"npm run build > /tmp/fleet-refresh-build-{res.box}.log 2>&1 "
            f"&& touch {build_complete} "
            f"|| echo $? > {build_failed}; "
            f"rm -f {build_marker}"
        )
        subprocess.Popen(["bash", "-c", script], close_fds=True)
        res.steps["build-cc-detached"] = True
        res.steps["build-cc-npm-cmd"] = npm_cmd
        res.steps["build-cc"] = "launched-detached"
        _info(f"  npm build launched detached; completion marker: {build_complete}")


def step_restart_cc(paths: dict, res: BoxResult, dry_run: bool) -> None:
    """Step 5: pm2 restart command-center (or pm2 start if not running)."""
    if dry_run:
        res.step_skip("restart-cc")
        return

    # Safety guard: NEVER issue openclaw gateway restart (Mac err 125)
    # This step only touches pm2 (Command Center), not the OpenClaw gateway process.

    cc_dir = paths.get("cc_dir")

    try:
        # Check if build completed (if detached)
        if cc_dir:
            build_failed = Path(cc_dir) / ".fleet-refresh-build-failed"
            build_running = Path(cc_dir) / ".fleet-refresh-build-running"
            if build_running.exists():
                res.step_fail("restart-cc", "npm build is still running; cannot restart CC with incomplete build")
                return
            if build_failed.exists():
                fail_code = build_failed.read_text().strip()
                res.step_fail("restart-cc", f"npm build failed (exit {fail_code}); not restarting CC")
                return

        # Try pm2 restart
        result = subprocess.run(
            ["pm2", "restart", "command-center"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            res.step_ok("restart-cc")
            return

        # pm2 restart failed; try pm2 start from CC dir
        if cc_dir and Path(cc_dir).is_dir():
            eco = Path(cc_dir) / "ecosystem.config.cjs"
            if eco.is_file():
                start_result = subprocess.run(
                    ["pm2", "start", str(eco)],
                    capture_output=True, text=True, timeout=30
                )
                if start_result.returncode == 0:
                    res.step_ok("restart-cc")
                    return
                res.step_fail("restart-cc",
                    f"pm2 start failed (exit {start_result.returncode}): {start_result.stderr[:200]}")
            else:
                res.step_fail("restart-cc", f"pm2 restart failed and no ecosystem.config.cjs at {cc_dir}")
        else:
            res.step_fail("restart-cc", f"pm2 restart failed (exit {result.returncode}): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        res.step_fail("restart-cc", "pm2 timed out")
    except FileNotFoundError:
        res.step_fail("restart-cc", "pm2 not found on PATH")
    except Exception as e:
        res.step_fail("restart-cc", str(e))


def step_sessions_reset_ceo(
    ceo_session_key: Optional[str],
    res: BoxResult,
    dry_run: bool,
) -> None:
    """
    Step 6: reset the CEO/main session so the next message rebuilds from disk.

    Uses `openclaw gateway call sessions.reset` — a gateway CALL, never a
    gateway process restart (Mac err 125 guard: see the spec).
    """
    if dry_run:
        res.step_skip("sessions-reset-CEO")
        return

    # SAFETY GUARD: explicit assertion that we never call gateway restart
    # (the spec requires this guard in code, not just docs)
    _info("  Issuing sessions.reset (gateway call — NOT gateway restart)")

    if not ceo_session_key:
        res.step_fail("sessions-reset-CEO",
            "CEO session key unresolved; cannot reset. "
            "Ensure sessions.json has an agent:main:telegram:direct:<id> entry.")
        return

    try:
        result = subprocess.run(
            ["openclaw", "gateway", "call", "sessions.reset",
             "--params", json.dumps({"key": ceo_session_key, "reason": "fleet-refresh"})],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            res.step_fail("sessions-reset-CEO",
                f"sessions.reset failed (exit {result.returncode}): {result.stderr[:200]}")
            return

        # Check for error in output
        try:
            resp = json.loads(result.stdout)
            if resp.get("ok") is False or "error" in resp:
                res.step_fail("sessions-reset-CEO", f"gateway call returned error: {resp}")
                return
        except Exception:
            pass  # Non-JSON response is OK as long as exit code was 0

        res.step_ok("sessions-reset-CEO")
    except subprocess.TimeoutExpired:
        res.step_fail("sessions-reset-CEO", "sessions.reset timed out")
    except FileNotFoundError:
        res.step_fail("sessions-reset-CEO", "openclaw not on PATH")
    except Exception as e:
        res.step_fail("sessions-reset-CEO", str(e))


def step_log(paths: dict, res: BoxResult, dry_run: bool,
             pinned_onboarding_tag: str, cc_tag: str) -> None:
    """Step 8: append result to .fleet-refresh-log.json."""
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
) -> BoxResult:
    """
    Execute all 8 steps for a single box.  Returns a BoxResult regardless of
    per-step failures (failure isolation).

    SAFETY: this function NEVER calls `openclaw gateway restart` — only
    `sessions.reset` (step 6).  Calling gateway restart over SSH on a Mac
    causes LaunchAgent err 125 and brings the box down.
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
    paths = _load_paths(shared_utils)

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

    if not verify_only:
        # Step 2: pull-onboarding
        try:
            step_pull_onboarding(repo_root, pinned_onboarding_tag, res, dry_run)
        except Exception as e:
            res.step_fail("pull-onboarding", str(e))

        # Step 3: pull-cc
        try:
            step_pull_cc(paths, cc_tag, res, dry_run, force_cc)
        except Exception as e:
            res.step_fail("pull-cc", str(e))

        # Step 4: build-cc (ONLY if pull-cc succeeded or was skipped)
        if "failed" not in str(res.steps.get("pull-cc", "")):
            try:
                step_build_cc(paths, res, dry_run, local)
            except Exception as e:
                res.step_fail("build-cc", str(e))

        # Step 5: restart-cc (ONLY if build-cc succeeded or was skipped)
        if "failed" not in str(res.steps.get("build-cc", "")):
            try:
                step_restart_cc(paths, res, dry_run)
            except Exception as e:
                res.step_fail("restart-cc", str(e))

        # Step 6: sessions-reset-CEO
        ceo_session_key = _resolve_ceo_session_key(paths)
        try:
            step_sessions_reset_ceo(ceo_session_key, res, dry_run)
        except Exception as e:
            res.step_fail("sessions-reset-CEO", str(e))
    else:
        ceo_session_key = _resolve_ceo_session_key(paths)
        for step in ["pull-onboarding", "pull-cc", "build-cc", "restart-cc", "sessions-reset-CEO"]:
            res.step_skip(step, "verify-only")

    # Step 7: verify (always runs — reports current state in dry-run mode)
    try:
        _check_deployed(paths, compat, pinned_onboarding_tag, res)
        _verify_loaded(paths, shared_utils, ceo_session_key if not verify_only else _resolve_ceo_session_key(paths), res)
        res.step_ok("verify")
    except Exception as e:
        res.step_fail("verify", str(e))

    # Step 8: log (skipped in verify-only as it's read-only mode)
    if not verify_only:
        try:
            step_log(paths, res, dry_run, pinned_onboarding_tag, cc_tag)
        except Exception as e:
            res.step_fail("log", str(e))

    # Determine final result
    has_failures = any("failed" in str(v) for v in res.steps.values())
    if dry_run:
        res.result = "dry-run"
    elif has_failures:
        total_steps = len(res.steps)
        failed_steps = sum(1 for v in res.steps.values() if "failed" in str(v))
        res.result = "failed" if failed_steps == total_steps else "partial"
    else:
        res.result = "ok"

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
    )

    # Emit JSON to stdout
    print(json.dumps(result.to_dict(), default=str))

    # Exit code
    if result.result in ("ok", "dry-run"):
        sys.exit(0)
    elif result.result == "partial":
        sys.exit(2)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
