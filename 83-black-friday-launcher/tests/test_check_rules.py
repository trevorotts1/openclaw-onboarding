"""Package check: the check_rules seam, honest design levels, the to_confirm gate and route-graph law.

Free: pure files and the fake page consumer. Nothing calls a provider or a hosting service.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import route_law  # noqa: E402
import substrate  # noqa: E402
from launcher_core import check_rules, checks, cli, intake, package, page_designs, route  # noqa: E402
from test_lane83_designs import COUNCIL, make_piece  # noqa: E402

PDF_AND_BOARD = ["wireframe_desktop_pdf", "wireframe_mobile_pdf", "mockup_desktop_pdf",
                 "mockup_mobile_pdf", "board"]


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PackageCase(unittest.TestCase):
    test_only = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        raw = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
        raw["test_only"] = self.test_only
        self.normalized = intake.validate(raw)
        self.graph = route.compile_route(self.normalized)

    def tearDown(self):
        self.tmp.cleanup()

    def pieces(self, **kw):
        return {n["role"]: make_piece(self.work, self.normalized, n, **kw) for n in self.graph["nodes"]}

    def build(self, pieces=None, name="pkg", **kw):
        kw.setdefault("require_designs", True)
        built = package.assemble(self.work / name, self.normalized, self.graph,
                                 pieces if pieces is not None else self.pieces(),
                                 source_root=self.work, council=COUNCIL, **kw)
        return built, self.work / name

    def check(self, built, root, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fails = checks.check_package(Path(built["manifest_path"]), root, **kw)
        return fails, out.getvalue()

    @staticmethod
    def reseal(root: Path, mutate):
        """Change the manifest and re-seal the receipt over it, as a hand edit that keeps the seal."""
        manifest_path = root / "package-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutate(manifest)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt_path = root / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["manifest"]["sha256"] = sha(manifest_path)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest_path


class SeamTests(PackageCase):
    def run_with_rule(self, source: str):
        built, root = self.build()
        rules = self.work / "rules"
        rules.mkdir(exist_ok=True)
        (rules / "rule_one.py").write_text(textwrap.dedent(source), encoding="utf-8")
        with mock.patch.object(check_rules, "RULES_DIR", rules):
            return self.check(built, root)[0]

    def test_a_package_with_no_rule_violation_passes(self):
        self.assertEqual(self.run_with_rule("def violations(manifest, root, skill_root):\n    return []\n"), [])

    def test_check_package_fails_on_every_violation_a_rule_module_returns(self):
        fails = self.run_with_rule("""
            def violations(manifest, root, skill_root):
                return ["AF-RULE-ONE: first", "AF-RULE-ONE: second"]
            """)
        self.assertEqual(fails, ["AF-RULE-ONE: first", "AF-RULE-ONE: second"])

    def test_a_rule_receives_the_manifest_and_the_package_root(self):
        fails = self.run_with_rule("""
            def violations(manifest, root, skill_root):
                return [f"saw {manifest['launch_id']} at {root.name}"]
            """)
        self.assertEqual(fails, ["saw TEST-FIXTURE-ELEVATION at pkg"])

    def test_a_broken_rule_module_is_a_violation_never_a_skip(self):
        for label, source in (("no function", "x = 1\n"),
                              ("raises", "def violations(m, r, s):\n    raise RuntimeError('boom')\n"),
                              ("bad return", "def violations(m, r, s):\n    return 'ok'\n"),
                              ("syntax error", "def violations(:\n")):
            fails = self.run_with_rule(source)
            self.assertEqual(len(fails), 1, (label, fails))
            self.assertTrue(fails[0].startswith("AF-LAUNCH-CHECK-RULE: rule_one"), (label, fails))

    def test_the_shipped_rules_folder_loads_cleanly(self):
        built, root = self.build()
        self.assertEqual(check_rules.run(json.loads(Path(built["manifest_path"]).read_text()), root, SKILL_ROOT), [])


class DesignLevelTests(PackageCase):
    def test_the_stub_lane_output_passes_as_images_only_render_pending(self):
        # The stub provider writes placeholder section images and never composes PDFs or boards.
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD)
        built, root = self.build(pieces)
        fails, printed = self.check(built, root)
        self.assertEqual(fails, [])
        self.assertIn("images only, render pending", printed)

    def test_images_only_counts_the_section_images_against_the_sections(self):
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD)
        pieces["checkout"]["artifacts"] = [
            a for a in pieces["checkout"]["artifacts"]
            if not (a["kind"] == "wireframe_desktop_section" and "_s02-of-02_" in a["path"])]
        built, root = self.build(pieces)
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: checkout wireframe desktop section has sections [1] of 2", fails)

    def test_images_only_still_needs_every_section_kind(self):
        pieces = self.pieces(provider="stub", omit=PDF_AND_BOARD + ["mockup_mobile_section"])
        built, root = self.build(pieces)
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing mockup mobile section", fails)

    def test_a_half_rendered_stub_package_is_not_images_only(self):
        built, root = self.build(self.pieces(provider="stub", omit=["board"]))
        fails, printed = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: checkout is missing board", fails)
        self.assertNotIn("images only", printed)

    def test_a_full_test_package_is_labelled_a_full_set(self):
        built, root = self.build()
        fails, printed = self.check(built, root)
        self.assertEqual(fails, [])
        self.assertIn("full set (test package)", printed)


class PaidPackageTests(PackageCase):
    test_only = False

    def test_a_paid_package_with_every_design_kind_passes_with_no_blanket_test_only_assertion(self):
        built, root = self.build(self.pieces(provider="kie"))
        self.assertIs(built["manifest"]["test_only"], False)
        fails, printed = self.check(built, root)
        self.assertEqual(fails, [])
        self.assertIn("full set (paid package)", printed)

    def test_a_paid_package_missing_a_kind_fails(self):
        built, root = self.build(self.pieces(provider="kie", omit=["board"]))
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing board", fails)

    def test_a_paid_package_with_stub_images_fails_the_provider_consistency_check(self):
        built, root = self.build(self.pieces(provider="stub"))
        fails, _ = self.check(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-PKG-MANIFEST: test_only is false but")
                            and "stub provider" in f for f in fails), fails[:3])

    def test_a_paid_package_cannot_skip_designs_without_a_waiver(self):
        built, root = self.build(self.pieces(provider="kie"), require_designs=False)
        self.assertIs(built["manifest"]["designs_required"], False)
        fails, _ = self.check(built, root)
        self.assertTrue(any("paid package must carry the full design set" in f for f in fails), fails)

    def test_a_waiver_needs_an_owner_approval_ref_and_the_label_is_printed(self):
        built, root = self.build(self.pieces(provider="kie"), require_designs=False)
        manifest_path = self.reseal(root, lambda m: m.update(
            designs_waiver={"approval_ref": ""}, delivery_label="designs waived"))
        fails, printed = self.check({"manifest_path": manifest_path}, root)
        self.assertTrue(any("waived with no owner approval reference" in f for f in fails), fails)
        manifest_path = self.reseal(root, lambda m: m.update(
            designs_waiver={"approval_ref": "owner-ok-2026-11-02"}, delivery_label="designs waived"))
        fails, printed = self.check({"manifest_path": manifest_path}, root)
        self.assertEqual(fails, [])
        self.assertIn("designs waived (owner approval owner-ok-2026-11-02)", printed)


class ToConfirmTests(PackageCase):
    ENTRY = {"field": "image_plan.design_style", "reason": "defaulted", "how_to_change": "say A, B or C"}

    def test_an_unconfirmed_default_blocks_the_check_until_a_record_names_it(self):
        built, root = self.build(to_confirm=[dict(self.ENTRY)])
        fails, _ = self.check(built, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-TO-CONFIRM: 'image_plan.design_style'") for f in fails), fails)
        (root / checks.TO_CONFIRM_RECORD).write_text(json.dumps({"confirmations": [
            {"field": "image_plan.design_style", "confirmation_ref": "client-reply-2026-11-02"}]}),
            encoding="utf-8")
        self.assertEqual(self.check(built, root)[0], [])

    def test_a_confirmation_with_no_reference_does_not_count(self):
        built, root = self.build(to_confirm=[dict(self.ENTRY)])
        (root / checks.TO_CONFIRM_RECORD).write_text(json.dumps({"confirmations": [
            {"field": "image_plan.design_style", "confirmation_ref": " "}]}), encoding="utf-8")
        self.assertTrue(any("AF-LAUNCH-TO-CONFIRM" in f for f in self.check(built, root)[0]))

    def test_a_default_hidden_from_the_manifest_is_caught_by_the_dispatch_report(self):
        built, root = self.build()
        (root / checks.DISPATCH_REPORT).write_text(json.dumps({"to_confirm": [dict(self.ENTRY)],
                                                               "landing_pages": ["landing"]}), encoding="utf-8")
        fails, _ = self.check(built, root)
        self.assertIn("AF-LAUNCH-TO-CONFIRM: the dispatch report lists default "
                      "'image_plan.design_style' that the package manifest does not carry", fails)

    def test_a_planned_sales_page_that_was_never_built_is_caught_by_the_dispatch_report(self):
        built, root = self.build()
        (root / checks.DISPATCH_REPORT).write_text(json.dumps({"to_confirm": [],
                                                               "landing_pages": ["landing", "sales"]}), encoding="utf-8")
        fails, _ = self.check(built, root)
        self.assertTrue(any("no signature sales page piece" in f for f in fails), fails)


class RouteGraphTests(PackageCase):
    def test_a_manifest_without_its_upsell_piece_fails(self):
        built, root = self.build()
        self.assertEqual(self.check(built, root)[0], [])
        manifest_path = self.reseal(root, lambda m: m.update(
            pieces=[p for p in m["pieces"] if p["role"] != "upsell_1"]))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertIn("AF-LAUNCH-PKG-MISSING-ROLE: route node 'upsell_1' has no delivered piece in the "
                      "package manifest", fails)

    def test_a_manifest_without_its_second_upsell_piece_fails(self):
        built, root = self.build()
        manifest_path = self.reseal(root, lambda m: m.update(
            pieces=[p for p in m["pieces"] if p["role"] != "upsell_2"]))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertTrue(any("route node 'upsell_2'" in f for f in fails), fails)

    def test_a_carried_graph_missing_a_doc_02_edge_fails_the_check(self):
        built, root = self.build()
        graph = json.loads((root / "route-graph.json").read_text(encoding="utf-8"))
        graph["edges"] = [e for e in graph["edges"] if e["event"] != "explicit_decline"][:]
        (root / "route-graph.json").write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n",
                                               encoding="utf-8")
        manifest_path = self.reseal(root, lambda m: m["route_graph"].update(
            sha256=sha(root / "route-graph.json")))
        fails, _ = self.check({"manifest_path": manifest_path}, root)
        self.assertTrue(any(f.startswith("AF-LAUNCH-ROUTE-LAW: missing contract edges") for f in fails), fails)

    def test_an_intact_graph_holds_the_law(self):
        built, root = self.build()
        graph = json.loads((root / "route-graph.json").read_text(encoding="utf-8"))
        record = route.launch_record(json.loads((root / "intake.json").read_text(encoding="utf-8")))
        self.assertEqual(route_law.graph_violations(record, graph), [])

    def test_assemble_refuses_a_compiled_graph_missing_a_doc_02_edge(self):
        compiler = substrate.compiler()
        real = compiler.compile_route

        def drop_an_edge(launch):
            graph = copy.deepcopy(real(launch))
            graph["edges"] = graph["edges"][1:]
            return graph

        with mock.patch.object(compiler, "compile_route", drop_an_edge):
            with self.assertRaises(route_law.RouteInvariantError) as ctx:
                route.compile_route(self.normalized)
            self.assertIn("missing contract edges", str(ctx.exception))
            intake_file = self.work / "intake.json"
            intake_file.write_text(json.dumps(json.loads(
                (FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))), encoding="utf-8")
            pieces_dir = self.work / "pieces-in"
            pieces_dir.mkdir()
            with mock.patch.object(cli.council, "planning_step", return_value=COUNCIL):
                with self.assertRaises(route_law.RouteInvariantError):
                    cli.main(["assemble", "--intake", str(intake_file), "--pieces", str(pieces_dir),
                              "--out", str(self.work / "out"), "--page-only"])
        self.assertFalse((self.work / "out" / "package-manifest.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
