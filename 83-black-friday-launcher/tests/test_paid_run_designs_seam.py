"""U-designs-seam: the files a PAID (kie) run leaves must be the files AF-LAUNCH-PAGE-DESIGNS counts.

Skill 49 lists a page's design files from structure/page_types.json (page_set.design_artifacts). Skill 83's
page_designs.classify only accepts the labeled client copies Skill 71 writes (combine_review_pdf's
write_labeled_images and PDFs), and only FINAL mockups. Before this unit the list held the raw proofs and the
VISUAL PDFs, so a real paid package could never pass `check`; and final-mockups closes AFTER dispatch, so even a
corrected list was stale. Free: the files are made by Skill 71's own combiner on tiny pictures, no provider.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import substrate  # noqa: E402
from launcher_core import checks, image_stages, page_designs  # noqa: E402
from test_page_designs_real import write_stage_state  # noqa: E402

S71 = "71-blackceo-signature-page/scripts"
combine = substrate.load(f"{S71}/combine_review_pdf.py", "seam_combine_review_pdf", S71)
labels = substrate.load(f"{S71}/deliverable_labels.py", "seam_deliverable_labels")
page_set = substrate.load("49-signature-funnel/scripts/page_set.py", "launcher_page_set", "49-signature-funnel/scripts")

PAGE, SLUG, SECTIONS = "upsell_1", "upsell-1", 8
# the Skill 71 stage whose close hashes each section kind (page_designs._STAGES_FOR)
STAGE_OF = {"wireframe_desktop_section": "desktop-wireframe", "wireframe_mobile_section": "mobile-tablet",
            "mockup_desktop_section": "final-mockups", "mockup_mobile_section": "final-mockups"}


def png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PaidRun:
    """One page's run folder, grown stage by stage the way a kie run grows it."""

    def __init__(self, root: Path) -> None:
        self.run = root / f"images-{PAGE}"
        self.run.mkdir(parents=True)
        (self.run / "intake.json").write_text(json.dumps({"page_role": PAGE}), encoding="utf-8")
        self.png = png()

    def draw(self, stage: str) -> None:
        """The stage's raw section pictures, then Skill 71's compose step (labeled copies, review PDFs)."""
        devices = {"desktop-wireframe": [""], "mobile-tablet": [""],
                   "visual-mockup": ["desktop/", "mobile/"], "final-mockups": ["desktop/", "mobile/"]}[stage]
        for prefix in devices:
            for n in range(1, SECTIONS + 1):
                target = self.run / stage / f"{prefix}{'part' if prefix else 'section'}-{n:02d}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.png)
        (self.run / stage / "stage-executor-record.json").write_text(json.dumps({"provider": "kie"}), encoding="utf-8")
        assert combine.build_stage(self.run, stage, SECTIONS) == 0

    def board(self) -> None:
        """The combined overview board the paid final-mockups composition writes."""
        target = self.run / "review-pdfs" / f"{labels.board_name(SLUG, 'combined', 'final-mockups')}.png"
        target.write_bytes(self.png)

    def artifacts(self, relative: bool):
        return page_set.design_artifacts(PAGE, self.run, relative=relative, with_provider=True)

    def kinds(self, artifacts) -> set:
        return {page_designs.classify(a["path"]) for a in artifacts} - {None}


class PaidRunDesignsSeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def finished_run(self) -> PaidRun:
        paid = PaidRun(self.root)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup", "final-mockups"):
            paid.draw(stage)
        paid.board()
        return paid

    def test_a_paid_run_after_compose_and_final_mockups_classifies_into_all_four_section_kinds_and_passes(self):
        paid = self.finished_run()
        arts = paid.artifacts(relative=True)
        self.assertEqual(len(checks.SECTION_KINDS), 4)
        self.assertTrue(set(checks.SECTION_KINDS) <= paid.kinds(arts), sorted(paid.kinds(arts)))
        self.assertEqual(paid.kinds(arts), set(page_designs.KINDS))  # PDFs and the board too: the full set
        # every section file is a labeled copy, one per section, each of the page's section count
        for kind in checks.SECTION_KINDS:
            self.assertEqual(sum(page_designs.classify(a["path"]) == kind for a in arts), SECTIONS, kind)
        # the package check, as a client delivery: real files, a closed run state that hashes them, a recorded
        # approval state, the page's section count
        hashes = {stage: {} for stage in ("desktop-wireframe", "mobile-tablet", "final-mockups", "design-board")}
        for art in arts:
            stage = STAGE_OF.get(page_designs.classify(art["path"]))
            if stage:
                hashes[stage][art["path"]] = art["sha256"]
        piece = {"role": PAGE, "page_kind": PAGE, "image_provider": "kie", "artifacts": arts,
                 "stage_state": write_stage_state(paid.run, "stage-state.json", hashes)}
        manifest = {"test_only": False, "designs_required": True, "pieces": [piece],
                    "design_approvals": page_designs.default_approvals()}
        self.assertEqual(page_designs.design_violations(manifest, paid.run), [])
        label, fails = checks._design_level(manifest, paid.run, True)
        self.assertEqual((label, fails), ("full set (paid package)", []))

    def test_the_stub_proofs_alone_still_list_and_classify_as_nothing(self):
        """Control, same instrument: the raw layout proofs a stub run draws are listed but are no design file."""
        paid = PaidRun(self.root)
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            (paid.run / stage).mkdir()
        for n in range(1, SECTIONS + 1):
            for rel in (f"desktop-wireframe/section-{n:02d}.png", f"mobile-tablet/section-{n:02d}.png",
                        f"visual-mockup/desktop/part-{n:02d}.png", f"visual-mockup/mobile/part-{n:02d}.png"):
                (paid.run / rel).parent.mkdir(parents=True, exist_ok=True)
                (paid.run / rel).write_bytes(paid.png)
        arts = paid.artifacts(relative=True)
        self.assertEqual(len([a for a in arts if a["path"].endswith(".png")]), SECTIONS * 4)
        self.assertEqual(paid.kinds(arts), set())

    def test_final_mockups_closing_after_dispatch_refreshes_the_piece_and_the_result_it_binds_to(self):
        for relative in (False, True):
            with self.subTest(relative=relative):
                launch = self.root / f"launch-{relative}"
                paid = PaidRun(launch / "dispatch")
                for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):  # what dispatch left
                    paid.draw(stage)
                result = {"role": PAGE, "request_id": "r1", "input_hash": "h1", "status": "ok",
                          "artifacts": paid.artifacts(relative)}
                stored = launch / "dispatch" / f"result-{PAGE}.json"
                stored.write_text(json.dumps(result), encoding="utf-8")
                (launch / "pieces").mkdir()
                piece_path = launch / "pieces" / f"{PAGE}.json"
                piece_path.write_text(json.dumps(result), encoding="utf-8")
                manifest = launch / "dispatch" / "dispatch-manifest.json"
                manifest.write_text(json.dumps({"results": [result]}), encoding="utf-8")
                before = json.loads(piece_path.read_text(encoding="utf-8"))["artifacts"]
                self.assertFalse({"mockup_desktop_section", "mockup_mobile_section"} & paid.kinds(before))

                paid.draw("final-mockups")  # the post-dispatch driver closes final-mockups
                paid.board()
                self.assertEqual(image_stages.refresh_pieces(launch, paid.run), [PAGE])

                piece = json.loads(piece_path.read_text(encoding="utf-8"))
                self.assertEqual(paid.kinds(piece["artifacts"]), set(page_designs.KINDS))
                self.assertEqual({(a["path"], a["sha256"]) for a in piece["artifacts"]},
                                 {(a["path"], a["sha256"]) for a in paid.artifacts(relative)})
                # package._bind_piece: every artifact of the piece is one the dispatch's stored result lists
                have = lambda doc: {(a["path"], a["sha256"]) for a in doc["artifacts"]}  # noqa: E731
                self.assertLessEqual(have(piece), have(json.loads(stored.read_text(encoding="utf-8"))))
                self.assertEqual(have(piece), have(json.loads(manifest.read_text(encoding="utf-8"))["results"][0]))
                # a second pass changes nothing
                self.assertEqual(image_stages.refresh_pieces(launch, paid.run), [PAGE])
                self.assertEqual(json.loads(piece_path.read_text(encoding="utf-8")), piece)


if __name__ == "__main__":
    unittest.main()
