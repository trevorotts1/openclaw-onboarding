#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_generate_videos.py — unit + break-it test suite for build unit U12
(scripts/generate_videos.py): draft + final scene/connector video generation
(spec Section 9.2/9.5/12.2, ADR-8, ADR-9).

NO NETWORK, NO REAL KIE_API_KEY VALUE, NO LIVE/PAID CALL. Every HTTP
interaction goes through generate_videos.FixtureKieTransport (spec §19.2
"Kie adapter against mocked API fixtures") — providers.kie.RequestsTransport
is never instantiated by this suite. FixtureKieTransport.download() DOES
synthesize real short ffmpeg-encoded clips (mirrors extract_boundaries.py's
own self-test convention) so this module's real encode/boundary-extraction
stage is genuinely exercised, not mocked away.

The class-level pipeline fixture (real ffmpeg encode+extract across 6 scenes
+ 1 connector) is built ONCE in setUpClass and read by every test method in
PipelineTestCase — never rebuilt per test method — to keep this suite fast.
Tests that need to observe a FAILURE before that pipeline exists use their
own cheap, isolated fixture instead.

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (_SKILL_DIR, _SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import approve_paid_run as apr  # noqa: E402
import generate_images as gi  # noqa: E402
import generate_videos as gv  # noqa: E402
import plan_visual_journey as pvj  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402
from providers import kie as kie_provider  # noqa: E402

PY = sys.executable or "python3"
SCRIPT = _SCRIPTS_DIR / "generate_videos.py"

_SECTIONS = ["hero", "problem", "solution", "offer", "proof", "cta"]


def _drive_p6_p7(tmp: Path, transport, verified_registry: Path) -> None:
    """Drives the real P6-ANCHOR/P7-STILLS pipeline so a P8/P9 fixture rests
    on genuinely valid upstream state (mirrors generate_videos.py's own
    self-test helper)."""
    style_contract = gi.build_style_contract(visual_world="a sunlit modern studio loft")
    provider = kie_provider.KieProvider(transport=transport)
    passed, detail = gi.run_concept_board(tmp, style_contract=style_contract, provider=provider, registry_path=str(verified_registry))
    assert passed, detail
    anchor = se.ProjectState(tmp).load("anchor-approval")
    passed, detail = gi.approve_concept_candidate(tmp, anchor["concept_candidates"][0]["candidate_id"], approved_by="test-operator")
    assert passed, detail
    passed, detail = gi.generate_final_anchor(tmp, provider=provider, registry_path=str(verified_registry))
    assert passed, detail
    passed, detail = gi.approve_final_anchor(tmp, approved_by="test-operator")
    assert passed, detail
    passed, detail = gi.generate_scene_stills(tmp, provider=provider, registry_path=str(verified_registry))
    assert passed, detail
    passed, detail = gi.approve_scene_stills(tmp, approved_by="test-operator")
    assert passed, detail


class PipelineTestCase(unittest.TestCase):
    """Builds ONE real end-to-end fixture (6 scenes, 1 connector at
    scene index 3) once for the whole class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._env_patch = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        cls._env_patch.start()
        cls.tmp = Path(tempfile.mkdtemp(prefix="cwfe-generate-videos-pipeline-"))
        cls.scratch = cls.tmp / "_fixture_scratch"

        pvj.build_fixture_project_and_content_manifest(cls.tmp, project_id="proj-video-pipeline-tests", sections=list(_SECTIONS))
        cls.state = se.ProjectState(cls.tmp)
        cls.state.transition_project_status("journey", reason="test: simulate P1-P3 passing")
        passed, detail = pvj.plan_visual_journey(cls.tmp)
        assert passed, detail
        apr.approve(cls.tmp, cap_usd=50.0, approved_by="test-operator", note="test cap")

        cls.verified_registry = gv.build_verified_media_registry_copy(cls.tmp)
        cls.transport = gv.FixtureKieTransport(cls.scratch)
        cls.provider = kie_provider.KieProvider(transport=cls.transport)

        _drive_p6_p7(cls.tmp, cls.transport, cls.verified_registry)

        passed, detail = gv.generate_draft_clips(cls.tmp, provider=cls.provider, registry_path=str(cls.verified_registry))
        assert passed, detail
        passed, detail = gv.approve_draft_clips(cls.tmp, approved_by="test-operator")
        assert passed, detail
        passed, detail = gv.generate_final_scene_clips(cls.tmp, provider=cls.provider, registry_path=str(cls.verified_registry))
        assert passed, detail
        passed, detail = gv.generate_connector_clips(cls.tmp, provider=cls.provider, registry_path=str(cls.verified_registry))
        assert passed, detail
        passed, detail = gv.approve_final_media(cls.tmp, approved_by="test-operator")
        assert passed, detail

    @classmethod
    def tearDownClass(cls) -> None:
        cls._env_patch.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)


class DraftClipsTests(PipelineTestCase):
    def test_one_draft_per_scene(self) -> None:
        drafts = self.state.load("draft-media-receipt")
        self.assertEqual(len(drafts["drafts"]), 6)
        self.assertEqual({d["scene_id"] for d in drafts["drafts"]}, {f"scene-0{i}-{s}" for i, s in enumerate(_SECTIONS, start=1)})

    def test_drafts_are_approved(self) -> None:
        drafts = self.state.load("draft-media-receipt")
        self.assertTrue(all(d["review_status"] == "approved" for d in drafts["drafts"]))

    def test_draft_media_approval_recorded_in_project_manifest(self) -> None:
        manifest = self.state.load("project-manifest")
        self.assertTrue(any(a["kind"] == "draft_media" for a in manifest["approvals"]))

    def test_draft_clips_have_distinct_hashes(self) -> None:
        drafts = self.state.load("draft-media-receipt")
        hashes = {d["hash_sha256"] for d in drafts["drafts"]}
        self.assertGreaterEqual(len(hashes), 2)

    def test_regenerating_drafts_is_idempotent(self) -> None:
        passed, detail = gv.generate_draft_clips(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed)
        self.assertIn("(0 newly generated", detail)


class FinalSceneClipsTests(PipelineTestCase):
    def test_six_scene_final_entries(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        finals = [a for a in vledger["assets"] if a["kind"] == "scene_final"]
        self.assertEqual(len(finals), 6)

    def test_every_final_clip_encoded_output_exists_on_disk(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        for a in vledger["assets"]:
            if a["kind"] == "scene_final":
                self.assertTrue(Path(a["encoded"]["output_path"]).exists(), a["encoded"]["output_path"])

    def test_every_final_clip_boundary_first_last_distinct(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        for a in vledger["assets"]:
            if a["kind"] == "scene_final":
                self.assertNotEqual(
                    a["boundary_frames"]["first"]["hash_sha256"], a["boundary_frames"]["last"]["hash_sha256"]
                )

    def test_scene_final_uses_the_scene_plans_own_generation_model(self) -> None:
        scene_plan = self.state.load("scene-plan")
        vledger = self.state.load("video-asset-ledger")
        finals_by_scene = {a["scene_id"]: a for a in vledger["assets"] if a["kind"] == "scene_final"}
        for scene in scene_plan["scenes"]:
            self.assertEqual(finals_by_scene[scene["scene_id"]]["model_id"], scene["generation_model"])

    def test_regenerating_final_scene_clips_is_idempotent(self) -> None:
        passed, detail = gv.generate_final_scene_clips(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed)
        self.assertIn("(0 newly generated", detail)


class ConnectorClipsTests(PipelineTestCase):
    def test_exactly_one_connector(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        connectors = [a for a in vledger["assets"] if a["kind"] == "connector"]
        self.assertEqual(len(connectors), 1)

    def test_connector_joins_the_correct_adjacent_scenes(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        connector = next(a for a in vledger["assets"] if a["kind"] == "connector")
        self.assertEqual(connector["from_scene_id"], "scene-03-solution")
        self.assertEqual(connector["to_scene_id"], "scene-04-offer")

    def test_connector_pins_the_real_encoded_adjacent_boundary_frames(self) -> None:
        """ADR-9 proof: the connector's uploaded frame-pin filenames must be
        the two adjacent scenes' own REAL encoded boundary frame files, not a
        generated still."""
        vledger = self.state.load("video-asset-ledger")
        from_final = next(a for a in vledger["assets"] if a["kind"] == "scene_final" and a["scene_id"] == "scene-03-solution")
        to_final = next(a for a in vledger["assets"] if a["kind"] == "scene_final" and a["scene_id"] == "scene-04-offer")
        expected_first = Path(from_final["boundary_frames"]["last"]["output_path"]).name
        expected_last = Path(to_final["boundary_frames"]["first"]["output_path"]).name
        self.assertIn(expected_first, self.transport.uploaded_file_names)
        self.assertIn(expected_last, self.transport.uploaded_file_names)

    def test_connector_boundary_first_last_distinct(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        connector = next(a for a in vledger["assets"] if a["kind"] == "connector")
        self.assertNotEqual(
            connector["boundary_frames"]["first"]["hash_sha256"], connector["boundary_frames"]["last"]["hash_sha256"]
        )

    def test_regenerating_connector_clips_is_idempotent(self) -> None:
        passed, detail = gv.generate_connector_clips(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed)
        self.assertIn("(0 newly generated", detail)

    def test_scene_ids_filter_to_a_non_connector_scene_finds_nothing(self) -> None:
        passed, detail = gv.generate_connector_clips(
            self.tmp, provider=self.provider, registry_path=str(self.verified_registry), scene_ids=("scene-01-hero",)
        )
        self.assertFalse(passed)


class ApprovalTests(PipelineTestCase):
    def test_every_video_asset_ledger_entry_is_approved(self) -> None:
        vledger = self.state.load("video-asset-ledger")
        self.assertTrue(all(a["approval_status"] == "approved" for a in vledger["assets"]))

    def test_final_media_approval_recorded_in_project_manifest(self) -> None:
        manifest = self.state.load("project-manifest")
        self.assertTrue(any(a["kind"] == "final_media" for a in manifest["approvals"]))


# ---------------------------------------------------------------------------
# Cheap, isolated fixtures for gate/ordering break-it tests that must observe
# a FAILURE before the (expensive) real pipeline above ever exists.
# ---------------------------------------------------------------------------
class GateOrderingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-generate-videos-gate-tests-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.provider = kie_provider.KieProvider(transport=gv.FixtureKieTransport(self.tmp / "_scratch"))


class PaidGateFailClosedTests(GateOrderingTestCase):
    def test_draft_clips_fail_closed_against_real_unverified_seedance_pricing(self) -> None:
        pvj.build_fixture_project_and_content_manifest(self.tmp, project_id="proj-gate-tests")
        state = se.ProjectState(self.tmp)
        state.transition_project_status("journey", reason="test")
        pvj.plan_visual_journey(self.tmp)
        apr.approve(self.tmp, cap_usd=50.0, approved_by="test-operator")
        _drive_p6_p7(self.tmp, self.provider.transport, gv.build_verified_media_registry_copy(self.tmp))
        # NOTE: no registry_path override here -- the REAL registry's Seedance
        # entry is unpriced/unverified and must fail AF-CWFE-PAID-GATE.
        passed, detail = gv.generate_draft_clips(self.tmp, provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("AF-CWFE-PAID-GATE", detail)


class OrderingTests(GateOrderingTestCase):
    def test_draft_clips_refuse_before_p6_anchor_exists(self) -> None:
        pvj.build_fixture_project_and_content_manifest(self.tmp, project_id="proj-order-tests")
        se.ProjectState(self.tmp).transition_project_status("journey", reason="test")
        pvj.plan_visual_journey(self.tmp)
        passed, detail = gv.generate_draft_clips(self.tmp, provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("P6-ANCHOR", detail)

    def test_final_scene_clips_refuse_before_draft_media_receipt_exists(self) -> None:
        passed, detail = gv.generate_final_scene_clips(self.tmp, provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("P8-DRAFT", detail)

    def test_connector_clips_refuse_before_video_asset_ledger_exists(self) -> None:
        passed, detail = gv.generate_connector_clips(self.tmp, provider=self.provider)
        self.assertFalse(passed)

    def test_approve_final_media_refuses_before_video_asset_ledger_exists(self) -> None:
        passed, detail = gv.approve_final_media(self.tmp, approved_by="test-operator")
        self.assertFalse(passed)

    def test_approve_draft_clips_rejects_empty_approver(self) -> None:
        passed, detail = gv.approve_draft_clips(self.tmp, approved_by="   ")
        self.assertFalse(passed)

    def test_approve_final_media_rejects_empty_approver(self) -> None:
        passed, detail = gv.approve_final_media(self.tmp, approved_by="")
        self.assertFalse(passed)


class CliTests(GateOrderingTestCase):
    def test_usage_error_missing_action(self) -> None:
        import subprocess

        result = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(result.returncode, gv.EXIT_USAGE)

    def test_usage_error_nonexistent_run_dir(self) -> None:
        import subprocess

        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", "/definitely/does/not/exist", "--action", "draft-clips"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, gv.EXIT_USAGE)

    def test_approve_draft_requires_approved_by(self) -> None:
        import subprocess

        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--action", "approve-draft"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, gv.EXIT_USAGE)


class SelfTestTests(unittest.TestCase):
    def test_module_self_test_passes(self) -> None:
        self.assertEqual(gv.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
