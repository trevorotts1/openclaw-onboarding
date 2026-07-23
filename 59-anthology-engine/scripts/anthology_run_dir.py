#!/usr/bin/env python3
"""anthology_run_dir.py -- the single durable per-participant run directory resolver.

U059: every anthology authoring stage (Skill 59 stage dispatchers AND the Skill 54
run_anthology.py orchestrator) resolves the participant's working directory through
this ONE function, so later stages read back exactly what earlier stages wrote.

The canonical layout is:

    59-anthology-engine/state/runs/participants/<safe-participant-id>/
        working/          <- gate artifacts every stage checks
        working/checkpoints/
        delivery/

"participants" is a fixed literal, never a stage name, so this can never collide
with the anthology-level assembly dir at state/runs/s9/<anthology_id> that
gate_engine.py::_s9_run_dir resolves.

Stdlib only (pathlib). No network, no model, no provider.
"""
from pathlib import Path

# The skill-59 root (this file lives in 59-anthology-engine/scripts/).
_SKILL_59_ROOT = Path(__file__).resolve().parent.parent


def resolve_participant_run_dir(participant_id, base=None):
    """Resolve (and create) the single durable per-participant run directory
    shared by EVERY anthology authoring stage.

    Args:
        participant_id: the participant key (any string; unsafe chars become '_').
        base: optional override for the skill-59 root (tests / verify runs).
              Defaults to this file's grandparent (59-anthology-engine/).

    Returns:
        Path to <base>/state/runs/participants/<safe-id>/ with working/ ensured.

    No stage may invent its own path string for the gate artifacts the next
    stage reads; all must call this resolver.
    """
    if base is None:
        base = _SKILL_59_ROOT
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (participant_id or "unknown"))
    # ONE canonical directory per participant, shared by EVERY authoring stage.
    # It used to be stage-scoped (state/runs/<STAGE>/<safe>), which meant S2 handed
    # 54-anthology-writer/run_anthology.py an EMPTY directory: the orchestrator walks
    # its phases from P0-INTAKE every time and fails closed at the first phase whose
    # gate artifacts are absent, and those artifacts (working/intake.json,
    # working/avatar.md) were written by S1 into a DIFFERENT directory. Every stage
    # now resolves the same path, so later stages read back what earlier ones wrote.
    d = Path(base) / "state" / "runs" / "participants" / safe
    (d / "working").mkdir(parents=True, exist_ok=True)
    return d
