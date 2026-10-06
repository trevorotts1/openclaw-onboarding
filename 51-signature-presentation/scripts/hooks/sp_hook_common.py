#!/usr/bin/env python3
"""Shared stdin / schema / context plumbing for Skill 51 host hooks (PRES-051).

Every handler in this directory is local, bounded, and read-only toward the
engine: prerequisite, lease, persona, artifact/QC and completion enforcement
stays in engine transactions (presentation_job Gates / Engine.close). Hooks
delegate to the engine doctor/status validator and surface state; a direct CLI
or disabled hooks cannot waive gates. Async hook output never approves a
transition.

Hard rules enforced here:
  * stdin JSON only, size-capped, read with a deadline; malformed input is an
    actionable local error, never a gate decision.
  * explicit company/presentation/run binding only — env
    (PRESENTATION_COMPANY_ID / PRESENTATION_ID / PRESENTATION_RUN_DIR) or an
    explicit session file (.presentation-session.json schema
    sp-session-context-v1). No cwd guessing, no default operator identity.
  * install-relative paths only (skill dir derived from __file__; engine dir
    resolved materialized-dept first, template sibling second, $SCRIPTS_DIR
    third). No hardcoded home paths.
  * never invoke a Claude host binary (no recursive session invocation).
  * never start paid/deploy work: hooks only run read-only engine commands
    (--status, --resume --diagnose-only). --run / --resume(execute) / --close /
    --new are refused by construction (see run_engine_readonly).
  * never print a secret value; logs carry names and digests only.
"""

from __future__ import annotations

import hashlib
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HOOK_VERSION = "1.2.0"
SCHEMA_VERSION = "sp-hook-v1"
SESSION_CONTEXT_SCHEMA = "sp-session-context-v1"

MAX_STDIN_BYTES = 256 * 1024
STDIN_TIMEOUT_S = 5.0
ENGINE_TIMEOUT_S = 10.0
MAX_CONTEXT_CHARS = 2000
REENTRY_BUDGET = 3

READONLY_ENGINE_ARGS = {
    "--status",
    "--resume",  # only paired with --diagnose-only (diagnosis prints, executes nothing)
    "--diagnose-only",
    "--json",
    "--repin",  # NOT read-only; listed here so the guard names it explicitly
    "--run",
    "--close",
    "--new",
}
# The only engine invocations a hook may ever run.
ALLOWED_ENGINE_ARGV = (
    ("--status",),
    ("--status", "--json"),
    ("--resume", "--diagnose-only"),
)


def eprint(*parts: Any) -> None:
    print(*parts, file=sys.stderr, flush=True)


def skill_dir() -> Path:
    """Install-relative skill root: scripts/hooks/sp_hook_common.py -> skill root."""
    return Path(__file__).resolve().parent.parent.parent


def scoped_log_dir(run_dir: Optional[Path] = None) -> Path:
    """Verbose logs go to scoped files, never to machine stdout."""
    if run_dir is not None:
        d = Path(run_dir) / "working" / "logs"
    else:
        d = skill_dir() / "scripts" / "hooks" / ".local-logs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def log_local(run_dir: Optional[Path], name: str, row: Dict[str, Any]) -> None:
    try:
        with open(scoped_log_dir(run_dir) / name, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        pass


def read_stdin_event() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read one JSON event from stdin with size cap and deadline.

    Returns (event, error). error is a short machine-safe code, never input content.
    """
    try:
        ready, _, _ = select.select([sys.stdin], [], [], STDIN_TIMEOUT_S)
    except (OSError, ValueError) as exc:
        return None, f"STDIN_UNREADABLE:{type(exc).__name__}"
    if not ready:
        return None, "STDIN_TIMEOUT"
    try:
        raw = sys.stdin.read(MAX_STDIN_BYTES + 1)
    except OSError as exc:
        return None, f"STDIN_UNREADABLE:{type(exc).__name__}"
    if raw is None:
        return None, "STDIN_EMPTY"
    if len(raw) > MAX_STDIN_BYTES:
        return None, "STDIN_TOO_LARGE"
    if not raw.strip():
        return None, "STDIN_EMPTY"
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None, "STDIN_MALFORMED_JSON"
    if not isinstance(event, dict):
        return None, "STDIN_NOT_AN_OBJECT"
    return event, None


REQUIRED_BY_EVENT = {
    "SessionStart": ("session_id", "hook_event_name", "cwd"),
    "PreToolUse": ("session_id", "hook_event_name", "tool_name", "tool_input"),
    "PostToolUse": (
        "session_id",
        "hook_event_name",
        "tool_name",
        "tool_input",
        "tool_response",
    ),
    "Stop": ("session_id", "hook_event_name"),
    "SubagentStop": ("session_id", "hook_event_name"),
}


def validate_event(event: Dict[str, Any], want: str) -> Optional[str]:
    """Fail-closed schema check. Returns None when valid, else a short reason."""
    if event.get("hook_event_name") != want:
        return f"WRONG_EVENT:{event.get('hook_event_name')!r}"
    missing = [k for k in REQUIRED_BY_EVENT[want] if k not in event]
    if missing:
        return "MISSING_FIELDS:" + ",".join(sorted(missing))
    if not isinstance(event.get("session_id"), str) or not event["session_id"]:
        return "BAD_SESSION_ID"
    return None


def _valid_session_file(obj: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    if obj.get("schema") != SESSION_CONTEXT_SCHEMA:
        return None
    if not obj.get("company_id") or not obj.get("presentation_id"):
        return None
    run_dir = obj.get("run_dir")
    if not run_dir or not Path(str(run_dir)).is_dir():
        return None
    return {
        "company_id": str(obj["company_id"]),
        "presentation_id": str(obj["presentation_id"]),
        "run_dir": str(Path(str(run_dir)).resolve()),
        "source": "session-file",
    }


def resolve_context(event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """Bind this host session to an explicit company/presentation/run.

    Order: explicit env triple first, then $PRESENTATION_SESSION_FILE, then
    <cwd>/.presentation-session.json. Anything else is UNBOUND with a setup
    instruction — never a guessed run dir, never a default identity.
    """
    env_run = os.environ.get("PRESENTATION_RUN_DIR", "").strip()
    env_company = os.environ.get("PRESENTATION_COMPANY_ID", "").strip()
    env_pres = os.environ.get("PRESENTATION_ID", "").strip()
    if env_run or env_company or env_pres:
        if env_run and env_company and env_pres and Path(env_run).is_dir():
            return (
                {
                    "company_id": env_company,
                    "presentation_id": env_pres,
                    "run_dir": str(Path(env_run).resolve()),
                    "source": "env",
                },
                "",
            )
        return None, (
            "UNBOUND: partial PRESENTATION_* env (need PRESENTATION_COMPANY_ID + "
            "PRESENTATION_ID + PRESENTATION_RUN_DIR pointing at an existing run dir)."
        )
    candidates: List[Path] = []
    explicit = os.environ.get("PRESENTATION_SESSION_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    cwd = event.get("cwd") or os.getcwd()
    try:
        candidates.append(Path(str(cwd)) / ".presentation-session.json")
    except OSError:
        pass
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            bound = _valid_session_file(json.loads(cand.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if bound is not None:
            bound["source"] = f"session-file:{cand}"
            return bound, ""
    return None, (
        "UNBOUND: no explicit company/presentation/run binding for this session. "
        "To bind: export PRESENTATION_COMPANY_ID + PRESENTATION_ID + "
        "PRESENTATION_RUN_DIR, or place a .presentation-session.json "
        f"(schema {SESSION_CONTEXT_SCHEMA}) in the session cwd. "
        "Nothing is assumed from the cwd."
    )


def engine_scripts_dir() -> Optional[Path]:
    """Resolve the Presentations engine scripts dir, install-relative first."""
    explicit = os.environ.get("SCRIPTS_DIR", "").strip()
    if explicit and Path(explicit).is_dir():
        return Path(explicit).resolve()
    ws = os.environ.get(
        "OPENCLAW_WORKSPACE",
        os.path.join(os.path.expanduser("~"), ".openclaw", "workspace"),
    )
    materialized = Path(ws) / "departments" / "Presentations" / "scripts"
    if (materialized / "presentation_job.py").is_file():
        return materialized.resolve()
    sibling = (
        skill_dir().parent
        / "23-ai-workforce-blueprint"
        / "templates"
        / "role-library"
        / "presentations"
        / "scripts"
    )
    if (sibling / "presentation_job.py").is_file():
        return sibling.resolve()
    return None


def engine_entry(scripts_dir: Path) -> Optional[Path]:
    cand = scripts_dir / "presentation_job.py"
    return cand if cand.is_file() else None


def run_engine_readonly(
    entry: Path, run_dir: Path, argv: Tuple[str, ...]
) -> Tuple[int, str, str]:
    """Run ONLY read-only engine commands. Anything else is refused locally."""
    if argv not in ALLOWED_ENGINE_ARGV:
        return 99, "", f"REFUSED: engine argv {list(argv)!r} is not read-only"
    cmd = [
        sys.executable or "python3",
        str(entry),
        *argv,
        "--run-dir",
        str(run_dir),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=ENGINE_TIMEOUT_S,
            env={k: v for k, v in os.environ.items()},
        )
        return proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:]
    except subprocess.TimeoutExpired:
        return 98, "", f"ENGINE_TIMEOUT after {ENGINE_TIMEOUT_S}s"
    except OSError as exc:
        return 97, "", f"ENGINE_SPAWN_FAILED:{type(exc).__name__}"


def read_engine_status(
    entry: Path, run_dir: Path
) -> Tuple[Optional[Dict[str, Any]], str]:
    rc, out, err = run_engine_readonly(entry, run_dir, ("--status", "--json"))
    if rc != 0:
        reason = (err.strip().splitlines() or [f"exit={rc}"])[-1][:200]
        return None, f"ENGINE_STATUS_FAILED:{reason}"
    try:
        state = json.loads(out)
    except json.JSONDecodeError:
        return None, "ENGINE_STATUS_UNPARSEABLE"
    if not isinstance(state, dict) or "job_id" not in state:
        return None, "ENGINE_STATUS_NOT_A_JOB"
    return state, ""


def read_lease_holder(run_dir: Path) -> str:
    doc = Path(run_dir) / "working" / ".lease.json"
    try:
        obj = json.loads(doc.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return "no lease record"
    if not isinstance(obj, dict):
        return "unreadable lease record"
    who = obj.get("who") or obj.get("holder") or "unknown holder"
    return f"pid={obj.get('pid')} host={obj.get('host')} who={who}"


def supervisor_coverage_note(run_dir: Path) -> str:
    roots = os.environ.get("PRESENTATION_SCAN_ROOTS", "").strip()
    if not roots:
        return (
            "durable supervisor: not configured to outlive this host "
            "(PRESENTATION_SCAN_ROOTS unset). If this host exits, status is "
            "suspended — no background work is claimed."
        )
    try:
        inside = any(
            str(Path(run_dir).resolve()).startswith(str(Path(r.strip()).resolve()))
            for r in roots.split(os.pathsep)
            if r.strip()
        )
    except OSError:
        inside = False
    if inside:
        return (
            "durable supervisor: this run sits under a configured scan root; "
            "eventual recovery is owned by presentation_job.py --supervise "
            "(bounded, backed-off), never by this hook."
        )
    return (
        "durable supervisor: configured scan roots do not cover this run; "
        "explicit cancellation wins and status stays suspended after host exit."
    )


def emit_additional_context(text: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text[:MAX_CONTEXT_CHARS],
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def digest_file(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def budgeted_state_path(run_dir: Path) -> Path:
    return Path(run_dir) / "working" / ".sp-stop-budget.json"


def load_budget(run_dir: Path) -> Dict[str, Any]:
    try:
        obj = json.loads(budgeted_state_path(run_dir).read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {"used": 0, "last_hash": "", "updated_at": ""}


def save_budget(run_dir: Path, budget: Dict[str, Any]) -> None:
    try:
        p = budgeted_state_path(run_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(budget, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
