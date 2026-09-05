# General Task and CEO fallback execution

New work is ingested once. An absent or unmatched department uses this client's General
Task department, or the CEO when Command Center assigns the verified catch-all fallback.
A missing department is not a reason to ask the owner to choose one or hold the work.

The assigned agent executes the existing task and execution. The authenticated dispatcher
context must match the agent, execution, company and installation. A `[catch-all]` string
in user content grants nothing. The worker retains QC, kill-switch, credential, budget,
and completion-evidence obligations. Specialists keep their original assignments.

`shared-utils/ceo_execution_policy.py` supplies V3 instructions to both doctrine stampers
and Skill 23 builders. Its bounded V1/V2 upgrade preserves bytes outside managed blocks,
including owner-written SOUL introductions. Existing role templates are replaced only
when the exact legacy generated protocol matches. The router's historical empty skill
list is retired; nonempty owner skill restrictions and tool restrictions are preserved.
The prompt plugin is an ES module and injects the same role-aware policy.

`shared-utils/sync_ceo_runtime_bindings.py` is a separate scoped synchronizer, never a
seeder. Supply an existing database, OpenClaw config, explicit company ID and company
folder, or an explicit company slug with matching build-state. It only binds one existing
agent row in that company's active canonical CEO/General workspace to one registered runtime
with real workspace and agent directories. `main` requires a workspace under that
company's canonical CEO department tree. CEO rows must have `is_master=1`; ordinary
Lead/QC/Specialist rows and archived workspaces are excluded. It never guesses from a person's display name,
changes an existing binding, or creates a runtime. Ambiguity remains unproven; old schemas
defer until migration 133 exists. The updater invokes it after a verified CC app upgrade.
Custom DB paths can use the explicit `--db` CLI; no discovery broadens the scope.

Offline checks:

- `python3 tests/unit/test_ceo_execution_policy.py`
- `python3 tests/unit/test_ceo_runtime_bindings.py`
- `bash tests/probe/test-p207-general-task-catchall-probe.sh`

These changes do not activate or test a live client runtime.
