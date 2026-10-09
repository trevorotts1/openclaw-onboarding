#!/usr/bin/env python3
"""U12: docs in lockstep with the code. Stdlib only.

(a) the choice-card-spec "Offered lengths (seconds)" line equals
    music_styles.OFFERED_LENGTHS_S;
(b) SKILL.md names the request-limit section and the not-built captions check;
(c) the onboarding SOP (when present) no longer says "three to four lip-sync
    lines, 15 to 20 seconds" and DS-2 lists the 2-minute length.
Run: python3 scripts/core/prompt_templates/test_docs_u12.py (pytest-collectable)."""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
SKILL = CORE.parent.parent
sys.path[:0] = [str(CORE), str(CORE / "music_styles")]
import music_styles as MS  # noqa: E402

SOP = None
for up in range(1, 6):
    c = SKILL.parents[up - 1] / "23-ai-workforce-blueprint/templates/role-library/video/sops/SOP--drama-song-ad-pipeline.md"
    if c.is_file():
        SOP = c
        break


def test_card_length_list_equals_offered_lengths():
    t = (SKILL / "references/choice-card-spec.md").read_text(encoding="utf-8")
    m = re.search(r"Offered lengths \(seconds\):\s*([0-9, ]+)\.", t)
    assert m, "choice-card-spec.md has no 'Offered lengths (seconds):' line"
    got = tuple(int(x) for x in m.group(1).replace(" ", "").split(",") if x)
    assert got == tuple(MS.OFFERED_LENGTHS_S), (got, MS.OFFERED_LENGTHS_S)


def test_skill_md_sections():
    t = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for s in ("## Request and prompt limits", "PROMPT_OVER_CAP", "NOT built on main (FU-U9",
              "BOOK_SHOT_NOT_CONTRACTED", "UNTAGGED_LYRIC_LINES"):
        assert s in t, s


def test_sop_lipsync_counts_and_lengths():
    if SOP is None:
        return  # 999-setup carries no SOP
    t = SOP.read_text(encoding="utf-8")
    assert "three to four lines" not in t, "stale DS-4 step 5 lip-sync count"
    assert "6 to 8" in t and "2 minutes" in t.split("### DS-3")[0]


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok:", n)
    print("ALL PASS")
