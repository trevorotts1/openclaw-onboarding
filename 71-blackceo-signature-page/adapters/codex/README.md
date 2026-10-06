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
