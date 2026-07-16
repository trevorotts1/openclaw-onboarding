#!/usr/bin/env python3
"""Unit tests for shared-utils/fab_qc.py — the FAB-QC funnel/automation build-quality gate.

Locks down the six library-aware dimensions and the >=8.5 + hard-miss verdict the audit
asked for: a faithful build passes; a thin/placeholder build fails naming D2; a build that
force-copied a template over an EXPLICIT user spec fails naming D5; a funnel that silently
dropped its linked_automations fails naming D6; a missing-persona build trips fail-closed D4.

Run:
    python3 tests/unit/fab-qc.test.py
    or: pytest tests/unit/fab-qc.test.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"
sys.path.insert(0, str(_SHARED_UTILS))

_spec = importlib.util.spec_from_file_location("fab_qc", _SHARED_UTILS / "fab_qc.py")
fab_qc = importlib.util.module_from_spec(_spec)
sys.modules["fab_qc"] = fab_qc          # required so @dataclass can resolve cls.__module__
_spec.loader.exec_module(fab_qc)


def _faithful_funnel() -> dict:
    return {
        "kind": "funnel",
        "match_decision": {
            "flex_decision": "USE_TEMPLATE", "intent_mode": "HANDS_OFF_DO_IT_ALL",
            "funnel_template_id": "squeeze-page", "matched_template_id": "squeeze-page",
            "linked_automations": {"automations": [{"automation_id": "soap-opera-sequence"}]},
        },
        "template": {
            "pageStructure": [{"page": "optin", "blocks": ["hero", "form"]},
                              {"page": "thankyou", "blocks": ["cta"]}],
            "copyFramework": {"primaryPersona": "Russell Brunson"},
            "books": ["DotCom Secrets"],
        },
        "artifact": {"pages": [
            {"page_id": "p1", "copy": {
                "hero": ("Get our free funnel swipe file today and finally grow the email list "
                         "you have put off building for months. Inside you get the exact opt-in "
                         "page, the seven-email follow-up sequence, and the pre-launch checklist "
                         "we use to ship a converting funnel in a single focused afternoon, with "
                         "no guesswork and nothing left to chance for a busy founder."),
                "form": "Enter your best email for instant access"}},
            {"page_id": "p2", "copy": {"cta": "Check your inbox for the link"}}]},
        "verify": {"overall_pass": True, "pages": [{"status": 200, "marker_present": True},
                                                   {"status": 200, "marker_present": True}]},
        "persona_log": "selected_persona: russell-brunson-the-funnel-hackers-cookbook\nrationale: page flow",
        "link_map": {"links": [{"funnel_template_id": "squeeze-page",
                                "primary_followup": {"automation_id": "soap-opera-sequence"}}]},
    }


class TestFabQc(unittest.TestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(sum(fab_qc.W.values()), 100)
        self.assertEqual(fab_qc.THRESHOLD, 8.5)

    def test_faithful_build_passes(self):
        r = fab_qc.grade(_faithful_funnel())
        self.assertTrue(r["passed"], r)
        self.assertGreaterEqual(r["score"], 8.5)
        self.assertEqual(r["hard_misses"], [])

    def test_thin_placeholder_copy_fails_naming_d2(self):
        inp = _faithful_funnel()
        inp["artifact"] = {"pages": [{"copy": {"hero": "[HEADLINE]", "form": "TODO"}},
                                     {"copy": {"cta": "Lorem ipsum dolor"}}]}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D2 Copy substance", r["hard_misses"])

    def test_thin_body_slot_below_floor_is_hard_miss_d2(self):
        # FIX-XC-04a: a body slot under the 40-word floor (no placeholder) HARD-MISSES D2.
        inp = _faithful_funnel()
        inp["artifact"] = {"pages": [
            {"copy": {"hero": "Grow your list fast with our free funnel swipe file today"}},
            {"copy": {"cta": "Check your inbox"}}]}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D2 Copy substance", r["hard_misses"])

    def test_page_lengthclass_floor_below_short_form_is_hard_miss_d2(self):
        # FIX-XC-04a: total page copy under the template lengthClass floor HARD-MISSES D2.
        inp = _faithful_funnel()
        inp["template"]["lengthClass"] = "short-form"   # >= 350 stripped words required
        r = fab_qc.grade(inp)          # faithful fixture carries only ~60 words total
        self.assertFalse(r["passed"])
        self.assertIn("D2 Copy substance", r["hard_misses"])

    def test_headline_and_cta_slots_are_exempt_at_low_floor(self):
        # FIX-XC-04a: short slots (headline/CTA/form) are legitimately short and pass.
        inp = _faithful_funnel()
        inp["template"].pop("lengthClass", None)
        inp["artifact"] = {"pages": [
            {"copy": {"headline": "Reclaim Your Focused Mornings Today", "cta": "Apply for the program",
                      "hero": ("A substantive hero paragraph that clears the forty word body "
                               "floor with real message-matched copy about the transformation "
                               "you get, the proof behind it, and exactly what to do next so a "
                               "reader never has to guess about the offer on this page today.")}},
            {"copy": {"cta": "Check your inbox for access"}}]}
        r = fab_qc.grade(inp)
        self.assertNotIn("D2 Copy substance", r["hard_misses"], r)

    def test_force_template_over_explicit_fails_naming_d5(self):
        inp = _faithful_funnel()
        inp["match_decision"]["intent_mode"] = "EXPLICIT_USER_SPEC"
        inp["match_decision"]["flex_decision"] = "USE_TEMPLATE"   # overrode the explicit spec
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D5 Flexibility honored", r["hard_misses"])

    def test_explicit_honored_passes_d5(self):
        inp = _faithful_funnel()
        inp["match_decision"]["intent_mode"] = "EXPLICIT_USER_SPEC"
        inp["match_decision"]["flex_decision"] = "HONOR_USER"
        r = fab_qc.grade(inp)
        self.assertTrue(r["passed"], r)

    def test_missing_persona_trips_failclosed_d4(self):
        inp = _faithful_funnel()
        inp["persona_log"] = ""
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D4 Persona grounding", r["hard_misses"])

    # ── B-U5 / U19 — FAB-QC D4 v2: bundle-aware voice grounding ─────────────
    # (the FAB-QC half of the U17<->U19 merge-paired unit, B.0 item 5: the
    # prior spec's P0 self-defeat is what these tests exist to close.)

    def test_bundle_active_grounds_on_blend_voice_not_template_persona(self):
        # A log naming the BLEND VOICE (not the template persona "Russell
        # Brunson" the fixture's copyFramework declares) must PASS D4 when a
        # bundle receipt is active — this is the v1 P0 self-defeat, fixed.
        inp = _faithful_funnel()
        inp["persona_log"] = "selected_persona: hormozi-100m-offers\nvoice_persona: hormozi-100m-offers\n"
        inp["persona_bundle"] = {"source": "threaded", "voice_persona_id": "hormozi-100m-offers"}
        r = fab_qc.grade(inp)
        self.assertTrue(r["passed"], r)
        self.assertNotIn("D4 Persona grounding", r["hard_misses"])

    def test_bundle_active_log_naming_only_template_persona_is_hard_miss(self):
        # Honest template-persona-only copy under an ACTIVE bundle must now
        # HARD MISS naming "blend voice not grounded" — the exact defect the
        # prior spec's P0 shipped (v2_dispatcher wired without the D4 fix).
        inp = _faithful_funnel()
        inp["persona_log"] = "selected_persona: russell-brunson-the-funnel-hackers-cookbook\n"
        inp["persona_bundle"] = {"source": "local", "voice_persona_id": "hormozi-100m-offers"}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D4 Persona grounding", r["hard_misses"])
        d4 = next(d for d in r["dimensions"] if d["name"] == "D4 Persona grounding")
        self.assertIn("blend voice not grounded", d4["observed"])

    def test_legacy_fixture_no_receipt_is_byte_identical_scorecard(self):
        # No persona_bundle key at all (every pre-B-U5 caller) -> the FULL
        # scorecard must be byte-identical to the pre-unit golden scorecard.
        inp_legacy = _faithful_funnel()
        inp_with_empty_bundle = _faithful_funnel()
        inp_with_empty_bundle["persona_bundle"] = {}
        inp_with_absent_source = _faithful_funnel()
        inp_with_absent_source["persona_bundle"] = {"source": "absent"}
        golden = fab_qc.grade(inp_legacy)
        self.assertEqual(golden, fab_qc.grade(inp_with_empty_bundle))
        self.assertEqual(golden, fab_qc.grade(inp_with_absent_source))
        self.assertTrue(golden["passed"], golden)

    def test_bundle_active_still_failclosed_on_missing_log(self):
        # The "no log -> 0.0 HARD MISS" fail-closed floor is unchanged in
        # BOTH modes.
        inp = _faithful_funnel()
        inp["persona_log"] = ""
        inp["persona_bundle"] = {"source": "cc", "voice_persona_id": "hormozi-100m-offers"}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D4 Persona grounding", r["hard_misses"])
        d4 = next(d for d in r["dimensions"] if d["name"] == "D4 Persona grounding")
        self.assertEqual(d4["score"], 0.0)

    # ── U117 (E6-3/G9) — voice_persona_grounded() extraction ────────────────
    # score_d4's bundle-aware token-match rule is now a standalone reusable
    # predicate (page_qc.py's comms-conformance "blend actually used" check
    # calls this SAME function rather than re-deriving the match rule). Pure
    # refactor: the two tests above (already passing unmodified) prove
    # score_d4's OWN behavior is byte-identical; these two prove the
    # extracted helper itself is correct in isolation.
    def test_voice_persona_grounded_direct_hit_and_miss(self):
        self.assertTrue(fab_qc.voice_persona_grounded(
            "selected_persona: hormozi-100m-offers\n", "hormozi-100m-offers"))
        self.assertFalse(fab_qc.voice_persona_grounded(
            "selected_persona: russell-brunson-the-funnel-hackers-cookbook\n",
            "hormozi-100m-offers"))

    def test_voice_persona_grounded_blank_inputs_never_crash(self):
        self.assertFalse(fab_qc.voice_persona_grounded("", ""))
        self.assertFalse(fab_qc.voice_persona_grounded("some log text", ""))
        self.assertFalse(fab_qc.voice_persona_grounded("", "hormozi-100m-offers"))

    def test_load_inputs_from_evidence_reads_persona_bundle_receipt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            routing = os.path.join(td, "routing")
            os.makedirs(routing, exist_ok=True)
            with open(os.path.join(routing, "persona-bundle-receipt.json"), "w") as f:
                json.dump({"source": "local", "voice_persona_id": "wiebe-copy-hackers"}, f)
            inp = fab_qc.load_inputs_from_evidence(td, "funnel")
            self.assertEqual(inp["persona_bundle"]["voice_persona_id"], "wiebe-copy-hackers")

    def test_load_inputs_from_evidence_absent_receipt_is_empty_dict(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "routing"), exist_ok=True)
            inp = fab_qc.load_inputs_from_evidence(td, "funnel")
            self.assertEqual(inp["persona_bundle"], {})

    def test_silently_dropped_linked_automations_fails_naming_d6(self):
        inp = _faithful_funnel()
        inp["match_decision"]["linked_automations"] = {"automations": []}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D6 Funnel<->automation link", r["hard_misses"])

    def test_user_override_of_linked_automation_is_honored_d6(self):
        inp = _faithful_funnel()
        inp["match_decision"]["linked_automations"] = {
            "automations": [{"automation_id": "soap-opera-sequence", "overridden_by_user": True}]}
        r = fab_qc.grade(inp)
        self.assertTrue(r["passed"], r)

    def test_render_5xx_is_hard_miss_d3(self):
        inp = _faithful_funnel()
        inp["verify"] = {"overall_pass": False, "pages": [{"status": 500}]}
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D3 Render/soundness", r["hard_misses"])

    def test_create_new_makes_d1_and_d4_na(self):
        inp = _faithful_funnel()
        inp["match_decision"]["flex_decision"] = "CREATE_NEW"
        inp["template"] = None
        inp["persona_log"] = "selected_persona: net-new persona chosen"
        r = fab_qc.grade(inp)
        # net-new with no template: D1 N/A=10, build still scoreable
        self.assertTrue(r["passed"], r)

    def test_automation_kind_scores_on_sequence_and_wf(self):
        inp = {
            "kind": "automation",
            "match_decision": {"flex_decision": "USE_TEMPLATE", "intent_mode": "HANDS_OFF_DO_IT_ALL"},
            "template": {"sequence": [{"channel": "email"}, {"channel": "email"}],
                         "copy_persona": {"primary": "Russell Brunson"}, "source_books": ["DotCom Secrets"]},
            "artifact": {"steps": [{"channel": "email", "copy": "Welcome aboard, here is what happens next today"},
                                   {"channel": "email", "copy": "Day two: the story behind why we built this for you"}]},
            "verify": {"items": [{"id": "WF-3", "status": "PASS"}, {"id": "WF-7", "status": "PASS"}]},
            "persona_log": "selected_persona: russell-brunson",
        }
        r = fab_qc.grade(inp)
        self.assertTrue(r["passed"], r)

    def test_automation_wf_fail_is_hard_miss_d3(self):
        inp = {
            "kind": "automation",
            "match_decision": {"flex_decision": "USE_TEMPLATE", "intent_mode": "HANDS_OFF_DO_IT_ALL"},
            "template": {"sequence": [{"channel": "email"}], "copy_persona": {"primary": "Brunson"}},
            "artifact": {"steps": [{"channel": "email", "copy": "real substantive copy goes here now"}]},
            "verify": {"items": [{"id": "WF-3", "status": "FAIL"}]},
            "persona_log": "selected_persona: brunson",
        }
        r = fab_qc.grade(inp)
        self.assertFalse(r["passed"])
        self.assertIn("D3 Render/soundness", r["hard_misses"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
