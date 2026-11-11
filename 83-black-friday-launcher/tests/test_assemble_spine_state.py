"""Issues 29, 36, 37 and 88 at the `assemble` command: the step spine reads STATE, not file presence.

Before: the spine closed on "every declared artifact exists", `assemble` threw away every check violation but the
byte-level ones, and a package whose graphics handoff had failed still emitted `stage_closed` to Command Center.
Now:

* `_close_step_spine` refuses a step whose artifact says ``"state": "failed"`` (graphics-handoff.json included) or
  that declares a failed state (``AF-LAUNCH-STEP-FAILED``), exactly as it refuses a missing artifact;
* `_handoff_blockers`: for a client delivery (test_only false) EVERY violation `check` would print blocks the
  handoff, and an unverified package blocks it with no violation to name;
* a refused spine emits `stage_blocked`, never `stage_closed`;
* `assemble` writes check-result.json from the same check_package run, and a practice package says so at its root.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
for entry in (SKILL_ROOT, SKILL_ROOT / "routes", SKILL_ROOT / "fixtures", HERE):
    sys.path.insert(0, str(entry))

import test_l26_delivery_scope as l26  # noqa: E402  (module reference: its TestCases are not collected twice)
from launcher_core import cli, graphics_hooks, package  # noqa: E402
from test_lane83_designs import make_piece  # noqa: E402

setUpModule, tearDownModule = l26.setUpModule, l26.tearDownModule  # launch events go to a temp spool


class SpineStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def artifact(self, name: str, doc) -> str:
        path = self.out / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def test_a_present_artifact_that_records_its_own_failure_keeps_the_spine_open(self):
        handoff = self.artifact("graphics-handoff.json", {"state": "failed", "reason": "OSError: disk full"})
        with self.assertRaises(package.PackageError) as ctx:
            cli._close_step_spine(self.out, [{"step": "graphics-handoff", "required": True, "artifacts": [handoff]}])
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-STEP-FAILED")
        self.assertIn("graphics-handoff", ctx.exception.detail)
        record = json.loads((self.out / "assemble-steps.json").read_text(encoding="utf-8"))
        self.assertFalse(record["closed"])
        self.assertEqual(record["steps"][0]["status"], "failed")

    def test_a_step_that_declares_a_failed_state_keeps_the_spine_open(self):
        manifest = self.artifact("package-manifest.json", {})
        with self.assertRaises(package.PackageError) as ctx:
            cli._close_step_spine(self.out, [{"step": "assemble", "required": True, "state": "failed",
                                              "artifacts": [manifest]}])
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-STEP-FAILED")

    def test_control_a_step_in_any_other_state_closes(self):
        # same instrument, same files: only the recorded state differs from the refusals above
        handoff = self.artifact("graphics-handoff.json", {"hosting": {"state": "not_authorized"}, "delivery": {}})
        manifest = self.artifact("package-manifest.json", {})
        for state in ("verified", "practice", None):
            with self.subTest(state=state):
                record = cli._close_step_spine(self.out, [
                    {"step": "assemble", "required": True, "state": state, "artifacts": [manifest]},
                    {"step": "graphics-handoff", "required": True, "artifacts": [handoff]}])
                self.assertTrue(record["closed"])

    def test_a_missing_artifact_still_keeps_its_own_code(self):
        with self.assertRaises(package.PackageError) as ctx:
            cli._close_step_spine(self.out, [{"step": "assemble", "required": True,
                                              "artifacts": [str(self.out / "never-written.json")]}])
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-STEP-ARTIFACT")

    def test_a_non_json_artifact_is_not_read_for_a_state(self):
        page = self.out / "page.html"
        page.write_text('<p>"state": "failed"</p>', encoding="utf-8")
        self.assertTrue(cli._close_step_spine(self.out, [{"step": "x", "required": True,
                                                          "artifacts": [str(page)]}])["closed"])


class HandoffBlockerTests(unittest.TestCase):
    QC = "AF-LAUNCH-IMAGE-QC: landing hero.png has no record in qc/image_qc_report.json (100 percent coverage)"
    BYTES = "AF-LAUNCH-PKG-HASH: landing artifact 'pieces/a/page.html' sha256 abc != def"

    def verification(self, state, *violations):
        return {"state": state, "violations": list(violations)}

    def test_a_client_package_is_blocked_by_a_violation_the_old_filter_discarded(self):
        # The old `broken` filter kept only artifact/receipt/manifest byte problems; this QC miss passed it.
        self.assertEqual(cli._handoff_blockers(self.verification("failed", self.QC), test_only=False), [self.QC])

    def test_a_client_package_with_every_violation_gone_and_a_verified_state_may_be_handed_off(self):
        self.assertEqual(cli._handoff_blockers(self.verification("verified"), test_only=False), [])

    def test_a_client_package_that_did_not_verify_is_blocked_even_with_no_violation_to_name(self):
        blockers = cli._handoff_blockers(self.verification("failed"), test_only=False)
        self.assertEqual(len(blockers), 1)
        self.assertIn("not 'verified'", blockers[0])

    def test_a_practice_package_keeps_the_byte_level_filter_only(self):
        self.assertEqual(cli._handoff_blockers(self.verification("failed", self.QC), test_only=True), [])
        self.assertEqual(cli._handoff_blockers(self.verification("failed", self.QC, self.BYTES), test_only=True), [])
        moved = "AF-LAUNCH-PKG-HASH: landing artifact 'pieces/a/page.html' does not match: artifact bytes moved"
        self.assertEqual(cli._handoff_blockers(self.verification("failed", self.QC, moved), test_only=True), [moved])


class CliAssembleTests(l26._Base):
    """`assemble` on the command line over a practice package (the client path needs a real dispatch run)."""

    def setUp(self):
        super().setUp()
        self.intake_path = Path(self.tmp.name) / "intake.json"
        self.intake_path.write_text(json.dumps(l26.base_intake()), encoding="utf-8")
        designs = Path(self.tmp.name) / "designs"
        designs.mkdir()
        for node in self.graph["nodes"]:
            piece = make_piece(designs, self.normalized, node)
            (self.run_dir / "pieces" / f"{node['role']}.json").write_text(json.dumps(piece), encoding="utf-8")

    def assemble(self, *extra):
        stdout, stderr, events = io.StringIO(), io.StringIO(), []
        argv = ["assemble", "--intake", str(self.intake_path), "--pieces", str(self.run_dir / "pieces"),
                "--out", str(self.run_dir), "--page-only", *extra]
        with mock.patch.object(cli.council, "planning_step", return_value=self.advice), \
                mock.patch.object(cli, "_launch_event", side_effect=lambda _id, ev: events.append(ev)), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue(), [e.get("event_type") for e in events]

    def test_a_failed_graphics_handoff_refuses_the_spine_and_stage_closed_is_never_emitted(self):
        with mock.patch.object(graphics_hooks, "handle_handoff", side_effect=OSError("disk full")):
            rc, out, err, events = self.assemble()
        self.assertEqual(rc, 2, err)
        self.assertIn("AF-LAUNCH-STEP-FAILED", err)
        self.assertIn("stage_blocked", events)
        self.assertNotIn("stage_closed", events)
        handoff = json.loads((self.run_dir / "graphics-handoff.json").read_text(encoding="utf-8"))
        self.assertEqual(handoff["state"], "failed")  # the failure is still recorded
        self.assertEqual(out.strip(), "")  # a refused assembly emits nothing

    def test_control_the_same_assemble_with_a_working_handoff_closes_the_stage(self):
        rc, out, err, events = self.assemble()
        self.assertEqual(rc, 0, err)
        self.assertIn("stage_closed", events)
        self.assertNotIn("stage_blocked", events)

    def test_assemble_writes_check_result_from_the_check_it_just_ran(self):
        rc, out, err, _events = self.assemble()
        self.assertEqual(rc, 0, err)
        record = json.loads((self.run_dir / graphics_hooks.CHECK_RESULT_REL).read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], graphics_hooks.CHECK_RESULT_SCHEMA)
        self.assertEqual(record["manifest"]["sha256"],
                         graphics_hooks._sha(self.run_dir / "package-manifest.json"))
        self.assertEqual(json.loads(out)["package_check"], {"passed": record["passed"], "path": "check-result.json"})
        # the fake consumer's practice package passes its own check, so this one is a pass: the record says so
        self.assertEqual((record["passed"], record["violation_count"]), (True, 0), record["violations"][:3])

    def test_a_failed_check_is_recorded_as_failed_with_its_violations(self):
        failed = {"state": "failed", "violations": ["AF-LAUNCH-IMAGE-QC: landing hero.png has no record"],
                  "artifacts_checked": 0, "units": {}}
        with mock.patch.object(cli.checks, "verify_package_receipt", return_value=failed):
            rc, out, err, _events = self.assemble()
        self.assertEqual(rc, 0, err)  # a practice package is not blocked by a review it never had
        record = json.loads((self.run_dir / graphics_hooks.CHECK_RESULT_REL).read_text(encoding="utf-8"))
        self.assertEqual((record["passed"], record["violation_count"]), (False, 1))
        self.assertEqual(record["violations"], failed["violations"])

    def test_hosting_named_on_the_command_line_is_refused_for_a_package_that_failed_its_check(self):
        uploader = mock.Mock(side_effect=AssertionError("the uploader must never run on an unchecked package"))
        failed = {"state": "failed", "violations": ["AF-LAUNCH-IMAGE-QC: landing hero.png has no record"],
                  "artifacts_checked": 0, "units": {}}
        with mock.patch.object(graphics_hooks, "_load_module", return_value=mock.Mock(push_graphics_media=uploader)), \
                mock.patch.object(cli.checks, "verify_package_receipt", return_value=failed):
            rc, out, err, _events = self.assemble("--host-media", "APPR-HOST-1")
        self.assertEqual(rc, 0, err)
        hosting = json.loads(out)["graphics"]["hosting"]
        self.assertEqual(hosting["state"], "needs_check")
        uploader.assert_not_called()

    def test_a_practice_package_says_so_at_its_root(self):
        rc, _out, err, _events = self.assemble()
        self.assertEqual(rc, 0, err)
        note = (self.run_dir / package.PRACTICE_PACKAGE_REL).read_text(encoding="utf-8")
        self.assertIn("PRACTICE PACKAGE", note)
        self.assertIn("never hand it to the client", note.lower())
        manifest = json.loads((self.run_dir / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertIs(manifest["test_only"], True)


if __name__ == "__main__":
    unittest.main()
