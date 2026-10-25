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


def base_intake() -> dict:
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
        "entitlement_attestation": {"basis": "purchase", "evidence_ref": "ev-1",
                                    "attested_by": "operator", "purchase_reference": "order-1"},
        "offers": [{"offer_id": "main-1", "name": "Launch", "role": "main",
                    "price": {"amount_minor": 49700, "currency": "USD"}}],
    }


def stub_council(_launch):
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub"}, "advice_state": "returned"}


def plan_fixture() -> dict:
    return json.loads(BF_PLAN.read_text(encoding="utf-8"))


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
    return out


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
        for role, piece in self.pieces.items():
            (pieces_dir / f"{role}.json").write_text(json.dumps(piece), encoding="utf-8")

    def _assemble(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["assemble", "--intake", str(self.intake_path),
                "--pieces", str(self.run_dir / "pieces"), "--out", str(self.run_dir), *extra]
        with mock.patch.object(cli.council, "planning_step", return_value=self.advice), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
