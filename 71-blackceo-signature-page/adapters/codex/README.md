# Codex Adapter

Evaluate the packaged skill against the current Codex runtime without redesigning the BlackCEO methodology.

1. Verify the current Codex skill-discovery mechanism in the local install.
2. If the normal local skills root is `~/.agents/skills` or `~/.codex/skills`, use the safe installer (it links into both):

```bash
python3 scripts/install_local.py --runtime codex --dry-run
python3 scripts/install_local.py --runtime codex
```

On Windows, run the same commands with `py scripts/install_local.py --runtime codex` (add `--dry-run` first).

3. Confirm that the runtime discovers the skill and can load references/assets/scripts.
4. Run `python3 tests/test_scripts.py` (the bundled PDF test needs Pillow: `python3 -m pip install --user Pillow` on macOS, `py -m pip install Pillow` on Windows).
5. Record any compatibility-only changes in the evaluation report.

Do not overwrite an existing target. Do not add credentials to the skill folder.

## Swarm spawn contract

Status: **no spawn contract is claimed for Codex yet.** The runner (`scripts/swarm_runner.py`) refuses a runtime whose adapter lacks this section's five parts, and this adapter currently documents only four of them; until the session-id capture below is verified against a live Codex install, runs that need a swarm must use another runtime or the sequential fallback. This is the honest state of the adapter, recorded rather than papered over.

- **Spawn mechanism.** One Codex exec session per item, with the rendered brief file as the task input: `codex exec --full-auto "$(cat <brief-file>)"`, one process per item, each confined to the run folder.
- **Session-id capture.** NOT YET VERIFIED. The contract requires the worker's session id to be printed as `SESSION: <id>` and recorded per item, because review stamping keys on it. The Codex exec surface must be checked on a live install for a stable session identifier the worker can print; until that check is done and recorded here, treat this adapter as having no spawn contract.
- **Exit-status observation.** The runner observes the exec process exit code directly: 0 finished, 2 transport failure, 3 validation or content failure, other nonzero treated as validation lane, timeout kill is the timeout lane.
- **Credential boundary.** A Codex worker inherits the client's own environment on the client's own box. The adapter never injects another client's keys or the operator's personal credentials.
- **swarm_mode declaration.** A future verified contract declares `swarm_mode: swarm` in `private/runner-state.json` for parallel runs.
- **Sequential fallback.** Available today: the runner declares the fallback in `private/runner-fallback.json` in the format `references/runtime-adapters.md` specifies, runs items one at a time through the same briefs and gate commands, and declares `swarm_mode: sequential-fallback`. Reviews performed by the same session that authored an item are stamped SELF-REVIEWED.
