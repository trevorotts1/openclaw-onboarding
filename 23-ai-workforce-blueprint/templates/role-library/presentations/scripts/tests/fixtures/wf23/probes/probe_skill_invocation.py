#!/usr/bin/env python3
"""WF23 prep: Claude Code / Claude Nine skill-invocation readiness probe TEMPLATE.

W6 acceptance requires each host to invoke the INSTALLED skill from the
user-facing surface (HOST-ACCEPTANCE.md: no direct-script shortcut counts).
This prep probe checks the static half of that contract hermetically:

  --skill claude-code|claude-nine --skills-dir DIR --entry PATH

READY (exit 0) only when BOTH hold:
  1. <skills-dir>/<skill>/SKILL.md exists and is non-empty;
  2. the canonical entry script exists and is executable
     (presentation-canonical-entry.sh — the single governed dispatch).

Anything else is NOT-READY (exit 2). The live half — actually invoking the
surface on the host — runs in W6, not here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

LEGAL_SKILLS = ("claude-code", "claude-nine")


def probe(skill: str, skills_dir: Path, entry: Path) -> dict:
    if skill not in LEGAL_SKILLS:
        return {"status": "NOT-READY", "skill": skill,
                "reason": f"unknown skill {skill!r}; want one of {LEGAL_SKILLS}"}
    md = skills_dir / skill / "SKILL.md"
    if not md.is_file():
        return {"status": "NOT-READY", "skill": skill,
                "reason": f"missing {md}"}
    try:
        if md.stat().st_size == 0:
            return {"status": "NOT-READY", "skill": skill,
                    "reason": f"empty {md}"}
    except OSError as exc:
        return {"status": "NOT-READY", "skill": skill,
                "reason": f"unreadable {md}: {exc}"}
    if not entry.is_file():
        return {"status": "NOT-READY", "skill": skill,
                "reason": f"missing canonical entry {entry}"}
    if not os.access(entry, os.X_OK):
        return {"status": "NOT-READY", "skill": skill,
                "reason": f"canonical entry not executable: {entry}"}
    return {"status": "READY", "skill": skill,
            "reason": f"SKILL.md + executable entry present"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skill", required=True, choices=LEGAL_SKILLS)
    ap.add_argument("--skills-dir", required=True, type=Path)
    ap.add_argument("--entry", required=True, type=Path)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 1)
    result = probe(args.skill, args.skills_dir, args.entry)
    print(json.dumps(result))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())
