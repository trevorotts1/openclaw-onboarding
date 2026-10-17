#!/usr/bin/env python3
"""Acceptance tests for Review Receipt v2 and friends (fix plan Items 2, 3, 4, 7, 12).

- Item 2: write_review.py session stamping / hash / note floor; gate close
  verifies v2 files, rejects v1 receipts with the migration message, and
  records review hashes in state.json (tamper caught by the next check).
- Item 3: visual-mockup and final-mockups require per-item reviews.
- Item 4: validate_wireframe.py section-plan checks.
- Item 7: REPORT.md review-mode stamp computation.
- Item 12: per-file review coverage and the average rule.

Amendment 6 deltas covered here: the SOP evidentiary fields on every
review (Item 2), the UNKNOWN-session rule (no session env still writes,
reviewer_session UNKNOWN, independent_review false, never INDEPENDENT),
mockup.html and bible markdown coverage (Item 3), and the per-artifact
average replacing cross-file pooling (Item 12).

Gate subprocess tests use a fixture contract derived from the REAL contract
with validator commands replaced by gate:noop, so review behavior is the
real contract's while unrelated validators stay out of the way.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"
VALIDATE_WIREFRAME = ROOT / "scripts" / "validate_wireframe.py"
PY = sys.executable

LONG_NOTE = "Checked against the artifact bytes and the stage rubric line by line."
PERFORMED_CHECK = "Opened the artifact itself and scored it against the stage rubric."
NEXT_ARTIFACT = "the stage receipt that closes on this review"


def write(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def fixture_contract(td: Path) -> Path:
    contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
    for stage in contract["stages"].values():
        stage["validators"] = ["gate:noop"]
    path = td / "contract-fixture.json"
    path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    return path


def scores_json(**criteria):
    return json.dumps({name: {"score": score, "note": LONG_NOTE}
                       for name, score in criteria.items()})


def run_write_review(run, stage, item, reviewer_session, scores, verdict="pass",
                     author_session="sess-author-1", contract=None, extra_env=None,
                     performed_check=PERFORMED_CHECK, next_artifact=NEXT_ARTIFACT,
                     repair_attempt=None, automatic_failures=None,
                     specific_defects=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")}
    if reviewer_session is not None:
        env["OPENCLAW_SESSION_ID"] = reviewer_session
    if contract is not None:
        env["STAGE_GATE_CONTRACT"] = str(contract)
    if extra_env:
        env.update(extra_env)
    cmd = [PY, str(WRITE_REVIEW), str(run), stage, item,
           "--scores", scores, "--verdict", verdict,
           "--performed-check", performed_check,
           "--next-current-artifact", next_artifact]
    if author_session is not None:
        cmd += ["--author-session", author_session]
    if repair_attempt is not None:
        cmd += ["--repair-attempt", str(repair_attempt)]
    if automatic_failures is not None:
        cmd += ["--automatic-failures", json.dumps(automatic_failures)]
    if specific_defects is not None:
        cmd += ["--specific-defects", json.dumps(specific_defects)]
    return subprocess.run(cmd, text=True, capture_output=True, env=env)


def run_gate(contract, *args):
    env = {**os.environ, "STAGE_GATE_CONTRACT": str(contract)}
    return subprocess.run([PY, str(GATE), *args], text=True, capture_output=True, env=env)


def put_receipt(run, stage, **kw):
    receipt = {"stage": stage, "status": "pass", "author_agent": "builder-agent",
               "author_session": "sess-author-1",
               "started_at": "2026-10-13T10:00:00+00:00",
               "finished_at": "2026-10-13T10:30:00+00:00", "artifacts": []}
    receipt.update(kw)
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps(receipt))


class WriteReviewTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="review-v2-"))
        self.contract = fixture_contract(self.td)
        self.run = self.td / "run"
        write(self.run / "copy" / "internal-manuscript.md", "manuscript body")
        write(self.run / "copy" / "public-copy.md", "public body")
        write(self.run / "copy" / "copy-manifest.json", "{}")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_no_session_env_writes_unknown_with_warning(self):
        # Amendment 6, Item 2 delta: no session id in the environment no
        # longer blocks the write. The limitation is recorded instead:
        # reviewer_session UNKNOWN, independent_review false, stderr warning.
        proc = run_write_review(self.run, "copy", "stage", None,
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("WARNING", proc.stderr)
        self.assertIn("UNKNOWN", proc.stderr)
        path = self.run / "private" / "reviews" / "copy" / "stage.review.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["reviewer_session"], "UNKNOWN")
        self.assertIs(data["independent_review"], False)

    def test_fail_verdict_requires_specific_defects(self):
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                scores_json(clarity=5), verdict="fail",
                                contract=self.contract)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("specific-defects", proc.stdout + proc.stderr)
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                scores_json(clarity=5), verdict="fail",
                                specific_defects=["Hero headline buries the offer"],
                                repair_attempt=2,
                                contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads((self.run / "private" / "reviews" / "copy"
                           / "stage.review.json").read_text())
        self.assertEqual(data["specific_defects"],
                         ["Hero headline buries the offer"])
        self.assertEqual(data["repair_attempt"], 2)

    def test_short_note_rejected(self):
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                json.dumps({"clarity": {"score": 9, "note": "looks fine"}}),
                                contract=self.contract)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("at least 40", proc.stdout + proc.stderr)

    def test_filename_only_note_rejected(self):
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                json.dumps({"clarity": {"score": 9,
                                                        "note": "internal-manuscript.md"}}),
                                contract=self.contract)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_writes_exact_v2_fields_with_computed_hash(self):
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        path = self.run / "private" / "reviews" / "copy" / "stage.review.json"
        data = json.loads(path.read_text())
        self.assertEqual(set(data), {"item", "artifact", "artifact_sha256",
                                     "author_session", "reviewer_session",
                                     "reviewed_at", "criteria", "verdict",
                                     "automatic_failures", "repair_attempt",
                                     "specific_defects", "performed_check",
                                     "next_current_artifact",
                                     "independent_review"})
        self.assertEqual(data["item"], "stage")
        self.assertEqual(data["reviewer_session"], "sess-reviewer-1")
        self.assertEqual(data["author_session"], "sess-author-1")
        self.assertEqual(data["automatic_failures"], [])
        self.assertEqual(data["repair_attempt"], 0)
        self.assertEqual(data["specific_defects"], [])
        self.assertEqual(data["performed_check"], PERFORMED_CHECK)
        self.assertEqual(data["next_current_artifact"], NEXT_ARTIFACT)
        self.assertIs(data["independent_review"], True)
        expected = hashlib.sha256(
            (self.run / data["artifact"]).read_bytes()).hexdigest()
        self.assertEqual(data["artifact_sha256"], expected)


class GateV2CloseTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="gate-v2-"))
        self.contract = fixture_contract(self.td)
        self.run = self.td / "run"
        write(self.run / "intake.json", "{}")
        run_gate(self.contract, "init", str(self.run))
        write(self.run / "copy" / "internal-manuscript.md", "manuscript body")
        write(self.run / "copy" / "public-copy.md", "public body")
        write(self.run / "copy" / "copy-manifest.json", "{}")

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def close_copy(self):
        return run_gate(self.contract, "close", str(self.run), "copy")

    def test_v1_receipt_fails_with_migration_message(self):
        put_receipt(self.run, "copy", scores={"clarity": 9})
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("v1", proc.stdout)
        self.assertIn("Migration", proc.stdout)
        self.assertIn("write_review.py", proc.stdout)

    def test_missing_review_file_fails_naming_item(self):
        put_receipt(self.run, "copy")
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("missing review file private/reviews/copy/stage.review.json",
                      proc.stdout)

    def test_self_review_same_session_fails(self):
        put_receipt(self.run, "copy")
        proc = run_write_review(self.run, "copy", "stage", "sess-author-1",
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("reviewer_session equals", proc.stdout)

    def test_independent_review_closes_and_records_review_hashes(self):
        put_receipt(self.run, "copy")
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        state = json.loads((self.run / "private" / "state.json").read_text())
        entry = state["stages"]["copy"]
        self.assertIn("private/reviews/copy/stage.review.json", entry["review_hashes"])
        self.assertNotIn("scores", entry["receipt"])
        self.assertEqual(entry["receipt"]["scores_summary"]["min"], 9.0)
        # Tamper with the review: the next stage's check must catch it.
        review_path = self.run / "private" / "reviews" / "copy" / "stage.review.json"
        data = json.loads(review_path.read_text())
        data["criteria"]["clarity"]["note"] = LONG_NOTE + " Edited after close."
        review_path.write_text(json.dumps(data, indent=2))
        proc = run_gate(self.contract, "check", str(self.run), "font-action-plan")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("review changed after close", proc.stdout + proc.stderr)

    def test_unknown_session_review_closes_but_is_not_independent(self):
        # The UNKNOWN-session review is a complete record, so the stage
        # closes; independence is what it can never claim (Item 7 stamp
        # coverage lives in PerFileAndCoversTest).
        put_receipt(self.run, "copy")
        proc = run_write_review(self.run, "copy", "stage", None,
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_artifact_changed_after_review_fails_hash_match(self):
        put_receipt(self.run, "copy")
        proc = run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                                scores_json(clarity=9), contract=self.contract)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        write(self.run / "copy" / "internal-manuscript.md", "rewritten after review")
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("artifact hash mismatch", proc.stdout)

    def test_score_below_each_fails(self):
        put_receipt(self.run, "copy")
        run_write_review(self.run, "copy", "stage", "sess-reviewer-1",
                         scores_json(clarity=7), contract=self.contract)
        proc = self.close_copy()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("below minimum 8", proc.stdout)


sys.path.insert(0, str(ROOT / "scripts"))


class PerFileAndCoversTest(unittest.TestCase):
    """Direct check_review_scores calls against the real contract."""

    @classmethod
    def setUpClass(cls):
        os.environ["STAGE_GATE_CONTRACT"] = str(ROOT / "references" / "stage-contract.json")
        import stage_gate
        cls.gate = stage_gate

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="perfile-v2-"))
        self.run = self.td / "run"

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def write_review_file(self, stage, item, artifact_rel, criteria,
                          author="sess-author-1", reviewer="sess-reviewer-1",
                          verdict="pass", automatic_failures=None, evidence=True,
                          run=None):
        run = run or self.run
        artifact = run / artifact_rel
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        data = {"item": item, "artifact": artifact_rel, "artifact_sha256": digest,
                "author_session": author, "reviewer_session": reviewer,
                "reviewed_at": "2026-10-13T11:00:00+00:00",
                "criteria": {k: {"score": v, "note": LONG_NOTE}
                             for k, v in criteria.items()},
                "verdict": verdict}
        if evidence:
            data.update({
                "automatic_failures": automatic_failures or [],
                "repair_attempt": 0,
                "specific_defects": [],
                "performed_check": PERFORMED_CHECK,
                "next_current_artifact": NEXT_ARTIFACT,
                "independent_review": bool(
                    reviewer and reviewer.upper() != "UNKNOWN"
                    and reviewer != author),
            })
        write(run / "private" / "reviews" / stage / f"{item}.review.json",
              json.dumps(data))

    def receipt(self):
        return {"author_agent": "builder-agent", "author_session": "sess-author-1"}

    def build_prompt_stage(self):
        write(self.run / "image-inventory-prompts" / "IMG-001.txt", "prompt one")
        write(self.run / "image-inventory-prompts" / "IMG-002.txt", "prompt two")

    def test_item12_missing_one_file_lists_it_uncovered(self):
        self.build_prompt_stage()
        self.write_review_file("image-inventory-prompts", "IMG-001",
                               "image-inventory-prompts/IMG-001.txt", {"fidelity": 9})
        failures = self.gate.check_review_scores(
            self.run, "image-inventory-prompts", self.receipt())
        joined = "\n".join(failures)
        self.assertIn("IMG-002", joined)
        self.assertIn("missing review file", joined)

    def test_item12_per_artifact_average_enforced(self):
        self.build_prompt_stage()
        # Amendment 6, Item 12 delta: the average is per artifact. IMG-001
        # is perfect and IMG-002 sits at 8.0: the pooled mean would be 9.0
        # and the old cross-file rule passed this stage. The per-artifact
        # rule must fail, naming IMG-002.
        self.write_review_file("image-inventory-prompts", "IMG-001",
                               "image-inventory-prompts/IMG-001.txt",
                               {"fidelity": 10, "richness": 10})
        self.write_review_file("image-inventory-prompts", "IMG-002",
                               "image-inventory-prompts/IMG-002.txt",
                               {"fidelity": 8, "richness": 8})
        failures = self.gate.check_review_scores(
            self.run, "image-inventory-prompts", self.receipt())
        self.assertTrue(any("IMG-002" in f and "average" in f
                            and "per-artifact" in f for f in failures), failures)
        self.assertFalse(any("IMG-001" in f and "average" in f
                             for f in failures), failures)
        # Each file reaching 8.5 on its own passes, even though no score
        # moved across files.
        self.write_review_file("image-inventory-prompts", "IMG-001",
                               "image-inventory-prompts/IMG-001.txt",
                               {"fidelity": 9, "richness": 8})
        self.write_review_file("image-inventory-prompts", "IMG-002",
                               "image-inventory-prompts/IMG-002.txt",
                               {"fidelity": 8, "richness": 9})
        failures = self.gate.check_review_scores(
            self.run, "image-inventory-prompts", self.receipt())
        self.assertEqual(failures, [], failures)

    def test_item12_recorded_auto_fail_blocks_close(self):
        self.build_prompt_stage()
        self.write_review_file("image-inventory-prompts", "IMG-001",
                               "image-inventory-prompts/IMG-001.txt",
                               {"fidelity": 9, "richness": 9},
                               automatic_failures=["provenance: stock photo "
                                                   "presented as generated"])
        self.write_review_file("image-inventory-prompts", "IMG-002",
                               "image-inventory-prompts/IMG-002.txt",
                               {"fidelity": 9, "richness": 9})
        failures = self.gate.check_review_scores(
            self.run, "image-inventory-prompts", self.receipt())
        self.assertTrue(any("IMG-001" in f and "automatic failure" in f
                            for f in failures), failures)

    def test_review_missing_evidentiary_fields_fails_by_name(self):
        self.build_prompt_stage()
        for item in ("IMG-001", "IMG-002"):
            self.write_review_file("image-inventory-prompts", item,
                                   f"image-inventory-prompts/{item}.txt",
                                   {"fidelity": 9, "richness": 9},
                                   evidence=False)
        failures = self.gate.check_review_scores(
            self.run, "image-inventory-prompts", self.receipt())
        joined = "\n".join(failures)
        for field in ("automatic_failures", "repair_attempt",
                      "performed_check", "next_current_artifact",
                      "independent_review"):
            self.assertIn(field, joined)

    def test_item3_visual_mockup_needs_bible_and_part_reviews(self):
        write(self.run / "visual-mockup" / "page-visual-bible.json", "{}")
        write(self.run / "visual-mockup" / "mockup.html", "<html></html>")
        write(self.run / "visual-mockup" / "desktop" / "part-01.png", b"png-d")
        write(self.run / "visual-mockup" / "mobile" / "part-01.png", b"png-m")
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        joined = "\n".join(failures)
        # Desktop and mobile parts share the stem part-01, so their item ids
        # are disambiguated by folder; the bible is its own item; the stage's
        # mockup.html is covered too (Amendment 6, Item 3 delta).
        for item in ("desktop-part-01", "mobile-part-01", "page-visual-bible",
                     "mockup"):
            self.assertIn(item, joined)
        self.assertIn("missing review file", joined)
        self.write_review_file("visual-mockup", "desktop-part-01",
                               "visual-mockup/desktop/part-01.png",
                               {"composition_fidelity": 9})
        self.write_review_file("visual-mockup", "mobile-part-01",
                               "visual-mockup/mobile/part-01.png",
                               {"composition_fidelity": 9})
        self.write_review_file("visual-mockup", "page-visual-bible",
                               "visual-mockup/page-visual-bible.json",
                               {"brand_token_discipline": 9})
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        joined = "\n".join(failures)
        self.assertEqual(joined.count("missing review file"), 1, failures)
        self.assertIn("mockup", joined)
        # The real writer resolves the mockup item and its review closes
        # the coverage gap.
        proc = run_write_review(
            self.run, "visual-mockup", "mockup", "sess-reviewer-1",
            scores_json(composition_fidelity=9),
            contract=ROOT / "references" / "stage-contract.json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        self.assertEqual(failures, [], failures)
        # A criterion under the stage minimum of 8 fails by name.
        self.write_review_file("visual-mockup", "mobile-part-01",
                               "visual-mockup/mobile/part-01.png",
                               {"composition_fidelity": 7})
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        self.assertTrue(any("below minimum 8" in f and "mobile-part-01" in f
                            for f in failures), failures)

    def test_item3_visual_mockup_bible_json_and_md_both_covered(self):
        # Amendment 6, Item 3 delta: the bible markdown is covered alongside
        # the bible JSON; sharing a folder and a stem, their item ids are
        # disambiguated by suffix.
        write(self.run / "visual-mockup" / "page-visual-bible.json", "{}")
        write(self.run / "visual-mockup" / "page-visual-bible.md", "# bible")
        write(self.run / "visual-mockup" / "mockup.html", "<html></html>")
        write(self.run / "visual-mockup" / "desktop" / "part-01.png", b"png-d")
        write(self.run / "visual-mockup" / "mobile" / "part-01.png", b"png-m")
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        joined = "\n".join(failures)
        self.assertIn("page-visual-bible-json", joined)
        self.assertIn("page-visual-bible-md", joined)
        for item, rel in (("desktop-part-01", "visual-mockup/desktop/part-01.png"),
                          ("mobile-part-01", "visual-mockup/mobile/part-01.png"),
                          ("page-visual-bible-json",
                           "visual-mockup/page-visual-bible.json")):
            self.write_review_file("visual-mockup", item, rel,
                                   {"brand_token_discipline": 9})
        # The markdown bible's review goes through the real writer, which
        # must resolve the suffix-disambiguated item id to the .md file.
        proc = run_write_review(
            self.run, "visual-mockup", "page-visual-bible-md", "sess-reviewer-1",
            scores_json(brand_token_discipline=9),
            contract=ROOT / "references" / "stage-contract.json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads((self.run / "private" / "reviews" / "visual-mockup"
                           / "page-visual-bible-md.review.json").read_text())
        self.assertEqual(data["artifact"], "visual-mockup/page-visual-bible.md")
        proc = run_write_review(
            self.run, "visual-mockup", "mockup", "sess-reviewer-1",
            scores_json(composition_fidelity=9),
            contract=ROOT / "references" / "stage-contract.json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        failures = self.gate.check_review_scores(
            self.run, "visual-mockup", self.receipt())
        self.assertEqual(failures, [], failures)

    def test_item3_final_mockups_needs_mockup_review(self):
        write(self.run / "final-mockups" / "mockup.html", "<html></html>")
        write(self.run / "final-mockups" / "desktop" / "part-01.png", b"png-d")
        write(self.run / "final-mockups" / "mobile" / "part-01.png", b"png-m")
        # Item 12: the hybrid board is a closing deliverable of the stage
        # and is in its review cover as the approval artifact.
        write(self.run / "final-mockups" / "hybrid-board.png", b"png-b")
        write(self.run / "final-mockups" / "hybrid-board.json", "{}")
        failures = self.gate.check_review_scores(
            self.run, "final-mockups", self.receipt())
        joined = "\n".join(failures)
        for item in ("desktop-part-01", "mobile-part-01", "mockup", "hybrid-board"):
            self.assertIn(item, joined)
        self.assertIn("missing review file", joined)
        for item, rel in (("desktop-part-01", "final-mockups/desktop/part-01.png"),
                          ("mobile-part-01", "final-mockups/mobile/part-01.png"),
                          ("hybrid-board", "final-mockups/hybrid-board.png"),
                          ("mockup", "final-mockups/mockup.html")):
            self.write_review_file("final-mockups", item, rel,
                                   {"composition_fidelity": 9})
        failures = self.gate.check_review_scores(
            self.run, "final-mockups", self.receipt())
        self.assertEqual(failures, [], failures)

    def test_item7_review_mode_stamps(self):
        empty = self.td / "empty"
        empty.mkdir()
        self.assertIn("UNKNOWN", self.gate.compute_review_mode(empty))
        write(self.run / "copy" / "public-copy.md", "public")
        self.write_review_file("copy", "stage", "copy/public-copy.md", {"clarity": 9})
        line = self.gate.compute_review_mode(self.run)
        self.assertIn("INDEPENDENT", line)
        self.assertIn("1 reviewer sessions", line)
        self.write_review_file("copy", "stage", "copy/public-copy.md", {"clarity": 9},
                               reviewer="sess-author-1")
        line = self.gate.compute_review_mode(self.run)
        self.assertIn("SELF-REVIEWED", line)
        self.assertIn("copy", line)

    def test_item7_unknown_session_never_independent(self):
        # Amendment 6, Item 2 delta: reviews whose reviewer session is
        # recorded as UNKNOWN never count as independent.
        run_unknown = self.td / "run-unknown"
        write(run_unknown / "copy" / "public-copy.md", "public")
        self.write_review_file("copy", "stage", "copy/public-copy.md",
                               {"clarity": 9}, reviewer="UNKNOWN",
                               run=run_unknown)
        line = self.gate.compute_review_mode(run_unknown)
        self.assertTrue(line.startswith("Review mode: UNKNOWN"), line)
        self.assertNotIn("INDEPENDENT", line)
        # Mixed: one genuinely independent review plus one UNKNOWN-session
        # review stamps SELF-REVIEWED, naming the unverified stage.
        run_mixed = self.td / "run-mixed"
        write(run_mixed / "copy" / "public-copy.md", "public")
        write(run_mixed / "visual-mockup" / "mockup.html", "<html></html>")
        self.write_review_file("copy", "stage", "copy/public-copy.md",
                               {"clarity": 9}, run=run_mixed)
        self.write_review_file("visual-mockup", "mockup",
                               "visual-mockup/mockup.html",
                               {"composition_fidelity": 9},
                               reviewer="UNKNOWN", run=run_mixed)
        line = self.gate.compute_review_mode(run_mixed)
        self.assertIn("SELF-REVIEWED", line)
        self.assertIn("visual-mockup", line)
        self.assertNotIn("INDEPENDENT", line)


class WireframeValidatorTest(unittest.TestCase):
    # Migrated to the Item 11 spec image set by Update Plan Item 15: the
    # validator now checks section slices (not the retired part-*.png
    # exports) plus the Item 15 annotation, slot-label, and brand-color
    # traits, so the compliant fixture carries real brand-colored slices
    # and a fully annotated plan. Each test's intent is unchanged.
    NAVY = (26, 26, 46)  # the skill brand file's palette navy

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="wireframe-"))
        self.run = self.td / "run"
        from PIL import Image
        self.Image = Image
        write(self.run / "copy" / "copy-manifest.json", json.dumps(
            {"sections": [{"section_id": "hero"}, {"section_id": "offer"}]}))
        write(self.run / "desktop-wireframe" / "image-inventory.json", json.dumps(
            {"images": [{"id": "IMG-001", "aspect_ratio": "16:9"},
                        {"id": "IMG-002", "aspect_ratio": "4:5"}]}))
        self.write_png(self.run / "desktop-wireframe" / "section-01.png", 1440)
        self.write_png(self.run / "desktop-wireframe" / "section-02.png", 1440)
        write(self.run / "desktop-wireframe" / "wireframe-full.png", "stub")
        write(self.run / "desktop-wireframe" / "wireframe.pdf", "stub")
        self.good_plan = [
            {"section_id": "hero", "section_number": 1, "section_name": "Hero",
             "copy_block_ids": ["hero-copy"],
             "image_slot_ids": ["IMG-001"], "reference_traits": [],
             "type_specs": {"h1": "64px", "h2": "32px", "body": "18px",
                            "cta": "18px"},
             "behavior_notes": "CTA before portrait on mobile",
             "header_strip": {"page_width_px": 1440, "content_width_px": 1200},
             "slot_labels": {"IMG-001": {"aspect_ratio": "16:9",
                                         "art_direction": "Founder portrait, hero"}}},
            {"section_id": "offer", "section_number": 2, "section_name": "Offer",
             "copy_block_ids": ["offer-copy"],
             "image_slot_ids": ["IMG-002"], "reference_traits": [],
             "type_specs": {"h1": "48px", "h2": "32px", "body": "18px",
                            "cta": "18px"},
             "behavior_notes": "No CTA",
             "slot_labels": {"IMG-002": {"aspect_ratio": "4:5",
                                         "art_direction": "Product still life"}}},
        ]
        self.write_plan(self.good_plan)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def write_png(self, path, width, height=300):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.Image.new("RGB", (width, height), self.NAVY).save(path)

    def write_plan(self, plan):
        write(self.run / "desktop-wireframe" / "section-plan.json", json.dumps(plan))

    def validate(self, stage="desktop-wireframe"):
        return subprocess.run([PY, str(VALIDATE_WIREFRAME), str(self.run), stage],
                              text=True, capture_output=True)

    def test_good_plan_passes(self):
        proc = self.validate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_reordered_section_fails_by_name(self):
        self.write_plan([self.good_plan[1], self.good_plan[0]])
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("order differs", proc.stdout)

    def test_missing_section_fails_by_name(self):
        self.write_plan([self.good_plan[0]])
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("'offer'", proc.stdout)

    def test_orphan_slot_fails_bidirectionally(self):
        plan = json.loads(json.dumps(self.good_plan))
        plan[0]["image_slot_ids"] = ["IMG-001", "IMG-999"]
        plan[1]["image_slot_ids"] = []
        self.write_plan(plan)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("IMG-999", proc.stdout)
        self.assertIn("IMG-002", proc.stdout)

    def test_missing_slice_fails(self):
        # Item 15 form of the old numbering-gap test: the spec image set
        # delivers exactly one section slice per planned section.
        (self.run / "desktop-wireframe" / "section-02.png").unlink()
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("one slice per section", proc.stdout)

    def test_wrong_width_fails(self):
        self.write_png(self.run / "desktop-wireframe" / "section-02.png", 800)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("width 800px, expected 1440px", proc.stdout)

    def test_ratio_mismatch_fails(self):
        plan = json.loads(json.dumps(self.good_plan))
        plan[0]["slot_aspect_ratios"] = {"IMG-001": "1:1"}
        self.write_plan(plan)
        proc = self.validate()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("IMG-001", proc.stdout)
        self.assertIn("does not match inventory ratio", proc.stdout)

    def test_missing_plan_is_unreadable_input(self):
        (self.run / "desktop-wireframe" / "section-plan.json").unlink()
        proc = self.validate()
        self.assertEqual(proc.returncode, 2, proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
