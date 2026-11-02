"""U-launcher-core-03: `cli plan` shows the client the plan and its hash; dispatch, assemble and
check refuse an approval that binds another hash; dispatch and assemble run the dependency
preflight first (PRD-02, CON-07). No network, nothing is built or spent."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from test_only_readback import paid_image_plan, patch_paid_budget  # noqa: E402
from launcher_core import cli, dependencies, intake  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "tests"))
from test_assemble_binding import COUNCIL, DispatchedRun, plan_hash  # noqa: E402
from test_page_designs_real import recorded_design_approval  # noqa: E402
from launcher_core.constants import resolve_ref, resolve_skill_dir  # noqa: E402

FIXTURE = SKILL_ROOT / "fixtures" / "elevation" / "intake.json"
CLIENT, WORKER = "client-test-1", "worker-test-9"


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main([str(a) for a in argv])
    return rc, out.getvalue(), err.getvalue()


def intake_doc(**over):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client"}
    doc.update(over)
    return doc


def real_hash(doc):
    return cli._plan_hash(cli._resolved_launch(doc)[1])


def approval_record(doc, **over):
    record = {"approval_id": "APPR-TEST", "plan_hash": real_hash(doc)}
    record.update(over)
    return record


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch_paid_budget(self)

    def write(self, name, doc):
        path = self.dir / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path


class PlanTests(_Tmp):
    def plan_doc(self):
        """The intake the client would hand `plan`: the picture choices the plan hash binds are all named."""
        doc = intake_doc()
        doc["image_plan"].update(design_style="B", image_cap_minor=72, image_currency="USD")
        return doc

    def test_plan_shows_every_offer_price_term_route_and_the_hash(self):
        # the acceptance command, as the client would run it, in a process that has the TEST-ONLY read-back
        # transport installed (a subprocess does not inherit the suite's: the fixtures name TEST-ONLY ids only)
        doc = self.plan_doc()
        runner = ("import sys; sys.path[:0] = [%r]; import test_only_readback; test_only_readback.install(); "
                  "from launcher_core import cli; sys.exit(cli.main(sys.argv[1:]))"
                  % str(SKILL_ROOT / "fixtures"))
        done = subprocess.run([sys.executable, "-c", runner, "plan", "--intake", str(self.write("i.json", doc))],
                              cwd=SKILL_ROOT, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        for offer in doc["offers"]:
            self.assertIn(offer["name"], done.stdout)
            self.assertIn(f"{offer['price']['amount_minor'] / 100:,.2f}", done.stdout, offer["name"])
        self.assertIn("one payment", done.stdout)
        self.assertIn("landing -> product_selection -> checkout", done.stdout)
        self.assertIn(f"plan_document_hash: {real_hash(doc)}", done.stdout)

    def test_the_printed_hash_is_the_one_an_approval_must_bind(self):
        doc = self.plan_doc()
        rc, out, _ = run_cli("plan", "--intake", self.write("i.json", doc))
        self.assertEqual(rc, 0)
        self.assertIn(approval_record(doc)["plan_hash"], out)

    def test_plan_takes_exactly_one_of_intake_or_plan(self):
        for argv in (("plan",), ("plan", "--intake", FIXTURE, "--plan", FIXTURE)):
            rc, _out, err = run_cli(*argv)
            self.assertEqual(rc, 2)
            self.assertIn("AF-LAUNCH-PLAN-ARGS", err)


class PlanBindsThePageChoiceTests(_Tmp):
    """APPROVAL-HASH: the plan a client approves must hash the same inputs dispatch binds, landing choice
    included. A choice changed after approval is a new plan, so dispatch refuses the old approval."""

    def plan_hash(self, *flags):
        rc, out, err = run_cli("plan", "--intake", self.write("i.json", intake_doc()), *flags)
        self.assertEqual(rc, 0, err)
        return next(line.split(": ", 1)[1] for line in out.splitlines() if line.startswith("plan_document_hash: ")), out

    def dispatch(self, approved_hash, *flags):
        doc = intake_doc()
        record = {"approval_id": "APPR-TEST", "plan_hash": approved_hash}
        argv = ["dispatch", "--intake", self.write("intake.json", doc), "--out", self.dir / "run",
                "--approval", self.write("approval.json", record), "--client", CLIENT, "--worker", WORKER, *flags]
        with mock.patch.object(cli.launch_bridge, "run", return_value={}) as run, \
                mock.patch.object(cli.launch_bridge, "summary_lines", return_value=[]):
            rc, _out, err = run_cli(*argv)
        return rc, err, run

    def test_the_landing_choice_changes_the_hash_plan_shows(self):
        default, _ = self.plan_hash()
        sales, shown = self.plan_hash("--landing-pages", "sales")
        both, _ = self.plan_hash("--landing-pages", "landing,sales")
        self.assertNotEqual(default, sales)
        self.assertEqual(default, both)  # Skill 49's recommended set for this funnel is both pages
        self.assertIn("Landing pages: sales", shown)
        self.assertNotEqual(sales, self.plan_hash("--landing-pages", "sales", "--extra-page", "downsell_2")[0])

    def test_plan_then_approve_that_hash_then_dispatch_succeeds(self):
        for flags in ((), ("--landing-pages", "sales"), ("--landing-pages", "landing,sales", "--extra-page", "downsell_2")):
            with self.subTest(flags=flags):
                approved, _ = self.plan_hash(*flags)
                rc, err, run = self.dispatch(approved, *flags)
                self.assertEqual(rc, 0, err)
                kw = run.call_args.kwargs
                want = [k for k in (flags[1].split(",") if flags else [])]
                self.assertEqual((kw["landing_pages"], kw["extra_pages"]),
                                 (want or None, ("downsell_2",) if "--extra-page" in flags else ()))

    def test_a_landing_choice_changed_after_approval_is_refused_by_name(self):
        for approved_flags, dispatch_flags in (((), ("--landing-pages", "sales")),
                                               (("--landing-pages", "sales"), ()),
                                               (("--landing-pages", "sales"), ("--landing-pages", "landing")),
                                               (("--landing-pages", "sales"), ("--landing-pages", "sales", "--extra-page", "downsell_2"))):
            with self.subTest(approved=approved_flags, dispatched=dispatch_flags):
                approved, _ = self.plan_hash(*approved_flags)
                rc, err, run = self.dispatch(approved, *dispatch_flags)
                self.assertEqual((rc, "AF-LAUNCH-APPROVAL-HASH" in err), (2, True), err)
                run.assert_not_called()
                self.assertFalse((self.dir / "run").exists())


class ApprovalBindingTests(_Tmp):
    def dispatch(self, doc, record, out=None):
        argv = ["dispatch", "--intake", self.write("intake.json", doc), "--out", out or self.dir / "run",
                "--approval", self.write("approval.json", record), "--client", CLIENT, "--worker", WORKER]
        with mock.patch.object(cli.launch_bridge, "run", return_value={}) as run, \
                mock.patch.object(cli.launch_bridge, "summary_lines", return_value=[]):
            rc, out, err = run_cli(*argv)
        return rc, err, run

    def live(self, **claim):
        doc = intake_doc(test_only=False)
        doc["image_plan"].update(paid_image_plan(10, "APPR-PAID"))
        doc["approval"] = {"ref": "APPR-TEST", "hash": real_hash(doc), **claim}
        return doc

    def test_an_intake_hash_that_is_not_the_real_hash_fails_dispatch_by_name(self):
        doc = self.live(hash="0" * 64)
        rc, err, run = self.dispatch(doc, approval_record(doc))
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-APPROVAL-BINDING", err)
        run.assert_not_called()
        self.assertFalse((self.dir / "run").exists())

    def test_an_intake_ref_that_is_not_the_approval_on_record_fails_dispatch(self):
        doc = self.live(ref="made-up")
        rc, err, run = self.dispatch(doc, approval_record(doc))
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-BINDING" in err), (2, True))
        run.assert_not_called()

    def test_a_test_only_intake_with_a_non_placeholder_mismatch_is_still_refused(self):
        doc = intake_doc(approval={"ref": "approval-1", "hash": "b" * 64})
        rc, err, run = self.dispatch(doc, approval_record(doc))
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-BINDING" in err), (2, True))
        run.assert_not_called()

    def test_an_approval_record_for_another_plan_fails_dispatch_by_name(self):
        doc = self.live()
        rc, err, run = self.dispatch(doc, approval_record(doc, plan_hash="1" * 64))
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-HASH" in err), (2, True))
        run.assert_not_called()

    def test_the_matching_approval_is_carried_to_the_build(self):  # control for the refusals above
        doc = self.live()
        rc, err, run = self.dispatch(doc, approval_record(doc))
        self.assertEqual(rc, 0, err)
        self.assertEqual(run.call_args.args[0]["approval"], {"ref": "APPR-TEST", "hash": real_hash(doc)})

    def test_a_fixture_placeholder_is_replaced_by_the_verified_hash_never_printed(self):
        doc = intake_doc()  # fixture: TEST-ONLY-APPROVAL with a made-up hash
        self.assertTrue(doc["approval"]["ref"].startswith("TEST-ONLY"))
        rc, err, run = self.dispatch(doc, approval_record(doc))
        self.assertEqual(rc, 0, err)
        self.assertEqual(run.call_args.args[0]["approval"], {"ref": "APPR-TEST", "hash": real_hash(doc)})

    def manifest_dir(self, approved, receipt_ref="APPR-TEST"):
        doc = self.live()
        _, launch = cli._resolved_launch(doc)
        launch["plan_approval_ref"] = "APPR-TEST"
        run = self.dir / "package"
        run.mkdir()
        (run / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
        (run / "receipt.json").write_text(json.dumps(
            {"approvals": {"launch_plan_build": receipt_ref}}), encoding="utf-8")
        manifest = run / "package-manifest.json"
        manifest.write_text(json.dumps({"launch_id": doc["launch_id"], "test_only": False,
                                        "approved_plan_hash": approved or cli._plan_hash(launch)}),
                            encoding="utf-8")
        return manifest, run

    def check(self, manifest, run):
        with mock.patch.object(cli.checks, "check_package", return_value=[]):  # isolate the binding
            return run_cli("check", "--manifest", manifest, "--root", run)

    def test_check_fails_when_the_package_hash_is_not_the_dispatched_plan(self):
        rc, out, _ = self.check(*self.manifest_dir("0" * 64))
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-APPROVAL-BINDING", out)

    def test_check_fails_when_the_receipt_names_another_approval(self):
        rc, out, _ = self.check(*self.manifest_dir(None, receipt_ref="made-up"))
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-BINDING" in out), (2, True))

    def test_check_passes_a_package_bound_to_the_dispatched_plan(self):  # control
        rc, out, _ = self.check(*self.manifest_dir(None))
        self.assertEqual(rc, 0, out)

    def test_a_live_package_with_no_dispatch_record_cannot_pass_check(self):
        manifest, run = self.manifest_dir(None)
        (run / "launch.json").unlink()
        rc, out, _ = self.check(manifest, run)
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-UNBOUND" in out), (2, True))

    def assemble(self, doc, **launch_over):
        run = self.dir / "run"
        (run / "pieces").mkdir(parents=True)
        normalized = intake.validate(doc)
        graph = cli.route.compile_route(normalized)
        for node in graph["nodes"]:
            (run / "pieces" / f"{node['role']}.json").write_text("{}", encoding="utf-8")
        launch = cli._resolved_launch(doc)[1]
        launch["plan_approval_ref"] = "APPR-TEST"
        launch.update(launch_over)
        (run / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
        fake = {"manifest_path": "m", "receipt_path": "r",
                "manifest": {"to_confirm": [], "delivery_scope": "page_only", "delivery_label": "x"}}
        with mock.patch.object(cli.package, "assemble", return_value=fake) as built, \
                mock.patch.object(cli.council, "planning_step", return_value={"status": "ok"}):
            rc, out, err = run_cli("assemble", "--intake", self.write("intake.json", doc),
                                   "--run-dir", run, "--out", self.dir / "out", "--page-only")
        return rc, err, built, run

    def test_assemble_takes_run_dir_and_binds_the_receipt_to_the_dispatch_record(self):
        doc = self.live()
        rc, err, built, run = self.assemble(doc)
        self.assertEqual(rc, 0, err)
        self.assertEqual(built.call_args.args[1]["approval"], {"ref": "APPR-TEST", "hash": real_hash(doc)})
        self.assertEqual(built.call_args.kwargs["source_root"], run)

    def test_assemble_refuses_an_intake_that_claims_another_hash(self):
        rc, err, built, _ = self.assemble(self.live(hash="0" * 64))
        self.assertEqual((rc, "AF-LAUNCH-APPROVAL-BINDING" in err), (2, True))
        built.assert_not_called()


def farm(root: Path, drop=None, versions=None) -> Path:
    """A copy of the repository root made of links, minus one path: the 'temp copy with one thing deleted'."""
    drop, versions = drop or (), versions or {}
    for item in REPO_ROOT.iterdir():
        if item.name in (".git", "node_modules") or item.name == "shared-utils":
            continue
        if item.name in versions:  # a real folder so one file can differ
            (root / item.name).mkdir()
            for child in item.iterdir():
                if child.name != "skill-version.txt":
                    (root / item.name / child.name).symlink_to(child)
            (root / item.name / "skill-version.txt").write_text(versions[item.name], encoding="utf-8")
        else:
            (root / item.name).symlink_to(item)
    (root / "shared-utils").mkdir()
    for child in (REPO_ROOT / "shared-utils").iterdir():
        if f"shared-utils/{child.name}" not in drop:
            (root / "shared-utils" / child.name).symlink_to(child)
    return root


class PreflightTests(_Tmp):
    def refuse(self, command, root):
        doc = intake_doc()
        argv = {"dispatch": ["dispatch", "--intake", self.write("i.json", doc), "--out", self.dir / "r",
                             "--approval", self.write("a.json", approval_record(doc)),
                             "--client", CLIENT, "--worker", WORKER],
                "assemble": ["assemble", "--intake", self.write("i.json", doc), "--run-dir", self.dir / "r",
                             "--out", self.dir / "o"]}[command]
        with mock.patch.object(dependencies, "REPO_ROOT", root):
            return run_cli(*argv)

    def test_the_manifest_names_the_contract_client_intake_and_a_floor_per_tree(self):
        entries = {e["id"]: e for e in dependencies.load_manifest()["entries"]}
        refs = {e["ref"] for e in entries.values()}
        self.assertIn("shared-utils/signature_launch_contract", refs)
        self.assertIn("shared-utils/client_intake", refs)
        self.assertNotIn("shared-utils/signature_launch", refs)  # the unused tree is replaced
        trees = [e for e in entries.values() if e["kind"] == "skill_tree"]
        self.assertGreaterEqual(len(trees), 10)
        for tree in trees:
            self.assertTrue(tree.get("min_version"), tree["id"])
        self.assertTrue({"tree-44-convert-and-flow-operator", "tree-50-email-engine"} <= set(entries))
        # both resolve by slug under either naming convention, as the 999 layout needs
        for slug in ("convert-and-flow-operator", "email-engine"):
            self.assertTrue(resolve_skill_dir(slug, REPO_ROOT).is_dir())
        # and a numbered reference resolves inside a deployed layout (.claude/skills/<slug>, no numeric prefix)
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / ".claude" / "skills" / "convert-and-flow-operator"
            (skill / "tools").mkdir(parents=True)
            (skill / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
            (skill / "tools" / "validate_graph.py").write_text("# fixture\n", encoding="utf-8")
            self.assertEqual(resolve_ref("44-convert-and-flow-operator/tools/validate_graph.py", tmp),
                             skill / "tools" / "validate_graph.py")

    def test_the_real_tree_passes_the_preflight(self):  # control: the instrument is not just always refusing
        report = dependencies.require()
        self.assertEqual(report["blockers"], [])

    def test_dispatch_and_assemble_refuse_naming_a_deleted_contract_directory(self):
        (self.dir / "copy").mkdir()
        root = farm(self.dir / "copy", drop=("shared-utils/signature_launch_contract",))
        self.assertEqual(dependencies.check(root)["blockers"], ["shared-utils-signature-launch"])
        for command in ("dispatch", "assemble"):
            rc, _out, err = self.refuse(command, root)
            self.assertEqual(rc, 2, command)
            self.assertIn("AF-LAUNCH-DEPENDENCY", err)
            self.assertIn("shared-utils/signature_launch_contract", err)
            self.assertFalse((self.dir / "r").exists(), command)

    def test_dispatch_and_assemble_refuse_when_client_intake_is_missing(self):
        (self.dir / "copy").mkdir()
        root = farm(self.dir / "copy", drop=("shared-utils/client_intake",))
        for command in ("dispatch", "assemble"):
            rc, _out, err = self.refuse(command, root)
            self.assertEqual(rc, 2)
            self.assertIn("shared-utils-client-intake", err)

    def test_a_tree_below_its_minimum_version_is_refused(self):
        (self.dir / "copy").mkdir()
        root = farm(self.dir / "copy", versions={"49-signature-funnel": "v0.0.1\n"})
        for command in ("dispatch", "assemble"):
            rc, _out, err = self.refuse(command, root)
            self.assertEqual(rc, 2)
            self.assertIn("tree-49-signature-funnel", err)
            self.assertIn("below the minimum", err)

    def test_an_intact_copy_gets_past_the_preflight(self):  # control on the instrument: farm without a deletion
        (self.dir / "copy").mkdir()
        root = farm(self.dir / "copy")
        doc = intake_doc()
        doc["image_plan"].pop("brand_file")  # stops at the picture plan, after the preflight
        argv = ["dispatch", "--intake", self.write("i.json", doc), "--out", self.dir / "r",
                "--approval", self.write("a.json", {}), "--client", CLIENT, "--worker", WORKER]
        with mock.patch.object(dependencies, "REPO_ROOT", root):
            rc, _out, err = run_cli(*argv)
        self.assertEqual(rc, 2)
        self.assertNotIn("AF-LAUNCH-DEPENDENCY", err)
        self.assertIn("three palettes", err)


class LaunchEventTests(_Tmp):
    def test_an_emitter_failure_never_changes_the_exit_code(self):
        manifest = self.write("package-manifest.json", {"launch_id": "L1", "test_only": True})
        with mock.patch.object(cli.checks, "check_package", return_value=[]), \
                mock.patch.object(cli.launch_bridge.substrate, "load", side_effect=RuntimeError("down")):
            rc, out, err = run_cli("check", "--manifest", manifest, "--root", self.dir)
        self.assertEqual(rc, 0)
        self.assertIn("PASS package complete", out)
        self.assertIn("[launch_events] skipped (RuntimeError)", err)


class DispatchBindsTheAnswersFile(_Tmp):
    """PRD-16: `dispatch --answers` refuses an intake that was not built from exactly that answers file."""

    def setUp(self):
        super().setUp()
        spec = importlib.util.spec_from_file_location(
            "launcher_intake_test_helpers",
            REPO_ROOT / "shared-utils" / "client_intake" / "tests" / "test_launcher_intake.py")
        self.helpers = helpers = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helpers)
        self.li = cli._launcher_intake()
        doc = json.loads(json.dumps(helpers.ELEVATION))  # the three answers a launch intake also needs, as the
        doc["meta"]["mode"] = "bf"                       # client gave them (set directly: the interview engine
        for qid, answer in (("entitlement", "attested"), ("plan_approval", "approve"),  # now cites transcripts)
                            ("visual_direction", helpers.HOUSE), ("checkout_terms", helpers.TERMS)):
            helpers.e._set(doc, qid, answer, "provided", "client")
        self.answers = self.write("answers.json", doc)
        _mode, derived, _ = self.li.derive_offers(doc)
        delivery = {"destination": "https://delivery.test-only.invalid/offer", "owner_confirmed": True}
        system = self.write("system.json", {  # what no answer can carry: where each offer is delivered
            **helpers.SYSTEM, "brand_file": "/tmp/test-brand.json",
            "extra_offer": {o["offer_id"]: {"delivery": delivery} for o in derived}})
        self.built = self.dir / "built"
        self.assertEqual(self.li.main(["build", str(self.answers), "--system", str(system),
                                       "--out", str(self.built)]), 0)

    def dispatch(self, answers=None):
        doc = json.loads((self.built / "intake.json").read_text(encoding="utf-8"))
        argv = ["dispatch", "--intake", self.built / "intake.json", "--answers", answers or self.answers,
                "--out", self.dir / "run", "--approval", self.write("approval.json", approval_record(doc)),
                "--client", CLIENT, "--worker", WORKER]
        with mock.patch.object(cli.launch_bridge, "run", return_value={}) as run, \
                mock.patch.object(cli.launch_bridge, "summary_lines", return_value=[]):
            rc, _out, err = run_cli(*argv)
        return rc, err, run

    def test_an_answers_file_that_changed_after_the_intake_was_built_is_refused_by_name(self):
        doc = json.loads(self.answers.read_text(encoding="utf-8"))
        doc["answers"]["upsell_1"]["value"]["price"]["amount_minor"] += 1
        rc, err, run = self.dispatch(self.write("moved-on.json", doc))
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-ANSWERS-HASH-MISMATCH", err)
        run.assert_not_called()
        self.assertFalse((self.dir / "run").exists())

    def test_an_intake_with_no_provenance_is_refused_by_name(self):
        (self.built / self.li.PROVENANCE_NAME).unlink()
        rc, err, run = self.dispatch()
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-ANSWERS-HASH-MISSING", err)
        run.assert_not_called()
        self.assertFalse((self.dir / "run").exists())

    def test_the_untouched_answers_reach_the_build_once(self):  # control: the refusal is the only gate added
        rc, err, run = self.dispatch()
        self.assertEqual(rc, 0, err)
        run.assert_called_once()


class AssembleFlagTests(DispatchedRun):
    """The assemble flags and what they refuse, on a real (free) dispatch run."""

    def cli_assemble(self, name, run=None, *flags):
        run = run or self.rundir
        doc_path = self.work / "intake.json"
        doc_path.write_text(json.dumps(self.doc), encoding="utf-8")
        with mock.patch.object(cli.council, "planning_step", return_value=COUNCIL):
            rc, out, err = run_cli("assemble", "--intake", doc_path, "--run-dir", run, "--out", self.work / name,
                                   "--page-only", *flags)
        return rc, out, err

    def waiver(self, **over):
        return {"approval_ref": "APPR-WAIVE-1", "subject_type": "design_waiver", "subject_hash": plan_hash(self.doc),
                "owner_identity_ref": CLIENT, "revoked": False, **over}

    def test_assemble_without_the_dispatch_report_is_refused_by_name(self):
        run = self.copy_run("cli-no-report")
        (run / "dispatch-report.json").unlink()
        rc, _out, err = self.cli_assemble("no-report", run)
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-PKG-DISPATCH-REPORT", err)
        self.assertFalse((self.work / "no-report" / "package-manifest.json").exists())

    def test_allow_no_designs_needs_the_owners_waiver_and_stamps_the_label(self):
        rc, _out, err = self.cli_assemble("no-waiver", None, "--allow-no-designs")
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-PKG-DESIGN-WAIVER", err)
        waiver = self.work / "waiver.json"
        waiver.write_text(json.dumps(self.waiver()), encoding="utf-8")
        rc, out, err = self.cli_assemble("waived", None, "--allow-no-designs", "--design-waiver", waiver)
        self.assertEqual(rc, 0, err)
        self.assertIn("designs waived (owner approval", json.loads(out)["delivery_label"])

    def design_approvals(self, doc):
        path = self.work / "approvals.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_design_approvals_that_do_not_resolve_to_a_recorded_board_approval_are_refused(self):
        path = self.design_approvals({
            "design_board": {"state": "approved", "approval_ref": "any string", "record_sha256": "0" * 64},
            "final_mockups": {"state": "awaiting_client_approval", "approval_ref": None}})
        rc, _out, err = self.cli_assemble("bad-approvals", None, "--design-approvals", path)
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS", err)
        self.assertIn("does not resolve to a recorded Design Board approval", err)

    def test_a_recorded_design_board_approval_is_accepted_and_carried_into_the_manifest(self):
        path = self.design_approvals(recorded_design_approval(self.work / "approvals-run"))
        rc, out, err = self.cli_assemble("good-approvals", None, "--design-approvals", path)
        self.assertEqual(rc, 0, err)
        manifest = json.loads((self.work / "good-approvals" / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["design_approvals"]["design_board"]["state"], "approved")


if __name__ == "__main__":
    unittest.main(verbosity=2)
