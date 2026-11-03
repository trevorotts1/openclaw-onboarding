"""Legacy Skill 49 structure proofs read the BUILT pages and tool runs, not the agent's ledgers.

STR-18  P5 parses each fragment for the profile's section markers (a fragment of 'x' fails);
        P7 recomputes QC from a Skill 6 tool run and re-runs ghl_gate.require_pass on the
        evidence root (a receipt that only says qc_score 9.0 fails); preview URLs must be ones
        a passing verify record checked.
STR-19  P1 derives the required page types from the locked funnel size (main-only fails).
IMG-16  P7, which the orchestrator runs before it certifies, needs wireframes and mockups
        for every page (legacy_downsell_images.py output): no visual direction, no certificate.
Run: python3 -m pytest 49-signature-funnel/scripts/test_legacy_structure_proofs.py -q
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
for p in (str(SCRIPTS), str(SKILL)):
    if p not in sys.path:
        sys.path.insert(0, p)

import prove_sf_build as build  # noqa: E402
import prove_sf_copy as copy_  # noqa: E402
import run_signature_funnel as runner  # noqa: E402

STRUCTURE = copy_._load_structure(None)
OPERATOR_KEY = "structure-proofs-operator-key-0123456789abcdef"


def codes(violations):
    return [c for c, _ in violations]


class Tmp(unittest.TestCase):
    def tmp(self):
        d = tempfile.mkdtemp(prefix="sf_structure_proofs_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return pathlib.Path(d)

    def isolate_gate_state(self, with_operator_key=False):
        """Keep the Skill 6 run-nonce files (and, for the orchestrator, the operator key) in a
        throwaway dir outside every run dir, never in the real HOME."""
        state = self.tmp()
        env = {"GHL_VERIFY_NONCE_DIR": str(state / "nonces")}
        if with_operator_key:
            key_file = state / "operator.key"
            key_file.write_text(OPERATOR_KEY + "\n", encoding="utf-8")
            key_file.chmod(0o600)
            env["SF_OPERATOR_KEY_FILE"] = str(key_file)
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def setUp(self):
        self.isolate_gate_state()

    def run_dir(self, size):
        rd = self.tmp()
        build.write_valid_run_evidence(rd, size)
        return rd


class P1PageSetTests(Tmp):
    def test_main_only_ledger_for_a_seven_step_funnel_flags_every_absent_page_type(self):
        ledger = copy_._valid_ledger(7)
        ledger["pages"] = ledger["pages"][:1]  # main only
        v, _ = copy_.verify(STRUCTURE, ledger)
        missing = [m for c, m in v if c == "AF-FUN-SECTION-MISSING"]
        absent = ["upsell", "downsell", "upsell-2", "downsell-2", "thank-you"]
        self.assertEqual(len(missing), len(absent), v)
        for page_type in absent:
            self.assertTrue(any(f"'{page_type}'" in m for m in missing), (page_type, missing))

    def test_complete_ledgers_pass_for_every_size(self):
        for size in (3, 5, 7):
            v, _ = copy_.verify(STRUCTURE, copy_._valid_ledger(size))
            self.assertEqual(v, [], (size, v))

    def test_ledger_may_not_describe_a_smaller_funnel_than_the_locked_brief(self):
        v, _ = copy_.verify(STRUCTURE, copy_._valid_ledger(3), funnel_size=7)
        self.assertIn("AF-FUN-SECTION-MISSING", codes(v))

    def test_unresolvable_size_fails_closed(self):
        ledger = copy_._valid_ledger(3)
        del ledger["funnel_size"]
        v, _ = copy_.verify(STRUCTURE, ledger)
        self.assertIn("AF-FUN-SECTION-MISSING", codes(v))

    def test_cli_takes_the_locked_size_from_the_brief_beside_the_ledger(self):
        rd = self.tmp()
        (rd / "brief.json").write_text(json.dumps({"funnel_size": 7}))
        ledger = copy_._valid_ledger(3)  # declares 3, passes alone
        (rd / "copy_ledger.json").write_text(json.dumps(ledger))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "prove_sf_copy.py"), "--ledger",
                               str(rd / "copy_ledger.json")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("AF-FUN-SECTION-MISSING", proc.stdout)
        (rd / "brief.json").write_text(json.dumps({"funnel_size": 3}))
        proc = subprocess.run([sys.executable, str(SCRIPTS / "prove_sf_copy.py"), "--ledger",
                               str(rd / "copy_ledger.json")], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)


class P5FragmentTests(Tmp):
    def frag_codes(self, rd, size=5):
        return codes(build.html_fragment_violations(rd, size))

    def test_valid_fragments_pass(self):
        for size in (3, 5, 7):
            self.assertEqual(self.frag_codes(self.run_dir(size), size), [], size)

    def test_a_fragment_containing_x_fails(self):
        rd = self.run_dir(5)
        (rd / "pages" / "main.fragment.html").write_text("x")
        self.assertIn("AF-FUN-HTML-SECTIONS", self.frag_codes(rd))

    def test_a_fragment_with_the_wrong_section_count_fails(self):
        rd = self.run_dir(5)
        path = rd / "pages" / "main.fragment.html"
        path.write_text(path.read_text().replace('data-section="12"', 'data-x="12"'))
        self.assertIn("AF-FUN-HTML-SECTIONS", self.frag_codes(rd))

    def test_thank_you_needs_its_three_markers(self):
        rd = self.run_dir(5)
        path = rd / "pages" / "thank-you.fragment.html"
        path.write_text(path.read_text().replace('data-section="TY-3"', 'data-x="TY-3"'))
        self.assertIn("AF-FUN-HTML-SECTIONS", self.frag_codes(rd))

    def test_a_marker_around_nothing_fails(self):
        rd = self.run_dir(5)
        path = rd / "pages" / "upsell.fragment.html"
        path.write_text(path.read_text().replace("upsell section 3 copy that carries real words.", ""))
        self.assertIn("AF-FUN-HTML-SECTIONS", self.frag_codes(rd))

    def test_a_missing_fragment_fails(self):
        rd = self.run_dir(5)
        (rd / "pages" / "downsell.fragment.html").unlink()
        self.assertIn("AF-FUN-HTML-FRAGMENT", self.frag_codes(rd))


class P7ToolRunTests(Tmp):
    def verify(self, rd, size=5, receipt=None):
        receipt = receipt or json.loads((rd / "build_receipt.json").read_text())
        return build.verify(receipt, funnel_size=size, run_dir=rd)[0]

    def test_complete_run_passes(self):
        self.assertEqual(self.verify(self.run_dir(5)), [])

    def test_receipt_saying_9_0_with_no_tool_run_record_fails(self):
        rd = self.run_dir(5)
        shutil.rmtree(rd / build.EVIDENCE_REL)
        receipt = json.loads((rd / "build_receipt.json").read_text())
        receipt["qc_score"] = 9.0
        self.assertIn("AF-FUN-BUILD-QC-RECORD", codes(self.verify(rd, receipt=receipt)))

    def test_cli_exits_2_for_that_receipt_and_0_with_the_record(self):
        rd = self.run_dir(5)
        cmd = [sys.executable, str(SCRIPTS / "prove_sf_build.py"), "--receipt",
               str(rd / "build_receipt.json"), "--funnel-size", "5"]
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True).returncode, 0)
        shutil.rmtree(rd / build.EVIDENCE_REL)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertIn("AF-FUN-BUILD-QC-RECORD", proc.stdout)

    def test_a_failing_verify_run_fails_even_with_a_9_receipt(self):
        rd = self.run_dir(5)
        path = rd / build.EVIDENCE_REL / "scorecard" / "verify-summary.json"
        summary = json.loads(path.read_text())
        summary["overall_pass"] = False
        path.write_text(json.dumps(summary))
        self.assertIn("AF-FUN-BUILD-QC-RECORD", codes(self.verify(rd)))

    def test_tampered_raw_log_fails_the_gate(self):
        rd = self.run_dir(5)
        path = rd / build.EVIDENCE_REL / "logs" / "final-preview-verify.json"
        path.write_text(path.read_text().replace('"PASS": true', '"PASS": false', 1))
        self.assertIn("AF-FUN-BUILD-QC-RECORD", codes(self.verify(rd)))

    def test_a_hand_written_summary_is_not_a_tool_run(self):
        rd = self.run_dir(5)
        path = rd / build.EVIDENCE_REL / "scorecard" / "verify-summary.json"
        summary = json.loads(path.read_text())
        summary["writer"] = "the agent"
        path.write_text(json.dumps(summary))
        self.assertIn("AF-FUN-BUILD-QC-RECORD", codes(self.verify(rd)))

    def test_a_preview_url_no_passing_record_checked_fails(self):
        rd = self.run_dir(5)
        receipt = json.loads((rd / "build_receipt.json").read_text())
        receipt["pages"][0]["preview_url"] = "https://app.gohighlevel.com/funnels/preview/never-visited"
        self.assertIn("AF-FUN-BUILD-PREVIEW-UNBOUND", codes(self.verify(rd, receipt=receipt)))

    def test_no_run_dir_fails_closed_on_every_evidence_code(self):
        v = build.verify(build._valid_receipt(5), funnel_size=5)[0]
        for code in ("AF-FUN-HTML-SECTIONS", "AF-FUN-BUILD-QC-RECORD", "AF-FUN-BUILD-PREVIEW-UNBOUND",
                     "AF-FUN-BUILD-VISUAL"):
            self.assertIn(code, codes(v))


class VisualDirectionTests(Tmp):
    def test_stage_names_match_the_tool_that_writes_them(self):
        import legacy_downsell_images
        self.assertEqual(build.VISUAL_STAGES, legacy_downsell_images.STAGES)

    def test_a_funnel_with_no_wireframe_or_mockup_set_fails(self):
        rd = self.run_dir(5)
        shutil.rmtree(rd / build.PAGE_IMAGES_REL)
        v = build.visual_direction_violations(rd, 5)
        self.assertEqual(set(codes(v)), {"AF-FUN-BUILD-VISUAL"})
        for page in ("main", "upsell", "downsell", "upsell-2", "thank-you"):
            self.assertTrue(any(f"page '{page}'" in m for _, m in v), page)

    def test_one_page_missing_one_stage_fails(self):
        rd = self.run_dir(5)
        (rd / build.PAGE_IMAGES_REL / "downsell" / "mobile-tablet" / "stage-executor-record.json").unlink()
        v = build.visual_direction_violations(rd, 5)
        self.assertEqual(len(v), 1, v)
        self.assertIn("downsell", v[0][1])

    def test_a_record_with_no_images_fails(self):
        rd = self.run_dir(5)
        rec = rd / build.PAGE_IMAGES_REL / "main" / "visual-mockup" / "stage-executor-record.json"
        rec.write_text(json.dumps({"images": []}))
        self.assertIn("AF-FUN-BUILD-VISUAL", codes(build.visual_direction_violations(rd, 5)))

    def test_a_record_edited_after_the_tool_receipt_fails(self):
        rd = self.run_dir(5)
        rec = rd / build.PAGE_IMAGES_REL / "main" / "desktop-wireframe" / "stage-executor-record.json"
        rec.write_text(json.dumps({"images": [{"id": "a"}, {"id": "b"}]}))
        self.assertIn("AF-FUN-BUILD-VISUAL", codes(build.visual_direction_violations(rd, 5)))

    def test_seven_step_checkout_needs_the_receipt_to_name_it_not_built(self):
        rd = self.run_dir(7)
        self.assertEqual(build.visual_direction_violations(rd, 7), [])
        receipt_path = rd / build.PAGE_IMAGES_REL / build.PAGE_IMAGES_RECEIPT
        receipt = json.loads(receipt_path.read_text())
        receipt["not_built"] = {}
        receipt_path.write_text(json.dumps(receipt))
        self.assertTrue(any("'checkout'" in m for _, m in build.visual_direction_violations(rd, 7)))


class OrchestratorCertifyTests(Tmp):
    """run_signature_funnel certify, end to end: each broken input aborts with NO certificate."""

    def setUp(self):
        self.isolate_gate_state(with_operator_key=True)

    def orchestrate(self, rd):
        with mock.patch.object(runner, "_mc_board_phase", lambda *a, **k: None), \
                mock.patch.object(runner, "_resolve_persona", lambda *a, **k: None):
            with mock.patch("sys.stdout"):
                return runner.orchestrate(rd, OPERATOR_KEY)

    def run_for(self, size=3):
        rd = self.tmp()
        runner._write_valid_run(rd, OPERATOR_KEY, size=size)
        (rd / "copy_ledger.json").write_text(json.dumps(copy_._valid_ledger(size)))
        build.write_valid_run_evidence(rd, size)
        return rd

    def assert_aborts_at(self, rd, phase):
        code, manifest = self.orchestrate(rd)
        self.assertEqual(code, runner.EXIT_GATE_FAIL, manifest)
        self.assertEqual(manifest.get("aborted_at"), phase, manifest)
        self.assertFalse((rd / "PROCESS-CERTIFICATE.json").exists())

    def test_a_complete_funnel_certifies(self):
        rd = self.run_for(3)
        code, _ = self.orchestrate(rd)
        self.assertEqual(code, runner.EXIT_OK)
        self.assertTrue((rd / "PROCESS-CERTIFICATE.json").exists())

    def test_no_visual_direction_means_no_certificate(self):
        rd = self.run_for(3)
        shutil.rmtree(rd / build.PAGE_IMAGES_REL)
        self.assert_aborts_at(rd, "P7-BUILD")

    def test_a_page_with_no_wireframe_or_mockup_set_means_no_certificate(self):
        rd = self.run_for(3)
        shutil.rmtree(rd / build.PAGE_IMAGES_REL / "upsell")
        self.assert_aborts_at(rd, "P7-BUILD")

    def test_an_x_fragment_never_certifies(self):
        rd = self.run_for(3)
        (rd / "pages" / "main.fragment.html").write_text("x")
        self.assert_aborts_at(rd, "P7-BUILD")

    def test_a_receipt_saying_9_0_with_no_tool_run_never_certifies(self):
        rd = self.run_for(3)
        shutil.rmtree(rd / build.EVIDENCE_REL)
        self.assert_aborts_at(rd, "P7-BUILD")

    def test_a_main_only_copy_ledger_aborts_at_p1(self):
        rd = self.run_for(7)
        ledger = copy_._valid_ledger(7)
        ledger["pages"] = ledger["pages"][:1]
        (rd / "copy_ledger.json").write_text(json.dumps(ledger))
        self.assert_aborts_at(rd, "P1-COPY")


if __name__ == "__main__":
    unittest.main()
