"""PD-TEST-158 -- the P4-COPY contract's NON-RENDERED fields must not reach copy[].

THE DEFECT, measured live on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

`slides.schema.json` defines `copy[]` as "the EXACT text that must appear rendered
on the slide", and `slides_assembly._FIELD_LINE_RE` exists to keep engine metadata
out of it. But that regex listed only
`HOOK_REFRAIN|LADDER|RESEARCH_USED|ARC|BEAT|TAG|TAGS`, while the P4-COPY contract
in `sops/slide-copywriter-sops.md` step 2 mandates a LARGER field set -- `SECTION`,
`PURPOSE`, `ARCHETYPE`, `PROOF USED`, `PEOPLE`, `TEXT_ANCHOR`, `PRESENTER NOTE`,
`HOOK VARIANT` were all missing from it.

That is not cosmetic. `copy[]` drives `build_deck._load_slide_copy_map` and hence
the AF-P-VERBATIM check, which FAILS a slide until every `copy[]` string is baked
verbatim into the image prompt. So metadata left in `copy[]` makes the engine
demand that its own bookkeeping be PAINTED ONTO THE SLIDE. The live run's
`working/checkpoints/prompt-worker-results-attempts.jsonl` carries it verbatim:

    AF-P-VERBATIM ... measured='copy not baked' required='SECTION: decision-rerank'
    AF-P-VERBATIM ... measured='copy not baked' required='PURPOSE: Force the
                      priority question out loud...'

and, worst of all, `PRESENTER NOTE` -- which the SOP itself defines as "sentences
the speaker says aloud that are NOT on the slide", with step 1 adding "never put
the presenter's spoken words on the slide". Demanding it be baked does exactly
what the doctrine forbids.

WHAT THESE TESTS PIN
  * every field the SOP's copy-block template prescribes is CLASSIFIED here, so a
    field added to the contract fails this suite until someone decides whether it
    renders (the same tripwire shape that caught PD-TEST-156);
  * every field classified NON-RENDERED is stripped by `copy_lines()`;
  * every field classified RENDERED survives, with its text intact;
  * the guard is not vacuous -- `copy_lines()` really does return the rendered
    lines of the live block shape.

The field list is read from the SOP itself rather than restated, so the contract
document is the single source of truth for WHICH fields exist; only the
rendered/non-rendered split is asserted here, with its reason.
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, Set

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import slides_assembly as sa  # noqa: E402

REPO_ROOT = SCRIPTS.parents[4]
SOP = (REPO_ROOT / "23-ai-workforce-blueprint" / "templates" / "role-library"
       / "presentations" / "sops" / "slide-copywriter-sops.md")

#: Field lines of the P4-COPY slide-block template, e.g. `   HEADLINE: [max 9 ...]`.
_TEMPLATE_FIELD_RE = re.compile(r"^\s{2,}([A-Z][A-Z0-9_ ]{2,20}):\s*\[", re.M)

#: Fields that ARE the slide's words, and must therefore reach `copy[]`.
RENDERED: Set[str] = {"HEADLINE", "EMPHASIS", "SUBHEAD", "SUPPORTING"}

#: Fields that are engine/authoring metadata, keyed to why. Every one of these is
#: prescribed by the SOP template and none of them is text a viewer should read.
NON_RENDERED: Dict[str, str] = {
    "SECTION": "arc-section name (engine routing)",
    "PURPOSE": "the one big idea, a brief addressed to the WRITER",
    "ARCHETYPE": "A1-A5 layout id (design routing)",
    "LADDER": "offer-ladder position (commercial routing)",
    "PROOF USED": "proof-inventory item name",
    "RESEARCH_USED": "research_map item_id(s)",
    "PEOPLE": "yes/no + representation group",
    "HOOK_REFRAIN": "yes/no + where the hook sits",
    "TEXT_ANCHOR": "a layout token (bottom band | left block | ...)",
    "PRESENTER NOTE": ("the SOP says these are 'sentences the speaker says aloud "
                       "that are NOT on the slide'"),
    "HOOK VARIANT": "which hook variant was used (engine metadata)",
}

#: A block in the live shape: the SOP template's own fields, filled in.
_LIVE_BLOCK = "\n".join([
    "SLIDE 1",
    "SECTION: decision-rerank",
    "PURPOSE: Force the priority question out loud and make the stakes visible.",
    "ARCHETYPE: A1",
    "LADDER: none",
    "HEADLINE: Department First, or Back on Your Plate?",
    "EMPHASIS: Department First",
    "SUBHEAD: Your plate holds the deck work. The department is missing.",
    "SUPPORTING:",
    "- Take a stance on this list",
    "- Carrying deck work alone",
    "PROOF USED: none",
    "RESEARCH_USED: none",
    "PEOPLE: no",
    "HOOK_REFRAIN: yes",
    "TEXT_ANCHOR: center punch",
    "PRESENTER NOTE: Name their real list out loud, then let the omission sit.",
    "HOOK VARIANT: The department is not a last resort.",
])


def _sop_fields() -> Set[str]:
    assert SOP.is_file(), f"the copy contract this guards is missing: {SOP}"
    text = SOP.read_text(encoding="utf-8")
    # Narrow to the copy-block template so unrelated `X: [` markdown cannot leak in.
    start = text.find("SLIDE [N]")
    assert start != -1, "the SOP no longer shows a `SLIDE [N]` template block"
    end = text.find("---", text.find("PRESENTER NOTE", start))
    window = text[start:end if end != -1 else start + 4000]
    return {m.group(1).strip() for m in _TEMPLATE_FIELD_RE.finditer(window)}


def test_every_contract_field_is_classified():
    """The tripwire: a NEW field in the SOP template must be classified here."""
    fields = _sop_fields()
    assert fields, "no fields parsed from the SOP template -- guard is vacuous"

    classified = RENDERED | set(NON_RENDERED)
    unclassified = sorted(fields - classified)
    assert not unclassified, (
        "the P4-COPY contract prescribes fields this test does not classify: "
        f"{unclassified}. Decide for each whether it is rendered ON the slide "
        "(add to RENDERED) or engine/authoring metadata (add to NON_RENDERED with "
        "a reason). Leaving it unclassified is how PD-TEST-158 happened: metadata "
        "stayed in copy[] and the engine then demanded it be baked into the image "
        "prompt, painting its own bookkeeping onto the slide.")

    stale = sorted(classified - fields)
    assert not stale, (
        f"these fields are classified here but no longer in the contract: {stale} "
        "-- drop them from this test so it keeps describing the real contract")


def test_every_non_rendered_field_is_stripped_from_copy():
    lines = sa.copy_lines(_LIVE_BLOCK)
    joined = "\n".join(lines)
    leaked = sorted(f for f in NON_RENDERED if re.search(rf"(?im)^\s*{re.escape(f)}\s*:", joined))
    assert not leaked, (
        "these engine-metadata fields reached copy[], and copy[] drives the "
        f"AF-P-VERBATIM check: {leaked}. Each is then DEMANDED verbatim in the "
        "image prompt, i.e. painted onto the rendered slide. Add them to "
        f"slides_assembly._FIELD_LINE_RE. Reasons: "
        + "; ".join(f"{f} = {NON_RENDERED[f]}" for f in leaked))


def test_every_rendered_field_survives_with_its_text():
    lines = sa.copy_lines(_LIVE_BLOCK)
    joined = "\n".join(lines)
    for field in sorted(RENDERED):
        assert re.search(rf"(?m)^\s*{re.escape(field)}\s*:", joined), (
            f"{field} is RENDERED copy but copy_lines() dropped it -- the slide "
            "would render without its own words")
    # The actual words must survive, not just the labels.
    for fragment in ("Department First, or Back on Your Plate?",
                     "Your plate holds the deck work.",
                     "Take a stance on this list"):
        assert fragment in joined, f"rendered text was lost: {fragment!r}"


def test_the_guard_is_not_vacuous():
    lines = sa.copy_lines(_LIVE_BLOCK)
    assert lines, "copy_lines() returned nothing for a full live-shaped block"
    assert len(lines) < len(_LIVE_BLOCK.splitlines()), (
        "copy_lines() stripped nothing at all -- the guard above would pass "
        "vacuously")
