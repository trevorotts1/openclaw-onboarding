#!/usr/bin/env python3
"""capability_probe.py — Skill 06 adaptive capability probe (plan P0-6 + 9.7-4).

WHY THIS EXISTS (skill6-fix-plan Part 2 / 2.1 / 9.2 / 9.6):
Skill 6 must run on OpenClaw pre-2.0 boxes (agent-browser only), OpenClaw 2.0+
(2026.8.1, managed browser plugin), 2026.9.x+ CUA boxes, Mac or VPS, with or
without Playwright, with or without a Firebase refresh token — by PROBING the
host, classifying it, selecting a browser lane, and degrading gracefully.
Never assume the operator reference box (2026.9.2 + CUA + 0.27.0 + Playwright).

ENGINE DEFAULT (2026-10-13, operator decision): the OpenClaw Chrome extension
is Skill 6's PRIMARY browser engine — the OpenClaw browser driven through the
extension on the operator's paired, already signed-in Chrome. The
openclaw_managed_browser lane is therefore selected FIRST, but only when the
extension itself is installed and current (see _probe_openclaw_extension);
agent-browser is the FALLBACK lane. Currency is enforced at install time by
scripts/check-openclaw-extension-version.sh; the probe re-checks it here so a
stale extension never silently becomes the default lane.

Output: one JSON document (stdout, and --out writes working/skill6-capability.json
under the skill dir by default). Every probe step is NON-FATAL: a failure sets the
field to false/"unknown" and appends to `warnings`. Secrets are booleans ONLY —
no secret VALUE is ever emitted, and env is the only source consulted.

ENVIRONMENT CAPABILITIES (Signature Launch spec 05 section 3, S06-02): the
report ALSO carries a top-level `environmentCapabilities` record (runtime/
harness identity, OS + architecture, container status, cgroup resource
limits, persistent storage root, client/location as references + booleans
only, per-lane browser availability + version, a REAL Playwright launch +
screenshot proof, OpenClaw extension currency/attach/health with honest
"unknown" states, approved auth methods, declared public/internal API
operations, and a per-section evidence timestamp). When the probe writes
its normal output file, the same record is also written standalone as
environment-capabilities.json next to it. All legacy top-level keys and
lane-selection semantics are unchanged; the legacy lane `extension.current`
keeps its historical boolean behavior (presence counts as current when the
expected version is unknown) — the new record is where unknown currentness
is surfaced as the string "unknown" instead of a silent pass.

Lane selection (plan 2.2 + 9.6 REVISED table, engine order revised 2026-10-13):
  1  openclaw_managed_browser — the OpenClaw browser lane (Chrome extension seat
                              first): ONLY if OpenClaw >= 2026.8.1 AND browser plugin
                              enabled AND `openclaw browser ...` CLI works AND the
                              OpenClaw Chrome extension is installed + current.
  2  agent_browser            — `agent-browser` on PATH (version reported). Lane 2b is
                              the same lane with playwright hybrid: iframeDrag.available.
  3  playwright_direct        — Playwright importable (legacy degraded fallback).
  4  existing_session         — NEVER default; only when env GHL_SKILL6_ALLOW_EXISTING_SESSION=1.
  5  cua_last_resort          — NEVER auto-selected.

If zero CDP lanes are usable -> selectedLane=null and blockers gets
"no-browser-lane" (fail-closed; plan 2.2 "no browser lane at all -> assert fail").

iframeDrag (plan 9.2): available = agent-browser present AND Playwright importable
(the hybrid lane). requires="playwright+cdp"; degradedWithout="STOP on cross-origin
tile/drag". Do NOT claim AB-only = full iframe capability.

No network at import/selftest time; --selftest is fully offline (injectable fake
runners, passes on a box with no binaries present). Stdlib only.
"""
from __future__ import annotations

import json
import os
import platform as _platform
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

# Plan Part 0: OpenClaw "2.0" shipped as version 2026.8.1 — that is the floor.
OC_2X_FLOOR = (2026, 8, 1)

# OpenClaw Chrome extension (Chrome Web Store identity, offered by the OpenClaw
# Foundation). The extension version preflight lives in
# scripts/check-openclaw-extension-version.sh; the probe re-derives the same
# facts from disk so lane selection can require an installed + current
# extension without launching a browser.
OPENCLAW_EXTENSION_ID = "kcdjddhmeafeomebliikmbpblkmkfoig"
# Env knobs (tests + operators): explicit Chrome user-data roots to scan
# (os.pathsep-separated), and an explicit expected-version override.
EXTENSION_ROOTS_ENV = "GHL_SKILL6_CHROME_PROFILE_ROOTS"
EXTENSION_EXPECTED_ENV = "SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"

# Secret env aliases. FIREBASE refresh token: the canonical chain is
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN -> GHL_FIREBASE_REFRESH_TOKEN ->
# FIREBASE_REFRESH_TOKEN (SKILL.md Prerequisites auth bullet). CAF_* is NOT canon
# for the refresh token here. LOCATION PIT chain per SKILL.md lines 128-150:
# GOHIGHLEVEL_API_KEY (preferred) -> GHL_API_KEY -> GOHIGHLEVEL_LOCATION_PIT ->
# GHL_LOCATION_PIT. Location id: GOHIGHLEVEL_LOCATION_ID -> GHL_LOCATION_ID.
# KIE image key: KIE_API_KEY. Booleans only in output — never values.
FIREBASE_TOKEN_ALIASES = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
    "FIREBASE_REFRESH_TOKEN",
)
LOCATION_PIT_ALIASES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
)
LOCATION_ID_ALIASES = (
    "GOHIGHLEVEL_LOCATION_ID",
    "GHL_LOCATION_ID",
)
KIE_KEY_ALIASES = ("KIE_API_KEY",)

# Optimizations are constant per plan 2.1 output contract.
OPTIMIZATIONS: Dict[str, Any] = {
    "preferHeadless": True,
    "maxParallelTabs": 1,
    "snapshotMode": "efficient",
    "iframeStrategy": "frame_scoped_snapshot",
}

# Probe subprocess timeouts (seconds) — every command is bounded, 5-15s.
TO_VERSION_S = 10
TO_PLUGINS_S = 10
TO_AGENT_BROWSER_S = 10
TO_PY_S = 15
TO_TABS_S = 10
# The Playwright launch+screenshot proof gets a longer bound: a cold
# headless Chromium start is slower than a version print, still bounded.
TO_PW_PROOF_S = 45

# Environment-capabilities knobs (S06-02). Storage root override + client
# identity references: VALUES are never emitted, only the env var NAME that
# supplied a value (a reference) and presence booleans.
STORAGE_ROOT_ENV = "GHL_SKILL6_STORAGE_ROOT"
CLIENT_IDENTITY_ALIASES = (
    "GHL_SKILL6_CLIENT_SLUG",
    "OPENCLAW_CLIENT_SLUG",
    "CLIENT_SLUG",
    "OPENCLAW_CLIENT_ID",
)

# Marker meaning "no usable limit could be determined" in the
# environment-capabilities record. Absent cgroup data is stated honestly
# with this string, never as a fabricated number.
UNBOUNDED_OR_UNKNOWN = "unbounded-or-unknown"

_SEMVER_RE = re.compile(r"(\d{1,4})\.(\d{1,3})\.(\d{1,3})")
_PLUGIN_RE = re.compile(r"^([A-Za-z0-9@/._-]+)\s+.*?(enabled|disabled)\b", re.IGNORECASE)


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(runner: Callable[..., Any], cmd: List[str], timeout: int) -> Any:
    """Run one probe command through the (injectable) runner; None on any failure."""
    try:
        return runner(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def _out(cp: Any) -> str:
    if cp is None or getattr(cp, "returncode", 1) != 0:
        return ""
    return (getattr(cp, "stdout", "") or "")


def _semver(version: str) -> Optional[List[int]]:
    m = _SEMVER_RE.search(version or "")
    if not m:
        return None
    return [int(m.group(1)), int(m.group(2)), int(m.group(3))]


def _semver_str(version: str) -> str:
    m = _SEMVER_RE.search(version or "")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else (version or "").strip()


_PLATFORM_MAP = {"darwin": "mac", "linux": "linux", "windows": "win"}


def _platform_name() -> str:
    return _PLATFORM_MAP.get(_platform.system().lower(), _platform.system().lower())


def _is_2x_or_newer(semver: Optional[List[int]]) -> bool:
    return bool(semver) and tuple(semver[:3]) >= OC_2X_FLOOR


def _secret_bool(env: Dict[str, str], aliases: tuple) -> bool:
    for name in aliases:
        val = env.get(name)
        if val is not None and val.strip() != "":
            return True
    return False


def _plugin_enabled(plugins_text: str, *names: str) -> bool:
    """True when any of `names` appears in `openclaw plugins list` as enabled.

    Parses line-form `name ... enabled`; falls back to bare-name mention when the
    output is a non-standard format but names the plugin at all (warning covers
    the ambiguity upstream)."""
    if not plugins_text:
        return False
    lines = [ln.strip() for ln in plugins_text.splitlines() if ln.strip()]
    for target in names:
        for ln in lines:
            if target in ln:
                m = _PLUGIN_RE.match(ln)
                if m:
                    return m.group(2).lower() == "enabled"
                # bare mention — treat as enabled only if "disabled" not on the line
                if "disabled" not in ln.lower():
                    return True
    return False


# ── individual probes (each non-fatal, each returns a partial dict) ──────────

def _probe_openclaw(runner: Callable[..., Any], env: Dict[str, str],
                    warnings: List[str]) -> Dict[str, Any]:
    cp = _run(runner, ["openclaw", "--version"], TO_VERSION_S)
    text = _out(cp)
    semver = _semver(text)
    if cp is None:
        warnings.append("openclaw --version probe failed (missing, timeout, or error)")
    elif cp.returncode != 0:
        warnings.append("openclaw --version exited non-zero")
    return {
        "cliPresent": cp is not None and cp.returncode == 0,
        "version": _semver_str(text.strip().splitlines()[0]) if text else "",
        "semver": semver,
        "is2xOrNewer": _is_2x_or_newer(semver),
    }


def _probe_agent_browser(runner: Callable[..., Any], env: Dict[str, str],
                         warnings: List[str]) -> Dict[str, Any]:
    # availability: `command -v agent-browser` equivalent via the runner
    cp = _run(runner, ["command", "-v", "agent-browser"], TO_VERSION_S)
    path = _out(cp).strip().splitlines()[0].strip() if _out(cp) else ""
    version = ""
    if path:
        vcp = _run(runner, ["agent-browser", "--version"], TO_AGENT_BROWSER_S)
        vtext = _out(vcp).strip().splitlines()[0] if _out(vcp) else ""
        version = _semver_str(vtext)
        if not version:
            warnings.append("agent-browser on PATH but --version unreadable")
    elif cp is not None and cp.returncode != 0:
        warnings.append("agent-browser not found on PATH")
    else:
        warnings.append("agent-browser probe failed (runner error or timeout)")
    return {
        "available": bool(path),
        "version": version,
        "path": path,
    }


def _probe_playwright(runner: Callable[..., Any], env: Dict[str, str],
                      warnings: List[str]) -> Dict[str, Any]:
    cp = _run(runner, [sys.executable or "python3", "-c", "import playwright"], TO_PY_S)
    available = cp is not None and cp.returncode == 0
    if cp is None:
        warnings.append("playwright import probe failed (timeout or runner error)")
    elif cp.returncode != 0:
        warnings.append("playwright python package not importable")
    # browsersInstalled: non-fatal check for the shared browsers dir
    browsers = False
    root = env.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(
        env.get("HOME", os.path.expanduser("~")), ".cache", "ms-playwright")
    try:
        browsers = os.path.isdir(root) and bool(os.listdir(root))
    except Exception:
        browsers = False
    if available and not browsers:
        warnings.append("playwright importable but no browser binaries found in "
                        f"{root}")
    return {"available": available, "browsersInstalled": bool(browsers)}


def _playwright_available(runner: Callable[..., Any], env: Dict[str, str]) -> bool:
    """Silent availability check — no duplicate warnings (reuses import probe)."""
    cp = _run(runner, [sys.executable or "python3", "-c", "import playwright"], TO_PY_S)
    return cp is not None and cp.returncode == 0


def _probe_openclaw_browser_plugin(runner: Callable[..., Any], env: Dict[str, str],
                                   oc: Dict[str, Any],
                                   warnings: List[str]) -> Dict[str, Any]:
    lane: Dict[str, Any] = {
        "pluginEnabled": False,
        "cliWorks": False,
        "playwrightAvailable": False,
        "profile": "openclaw",
        "doctorOk": False,
    }
    if not oc["cliPresent"]:
        warnings.append("openclaw CLI absent — managed-browser lane not probed")
        return lane
    pcp = _run(runner, ["openclaw", "plugins", "list"], TO_PLUGINS_S)
    ptext = _out(pcp)
    if pcp is None:
        warnings.append("openclaw plugins list probe failed (timeout or runner error)")
    elif pcp.returncode != 0:
        warnings.append("openclaw plugins list exited non-zero")
    lane["pluginEnabled"] = _plugin_enabled(ptext, "browser", "@openclaw/browser-plugin")
    lane["playwrightAvailable"] = _playwright_available(runner, env)
    # CLI works: `openclaw browser status` with the managed profile
    bcp = _run(runner, ["openclaw", "browser", "--browser-profile", "openclaw",
                        "status"], TO_VERSION_S)
    lane["cliWorks"] = bcp is not None and bcp.returncode == 0
    if bcp is not None and bcp.returncode != 0:
        warnings.append("openclaw browser status failed for profile 'openclaw'")
    # doctor --deep is optional and slow: short timeout, failure non-fatal
    dcp = _run(runner, ["openclaw", "browser", "doctor", "--deep"], 15)
    lane["doctorOk"] = dcp is not None and dcp.returncode == 0
    return lane


def _chrome_user_data_roots(env: Dict[str, str]) -> List[str]:
    """Chrome/Chromium user-data dirs to scan for the OpenClaw extension.

    Explicit env roots win (tests, operators); otherwise the OS Chrome dir
    plus every OpenClaw-managed browser user-data dir on the box. Pure path
    math — nothing is created and no browser is launched."""
    roots: List[str] = []
    raw = env.get(EXTENSION_ROOTS_ENV, "")
    if raw:
        roots.extend([p for p in raw.split(os.pathsep) if p])
    home = env.get("HOME") or os.path.expanduser("~")
    system = (env.get("OS") or "").lower()
    import platform as _pf
    plat = system or _pf.system().lower()
    if "darwin" in plat or "mac" in plat:
        roots.append(os.path.join(
            home, "Library", "Application Support", "Google", "Chrome"))
    else:
        roots.append(os.path.join(home, ".config", "google-chrome"))
        roots.append(os.path.join(home, ".config", "chromium"))
    oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
    browser_dir = os.path.join(oc_home, "browser")
    try:
        for name in sorted(os.listdir(browser_dir)):
            ud = os.path.join(browser_dir, name, "user-data")
            if os.path.isdir(ud):
                roots.append(ud)
    except OSError:
        pass
    seen: List[str] = []
    for r in roots:
        if r not in seen:
            seen.append(r)
    return seen


def _extension_version_in_user_data(user_data: str) -> Optional[str]:
    """Newest installed OpenClaw extension version in one user-data dir.

    Reads each profile's Secure Preferences; returns the max version string
    for OPENCLAW_EXTENSION_ID, or None when the extension is absent."""
    import glob as _glob
    best: Optional[List[int]] = None
    best_str: Optional[str] = None
    candidates = [user_data] + sorted(
        d for d in _glob.glob(os.path.join(user_data, "*")) if os.path.isdir(d))
    for prof in candidates:
        prefs = os.path.join(prof, "Secure Preferences")
        try:
            with open(prefs, "r") as f:
                data = json.load(f)
        except Exception:
            continue
        settings = (data.get("extensions", {}) or {}).get("settings", {}) or {}
        info = settings.get(OPENCLAW_EXTENSION_ID)
        if not info:
            continue
        ver = ((info.get("manifest") or {}).get("version")
               or info.get("version") or "")
        parsed = _semver(str(ver))
        if parsed and (best is None or parsed > best):
            best, best_str = parsed, _semver_str(str(ver))
    return best_str


def _probe_openclaw_extension(env: Dict[str, str],
                              warnings: List[str]) -> Dict[str, Any]:
    """OpenClaw Chrome extension presence + currency, from disk only.

    expectedVersion: EXTENSION_EXPECTED_ENV wins; else the version of the
    extension source the local OpenClaw install bundles
    (~/.openclaw/browser/chrome-extension/manifest.json); else None, in which
    case presence alone counts as current-with-warning (the standalone
    preflight script is the store-currency authority)."""
    installed: Optional[str] = None
    for root in _chrome_user_data_roots(env):
        ver = _extension_version_in_user_data(root)
        if ver and (installed is None
                    or (_semver(ver) or []) > (_semver(installed) or [])):
            installed = ver
    expected = env.get(EXTENSION_EXPECTED_ENV) or None
    if not expected:
        home = env.get("HOME") or os.path.expanduser("~")
        oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
        manifest = os.path.join(oc_home, "browser", "chrome-extension",
                                "manifest.json")
        try:
            with open(manifest, "r") as f:
                expected = str(json.load(f).get("version") or "") or None
        except Exception:
            expected = None
    if installed is None:
        current = False
        warnings.append("OpenClaw Chrome extension not found in any Chrome "
                        "profile on this box; the PRIMARY lane is unavailable "
                        "(install it from the Chrome Web Store; see "
                        "scripts/check-openclaw-extension-version.sh)")
    elif expected is None:
        current = True
        warnings.append("OpenClaw Chrome extension present (v%s) but the "
                        "expected version is unknown on this box; presence "
                        "accepted; run scripts/check-openclaw-extension-"
                        "version.sh for the store-currency check" % installed)
    else:
        current = (_semver(installed) or []) >= (_semver(expected) or [])
        if not current:
            warnings.append("OpenClaw Chrome extension is behind: installed "
                            "v%s, expected v%s; update it before relying on "
                            "the PRIMARY lane (scripts/check-openclaw-"
                            "extension-version.sh)" % (installed, expected))
    return {
        "installed": installed is not None,
        "version": installed,
        "expectedVersion": expected,
        "current": bool(current),
    }


def _probe_existing_session(env: Dict[str, str],
                            warnings: List[str]) -> Dict[str, Any]:
    opted_in = env.get("GHL_SKILL6_ALLOW_EXISTING_SESSION", "") == "1"
    return {
        "userProfileConfigured": opted_in,
        "chromeExtension": opted_in,
    }


def _probe_cua(runner: Callable[..., Any], env: Dict[str, str],
               warnings: List[str]) -> Dict[str, Any]:
    is_mac = sys.platform == "darwin"
    pcp = None
    if not is_mac:
        pcp = _run(runner, ["openclaw", "plugins", "list"], TO_PLUGINS_S)
    else:
        # mac side still parses plugins list when the CLI is present
        pcp = _run(runner, ["openclaw", "plugins", "list"], TO_PLUGINS_S)
    ptext = _out(pcp)
    plugin_enabled = _plugin_enabled(ptext, "cua-computer", "computer")
    app_present = False
    driver_present = False
    if is_mac:
        apps = env.get("GHL_SKILL6_APP_DIRS", "/Applications")
        try:
            app_present = os.path.isdir(os.path.join(apps, "OpenClaw.app"))
            driver_present = os.path.isdir(os.path.join(apps, "CuaDriver.app"))
        except Exception:
            app_present = driver_present = False
    provider = "none"
    if plugin_enabled and driver_present:
        provider = "cua"
    elif driver_present:
        provider = "peekaboo"
    elif plugin_enabled:
        provider = "unknown"
    return {
        "pluginEnabled": plugin_enabled,
        "appPresent": bool(app_present),
        "driverPresent": bool(driver_present),
        "providerSelected": provider,
    }


# ── environment capabilities (spec 05 section 3, S06-02) ─────────────────────
# Everything in this section is NON-FATAL and disk/process-local: a failure
# records "unknown" (or the UNBOUNDED_OR_UNKNOWN marker), never a guess.
# Secrets appear as booleans and env-var reference NAMES only.

def _utc_now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None


def _detect_harness(env: Dict[str, str]) -> Dict[str, Any]:
    """Runtime/harness identity from process/env markers only.

    Known markers win in a fixed order; anything else is stated as
    "unknown" — the harness is never guessed from the working directory
    or the model name."""
    checks = (
        ("claude-code", ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                         "CLAUDE_CODE_SSE_PORT")),
        ("codex", ("CODEX_SANDBOX", "CODEX_HOME", "CODEX_CLI")),
        ("openclaw", ("OPENCLAW_HOME", "OPENCLAW_GATEWAY_PORT",
                      "OPENCLAW_SESSION")),
        ("cursor", ("CURSOR_AGENT", "CURSOR_TRACE_ID")),
        ("9router-claude-nine", ("NINEROUTER_HOME", "CLAUDE_NINE_HOME")),
    )
    for name, markers in checks:
        for marker in markers:
            if env.get(marker):
                version = "unknown"
                for vkey in (f"{name.upper().replace('-', '_')}_VERSION",
                             "HARNESS_VERSION"):
                    if env.get(vkey):
                        version = str(env[vkey])
                        break
                return {"name": name, "version": version,
                        "evidence": f"env:{marker}"}
    if env.get("container"):
        return {"name": "unknown", "version": "unknown",
                "evidence": "container-env-only"}
    return {"name": "unknown", "version": "unknown", "evidence": "none"}


def _cgroup_paths(sys_root: Optional[str]) -> Dict[str, str]:
    """Absolute probe paths, optionally re-rooted under sys_root (tests)."""
    root = sys_root or ""
    return {
        "dockerenv": os.path.join(root, ".dockerenv"),
        "proc_cgroup": os.path.join(root, "proc", "1", "cgroup"),
        "cgroup_dir": os.path.join(root, "sys", "fs", "cgroup"),
    }


def _detect_container(env: Dict[str, str],
                      sys_root: Optional[str] = None) -> Dict[str, Any]:
    """Container status from real markers: /.dockerenv, the init process's
    cgroup lines, and the container= env marker runtimes inject."""
    paths = _cgroup_paths(sys_root)
    markers: List[str] = []
    if os.path.exists(paths["dockerenv"]):
        markers.append("/.dockerenv present")
    proc_cgroup = _read_text_file(paths["proc_cgroup"]) or ""
    for token in ("docker", "kubepods", "containerd", "libpod", "podman"):
        if token in proc_cgroup:
            markers.append(f"proc-1-cgroup:{token}")
            break
    if env.get("container"):
        markers.append("env:container")
    cg_version = "unknown"
    if os.path.exists(os.path.join(paths["cgroup_dir"], "cgroup.controllers")):
        cg_version = "v2"
    elif os.path.isdir(os.path.join(paths["cgroup_dir"], "memory")):
        cg_version = "v1"
        if os.path.exists(os.path.join(paths["cgroup_dir"],
                                       "cgroup.controllers")):
            cg_version = "mixed"
    return {
        "inContainer": bool(markers),
        "markers": markers,
        "cgroupVersion": cg_version,
    }


def _parse_cgroup_limits(sys_root: Optional[str] = None) -> Dict[str, Any]:
    """Real cgroup CPU/memory limits (spec 05 section 3: on Docker, inspect
    the real files). v2 files win when present; v1 named hierarchies are the
    fallback. Absent or 'no limit' values read UNBOUNDED_OR_UNKNOWN."""
    paths = _cgroup_paths(sys_root)
    base = paths["cgroup_dir"]
    result: Dict[str, Any] = {
        "memoryLimitBytes": UNBOUNDED_OR_UNKNOWN,
        "cpuLimitCores": UNBOUNDED_OR_UNKNOWN,
        "source": "none",
    }
    # ── cgroup v2 (unified hierarchy) ──
    mem_max = _read_text_file(os.path.join(base, "memory.max"))
    cpu_max = _read_text_file(os.path.join(base, "cpu.max"))
    if mem_max is not None or cpu_max is not None:
        result["source"] = "cgroup-v2"
        if mem_max is not None:
            mem_max = mem_max.strip()
            if mem_max != "max":
                try:
                    result["memoryLimitBytes"] = int(mem_max)
                except ValueError:
                    pass
        if cpu_max is not None:
            parts = cpu_max.split()
            if len(parts) == 2 and parts[0] != "max":
                try:
                    quota, period = int(parts[0]), int(parts[1])
                    if quota > 0 and period > 0:
                        result["cpuLimitCores"] = quota / period
                except ValueError:
                    pass
        return result
    # ── cgroup v1 (named hierarchies) ──
    mem_v1 = _read_text_file(os.path.join(base, "memory",
                                          "memory.limit_in_bytes"))
    quota_v1 = _read_text_file(os.path.join(base, "cpu",
                                            "cpu.cfs_quota_us"))
    period_v1 = _read_text_file(os.path.join(base, "cpu",
                                             "cpu.cfs_period_us"))
    if mem_v1 is not None or quota_v1 is not None:
        result["source"] = "cgroup-v1"
        if mem_v1 is not None:
            try:
                limit = int(mem_v1.strip())
                # The kernel reports "no limit" as a value near LONG_MAX
                # (page-aligned); anything >= 2**60 is that sentinel.
                if 0 < limit < 2 ** 60:
                    result["memoryLimitBytes"] = limit
            except ValueError:
                pass
        if quota_v1 is not None and period_v1 is not None:
            try:
                quota, period = int(quota_v1.strip()), int(period_v1.strip())
                if quota > 0 and period > 0:
                    result["cpuLimitCores"] = quota / period
            except ValueError:
                pass
    return result


def _storage_root(env: Dict[str, str]) -> Dict[str, Any]:
    """The persistent storage root actually in use, in resolution order:
    explicit env override, the fleet durable root (/data/.openclaw), the
    operator's OpenClaw home, else this skill's working/ evidence dir."""
    override = env.get(STORAGE_ROOT_ENV)
    if override:
        root, source = override, f"env:{STORAGE_ROOT_ENV}"
    else:
        home = env.get("HOME") or os.path.expanduser("~")
        oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
        if os.path.isdir("/data/.openclaw"):
            root, source = "/data/.openclaw", "durable-root"
        elif os.path.isdir(oc_home):
            root, source = oc_home, "openclaw-home"
        else:
            skill_dir = os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))
            root = os.path.join(skill_dir, "working")
            source = "skill-working-dir"
    try:
        writable = os.path.isdir(root) and os.access(root, os.W_OK)
    except Exception:
        writable = False
    return {"persistentRoot": root, "source": source, "writable": bool(writable)}


def _first_env_reference(env: Dict[str, str], aliases: tuple) -> Optional[str]:
    """Name of the first env var in `aliases` holding a value (reference
    only — the value itself is never returned or emitted)."""
    for name in aliases:
        val = env.get(name)
        if val is not None and val.strip() != "":
            return name
    return None


# The Playwright proof child: launches an isolated headless Chromium page,
# screenshots to a temp path OUTSIDE the skill dir, prints one JSON verdict
# line, and removes its temp artifacts. Exit code is always 0; the verdict
# line is the evidence. It deliberately imports via playwright.sync_api so
# the probe's own "import playwright" package check stays the only command
# carrying that exact string.
_PW_PROOF_SCRIPT = r"""
import json, os, tempfile
def _verdict(launched, shot, err):
    print(json.dumps({"launched": launched, "screenshotTaken": shot,
                      "errorClass": err}))
try:
    from playwright.sync_api import sync_playwright
except Exception:
    _verdict(False, False, "playwright-missing")
    raise SystemExit(0)
_tmp = tempfile.mkdtemp(prefix="skill6-pw-proof-")
_shot = os.path.join(_tmp, "proof.png")
try:
    with sync_playwright() as _p:
        _b = _p.chromium.launch(headless=True)
        _pg = _b.new_page()
        _pg.set_content("<title>skill6-proof</title><h1>ok</h1>")
        _pg.screenshot(path=_shot)
        _b.close()
    _ok = os.path.isfile(_shot) and os.path.getsize(_shot) > 0
    _verdict(True, bool(_ok), None if _ok else "screenshot-failed")
except Exception as _e:
    _msg = str(_e)
    if "Executable doesn't exist" in _msg or "has not been installed" in _msg:
        _verdict(False, False, "browser-binary-missing")
    else:
        _verdict(False, False, "launch-failed")
finally:
    try:
        if os.path.exists(_shot):
            os.remove(_shot)
        os.rmdir(_tmp)
    except Exception:
        pass
"""


def _default_playwright_launcher(runner: Callable[..., Any],
                                 package_available: bool) -> Dict[str, Any]:
    """Run the REAL launch proof through the injectable runner and parse
    the child's JSON verdict. A transport-level failure (no verdict line)
    is classified from the package probe, never upgraded to a pass."""
    proof: Dict[str, Any] = {"attempted": True, "launched": False,
                             "screenshotTaken": False, "errorClass": None}
    cp = _run(runner, [sys.executable or "python3", "-c", _PW_PROOF_SCRIPT],
              TO_PW_PROOF_S)
    verdict = None
    for line in (_out(cp) or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                verdict = json.loads(line)
            except Exception:
                verdict = None
    if verdict is not None:
        proof["launched"] = bool(verdict.get("launched"))
        proof["screenshotTaken"] = bool(verdict.get("screenshotTaken"))
        proof["errorClass"] = verdict.get("errorClass")
    else:
        proof["errorClass"] = ("playwright-missing" if not package_available
                               else "launch-failed")
    return proof


def _extension_expected_source(env: Dict[str, str]) -> str:
    """Where the expected extension version came from (mirrors
    _probe_openclaw_extension's resolution order, for the record)."""
    if env.get(EXTENSION_EXPECTED_ENV):
        return f"env:{EXTENSION_EXPECTED_ENV}"
    home = env.get("HOME") or os.path.expanduser("~")
    oc_home = env.get("OPENCLAW_HOME") or os.path.join(home, ".openclaw")
    manifest = os.path.join(oc_home, "browser", "chrome-extension",
                            "manifest.json")
    if _read_text_file(manifest) is not None:
        return "bundled-manifest:~/.openclaw/browser/chrome-extension/manifest.json"
    return "unknown"


# Declared API operations (spec 05 sections 3-4): what the skill's adapters
# implement, labeled DECLARED — a capability report is not a live call, and
# nothing here claims a live proof that did not happen in this run.
_DECLARED_API_OPERATIONS: Dict[str, Any] = {
    "verification": "declared-not-live-proven",
    "public": [
        {"operation": "funnels.list", "method": "GET",
         "path": "/funnels/funnel/list", "kind": "read"},
        {"operation": "funnels.page.list", "method": "GET",
         "path": "/funnels/page", "kind": "read"},
        {"operation": "products.crud", "method": "CRUD",
         "path": "/products", "kind": "write"},
        {"operation": "custom-values.crud", "method": "CRUD",
         "path": "/locations/{locationId}/customValues", "kind": "write"},
        {"operation": "tags.create", "method": "POST",
         "path": "/locations/{locationId}/tags", "kind": "write"},
        {"operation": "funnel-redirects.crud", "method": "CRUD",
         "path": "/funnels/lookup/redirect", "kind": "write"},
        {"operation": "media.upload", "method": "POST",
         "path": "/medias/upload-file", "kind": "write"},
    ],
    "internal": [
        {"operation": "spa.funnels.page.list", "method": "GET",
         "path": "/funnels/page/list", "kind": "read",
         "note": "internal SPA family; version/capture-gated, not an "
                 "official stable API"},
        {"operation": "spa.pages.autosave", "method": "POST",
         "path": "builder autosave (captured contract)", "kind": "write",
         "note": "internal SPA family; version/capture-gated, not an "
                 "official stable API"},
        {"operation": "spa.workflows.triggers", "method": "GET/POST",
         "path": "workflow trigger read/rewire (captured contract)",
         "kind": "write",
         "note": "internal SPA family; version/capture-gated, not an "
                 "official stable API"},
    ],
}


def _build_environment_capabilities(
        runner: Callable[..., Any], env: Dict[str, str],
        stamp: Callable[[], str],
        oc: Dict[str, Any], lanes: Dict[str, Any], secrets: Dict[str, bool],
        pw_package_available: bool,
        pw_launcher: Optional[Callable[[], Dict[str, Any]]] = None,
        sys_root: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the spec 05 section 3 environment-capabilities record from
    the sections the probe already measured, plus the new environment
    probes. Every section carries its own evidence timestamp."""
    harness = _detect_harness(env)
    runtime = {
        "name": harness["name"],
        "version": harness["version"],
        "evidence": harness["evidence"],
        "python": _platform.python_version(),
        "evidenceAt": stamp(),
    }
    os_section = {
        "system": _platform.system(),
        "release": _platform.release(),
        "architecture": _platform.machine() or "unknown",
        "platform": _platform_name(),
        "evidenceAt": stamp(),
    }
    container_probe = _detect_container(env, sys_root)
    container = {
        "inContainer": container_probe["inContainer"],
        "markers": container_probe["markers"],
        "cgroupVersion": container_probe["cgroupVersion"],
        "evidenceAt": stamp(),
    }
    limits = _parse_cgroup_limits(sys_root)
    resource_limits = {
        "memoryLimitBytes": limits["memoryLimitBytes"],
        "cpuLimitCores": limits["cpuLimitCores"],
        "cpuCount": os.cpu_count(),
        "source": limits["source"],
        "evidenceAt": stamp(),
    }
    storage_probe = _storage_root(env)
    storage = {
        "persistentRoot": storage_probe["persistentRoot"],
        "source": storage_probe["source"],
        "writable": storage_probe["writable"],
        "evidenceAt": stamp(),
    }
    client_ref = _first_env_reference(env, CLIENT_IDENTITY_ALIASES)
    client = {
        "identityPresent": client_ref is not None,
        "identityReference": client_ref,
        "evidenceAt": stamp(),
    }
    location_ref = _first_env_reference(env, LOCATION_ID_ALIASES)
    location = {
        "present": bool(secrets.get("locationId")),
        "reference": location_ref,
        # A disk/env probe cannot verify a location against the account;
        # stated honestly instead of inheriting the presence boolean.
        "verified": "unknown",
        "evidenceAt": stamp(),
    }
    ab = lanes["agent_browser"]
    managed = lanes["openclaw_managed_browser"]
    pw_lane = lanes["playwright_direct"]
    chrome_version = "unknown"
    for binary in ("google-chrome", "chromium", "chromium-browser"):
        vcp = _run(runner, [binary, "--version"], TO_VERSION_S)
        vtext = _out(vcp).strip()
        if vtext:
            chrome_version = _semver_str(vtext.splitlines()[0])
            break
    pw_version = "unknown"
    if pw_package_available:
        vcp = _run(runner, [sys.executable or "python3", "-c",
                            "import importlib.metadata as _m; "
                            "print(_m.version('playwright'))"], TO_PY_S)
        vtext = _out(vcp).strip()
        if vtext:
            pw_version = vtext.splitlines()[0].strip()
    browsers = {
        "agentBrowser": {"available": bool(ab["available"]),
                         "version": ab.get("version") or "unknown"},
        "openclawManagedBrowser": {
            "pluginEnabled": bool(managed["pluginEnabled"]),
            "cliWorks": bool(managed["cliWorks"]),
            "profile": managed.get("profile") or "unknown"},
        "chrome": {
            "userDataFound": bool(_chrome_user_data_roots(env)
                                  and any(os.path.isdir(r) for r in
                                          _chrome_user_data_roots(env))),
            "version": chrome_version},
        "playwright": {
            "packageAvailable": bool(pw_lane["available"]),
            "packageVersion": pw_version,
            "browsersInstalled": bool(pw_lane["browsersInstalled"])},
        "evidenceAt": stamp(),
    }
    if pw_launcher is not None:
        proof = dict(pw_launcher())
        proof.setdefault("attempted", True)
    else:
        proof = _default_playwright_launcher(runner, pw_package_available)
    playwright_proof = {
        "attempted": bool(proof.get("attempted")),
        "launched": bool(proof.get("launched")),
        "screenshotTaken": bool(proof.get("screenshotTaken")),
        "errorClass": proof.get("errorClass"),
        "evidenceAt": stamp(),
    }
    ext = managed.get("extension") or {}
    if not ext.get("installed"):
        ext_current: Any = False
    elif ext.get("expectedVersion") is None:
        # Per spec 05 section 3: unknown expected version means unknown
        # currentness. The legacy lane field keeps its boolean behavior;
        # this record is where the unknown is surfaced.
        ext_current = "unknown"
    else:
        ext_current = bool(ext.get("current"))
    attached = "unknown"
    connection_health = "unknown"
    if oc.get("cliPresent"):
        tcp = _run(runner, ["openclaw", "browser", "tabs"], TO_TABS_S)
        if tcp is not None and tcp.returncode == 0:
            attached = "attached"
            connection_health = "healthy"
        elif managed.get("cliWorks"):
            connection_health = "degraded"
    extension = {
        "installed": bool(ext.get("installed")),
        "installedVersion": ext.get("version"),
        "expectedVersion": ext.get("expectedVersion"),
        "expectedSource": _extension_expected_source(env),
        "current": ext_current,
        "attached": attached,
        "connectionHealth": connection_health,
        "evidenceAt": stamp(),
    }
    skill_tools = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    auth_methods = {
        "firebaseRefreshToken": {"approved": True,
                                 "present": bool(
                                     secrets.get("firebaseRefreshToken"))},
        "locationPit": {"approved": True,
                        "present": bool(secrets.get("locationPit"))},
        "locationId": {"approved": True,
                       "present": bool(secrets.get("locationId"))},
        "gatedEmail2faBootstrap": {
            "approved": True,
            "modulePresent": os.path.isfile(
                os.path.join(skill_tools, "ghl_auth.py"))},
        "evidenceAt": stamp(),
    }
    api_operations = dict(_DECLARED_API_OPERATIONS)
    api_operations["evidenceAt"] = stamp()
    return {
        "schema": "skill6-environment-capabilities/1",
        "generatedAt": stamp(),
        "runtime": runtime,
        "os": os_section,
        "container": container,
        "resourceLimits": resource_limits,
        "storage": storage,
        "client": client,
        "location": location,
        "browsers": browsers,
        "playwrightProof": playwright_proof,
        "extension": extension,
        "authMethods": auth_methods,
        "apiOperations": api_operations,
    }


# ── lane selection (plan 2.2 + 9.6 REVISED) ───────────────────────────────────

def _oc_lane_eligible(oc: Dict[str, Any]) -> bool:
    """The OpenClaw browser lane (PRIMARY since 2026-10-13) requires the
    plugin + a working CLI + the Chrome extension installed and current."""
    ext = oc.get("extension") or {}
    return bool(oc.get("pluginEnabled") and oc.get("cliWorks")
                and ext.get("installed") and ext.get("current"))


def _select_lane(lanes: Dict[str, Any], env: Dict[str, str]) -> Optional[str]:
    ab = lanes["agent_browser"]["available"]
    pw = lanes["playwright_direct"]["available"]
    oc = lanes["openclaw_managed_browser"]
    if _oc_lane_eligible(oc):
        return "openclaw_managed_browser"  # 1 — PRIMARY (extension default)
    if ab:
        return "agent_browser"          # 2 / 2b (2b when playwright also present)
    if pw:
        return "playwright_direct"      # 3
    if env.get("GHL_SKILL6_ALLOW_EXISTING_SESSION", "") == "1":
        return "existing_session"       # 4 — explicit opt-in only
    return None                          # 5 cua_last_resort NEVER auto-selected


# ── main probe ────────────────────────────────────────────────────────────────

def run_probe(runner: Callable[..., Any] = subprocess.run,
              env: Optional[Dict[str, str]] = None,
              now: Optional[str] = None,
              paths: Optional[Dict[str, str]] = None,
              pw_launcher: Optional[Callable[[], Dict[str, Any]]] = None,
              sys_root: Optional[str] = None) -> Dict[str, Any]:
    """Run the full capability probe. All deps injectable for tests.

    runner: subprocess.run-compatible callable (cmd, capture_output, text, timeout).
    env:    environment mapping (default os.environ). Booleans only in output.
    now:    ISO-8601 probedAt override (default UTC now).
    paths:  optional {"appDirs": ...} override for mac app checks.
    pw_launcher: optional () -> proof-dict override for the Playwright
            launch proof (tests); default runs the real isolated launch.
    sys_root: optional filesystem root prefix for the container/cgroup
            probes (tests); default reads the real /, /.dockerenv,
            /proc/1/cgroup and /sys/fs/cgroup.
    """
    if env is None:
        env = dict(os.environ)
    explicit_now = now is not None
    if now is None:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

    def _stamp() -> str:
        # Per-section evidence timestamps (spec 05 section 3): a fresh UTC
        # stamp per section in a live run; the caller's fixed `now` when
        # one was injected (tests stay deterministic).
        return now if explicit_now else _utc_now_iso()
    warnings: List[str] = []

    if paths and paths.get("appDirs"):
        env = dict(env)
        env["GHL_SKILL6_APP_DIRS"] = paths["appDirs"]

    oc = _probe_openclaw(runner, env, warnings)
    ab = _probe_agent_browser(runner, env, warnings)
    pw = _probe_playwright(runner, env, warnings)
    managed = _probe_openclaw_browser_plugin(runner, env, oc, warnings)
    extension = _probe_openclaw_extension(env, warnings)
    existing = _probe_existing_session(env, warnings)
    cua = _probe_cua(runner, env, warnings)

    lanes = {
        "agent_browser": ab,
        "openclaw_managed_browser": {
            "pluginEnabled": managed["pluginEnabled"],
            "cliWorks": managed["cliWorks"],
            "playwrightAvailable": managed["playwrightAvailable"],
            "profile": managed["profile"],
            "doctorOk": managed["doctorOk"],
            "extension": extension,
        },
        "existing_session": existing,
        "playwright_direct": pw,
        "cua": cua,
        "computer_peekaboo": {"likely": cua["driverPresent"]},
    }

    secrets = {
        "firebaseRefreshToken": _secret_bool(env, FIREBASE_TOKEN_ALIASES),
        "locationPit": _secret_bool(env, LOCATION_PIT_ALIASES),
        "locationId": _secret_bool(env, LOCATION_ID_ALIASES),
        "kieApiKey": _secret_bool(env, KIE_KEY_ALIASES),
    }

    # Secrets policy (plan 2.4-1: QC asserts secrets policy) — missing GHL
    # credentials are WARNINGS, not blockers; blocker only for the browser lane.
    if not secrets["firebaseRefreshToken"]:
        warnings.append("no Firebase refresh token alias found in env "
                        "(GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / "
                        "GHL_FIREBASE_REFRESH_TOKEN / FIREBASE_REFRESH_TOKEN)")
    if not secrets["locationPit"]:
        warnings.append("no LOCATION PIT alias found in env "
                        "(GOHIGHLEVEL_API_KEY / GHL_API_KEY / "
                        "GOHIGHLEVEL_LOCATION_PIT / GHL_LOCATION_PIT)")
    if not secrets["locationId"]:
        warnings.append("no location id alias found in env "
                        "(GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID)")

    selected = _select_lane(lanes, env)

    # OpenClaw-lane gate: the OpenClaw browser lane only when OC >= 2026.8.1
    # AND plugin enabled AND cli works AND the Chrome extension is installed
    # and current (plan 2.2, engine order revised 2026-10-13). Demote with a
    # warning when below the floor.
    oc_semver = oc.get("semver")
    if selected == "openclaw_managed_browser" and not _is_2x_or_newer(oc_semver):
        selected = "playwright_direct" if pw["available"] else None
        warnings.append("openclaw older than 2026.8.1 — managed-browser lane "
                        "not eligible (plan 2.2)")
    elif (oc.get("cliPresent") and managed["pluginEnabled"]
            and managed["cliWorks"] and not _is_2x_or_newer(oc_semver)):
        # Below-floor OpenClaw: the lane was never selected (the extension
        # gate or the floor), but the operator still gets the floor warning.
        warnings.append("openclaw older than 2026.8.1 — managed-browser lane "
                        "not eligible (plan 2.2)")

    fallback_chain: List[str] = []
    if _oc_lane_eligible(lanes["openclaw_managed_browser"]):
        fallback_chain.append("openclaw_managed_browser")
    if ab["available"]:
        fallback_chain.append("agent_browser")
    if pw["available"]:
        fallback_chain.append("playwright_direct")
    fallback_chain.append("cua_last_resort")

    # iframeDrag (plan 9.2 / 9.7-4): available = agent-browser present AND
    # Playwright importable (the hybrid). Fail-closed without it.
    iframe_drag = {
        "available": bool(ab["available"] and pw["available"]),
        "requires": "playwright+cdp",
        "degradedWithout": "STOP on cross-origin tile/drag",
    }
    if ab["available"] and not pw["available"]:
        warnings.append("agent-browser present without Playwright — cross-origin "
                        "iframe drag unavailable (lane degrades to partial)")

    blockers: List[str] = []
    if selected is None:
        blockers.append("no-browser-lane")

    environment_capabilities = _build_environment_capabilities(
        runner, env, _stamp, oc, lanes, secrets,
        pw_package_available=pw["available"],
        pw_launcher=pw_launcher, sys_root=sys_root)

    return {
        "probedAt": now,
        "platform": _platform_name(),  # mac | linux | win per plan Part 2.1
        "openclaw": oc,
        "lanes": lanes,
        "secrets": secrets,
        "selectedLane": selected,
        "fallbackChain": fallback_chain,
        "optimizations": dict(OPTIMIZATIONS),
        "iframeDrag": iframe_drag,
        "blockers": blockers,
        "warnings": warnings,
        "environmentCapabilities": environment_capabilities,
    }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="capability_probe",
        description="Skill 06 adaptive browser capability probe. Stdlib only, "
                    "booleans-only secrets, non-fatal probes.")
    p.add_argument("--out", default=None,
                   help="Write JSON to PATH (default working/skill6-capability.json "
                        "relative to the skill dir)")
    p.add_argument("--json", action="store_true",
                   help="Print JSON to stdout only (do not write the file)")
    p.add_argument("--reprobe", action="store_true",
                   help="Ignore any cached/freshness state and probe afresh")
    p.add_argument("--selftest", action="store_true",
                   help="Offline self-test with fake runners (no binaries needed)")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    result = run_probe()
    text = json.dumps(result, indent=2, sort_keys=False)
    print(text)
    if not args.json:
        # skill dir = parent of tools/ (this file lives in 06-ghl-install-pages/tools/)
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workdir = os.path.join(skill_dir, "working")
        out_path = args.out or os.path.join(workdir, "skill6-capability.json")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "w") as f:
                f.write(text + "\n")
        except Exception as e:  # non-fatal: stdout already has the JSON
            print(f"warning: could not write {out_path}: {e}", file=sys.stderr)
        # Spec 05 section 3: the environment-capabilities record also
        # stands alone as environment-capabilities.json next to the
        # capability output.
        envcaps_path = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                                    "environment-capabilities.json")
        try:
            with open(envcaps_path, "w") as f:
                f.write(json.dumps(result["environmentCapabilities"],
                                   indent=2) + "\n")
        except Exception as e:  # non-fatal, same policy as the main output
            print(f"warning: could not write {envcaps_path}: {e}",
                  file=sys.stderr)
    return 0


def _selftest() -> int:
    """Offline: injectable fake runners, zero binaries required. Exit 0 on pass."""
    errors: List[str] = []

    # 1. nothing on the box -> selectedLane null + no-browser-lane blocker
    def r_none(cmd, **kw):
        cp = type("CP", (), {})()
        cp.returncode = 1
        cp.stdout = ""
        cp.stderr = ""
        return cp

    res = run_probe(runner=r_none, env={}, now="2026-09-07T00:00:00Z")
    if res["selectedLane"] is not None:
        errors.append(f"empty box should select no lane, got {res['selectedLane']}")
    if "no-browser-lane" not in res["blockers"]:
        errors.append("empty box missing no-browser-lane blocker")

    # 1b. environment-capabilities record rides along (spec 05 section 3):
    #     shape present, Playwright proof attempted and honestly failed on
    #     an empty box, extension currentness False when not installed.
    envcaps = res.get("environmentCapabilities") or {}
    for section in ("runtime", "os", "container", "resourceLimits",
                    "storage", "client", "location", "browsers",
                    "playwrightProof", "extension", "authMethods",
                    "apiOperations"):
        if section not in envcaps:
            errors.append(f"environmentCapabilities missing section {section}")
        elif section != "apiOperations" and "evidenceAt" not in envcaps[section]:
            errors.append(f"environmentCapabilities.{section} missing evidenceAt")
    proof = envcaps.get("playwrightProof") or {}
    if proof.get("attempted") is not True or proof.get("launched") is not False:
        errors.append(f"empty-box playwright proof wrong: {proof}")
    _ext = envcaps.get("extension") or {}
    if _ext.get("current") not in (True, False, "unknown"):
        errors.append(f"extension currentness not an honest state: {_ext}")
    if not _ext.get("installed") and _ext.get("current") is not False:
        # The extension probe reads the real disk even with fake runners,
        # so an installed extension here is the host's own — but a NOT
        # installed extension must never read as current.
        errors.append("extension absent yet currentness is not False")

    # 2. agent-browser only -> lane 1
    def r_ab(cmd, **kw):
        cp = type("CP", (), {})()
        cp.returncode = 0
        joined = " ".join(cmd)
        if cmd[:2] == ["command", "-v"]:
            cp.stdout = "/usr/local/bin/agent-browser\n"
        elif "agent-browser" in joined and "--version" in joined:
            cp.stdout = "0.27.0\n"
        else:
            cp.stdout = ""
            cp.returncode = 1
        cp.stderr = ""
        return cp

    res = run_probe(runner=r_ab, env={}, now="2026-09-07T00:00:00Z")
    if res["selectedLane"] != "agent_browser":
        errors.append(f"ab-only box should select agent_browser, got {res['selectedLane']}")
    if res["lanes"]["agent_browser"]["version"] != "0.27.0":
        errors.append("ab version not parsed")
    if res["lanes"]["agent_browser"]["available"] is not True:
        errors.append("ab availability wrong")

    # 3. semver floor: 2026.8.1 is 2x; 2026.7.9 is not; 2026.9.2 is
    if not _is_2x_or_newer([2026, 8, 1]):
        errors.append("2026.8.1 should count as 2xOrNewer")
    if _is_2x_or_newer([2026, 7, 9]):
        errors.append("2026.7.9 should NOT count as 2xOrNewer")
    if not _is_2x_or_newer([2026, 9, 2]):
        errors.append("2026.9.2 should count as 2xOrNewer")

    # 4. secrets: booleans from env, never values
    fake_env = {"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "SECRETVALUE",
                "GHL_API_KEY": "PITVALUE",
                "GHL_LOCATION_ID": "LOCID", "KIE_API_KEY": "KIEVAL"}
    res = run_probe(runner=r_none, env=fake_env, now="2026-09-07T00:00:00Z")
    if res["secrets"] != {"firebaseRefreshToken": True, "locationPit": True,
                          "locationId": True, "kieApiKey": True}:
        errors.append(f"secrets booleans wrong: {res['secrets']}")
    blob = json.dumps(res)
    for secret_val in ("SECRETVALUE", "PITVALUE", "LOCID", "KIEVAL"):
        if secret_val in blob:
            errors.append("secret value leaked into probe output")

    # 5. fallbackChain ordering (ab-only box, re-run r_ab): agent_browser first,
    #    no managed lane, cua_last_resort terminal
    res_ab = run_probe(runner=r_ab, env={}, now="2026-09-07T00:00:00Z")
    if res_ab["fallbackChain"] != ["agent_browser", "cua_last_resort"]:
        errors.append(f"ab-only fallbackChain wrong: {res_ab['fallbackChain']}")
    if res_ab["fallbackChain"][-1] != "cua_last_resort":
        errors.append("fallbackChain must end with cua_last_resort")
    # 6. iframeDrag fail-closed: AB present without Playwright -> available false
    if res_ab["iframeDrag"]["available"] is not False:
        errors.append("iframeDrag must be false without Playwright")
    if res_ab["iframeDrag"]["requires"] != "playwright+cdp":
        errors.append("iframeDrag.requires must be 'playwright+cdp'")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — lane selection + blockers + semver floor + "
          "secrets booleans (fake runners, offline, no binaries needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())