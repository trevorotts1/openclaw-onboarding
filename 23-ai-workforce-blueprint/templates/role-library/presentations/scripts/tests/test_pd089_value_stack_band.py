"""PD-089 — value-stack slides get their own copy band (AF-COPY-BAND).

THE DEFECT (PD-089, held by decision D-16). The August 20, 2026 ruling — the
AF-C8 ARCHETYPE CARVE-OUT proved by `test_af_c8_archetype_carveout.py` in this
same directory — allows a value-stack / offer-stack slide a 9-word headline,
an 18-word sub-copy and SIX line items of up to 7 words each (62 words total).
`build_deck._chk_copy_density` modelled only an ordinary teaching slide: 3
bullets, each 8-30 characters, 180 characters for the whole slide. So a
fully SOP-compliant offer stack — the doctrine's own numbers — was mechanically
guaranteed to FAIL AF-COPY-BAND, exactly the same class of contradiction the
carve-out fixed for the (now retired) AF-C8 word count.

THE RULING BUILT HERE. When the slide's arc tag text marks value-stack /
offer-stack, the bullet and slide-total bands widen; every other field and
every other slide is unchanged:

    value-stack / offer-stack slides ..... bullets <= 6, each 8-60 chars,
                                           slide total <= 420 chars
    every other slide ................... UNCHANGED (3 x 8-30, total 180)

WHAT THESE TESTS PIN (acceptance row A1)

  * the carve-out test's own fixture, laid out as a `slides.json` copy[] row,
    PASSES once its arc tag marks value-stack — the whole point of the unit;
  * the identical row with NO value-stack tag still FAILS — the wider band
    never leaks onto an ordinary slide;
  * all five spellings the ruling names are recognised, and `tally` is matched
    as a WORD so a tag such as `totally` cannot open the band by accident;
  * the wider band is still a BAND: a 7th bullet and a slide past 420 chars
    both fail on a tagged slide;
  * `_chk_copy_density` (preflight) and `_chk_copy_qc` (the report's own
    re-measure) resolve the band through ONE helper, so the two gates cannot
    drift apart the way the doctrine did.

The fixture is copied verbatim from `test_af_c8_archetype_carveout.py`'s
`test_compliant_value_stack_slide_passes` — headline 9 words, sub-copy 18
words, 6 line items — so this unit is pinned to the SAME numbers the doctrine
already enforces, and a later change to that fixture fails loudly rather than
silently disagreeing with the ruling.

No network, no credentials. Stdlib + pytest only.
"""

import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402

# --- the carve-out test's own fixture, verbatim -----------------------------
HEADLINE = "Here Is Everything Included In Your Complete Package Today"  # 9 words
SUBCOPY = (
    "This full stack gives you the exact tools training support "
    "and accountability you need to win right now"
)  # 18 words
ITEMS = [
    "Weekly Live Coaching Calls, $2000 value",
    "Private Community Access, $500 value today",
    "Done For You Templates, $1000 value",
    "Monthly Strategy Session, $750 value",
    "Bonus Swipe File Library, $300 value",
    "Lifetime Updates And Support, $1500 value",
]

VALUE_STACK_TAGS = ("value-stack", "value_stack", "offer-stack", "offer_stack", "tally")


def _copy_row(items=None):
    """copy[] positional semantics: 0 HEADLINE, 1 SUBHEAD, 2 KICKER (unused ->
    empty, which the gate skips), 3+ BULLETS."""
    return [HEADLINE, SUBCOPY, ""] + list(items if items is not None else ITEMS)


def _run_dir(tmp_path, tag, copy_row):
    """A run dir holding the slides.json the renderer reads plus an
    arc_allocation.json carrying the slide's own tag text."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps([{"slide": 1, "scene": "value stack", "copy": copy_row}]))
    (rd / "working" / "copy" / "arc_allocation.json").write_text(
        json.dumps({"slots": [{"slide": 1, "tag": tag}]}))
    return rd


def _report(slides=(1,)):
    return {
        "gate": "Phase 1Q",
        "average": 9.1,
        "triggered_autofails": [],
        "pass": True,
        "qc_independence": {"graded_by": "qc-specialist-presentations",
                            "independent": True, "builder": "slide-copywriter",
                            "self_graded": False},
        "per_slide_scores": [{"slide": s, "average": 9.0, "pass": True,
                              "notes": "clean"} for s in slides],
    }


# ---------------------------------------------------------------------------
# A1, first half — a tagged value-stack slide clears the gate.
# ---------------------------------------------------------------------------
def test_tagged_value_stack_slide_passes(tmp_path):
    """The carve-out fixture is legal copy on a value-stack slide."""
    rd = _run_dir(tmp_path, "value-stack", _copy_row())
    assert bd._chk_copy_density(rd) == "", "value-stack copy must clear AF-COPY-BAND"


@pytest.mark.parametrize("tag", VALUE_STACK_TAGS)
def test_every_ruling_spelling_opens_the_band(tmp_path, tag):
    """All five spellings the ruling names mark a value-stack slide."""
    assert bd._is_value_stack_slide(tag.lower()) is True
    rd = _run_dir(tmp_path, tag, _copy_row())
    assert bd._chk_copy_density(rd) == "", f"{tag} must be recognised"


def test_tag_inside_a_longer_section_label_still_matches(tmp_path):
    rd = _run_dir(tmp_path, "the offer-stack section", _copy_row())
    assert bd._chk_copy_density(rd) == ""


# ---------------------------------------------------------------------------
# A1, second half — the same row with no value-stack tag still fails.
# ---------------------------------------------------------------------------
def test_untagged_identical_slide_fails(tmp_path):
    """The wider band never leaks onto an ordinary teaching slide."""
    rd = _run_dir(tmp_path, "teaching-point", _copy_row())
    reason = bd._chk_copy_density(rd)
    assert reason, "the same 6-bullet row must FAIL without the value-stack tag"
    assert "AF-COPY-BAND" in reason
    assert "6 bullets" in reason and "3-bullet max" in reason, reason


@pytest.mark.parametrize("tag", ("", "totally", "value-add", "stack"))
def test_near_miss_tags_do_not_open_the_band(tmp_path, tag):
    """`tally` is a WORD marker: `totally` must not open the band, and neither
    may a tag that only says `value` or `stack` on its own."""
    rd = _run_dir(tmp_path, tag, _copy_row())
    assert bd._chk_copy_density(rd), f"tag {tag!r} must NOT be treated as value-stack"


# ---------------------------------------------------------------------------
# The wider band is still a band.
# ---------------------------------------------------------------------------
def test_seventh_bullet_fails_on_a_tagged_slide(tmp_path):
    rd = _run_dir(tmp_path, "value-stack", _copy_row(ITEMS + ["Fast Start Guide"]))
    reason = bd._chk_copy_density(rd)
    assert "7 bullets" in reason and "6-bullet max" in reason, reason


def test_slide_over_420_chars_fails_on_a_tagged_slide(tmp_path):
    long_items = []
    for i in range(1, 7):
        base = f"Line item {i}: "
        long_items.append(base + "x" * (60 - len(base)))  # exactly 60, inside the band
    rd = _run_dir(tmp_path, "value-stack", _copy_row(long_items))
    reason = bd._chk_copy_density(rd)
    assert "SLIDE TOTAL" in reason and "40-420" in reason, reason


# ---------------------------------------------------------------------------
# One band, two gates — the preflight check and the QC report's re-measure
# must never disagree (the drift PD-089 exists to stop).
# ---------------------------------------------------------------------------
def test_qc_teeth_accept_the_same_value_stack_copy(tmp_path):
    rd = _run_dir(tmp_path, "value-stack", _copy_row())
    (rd / "working" / "qc").mkdir(parents=True)
    report = rd / "working" / "qc" / "copy_qc_report.json"
    report.write_text(json.dumps(_report()))
    assert bd._chk_copy_qc(report) == "", (
        "a genuine copy-QC report over value-stack copy must not be called a "
        "fabricated pass by the re-measure")
    # ... and the identical copy on an untagged slide is still a contradiction.
    rd2 = _run_dir(tmp_path / "untagged", "teaching-point", _copy_row())
    (rd2 / "working" / "qc").mkdir(parents=True)
    report2 = rd2 / "working" / "qc" / "copy_qc_report.json"
    report2.write_text(json.dumps(_report()))
    assert "AF-COPY-QC" in bd._chk_copy_qc(report2)


def test_both_gates_resolve_the_same_band_helper():
    """Guards against a future edit hardcoding one gate's numbers again."""
    vs = bd._copy_bands_for("value-stack")
    assert (vs["bullet_max"], vs["bullet_floor"], vs["bullet_ceiling"],
            vs["total_ceiling"]) == (6, 8, 60, 420)
    plain = bd._copy_bands_for("teaching-point")
    assert (plain["bullet_max"], plain["bullet_floor"], plain["bullet_ceiling"],
            plain["total_ceiling"]) == (3, 8, 30, 180)
