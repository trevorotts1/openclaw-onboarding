#!/usr/bin/env python3
"""Resolve a sibling skill by SLUG under either directory convention.

Skill 71 reaches two other skills at run time: Skill 49's `scripts/kie74_receipt.py`
(the one writer/checker of transport receipts) and Skill 74's `scripts/kie_live_adapter.py`
(the paid KIE transport). Both used to be spelled as a hard-coded numbered directory
(`SKILL_ROOT.parent / "49-signature-funnel" / ...`), plus, for the adapter, another
checkout under the operator's home (`~/openclaw-onboarding/74-kie-live-adapter/...`).

Neither spelling survives distribution. A 999 package names the trees by bare slug
(`.claude/skills/signature-funnel`), the onboarding repository names them
`<number>-<slug>`, and the operator's home is not part of any installation. This
module is the ONE resolver both call sites use, with the same acceptance rule Skill
83's `launcher_core.constants.resolve_skill_dir` applies:

  * a candidate is a directory named `<slug>` or ending in `-<slug>` that carries a
    SKILL.md, searched in the skill root's parent and its `.claude/skills` and
    `skills` children (the onboarding and the deployed layouts);
  * an exact `<number>-<slug>` wins over a bare `<slug>`;
  * nothing under `Path.home()` and no other repository is ever consulted;
  * no candidate returns None, so a missing sibling is one named absence the caller
    reports, never a FileNotFoundError from deep inside an import.

Stdlib only. Reads nothing, writes nothing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_NUMERIC_PREFIX = re.compile(r"^(\d+)-(.+)$")


def skill_root_for(script: Path) -> Path:
    """The skill tree a script under <skill>/scripts/ belongs to."""
    return Path(script).resolve().parents[1]


def search_bases(skill_root: Path) -> tuple:
    """Every directory a sibling skill may live in, for this layout, nearest first."""
    root = Path(skill_root).resolve()
    bases = [root.parent, root.parent / ".claude" / "skills", root.parent / "skills"]
    seen, out = set(), []
    for base in bases:
        if base.is_dir() and str(base) not in seen:
            seen.add(str(base))
            out.append(base)
    return tuple(out)


def skill_dir_for(slug: str, skill_root: Path) -> Optional[Path]:
    """The directory for `slug`, or None. Never guesses from a file path."""
    candidates = []
    for base in search_bases(skill_root):
        try:
            entries = sorted(base.iterdir(), key=lambda p: p.name.encode("utf-8"))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or not (entry / "SKILL.md").is_file():
                continue
            if entry.name == slug or entry.name.endswith("-" + slug):
                bare = entry.name == slug
                candidates.append((bare, entry))
    if not candidates:
        return None
    # An exact <number>-<slug> wins, then the bare slug, then the first by name.
    numbered = sorted((p for bare, p in candidates if not bare),
                      key=lambda p: (int(_NUMERIC_PREFIX.match(p.name).group(1))
                                     if _NUMERIC_PREFIX.match(p.name) else 0, p.name))
    if numbered:
        return numbered[0]
    return sorted((p for bare, p in candidates if bare), key=lambda p: p.name)[0]


def skill_file(slug: str, *parts: str, skill_root: Path) -> Optional[Path]:
    """A named file inside the sibling skill, or None when the skill or the file is absent."""
    directory = skill_dir_for(slug, skill_root)
    return directory.joinpath(*parts) if directory is not None else None


def self_check() -> int:
    """Prove the resolver on throwaway trees: bare slug, numbered, both, and neither."""
    import tempfile

    failures = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for layout, name in (("onboard", "49-signature-funnel"),
                             ("deployed", ".claude/skills/signature-funnel")):
            skill = tmp / layout / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: signature-funnel\n---\n", encoding="utf-8")
            got = skill_dir_for("signature-funnel", skill)
            if got is None or got.resolve() != skill.resolve():
                failures.append(f"{layout}: resolved {got}, expected {skill}")
            missing = skill_dir_for("kie-live-adapter", skill)
            if missing is not None:
                failures.append(f"{layout}: a missing sibling resolved to {missing}")
        both = tmp / "both"
        for name in ("signature-funnel", "49-signature-funnel"):
            (both / name).mkdir(parents=True)
            (both / name / "SKILL.md").write_text("---\nname: signature-funnel\n---\n",
                                                 encoding="utf-8")
        anchor = both / "71-blackceo-signature-page"
        (anchor / "scripts").mkdir(parents=True)
        (anchor / "SKILL.md").write_text("---\nname: blackceo-signature-page\n---\n", encoding="utf-8")
        got = skill_dir_for("signature-funnel", anchor)
        if got is None or got.name != "49-signature-funnel":
            failures.append(f"both: numbered must win, resolved {got}")
    for failure in failures:
        print("SELF-CHECK FAIL: " + failure)
    if failures:
        return 1
    print("SELF-CHECK PASS — bare slug, numbered directory, numbered-wins and absent sibling")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(self_check())
