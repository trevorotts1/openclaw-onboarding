#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_resolve_execution_environment.py — unit tests for build unit U3
(scripts/resolve_execution_environment.py + scripts/prove_p0_environment.py).

stdlib unittest only (no pytest dependency assumed). Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
or directly:
  python3 62-cinematic-web-funnel-engine/tests/unit/test_resolve_execution_environment.py -v

Covers, per the U3 directive:
  - fail-closed environment detection (undetected / unknown override)
  - Claude Code role/alias mapping (Opus/Sonnet/Haiku)
  - Codex role/alias mapping (SOL/TERRA/LUNA)
  - required-role actual-model resolution never silently defaults
  - architect_judge NEVER receives an automatic capability fallback
  - mechanical_verifier/documentation_writer MAY receive an explicit,
    recorded capability fallback only when the operator opts in
  - builder and judge must be provably different models, with a non-silent,
    reasoned override escape hatch
  - role-config cannot silently downgrade a required role
  - environment-receipt.json is written correctly via the CLI and via the
    prove_p0_environment.py phase-gate wrapper (subprocess + evaluate())
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import resolve_execution_environment as ree  # noqa: E402
import prove_p0_environment as p0  # noqa: E402

PY = sys.executable or "python3"
RESOLVER_PATH = _SCRIPTS_DIR / "resolve_execution_environment.py"
GATE_PATH = _SCRIPTS_DIR / "prove_p0_environment.py"

FULL_CLAUDE_ENV = {
    "CLAUDECODE": "1",
    "CWFE_MODEL_ARCHITECT_JUDGE": "claude-opus-4-8-fixture",
    "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
    "CWFE_MODEL_MECHANICAL_VERIFIER": "claude-haiku-4-5-fixture",
}

FULL_CODEX_ENV = {
    "CWFE_ENVIRONMENT": "codex",
    "CWFE_MODEL_ARCHITECT_JUDGE": "sol-fixture-model",
    "CWFE_MODEL_BUILDER": "terra-fixture-model",
    "CWFE_MODEL_MECHANICAL_VERIFIER": "luna-fixture-model",
}


class TestEnvironmentDetection(unittest.TestCase):
    def test_undetected_when_no_signal_and_no_override(self):
        r = ree.resolve(env={})
        self.assertEqual(r["environment"]["name"], "undetected")
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any("ENV-UNDETECTED" in x for x in r["failure_reasons"]))

    def test_unknown_explicit_override_raises_usage_error(self):
        with self.assertRaises(ree.UsageError):
            ree.resolve(environment_override="gpt-5-cli", env={})

    def test_unknown_env_var_override_raises_usage_error(self):
        with self.assertRaises(ree.UsageError):
            ree.resolve(env={"CWFE_ENVIRONMENT": "not-a-real-environment"})

    def test_claude_code_autodetects_from_signal_env_var(self):
        r = ree.resolve(env={"CLAUDECODE": "1"})
        self.assertEqual(r["environment"]["name"], "claude-code")
        self.assertFalse(r["environment"]["explicit_override"])

    def test_codex_autodetects_from_signal_env_var(self):
        r = ree.resolve(env={"CODEX_HOME": "/some/path"})
        self.assertEqual(r["environment"]["name"], "codex")

    def test_explicit_override_wins_over_autodetect_signal(self):
        r = ree.resolve(environment_override="codex", env={"CLAUDECODE": "1"})
        self.assertEqual(r["environment"]["name"], "codex")
        self.assertTrue(r["environment"]["explicit_override"])


class TestRoleAliasMapping(unittest.TestCase):
    def test_claude_code_maps_opus_sonnet_haiku(self):
        r = ree.resolve(env=FULL_CLAUDE_ENV)
        self.assertEqual(r["roles"]["architect_judge"]["alias"], "Opus")
        self.assertEqual(r["roles"]["builder"]["alias"], "Sonnet")
        self.assertEqual(r["roles"]["mechanical_verifier"]["alias"], "Haiku")
        self.assertEqual(r["roles"]["documentation_writer"]["alias"], "Fable")
        self.assertFalse(r["roles"]["documentation_writer"]["required"])

    def test_codex_maps_sol_terra_luna(self):
        r = ree.resolve(env=FULL_CODEX_ENV)
        self.assertEqual(r["roles"]["architect_judge"]["alias"], "SOL")
        self.assertEqual(r["roles"]["builder"]["alias"], "TERRA")
        self.assertEqual(r["roles"]["mechanical_verifier"]["alias"], "LUNA")
        self.assertEqual(r["status"], "PASS")

    def test_role_config_overrides_alias_string(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "role-config.json"
            cfg_path.write_text(json.dumps({"claude-code": {"builder": {"alias": "Sonnet-Custom"}}}), encoding="utf-8")
            r = ree.resolve(env=FULL_CLAUDE_ENV, role_config_path=str(cfg_path))
            self.assertEqual(r["roles"]["builder"]["alias"], "Sonnet-Custom")
            self.assertEqual(r["roles"]["builder"]["alias_source"], "role-config")

    def test_role_config_cannot_downgrade_required_role(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "role-config.json"
            cfg_path.write_text(
                json.dumps({"claude-code": {"architect_judge": {"required": False}}}), encoding="utf-8"
            )
            r = ree.resolve(env={"CLAUDECODE": "1"}, role_config_path=str(cfg_path))
            self.assertTrue(r["roles"]["architect_judge"]["required"])
            self.assertTrue(any("BLOCKED" in note for note in r["notes"]))

    def test_role_config_missing_file_is_usage_error(self):
        with self.assertRaises(ree.UsageError):
            ree.resolve(env=FULL_CLAUDE_ENV, role_config_path="/nonexistent/path/role-config.json")


class TestActualModelResolution(unittest.TestCase):
    def test_required_role_unresolved_fails_closed_no_default_guessed(self):
        r = ree.resolve(env={"CLAUDECODE": "1"})
        for role in ("architect_judge", "builder", "mechanical_verifier"):
            self.assertIsNone(r["roles"][role]["actual_model"])
            self.assertFalse(r["roles"][role]["resolved"])
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any("ROLE-MODEL-UNRESOLVED" in x for x in r["failure_reasons"]))

    def test_resolution_file_takes_priority_over_env_var(self):
        with tempfile.TemporaryDirectory() as td:
            res_path = Path(td) / "resolution.json"
            res_path.write_text(json.dumps({"builder": "from-resolution-file"}), encoding="utf-8")
            env = dict(FULL_CLAUDE_ENV)
            env["CWFE_MODEL_BUILDER"] = "from-env-var"
            r = ree.resolve(env=env, resolution_file_path=str(res_path))
            self.assertEqual(r["roles"]["builder"]["actual_model"], "from-resolution-file")
            self.assertEqual(r["roles"]["builder"]["actual_model_source"], "resolution-file")

    def test_resolution_file_missing_is_usage_error(self):
        with self.assertRaises(ree.UsageError):
            ree.resolve(env=FULL_CLAUDE_ENV, resolution_file_path="/nonexistent/resolution.json")

    def test_documentation_writer_optional_role_does_not_block_pass(self):
        r = ree.resolve(env=FULL_CLAUDE_ENV)
        self.assertFalse(r["roles"]["documentation_writer"]["resolved"])
        self.assertEqual(r["status"], "PASS")


class TestArchitectJudgeNeverSilentlySubstituted(unittest.TestCase):
    def test_no_automatic_fallback_for_architect_judge_even_with_flag(self):
        env = {
            "CLAUDECODE": "1",
            "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
            "CWFE_MODEL_MECHANICAL_VERIFIER": "claude-haiku-4-5-fixture",
        }
        r = ree.resolve(env=env, allow_capability_fallback=True)
        self.assertIsNone(r["roles"]["architect_judge"]["actual_model"])
        self.assertFalse(r["roles"]["architect_judge"]["fallback_used"])
        self.assertEqual(r["status"], "FAIL")

    def test_architect_judge_not_in_fallback_eligible_roles(self):
        self.assertNotIn("architect_judge", ree.FALLBACK_ELIGIBLE_ROLES)


class TestCapabilityFallbackForNonJudgeRoles(unittest.TestCase):
    def test_mechanical_verifier_fallback_requires_explicit_flag(self):
        env = {
            "CLAUDECODE": "1",
            "CWFE_MODEL_ARCHITECT_JUDGE": "claude-opus-4-8-fixture",
            "CWFE_MODEL_BUILDER": "claude-sonnet-5-fixture",
        }
        r_no_flag = ree.resolve(env=env, allow_capability_fallback=False)
        self.assertEqual(r_no_flag["status"], "FAIL")
        self.assertFalse(r_no_flag["roles"]["mechanical_verifier"]["fallback_used"])

        r_with_flag = ree.resolve(env=env, allow_capability_fallback=True)
        self.assertEqual(r_with_flag["status"], "PASS")
        mv = r_with_flag["roles"]["mechanical_verifier"]
        self.assertTrue(mv["fallback_used"])
        self.assertEqual(mv["fallback_from"], "builder")
        self.assertEqual(mv["actual_model"], "claude-sonnet-5-fixture")
        self.assertTrue(any("CAPABILITY-FALLBACK" in note for note in r_with_flag["notes"]))


class TestBuilderJudgeDistinctness(unittest.TestCase):
    def test_distinct_models_pass_and_record_distinct_true(self):
        r = ree.resolve(env=FULL_CLAUDE_ENV)
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["builder_judge_distinctness"]["distinct"])

    def test_identical_models_fail_closed_without_acknowledgement(self):
        env = dict(FULL_CLAUDE_ENV)
        env["CWFE_MODEL_BUILDER"] = env["CWFE_MODEL_ARCHITECT_JUDGE"]
        r = ree.resolve(env=env)
        self.assertEqual(r["status"], "FAIL")
        self.assertFalse(r["builder_judge_distinctness"]["distinct"])
        self.assertTrue(any("BUILDER-JUDGE-COLLISION" in x for x in r["failure_reasons"]))

    def test_identical_models_bare_flag_without_reason_still_fails(self):
        env = dict(FULL_CLAUDE_ENV)
        env["CWFE_MODEL_BUILDER"] = env["CWFE_MODEL_ARCHITECT_JUDGE"]
        r = ree.resolve(env=env, acknowledge_same_model_builder_judge=True, same_model_reason="")
        self.assertEqual(r["status"], "FAIL", "a bare flag flip with no reason must not silently pass")

    def test_identical_models_pass_with_explicit_reasoned_acknowledgement(self):
        env = dict(FULL_CLAUDE_ENV)
        env["CWFE_MODEL_BUILDER"] = env["CWFE_MODEL_ARCHITECT_JUDGE"]
        r = ree.resolve(
            env=env,
            acknowledge_same_model_builder_judge=True,
            same_model_reason="fixture: single-model roster deliberately tested",
        )
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["builder_judge_distinctness"]["override_acknowledged"])
        self.assertEqual(
            r["builder_judge_distinctness"]["override_reason"],
            "fixture: single-model roster deliberately tested",
        )


class TestCliSubprocessAndExitCodes(unittest.TestCase):
    def _run_cli(self, env_overrides, extra_args=None):
        import os

        full_env = dict(os.environ)
        full_env.update(env_overrides)
        # Strip signal vars from a claude-code test session so tests requesting
        # "undetected" behave deterministically regardless of the outer harness.
        for var in ree.DEFAULT_CLAUDE_SIGNAL_VARS + ree.DEFAULT_CODEX_SIGNAL_VARS:
            full_env.pop(var, None)
        full_env.update(env_overrides)
        args = [PY, str(RESOLVER_PATH)] + (extra_args or [])
        return subprocess.run(args, capture_output=True, text=True, env=full_env)

    def test_cli_self_test_exits_zero(self):
        proc = subprocess.run([PY, str(RESOLVER_PATH), "--self-test"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_cli_pass_scenario_exit_zero_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self._run_cli(FULL_CLAUDE_ENV, ["--run-dir", td])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            receipt_path = Path(td) / "environment-receipt.json"
            self.assertTrue(receipt_path.is_file())
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["roles"]["architect_judge"]["actual_model"], "claude-opus-4-8-fixture")

    def test_cli_fail_scenario_exit_two_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            proc = self._run_cli({"CLAUDECODE": "1"}, ["--run-dir", td])
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            receipt_path = Path(td) / "environment-receipt.json"
            self.assertTrue(receipt_path.is_file())
            data = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "FAIL")
            self.assertEqual(data["af_code"], "AF-CWFE-P0-ENVIRONMENT")

    def test_cli_usage_error_exit_three(self):
        proc = self._run_cli(FULL_CLAUDE_ENV, ["--role-config", "/nonexistent/role-config.json"])
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)


class TestProveP0EnvironmentGate(unittest.TestCase):
    def test_evaluate_pass_writes_receipt_and_returns_true(self):
        import os

        with tempfile.TemporaryDirectory() as td:
            saved = {}
            for k, v in FULL_CLAUDE_ENV.items():
                saved[k] = os.environ.get(k)
                os.environ[k] = v
            try:
                passed, detail = p0.evaluate(Path(td))
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertTrue(passed, detail)
            self.assertTrue((Path(td) / "environment-receipt.json").is_file())

    def test_gate_cli_matches_orchestrator_invocation_contract(self):
        """run_cinematic_web_funnel.py's _run_phase_gate calls exactly
        `python3 <gate> --run-dir <run_dir>` and treats returncode == 0 as
        PASS. Prove the gate script honors that exact contract."""
        import os

        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ)
            env.update(FULL_CODEX_ENV)
            proc = subprocess.run(
                [PY, str(GATE_PATH), "--run-dir", td],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((Path(td) / "environment-receipt.json").is_file())

    def test_gate_cli_nonexistent_run_dir_is_usage_error(self):
        proc = subprocess.run(
            [PY, str(GATE_PATH), "--run-dir", "/nonexistent/run/dir/for/u3/tests"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
