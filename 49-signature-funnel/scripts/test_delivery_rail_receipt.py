#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_delivery_rail_receipt.py - M1: the delivery-rail receipt replaces every Skill 49 -> Skill 6 call.

P4-MEDIA and P7-BUILD certify only on operator-key-signed receipt lines the delivery rail (named in
brief.delivery_rail) wrote into the run (`delegation_receipt.record`), shaped by
schema/delivery-rail-receipt.schema.json (id sf-delivery-rail-receipt/v1). Covers: the schema, the P4 seam
(AF-FUN-DELEG-MEDIA), the P9 re-check (AF-FUN-IMG-HOST), the persona-used report through Skill 49's own board
client, the required brief field, and the doc lockstep for the renamed phases and the removed nonce wording.
The P7 half lives in test_legacy_structure_proofs.py (P7ToolRunTests) and prove_sf_build.py --self-test.

Run:  python3 -m pytest 49-signature-funnel/scripts/test_delivery_rail_receipt.py -q
"""
import copy
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent
for p in (str(HERE), str(SKILL)):
    if p not in sys.path:
        sys.path.insert(0, p)

import copy_persona_blend_seam as seam  # noqa: E402
import delegation_receipt as dr  # noqa: E402
import mc_board  # noqa: E402
import prove_sf_cert  # noqa: E402
import prove_sf_intake as intake  # noqa: E402
import prove_sf_no_pitch as nopitch  # noqa: E402
import run_signature_funnel as runner  # noqa: E402
import stub_provider_adapter as stub  # noqa: E402

SCHEMA = SKILL / "schema" / "delivery-rail-receipt.schema.json"
DELEGATE = "delivery rail named by brief.delivery_rail :: sf-delivery-rail-receipt/v1"


class Run(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        stub.ensure_fixture_operator_key()
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.rd = Path(self._td.name) / "run-rail"
        self.rd.mkdir()
        self.ledger = {"images": [
            {"page_type": "main", "section": 1, "kie_task_id": "kie_a", "media_url": "https://media.rail.test/a.png"},
            {"page_type": "main", "section": 5, "kie_task_id": "kie_b", "media_url": "https://media.rail.test/b.png"}]}
        (self.rd / "media_ledger.json").write_text(json.dumps(self.ledger), encoding="utf-8")

    def lines(self):
        return [json.loads(x) for x in (self.rd / dr.RECEIPTS_REL).read_text(encoding="utf-8").splitlines()]

    def write_lines(self, lines):
        (self.rd / dr.RECEIPTS_REL).write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


class TheSchema(Run):
    def test_schema_is_json_and_names_both_phases(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "sf-delivery-rail-receipt/v1")
        self.assertEqual(schema["properties"]["phase"]["enum"], ["P4-MEDIA", "P7-BUILD"])

    def test_signed_rail_lines_validate_for_both_phases(self):
        runner._stub_rail_media_emit(self.rd)
        receipt = {"pages": [{"page_type": "main", "preview_url": "https://app.rail.test/p/main"}]}
        import prove_sf_build as build
        stub.emit_rail(self.rd, "P7-BUILD", build.rail_rows(receipt))
        self.assertEqual(dr.rail_schema_problems(self.rd, "P4-MEDIA"), [])
        self.assertEqual(dr.rail_schema_problems(self.rd, "P7-BUILD"), [])

    def test_each_missing_or_malformed_field_is_named(self):
        runner._stub_rail_media_emit(self.rd)
        base = self.lines()[0]
        for field, bad in (("hosted_url", None), ("hosted_url", "ftp://x"), ("harness_sig", "short"),
                           ("covers", []), ("http_status", "200"), ("run_id", None)):
            line = copy.deepcopy(base)
            if bad is None:
                line.pop(field)
            else:
                line[field] = bad
            self.write_lines([line])
            problems = dr.rail_schema_problems(self.rd, "P4-MEDIA")
            self.assertTrue(any(field in p for p in problems), (field, bad, problems))

    def test_p7_line_needs_its_five_fields(self):
        import prove_sf_build as build
        receipt = {"pages": [{"page_type": "main", "preview_url": "https://app.rail.test/p/main"}]}
        for field in ("preview_url", "PASS", "checks", "dom_sha256", "screenshot_sha256"):
            (self.rd / dr.RECEIPTS_REL).unlink(missing_ok=True)
            rows = [(p, {k: v for k, v in f.items() if k != field}) for p, f in build.rail_rows(receipt)]
            stub.emit_rail(self.rd, "P7-BUILD", rows)
            self.assertTrue(any(field in p for p in dr.rail_schema_problems(self.rd, "P7-BUILD")), field)

    def test_an_unreadable_schema_is_a_problem_not_a_pass(self):
        runner._stub_rail_media_emit(self.rd)
        with mock.patch.object(dr, "RAIL_SCHEMA_PATH", self.rd / "no-such-schema.json"):
            self.assertTrue(dr.rail_schema_problems(self.rd, "P4-MEDIA"))
            ok, detail = dr.require_rail(self.rd, "P4-MEDIA", af="AF-X")
            self.assertFalse(ok)
            self.assertIn("AF-X-SCHEMA", detail)


class P4HostedUrlSeam(Run):
    def test_urls_equal_to_the_rails_hosted_url_pass(self):
        runner._stub_provider_emit(self.rd, "P3-IMAGES", ["kie_a", "kie_b"])
        runner._stub_rail_media_emit(self.rd)
        ok, detail = runner._gate_p4_media(self.rd)
        self.assertTrue(ok, detail)
        self.assertIn("equal the rail's hosted_url", detail)

    def test_no_receipt_store_fails_closed(self):
        ok, detail = runner._gate_p4_media(self.rd)
        self.assertFalse(ok)
        self.assertIn("ABSENT", detail)

    def test_a_ledger_url_the_rail_never_recorded_is_af_fun_deleg_media(self):
        runner._stub_rail_media_emit(self.rd)
        self.ledger["images"][0]["media_url"] = "https://cdn.elsewhere.test/a.png"
        (self.rd / "media_ledger.json").write_text(json.dumps(self.ledger), encoding="utf-8")
        ok, detail = runner._gate_p4_media(self.rd)
        self.assertFalse(ok)
        self.assertIn("AF-FUN-DELEG-MEDIA", detail)

    def test_a_host_name_is_no_longer_proof_of_anything(self):
        """A well-known GHL host in the ledger with no rail receipt behind it fails: no fingerprint remains."""
        led = {"images": [{"page_type": "main", "section": 1, "kie_task_id": "kie_a",
                           "media_url": "https://storage.gohighlevel.com/loc/x/a.png"}]}
        (self.rd / "media_ledger.json").write_text(json.dumps(led), encoding="utf-8")
        ok, detail = runner._gate_p4_media(self.rd)
        self.assertFalse(ok)
        stub.emit_rail(self.rd, "P4-MEDIA", [("kie_a", {"hosted_url": "https://media.rail.test/other.png"})])
        ok, detail = runner._gate_p4_media(self.rd)
        self.assertFalse(ok)
        self.assertIn("AF-FUN-DELEG-MEDIA", detail)

    def test_unsigned_edited_and_other_run_lines_fail(self):
        runner._stub_rail_media_emit(self.rd)
        good = self.lines()
        unsigned = [{k: v for k, v in x.items() if k != "harness_sig"} for x in good]
        self.write_lines(unsigned)
        self.assertIn("UNSIGNED", runner._gate_p4_media(self.rd)[1])
        edited = copy.deepcopy(good)
        edited[0]["hosted_url"] = "https://cdn.elsewhere.test/a.png"
        self.write_lines(edited)
        self.assertIn("forged", runner._gate_p4_media(self.rd)[1])
        other = Path(self._td.name) / "run-other"
        other.mkdir()
        (other / "media_ledger.json").write_text(json.dumps(self.ledger), encoding="utf-8")
        self.write_lines(good)
        (other / dr.RECEIPTS_REL).write_text((self.rd / dr.RECEIPTS_REL).read_text(encoding="utf-8"), encoding="utf-8")
        self.assertIn("UNSIGNED", runner._gate_p4_media(other)[1])

    def test_a_line_the_orchestrator_wrote_for_itself_is_refused(self):
        for img in self.ledger["images"]:
            dr.record(self.rd, phase="P4-MEDIA", provider="rail", operation="record",
                      provider_response_id="r-" + img["kie_task_id"], http_status=200,
                      remote_id="m-" + img["kie_task_id"], covers=[img["kie_task_id"]],
                      extra={"hosted_url": img["media_url"]})
        lines = self.lines()
        for line in lines:        # what a run that stamped its own evidence would carry
            line["recorded_by"] = "run_signature_funnel"
        self.write_lines(lines)
        self.assertFalse(runner._gate_p4_media(self.rd)[0])


class P9RechecksTheSameUrls(Run):
    def test_p9_binds_the_ledger_url_to_the_p4_receipt(self):
        runner._stub_rail_media_emit(self.rd)
        led = nopitch._valid_ledger()
        led["images"] = copy.deepcopy(self.ledger["images"])
        self.assertEqual(nopitch.evaluate_ledger(led, self.rd)[0], nopitch.EXIT_OK)
        led["images"][1]["media_url"] = "https://cdn.elsewhere.test/b.png"
        code, fails = nopitch.evaluate_ledger(led, self.rd)
        self.assertEqual(code, nopitch.EXIT_VIOLATION)
        self.assertIn("AF-FUN-IMG-HOST", [c for c, _ in fails])

    def test_ledger_only_mode_keeps_a_plain_shape_check(self):
        led = nopitch._valid_ledger()
        self.assertEqual(nopitch.evaluate_ledger(led)[0], nopitch.EXIT_OK)
        led["images"][0]["media_url"] = "https://example.com/x.png"
        self.assertEqual(nopitch.evaluate_ledger(led)[0], nopitch.EXIT_VIOLATION)

    def test_p9_with_a_run_dir_and_no_p4_receipts_fails_closed(self):
        code, fails = nopitch.evaluate_ledger(nopitch._valid_ledger(), self.rd)
        self.assertEqual(code, nopitch.EXIT_VIOLATION)
        self.assertIn("AF-FUN-IMG-HOST", [c for c, _ in fails])


class PhaseSpineAndBrief(unittest.TestCase):
    def test_labels_agree_in_both_files_and_name_the_receipt(self):
        want = {"P4-MEDIA": "delivery-rail receipt (P4)", "P7-BUILD": "delivery-rail receipt (P7)"}
        cert = dict(prove_sf_cert.EXPECTED_PHASES)
        with tempfile.TemporaryDirectory() as td:
            gates = {pid: prover for pid, prover, _ in runner._phase_gates(Path(td))}
        for pid, label in want.items():
            self.assertEqual(cert[pid], label)
            self.assertEqual(gates[pid], label)
        self.assertEqual(list(cert), [pid for pid, _, _ in runner._phase_gates(Path("."))])

    def test_the_brief_must_name_its_delivery_rail(self):
        persona_log = intake._VALID_PERSONA_LOG
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "hormozi-100m-offers").mkdir()
            with mock.patch.object(intake, "_persona_registry_dir", lambda: Path(td)):
                ok = intake._valid_runtime(3)
                self.assertEqual(intake.evaluate(ok, persona_log=persona_log), [])
                for bad in (None, "", "   ", 7):
                    brief = intake._valid_runtime(3)
                    if bad is None:
                        brief.pop("delivery_rail")
                    else:
                        brief["delivery_rail"] = bad
                    codes = [c for c, _ in intake.evaluate(brief, persona_log=persona_log)]
                    self.assertIn(intake.AF_MISSING, codes, bad)

    def test_the_intake_spec_documents_the_field(self):
        spec = json.loads((SKILL / "intake" / "sf-intake-questions.json").read_text(encoding="utf-8"))
        self.assertIn("delivery_rail", spec["runtime_intake_contract"]["required_fields"])

    def test_manifest_delegate_fields_and_titles(self):
        manifest = json.loads((SKILL / "FUNNEL-MANIFEST.json").read_text(encoding="utf-8"))
        phases = {p["id"]: p for p in manifest["phases"]}
        self.assertEqual(phases["P4-MEDIA"]["delegate"], DELEGATE)
        self.assertEqual(phases["P7-BUILD"]["delegate"], DELEGATE)
        pipeline = json.loads((REPO / "universal-sops/funnel-craft/FUNNEL-PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(pipeline["delivery_rail"]["owner"], "brief.delivery_rail")
        sop = (REPO / "universal-sops/funnel-craft/SOP-FUNNEL-04-BUILD.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(sop, "# SOP-FUNNEL-04: GHL MEDIA + FUNNEL BUILD (DELEGATED to the delivery rail named in the brief)")


class PersonaUsedGoesThroughOurOwnBoardClient(unittest.TestCase):
    ENV = {"COMMAND_CENTER_URL": "https://cc.example.test", "MC_API_TOKEN": "tok", "WEBHOOK_SECRET": "sec"}

    def test_no_board_or_no_voice_returns_false_and_never_raises(self):
        self.assertFalse(mc_board.report_persona_used("t1", voice_persona_id="v", env={}))
        self.assertFalse(mc_board.report_persona_used("", voice_persona_id="v", env=self.ENV))
        self.assertFalse(mc_board.report_persona_used("t1", env=self.ENV))

    def test_posts_the_persona_used_activity_bearer_only(self):
        seen = {}

        def fake(method, url, payload, cfg):
            seen.update(method=method, url=url, payload=payload, secret=cfg["secret"], token=cfg["token"])
            return 201, {"ok": True}
        with mock.patch.object(mc_board, "_request", fake):
            ok = mc_board.report_persona_used("t-9", page="main", voice_persona_id="hormozi-100m-offers",
                                              topic_persona_id="miller", blend_directive_sha="abc", goal="opt in",
                                              env=self.ENV)
        self.assertTrue(ok)
        self.assertEqual((seen["method"], seen["url"]), ("POST", "https://cc.example.test/api/tasks/t-9/activities"))
        self.assertEqual(seen["secret"], "")          # the activities route is bearer-authenticated
        self.assertEqual(seen["token"], "tok")
        meta = seen["payload"]["metadata"]
        self.assertEqual(meta, {"kind": "persona_used", "voice_persona_id": "hormozi-100m-offers", "page": "main",
                                "topic_persona_id": "miller", "blend_directive_sha": "abc", "goal": "opt in"})
        self.assertEqual(seen["payload"]["activity_type"], "updated")

    def test_http_error_and_exception_are_swallowed(self):
        with mock.patch.object(mc_board, "_request", lambda *a, **k: (500, None)):
            self.assertFalse(mc_board.report_persona_used("t", voice_persona_id="v", env=self.ENV))
        def boom(*a, **k):
            raise OSError("down")
        with mock.patch.object(mc_board, "_request", boom):
            self.assertFalse(mc_board.report_persona_used("t", voice_persona_id="v", env=self.ENV))

    def test_the_copy_seam_uses_mc_board_and_imports_no_sibling_board_module(self):
        calls = []
        bundle = {"voice_persona_id": "hormozi-100m-offers", "topic_persona_id": "miller",
                  "task_personas": [{"persona_id": "t1"}]}
        with mock.patch.object(mc_board, "report_persona_used", lambda tid, **kw: calls.append((tid, kw)) or True):
            self.assertTrue(seam.report_persona_used_to_card("task-1", bundle, page="main", goal="g", env={}))
        self.assertEqual(calls[0][0], "task-1")
        self.assertEqual(calls[0][1]["voice_persona_id"], "hormozi-100m-offers")
        self.assertEqual(calls[0][1]["task_persona_id"], "t1")
        self.assertNotIn("cc" + "_board", sys.modules)
        self.assertFalse(hasattr(seam, "_load_cc" + "_board_module"))
        self.assertFalse(seam.report_persona_used_to_card("", bundle))


class DocLockstep(unittest.TestCase):
    """M9-style lockstep for issue 84: the docs name the operator key, never a run-scoped nonce."""
    DOCS = ("49-signature-funnel/SKILL.md", "49-signature-funnel/FUNNEL-MANIFEST.json",
            "universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md",
            "universal-sops/funnel-craft/MASTER-FUNNEL-QC-AUTOFAIL-RULESET.md",
            "universal-sops/funnel-craft/FUNNEL-PIPELINE-MANIFEST.json", "universal-sops/funnel-craft/README.md",
            "49-signature-funnel/MASTERDOC.md")
    STALE = re.compile(r"run-scoped[ -]0600|0600[ -]nonce|front-door[ -]nonce|run-scoped front-door|for the nonce\b",
                       re.IGNORECASE)

    def test_no_doc_describes_a_run_scoped_nonce_the_code_refuses(self):
        for rel in self.DOCS:
            text = (REPO / rel).read_text(encoding="utf-8")
            self.assertIsNone(self.STALE.search(text), (rel, self.STALE.search(text)))

    def test_the_docs_say_the_certificate_is_keyed_by_the_operator_key(self):
        for rel in ("49-signature-funnel/SKILL.md", "49-signature-funnel/FUNNEL-MANIFEST.json"):
            self.assertIn("operator key", (REPO / rel).read_text(encoding="utf-8"), rel)
        self.assertIn("a caller-supplied nonce is refused", (SKILL / "FUNNEL-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn("operator key", (REPO / "universal-sops/funnel-craft/SOP-FUNNEL-05-CERTIFY.md").read_text(encoding="utf-8"))

    def test_the_code_really_refuses_a_nonce(self):
        with tempfile.TemporaryDirectory() as td:
            ok, msg = runner._check_front_door(Path(td), "n0nce", None)
        self.assertFalse(ok)
        self.assertIn("AF-FUN-FRONT-DOOR", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
