#!/usr/bin/env python3
"""SessionStart handler (PRES-051): bounded local-only readiness.

Reads stdin event JSON, resolves the selected session's explicit runtime
context, returns version/readiness and a pending-run summary. Missing context
yields a setup instruction, never a default operator identity. Never installs
dependencies, launches paid work, restarts a gateway, or merges code merely
because Claude starts. Reattachment to an already authorized job validates
lease/current revision before claiming any worker.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_hook_common import (  # noqa: E402
    HOOK_VERSION,
    REENTRY_BUDGET,
    digest_file,
    emit_additional_context,
    engine_entry,
    engine_scripts_dir,
    eprint,
    log_local,
    read_engine_status,
    read_lease_holder,
    read_stdin_event,
    resolve_context,
    utcnow,
    validate_event,
)


def main() -> int:
    event, err = read_stdin_event()
    if err is not None or event is None:
        msg = (
            f"[sp-hooks] SessionStart unreadable input ({err}); "
            "no readiness claimed. Bind with PRESENTATION_COMPANY_ID + "
            "PRESENTATION_ID + PRESENTATION_RUN_DIR."
        )
        emit_additional_context(msg)
        eprint(msg)
        return 0
    bad = validate_event(event, "SessionStart")
    if bad is not None:
        msg = f"[sp-hooks] SessionStart schema invalid ({bad}); no readiness claimed."
        emit_additional_context(msg)
        eprint(msg)
        return 0

    bound, why = resolve_context(event)
    scripts = engine_scripts_dir()
    entry = engine_entry(scripts) if scripts is not None else None
    hook_digest = digest_file(Path(__file__).resolve())
    host = event.get("cwd", "?")
    session = event.get("session_id", "?")

    if bound is None:
        msg = (
            f"[sp-hooks v{HOOK_VERSION}] SessionStart: {why} "
            f"(engine={'found' if entry else 'NOT FOUND'}; host cwd={host}). "
            "No paid work started, no worker claimed."
        )
        emit_additional_context(msg)
        eprint(msg)
        return 0

    run_dir = Path(bound["run_dir"])
    state, serr = read_engine_status(entry, run_dir) if entry else (None, "NO_ENGINE")
    lease = read_lease_holder(run_dir)
    log_local(
        run_dir,
        "sp-session-start.jsonl",
        {
            "at": utcnow(),
            "session": session,
            "company": bound["company_id"],
            "presentation": bound["presentation_id"],
            "hook_digest": hook_digest,
            "status_ok": state is not None,
        },
    )
    if state is None:
        msg = (
            f"[sp-hooks v{HOOK_VERSION}] SessionStart: bound "
            f"{bound['company_id']}/{bound['presentation_id']} but {serr}; "
            f"lease: {lease}. Stopped before claiming anything. "
            f"{resolve_context.__doc__.splitlines()[0] if False else ''}"
            "Re-run the canonical door from the bound run dir to reattach."
        )
        emit_additional_context(msg)
        eprint(msg)
        return 0

    terminal = state.get("terminal") or "in progress"
    phases = state.get("phases") or []
    done = sum(1 for p in phases if p.get("status") == "done")
    msg = (
        f"[sp-hooks v{HOOK_VERSION}] SessionStart READY: "
        f"{bound['company_id']}/{bound['presentation_id']}/{state.get('job_id')} "
        f"terminal={terminal} phases={done}/{len(phases)} lease=[{lease}] "
        f"(source={bound['source']}). Reattachment validates lease + revision "
        f"{str(state.get('manifest_sha256'))[:12]} before any worker is claimed; "
        f"Stop budget {REENTRY_BUDGET} armed. Enforcement stays in engine transactions."
    )
    emit_additional_context(msg)
    eprint(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
