#!/usr/bin/env python3
"""capability_probe.py — Skill 06 adaptive capability probe (plan P0-6 + 9.7-4).

WHY THIS EXISTS (skill6-fix-plan Part 2 / 2.1 / 9.2 / 9.6):
Skill 6 must run on OpenClaw pre-2.0 boxes (agent-browser only), OpenClaw 2.0+
(2026.8.1, managed browser plugin), 2026.9.x+ CUA boxes, Mac or VPS, with or
without Playwright, with or without a Firebase refresh token — by PROBING the
host, classifying it, selecting a browser lane, and degrading gracefully.
Never assume the operator reference box (2026.9.2 + CUA + 0.27.0 + Playwright).

Output: one JSON document (stdout, and --out writes working/skill6-capability.json
under the skill dir by default). Every probe step is NON-FATAL: a failure sets the
field to false/"unknown" and appends to `warnings`. Secrets are booleans ONLY —
no secret VALUE is ever emitted, and env is the only source consulted.

Lane selection (plan 2.2 + 9.6 REVISED table):
  1  agent_browser            — `agent-browser` on PATH (version reported). Lane 1b is
                              the same lane with playwright hybrid: iframeDrag.available.
  2  openclaw_managed_browser — ONLY if OpenClaw >= 2026.8.1 AND browser plugin enabled
                              AND `openclaw browser ...` CLI works.
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


# ── lane selection (plan 2.2 + 9.6 REVISED) ───────────────────────────────────

def _select_lane(lanes: Dict[str, Any], env: Dict[str, str]) -> Optional[str]:
    ab = lanes["agent_browser"]["available"]
    pw = lanes["playwright_direct"]["available"]
    oc = lanes["openclaw_managed_browser"]
    if ab:
        return "agent_browser"          # 1 / 1b (1b when playwright also present)
    if oc["pluginEnabled"] and oc["cliWorks"]:
        return "openclaw_managed_browser"  # 2
    if pw:
        return "playwright_direct"      # 3
    if env.get("GHL_SKILL6_ALLOW_EXISTING_SESSION", "") == "1":
        return "existing_session"       # 4 — explicit opt-in only
    return None                          # 5 cua_last_resort NEVER auto-selected


# ── main probe ────────────────────────────────────────────────────────────────

def run_probe(runner: Callable[..., Any] = subprocess.run,
              env: Optional[Dict[str, str]] = None,
              now: Optional[str] = None,
              paths: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run the full capability probe. All deps injectable for tests.

    runner: subprocess.run-compatible callable (cmd, capture_output, text, timeout).
    env:    environment mapping (default os.environ). Booleans only in output.
    now:    ISO-8601 probedAt override (default UTC now).
    paths:  optional {"appDirs": ...} override for mac app checks.
    """
    if env is None:
        env = dict(os.environ)
    if now is None:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    warnings: List[str] = []

    if paths and paths.get("appDirs"):
        env = dict(env)
        env["GHL_SKILL6_APP_DIRS"] = paths["appDirs"]

    oc = _probe_openclaw(runner, env, warnings)
    ab = _probe_agent_browser(runner, env, warnings)
    pw = _probe_playwright(runner, env, warnings)
    managed = _probe_openclaw_browser_plugin(runner, env, oc, warnings)
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

    # Lane-2 gate: managed browser only when OC >= 2026.8.1 AND plugin enabled
    # AND cli works (plan 2.2). Demote with a warning when below the floor.
    oc_semver = oc.get("semver")
    if selected == "openclaw_managed_browser" and not _is_2x_or_newer(oc_semver):
        selected = "playwright_direct" if pw["available"] else None
        warnings.append("openclaw older than 2026.8.1 — managed-browser lane "
                        "not eligible (plan 2.2)")

    fallback_chain: List[str] = []
    if ab["available"]:
        fallback_chain.append("agent_browser")
    if managed["pluginEnabled"] and managed["cliWorks"]:
        fallback_chain.append("openclaw_managed_browser")
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