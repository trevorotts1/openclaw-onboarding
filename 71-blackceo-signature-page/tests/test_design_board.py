#!/usr/bin/env python3
"""Design Board (SPF021): contract, QC floor, approval binding, executor and stage gates.

Free: no provider call anywhere; the board PNGs are tiny local fixtures.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board_fixture as bf  # noqa: E402

ROOT = bf.ROOT
db = bf.design_board
EXEC = ROOT / "scripts" / "stage_executor.py"
GATE = ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"
PY = sys.executable


def run(cmd, env=None):
    return subprocess.run([PY, *map(str, cmd)], text=True, capture_output=True, env=env or bf.subprocess_env())


class Base(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="design-board-test-"))
        self.run_dir = self.td / "run"

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def request(self):
        return json.loads((self.run_dir / "production-request.json").read_text(encoding="utf-8"))

    def rewrite_request(self, fn):
        req = self.request()
        fn(req)
        (self.run_dir / "production-request.json").write_text(json.dumps(req), encoding="utf-8")


class ContractTests(Base):
    def test_required_blocks_adapt_per_page_role(self):
        landing = bf.make_run(self.td / "a", "landing")
        thanks = bf.make_run(self.td / "b", "thank_you")
        checkout = bf.make_run(self.td / "c", "checkout")
        got = {}
        for role, rd in (("landing", landing), ("thank_you", thanks), ("checkout", checkout)):
            req = json.loads((rd / "production-request.json").read_text(encoding="utf-8"))
            got[role] = db.plan(rd, req)["expected"]["required_blocks"]
        self.assertIn("aesthetic", got["landing"])
        self.assertIn("banner", got["landing"])
        self.assertIn("size", got["landing"])
        self.assertIn("icons", got["thank_you"])
        self.assertNotIn("aesthetic", got["thank_you"])
        self.assertNotIn("icons", got["checkout"])
        for blocks in got.values():
            for core in ("header", "palette", "typography", "imagery", "cues", "footer"):
                self.assertIn(core, blocks)

    def test_all_seven_page_roles_supported(self):
        schema = json.loads((ROOT / "references" / "page-request.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["page_role"]["enum"]), set(db.ROLE_LABEL))

    def test_prompt_carries_palette_logo_images_and_no_foreign_brand(self):
        bf.make_run(self.run_dir, "landing")
        plan = db.plan(self.run_dir, self.request())
        prompt, sizes = db.compose_prompt(plan, self.request())
        for hexv in ("#1F4E79", "#C8963E", "#9C2F3A", "#F6F1E7", "#222222"):
            self.assertIn(hexv, prompt)
        self.assertIn("Harbor #1F4E79", prompt)
        self.assertIn("Test Client Co", prompt)
        self.assertIn("1 attached" if False else "attached", prompt)
        self.assertEqual(len(db.references(plan)), 2)  # logo + the one slot file
        self.assertNotIn("Set for Life", prompt)
        self.assertEqual(sizes["chars"], len(prompt))

    def test_required_content_is_never_invented(self):
        bf.make_run(self.run_dir, "thank_you", {"icons": []})
        with self.assertRaises(db.BoardError) as cm:
            db.plan(self.run_dir, self.request())
        self.assertIn("icons", str(cm.exception))

    def test_unresolved_brand_colors_refuse(self):
        bf.make_run(self.run_dir, "landing")
        (self.run_dir / "inputs" / "brand.json").write_text(
            json.dumps({"brand_id": "test-client-co", "palette": {"gold": "CLIENT_MUST_SUPPLY"}}))
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())

    def test_example_client_words_refused_on_another_clients_board(self):
        bf.make_run(self.run_dir, "landing", {"positioning_line": "Wealth looks good on you."})
        plan = db.plan(self.run_dir, self.request())
        with self.assertRaises(db.BoardError) as cm:
            db.compose_prompt(plan, self.request())
        self.assertIn("another client", str(cm.exception))

    def test_missing_slot_file_refuses(self):
        bf.make_run(self.run_dir, "landing")
        self.rewrite_request(lambda r: r["sections"][0]["slots"][0].update(file="inputs/nope.png"))
        with self.assertRaises(db.BoardError):
            db.plan(self.run_dir, self.request())


class QcAndApprovalTests(Base):
    def seeded(self, **kw):
        bf.make_run(self.run_dir, kw.pop("role", "landing"))
        bf.seed_board(self.run_dir, **kw)

    def test_passes_with_approval(self):
        self.seeded()
        self.assertEqual(db.gate_failures(self.run_dir), [])

    def test_no_approval_fails_gate_but_passes_qc_floor(self):
        self.seeded(approved=False)
        self.assertEqual(db.validate(self.run_dir), [])
        self.assertTrue(any("no client approval" in f for f in db.gate_failures(self.run_dir)))

    def test_stub_board_never_validates(self):
        self.seeded(approved=False, provider="stub")
        self.assertTrue(any("stub placeholder" in f for f in db.validate(self.run_dir)))

    def test_approve_refuses_failing_board(self):
        self.seeded(approved=False)
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] = "nothing legible"
        db.save_record(self.run_dir, rec)
        with self.assertRaises(db.BoardError):
            db.approve(self.run_dir, "Client", "msg")

    def test_palette_must_be_the_resolved_client_palette(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["palette"][0]["hex"] = "#00FF00"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("palette" in f for f in db.validate(self.run_dir)))

    def test_readback_hex_outside_palette_and_missing_hex(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] += "\nExtra #123456"
        rec["readback"]["text"] = rec["readback"]["text"].replace("#222222", "")
        db.save_record(self.run_dir, rec)
        fails = " | ".join(db.validate(self.run_dir))
        self.assertIn("#123456", fails)
        self.assertIn("#222222", fails)

    def test_required_block_absent_from_readback(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] = rec["readback"]["text"].replace("BUILT TO LAST.", "")
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("'footer'" in f for f in db.validate(self.run_dir)))

    def test_foreign_brand_text_on_board_fails(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["readback"]["text"] += "\nSET FOR LIFE"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("another client" in f for f in db.validate(self.run_dir)))

    def test_logo_change_invalidates(self):
        self.seeded()
        bf.png(self.run_dir / "inputs" / "logo.png", (1, 2, 3))
        self.assertTrue(any("logo" in f for f in db.validate(self.run_dir)))

    def test_added_slot_makes_board_stale(self):
        self.seeded()
        self.rewrite_request(lambda r: r["sections"][1]["slots"].append(
            {"slot_id": "IMG-009", "art_direction": "New scene."}))
        self.assertTrue(any("image slots changed" in f for f in db.gate_failures(self.run_dir)))

    def test_changed_image_file_fails(self):
        self.seeded()
        bf.png(self.run_dir / "inputs" / "img1.png", (9, 9, 9))
        self.assertTrue(any("IMG-001 changed" in f for f in db.validate(self.run_dir)))

    def test_changed_board_after_approval_is_stale(self):
        self.seeded()
        bf.png(self.run_dir / db.BOARD_FILE, (1, 1, 1))
        fails = " | ".join(db.gate_failures(self.run_dir))
        self.assertIn("changed after it was recorded", fails)

    def test_new_readback_clears_approval(self):
        self.seeded()
        db.finalize(self.run_dir, db.load_record(self.run_dir)["readback"]["text"], "again")
        self.assertIsNone(db.load_record(self.run_dir)["approval"])

    def test_wrong_page_role_for_run(self):
        self.seeded()
        rec = db.load_record(self.run_dir)
        rec["page_role"] = "checkout"
        db.save_record(self.run_dir, rec)
        self.assertTrue(any("run declares" in f for f in db.validate(self.run_dir)))

    def test_cli_validate_and_gate_exit_codes(self):
        self.seeded(approved=False)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "validate", self.run_dir]).returncode, 0)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "gate", self.run_dir]).returncode, 1)
        ok = run([ROOT / "scripts" / "design_board.py", "approve", self.run_dir,
                  "--by", "Test Client", "--evidence", "msg-1"])
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(run([ROOT / "scripts" / "design_board.py", "gate", self.run_dir]).returncode, 0)


class ExecutorTests(Base):
    def test_preflight_composes_board_for_landing_and_thank_you_without_a_call(self):
        for role in ("landing", "thank_you"):
            rd = bf.make_run(self.td / role, role)
            out = run([EXEC, rd, "--stages", "design-board", "--preflight"])
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn(f"PREFLIGHT design-board {role} ratio=4:3", out.stdout)
            self.assertIn("#1F4E79", out.stdout)
            self.assertFalse((rd / "design-board").exists(), "preflight writes nothing")

    def test_board_stage_runs_alone(self):
        bf.make_run(self.run_dir)
        out = run([EXEC, self.run_dir, "--stages", "design-board,desktop-wireframe", "--preflight"])
        self.assertEqual(out.returncode, 1)
        self.assertIn("on its own", out.stdout)

    def test_stub_board_is_written_but_never_passes_the_gate(self):
        bf.make_run(self.run_dir)
        out = run([EXEC, self.run_dir, "--stages", "design-board", "--provider", "stub"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.run_dir / db.BOARD_FILE).is_file())
        self.assertTrue(any("stub placeholder" in f for f in db.validate(self.run_dir)))

    def test_wireframe_refused_without_approval_allowed_with_it(self):
        bf.make_run(self.run_dir)
        refused = run([EXEC, self.run_dir, "--stages", "desktop-wireframe", "--preflight"])
        self.assertEqual(refused.returncode, 1)
        self.assertIn("no board yet", refused.stdout)
        bf.seed_board(self.run_dir, approved=False)
        refused = run([EXEC, self.run_dir, "--stages", "desktop-wireframe", "--preflight"])
        self.assertEqual(refused.returncode, 1)
        self.assertIn("no client approval recorded", refused.stdout)
        db.approve(self.run_dir, "Test Client", "msg-1")
        allowed = run([EXEC, self.run_dir, "--stages", "desktop-wireframe", "--preflight"])
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertIn("PREFLIGHT desktop-wireframe", allowed.stdout)

    def test_item_mode_is_gated_too(self):
        bf.make_run(self.run_dir)
        (self.run_dir / "image-inventory-prompts").mkdir()
        (self.run_dir / "image-inventory-prompts" / "IMG-001.txt").write_text("prompt")
        out = run([EXEC, self.run_dir, "--stage", "image-generation-qc", "--item", "IMG-001"])
        self.assertEqual(out.returncode, 1)
        self.assertFalse((self.run_dir / "image-generation-qc").exists())


class StageGateTests(Base):
    """The real design-board validator behind the real gate, on a three-stage fixture contract."""

    def setUp(self):
        super().setUp()
        full = json.loads((ROOT / "references" / "stage-contract.json").read_text())
        keep = ["font-action-plan", "design-board", "desktop-wireframe"]
        stages = {k: full["stages"][k] for k in keep}
        stages["font-action-plan"] = {"depends_on": [], "requires_artifacts": [],
                                      "artifacts": [{"glob": "font-action-plan/font-map.json", "min_count": 1}],
                                      "validators": ["gate:noop"], "review_required": False,
                                      "min_scores": None}
        stages["desktop-wireframe"] = {"depends_on": ["font-action-plan", "design-board"],
                                       "requires_artifacts": [], "artifacts": [],
                                       "validators": ["gate:noop"], "review_required": False,
                                       "min_scores": None}
        contract = {"version": 1, "stage_order": keep, "stages": stages}
        self.contract = self.td / "contract.json"
        self.contract.write_text(json.dumps(contract), encoding="utf-8")
        self.env = {**bf.subprocess_env(), "STAGE_GATE_CONTRACT": str(self.contract)}
        bf.make_run(self.run_dir)
        self.gate("init", self.run_dir)
        self.receipt("font-action-plan")
        self.assertEqual(self.gate("close", self.run_dir, "font-action-plan").returncode, 0)

    def gate(self, *args):
        return run([GATE, *args], env=self.env)

    def receipt(self, stage):
        path = self.run_dir / "private" / "receipts" / f"{stage}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "stage": stage, "status": "pass", "author_agent": "builder", "reviewer_agent": "reviewer",
            "started_at": "2026-10-19T10:00:00+00:00", "finished_at": "2026-10-19T10:30:00+00:00",
            "artifacts": [], "notes": "fixture"}), encoding="utf-8")

    def review(self):
        env = {k: v for k, v in self.env.items() if "SESSION" not in k}
        env["OPENCLAW_SESSION_ID"] = "reviewer-session"
        scores = json.dumps({"brand_fidelity": {"score": 9, "note": "Checked against the board bytes and the contract line by line."}})
        out = subprocess.run(
            [PY, str(WRITE_REVIEW), str(self.run_dir), "design-board", "design-board",
             "--scores", scores, "--verdict", "pass",
             "--performed-check", "Opened the board image and scored it against the contract.",
             "--next-current-artifact", "the stage receipt that closes on this review",
             "--author-session", "builder-session"], text=True, capture_output=True, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_wireframe_stage_is_refused_until_the_board_is_approved_and_closed(self):
        # 1. no board at all
        out = self.gate("check", self.run_dir, "desktop-wireframe")
        self.assertEqual(out.returncode, 1)
        self.assertIn("dependency design-board is not closed", out.stdout + out.stderr)
        # 2. board made, read back, but the client has not approved: the board cannot close
        bf.seed_board(self.run_dir, approved=False)
        self.receipt("design-board")
        self.review()
        out = self.gate("close", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 1)
        self.assertIn("no client approval recorded", out.stdout + out.stderr)
        self.assertEqual(self.gate("check", self.run_dir, "desktop-wireframe").returncode, 1)
        # 3. client approval recorded: the board closes and the wireframe stage may start
        db.approve(self.run_dir, "Test Client", "msg-1")
        out = self.gate("close", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.gate("check", self.run_dir, "desktop-wireframe")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # 4. any change to the approved board after close is caught by the closed-artifact hashes
        bf.png(self.run_dir / db.BOARD_FILE, (5, 5, 5))
        out = self.gate("check", self.run_dir, "desktop-wireframe")
        self.assertEqual(out.returncode, 1)
        self.assertIn("changed after close", out.stdout + out.stderr)

    def test_brand_colors_unresolved_blocks_design_board_check(self):
        (self.run_dir / "inputs" / "brand.json").write_text(
            json.dumps({"brand_id": "test-client-co", "palette": {"gold": "CLIENT_MUST_SUPPLY"}}))
        out = self.gate("check", self.run_dir, "design-board")
        self.assertEqual(out.returncode, 1)
        self.assertIn("brand colors", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
