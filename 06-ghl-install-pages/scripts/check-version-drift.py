#!/usr/bin/env python3
"""Version-marker consistency gate for Skill 06 (repo version-bump hygiene).

v19.0.1 fix (cleanup lane, install-advisory investigation): this checker used
to demand triple equality across skill-version.txt, SKILL.md, AND the
CHANGELOG.md top heading. That is no longer the correct invariant.

scripts/bump-version.sh (see "G3-on-06 GAP FIX", v14.0.1) DELIBERATELY tracks
06-ghl-install-pages/skill-version.txt and SKILL.md's nested `metadata:
version:` at the REPO version (v14.0.1 comment: "intentionally tracked at the
repo /version ... like 23-ai-workforce-blueprint/skill-version.txt"), so the
G3 CI guard stays green whenever the browser-manager markers roll. 06's own
CHANGELOG.md, like every other skill's, is an independent historical log kept
at 06's own per-skill semver (it was at v6.x/v17.x while skill-version.txt
was already repo-locked at v14+/v19) — 23-ai-workforce-blueprint has the same
repo-locked skill-version.txt/independent-CHANGELOG split and, correctly,
ships no triple-equality gate at all. Comparing CHANGELOG's number against
the repo-locked markers was therefore comparing two different, intentionally
independent version namespaces — it could never pass after a repo bump
without someone remembering to also hand-add a same-numbered CHANGELOG entry,
and nothing else in the repo does that. That's what fired the "05/06 not
verified" install advisory on the Wave-7 re-install (06's qc-*.sh -- FAIL on
this exact assertion; 05 was a separate, since-fixed gate false-positive).

What this checker now verifies (the invariant that's actually intended):
  1. ``skill-version.txt`` and SKILL.md's ``metadata.version`` MUST agree —
     both are repo-locked by bump-version.sh in the same commit, so if they
     disagree, one of the two lockstep `_roll_marker`/rewrite steps was
     missed (the real regression the repo-lock exists to prevent).
  2. ``CHANGELOG.md`` MUST have a parseable top ``## [vX.Y.Z]`` heading — i.e.
     the file exists and isn't malformed/empty. Its NUMBER is intentionally
     NOT compared to the repo-locked markers.

Usage::

    check-version-drift.py <skill-dir>

Exit 0 when (1) and (2) hold; exit 1 (printing the values) otherwise. No
third-party deps; stdlib only.
"""
from __future__ import annotations

import pathlib
import re
import sys


def _norm(v: str) -> str:
    return v.strip().lstrip("vV").strip()


def read_versions(skill_dir: pathlib.Path) -> dict:
    """Return ``{"skill_version_txt", "skill_md", "changelog"}`` normalized."""
    out: dict = {}

    txt_path = skill_dir / "skill-version.txt"
    out["skill_version_txt"] = (
        _norm(txt_path.read_text(encoding="utf-8")) if txt_path.exists() else "MISSING:skill-version.txt"
    )

    smd_path = skill_dir / "SKILL.md"
    if smd_path.exists():
        m = re.search(
            r"^\s*version:\s*[\"']?v?([0-9]+\.[0-9]+\.[0-9]+)",
            smd_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        out["skill_md"] = _norm(m.group(1)) if m else "UNPARSEABLE:SKILL.md"
    else:
        out["skill_md"] = "MISSING:SKILL.md"

    chg_path = skill_dir / "CHANGELOG.md"
    if chg_path.exists():
        m = re.search(
            r"^##\s*\[v?([0-9]+\.[0-9]+\.[0-9]+)\]",
            chg_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        out["changelog"] = _norm(m.group(1)) if m else "UNPARSEABLE:CHANGELOG.md"
    else:
        out["changelog"] = "MISSING:CHANGELOG.md"

    return out


def main(argv: list) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: check-version-drift.py <skill-dir>\n")
        return 2
    skill_dir = pathlib.Path(argv[1])
    v = read_versions(skill_dir)

    markers_ok = (
        v["skill_version_txt"] == v["skill_md"]
        and not any(
            v[k].startswith(("MISSING", "UNPARSEABLE")) for k in ("skill_version_txt", "skill_md")
        )
    )
    changelog_ok = not v["changelog"].startswith(("MISSING", "UNPARSEABLE"))
    agree = markers_ok and changelog_ok

    verdict = "OK" if agree else "DRIFT"
    sys.stderr.write(
        f"skill-version.txt={v['skill_version_txt']} "
        f"SKILL.md={v['skill_md']} "
        f"CHANGELOG={v['changelog']} "
        f"(markers-agree={markers_ok} changelog-wellformed={changelog_ok}) -> {verdict}\n"
    )
    return 0 if agree else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
