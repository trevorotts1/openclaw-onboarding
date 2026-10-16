# Claude Code Adapter

Evaluate the packaged skill against the current Claude Code runtime without redesigning the BlackCEO methodology.

1. Verify the current Claude Code skill-discovery mechanism in the local install.
2. If the normal local skills root is `~/.claude/skills`, use the safe installer:

```bash
python3 scripts/install_local.py --runtime claude-code --dry-run
python3 scripts/install_local.py --runtime claude-code
```

On Windows, run the same commands with `py scripts/install_local.py --runtime claude-code` (add `--dry-run` first).

3. Confirm that the runtime discovers the skill and can load references/assets/scripts.
4. Run `python3 tests/test_scripts.py` (the bundled PDF test needs Pillow: `python3 -m pip install --user Pillow` on macOS, `py -m pip install Pillow` on Windows).
5. Record any compatibility-only changes in the evaluation report.

Do not overwrite an existing target. Do not add credentials to the skill folder.

## Swarm spawn contract

How `scripts/swarm_runner.py` spawns one worker per item under Claude Code (the general contract lives in `references/runtime-adapters.md`, "Swarm spawn contract"):

- **Spawn mechanism.** One Claude Code subagent per item, spawned with the rendered brief file as its task input. The runner's template (runtime name `claude-code`, overridable per host): `claude --print --session-id swarm-<stage>-<item> "$(cat <brief-file>)"`. Each subagent gets its own session and works only its item's expected outputs.
- **Session-id capture.** The session id is the one the runner assigns at spawn (`swarm-<stage>-<item>`) and the subagent prints it back as `SESSION: <id>` on stdout; the runner records the printed value per item. Review stamping uses the reviewing subagent's captured session id.
- **Exit-status observation.** The runner observes the subagent process exit code directly: 0 finished, 2 transport failure, 3 validation or content failure, other nonzero treated as validation lane, timeout kill is the timeout lane.
- **Credential boundary.** Subagents inherit the environment of the Claude Code process the runner launched, which is the client's own environment on the client's own box. The adapter never injects another client's keys or the operator's personal credentials into a subagent.
- **swarm_mode declaration.** Runs under this adapter declare `swarm_mode: swarm` in `private/runner-state.json` when subagents actually spawned in parallel.
- **Sequential fallback.** Where isolated subagent spawning is unavailable (a harness build without subagent support, or the operator's choice), the runner declares the fallback in `private/runner-fallback.json` in the format `references/runtime-adapters.md` specifies, runs items one at a time through the same briefs and gate commands, and declares `swarm_mode: sequential-fallback`. Reviews performed by the same session that authored an item are stamped SELF-REVIEWED; the fallback never presents them as independent.
