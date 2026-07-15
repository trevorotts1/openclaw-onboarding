#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_breakit_adversarial.py — U21 adversarial "break-it" test suite for
the Cinematic and Web Funnel Engine (Skill 62), exercised at the real
subprocess/CLI boundary the orchestrator and its phase gates actually use
(spec 19.4 "break-it tests"; this build unit's directive names six required
cases explicitly: missing gate, corrupt manifest, budget-exceeded,
seam-discontinuity, broken build — plus empty intake, already covered by
test_full_pipeline_e2e.FrontDoorRealChainTests.test_empty_run_dir_fails_
closed_at_p1_intake_after_p0_passes).

Every case here either (a) exercises the REAL current build state (e.g. a
bare run-dir fail-closing at the first phase) or (b) reuses a real,
already-proven production function/fixture-builder from the unit that owns
it, invoked through a NEW vantage point (a mutated skill-dir copy, the real
subprocess CLI, or a deliberately hostile input) that no existing per-unit
suite already covers — never a re-implementation of another suite's fixture
or assertion logic. (All 17 phase gate scripts now exist and are committed,
so the "missing gate" fail-closed path is exercised via the synthetic
mutated-manifest fixture below, not a genuinely absent gate.)

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/e2e -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _e2e_support as sup  # noqa: E402

import state_engine  # noqa: E402

_FIXTURE_ENV = {
    "CWFE_ENVIRONMENT": "claude-code",
    "CWFE_MODEL_ARCHITECT_JUDGE": "claude-opus-4-8-fixture",
    "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
    "CWFE_MODEL_MECHANICAL_VERIFIER": "claude-haiku-4-5-fixture",
}


def _mint_nonce(run_dir: Path) -> str:
    """Mints a front-door nonce exactly the way cinematic-web-funnel-entry.sh
    does (0600 file at <run_dir>/.cwfe_run_nonce), for tests that must call
    run_cinematic_web_funnel.py directly against a MUTATED skill-dir copy
    (the real entry shell always resolves the unmutated skill dir next to
    itself, so it cannot be pointed at a corrupted manifest copy)."""
    import secrets

    nonce = secrets.token_hex(32)
    nonce_file = run_dir / ".cwfe_run_nonce"
    nonce_file.write_text(nonce, encoding="utf-8")
    nonce_file.chmod(0o600)
    return nonce


# ---------------------------------------------------------------------------
# 1) MISSING GATE
# ---------------------------------------------------------------------------
class MissingGateBreakItTests(unittest.TestCase):
    """Real case: a bare run-dir driven through the real front door fail-closes
    at the FIRST phase and never emits a certificate (all 17 gates now exist,
    so this stops on a missing upstream ARTIFACT, not a missing gate script).
    Synthetic case: a copied skill dir with an EARLIER phase's gate path
    rewritten to a nonexistent file, proving GATE-SCRIPT-MISSING fail-closed
    behavior is still generic to the mechanism, exercised even though no real
    gate is actually absent anymore."""

    def test_real_no_skip_orchestrator_run_never_certifies_a_bare_run_dir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-missinggate-real-") as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            import os

            env = dict(os.environ)
            env.update(_FIXTURE_ENV)
            result = sup.run(
                ["bash", str(sup.ENTRY_SHELL_PATH), "--run-dir", str(run_dir)], env=env, timeout=60
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((run_dir / "PROCESS-CERTIFICATE.json").exists())
            # An empty run_dir fails at P0 (no environment-receipt yet), a
            # real, early fail-closed stop. The point this case proves is
            # narrower and stronger: no certificate is EVER emitted from a
            # bare run-dir that carries none of the real upstream artifacts,
            # regardless of which phase a given run happens to fail on first.
            phase_status = json.loads((run_dir / "phase-status.json").read_text(encoding="utf-8"))
            self.assertFalse(
                any(p["status"] == "CERTIFIED" for p in phase_status["phases"]),
                msg="no phase may ever report CERTIFIED status",
            )

    def test_synthetic_missing_gate_on_a_mutated_copy_halts_with_gate_script_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-missinggate-synthetic-") as tmp:
            tmp_path = Path(tmp)
            copied_skill_dir = sup.copy_skill_dir_to_temp(tmp_path)

            manifest_path = copied_skill_dir / "CWFE-MANIFEST.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for phase in manifest["phases"]:
                if phase["id"] == "P1-INTAKE":
                    phase["gate"] = "scripts/this_gate_script_does_not_exist.py"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            run_dir = tmp_path / "run"
            run_dir.mkdir()
            nonce = _mint_nonce(run_dir)

            import os

            env = dict(os.environ)
            env.update(_FIXTURE_ENV)
            result = sup.run(
                [sup.PY, str(copied_skill_dir / "run_cinematic_web_funnel.py"),
                 "--run-dir", str(run_dir), "--nonce", nonce],
                env=env,
                timeout=60,
            )
            self.assertEqual(result.returncode, 2, msg=result.combined)  # EXIT_GATE_FAIL
            self.assertIn("GATE-SCRIPT-MISSING", result.combined)
            self.assertIn("this_gate_script_does_not_exist.py", result.combined)
            self.assertFalse((run_dir / "PROCESS-CERTIFICATE.json").exists())

            phase_status = json.loads((run_dir / "phase-status.json").read_text(encoding="utf-8"))
            statuses = {p["id"]: p["status"] for p in phase_status["phases"]}
            self.assertEqual(statuses["P0-ENVIRONMENT"], "PASS")
            self.assertEqual(statuses["P1-INTAKE"], "GATE-SCRIPT-MISSING")
            self.assertNotIn("P2-METHODOLOGY", statuses, msg="no-skip: must halt, never skip past a missing gate")


# ---------------------------------------------------------------------------
# 2) CORRUPT MANIFEST
# ---------------------------------------------------------------------------
class CorruptManifestBreakItTests(unittest.TestCase):
    """Each variant mutates a private copy of CWFE-MANIFEST.json and proves
    run_cinematic_web_funnel.py dies AF-CWFE-FRONT-DOOR (exit 3) BEFORE
    running a single phase gate — a malformed manifest must never produce a
    partial or reordered run (module docstring, _validate_manifest)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-manifest-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.copied_skill_dir = sup.copy_skill_dir_to_temp(self.tmp_path)
        self.manifest_path = self.copied_skill_dir / "CWFE-MANIFEST.json"
        self.run_dir = self.tmp_path / "run"
        self.run_dir.mkdir()
        self.nonce = _mint_nonce(self.run_dir)

    def _invoke(self) -> sup.RunResult:
        return sup.run(
            [sup.PY, str(self.copied_skill_dir / "run_cinematic_web_funnel.py"),
             "--run-dir", str(self.run_dir), "--nonce", self.nonce],
            timeout=30,
        )

    def test_invalid_json_dies_front_door(self) -> None:
        self.manifest_path.write_text("{not valid json ]][", encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("AF-CWFE-FRONT-DOOR", result.combined)
        self.assertFalse((self.run_dir / "phase-status.json").exists())
        self.assertFalse((self.run_dir / "PROCESS-CERTIFICATE.json").exists())

    def test_duplicate_af_code_across_phases_dies_front_door(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["phases"][1]["af_code"] = manifest["phases"][0]["af_code"]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("AF-CWFE-FRONT-DOOR", result.combined)
        self.assertIn("duplicate AF codes", result.combined)

    def test_non_contiguous_phase_order_dies_front_door(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["phases"][5]["order"] = 99
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("not contiguous", result.combined)

    def test_wrong_phase_count_dies_front_door(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["phases"] = manifest["phases"][:10]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("must declare exactly 17 phases", result.combined)

    def test_missing_phases_array_dies_front_door(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        del manifest["phases"]
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("no phases", result.combined)

    def test_wrong_start_or_end_phase_id_dies_front_door(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["phases"][0]["id"] = "P0-RENAMED"
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = self._invoke()
        self.assertEqual(result.returncode, 3, msg=result.combined)
        self.assertIn("do not start at P0-ENVIRONMENT", result.combined)


# ---------------------------------------------------------------------------
# 3) BUDGET-EXCEEDED
# ---------------------------------------------------------------------------
class BudgetExceededBreakItTests(unittest.TestCase):
    """Real production state_engine.ProjectState.begin_task() — the single
    spend-authorization choke point every paid-call path in this skill must
    go through (spec 10.4 "Hard-stop before the next paid call if projected
    spend exceeds the cap"). Proves the hard-stop AND that a refused call
    leaves no ledger entry behind (no partial/leaked spend record)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-budget-")
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name) / "run"
        self.run_dir.mkdir()
        self.state = state_engine.ProjectState(self.run_dir)
        self.state.create_project(
            project_id="e2e-breakit-budget-project",
            client_slug="e2e-breakit-client",
            project_slug="e2e-breakit-budget-project",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=5.00,
        )

    def test_single_call_exceeding_the_cap_is_hard_stopped_with_no_ledger_leak(self) -> None:
        with self.assertRaises(state_engine.BudgetExceeded):
            self.state.begin_task(
                provider="kie", model="kie-veo3-fast", operation="generate_video",
                params={"scene": "scene-01"}, estimated_cost_usd=5.01,
            )
        ledger = self.state.load("cost-ledger")
        self.assertEqual(ledger["entries"], [])
        self.assertEqual(ledger["cumulative_spend_usd"], 0.0)

    def test_several_queued_calls_that_jointly_exceed_the_cap_are_hard_stopped(self) -> None:
        """Spend must be hard-stopped on PROJECTED total (cumulative +
        outstanding queued/submitted/in_progress + this call's estimate),
        not merely on already-completed cumulative spend — two calls that
        are each individually affordable but jointly blow the cap must not
        both be admitted."""
        first_request_hash = self.state.compute_request_hash(
            provider="kie", model="kie-veo3-fast", operation="generate_video", params={"scene": "scene-01"}
        )
        second_request_hash = self.state.compute_request_hash(
            provider="kie", model="kie-veo3-fast", operation="generate_video", params={"scene": "scene-02"}
        )
        self.state.begin_task(
            provider="kie", model="kie-veo3-fast", operation="generate_video",
            params={"scene": "scene-01"}, estimated_cost_usd=3.00,
        )
        with self.assertRaises(state_engine.BudgetExceeded):
            self.state.begin_task(
                provider="kie", model="kie-veo3-fast", operation="generate_video",
                params={"scene": "scene-02"}, estimated_cost_usd=3.00,
            )
        ledger = self.state.load("cost-ledger")
        self.assertEqual(len(ledger["entries"]), 1, msg="only the first, affordable call may be admitted")
        self.assertEqual(ledger["entries"][0]["request_hash"], first_request_hash)
        self.assertNotEqual(
            {e["request_hash"] for e in ledger["entries"]}, {second_request_hash},
            msg="the refused, over-budget scene-02 call must never appear in the ledger",
        )

    def test_a_call_at_exactly_the_cap_is_admitted_no_off_by_one(self) -> None:
        self.state.begin_task(
            provider="kie", model="kie-veo3-fast", operation="generate_video",
            params={"scene": "scene-exact"}, estimated_cost_usd=5.00,
        )
        ledger = self.state.load("cost-ledger")
        self.assertEqual(len(ledger["entries"]), 1)


# ---------------------------------------------------------------------------
# 4) SEAM-DISCONTINUITY
# ---------------------------------------------------------------------------
class SeamDiscontinuityBreakItTests(unittest.TestCase):
    """Reuses verify_seams.py's OWN real ffmpeg fixture builders
    (_make_continuous_pair / _make_hard_cut_pair / _make_boundary_receipt —
    the exact functions its --self-test uses) to build a genuinely
    discontinuous seam-sequence.json, then drives scripts/verify_seams.py
    through the REAL subprocess CLI contract
    (`verify_seams.py --run-dir <dir>`) the orchestrator uses — a boundary
    verify_seams.py's own self_test() never exercises (it calls evaluate()
    in-process, not through a subprocess)."""

    def setUp(self) -> None:
        import verify_seams as vs  # noqa: E402

        self.vs = vs
        try:
            self.binaries = vs.mf.require_binaries()
        except vs.mf.MediaToolingUnavailable as exc:  # pragma: no cover - env-dependent
            self.skipTest(f"ffmpeg/ffprobe not available: {exc}")

        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-seam-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)

    def test_cli_subprocess_fails_closed_on_a_real_discontinuous_hard_cut_seam(self) -> None:
        cut_a, cut_b = self.vs._make_hard_cut_pair(self.tmp_path, self.binaries)
        receipt_a = self.vs._make_boundary_receipt(self.tmp_path, "cut-a", cut_a)
        receipt_b = self.vs._make_boundary_receipt(self.tmp_path, "cut-b", cut_b)
        receipt_a_path = self.tmp_path / "cut-a" / f"{cut_a.stem}.boundary-frames.json"
        receipt_b_path = self.tmp_path / "cut-b" / f"{cut_b.stem}.boundary-frames.json"
        self.assertTrue(receipt_a_path.exists() and receipt_b_path.exists())

        broken_sequence = {
            "clips": [
                {"clip_id": "scene-cut-a", "boundary_frames_path": str(receipt_a_path)},
                {"clip_id": "scene-cut-b", "boundary_frames_path": str(receipt_b_path)},
            ]
        }
        run_dir = self.tmp_path / "run"
        run_dir.mkdir()
        (run_dir / self.vs.DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(broken_sequence), encoding="utf-8")

        result = sup.run([sup.PY, "scripts/verify_seams.py", "--run-dir", str(run_dir)], cwd=sup.SKILL_DIR, timeout=60)
        self.assertNotEqual(result.returncode, 0, msg=result.combined)
        self.assertIn("P10-ENCODE-SEAM", result.combined)

        report = json.loads((run_dir / self.vs.DEFAULT_REPORT_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(report["overall_status"], self.vs.SEAM_STATUS_FAIL)
        self.assertEqual(report["seam_count"], 1)
        self.assertNotEqual(report["seams"][0]["status"], self.vs.SEAM_STATUS_PASS)

    def test_cli_subprocess_passes_on_a_real_continuous_seam_same_binaries(self) -> None:
        """Control case for the above: the SAME CLI subprocess boundary, the
        SAME clip-pair builder family, but a genuinely continuous hand-off —
        proves the CLI's fail-closed result above is a real discontinuity
        detection, not a broken CLI wrapper that always fails."""
        cont_a, cont_b = self.vs._make_continuous_pair(self.tmp_path, self.binaries)
        self.vs._make_boundary_receipt(self.tmp_path, "cont-a", cont_a)
        self.vs._make_boundary_receipt(self.tmp_path, "cont-b", cont_b)
        receipt_a_path = self.tmp_path / "cont-a" / f"{cont_a.stem}.boundary-frames.json"
        receipt_b_path = self.tmp_path / "cont-b" / f"{cont_b.stem}.boundary-frames.json"

        good_sequence = {
            "clips": [
                {"clip_id": "scene-cont-a", "boundary_frames_path": str(receipt_a_path)},
                {"clip_id": "scene-cont-b", "boundary_frames_path": str(receipt_b_path)},
            ]
        }
        run_dir = self.tmp_path / "run-good"
        run_dir.mkdir()
        (run_dir / self.vs.DEFAULT_SEQUENCE_FILENAME).write_text(json.dumps(good_sequence), encoding="utf-8")

        result = sup.run([sup.PY, "scripts/verify_seams.py", "--run-dir", str(run_dir)], cwd=sup.SKILL_DIR, timeout=60)
        self.assertEqual(result.returncode, 0, msg=result.combined)
        report = json.loads((run_dir / self.vs.DEFAULT_REPORT_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(report["overall_status"], self.vs.SEAM_STATUS_PASS)


# ---------------------------------------------------------------------------
# 5) BROKEN BUILD
# ---------------------------------------------------------------------------
class BrokenBuildBreakItTests(unittest.TestCase):
    """Real npm/tsc/next toolchain (SLOW, network for npm install). Builds
    the real U15 fixture site, injects a genuine TypeScript syntax error
    into the materialized site AFTER a clean build, then proves
    prove_site.py's real subprocess CLI independently re-runs the toolchain
    (never trusting a stale, now-inconsistent build-receipt.json) and fails
    closed — a boundary the module's own docstring calls out
    (`_independently_reverify_toolchain`) but the CLI-subprocess vantage
    point is new here."""

    def test_prove_site_cli_rejects_a_build_receipt_whose_site_now_fails_to_compile(self) -> None:
        sys.path.insert(0, str(sup.SKILL_DIR / "tests" / "fixtures" / "site-fixture"))
        import make_fixture  # noqa: E402
        import build_site as bs  # noqa: E402

        with tempfile.TemporaryDirectory(prefix="cwfe-e2e-breakit-brokenbuild-") as tmp:
            run_dir = Path(tmp) / "run"
            make_fixture.write_fixture_run_dir(run_dir)
            state = state_engine.ProjectState(run_dir)
            state.create_project(
                project_id=make_fixture.PROJECT_ID, client_slug="e2e-breakit-brokenbuild",
                project_slug=make_fixture.PROJECT_ID, deliverable_type="cinematic-landing-page",
                budget_cap_usd=25.0,
            )

            build_result = bs.build_site(run_dir, skip_toolchain=False, toolchain_timeout=600)
            self.assertEqual(build_result.receipt["status"], "pass", msg="precondition: fixture must build clean first")

            # Sanity precondition: the untouched, freshly built site really
            # does pass the gate before we break anything.
            clean_gate = sup.run([sup.PY, "scripts/prove_site.py", "--run-dir", str(run_dir)], cwd=sup.SKILL_DIR, timeout=300)
            self.assertEqual(clean_gate.returncode, 0, msg=clean_gate.combined)

            site_dir = Path(build_result.receipt["site_dir"])
            page_path = site_dir / "app" / "page.tsx"
            self.assertTrue(page_path.exists())
            original_source = page_path.read_text(encoding="utf-8")
            # A deliberate, unambiguous TypeScript syntax error — an unclosed
            # brace/paren the compiler cannot recover from.
            page_path.write_text(original_source + "\nexport function broken( {{{ this is not valid typescript\n", encoding="utf-8")

            broken_gate = sup.run([sup.PY, "scripts/prove_site.py", "--run-dir", str(run_dir)], cwd=sup.SKILL_DIR, timeout=300)
            self.assertNotEqual(broken_gate.returncode, 0, msg="prove_site.py must reject a site that no longer compiles")
            self.assertIn("P11-SITE-BUILD", broken_gate.combined)


if __name__ == "__main__":
    unittest.main()
