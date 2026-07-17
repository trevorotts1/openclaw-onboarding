#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_media.py — unit + break-it test suite for build units U11+U12
(scripts/prove_media.py): the P6-ANCHOR / P7-STILLS / P8-DRAFT /
P9-FINAL-MEDIA phase gates.

Builds minimal, HAND-CRAFTED, disk-backed fixture artifacts directly via
state_engine.ProjectState.save() (mirrors prove_budget.py's own
_self_test_scene_plan() precedent) rather than driving generate_images.py's
/ generate_videos.py's full paid-call pipeline — a gate test proves the
gate's EVALUATION logic; test_generate_images.py / test_generate_videos.py
already cover their producer pipelines end-to-end against mocked Kie
fixtures. The P9-FINAL-MEDIA fixtures below are the one exception: they
synthesize a REAL short ffmpeg clip and run it through the REAL
encode_scrub_media.py -> extract_boundaries.py pipeline, because
evaluate_final()'s own job is verifying that exact real on-disk chain — a
hand-faked encoded/boundary_frames record would not exercise the check it
exists to prove.

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

import encode_scrub_media as esm  # noqa: E402
import extract_boundaries as eb  # noqa: E402
import media_ffmpeg as mf  # noqa: E402
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

    def _write_fully_valid_p7(self, scene_ids=("scene-01-hero",)):
        """Composes every P6/P7 helper above into one fully-valid,
        evaluate_stills()-passing fixture — the common precondition every
        P8/P9 test below needs."""
        self._write_locked_anchor()
        scene_plan = self._write_scene_plan(scene_ids=scene_ids)
        ledger = self._write_full_ledger(scene_ids=scene_ids, approved=True)
        self._mirror_scene_plan_from_ledger(scene_plan, ledger)
        return scene_plan, ledger

    def _write_draft(self, scene_id="scene-01-hero", *, review_status="approved"):
        """Accumulates into any existing draft-media-receipt.json (never
        overwrites a previously-written scene's draft) — mirrors the real
        producer's incremental-save behavior so multi-scene fixtures work."""
        now = _now()
        draft = _asset(
            self.media_dir / "video" / "drafts" / f"{scene_id}.mp4", f"DRAFT-{scene_id}".encode("utf-8"),
            model_id="kie-bytedance-seedance-1.5-pro",
        )
        draft.update(
            scene_id=scene_id, duration_seconds=8.0,
            input_urls=["https://fixtures.example/first.png", "https://fixtures.example/last.png"],
            review_status=review_status,
        )
        if self.state.exists("draft-media-receipt"):
            receipt = self.state.load("draft-media-receipt")
            receipt["drafts"] = [d for d in receipt["drafts"] if d["scene_id"] != scene_id] + [draft]
            receipt["updated_at"] = now
        else:
            receipt = {
                "schema_version": "1.0.0", "project_id": "proj-prove-media-tests",
                "drafts": [draft], "created_at": now, "updated_at": now,
            }
        self.state.save("draft-media-receipt", receipt)
        return receipt

    def _make_real_final_asset(self, label: str, *, approval_status="approved") -> Dict[str, Any]:
        """Synthesizes a REAL short ffmpeg clip and runs it through the REAL
        encode_scrub_media.py -> extract_boundaries.py pipeline, so
        evaluate_final()'s hash/provenance checks are exercised against
        genuinely decodable, genuinely distinct encoded media."""
        binaries = mf.require_binaries()
        raw_dir = self.media_dir / "video" / "final" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{label}.mp4"
        cmd = [
            binaries["ffmpeg"], "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(raw_path),
        ]
        proc = mf.run_cmd(cmd, label="ffmpeg-test-fixture")
        assert proc.returncode == 0 and raw_path.exists(), proc.stderr

        asset_id = f"{label}-final"
        encode_out_dir = self.media_dir / "video" / "final" / "encoded" / asset_id
        media_receipt = esm.encode_scrub_media(raw_path, encode_out_dir, asset_id=asset_id, variant_names=["desktop"])
        variant = media_receipt["variants"][0]
        boundaries_out_dir = self.media_dir / "video" / "final" / "boundaries" / asset_id
        variant_path = Path(variant["output_path"])
        boundary_receipt = eb.extract_boundaries(variant_path, boundaries_out_dir)
        by_pos = {f["position"]: f for f in boundary_receipt["frames"]}

        asset = _asset(raw_path, raw_path.read_bytes(), model_id="kie-bytedance-seedance-1.5-pro", provider_task_id=f"fixture-{label}-task")
        asset.update(
            asset_id=f"{label}:final", kind="scene_final", scene_id=label, from_scene_id=None, to_scene_id=None,
            duration_seconds=2.0, input_urls=["https://fixtures.example/first.png", "https://fixtures.example/last.png"],
            encoded={
                "media_processing_receipt_path": str(encode_out_dir / f"{asset_id}.media-processing-receipt.json"),
                "variant_name": variant["variant_name"], "output_path": variant["output_path"],
                "width": variant["width"], "height": variant["height"],
                "duration_seconds": variant["duration_seconds"], "hash_sha256": variant["hash_sha256"],
            },
            boundary_frames={
                "boundary_frames_receipt_path": str(boundaries_out_dir / f"{variant_path.stem}.boundary-frames.json"),
                "first": {
                    "frame_index": by_pos["first"]["frame_index"], "timestamp_seconds": by_pos["first"]["timestamp_seconds"],
                    "output_path": by_pos["first"]["output_path"], "hash_sha256": by_pos["first"]["hash_sha256"],
                },
                "last": {
                    "frame_index": by_pos["last"]["frame_index"], "timestamp_seconds": by_pos["last"]["timestamp_seconds"],
                    "output_path": by_pos["last"]["output_path"], "hash_sha256": by_pos["last"]["hash_sha256"],
                },
            },
            approval_status=approval_status,
        )
        return asset

    def _write_full_p9(self, scene_ids=("scene-01-hero",)):
        self._write_fully_valid_p7(scene_ids=scene_ids)
        for sid in scene_ids:
            self._write_draft(sid, review_status="approved")
        assets = [self._make_real_final_asset(sid) for sid in scene_ids]
        now = _now()
        vledger = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests",
            "assets": assets, "created_at": now, "updated_at": now,
        }
        self.state.save("video-asset-ledger", vledger)
        return vledger


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
# evaluate_draft
# ---------------------------------------------------------------------------
class EvaluateDraftTests(ProveMediaTestCase):
    def test_fails_when_p7_stills_not_yet_passed(self) -> None:
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertFalse(passed)
        self.assertIn("P7-STILLS", detail)

    def test_fails_when_draft_media_receipt_missing(self) -> None:
        self._write_fully_valid_p7()
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertFalse(passed)
        self.assertIn("draft-media-receipt.json does not exist", detail)

    def test_fails_when_draft_not_approved(self) -> None:
        self._write_fully_valid_p7()
        self._write_draft(review_status="proposed")
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertFalse(passed)
        self.assertIn("review_status", detail)

    def test_fails_when_a_scene_has_no_draft_entry(self) -> None:
        self._write_fully_valid_p7(scene_ids=("scene-01-hero", "scene-02-cta"))
        self._write_draft("scene-01-hero", review_status="approved")
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-02-cta", detail)
        self.assertIn("missing draft-media-receipt entry", detail)

    def test_passes_on_fully_valid_fixture(self) -> None:
        self._write_fully_valid_p7()
        self._write_draft(review_status="approved")
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertTrue(passed, detail)
        self.assertTrue((self.tmp / "draft-gate-receipt.json").exists())

    def test_detects_tampered_draft_file(self) -> None:
        self._write_fully_valid_p7()
        receipt = self._write_draft(review_status="approved")
        Path(receipt["drafts"][0]["local_path"]).write_bytes(b"TAMPERED-DRAFT")
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertFalse(passed)
        self.assertIn("hash", detail)

    def test_multi_scene_all_required(self) -> None:
        scene_ids = ("scene-01-hero", "scene-02-cta")
        self._write_fully_valid_p7(scene_ids=scene_ids)
        for sid in scene_ids:
            self._write_draft(sid, review_status="approved")
        passed, detail = pm.evaluate_draft(self.tmp)
        self.assertTrue(passed, detail)


# ---------------------------------------------------------------------------
# evaluate_final
# ---------------------------------------------------------------------------
class EvaluateFinalTests(ProveMediaTestCase):
    def test_fails_when_p8_draft_not_yet_passed(self) -> None:
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("P8-DRAFT", detail)

    def test_fails_when_video_asset_ledger_missing(self) -> None:
        self._write_fully_valid_p7()
        self._write_draft(review_status="approved")
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("video-asset-ledger.json does not exist", detail)

    def test_fails_when_final_clip_not_approved(self) -> None:
        self._write_fully_valid_p7()
        self._write_draft(review_status="approved")
        asset = self._make_real_final_asset("scene-01-hero", approval_status="proposed")
        now = _now()
        self.state.save("video-asset-ledger", {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests",
            "assets": [asset], "created_at": now, "updated_at": now,
        })
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("approval_status", detail)

    def test_passes_on_fully_valid_real_fixture(self) -> None:
        self._write_full_p9()
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertTrue(passed, detail)
        self.assertTrue((self.tmp / "final-media-gate-receipt.json").exists())

    def test_fails_when_a_scene_has_no_final_entry(self) -> None:
        scene_ids = ("scene-01-hero", "scene-02-cta")
        self._write_fully_valid_p7(scene_ids=scene_ids)
        for sid in scene_ids:
            self._write_draft(sid, review_status="approved")
        # Only scene-01-hero gets a real P9 final asset; scene-02-cta's is
        # deliberately missing, so P6/P7/P8 all pass and this isolates the
        # exact check under test.
        asset = self._make_real_final_asset("scene-01-hero")
        now = _now()
        self.state.save("video-asset-ledger", {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-tests",
            "assets": [asset], "created_at": now, "updated_at": now,
        })
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-02-cta", detail)
        self.assertIn("missing video-asset-ledger kind='scene_final' entry", detail)

    def test_detects_tampered_encoded_output(self) -> None:
        vledger = self._write_full_p9()
        Path(vledger["assets"][0]["encoded"]["output_path"]).write_bytes(b"TAMPERED-ENCODED")
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("encoded output file hash mismatch", detail)

    def test_detects_tampered_raw_clip(self) -> None:
        vledger = self._write_full_p9()
        Path(vledger["assets"][0]["local_path"]).write_bytes(b"TAMPERED-RAW")
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("hash", detail)

    def test_detects_boundary_first_last_collision(self) -> None:
        vledger = self._write_full_p9()
        asset = vledger["assets"][0]
        first_path = Path(asset["boundary_frames"]["first"]["output_path"])
        last_path = Path(asset["boundary_frames"]["last"]["output_path"])
        last_path.write_bytes(first_path.read_bytes())
        asset["boundary_frames"]["last"]["hash_sha256"] = asset["boundary_frames"]["first"]["hash_sha256"]
        self.state.save("video-asset-ledger", vledger)
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("hash identically", detail)

    def test_fails_when_connector_required_but_no_connector_entry(self) -> None:
        vledger = self._write_full_p9()
        scene_plan = self.state.load("scene-plan")
        scene_plan["scenes"][0]["connector_required"] = True
        self.state.save("scene-plan", scene_plan)
        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("no video-asset-ledger kind='connector' entry", detail)

    def test_detects_miswired_connector_adjacency(self) -> None:
        vledger = self._write_full_p9()
        scene_plan = self.state.load("scene-plan")
        scene_plan["scenes"][0]["connector_required"] = True
        self.state.save("scene-plan", scene_plan)

        bogus_connector = self._make_real_final_asset("scene-01-hero-connector")
        bogus_connector.update(kind="connector", scene_id=None, from_scene_id="scene-99-bogus", to_scene_id="scene-01-hero")
        vledger["assets"].append(bogus_connector)
        self.state.save("video-asset-ledger", vledger)

        passed, detail = pm.evaluate_final(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-plan adjacency", detail)

    def test_passes_with_correctly_wired_connector(self) -> None:
        vledger = self._write_full_p9()
        scene_plan = self.state.load("scene-plan")
        scene_plan["scenes"][0]["connector_required"] = True  # index 0 -> expected_from=None
        self.state.save("scene-plan", scene_plan)

        connector = self._make_real_final_asset("scene-01-hero-connector")
        connector.update(kind="connector", scene_id=None, from_scene_id=None, to_scene_id="scene-01-hero")
        vledger["assets"].append(connector)
        self.state.save("video-asset-ledger", vledger)

        passed, detail = pm.evaluate_final(self.tmp)
        self.assertTrue(passed, detail)
        self.assertIn("1 connector clip(s)", detail)


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

    def test_explicit_check_flag_draft_fails_without_p8_fixture(self) -> None:
        # this test class's setUp only builds a P6/P7 fixture -- P8 correctly
        # fails. A FAILing gate's [FAIL] line goes to stderr (main()'s own
        # convention — only a [PASS] line goes to stdout).
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--check", "draft"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertIn("P8-DRAFT", result.stderr)

    def test_explicit_check_flag_final_fails_without_p9_fixture(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--check", "final"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertIn("P9-FINAL-MEDIA", result.stderr)

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
