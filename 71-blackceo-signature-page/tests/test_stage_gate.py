#!/usr/bin/env python3
"""Tests for scripts/stage_gate.py — order B2 test items (a)-(d) plus the
per-file validator substitution regression (e)-(g).

Runs the gate as a subprocess against fixture run folders so the exit codes,
output text, and state files are tested exactly as an agent would see them.

Scope: gate logic (stage-contract.json + stage_gate.py). Tests (a)-(d) replace
validator commands owned by other order items with the gate's own noop builtin
via a fixture contract; tests (e)-(f) keep the REAL per-file validator commands
of the two image stages (validate_prompt.py {file} {sauce},
validate_image_grade.py {file} --brand {brand}) so a substitution regression
fails loudly instead of being masked by gate:noop.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "stage_gate.py"
WRITE_REVIEW = ROOT / "scripts" / "write_review.py"
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402  (module import loads the real contract)
sys.path.insert(0, str(ROOT / "tests"))
import fit_prompt  # noqa: E402


def fitted_good_prompt():
    """tests/fixtures/prompt_good.txt grown into the KIE rule 12 band (the length gate measures the model maxLength)."""
    return fit_prompt.fit_text((ROOT / "tests" / "fixtures" / "prompt_good.txt").read_text(encoding="utf-8"))


def run_gate(*args, expect=None, env=None):
    proc = subprocess.run([PY, str(GATE), *args], text=True, capture_output=True, env=env)
    if expect is not None:
        assert proc.returncode == expect, (
            f"stage_gate {' '.join(args)}: expected rc={expect}, got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def write(path: Path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def receipt(stage, author="builder-agent", reviewer=None, status="pass", scores=None, extra=None):
    r = {
        "stage": stage,
        "status": status,
        "author_agent": author,
        "reviewer_agent": reviewer or author,
        "started_at": "2026-10-05T10:00:00+00:00",
        "finished_at": "2026-10-05T10:30:00+00:00",
        "artifacts": [],
        "notes": "fixture",
    }
    # Review Receipt v2: receipts carry no scores. The scores key is only
    # emitted when a caller passes a non-empty dict (the legacy image-chain
    # fixtures below, which predate v2 and are out of scope here).
    if scores:
        r["scores"] = scores
    if extra:
        r.update(extra)
    return r


def put_receipt(run: Path, stage, **kw):
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps(receipt(stage, **kw)))


REVIEW_NOTE = "Checked against the artifact bytes and the stage rubric line by line."
REVIEW_PERFORMED = "Opened the artifact itself and scored it against the stage rubric."
REVIEW_NEXT = "the stage receipt that closes on this review"


def write_review(run, stage, item, criteria, author_session, reviewer_session, env):
    """Write one Review Receipt v2 file with the real writer, run from the
    reviewer's session (OPENCLAW_SESSION_ID), exactly as a run would."""
    scores = json.dumps({name: {"score": score, "note": REVIEW_NOTE}
                         for name, score in criteria.items()})
    wenv = {k: v for k, v in env.items()
            if k not in ("OPENCLAW_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
                         "CLAUDE_SESSION_ID")}
    wenv["OPENCLAW_SESSION_ID"] = reviewer_session
    proc = subprocess.run(
        [PY, str(WRITE_REVIEW), str(run), stage, item,
         "--scores", scores, "--verdict", "pass",
         "--performed-check", REVIEW_PERFORMED,
         "--next-current-artifact", REVIEW_NEXT,
         "--author-session", author_session],
        text=True, capture_output=True, env=wenv)
    assert proc.returncode == 0, (
        f"write_review {stage}/{item}: rc={proc.returncode}\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def kie_transport(files, **over):
    """A valid Skill 74 transport block for the given generated files (all default-route 16:9)."""
    tasks = [{"file": f, "task_id": f"task-{i:03d}", "model_id": "model-from-skill-66",
              "model_source": "latest-family", "requested_ratio": "16:9", "generated_ratio": "16:9",
              "preflight_ok": True, "budget_exit": 0} for i, f in enumerate(files, 1)]
    t = {"skill": "74-kie-live-adapter", "policy": "66-kie-image", "mode": "active", "tasks": tasks}
    t.update(over)
    return t


def kie_receipts(run, transport):
    """Write the receipts/kie74 result file each Skill 74 task points to."""
    for x in transport.get("tasks", []):
        if "task_id" in x:
            write(run / "receipts" / "kie74" / f"{x['task_id']}.json", json.dumps({
                "provider": "kie", "adapter": "74-kie-live-adapter", "adapter_mode": "active",
                "backend": "native-live", "model_id": x.get("model_id"), "task_id": x["task_id"],
                "state": "success", "saved_paths": [x["file"]], "warnings": [], "data": {}}))


KIE_COST = {"provider": "kie", "credits_before": 100.0, "credits_after": 88.0}
KIE_FILES = ["image-generation-qc/Image-001.png", "image-generation-qc/Image-002.png"]


def png_bytes():
    # 1x1 transparent PNG, byte-identical every call for deterministic hashing.
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def png_variant(index):
    """Distinct deterministic PNG bytes per index (stdlib only): a
    16x16 two-tone pattern from a fixed palette, seeded per index. The
    image-chain fixtures need genuinely distinct images, not just
    distinct bytes: the assembled gate's grade screen detects
    duplicates by average hash, under which any two solid-color
    images are identical."""
    import random
    import struct
    import zlib
    palette = [(200, 40, 40), (40, 200, 40), (40, 40, 200), (200, 200, 40)]
    base = palette[index % len(palette)]
    dark = tuple(int(c * 0.45) for c in base)
    rng = random.Random(1000 + index)
    px = [[base if rng.random() < 0.5 else dark for _ in range(16)]
          for _ in range(16)]

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def fixture_contract(td: Path) -> Path:
    """Copy the real contract, replacing validator commands that call scripts other
    executors own with gate:noop so these tests exercise ONLY gate logic."""
    contract = json.loads((ROOT / "references" / "stage-contract.json").read_text())
    for stage in contract["stages"].values():
        stage["validators"] = ["gate:noop"]
    path = td / "contract-fixture.json"
    path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    return path


class StageGateTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="stage-gate-test-"))
        # Fixture contract + env: real stage/dependency shape, validators disabled.
        self.contract_path = fixture_contract(self.td)
        self.env = {**os.environ, "STAGE_GATE_CONTRACT": str(self.contract_path)}

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    # ---- (a) check responsive-html with no visual-mockup receipt fails naming visual-mockup
    def test_a_check_responsive_html_fails_naming_visual_mockup(self):
        run, gate = self.build_run_chain()
        # Break visual-mockup's closure: remove its receipt, close-out, and every
        # later stage's closure so the transitive chain stops at visual-mockup.
        (run / "private" / "receipts" / "visual-mockup.json").unlink()
        state_path = run / "private" / "state.json"
        state = json.loads(state_path.read_text())
        for stage in ("visual-mockup", "image-inventory-prompts", "image-generation-qc",
                      "image-map-upload", "final-mockups"):
            state["stages"].pop(stage, None)
        state_path.write_text(json.dumps(state, indent=2))
        proc = run_gate("check", str(run), "responsive-html", expect=1, env=self.env)
        combined = proc.stdout + proc.stderr
        self.assertIn("visual-mockup", combined,
                      "failure output must name the unclosed dependency visual-mockup")

    # ---- (b) close whose only review comes from the author's own session fails
    def test_b_close_reviewer_equals_author_fails(self):
        run = self.td / "run"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "Test"}}))
        run_gate("init", str(run), expect=0, env=self.env)
        put_receipt(run, "copy", author="builder-agent", reviewer="builder-agent")
        write(run / "copy" / "internal-manuscript.md", "x")
        write(run / "copy" / "public-copy.md", "x")
        write(run / "copy" / "copy-manifest.json", "{}")
        # Review Receipt v2: the only review was written from the author's
        # own session, so the gate refuses the close on independence.
        write_review(run, "copy", "stage", {"clarity": 9},
                     "builder-session", "builder-session", self.env)
        proc = run_gate("close", str(run), "copy", expect=1, env=self.env)
        combined = proc.stdout + proc.stderr
        self.assertIn("reviewer_session equals author_session", combined)

    # ---- (b2) close with an independent reviewer passes
    def test_b2_close_independent_reviewer_passes(self):
        run = self.td / "run"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "Test"}}))
        run_gate("init", str(run), expect=0, env=self.env)
        put_receipt(run, "copy", author="builder-agent", reviewer="reviewer-agent")
        write(run / "copy" / "internal-manuscript.md", "x")
        write(run / "copy" / "public-copy.md", "x")
        write(run / "copy" / "copy-manifest.json", "{}")
        write_review(run, "copy", "stage", {"clarity": 9},
                     "builder-session", "reviewer-session", self.env)
        run_gate("close", str(run), "copy", expect=0, env=self.env)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["copy"]["status"], "closed")
        self.assertIn("closed_at", state["stages"]["copy"])
        self.assertIn("copy/public-copy.md", state["stages"]["copy"]["artifact_hashes"])

    # ---- (c) changing an artifact after close makes the next check fail
    def test_c_changed_artifact_after_close_fails_check(self):
        run = self.td / "run"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "Test"}}))
        run_gate("init", str(run), expect=0, env=self.env)
        put_receipt(run, "intake", author="intake-agent", reviewer="intake-agent")
        run_gate("close", str(run), "intake", expect=0, env=self.env)
        # intake closed; next stage check passes
        run_gate("check", str(run), "copy", expect=0, env=self.env)
        # mutate the closed artifact
        time.sleep(0.01)
        write(run / "intake.json", json.dumps({"tampered": True}))
        proc = run_gate("check", str(run), "copy", expect=1, env=self.env)
        combined = proc.stdout + proc.stderr
        self.assertIn("changed after close", combined)

    # ---- (d) complete fixture run passes report
    def test_d_complete_fixture_run_report(self):
        run, gate = self.build_run_chain()
        # responsive-html closed with a reviewer listing every compare sheet
        write(run / "responsive-html" / "index.html", "<html></html>")
        write(run / "responsive-html" / "page.txt", "code-only")
        write(run / "responsive-html" / "compare" / "compare-1440-01.png", png_bytes())
        # Update Plan Item 16: close requires the parity evidence at
        # both widths and the drift table with status "pass".
        write(run / "responsive-html" / "compare" / "compare-390-01.png", png_bytes())
        write(run / "responsive-html" / "compare" / "compare-report.json",
              json.dumps({"tool": "compare_sheet.py",
                          "drift": {"status": "pass",
                                    "widths": {"1440": {"failures": [], "table": []},
                                               "390": {"failures": [], "table": []}}}}))
        put_receipt(run, "responsive-html", author="html-builder", reviewer="visual-reviewer")
        write_review(run, "responsive-html", "compare-1440-01",
                     {"brand_palette_fidelity": 9, "section_match": 8},
                     "html-builder-session", "visual-reviewer-session", self.env)
        write_review(run, "responsive-html", "compare-390-01",
                     {"brand_palette_fidelity": 9, "section_match": 8},
                     "html-builder-session", "visual-reviewer-session", self.env)
        gate("close", str(run), "responsive-html", expect=0)
        # ghl-install-test + publish-verify close as not_authorized (allowed stages)
        put_receipt(run, "ghl-install-test", status="not_authorized")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        # Assembly fix (S8): S5's contract entries for these stages
        # require their delivery artifacts even on a not_authorized
        # close; this fixture predates them.
        write(run / "ghl-install-test" / "funnel-completion.json", "{}")
        write(run / "ghl-install-test" / "evidence" / "desktop.png", png_bytes())
        write(run / "ghl-install-test" / "evidence" / "mobile.png", png_bytes())
        gate("close", str(run), "ghl-install-test", expect=0)
        put_receipt(run, "publish-verify", status="not_authorized")
        write(run / "publish-verify" / "receipts" / "note.md", "n/a")
        write(run / "publish-verify" / "fetch-record.json", "{}")
        gate("close", str(run), "publish-verify", expect=0)
        # Assembly fix (S8): the assembled system has a 14th stage
        # (automation-wiring, Item 31) that S1's fixture predates. This
        # intake declares no GHL workflows publish, so the stage
        # records not_applicable at close and the run can complete.
        gate("close", str(run), "automation-wiring", expect=0)
        # Assembly fix (S8): Item 34's deliverables contract postdates
        # this fixture too; cmd_report refuses while the deliverables
        # folder does not verify. Mirror S5's minimal valid folder.
        deliverables = {
            "page/index.html": "<html><body>page</body></html>",
            "assets/hero.png": png_bytes(),
            "copy/public-copy.md": "approved copy",
            "reports/REPORT.md": "run report",
            "reports/REPORT.json": "{}",
            "handoffs/automation-handoff.json": "{}",
            "receipts/intake.json": "{}",
            "provenance.json": json.dumps({
                "run_id": "run-test-1",
                "github": {"owner": "op", "repo": "pages", "branch": "main",
                           "commit_sha": "abc1234"},
                "vercel": {"project_id": "prj_1", "deployment_id": "dpl_1",
                           "url": "https://pages.example.com/"},
                "ghl": {"location_id": "loc_1", "funnel_id": "F-100"}}),
        }
        for rel, data in deliverables.items():
            write(run / "deliverables" / rel, data)
        write(run / "deliverables" / "manifest.json", json.dumps(
            {"run_id": "run-test-1",
             "files": sorted(set(deliverables) | {"manifest.json"})}))
        proc = run_gate("report", str(run), expect=0, env=self.env)
        report = (run / "REPORT.md").read_text()
        # Assembly ruling (S8): this fixture's intake is a test run, and
        # Item 6 rule 1 (S5, owner-ordered) says a test run's report
        # never reads as a production delivery, even when every stage
        # closed. S1's original "RUN COMPLETE" headline assertion
        # predates Item 6; the banner is the assembled semantics. The
        # completion evidence is the stage table asserted below.
        self.assertIn("TEST RUN, NOT A PRODUCTION DELIVERY", report)
        self.assertIn("PASS", report)
        self.assertNotIn("NOT RUN |", report)
        self.assertIn("ghl-install-test | NOT AUTHORIZED", report)
        self.assertIn("publish-verify | NOT AUTHORIZED", report)
        # Cost line summed from the image-generation-qc receipt (100.0 - 88.0)
        self.assertIn("kie: 12.00 credits", report)

    # ---- (e) real per-file validator commands substitute {sauce} and {brand}
    #
    # Regression for the 1.0.x substitution bug: resolve_brand_placeholder returned
    # the raw template on the __per_file__ path, so
    #   close image-inventory-prompts  ran  validate_prompt.py <file> {sauce}   (argparse rc=1)
    #   close image-generation-qc      ran  validate_image_grade.py <file> --brand {brand}
    # and the image stages could never close. The fixture contract (gate:noop)
    # masked this; these tests run the REAL contract with the REAL validator
    # commands on the two per-file stages.
    def build_image_stage_chain(self, run: Path, prompt_text: str, images=2):
        """Materialize a run folder with the two image stages ready to close,
        plus the real passing prompt fixture and real PNG bytes."""
        real_contract = ROOT / "references" / "stage-contract.json"
        env = {**os.environ, "STAGE_GATE_CONTRACT": str(real_contract)}
        # Dependency chain uses noop-closed stages built with the fixture contract.
        fixture_env = self.env
        # (rebuild helpers from build_run_chain's file layout without its noop closes
        # for the two image stages; those are closed by these tests on the real contract)
        write(run / "private" / "brand.json", json.dumps({
            "fonts": {"display": "Test", "body": "Test", "accent": "Test"},
            "logo": {"files": "test.png", "masthead_files": "test.png"},
            # Update plan Item 10 (record corrected on rebuild): this chain
            # writes intake.json itself and never routes this brand file
            # through write_intake, so the Item 10 intake check never sees
            # it. The old "test.png" value is corrected for consistency
            # only: it names no existing file, a form the skill's own
            # validator would reject if the file were ever consumed, so
            # the fixture carries a form-valid dummy (a bare 64-hex hash).
            "founder_photos": "f" * 64,
            # Assembly fix (S8): the real brand file carries a grade
            # object (thresholds null until Item 8 calibration);
            # validate_image_grade.py fails a brand file with no grade
            # object at all, by design.
            "grade": {"min_mean_saturation": None, "min_luma_std": None},
        }))
        write(run / "intake.json", json.dumps({
            "page_version": "standard", "brand_owner": "blackceo",
            "brand_file": "private/brand.json",
            "creative_direction": None, "image_cap": images, "test_run": True,
            # Assembly fix (S8): the Item 13 layout gate (S3 Request 2)
            # refuses the layout-stage closes below without the
            # owner-supplied reference files or a recorded waiver.
            "layout_waivers": [
                {"gate": "layout-references",
                 "reason": "test fixture: owner-supplied Item 13 reference files absent"}],
        }))
        write(run / "copy" / "internal-manuscript.md", "internal")
        write(run / "copy" / "public-copy.md", "public")
        write(run / "copy" / "copy-manifest.json", "{}")
        write(run / "font-action-plan" / "font-map.json", json.dumps({"fonts": {}}))
        write(run / "font-action-plan" / "action-plan.md", "plan")
        # Update Plan Item 11: the wireframe stages deliver the spec
        # image set (section slices, stitched full-page PNG, combined
        # PDF); the retired part-*.png exports no longer satisfy the
        # contract, so this fixture writes the new deliverables.
        write(run / "desktop-wireframe" / "section-01.png", "stub")
        write(run / "desktop-wireframe" / "wireframe-full.png", "stub")
        write(run / "desktop-wireframe" / "wireframe.pdf", "stub")
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": f"IMG-{i:03d}"} for i in range(1, images + 1)]}))
        # Assembly fix (S8): the delta contract's desktop-wireframe
        # review covers section-plan.json, mockup.html and bible.md
        # (Item 3); this legacy fixture predates the delta.
        write(run / "desktop-wireframe" / "section-plan.json", "{}")
        write(run / "desktop-wireframe" / "mockup.html", "<html></html>")
        write(run / "desktop-wireframe" / "bible.md", "# bible")
        write(run / "mobile-tablet" / "section-01.png", "stub")
        write(run / "mobile-tablet" / "wireframe-full.png", "stub")
        write(run / "mobile-tablet" / "wireframe.pdf", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        # Assembly fix (S8): the assembled contract also requires
        # mobile-tablet/section-plan.json (S3 Request 1 contract reads).
        write(run / "mobile-tablet" / "section-plan.json", "{}")
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        write(run / "visual-mockup" / "mockup.html", "<html></html>")
        write(run / "visual-mockup" / "desktop" / "part-01.png", "stub")
        write(run / "visual-mockup" / "mobile" / "part-01.png", "stub")
        for i in range(1, images + 1):
            write(run / "image-inventory-prompts" / f"IMG-{i:03d}.txt", prompt_text)
            write(run / "image-generation-qc" / f"Image-{i:03d}.png", png_variant(i))
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        # Assembly fix (S8): GCR-S2-4 (Item 10) requires a governing
        # style selection record before the prompts stage can close.
        write(run / "image-inventory-prompts" / "style-selection.json",
              json.dumps({"schema_version": 1, "selections": [
                  {"applies_to": "all", "source_library": "image-guide-sauce-only",
                   "style_id": "signature-grade", "branded_name": "Signature Grade"}]}))
        write(run / "image-generation-qc" / "image-qc.json", "{}")

        def gate(*args, expect=None, env=fixture_env):
            return run_gate(*args, expect=expect, env=env)

        gate("init", str(run), expect=0)
        # Assembly fix (S8): these legacy fixtures predated Review
        # Receipt v2 (S1's receipt() note flagged them as out of scope
        # while the module could not run standalone). They now close
        # the way build_run_chain does: no scores in receipts, one v2
        # review file per reviewed stage, from the reviewer's session.
        noop_stages = [
            ("intake", "intake-agent", "intake-reviewer", {"grounding": 9, "craft": 9}),
            ("copy", "copy-writer", "copy-reviewer", {"clarity": 9, "voice": 9}),
            ("font-action-plan", "font-planner", None, None),
            ("desktop-wireframe", "wireframe-lead", "wireframe-reviewer", {"layout": 9}),
            ("mobile-tablet", "mobile-lead", "mobile-reviewer", {"responsiveness": 9}),
            ("visual-mockup", "mock-builder", None, None),
        ]
        for stage, author, reviewer, criteria in noop_stages:
            extra = {"author_session_id": f"sess-author-{stage}",
                     "reviewer_session_id": f"sess-reviewer-{stage}"}
            put_receipt(run, stage, author=author, reviewer=reviewer or author,
                        extra=extra)
            if stage == "visual-mockup":
                # Per-artifact coverage (Item 3 delta): one review per
                # artifact, mirroring build_run_chain's review table.
                for item, item_criteria in [
                        ("desktop-part-01", {"composition_fidelity": 9}),
                        ("mobile-part-01", {"composition_fidelity": 9}),
                        ("page-visual-bible", {"brand_token_discipline": 9}),
                        ("mockup", {"composition_fidelity": 9})]:
                    write_review(run, stage, item, item_criteria,
                                 "mock-session", "mock-review-session",
                                 fixture_env)
            elif reviewer:
                write_review(run, stage, "stage", criteria,
                             f"sess-author-{stage}", f"sess-reviewer-{stage}",
                             {**fixture_env, "AGENT_ID": reviewer})
            gate("close", str(run), stage, expect=0)

        def gate_returned(*args, expect=None, env=None):
            """The gate the image-stage tests close with. Assembly fix
            (S8): the two image stages are itemized in the assembled
            contract (Item 20), so their stage closes fan in on
            item-level closes (S7's recorded composition finding: the
            tests close items first; the gate is not weakened), and the
            tests' legacy receipts carry v1 scores, which translate
            here into the stage's Review Receipt v2 file."""
            use_env = env if env is not None else fixture_env
            if len(args) >= 3 and args[0] == "close" and args[2] in (
                    "image-inventory-prompts", "image-generation-qc"):
                stage = args[2]
                receipt_path = run / "private" / "receipts" / f"{stage}.json"
                if receipt_path.is_file():
                    data = json.loads(receipt_path.read_text())
                    # The legacy receipts carry the review scores in the
                    # receipt; v2 moves them into the per-item review
                    # files (the image stages score per artifact).
                    had_scores = "scores" in data
                    scores = data.pop("scores", None) or {"fidelity": 9}
                    if had_scores:
                        receipt_path.write_text(json.dumps(data), encoding="utf-8")
                    sessions = {"image-inventory-prompts":
                                ("prompt-session", "prompt-review-session"),
                                "image-generation-qc":
                                ("image-session", "image-review-session")}[stage]
                    inventory = json.loads(
                        (run / "desktop-wireframe" / "image-inventory.json").read_text())
                    # Review files are keyed by artifact file stem
                    # (Image-001), item closes by inventory id (IMG-001);
                    # the gate maps between them by numeric suffix.
                    stems = [Path(vf).stem for vf in (data.get("validator_files") or [])]
                    for idx, entry in enumerate(inventory.get("images", [])):
                        item = entry["id"]
                        stem = stems[idx] if idx < len(stems) else item
                        write_review(run, stage, stem, scores,
                                     sessions[0], sessions[1], use_env)
                        run_gate("close-item", str(run), stage, item, env=use_env)
            return gate(*args, expect=expect, env=use_env)

        return env, gate_returned

    def test_e_close_image_inventory_prompts_real_validator(self):
        # Passing fixture prompt contains the exact Signature Grade Block, so
        # --sauce-only (from the SECRET_SAUCE_ONLY bible) must pass when {sauce}
        # is actually substituted — and fail when it is not.
        prompt_text = fitted_good_prompt()
        run = self.td / "run-real"
        env, gate = self.build_image_stage_chain(run, prompt_text)
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": [
                        "image-inventory-prompts/IMG-001.txt",
                        "image-inventory-prompts/IMG-002.txt",
                    ]})
        gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["image-inventory-prompts"]["status"], "closed")

    def test_f_close_image_generation_qc_real_validator(self):
        run = self.td / "run-qc"
        prompt_text = fitted_good_prompt()
        env, gate = self.build_image_stage_chain(run, prompt_text)
        # Close the prompt stage first on the real contract (dependency chain).
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": [
                        "image-inventory-prompts/IMG-001.txt",
                        "image-inventory-prompts/IMG-002.txt",
                    ]})
        gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
        kie_receipts(run, kie_transport(KIE_FILES))
        put_receipt(run, "image-generation-qc", author="image-gen",
                    reviewer="image-reviewer", scores={"grade": 9},
                    extra={"cost": dict(KIE_COST),
                           "transport": kie_transport(KIE_FILES),
                           "validator_files": [
                               "image-generation-qc/Image-001.png",
                               "image-generation-qc/Image-002.png",
                           ]})
        gate("close", str(run), "image-generation-qc", expect=0, env=env)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["image-generation-qc"]["status"], "closed")

    # ---- (j) GU-016: a run path containing a space must not tear the argv
    def test_j_per_file_validator_survives_a_run_path_with_spaces(self):
        # The per-file validator command used to be substituted into a string
        # and then shlex.split, so every space in the run folder path became an
        # argument boundary and the real validator (validate_prompt.py) rejected
        # the torn path. Stage the whole chain under a spaced run path and close
        # the prompts stage on the REAL contract: the validator must receive the
        # path as ONE argument, and the stage must close.
        run = self.td / "run with spaces"
        env, gate = self.build_image_stage_chain(run, fitted_good_prompt())
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": [
                        "image-inventory-prompts/IMG-001.txt",
                        "image-inventory-prompts/IMG-002.txt",
                    ]})
        proc = gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("validator exit", combined)
        self.assertNotIn("unrecognized arguments", combined)
        state = json.loads((run / "private" / "state.json").read_text())
        self.assertEqual(state["stages"]["image-inventory-prompts"]["status"], "closed")

    def test_g_missing_sauce_block_fails_close_with_real_validator(self):
        # Negative control: a prompt MISSING the Signature Grade Block must fail
        # close under --sauce-only, proving {sauce} really reaches the validator.
        prompt_text = fitted_good_prompt()
        grade_block = (ROOT / "assets" / "brand" / "signature-grade-block.txt").read_text().rstrip("\n")
        run = self.td / "run-nograde"
        env, gate = self.build_image_stage_chain(run, prompt_text.replace(grade_block, ""))
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": [
                        "image-inventory-prompts/IMG-001.txt",
                        "image-inventory-prompts/IMG-002.txt",
                    ]})
        proc = run_gate("close", str(run), "image-inventory-prompts", expect=1, env=env)
        combined = proc.stdout + proc.stderr
        self.assertIn("Missing Signature Grade Block", combined)

    # ---- (i) Skill 74 transport gate on image-generation-qc (owner order: one approved KIE path)
    def close_image_qc(self, no_files=False, agnes=False, **extra):
        run = self.td / "run-transport"
        env, gate = self.build_image_stage_chain(
            run, fitted_good_prompt())
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": ["image-inventory-prompts/IMG-001.txt",
                                               "image-inventory-prompts/IMG-002.txt"]})
        gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
        base = {"cost": dict(KIE_COST), "validator_files": KIE_FILES}
        base.update(extra)
        if not no_files and isinstance(extra.get("transport"), dict):
            kie_receipts(run, extra["transport"])
        if agnes:
            subprocess.run([PY, str(ROOT / "scripts" / "write_intake.py"), str(run), "--page-version", "standard",
                            "--brand-owner", "blackceo", "--brand-file", "private/brand.json",
                            "--image-cap", "2", "--image-engine", "agnes", "--test-run"], check=True)
        put_receipt(run, "image-generation-qc", author="image-gen", reviewer="image-reviewer",
                    scores={"grade": 9}, extra=base)
        # Assembly fix (S8): close through the chain's returned gate so
        # the v2 translation and item-level closes run, exactly as the
        # success-path tests do; the raw run_gate close predates both.
        return gate("close", str(run), "image-generation-qc", env=env)

    def test_i1_no_transport_block_is_refused(self):
        proc = self.close_image_qc()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("missing transport block", proc.stdout + proc.stderr)

    def test_i2_hand_rolled_route_is_refused(self):
        proc = self.close_image_qc(transport=kie_transport(KIE_FILES, skill="curl-createTask"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not an approved route", proc.stdout + proc.stderr)

    def test_i3_shadow_mode_is_refused(self):
        proc = self.close_image_qc(transport=kie_transport(KIE_FILES, mode="shadow"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must be 'active'", proc.stdout + proc.stderr)

    def test_i4_task_missing_for_a_file_is_refused(self):
        proc = self.close_image_qc(transport=kie_transport(KIE_FILES[:1]))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("transport.tasks cover", proc.stdout + proc.stderr)

    def test_i5_placeholder_task_id_and_failed_preflight_refused(self):
        t = kie_transport(KIE_FILES)
        t["tasks"][0]["task_id"] = "placeholder"
        t["tasks"][1]["preflight_ok"] = False
        proc = self.close_image_qc(transport=t)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing or a placeholder", out)
        self.assertIn("preflight_ok must be true", out)

    def test_i6_n43_ratio_rule(self):
        t = kie_transport(KIE_FILES)
        t["tasks"][0].update(requested_ratio="4:5", generated_ratio="4:5")   # default route must send 3:4
        t["tasks"][1].update(requested_ratio="3:1", generated_ratio="3:1")   # legacy-only ratio on the default source
        proc = self.close_image_qc(transport=t)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 1)
        self.assertIn("N43 ratio rule violated: requested 4:5, generated 4:5, expected 3:4", out)
        self.assertIn("N43 sends 3:1 to the legacy route only", out)

    def test_i7_n43_ratio_rule_passes_when_followed(self):
        t = kie_transport(KIE_FILES)
        t["tasks"][0].update(requested_ratio="4:5", generated_ratio="3:4")
        t["tasks"][1].update(requested_ratio="3:1", generated_ratio="3:1", model_source="legacy-ratio-route")
        proc = self.close_image_qc(transport=t)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_i8_cost_provider_must_match_route(self):
        proc = self.close_image_qc(transport=kie_transport(KIE_FILES),
                                   cost={"provider": "agnes", "credits_before": 1, "credits_after": 0})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cost.provider must be 'kie'", proc.stdout + proc.stderr)

    def test_i9_agnes_route_when_selected(self):
        t = {"skill": "63-agnes-image", "policy": "63-agnes-image",
             "tasks": [{"file": f} for f in KIE_FILES]}
        proc = self.close_image_qc(agnes=True, transport=t,
                                   cost={"provider": "agnes", "credits_before": 5, "credits_after": 3})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_i10_agnes_without_client_selection_refused(self):
        t = {"skill": "63-agnes-image", "policy": "63-agnes-image",
             "tasks": [{"file": f} for f in KIE_FILES]}
        proc = self.close_image_qc(transport=t, cost={"provider": "agnes", "credits_before": 5, "credits_after": 3})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("client must have selected Agnes", proc.stdout + proc.stderr)

    def test_i15_intake_writer_records_the_engine_choice(self):
        d = self.td / "intake-run"
        d.mkdir()
        w = [PY, str(ROOT / "scripts" / "write_intake.py"), str(d), "--page-version", "long-form",
             "--brand-owner", "blackceo", "--image-cap", "3"]
        subprocess.run(w, check=True, capture_output=True)
        self.assertEqual(json.loads((d / "intake.json").read_text())["image_engine"], "kie")
        self.assertFalse(stage_gate._agnes_selected(d))
        subprocess.run(w + ["--image-engine", "agnes"], check=True, capture_output=True)
        self.assertEqual(json.loads((d / "intake.json").read_text())["image_engine"], "agnes")
        self.assertTrue(stage_gate._agnes_selected(d))
        bad = subprocess.run(w + ["--image-engine", "dalle"], capture_output=True)
        self.assertNotEqual(bad.returncode, 0)

    def test_i16_intake_stage_requires_image_engine(self):
        env = {**os.environ, "STAGE_GATE_CONTRACT": str(ROOT / "references" / "stage-contract.json")}
        run = self.td / "intake-gate"
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "T", "body": "T", "accent": "T"},
              "logo": {"files": "t.png", "masthead_files": "t.png"},
              # Update plan Item 10: this fixture's own write_intake
              # invocation refuses the old "t.png" value (a founder_photos
              # entry naming no existing file; the independent review's
              # revert probe exits 2 on it), so the fixture carries a
              # form-valid dummy hash instead.
              "founder_photos": "f" * 64}))
        write(run / "intake.json", json.dumps({"page_version": "standard", "brand_file": "private/brand.json"}))
        run_gate("init", str(run), expect=0, env=env)
        put_receipt(run, "intake", author="intake-agent")
        proc = run_gate("close", str(run), "intake", expect=1, env=env)
        self.assertIn("image_engine", proc.stdout + proc.stderr)
        subprocess.run([PY, str(ROOT / "scripts" / "write_intake.py"), str(run), "--page-version", "standard",
                        "--brand-owner", "blackceo", "--brand-file", "private/brand.json", "--image-cap", "1"],
                       check=True, capture_output=True)
        run_gate("close", str(run), "intake", expect=0, env=env)

    def test_i11_task_id_without_result_file_refused(self):
        proc = self.close_image_qc(no_files=True, transport=kie_transport(KIE_FILES))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no readable receipts/kie74", proc.stdout + proc.stderr)

    def test_i12_duplicate_task_id_refused(self):
        t = kie_transport(KIE_FILES)
        t["tasks"][1]["task_id"] = t["tasks"][0]["task_id"]
        proc = self.close_image_qc(transport=t)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("is used for both", proc.stdout + proc.stderr)

    def test_i13_two_result_files_with_one_task_id_refused(self):
        t = kie_transport(KIE_FILES)
        run = self.td / "run-transport"
        proc_run = None
        orig = kie_receipts

        def dup(run_, transport):
            orig(run_, transport)
            write(run_ / "receipts" / "kie74" / "copy.json", (run_ / "receipts" / "kie74" / "task-001.json").read_text())
        globals()["kie_receipts"] = dup
        try:
            proc = self.close_image_qc(transport=t)
        finally:
            globals()["kie_receipts"] = orig
        self.assertEqual(proc.returncode, 1)
        self.assertIn("carry the same task_id", proc.stdout + proc.stderr)

    def test_i14_explicit_request_needs_evidence(self):
        t = kie_transport(KIE_FILES)
        t["tasks"][0].update(requested_ratio="4:5", generated_ratio="4:5", model_source="explicit-request")
        proc = self.close_image_qc(transport=t)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("needs evidence", proc.stdout + proc.stderr)
        for weak in ("pin", "placeholder", "short one", "xxxxxxxxxxxx", "twowordsonly here ok"[:12]):
            t["tasks"][0]["evidence"] = weak
            self.assertEqual(self.close_image_qc(transport=t).returncode, 1, weak)
        t["tasks"][0]["evidence"] = "client asked for the legacy model by name in the intake"
        proc = self.close_image_qc(transport=t)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_h_empty_validator_command_clean_failure(self):
        # Hardening: run_one_validator("") must emit a clean failure line, not an
        # IndexError traceback.
        line = stage_gate.run_one_validator("", self.td)
        self.assertIsNotNone(line)
        self.assertIn("empty command", line)

    def build_run_chain(self):
        """Close every stage up to final-mockups on the fixture contract."""
        run = self.td / "run"
        # Fixture brand: satisfies gate:must_supply without the real Trevor-supplied facts.
        write(run / "private" / "brand.json", json.dumps({
            "fonts": {"display": "Test", "body": "Test", "accent": "Test"},
            "logo": {"files": "test.png", "masthead_files": "test.png"},
            # Record repair (post-review observation): same latent-trap
            # class as the Item 10 fixture corrections. This brand file
            # also never reaches write_intake or founder_allowed_hashes in
            # tests (test_a/test_d), so this change is consistency only:
            # the fixture carries a form-valid dummy instead of a
            # nonexistent path the validator would reject if consumed.
            "founder_photos": "f" * 64,
        }))
        write(run / "intake.json", json.dumps({
            "page_version": "standard", "brand_owner": "blackceo",
            "brand_file": "private/brand.json",
            "creative_direction": None, "image_cap": 2, "test_run": True,
            # S8 assembly: the Item 13 layout gate fires at wireframe and
            # mockup close in gate code (not via contract validators), and
            # the owner-supplied reference files are absent from the test
            # environment; the fixture records the waiver, as a real run
            # whose owner waived them would.
            "layout_waivers": [{"gate": "layout-references",
                                "reason": "test fixture: layout reference files are "
                                          "owner-supplied (Item 13) and absent here"}],
        }))
        write(run / "copy" / "internal-manuscript.md", "internal")
        write(run / "copy" / "public-copy.md", "public")
        write(run / "copy" / "copy-manifest.json", "{}")
        write(run / "font-action-plan" / "font-map.json", json.dumps({"fonts": {}}))
        write(run / "font-action-plan" / "action-plan.md", "plan")
        # Update Plan Item 11: the wireframe stages deliver the spec
        # image set (one section slice per planned section, stitched
        # full-page PNG, combined PDF); the retired part-*.png exports
        # no longer satisfy the contract.
        for i in (1, 2):
            write(run / "desktop-wireframe" / f"section-{i:02d}.png", "stub")
        write(run / "desktop-wireframe" / "wireframe-full.png", "stub")
        write(run / "desktop-wireframe" / "wireframe.pdf", "stub")
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": "IMG-001"}, {"id": "IMG-002"}]}))
        write(run / "desktop-wireframe" / "section-plan.json", json.dumps([
            {"section_id": "hero", "copy_block_ids": ["hero-copy"],
             "image_slot_ids": ["IMG-001"], "reference_traits": []},
            {"section_id": "offer", "copy_block_ids": ["offer-copy"],
             "image_slot_ids": ["IMG-002"], "reference_traits": []},
        ]))
        write(run / "mobile-tablet" / "section-01.png", "stub")
        write(run / "mobile-tablet" / "section-02.png", "stub")
        write(run / "mobile-tablet" / "wireframe-full.png", "stub")
        write(run / "mobile-tablet" / "wireframe.pdf", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(run / "mobile-tablet" / "section-plan.json", json.dumps([
            {"section_id": "hero", "copy_block_ids": ["hero-copy"],
             "image_slot_ids": ["IMG-001"], "reference_traits": []},
            {"section_id": "offer", "copy_block_ids": ["offer-copy"],
             "image_slot_ids": ["IMG-002"], "reference_traits": []},
        ]))
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        write(run / "visual-mockup" / "mockup.html", "<html></html>")
        write(run / "visual-mockup" / "desktop" / "part-01.png", "stub")
        write(run / "visual-mockup" / "mobile" / "part-01.png", "stub")
        write(run / "image-inventory-prompts" / "IMG-001.txt", "prompt")
        write(run / "image-inventory-prompts" / "IMG-002.txt", "prompt")
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        # Assembly fix (S8): GCR-S2-4 (Item 10) requires a governing
        # style selection record before the prompts stage can close.
        write(run / "image-inventory-prompts" / "style-selection.json",
              json.dumps({"schema_version": 1, "selections": [
                  {"applies_to": "all", "source_library": "image-guide-sauce-only",
                   "style_id": "signature-grade", "branded_name": "Signature Grade"}]}))
        write(run / "image-generation-qc" / "Image-001.png", "stub")
        write(run / "image-generation-qc" / "Image-002.png", "stub")
        write(run / "image-generation-qc" / "image-qc.json", "{}")
        write(run / "image-map-upload" / "image-map.json", "{}")
        write(run / "image-map-upload" / "image-map.md", "map")
        write(run / "final-mockups" / "mockup.html", "<html></html>")
        write(run / "final-mockups" / "desktop" / "part-01.png", "stub")
        write(run / "final-mockups" / "mobile" / "part-01.png", "stub")
        # Item 12: the hybrid board is a closing deliverable of the stage.
        write(run / "final-mockups" / "hybrid-board.png", "stub")
        write(run / "final-mockups" / "hybrid-board.json", "{}")
        # Update Plan Item 15: the final-mockups stage carries its
        # section generation record; every slot traces to its generated
        # file (written above under image-generation-qc/).
        write(run / "final-mockups" / "generation-record.json", json.dumps(
            {"stage": "final-mockups", "sections": [
                {"section_id": "hero", "slots": [
                    {"slot_id": "IMG-001", "source": "generated",
                     "file": "image-generation-qc/Image-001.png"}]},
                {"section_id": "offer", "slots": [
                    {"slot_id": "IMG-002", "source": "generated",
                     "file": "image-generation-qc/Image-002.png"}]}]}))

        def gate(*args, expect=None):
            return run_gate(*args, expect=expect, env=self.env)

        gate("init", str(run), expect=0)
        authors = {
            "intake": "intake-agent", "copy": "copy-writer",
            "font-action-plan": "font-planner", "desktop-wireframe": "wireframe-lead",
            "mobile-tablet": "mobile-lead", "visual-mockup": "mock-builder",
            "image-inventory-prompts": "prompt-writer",
            "image-generation-qc": "image-gen",
            "image-map-upload": "map-builder", "final-mockups": "final-builder",
        }
        reviewers = {
            "copy": "copy-reviewer", "desktop-wireframe": "wireframe-reviewer",
            "mobile-tablet": "mobile-reviewer", "image-inventory-prompts": "prompt-reviewer",
            "image-generation-qc": "image-reviewer",
        }
        # Review Receipt v2: every review-required stage gets one review
        # file per required item, written by the real writer from a
        # reviewer session distinct from the author session, before close.
        review_items = {
            "copy": [("stage", {"clarity": 9})],
            "desktop-wireframe": [("stage", {"layout": 9})],
            "mobile-tablet": [("stage", {"reflow": 8})],
            "visual-mockup": [("desktop-part-01", {"composition_fidelity": 9}),
                              ("mobile-part-01", {"composition_fidelity": 9}),
                              ("page-visual-bible", {"brand_token_discipline": 9}),
                              ("mockup", {"composition_fidelity": 9})],
            "image-inventory-prompts": [("IMG-001", {"fidelity": 9}),
                                        ("IMG-002", {"fidelity": 9})],
            "image-generation-qc": [("Image-001", {"grade": 9}),
                                    ("Image-002", {"grade": 9})],
            "final-mockups": [("desktop-part-01", {"composition_fidelity": 9}),
                              ("mobile-part-01", {"composition_fidelity": 9}),
                              ("hybrid-board", {"composition_fidelity": 9}),
                              ("mockup", {"composition_fidelity": 9})],
        }
        review_sessions = {
            "copy": ("copy-session", "copy-review-session"),
            "desktop-wireframe": ("wireframe-session", "wireframe-review-session"),
            "mobile-tablet": ("mobile-session", "mobile-review-session"),
            "visual-mockup": ("mock-session", "mock-review-session"),
            "image-inventory-prompts": ("prompt-session", "prompt-review-session"),
            "image-generation-qc": ("image-session", "image-review-session"),
            "final-mockups": ("final-session", "final-review-session"),
        }
        kie_receipts(run, kie_transport(KIE_FILES))
        costs = {"image-generation-qc": {"provider": "kie", "credits_before": 100.0,
                                          "credits_after": 88.0,
                                          "transport": kie_transport(KIE_FILES)}}
        for stage in authors:
            put_receipt(run, stage, author=authors[stage],
                        reviewer=reviewers.get(stage, authors[stage]),
                        extra=({"cost": {k: v for k, v in costs[stage].items() if k != "transport"},
                                "transport": costs[stage]["transport"]} if stage in costs else None))
            for item, criteria in review_items.get(stage, []):
                author_session, reviewer_session = review_sessions[stage]
                write_review(run, stage, item, criteria,
                             author_session, reviewer_session, self.env)
            # S8 assembly (S7's recorded composition finding): with Item
            # 20's item gates in force, an itemized stage's close refuses
            # until every item is closed at item level first (fan-in).
            # The gate is unchanged; the chain closes the items first,
            # as a real run under the swarm runner does.
            if stage in ("image-inventory-prompts", "image-generation-qc"):
                for item_id in ("IMG-001", "IMG-002"):
                    gate("close-item", str(run), stage, item_id, expect=0)
            gate("close", str(run), stage, expect=0)
        return run, gate


if __name__ == "__main__":
    unittest.main(verbosity=2)
