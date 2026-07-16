#!/usr/bin/env python3
"""
p304-agent-browser-conformance-probe.py — P3-04 (c)5: per-box Skill-6
agent-browser conformance probe.

SHIPS IN P6-01 (built and QC'd now; run against live fleet boxes only in the
final rollout phase per meta-rule 2.1/2.7 — no canary, evidence-backed QC now,
post-deploy per-box validation in the real rollout). This script is the probe
ARTIFACT the spec's P3-04 (c)5 line names; it is not executed against any
live/client box by this build unit.

WHAT THIS CHECKS (verbatim from the spec's P3-04 (c)5 line)
--------------------------------------------------------------
  1. headed flag false            -> browser_manager.sh's box-level headless
                                      lock (`unset AGENT_BROWSER_HEADED` +
                                      `export AGENT_BROWSER_HEADED=false`) is
                                      present in source (the B1 lock, D6).
  2. guard version >= v14.1.4     -> GUARD_AGENT_BROWSER_MANAGED_VERSION
                                      (guard-agent-browser-managed.sh) AND
                                      BM_HEADLESS_LOCK_FLOOR
                                      (browser_manager.sh) both meet the
                                      B1 version-gate floor.
  3. reaper cron present          -> an `agent-browser-reaper` cron with the
                                      hourly `13 * * * *` schedule is
                                      registered (`openclaw cron list --json`
                                      by default; injectable for tests/CI via
                                      --cron-list-json / --cron-list-file).
  4. zero stale Chromium procs    -> zero Chromium/headless_shell processes
                                      scoped to the agent-browser/Playwright
                                      profile tree (the SAME match the host
                                      reaper itself uses: AB_ENGINE_DIR /
                                      AB_REAPER_PLAYWRIGHT_DIR via
                                      --user-data-dir|--profile|profile-
                                      directory) whose elapsed age exceeds the
                                      session TTL (default 1800s, the
                                      AB_SESSION_TTL browser_manager.sh
                                      default; --ttl-seconds overrides).
                                      Count of stale procs found = the
                                      operator's slow-box blast-radius number
                                      (P3-04 (b) residual note).
  5. Mac-vs-VPS env matrix        -> reuses 06-ghl-install-pages/ENV-MATRIX.md's
                                      OWN canonical primitives
                                      (browser_manager.durable_root() /
                                      is_vps() / supervisor()) for platform
                                      detection — never a new hand-rolled
                                      check (the doc's own adaptation-contract
                                      rule 1) — plus a static bash-3.2-safety
                                      scan of the 3 core scripts for the
                                      doc's own banned-builtins list
                                      (mapfile / readarray / declare -A /
                                      local -A / ${var,,} / ${var^^} / wait -n).

This module performs NO GHL/browser I/O and NEVER kills a process — read-only,
same discipline as ghl_selector_drift_probe.py / scripts/probe/p207-*.py. Every
live-system read (cron list, `ps`, the 3 source files) is dependency-injected
via a CLI override so this probe is fully unit-testable offline; only the
CLI's DEFAULTS touch the real box (openclaw cron list / ps / disk reads).

USAGE
  p304-agent-browser-conformance-probe.py [--json] [--box <label>]
      [--repo-root DIR] [--browser-manager-sh PATH] [--guard-sh PATH]
      [--reaper-sh PATH]
      [--cron-list-json JSON] [--cron-list-file PATH]
      [--ps-output-file PATH] [--ttl-seconds N] [--now-epoch N]
      [--platform mac|vps|unknown] [--env EXTRA=VAL ...]

EXIT CODES
  0  ARMED        (all 4 gating checks pass; env matrix is reported, not gating
                    except its bash-3.2-safety sub-check, which IS gating)
  1  DEGRADED     (one or more gating checks failed)
  2  UNRESOLVABLE (a check could not run at all — e.g. no cron-list source
                   available and no override given; never fabricated as a pass)
================================================================================
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import importlib.util as _ilu
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent.parent

BM_HEADLESS_LOCK_FLOOR_DEFAULT_LABEL = "v14.1.4"

# ENV-MATRIX.md's own banned-builtins list (adaptation contract rule 3) — the
# exact set that broke `parallel_saves.sh`'s `mapfile -t` under real bash 3.2.
_BANNED_BASH32_PATTERNS = [
    (re.compile(r"\bmapfile\b"), "mapfile"),
    (re.compile(r"\breadarray\b"), "readarray"),
    (re.compile(r"\bdeclare\s+-A\b"), "declare -A"),
    (re.compile(r"\blocal\s+-A\b"), "local -A"),
    (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*,,\}"), "${var,,}"),
    (re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\^\^\}"), "${var^^}"),
    (re.compile(r"\bwait\s+-n\b"), "wait -n"),
]


def _hostname():
    try:
        import socket
        return socket.gethostname().split(".")[0]
    except OSError:
        return "unknown"


def _load_module(mod_name, path):
    spec = _ilu.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def _parse_version(label):
    """'v14.1.4' -> (14, 1, 4). Non-numeric/missing -> None (never guessed)."""
    if not label:
        return None
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", label.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def _version_at_least(label, floor_label):
    v = _parse_version(label)
    floor = _parse_version(floor_label)
    if v is None or floor is None:
        return None  # unresolvable, never guessed as pass or fail
    return v >= floor


# ---------------------------------------------------------------------------
# Check 1 — headed flag locked false (B1/D6 source-presence check)
# ---------------------------------------------------------------------------
def check_headless_lock(browser_manager_sh):
    p = Path(browser_manager_sh)
    if not p.is_file():
        return {
            "browser_manager_sh": str(p),
            "unset_present": False,
            "export_false_present": False,
            "note": f"browser_manager.sh not found at {p} (skill 06 not installed on this box)",
            "rc": 2,
        }
    text = p.read_text(encoding="utf-8", errors="replace")
    unset_present = bool(re.search(r"^\s*unset\s+AGENT_BROWSER_HEADED\b", text, re.MULTILINE))
    export_false_present = bool(
        re.search(r"^\s*export\s+AGENT_BROWSER_HEADED=false\b", text, re.MULTILINE)
    )
    ok = unset_present and export_false_present
    return {
        "browser_manager_sh": str(p),
        "unset_present": unset_present,
        "export_false_present": export_false_present,
        "note": (
            "box-level headless lock present (unset + export AGENT_BROWSER_HEADED=false)"
            if ok else
            "box-level headless lock MISSING or PARTIAL — a truthy AGENT_BROWSER_HEADED "
            "could open a visible window (D6 violation)"
        ),
        "rc": 0 if ok else 1,
    }


# ---------------------------------------------------------------------------
# Check 2 — guard version + headless-lock floor >= v14.1.4 (B1 version gate)
# ---------------------------------------------------------------------------
def check_version_floor(guard_sh, browser_manager_sh, floor_label=BM_HEADLESS_LOCK_FLOOR_DEFAULT_LABEL):
    def _extract(path, marker):
        p = Path(path)
        if not p.is_file():
            return None, f"{p} not found"
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(marker + r'\s*=\s*"([^"]+)"', text)
        if not m:
            return None, f"{marker} marker not found in {p}"
        return m.group(1), None

    guard_version, guard_err = _extract(guard_sh, "GUARD_AGENT_BROWSER_MANAGED_VERSION")
    lock_floor, lock_err = _extract(browser_manager_sh, "BM_HEADLESS_LOCK_FLOOR")

    guard_ok = _version_at_least(guard_version, floor_label)
    lock_ok = _version_at_least(lock_floor, floor_label)

    if guard_ok is None or lock_ok is None:
        return {
            "guard_version": guard_version,
            "bm_headless_lock_floor": lock_floor,
            "floor": floor_label,
            "guard_meets_floor": guard_ok,
            "lock_meets_floor": lock_ok,
            "note": f"could not resolve one or both versions ({guard_err or ''} {lock_err or ''})".strip(),
            "rc": 2,
        }

    ok = guard_ok and lock_ok
    return {
        "guard_version": guard_version,
        "bm_headless_lock_floor": lock_floor,
        "floor": floor_label,
        "guard_meets_floor": guard_ok,
        "lock_meets_floor": lock_ok,
        "note": (
            f"guard ({guard_version}) and headless-lock floor ({lock_floor}) both meet {floor_label}"
            if ok else
            f"guard ({guard_version}) or headless-lock floor ({lock_floor}) is BELOW {floor_label} "
            "(pre-B1 box — headed/version regressions are unguarded)"
        ),
        "rc": 0 if ok else 1,
    }


# ---------------------------------------------------------------------------
# Check 3 — reaper cron present (hourly, 13 * * * *)
# ---------------------------------------------------------------------------
def _run_cron_list_json():
    if shutil.which("openclaw") is None:
        return None, "openclaw CLI not on PATH"
    try:
        out = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"openclaw cron list --json failed to run: {exc}"
    if out.returncode != 0 or not out.stdout.strip():
        return None, f"openclaw cron list --json exited {out.returncode} with no output"
    try:
        return json.loads(out.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"openclaw cron list --json did not return valid JSON: {exc}"


def check_reaper_cron(cron_list_json=None, cron_list_file=None):
    if cron_list_json is not None:
        crons = cron_list_json
        source = "--cron-list-json override"
    elif cron_list_file is not None:
        try:
            crons = json.loads(Path(cron_list_file).read_text(encoding="utf-8"))
            source = f"--cron-list-file {cron_list_file}"
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "source": f"--cron-list-file {cron_list_file}",
                "reaper_present": False,
                "schedule_hourly": False,
                "note": f"could not read/parse --cron-list-file: {exc}",
                "rc": 2,
            }
    else:
        crons, err = _run_cron_list_json()
        source = "openclaw cron list --json (live)"
        if crons is None:
            return {
                "source": source,
                "reaper_present": False,
                "schedule_hourly": False,
                "note": f"cron list unavailable: {err} -- cannot verify reaper registration "
                        "(never fabricated as a pass)",
                "rc": 2,
            }

    # Accept either a bare list or {"crons": [...]} / {"data": [...]} shapes.
    entries = crons if isinstance(crons, list) else (crons.get("crons") or crons.get("data") or [])
    reaper_entries = [
        e for e in entries
        if isinstance(e, dict) and "agent-browser-reaper" in str(e.get("name", ""))
    ]
    if not reaper_entries:
        return {
            "source": source,
            "reaper_present": False,
            "schedule_hourly": False,
            "note": "no cron named 'agent-browser-reaper' found in cron list",
            "rc": 1,
        }
    schedules = [str(e.get("schedule", "")) for e in reaper_entries]
    hourly = any("13 * * * *" in s for s in schedules)
    return {
        "source": source,
        "reaper_present": True,
        "schedule_hourly": hourly,
        "schedules_seen": schedules,
        "note": (
            "agent-browser-reaper cron present with the hourly (13 * * * *) schedule"
            if hourly else
            f"agent-browser-reaper cron present but NOT on the hourly schedule "
            f"(saw: {schedules})"
        ),
        "rc": 0 if hourly else 1,
    }


# ---------------------------------------------------------------------------
# Check 4 — zero stale Chromium processes under the profile (age > TTL)
# ---------------------------------------------------------------------------
_ETIME_RE = re.compile(
    r"^(?:(?:(\d+)-)?(\d+):)?(\d+):(\d+)$"  # [[DD-]HH:]MM:SS
)


def _etime_to_seconds(etime):
    """Parse `ps -o etime=` output ('MM:SS', 'HH:MM:SS', 'DD-HH:MM:SS') to
    whole seconds. Unparseable -> None (never guessed)."""
    etime = etime.strip()
    m = _ETIME_RE.match(etime)
    if not m:
        return None
    days, hours, minutes, seconds = m.groups()
    total = int(minutes) * 60 + int(seconds)
    if hours:
        total += int(hours) * 3600
    if days:
        total += int(days) * 86400
    return total


def _run_ps_scoped():
    try:
        out = subprocess.run(
            ["ps", "-axww", "-o", "pid=,etime=,command="],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"`ps` failed to run: {exc}"
    if out.returncode != 0:
        return None, f"`ps` exited {out.returncode}"
    return out.stdout, None


def check_stale_chromium(ps_output=None, ps_output_file=None,
                          ab_engine_dir=None, playwright_dir=None,
                          ttl_seconds=1800, home=None):
    home = home or os.environ.get("HOME", "")
    ab_engine_dir = ab_engine_dir or os.path.join(home, ".agent-browser")
    playwright_dir = playwright_dir or os.path.join(home, ".cache", "ms-playwright-ghl")

    if ps_output is not None:
        text, source = ps_output, "--ps-output override"
    elif ps_output_file is not None:
        try:
            text = Path(ps_output_file).read_text(encoding="utf-8", errors="replace")
            source = f"--ps-output-file {ps_output_file}"
        except OSError as exc:
            return {
                "source": f"--ps-output-file {ps_output_file}",
                "scoped_total": 0, "stale_count": 0, "stale_pids": [],
                "note": f"could not read --ps-output-file: {exc}",
                "rc": 2,
            }
    else:
        text, err = _run_ps_scoped()
        source = "ps -axww -o pid=,etime=,command= (live)"
        if text is None:
            return {
                "source": source,
                "scoped_total": 0, "stale_count": 0, "stale_pids": [],
                "note": f"process table unavailable: {err} -- cannot verify (never fabricated as a pass)",
                "rc": 2,
            }

    # SAME match the host reaper itself uses (scripts/agent-browser-reaper.sh):
    # a --user-data-dir/--profile/profile-directory flag pointing under the
    # scoped profile tree, AND the command names chrom*/headless_shell,
    # excluding grep's own line (n/a here — we match python-side, not piped
    # through a literal `grep`).
    profile_alt = "|".join(re.escape(d) for d in (ab_engine_dir, playwright_dir) if d)
    scoped_re = re.compile(
        r"(--user-data-dir|--profile|profile-directory)[= ]?\S*(?:" + profile_alt + r")"
    ) if profile_alt else None
    chrom_re = re.compile(r"chrom|headless_shell", re.IGNORECASE)

    scoped = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, etime, command = parts[0], parts[1], parts[2]
        if scoped_re is None or not scoped_re.search(command):
            continue
        if not chrom_re.search(command):
            continue
        age = _etime_to_seconds(etime)
        scoped.append({"pid": pid, "etime": etime, "age_seconds": age, "command": command[:160]})

    stale = [p for p in scoped if p["age_seconds"] is not None and p["age_seconds"] > ttl_seconds]
    ok = len(stale) == 0
    return {
        "source": source,
        "ab_engine_dir": ab_engine_dir,
        "playwright_dir": playwright_dir,
        "ttl_seconds": ttl_seconds,
        "scoped_total": len(scoped),
        "stale_count": len(stale),
        "stale_pids": [p["pid"] for p in stale],
        "note": (
            f"zero Chromium/headless_shell procs under the profile tree older than TTL ({ttl_seconds}s) "
            f"out of {len(scoped)} scoped"
            if ok else
            f"{len(stale)} Chromium/headless_shell proc(s) under the profile tree exceed the TTL "
            f"({ttl_seconds}s) -- this count IS the operator's slow-box blast-radius number for this box"
        ),
        "rc": 0 if ok else 1,
    }


# ---------------------------------------------------------------------------
# Check 5 — Mac-vs-VPS env matrix (ENV-MATRIX.md's own primitives, no new
# hand-rolled check) + bash-3.2-safety static scan (the doc's banned list)
# ---------------------------------------------------------------------------
def check_env_matrix(browser_manager_py, scripts_to_scan, platform_override=None, env=None):
    env = env if env is not None else os.environ
    result = {
        "platform": None, "durable_root": None, "supervisor": None,
        "bash32_violations": [], "note": "", "rc": 0,
    }

    if platform_override in ("mac", "vps"):
        result["platform"] = platform_override
    else:
        p = Path(browser_manager_py)
        if not p.is_file():
            result["note"] = f"browser_manager.py not found at {p}; platform undetermined"
            result["rc"] = 2
        else:
            mod = _load_module("browser_manager__p304probe", str(p))
            result["durable_root"] = mod.durable_root(env=dict(env))
            result["platform"] = "vps" if mod.is_vps(env=dict(env)) else (
                "mac" if result["durable_root"] else "unknown"
            )
            result["supervisor"] = mod.supervisor(env=dict(env))

    violations = []
    for script_path in scripts_to_scan:
        sp = Path(script_path)
        if not sp.is_file():
            continue
        text = sp.read_text(encoding="utf-8", errors="replace")
        # Strip full-line + inline `#` comments FIRST (same heuristic as
        # guard-agent-browser-managed.sh's own strip_bash) — otherwise this
        # scan false-positives on the doc's OWN prose explaining the bash-3.2
        # incompatibility (e.g. "Do NOT reintroduce `declare -A` / `mapfile`
        # here" in agent-browser-reaper.sh's header comment, which literally
        # contains the banned tokens as documentation, not code).
        code_lines = []
        for line in text.splitlines():
            if re.match(r"^\s*#", line):
                code_lines.append("")
                continue
            code_lines.append(re.sub(r"(?<!\S)#.*$", "", line))
        stripped_text = "\n".join(code_lines)
        for pat, label in _BANNED_BASH32_PATTERNS:
            for m in pat.finditer(stripped_text):
                lineno = stripped_text.count("\n", 0, m.start()) + 1
                violations.append({"file": str(sp), "line": lineno, "construct": label})
    result["bash32_violations"] = violations

    if violations:
        result["rc"] = 1
        result["note"] = (
            f"{len(violations)} bash-3.2-unsafe construct(s) found in Skill-6 core scripts "
            "(would crash under real /bin/bash 3.2 on a stock Mac — ENV-MATRIX.md adaptation "
            "contract rule 3)"
        )
    elif result["rc"] == 0:
        result["note"] = (
            f"platform={result['platform']}; no banned bash-3.2-unsafe constructs found in "
            f"{len(scripts_to_scan)} core script(s)"
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--box", default=os.environ.get("OPENCLAW_BOX_LABEL") or _hostname())
    ap.add_argument("--repo-root", default=str(REPO_ROOT_DEFAULT))
    ap.add_argument("--browser-manager-sh", default=None)
    ap.add_argument("--browser-manager-py", default=None)
    ap.add_argument("--guard-sh", default=None)
    ap.add_argument("--reaper-sh", default=None)
    ap.add_argument("--cron-list-json", default=None, help="inline JSON override (test isolation)")
    ap.add_argument("--cron-list-file", default=None, help="path to a JSON file override (test isolation)")
    ap.add_argument("--ps-output-file", default=None, help="path to canned `ps` output (test isolation)")
    ap.add_argument("--ttl-seconds", type=int, default=1800)
    ap.add_argument("--ab-engine-dir", default=None)
    ap.add_argument("--playwright-dir", default=None)
    ap.add_argument("--home", default=None, help="override $HOME for profile-dir defaults (test isolation)")
    ap.add_argument("--platform", choices=["mac", "vps"], default=None,
                     help="override platform auto-detection (test isolation)")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root)
    browser_manager_sh = args.browser_manager_sh or str(repo_root / "06-ghl-install-pages" / "tools" / "browser_manager.sh")
    browser_manager_py = args.browser_manager_py or str(repo_root / "06-ghl-install-pages" / "tools" / "browser_manager.py")
    guard_sh = args.guard_sh or str(repo_root / "scripts" / "guard-agent-browser-managed.sh")
    reaper_sh = args.reaper_sh or str(repo_root / "scripts" / "agent-browser-reaper.sh")

    cron_list_json = json.loads(args.cron_list_json) if args.cron_list_json else None

    headless = check_headless_lock(browser_manager_sh)
    versions = check_version_floor(guard_sh, browser_manager_sh)
    reaper = check_reaper_cron(cron_list_json, args.cron_list_file)
    chromium = check_stale_chromium(
        ps_output_file=args.ps_output_file, ttl_seconds=args.ttl_seconds,
        ab_engine_dir=args.ab_engine_dir, playwright_dir=args.playwright_dir,
        home=args.home,
    )
    env_matrix = check_env_matrix(
        browser_manager_py, [browser_manager_sh, reaper_sh, guard_sh],
        platform_override=args.platform,
    )

    gating_checks = [headless, versions, reaper, chromium, env_matrix]
    rcs = [c["rc"] for c in gating_checks]
    overall_rc = 2 if 2 in rcs else max(rcs)
    overall_armed = overall_rc == 0

    verdict = {
        "box": args.box,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headless_lock": headless,
        "version_floor": versions,
        "reaper_cron": reaper,
        "stale_chromium": chromium,
        "env_matrix": env_matrix,
        "overall_armed": overall_armed,
        "overall_rc": overall_rc,
    }

    _emit(verdict, args.json)
    return overall_rc


def _emit(verdict, as_json):
    if as_json:
        print(json.dumps(verdict, indent=2))
        return
    box = verdict.get("box", "unknown")
    checked_at = verdict.get("checked_at", "")
    print(f"P3-04 agent-browser conformance probe — box: {box}  ({checked_at})")

    def _tag(rc):
        return "[OK]  " if rc == 0 else ("[FAIL]" if rc == 1 else "[ERROR]")

    for label, key in (
        ("headed flag locked false", "headless_lock"),
        ("guard/lock version floor", "version_floor"),
        ("reaper cron present", "reaper_cron"),
        ("zero stale Chromium procs", "stale_chromium"),
        ("Mac-vs-VPS env matrix", "env_matrix"),
    ):
        c = verdict[key]
        print(f"  {_tag(c['rc'])} {label}: {c['note']}")

    print(f"  VERDICT: {'ARMED' if verdict['overall_armed'] else ('DEGRADED' if verdict['overall_rc'] == 1 else 'UNRESOLVABLE')}")


if __name__ == "__main__":
    sys.exit(main())
