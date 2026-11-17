"""PD-094b -- the dollar-figure paragraph follows the price decision.

Spec (01-BUILD-SPEC.md, PD-094b): replace the paragraph that begins
"The only authorized dollar figure on the deck face is the SINGLE big callout"
with:

    On slides that are not offer-arc slides listed in AF-PRICE-FACE, the face
    carries promises and outcomes, not dollar values.

Acceptance rows A1, A2, A3 are one test each.

A2 note (recorded, not hidden): the spec says "role file, Part F, then
regenerate its mirror". SOP 9.10 -- and therefore Part F -- is NOT carried in
slide-image-creator.md; that role file's own numbering note records the
divergence: "SOPs 9.10 (one-page infographic) and 9.11 ... are carried in the
SOP mirror (sops/slide-image-creator-sops.md) and are binding from there".
So A2 proves the strongest true invariant available: the role file still
defines every SOP the mirror carries it, the mirror carries every SOP the role
file defines, and the role file was not edited. Literal whole-file mirror
equality is FALSE at the base commit in 7 other sections (pre-existing drift,
proven in evidence/PD-094b/BUILD-REPORT.md), so it is not asserted here.
"""
import os
import pathlib
import re
import subprocess

PRES = pathlib.Path(__file__).resolve().parent.parent.parent
ROLE = PRES / "slide-image-creator.md"
MIRROR = PRES / "sops" / "slide-image-creator-sops.md"
QC = PRES / "qc-specialist-presentations.md"
QC_REL = (
    "23-ai-workforce-blueprint/templates/role-library/presentations/"
    "qc-specialist-presentations.md"
)

NEW_SENTENCE = (
    "On slides that are not offer-arc slides listed in AF-PRICE-FACE, the face "
    "carries promises and outcomes, not dollar values."
)
OLD_LEAD = "The only authorized dollar figure on the deck face is the SINGLE big callout"
OLD_DECK_WIDE = "SINGLE big callout"
PART_F_RE = re.compile(
    r"\*\*Part F -- PROMISES-NOT-PRICES.*?\*\*(.*?)(?=\n\*\*Part [G-Z]|\Z)", re.S
)
SOP_RE = re.compile(r"^### (SOP 9\.\d+)\b[^\n]*$", re.M)


def _text(p):
    return p.read_text(encoding="utf-8")


def _part_f():
    m = PART_F_RE.search(_text(MIRROR))
    assert m, "Part F block not found in the SOP mirror"
    return m.group(1)


def _base_commit():
    """Base of this branch, or None when it cannot be resolved."""
    env = os.environ.get("PD094B_BASE")
    if env:
        return env
    for rev in ("HEAD~1", "origin/main"):
        p = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", rev],
            cwd=PRES, capture_output=True, text=True,
        )
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    return None


def _show(rev, path):
    p = subprocess.run(
        ["git", "show", f"{rev}:{path}"], cwd=PRES,
        capture_output=True, text=True,
    )
    return p.stdout if p.returncode == 0 else None


def _price_face_row():
    """PD-090's AF-PRICE-FACE row: its branch first, then this tree.

    PD-090 lands with this unit (shared --hold-d17), so before the merge the
    rewritten row lives only on the sibling branch; afterwards the working tree
    carries it and a deleted branch is not a failure. PD-090 labels the row
    `| AF-PRICE-FACE (role-level; not in the registry) |`, so match the row by
    its first cell -- the parenthetical is PD-090's qualifier, not a lost row.
    """
    sources = (
        _show("origin/pd/fl23-role-procedures-b--hold-d17", QC_REL),
        _show("pd/fl23-role-procedures-b--hold-d17", QC_REL),
        _text(QC),
    )
    for text in sources:
        for line in (text or "").splitlines():
            if re.match(r"^\|\s*AF-PRICE-FACE\b", line):
                return line
    return ""


# ---------------------------------------------------------------------------
# A1 -- the new sentence is present once and the old paragraph is gone
# ---------------------------------------------------------------------------
def test_A1_new_sentence_present_once_and_old_paragraph_gone():
    body = _part_f()
    assert body.count(NEW_SENTENCE) == 1, "new sentence must appear exactly once in Part F"
    assert OLD_LEAD not in _text(MIRROR), "old paragraph lead is still present"
    assert OLD_DECK_WIDE not in _text(MIRROR), "the deck-wide single-price rule survived"


# ---------------------------------------------------------------------------
# A2 -- the mirror still covers the role file's section 9, and the role file
#       was not edited (SOP 9.10 Part F is mirror-only; see module docstring)
# ---------------------------------------------------------------------------
def test_A2_mirror_covers_role_file_section_9_and_role_file_untouched():
    role_sops = set(SOP_RE.findall(_text(ROLE)))
    mirror_sops = set(SOP_RE.findall(_text(MIRROR)))

    assert role_sops, "role file defines no SOP 9.x headings"
    missing = sorted(role_sops - mirror_sops)
    assert not missing, f"mirror dropped SOP blocks the role file defines: {missing}"

    # SOP 9.10 (Part F) is mirror-only -- the premise the spec assumes is false.
    assert "SOP 9.10" in mirror_sops
    assert "SOP 9.10" not in role_sops, (
        "role file now carries SOP 9.10; regenerate the mirror instead of hand-editing"
    )

    # The edit is not duplicated into the role file.
    assert NEW_SENTENCE not in _text(ROLE)

    # Role file bytes vs base, when base is resolvable.
    base = _base_commit()
    if base:
        old = _show(base, "23-ai-workforce-blueprint/templates/role-library/presentations/"
                          "slide-image-creator.md")
        if old is not None:
            assert old == _text(ROLE), "role file changed; this unit edits the mirror only"


# ---------------------------------------------------------------------------
# A3 -- the rule agrees with PD-090's rewritten AF-PRICE-FACE
# ---------------------------------------------------------------------------
PD090_CLASSES = ("price-belt", "value-stack", "tally", "re-pitch", "value-gap",
                 "callback", "component-card")


def test_A3_rule_agrees_with_pd090_price_face():
    body = _part_f()

    # The new rule delegates the dollar-figure whitelist to AF-PRICE-FACE.
    assert "AF-PRICE-FACE" in body
    assert "not dollar values" in body

    # The promise-copy FAIL/PASS examples stay (Change nothing else).
    assert 'FAIL: "Day 1 Strategy Session | Value: $997"' in body
    assert '- PASS: "Day 1: The one conversation' in body

    row = _price_face_row()
    assert row, (
        "no AF-PRICE-FACE row on PD-090's branch or in "
        "qc-specialist-presentations.md; A3 quotes PD-090's rewritten row"
    )
    for cls in PD090_CLASSES:
        assert cls in row, f"PD-090 row lost class {cls!r}: {row}"
    assert "Unauthorized dollar figures on a slide face outside" in row
