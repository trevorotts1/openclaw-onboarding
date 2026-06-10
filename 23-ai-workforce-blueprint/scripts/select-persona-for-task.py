#!/usr/bin/env python3
"""
select-persona-for-task.py — DEPRECATION SHIM

This file is a thin shim.  The canonical persona selector is now
persona-selector-v2.py in this same directory.

Per PRD item 1.1 (Wave 1, 2026-06-09):
  - persona-selector-v2.py is declared the ONE canonical selector.
  - select-persona-for-task.py is archived; its body has been replaced
    by this shim that delegates all calls to v2 and prints a deprecation
    warning to stderr.

WHY: AGENTS.md rule N16, the Command Center (src/lib/persona-selector.ts),
and persona-matching-protocol.md all reference v2.  Maintaining v1 as a
separate live implementation meant that QC scripts and INSTALL.md were
verifying a dead code path.  The two things v1 had that v2 lacked —
semantic candidate retrieval via gemini-search.py and the DEPT_DOMAIN_TAGS
keyword filter — have been ported into v2.select_persona().

USAGE: All existing callers continue to work unchanged.  Arguments are
forwarded verbatim to persona-selector-v2.py.  The only visible change
is the deprecation notice on stderr.

REMOVAL: This shim will be removed in a future release.  Update your
callers now:
  old: .../scripts/select-persona-for-task.py --dept X --task Y
  new: .../scripts/persona-selector-v2.py --department X --task Y
       (note: --dept becomes --department in v2)

The original v1 implementation is preserved in archive/ for reference.
"""
import os
import sys
from pathlib import Path


def main() -> int:
    print(
        "[select-persona-for-task v1] DEPRECATED: this entry point is a shim. "
        "Use persona-selector-v2.py directly.  "
        "See 23-ai-workforce-blueprint/scripts/archive/README.md for migration notes.",
        file=sys.stderr,
    )

    v2 = Path(__file__).parent / "persona-selector-v2.py"
    if not v2.exists():
        print(
            f"[select-persona-for-task shim] ERROR: persona-selector-v2.py not found at {v2}. "
            f"Re-run update-skills.sh --only 23 to restore it.",
            file=sys.stderr,
        )
        return 1

    # Translate legacy argument name: v1 used --dept, v2 uses --department.
    # Forward all other args unchanged.
    args = sys.argv[1:]
    translated: list = []
    i = 0
    while i < len(args):
        if args[i] == "--dept":
            translated.append("--department")
            i += 1
        elif args[i].startswith("--dept="):
            translated.append("--department=" + args[i].split("=", 1)[1])
            i += 1
        else:
            translated.append(args[i])
            i += 1

    # exec replaces the current process — exit code passes through.
    os.execv(sys.executable, [sys.executable, str(v2)] + translated)
    return 0  # unreachable; execv never returns on success


if __name__ == "__main__":
    sys.exit(main())
