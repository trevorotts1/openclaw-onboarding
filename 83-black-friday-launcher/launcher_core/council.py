"""Council advice in launch planning (Skill 77).

The planning step invokes Skill 77 through its documented offline entry point
(`scripts/doctor.mjs`, which performs no network and no writes) and records the
result in the launch record and the package receipt.

Rules this module enforces:

- Council advice is INCLUDED in launch planning: the step always runs and is
  always recorded.
- A not-ready result is recorded and the build CONTINUES. The record carries
  ``blocks_build: false`` as a literal, so no caller can turn advice into a gate.
- Advice is never permission: ``is_permission`` is likewise a literal false.
- No live paid session is required. A caller may inject a runner (tests use a
  stub); the default runner only asks the installed package whether it is ready
  and reports the truth.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .constants import COUNCIL_ENTRY_POINT, COUNCIL_SKILL_DIR

STEP = "council_launch_planning"
ADVICE_PENDING = "pending_live_session"
ADVICE_RETURNED = "returned"

Runner = Callable[[Dict[str, Any]], Dict[str, Any]]


def skill_root() -> Path:
    """The Skill 77 tree, resolved from the repository that contains this skill."""
    return Path(__file__).resolve().parent.parent.parent / COUNCIL_SKILL_DIR


def entry_point() -> Path:
    return skill_root() / COUNCIL_ENTRY_POINT


def run_skill77(launch: Dict[str, Any], timeout_s: int = 120) -> Dict[str, Any]:
    """Ask the installed Skill 77 package whether it is ready. Offline only.

    No session is started, no model is called, nothing is written. A missing
    tree, a missing runtime or a non-zero doctor exit is reported as not-ready,
    never guessed into a verdict.
    """
    root = skill_root()
    entry = entry_point()
    if not entry.is_file():
        return {"status": "not_ready", "ready": False,
                "detail": f"{COUNCIL_SKILL_DIR}/{COUNCIL_ENTRY_POINT} is not installed",
                "advice": None, "advice_state": ADVICE_PENDING}
    node = shutil.which("node")
    if not node:
        return {"status": "not_ready", "ready": False,
                "detail": "no node runtime on PATH; the Skill 77 entry point cannot run",
                "advice": None, "advice_state": ADVICE_PENDING}
    try:
        proc = subprocess.run(
            [node, str(entry), "--root", str(root)],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "not_ready", "ready": False,
                "detail": f"Skill 77 entry point failed to run: {exc}",
                "advice": None, "advice_state": ADVICE_PENDING}
    ok = proc.returncode == 0
    lines = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().splitlines()
    detail = lines[-1] if lines else ""
    return {
        "status": "ready_no_advice" if ok else "not_ready",
        "ready": ok,
        "exit_code": proc.returncode,
        "detail": detail,
        "advice": None,
        "advice_state": ADVICE_PENDING,
    }


def planning_step(launch: Dict[str, Any],
                  runner: Optional[Runner] = None) -> Dict[str, Any]:
    """Run the Council planning step and return the record that travels with the build.

    Never raises: every failure is a recorded not-ready result. Never blocks.
    """
    runner = runner or run_skill77
    try:
        result = runner(launch)
    except Exception as exc:  # a runner failure is a recorded fact, not a crash
        result = {"status": "not_ready", "ready": False,
                  "detail": f"council runner error: {exc}",
                  "advice": None, "advice_state": ADVICE_PENDING}
    if not isinstance(result, dict):
        result = {"status": "not_ready", "ready": False,
                  "detail": f"council runner returned {type(result).__name__}",
                  "advice": None, "advice_state": ADVICE_PENDING}
    status = result.get("status")
    if status not in ("ready_no_advice", "advice_returned", "not_ready"):
        status = "not_ready"
    advice_state = result.get("advice_state")
    if advice_state not in (ADVICE_PENDING, ADVICE_RETURNED):
        advice_state = ADVICE_RETURNED if result.get("advice") else ADVICE_PENDING
    return {
        "step": STEP,
        "skill": COUNCIL_SKILL_DIR,
        "entry_point": COUNCIL_ENTRY_POINT,
        "status": status,
        "ready": bool(result.get("ready")),
        "advice": result.get("advice"),
        "advice_state": advice_state,
        "detail": result.get("detail", ""),
        "blocks_build": False,
        "is_permission": False,
    }
