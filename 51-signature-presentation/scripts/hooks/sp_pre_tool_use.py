#!/usr/bin/env python3
"""PreToolUse handler (PRES-051): delegate selected presentation mutations.

Only relevant supported entry tools. Parses structured tool input; no regex
over arbitrary Bash pretends to enforce every possible bypass. Unknown or
malformed relevant requests cannot be certified. Unrelated tools/sessions
pass without being trapped. The CLI/state transitions enforce the gate.

This hook NEVER blocks by itself: it exits 0 always and only surfaces the
engine's own verdict as context. Async/hook output cannot approve a
transition; blocking stays in engine transactions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_hook_common import (  # noqa: E402
    HOOK_VERSION,
    eprint,
    engine_entry,
    engine_scripts_dir,
    log_local,
    read_engine_status,
    read_stdin_event,
    resolve_context,
    utcnow,
    validate_event,
)

# Relevant: mutations that could attempt a presentation state transition.
# Everything else passes untouched.
RELEVANT_PREFIXES = (
    "presentation_job.py --close",
    "presentation_job.py --resume",
    "presentation_job.py --run",
    "presentation-canonical-entry.sh",
)
RELEVANT_TOOLS = {"Bash"}


def _tool_text(tool_name: str, tool_input: object) -> str:
    if not isinstance(tool_input, dict):
        return ""
    parts = []
    for key in ("command", "cmd", "script", "file_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str):
            parts.append(val)
    return "\n".join(parts)


def main() -> int:
    event, err = read_stdin_event()
    if err is not None or event is None:
        eprint(f"[sp-hooks] PreToolUse unreadable input ({err}); passing (no certification).")
        return 0
    bad = validate_event(event, "PreToolUse")
    if bad is not None:
        eprint(f"[sp-hooks] PreToolUse schema invalid ({bad}); passing (cannot certify).")
        return 0

    tool_name = event.get("tool_name", "")
    text = _tool_text(tool_name, event.get("tool_input"))
    if tool_name not in RELEVANT_TOOLS or not any(p in text for p in RELEVANT_PREFIXES):
        return 0  # unrelated tool: pass without being trapped

    bound, why = resolve_context(event)
    if bound is None:
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] PreToolUse: relevant mutation seen but {why} "
            "Cannot certify — run it through the canonical door from the bound run dir; "
            "the engine gate decides."
        )
        return 0

    scripts = engine_scripts_dir()
    entry = engine_entry(scripts) if scripts is not None else None
    run_dir = Path(bound["run_dir"])
    state, serr = read_engine_status(entry, run_dir) if entry else (None, "NO_ENGINE")
    log_local(
        run_dir,
        "sp-pre-tool-use.jsonl",
        {
            "at": utcnow(),
            "session": event.get("session_id"),
            "company": bound["company_id"],
            "presentation": bound["presentation_id"],
            "tool": tool_name,
            "status_ok": state is not None,
        },
    )
    if state is None:
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] PreToolUse: {bound['company_id']}/"
            f"{bound['presentation_id']} engine status unavailable ({serr}). "
            "Not certified; the engine transaction enforces the gate."
        )
        return 0
    terminal = state.get("terminal") or "in progress"
    eprint(
        f"[sp-hooks v{HOOK_VERSION}] PreToolUse: delegated to engine validator — "
        f"{bound['company_id']}/{bound['presentation_id']}/{state.get('job_id')} "
        f"terminal={terminal}. This hook does not approve the transition; "
        "the engine transaction decides."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
