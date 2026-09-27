# TYP Self-Heal Migration Procedure

## Current compact installations

`CORE_REFERENCE_POLICY_V1` identifies the compact storage contract. The guarded legacy `scripts/typ-migrate.sh` detects this marker and skips its old migration/appending behavior. A successful skip means the legacy routine did not run; it is not proof of a full audit. Use the core validator and inspect pointers, character counts and authoritative references instead.

Do not run an older unguarded script to repair a compact installation. It can recreate multi-line summaries, duplicate folders and memory receipts. Do not remove the marker to bypass the guard.

## Legacy workspaces

Older clients may contain large manuals in bootstrap or deep documents in misplaced folders. Inspect the actual installed script before use. The legacy dry run is:

```bash
bash scripts/typ-migrate.sh --dry-run --verbose /path/to/workspace
```

Its historical line-based heuristics (>400 lines/file and >25 nonblank lines/section) are only candidate detection, not the current acceptance rule. Compact acceptance uses whole-file character budgets: AGENTS.md 15,000; MEMORY.md 8,000; TOOLS.md 15,000. Long single-line files can exceed a budget despite passing line heuristics.

Legacy automatic apply is not the approved compact migration mechanism. Its historical behavior included extracting large sections, appending collision content and injecting notices/rules. Review proposed changes first and reconcile them according to the process below. Do not treat notice text as a request to expand a new core summary.

## Safe migration

1. Identify the active workspace, authoritative master root, current writer scripts and watcher baseline. Capture hashes and verified recovery copies. Preserve dirty source changes.
2. Inventory topic sections and incoming references. Distinguish exact duplicates from differing versions and sole-original documents.
3. Reuse the canonical master root. Mac default: `~/Downloads/openclaw-master-files/`; documented Docker VPS: `/data/.openclaw/master-files/`. Confirm persistence. Use apis/, skills/, processes/, references/, and playbooks/ for books/SOPs/playbooks.
4. Preserve useful full procedures externally. Merge differing versions deliberately; never concatenate duplicate material on each rerun. Keep retired versions in recovery/history outside active bootstrap.
5. Replace each necessary topic block with one short trigger plus exact absolute reference path, or a link from an existing reference index. A stable version-free ID owns the pointer. An existing sufficient pointer requires no new block.
6. Keep durable owner facts and essential global rules in their appropriate core file. Remove learning/install receipts, temporary handoffs, duplicate versions and malformed promotion leftovers from permanent context.
7. Stage and validate complete core files: character budgets, existing paths, balanced markers/fences and preserved owner facts. Reconcile concurrent edits using expected hashes and the shared writer lock. Use the approved watcher migration mechanism for a deliberate large reduction.
8. Verify live files equal the approved baseline and remain unchanged across a watcher cycle. Run deduplication in dry-run mode. Repeat validation; an identical rerun must create no duplicate entry or backup.
9. Record the migration outside core with changed locations, recovery details, verification and any held proposals. Keep 14-day snapshot retention based on creation metadata, not old source mtimes.

## Subagent inheritance

The active AGENTS.md contains the essential compact policy and task-triggered pointer. Agents follow that policy and retrieve the relevant reference before acting. Do not copy a full storage doctrine into several core files merely for inheritance. Validate actual runtime file injection when debugging an agent's behavior rather than assuming every agent receives the same files.

## After an interrupted migration

Read the task manifest and staged proposal, verify current hashes and existing targets, then resume only missing steps. Replace legacy MIGRATION NOTICE placeholders with the short trigger/pointer after checking the extracted content. Never paste the full extracted content back into core. Report held or pending changes honestly.
