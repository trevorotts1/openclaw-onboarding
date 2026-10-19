"""Assert-based checks for LAUNCH-02 core. Stdlib only: python3 -m unittest."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks, intake, package, route  # noqa: E402
from launcher_core.constants import (  # noqa: E402
    PLACEHOLDER_TOKENS,
    SEAM_IDS,
    SKILL_DIR_NAME,
    SKILL_NUMBER,
    SkillResolutionError,
    resolve_ref,
    resolve_skill_dir,
)


def base_intake(mode: str = "single_simple") -> dict:
    offers = [{"offer_id": "main-1", "name": "Black Friday Launch", "role": "main",
               "price": {"amount_minor": 49700, "currency": "USD"}}]
    if mode == "multiple_options":
        offers.append({"offer_id": "main-2", "name": "Launch + Coaching", "role": "main",
                       "price": {"amount_minor": 99700, "currency": "USD"}})
    return {
        "schema_version": "1.0",
        "tenant_id": "tenant-a",
        "location_id": "loc-a",
        "launch_id": "bf-2026",
        "revision": 1,
        "journey_mode": mode,
        "brand": {"ref": "brand-a", "hash": "a" * 64},
        "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-1", "hash": "b" * 64},
        "entitlement_attestation": {
            "basis": "purchase",
            "evidence_ref": "evidence-1",
            "attested_by": "operator",
            "purchase_reference": "order-1",
        },
        "offers": offers,
    }


def with_upsells(payload: dict) -> dict:
    p = copy.deepcopy(payload)
    p["offers"] += [
        {"offer_id": "u1", "name": "Upsell One", "role": "upsell_1",
         "price": {"amount_minor": 19700, "currency": "USD"}},
        {"offer_id": "d1", "name": "Downsell One", "role": "downsell_1",
         "price": {"amount_minor": 9700, "currency": "USD"}},
        {"offer_id": "u2", "name": "Upsell Two", "role": "upsell_2",
         "price": {"amount_minor": 29700, "currency": "USD"}},
    ]
    return p


def make_pieces(run_dir: Path, graph: dict, normalized: dict) -> dict:
    pieces = {}
    for node in graph["nodes"]:
        rel = f"pieces/{node['page_id']}/page.html"
        target = run_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<html>{node['role']}</html>\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
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
            "artifacts": [{"path": rel, "sha256": digest}],
            "author_session": "builder-1",
            "reviewer_session": None,
            "independent_review": False,
            "proof_class": "L0",
            "blockers": [],
            "native_bindings_ref": None,
            "test_only": True,
        }
    return pieces


class ConstantsTest(unittest.TestCase):
    def test_directory_name_derives_from_one_constant(self):
        self.assertEqual(SKILL_DIR_NAME, f"{SKILL_NUMBER}-black-friday-launcher")
        # SKILL_ROOT comes from this file's location, so the Launcher also runs
        # under a slug-named directory. The on-disk name is one of the two
        # conventions the resolver accepts, never a second source of truth.
        self.assertIn(SKILL_ROOT.name, (SKILL_DIR_NAME, "black-friday-launcher"))

    def test_resolver_accepts_either_convention_and_prefers_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bare = root / "signature-funnel"
            numeric = root / "49-signature-funnel"
            # The fixtures are pretending to be skill trees, and a skill tree
            # carries SKILL.md; resolution requires it so a stale or partial
            # directory can never win over a real one.
            bare.mkdir()
            (bare / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
            self.assertEqual(resolve_skill_dir("signature-funnel", root), bare)
            numeric.mkdir()
            (numeric / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
            self.assertEqual(resolve_skill_dir("signature-funnel", root), numeric)
            self.assertEqual(resolve_ref("49-signature-funnel/scripts/x.py", root),
                             numeric / "scripts" / "x.py")
            self.assertEqual(resolve_ref("signature-funnel/scripts/x.py", root),
                             numeric / "scripts" / "x.py")

    def test_resolver_ignores_a_directory_that_is_not_a_skill_tree(self):
        # A stale or partial <number>-<slug> directory carries no SKILL.md; it
        # must never win resolution over the real tree, or a 999 package whose
        # .claude/skills holds both would silently load the partial one.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / "83-black-friday-launcher"
            real = root / "black-friday-launcher"
            stale.mkdir()
            real.mkdir()
            (real / "SKILL.md").write_text("# real\n", encoding="utf-8")
            self.assertEqual(resolve_skill_dir("black-friday-launcher", root), real)

    def test_resolver_fails_closed_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SkillResolutionError) as ctx:
                resolve_skill_dir("no-such-skill", Path(tmp))
            self.assertIn("no-such-skill", str(ctx.exception))

    def test_remaining_named_seams_are_unique(self):
        self.assertEqual(len(SEAM_IDS), 2)
        self.assertEqual(len(set(SEAM_IDS)), 2)

    def test_registration_record_marks_number_as_assigned(self):
        record = json.loads((SKILL_ROOT / "registration.json").read_text(encoding="utf-8"))
        self.assertEqual(record["skill"]["number"], SKILL_NUMBER)
        self.assertTrue(record["skill"]["number_final"])
        self.assertEqual(sorted(record["open_decisions"]), sorted(SEAM_IDS))


class IntakeTest(unittest.TestCase):
    def test_valid_single_simple_defaults_are_recorded_not_silent(self):
        result = intake.validate(base_intake())
        self.assertEqual(result["journey_mode"], "single_simple")
        self.assertTrue(result["test_only"])
        self.assertTrue(result["provenance"]["test_only"].startswith("default:"))
        self.assertEqual(result["provenance"]["tenant_id"], "supplied")

    def test_missing_price_fails_closed(self):
        payload = base_intake()
        del payload["offers"][0]["price"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-OFFER")

    def test_zero_price_is_never_invented(self):
        payload = base_intake()
        payload["offers"][0]["price"]["amount_minor"] = 0
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-PRICE")

    def test_missing_required_field_names_the_field(self):
        payload = base_intake()
        del payload["tenant_id"]
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-MISSING")
        self.assertEqual(ctx.exception.field, "tenant_id")

    def test_undeclared_field_is_refused(self):
        payload = base_intake()
        payload["default_price"] = 100
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-UNKNOWN")

    def test_multiple_options_needs_two_main_offers(self):
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(base_intake("multiple_options") | {"offers": base_intake()["offers"]})
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-OFFER")

    def test_free_entry_is_not_reachable_by_omission(self):
        payload = base_intake()
        payload["journey_mode"] = "free_entry"
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-MODE")

    def test_upsell_two_without_a_parent_purchase_is_refused(self):
        payload = base_intake()
        payload["offers"].append({"offer_id": "u2", "name": "U2", "role": "upsell_2",
                                  "price": {"amount_minor": 100, "currency": "USD"}})
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-INTAKE-ROUTE")


class RouteTest(unittest.TestCase):
    def test_single_simple_skips_product_selection(self):
        graph = route.compile_route(intake.validate(base_intake()))
        self.assertEqual([n["role"] for n in graph["nodes"]],
                         ["landing", "checkout", "thank_you"])
        self.assertEqual(len(graph["edges"]), 2)

    def test_multiple_options_inserts_product_selection(self):
        graph = route.compile_route(intake.validate(base_intake("multiple_options")))
        self.assertEqual([n["role"] for n in graph["nodes"]],
                         ["landing", "product_selection", "checkout", "thank_you"])
        self.assertTrue(any(e["event"] == "selection_validated" for e in graph["edges"]))

    def test_full_chain_branches_match_the_contract(self):
        graph = route.compile_route(intake.validate(with_upsells(base_intake())))
        self.assertEqual([n["role"] for n in graph["nodes"]],
                         ["landing", "checkout", "upsell_1", "downsell_1", "upsell_2", "thank_you"])
        pairs = {(next(n["role"] for n in graph["nodes"] if n["page_id"] == e["from"]),
                  e["event"],
                  next(n["role"] for n in graph["nodes"] if n["page_id"] == e["to"]))
                 for e in graph["edges"]}
        self.assertIn(("upsell_1", "explicit_decline", "downsell_1"), pairs)
        self.assertIn(("downsell_1", "payment_succeeded", "upsell_2"), pairs)
        self.assertIn(("upsell_2", "explicit_decline", "thank_you"), pairs)

    def test_cycle_is_refused(self):
        graph = route.compile_route(intake.validate(base_intake()))
        graph["edges"].append({"from": graph["nodes"][-1]["page_id"],
                               "event": "explicit_decline",
                               "to": graph["nodes"][1]["page_id"],
                               "guard": "fabricated_cycle"})
        with self.assertRaises(route.RouteError) as ctx:
            route.validate_route(graph)
        self.assertIn(ctx.exception.code, ("AF-LAUNCH-ROUTE-CYCLE", "AF-LAUNCH-ROUTE-TERMINAL"))

    def test_unreachable_node_is_refused(self):
        graph = route.compile_route(intake.validate(base_intake()))
        graph["nodes"].append({"page_id": "orphan", "role": "upsell_1"})
        with self.assertRaises(route.RouteError) as ctx:
            route.validate_route(graph)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ROUTE-REACH")

    def test_payment_error_state_cannot_grant_access(self):
        graph = route.compile_route(intake.validate(base_intake()))
        graph["pending_failed_payment_behavior"] = "grant_access_anyway"
        with self.assertRaises(route.RouteError) as ctx:
            route.validate_route(graph)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-ROUTE-PAYMENT-ERROR")


def stub_council(_launch):
    """Offline Council stub: no live session, no network, no paid model."""
    return {"status": "advice_returned", "ready": True,
            "advice": {"recommendation": "stub advice", "advisory_only": True},
            "advice_state": "returned"}


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run"
        self.normalized = intake.validate(base_intake())
        self.graph = route.compile_route(self.normalized)
        self.pieces = make_pieces(self.run_dir, self.graph, self.normalized)
        self.out = package.assemble(self.run_dir, self.normalized, self.graph,
                                    self.pieces, council_runner=stub_council)
        self.manifest_path = self.run_dir / "package-manifest.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_assembles_manifest_and_receipt(self):
        self.assertTrue(self.manifest_path.is_file())
        self.assertTrue((self.run_dir / "receipt.json").is_file())
        self.assertEqual([p["role"] for p in self.out["manifest"]["pieces"]],
                         ["landing", "checkout", "thank_you"])
        self.assertEqual(self.out["receipt"]["manifest"]["sha256"],
                         hashlib.sha256(self.manifest_path.read_bytes()).hexdigest())

    def test_receipt_reuses_the_s49_store(self):
        self.assertIn(self.out["receipt"]["receipt_evidence"]["state"], ("absent", "verified"))
        self.assertEqual(self.out["receipt"]["receipt_evidence"]["store"],
                         "delegation_receipts.jsonl")

    def test_a_real_s49_receipt_moves_the_store_to_verified(self):
        module = package._load_receipt_module()
        self.assertIsNotNone(module, "Skill 49 delegation_receipt.py must be reachable")
        module.record(self.run_dir, phase="P3-IMAGES", provider="kie",
                      operation="createTask", provider_response_id="task-123",
                      http_status=200, remote_id="media-456", covers=["img-1"])
        evidence = package.receipt_evidence(self.run_dir)
        self.assertEqual(evidence["state"], "verified")
        self.assertEqual(evidence["entries"], 1)
        # Re-assembling seals the verified store into the receipt.
        out = package.assemble(self.run_dir, self.normalized, self.graph, self.pieces,
                               council_runner=stub_council)
        self.assertEqual(out["receipt"]["receipt_evidence"]["state"], "verified")
        self.assertEqual(checks.check_package(self.manifest_path, self.run_dir), [])

    def test_clean_package_passes_checks(self):
        self.assertEqual(checks.check_package(self.manifest_path, self.run_dir), [])

    def test_missing_artifact_source_fails_assembly(self):
        pieces = copy.deepcopy(self.pieces)
        pieces["landing"]["artifacts"][0]["path"] = "pieces/not-there.html"
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, pieces,
                             council_runner=stub_council)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-ARTIFACT-MISSING")

    def test_assemble_is_self_contained(self):
        for piece in self.out["manifest"]["pieces"]:
            for art in piece["artifacts"]:
                self.assertTrue((self.run_dir / art["path"]).is_file(), art["path"])
                self.assertTrue(art["path"].startswith("pieces/"), art["path"])

    def test_missing_piece_fails_assembly(self):
        pieces = dict(self.pieces)
        pieces.pop("checkout")
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, pieces,
                             council_runner=stub_council)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-MISSING")

    def test_blocked_piece_fails_assembly(self):
        pieces = copy.deepcopy(self.pieces)
        pieces["landing"]["status"] = "blocked"
        with self.assertRaises(package.PackageError) as ctx:
            package.assemble(self.run_dir, self.normalized, self.graph, pieces,
                             council_runner=stub_council)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-PKG-BLOCKED")

    def test_deleted_artifact_fails_check(self):
        art = self.out["manifest"]["pieces"][0]["artifacts"][0]["path"]
        (self.run_dir / art).unlink()
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-ARTIFACT-MISSING") for f in fails), fails)

    def test_tampered_artifact_fails_hash_check(self):
        art = self.out["manifest"]["pieces"][0]["artifacts"][0]["path"]
        (self.run_dir / art).write_text("tampered\n", encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-HASH") for f in fails), fails)

    def test_placeholder_binding_fails_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["bindings"]["cli"] = "/path/to/launcher"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-PLACEHOLDER") for f in fails), fails)

    def test_unresolved_binding_fails_check(self):
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["bindings"]["skill_entry"] = "not-a-real-file.md"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        fails = checks.check_package(self.manifest_path, self.run_dir)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-PATH-UNRESOLVED") for f in fails), fails)

    def test_placeholder_detector_knows_real_from_fake(self):
        self.assertTrue(checks.is_placeholder_path("/path/to/x"))
        self.assertTrue(checks.is_placeholder_path("skills/<name>/SKILL.md"))
        self.assertFalse(checks.is_placeholder_path("launcher_core/cli.py"))
        self.assertEqual(len(PLACEHOLDER_TOKENS), len(set(PLACEHOLDER_TOKENS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
