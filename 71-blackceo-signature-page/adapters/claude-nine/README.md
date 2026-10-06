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
