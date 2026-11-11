"""A 3/5/7-step funnel gets wireframes and mockups for EVERY page it has (SPF030, LANE-49).

legacy_downsell_images.py runs Skill 71's pipeline for every page of the funnel size except the
design-only checkout (named in the receipt): three stages (desktop wireframe, mobile wireframe,
visual mockup), offline stub provider, each page checked against structure/page_types.json.
Run: python3 test_legacy_downsell_images.py

Harmony issues 2, 10, 38, 62: the tool draws only through Skill 71's one admission door
(run_governed_stage.py), never the executor itself; a stub run needs a stub_render approval that is a
Command Center record (a loopback fake of the real service answers here, so the REAL shared verifier runs);
free text is refused by the tool and again by the P7 prover; the harness marker SKILL71_FIXTURE_RUN=1 lets
the stub fixture run on a run with no gate state, and without it the run is refused.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
TOOL = SCRIPTS / "legacy_downsell_images.py"
SKILL71 = REPO / "71-blackceo-signature-page"
CHECKOUT_MANUSCRIPT = SKILL71 / "tests" / "fixtures" / "copy_examples" / "checkout-example.md"
BRAND = SKILL71 / "assets" / "brand" / "blackceo-brand.json"
LEDGER = json.loads((SCRIPTS.parent / "examples" / "golden-daybreak" / "copy_ledger.json").read_text())
sys.path.insert(0, str(SKILL71 / "scripts"))
sys.path.insert(0, str(SKILL71 / "tests"))
import board_fixture as bf  # noqa: E402  (Skill 71's own Design Board fixture, read-only)
import deliverable_labels  # noqa: E402
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "tests"))  # the loopback stand-in lives in tests/, which the bypass scan skips
from fake_command_center import FakeCommandCenter  # noqa: E402

CC = FakeCommandCenter()  # a loopback Command Center: the real approval_record.verify talks to it


def setUpModule():
    CC.start()


def tearDownModule():
    CC.stop()


def tool_env(marker="1", **extra):
    """The child environment: the fake Command Center, and the Skill 71 harness marker (or none)."""
    env = {**os.environ, **CC.env(), **extra}
    env.pop("SKILL71_FIXTURE_RUN", None)
    if marker is not None:
        env["SKILL71_FIXTURE_RUN"] = marker
    return env


def mint_for(ledger_path, kind="stub_render", **kw):
    return CC.mint(kind, hashlib.sha256(pathlib.Path(ledger_path).read_bytes()).hexdigest(), **kw)

# slug -> (page_key, sections): what each page of the 7-step funnel must end with
PAGES = {"main": ("sales", 12), "upsell": ("upsell_1", 8), "downsell": ("downsell_1", 8),
         "upsell-2": ("upsell_2", 8), "downsell-2": ("downsell_2", 8), "thank-you": ("thank_you", 5)}


class LegacyPageImagesTests(unittest.TestCase):
    def run_tool(self, ledger, *extra, marker="1", env=None):
        # Fix plan B2 (unowned requirement G-3): the tool DEFAULTS to the real provider now, so a
        # run that wants the offline stub must ask for it and carry the owner approval that
        # permitted it. Issue 38: that approval is a Command Center record for THIS ledger, minted
        # here by the loopback Command Center. This suite exercises the stub path end to end.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        (root / "ledger.json").write_text(json.dumps(ledger))
        if "--image-provider" not in extra:
            extra = (*extra, "--image-provider", "stub", "--stub-approved-by", mint_for(root / "ledger.json"))
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--ledger", str(root / "ledger.json"),
             "--skill71-root", str(SKILL71), "--brand-file", str(BRAND),
             "--brand-owner", "blackceo", "--out-dir", str(root / "out"), *extra],
            capture_output=True, text=True, env=env if env is not None else tool_env(marker))
        return proc, root / "out"

    def test_seven_step_funnel_gets_designs_for_every_page_but_the_design_only_checkout(self):
        proc, out = self.run_tool(LEDGER)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), sorted(PAGES))
        self.assertEqual(list(report["not_built"]), ["checkout"])
        for slug, (key, sections) in PAGES.items():
            page = report["pages"][slug]
            self.assertEqual(page["page_key"], key)
            self.assertEqual({k: v["images"] for k, v in page["stages"].items()},
                             {"desktop-wireframe": sections, "mobile-tablet": sections, "visual-mockup": 2 * sections})
            # a stub run is images only: the review PDFs and boards are named as render pending
            self.assertIn("desktop_wireframe_pdf", page["render_pending"])
        self.assertTrue((out / "page-images-receipt.json").is_file())

    def test_each_page_carries_its_own_copy_and_is_labelled_as_itself(self):
        proc, out = self.run_tool(LEDGER)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        want = {"main": "sales_page", "upsell": "upsell_1", "upsell-2": "upsell_2", "downsell": "downsell_1",
                "downsell-2": "downsell_2", "thank-you": "thank_you"}
        for slug, role in want.items():
            self.assertEqual(deliverable_labels.declared_page_role(out / slug), role, slug)

        def request(slug):
            return (out / slug / "production-request-visual-mockup.json").read_text()
        self.assertIn("Single Day Pass", request("downsell-2"))
        self.assertNotIn("Single Day Pass", request("downsell"))
        self.assertIn("Fast Track Sprint", request("upsell"))
        self.assertNotIn("Founders Table Retreat", request("upsell"))
        self.assertIn("Founders Table Retreat", request("upsell-2"))
        self.assertIn("Daybreak Method", request("main"))
        self.assertEqual(json.loads(request("downsell"))["decline_action"], {"label": "No thanks"})

    def test_the_thank_you_page_invents_no_price_or_order_reference(self):
        proc, out = self.run_tool(LEDGER, "--page", "thank-you", "--access-label", "Open My Daybreak")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        text = (out / "thank-you" / "copy" / "internal-manuscript.md").read_text()
        self.assertIn("The Daybreak Method. Paid.", text)
        self.assertIn("Open My Daybreak", text)
        self.assertNotRegex(text, r"[$]|USD|Order reference")
        self.assertIn("It is official", text)  # TY-1 verbatim
        self.assertIn("Check your email for your receipt", text)  # TY-2 step verbatim

    def test_five_step_funnel_has_one_downsell_and_no_checkout_note(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), ["downsell", "main", "thank-you", "upsell", "upsell-2"])
        self.assertEqual(report["not_built"], {})

    def test_three_step_funnel_builds_main_upsell_and_thank_you(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=3))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(sorted(json.loads(proc.stdout)["pages"]), ["main", "thank-you", "upsell"])

    def test_page_flag_narrows_and_refuses_a_page_outside_the_funnel(self):
        proc, _ = self.run_tool(LEDGER, "--page", "downsell-2")
        self.assertEqual(list(json.loads(proc.stdout)["pages"]), ["downsell-2"])
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=5), "--page", "downsell-2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("downsell-2", proc.stderr)
        proc, _ = self.run_tool(LEDGER, "--page", "checkout")
        self.assertEqual(proc.returncode, 2)

    def test_a_page_missing_a_section_is_refused_by_name(self):
        for slug, needle in (("downsell-2", "must carry sections 1..8"), ("main", "must carry sections 1..12"),
                             ("upsell", "must carry sections 1..8"), ("thank-you", "TY-1, TY-2, TY-3")):
            ledger = json.loads(json.dumps(LEDGER))
            page = next(p for p in ledger["pages"] if p["page_type"] == slug)
            page["sections"] = page["sections"][:2]
            proc, _ = self.run_tool(ledger, "--page", slug)
            self.assertEqual(proc.returncode, 2, slug)
            self.assertIn(f"{slug}: the copy ledger page {needle}" if slug != "thank-you"
                          else f"{slug}: the copy ledger page must carry sections {needle}", proc.stderr)

    def test_seven_step_checkout_is_drawn_from_the_staged_manuscript(self):
        proc, out = self.run_tool(LEDGER, "--checkout-manuscript", str(CHECKOUT_MANUSCRIPT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(sorted(report["pages"]), sorted([*PAGES, "checkout"]))
        self.assertEqual(report["not_built"], {})
        page = report["pages"]["checkout"]
        self.assertEqual(page["page_key"], "checkout")
        self.assertEqual({k: v["images"] for k, v in page["stages"].items()},
                         {"desktop-wireframe": 5, "mobile-tablet": 5, "visual-mockup": 10})

    def test_checkout_manuscript_with_card_fields_is_refused(self):
        bad = pathlib.Path(tempfile.mkdtemp()) / "checkout.md"
        bad.write_text(CHECKOUT_MANUSCRIPT.read_text(encoding="utf-8") + "\nCard number field.\n", encoding="utf-8")
        proc, _ = self.run_tool(LEDGER, "--page", "checkout", "--checkout-manuscript", str(bad))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("native checkout form only", proc.stderr)

    def test_without_the_manuscript_the_receipt_says_what_checkout_needs(self):
        proc, _ = self.run_tool(LEDGER, "--page", "main")
        self.assertIn("--checkout-manuscript", json.loads(proc.stdout)["not_built"]["checkout"])

    def test_paid_provider_needs_the_owner_flag(self):
        proc, _ = self.run_tool(LEDGER, "--image-provider", "kie")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--allow-paid", proc.stderr)


class WireframeSlotsetBoundToRequest(unittest.TestCase):
    """AF-FUN-VISUAL-SLOTSET (G-10): the tool writes the wireframe section plan and inventory from the
    page's own production request, after giving every section the funnel structure requires an image
    for a slot. The real tool output goes through the real prover; only final-mockups may remain."""

    run_tool = LegacyPageImagesTests.run_tool

    def check_size(self, size):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import prove_sf_build
        proc, out = self.run_tool({**LEDGER, "funnel_size": size})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        run = out.parent / "run"
        run.mkdir()
        out.rename(run / "page-images")
        # P7 re-verifies the stub approval (issue 38) against this run's copy_ledger.json at the loopback
        # Command Center; the assertion below is unchanged: only final-mockups is still missing.
        (run / "copy_ledger.json").write_bytes((out.parent / "ledger.json").read_bytes())
        with mock.patch.dict(os.environ, CC.env()):
            violations = prove_sf_build.visual_direction_violations(run, size)
        self.assertEqual({code for code, _ in violations}, {"AF-FUN-BUILD-VISUAL"}, violations)
        self.assertTrue(all("final-mockups" in msg for _, msg in violations), violations)
        for plan_file in (run / "page-images").glob("*/desktop-wireframe/section-plan.json"):
            ids = [i for sec in json.loads(plan_file.read_text()) for i in sec["image_slot_ids"]]
            self.assertEqual(len(ids), len(set(ids)), plan_file)  # renumbering kept every id unique
        main = json.loads((run / "page-images" / "main" / "desktop-wireframe" / "section-plan.json").read_text())
        self.assertEqual([len(sec["image_slot_ids"]) for sec in main], [1] * 12)  # 6, 7, 11 are no longer empty

    def test_size_3(self):
        self.check_size(3)

    def test_size_5(self):
        self.check_size(5)

    def test_size_7(self):
        self.check_size(7)


class RecordFinalMockups(unittest.TestCase):
    """G-4 (defect A): --record-final-mockups merges the closed final-mockups records into the receipt, so
    the real P7 prover sees no AF-FUN-BUILD-VISUAL. It draws nothing and spends nothing."""

    run_tool = LegacyPageImagesTests.run_tool

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import prove_sf_build
        self.build = prove_sf_build
        proc, out = self.run_tool({**LEDGER, "funnel_size": 3})  # stub run: no paid call
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.run_dir = out.parent / "run"
        self.run_dir.mkdir()
        out.rename(self.run_dir / "page-images")
        self.base = self.run_dir / "page-images"
        self.pages = sorted(json.loads((self.base / "page-images-receipt.json").read_text())["pages"])

    def plant(self, skip=(), images=("a.png",)):
        for slug in self.pages:
            if slug not in skip:
                d = self.base / slug / "final-mockups"
                d.mkdir(parents=True, exist_ok=True)
                (d / "stage-executor-record.json").write_text(json.dumps({"images": list(images)}))

    def record(self):
        return subprocess.run([sys.executable, str(TOOL), "--record-final-mockups", "--out-dir", str(self.base)],
                              capture_output=True, text=True)

    def visual(self):
        return [v for v in self.build.visual_direction_violations(self.run_dir, 3) if v[0] == "AF-FUN-BUILD-VISUAL"]

    def test_before_the_mode_the_prover_refuses_and_after_it_passes(self):
        self.plant()
        self.assertTrue(self.visual())  # the control: the records alone do not certify
        proc = self.record()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.visual(), [])

    def test_a_page_without_a_record_exits_2_naming_it_and_leaves_the_receipt_alone(self):
        self.plant(skip=("upsell",))
        before = (self.base / "page-images-receipt.json").read_bytes()
        proc = self.record()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("upsell", proc.stderr)
        self.assertNotIn("main", proc.stderr)
        self.assertEqual((self.base / "page-images-receipt.json").read_bytes(), before)

    def test_a_record_with_no_images_is_refused(self):
        self.plant(images=())
        self.assertEqual(self.record().returncode, 2)

    def test_a_record_changed_after_the_mode_ran_fails_on_the_sha256(self):
        self.plant()
        self.assertEqual(self.record().returncode, 0)
        (self.base / "main" / "final-mockups" / "stage-executor-record.json").write_text('{"images": ["b.png"]}')
        self.assertTrue(any("sha256" in msg for _, msg in self.visual()), self.visual())

    def test_the_mode_needs_no_provider_flag_and_makes_no_subprocess_call(self):
        self.plant()
        spec = importlib.util.spec_from_file_location("legacy_images_record", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with mock.patch.object(tool.subprocess, "run", side_effect=AssertionError("spawned")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tool.main(["--record-final-mockups", "--out-dir", str(self.base)]), 0)


FAKE_ADAPTER = """#!/usr/bin/env python3
import json, os
print(json.dumps({"state": "success", "data": {"source": "fake", "changed": True, "routes": {
    "Text to Image": os.environ["FAKE_LATEST"] + "-text-to-image",
    "Image to Image": os.environ["FAKE_LATEST"] + "-image-to-image"}}}))
"""


class ImageModelResolvedThroughSkill66(unittest.TestCase):
    """IMG-19: the tool holds no model id; the paid model is Skill 66's default, resolved once per run."""

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        spec = importlib.util.spec_from_file_location("legacy_downsell_images_under_test", TOOL)
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "ledger.json").write_text(json.dumps(LEDGER))

    def run_main(self, *extra):
        """main() with every subprocess stubbed (no paid call); returns (exit code, stderr, argv list)."""
        seen, real = [], subprocess.run

        def fake_run(cmd, **kw):
            if not pathlib.Path(cmd[1]).name.startswith(("build_production_request", "run_governed_stage")):
                return real(cmd, **kw)  # Skill 66's own call to the Skill 74 adapter is real
            seen.append(list(cmd))
            if "--out" in cmd:  # the real builder writes the request the tool now reads back to bind slots
                (pathlib.Path(kw["cwd"]) / cmd[cmd.index("--out") + 1]).write_text('{"sections": []}')
            return subprocess.CompletedProcess(cmd, 0, "", "")
        err = io.StringIO()
        with mock.patch.object(self.tool.subprocess, "run", fake_run), contextlib.redirect_stderr(err):
            code = self.tool.main(["--ledger", str(self.root / "ledger.json"), "--skill71-root", str(SKILL71),
                                   "--brand-file", str(BRAND), "--brand-owner", "blackceo",
                                   "--out-dir", str(self.root / "out"), "--page", "downsell", *extra])
        return code, err.getvalue(), seen

    def models(self, seen):
        return [c[c.index("--model") + 1] for c in seen if "--model" in c]

    def test_the_source_holds_no_hard_coded_model_id(self):
        self.assertNotIn("gpt-image-2-6/sunburst-image-to-image", TOOL.read_text(encoding="utf-8"))

    def test_changing_the_skill66_default_changes_the_model_in_every_production_request(self):
        adapter = self.root / "kie_live_adapter.py"  # Skill 74 `latest-family`, the way Skill 66 asks it
        adapter.write_text(FAKE_ADAPTER, encoding="utf-8")
        seen_models = []
        for latest in ("gpt-image-8", "gpt-image-9"):
            with mock.patch.dict(os.environ, {"KIE_LIVE_ADAPTER_PATH": str(adapter), "FAKE_LATEST": latest}):
                _, _, seen = self.run_main("--image-provider", "kie", "--allow-paid")
            models = self.models(seen)
            self.assertEqual(models, [f"{latest}-image-to-image"] * 3)  # one build per stage
            seen_models.append(models[0])
        self.assertNotEqual(*seen_models)

    def test_skill66_selector_missing_refuses_and_builds_nothing(self):
        empty = self.root / "no-skill66"
        empty.mkdir()
        source = (REPO / "shared-utils" / "signature_launch" / "image_model.py").read_text(encoding="utf-8")
        broken = self.root / "image_model.py"
        broken.write_text("\n".join(f"SKILL66_ROOT = Path({str(empty)!r})" if ln.startswith("SKILL66_ROOT =") else ln
                                    for ln in source.splitlines()), encoding="utf-8")
        real = importlib.util.spec_from_file_location
        redirect = lambda name, path, *a, **k: real(name, broken if name == "signature_launch_image_model" else path, *a, **k)
        with mock.patch.object(self.tool.importlib.util, "spec_from_file_location", redirect):
            code, err, seen = self.run_main("--image-provider", "kie", "--allow-paid")
        self.assertEqual(code, 2)
        self.assertIn("Skill 66 did not resolve", err)
        self.assertEqual(seen, [])


class StubApprovalIsAVerifiedCommandCenterRecord(unittest.TestCase):
    """Issue 38: --stub-approved-by was free text (`"owner said yes"` certified placeholder PNGs). It is now a
    Command Center approval id (kind stub_render, bound to the sha256 of the run's copy ledger) verified by
    the ONE shared verifier, in this tool and again at P7."""

    run_tool = LegacyPageImagesTests.run_tool

    def ledger_file(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = pathlib.Path(tmp.name) / "ledger.json"
        path.write_text(json.dumps(dict(LEDGER, funnel_size=3)))
        return path

    def refused(self, approval_id, ledger_path=None, env=None):
        ledger_path = ledger_path or self.ledger_file()
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--ledger", str(ledger_path), "--skill71-root", str(SKILL71),
             "--brand-file", str(BRAND), "--brand-owner", "blackceo", "--out-dir", str(ledger_path.parent / "out"),
             "--image-provider", "stub", "--stub-approved-by", approval_id],
            capture_output=True, text=True, env=env or tool_env())
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("REFUSED: --stub-approved-by:", proc.stderr)
        self.assertFalse((ledger_path.parent / "out").exists(), "a refused stub run draws and writes nothing")
        return proc

    def test_free_text_is_refused_and_nothing_is_drawn(self):
        self.refused("owner said yes")
        self.refused("fixture-owner-approval")

    def test_an_approval_for_another_ledger_is_refused(self):
        ledger = self.ledger_file()
        other = ledger.parent / "other.json"
        other.write_text(json.dumps({"some": "other plan"}))
        self.refused(mint_for(other), ledger)

    def test_a_revoked_an_expired_and_a_wrong_kind_approval_are_refused(self):
        ledger = self.ledger_file()
        self.refused(mint_for(ledger, revoked=True), ledger)
        self.refused(mint_for(ledger, expires_in=-60), ledger)
        self.refused(mint_for(ledger, kind="design_board"), ledger)

    def test_an_unreachable_command_center_is_a_refusal_not_a_pass(self):
        ledger = self.ledger_file()
        env = tool_env()
        for key in ("MISSION_CONTROL_URL", "MC_API_TOKEN"):
            env.pop(key)
        proc = self.refused(mint_for(ledger), ledger, env=env)
        self.assertIn("MISSION_CONTROL_URL", proc.stderr)

    def test_a_verified_record_is_carried_in_the_receipt(self):
        proc, out = self.run_tool(dict(LEDGER, funnel_size=3), "--page", "thank-you")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        approval = json.loads(proc.stdout)["stub_approval"]
        ledger_hash = hashlib.sha256((out.parent / "ledger.json").read_bytes()).hexdigest()
        self.assertEqual(sorted(approval), ["approval_id", "kind", "plan_hash", "verified"])
        self.assertEqual((approval["kind"], approval["verified"], approval["plan_hash"]),
                         ("stub_render", True, ledger_hash))
        self.assertIn(approval["approval_id"], CC.rows)

    def test_the_real_provider_needs_no_stub_approval_and_records_none(self):
        proc, _ = self.run_tool(dict(LEDGER, funnel_size=3), "--image-provider", "kie")
        self.assertEqual(proc.returncode, 2)  # no --allow-paid: refused before any approval is looked at
        self.assertIn("--allow-paid", proc.stderr)
        self.assertNotIn("stub", proc.stderr.lower())


class OneDoorIntoSkill71(unittest.TestCase):
    """Issues 2, 10, 62: the tool never names the executor; it draws through run_governed_stage.py, so the
    stage gate is consulted first and an ungated stub run is refused outside a test harness."""

    run_tool = LegacyPageImagesTests.run_tool

    def test_the_tool_names_the_door_and_never_the_executor(self):
        source = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("stage_executor.py", source)
        self.assertIn("run_governed_stage.py", source)

    def test_a_stub_run_without_the_harness_marker_is_refused_by_the_gate_rule(self):
        proc, out = self.run_tool(dict(LEDGER, funnel_size=3), "--page", "thank-you", marker=None)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("AF-71-UNGATED", proc.stderr)
        self.assertFalse(list(out.rglob("section-*.png")), "no placeholder was drawn")
        self.assertFalse((out / "page-images-receipt.json").exists())

    def test_every_stage_goes_through_the_admission_call(self):
        proc, out = self.run_tool(dict(LEDGER, funnel_size=3), "--page", "thank-you")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        decisions = json.loads((out / "thank-you" / "private" / "governor.json").read_text())
        self.assertTrue(decisions, "run_governed_stage.py recorded its admission decisions")
        self.assertIn("direct_executor", json.dumps(decisions))


class LegacyToolRefusalsNameTheirCause(unittest.TestCase):
    """Round 4: two refusals that other checks would also catch, pinned by their own words."""

    run_tool = LegacyPageImagesTests.run_tool

    def test_a_stub_run_without_any_approval_says_so(self):
        proc, out = self.run_tool(dict(LEDGER, funnel_size=3), "--image-provider", "stub", "--stub-approved-by", "")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("needs the owner's approval", proc.stderr)
        self.assertFalse(out.exists())

    def test_a_skill71_tree_without_the_door_is_refused_by_name(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name) / "skill71"
        (root / "scripts").mkdir(parents=True)
        (root / "references").mkdir()
        (root / "scripts" / "build_production_request.py").write_text("")
        (root / "references" / "page-structures.json").write_text(json.dumps({"roles": {}}))
        ledger = pathlib.Path(tmp.name) / "ledger.json"
        ledger.write_text(json.dumps(dict(LEDGER, funnel_size=3)))
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--ledger", str(ledger), "--skill71-root", str(root), "--brand-file", str(BRAND),
             "--brand-owner", "blackceo", "--out-dir", str(pathlib.Path(tmp.name) / "out"), "--image-provider", "kie",
             "--allow-paid"], capture_output=True, text=True, env=tool_env())
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("lacks", proc.stderr)
        self.assertIn("run_governed_stage.py", proc.stderr)


class P7RechecksTheStubApproval(unittest.TestCase):
    """The P7 prover does not take the receipt's word: it verifies the record again, against the run's own
    copy_ledger.json, so a revoked approval, a changed ledger or a bare string fails AF-FUN-BUILD-VISUAL-STUB."""

    run_tool = LegacyPageImagesTests.run_tool

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import prove_sf_build
        self.build = prove_sf_build
        patch = mock.patch.dict(os.environ, CC.env())
        patch.start()
        self.addCleanup(patch.stop)
        proc, out = self.run_tool(dict(LEDGER, funnel_size=3))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.run_dir = out.parent / "run"
        self.run_dir.mkdir()
        out.rename(self.run_dir / "page-images")
        (self.run_dir / "copy_ledger.json").write_bytes((out.parent / "ledger.json").read_bytes())
        self.receipt = self.run_dir / "page-images" / "page-images-receipt.json"

    def stub_codes(self):
        return [m for c, m in self.build.visual_direction_violations(self.run_dir, 3)
                if c == "AF-FUN-BUILD-VISUAL-STUB"]

    def rewrite(self, **fields):
        data = json.loads(self.receipt.read_text())
        data.update(fields)
        self.receipt.write_text(json.dumps(data))

    def test_a_verified_record_clears_the_stub_check(self):
        self.assertEqual(self.stub_codes(), [])

    def test_a_bare_string_fails(self):
        self.rewrite(stub_approval="owner said yes")
        self.assertTrue(self.stub_codes())
        self.rewrite(stub_approval={"approval_id": "x", "verified": False})
        self.assertTrue(self.stub_codes())

    def test_a_missing_record_fails(self):
        self.rewrite(stub_approval=None)
        self.assertTrue(self.stub_codes())

    def test_a_genuine_id_and_matching_hash_without_verified_true_is_refused(self):
        """Judge loop 2: the receipt names a real approval id and the right plan hash, but the verified flag
        is missing, or false. Only the flag stands between that claim and a pass at P7 (the Command Center
        would verify the id), so recheck must refuse both, through the prover and through recheck itself."""
        import stub_approval
        good = json.loads(self.receipt.read_text())["stub_approval"]
        ledger = self.run_dir / "copy_ledger.json"
        self.assertEqual(stub_approval.recheck(good, ledger), [], "control: the untouched record verifies")
        missing = {k: v for k, v in good.items() if k != "verified"}
        for name, record in (("missing", missing), ("false", dict(good, verified=False)),
                             ("truthy string", dict(good, verified="true"))):
            with self.subTest(verified=name):
                self.assertTrue(stub_approval.recheck(record, ledger), "refused by recheck")
                self.rewrite(stub_approval=record)
                self.assertIn("not a verified approval record", " ".join(self.stub_codes()))

    def test_a_revoked_approval_fails_even_though_the_receipt_says_verified(self):
        approval = json.loads(self.receipt.read_text())["stub_approval"]
        CC.rows[approval["approval_id"]]["revoked"] = True
        self.assertTrue(self.stub_codes())

    def test_a_ledger_changed_after_the_approval_fails(self):
        (self.run_dir / "copy_ledger.json").write_text(json.dumps({"a": "different plan"}))
        self.assertIn("different copy ledger", " ".join(self.stub_codes()))

    def test_an_unreachable_command_center_fails_closed(self):
        with mock.patch.dict(os.environ, {"MISSION_CONTROL_URL": "http://127.0.0.1:1"}):
            self.assertTrue(self.stub_codes())



class EndToEndStubRunThroughTheGovernedDoor(unittest.TestCase):
    """Issue 2 (ruling WP-02-2.a): the three legacy stages come out of the governed door; P7's visual gate
    FAILS for want of final-mockups; after a fixture Design Board approval the same door draws final-mockups
    and the gate PASSES. The board is the Skill 71 test fixture (real tesseract reads it); nothing under
    Skill 6 or Skill 45 is touched."""

    run_tool = LegacyPageImagesTests.run_tool

    def visual_only(self, run_dir):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "prove_sf_build.py"), "--visual-only", "--run-dir", str(run_dir),
             "--funnel-size", "3"], capture_output=True, text=True, env=tool_env())

    def draw_final_mockups(self, run_dir, slug, tool):
        page = run_dir / "page-images" / slug
        build = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_production_request_with_layouts.py"), str(SKILL71 / "scripts"),
             "--manuscript", "copy/internal-manuscript.md", *tool.MANUSCRIPT_PAGES[slug]["build"],
             "--stage", "final-mockups", "--model", "STUB-NO-MODEL",
             "--out", "production-request-final-mockups.json", "--run-dir", "."],
            cwd=page, capture_output=True, text=True, env=tool_env())
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        request = json.loads((page / "production-request-final-mockups.json").read_text())
        request["design_board"] = dict(bf.SPEC, color_names={"gold": "Harbor", "navy": "Midnight", "cream": "Parchment"})
        n = 0
        for sec in request["sections"]:  # the page's images exist by now: the board shows real files
            for slot in sec.get("slots") or []:
                n += 1
                bf.png(page / "inputs" / f"img{n}.png", (40 * n % 250, 90, 140))
                slot["file"] = f"inputs/img{n}.png"
        plan = json.loads((page / "desktop-wireframe" / "section-plan.json").read_text())
        for sid in (i for sec in plan for i in sec["image_slot_ids"]):  # the wireframe's own slots, generated
            bf.png(page / "image-generation-qc" / f"Image-{sid.split('-')[-1]}.png", (60, 100, int(sid.split('-')[-1]) * 7 % 250))
        (page / "production-request-final-mockups.json").write_text(json.dumps(request))
        (page / "production-request.json").write_text(json.dumps(request))  # the board fixture reads this name
        bf.png(page / "inputs" / "logo.png", (30, 60, 90))
        (page / "font-action-plan").mkdir(exist_ok=True)
        (page / "font-action-plan" / "font-map.json").write_text(json.dumps(bf.FONT_MAP))
        door = [sys.executable, str(SKILL71 / "scripts" / "run_governed_stage.py"), ".", "--request",
                "production-request-final-mockups.json", "--stage", "final-mockups", "--provider", "stub"]
        # no board yet: the door refuses and draws nothing
        refused = subprocess.run(door, cwd=page, capture_output=True, text=True, env=tool_env())
        self.assertIn("no board yet", refused.stdout + refused.stderr)
        self.assertFalse((page / "final-mockups" / "stage-executor-record.json").exists())
        # a paid dispatch is stopped at the gate check, before any spend
        paid = subprocess.run(door[:-2] + ["--provider", "kie", "--allow-paid"], cwd=page, capture_output=True,
                              text=True, env=tool_env())
        self.assertEqual(paid.returncode, 1, paid.stdout + paid.stderr)
        self.assertIn("REFUSED", paid.stdout)
        self.assertFalse((page / "final-mockups").exists())
        # the fixture Design Board approval (the client's own recorded message)
        bf.seed_real_board(page, approved=True)
        done = subprocess.run(door, cwd=page, capture_output=True, text=True, env=tool_env())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue((page / "final-mockups" / "stage-executor-record.json").is_file())

    @bf.needs_ocr
    def test_visual_gate_fails_without_final_mockups_then_passes_after_the_approved_board(self):
        def render_board(path, palette, lines=(), size=(1600, 1200)):  # large type: tesseract reads every line
            from PIL import Image, ImageDraw, ImageFont
            path.parent.mkdir(parents=True, exist_ok=True)
            im = Image.new("RGB", size, (255, 255, 255))
            d = ImageDraw.Draw(im)
            for i, x in enumerate(palette):
                d.rectangle([20 + i * 90, 1100, 100 + i * 90, 1180], fill=x["hex"])
            font = ImageFont.load_default(size=36)
            for i, line in enumerate(lines):
                d.text((20 + (i // 20) * 800, 20 + (i % 20) * 50), line, fill=(20, 20, 20), font=font)
            im.save(path)

        spec = importlib.util.spec_from_file_location("legacy_downsell_images_e2e", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        proc, out = self.run_tool({**LEDGER, "funnel_size": 3})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        run_dir = out.parent / "run"
        run_dir.mkdir()
        out.rename(run_dir / "page-images")
        (run_dir / "copy_ledger.json").write_bytes((out.parent / "ledger.json").read_bytes())
        # the three stages came out of the governed door: every page recorded its admission decisions
        for slug in ("main", "upsell", "thank-you"):
            self.assertIn("direct_executor", (run_dir / "page-images" / slug / "private" / "governor.json").read_text())
        before = self.visual_only(run_dir)
        self.assertEqual(before.returncode, 2, before.stdout + before.stderr)
        self.assertIn("final-mockups", before.stdout + before.stderr)
        with mock.patch.object(bf, "render_board", render_board):
            for slug in ("main", "upsell", "thank-you"):
                self.draw_final_mockups(run_dir, slug, tool)
        recorded = subprocess.run([sys.executable, str(TOOL), "--record-final-mockups", "--out-dir",
                                   str(run_dir / "page-images")], capture_output=True, text=True, env=tool_env())
        self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
        after = self.visual_only(run_dir)
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)


class TheDoorGetsTheProviderAndThePaidFlag(unittest.TestCase):
    """Round 4: the tool hands the provider to the door, and appends --allow-paid for kie
    only (a kie request the door never sees the flag for would be refused; a stub request must never get it)."""

    setUp = ImageModelResolvedThroughSkill66.setUp
    run_main = ImageModelResolvedThroughSkill66.run_main

    def door_calls(self, *flags):
        adapter = self.root / "kie_live_adapter.py"
        adapter.write_text(FAKE_ADAPTER, encoding="utf-8")
        with mock.patch.dict(os.environ, {"KIE_LIVE_ADAPTER_PATH": str(adapter), "FAKE_LATEST": "gpt-image-8",
                                          **CC.env()}):
            # the stubbed door writes no stage record, so the run stops after the first door call: that call
            # is the evidence (the tool builds the door command the same way for every stage)
            _, _, seen = self.run_main(*flags)
        return [c for c in seen if pathlib.Path(c[1]).name == "run_governed_stage.py"]

    def test_a_kie_run_passes_allow_paid_and_the_provider_to_the_door(self):
        calls = self.door_calls("--image-provider", "kie", "--allow-paid")
        self.assertTrue(calls, "the tool reached the door")
        for cmd in calls:
            self.assertEqual(cmd[cmd.index("--provider") + 1], "kie")
            self.assertIn("--allow-paid", cmd)

    def test_a_stub_run_never_gets_allow_paid(self):
        calls = self.door_calls("--image-provider", "stub", "--stub-approved-by", mint_for(self.root / "ledger.json"))
        self.assertTrue(calls, "the tool reached the door")
        for cmd in calls:
            self.assertEqual(cmd[cmd.index("--provider") + 1], "stub")
            self.assertNotIn("--allow-paid", cmd)


class AMissingSharedVerifierRefuses(unittest.TestCase):
    """Round 4: stub_approval loads the ONE shared verifier; if that file is gone it must refuse (fail closed),
    never pass a stub approval it could not check. Both entry points: the tool's check and the P7 recheck."""

    def setUp(self):
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(sys.path.remove, str(SCRIPTS))
        import stub_approval
        self.stub = stub_approval
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ledger = pathlib.Path(tmp.name) / "ledger.json"
        self.ledger.write_text(json.dumps(dict(LEDGER, funnel_size=3)))
        self.gone = pathlib.Path(tmp.name) / "no-such-approval_record.py"
        patch = mock.patch.dict(os.environ, CC.env())
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_blank_approval_id_is_refused_before_the_verifier_is_asked(self):
        for blank in (None, "", "   ", 7):
            with self.subTest(blank=blank), mock.patch.object(self.stub, "_verifier", side_effect=AssertionError("asked")):
                with self.assertRaises(self.stub.StubApprovalRefused) as ctx:
                    self.stub.verify_for_ledger(blank, self.ledger)
            self.assertIn("no approval id", str(ctx.exception))

    def test_control_the_real_verifier_accepts_a_genuine_record(self):
        record = self.stub.verify_for_ledger(mint_for(self.ledger), self.ledger)
        self.assertTrue(record["verified"])
        self.assertEqual(self.stub.recheck(record, self.ledger), [])

    def test_verify_for_ledger_refuses_when_the_verifier_file_is_missing(self):
        approval_id = mint_for(self.ledger)  # genuine, so only the missing verifier can be the reason
        with mock.patch.object(self.stub, "_APPROVAL_RECORD", self.gone):
            with self.assertRaises(self.stub.StubApprovalRefused) as ctx:
                self.stub.verify_for_ledger(approval_id, self.ledger)
        self.assertIn("not installed", str(ctx.exception))

    def test_recheck_refuses_when_the_verifier_file_is_missing(self):
        record = self.stub.verify_for_ledger(mint_for(self.ledger), self.ledger)
        with mock.patch.object(self.stub, "_APPROVAL_RECORD", self.gone):
            problems = self.stub.recheck(record, self.ledger)
        self.assertEqual(len(problems), 1)
        self.assertIn("not installed", problems[0])


if __name__ == "__main__":
    unittest.main()
