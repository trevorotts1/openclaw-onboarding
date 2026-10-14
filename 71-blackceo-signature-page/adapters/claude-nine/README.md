# Claude-Nine Adapter

Claude-Nine is part of the Phase-1 evaluation target, but this package intentionally does not guess its active skills path.

1. Inspect the actual Claude-Nine/Claude Code harness configuration in the user's environment.
2. If Claude-Nine shares the same Claude Code skill root, the existing canonical symlink may already expose the skill.
3. If it uses another skills root, pass that verified root explicitly:

```bash
python3 scripts/install_local.py --runtime claude-nine --target-root /verified/skills/root --dry-run
python3 scripts/install_local.py --runtime claude-nine --target-root /verified/skills/root
```

On Windows, run the same commands with `py scripts/install_local.py --runtime claude-nine --target-root /verified/skills/root` (add `--dry-run` first).

4. Confirm discovery and run `python3 tests/test_scripts.py` (the bundled PDF test needs Pillow: `python3 -m pip install --user Pillow` on macOS, `py -m pip install Pillow` on Windows).
5. Report exact path behavior and any compatibility-only changes.

Do not invent a Claude-Nine path. Do not create a second independently maintained BlackCEO methodology copy when a safe shared core is possible.

## Swarm spawn contract

How `scripts/swarm_runner.py` spawns one worker per item under Claude-Nine, the Claude Code harness shape used by the 999-setup edition (the general contract lives in `references/runtime-adapters.md`, "Swarm spawn contract"):

- **Spawn mechanism.** One subagent per item inside the Claude-Nine harness, spawned with the rendered brief file as its task input. The runner's template (runtime name `claude-nine`, overridable per host): `claude --print --session-id swarm-<stage>-<item> "$(cat <brief-file>)"`, executed by the harness's Claude Code binary. Models route through 9Router rather than hardcoded provider refs, as everywhere in the 999 edition; the routing is the harness's business and the brief never names a model.
- **Session-id capture.** The session id is the one the runner assigns at spawn (`swarm-<stage>-<item>`) and the subagent prints it back as `SESSION: <id>` on stdout; the runner records the printed value per item. Review stamping uses the reviewing subagent's captured session id. Cross-harness note: a session id is only meaningful inside the harness that minted it; a run executed from the 999 copy records Claude-Nine session ids, never borrowed OpenClaw ones.
- **Exit-status observation.** The runner observes the subagent process exit code directly: 0 finished, 2 transport failure, 3 validation or content failure, other nonzero treated as validation lane, timeout kill is the timeout lane.
- **Credential boundary.** Subagents inherit the client's own environment inside the client's own Claude-Nine install. A skill running from 999 resolves its routes inside the Claude Code harness (999's own native skills and vendored modules); it never reaches back into an OpenClaw tree for credentials or transport.
- **swarm_mode declaration.** Runs under this adapter declare `swarm_mode: swarm` in `private/runner-state.json` when subagents actually spawned in parallel.
- **Sequential fallback.** Where the harness cannot spawn isolated subagents, the runner declares the fallback in `private/runner-fallback.json` in the format `references/runtime-adapters.md` specifies, runs items one at a time through the same briefs and gate commands, and declares `swarm_mode: sequential-fallback`. Reviews performed by the same session that authored an item are stamped SELF-REVIEWED; the fallback never presents them as independent.
