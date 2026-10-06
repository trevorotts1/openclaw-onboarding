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
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))
import stage_gate  # noqa: E402  (module import loads the real contract)


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
        "scores": scores or {},
        "notes": "fixture",
    }
    if extra:
        r.update(extra)
    return r


def put_receipt(run: Path, stage, **kw):
    write(run / "private" / "receipts" / f"{stage}.json", json.dumps(receipt(stage, **kw)))


def kie_transport(files, **over):
    """A valid Skill 74 transport block for the given generated files (all default-route 16:9)."""
    tasks = [{"file": f, "task_id": f"task-{i:03d}", "model_id": "model-from-skill-66",
              "model_source": "latest-family", "requested_ratio": "16:9", "generated_ratio": "16:9",
              "preflight_ok": True, "budget_exit": 0} for i, f in enumerate(files, 1)]
    t = {"skill": "74-kie-live-adapter", "policy": "66-kie-image", "mode": "active", "tasks": tasks}
    t.update(over)
    return t


KIE_COST = {"provider": "kie", "credits_before": 100.0, "credits_after": 88.0}
KIE_FILES = ["image-generation-qc/Image-001.png", "image-generation-qc/Image-002.png"]


def png_bytes():
    # 1x1 transparent PNG, byte-identical every call for deterministic hashing.
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


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

    # ---- (b) close with reviewer_agent == author_agent fails
    def test_b_close_reviewer_equals_author_fails(self):
        run = self.td / "run"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "Test"}}))
        run_gate("init", str(run), expect=0, env=self.env)
        put_receipt(run, "copy", author="builder-agent", reviewer="builder-agent")
        write(run / "copy" / "internal-manuscript.md", "x")
        write(run / "copy" / "public-copy.md", "x")
        write(run / "copy" / "copy-manifest.json", "{}")
        proc = run_gate("close", str(run), "copy", expect=1, env=self.env)
        combined = proc.stdout + proc.stderr
        self.assertIn("reviewer_agent equals author_agent", combined)

    # ---- (b2) close with an independent reviewer passes
    def test_b2_close_independent_reviewer_passes(self):
        run = self.td / "run"
        write(run / "intake.json", "{}")
        write(run / "private" / "brand.json", json.dumps({"fonts": {"display": "Test"}}))
        run_gate("init", str(run), expect=0, env=self.env)
        put_receipt(run, "copy", author="builder-agent", reviewer="reviewer-agent",
                    scores={"clarity": 9})
        write(run / "copy" / "internal-manuscript.md", "x")
        write(run / "copy" / "public-copy.md", "x")
        write(run / "copy" / "copy-manifest.json", "{}")
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
        put_receipt(run, "responsive-html", author="html-builder", reviewer="visual-reviewer",
                    extra={
                        "scores": {"brand_palette_fidelity": 9, "section_match": 8},
                        "review_files": {"responsive-html/compare/compare-1440-01.png": {"score": 9}},
                    })
        gate("close", str(run), "responsive-html", expect=0)
        # ghl-install-test + publish-verify close as not_authorized (allowed stages)
        put_receipt(run, "ghl-install-test", status="not_authorized")
        write(run / "ghl-install-test" / "install-steps.md", "steps")
        gate("close", str(run), "ghl-install-test", expect=0)
        put_receipt(run, "publish-verify", status="not_authorized")
        write(run / "publish-verify" / "receipts" / "note.md", "n/a")
        gate("close", str(run), "publish-verify", expect=0)
        proc = run_gate("report", str(run), expect=0, env=self.env)
        report = (run / "REPORT.md").read_text()
        self.assertIn("RUN COMPLETE", report)
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
            "founder_photos": "test.png",
        }))
        write(run / "intake.json", json.dumps({
            "page_version": "standard", "brand_owner": "blackceo",
            "brand_file": "private/brand.json",
            "creative_direction": None, "image_cap": images, "test_run": True,
        }))
        write(run / "copy" / "internal-manuscript.md", "internal")
        write(run / "copy" / "public-copy.md", "public")
        write(run / "copy" / "copy-manifest.json", "{}")
        write(run / "font-action-plan" / "font-map.json", json.dumps({"fonts": {}}))
        write(run / "font-action-plan" / "action-plan.md", "plan")
        for i in range(1, images + 1):
            write(run / "desktop-wireframe" / f"part-{i:02d}.png", "stub")
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": f"IMG-{i:03d}"} for i in range(1, images + 1)]}))
        write(run / "mobile-tablet" / "part-01.png", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        write(run / "visual-mockup" / "mockup.html", "<html></html>")
        write(run / "visual-mockup" / "desktop" / "part-01.png", "stub")
        write(run / "visual-mockup" / "mobile" / "part-01.png", "stub")
        for i in range(1, images + 1):
            write(run / "image-inventory-prompts" / f"IMG-{i:03d}.txt", prompt_text)
            write(run / "image-generation-qc" / f"Image-{i:03d}.png", png_bytes())
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        write(run / "image-generation-qc" / "image-qc.json", "{}")

        def gate(*args, expect=None, env=fixture_env):
            return run_gate(*args, expect=expect, env=env)

        gate("init", str(run), expect=0)
        noop_stages = [
            ("intake", "intake-agent", None, None, None),
            ("copy", "copy-writer", "copy-reviewer", {"clarity": 9}, None),
            ("font-action-plan", "font-planner", None, None, None),
            ("desktop-wireframe", "wireframe-lead", "wireframe-reviewer", {"layout": 9}, None),
            ("mobile-tablet", "mobile-lead", "mobile-reviewer", {"reflow": 8}, None),
            ("visual-mockup", "mock-builder", None, None, None),
        ]
        for stage, author, reviewer, scores, extra in noop_stages:
            put_receipt(run, stage, author=author, reviewer=reviewer or author,
                        scores=scores or {}, extra=extra)
            gate("close", str(run), stage, expect=0)
        return env, gate

    def test_e_close_image_inventory_prompts_real_validator(self):
        # Passing fixture prompt contains the exact Signature Grade Block, so
        # --sauce-only (from the SECRET_SAUCE_ONLY bible) must pass when {sauce}
        # is actually substituted — and fail when it is not.
        prompt_text = (ROOT / "tests" / "fixtures" / "prompt_good.txt").read_text(encoding="utf-8")
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
        prompt_text = (ROOT / "tests" / "fixtures" / "prompt_good.txt").read_text(encoding="utf-8")
        env, gate = self.build_image_stage_chain(run, prompt_text)
        # Close the prompt stage first on the real contract (dependency chain).
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": [
                        "image-inventory-prompts/IMG-001.txt",
                        "image-inventory-prompts/IMG-002.txt",
                    ]})
        gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
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

    def test_g_missing_sauce_block_fails_close_with_real_validator(self):
        # Negative control: a prompt MISSING the Signature Grade Block must fail
        # close under --sauce-only, proving {sauce} really reaches the validator.
        prompt_text = (ROOT / "tests" / "fixtures" / "prompt_good.txt").read_text(encoding="utf-8")
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
    def close_image_qc(self, **extra):
        run = self.td / "run-transport"
        env, gate = self.build_image_stage_chain(
            run, (ROOT / "tests" / "fixtures" / "prompt_good.txt").read_text(encoding="utf-8"))
        put_receipt(run, "image-inventory-prompts", author="prompt-writer",
                    reviewer="prompt-reviewer", scores={"fidelity": 9},
                    extra={"validator_files": ["image-inventory-prompts/IMG-001.txt",
                                               "image-inventory-prompts/IMG-002.txt"]})
        gate("close", str(run), "image-inventory-prompts", expect=0, env=env)
        base = {"cost": dict(KIE_COST), "validator_files": KIE_FILES}
        base.update(extra)
        put_receipt(run, "image-generation-qc", author="image-gen", reviewer="image-reviewer",
                    scores={"grade": 9}, extra=base)
        return run_gate("close", str(run), "image-generation-qc", env=env)

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
        proc = self.close_image_qc(transport=t,
                                   cost={"provider": "agnes", "credits_before": 5, "credits_after": 3})
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
            "founder_photos": "test.png",
        }))
        write(run / "intake.json", json.dumps({
            "page_version": "standard", "brand_owner": "blackceo",
            "brand_file": "private/brand.json",
            "creative_direction": None, "image_cap": 2, "test_run": True,
        }))
        write(run / "copy" / "internal-manuscript.md", "internal")
        write(run / "copy" / "public-copy.md", "public")
        write(run / "copy" / "copy-manifest.json", "{}")
        write(run / "font-action-plan" / "font-map.json", json.dumps({"fonts": {}}))
        write(run / "font-action-plan" / "action-plan.md", "plan")
        for i in (1, 2):
            write(run / "desktop-wireframe" / f"part-{i:02d}.png", "stub")
        write(run / "desktop-wireframe" / "image-inventory.json",
              json.dumps({"images": [{"id": "IMG-001"}, {"id": "IMG-002"}]}))
        write(run / "mobile-tablet" / "part-01.png", "stub")
        write(run / "mobile-tablet" / "tablet-rules.md", "rules")
        write(run / "visual-mockup" / "page-visual-bible.json",
              json.dumps({"selection_mode": "SECRET_SAUCE_ONLY"}))
        write(run / "visual-mockup" / "mockup.html", "<html></html>")
        write(run / "visual-mockup" / "desktop" / "part-01.png", "stub")
        write(run / "visual-mockup" / "mobile" / "part-01.png", "stub")
        write(run / "image-inventory-prompts" / "IMG-001.txt", "prompt")
        write(run / "image-inventory-prompts" / "IMG-002.txt", "prompt")
        write(run / "image-inventory-prompts" / "prompt-manifest.json", "{}")
        write(run / "image-generation-qc" / "Image-001.png", "stub")
        write(run / "image-generation-qc" / "Image-002.png", "stub")
        write(run / "image-generation-qc" / "image-qc.json", "{}")
        write(run / "image-map-upload" / "image-map.json", "{}")
        write(run / "image-map-upload" / "image-map.md", "map")
        write(run / "final-mockups" / "mockup.html", "<html></html>")
        write(run / "final-mockups" / "desktop" / "part-01.png", "stub")
        write(run / "final-mockups" / "mobile" / "part-01.png", "stub")

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
        scores = {
            "copy": {"clarity": 9},
            "desktop-wireframe": {"layout": 9},
            "mobile-tablet": {"reflow": 8},
            "image-inventory-prompts": {"fidelity": 9},
            "image-generation-qc": {"grade": 9},
        }
        costs = {"image-generation-qc": {"provider": "kie", "credits_before": 100.0,
                                          "credits_after": 88.0,
                                          "transport": kie_transport(KIE_FILES)}}
        for stage in authors:
            put_receipt(run, stage, author=authors[stage],
                        reviewer=reviewers.get(stage, authors[stage]),
                        scores=scores.get(stage, {}),
                        extra=({"cost": {k: v for k, v in costs[stage].items() if k != "transport"},
                                "transport": costs[stage]["transport"]} if stage in costs else None))
            gate("close", str(run), stage, expect=0)
        return run, gate


if __name__ == "__main__":
    unittest.main(verbosity=2)
