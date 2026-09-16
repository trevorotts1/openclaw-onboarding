"""PD-TEST-194 -- PD-TEST-135's re-open path was INERT on the park it was written for.

THE DEFECT, MEASURED ON THE LIVE RUN (pres-operator-1d269693, P4-PROMPT).

PD-TEST-135 added `_block_is_verifier_sourced` so that a phase parked by the
engine's own SUBSTANCE check could be re-entered by a later resume -- "so the
repaired checker actually reaches it". On the live run BOTH of its gates passed
and it still returned False:

  * the reason DOES begin with the checker's prefix ("substance check failed: ...");
  * the newest heal event IS a `verifier_substance` event;
  * there is NO dispatcher park marker.

It failed on the last line, the episode match, because that match compares the
blocked_reason against the heal event's reason as TEXT:

    blocked_reason : ... slide-1: AF-WORLD-SCALE -- ; ... AF-FACE-PROMPT-MISSING ...
    heal ev_reason : ... slide-1: AF-FACE-PROMPT-MISSING -- ; ... AF-P-DENSITY ...

Neither `reason.startswith(ev_reason)` nor `ev_reason[:60] in reason` can hold:
the two lists differ in BOTH order and membership (AF-WORLD-SCALE appears only in
the block; AF-P-DENSITY appears only in the heal event). The consequence was
exactly the defect PD-TEST-135 claims to fix -- the park could not be re-entered
on ANY resume, so its descendants stayed withheld and the run re-parked
identically forever, even with the repaired checker installed.

WHY IT IS NOT A FREAK. PD-TEST-190 measured that this checker's omissions are
NON-DETERMINISTIC -- which required token family is missing varies per draw -- so
the verdict's head and tail both move between two attempts of the SAME episode.
A text-prefix episode test therefore cannot survive the checker it is testing.

THE FIX tests the one thing that IS invariant: the IDENTITY of the failing
checks, as a SET, not their order or the prose between them.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import phases as P  # noqa: E402

PREFIX = "substance check failed"


def _park(blocked_reason, heal_reason=None, *, cls="verifier_substance",
          extra_events=()):
    events = list(extra_events)
    if heal_reason is not None:
        events.append({"at": "2026-09-16T17:46:31-04:00", "rung": 2, "attempt": 1,
                       "class": cls, "reason": heal_reason})
    return {"id": "P4-PROMPT", "status": "blocked",
            "blocked_reason": blocked_reason, "heal_events": events}


# The live P4-PROMPT pair, taken VERBATIM from the run's own state.json (F4,
# independent review: the earlier fixture was a 4-item paraphrase, not the real
# 10-item verdicts). Captured literally so the pinned property is faithful.
LIVE_BLOCK = 'substance check failed: AF-PROMPT-FLOOR slide-1: AF-WORLD-SCALE — ; AF-PROMPT-FLOOR slide-1: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-1: AF-LIGHT-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-1: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-4: AF-LIGHT-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-4: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-6: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-6: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-8: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-8: AF-HAIR-INAUTHENTIC — . An owner_skip_approval token for this phase is required to advance it to done.'
LIVE_HEAL = 'substance check failed: AF-PROMPT-FLOOR slide-1: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-1: AF-LIGHT-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-1: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-4: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-4: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-4: AF-P-DENSITY — ; AF-PROMPT-FLOOR slide-6: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-6: AF-HAIR-INAUTHENTIC — ; AF-PROMPT-FLOOR slide-8: AF-FACE-PROMPT-MISSING — ; AF-PROMPT-FLOOR slide-8: AF-HAIR-INAUTHENTIC — .'


def test_the_live_reordered_verdict_is_an_episode_match():
    """THE REGRESSION. This exact shape returned False before the fix."""
    ps = _park(LIVE_BLOCK, LIVE_HEAL)
    # Guard the premises, so this test cannot pass for the wrong reason: both of
    # the ORIGINAL gates must still hold, and the old text test must still fail.
    assert LIVE_BLOCK.lower().startswith(P._VERIFIER_VERDICT_PREFIX)
    assert ps["heal_events"][-1]["class"] == "verifier_substance"
    assert not LIVE_BLOCK.startswith(LIVE_HEAL), "the old startswith test must fail"
    assert LIVE_HEAL[:60] not in LIVE_BLOCK, "the old 60-char test must fail"
    assert P._block_is_verifier_sourced(ps), (
        "the live reordered verdict is still misclassified as an operator park, so "
        "PD-TEST-135's re-open path cannot fire and the phase can never be "
        "re-entered on any resume -- the exact defect it was written to fix")


def test_a_single_shared_AUTOFAIL_is_enough():
    """One genuinely-shared autofail identifies the episode.

    NOTE: the LABEL does not count -- see
    `test_the_check_LABEL_alone_is_not_an_episode_match`. This test previously
    shared only `AF-PROMPT-FLOOR`, which F1 (independent review) measured to be a
    tautology, since every line that checker emits carries it.
    """
    ps = _park(f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-HAIR-INAUTHENTIC \u2014 ; ",
               f"{PREFIX}: AF-PROMPT-FLOOR slide-2: AF-HAIR-INAUTHENTIC \u2014 ; ")
    assert P._verdict_check_ids(ps["blocked_reason"]) == {"AF-HAIR-INAUTHENTIC"}
    assert P._block_is_verifier_sourced(ps)


def test_identical_verdicts_still_match():
    """The pre-existing behaviour must not regress."""
    same = f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-P-DENSITY \u2014 ; "
    assert P._block_is_verifier_sourced(_park(same, same))


def test_operator_prose_is_still_never_verifier_sourced():
    """THE PROTECTION THE DOCSTRING RELIES ON.

    `_READMITTABLE_PHASE_STATUSES` states owner-decision parks are never
    re-admitted. The verdict PREFIX is what separates engine text from operator
    prose, and the widening must not weaken it. Note the owner park below SHARES
    an autofail id with the heal event -- so if the fix had skipped the prefix
    gate, this would wrongly reopen. It does not.
    """
    owner = "An owner_skip_approval token for this phase is required to advance it to done."
    ps = _park(owner, f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-P-DENSITY \u2014 ; ")
    assert not P._block_is_verifier_sourced(ps)
    # ...even when the operator prose quotes autofails verbatim.
    quoting = "Owner decision needed: AF-PROMPT-FLOOR and AF-P-DENSITY are outstanding."
    assert not P._block_is_verifier_sourced(
        _park(quoting, f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-P-DENSITY \u2014 ; "))


def test_a_stale_verifier_heal_cannot_reopen_a_later_budget_park():
    """The other protection the docstring names, kept intact.

    A dispatcher BUDGET park does not carry the checker's prefix, so it is
    rejected at the first gate however old or verifier-sourced the heal history is.
    """
    budget = ("dispatcher paid retry budget: paid retry budget exhausted after 11 "
              "of the declared bounded total 11 provider attempts")
    assert not P._block_is_verifier_sourced(_park(budget, LIVE_HEAL))


def test_no_heal_events_or_a_non_verifier_heal_is_not_verifier_sourced():
    assert not P._block_is_verifier_sourced(_park(LIVE_BLOCK, None))
    # A heal whose REASON is not a verdict is rejected whatever its class says.
    assert not P._block_is_verifier_sourced(
        _park(LIVE_BLOCK, "dispatcher retry ceiling: 8 identical error outcomes",
              cls="dispatcher_budget"))
    # NOTE (F2): a heal carrying class="dispatcher_budget" but a VERDICT-SHAPED
    # reason IS now accepted -- the class is derived from the reason by keyword,
    # so the reason is the structural fact and the label is the inference. That
    # is the change F2 makes, and it is asserted in
    # `test_a_substance_verdict_that_mentions_the_TRANSPORT_is_still_reopenable`.


def test_check_id_extraction_ignores_prose_and_order():
    a = P._verdict_check_ids(LIVE_BLOCK)
    b = P._verdict_check_ids(LIVE_HEAL)
    assert "AF-WORLD-SCALE" in a and "AF-WORLD-SCALE" not in b
    assert "AF-P-DENSITY" in b and "AF-P-DENSITY" not in a
    assert P._verdict_check_ids("") == set()
    assert P._verdict_check_ids(None) == set()


def test_the_generic_label_widening_was_REMOVED_by_F1():
    """Supersedes the widening disclosed in cf7fc37e6.

    That commit honestly disclosed that two verdicts sharing ONLY the generic
    check label now matched (BASE False -> True). Independent review then
    measured that the label is hard-coded on every line the checker emits, which
    makes that match a tautology, so F1 removed it: the autofails are extracted
    from after `slide-<n>:`. The disclosure is kept as history; the behaviour it
    described is now asserted gone.
    """
    ps = _park(f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-HAIR-INAUTHENTIC \u2014 ; ",
               f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-P-DENSITY \u2014 ; ")
    shared = (P._verdict_check_ids(ps["blocked_reason"])
              & P._verdict_check_ids(ps["heal_events"][-1]["reason"]))
    assert shared == set(), f"the label is still carrying a match: {shared}"
    assert not P._block_is_verifier_sourced(ps)


def test_a_degenerate_empty_verdict_is_PRE_EXISTING_not_introduced_here():
    """True at BASE too -- pinned so a future reader does not blame this change.

    `"substance check failed: "` matches itself via the ORIGINAL
    `reason.startswith(ev_reason)` path, which this fix preserves.
    """
    assert P._block_is_verifier_sourced(_park(f"{PREFIX}: ", f"{PREFIX}: "))


def test_the_check_LABEL_alone_is_not_an_episode_match():
    """F1 (independent review): the intersection must not be a tautology.

    `phase_verifiers` hard-codes the literal label `AF-PROMPT-FLOOR` on EVERY
    line that checker emits, so intersecting all `AF-` tokens matched two draws
    with wholly disjoint autofails. Measured before this fix: `True`. The
    autofails are extracted from after `slide-<n>:` precisely so the constant
    label cannot carry the match on its own.
    """
    ps = _park(f"{PREFIX}: AF-PROMPT-FLOOR slide-1: AF-AAA \u2014 ; ",
               f"{PREFIX}: AF-PROMPT-FLOOR slide-9: AF-ZZZ \u2014 ; ")
    a = P._verdict_check_ids(ps["blocked_reason"])
    b = P._verdict_check_ids(ps["heal_events"][-1]["reason"])
    assert a == {"AF-AAA"} and b == {"AF-ZZZ"}, (a, b)
    assert not (a & b)
    assert not P._block_is_verifier_sourced(ps), (
        "the constant check label alone reopened the park -- the intersection is "
        "a tautology again")


def test_the_real_verdicts_still_match_on_THREE_real_autofails():
    """The fix must not depend on the label -- it does not."""
    shared = (P._verdict_check_ids(LIVE_BLOCK)
              & P._verdict_check_ids(LIVE_HEAL))
    assert shared == {"AF-FACE-PROMPT-MISSING", "AF-LIGHT-PROMPT-MISSING",
                      "AF-HAIR-INAUTHENTIC"}, shared
    assert "AF-PROMPT-FLOOR" not in shared, "the label leaked back into the match"
    assert "AF-WORLD-SCALE" not in shared and "AF-P-DENSITY" not in shared
    assert P._block_is_verifier_sourced(_park(LIVE_BLOCK, LIVE_HEAL))


def test_a_substance_verdict_that_mentions_the_TRANSPORT_is_still_reopenable():
    """F2 (independent review): the heal `class` is DERIVED, not authoritative.

    phases.py writes it as `heal.classify_failure(sub_reason)`, and
    `_PROVIDER_ERROR_MARKERS` matches bare words -- "provider", "timeout",
    "connection", "quota", "429" -- so a genuine substance verdict that merely
    mentions the transport was labelled `provider_error` and gate (b) rejected
    it. Measured before this fix: `False`; a measurable class of substance parks
    was permanently unreopenable.
    """
    ps = _park(f"{PREFIX}: AF-IMAGE-GROUNDING: the image provider returned 429 "
               f"rate limit for slide-3.",
               f"{PREFIX}: AF-IMAGE-GROUNDING slide-3: AF-IMAGE-GROUNDING \u2014 "
               f"provider 429", cls="provider_error")
    assert not ps["blocked_reason"].lower().startswith("dispatcher")
    assert P._block_is_verifier_sourced(ps)


def test_the_widened_heal_gate_still_rejects_a_non_verifier_heal():
    """The F2 widening must not accept a heal whose REASON is not a verdict."""
    ps = _park(f"{PREFIX}: AF-A \u2014 ; ", "dispatcher budget park AF-A",
               cls="dispatcher_budget")
    assert not P._block_is_verifier_sourced(ps)
