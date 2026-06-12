# TIER 3 HELD PROPOSALS

This file captures proposals that require operator GO before implementation.
Per the three-tier authority system, any change to command-center architecture is TIER 3: propose and hold.

---

## PROPOSAL T3-001: Bugs Department Kanban Lane Mapping

**Proposed by:** bugs sub-agent (build-bugs-healer-departments branch)
**Date:** 2026-06-12
**Category:** Command Center Architecture (TIER 3)

### What this proposes

The Bugs Department SOPs (B-9.3) define a bug lifecycle with 7 stages:
REPORTED -> TRIAGED -> HEALING -> VERIFYING -> HEALED -> REGRESSION WATCH -> CLOSED

The ZHC command center's Kanban board uses a FIXED status set:
backlog / assigned / in_progress / review / done / blocked

These are task-lifecycle statuses, not bug-lifecycle statuses. Adding new lane columns to the board is a command-center architecture change.

### Recommended mapping (Fable-aligned, from SYSTEM-INTEGRATION-STRATEGY.md C1)

Use the EXISTING status set for bug tickets as a dedicated bugs workspace. Mapping:
- REPORTED = backlog
- TRIAGED = assigned
- HEALING = in_progress
- VERIFYING = review
- HEALED = done
- REGRESSION WATCH: maintained in the ticket ledger + a scheduled Bug Librarian sweep (no custom lane needed)
- CLOSED: ticket ledger final state; card may be archived
- blocked: used for SLA breach flags on any card

A dedicated bugs workspace (separate from department workspaces) provides visual isolation without requiring new lanes.

### What needs operator GO

1. Approval to create a dedicated "bugs" workspace in the command center.
2. Confirmation of the lane mapping above OR an alternative the operator prefers.
3. Approval to add the scheduled REGRESSION WATCH sweep (Bug Librarian cron).

### Risk if not actioned

The Bugs Department operates fully on its ticket ledger (working/bugs/intake_ledger.json and working/bugs/triage_ledger.json) without any command center integration. All SOPs function correctly using the ledger as the source of truth. The Kanban integration is a visibility enhancement, not a functional prerequisite.

**Status: BUILT -- operator GO 2026-06-12. See PR t3-healer-every-department (T3-002) and blackceo-command-center PR (T3-001).**

---

## PROPOSAL T3-002: Embedded department Healer propagation (the QUAD, ~+20 agents per box)

**Proposed by:** wire (architect sub-agent, build-bugs-healer-departments branch)
**Date:** 2026-06-12
**Category:** New specialists across every department + per-box scale/cost (TIER 3)

### What this proposes

The build order PART 8 step 6 and SYSTEM-INTEGRATION-STRATEGY.md C3 call for ONE department Healer embedded in EVERY department, instantiated from the PART 5 template (templates/role-library/healer/dept-healer-template.md).

I implemented the generator change (the trio becomes a QUAD) in scripts/generate-trio-roles.py behind an opt-in flag, and TESTED it dry-run, but I did NOT run it to materialize the Healer files into the department folders or register them in _index.json. Doing so is the operator-gated scale decision the docs flag.

### What was built (SAFE, file-level, already done)

- scripts/generate-trio-roles.py now has make_healer_content(), needs_healer_file(), healer_role_slug/filename(), and a --with-healer flag (DEFAULT OFF). Default runs stay trio-only and touch no Healer files. With --with-healer it instantiates the PART 5 template per department, filling {{DEPARTMENT_NAME}}, role_type healer (NEVER qc), and registers each in _index.json. Verified: dry-run lists the per-dept Healer files, writes nothing; default mode produces zero Healer output.

### What needs operator GO (the propagation, HELD)

1. Decision: embed one standing Healer in every department (~+20 standing agents per box, 20 depts x 1, against the N14 caps and persona/orchestration load) vs the leaner alternative Fable names: ONE Healer department whose Chief Healer dispatches per-department healing sub-agents on demand (sub-specialist model, Section 19).
2. If GO on standing Healers: run `python3 scripts/generate-trio-roles.py --with-healer` (writes healer-<dept>.md into every dept + registers in _index.json), then per-box converge + embedding_health verify.
3. The standing Healer Department roster roles named in PART 3.2 that have NO role files yet (Global Model Registrar, SOP Library Custodian, Deep Research Specialist -- Healing): author the 19-section files before they can be registered/materialized. Currently only chief-healer.md exists; healer-suggested-roles.md lists only chief-healer so materialization never points at a missing file.

### Risk if not actioned

Bugs + Healer ship as registered departments (bugs: 3 specialists; healer: Chief Healer) and every future client materializes them. Per-department embedded Healers simply do not exist until the operator decides the scale model. No functional break; the immune system runs at the Chief Healer / Bugs Department level until per-dept Healers are turned on.

**Status: BUILT -- operator GO 2026-06-12. generate-trio-roles.py default flipped to QUAD (--no-healer opt-out); 18 healer-<dept>.md files materialized; _index.json updated (total_roles 285 -> 303); heartbeat OFF (agentsOnly=[main]); role_type healer, never qc.**

---

## NOTE N-001: Bug lifecycle mapped onto EXISTING Kanban statuses (no new lanes implemented)

**By:** wire (architect)
**Category:** Command Center mapping note (the SAFE choice; new lanes remain TIER 3 under T3-001)

Per PART 7.1 and SYSTEM-INTEGRATION-STRATEGY.md C1, the CC Kanban status set is FIXED (backlog / assigned / in_progress / review / done / blocked) and is task-lifecycle state, not configurable data. Adding bug-lifecycle lane columns is a CC architecture change = TIER 3 (held under T3-001).

The SAFE wiring (no CC change) is to MAP the bug lifecycle onto the existing statuses:
- REPORTED = backlog
- TRIAGED = assigned
- HEALING = in_progress
- VERIFYING = review
- HEALED = done
- REGRESSION WATCH = ticket ledger + scheduled Bug Librarian sweep (no lane)
- CLOSED = ticket ledger final state (card archived)
- blocked = SLA-breach flag on any card

The Bug Ticket JSON ledger remains the source of truth; the card is the view. No CC DB schema, model-manifest, or master-SOP edits were made by this pass. The dedicated "bugs" workspace and any new lanes stay HELD under T3-001.

---
