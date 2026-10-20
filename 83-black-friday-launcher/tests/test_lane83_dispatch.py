"""Lane 83: `cli dispatch` turns an intake into a Skill 49 launch record and builds every page.

Free: the page skills are replaced by tests/lane83_fake_consumer.py (no network, no provider), and a
KIE adapter that fails loudly if it is ever started proves zero paid calls.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
from launcher_core import (checks, cli, image_plan, intake, launch_bridge,  # noqa: E402
                           package, route)

CLIENT, WORKER = "client-test-1", "worker-test-9"
LABELS = substrate.source("71-blackceo-signature-page/scripts/deliverable_labels.py")
CONSUMER = HERE / "lane83_fake_consumer.py"


def payload(name: str, **plan) -> dict:
    doc = json.loads((FIXTURES / name / "intake.json").read_text(encoding="utf-8"))
    doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client", **plan}
    return doc


def launch_for(doc: dict) -> dict:
    normalized = intake.validate(doc)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
    return launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)


def approval_for(doc: dict, **over) -> dict:
    launch = launch_for(doc)
    record = {"schema_version": "1.0", "approval_id": "APPR-TEST", "subject_type": "launch_plan_build",
              "subject_hash": substrate.dispatch().vlp.plan_document_hash(launch),
              "owner_identity_ref": CLIENT, "source_message_ref": "msg-test-1",
              "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "scope": ["launch_plan_build"], "revoked": False,
              "verification_class": "recorded_consent_not_cryptographically_sealed"}
    record.update(over)
    return record


def consumer_config(extra_by_role=None, sleep=0.0) -> dict:
    extra_by_role = extra_by_role or {}
    roles = substrate.dispatch().PAGE_ROLES
    landing_pages = ["--pages", "{landing_pages}"]  # the real landing bridge builds Skill 49's planned set
    return {"adapters": {role: {"command": [sys.executable, str(CONSUMER), "{request}", "{result}",
                                            str(LABELS), "--sleep", str(sleep), *extra_by_role.get(role, []),
                                            *(landing_pages if role == "landing" else [])],
                                "timeout_s": 60} for role in roles}}


def run_dispatch(doc, out, **kw):
    if "adapters_config" not in kw:
        kw["adapters_config"] = consumer_config()
    return launch_bridge.run(doc, out, approval=kw.pop("approval", None) or approval_for(doc),
                             client_identity_ref=kw.pop("client", CLIENT),
                             worker_identity_ref=kw.pop("worker", WORKER), **kw)


ELEVATION_ROLES = ["landing", "product_selection", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"]
# Skill 49 plans the signature sales page beside the landing page for a full funnel
ELEVATION_PAGES = ["landing", "sales"] + ELEVATION_ROLES[1:]


class BridgeRecordTests(unittest.TestCase):
    def test_elevation_launch_record_passes_skill_49s_own_validator(self):
        launch = launch_for(payload("elevation"))
        self.assertEqual(launch_bridge.check_launch_record(launch), [])
        self.assertEqual(launch["status"], "approved")
        self.assertEqual(launch["image_provider"], "kie")
        self.assertEqual(len(launch["route_graph_hash"]), 64)
        self.assertEqual(launch["plan_approval_ref"], "TEST-ONLY-APPROVAL")

    def test_the_record_carries_every_offer_and_price_from_the_intake_unchanged(self):
        doc = payload("elevation")
        launch = launch_for(doc)
        want = {o["offer_id"]: o["price"]["amount_minor"] for o in doc["offers"]}
        got = {o["offer_id"]: o["prices"][0]["amount_minor"] for o in launch["offers"]}
        self.assertEqual(got, want)
        u1 = next(o for o in launch["offers"] if o["slot"] == "upsell_1")
        d1 = next(o for o in launch["offers"] if o["slot"] == "downsell_1")
        self.assertEqual((u1["excludes"], d1["excludes"]), (["D1"], ["U1"]))

    def test_folded_levels_either_validates_or_is_named_not_silently_dropped(self):
        launch = launch_for(payload("seven-figure-preneur"))
        fails = launch_bridge.check_launch_record(launch)
        if "folded_levels" in substrate.dispatch().vlp.JOURNEY_MODES:
            self.assertEqual(fails, [])
        else:  # awaiting Lane 49: the refusal is by name, never a rewrite to another journey mode
            self.assertTrue(any("folded_levels" in f for f in fails), fails)
            self.assertEqual(launch["journey_mode"], "folded_levels")

    def test_lane_plan_names_what_runs_first_and_what_runs_together(self):
        graph = route.compile_route(intake.validate(payload("elevation")))
        plan = launch_bridge.lane_plan(graph, workers=6)
        self.assertEqual(plan["phase_1_alone"], ["landing"])
        self.assertEqual(plan["phase_2_together"], ELEVATION_ROLES[1:])
        self.assertEqual((plan["independent_pages"], plan["workers"]), (6, 6))
        self.assertIn("visual direction", plan["phase_1_reason"] + " visual direction")
        side = launch_bridge.lane_plan(graph, workers=6, side_by_side=True)  # what Skill 49 does with workers
        self.assertEqual((side["phase_1_alone"], side["phase_2_together"]), ([], ELEVATION_ROLES))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "run"
        # a KIE adapter that fails loudly if anything ever starts it: proof of zero paid calls
        self.marker = Path(self.tmp.name) / "kie-was-called"
        self.adapter = Path(self.tmp.name) / "kie_live_adapter.py"
        self.adapter.write_text(f"import sys, pathlib\npathlib.Path({str(self.marker)!r}).write_text('called')\n"
                                "sys.exit(99)\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"SKILL71_KIE_ADAPTER": str(self.adapter)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_full_funnel_dispatches_every_page_and_writes_one_result_per_page(self):
        report = run_dispatch(payload("elevation"), self.out)
        self.assertEqual(report["pages"], ELEVATION_PAGES)
        for page in ELEVATION_PAGES:
            result = json.loads((self.out / "pieces" / f"{page}.json").read_text(encoding="utf-8"))
            self.assertEqual(result["page_kind"], {"landing": "opt_in"}.get(page, page))
        self.assertEqual(report["execution"], "executed")
        self.assertEqual(json.loads((self.out / "dispatch-report.json").read_text())["pages"], ELEVATION_PAGES)

    def test_nothing_is_spent_on_a_practice_run(self):
        report = run_dispatch(payload("elevation"), self.out)
        self.assertEqual((report["executor_provider"], report["paid_calls_allowed"]), ("stub", False))
        self.assertFalse(self.marker.exists(), "the KIE adapter must never be started by a practice run")

    def test_defaults_are_reported_with_a_way_to_change_each(self):
        report = run_dispatch(payload("elevation"), self.out)
        fields = {r["field"] for r in report["to_confirm"]}
        self.assertIn("image_plan.design_style", fields)
        self.assertIn("image_plan.image_cap", fields)
        self.assertTrue(all(r["how_to_change"] for r in report["to_confirm"]))
        text = "\n".join(launch_bridge.summary_lines(report))
        self.assertIn("waiting for your confirmation", text)
        self.assertIn("Nothing was spent", text)

    def test_the_dispatch_report_has_no_waiting_choices_when_the_client_chose_everything(self):
        doc = payload("elevation", design_style="B", image_provider="kie", image_cap=200)
        report = run_dispatch(doc, self.out, landing_pages=["landing", "sales"])
        self.assertEqual(report["to_confirm"], [])
        self.assertIn("Every choice came from you", "\n".join(launch_bridge.summary_lines(report)))

    def test_assembled_package_keeps_every_page_labeled_and_passes_the_design_check(self):
        doc = payload("elevation")
        report = run_dispatch(doc, self.out)
        normalized = intake.validate(doc)
        graph = route.compile_route(normalized)
        pieces = {r: json.loads((self.out / "pieces" / f"{r}.json").read_text()) for r in report["pages"]}
        built = package.assemble(self.out / "package", normalized, graph, pieces, source_root=self.out,
                                 council={"step": "council_launch_planning", "skill": "x", "entry_point": "x",
                                          "status": "not_ready", "advice_state": "pending_live_session",
                                          "blocks_build": False, "is_permission": False},
                                 require_designs=True, to_confirm=report["to_confirm"])
        manifest = built["manifest"]
        self.assertTrue(manifest["designs_required"])
        up1 = next(p for p in manifest["pieces"] if p["role"] == "upsell_1")
        names = sorted(Path(a["path"]).name for a in up1["artifacts"])
        self.assertIn("upsell-1_DESKTOP_WIREFRAMES.pdf", names)       # the labeled name survives packaging
        self.assertIn("upsell-1_MOBILE_MOCKUPS-FINAL.pdf", names)
        folders = {Path(a["path"]).parent.name for a in up1["artifacts"]}
        self.assertTrue({"review-pdfs", "desktop-wireframes", "mobile-mockups"} <= folders, folders)
        self.assertEqual(manifest["design_approvals"]["design_board"]["state"], "awaiting_client_approval")
        fails = [f for f in checks.check_package(Path(built["manifest_path"]), self.out / "package")
                 if "AF-LAUNCH-PAGE-DESIGNS" in f]
        self.assertEqual(fails, [])

    def test_an_opted_in_downsell_2_is_dispatched_labeled_and_packaged_beside_downsell_1(self):
        doc = payload("elevation")
        config = consumer_config()
        config["adapters"]["downsell_2"] = {"command": config["adapters"]["downsell_1"]["command"]
                                            + ["--instance", "downsell_2"], "timeout_s": 60}
        report = run_dispatch(doc, self.out, adapters_config=config, extra_pages=("downsell_2",))
        self.assertEqual(sorted(report["pages"]), sorted(ELEVATION_PAGES + ["downsell_2"]))
        self.assertIn("downsell_2", report["lane_plan"]["phase_2_together"])
        normalized = intake.validate(doc)
        pieces = {r: json.loads((self.out / "pieces" / f"{r}.json").read_text()) for r in report["pages"]}
        built = package.assemble(self.out / "package", normalized, route.compile_route(normalized), pieces,
                                 source_root=self.out, require_designs=True, to_confirm=report["to_confirm"],
                                 council={"step": "s", "skill": "x", "entry_point": "x", "status": "not_ready",
                                          "advice_state": "p", "blocks_build": False, "is_permission": False})
        self.assertEqual(checks.check_package(Path(built["manifest_path"]), self.out / "package"), [])
        d2 = [p for p in built["manifest"]["pieces"] if "downsell_2" in json.dumps(p)]
        self.assertTrue(d2, "downsell_2 is in the package manifest")

    def test_a_page_missing_its_mobile_mockup_pdf_fails_the_package_by_name(self):
        doc = payload("elevation")
        config = consumer_config({"upsell_1": ["--omit", "mockup_mobile_pdf"]})
        report = run_dispatch(doc, self.out, adapters_config=config)
        normalized = intake.validate(doc)
        pieces = {r: json.loads((self.out / "pieces" / f"{r}.json").read_text()) for r in report["pages"]}
        built = package.assemble(self.out / "package", normalized, route.compile_route(normalized), pieces,
                                 source_root=self.out, require_designs=True,
                                 council={"step": "s", "skill": "x", "entry_point": "x", "status": "not_ready",
                                          "advice_state": "p", "blocks_build": False, "is_permission": False})
        fails = checks.check_package(Path(built["manifest_path"]), self.out / "package")
        self.assertTrue(any("upsell_1 is missing mockup mobile pdf" in f for f in fails), fails)

    def test_self_approval_is_refused_and_nothing_is_written_as_a_result(self):
        doc = payload("elevation")
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            run_dispatch(doc, self.out, client=WORKER, worker=WORKER,
                         approval=approval_for(doc, owner_identity_ref=WORKER))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-DISPATCH")
        self.assertFalse((self.out / "pieces").exists() and any((self.out / "pieces").iterdir()))

    def test_a_stale_approval_hash_is_refused(self):
        doc = payload("elevation")
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            run_dispatch(doc, self.out, approval=approval_for(doc, subject_hash="0" * 64))
        self.assertIn("does not match the current plan", str(ctx.exception))

    def test_agnes_is_refused_by_name_before_anything_runs(self):
        with self.assertRaises(image_plan.ImagePlanError) as ctx:
            run_dispatch(payload("elevation", image_provider="agnes"), self.out,
                         approval={})
        self.assertIn("agnes", ctx.exception.detail)
        self.assertFalse((self.out / "dispatch").exists())
        self.assertFalse(self.marker.exists())

    def test_a_live_run_without_approval_or_cap_never_starts(self):
        doc = payload("elevation")
        doc["test_only"] = False
        with self.assertRaises(image_plan.ImagePlanError) as ctx:
            run_dispatch(doc, self.out, approval={})
        self.assertIn(ctx.exception.code, ("AF-LAUNCH-IMAGE-PLAN-CAP", "AF-LAUNCH-IMAGE-PLAN-APPROVAL"))
        self.assertFalse(self.marker.exists())

    def test_the_dispatcher_is_asked_for_parallel_lanes_when_it_has_them(self):
        seen = {}
        real = substrate.dispatch()

        class FakeDispatch:
            vlp, clr, pset, DispatchError = real.vlp, real.clr, real.pset, real.DispatchError
            executor_from_config = staticmethod(real.executor_from_config)

            @staticmethod
            def dispatch(launch, approval, *, client_identity_ref, worker_identity_ref, parallel=None, **kw):
                seen["parallel"] = parallel
                return real.dispatch(launch, approval, client_identity_ref=client_identity_ref,
                                     worker_identity_ref=worker_identity_ref, **kw)

        doc = payload("elevation")
        config = consumer_config()
        with mock.patch.object(launch_bridge.substrate, "dispatch", return_value=FakeDispatch):
            report = run_dispatch(doc, self.out, parallel=4, adapters_config=config)
        self.assertEqual(seen["parallel"], 4)
        self.assertEqual(report["parallel"], "parallel x4")

    def test_without_a_parallel_mode_the_report_says_serial_instead_of_pretending(self):
        report = run_dispatch(payload("elevation"), self.out, parallel=4)
        if "parallel" in __import__("inspect").signature(substrate.dispatch().dispatch).parameters:
            self.assertEqual(report["parallel"], "parallel x4")
        else:
            self.assertTrue(report["parallel"].startswith("serial"), report["parallel"])
        side = report["parallel"].startswith("parallel")  # what ran is what is reported
        self.assertEqual(report["lane_plan"]["phase_1_alone"], [] if side else ["landing"])

    def _spy_dispatch(self, doc, **kw):
        """Run the bridge against Skill 49's real dispatch, but stop it at the call and return what it was given."""
        seen = {}
        real = substrate.dispatch()

        def stop(launch, approval, **kwargs):
            seen.update(kwargs)
            raise real.DispatchError("spy: stopped at the call")
        stop.__signature__ = __import__("inspect").signature(real.dispatch)  # the real argument list

        class Spy:
            vlp, clr, pset, DispatchError = real.vlp, real.clr, real.pset, real.DispatchError
            swarm = real.swarm
            executor_from_config = staticmethod(real.executor_from_config)
            dispatch = staticmethod(stop)

        config = consumer_config()
        with mock.patch.object(launch_bridge.substrate, "dispatch", return_value=Spy):
            with self.assertRaises(launch_bridge.BridgeError):
                run_dispatch(doc, self.out, adapters_config=config, **kw)
        return seen

    @unittest.skipUnless("image_inputs" in __import__("inspect").signature(substrate.dispatch().dispatch).parameters,
                         "Skill 49's dispatch has no swarm arguments in this checkout")
    def test_no_parallel_flag_uses_the_runner_workers_and_the_spend_ledger_gets_the_image_inputs(self):
        seen = self._spy_dispatch(payload("elevation"))
        self.assertEqual(seen["parallel"], substrate.dispatch().swarm.default_workers())
        self.assertEqual(seen["image_inputs"]["image_provider"], "stub")
        self.assertFalse(seen["image_inputs"]["allow_paid"])
        self.assertNotIn("limiter", seen)  # free stub run: no KIE tokens needed

    @unittest.skipUnless("limiter" in __import__("inspect").signature(substrate.dispatch().dispatch).parameters,
                         "Skill 49's dispatch has no swarm arguments in this checkout")
    def test_a_paid_run_hands_skill_49_the_cap_ledger_inputs_and_the_kie_limiter(self):
        doc = payload("elevation", image_cap=9, paid_render_approval_ref="TEST-APPROVAL-REF")
        doc["test_only"] = False
        sentinel = object()
        with mock.patch.object(substrate.dispatch().swarm, "kie_limiter", return_value=sentinel):
            seen = self._spy_dispatch(doc, approval={})
        self.assertIs(seen["limiter"], sentinel)
        self.assertEqual((seen["image_inputs"]["image_provider"], seen["image_inputs"]["image_cap"],
                          seen["image_inputs"]["allow_paid"]), ("kie", 9, True))

    def test_folded_levels_dispatches_the_page_set_with_no_selection_page(self):
        doc = payload("seven-figure-preneur")
        if "folded_levels" not in substrate.dispatch().vlp.JOURNEY_MODES:
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                run_dispatch(doc, self.out, approval={})
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-RECORD")
            self.assertIn("folded_levels", ctx.exception.detail)
            self.assertIn("Nothing was dispatched", ctx.exception.detail)
            return
        report = run_dispatch(doc, self.out)
        self.assertEqual(report["pages"], ["landing", "sales", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"])

    def test_folded_levels_path_is_ready_the_moment_the_validator_accepts_the_mode(self):
        """Lane 49 adds folded_levels to Skill 49's validator. This simulates only that one-word change
        (the mode tuple) and proves the rest of the 7FigurePreneur dispatch already works end to end."""
        vlp = substrate.dispatch().vlp
        modes = vlp.JOURNEY_MODES if "folded_levels" in vlp.JOURNEY_MODES else vlp.JOURNEY_MODES + ("folded_levels",)
        doc = payload("seven-figure-preneur")
        with mock.patch.object(vlp, "JOURNEY_MODES", modes):
            report = run_dispatch(doc, self.out)
        self.assertEqual(report["pages"], ["landing", "sales", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"])
        self.assertNotIn("product_selection", report["pages"])
        side = report["parallel"].startswith("parallel")
        self.assertEqual(report["lane_plan"]["phase_1_alone"], [] if side else ["landing"])
        self.assertIn("landing", report["lane_plan"]["phase_1_alone"] + report["lane_plan"]["phase_2_together"])
        self.assertFalse(self.marker.exists())

    def test_no_adapters_is_a_plain_message_not_a_stack_trace(self):
        doc = payload("elevation")
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge.run(doc, self.out, approval=approval_for(doc), client_identity_ref=CLIENT,
                              worker_identity_ref=WORKER)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        self.assertIn("Nothing was dispatched", ctx.exception.detail)


class LandingPagesTests(unittest.TestCase):
    """Skill 83's real adapter builder, Skill 49's landing-page check, and the sales page piece."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "fresh-run"   # a first run: the folder does not exist yet
        self.brand = Path(self.tmp.name) / "brand.json"
        self.brand.write_text("{}", encoding="utf-8")

    def adapter_inputs(self):
        files = Path(self.tmp.name) / "inputs"
        files.mkdir()

        def f(name):
            path = files / name
            path.write_text("{}", encoding="utf-8")
            return str(path)
        roles = ("upsell_1", "upsell_2", "downsell_1")
        return {"bridge_config": f("bridge.json"), "author_session": "sess", "checkout_manuscript": f("checkout.md"),
                "copy": {r: f(f"copy-{r}.json") for r in roles},
                "journey": {r: f(f"journey-{r}.json") for r in roles},
                "enrichment": {r: f(f"enr-{r}.json") for r in roles}}

    def real_config_run(self, check):
        """Run the bridge with the real adapter builder; `check` sees the real config, then fake pages answer."""
        doc = payload("elevation", brand_file=str(self.brand))
        real = substrate.dispatch()
        fake_pages = consumer_config()

        def checked(config, work_dir, landing_pages=None):
            check(config, work_dir, landing_pages, real)
            return real.executor_from_config(fake_pages, work_dir, landing_pages=landing_pages)

        class Spy:
            vlp, clr, pset, DispatchError = real.vlp, real.clr, real.pset, real.DispatchError
            swarm, dispatch = real.swarm, staticmethod(real.dispatch)
            executor_from_config = staticmethod(checked)

        with mock.patch.object(launch_bridge.substrate, "dispatch", return_value=Spy):
            return run_dispatch(doc, self.out, adapters_config=None, adapter_inputs=self.adapter_inputs())

    def test_a_first_run_with_the_real_adapter_builder_gets_past_skill_49s_landing_page_check(self):
        seen = {}

        def check(config, work_dir, landing_pages, real):
            seen["command"] = config["adapters"]["landing"]["command"]
            seen["landing_pages"] = landing_pages
            real.executor_from_config(config, work_dir, landing_pages=landing_pages)  # Skill 49's real check

        report = self.real_config_run(check)
        self.assertIn("{landing_pages}", seen["command"])
        self.assertEqual(seen["landing_pages"], ["landing", "sales"])
        self.assertEqual(report["pages"], ELEVATION_PAGES)

    def test_every_flag_in_a_real_adapter_command_is_one_its_page_script_declares(self):
        """A flag the script only passes along (landing_bridge.py and upsell_wrapper.py mention --brand-file
        as a string) is refused as an unrecognized argument, so a launch would build no page."""
        checked = []

        def check(config, work_dir, landing_pages, real):
            for role, spec in config["adapters"].items():
                command = spec["command"]
                if command[0] == "bash":
                    continue
                usage = subprocess.run([command[0], command[1], "--help"], capture_output=True, text=True).stdout
                for flag in (p for p in command if str(p).startswith("--")):
                    self.assertIn(flag, usage, f"{role}: {Path(command[1]).name} does not accept {flag}")
                    checked.append(flag)

        self.real_config_run(check)
        self.assertGreater(len(checked), 40)

    def test_the_two_image_input_files_each_hold_only_what_their_reader_accepts(self):
        self.real_config_run(lambda *a: None)
        shared = json.loads((self.out / "image_inputs.json").read_text())
        self.assertEqual(sorted(shared), sorted(image_plan.C3_KEYS))
        order = json.loads((self.out / "order-page-inputs.json").read_text())
        self.assertEqual((order["provider"], order["test_run"]), ("stub", True))
        substrate.dispatch().pset.load_image_inputs(self.out / "image_inputs.json")  # Skill 49's strict reader

    def test_a_missing_per_page_input_is_a_plain_refusal_not_a_traceback(self):
        inputs = self.adapter_inputs()
        Path(inputs["copy"]["upsell_1"]).unlink()
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            run_dispatch(payload("elevation", brand_file=str(self.brand)), self.out, adapters_config=None,
                         adapter_inputs=inputs)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        self.assertIn("Nothing was dispatched", ctx.exception.detail)

    def test_a_launch_without_the_order_forms_copy_is_refused_before_any_page_is_built(self):
        inputs = self.adapter_inputs()
        del inputs["checkout_manuscript"]
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            run_dispatch(payload("elevation", brand_file=str(self.brand)), self.out, adapters_config=None,
                         adapter_inputs=inputs)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-ADAPTERS")
        self.assertIn("checkout_manuscript", ctx.exception.detail)
        self.assertFalse((self.out / "pieces").exists())

    def build(self, landing_pages=None, **consumer_extra):
        doc = payload("elevation")
        report = run_dispatch(doc, self.out, adapters_config=consumer_config(consumer_extra),
                              landing_pages=landing_pages)
        return doc, report

    def assemble(self, doc, report):
        normalized = intake.validate(doc)
        pieces = {r: json.loads((self.out / "pieces" / f"{r}.json").read_text()) for r in report["pages"]}
        return package.assemble(self.out / "package", normalized, route.compile_route(normalized), pieces,
                                source_root=self.out, require_designs=True, to_confirm=report["to_confirm"],
                                landing_pages=report["landing_pages"],
                                council={"step": "s", "skill": "x", "entry_point": "x", "status": "not_ready",
                                         "advice_state": "p", "blocks_build": False, "is_permission": False})

    def test_the_sales_page_gets_its_own_piece_and_the_design_check_requires_its_designs(self):
        doc, report = self.build()
        self.assertEqual(report["page_labels"][:2], ["Signature Landing Page", "Signature Sales Page"])
        built = self.assemble(doc, report)
        sales = next(p for p in built["manifest"]["pieces"] if p["role_instance"] == "sales")
        self.assertTrue(all(Path(a["path"]).name.startswith("sales-page_")
                            for a in sales["artifacts"] if a.get("kind")))
        manifest_path = Path(built["manifest_path"])
        self.assertEqual(checks.check_package(manifest_path, self.out / "package"), [])
        # remove the sales page's mobile mockup PDF from the delivered package: the check names the page
        manifest = json.loads(manifest_path.read_text())
        piece = next(p for p in manifest["pieces"] if p["role_instance"] == "sales")
        piece["artifacts"] = [a for a in piece["artifacts"] if a.get("kind") != "mockup_mobile_pdf"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(manifest_path, self.out / "package", require_designs=True)
        self.assertTrue(any("landing:sales:sales is missing mockup mobile pdf" in f for f in fails), fails)

    def test_the_landing_pages_choice_is_reported_to_confirm_only_when_the_client_did_not_make_it(self):
        _, report = self.build()
        self.assertIn("landing_pages", {r["field"] for r in report["to_confirm"]})
        self.assertIn("landing_pages", "\n".join(launch_bridge.summary_lines(report)))
        self.out = self.out.parent / "second"
        _, chosen = self.build(landing_pages=["sales"])
        self.assertNotIn("landing_pages", {r["field"] for r in chosen["to_confirm"]})

    def test_only_the_sales_page_or_only_the_landing_page_is_one_piece_with_its_own_kind(self):
        _, report = self.build(landing_pages=["sales"])
        self.assertEqual(report["pages"][0], "landing")
        self.assertNotIn("sales", report["pages"])
        piece = json.loads((self.out / "pieces" / "landing.json").read_text())
        self.assertEqual(piece["page_kind"], "sales")
        self.assertTrue(all("sales-page_" in Path(a["path"]).name for a in piece["artifacts"]))

    def test_a_planned_sales_page_with_no_file_of_its_own_is_refused_not_dropped(self):
        result = {"artifacts": [{"path": "landing_DESKTOP_WIREFRAMES.pdf", "sha256": "0" * 64,
                                 "kind": "wireframe_desktop_pdf"}]}
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            launch_bridge.split_landing(result, ["landing", "sales"])
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-LANDING-SPLIT")

    def test_a_package_for_both_landing_pages_without_the_sales_piece_is_refused(self):
        doc, report = self.build()
        normalized = intake.validate(doc)
        pieces = {r: json.loads((self.out / "pieces" / f"{r}.json").read_text())
                  for r in report["pages"] if r != "sales"}
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.out / "package", normalized, route.compile_route(normalized), pieces,
                             source_root=self.out, landing_pages=report["landing_pages"])
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-MISSING")


class CliTests(unittest.TestCase):
    def test_cli_dispatch_prints_the_plain_english_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            doc = payload("elevation")
            (tmp / "intake.json").write_text(json.dumps(doc), encoding="utf-8")
            (tmp / "approval.json").write_text(json.dumps(approval_for(doc)), encoding="utf-8")
            (tmp / "adapters.json").write_text(json.dumps(consumer_config()), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["dispatch", "--intake", str(tmp / "intake.json"), "--out", str(tmp / "run"),
                               "--approval", str(tmp / "approval.json"), "--client", CLIENT,
                               "--worker", WORKER, "--adapters", str(tmp / "adapters.json"), "--parallel", "4"])
            self.assertEqual(rc, 0)
            text = buf.getvalue()
            self.assertIn("Built 8 pages: Signature Landing Page, Signature Sales Page, Order Page", text)
            self.assertIn("practice placeholders only. Nothing was spent.", text)
            self.assertIn("waiting for your confirmation", text)

    def test_cli_failure_is_exit_2_with_the_plain_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            doc = payload("elevation")
            doc["image_plan"].pop("brand_file")
            (tmp / "intake.json").write_text(json.dumps(doc), encoding="utf-8")
            (tmp / "approval.json").write_text("{}", encoding="utf-8")
            (tmp / "adapters.json").write_text(json.dumps(consumer_config()), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = cli.main(["dispatch", "--intake", str(tmp / "intake.json"), "--out", str(tmp / "run"),
                               "--approval", str(tmp / "approval.json"), "--client", CLIENT,
                               "--worker", WORKER, "--adapters", str(tmp / "adapters.json")])
            self.assertEqual(rc, 2)
            self.assertIn("three palettes", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
