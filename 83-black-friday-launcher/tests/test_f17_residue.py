"""F17's three residues: role section structure, named missing pages, and per-instance receipts.

F17 item 5: a page's sections are its OWN role's structure (Skill 71's routing: page-structures.json,
copy-specs/roles, the registered copy forms, page-kinds), never the sales page's skeleton.
F17 item 6/7: design completeness binds the exact page instance — one run's stage receipt is one page
instance's receipt, and a planned page with no run is NAMED, never folded into a count.

Free: pure files and fixtures, no provider and no network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
for path in (HERE, SKILL_ROOT, SKILL_ROOT / "routes"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import substrate  # noqa: E402
from launcher_core import image_stages, page_designs  # noqa: E402
from lane83_fake_consumer import PNG  # noqa: E402  a real 1x1 PNG

LABELS = substrate.load("71-blackceo-signature-page/scripts/deliverable_labels.py", "f17_residue_labels")
RULE_FILE = SKILL_ROOT / "launcher_core" / "check_rules" / "image_qc.py"
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox [0 0 612 792]>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha(data)


def design_set(root: Path, slug: str, numbers, *, base: str, stages: int) -> tuple:
    """One page's full design set, its section files numbered `numbers` of `stages`."""
    arts, hashes = [], {"desktop-wireframe": {}, "mobile-tablet": {}, "final-mockups": {}, "design-board": {}}
    for device, wire in (("desktop", "desktop-wireframe"), ("mobile", "mobile-tablet")):
        for n in numbers:
            for kind, stage, data in (("wireframe", wire, PNG), ("mockup", "final-mockups", PNG)):
                name = LABELS.image_name(slug, device, stage, n, stages, f"s{n}")
                rel = f"{base}/{LABELS.folder(device, stage)}/{name}"
                digest = write(root / rel, data)
                hashes[stage][rel] = digest
                arts.append({"path": rel, "sha256": digest, "provider": "kie"})
        for stage, name in ((wire, LABELS.pdf_name(slug, device, wire)),
                            ("final-mockups", LABELS.pdf_name(slug, device, "final-mockups"))):
            rel = f"{base}/review-pdfs/{name}"
            digest = write(root / rel, PDF)
            hashes[stage][rel] = digest
            arts.append({"path": rel, "sha256": digest, "provider": "kie"})
    rel = f"{base}/review-pdfs/{LABELS.board_name(slug, 'combined', 'final-mockups')}.png"
    digest = write(root / rel, PNG)
    hashes["design-board"][rel] = digest
    arts.append({"path": rel, "sha256": digest, "provider": "kie"})
    return arts, hashes


def stage_state(root: Path, rel: str, hashes: dict) -> dict:
    doc = {"stages": {name: {"status": "closed", "receipt_status": "pass", "artifact_hashes": h}
                      for name, h in hashes.items()}}
    data = json.dumps(doc).encode()
    return {"path": rel, "sha256": write(root / rel, data)}


def delivery(*pieces) -> dict:
    return {"test_only": False, "pieces": list(pieces),
            "design_approvals": page_designs.default_approvals()}


def closed_run(parent: Path, name: str, role: str, *, page_kind=None) -> Path:
    """A Skill 71 run folder whose five image stages are closed (what the stage rule re-reads)."""
    run = parent / name
    digest = write(run / "image-generation-qc" / "Image-01.png", PNG)
    rel = "image-generation-qc/Image-01.png"
    stages = {stage: {"status": "closed", "receipt_status": "pass", "artifact_hashes": {rel: digest}}
              for stage in image_stages.STAGES}
    intake = {"page_role": role}
    if page_kind:
        intake["page_kind"] = page_kind
    (run / "intake.json").parent.mkdir(parents=True, exist_ok=True)
    (run / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
    (run / "private").mkdir(parents=True, exist_ok=True)
    (run / "private" / "state.json").write_text(json.dumps({"stages": stages}), encoding="utf-8")
    (run / "private" / "receipts").mkdir(parents=True, exist_ok=True)
    for stage in image_stages.STAGES:
        (run / "private" / "receipts" / f"{stage}.json").write_text(json.dumps({"status": "pass"}),
                                                                   encoding="utf-8")
    return run


def rule():
    spec = importlib.util.spec_from_file_location("f17_residue_image_qc", RULE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class SectionStructureTests(unittest.TestCase):
    """(a) each role's own section structure, from Skill 71's routing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def page(self, role, slug, numbers, stages):
        arts, hashes = design_set(self.root, slug, numbers, base=f"pieces/{slug}", stages=stages)
        return {"role": role, "page_kind": role, "image_provider": "kie", "artifacts": arts,
                "stage_state": stage_state(self.root, f"stage-state-{slug}.json", hashes)}

    def test_every_role_in_the_launch_inventory_resolves_its_own_structure(self):
        from launcher_core import section_structure
        for piece, sections in (({"role": "landing"}, 15), ({"role": "landing", "page_kind": "sales"}, 12),
                                ({"role": "product_selection"}, 5), ({"role": "checkout"}, 5),
                                ({"role": "upsell_1"}, 8), ({"role": "upsell_2"}, 8),
                                ({"role": "downsell_1"}, 8), ({"role": "thank_you"}, 5)):
            structure = section_structure.resolve(piece)
            self.assertEqual(structure["state"], "known", piece)
            self.assertEqual(len(structure["sequences"][0]), sections, piece)

    def test_an_upsell_page_numbered_one_to_eight_passes(self):
        piece = self.page("upsell_1", "upsell-1", range(1, 9), 8)
        self.assertEqual(page_designs.design_violations(delivery(piece), self.root), [])

    def test_a_page_with_the_right_count_and_the_wrong_sections_is_refused(self):
        piece = self.page("upsell_1", "upsell-1", range(5, 13), 12)
        fails = page_designs.design_violations(delivery(piece), self.root)
        hit = [f for f in fails if "section structure" in f]
        self.assertTrue(hit, fails)
        self.assertIn("role upsell_1", hit[0])
        self.assertIn("no section 1, 2, 3, 4", hit[0])          # named, not counted
        self.assertIn("has 12 section(s) and this role has 8", hit[0])

    def test_the_sales_skeleton_is_not_applied_to_another_role(self):
        # a checkout page drawn with the sales page's twelve numbered sections
        piece = self.page("checkout", "checkout", range(1, 13), 12)
        hit = [f for f in page_designs.design_violations(delivery(piece), self.root)
               if "own section structure" in f]
        self.assertTrue(hit, "a checkout page carries five sections, not the sales page's twelve")
        self.assertIn("this role has 5", hit[0])


class NamedMissingPageTests(unittest.TestCase):
    """(b) a missing page is NAMED with its page identity and role; a count is never proof."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.root / "qc").mkdir(parents=True, exist_ok=True)

    def report(self, pages, **extra):
        doc = {"pages": pages, **extra}
        (self.root / "qc" / "image_stages_report.json").write_text(json.dumps(doc), encoding="utf-8")
        return doc

    def test_one_role_level_run_cannot_answer_for_two_planned_page_instances(self):
        run = closed_run(self.root / "run", "landing", "landing")
        self.report([{"page": "landing", "role": "landing", "run_dir": str(run)}])
        pieces = [{"role": "landing", "page_kind": "opt_in"}, {"role": "landing", "page_kind": "sales"}]
        fails = rule()._stage_violations({"test_only": True, "pieces": pieces}, self.root)
        self.assertTrue(all(any(f"page landing:{kind}" in f and "role-level row" in f for f in fails)
                            for kind in ("opt_in", "sales")), fails)

    def test_an_unknown_planned_page_set_is_named_not_silently_skipped(self):
        run = closed_run(self.root / "run", "landing", "landing")
        self.report([{"page": "landing", "page_key": "landing:opt_in", "role": "landing",
                      "run_dir": str(run)}],
                    expected_pages_state="unknown", reason="the run has no launch.json with a journey_mode")
        fails = rule()._stage_violations({"test_only": True, "pieces": [{"role": "landing"}]}, self.root)
        self.assertTrue(any("planned page set is 'unknown'" in f and "journey_mode" in f for f in fails), fails)

    def test_a_missing_page_is_named_by_its_page_identity_and_role(self):
        self.report([{"page": "landing-sales", "page_key": "landing:sales", "role": "landing",
                      "run_dir": str(self.root / "run" / "absent"), "status": "missing_page",
                      "reason": "the launch plans this page and no Skill 71 run folder for it was found"}],
                    expected_pages_state="known")
        fails = rule()._stage_violations({"test_only": True, "pieces": [{"role": "landing", "page_kind": "sales"}]},
                                         self.root)
        self.assertTrue(any("page landing:sales" in f and "role landing" in f and "is missing" in f
                            and "no Skill 71 run folder" in f for f in fails), fails)


class NoSharedReceiptsTests(unittest.TestCase):
    """(c) instance A's receipt presented to instance B is REFUSED (the negative control)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.root / "qc").mkdir(parents=True, exist_ok=True)

    def page(self, role, slug):
        arts, hashes = design_set(self.root, slug, range(1, 9), base=f"pieces/{slug}", stages=8)
        return {"role": role, "page_kind": role, "image_provider": "kie", "artifacts": arts,
                "stage_state": stage_state(self.root, f"stage-state-{slug}.json", hashes)}

    def test_b_refuses_as_receipt_even_though_its_files_are_byte_identical(self):
        a, b = self.page("upsell_1", "upsell-1"), self.page("upsell_2", "upsell-2")
        b["stage_state"] = dict(a["stage_state"])  # instance A's receipt, presented to instance B
        fails = page_designs.design_violations(delivery(a, b), self.root)
        self.assertTrue(any("upsell_2" in f and "is not among the files the closed" in f for f in fails), fails[:3])
        self.assertTrue(any("upsell_1 and upsell_2 cite the same stage_gate receipt" in f for f in fails), fails)

    def test_one_page_run_is_one_page_instances_receipt(self):
        run = closed_run(self.root / "run", "landing", "landing", page_kind="opt_in")
        (self.root / "qc" / "image_stages_report.json").write_text(json.dumps({
            "pages": [{"page": "opt-in", "page_key": "landing:opt_in", "role": "landing", "run_dir": str(run)},
                      {"page": "sales", "page_key": "landing:sales", "role": "landing", "run_dir": str(run)}],
            "expected_pages_state": "known"}), encoding="utf-8")
        pieces = [{"role": "landing", "page_kind": "opt_in"}, {"role": "landing", "page_kind": "sales"}]
        fails = rule()._stage_violations({"test_only": True, "pieces": pieces}, self.root)
        self.assertTrue(any("cite the same page run" in f and "never transferable" in f for f in fails), fails)

    def test_a_row_whose_run_belongs_to_another_page_is_refused(self):
        run = closed_run(self.root / "run", "landing", "landing", page_kind="opt_in")
        (self.root / "qc" / "image_stages_report.json").write_text(json.dumps({
            "pages": [{"page": "sales", "page_key": "landing:sales", "role": "landing", "run_dir": str(run)}],
            "expected_pages_state": "known"}), encoding="utf-8")
        fails = rule()._stage_violations(
            {"test_only": True, "pieces": [{"role": "landing", "page_kind": "sales"}]}, self.root)
        self.assertTrue(any("whose own intake declares landing:opt_in" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main(verbosity=2)
