"""Lane 83: AF-LAUNCH-PAGE-DESIGNS, slot-keyed packaging, adapter image wiring and the graphics hooks.

Free: pure files and fixtures. Nothing calls a provider or a hosting service.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import adapters  # noqa: E402
import substrate  # noqa: E402
from launcher_core import (checks, graphics_hooks, intake, package, page_designs, route)  # noqa: E402

COUNCIL = {"step": "council_launch_planning", "skill": "x", "entry_point": "x", "status": "not_ready",
           "advice_state": "pending_live_session", "blocks_build": False, "is_permission": False}
CONSUMER = HERE / "lane83_fake_consumer.py"
LABELS = substrate.source("71-blackceo-signature-page/scripts/deliverable_labels.py")


def fixture(name):
    return json.loads((FIXTURES / name / "intake.json").read_text(encoding="utf-8"))


def make_piece(work: Path, normalized, node, *, instance=None, omit=(), provider="stub", extra_args=()):
    """One page result from the free fake consumer, then loaded back as the dict `assemble` takes."""
    req = {"tenant_id": normalized["tenant_id"], "location_id": normalized["location_id"],
           "launch_id": normalized["launch_id"], "revision": normalized["revision"],
           "request_id": f"req-{instance or node['role']}", "input_hash": "c" * 64,
           "page_id": node["page_id"], "page_role": node["role"], "test_only": True}
    tag = instance or node["role"]
    req_path, res_path = work / f"req-{tag}.json", work / f"res-{tag}.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    cmd = [sys.executable, str(CONSUMER), str(req_path), str(res_path), str(LABELS), "--provider", provider]
    for kind in omit:
        cmd += ["--omit", kind]
    if instance:
        cmd += ["--instance", instance]
    subprocess.run(cmd + list(extra_args), check=True)
    piece = json.loads(res_path.read_text(encoding="utf-8"))
    if instance:
        piece["page_id"] = f"{normalized['launch_id']}-{instance.upper()}"
    return piece


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        self.normalized = intake.validate(fixture("elevation"))
        self.graph = route.compile_route(self.normalized)

    def tearDown(self):
        self.tmp.cleanup()

    def pieces(self, **per_role):
        return {n["role"]: make_piece(self.work, self.normalized, n, **per_role.get(n["role"], {}))
                for n in self.graph["nodes"]}

    def assemble(self, pieces, name="pkg", **kw):
        kw.setdefault("require_designs", True)
        return package.assemble(self.work / name, self.normalized, self.graph, pieces,
                                source_root=self.work, council=COUNCIL, **kw)

    def check(self, built, name="pkg"):
        return checks.check_package(Path(built["manifest_path"]), self.work / name)


class DesignCheckTests(Base):
    def test_a_package_with_every_page_fully_designed_and_labeled_passes(self):
        built = self.assemble(self.pieces())
        self.assertEqual(self.check(built), [])

    def test_a_design_less_package_fails_for_every_page(self):
        pieces = self.pieces()
        for role, piece in pieces.items():
            doc = self.work / f"{role}-page.html"
            doc.write_text("<html></html>", encoding="utf-8")
            piece["artifacts"] = [{"path": str(doc), "sha256": hashlib.sha256(doc.read_bytes()).hexdigest()}]
        fails = self.check(self.assemble(pieces, name="bare"), name="bare")
        for role in ("landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"):
            self.assertTrue(any(f"{role} is missing wireframe desktop section" in f for f in fails), (role, fails))

    def test_a_page_missing_a_kind_is_named_with_the_kind(self):
        for kind in page_designs.KINDS:
            built = self.assemble(self.pieces(checkout={"omit": [kind]}), name=f"k-{kind}")
            fails = self.check(built, name=f"k-{kind}")
            self.assertIn(f"AF-LAUNCH-PAGE-DESIGNS: checkout is missing {kind.replace('_', ' ')}", fails, kind)

    def test_stub_made_images_fail_a_real_package_but_pass_a_test_only_one(self):
        built = self.assemble(self.pieces())
        manifest = json.loads(Path(built["manifest_path"]).read_text(encoding="utf-8"))
        root = self.work / "pkg"
        self.assertEqual(page_designs.design_violations(manifest, root), [])  # test_only true: placeholders fine
        manifest["test_only"] = False
        fails = page_designs.design_violations(manifest, root)
        self.assertTrue(any("made by the stub provider" in f for f in fails), fails[:3])
        real = self.assemble(self.pieces(**{n["role"]: {"provider": "kie"} for n in self.graph["nodes"]}),
                             name="real")
        manifest = json.loads(Path(real["manifest_path"]).read_text(encoding="utf-8"))
        manifest["test_only"] = False
        self.assertEqual(page_designs.design_violations(manifest, self.work / "real"), [])

    def test_a_file_not_labeled_for_its_own_page_fails(self):
        pieces = self.pieces()
        art = next(a for a in pieces["landing"]["artifacts"] if a["kind"] == "wireframe_desktop_pdf")
        wrong = Path(art["path"]).with_name("upsell-1_DESKTOP_WIREFRAMES.pdf")
        Path(art["path"]).rename(wrong)
        art["path"] = str(wrong)
        fails = self.check(self.assemble(pieces, name="mislabeled"), name="mislabeled")
        self.assertTrue(any("is not labeled for this page" in f and "'landing_'" in f for f in fails), fails)

    def test_design_and_final_mockup_approvals_are_recorded_as_waiting_for_the_client(self):
        built = self.assemble(self.pieces())
        approvals = built["manifest"]["design_approvals"]
        self.assertEqual({k: v["state"] for k, v in approvals.items()},
                         {"design_board": "awaiting_client_approval", "final_mockups": "awaiting_client_approval"})
        self.assertEqual(built["receipt"]["design_approvals"], approvals)
        manifest = json.loads(Path(built["manifest_path"]).read_text(encoding="utf-8"))
        manifest["design_approvals"]["final_mockups"] = {"state": "approved", "approval_ref": ""}
        self.assertTrue(any("approved with no approval reference" in f
                            for f in page_designs.design_violations(manifest, self.work / "pkg")))
        del manifest["design_approvals"]
        self.assertTrue(any("does not record the client approval state" in f
                            for f in page_designs.design_violations(manifest, self.work / "pkg")))

    def test_the_check_is_opt_in_for_old_style_packages_and_on_for_deliveries(self):
        bare = self.assemble(self.pieces(), name="optional", require_designs=False)
        self.assertFalse(bare["manifest"]["designs_required"])
        manifest_path = Path(bare["manifest_path"])
        self.assertEqual(checks.check_package(manifest_path, self.work / "optional"), [])
        self.assertEqual(checks.check_package(manifest_path, self.work / "optional", require_designs=True), [])


class SlotTests(Base):
    def downsell_2(self, label_instance="downsell_2"):
        node = next(n for n in self.graph["nodes"] if n["role"] == "downsell_1")
        return make_piece(self.work, self.normalized, node, instance=label_instance)

    def test_two_pages_of_one_role_with_different_slots_both_survive_packaging(self):
        pieces = self.pieces()
        pieces["downsell_2"] = self.downsell_2()
        built = self.assemble(pieces, name="two-downsells")
        got = [(p["role"], p["role_instance"], p["slot"]) for p in built["manifest"]["pieces"]
               if p["role"] == "downsell_1"]
        self.assertEqual(sorted(got, key=str), sorted([("downsell_1", None, "downsell_1"),
                                                       ("downsell_1", "downsell_2", "downsell_2")], key=str))
        self.assertEqual(self.check(built, name="two-downsells"), [])
        d2 = next(p for p in built["manifest"]["pieces"] if p["slot"] == "downsell_2")
        self.assertTrue(all(Path(a["path"]).name.startswith("downsell-2_") for a in d2["artifacts"]
                            if a.get("kind")))
        self.assertEqual({p["page_id"] for p in built["manifest"]["pieces"]}.__len__(), 8)

    def test_downsell_2_is_held_to_the_same_design_set_as_every_page(self):
        pieces = self.pieces()
        node = next(n for n in self.graph["nodes"] if n["role"] == "downsell_1")
        pieces["downsell_2"] = make_piece(self.work, self.normalized, node, instance="downsell_2",
                                          omit=["wireframe_mobile_pdf"])
        built = self.assemble(pieces, name="d2-short")
        fails = self.check(built, name="d2-short")
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: downsell_1:downsell_2 is missing wireframe mobile pdf", fails)

    def test_downsell_2_labeled_as_downsell_1_is_caught(self):
        pieces = self.pieces()
        node = next(n for n in self.graph["nodes"] if n["role"] == "downsell_1")
        pieces["downsell_2"] = make_piece(self.work, self.normalized, node)  # files named downsell-1_
        pieces["downsell_2"]["page_id"] = f"{self.normalized['launch_id']}-DOWNSELL_2"
        pieces["downsell_2"]["role_instance"] = "downsell_2"
        built = self.assemble(pieces, name="d2-mislabeled")
        fails = self.check(built, name="d2-mislabeled")
        self.assertTrue(any("'downsell-2_'" in f for f in fails), fails[:2])

    def test_a_downsell_2_with_no_downsell_1_page_is_refused(self):
        normalized = intake.validate(fixture("elevation"))
        offers = [o for o in normalized["offers"] if o["role"] not in ("downsell_1", "upsell_1", "upsell_2")]
        raw = fixture("elevation")
        raw["offers"] = [o for o in raw["offers"] if o["role"] not in ("downsell_1", "upsell_1", "upsell_2")]
        normalized = intake.validate(raw)
        graph = route.compile_route(normalized)
        pieces = {n["role"]: make_piece(self.work, normalized, n) for n in graph["nodes"]}
        pieces["downsell_2"] = make_piece(self.work, normalized, graph["nodes"][0], instance="downsell_2")
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.work / "orphan", normalized, graph, pieces, source_root=self.work,
                             council=COUNCIL)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-SLOT")
        self.assertTrue(offers)

    def test_two_different_files_that_would_land_on_one_path_are_refused(self):
        pieces = self.pieces()
        landing = pieces["landing"]
        # one file already sits in its page folder; a second, different file has the same name beside it
        page_dir = self.work / "pieces" / landing["page_id"]
        page_dir.mkdir(parents=True)
        inside = page_dir / "notes.txt"
        beside = self.work / "notes.txt"
        inside.write_bytes(b"one")
        beside.write_bytes(b"two")
        landing["artifacts"] = [{"path": str(inside), "sha256": hashlib.sha256(b"one").hexdigest()},
                                {"path": str(beside), "sha256": hashlib.sha256(b"two").hexdigest()}]
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(pieces, name="collide", require_designs=False)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-COLLISION")


class PageTypesTests(unittest.TestCase):
    def test_without_the_contract_file_the_builtin_set_is_used_and_says_so(self):
        spec, source = page_designs.load_page_types(Path("/nonexistent-root"))
        self.assertEqual((spec, source), ({}, "builtin"))
        self.assertEqual(page_designs.required_kinds({"role": "upsell_1"}, spec), list(page_designs.KINDS))

    def test_a_page_types_file_adds_requirements_with_no_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "49-signature-funnel"
            (skill / "structure").mkdir(parents=True)
            (skill / "SKILL.md").write_text("x", encoding="utf-8")
            (skill / "structure" / "page_types.json").write_text(json.dumps({"pages": {
                "sales_page": {"role": "landing", "page_kind": "sales",
                               "deliverables": ["wireframe_desktop_pdf", "mockup_mobile_pdf"]}}}), encoding="utf-8")
            spec, source = page_designs.load_page_types(root)
            self.assertTrue(source.startswith("file:"), source)
            self.assertEqual(page_designs.required_kinds({"role": "landing", "page_kind": "sales"}, spec),
                             ["wireframe_desktop_pdf", "mockup_mobile_pdf"])

    def test_label_slug_follows_skill_71_names(self):
        self.assertEqual(page_designs.label_slug({"role": "upsell_1"}), "upsell-1")
        self.assertEqual(page_designs.label_slug({"role": "downsell_1", "role_instance": "downsell_2"}), "downsell-2")
        self.assertEqual(page_designs.label_slug({"role": "landing", "page_kind": "sales"}), "sales-page")
        self.assertEqual(page_designs.label_slug({"role": "landing", "page_kind": "landing"}), "landing")
        self.assertEqual(page_designs.page_key({"role": "landing", "page_kind": "sales"}), "landing:sales")

    def test_classify_reads_skill_71_file_names(self):
        labels = substrate.load("71-blackceo-signature-page/scripts/deliverable_labels.py", "lane83_labels_t")
        self.assertEqual(page_designs.classify(labels.pdf_name("upsell_1", "mobile", "mobile-tablet")),
                         "wireframe_mobile_pdf")
        self.assertEqual(page_designs.classify(labels.pdf_name("landing", "desktop", "final-mockups")),
                         "mockup_desktop_pdf")
        self.assertEqual(page_designs.classify(labels.image_name("landing", "desktop", "desktop-wireframe", 1, 8, "Hero")),
                         "wireframe_desktop_section")
        self.assertEqual(page_designs.classify(labels.board_name("landing", "combined", "final-mockups") + ".png"),
                         "board")
        self.assertIsNone(page_designs.classify("page.html"))


class AdapterWiringTests(unittest.TestCase):
    def inputs(self, tmp: Path):
        work = tmp / "work"
        work.mkdir()
        files = {}
        for name in ("launch", "bridge", "images"):
            files[name] = tmp / f"{name}.json"
            files[name].write_text("{}", encoding="utf-8")
        per = {role: tmp / f"x-{role}.json" for role in ("upsell_1", "upsell_2", "downsell_1")}
        for p in per.values():
            p.write_text("{}", encoding="utf-8")
        return {"work_dir": work, "launch_record": files["launch"], "bridge_config": files["bridge"],
                "author_session": "session-test", "copy": per, "journey": per, "enrichment": per,
                "image_inputs": files["images"]}

    PLAN = {"design_style": "B", "brand_file": "/tmp/b.json", "brand_owner": "Client", "image_cap": 50}

    def test_every_wrapper_that_declares_a_shared_image_flag_receives_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = adapters.build_dispatch_config(**self.inputs(Path(tmp)), image_plan=self.PLAN,
                                                    image_provider="stub")
            wiring = adapters.image_wiring(config)
            down = config["adapters"]["downsell_1"]["command"]
            for flag, value in (("--brand-file", "/tmp/b.json"), ("--brand-owner", "Client"), ("--image-cap", "50")):
                self.assertEqual(down[down.index(flag) + 1], value)
            self.assertEqual(down[down.index("--image-provider") + 1], "stub")
            self.assertIn("--skill71-root", wiring["downsell_1"])
            self.assertNotIn("--allow-paid", down)  # a practice run never carries the paid switch

    def test_wiring_is_driven_by_what_each_wrapper_declares_so_none_can_break(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = adapters.build_dispatch_config(**self.inputs(Path(tmp)), image_plan=self.PLAN)
            for role, spec in config["adapters"].items():
                for flag in adapters.image_wiring(config)[role]:
                    script = next(Path(p) for p in spec["command"] if str(p).endswith(".py"))
                    self.assertTrue(adapters._declares(script, flag) or flag in spec["command"], (role, flag))

    def test_without_an_image_plan_the_commands_are_exactly_what_they_were(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self.inputs(Path(tmp))
            plain = adapters.build_dispatch_config(**inputs)
            planned = adapters.build_dispatch_config(**inputs, image_plan=self.PLAN)
            self.assertTrue(all(flags == [] for flags in adapters.image_wiring(plain).values()),
                            adapters.image_wiring(plain))
            self.assertNotEqual(plain["adapters"]["downsell_1"], planned["adapters"]["downsell_1"])


class GraphicsHooksTests(Base):
    def test_the_automatic_fail_battery_is_read_from_the_stage_contract(self):
        battery = graphics_hooks.autofail_battery()
        self.assertEqual([r["code"] for r in battery], [f"AF-G{i}" for i in range(1, 9)])

    def test_qc_request_lists_every_image_the_battery_and_the_independence_rule(self):
        built = self.assemble(self.pieces())
        job = self.work / "job"
        request = graphics_hooks.qc_request(built["manifest"], self.work / "pkg", job,
                                            author_models={"landing_desktop_wireframe_s01-of-02_hero": "model-a"})
        self.assertEqual(request["procedure"], "SOP-GIP-02")
        self.assertEqual(request["pass_bar"], {"average_at_least": 8.5, "automatic_failures": 0})
        self.assertEqual(len(request["automatic_fail_battery"]), 8)
        pages = {a["page"] for a in request["assets"]}
        self.assertEqual(pages, {n["role"] for n in self.graph["nodes"]})
        self.assertTrue(all(a["local_path"].endswith(".png") for a in request["assets"]))
        unknown = [a for a in request["assets"] if a["prompt_author_model"] == "UNKNOWN"]
        self.assertTrue(unknown)  # an unknown author model is recorded as unknown, never guessed
        self.assertIn("NOT independent", request["reviewer_rule"])
        self.assertTrue((job / "qc" / "image_qc_request.json").is_file())

    def test_delivery_record_never_publishes_and_names_the_missing_capability(self):
        built = self.assemble(self.pieces())
        job = self.work / "job"
        record = graphics_hooks.delivery_record(built["manifest"], self.work / "pkg", job, probe_env={})
        self.assertFalse(record["published"])
        self.assertEqual(record["publishing_performed_by_this_record"], "never")
        self.assertEqual(record["delivery_state"], "local_only_missing_capability")
        self.assertTrue(any("no live hosted link" in m for m in record["missing_capability"]))
        self.assertTrue(all(a["hosted"] is False and a["public_url"] is None for a in record["assets"]))
        self.assertEqual(record["qc_summary"]["not_reviewed"], len(record["assets"]))
        self.assertNotIn("pit_", json.dumps(record).lower())  # no credential value ever lands in the record

    def test_delivery_record_reads_an_existing_hosting_ledger_but_only_trusts_live_links(self):
        built = self.assemble(self.pieces())
        job = self.work / "job"
        images = graphics_hooks.collect_images(built["manifest"], self.work / "pkg")
        (job / "qc").mkdir(parents=True)
        (job / "qc" / "image_qc_report.json").write_text(json.dumps({"assets": [
            {"local_path": a["local_path"], "asset_id": a["asset_id"], "average": 9.0, "pass": True,
             "triggered_autofails": []} for a in images]}), encoding="utf-8")
        (job / "media_library.json").write_text(json.dumps({"uploaded": [
            {"local_path": a["local_path"], "ghl_upload_status": "complete", "public_url": "https://example.test/x.png",
             "liveness": {"live": True}} for a in images]}), encoding="utf-8")
        record = graphics_hooks.delivery_record(built["manifest"], self.work / "pkg", job)
        self.assertEqual(record["delivery_state"], "hosted_links_recorded")
        self.assertEqual(record["missing_capability"], [])
        self.assertEqual(record["qc_summary"]["qc_passed"], len(images))
        (job / "media_library.json").write_text(json.dumps({"uploaded": [
            {"local_path": a["local_path"], "ghl_upload_status": "complete", "public_url": "https://example.test/x.png",
             "liveness": {"live": False}} for a in images]}), encoding="utf-8")
        again = graphics_hooks.delivery_record(built["manifest"], self.work / "pkg", job)
        self.assertEqual(again["delivery_state"], "local_only_missing_capability")


if __name__ == "__main__":
    unittest.main(verbosity=2)
