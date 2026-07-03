#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_tone_core_sync.py — prove this skill's baked tone stages are byte-for-byte
in lockstep with the canonical shared tone/writing core, so the shared IP never drifts.

Compares 54-anthology-writer/prompts/{04..08} against
shared-utils/tone-writing-core/prompts/{04..08}. Fail-closed. (AF-AW-TONE-DRIFT)
Exit 0 = in sync, 2 = drift, 3 = usage/IO error.

Skill 54 references the shared tone-writing-core (Trevor's standing decision: the
writing skills stay SEPARATE skills sharing ONE tone core). It bakes a lockstep
copy for a self-contained run and proves the copy here at build/CI time.
"""
from __future__ import annotations
import hashlib
import sys
from pathlib import Path

SKILL_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
# repo-root/shared-utils/tone-writing-core — three parents up from scripts/
CORE = Path(__file__).resolve().parents[2] / "shared-utils" / "tone-writing-core" / "prompts"
TONE_STAGES = ["04-tone-style-1", "05-tone-style-2", "06-tone-style-3", "07-tone-style-4", "08-blended-tone"]
FILES = ["system.md", "methodology.md", "user.md"]


def _h(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    if not CORE.is_dir():
        print(f"USAGE/IO ERROR: shared tone core not found at {CORE}")
        return 3
    drift = []
    for stage in TONE_STAGES:
        for f in FILES:
            a = SKILL_PROMPTS / stage / f
            b = CORE / stage / f
            if not a.is_file() or not b.is_file():
                drift.append(f"{stage}/{f}: missing ({'skill' if not a.is_file() else 'core'})")
            elif _h(a) != _h(b):
                drift.append(f"{stage}/{f}: sha256 drift from canonical core")
    if drift:
        print(f"AF-AW-TONE-DRIFT: {len(drift)} tone-core drift(s) — skill baked copy != canonical shared core.")
        for d in drift:
            print(f"  DRIFT {d}")
        return 2
    print(f"PASS: all {len(TONE_STAGES)} tone stages in lockstep with shared-utils/tone-writing-core.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
