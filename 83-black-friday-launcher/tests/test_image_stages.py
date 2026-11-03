"""U-images-05 (IMG-01, IMG-12): real image stages after dispatch, and a check that refuses without them.

Free: no provider, no network. The Skill 71 commands are replaced by a recording fake runner that
behaves like the gate (a stage opens only when the one before it is closed; a Design Board without a
recorded approval never lets final-mockups start); the check rule is run on a real stub package.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks, cli, graphics_hooks, image_stages  # noqa: E402
from launcher_core.image_stages import STAGES  # noqa: E402
from test_lane83_designs import Base  # noqa: E402  (a real stub-provider package, no tests of its own)

RULE_FILE = SKILL_ROOT / "launcher_core" / "check_rules" / "image_qc.py"
SKILL71 = SKILL_ROOT.parent / "71-blackceo-signature-page"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
       b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00"
       b"\x00\x00IEND\xaeB`\x82")


def write(path: Path, data="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def close_stage(run: Path, stage: str):
    """What stage_gate.py close leaves behind: state, a pass receipt and the artifact hashes."""
    art = write(run / stage / "artifact.txt", f"{stage} done")
    state_path = run / "private" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {"stages": {}, "receipts": {}}
    state["stages"][stage] = {"status": "closed", "receipt_status": "pass",
                              "artifact_hashes": {f"{stage}/artifact.txt": hashlib.sha256(art.read_bytes()).hexdigest()}}
    write(state_path, json.dumps(state))
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps({"status": "pass"}))


def make_run(root: Path, name: str, role: str, closed=()) -> Path:
    run = root / "dispatch" / name
    write(run / "intake.json", json.dumps({"page_role": role, "copy_version": "standard"}))
    write(run / "desktop-wireframe" / "image-inventory.json", json.dumps({"images": [{"id": "IMG-001"}, {"id": "IMG-002"}]}))
    write(run / "copy" / "internal-manuscript.md", "# copy")
    write(run / "private" / "state.json", json.dumps({"stages": {}, "receipts": {}}))
    for stage in closed:
        close_stage(run, stage)
    return run


class FakeSkill71:
    """Records every command and answers like Skill 71's gate and executor would."""

    def __init__(self):
        self.calls = []
        self.client_approved = set()

    def __call__(self, argv):
        script, args = Path(argv[1]).name, [str(a) for a in argv[2:]]
        self.calls.append((script, args))
        run = Path(next(a for a in args if "/" in a))
        if script == "stage_gate.py":
            verb, stage = args[0], args[2]
            if verb == "check":  # the dependency chain: every earlier stage must be closed
                before = STAGES[:STAGES.index(stage)]
                bad = [s for s in before if not image_stages.stage_closed(run, s)]
                return (1, f"stage {stage} cannot start: dependency {bad[0]} is not closed") if bad else (0, "")
            close_stage(run, stage)
            return 0, ""
        if script == "stage_executor.py":
            if "--item" in args:
                item = args[args.index("--item") + 1]
                write(run / "image-generation-qc" / f"Image-{item[-2:]}.png", PNG)
            elif "design-board" in args:
                write(run / "design-board" / "design-board.png", PNG)
            else:
                write(run / "final-mockups" / "stage-executor-record.json", "{}")
            return 0, ""
        if script == "design_board.py":
            return (0, "") if run in self.client_approved else (1, "no recorded client approval")
        if script == "build_production_request.py":
            write(Path(args[args.index("--out") + 1]), "{}")
            return 0, ""
        raise AssertionError(f"unexpected command {script}")

    def ran(self, script, needle=None):
        return [a for s, a in self.calls if s == script and (needle is None or needle in a)]


def approve_layout(root: Path):
    write(root / image_stages.LAYOUT_APPROVAL_REL, json.dumps({"approval_ref": "client-msg-1"}))


def author(run: Path):
    for item in ("IMG-001", "IMG-002"):
        write(run / "image-inventory-prompts" / f"{item}.txt", "prompt")
    write(run / "image-map-upload" / "image-map.json", "{}")


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def drive(self, fake, **kw):
        return image_stages.drive(self.root, runner=fake, **kw)

    def test_the_five_stages_are_skill_71s_own_in_its_order(self):
        order = json.loads((SKILL71 / "references" / "stage-contract.json").read_text())["stage_order"]
        self.assertEqual(list(STAGES), [s for s in order if s in STAGES])
        self.assertEqual(STAGES[-2:], ("design-board", "final-mockups"))
        for script in ("stage_gate.py", "stage_executor.py", "design_board.py", "build_production_request.py"):
            self.assertTrue((image_stages.scripts_dir() / script).is_file(), script)

    def test_layout_proofs_are_the_first_checkpoint_nothing_runs_before_the_clients_approval(self):
        make_run(self.root, "landing", "landing")
        fake = FakeSkill71()
        report = self.drive(fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(report["pages"][0]["status"], "awaiting_layout_proof_approval")
        self.assertFalse(report["complete"])
        self.assertTrue((self.root / image_stages.REPORT_REL).is_file())

    def test_stages_run_in_order_stop_at_the_design_board_and_final_mockups_waits_for_the_client(self):
        approve_layout(self.root)
        run = make_run(self.root, "landing", "landing")
        author(run)
        fake = FakeSkill71()
        report = self.drive(fake)
        page = report["pages"][0]
        self.assertEqual(page["stages"], {"image-inventory-prompts": "closed", "image-generation-qc": "closed",
                                          "image-map-upload": "closed", "design-board": "open",
                                          "final-mockups": "open"})
        self.assertEqual(page["status"], "awaiting_client_approval")
        self.assertEqual([a[2] for a in fake.ran("stage_gate.py", "close")],
                         ["image-inventory-prompts", "image-generation-qc", "image-map-upload"])
        self.assertEqual(len(fake.ran("stage_executor.py", "--item")), 2)  # one drawing per inventory slot
        self.assertEqual(fake.ran("stage_executor.py", "final-mockups"), [])  # never started
        self.assertEqual(fake.ran("build_production_request.py"), [])
        self.assertFalse(report["complete"])
        # the client approves the board (their act, recorded by design_board.py); the next run finishes
        fake.client_approved.add(run.resolve())
        again = self.drive(fake)
        self.assertEqual(set(again["pages"][0]["stages"].values()), {"closed"})
        self.assertTrue(again["complete"])
        self.assertEqual(len(fake.ran("build_production_request.py")), 1)  # its request, built once the board is approved
        self.assertEqual(fake.ran("stage_executor.py", "final-mockups")[0][-2:], ["--provider", "stub"])

    def test_unauthored_prompts_stop_the_page_by_name_and_nothing_is_drawn(self):
        approve_layout(self.root)
        make_run(self.root, "upsell", "upsell_1")
        fake = FakeSkill71()
        page = self.drive(fake)["pages"][0]
        self.assertEqual(page["status"], "needs_authoring")
        self.assertIn("IMG-001", page["reason"])
        self.assertEqual(fake.ran("stage_executor.py"), [])

    def test_a_failing_gate_close_blocks_the_page_and_is_reported_not_hidden(self):
        approve_layout(self.root)
        run = make_run(self.root, "landing", "landing")
        author(run)

        def refuse_close(argv):
            if Path(argv[1]).name == "stage_gate.py" and argv[2] == "close":
                return 1, "review missing"
            return FakeSkill71()(argv)

        page = self.drive(refuse_close)["pages"][0]
        self.assertEqual((page["status"], page["stages"]["image-inventory-prompts"]), ("blocked", "open"))
        self.assertIn("review missing", page["reason"])

    def test_a_stage_changed_after_it_closed_no_longer_counts_as_closed(self):
        run = make_run(self.root, "landing", "landing", closed=STAGES)
        self.assertTrue(all(image_stages.stage_closed(run, s) for s in STAGES))
        write(run / "final-mockups" / "artifact.txt", "swapped after close")
        self.assertFalse(image_stages.stage_closed(run, "final-mockups"))

    def test_the_command_line_exits_non_zero_until_every_page_is_closed(self):
        make_run(self.root, "landing", "landing")
        done = subprocess.run([sys.executable, "-m", "launcher_core.image_stages", "--run-dir", str(self.root)],
                              cwd=SKILL_ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("layout proofs are the first approval checkpoint", done.stdout)
        approve_layout(self.root)
        make_run(self.root, "landing", "landing", closed=STAGES)
        ok = subprocess.run([sys.executable, "-m", "launcher_core.image_stages", "--run-dir", str(self.root)],
                            cwd=SKILL_ROOT, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)


class ReportViolationTests(unittest.TestCase):
    """IMG-12: check_package-side rule for qc/image_qc_report.json (SOP-GIP-02)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = write(self.root / "desktop-wireframes" / "landing_desktop_wireframe_s1-of-1_hero.png", PNG)
        self.manifest = {"pieces": [{"role": "landing", "artifacts": [
            {"path": "desktop-wireframes/" + self.image.name, "kind": "wireframe_desktop_section", "provider": "stub"}]}]}

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, **rec):
        record = {"local_path": str(self.image), "asset_id": self.image.stem, "average": 9.1, "pass": True,
                  "triggered_autofails": []}
        record.update(rec)
        write(self.root / graphics_hooks.QC_REPORT_REL, json.dumps({"assets": [record]}))

    def fails(self):
        return graphics_hooks.report_violations(self.manifest, self.root)

    def test_a_missing_report_fails(self):
        self.assertIn("image_qc_report.json is missing", self.fails()[0])

    def test_a_clean_report_passes(self):
        self.report()
        self.assertEqual(self.fails(), [])

    def test_an_average_under_the_bar_fails(self):
        self.report(average=8.4)
        self.assertTrue(any("under the 8.5 bar" in f for f in self.fails()), self.fails())

    def test_an_automatic_failure_fails_even_with_a_high_average(self):
        self.report(triggered_autofails=["AF-G1"])
        self.assertTrue(any("AF-G1" in f for f in self.fails()), self.fails())

    def test_an_average_that_is_not_a_number_fails(self):
        for bad in (True, "9.5", None, float("nan")):
            self.report(average=bad)
            self.assertTrue(any("no numeric average" in f for f in self.fails()), bad)

    def test_an_image_the_report_leaves_out_fails_full_coverage(self):
        self.report(local_path=str(self.root / "elsewhere.png"))
        self.assertTrue(any("has no record" in f for f in self.fails()), self.fails())

    def test_an_image_changed_after_review_fails(self):
        self.report(sha256="0" * 64)
        self.assertTrue(any("changed after it was reviewed" in f for f in self.fails()), self.fails())


class PackageCheckTests(Base):
    """IMG-01 and IMG-12 proofs on a real stub-provider package: it fails until every stage is closed."""

    def rule(self):
        spec = importlib.util.spec_from_file_location("launcher_core.check_rules.image_qc", RULE_FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.violations

    def package(self):
        built = self.assemble(self.pieces())
        root = self.work / "pkg"
        return json.loads(Path(built["manifest_path"]).read_text()), root, built

    def close_every_page(self, manifest, root, stages=STAGES, skip=None):
        pages = []
        for n, piece in enumerate(manifest["pieces"]):
            run = make_run(self.work, f"run-{n}", piece["role"], closed=[s for s in stages if (n, s) != skip])
            pages.append({"page": run.name, "role": piece["role"], "run_dir": str(run)})
        write(root / image_stages.REPORT_REL, json.dumps({"pages": pages}))

    def write_clean_qc(self, manifest, root):
        assets = [{"local_path": i["local_path"], "asset_id": i["asset_id"], "average": 9.0, "pass": True,
                   "triggered_autofails": []} for i in graphics_hooks.collect_images(manifest, root)]
        write(root / graphics_hooks.QC_REPORT_REL, json.dumps({"assets": assets}))

    def launched(self, root):
        """The mark a launch dispatch leaves in the package root."""
        write(root / "dispatch-report.json", "{}")

    def test_the_layout_proof_package_fails_with_no_stage_report_and_no_qc_report(self):
        manifest, root, _ = self.package()
        self.launched(root)
        fails = self.rule()(manifest, root, SKILL_ROOT)
        self.assertTrue(any("image_stages_report.json is missing" in f and "layout proofs only" in f for f in fails), fails)
        self.assertTrue(any("image_qc_report.json is missing" in f for f in fails), fails)

    def test_a_paid_package_always_needs_its_stages_and_qc_report(self):
        manifest, root, _ = self.package()
        fails = self.rule()(dict(manifest, test_only=False), root, SKILL_ROOT)
        self.assertTrue(any(f.startswith("AF-LAUNCH-IMAGE-STAGES") for f in fails), fails)
        self.assertTrue(any(f.startswith("AF-LAUNCH-IMAGE-QC") for f in fails), fails)

    def test_a_bare_stub_package_stays_images_only_until_a_launch_marks_it(self):
        manifest, root, _ = self.package()
        self.assertIs(manifest["test_only"], True)
        self.assertEqual(self.rule()(manifest, root, SKILL_ROOT), [])  # 'images only, render pending'
        self.launched(root)
        self.assertNotEqual(self.rule()(manifest, root, SKILL_ROOT), [])

    def test_it_fails_until_design_board_and_final_mockups_are_closed_for_every_page(self):
        manifest, root, _ = self.package()
        self.write_clean_qc(manifest, root)
        first = STAGES[:3]
        self.close_every_page(manifest, root, stages=first)
        fails = self.rule()(manifest, root, SKILL_ROOT)
        for page in range(len(manifest["pieces"])):
            for stage in ("design-board", "final-mockups"):
                self.assertTrue(any(f"page run-{page} stage {stage} is not closed" in f for f in fails), (page, stage))
        self.close_every_page(manifest, root, skip=(2, "final-mockups"))  # one page one stage short
        self.assertEqual([f for f in self.rule()(manifest, root, SKILL_ROOT)],
                         [f"AF-LAUNCH-IMAGE-STAGES: page run-2 stage final-mockups is not closed by stage_gate.py"])
        self.close_every_page(manifest, root)
        self.assertEqual(self.rule()(manifest, root, SKILL_ROOT), [])

    def test_it_fails_when_the_qc_report_has_a_low_or_failed_asset_even_if_every_stage_is_closed(self):
        manifest, root, _ = self.package()
        self.close_every_page(manifest, root)
        self.write_clean_qc(manifest, root)
        self.assertEqual(self.rule()(manifest, root, SKILL_ROOT), [])
        report = json.loads((root / graphics_hooks.QC_REPORT_REL).read_text())
        report["assets"][0]["average"] = 8.49
        report["assets"][1]["triggered_autofails"] = ["AF-G2"]
        write(root / graphics_hooks.QC_REPORT_REL, json.dumps(report))
        fails = self.rule()(manifest, root, SKILL_ROOT)
        self.assertEqual(len(fails), 2, fails)

    def test_a_page_left_out_of_the_stage_report_fails(self):
        manifest, root, _ = self.package()
        self.write_clean_qc(manifest, root)
        self.close_every_page(manifest, root)
        doc = json.loads((root / image_stages.REPORT_REL).read_text())
        doc["pages"] = doc["pages"][:-1]
        write(root / image_stages.REPORT_REL, json.dumps(doc))
        self.assertTrue(any("page run(s)" in f or "has no page run" in f for f in self.rule()(manifest, root, SKILL_ROOT)))

    @unittest.skipUnless((SKILL_ROOT / "launcher_core" / "check_rules" / "__init__.py").is_file(),
                         "the check_rules seam lands with U-launcher-core-02; QC re-runs rows 2-4 after it lands")
    def test_cli_check_fails_a_stub_launch_until_every_page_closes_its_stages(self):
        manifest, root, built = self.package()
        self.launched(root)
        argv = ["check", "--manifest", str(built["manifest_path"]), "--root", str(root)]
        image = lambda fails: [f for f in fails if f.startswith("AF-LAUNCH-IMAGE")]
        fails = checks.check_package(Path(built["manifest_path"]), root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-IMAGE-STAGES") for f in fails), fails)
        self.assertTrue(any(f.startswith("AF-LAUNCH-IMAGE-QC") for f in fails), fails)
        self.assertEqual(cli.main(argv), 2)
        self.write_clean_qc(manifest, root)
        self.close_every_page(manifest, root, skip=(0, "final-mockups"))
        self.assertEqual(image(checks.check_package(Path(built["manifest_path"]), root)),
                         ["AF-LAUNCH-IMAGE-STAGES: page run-0 stage final-mockups is not closed by stage_gate.py"])
        self.assertEqual(cli.main(argv), 2)
        self.close_every_page(manifest, root)
        self.assertEqual(image(checks.check_package(Path(built["manifest_path"]), root)), [])
        self.assertEqual(cli.main(argv), 0)


class ModelIsNeverALiteralTests(unittest.TestCase):
    """IMG-19 (carried): run_page_role_stages.py takes its image model from Skill 66, never a literal."""

    SCRIPT = SKILL71 / "scripts" / "run_page_role_stages.py"

    def load(self):
        spec = importlib.util.spec_from_file_location("lane_run_page_role_stages", self.SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_main(self, module, provider, resolver_source):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            write(run / "intake.json", json.dumps({"copy_version": "thank-you"}))
            if resolver_source is None:
                module.IMAGE_MODEL_PATH = Path(tmp) / "absent" / "image_model.py"
            else:
                module.IMAGE_MODEL_PATH = write(Path(tmp) / "image_model.py", resolver_source)
            with mock.patch.object(module.subprocess, "run", return_value=mock.Mock(returncode=0)) as sub:
                rc = module.main([str(run), "--provider", provider, "--stages", "visual-mockup"])
            return rc, [c.args[0] for c in sub.call_args_list]

    def test_the_source_holds_no_model_id_literal(self):
        self.assertNotIn("gpt-image", self.SCRIPT.read_text(encoding="utf-8"))

    def test_the_stub_provider_names_no_model(self):
        rc, calls = self.run_main(self.load(), "stub", None)
        self.assertEqual(rc, 0)
        build = calls[0]
        self.assertEqual(build[build.index("--model") + 1], "STUB-NO-MODEL")

    def test_a_real_run_follows_skill_66s_latest_id(self):
        rc, calls = self.run_main(self.load(), "kie", "def resolve():\n    return 'FAKE-LATEST'\n")
        self.assertEqual(rc, 0)
        build = calls[0]
        self.assertEqual(build[build.index("--model") + 1], "FAKE-LATEST")

    def test_a_model_that_cannot_be_resolved_refuses_and_draws_nothing(self):
        rc, calls = self.run_main(self.load(), "kie", None)
        self.assertEqual((rc, calls), (1, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
