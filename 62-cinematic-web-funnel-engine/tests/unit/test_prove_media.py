#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_media.py — unit + break-it test suite for build unit U11
(scripts/prove_media.py): the P6-ANCHOR / P7-STILLS phase gates.

Builds minimal, HAND-CRAFTED, disk-backed fixture artifacts directly via
state_engine.ProjectState.save() (mirrors prove_budget.py's own
_self_test_scene_plan() precedent) rather than driving generate_images.py's
full paid-call pipeline — a gate test proves the gate's EVALUATION logic;
generate_images.py's own test suite (test_generate_images.py) already covers
the producer pipeline end-to-end against mocked Kie fixtures.

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import datetime
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (_SKILL_DIR, _SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import prove_media as pm  # noqa: E402
import state_engine as se  # noqa: E402

PY = sys.executable or "python3"
SCRIPT = _SCRIPTS_DIR / "prove_media.py"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_file(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _asset(local_path: Path, content: bytes, **overrides: Any) -> Dict[str, Any]:
    base = {
        "model_id": "kie-gpt-image-2-image-to-image",
        "provider_task_id": "fixture-task",
        "local_path": str(local_path),
        "hash_sha256": _write_file(local_path, content),
        "prompt": "fixture prompt",
        "aspect_ratio": "16:9",
        "resolution": "2K",
        "generated_at": _now(),
    }
    base.update(overrides)
    return base


def _empty_style_contract() -> Dict[str, Any]:
    return {
        "visual_world": "x", "realism_level": "photoreal", "palette": [], "material_language": "x",
        "lighting_logic": "x", "lens_family": "x", "composition_system": "x",
        "prohibited_styles": [], "negative_prompt": "",
    }


class ProveMediaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-media-tests-"))
        self.state = se.ProjectState(self.tmp)
        self.state.create_project(
            project_id="proj-prove-media-tests", client_slug="acme", project_slug="launch",
            deliverable_type="cinematic-landing-page", budget_cap_usd=10.0,
        )
        self.media_dir = self.tmp / "media"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_locked_anchor(self, *, approved_by="tester", record_manifest_approval=True):
        now = _now()
        candidate = _asset(self.media_dir / "anchor" / "concept-01.png", b"CONCEPT-01")
        candidate["candidate_id"] = "concept-01"
        final_anchor = _asset(self.media_dir / "anchor" / "final-anchor.png", b"FINAL-ANCHOR")
        anchor = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests", "status": "anchor_approved",
            "style_contract": _empty_style_contract(), "concept_candidates": [candidate],
            "approved_candidate_id": "concept-01", "final_anchor": final_anchor,
            "approved_by": approved_by, "approved_at": now, "created_at": now, "updated_at": now,
        }
        self.state.save("anchor-approval", anchor)
        if record_manifest_approval:
            manifest = self.state.load("project-manifest")
            manifest["approvals"].append(
                {"kind": "anchor_final", "approved_by": approved_by, "approved_at": now, "hash_sha256": final_anchor["hash_sha256"]}
            )
            self.state.save("project-manifest", manifest)
        return anchor

    def _write_scene_plan(self, scene_ids=("scene-01-hero",)):
        now = _now()
        scenes = []
        for sid in scene_ids:
            scenes.append({
                "scene_id": sid, "page_section": "hero", "narrative_purpose": "x", "conversion_purpose": "x",
                "visual_motif": "x", "anchor_inputs": [],
                "camera": {"start_state": "wide", "end_state": "medium", "motion_direction": "push-in", "motion_speed": "slow"},
                "duration_seconds": 8, "crop_rules": {"desktop": "16:9 full-bleed", "mobile": "9:16 crop-safe"},
                "copy_overlay_timing": [], "cta_relationship": "none", "generation_model": "kie-bytedance-seedance-1.5-pro",
                "generation_tier": "final-motion", "connector_required": False, "expected_generation_count": 1,
                "estimated_cost_usd": 0.4, "approval_status": "proposed", "anchor_asset_hash": None,
            })
        scene_plan = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests",
            "architecture": "continuous-forward-journey", "scenes": scenes, "created_at": now, "updated_at": now,
        }
        self.state.save("scene-plan", scene_plan)
        return scene_plan

    def _write_full_ledger(self, scene_ids=("scene-01-hero",), *, approved=True):
        now = _now()
        assets = []
        for sid in scene_ids:
            for purpose, tag in (("anchor_still", "ANCHOR"), ("first_frame_still", "FIRST"), ("last_frame_still", "LAST")):
                a = _asset(
                    self.media_dir / "scenes" / sid / f"{purpose}.png",
                    f"{sid}-{tag}".encode("utf-8"),
                    asset_id=f"{sid}:{purpose}", scene_id=sid, purpose=purpose,
                    approval_status="approved" if approved else "proposed",
                )
                assets.append(a)
        ledger = {"schema_version": "1.0.0", "project_id": "proj-prove-media-tests", "assets": assets, "created_at": now, "updated_at": now}
        self.state.save("asset-ledger", ledger)
        return ledger

    def _mirror_scene_plan_from_ledger(self, scene_plan, ledger):
        by_scene_anchor = {a["scene_id"]: a for a in ledger["assets"] if a["purpose"] == "anchor_still"}
        for scene in scene_plan["scenes"]:
            still = by_scene_anchor.get(scene["scene_id"])
            if still is not None:
                scene["approval_status"] = "anchor_approved"
                scene["anchor_asset_hash"] = still["hash_sha256"]
        self.state.save("scene-plan", scene_plan)
        return scene_plan


# ---------------------------------------------------------------------------
# evaluate_anchor
# ---------------------------------------------------------------------------
class EvaluateAnchorTests(ProveMediaTestCase):
    def test_fails_with_no_anchor_approval(self) -> None:
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("does not exist", detail)

    def test_fails_on_empty_concept_board(self) -> None:
        now = _now()
        anchor = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests", "status": "proposed",
            "style_contract": _empty_style_contract(), "concept_candidates": [], "approved_candidate_id": None,
            "final_anchor": None, "approved_by": None, "approved_at": None, "created_at": now, "updated_at": now,
        }
        self.state.save("anchor-approval", anchor)
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("concept_candidates is empty", detail)
        self.assertIn("status=", detail)

    def test_fails_without_matching_manifest_approval(self) -> None:
        self._write_locked_anchor(record_manifest_approval=False)
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("anchor_final", detail)

    def test_passes_on_fully_valid_fixture(self) -> None:
        self._write_locked_anchor()
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertTrue(passed, detail)
        self.assertTrue((self.tmp / "anchor-gate-receipt.json").exists())

    def test_detects_tampered_final_anchor_file(self) -> None:
        anchor = self._write_locked_anchor()
        Path(anchor["final_anchor"]["local_path"]).write_bytes(b"TAMPERED")
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("hash", detail)

    def test_detects_missing_concept_candidate_file(self) -> None:
        anchor = self._write_locked_anchor()
        Path(anchor["concept_candidates"][0]["local_path"]).unlink()
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("does not exist on disk", detail)

    def test_detects_approved_candidate_id_not_in_concept_candidates(self) -> None:
        anchor = self._write_locked_anchor()
        anchor["approved_candidate_id"] = "concept-does-not-exist"
        self.state.save("anchor-approval", anchor)
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)
        self.assertIn("does not reference", detail)

    def test_fails_when_status_not_anchor_approved(self) -> None:
        anchor = self._write_locked_anchor()
        anchor["status"] = "concept_approved"
        self.state.save("anchor-approval", anchor)
        passed, detail = pm.evaluate_anchor(self.tmp)
        self.assertFalse(passed)

    def test_writes_receipt_on_failure_too(self) -> None:
        pm.evaluate_anchor(self.tmp)
        self.assertTrue((self.tmp / "anchor-gate-receipt.json").exists())


# ---------------------------------------------------------------------------
# evaluate_stills
# ---------------------------------------------------------------------------
class EvaluateStillsTests(ProveMediaTestCase):
    def test_fails_when_anchor_not_yet_approved(self) -> None:
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("P6-ANCHOR", detail)

    def test_fails_when_scene_plan_missing(self) -> None:
        self._write_locked_anchor()
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-plan.json does not exist", detail)

    def test_fails_when_asset_ledger_missing(self) -> None:
        self._write_locked_anchor()
        self._write_scene_plan()
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("asset-ledger.json does not exist", detail)

    def test_fails_when_assets_not_approved(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        self._write_full_ledger(approved=False)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("approval_status", detail)

    def test_fails_when_scene_plan_not_mirrored(self) -> None:
        self._write_locked_anchor()
        self._write_scene_plan()
        self._write_full_ledger(approved=True)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-plan.json approval_status", detail)

    def test_passes_on_fully_valid_fixture(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        ledger = self._write_full_ledger(approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertTrue(passed, detail)
        self.assertTrue((self.tmp / "stills-gate-receipt.json").exists())

    def test_multi_scene_all_required(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan(scene_ids=("scene-01-hero", "scene-02-problem", "scene-03-cta"))
        ledger = self._write_full_ledger(scene_ids=("scene-01-hero", "scene-02-problem", "scene-03-cta"), approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertTrue(passed, detail)
        self.assertEqual(len(ledger["assets"]), 9)

    def test_fails_when_one_scene_missing_a_purpose(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        ledger = self._write_full_ledger(approved=True)
        ledger["assets"] = [a for a in ledger["assets"] if a["purpose"] != "last_frame_still"]
        self.state.save("asset-ledger", ledger)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("missing asset-ledger purpose", detail)

    def test_detects_scene_plan_hash_drift_from_ledger(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        ledger = self._write_full_ledger(approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        scene_plan["scenes"][0]["anchor_asset_hash"] = "f" * 64
        self.state.save("scene-plan", scene_plan)
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("does not match", detail)

    def test_detects_tampered_scene_still_file(self) -> None:
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        ledger = self._write_full_ledger(approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        Path(ledger["assets"][0]["local_path"]).write_bytes(b"TAMPERED-SCENE-STILL")
        passed, detail = pm.evaluate_stills(self.tmp)
        self.assertFalse(passed)
        self.assertIn("hash", detail)


# ---------------------------------------------------------------------------
# CLI dispatch (CWFE_MEDIA_CHECK env var / --check flag)
# ---------------------------------------------------------------------------
class CliDispatchTests(ProveMediaTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan()
        ledger = self._write_full_ledger(approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)

    def test_default_check_is_anchor(self) -> None:
        result = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("P6-ANCHOR", result.stdout)

    def test_explicit_check_flag_stills(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--check", "stills"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("P7-STILLS", result.stdout)

    def test_env_var_check_stills(self) -> None:
        import os

        env = dict(os.environ)
        env["CWFE_MEDIA_CHECK"] = "stills"
        result = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("P7-STILLS", result.stdout)

    def test_usage_error_missing_run_dir(self) -> None:
        result = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)

    def test_usage_error_nonexistent_run_dir(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp / "nope")], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 3)


class SelfTestTests(unittest.TestCase):
    def test_module_self_test_passes(self) -> None:
        result = subprocess.run([PY, str(SCRIPT), "--self-test"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
