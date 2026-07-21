#!/usr/bin/env python3
"""Repo-integrity check: every entry-point command documented in a skill's
SKILL.md must resolve to a file that actually ships in this repository.

Why this exists (T2-07). Three skills documented a runnable entry point at a
path that does not exist:

    23-ai-workforce-blueprint/SKILL.md   bash add-role.sh ...
    32-command-center-setup/SKILL.md     bash sync-extensions.sh --converge
    22-book-to-persona-...  /SKILL.md    bash add-persona-from-source.sh ...

All three scripts live under the skill's own scripts/ directory. An agent that
follows the documented line runs "bash: add-role.sh: No such file or directory"
and the role, the converge, or the persona never happens. For 32 the converge is
described in the same document as mandatory, so a newly added department is left
unmaterialised.

What is checked. Inside fenced code blocks in every `NN-*/SKILL.md`, any line
whose first word is bash/sh/python3/python and whose first argument is a
REPO-RELATIVE path ending in .sh or .py must resolve, either from the repository
root or from the documenting skill's own directory. Absolute paths (`/...`),
home paths (`~/...`), variable-bearing paths (`$VAR/...`) and placeholder paths
(anything containing < > * ? { }) are out of scope: those name a runtime
location on a box, not a file this repository is expected to contain.

Exit codes:
  0 -- every documented repo-relative entry point resolves
  1 -- at least one does not (each is printed with file:line and the path)
  2 -- usage error
"""

from __future__ import annotations

import argparse
import os
import re
import sys

FENCE_RE = re.compile(r"^\s*```")
SKILL_DIR_RE = re.compile(r"^\d\d-")
CMD_RE = re.compile(r"^\s*(?:bash|sh|python3|python)\s+(\S+)")

# A first argument we deliberately do not resolve: it names a runtime location
# on a box, a shell variable, or a documentation placeholder.
OUT_OF_SCOPE_PREFIXES = ("~", "/", "$", "-", "<", "{", '"', "'")
PLACEHOLDER_CHARS = set("<>*?{}$")


def documented_entrypoints(repo_root: str):
    """Yield (rel_md_path, lineno, skill_dir_abs, argument) for each in-scope
    documented entry point."""
    for name in sorted(os.listdir(repo_root)):
        skill_dir = os.path.join(repo_root, name)
        if not os.path.isdir(skill_dir) or not SKILL_DIR_RE.match(name):
            continue
        md_path = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(md_path):
            continue
        in_fence = False
        with open(md_path, encoding="utf-8", errors="replace") as handle:
            for lineno, line in enumerate(handle, 1):
                if FENCE_RE.match(line):
                    in_fence = not in_fence
                    continue
                if not in_fence:
                    continue
                match = CMD_RE.match(line)
                if not match:
                    continue
                arg = match.group(1).strip()
                if arg.startswith(OUT_OF_SCOPE_PREFIXES):
                    continue
                if not arg.endswith((".sh", ".py")):
                    continue
                if PLACEHOLDER_CHARS & set(arg):
                    continue
                yield f"{name}/SKILL.md", lineno, skill_dir, arg


def unresolved(repo_root: str):
    """Return the list of documented entry points that do not resolve."""
    misses = []
    for rel_md, lineno, skill_dir, arg in documented_entrypoints(repo_root):
        from_root = os.path.join(repo_root, arg)
        from_skill = os.path.join(skill_dir, arg)
        if os.path.exists(from_root) or os.path.exists(from_skill):
            continue
        misses.append((rel_md, lineno, arg))
    return misses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print(f"[entrypoints] ERROR: not a directory: {repo_root}", file=sys.stderr)
        return 2

    checked = list(documented_entrypoints(repo_root))
    misses = unresolved(repo_root)

    if misses:
        print(
            f"[entrypoints] FAIL: {len(misses)} of {len(checked)} documented "
            f"entry point(s) do not resolve in this repository:"
        )
        for rel_md, lineno, arg in misses:
            print(f"  UNRESOLVED  {rel_md}:{lineno}  ->  {arg}")
        print(
            "[entrypoints] Fix the document to name the shipped path "
            "(usually <skill>/scripts/<name>), or ship the script."
        )
        return 1

    if not args.quiet:
        print(f"[entrypoints] PASS: {len(checked)} documented entry point(s) all resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
