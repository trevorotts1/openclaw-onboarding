"""PD-TEST-098 -- the design-page producer must be BOUNDED BY THE SAME BAND THE
CONSUMER ENFORCES (tests/test_pd098_design_prompt_band.py).

THE DEFECT (measured on live run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4, not theorised). The three
upsell page-design phases were refused before any paid call:

    FATAL: sales design prompt FAILS the shared rich-prompt gate (SOP 9.10 step 5)
      - AF-P2: prompt is 58482 chars, over the hard ceiling of 18000

with `prompts/sales.design.txt` = 58,484 / `checkout.design.txt` = 49,526 /
`vsl.design.txt` = 51,334 chars against an 18,000 ceiling -- a 2.7x-3.2x
overshoot.

THE MECHANISM (this is what the guard has to pin). P-U-DESIGN-SALES /
-CHECKOUT / -VSL declare `fanout {by: slide, desired_count: 3}` but ONE
`produces_artifact` (`prompts/<page>.design.txt`), and their reducer is
`dispatcher._reduce_text_concat`, which CONCATENATES the admitted unit texts.
The consumer `build_infographic.resolve_design_prompt` reads that ONE file and
sends it VERBATIM as ONE prompt, gated at
`prompt_gate.PROMPT_CHAR_FLOOR .. PROMPT_CHAR_CEILING` on the AGGREGATE.

The producer knew none of it:

  * `ARTIFACT_CONTRACTS` has no `P-U-DESIGN-*` key, so `compose_prompt` fell
    through to `GENERIC_CONTRACT`, whose whole length rule is "real prose long
    enough to be substantive (not a one-line stub)" -- NO upper bound anywhere;
  * the owning role's SOP gives the 9,000-14,000 band PER PROMPT, so each of
    the three units spent it on itself;
  * the unit validator was `_validate_text` -- "non-empty is the mechanical
    floor" -- so all three over-budget units reported ok, the reducer wrote a
    58,484-char file, and the ceiling surfaced three phases later at the PAID
    render call.

Measured unit outputs on the live run: sales 20,917 + 20,024 + 17,537 = 58,478
(+4 separator chars = the 58,484-char file).

WHAT THESE TESTS PIN
  1. The authoring instruction the design unit actually receives STATES the
     band, and states it as a SHARED budget on the aggregate.
  2. The band numbers are IMPORTED from prompt_gate, not re-typed -- changing
     the gate's constants changes the producer's budget (so they cannot drift).
  3. The per-part shares SUM INTO the band for every part count: a phase whose
     units each pass their own validator cannot assemble an out-of-band file.
  4. The live defect shape (a ~20k part) FAILS ITS OWN cheap text validation
     instead of being discovered after the image call.
  5. End to end through `_dispatch_phase_fanout_units`, a compliant producer run
     lands inside the band and clears the REAL shared gate.
  6. The part count is the ADMITTED count, not the ENUMERATED one (the live run
     enumerated 8 deck slides and admitted 3; budgeting by 8 would drive the
     aggregate UNDER the floor).

NON-VACUOUSNESS: every assertion here is against the pre-fix code path --
reverting the functional change turns tests 1, 3, 4, 5 and 6 red (see the PR
body for the ablation counts). Nothing in this file is asserted against a
constant defined only by this file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import prompt_gate as PG  # noqa: E402
from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402


class FakePhase:
    """Phase-shaped stub -- these tests never load a manifest."""

    def __init__(self, pid: str, role: str):
        self.id = pid
        self.owning_role = role
        self.workers = 1
        self.budget_minutes = 5
        self.executor_kind = "agent"


# The live run's shape: 8 deck slides enumerated, `desired_count: 3` admitted.
N_SLIDES = 8
DESIRED = 3
LIVE_PART_LENGTHS = (20917, 20024, 17537)  # measured: sales.design.txt's 3 units

# The three phase ids, taken from PIPELINE-MANIFEST.json v69 (NOT from the
# fix's own dict) so these tests still COLLECT and FAIL against pre-fix code
# instead of erroring at import -- an ablation has to produce per-test
# failures to be worth anything.
DESIGN_PHASES = ("P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT", "P-U-DESIGN-VSL")


def _dept(tmp_path: Path, role: str) -> Path:
    dept = tmp_path / "dept"
    r = dept / role
    r.mkdir(parents=True)
    (r / "how-to.md").write_text("SOP: author rich image prompts.\n")
    return dept


def _design_run(tmp_path: Path, phase: str) -> Path:
    """A run dir with N_SLIDES slides -- enough that `desired_count` actually
    binds (the live run's 8-enumerated / 3-admitted shape)."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    (rd / "working" / "upsell" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(
        {"slots": [{"ordinal": n, "arc": "A"} for n in range(1, N_SLIDES + 1)]}))
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(
        {"slides": [{"ordinal": n} for n in range(1, N_SLIDES + 1)]}))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"client": "t"}))
    page = D.DESIGN_PAGE_PHASES[phase]
    (rd / "working" / "upsell" / "copy" / f"{page}.fragment.md").write_text(
        "# fragment\n\nreal upsell copy for the page design\n")
    return rd


def _unit_order(phase: str, ordinal: int, admitted: int, enumerated: int):
    """The work order a design unit is dispatched with (the dispatcher stamps
    `admitted_count` from wanted_items; `unit_count` is the enumerated count)."""
    return {
        "phase": phase,
        "owning_role": "slide-image-creator",
        "produces_artifact": [f"prompts/{D.DESIGN_PAGE_PHASES[phase]}.design.txt"],
        "_unit_scope": "",
        "_unit_payload": {
            "key": f"slide-{ordinal:02d}",
            "scope": "slide",
            "phase_id": phase,
            "ordinal": ordinal,
            "unit_count": enumerated,
            "admitted_count": admitted,
            "output_schema": "text: ONE page-design prompt for the scoped slide",
        },
    }


def _compose(phase: str, order, tmp_path: Path):
    dept = _dept(tmp_path, "slide-image-creator")
    rd = _design_run(tmp_path, phase)
    return D.compose_prompt(
        phase_id=phase, owning_role="slide-image-creator", dept_root=dept,
        run_dir=rd, order=order, attempt=1, prior_reasons=None)


# ---------------------------------------------------------------------------
# 1. The authoring instruction STATES the band, as a SHARED budget.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phase", DESIGN_PHASES)
def test_authoring_instruction_states_the_shared_band(phase, tmp_path):
    """The regression this defect needed: the model authoring the design prompt
    is TOLD the band the consumer will enforce, with the real numbers."""
    order = _unit_order(phase, ordinal=2, admitted=DESIRED, enumerated=N_SLIDES)
    _system, user = _compose(phase, order, tmp_path)
    contract = user.split("=== OUTPUT CONTRACT")[-1]

    assert f"{PG.PROMPT_CHAR_FLOOR:,}" in contract, (
        "the design unit's contract must state the shared FLOOR")
    assert f"{PG.PROMPT_CHAR_CEILING:,}" in contract, (
        "the design unit's contract must state the shared CEILING")

    floor_share, ceiling_share = D.design_unit_char_budget(DESIRED)
    assert f"{floor_share:,}" in contract and f"{ceiling_share:,}" in contract, (
        "the contract must state THIS unit's own share of the shared band")
    assert "SHARED" in contract and "ASSEMBLED FILE" in contract, (
        "the band must be stated as a budget on the AGGREGATE, not per prompt")
    assert f"PART 2 OF {DESIRED}" in user, (
        "the unit must be told it authors one PART of the one prompt")
    # The bandless fallback is exactly what let a 58k prompt be authored
    # against an 18k ceiling -- it must no longer be what this unit receives.
    assert D.GENERIC_CONTRACT not in user, (
        "the design phases must not fall through to the bandless GENERIC_CONTRACT")


def test_design_artifact_is_one_prompt_not_n_slide_prompts(tmp_path):
    """The scope instruction must say PART-of-ONE, not 'ONE UNIT ... for SLIDE
    N OF M': the live units each authored their own COMPLETE prompt for their
    own deck slide, which is how three prompts got concatenated into one."""
    payload = {"key": "slide-02", "scope": "slide", "phase_id": "P-U-DESIGN-SALES",
               "ordinal": 2, "unit_count": N_SLIDES, "admitted_count": DESIRED,
               "unit_kind": "text: ONE page-design prompt for the scoped slide"}
    scope_text = D._unit_scope_text(payload)
    assert scope_text is not None
    assert f"PART 2 OF {DESIRED}" in scope_text
    assert "ONE" in scope_text and "PAGE-DESIGN PROMPT" in scope_text
    assert "SLIDE 2 OF 8" not in scope_text


# ---------------------------------------------------------------------------
# 2. The numbers are IMPORTED from prompt_gate -- they cannot drift.
# ---------------------------------------------------------------------------
def test_budget_is_derived_from_prompt_gate_not_hardcoded(monkeypatch):
    """A second copy of 9,000/18,000 in the producer is exactly the drift this
    fix exists to prevent: move the gate's constants and the producer's budget
    must move with them."""
    monkeypatch.setattr(PG, "PROMPT_CHAR_FLOOR", 12000)
    monkeypatch.setattr(PG, "PROMPT_CHAR_CEILING", 24000)
    floor_share, ceiling_share = D.design_unit_char_budget(3)
    assert (floor_share, ceiling_share) == ((12000 - 4 + 2) // 3,
                                            (24000 - 4) // 3)
    assert ceiling_share > 5998, (
        "the budget followed a monkeypatched gate constant, so it is imported, "
        "not hard-coded")


# ---------------------------------------------------------------------------
# 3. The shares SUM INTO the band, for every part count.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("n", [1, 2, 3, 4, 8])
def test_part_shares_sum_into_the_band(n):
    """The property that makes the fix sufficient: if every part sits in its
    own share, the ASSEMBLED artifact cannot be out of band -- so the units can
    never again assemble a file the consumer must refuse."""
    floor_share, ceiling_share = D.design_unit_char_budget(n)
    sep_total = len(D._UNIT_TEXT_SEPARATOR) * (n - 1)
    agg_min = floor_share * n + sep_total
    agg_max = ceiling_share * n + sep_total
    assert PG.PROMPT_CHAR_FLOOR <= agg_min, (
        f"n={n}: all-parts-at-floor assembles to {agg_min}, under the "
        f"{PG.PROMPT_CHAR_FLOOR} floor")
    assert agg_max <= PG.PROMPT_CHAR_CEILING, (
        f"n={n}: all-parts-at-ceiling assembles to {agg_max}, over the "
        f"{PG.PROMPT_CHAR_CEILING} ceiling")


def test_reducer_separator_is_the_one_the_budget_charges_for():
    """`_reduce_text_concat` must join with the SAME separator the budget
    charges for, or units are budgeted against a different assembly."""
    ordered = [({}, "a" * 3000), ({}, "b" * 3000), ({}, "c" * 3000)]
    merged = D._reduce_text_concat(ordered)
    assert merged == D._UNIT_TEXT_SEPARATOR.join(["a" * 3000] * 1 +
                                                ["b" * 3000] + ["c" * 3000])
    _, ceiling_share = D.design_unit_char_budget(3)
    assert len(merged) <= ceiling_share * 3 + len(D._UNIT_TEXT_SEPARATOR) * 2
    assert len(merged) <= PG.PROMPT_CHAR_CEILING


# ---------------------------------------------------------------------------
# 4. The live defect shape fails its OWN cheap validation.
# ---------------------------------------------------------------------------
def test_live_defect_shape_fails_unit_validation():
    """The exact measured magnitude: a ~20k part, which is a perfectly good
    SINGLE prompt and therefore passed `_validate_text` -- and is 3.5x its
    share of the aggregate budget. It must fail HERE, not at the paid gate."""
    payload = {"phase_id": "P-U-DESIGN-SALES", "ordinal": 1,
               "unit_count": N_SLIDES, "admitted_count": DESIRED}
    for length in LIVE_PART_LENGTHS:
        ok, problems = D._validate_design_page_unit(payload, "x " * (length // 2))
        assert not ok, f"a {length}-char part must not validate"
        assert any("PD-TEST-098" in p and "AF-P2" in p for p in problems), problems


def test_in_share_part_validates_and_stub_fails():
    payload = {"phase_id": "P-U-DESIGN-SALES", "ordinal": 1,
               "unit_count": N_SLIDES, "admitted_count": DESIRED}
    floor_share, ceiling_share = D.design_unit_char_budget(DESIRED)

    ok, problems = D._validate_design_page_unit(
        payload, "y " * (floor_share // 2 + 200))
    assert ok, problems

    ok, problems = D._validate_design_page_unit(payload, "too short")
    assert not ok and any("AF-P1" in p for p in problems), problems

    ok, problems = D._validate_design_page_unit(
        payload, "z " * (ceiling_share // 2 + 50))
    assert not ok and any("AF-P2" in p for p in problems), problems


def test_every_design_phase_uses_the_band_validator():
    """The fix's own registry must cover exactly the manifest's three phases."""
    assert set(D.DESIGN_PAGE_PHASES) == set(DESIGN_PHASES)
    for phase in DESIGN_PHASES:
        assert D._UNIT_VALIDATORS[phase] is D._validate_design_page_unit


# ---------------------------------------------------------------------------
# 5. Cost of a compliant set of parts lands in band (the parts are achievable).
# ---------------------------------------------------------------------------
def _compliant_parts(n: int):
    """N parts, each inside its share, which TOGETHER clear the real gate:
    part 1 opens the prompt ([ARCHETYPE + palette + size + composition +
    spelling-lock), the middle continues it, the last closes it with the
    one DO-NOT BLOCK. Written as a fixture because the assertion below is
    about the BAND, not about model prose."""
    vocab = ("anchor cadence typographic kerning baseline ligature counters humanist "
             "geometric grotesque palette saturation vibrance clarity grain filmic "
             "anamorphic flare amber tungsten sconce rimlight bokeh aperture volumetric "
             "editorial luminous shadow specular skyline twilight metropolitan atrium "
             "leading negative breathing hierarchy rhythm tension balance contrast "
             "warmth texture depth focus gesture poise resolve candour momentum").split()
    def body(seed, room):
        """Fill `room` chars with distinct, non-repeating sentences -- sized by
        measuring, never by guessing, so no structural block is truncated."""
        out: list = []
        used = 0
        i = 0
        while used < room:
            sentence = (
                f"Note {seed}-{i}: the {vocab[(seed * 7 + i) % len(vocab)]} "
                f"treatment at station {i} carries its own lighting palette "
                f"placement and mood clause.")
            if used + len(sentence) + 1 > room:
                break
            out.append(sentence)
            used += len(sentence) + 1
            i += 1
        return " ".join(out)
    part_len = D.design_unit_char_budget(n)[1]
    head = ("[ARCHETYPE: split-hero editorial]\n"
            "Composition: rule of thirds grid, headline in the upper-third safe margin, "
            "focal point in the right third. Palette anchored on brand hex #0A2540 with "
            "accent #F2B134. Headline typography at 96pt bold, subhead 42pt.\n"
            'HEADLINE VERBATIM + SPELLING-LOCK: render this exact string '
            'letter-for-letter, spelled exactly: "One Request. One Package."\n')
    do_not = ("\n\nDO-NOT BLOCK:\n"
              "Do not render any misspelled or garbled text; render every quoted string letter-for-letter. "
              "Do not redraw, recolor, or reinterpret the logo or monogram. "
              "Do not include any placeholder, bracketed token, or TBD build note. "
              "Do not add presenter narration, stage direction, or webinar self-talk. "
              "Do not produce anatomical artifacts such as a fused hand or extra limb. "
              "Do not let a busy cluttered background compete behind any text zone. "
              "Do not lighten, ashen, or desaturate any deep skin tone. "
              "Do not add a watermark, emoji, clipart, Calibri or Arial default font.\n")
    parts = []
    for k in range(n):
        prefix = head if k == 0 else ""
        suffix = do_not if k == n - 1 else ""
        room = part_len - len(prefix) - len(suffix) - 2
        part = prefix + body(k + 1, room) + suffix
        assert len(part) <= part_len, "fixture part exceeded its share"
        assert (k != 0) or "[ARCHETYPE" in part
        assert (k != n - 1) or "DO-NOT BLOCK" in part
        parts.append(part)
    return parts


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_compliant_parts_assemble_into_a_gate_passing_artifact(n):
    """The producer's stated band must be ACHIEVABLE, and a compliant run must
    produce something the real consumer gate accepts -- otherwise the fix would
    just move the refusal."""
    parts = _compliant_parts(n)
    payload = {"phase_id": "P-U-DESIGN-SALES", "unit_count": n, "admitted_count": n}
    for i, part in enumerate(parts, start=1):
        payload["ordinal"] = i
        ok, problems = D._validate_design_page_unit(payload, part)
        assert ok, f"part {i}/{n} of the fixture failed its own share: {problems}"

    merged = D._reduce_text_concat([({}, p) for p in parts])
    assert PG.PROMPT_CHAR_FLOOR <= len(merged) <= PG.PROMPT_CHAR_CEILING, (
        f"n={n}: assembled {len(merged)} chars is outside the "
        f"{PG.PROMPT_CHAR_FLOOR}-{PG.PROMPT_CHAR_CEILING} band")
    assert PG.prompt_problems(merged, "One Request. One Package.") == [], (
        "a producer-compliant assembly must clear the REAL shared gate")


# ---------------------------------------------------------------------------
# 6. The part count is the ADMITTED count, not the ENUMERATED one.
# ---------------------------------------------------------------------------
def test_admitted_count_governs_not_enumerated_count():
    """The live run enumerated 8 deck slides and `desired_count: 3` admitted 3.
    Dividing the shared band by the ENUMERATED 8 would budget each part for an
    8-part assembly while only 3 are reduced -- driving the aggregate UNDER the
    floor. `admitted_count` must win."""
    assert D.design_part_count({"admitted_count": 3, "unit_count": 8}) == 3
    assert D.design_part_count({"unit_count": 8}) == 8       # fallback
    assert D.design_part_count({}) == 1                      # last resort

    floor_share, _ = D.design_unit_char_budget(
        D.design_part_count({"admitted_count": 3, "unit_count": 8}))
    agg_min = floor_share * 3 + 2 * (3 - 1)
    assert agg_min >= PG.PROMPT_CHAR_FLOOR, (
        "budgeting by the enumerated 8 would assemble under the floor")


def test_dispatcher_stamps_admitted_count_from_wanted_items(tmp_path, monkeypatch):
    """`admitted_count` is stamped by the admission pass, so a unit budgeted for
    a 4-part phase that admits 3 still assembles in band."""
    rd = _design_run(tmp_path, "P-U-DESIGN-SALES")
    dept = _dept(tmp_path, "slide-image-creator")
    seen: list = []

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        seen.append(user_prompt)
        idx = len(seen)
        parts = _compliant_parts(DESIRED)
        return (parts[idx - 1], {"request_id": "req-stub"},
                {"provider": "stub", "model": "stub-1"})

    monkeypatch.setattr(D, "dispatch_complete", fake_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    target = rd / "prompts" / "sales.design.txt"
    res = D._dispatch_phase_fanout_units(
        rd, {"owning_role": "slide-image-creator",
             "produces_artifact": ["prompts/sales.design.txt"]},
        dept_root=dept, phase_obj=FakePhase("P-U-DESIGN-SALES", "slide-image-creator"),
        worker_id="test",
        spec=fanout.parse_fanout_field(
            {"by": "slide", "desired_count": DESIRED, "batch_width": DESIRED}),
        patterns=["prompts/sales.design.txt"], target=target,
        prior_reasons=[])
    assert res.status == "ok", res.reasons
    assert len(seen) == DESIRED, "desired_count bounds the admitted parts"

    # THE ACCEPTANCE: the producer's own artifact is inside the band the
    # consumer enforces, and clears the real gate.
    artifact = target.read_text(encoding="utf-8").strip()
    assert PG.PROMPT_CHAR_FLOOR <= len(artifact) <= PG.PROMPT_CHAR_CEILING, (
        f"producer wrote {len(artifact)} chars -- outside the "
        f"{PG.PROMPT_CHAR_FLOOR}-{PG.PROMPT_CHAR_CEILING} band")
    assert PG.prompt_problems(artifact, "One Request. One Package.") == []
    for prompt in seen:
        assert "PART" in prompt and "SHARED" in prompt, (
            "every admitted unit must have been told its share of the band")


def test_pre_fix_shape_would_be_refused_by_the_gate():
    """NON-VACUITY anchor: the measured live shape, reassembled, is exactly what
    the consumer refuses -- so the assertions above are testing a real fix and
    not a tautology about this file's own fixture."""
    live = [({}, "x " * (n // 2)) for n in LIVE_PART_LENGTHS]
    merged = D._reduce_text_concat(live)
    problems = PG.prompt_problems(merged)
    assert any("AF-P2" in p and "over the hard ceiling" in p for p in problems), (
        "the live shape must still be refused by the gate")
