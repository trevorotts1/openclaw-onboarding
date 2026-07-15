#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_generate_images.py — unit + break-it test suite for build unit U11
(scripts/generate_images.py): the anchor image / scene still generator
(spec Section 9.2/9.3).

NO NETWORK, NO REAL KIE_API_KEY VALUE, NO LIVE/PAID CALL. Every HTTP
interaction goes through generate_images.FixtureKieTransport (spec §19.2
"Kie adapter against mocked API fixtures") — providers.kie.RequestsTransport
is never instantiated by this suite.

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import shutil
import subprocess
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
import plan_visual_journey as pvj  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402
from providers import kie as kie_provider  # noqa: E402

PY = sys.executable or "python3"
SCRIPT = _SCRIPTS_DIR / "generate_images.py"


class GenerateImagesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-generate-images-tests-"))
        self.env_patch = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.provider = kie_provider.KieProvider(transport=gi.FixtureKieTransport())
        self.verified_registry = gi.build_verified_image_registry_copy(self.tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fixture_project(self, **kwargs):
        project_manifest, content_manifest = pvj.build_fixture_project_and_content_manifest(self.tmp, **kwargs)
        state = se.ProjectState(self.tmp)
        state.transition_project_status("journey", reason="test: simulate P1-P3 passing")
        passed, detail = pvj.plan_visual_journey(self.tmp)
        assert passed, detail
        apr.approve(self.tmp, cap_usd=50.0, approved_by="test-operator", note="test cap")
        return project_manifest, content_manifest

    def _style_contract(self):
        return gi.build_style_contract(visual_world="a sunlit modern studio loft")


# ---------------------------------------------------------------------------
# AF-CWFE-PAID-GATE wiring: the REAL registry's unverified gpt-image-2
# pricing must fail-closed today.
# ---------------------------------------------------------------------------
class PaidGateFailClosedTests(GenerateImagesTestCase):
    def test_concept_board_fails_closed_against_real_unverified_registry(self) -> None:
        self._fixture_project()
        passed, detail = gi.run_concept_board(self.tmp, style_contract=self._style_contract(), provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("AF-CWFE-PAID-GATE", detail)

    def test_concept_board_leaves_no_partial_state_on_first_blocked_call(self) -> None:
        self._fixture_project()
        gi.run_concept_board(self.tmp, style_contract=self._style_contract(), provider=self.provider)
        state = se.ProjectState(self.tmp)
        # anchor-approval.json may have been written with an empty candidate
        # list (the very first paid call was blocked before any asset was
        # produced) but must never contain a half-generated candidate.
        if state.exists("anchor-approval"):
            self.assertEqual(state.load("anchor-approval")["concept_candidates"], [])

    def test_run_concept_board_fails_before_intake_locked(self) -> None:
        se.ProjectState(self.tmp).create_project(
            project_id="proj-no-intake", client_slug="acme", project_slug="launch",
            deliverable_type="cinematic-landing-page", budget_cap_usd=10.0,
        )
        passed, detail = gi.run_concept_board(self.tmp, style_contract=self._style_contract(), provider=self.provider)
        self.assertFalse(passed)

    def test_run_concept_board_fails_without_project_manifest(self) -> None:
        passed, detail = gi.run_concept_board(self.tmp, style_contract=self._style_contract(), provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("project-manifest.json does not exist", detail)


# ---------------------------------------------------------------------------
# Full happy path against the TEST-ONLY verified-price registry copy
# ---------------------------------------------------------------------------
class ConceptBoardHappyPathTests(GenerateImagesTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._fixture_project()

    def test_run_concept_board_generates_three_distinct_candidates(self) -> None:
        passed, detail = gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        self.assertTrue(passed, detail)
        state = se.ProjectState(self.tmp)
        anchor = state.load("anchor-approval")
        self.assertEqual(len(anchor["concept_candidates"]), 3)
        self.assertEqual(len({c["hash_sha256"] for c in anchor["concept_candidates"]}), 3)
        for candidate in anchor["concept_candidates"]:
            self.assertTrue(Path(candidate["local_path"]).is_file())
            self.assertEqual(candidate["model_id"], "kie-gpt-image-2-text-to-image")

    def test_run_concept_board_is_idempotent(self) -> None:
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        state = se.ProjectState(self.tmp)
        before = state.load("anchor-approval")["concept_candidates"]
        passed, detail = gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        self.assertTrue(passed)
        self.assertIn("0 newly generated", detail)
        after = state.load("anchor-approval")["concept_candidates"]
        self.assertEqual(before, after)

    def test_run_concept_board_refuses_once_locked(self) -> None:
        self._run_full_anchor_pipeline()
        passed, detail = gi.run_concept_board(self.tmp, style_contract=self._style_contract(), provider=self.provider)
        self.assertFalse(passed)
        self.assertIn("anchor_approved", detail)

    def test_approve_concept_candidate_rejects_unknown_candidate_id(self) -> None:
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        passed, detail = gi.approve_concept_candidate(self.tmp, "concept-99", approved_by="tester")
        self.assertFalse(passed)
        self.assertIn("not found", detail)

    def test_approve_concept_candidate_rejects_empty_approver(self) -> None:
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        state = se.ProjectState(self.tmp)
        candidate_id = state.load("anchor-approval")["concept_candidates"][0]["candidate_id"]
        passed, detail = gi.approve_concept_candidate(self.tmp, candidate_id, approved_by="  ")
        self.assertFalse(passed)

    def _run_full_anchor_pipeline(self):
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        state = se.ProjectState(self.tmp)
        candidate_id = state.load("anchor-approval")["concept_candidates"][0]["candidate_id"]
        gi.approve_concept_candidate(self.tmp, candidate_id, approved_by="tester")
        gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        gi.approve_final_anchor(self.tmp, approved_by="tester")


class FinalAnchorTests(GenerateImagesTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._fixture_project()
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        state = se.ProjectState(self.tmp)
        self.candidate_id = state.load("anchor-approval")["concept_candidates"][0]["candidate_id"]

    def test_generate_final_anchor_refuses_before_concept_approved(self) -> None:
        passed, detail = gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertFalse(passed)
        self.assertIn("concept_approved", detail)

    def test_generate_final_anchor_succeeds_after_concept_approved(self) -> None:
        gi.approve_concept_candidate(self.tmp, self.candidate_id, approved_by="tester")
        passed, detail = gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed, detail)
        state = se.ProjectState(self.tmp)
        anchor = state.load("anchor-approval")
        self.assertIsNotNone(anchor["final_anchor"])
        self.assertTrue(Path(anchor["final_anchor"]["local_path"]).is_file())

    def test_generate_final_anchor_is_idempotent(self) -> None:
        gi.approve_concept_candidate(self.tmp, self.candidate_id, approved_by="tester")
        gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        state = se.ProjectState(self.tmp)
        first_hash = state.load("anchor-approval")["final_anchor"]["hash_sha256"]
        passed, detail = gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed)
        self.assertIn("already generated", detail)
        self.assertEqual(state.load("anchor-approval")["final_anchor"]["hash_sha256"], first_hash)

    def test_approve_final_anchor_refuses_before_final_anchor_generated(self) -> None:
        gi.approve_concept_candidate(self.tmp, self.candidate_id, approved_by="tester")
        passed, detail = gi.approve_final_anchor(self.tmp, approved_by="tester")
        self.assertFalse(passed)

    def test_approve_final_anchor_records_audit_trail(self) -> None:
        gi.approve_concept_candidate(self.tmp, self.candidate_id, approved_by="tester")
        gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        passed, detail = gi.approve_final_anchor(self.tmp, approved_by="tester")
        self.assertTrue(passed, detail)
        state = se.ProjectState(self.tmp)
        manifest = state.load("project-manifest")
        matches = [a for a in manifest["approvals"] if a["kind"] == "anchor_final"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["approved_by"], "tester")
        anchor = state.load("anchor-approval")
        self.assertEqual(anchor["status"], "anchor_approved")

    def test_approve_final_anchor_is_idempotent(self) -> None:
        gi.approve_concept_candidate(self.tmp, self.candidate_id, approved_by="tester")
        gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        state = se.ProjectState(self.tmp)
        approvals_before = len(state.load("project-manifest")["approvals"])
        passed, detail = gi.approve_final_anchor(self.tmp, approved_by="someone-else")
        self.assertTrue(passed)
        self.assertIn("idempotent", detail)
        self.assertEqual(len(state.load("project-manifest")["approvals"]), approvals_before)


# ---------------------------------------------------------------------------
# P7-STILLS
# ---------------------------------------------------------------------------
class SceneStillsTests(GenerateImagesTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._fixture_project(sections=["hero", "problem", "cta"])
        gi.run_concept_board(
            self.tmp, style_contract=self._style_contract(), provider=self.provider,
            registry_path=str(self.verified_registry),
        )
        state = se.ProjectState(self.tmp)
        candidate_id = state.load("anchor-approval")["concept_candidates"][0]["candidate_id"]
        gi.approve_concept_candidate(self.tmp, candidate_id, approved_by="tester")
        gi.generate_final_anchor(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))

    def test_generate_scene_stills_refuses_before_anchor_approved(self) -> None:
        passed, detail = gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertFalse(passed)
        self.assertIn("anchor is approved", detail)

    def test_generate_scene_stills_full_pipeline(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        passed, detail = gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed, detail)

        state = se.ProjectState(self.tmp)
        ledger = state.load("asset-ledger")
        scene_plan = state.load("scene-plan")
        self.assertEqual(len(ledger["assets"]), 3 * len(scene_plan["scenes"]))
        for scene in scene_plan["scenes"]:
            purposes = {a["purpose"] for a in ledger["assets"] if a["scene_id"] == scene["scene_id"]}
            self.assertEqual(purposes, {"anchor_still", "first_frame_still", "last_frame_still"})
        for asset in ledger["assets"]:
            self.assertTrue(Path(asset["local_path"]).is_file())
            self.assertEqual(asset["approval_status"], "proposed")

    def test_generate_scene_stills_scoped_to_one_scene(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        state = se.ProjectState(self.tmp)
        scene_id = state.load("scene-plan")["scenes"][0]["scene_id"]
        passed, detail = gi.generate_scene_stills(
            self.tmp, scene_ids=(scene_id,), provider=self.provider, registry_path=str(self.verified_registry)
        )
        self.assertTrue(passed, detail)
        ledger = state.load("asset-ledger")
        self.assertEqual(len(ledger["assets"]), 3)
        self.assertTrue(all(a["scene_id"] == scene_id for a in ledger["assets"]))

    def test_generate_scene_stills_unknown_scene_id_fails(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        passed, detail = gi.generate_scene_stills(
            self.tmp, scene_ids=("nonexistent-scene",), provider=self.provider, registry_path=str(self.verified_registry)
        )
        self.assertFalse(passed)

    def test_generate_scene_stills_is_idempotent(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        state = se.ProjectState(self.tmp)
        before = state.load("asset-ledger")["assets"]
        passed, detail = gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        self.assertTrue(passed)
        self.assertIn("0 newly generated", detail)
        self.assertEqual(state.load("asset-ledger")["assets"], before)

    def test_approve_scene_stills_mirrors_into_scene_plan(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        passed, detail = gi.approve_scene_stills(self.tmp, approved_by="tester")
        self.assertTrue(passed, detail)

        state = se.ProjectState(self.tmp)
        ledger = state.load("asset-ledger")
        scene_plan = state.load("scene-plan")
        self.assertTrue(all(a["approval_status"] == "approved" for a in ledger["assets"]))
        for scene in scene_plan["scenes"]:
            self.assertEqual(scene["approval_status"], "anchor_approved")
            expected_hash = next(
                a for a in ledger["assets"] if a["scene_id"] == scene["scene_id"] and a["purpose"] == "anchor_still"
            )["hash_sha256"]
            self.assertEqual(scene["anchor_asset_hash"], expected_hash)

        manifest = state.load("project-manifest")
        matches = [a for a in manifest["approvals"] if a["kind"] == "scene_stills"]
        self.assertEqual(len(matches), 1)

    def test_approve_scene_stills_scoped_to_one_scene_leaves_others_untouched(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        state = se.ProjectState(self.tmp)
        scene_ids = [s["scene_id"] for s in state.load("scene-plan")["scenes"]]
        passed, detail = gi.approve_scene_stills(self.tmp, approved_by="tester", scene_ids=(scene_ids[0],))
        self.assertTrue(passed, detail)

        scene_plan = state.load("scene-plan")
        approved = {s["scene_id"]: s["approval_status"] for s in scene_plan["scenes"]}
        self.assertEqual(approved[scene_ids[0]], "anchor_approved")
        for other_id in scene_ids[1:]:
            self.assertEqual(approved[other_id], "proposed")

    def test_approve_scene_stills_rejects_empty_approver(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        passed, detail = gi.approve_scene_stills(self.tmp, approved_by="")
        self.assertFalse(passed)

    def test_approve_scene_stills_fails_with_no_matching_assets(self) -> None:
        gi.approve_final_anchor(self.tmp, approved_by="tester")
        gi.generate_scene_stills(self.tmp, provider=self.provider, registry_path=str(self.verified_registry))
        passed, detail = gi.approve_scene_stills(self.tmp, approved_by="tester", scene_ids=("nonexistent-scene",))
        self.assertFalse(passed)


# ---------------------------------------------------------------------------
# CLI subprocess contract
# ---------------------------------------------------------------------------
class CliTests(GenerateImagesTestCase):
    def test_usage_error_missing_action(self) -> None:
        result = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 3)

    def test_usage_error_nonexistent_run_dir(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp / "does-not-exist"), "--action", "concept-board"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 3)

    def test_concept_board_action_fails_closed_against_real_registry(self) -> None:
        self._fixture_project()
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--action", "concept-board", "--visual-world", "a quiet harbor at dawn"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("AF-CWFE-PAID-GATE", result.stderr)

    def test_approve_concept_requires_candidate_id_and_approved_by(self) -> None:
        result = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--action", "approve-concept"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 3)


class SelfTestTests(unittest.TestCase):
    def test_module_self_test_passes(self) -> None:
        result = subprocess.run([PY, str(SCRIPT), "--self-test"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("RESULT: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
