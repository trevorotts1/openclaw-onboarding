#!/usr/bin/env python3
"""Stop/SubagentStop handler (PRES-051): bounded corrective feedback.

For an active scoped presentation, inspects engine status. If the agent
claims completion without evidence, emits bounded corrective feedback.
Checks stop_hook_active plus a persisted reentry budget (REENTRY_BUDGET).
Never forces an endless loop, never ignores cancellation, never retries a
missing credential. Persists resumable blocked state + next action when work
cannot proceed. Durable scheduling and the final completion auditor own
eventual work/recovery; the hook never guarantees the host stays alive.

Exit codes: 0 always (feedback as stderr/context). Exit 2 is intentionally
never used here: blocking a Stop is the loop shape the budget exists to
prevent; the engine transaction remains the only gate.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp_hook_common import (  # noqa: E402
    HOOK_VERSION,
    REENTRY_BUDGET,
    digest_file,
    engine_entry,
    engine_scripts_dir,
    eprint,
    load_budget,
    log_local,
    read_engine_status,
    read_stdin_event,
    resolve_context,
    save_budget,
    supervisor_coverage_note,
    utcnow,
)

COMPLETION_WORDS = ("complete", "completed", "done", "finished", "shipped", "delivered")


def _claims_completion(event: dict) -> bool:
    text = str(event.get("last_assistant_message", "") or "").lower()
    return any(w in text for w in COMPLETION_WORDS)


def main() -> int:
    event, err = read_stdin_event()
    if err is not None or event is None:
        eprint(f"[sp-hooks] Stop unreadable input ({err}); allowing stop.")
        return 0
    if event.get("hook_event_name") not in ("Stop", "SubagentStop"):
        eprint("[sp-hooks] Stop: wrong event; allowing stop.")
        return 0

    # Loop protection first: stop_hook_active means our own prior feedback is
    # already in the transcript — never stack another.
    if event.get("stop_hook_active") is True:
        eprint("[sp-hooks] Stop: stop_hook_active=true; allowing stop (no stacked feedback).")
        return 0

    bound, why = resolve_context(event)
    if bound is None:
        eprint(f"[sp-hooks] Stop: {why} Allowing stop.")
        return 0

    run_dir = Path(bound["run_dir"])
    budget = load_budget(run_dir)
    hook_digest = digest_file(Path(__file__).resolve())
    scripts = engine_scripts_dir()
    entry = engine_entry(scripts) if scripts is not None else None
    state, serr = read_engine_status(entry, run_dir) if entry else (None, "NO_ENGINE")

    # Reentry guard: same engine revision already answered within budget.
    state_hash = ""
    if state is not None:
        state_hash = hashlib.sha256(
            json.dumps(
                {
                    "terminal": state.get("terminal"),
                    "phases": [(p.get("id"), p.get("status")) for p in state.get("phases", [])],
                    "gates": {k: v.get("state") for k, v in (state.get("gates") or {}).items()},
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
    used = int(budget.get("used", 0) or 0)
    if state is not None and budget.get("last_hash") == state_hash and used >= 1:
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] Stop: identical engine state already "
            f"answered (hash={state_hash}); allowing stop (reentry guard)."
        )
        return 0
    if used >= REENTRY_BUDGET:
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] Stop: reentry budget spent "
            f"({used}/{REENTRY_BUDGET}); allowing stop. "
            + supervisor_coverage_note(run_dir)
        )
        return 0

    if state is None:
        save_budget(
            run_dir,
            {"used": used + 1, "last_hash": "", "updated_at": utcnow(),
             "reason": serr, "hook_digest": hook_digest},
        )
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] Stop: engine status unavailable ({serr}); "
            "persisted resumable blocked state: re-run the canonical door from "
            f"{run_dir} when ready. Allowing stop. " + supervisor_coverage_note(run_dir)
        )
        return 0

    terminal = state.get("terminal") or "in progress"
    gates = state.get("gates") or {}
    failed = sorted(k for k, g in gates.items() if g.get("state") == "fail")
    claimed = _claims_completion(event)
    evidence_ok = terminal == "DONE" and not failed

    log_local(
        run_dir,
        "sp-stop.jsonl",
        {
            "at": utcnow(),
            "session": event.get("session_id"),
            "company": bound["company_id"],
            "presentation": bound["presentation_id"],
            "terminal": terminal,
            "failed_gates": failed,
            "claimed_completion": claimed,
            "budget_used": used + 1,
            "hook_digest": hook_digest,
        },
    )
    if claimed and not evidence_ok:
        save_budget(
            run_dir,
            {"used": used + 1, "last_hash": state_hash, "updated_at": utcnow(),
             "reason": "completion-claimed-without-evidence", "hook_digest": hook_digest},
        )
        eprint(
            f"[sp-hooks v{HOOK_VERSION}] Stop: completion claimed but engine says "
            f"terminal={terminal} failed_gates={failed or 'none-yet'}. "
            f"Next action: python3 presentation_job.py --resume --run-dir {run_dir} "
            f"(budget {used + 1}/{REENTRY_BUDGET}). The engine transaction decides; "
            "this feedback approves nothing. Allowing stop after this note. "
            + supervisor_coverage_note(run_dir)
        )
        return 0

    eprint(
        f"[sp-hooks v{HOOK_VERSION}] Stop: terminal={terminal} "
        f"claimed_completion={claimed}; no corrective feedback owed. Allowing stop. "
        + supervisor_coverage_note(run_dir)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
