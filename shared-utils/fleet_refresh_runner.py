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
import time
from pathlib import Path
from typing import Any, Optional

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
    Returns e.g. "agent:main:telegram:direct:1234567890" or None.

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
    # D1: read the ACTIVE skills-dir stamp (paths["skills"]), not repo_root —
    # update-skills.sh writes <skills-dir>/.onboarding-version, never
    # repo_root/.onboarding-version. Matches step_pull_onboarding's read-path
    # so detect/verify never disagree with the actual roll outcome.
    skills_dir = Path(paths.get("skills") or Path(paths["root"]) / "skills")
    res.onboarding_version = _read_onboarding_version(skills_dir)
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


def step_pull_onboarding(paths: dict, repo_root: Path, pinned_tag: str, res: BoxResult, dry_run: bool) -> None:
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
        return

    update_skills = repo_root / "update-skills.sh"
    if not update_skills.is_file():
        res.step_fail("pull-onboarding", f"update-skills.sh not found at {update_skills}")
        return

    skills_dir = Path(paths.get("skills") or Path(paths["root"]) / "skills")
    stamp_file = skills_dir / ".onboarding-version"

    try:
        result = subprocess.run(
            ["bash", str(update_skills)],
            capture_output=True, text=True, timeout=1200,
            # SECURITY/PRIVACY (v20.0.9): the fleet roll is MAINTENANCE — export
            # OPENCLAW_MAINTENANCE_SILENT=1 into the updater's environment so it
            # (and every subprocess it spawns: migrate-existing-workforce.sh and
            # the embedded qc-completeness.sh) HARD-suppresses any QC Telegram to a
            # client chat, independent of the box's chat/account config. This runner
            # executes ON the target box, so the var reaches the remote updater.
            env={**os.environ, "OPENCLAW_UPDATE_AUTO_SYNC": "1",
                 "OPENCLAW_MAINTENANCE_SILENT": "1"},
        )
        post_stamp = stamp_file.read_text().strip() if stamp_file.is_file() else None
        if result.returncode == 0 and post_stamp == pinned_tag:
            res.onboarding_version = post_stamp
            res.step_ok("pull-onboarding")
        else:
            res.step_fail(
                "pull-onboarding",
                f"update-skills.sh exited {result.returncode}; stamp={post_stamp!r} "
                f"expected={pinned_tag!r}: {result.stderr[:200]}"
            )
    except subprocess.TimeoutExpired:
        res.step_fail("pull-onboarding", "update-skills.sh timed out after 1200s")
    except Exception as e:
        res.step_fail("pull-onboarding", str(e))


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
    if not cc_dir or not Path(cc_dir).is_dir():
        res.step_fail("pull-cc", f"CC dir not found: {cc_dir}")
        return

    try:
        subprocess.run(
            ["git", "-C", str(cc_dir), "fetch", "origin", "main"],
            check=True, capture_output=True, timeout=60,
        )

        def current_on_main() -> bool:
            branch = subprocess.run(
                ["git", "-C", str(cc_dir), "symbolic-ref", "--quiet", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if branch.returncode != 0 or branch.stdout.strip() != "main":
                return False
            ancestry = subprocess.run(
                ["git", "-C", str(cc_dir), "merge-base", "--is-ancestor", "origin/main", "HEAD"],
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
            update_result = subprocess.run(
                ["bash", str(updater)], cwd=str(cc_dir), env=update_env,
                capture_output=True, text=True, timeout=1200,
            )
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
        res.step_ok("pull-cc")
    except subprocess.CalledProcessError as e:
        res.step_fail("pull-cc", f"git failed (exit {e.returncode}): {e.stderr[:200] if e.stderr else ''}")
    except subprocess.TimeoutExpired:
        res.step_fail("pull-cc", "git operation timed out")
    except Exception as e:
        res.step_fail("pull-cc", str(e))


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

    try:
        result = subprocess.run(
            ["node", "--import", "tsx", "--test", str(duck_test)],
            cwd=str(cc_dir),
            capture_output=True, text=True, timeout=300,
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
    if not cc_dir or not Path(cc_dir).is_dir():
        res.step_fail("build-cc", f"CC dir not found: {cc_dir}")
        return

    cc_dir = Path(cc_dir)

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
        deploy_result = subprocess.run(
            ["bash", str(atomic_deploy)],
            cwd=str(cc_dir),
            capture_output=True, text=True, timeout=600,
        )
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

        if deploy_result.returncode != 0:
            res.step_fail("build-cc", f"atomic-deploy.sh exited {deploy_result.returncode}: {deploy_detail}")
            return

    except subprocess.TimeoutExpired:
        res.step_fail("build-cc", "atomic-deploy.sh timed out after 600s")
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
    if not cc_dir or not Path(cc_dir).is_dir():
        res.step_fail("restart-cc", f"CC dir not found: {cc_dir}")
        return

    cc_dir = Path(cc_dir)

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
        restart_result = subprocess.run(
            ["bash", str(atomic_deploy)],
            cwd=str(cc_dir),
            capture_output=True, text=True, timeout=600,
        )
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
        res.step_fail("restart-cc", "atomic-deploy.sh timed out after 600s")
        return
    except Exception as exc:
        res.step_fail("restart-cc", f"atomic-deploy.sh failed to launch: {exc}")
        return

    res.step_ok("restart-cc")


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
        res.step_fail("sessions-reset-CEO",
            "CEO session key unresolved; cannot reset. "
            "Ensure sessions.json has an agent:main:telegram:direct:<id> entry.")
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
    company_dir = paths.get("company_dir")
    if company_dir:
        company_dir = Path(company_dir)
    else:
        company_dir = None
        try:
            if company_root.is_dir():
                for child in sorted(company_root.iterdir()):
                    if child.is_dir() and (
                        (child / "company-config.json").is_file()
                        or (child / "departments.json").is_file()
                    ):
                        company_dir = child
                        break
        except OSError:
            company_dir = None

    def _pick(key: str, rel: str) -> Path:
        v = paths.get(key)
        if v:
            return Path(v)
        return (company_dir / rel) if company_dir else (workspace / rel)

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
        "build_state":        Path(paths.get("build_state") or (workspace / ".workforce-build-state.json")),
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
    depts = _prov_read_json(pp.get("departments_json"))
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
            step_pull_onboarding(paths, repo_root, pinned_onboarding_tag, res, dry_run)
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
    # 0  success / dry-run
    # 1  fatal (platform detection failure, missing required args)
    # 2  partial (at least one step failed but run continued)
    # 3  transient error (step emitted [exit-3] marker) — caller retries,
    #    then marks box UNKNOWN on repeated failure; NEVER destructive
    if result.result in ("ok", "dry-run"):
        sys.exit(0)
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
