"""L26 (finding 42): a full Black Friday launch requires the shared launch plan.

Without the plan the calendar and planned-unit checks do not run, so a page-only
package used to assemble and pass while being called a launch. Full-launch
delivery now refuses without a plan, and plan-free output is labelled page-only
in the manifest, the receipt and the CLI result.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
BF_PLAN = REPO_ROOT / "shared-utils/signature_launch_contract/fixtures/black-friday.json"
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import cli, council, intake, launch_plan, package, route  # noqa: E402


_SPOOL = {}


def setUpModule():
    # Building a package appends launch events to ~/.openclaw/data/signature-launch/events-spool when no ingest
    # URL is set. Send them to a temp folder, so nothing in this module (or in a child launcher it starts,
    # which inherits the variable) writes into the real home folder.
    _SPOOL["dir"] = tempfile.TemporaryDirectory()
    _SPOOL["env"] = mock.patch.dict(os.environ, {"LAUNCH_EVENTS_SPOOL": _SPOOL["dir"].name})
    _SPOOL["env"].start()


def tearDownModule():
    _SPOOL["env"].stop()
    _SPOOL["dir"].cleanup()


def _base_intake_raw() -> dict:
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": "black-friday-2026",
        "revision": 1,
        "journey_mode": "single_simple",
        "brand": {"ref": "brand-a", "hash": "a" * 64},
        "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "offers": [{"offer_id": "main-1", "name": "Launch", "role": "main",
                    "price": {"amount_minor": 49700, "currency": "USD"}}],
    }


def stub_council(_launch):
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub"}, "advice_state": "returned"}


def plan_fixture() -> dict:
    from test_delivery_units import bound_plan
    return bound_plan()  # bound to this file's intake: tenant-a, loc-a, revision 1, approval 'b'*64 (CON-04)


def lane_deliveries(plan: dict, run_dir: Path) -> dict:
    """Producing-lane delivery receipts: staged bytes plus the lane's own
    validation and request echo (mirrors test_launch_plan_law)."""
    plan_sha = hashlib.sha256(
        (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode("utf-8")).hexdigest()
    out = {}
    for unit in launch_plan.planned_units(plan):
        rel = f"lane/{unit['id']}/delivery.html"
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"<html>{unit['id']}</html>\n".encode("utf-8"))
        out[unit["id"]] = {
            "state": "complete",
            "artifacts": [{"path": rel,
                           "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                           "size": target.stat().st_size}],
            "lane_validation": {"lane": "L06", "contract": "lane.output.v1",
                                "state": "passed"},
            "request": {"plan_sha256": plan_sha,
                        "request_id": f"lane-{unit['id']}",
                        "input_hash": "d" * 64},
        }
    from test_delivery_units import with_skill44_builds
    return with_skill44_builds(plan, run_dir, out)


def pieces_for(run_dir: Path, graph: dict, normalized: dict) -> dict:
    pieces = {}
    for node in graph["nodes"]:
        rel = f"pieces/{node['page_id']}/page.html"
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<html>{node['role']}</html>\n", encoding="utf-8")
        pieces[node["role"]] = {
            "schema_version": "1.0",
            "tenant_id": normalized["tenant_id"],
            "location_id": normalized["location_id"],
            "launch_id": normalized["launch_id"],
            "revision": normalized["revision"],
            "request_id": f"req-{node['page_id']}",
            "input_hash": "c" * 64,
            "page_id": node["page_id"],
            "status": "authored",
            "artifacts": [{"path": rel,
                           "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}],
            "author_session": "builder-1",
            "independent_review": False,
            "proof_class": "L0",
            "blockers": [],
            "native_bindings_ref": None,
            "test_only": True,
        }
    return pieces


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(base_intake())
        self.advice = council.planning_step(self.normalized, runner=stub_council)
        self.graph = route.compile_route(self.normalized, self.advice)
        self.pieces = pieces_for(self.run_dir, self.graph, self.normalized)

    def tearDown(self):
        self.tmp.cleanup()


class PackageScopeTests(_Base):
    def test_full_launch_without_the_shared_plan_is_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                             council=self.advice,
                             delivery_scope=package.DELIVERY_SCOPE_FULL)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PLAN-REQUIRED")
        self.assertFalse((self.run_dir / "package-manifest.json").exists())
        self.assertFalse((self.run_dir / "receipt.json").exists())

    def test_plan_free_package_is_labelled_page_only(self):
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council=self.advice)
        manifest = out["manifest"]
        self.assertNotIn("launch_plan", manifest)
        self.assertEqual(manifest["delivery_scope"], package.DELIVERY_SCOPE_PAGE_ONLY)
        self.assertIn("page-only", manifest["delivery_label"])
        self.assertEqual(out["receipt"]["delivery_scope"], package.DELIVERY_SCOPE_PAGE_ONLY)
        written = json.loads((self.run_dir / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(written["delivery_scope"], package.DELIVERY_SCOPE_PAGE_ONLY)

    def test_page_only_scope_with_a_plan_is_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                             council=self.advice,
                             launch_plan={"launch_id": self.normalized["launch_id"]},
                             delivery_scope=package.DELIVERY_SCOPE_PAGE_ONLY)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-SCOPE-CONFLICT")
        self.assertFalse((self.run_dir / "package-manifest.json").exists())
        self.assertFalse((self.run_dir / "receipt.json").exists())

    def test_an_unknown_delivery_scope_is_refused(self):
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                             council=self.advice, delivery_scope="launch_everything")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-SCOPE-UNKNOWN")
        self.assertFalse((self.run_dir / "package-manifest.json").exists())
        self.assertFalse((self.run_dir / "receipt.json").exists())

    @unittest.skipUnless(BF_PLAN.is_file(), "shared launch-plan contract fixture is not installed")
    def test_a_sealed_plan_labels_the_package_a_full_launch(self):
        plan = plan_fixture()
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council=self.advice, launch_plan=plan,
                               deliveries=lane_deliveries(plan, self.run_dir))
        manifest = out["manifest"]
        self.assertIn("launch_plan", manifest)
        self.assertEqual(manifest["delivery_scope"], package.DELIVERY_SCOPE_FULL)
        self.assertEqual(manifest["delivery_label"],
                         package.DELIVERY_LABELS[package.DELIVERY_SCOPE_FULL])
        self.assertEqual(out["receipt"]["delivery_scope"], package.DELIVERY_SCOPE_FULL)
        written = json.loads((self.run_dir / "package-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(written["delivery_scope"], package.DELIVERY_SCOPE_FULL)


class CliScopeTests(_Base):
    def setUp(self):
        super().setUp()
        self.intake_path = Path(self.tmp.name) / "intake.json"
        self.intake_path.write_text(json.dumps(base_intake()), encoding="utf-8")
        pieces_dir = self.run_dir / "pieces"
        # `assemble` refuses a package without a complete design set (B4, then the AF-LAUNCH-ASSEMBLE-DESIGN
        # refusal at the CLI). This class covers delivery scope, not the design set, so every page on the CLI
        # path comes from the free fake consumer, which writes the full labelled design set for the page.
        from test_lane83_designs import make_piece
        designs = Path(self.tmp.name) / "designs"
        designs.mkdir()
        for node in self.graph["nodes"]:
            piece = make_piece(designs, self.normalized, node)
            (pieces_dir / f"{node['role']}.json").write_text(json.dumps(piece), encoding="utf-8")

    def _assemble(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["assemble", "--intake", str(self.intake_path),
                "--pieces", str(self.run_dir / "pieces"), "--out", str(self.run_dir), *extra]
        with mock.patch.object(cli.council, "planning_step", return_value=self.advice), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_cli_partial_design_set_refuses_and_seals_nothing(self):
        # M3 (ASM-001): one page short of its mobile wireframe PDF. package.assemble refuses before its
        # first write, so the out dir holds no manifest, no receipt and no copied piece.
        from test_lane83_designs import make_piece
        node = self.graph["nodes"][0]
        piece = make_piece(Path(self.tmp.name) / "designs", self.normalized, node,
                           omit=["wireframe_mobile_pdf"])
        (self.run_dir / "pieces" / f"{node['role']}.json").write_text(json.dumps(piece), encoding="utf-8")
        before = sorted(str(p) for p in self.run_dir.rglob("*"))
        rc, out, err = self._assemble("--page-only")
        self.assertEqual(rc, 2, err)
        self.assertIn("AF-LAUNCH-ASSEMBLE-DESIGN", err)
        self.assertEqual(out.strip(), "")
        for name in ("package-manifest.json", "receipt.json", "assemble-steps.json"):
            self.assertFalse((self.run_dir / name).exists(), name)
        self.assertEqual(sorted(str(p) for p in self.run_dir.rglob("*")), before)  # nothing at all written

    def test_cli_refused_spine_emits_no_stage_closed(self):
        # M2 (G-5): with the graphics artifact removed the spine refuses; stage_closed must not precede it.
        events = []
        real = cli._close_step_spine

        def drop_graphics(out_dir, steps):
            (Path(out_dir) / "graphics-handoff.json").unlink()
            return real(out_dir, steps)

        with mock.patch.object(cli, "_launch_event", side_effect=lambda _id, ev: events.append(ev)), \
                mock.patch.object(cli, "_close_step_spine", side_effect=drop_graphics):
            rc, _out, err = self._assemble("--page-only")
        self.assertEqual(rc, 2, err)
        self.assertIn("AF-LAUNCH-STEP-ARTIFACT", err)
        self.assertNotIn("stage_closed", [e.get("event_type") for e in events])

    def test_cli_full_launch_requires_the_plan(self):
        rc, _out, err = self._assemble()
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-PLAN-REQUIRED", err)
        self.assertIn("--page-only", err)  # the refusal must name the CLI's own opt-in

    def test_cli_page_only_result_is_labelled_page_only(self):
        rc, out, err = self._assemble("--page-only")
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["delivery_scope"], package.DELIVERY_SCOPE_PAGE_ONLY)
        self.assertIn("page-only", payload["delivery_label"])

    def test_cli_page_only_with_a_plan_is_refused(self):
        plan_path = Path(self.tmp.name) / "plan.json"
        plan_path.write_text(json.dumps({"launch_id": "black-friday-2026"}), encoding="utf-8")
        rc, out, err = self._assemble("--page-only", "--launch-plan", str(plan_path))
        self.assertEqual(rc, 2)
        self.assertIn("AF-LAUNCH-SCOPE-CONFLICT", err)
        self.assertEqual(out.strip(), "")  # a refused assembly emits nothing



CHECKOUT_TERMS = {
    "guarantee_ref": "TEST-ONLY-GUARANTEE-REF", "guarantee_text": "Test-only guarantee text.",
    "terms_ref": "TEST-ONLY-TERMS-REF", "terms_text": "Test-only terms text.",
    "consent_ref": "TEST-ONLY-CONSENT-REF", "consent_text": "Test-only consent text.",
}


_ANSWERS_DIR = tempfile.TemporaryDirectory()  # the client's answers files for the inline intakes below


def _answers_doc(offers: list) -> dict:
    """A client-intake-answers/v1 doc that says exactly what the inline offers say (every entry provided)."""
    answers = {"billing": {"value": "one_time", "status": "provided"}}
    mains = []
    for o in offers:
        item = {"offer_id": o["offer_id"], "display_name": o["name"],
                "price": {"amount_minor": o["price"]["amount_minor"], "currency": o["price"]["currency"]},
                "deliverables": list((o.get("level") or {}).get("deliverables") or [])}
        if o["role"] == "main":
            mains.append(item)
        else:
            answers[o["role"]] = {"value": item, "status": "provided"}
    answers["packages"] = {"value": mains, "status": "provided"}
    return {"schema": "client-intake-answers/v1", "answers": answers}


def with_checkout_facts(payload: dict) -> dict:
    """The owner-supplied checkout facts intake requires (CHK-16): terms block + delivery per offer,
    and the price provenance (source_ref per offer plus the answers file they resolve in)."""
    payload.setdefault("checkout_terms", dict(CHECKOUT_TERMS))
    mains = 0
    for o in payload["offers"]:
        o.setdefault("delivery", {"destination": f"https://members.example.com/{o['offer_id']}",
                                  "owner_confirmed": True})
        if o["role"] in ("upsell_1", "downsell_1", "upsell_2") or (
                o["role"] == "main" and payload["journey_mode"] != "single_simple"):
            o.setdefault("level", {"state": "supplied", "name": o["name"],
                                   "deliverables": [f"{o['name']} access"]})
        if o["role"] == "main":
            o["price"].setdefault("source_ref", f"answers-file:packages[{mains}]")
            mains += 1
        else:
            o["price"].setdefault("source_ref", f"answers-file:{o['role']}")
    if "answers_file" not in payload:
        text = json.dumps(_answers_doc(payload["offers"]), indent=1, sort_keys=True)
        path = Path(_ANSWERS_DIR.name) / f"answers-{hashlib.sha256(text.encode()).hexdigest()[:16]}.json"
        path.write_text(text, encoding="utf-8")
        payload["answers_file"] = str(path)
    return payload


def base_intake(*args, **kwargs) -> dict:
    return with_checkout_facts(_base_intake_raw(*args, **kwargs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
