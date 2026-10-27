#!/usr/bin/env python3
"""Unit tests for playbook_engine.py (U-16).

Run: python3 -m unittest discover -s tools/tests  (from the skill root)
 or: python3 tools/tests/test_playbook_engine.py

Covers parser, validation, structural hashing, mermaid emission, build
contracts, phase-heading closure, exit-rule parsing, and conversation lint.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(
            p1["tools"],
            ["update_tags", "update_contact", "reference_documents"],
        )
        self.assertEqual(p1["skip_if_field_filled"], "contact.email")
        self.assertEqual(p1["max_attempts"], "2")
        self.assertEqual(p1["gate_if_not_met"], "budget qualified")
        self.assertIn("not the right fit", p1["gate_closing"])

    def test_phase_source_line(self):
        lines = [line for line in GOOD.splitlines()
                 if not line.lstrip().startswith("```")]
        for phase in self.p["phases"]:
            self.assertEqual(
                lines[phase["line"] - 1].split("Phase")[1].split("-")[0].strip(),
                str(phase["number"]),
            )

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
        phase1 = engine.parse_playbook(GOOD)["phases"][0]
        tools = engine.resolve_phase_tools(phase1)
        self.assertIn("escalate_to_human", tools)
        self.assertIn("update_tags", tools)

    def test_global_reference_documents_always_on(self):
        phase4 = engine.parse_playbook(GOOD)["phases"][3]
        self.assertIn("reference_documents", engine.resolve_phase_tools(phase4))


class TestValidateGood(unittest.TestCase):
    def test_good_is_clean(self):
        defects = engine.validate_playbook(engine.parse_playbook(GOOD))
        self.assertEqual(defects, [], "good fixture should have zero defects: %s" % defects)


class TestValidateBroken(unittest.TestCase):
    def setUp(self):
        self.p = engine.parse_playbook(BROKEN)
        self.defects = engine.validate_playbook(self.p)
        self.blob = " || ".join(self.defects)

    def test_has_defects(self):
        self.assertTrue(self.defects)

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
        defects = engine.validate_playbook(
            engine.parse_playbook(pb), registry_targets={"pricing-inquiry"}
        )
        self.assertTrue(any("support-intake" in d for d in defects))
        defects_ok = engine.validate_playbook(
            engine.parse_playbook(pb), registry_targets={"support-intake"}
        )
        self.assertFalse(any("route target" in d for d in defects_ok))


class TestHash(unittest.TestCase):
    def test_stable_across_copy_edits(self):
        h1 = engine.structure_hash(engine.parse_playbook(GOOD))
        copy_edit = GOOD.replace(
            "Warm, concise, and helpful.", "Friendly and brief."
        ).replace(
            "Greet warmly, confirm the interest,",
            "Say hello, confirm interest,",
        )
        h2 = engine.structure_hash(engine.parse_playbook(copy_edit))
        self.assertEqual(h1, h2, "copy edits must not change the structure hash")

    def test_changes_on_structural_edit(self):
        structural = GOOD.replace(
            "tools: book_appointment, check_availability, update_tags, update_contact, reference_documents",
            "tools: check_availability, update_tags, update_contact, reference_documents",
        )
        self.assertNotEqual(
            engine.structure_hash(engine.parse_playbook(GOOD)),
            engine.structure_hash(engine.parse_playbook(structural)),
        )

    def test_hash_is_hex_sha256(self):
        h = engine.structure_hash(engine.parse_playbook(GOOD))
        self.assertEqual(len(h), 64)
        int(h, 16)

    def test_escalation_second_line_changes_hash(self):
        base = (
            "# WF\n\n### Phase 1 - One\n\n"
            "## On escalation\nEscalate to operator.\nRecord the case.\n"
        )
        changed = base.replace("Record the case.", "Notify supervisor.")
        self.assertNotEqual(
            engine.structure_hash(engine.parse_playbook(base)),
            engine.structure_hash(engine.parse_playbook(changed)),
        )

    def test_on_success_order_changes_hash(self):
        base = (
            "# WF\n\n### Phase 1 - One\n\n"
            "## On success\nTag contact.\nSend confirmation.\n"
        )
        reordered = base.replace(
            "Tag contact.\nSend confirmation.",
            "Send confirmation.\nTag contact.",
        )
        extra = base.replace(
            "Send confirmation.", "Send confirmation.\nWrite audit log."
        )
        h = engine.structure_hash(engine.parse_playbook(base))
        self.assertNotEqual(h, engine.structure_hash(engine.parse_playbook(reordered)))
        self.assertNotEqual(h, engine.structure_hash(engine.parse_playbook(extra)))


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
        self.assertNotIn("```", self.mmd)


class TestResolveFromLog(unittest.TestCase):
    def test_resolve_with_playbook(self):
        res = engine.resolve_from_log(LOG, GOOD)
        self.assertEqual(res["active_workflow"], "good-playbook")
        self.assertEqual(res["active_phase"], 4)
        self.assertEqual(res["phase_attempts"], "1:2, 2:1, 3:0, 4:1")
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
        reg = (
            "# Conversation Workflows Registry\n\n"
            "| ID | Name | OpenClaw playbook |\n"
            "|---|---|---|\n"
            "| appointment-booking | Booking | appointment-booking.md |\n"
            "| support-intake | Support | support-intake.md |\n"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(reg)
            path = fh.name
        try:
            ids = engine._load_registry_ids(path)
        finally:
            os.unlink(path)
        self.assertEqual(ids, {"appointment-booking", "support-intake"})
        self.assertNotIn("id", ids)


class TestPhaseHeadingClosure(unittest.TestCase):
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
        self.assertEqual(self.ph1["tools"], ["check_availability"])
        for leaked in ("book_appointment", "send_invoice", "everything"):
            self.assertNotIn(leaked, self.ph1["tools"])

    def test_rogue_heading_does_not_corrupt_max_attempts(self):
        self.assertEqual(self.ph1["max_attempts"], "2")

    def test_rogue_heading_not_in_resolved_tools(self):
        resolved = engine.resolve_phase_tools(self.ph1)
        self.assertIn("check_availability", resolved)
        self.assertNotIn("book_appointment", resolved)
        self.assertNotIn("everything", resolved)

    def test_phase_count_is_two(self):
        self.assertEqual(len(self.p["phases"]), 2)
        self.assertEqual(self.p["phases"][1]["number"], 2)
        self.assertEqual(self.p["phases"][1]["tools"], ["update_tags"])

    def test_h1_and_h2_headings_still_close(self):
        pb = (
            "### Phase 1 - Qualify\n"
            "tools: check_availability\n"
            "## Some section\n"
            "tools: book_appointment\n"
        )
        self.assertEqual(
            engine.parse_playbook(pb)["phases"][0]["tools"],
            ["check_availability"],
        )

    def test_h4_edge_heading_does_not_close(self):
        pb = (
            "### Phase 1 - Qualify\n"
            "tools: check_availability\n"
            "#### Edge case: no availability\n"
            "max-attempts: 3\n"
        )
        phase = engine.parse_playbook(pb)["phases"][0]
        self.assertEqual(phase["tools"], ["check_availability"])
        self.assertEqual(phase["max_attempts"], "3")


class TestExitRuleOrderIndependence(unittest.TestCase):
    def test_normal_order_closing_then_target(self):
        rule = engine._parse_exit_rule(
            "switch, action: route, closing: Handing you over, target: support-intake"
        )
        self.assertEqual(rule["tag"], "switch")
        self.assertEqual(rule["action"], "route")
        self.assertEqual(rule["closing"], "Handing you over")
        self.assertEqual(rule["target"], "support-intake")

    def test_reversed_order_target_then_closing(self):
        rule = engine._parse_exit_rule(
            "switch, action: route, target: support-intake, closing: Handing you over"
        )
        self.assertEqual(rule["target"], "support-intake")
        self.assertEqual(rule["closing"], "Handing you over")
        self.assertEqual(rule["action"], "route")

    def test_both_orders_parse_identically(self):
        first = engine._parse_exit_rule(
            "x, action: route, closing: bye now, target: t-id"
        )
        second = engine._parse_exit_rule(
            "x, action: route, target: t-id, closing: bye now"
        )
        self.assertEqual(first, second)

    def test_reversed_route_validates_clean(self):
        pb = (
            "### Phase 1 - Only\n"
            "tools: reference_documents\n"
            "Do the thing.\n\n"
            "Exit rules\n"
            "exit-when-tag: switch, action: route, target: support-intake, closing: Bye\n\n"
            "## On success\nWin.\n"
        )
        defects = engine.validate_playbook(
            engine.parse_playbook(pb), registry_targets={"support-intake"}
        )
        self.assertFalse(any("route" in d and "target" in d for d in defects))

    def test_malformed_no_action_is_loud_not_silent(self):
        rule = engine._parse_exit_rule("foo, target: bar")
        self.assertEqual(rule["tag"], "foo")
        self.assertIsNone(rule["action"])
        self.assertEqual(rule["target"], "bar")
        pb = (
            "### Phase 1 - Only\n"
            "tools: reference_documents\n\n"
            "Exit rules\n"
            "exit-when-tag: foo, target: bar\n\n"
            "## On success\nWin.\n"
        )
        defects = engine.validate_playbook(engine.parse_playbook(pb))
        self.assertTrue(any("action" in d for d in defects))

    def test_tag_only_no_clauses(self):
        rule = engine._parse_exit_rule("just-a-tag")
        self.assertEqual(rule["tag"], "just-a-tag")
        self.assertIsNone(rule["action"])
        self.assertIsNone(rule["closing"])
        self.assertIsNone(rule["target"])


class TestBuildContract(unittest.TestCase):
    def test_contract_hash_matches_structure_hash(self):
        parsed = engine.parse_playbook(GOOD)
        contract = engine.write_build_contract(parsed, "good-playbook", "good-playbook.md")
        self.assertEqual(
            contract["playbook_structure_hash"],
            engine.structure_hash(engine.parse_playbook(GOOD)),
        )

    def test_contract_keys_and_order(self):
        contract = engine.write_build_contract(
            engine.parse_playbook(GOOD), "good-playbook", "good-playbook.md"
        )
        self.assertEqual(
            list(contract.keys()),
            [
                "contract_version", "playbook_id", "playbook_path",
                "playbook_structure_hash", "generated_at", "trigger", "tags",
                "fields", "custom_values", "calendars", "pipeline", "exit_rules",
                "tools", "channels", "model_tier", "workflow", "acceptance",
                "warnings",
            ],
        )

    def test_contract_declares_mapping(self):
        contract = engine.write_build_contract(
            engine.parse_playbook(GOOD), "good-playbook", "good-playbook.md"
        )
        self.assertEqual(contract["tags"]["applies"], [])
        self.assertEqual(contract["tags"]["reads"], [])
        self.assertEqual(
            contract["calendars"],
            [
                {"key": "default", "id": "CAL_ID_A"},
                {"key": "on-site estimate", "id": "CAL_ID_B"},
            ],
        )
        self.assertEqual(contract["pipeline"]["id"], "sales-pipeline")
        self.assertEqual(
            [stage["name"] for stage in contract["pipeline"]["stages"]],
            ["STAGE_QUALIFIED", "STAGE_BOOKED"],
        )
        self.assertEqual(
            [field["name"] for field in contract["fields"]],
            ["contact.email", "ZHC_budget_range"],
        )

    def test_contract_never_fabricates(self):
        contract = engine.write_build_contract(
            engine.parse_playbook(GOOD), "good-playbook", "good-playbook.md"
        )
        self.assertEqual(contract["trigger"], {"kind": None, "tag": None})
        self.assertEqual(contract["custom_values"], [])
        self.assertEqual(contract["channels"], [])
        self.assertEqual(
            contract["acceptance"]["must_pass"],
            ["fields_exist", "calendars_exist", "pipeline_stages_exist"],
        )
        self.assertTrue(contract["acceptance"]["must_pass"])
        self.assertTrue(all(value is None for value in contract["workflow"].values()))
        warnings = "\n".join(contract["warnings"])
        for section in ("trigger", "custom_values", "channels", "workflow"):
            self.assertIn(section, warnings)

    def test_cli_writes_file(self):
        expected_hash = engine.structure_hash(engine.parse_playbook(GOOD))
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "x.json"
            result = subprocess.run(
                [
                    sys.executable, str(TOOLS_DIR / "playbook_engine.py"),
                    "build-contract", str(FIXTURES / "good-playbook.md"),
                    "--out", str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            contract = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(contract["playbook_structure_hash"], expected_hash)

    def test_contract_must_pass_is_never_empty(self):
        contract = engine.write_build_contract(
            engine.parse_playbook(GOOD), "good-playbook", "good-playbook.md"
        )
        must_pass = contract["acceptance"]["must_pass"]
        self.assertIsInstance(must_pass, list)
        self.assertGreater(len(must_pass), 0)
        self.assertNotIn("tags_exist", must_pass)

    def test_refuses_vacuous_contract_cli(self):
        pb_text = (
            "# Empty playbook\n"
            "Created: 2026-10-27\n\n"
            "### Phase 1 - Say hello\n"
            "Say hello.\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            pb = Path(tmpdir) / "empty-playbook.md"
            output = Path(tmpdir) / "contract.json"
            pb.write_text(pb_text, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(TOOLS_DIR / "playbook_engine.py"),
                    "build-contract", str(pb), "--out", str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("vacuous build contract", result.stderr)
            self.assertFalse(output.exists())

    def test_cli_emits_non_empty_must_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "contract.json"
            result = subprocess.run(
                [
                    sys.executable, str(TOOLS_DIR / "playbook_engine.py"),
                    "build-contract", str(FIXTURES / "good-playbook.md"),
                    "--out", str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                contract["acceptance"]["must_pass"],
                ["fields_exist", "calendars_exist", "pipeline_stages_exist"],
            )


class TestFormattingLaws(unittest.TestCase):
    def test_no_em_dash_in_engine_source(self):
        src = (TOOLS_DIR / "playbook_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", src)

    def test_parse_json_roundtrips(self):
        self.assertIsInstance(json.dumps(engine.parse_playbook(GOOD)), str)


class TestPhaseNumberRegressions(unittest.TestCase):
    DUPLICATE = (
        "# Workflow\n\n"
        "### Phase 2 - First\n"
        "tools: update_tags\n\n"
        "### Phase 2 - Second\n"
        "tools: update_tags\n"
    )
    OUT_OF_ORDER = (
        "# Workflow\n\n"
        "### Phase 3 - Third\n"
        "tools: update_tags\n\n"
        "### Phase 2 - Second\n"
        "tools: update_tags\n"
    )

    def test_duplicate_phase_numbers_include_lines(self):
        defects = engine.validate_playbook(engine.parse_playbook(self.DUPLICATE))
        self.assertTrue(any(
            "duplicate phase numbers: 2 (lines 3, 6)" in defect
            for defect in defects
        ))

    def test_duplicate_phase_numbers_cli_exit_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "duplicate.md"
            path.write_text(self.DUPLICATE, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(TOOLS_DIR / "playbook_engine.py"),
                    "validate", str(path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("lines 3, 6", result.stdout + result.stderr)

    def test_out_of_order_sequence(self):
        defects = engine.validate_playbook(engine.parse_playbook(self.OUT_OF_ORDER))
        self.assertTrue(any(
            "phases are out of order: 3, 2 (expected 2, 3)" in defect
            for defect in defects
        ))

    def test_out_of_order_cli_exit_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "order.md"
            path.write_text(self.OUT_OF_ORDER, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(TOOLS_DIR / "playbook_engine.py"),
                    "validate", str(path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "phases are out of order: 3, 2 (expected 2, 3)",
                result.stdout + result.stderr,
            )

    def test_malformed_phase_header(self):
        fixture = "# Workflow\n\n### Phase - No Number\n"
        defects = engine.validate_playbook(engine.parse_playbook(fixture))
        self.assertTrue(any("malformed phase header at line" in defect for defect in defects))


class TestConversationLintRegressions(unittest.TestCase):
    def fixture(
        self,
        objections="- Objection\n",
        kpis="- Booking target: 20%",
        transcript=(
            "Customer: Hello.\n"
            "Agent: Hi.\n"
            "Customer: Help?\n"
            "Agent: Your next step is to book an appointment."
        ),
    ):
        return (
            "# Workflow\n\n"
            "### Phase 1 - Qualify\n"
            "example: Hello.\n\n"
            "## Objection Library\n%s\n"
            "## Conversational KPIs\n%s\n"
            "## Golden Transcript\n%s\n"
            "## Never say\n- prohibited phrase\n"
        ) % (objections, kpis, transcript)

    def test_five_objection_bullets_do_not_count(self):
        bullets = "\n".join([
            "- Too expensive", "- Not now", "- Too busy",
            "- Maybe later", "- No thanks",
        ])
        defects = engine.conversation_lint(
            engine.parse_playbook(self.fixture(objections=bullets))
        )
        self.assertIn("objection library has 0 objection(s), minimum is 5", defects)

    def test_five_complete_objection_rows_count(self):
        rows = (
            "| Objection | Response | Never say |\n"
            "|---|---|---|\n"
            + "\n".join(
                "| objection %d | response %d | prohibited %d |" % (i, i, i)
                for i in range(5)
            )
        )
        defects = engine.conversation_lint(
            engine.parse_playbook(self.fixture(objections=rows))
        )
        self.assertFalse(any("objection library" in defect for defect in defects))

    def test_alternating_transcript_requires_outcome(self):
        transcript = (
            "Customer: Hi.\nAgent: Hello.\n"
            "Customer: Okay.\nAgent: Anything else?"
        )
        defects = engine.conversation_lint(
            engine.parse_playbook(self.fixture(transcript=transcript))
        )
        self.assertTrue(any("golden transcript has no stated outcome" in d for d in defects))

    def test_agent_only_transcript_does_not_alternate(self):
        transcript = (
            "Agent: Hi.\nAgent: Hello.\nAgent: Okay.\nAgent: Done."
        )
        defects = engine.conversation_lint(
            engine.parse_playbook(self.fixture(transcript=transcript))
        )
        self.assertTrue(any(
            "golden transcript turns do not alternate speakers" in d
            for d in defects
        ))

    def test_prose_kpi_requires_numeric_target(self):
        defects = engine.conversation_lint(
            engine.parse_playbook(
                self.fixture(kpis="- Be friendly and helpful at all times.")
            )
        )
        self.assertTrue(any(
            "conversational KPI line has no numeric target" in d
            for d in defects
        ))

    def test_table_kpi_header_is_not_a_target(self):
        kpis = (
            "| KPI | Target |\n"
            "|---|---|\n"
            "| Booking rate | 20% |"
        )
        defects = engine.conversation_lint(
            engine.parse_playbook(self.fixture(kpis=kpis))
        )
        self.assertFalse(any("conversational KPI" in d for d in defects))


if __name__ == "__main__":
    unittest.main(verbosity=2)
