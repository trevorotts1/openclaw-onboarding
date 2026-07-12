#!/usr/bin/env python3
"""Unit tests for playbook_engine.py (U-16).

Run: python3 -m unittest discover -s tools/tests  (from the skill root)
 or: python3 tools/tests/test_playbook_engine.py

Covers one good playbook fixture and one deliberately broken fixture per
grammar family: header (model-tier enum), phase tools vocabulary, the
escalate-never-gated-off invariant, exit-rule grammar (route needs target,
action enum), and the U-9 cross-validations (tools-used vs phases, exits-used
vs exit rules). Also covers hash stability, mermaid emission, and the U-4
resolve lookup.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Make the tools/ directory importable regardless of the invoking cwd.
TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import playbook_engine as engine  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOOD = (FIXTURES / "good-playbook.md").read_text(encoding="utf-8")
BROKEN = (FIXTURES / "broken-playbook.md").read_text(encoding="utf-8")
LOG = (FIXTURES / "sample-log.md").read_text(encoding="utf-8")


class TestParse(unittest.TestCase):
    def setUp(self):
        self.p = engine.parse_playbook(GOOD)

    def test_header(self):
        self.assertEqual(self.p["header"]["persona"], "house-standard")
        self.assertEqual(self.p["header"]["model_tier"], "realtime-standard")

    def test_declares(self):
        d = self.p["declares"]
        self.assertIn("book_appointment", d["tools-used"])
        self.assertIn("already-booked", d["exits-used"])
        self.assertIn("ZHC_budget_range", d["fields-used"])
        self.assertEqual(d["pipeline"], "sales-pipeline")
        self.assertTrue(any("qualified" in s for s in d["stage-map"]))
        self.assertTrue(any("CAL_ID_B" in c for c in d["calendars"]))

    def test_phases(self):
        self.assertEqual(len(self.p["phases"]), 4)
        p1 = self.p["phases"][0]
        self.assertEqual(p1["number"], 1)
        self.assertIn("Acknowledge", p1["name"])
        self.assertEqual(p1["tools"], ["update_tags", "update_contact", "reference_documents"])
        self.assertEqual(p1["skip_if_field_filled"], "contact.email")
        self.assertEqual(p1["max_attempts"], "2")
        self.assertEqual(p1["gate_if_not_met"], "budget qualified")
        self.assertIn("not the right fit", p1["gate_closing"])

    def test_exit_rules(self):
        rules = self.p["exit_rules"]
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]["tag"], "already-booked")
        self.assertEqual(rules[0]["action"], "end")
        self.assertEqual(rules[1]["tag"], "talk-to-human")
        self.assertEqual(rules[1]["action"], "handoff")

    def test_win_and_escalation(self):
        self.assertIsNotNone(self.p["win_action"])
        self.assertIsNotNone(self.p["escalation"])


class TestResolvePhaseTools(unittest.TestCase):
    def test_default_safe_minimum(self):
        tools = engine.resolve_phase_tools(None)
        self.assertIn("reference_documents", tools)
        self.assertIn("update_tags", tools)
        self.assertIn("escalate_to_human", tools)

    def test_explicit_phase_always_grants_escalate(self):
        p = engine.parse_playbook(GOOD)
        phase1 = p["phases"][0]
        tools = engine.resolve_phase_tools(phase1)
        # escalate_to_human is always granted even though the phase never lists it.
        self.assertIn("escalate_to_human", tools)
        self.assertIn("update_tags", tools)

    def test_global_reference_documents_always_on(self):
        p = engine.parse_playbook(GOOD)
        # Phase 4 lists reference_documents explicitly; it stays present.
        phase4 = p["phases"][3]
        self.assertIn("reference_documents", engine.resolve_phase_tools(phase4))


class TestValidateGood(unittest.TestCase):
    def test_good_is_clean(self):
        p = engine.parse_playbook(GOOD)
        defects = engine.validate_playbook(p)
        self.assertEqual(defects, [], "good fixture should have zero defects: %s" % defects)


class TestValidateBroken(unittest.TestCase):
    def setUp(self):
        self.p = engine.parse_playbook(BROKEN)
        self.defects = engine.validate_playbook(self.p)
        self.blob = " || ".join(self.defects)

    def test_has_defects(self):
        self.assertTrue(self.defects, "broken fixture must produce defects")

    def test_bad_model_tier(self):
        self.assertIn("hyperspeed-max", self.blob)

    def test_out_of_vocab_phase_tool(self):
        self.assertIn("warp_drive", self.blob)

    def test_escalate_never_gated_off(self):
        self.assertIn("escalate_to_human", self.blob)
        self.assertIn("can never be gated off", self.blob)

    def test_bad_max_attempts(self):
        self.assertTrue(any("max-attempts" in d for d in self.defects))

    def test_route_without_target(self):
        self.assertTrue(any("route requires a target" in d for d in self.defects))

    def test_bad_exit_action(self):
        self.assertTrue(any("teleport" in d for d in self.defects))

    def test_declares_tool_not_in_phase(self):
        self.assertTrue(any("teleport_customer" in d for d in self.defects))

    def test_declares_exit_not_declared(self):
        self.assertTrue(any("never-declared-exit" in d for d in self.defects))


class TestValidateCrossFile(unittest.TestCase):
    def test_route_target_absent_from_registry(self):
        # A route to a target absent from the registry is a defect.
        pb = (
            "# WF\n\n"
            "## What the agent does\n\n"
            "### Phase 1 - Only\n"
            "tools: reference_documents\n"
            "Do the thing.\n\n"
            "Exit rules\n"
            "exit-when-tag: switch-to-support, action: route, target: support-intake\n\n"
            "## On success\nWin.\n"
        )
        p = engine.parse_playbook(pb)
        defects = engine.validate_playbook(p, registry_targets={"pricing-inquiry"})
        self.assertTrue(any("support-intake" in d for d in defects))
        # Present in the registry => clean on that dimension.
        defects_ok = engine.validate_playbook(p, registry_targets={"support-intake"})
        self.assertFalse(any("route target" in d for d in defects_ok))


class TestHash(unittest.TestCase):
    def test_stable_across_copy_edits(self):
        h1 = engine.structure_hash(engine.parse_playbook(GOOD))
        # A pure copy/tone edit (change prose only) must NOT change the hash.
        copy_edit = GOOD.replace("Warm, concise, and helpful.", "Friendly and brief.")
        copy_edit = copy_edit.replace("Greet warmly, confirm the interest,",
                                      "Say hello, confirm interest,")
        h2 = engine.structure_hash(engine.parse_playbook(copy_edit))
        self.assertEqual(h1, h2, "copy edits must not change the structure hash")

    def test_changes_on_structural_edit(self):
        h1 = engine.structure_hash(engine.parse_playbook(GOOD))
        # Removing a tool from a phase is a structural change.
        structural = GOOD.replace(
            "tools: book_appointment, check_availability, update_tags, update_contact, reference_documents",
            "tools: check_availability, update_tags, update_contact, reference_documents",
        )
        h2 = engine.structure_hash(engine.parse_playbook(structural))
        self.assertNotEqual(h1, h2, "structural edits must change the hash")

    def test_hash_is_hex_sha256(self):
        h = engine.structure_hash(engine.parse_playbook(GOOD))
        self.assertEqual(len(h), 64)
        int(h, 16)  # raises if not hex


class TestMermaid(unittest.TestCase):
    def setUp(self):
        self.mmd = engine.to_mermaid(engine.parse_playbook(GOOD))

    def test_has_flowchart_header(self):
        self.assertTrue(self.mmd.startswith("flowchart TD"))

    def test_has_all_phase_nodes(self):
        for n in range(1, 5):
            self.assertIn("phase%d[" % n, self.mmd)

    def test_has_exit_and_escalation(self):
        self.assertIn("exit", self.mmd)
        self.assertIn("escalation", self.mmd)

    def test_no_triple_backtick(self):
        # A .mmd artifact must never carry a markdown fence.
        self.assertNotIn("```", self.mmd)


class TestResolveFromLog(unittest.TestCase):
    def test_resolve_with_playbook(self):
        res = engine.resolve_from_log(LOG, GOOD)
        self.assertEqual(res["active_workflow"], "good-playbook")
        self.assertEqual(res["active_phase"], 4)
        self.assertEqual(res["phase_attempts"], "1:2, 2:1, 3:0, 4:1")
        # Phase 4 grants booking; escalate is always present.
        self.assertIn("book_appointment", res["enabled_tools"])
        self.assertIn("escalate_to_human", res["enabled_tools"])

    def test_resolve_without_playbook(self):
        res = engine.resolve_from_log(LOG, None)
        self.assertEqual(res["active_workflow"], "good-playbook")
        self.assertIsNone(res["enabled_tools"])

    def test_read_log_header(self):
        h = engine.read_log_header(LOG)
        self.assertEqual(h["active_workflow"], "good-playbook")
        self.assertEqual(h["active_phase"], "4")


class TestRegistryIds(unittest.TestCase):
    def test_parses_ids_and_skips_separators(self):
        import tempfile
        reg = (
            "# Conversation Workflows Registry\n\n"
            "| ID | Name | OpenClaw playbook |\n"
            "|---|---|---|\n"
            "| appointment-booking | Booking | appointment-booking.md |\n"
            "| support-intake | Support | support-intake.md |\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(reg)
            path = fh.name
        ids = engine._load_registry_ids(path)
        os.unlink(path)
        # Real ids parse; the header row and the |---| separator row do not.
        self.assertEqual(ids, {"appointment-booking", "support-intake"})
        self.assertNotIn("id", ids)


class TestPhaseHeadingClosure(unittest.TestCase):
    """P3-07 step 1: a rogue mid-phase level-3 (###) non-Phase heading must
    CLOSE the phase block. Its key:value-looking lines must NOT leak into the
    preceding phase's tools/max-attempts (the data the U-1 tool-gating gates
    trust). Pre-fix, the closing check matched only '# '/'## ', so a bare
    '### Notes' silently absorbed its lines into the phase above it.
    """

    ROGUE = (
        "# WF\n\n"
        "## What the agent does\n\n"
        "### Phase 1 - Qualify\n"
        "tools: check_availability\n"
        "max-attempts: 2\n"
        "Ask what they need.\n\n"
        "### Notes\n"
        "tools: book_appointment, send_invoice, everything\n"
        "max-attempts: 99\n\n"
        "### Phase 2 - Close\n"
        "tools: update_tags\n"
        "Wrap up.\n"
    )

    def setUp(self):
        self.p = engine.parse_playbook(self.ROGUE)
        self.ph1 = self.p["phases"][0]

    def test_rogue_heading_does_not_leak_tools(self):
        # Phase 1 granted ONLY check_availability. The '### Notes' tools line
        # must NOT bleed in.
        self.assertEqual(self.ph1["tools"], ["check_availability"])
        for leaked in ("book_appointment", "send_invoice", "everything"):
            self.assertNotIn(leaked, self.ph1["tools"],
                             "'%s' leaked from '### Notes' into Phase 1" % leaked)

    def test_rogue_heading_does_not_corrupt_max_attempts(self):
        # Phase 1's max-attempts is 2; the rogue block's 'max-attempts: 99'
        # must not overwrite it.
        self.assertEqual(self.ph1["max_attempts"], "2")

    def test_rogue_heading_not_in_resolved_tools(self):
        # The tool-gating gate resolves the enabled set from the phase; the
        # leaked tools must not become grantable.
        resolved = engine.resolve_phase_tools(self.ph1)
        self.assertIn("check_availability", resolved)
        self.assertNotIn("book_appointment", resolved)
        self.assertNotIn("everything", resolved)

    def test_phase_count_is_two(self):
        # '### Notes' is NOT a phase; only Phase 1 and Phase 2 are phases.
        self.assertEqual(len(self.p["phases"]), 2)
        self.assertEqual(self.p["phases"][1]["number"], 2)
        self.assertEqual(self.p["phases"][1]["tools"], ["update_tags"])

    def test_h1_and_h2_headings_still_close(self):
        # The fix must not regress '# '/'## ' closure: a '## ' section heading
        # after Phase 1 still closes it.
        pb = (
            "### Phase 1 - Qualify\n"
            "tools: check_availability\n"
            "## Some section\n"
            "tools: book_appointment\n"
        )
        p = engine.parse_playbook(pb)
        self.assertEqual(p["phases"][0]["tools"], ["check_availability"])

    def test_h4_edge_heading_does_not_close(self):
        # A deeper '#### edge' heading inside a phase must NOT close it (kv lines
        # under it still belong to the phase) - the documented '#### edge'
        # carve-out is preserved.
        pb = (
            "### Phase 1 - Qualify\n"
            "tools: check_availability\n"
            "#### Edge case: no availability\n"
            "max-attempts: 3\n"
        )
        p = engine.parse_playbook(pb)
        self.assertEqual(p["phases"][0]["tools"], ["check_availability"])
        self.assertEqual(p["phases"][0]["max_attempts"], "3")


class TestExitRuleOrderIndependence(unittest.TestCase):
    """P3-07 step 2: closing: and target: may appear in EITHER order after the
    action clause. Neither may swallow the other's value. Pre-fix, a reversed
    'target: ..., closing: ...' let target greedily eat the trailing closing.
    """

    def test_normal_order_closing_then_target(self):
        r = engine._parse_exit_rule(
            "switch, action: route, closing: Handing you over, target: support-intake")
        self.assertEqual(r["tag"], "switch")
        self.assertEqual(r["action"], "route")
        self.assertEqual(r["closing"], "Handing you over")
        self.assertEqual(r["target"], "support-intake")

    def test_reversed_order_target_then_closing(self):
        r = engine._parse_exit_rule(
            "switch, action: route, target: support-intake, closing: Handing you over")
        # target must be EXACTLY the id - it must not swallow the closing text.
        self.assertEqual(r["target"], "support-intake")
        self.assertEqual(r["closing"], "Handing you over")
        self.assertEqual(r["action"], "route")

    def test_both_orders_parse_identically(self):
        a = engine._parse_exit_rule(
            "x, action: route, closing: bye now, target: t-id")
        b = engine._parse_exit_rule(
            "x, action: route, target: t-id, closing: bye now")
        self.assertEqual(a, b)

    def test_reversed_route_validates_clean(self):
        # A reversed-order route rule must not produce a spurious "route needs a
        # target" defect (the target was being corrupted pre-fix).
        pb = (
            "### Phase 1 - Only\n"
            "tools: reference_documents\n"
            "Do the thing.\n\n"
            "Exit rules\n"
            "exit-when-tag: switch, action: route, target: support-intake, closing: Bye\n\n"
            "## On success\nWin.\n"
        )
        p = engine.parse_playbook(pb)
        defects = engine.validate_playbook(p, registry_targets={"support-intake"})
        self.assertFalse(any("route" in d and "target" in d for d in defects),
                         "reversed-order route should validate clean: %s" % defects)

    def test_malformed_no_action_is_loud_not_silent(self):
        # A tag with named clauses but NO action clause must leave action None,
        # which validate_playbook flags loudly (never a silent bad action).
        r = engine._parse_exit_rule("foo, target: bar")
        self.assertEqual(r["tag"], "foo")
        self.assertIsNone(r["action"])
        self.assertEqual(r["target"], "bar")
        pb = (
            "### Phase 1 - Only\n"
            "tools: reference_documents\n\n"
            "Exit rules\n"
            "exit-when-tag: foo, target: bar\n\n"
            "## On success\nWin.\n"
        )
        p = engine.parse_playbook(pb)
        defects = engine.validate_playbook(p)
        self.assertTrue(any("action" in d for d in defects),
                        "a missing action must be a loud defect: %s" % defects)

    def test_tag_only_no_clauses(self):
        r = engine._parse_exit_rule("just-a-tag")
        self.assertEqual(r["tag"], "just-a-tag")
        self.assertIsNone(r["action"])
        self.assertIsNone(r["closing"])
        self.assertIsNone(r["target"])


class TestFormattingLaws(unittest.TestCase):
    """The engine and its fixtures must obey the operator formatting laws."""

    def test_no_em_dash_in_engine_source(self):
        src = (TOOLS_DIR / "playbook_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", src, "no em dash allowed in engine source")

    def test_parse_json_roundtrips(self):
        p = engine.parse_playbook(GOOD)
        # Every parse result must be JSON-serializable (the gates consume JSON).
        s = json.dumps(p)
        self.assertIsInstance(s, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
