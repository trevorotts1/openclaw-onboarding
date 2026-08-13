#!/usr/bin/env python3
"""capacity.py -- 9Router capacity probe for the Presentations department.

WORK-ITEM-12 of MASTER-SPEC-2026-08-09 (Presentations Department anti-drift fix).

Root cause this prevents (SESSION-LOG Item 6): the 2026-08-09 run used ~35 of
320 available agents (11% utilization) because capacity_plan.json self-imposed
max_concurrent_agents: 8 with probe_mode: "SIMULATED". The orchestrator guessed
instead of measuring. Law 14: "A number you did not measure is a rumour."
Law 38: "Nobody's capacity is assumed."

CAPACITY DOCTRINE (EXECUTION-PLAN.md Section A, MAXIMUM-PARALLELISM DOCTRINE,
operator directive 2026-08-10 -- SUPERSEDES the prior 20x16=320 / 25% reserve
numbers from the original spec-protocol text):

    provider_ceiling   = 2500   (DeepSeek v4 Flash -- up to 2,500 agents in parallel)
    workflows          = 30     (operator directive: up to 30 workflows at one time)
    subagents_per_wf   = 16     (operator directive: 16 sub-agents per workflow)
    dispatchable       = min(provider_ceiling, 30 * 16) = min(2500, 480) = 480
    reserve            = 0      (operator directive: "without any gating" --
                                 NO reserve, NO artificial cap, NO self-limiting)
    effective          = 480    (full width, always)

The probe is NEVER simulated. It is a read-only measurement of
~/.claude-nine/settings.json (fallback ~/.claude/settings.json) and the local
process table. It costs nothing to run and works in both live and simulated
contexts. A simulated probe produces fake numbers; this module cannot emit one.

Exit codes: 0 success, 2 settings.json missing/unreadable, 3 internal error.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# --- Doctrine constants (EXECUTION-PLAN.md Section A, binding) ---------------

PROVIDER_CEILING = 2500        # DeepSeek v4 Flash parallel ceiling
PROVIDER_NAME = "DeepSeek v4 Flash (via 9Router)"
WORKFLOWS = 30                 # operator directive 2026-08-10
SUBAGENTS_PER_WORKFLOW = 16    # operator directive 2026-08-10
RESERVE = 0                    # operator directive: "without any gating" -- NO reserve
PROBE_MODE = "live"            # NEVER "SIMULATED"

SETTINGS_CANDIDATES = [
    Path.home() / ".claude-nine" / "settings.json",
    Path.home() / ".claude" / "settings.json",
]

# Process-table signature for working-concurrency measurement.
# argv[0] basename starting with "claude" catches live Claude Code sessions and
# their spawned subagents (each is a separate process); "openclaw" catches the
# gateway. The pattern is deliberately reported alongside the count so the
# number is auditable, never taken on faith.
PROCESS_PATTERN = re.compile(r"^(claude|openclaw)")


def read_settings() -> dict:
    """Read the harness settings.json. Returns the measured values.

    Exits 2 on missing/unreadable file or missing subagent ceiling -- never
    returns fake numbers (Law 14). Secret material (API key helpers, tokens)
    is never read into the result and never printed."""
    for path in SETTINGS_CANDIDATES:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"capacity: settings unreadable at {path}: {exc}", file=sys.stderr)
            sys.exit(2)
        env = raw.get("env") or {}

        def _int(key: str):
            try:
                return int(env.get(key))
            except (TypeError, ValueError):
                return None

        max_subagents = _int("CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION")
        if max_subagents is None:
            print(
                "capacity: CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION absent or "
                f"non-integer in {path} -- refusing to guess (Law 14)",
                file=sys.stderr,
            )
            sys.exit(2)
        return {
            "settings_path": str(path),
            "max_subagents": max_subagents,
            "max_context_tokens": _int("CLAUDE_CODE_MAX_CONTEXT_TOKENS"),
            "max_output_tokens": _int("CLAUDE_CODE_MAX_OUTPUT_TOKENS"),
            "model": raw.get("model"),
            "subagent_model": env.get("CLAUDE_CODE_SUBAGENT_MODEL"),
            "base_url": env.get("ANTHROPIC_BASE_URL"),
        }
    print(
        "capacity: no settings.json found at: "
        + ", ".join(str(p) for p in SETTINGS_CANDIDATES),
        file=sys.stderr,
    )
    sys.exit(2)


def compute_dispatchable(max_subagents: int) -> int:
    """dispatchable = min(harness ceiling, provider ceiling, 30 workflows x 16).

    MAXIMUM-PARALLELISM DOCTRINE (operator directive 2026-08-10): 30 workflows
    x 16 subagents = 480, bounded by the DeepSeek v4 Flash ceiling of 2500.
    The harness-declared ceiling (settings.json) is also a bound -- with the
    measured 1000 it does not bind (480 < 1000)."""
    return min(max_subagents, PROVIDER_CEILING, WORKFLOWS * SUBAGENTS_PER_WORKFLOW)


def compute_reserve(dispatchable: int) -> int:
    """Reserve is 0. The prior spec-protocol Law 44 reserve
    (max(25% of dispatchable, 2)) is SUPERSEDED by the operator directive
    2026-08-10: 'without any gating' -- NO reserve, NO artificial cap."""
    return RESERVE


def compute_available(dispatchable: int, reserve: int) -> int:
    """available = dispatchable - reserve. With reserve 0: full width."""
    return dispatchable - reserve


def measure_working_concurrent() -> tuple:
    """Count live harness/subagent processes on the local box.

    Uses psutil when importable; otherwise `ps -A -o pid=,command=` parsing.
    Returns (count, method, ok). On failure returns (0, reason, False) and the
    caller labels the number UNMEASURED -- never a fabricated value."""
    self_pid = os.getpid()
    try:
        import psutil  # optional dependency

        count = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == self_pid:
                    continue
                if PROCESS_PATTERN.match(proc.info["name"] or ""):
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return count, "psutil process_iter, pattern " + PROCESS_PATTERN.pattern, True
    except ImportError:
        pass
    try:
        out = subprocess.run(
            ["ps", "-A", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode != 0:
            return 0, f"ps exited {out.returncode}", False
        count = 0
        for line in out.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            pid_str, command = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            if pid == self_pid:
                continue
            argv0 = command.split(None, 1)[0]
            basename = os.path.basename(argv0)
            if basename.startswith("python") and "capacity.py" in command:
                continue  # this probe's own interpreter
            if PROCESS_PATTERN.match(basename):
                count += 1
        return count, "ps -A scan, argv[0] pattern " + PROCESS_PATTERN.pattern, True
    except Exception as exc:  # noqa: BLE001 -- measurement must never raise
        return 0, f"measurement failed: {exc}", False


def probe() -> dict:
    """The main entry point. Read-only measurement; never mutates anything.

    Returns the full measured budget. probe_mode is always "live" -- a
    simulated probe is structurally impossible here."""
    settings = read_settings()
    dispatchable = compute_dispatchable(settings["max_subagents"])
    reserve = compute_reserve(dispatchable)
    available = compute_available(dispatchable, reserve)
    working, method, ok = measure_working_concurrent()
    result = {
        "probe_mode": PROBE_MODE,
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "settings_path": settings["settings_path"],
        "max_subagents": settings["max_subagents"],
        "max_context_tokens": settings["max_context_tokens"],
        "max_output_tokens": settings["max_output_tokens"],
        "model": settings["model"],
        "subagent_model": settings["subagent_model"],
        "base_url": settings["base_url"],
        "provider": PROVIDER_NAME,
        "provider_ceiling": PROVIDER_CEILING,
        "workflows": WORKFLOWS,
        "subagents_per_workflow": SUBAGENTS_PER_WORKFLOW,
        "doctrine_width": WORKFLOWS * SUBAGENTS_PER_WORKFLOW,
        "dispatchable": dispatchable,
        "reserve": reserve,
        "available": available,
        "working_concurrent": working if ok else "UNMEASURED",
        "working_concurrent_method": method,
    }
    return result


def format_report(result: dict) -> str:
    """Human-readable report + machine-greppable JSON block.

    The JSON block guarantees the acceptance greps succeed:
      grep '"probe_mode"'  -> "probe_mode": "live"
      grep '"dispatchable"' -> "dispatchable": 480"""
    lines = [
        "CAPACITY PROBE -- Presentations department (WORK-ITEM-12)",
        f"Probe mode: {result['probe_mode']} (never SIMULATED)",
        f"Settings measured from: {result['settings_path']}",
        (
            f"Harness: {result['max_subagents']} subagents permitted "
            f"(context {result['max_context_tokens']}, "
            f"output {result['max_output_tokens']}, "
            f"model {result['model']}, subagent model {result['subagent_model']})"
        ),
        (
            f"Provider: {result['provider']} -- ceiling "
            f"{result['provider_ceiling']} parallel"
        ),
        (
            f"Doctrine width: {result['workflows']} workflows x "
            f"{result['subagents_per_workflow']} subagents = "
            f"{result['doctrine_width']}"
        ),
        (
            f"Dispatchable: min({result['max_subagents']}, "
            f"{result['provider_ceiling']}, {result['doctrine_width']}) = "
            f"{result['dispatchable']}"
        ),
        f"Reserve: {result['reserve']} (operator directive: no gating)",
        f"Effective available: {result['available']} (full width, always)",
        (
            f"Working concurrent now: {result['working_concurrent']} "
            f"({result['working_concurrent_method']})"
        ),
        "",
        "=== JSON ===",
        json.dumps(result, indent=2),
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="9Router capacity probe -- measures, never guesses."
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        required=True,
        help="Run the live capacity probe and print the measured numbers.",
    )
    parser.parse_args()
    try:
        result = probe()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"capacity: internal error: {exc}", file=sys.stderr)
        return 3
    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
