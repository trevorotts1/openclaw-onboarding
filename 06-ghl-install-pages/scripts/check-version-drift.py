#!/usr/bin/env python3
"""Version-drift triple-equality gate for Skill 06 (repo version-bump hygiene).

The single version of record MUST agree across three places:
  1. ``skill-version.txt``          (the canonical version file)
  2. ``SKILL.md`` frontmatter       (``metadata.version: "X.Y.Z"``)
  3. ``CHANGELOG.md`` top entry     (the first ``## [vX.Y.Z]`` heading)

Any drift between them is a release-hygiene failure (a skill whose three
version strings disagree shipped with a missed bump). Comparison is
leading-``v`` and whitespace insensitive.

Usage::

    check-version-drift.py <skill-dir>

Exit 0 when all three agree; exit 1 (printing the three values) on drift or a
missing/unparseable version. No third-party deps; stdlib only.
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
    agree = (
        v["skill_version_txt"] == v["skill_md"] == v["changelog"]
        and not any(s.startswith(("MISSING", "UNPARSEABLE")) for s in v.values())
    )
    verdict = "OK" if agree else "DRIFT"
    sys.stderr.write(
        f"skill-version.txt={v['skill_version_txt']} "
        f"SKILL.md={v['skill_md']} "
        f"CHANGELOG={v['changelog']} -> {verdict}\n"
    )
    return 0 if agree else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
