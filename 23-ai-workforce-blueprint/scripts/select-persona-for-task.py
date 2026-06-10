#!/usr/bin/env python3
"""
select-persona-for-task.py — DEPRECATED SHIM (PRD item 1.1, v11.4.0)

This script is a thin compatibility shim. It translates v1 arguments and
delegates ALL work to persona-selector-v2.py, which is the canonical selector.

A deprecation warning is always printed to stderr so stale callers are
visible in operator logs and QC traces.

MIGRATION: replace calls to this script with:
    python3 persona-selector-v2.py --department <dept> --task "<task>" --format json

This shim will be removed one release after fleet-wide migration to v2.
See 23-ai-workforce-blueprint/scripts/archive/README.md for full details.
"""
import os
import subprocess
import sys
from pathlib import Path

# ─── DEPRECATION NOTICE ───────────────────────────────────────────────────────
print(
    "[select-persona-for-task] DEPRECATED: this entry point is a shim that "
    "delegates to persona-selector-v2.py. Update your callers to call "
    "persona-selector-v2.py directly (use --department instead of --dept). "
    "See archive/README.md. This shim will be removed in the next release.",
    file=sys.stderr,
)

# ─── LOCATE v2 ────────────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
V2_SCRIPT = _THIS_DIR / "persona-selector-v2.py"

if not V2_SCRIPT.exists():
    print(
        f"[select-persona-for-task] FATAL: persona-selector-v2.py not found at "
        f"{V2_SCRIPT}. Cannot delegate. Reinstall Skill 23.",
        file=sys.stderr,
    )
    sys.exit(1)

# ─── ARGUMENT TRANSLATION ─────────────────────────────────────────────────────
# v1 uses --dept; v2 uses --department. Translate transparently.
# All other args (--task, --format, --company-slug, --mode-switch, etc.) are
# passed through unchanged except --company-slug (v2 does not have it — omit
# with a warning since v2 uses path resolver for company discovery).
args_in = sys.argv[1:]
args_out = []
i = 0
while i < len(args_in):
    arg = args_in[i]
    if arg == "--dept":
        args_out.append("--department")
        i += 1
        if i < len(args_in):
            args_out.append(args_in[i])
            i += 1
    elif arg.startswith("--dept="):
        args_out.append("--department=" + arg[len("--dept="):])
        i += 1
    elif arg == "--company-slug":
        # v2 resolves the company via get_openclaw_paths(); skip this arg
        print(
            "[select-persona-for-task] NOTE: --company-slug is not supported "
            "in v2; v2 uses get_openclaw_paths() for company discovery.",
            file=sys.stderr,
        )
        i += 2  # skip flag and its value
    elif arg.startswith("--company-slug="):
        print(
            "[select-persona-for-task] NOTE: --company-slug is not supported "
            "in v2; v2 uses get_openclaw_paths() for company discovery.",
            file=sys.stderr,
        )
        i += 1
    elif arg == "--top-k-semantic" or arg == "--top-k-final":
        # v2 does not expose these; skip with a note
        print(
            f"[select-persona-for-task] NOTE: {arg} is not supported in v2 "
            "(funnel top-k is internal). Skipping.",
            file=sys.stderr,
        )
        i += 2
    elif arg.startswith("--top-k-"):
        i += 1  # skip
    else:
        args_out.append(arg)
        i += 1

# ─── DELEGATE TO v2 ───────────────────────────────────────────────────────────
result = subprocess.run(
    [sys.executable, str(V2_SCRIPT)] + args_out,
)
sys.exit(result.returncode)
