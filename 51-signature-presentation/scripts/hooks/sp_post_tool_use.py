#!/usr/bin/env python3
"""PostToolUse handler (PRES-051): record observed operations, reconcile local state.

Records observed CLI operation IDs/status and reconciles local state. A
successful shell exit never becomes a fabricated uploaded/complete receipt.
Host notifications stay separate from authoritative verification. Always
exits 0; never blocks, never approves.
"""

from __future__ import annotations

import hashlib
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

RELEVANT_TOOLS = {"Bash", "Write", "Edit"}


def main() -> int:
    event, err = read_stdin_event()
    if err is not None or event is None:
        eprint(f"[sp-hooks] PostToolUse unreadable input ({err}); nothing recorded.")
        return 0
    bad = validate_event(event, "PostToolUse")
    if bad is not None:
        eprint(f"[sp-hooks] PostToolUse schema invalid ({bad}); nothing recorded.")
        return 0

    if event.get("tool_name") not in RELEVANT_TOOLS:
        return 0
    bound, _ = resolve_context(event)
    if bound is None:
        return 0  # unrelated session: pass silently

    run_dir = Path(bound["run_dir"])
    response = event.get("tool_response")
    resp_digest = hashlib.sha256(
        json.dumps(response, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    scripts = engine_scripts_dir()
    entry = engine_entry(scripts) if scripts is not None else None
    state, _ = read_engine_status(entry, run_dir) if entry else (None, "")
    record = {
        "at": utcnow(),
        "session": event.get("session_id"),
        "company": bound["company_id"],
        "presentation": bound["presentation_id"],
        "tool": event.get("tool_name"),
        "tool_use_id": event.get("tool_use_id"),
        "response_digest": resp_digest,
        "engine_terminal": (state or {}).get("terminal") if state else "unknown",
        "note": "observed shell/tool outcome only; never an uploaded/complete receipt",
    }
    log_local(run_dir, "sp-post-tool-use.jsonl", record)
    eprint(
        f"[sp-hooks v{HOOK_VERSION}] PostToolUse recorded "
        f"(tool_use={event.get('tool_use_id')} digest={resp_digest} "
        f"engine_terminal={record['engine_terminal']}). "
        "Authoritative verification stays with the engine."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
