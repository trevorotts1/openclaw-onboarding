# SPEC — Persistent department-agent spawn (platform-level)

**Status:** SPECIFICATION (platform/gateway behavior — NOT implemented by the onboarding scripts)
**Owner:** OpenClaw gateway / platform team
**Added:** 2026-06-21 (v13.2.2 routing-gate hardening)
**Related:** `23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md` R11

---

## Problem

When the Master Orchestrator routes a task by **directly spawning** a department
specialist (the R6/R7 "spawn a sub-agent with instructions" path), the gateway
today spawns that specialist as an **ephemeral child of the current turn**:

- `spawn_mode: "run"` — the child runs inside the owner-message turn.
- `controller: agent:main:main` — the child is owned by the orchestrator's main
  session, and its lifecycle is bound to that turn.

The consequence: when a **new owner message** arrives, a new turn starts and the
previous turn's children are torn down. A specialist that was mid-task dies with
its deliverable half-written. This is the same class of failure as the
CEO-self-execution bug — work that does not survive the conversation.

The repo already builds one **persistent** agent per department
(`agents.list[].id = "dept-<slug>"`, own `workspace` / `agentDir` / `model`,
`is_master = 0` in `mission-control.db`). The **task-board** path
(`POST /api/tasks/ingest` → `agent:<dept>` session) already survives turns,
because a board task outlives any single turn and the persistent agent picks it
up. The gap is ONLY the **direct-spawn** path.

---

## What is repo-side (already done in v13.2.2)

1. **Persistent per-department agents exist.** `build-workforce.py`
   `add_agent_to_config()` writes a `dept-<slug>` agent with its own session,
   workspace, agentDir, model, and a schema-valid `subagents` block
   (`{ allowAgents, model }`). These are NOT turn-scoped — they are standing
   agents bound to their department workspace.
2. **Doctrine mandates routing to them.** SOP-00 **R11** requires production work
   to be dispatched via the task board to the persistent `agent:<dept>` session,
   and explicitly forbids running production work as a turn-scoped inline child.
   This makes the survival mechanism the *default and only sanctioned* path.

The onboarding scripts CANNOT set the spawn mode / controller directly: the
strict `AgentEntrySchema.subagents` accepts only `{ allowAgents, model }`. Any
other key (e.g. a hypothetical `spawnMode` / `controller` / `detached`) is
rejected at `config validate`, so writing it would brick the box. That is why
the items below are specified for the platform rather than implemented here.

---

## What is platform-side (this spec — for the gateway team)

For the **direct-spawn** path (orchestrator spawns a department specialist with
instructions), the gateway SHOULD support spawning the specialist as an
**INDEPENDENT, PERSISTENT** agent whose lifetime is **decoupled from the
controlling turn**:

1. **Independent session.** The spawned specialist runs in its OWN session
   (`agent:<dept>`), bound to its OWN department workspace — NOT as a child of
   `agent:main:main`. The orchestrator hands off; it does not own the worker.
2. **Detached spawn.** The spawn mode for a production dispatch SHOULD be a
   detached/background spawn (analogous to "fire and forget" / `run_in_background`)
   so the worker continues after the orchestrator's turn ends.
3. **Cleanup decoupled from the turn.** Teardown of the spawned specialist MUST
   be driven by the WORK's completion (task done / failed / handed back), NOT by
   the controlling turn ending. A new owner message MUST NOT tear down an
   in-flight department worker.
4. **Re-attach / status, not re-spawn.** A subsequent orchestrator turn that needs
   the worker's status SHOULD query the persistent session (or the task board),
   not spawn a fresh duplicate child.

### Suggested config surface (gateway team to design + validate)

If/when the gateway adds first-class support, the natural home is an extension of
the per-agent `subagents` block, e.g.:

```jsonc
// PROPOSED — NOT YET VALID; the gateway team owns the schema + validation.
"subagents": {
  "allowAgents": ["*"],
  "model": { "fallbacks": ["..."] },
  "spawnMode": "detached",        // run | detached  (default today: run)
  "lifecycle": "work-scoped"      // turn-scoped | work-scoped
}
```

Until that schema ships and `config validate` accepts it, the onboarding repo
MUST NOT write these keys (it would fail validation). The repo-side guarantee
(persistent dept agents + R11 task-board routing) is the interim mechanism that
keeps production work alive across turns.

---

## Acceptance (when the platform implements this)

- Orchestrator dispatches a long task, then the owner sends a second message →
  the dispatched specialist is STILL running and completes its work.
- The specialist's session id is `agent:<dept>` (its persistent session), not a
  turn-scoped child of `agent:main:main`.
- Killing/ending the orchestrator turn does NOT abort the in-flight worker.
