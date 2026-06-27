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
            {"page_id": "p1", "copy": {"hero": "Get the free funnel swipe file today and grow your list",
                                        "form": "Enter your best email to receive instant access right now"}},
            {"page_id": "p2", "copy": {"cta": "Check your inbox now for the download link we just sent over"}}]},
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
