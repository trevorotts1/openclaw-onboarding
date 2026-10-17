# Runtime Adapters - Phase 1

The BlackCEO methodology is runtime-independent. Installation/discovery mechanics are runtime-specific.

## Canonical-core principle

Prefer one real complete skill folder and safe symlinks into local runtimes when the runtime supports them. Link the entire `blackceo-signature-page` folder, not only `SKILL.md`, because references, scripts, tests, adapters, and assets must travel together.

Do not create separately maintained methodology copies for Claude Code, Claude-Nine, and Codex unless a runtime requires it.

## Safe install helper

Use `python3 scripts/install_local.py --dry-run` before creating any link.

Known Phase-1 helper defaults in this package:

- Claude Code target root: `~/.claude/skills`
- Codex target roots: `~/.agents/skills` and `~/.codex/skills` (both linked when present)
- Claude-Nine: no hard-coded target. Supply its verified skills root with `--target-root`.

Runtime paths and discovery behavior can change. The receiving agent must verify its current environment before using a default and must not claim compatibility solely because a path exists.

The installer refuses to overwrite an existing nonmatching file/directory/symlink. A conflict must be inspected and reconciled intentionally.

## Claude Code adapter

See `adapters/claude-code/README.md`.

## Codex adapter

See `adapters/codex/README.md`.

## Claude-Nine adapter

See `adapters/claude-nine/README.md`. Claude-Nine's exact skill directory is intentionally not guessed; verify the active harness/install and then use the safe installer with the confirmed target root.

## External tools

This skill does not bundle secrets or connectors. Detect available tools at runtime.

Potential live dependencies include:

- Kie.ai or another image engine;
- Agnes when selected;
- GHL;
- browser/computer control;
- GitHub;
- Vercel or another hosting target.

If a tool is absent, keep the local artifacts complete and mark the live integration stage BLOCKED with the exact missing capability.

## Phase 2 boundary

Do not modify the user's OpenClaw GitHub distribution in Phase 1. The vetted core is adapted to the OpenClaw repository/install/update workflow only after Phase-1 evaluation and reconciliation.

## Swarm spawn contract (fix plan Item 23)

The swarm runner (`scripts/swarm_runner.py`, spec in `references/swarm-plan.md`) fans a run's items out to worker sessions. It may only use a runtime whose adapter documents a spawn contract in its README, with all five parts below. A runtime without a documented contract is refused by name; the runner never improvises a spawn path.

The contract, for every runtime:

1. **Brief in.** The runner renders a per-item brief from `references/swarm-briefs/` to a file and hands the worker exactly one item: objective, input paths, reads, expected output paths, the validators that will run, done criteria, and a per-item note file path.
2. **Spawn mechanism.** The adapter names the exact mechanism and command shape that starts one isolated worker session for one brief, and how concurrent workers stay isolated from each other.
3. **Session-id capture.** The mechanism returns or prints the worker's session id. The runner records it per item; review stamping (`scripts/write_review.py`) uses the reviewing worker's session id, so a review whose session id cannot be captured cannot be stamped and does not count.
4. **Exit-status observation.** The runner observes the worker's exit status itself: 0 means the attempt finished, 2 means transport failure, 3 means validation or content failure, any other nonzero is treated as a validation-lane failure, and a kill by timeout is the timeout lane. A worker's own claim of success is never a result; results are validator exit codes, output files on disk, and Skill 74 receipts.
5. **Artifacts plus observed-result receipt out.** The worker writes artifacts and its note file, and nothing else. Receipts, review files, and gate state are written by the runner and `scripts/stage_gate.py` from what they observe. Workers never write receipts, reviews, or state.

**Credential boundary.** A worker inherits only its own client's keys, from that client's own environment. No spawn mechanism may pass another client's credentials, the operator's personal keys, or a shared master key into a worker session. The runner holds no provider keys at all: it never calls KIE; Skill 74 transports generation, and the generation worker runs inside the client's own environment.

**The `swarm_mode` declaration.** Every run record (`private/runner-state.json`) declares `swarm_mode`: `swarm` when items ran as parallel worker sessions, `sequential-fallback` when they did not. A run that claims swarm mode while running sequentially is a false record; the declaration exists so a degraded run is honest about what it was.

**The honest fallback declaration.** When a runtime cannot spawn isolated workers, or the active runner profile lacks a capability an item needs, the runner writes `private/runner-fallback.json` and mirrors it into `runner-state.json` before running anything sequentially:

```json
{
  "declared": true,
  "runtime": "<runtime name>",
  "reason": "<why isolated spawning or the capability is unavailable>",
  "items": ["<node ids that will run sequentially>"],
  "capability": "<render | transport | null>",
  "at": "<ISO timestamp>",
  "mode": "sequential-fallback"
}
```

Items then run one at a time through the same briefs, validators, and gate commands. Reviews done in the same session as the authoring are labeled SELF-REVIEWED by the review stamp (Item 7); the fallback never launders a self-review into an independent one. A transport capability gap is the one case with no sequential substitute: a non-active transport mode cannot dispatch paid generation at any concurrency, so those items are blocked with that reason named, with the fallback still declared.

### Per-runtime contracts

- **OpenClaw native sessions** (`adapters/` has no separate folder; this is the home runtime): see the spawn contract summary below; per-shape notes follow it.
- **Claude Code subagents**: see `adapters/claude-code/README.md`, "Swarm spawn contract".
- **Claude-Nine**: see `adapters/claude-nine/README.md`, "Swarm spawn contract". Claude-Nine is the 999-setup harness shape: the same contract, with models routed through 9Router instead of hardcoded, per the 999 edition.
- **Codex**: see `adapters/codex/README.md`, "Swarm spawn contract".
- **Sequential single-agent**: no adapter folder; the contract is this section. One agent works the item DAG in dependency order at concurrency 1, with the same briefs and gate commands, and the run record declares `swarm_mode: sequential-fallback` from the start.

### OpenClaw native sessions: spawn contract summary

- Spawn mechanism: one OpenClaw session per item on the client's own gateway, started by the runner with the brief as the session's task input (runner template `openclaw` in `scripts/swarm_runner.py`, overridable per host).
- Session-id capture: the gateway's session id for the spawned session, printed by the spawn command as `SESSION: <id>` and recorded by the runner per item.
- Exit status: the session's completion status is observed by the runner from the gateway's run result (completed, failed, timed out), mapped onto the exit-code lanes in part 4 above.
- Credential boundary: the session runs inside the client's own OpenClaw, with that client's own keys. Nothing about another client, and nothing of the operator's personal environment, crosses into it.

### Per-shape notes (Amendment 1)

- **fleet-mac**: workers are sessions of the client's own Mac gateway. Nothing leaves the box except the Item 24 run-event feed. No container tooling is involved in the spawn path.
- **fleet-hostinger**: workers are sessions of the container's own gateway. `docker exec` is provisioning and debugging only, never the spawn path: a worker spawned by exec has no gateway session id, so its reviews cannot be stamped and its results cannot be recorded.
- **fleet-contabo**: a runner spawns sessions only inside its own client's OpenClaw. No Docker socket is ever mounted into a client container, so cross-container spawning is not merely forbidden but mechanically impossible. The one thing shared across a box's containers is the KIE account budget when containers share one KIE account, and that sharing is a state file path (see `references/runner-profiles.json`), not a spawn path.
