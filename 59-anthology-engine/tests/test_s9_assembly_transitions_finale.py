#!/usr/bin/env python3
"""test_s9_assembly_transitions_finale.py -- U9 provers for S9 assembly.

Two provers over the COMPILED anthology manuscript, both hermetic (every LLM call
is MOCKED; no network, no live model, no ledger writes beyond in-memory fakes):

  PROVER (a) prove_transitions -- the compiled edition carries EXACTLY N-1
    inter-chapter transitions; each seam names the NEXT chapter's LOCKED title;
    zero em-dashes across the bridges; each bridge is 150-300 words; and a
    byte-diff proves every frozen chapter body is unchanged by the insertions.

  PROVER (b) prove_finale -- the compiled edition carries EXACTLY ONE brand-new
    Grand Finale with its OWN title, referencing every included chapter at least
    once, ending with an action-steps section, holding the 14-point floor, and
    carrying zero em-dashes.

The build path is exercised end-to-end: write_transitions (ae-05) + write_finale
(ae-06) run against a FAKE router, compile_manuscript interleaves them into the
frozen chapters, and the two provers grade the real compiled bytes. Negative
tests prove each prover CATCHES its failure mode (wrong count, missing title
reference, an em-dash, an edited frozen chapter, a missing finale chapter
reference, a missing action-steps section, a sub-14pt font).

Run: python3 -m pytest 59-anthology-engine/tests/test_s9_assembly_transitions_finale.py -q
 or: python3 59-anthology-engine/tests/test_s9_assembly_transitions_finale.py
"""
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stage_s9_assembly_logic as logic  # noqa: E402

ORDER = ["cA::x", "cB::x", "cC::x"]
TITLES = {"cA::x": "Rise", "cB::x": "Fall Forward", "cC::x": "Begin Again"}
META = [
    {"participant_key": "cA::x", "chapter_title": "Rise", "contributor_name": "Ada",
     "one_line_summary": "a first climb", "word_count": 3000, "tone": "warm"},
    {"participant_key": "cB::x", "chapter_title": "Fall Forward", "contributor_name": "Ben",
     "one_line_summary": "a stumble that teaches", "word_count": 2100, "tone": "wry"},
    {"participant_key": "cC::x", "chapter_title": "Begin Again", "contributor_name": "Cyd",
     "one_line_summary": "a fresh start", "word_count": 2600, "tone": "hopeful"},
]
BODIES = {"cA::x": b"# Rise\n\nbody A\n", "cB::x": b"# Fall\n\nbody B\n",
          "cC::x": b"# Begin\n\nbody C\n"}
FROZEN = {k: logic.sha256_hex(v) for k, v in BODIES.items()}


def _bridge(next_title, target=210):
    """A deterministic in-band (150-300 word) editor bridge that names
    `next_title` verbatim and carries zero em-dashes -- an ae-05 reply body."""
    words = "We pause here at the seam between two finished voices.".split()
    words += ("The chapter that follows is titled %s and it carries the theme "
              "onward with fresh conviction and open hands." % next_title).split()
    while len(words) < target:
        words += "The reader turns the page with intention and a steady open heart.".split()
    return " ".join(words[:target]) + "."


def _finale_body():
    lines = ["This collection gathered every voice into one arc of resilience and hope."]
    for k in ORDER:
        lines.append("In %s, the reader meets a turning point that echoes the whole theme."
                     % TITLES[k])
    lines += ["", "## Where Do You Go From Here", "",
              "1. Begin the practice today, in one small way.",
              "2. Share your own story with a single person who needs it.",
              "3. Return to these pages whenever the road turns."]
    return "\n".join(lines)


def _fake_router(tier, messages, context, run_dir=None, model_map_path=None):
    """One fake for both ae-05 (per seam) and ae-06 (the finale)."""
    assert tier == logic.TIER_HEAVY
    step = context["step"]
    if step.startswith("s9_transition_"):
        seam = int(step.rsplit("_", 1)[1])          # seam k names order[k]
        to_title = TITLES[ORDER[seam]]
        return {"text": "<!-- TRANSITION -->\n%s\n<!-- END TRANSITION -->" % _bridge(to_title),
                "model_used": "glm-x", "tier": tier, "provider": "p", "usage": {}}
    if step == "s9_grand_finale":
        return {"text": json.dumps({"finale_title": "The Bridge We Built Together",
                                    "finale_markdown": _finale_body()}),
                "model_used": "glm-x", "tier": tier, "provider": "p", "usage": {}}
    raise AssertionError("unexpected step %r" % step)


def _writer(subcmd_args):
    if subcmd_args and subcmd_args[0] == "assembly-advance":
        return (0, {"assembly_state": "compiled"}, "")
    return (0, {}, "")


def _engine(router=_fake_router):
    eng = logic.S9Assembly("anthU9", db=":memory:", router=router, state_writer=_writer,
                           chapter_source=lambda mk: (BODIES[mk], FROZEN[mk]),
                           longctx_available=False)
    eng._anth_cache = {"name": "The Collection", "theme": "resilience", "min_chapters": 2}
    return eng


def _compile():
    """Drive the whole build once and return the compiled manuscript string."""
    eng = _engine()
    transitions = eng.write_transitions(ORDER, META)
    finale = eng.write_finale(ORDER, META, producer_display_name="P")
    out = eng.compile_manuscript(ORDER, FROZEN, "FRONT MATTER", "# Introduction\n\nintro",
                                 {k: "bio %s" % TITLES[k] for k in ORDER}, "BACK MATTER",
                                 transitions=transitions, finale=finale)
    return out["manuscript"], out, transitions, finale


# --------------------------------------------------------------------------- #
# PROVER (a): inter-chapter transitions
# --------------------------------------------------------------------------- #
def test_compile_carries_exactly_n_minus_1_transitions_and_one_finale():
    ms, out, _t, _f = _compile()
    assert out["transition_count"] == len(ORDER) - 1 == 2
    assert out["finale_present"] is True
    assert len(logic.extract_transition_blocks(ms)) == 2
    assert logic.extract_finale_block(ms) is not None


def test_prove_transitions_passes_on_clean_compile():
    ms, _o, _t, _f = _compile()
    rep = logic.prove_transitions(ms, ORDER, TITLES, frozen_bodies=BODIES)
    assert rep["ok"], rep["issues"]
    assert rep["transition_count"] == 2 and rep["expected"] == 2
    assert rep["total_em_dashes"] == 0
    assert rep["frozen_unchanged"] is True
    # each seam names the NEXT locked title
    assert rep["seams"][0]["next_title"] == "Fall Forward"
    assert rep["seams"][1]["next_title"] == "Begin Again"
    assert all(s["references_next_title"] for s in rep["seams"])


def test_frozen_chapters_are_byte_identical_in_compiled_manuscript():
    ms, _o, _t, _f = _compile()
    for key, body in BODIES.items():
        assert body.decode("utf-8") in ms, "frozen chapter %s not verbatim" % key


def test_prove_transitions_catches_wrong_count():
    ms, _o, _t, _f = _compile()
    dropped = logic._TRANSITION_BLOCK_RE.sub("", ms, count=1)  # remove one seam
    rep = logic.prove_transitions(dropped, ORDER, TITLES)
    assert not rep["ok"] and rep["transition_count"] == 1 and rep["expected"] == 2


def test_prove_transitions_catches_missing_next_title():
    ms, _o, _t, _f = _compile()
    broken = ms.replace("Begin Again", "A Different Title")
    rep = logic.prove_transitions(broken, ORDER, TITLES, frozen_bodies=BODIES)
    assert not rep["ok"]
    assert any("does not name the next locked title" in i for i in rep["issues"])


def test_prove_transitions_catches_em_dash():
    ms, _o, _t, _f = _compile()
    injected = ms.replace("We pause here at the seam", "We pause here — at the seam", 1)
    rep = logic.prove_transitions(injected, ORDER, TITLES)
    assert rep["total_em_dashes"] > 0 and not rep["ok"]


def test_prove_transitions_byte_diff_catches_edited_frozen_chapter():
    ms, _o, _t, _f = _compile()
    tampered = ms.replace("body B", "body B EDITED")
    rep = logic.prove_transitions(tampered, ORDER, TITLES, frozen_bodies=BODIES)
    assert rep["frozen_unchanged"] is False and not rep["ok"]


# --------------------------------------------------------------------------- #
# PROVER (b): the brand-new Grand Finale
# --------------------------------------------------------------------------- #
def test_prove_finale_passes_on_clean_compile():
    ms, _o, _t, _f = _compile()
    rep = logic.prove_finale(ms, TITLES, order=ORDER)
    assert rep["ok"], rep["issues"]
    assert rep["present"] and rep["finale_title"] == "The Bridge We Built Together"
    assert rep["chapters_referenced"] == 3 and not rep["missing_references"]
    assert rep["action_steps_present"] and rep["em_dashes"] == 0 and rep["font_floor_ok"]


def test_finale_has_its_own_title_distinct_from_the_concept():
    _ms, _o, _t, finale = _compile()
    assert finale["finale_title"] and finale["finale_title"] != "The Grand Finale"


def test_prove_finale_catches_missing_chapter_reference():
    ms, _o, _t, _f = _compile()
    stripped = ms.replace(
        "In Begin Again, the reader meets a turning point that echoes the whole theme.", "")
    rep = logic.prove_finale(stripped, TITLES, order=ORDER)
    assert not rep["ok"] and "cC::x" in rep["missing_references"]


def test_prove_finale_catches_missing_action_steps():
    ms, _o, _t, _f = _compile()
    no_steps = ms.replace("## Where Do You Go From Here", "## Some Other Heading")
    rep = logic.prove_finale(no_steps, TITLES, order=ORDER)
    assert not rep["action_steps_present"] and not rep["ok"]


def test_prove_finale_catches_em_dash():
    ms, _o, _t, _f = _compile()
    injected = ms.replace("one arc of resilience", "one arc — of resilience")
    rep = logic.prove_finale(injected, TITLES, order=ORDER)
    assert rep["em_dashes"] > 0 and not rep["ok"]


def test_prove_finale_catches_sub_14pt_font():
    ms, _o, _t, _f = _compile()
    shrunk = ms.replace("1. Begin the practice today, in one small way.",
                        "<span style=\"font-size: 11pt\">1. Begin the practice today.</span>")
    rep = logic.prove_finale(shrunk, TITLES, order=ORDER)
    assert not rep["font_floor_ok"] and not rep["ok"]


def test_prove_finale_catches_absent_finale():
    rep = logic.prove_finale("a manuscript with no finale block", TITLES, order=ORDER)
    assert not rep["present"] and not rep["ok"]


# --------------------------------------------------------------------------- #
# Fail-closed writers + ordering cockpit (U9c)
# --------------------------------------------------------------------------- #
def test_write_transitions_fail_closed_when_next_title_unlocked():
    eng = _engine()
    try:
        eng.write_transitions(ORDER, [{"participant_key": "cA::x", "chapter_title": "Rise"},
                                      {"participant_key": "cB::x"},  # no locked title
                                      {"participant_key": "cC::x", "chapter_title": "Begin Again"}])
        raise AssertionError("expected TransitionInvalid")
    except logic.TransitionInvalid:
        pass


def test_write_finale_fail_closed_when_reply_drops_a_chapter():
    def bad(tier, messages, context, run_dir=None, model_map_path=None):
        return {"text": json.dumps({"finale_title": "T",
                                    "finale_markdown": "Only Rise named.\n\n"
                                    "## Where Do You Go From Here\n\n1. Go."}),
                "model_used": "m", "tier": tier, "provider": "p", "usage": {}}
    eng = _engine(router=bad)
    try:
        eng.write_finale(ORDER, META)
        raise AssertionError("expected FinaleInvalid")
    except logic.FinaleInvalid:
        pass


def test_ordering_cockpit_view_exposes_order_and_per_slot_rationale():
    view = logic.build_ordering_view(
        ORDER,
        [{"position": 1, "participant_key": "cA::x", "reason": "strong opener"},
         {"position": 2, "participant_key": "cB::x", "reason": "tonal reset"},
         {"position": 3, "participant_key": "cC::x", "reason": "resonant close"}],
        "opener/closer with a wry middle", META)
    assert view["order"] == ORDER
    assert [s["position"] for s in view["slots"]] == [1, 2, 3]
    assert view["slots"][0]["chapter_title"] == "Rise"
    assert view["slots"][0]["rationale"] == "strong opener"
    assert view["slots"][2]["rationale"] == "resonant close"
    assert all(s["rationale"] for s in view["slots"]), "every slot carries a one-line rationale"
    assert view["overall_rationale"] == "opener/closer with a wry middle"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_s9_assembly_transitions_finale: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
