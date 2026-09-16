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
RENDERED: Set[str] = {"HEADLINE", "SUBHEAD", "SUPPORTING"}

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
    "MOVE TAG": ("PD-TEST-173 -- which of the eight build-move beats this slide carries. build_deck.AF-NO-SHIFT "
                 "REQUIRES >=5 of the eight tags to appear in slides_copy.md, monotonic, so the writer MUST record "
                 "them in the copy file; before MOVE TAG was classified, the live run's `MOVE TAG: TRIGGER` line "
                 "was not stripped, became copy[0] -- THE HEADLINE -- and shifted every positional reader by one "
                 "for that slide (slide_craft AF-OBI-1 and build_deck AF-COPY-BAND both graded it as slide text). "
                 "NOTE, retracted claim: an earlier revision of this docstring said AF-P-VERBATIM then demanded it "
                 "be painted onto the slide as its headline. That is FALSE -- slide-08.txt:48 mentions the tag in a "
                 "metadata section and says 'Render nothing from that tag as visible artwork', and AF-P-VERBATIM is a "
                 "substring-presence test, so the mention satisfied it; 0 of the run's 56 AF-P-VERBATIM failures name "
                 "MOVE TAG. The harm here is positional, not verbatim."),
    "EMPHASIS": ("which words take the accent colour -- a DESIGN instruction; the accent word already sits inside "
                 "the headline, and the engine's own P4-PROMPT contract lists EMPHASIS among the fields that are "
                 "'internal production metadata never rendered on the slide'"),
    "PRESENTER NOTE": ("the SOP says these are 'sentences the speaker says aloud "
                       "that are NOT on the slide'"),
    "HOOK VARIANT": "which hook variant was used (engine metadata)",
}

#: A block in the REAL live shape -- taken from the run's own slides_copy.md,
#: including the two things the first version of this fixture lacked and which
#: therefore went unnoticed: contract-sanctioned QC-NOTE HTML comments (the SOP
#: 9.1 tells the writer to "flag the gap in a comment in slides_copy.md") and a
#: standalone `---` rule. Both reached copy[] and were demanded verbatim.
_LIVE_BLOCK = "\n".join([
    # NOTE: no leading `SLIDE 1` line. Production never passes the block
    # DELIMITER to copy_lines (iter_slide_copy_blocks returns the body only), so
    # including it made copy_lines emit it as a copy line and skewed the
    # positional assertions below. Review finding on the previous revision.
    "SECTION: decision-rerank",
    "PURPOSE: Force the priority question out loud and make the stakes visible.",
    "ARCHETYPE: A1",
    "LADDER: none",
    # PD-TEST-173: the live run carries this line (slides_copy.md line 140) and
    # it was the ONLY field-shaped line in the whole file that copy_lines() did
    # not strip -- so it became copy[0], i.e. the HEADLINE.
    "MOVE TAG: TRIGGER",
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
    "<!-- QC-NOTE: AF-NO-BRANDED-METHOD -- intake.json has no named_methodology -->",
    "---",
])

#: Lines that are engine bookkeeping but are NOT `FIELD:` lines, so the field
#: classification cannot describe them. They are stripped structurally.
_NON_FIELD_BOOKKEEPING = ("QC-NOTE", "<!--", "---")


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


def test_every_rendered_VALUE_survives_and_its_LABEL_does_not():
    """PD-TEST-169: copy[] is the slide's TEXT, not a labelled form.

    slides.schema.json defines copy[] as "the EXACT text that must appear
    rendered on the slide, in reading order. Index 0 is treated as the HEADLINE"
    and its own example is ["Northwind Co", "Three moves that doubled our
    pipeline in 90 days"] -- BARE text. A `HEADLINE:` prefix is therefore not
    slide copy, and leaving it in made AF-P-VERBATIM demand the LABEL be painted
    into the image (measured live: 8 of 8 prompts failed on exactly that)."""
    lines = sa.copy_lines(_LIVE_BLOCK)
    joined = "\n".join(lines)

    # The VALUES survive...
    for fragment in ("Department First, or Back on Your Plate?",
                     "Your plate holds the deck work.",
                     "Take a stance on this list"):
        assert fragment in joined, f"rendered text was lost: {fragment!r}"

    # ...and the LABELS do not.
    for field in sorted(RENDERED):
        assert not re.search(rf"(?m)^\s*{re.escape(field)}\s*:", joined), (
            f"the {field}: label reached copy[] -- copy[] is the text RENDERED on "
            "the slide, and a label is not that text")

    # copy[] must be in the shape its POSITIONAL consumers assume: index 0 the
    # headline, index 1 the subhead, the rest body lines (PD-TEST-163).
    assert lines[0] == "Department First, or Back on Your Plate?", lines[0]
    assert lines[1] == "Your plate holds the deck work. The department is missing.", lines[1]
    assert lines[2] == "Take a stance on this list", lines[2]


def test_non_field_bookkeeping_is_stripped_too():
    """HTML comments and standalone `---` rules are bookkeeping, not slide copy.

    The field classification cannot see these: they are not `FIELD:` lines, and
    the P4-COPY contract actively tells the writer to leave QC notes in comments
    (SOP 9.1). The first version of this fix missed all of them, and AF-P-VERBATIM
    then demanded the QC notes be baked into the image prompt."""
    joined = "\n".join(sa.copy_lines(_LIVE_BLOCK))
    leaked = [token for token in _NON_FIELD_BOOKKEEPING if token in joined]
    assert not leaked, (
        f"non-field engine bookkeeping reached copy[]: {leaked}. copy[] drives "
        "AF-P-VERBATIM, so each is DEMANDED verbatim in the image prompt. Strip "
        "HTML comments and standalone horizontal rules in copy_lines() -- see "
        "_HTML_COMMENT_RE / _RULE_LINE_RE.")


def test_every_field_regex_token_is_a_contract_field():
    """The REVERSE direction: the regex may not invent field names.

    The contract->classification tripwire above is one-directional, so it cannot
    catch a token added to `_FIELD_LINE_RE` that no contract prescribes. The first
    version of this fix shipped exactly that (`VISUAL_ANCHOR`, which appears
    nowhere in the repo outside the regex) while claiming to be "grounded in the
    contract". This asserts the set is a subset of the contract's own fields (plus
    the legacy aliases the engine has always stripped)."""
    legacy = {"ARC", "BEAT", "TAG", "TAGS"}
    pattern = sa._FIELD_LINE_RE.pattern
    # Pull the alternation body out of `^\s*(?:A|B|C)\s*:` and undo the escapes.
    import re as _re
    body = pattern.split("(?:", 1)[1].rsplit(")", 1)[0]
    tokens = set()
    for t in body.split("|"):
        # `HOOK\s+VARIANT` -> `HOOK VARIANT`; `PROOF\s+USED` -> `PROOF USED`.
        norm = _re.sub(r"\\s\+?", " ", t).replace("\\", "").strip().upper()
        norm = _re.sub(r"\s+", " ", norm)
        if norm:
            tokens.add(norm)
    assert tokens, "could not parse any token out of _FIELD_LINE_RE"

    unknown = sorted(tokens - _sop_fields() - legacy)
    assert not unknown, (
        f"_FIELD_LINE_RE strips fields no contract prescribes: {unknown}. Either "
        "the contract is missing them (add them there first) or they are invented "
        "-- an invented token silently deletes real slide copy, and the "
        "contract->classification tripwire cannot see it.")


def test_move_tag_never_becomes_the_headline():
    """PD-TEST-173 -- the engine's own routing metadata must not BE the headline.

    `MOVE TAG` is not optional decoration: `build_deck.AF-NO-SHIFT` requires >=5
    of the eight build-move tags to appear IN `slides_copy.md`, monotonic, so the
    copywriter has to record them in the copy file -- and before this field was
    classified, the block template never said how, so the live run invented
    `MOVE TAG: TRIGGER`. Nothing stripped it, so it landed at copy[0].

    That is the most damaging possible position. copy[0] is the HEADLINE: it is
    the field `slide_craft` AF-OBI-2 word-counts, the field
    `build_deck._chk_copy_density` measures against the headline band, the field
    `workbook_mapper._title_from_copy` prints as the workbook's slide title, and
    -- through AF-P-VERBATIM -- a string the image prompt must render verbatim.

    Measured on the live run before this fix: slide 08's copy[0] was
    `MOVE TAG: TRIGGER`, the real headline sat at index 1, and
    `working/prompts/slide-08.txt` contains the string `MOVE TAG` exactly once
    while the other seven prompts contain it zero times.
    """
    lines = sa.copy_lines(_LIVE_BLOCK)
    assert lines, "copy_lines() returned nothing"
    assert lines[0] == "Department First, or Back on Your Plate?", (
        "the first copy line is not the headline -- an engine metadata line has "
        f"taken copy[0]: {lines[0]!r}. copy[0] is what AF-OBI-2 word-counts, what "
        "the copy-density band measures (AF-COPY-BAND bands fields[0] as the "
        "HEADLINE), and what the workbook prints as the slide title.")
    assert not any(re.match(r"(?i)^\s*MOVE\s+TAG\s*:", ln) for ln in lines), (
        f"a MOVE TAG line reached copy[]: {lines}")
    # and it must not survive in any other guise either
    assert "TRIGGER" not in "\n".join(lines), (
        "the move tag VALUE leaked into copy[] without its label")


def test_the_guard_is_not_vacuous():
    lines = sa.copy_lines(_LIVE_BLOCK)
    assert lines, "copy_lines() returned nothing for a full live-shaped block"
    assert len(lines) < len(_LIVE_BLOCK.splitlines()), (
        "copy_lines() stripped nothing at all -- the guard above would pass "
        "vacuously")
