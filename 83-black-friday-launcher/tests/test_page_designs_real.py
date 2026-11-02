"""AF-LAUNCH-PAGE-DESIGNS needs real files from a closed stage_gate run and a recorded client approval.

IMG-02 (stub or renamed files, layout proofs as mockups, declared kinds), IMG-10 (Design Board approval
is the client's recorded message, never typed), IMG-13 (page_types.json is read), STR-25 (an approval
reference resolves to a recorded Design Board approval), STR-15 (section counts). Free: pure files.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
SKILL71_TESTS = SKILL_ROOT.parent / "71-blackceo-signature-page" / "tests"
for p in (HERE, SKILL_ROOT, SKILL_ROOT / "routes"):
    sys.path.insert(0, str(p))

import substrate  # noqa: E402
from launcher_core import page_designs  # noqa: E402
from lane83_fake_consumer import PNG  # noqa: E402  a real 1x1 PNG
from test_lane83_designs import Base  # noqa: E402

LABELS = substrate.load("71-blackceo-signature-page/scripts/deliverable_labels.py", "page_designs_real_labels")
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox [0 0 612 792]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
PAGE_TYPES = "49-signature-funnel/structure/page_types.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def client_package(root: Path, role: str, sections: int, *, png: bytes = PNG, provider: str = "kie",
                   mockup_stage: str = "final-mockups", closed: bool = True) -> dict:
    """A non-test manifest for one page whose files exist under root and whose stage_gate state is recorded."""
    root.mkdir(parents=True, exist_ok=True)
    arts, hashes = [], {"desktop-wireframe": {}, "mobile-tablet": {}, "final-mockups": {}}

    def put(kind, rel, data, stage=None):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
        arts.append({"path": rel, "sha256": sha(data), "kind": kind, "provider": provider})
        if stage:
            hashes[stage][rel] = sha(data)

    for device, wire_stage in (("desktop", "desktop-wireframe"), ("mobile", "mobile-tablet")):
        for n in range(1, sections + 1):
            put(f"wireframe_{device}_section", f"pieces/{role}/{LABELS.folder(device, wire_stage)}/"
                f"{LABELS.image_name(role, device, wire_stage, n, sections, f's{n}')}", png, wire_stage)
            put(f"mockup_{device}_section", f"pieces/{role}/{LABELS.folder(device, 'final-mockups')}/"
                f"{LABELS.image_name(role, device, mockup_stage, n, sections, f's{n}')}", png, "final-mockups")
        put(f"wireframe_{device}_pdf", f"pieces/{role}/review-pdfs/{LABELS.pdf_name(role, device, wire_stage)}", PDF, None)
        put(f"mockup_{device}_pdf", f"pieces/{role}/review-pdfs/{LABELS.pdf_name(role, device, mockup_stage)}", PDF, None)
    put("board", f"pieces/{role}/review-pdfs/{LABELS.board_name(role, 'combined', 'final-mockups')}.png", png, None)
    stages = {s: {"status": "closed" if closed else "open", "receipt_status": "pass", "artifact_hashes": h}
              for s, h in hashes.items()}
    state = json.dumps({"stages": stages}).encode()
    (root / f"stage-state-{role}.json").write_bytes(state)
    return {"role": role, "page_kind": role, "image_provider": provider, "artifacts": arts,
            "stage_state": {"path": f"stage-state-{role}.json", "sha256": sha(state)}}


def manifest_of(*pieces, approvals=None) -> dict:
    return {"test_only": False, "pieces": list(pieces),
            "design_approvals": approvals or page_designs.default_approvals()}


class ClassifyTests(unittest.TestCase):
    def test_only_final_mockups_are_mockups_and_a_declared_kind_is_never_believed(self):
        self.assertIsNone(page_designs.classify("landing_DESKTOP_MOCKUPS-VISUAL.pdf"))
        self.assertIsNone(page_designs.classify(LABELS.image_name("landing", "desktop", "visual-mockup", 1, 8, "Hero")))
        self.assertEqual(page_designs.classify("landing_DESKTOP_MOCKUPS-FINAL.pdf"), "mockup_desktop_pdf")
        self.assertEqual(page_designs.classify(LABELS.image_name("landing", "mobile", "final-mockups", 1, 8, "Hero")),
                         "mockup_mobile_section")
        self.assertIsNone(page_designs.classify("landing_notes.txt", "board"))  # declared kind ignored
        self.assertIsNone(page_designs.classify("desktop-mockups/anything.png"))  # a folder is not FINAL


class RealFileTests(Base):
    def test_a_package_of_one_byte_files_of_the_right_name_fails_check_package(self):
        pieces = self.pieces()
        for piece in pieces.values():
            for art in piece["artifacts"]:
                Path(art["path"]).write_bytes(b"x")
                art["sha256"] = sha(b"x")
        built = self.assemble(pieces, name="junk")
        fails = self.check(built, name="junk")
        self.assertTrue(any("is not a PNG" in f for f in fails), fails[:3])
        self.assertTrue(any("is not a PDF" in f for f in fails), fails[:3])

    def test_a_package_with_only_layout_proof_mockups_fails_the_mockup_requirement(self):
        pieces = self.pieces()
        for art in pieces["landing"]["artifacts"]:
            old = Path(art["path"])
            if art["kind"] in ("mockup_desktop_pdf", "mockup_mobile_pdf"):
                new = old.with_name(old.name.replace("MOCKUPS-FINAL", "MOCKUPS-VISUAL"))
                old.rename(new)
                art["path"] = str(new)
        fails = self.check(self.assemble(pieces, name="visual"), name="visual")
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing mockup desktop pdf", fails)
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing mockup mobile pdf", fails)

    def test_a_declared_kind_on_an_unrelated_file_satisfies_nothing(self):
        pieces = self.pieces()
        doc = self.work / "landing_page.html"
        doc.write_text("<html></html>", encoding="utf-8")
        pieces["landing"]["artifacts"] = [{"path": str(doc), "sha256": sha(doc.read_bytes()), "kind": "board"}]
        fails = self.check(self.assemble(pieces, name="declared"), name="declared")
        self.assertIn("AF-LAUNCH-PAGE-DESIGNS: landing is missing board", fails)


class ClientDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def fails(self, piece, sub=None):
        return page_designs.design_violations(manifest_of(piece), self.root / sub if sub else self.root)

    def test_real_files_from_a_closed_stage_gate_run_pass(self):
        self.assertEqual(self.fails(client_package(self.root, "checkout", 5)), [])

    def test_a_stub_provider_package_fails(self):
        fails = self.fails(client_package(self.root, "checkout", 5, provider="stub"))
        self.assertTrue(any("made by the stub provider" in f for f in fails), fails[:2])

    def test_a_one_byte_file_in_a_closed_run_still_fails(self):
        piece = client_package(self.root, "checkout", 5)
        victim = next(a for a in piece["artifacts"] if a["kind"] == "wireframe_desktop_section")
        (self.root / victim["path"]).write_bytes(b"x")
        victim["sha256"] = sha(b"x")
        self.assertTrue(any("is not a PNG" in f for f in self.fails(piece)))

    def test_a_png_with_no_size_and_a_pdf_with_no_page_fail(self):
        zero = bytearray(PNG)
        zero[16:24] = bytes(8)  # width 0, height 0
        fails = self.fails(client_package(self.root, "checkout", 5, png=bytes(zero)))
        self.assertTrue(any("zero width or height" in f for f in fails), fails[:2])
        piece = client_package(self.root / "b", "checkout", 5)
        pdf = next(a for a in piece["artifacts"] if a["kind"] == "mockup_desktop_pdf")
        (self.root / "b" / pdf["path"]).write_bytes(b"%PDF-1.4\n%%EOF\n")
        pdf["sha256"] = sha(b"%PDF-1.4\n%%EOF\n")
        self.assertTrue(any("no page of nonzero size" in f for f in page_designs.design_violations(
            manifest_of(piece), self.root / "b")))

    def test_a_file_outside_any_closed_run_fails(self):
        piece = client_package(self.root, "checkout", 5)
        state = json.loads((self.root / piece["stage_state"]["path"]).read_text(encoding="utf-8"))
        state["stages"]["final-mockups"]["artifact_hashes"] = {}
        raw = json.dumps(state).encode()
        (self.root / piece["stage_state"]["path"]).write_bytes(raw)
        piece["stage_state"]["sha256"] = sha(raw)
        self.assertTrue(any("is not among the files the closed final-mockups stage recorded" in f
                            for f in self.fails(piece)))

    def test_an_open_stage_or_a_missing_or_altered_state_fails(self):
        self.assertTrue(any("comes from no closed" in f for f in
                            self.fails(client_package(self.root / "a", "checkout", 5, closed=False), "a")))
        piece = client_package(self.root / "b", "checkout", 5)
        piece["stage_state"]["sha256"] = "0" * 64
        self.assertTrue(any("does not match its recorded hash" in f for f in
                            page_designs.design_violations(manifest_of(piece), self.root / "b")))
        del piece["stage_state"]
        self.assertTrue(any("carries no stage_state" in f for f in
                            page_designs.design_violations(manifest_of(piece), self.root / "b")))

    def test_the_visual_mockup_stage_is_not_the_final_mockup_stage(self):
        piece = client_package(self.root, "checkout", 5)
        state = json.loads((self.root / piece["stage_state"]["path"]).read_text(encoding="utf-8"))
        state["stages"]["visual-mockup"] = state["stages"].pop("final-mockups")
        raw = json.dumps(state).encode()
        (self.root / piece["stage_state"]["path"]).write_bytes(raw)
        piece["stage_state"]["sha256"] = sha(raw)
        self.assertTrue(any("comes from no closed final-mockups stage" in f for f in self.fails(piece)))

    def test_one_section_image_of_fifteen_fails_and_fifteen_pass(self):
        self.assertEqual(self.fails(client_package(self.root / "ok", "landing", 15), "ok"), [])
        fails = page_designs.design_violations(manifest_of(client_package(self.root / "one", "landing", 1)),
                                               self.root / "one")
        self.assertTrue(any("has 1 wireframe desktop section images; its page type has [15] sections" in f
                            for f in fails), fails[:3])


class PageTypesTests(unittest.TestCase):
    def test_the_repository_file_is_read_not_the_builtin_set(self):
        spec, source = page_designs.load_page_types()
        self.assertEqual(source, f"file:{PAGE_TYPES}")
        self.assertEqual(set(spec["checkout"]), set(page_designs.KINDS))
        self.assertTrue(page_designs.load_page_rules()["checkout"]["design_only"])
        self.assertFalse(page_designs.load_page_rules()["upsell_1"]["design_only"])

    def test_editing_the_top_level_deliverables_changes_what_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "49-signature-funnel" / "structure").mkdir(parents=True)
            (root / "49-signature-funnel" / "SKILL.md").write_text("x", encoding="utf-8")
            doc = {"deliverables": [{"id": "desktop_wireframe_pdf"}, {"id": "overview_boards"}],
                   "pages": {"checkout": {"role": "checkout", "design_only": True},
                             "upsell_1": {"role": "upsell_1", "deliverables": ["mockup_mobile_pdf"]}}}
            (root / PAGE_TYPES).write_text(json.dumps(doc), encoding="utf-8")
            spec, source = page_designs.load_page_types(root)
            self.assertEqual(source, f"file:{PAGE_TYPES}")
            self.assertEqual(page_designs.required_kinds({"role": "checkout"}, spec),
                             ["wireframe_desktop_pdf", "board"])
            self.assertEqual(page_designs.required_kinds({"role": "upsell_1"}, spec), ["mockup_mobile_pdf"])
            (root / PAGE_TYPES).write_text("{not json", encoding="utf-8")  # present but broken: never builtin
            with self.assertRaises(page_designs.PageTypesError):
                page_designs.load_page_types(root)


class ApprovalTests(unittest.TestCase):
    """IMG-10 and STR-25 against a real Skill 71 Design Board record."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SKILL71_TESTS))
        import board_fixture
        cls.bf = board_fixture
        cls.db = board_fixture.design_board

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="page-designs-approval-"))
        self.addCleanup(shutil.rmtree, self.td, True)
        patch = mock.patch.object(self.db, "ocr_text", self.bf.fake_ocr)
        patch.start()
        self.addCleanup(patch.stop)
        self.run_dir = self.td / "run"
        self.bf.make_run(self.run_dir, "landing")
        self.bf.seed_board(self.run_dir, approved=False)

    def message(self, **over):
        path = self.td / "message.json"
        path.write_text(json.dumps({"message_id": "m-1", "sender_ref": "Test Client", **over}), encoding="utf-8")
        return path

    def test_approve_refuses_free_text_evidence_and_a_typed_identity(self):
        for evidence in ("ok", "msg-1", "", str(self.td / "missing.json")):
            with self.assertRaises(self.db.BoardError, msg=evidence):
                self.db.approve(self.run_dir, "client", evidence)
        with self.assertRaises(self.db.BoardError):  # --by is not the recorded sender
            self.db.approve(self.run_dir, "client", self.message())
        self.assertIsNone(self.db.load_record(self.run_dir)["approval"])

    def test_approve_takes_a_hashed_client_message_record(self):
        message = self.message()
        approval = self.db.approve(self.run_dir, "Test Client", message)
        self.assertEqual(approval["evidence_sha256"], sha(message.read_bytes()))
        self.assertEqual((approval["approved_by"], approval["evidence_message_id"]), ("Test Client", "m-1"))
        self.assertEqual(self.db.gate_failures(self.run_dir), [])

    def test_a_record_written_by_this_runs_own_session_or_naming_another_board_is_refused(self):
        with mock.patch.dict("os.environ", {"SIGNATURE_AUTHOR_SESSION": "sess-agent"}):
            with self.assertRaises(self.db.BoardError):
                self.db.approve(self.run_dir, "Test Client", self.message(session="sess-agent"))
        with self.assertRaises(self.db.BoardError):
            self.db.approve(self.run_dir, "Test Client", self.message(board_sha256="f" * 64))

    def test_a_launch_run_binds_approval_to_the_launch_client_identity(self):
        (self.run_dir / "launch.json").write_text(json.dumps({"tenant_id": "tenant-a"}), encoding="utf-8")
        with self.assertRaises(self.db.BoardError):
            self.db.approve(self.run_dir, "Test Client", self.message())
        self.db.approve(self.run_dir, "tenant-a", self.message(sender_ref="tenant-a"))

    def package_approval(self, ref, **over):
        entry = {"state": "approved", "approval_ref": ref, **over}
        return {"design_board": entry, "final_mockups": dict(entry)}

    def violations(self, approvals):
        return page_designs.design_violations({"test_only": True, "pieces": [], "design_approvals": approvals},
                                              self.td / "pkg")

    def test_an_unresolvable_or_unrecorded_approval_ref_fails_and_a_recorded_one_passes(self):
        pkg = self.td / "pkg"
        pkg.mkdir()
        self.assertTrue(any("does not resolve to a recorded Design Board approval" in f for f in
                            self.violations(self.package_approval("any string at all"))))
        self.assertTrue(any("no design board record with an approval" in f or "is not a design board record" in f
                            for f in self.violations(self.package_approval(
                                str(self.run_dir / "design-board" / "production-record.json"),
                                record_sha256=sha((self.run_dir / "design-board" / "production-record.json").read_bytes())))))
        self.db.approve(self.run_dir, "Test Client", self.message())
        record = self.run_dir / "design-board" / "production-record.json"
        self.assertEqual(self.violations(self.package_approval(str(record), record_sha256=sha(record.read_bytes()))), [])
        self.assertTrue(any("does not match its recorded hash" in f for f in
                            self.violations(self.package_approval(str(record), record_sha256="0" * 64))))

    def test_an_approval_with_no_recorded_client_message_fails(self):
        self.db.approve(self.run_dir, "Test Client", self.message())
        record = self.run_dir / "design-board" / "production-record.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["approval"].pop("evidence_sha256")  # a hand-written approval block
        record.write_text(json.dumps(data), encoding="utf-8")
        fails = self.violations(self.package_approval(str(record), record_sha256=sha(record.read_bytes())))
        self.assertTrue(any("lacks evidence_sha256" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main(verbosity=2)
