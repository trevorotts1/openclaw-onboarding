"""Council advice in launch planning (Skill 77).

The planning step invokes Skill 77 through its documented offline entry point
(`scripts/doctor.mjs`, which performs no network and no writes) and records the
result in the launch record and the package receipt.

Rules this module enforces:

- The step always runs and is always recorded, and it is labelled for what it is.
  Without a live session it is a PACKAGE CHECK, not advice: the record carries
  ``council_session_held: false`` and a client summary that says no Council advice
  was obtained. Nothing here reads like a review that did not happen.
- By default a not-ready result is recorded and the build CONTINUES. The record
  carries ``blocks_build: false`` as a literal, so no caller can turn advice into a
  gate. A caller that wants real advice passes ``council_required=True`` and the
  step refuses (CouncilRequiredError) unless a session returned advice.
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

from .constants import (COUNCIL_ADVICE_SUMMARY, COUNCIL_ENTRY_POINT,
                        COUNCIL_NO_ADVICE_SUMMARY, COUNCIL_SKILL_SLUG, skill_path)

STEP = "council_launch_planning"
ADVICE_PENDING = "pending_live_session"
ADVICE_RETURNED = "returned"

Runner = Callable[[Dict[str, Any]], Dict[str, Any]]


class CouncilRequiredError(Exception):
    """council_required was set and no Council session returned advice."""

    code = "AF-LAUNCH-COUNCIL-REQUIRED"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")
        self.detail = detail


def skill_root() -> Path:
    """The Council tree, resolved by slug under either naming convention."""
    return skill_path(COUNCIL_SKILL_SLUG)


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
                "detail": f"{COUNCIL_SKILL_SLUG}/{COUNCIL_ENTRY_POINT} is not installed",
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
    detail = "package check only, no Council session: " + (lines[-1] if lines else "")
    return {
        "status": "ready_no_advice" if ok else "not_ready",
        "ready": ok,
        "exit_code": proc.returncode,
        "detail": detail,
        "advice": None,
        "advice_state": ADVICE_PENDING,
    }


def planning_step(launch: Dict[str, Any],
                  runner: Optional[Runner] = None,
                  council_required: bool = False) -> Dict[str, Any]:
    """Run the Council planning step and return the record that travels with the build.

    Every runner failure is a recorded not-ready result, and by default the step never
    blocks. With ``council_required=True`` it raises CouncilRequiredError when no
    Council session returned advice (a package check alone is not a session).
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
    session_held = status == "advice_returned" and advice_state == ADVICE_RETURNED \
        and bool(result.get("advice"))
    if council_required and not session_held:
        raise CouncilRequiredError(
            "council_required is set but no Council session returned advice "
            f"(status {status!r}); {COUNCIL_NO_ADVICE_SUMMARY}")
    return {
        "step": STEP,
        "skill": COUNCIL_SKILL_SLUG,
        "entry_point": COUNCIL_ENTRY_POINT,
        "status": status,
        "ready": bool(result.get("ready")),
        "advice": result.get("advice"),
        "advice_state": advice_state,
        "detail": result.get("detail", ""),
        "council_session_held": session_held,
        "client_summary": COUNCIL_ADVICE_SUMMARY if session_held else COUNCIL_NO_ADVICE_SUMMARY,
        "blocks_build": False,
        "is_permission": False,
    }
