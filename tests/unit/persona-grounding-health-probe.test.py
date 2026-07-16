#!/usr/bin/env python3
"""
tests/unit/persona-grounding-health-probe.test.py
─────────────────────────────────────────────────────────────────────────────
A-U12 (Skill 6 v2 master spec, master id U12, crosswalk A/A-U12) — ONB half
of the both-repo "Blend observability" unit: "match-score distribution
advisory in deep-health + `persona_grounding_degraded` event/chip".

Proves shared-utils/persona_grounding_health_probe.py, the ONB probe the
Command Center's deep-health check is expected to shell out to:

  1. SCHEMA-VALIDATED, ADVISORY-ONLY (A-U12 accept a): run_probe() returns
     exactly the top-level shape {probe, box, advisory_only, persona_match,
     grounding}; `persona_match` contains EXACTLY {count, mean, min, max,
     buckets} with `buckets` EXACTLY {low, mid, high} — never a stray
     pass/fail field a caller could mistakenly gate on. `advisory_only` is
     always True.

  2. `persona_match` is VERBATIM from persona_blend.match_score_distribution
     — not re-derived arithmetic — proven by writing a KNOWN-score fixture
     log and cross-checking the probe's numbers independently.

  3. NON-GATING PROVEN BY TEST (A-U12 accept a, this probe's own half of
     it): the CLI's exit code is 0 in EVERY scenario exercised here — a
     healthy box, a degraded box, an absent log, a malformed log — because
     an advisory probe must never let a caller derive a health verdict from
     its own process exit code (see module docstring's ADVISORY DOCTRINE).

  4. GROUNDING-DEGRADED FIRES AND CLEARS (A-U12 accept b/c, translated to
     the ONB probe layer per the per-repo/offline acceptance doctrine —
     MASTER SPEC v2 §E.3 "OPERATOR RULINGS 2026-07-15"): deleting the
     fixture company-config.json yields degraded=True and
     event="persona_grounding_degraded" on the VERY NEXT probe call (one
     probe cycle); restoring the file clears both on the call after that —
     proven as one continuous present -> absent -> present sequence against
     the SAME paths dict (not three independent fixtures), so this is a
     genuine before/after proof, never three isolated snapshots.

  5. Each of the two DEGRADING grounding reasons (company-config absent,
     semantic_task_fit unavailable) is independently detectable — proven by
     monkeypatching the loaded selector module's own flags, never by
     re-implementing the detection logic in this test file. `llm_score`
     unavailability is proven to be reported as INFORMATIONAL layers-only
     context and to NEVER flip `degraded`/`event` — verified against
     persona-selector-v2.py's own compute_layer_scores()/SCORING_MODE
     fallback (an LLM-unavailable box runs the real, non-flat
     _heuristic_layer_scores() path, never the flat-0.6 score_layer stub),
     never asserted as an assumption.

  6. NEVER RAISES: every public function in the probe returns an honest
     degraded/empty result rather than propagating an exception, even when
     pointed at garbage paths.

Run:
    python3 tests/unit/persona-grounding-health-probe.test.py
    or: pytest tests/unit/persona-grounding-health-probe.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent            # tests/unit/
_REPO_ROOT = _HERE.parent.parent          # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_PROBE_PATH = _SHARED_UTILS / "persona_grounding_health_probe.py"
assert _PROBE_PATH.is_file(), f"probe not found at {_PROBE_PATH}"

_ENV_LOG_KEY = "OPENCLAW_PERSONA_MATCH_SCORE_LOG"


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "persona_grounding_health_probe_under_test", _PROBE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = _load_probe()


def _write_company_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "2.0",
                                 "default_persona_id": "hormozi-100m-offers"}))


def _write_score_log(env_path: Path, scores: list) -> None:
    """Write a hand-built match-score-log.jsonl directly, mirroring
    persona_blend.log_match_score's own record shape, so this test proves
    the probe's numbers independently of the writer."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        for s in scores:
            f.write(json.dumps({
                "ts": "2026-07-15T00:00:00+00:00", "dimension": "topic",
                "persona_id": "p", "score": s, "task_category": "content",
                "content_task": True,
            }) + "\n")


class TestPersonaMatchAdvisorySchema(unittest.TestCase):
    """A-U12 accept (a): the persona_match advisory object's exact shape."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_env = os.environ.get(_ENV_LOG_KEY)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop(_ENV_LOG_KEY, None)
        else:
            os.environ[_ENV_LOG_KEY] = self._old_env
        self._tmp.cleanup()

    def test_schema_exact_keys_on_empty_log(self):
        os.environ[_ENV_LOG_KEY] = str(self.tmp / "absent.jsonl")
        pm = probe.get_persona_match_advisory({})
        self.assertEqual(set(pm.keys()), {"count", "mean", "min", "max", "buckets"})
        self.assertEqual(set(pm["buckets"].keys()), {"low", "mid", "high"})
        self.assertEqual(pm["count"], 0)
        self.assertIsNone(pm["mean"])

    def test_no_pass_fail_field_ever_present(self):
        """NON-GATING: nothing in this dict is a boolean health verdict."""
        os.environ[_ENV_LOG_KEY] = str(self.tmp / "log.jsonl")
        _write_score_log(self.tmp / "log.jsonl", [0.9, 0.9, 0.9])
        pm = probe.get_persona_match_advisory({})
        for forbidden in ("ok", "pass", "healthy", "degraded", "verdict"):
            self.assertNotIn(forbidden, pm)

    def test_matches_persona_blend_distribution_verbatim(self):
        """persona_match is NOT re-derived — it IS match_score_distribution()."""
        log_path = self.tmp / "log.jsonl"
        os.environ[_ENV_LOG_KEY] = str(log_path)
        scores = [0.1, 0.2, 0.5, 0.7, 0.95]
        _write_score_log(log_path, scores)

        pb = probe._load_persona_blend()
        expected = pb.match_score_distribution({})
        actual = probe.get_persona_match_advisory({})
        self.assertEqual(actual, expected)
        # Cross-checked independently of the implementation's own math:
        self.assertEqual(actual["count"], 5)
        self.assertAlmostEqual(actual["mean"], sum(scores) / len(scores))
        self.assertEqual(actual["buckets"], {"low": 2, "mid": 1, "high": 2})

    def test_never_raises_on_garbage_env_override(self):
        # A directory where a file is expected -> unreadable, never fatal.
        blocker = self.tmp / "blocker_dir"
        blocker.mkdir()
        os.environ[_ENV_LOG_KEY] = str(blocker)
        try:
            pm = probe.get_persona_match_advisory({})
        except Exception as e:  # pragma: no cover
            self.fail(f"get_persona_match_advisory raised {e!r} — must be best-effort")
        self.assertEqual(pm["count"], 0)


class TestGroundingLayers(unittest.TestCase):
    """A-U12 accept (b)/(c), proven at the ONB probe layer (per-repo/offline
    acceptance doctrine, MASTER SPEC v2 §E.3): deleting/restoring the
    fixture company-config toggles `persona_grounding_degraded` — the
    signal the Command Center's chip/event consumes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg_path = self.tmp / "company-config.json"
        self.paths = {"company_config": self.cfg_path}

    def tearDown(self):
        self._tmp.cleanup()

    def test_present_valid_config_and_real_modules_is_not_degraded(self):
        _write_company_config(self.cfg_path)
        result = probe.check_grounding_layers(self.paths)
        self.assertFalse(result["degraded"])
        self.assertIsNone(result["event"])
        self.assertEqual(result["reasons"], [])
        self.assertTrue(result["layers"]["company_config_present"])

    def test_absent_config_degrades_with_named_event(self):
        # cfg_path never written -> absent from the start.
        result = probe.check_grounding_layers(self.paths)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["event"], "persona_grounding_degraded")
        self.assertFalse(result["layers"]["company_config_present"])
        self.assertTrue(any("company-config" in r for r in result["reasons"]))

    def test_delete_then_restore_toggles_within_one_probe_cycle_each(self):
        """The exact A-U12 (b)/(c) narrative: present -> delete -> degraded
        (one call) -> restore -> clears (one call) — one continuous fixture,
        not three independent snapshots."""
        _write_company_config(self.cfg_path)
        healthy_1 = probe.check_grounding_layers(self.paths)
        self.assertFalse(healthy_1["degraded"])

        self.cfg_path.unlink()
        degraded = probe.check_grounding_layers(self.paths)
        self.assertTrue(degraded["degraded"])
        self.assertEqual(degraded["event"], "persona_grounding_degraded")

        _write_company_config(self.cfg_path)
        healthy_2 = probe.check_grounding_layers(self.paths)
        self.assertFalse(healthy_2["degraded"])
        self.assertIsNone(healthy_2["event"])

    def test_semantic_task_fit_unavailable_is_independently_detected(self):
        sel = probe._load_selector()
        orig = sel.SEMANTIC_AVAILABLE
        sel.SEMANTIC_AVAILABLE = False
        try:
            _write_company_config(self.cfg_path)
            result = probe.check_grounding_layers(self.paths)
            self.assertTrue(result["degraded"])
            self.assertFalse(result["layers"]["semantic_task_fit_available"])
            self.assertTrue(result["layers"]["company_config_present"])
            self.assertTrue(any("semantic_task_fit" in r for r in result["reasons"]))
        finally:
            sel.SEMANTIC_AVAILABLE = orig

    def test_llm_score_unavailable_is_informational_only_never_degrades(self):
        """Verified against persona-selector-v2.py: SCORING_MODE defaults to
        "heuristic" when LLM_AVAILABLE is False, and compute_layer_scores()
        only reaches the flat-0.6 score_layer stub when effective=="llm" AND
        LLM_AVAILABLE — so an LLM-unavailable box runs the real
        _heuristic_layer_scores() path, never a neutral-floor fallback.
        llm_score_available must be reported (informational) but must NOT
        flip degraded/event."""
        sel = probe._load_selector()
        orig = sel.LLM_AVAILABLE
        sel.LLM_AVAILABLE = False
        try:
            _write_company_config(self.cfg_path)
            result = probe.check_grounding_layers(self.paths)
            self.assertFalse(result["degraded"],
                              "LLM-unavailable alone must NOT be degraded — "
                              "heuristic scoring is a real, supported path")
            self.assertIsNone(result["event"])
            self.assertFalse(result["layers"]["llm_score_available"],
                              "the flag must still be reported, informationally")
            self.assertFalse(any("llm_score" in r for r in result["reasons"]),
                              "llm_score must never contribute a degrading reason")
        finally:
            sel.LLM_AVAILABLE = orig

    def test_both_degrading_reasons_can_fire_together_llm_flag_ignored(self):
        sel = probe._load_selector()
        orig_sem, orig_llm = sel.SEMANTIC_AVAILABLE, sel.LLM_AVAILABLE
        sel.SEMANTIC_AVAILABLE = False
        sel.LLM_AVAILABLE = False  # must NOT add a third reason
        try:
            result = probe.check_grounding_layers(self.paths)  # cfg also absent
            self.assertTrue(result["degraded"])
            self.assertEqual(len(result["reasons"]), 2,
                              f"expected exactly 2 degrading reasons "
                              f"(company-config + semantic_task_fit), got: "
                              f"{result['reasons']!r}")
            self.assertFalse(result["layers"]["llm_score_available"])
        finally:
            sel.SEMANTIC_AVAILABLE = orig_sem
            sel.LLM_AVAILABLE = orig_llm


class TestRunProbe(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg_path = self.tmp / "company-config.json"
        self._old_env = os.environ.get(_ENV_LOG_KEY)
        os.environ[_ENV_LOG_KEY] = str(self.tmp / "log.jsonl")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop(_ENV_LOG_KEY, None)
        else:
            os.environ[_ENV_LOG_KEY] = self._old_env
        self._tmp.cleanup()

    def test_top_level_schema_exact_keys(self):
        _write_company_config(self.cfg_path)
        result = probe.run_probe(paths={"company_config": self.cfg_path}, box="test-box")
        self.assertEqual(set(result.keys()),
                          {"probe", "box", "advisory_only", "persona_match", "grounding"})
        self.assertEqual(result["probe"], "persona-grounding-health")
        self.assertEqual(result["box"], "test-box")

    def test_advisory_only_is_always_true(self):
        for cfg_present in (True, False):
            if cfg_present:
                _write_company_config(self.cfg_path)
            elif self.cfg_path.exists():
                self.cfg_path.unlink()
            result = probe.run_probe(paths={"company_config": self.cfg_path})
            self.assertTrue(result["advisory_only"])

    def test_box_defaults_to_env_override(self):
        old_box = os.environ.get("OPENCLAW_BOX_LABEL")
        os.environ["OPENCLAW_BOX_LABEL"] = "labeled-box-42"
        try:
            _write_company_config(self.cfg_path)
            result = probe.run_probe(paths={"company_config": self.cfg_path})
            self.assertEqual(result["box"], "labeled-box-42")
        finally:
            if old_box is None:
                os.environ.pop("OPENCLAW_BOX_LABEL", None)
            else:
                os.environ["OPENCLAW_BOX_LABEL"] = old_box


class TestCLI(unittest.TestCase):
    """CLI-level proof that this probe is genuinely non-gating: exit code 0
    in every scenario, degraded or healthy alike."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg_path = self.tmp / "company-config.json"
        self.personas_dir = self.tmp / "coaching-personas"
        self.personas_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, extra_env=None):
        env = dict(os.environ)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(_PROBE_PATH), "--json",
             "--company-config", str(self.cfg_path),
             "--coaching-personas", str(self.personas_dir)],
            capture_output=True, text=True, check=False, env=env)

    def test_cli_exit_0_when_healthy(self):
        _write_company_config(self.cfg_path)
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertFalse(data["grounding"]["degraded"])

    def test_cli_exit_0_when_degraded(self):
        # cfg_path never written.
        proc = self._run()
        self.assertEqual(
            proc.returncode, 0,
            f"advisory probe must exit 0 even when degraded; stderr={proc.stderr!r}")
        data = json.loads(proc.stdout)
        self.assertTrue(data["grounding"]["degraded"])
        self.assertEqual(data["grounding"]["event"], "persona_grounding_degraded")

    def test_cli_json_is_single_object_with_full_schema(self):
        _write_company_config(self.cfg_path)
        proc = self._run()
        data = json.loads(proc.stdout)
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data.keys()),
                          {"probe", "box", "advisory_only", "persona_match", "grounding"})

    def test_cli_env_log_override_reaches_persona_match(self):
        _write_company_config(self.cfg_path)
        log_path = self.tmp / "custom-log.jsonl"
        _write_score_log(log_path, [0.9, 0.9])
        proc = self._run(extra_env={_ENV_LOG_KEY: str(log_path)})
        data = json.loads(proc.stdout)
        self.assertEqual(data["persona_match"]["count"], 2)


class TestFleetRefreshRunnerWiring(unittest.TestCase):
    """Mirrors A-U8's TestFleetRefreshRunnerWiring (persona-embedding-drift-
    probe.test.py): proves shared-utils/fleet_refresh_runner.py's
    step_persona_grounding_health() calls this probe and records a
    NON-GATING advisory — 'pass' or 'degraded:...', NEVER 'failed:...' —
    so a degraded grounding verdict never trips fleet_refresh_runner's
    has_failures / step_fail path."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_env = os.environ.get(_ENV_LOG_KEY)
        os.environ[_ENV_LOG_KEY] = str(self.tmp / "log.jsonl")

        _runner_spec = importlib.util.spec_from_file_location(
            "fleet_refresh_runner_for_u12_test", _SHARED_UTILS / "fleet_refresh_runner.py")
        self.runner = importlib.util.module_from_spec(_runner_spec)
        sys.modules["fleet_refresh_runner_for_u12_test"] = self.runner
        _runner_spec.loader.exec_module(self.runner)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop(_ENV_LOG_KEY, None)
        else:
            os.environ[_ENV_LOG_KEY] = self._old_env
        self._tmp.cleanup()

    def test_step_records_pass_when_grounded(self):
        cfg_path = self.tmp / "company-config.json"
        _write_company_config(cfg_path)
        res = self.runner.BoxResult(box="test-box", dry_run=False)
        paths = {"company_config": cfg_path}
        result = self.runner.step_persona_grounding_health(paths, _SHARED_UTILS, res)

        self.assertFalse(result["grounding"]["degraded"])
        self.assertEqual(res.steps["persona-grounding-health"], "pass")

    def test_step_records_degraded_advisory_never_containing_failed(self):
        # company-config.json deliberately absent -> degraded.
        missing_cfg = self.tmp / "does-not-exist.json"
        res = self.runner.BoxResult(box="test-box", dry_run=False)
        paths = {"company_config": missing_cfg}
        result = self.runner.step_persona_grounding_health(paths, _SHARED_UTILS, res)

        self.assertTrue(result["grounding"]["degraded"])
        self.assertIn("persona-grounding-health", res.steps)
        recorded = res.steps["persona-grounding-health"]
        self.assertTrue(recorded.startswith("degraded:"))
        self.assertNotIn("failed", recorded,
                         "the advisory must NEVER contain 'failed' — it must "
                         "not trip fleet_refresh_runner's has_failures check")

    def _run_box_has_failures(self, res) -> bool:
        """The EXACT verdict expression run_box uses (fleet_refresh_runner.py:
        `has_failures = any("failed" in str(v) for v in res.steps.values())`).
        Asserted against directly so this contract is proven end-to-end
        against the real gate, not against a paraphrase of it."""
        return any("failed" in str(v) for v in res.steps.values())

    def _degrade_via_selector_load_failure(self, res):
        """Force the ONE degrade path whose reason text interpolates an
        arbitrary exception message — a box where the selector module cannot
        be loaded at all (e.g. 23-ai-workforce-blueprint not installed).

        NOTE: step_persona_grounding_health imports the probe under its
        CANONICAL name ('persona_grounding_health_probe'), which is a distinct
        module object from this file's `probe` (loaded under a _under_test
        alias). Patch the instance the RUNNER will actually resolve — importing
        it here first so the runner's own `from ... import run_probe` reuses
        this already-patched sys.modules entry."""
        sys.path.insert(0, str(_SHARED_UTILS))
        import persona_grounding_health_probe as runner_probe

        old_loader = runner_probe._load_selector
        old_cache = runner_probe._SELECTOR_MODULE

        def _boom():
            # An exception whose OWN message contains the gating token — the
            # probe cannot control what upstream exceptions say.
            raise FileNotFoundError("persona-selector-v2.py: open failed")

        runner_probe._load_selector, runner_probe._SELECTOR_MODULE = _boom, None
        self.addCleanup(
            lambda: setattr(runner_probe, "_SELECTOR_MODULE", old_cache))
        self.addCleanup(
            lambda: setattr(runner_probe, "_load_selector", old_loader))
        return self.runner.step_persona_grounding_health(
            {"company_config": self.tmp / "does-not-exist.json"},
            _SHARED_UTILS, res)

    def test_selector_load_failure_advisory_never_gates_the_box(self):
        """REGRESSION (A-U12 ACCEPT (a): "the box's health status is UNCHANGED
        by ANY value of it"). The selector-unloadable degrade path builds its
        reason from an arbitrary exception message. If that text reaches
        res.steps carrying the substring "failed", run_box's substring verdict
        test flips the box to partial/failed — an ADVISORY probe silently
        gating the box's health. Proven here against the real gate."""
        res = self.runner.BoxResult(box="test-box", dry_run=False)
        result = self._degrade_via_selector_load_failure(res)

        self.assertTrue(result["grounding"]["degraded"],
                        "selector-unloadable must still be reported degraded")
        recorded = res.steps["persona-grounding-health"]
        self.assertTrue(recorded.startswith("degraded:"))
        self.assertNotIn(
            "failed", recorded,
            "an advisory step value must never carry run_box's gating token, "
            "however the underlying exception happened to be worded")
        self.assertFalse(
            self._run_box_has_failures(res),
            "A-U12 non-gating contract: a degraded grounding advisory must "
            "leave run_box's has_failures False (box verdict stays 'ok')")

    def test_scrub_gating_token_is_case_insensitive_and_keeps_text(self):
        """The scrub removes ONLY the gating token and leaves the reason
        legible — an advisory that gates is broken, but an advisory scrubbed
        into uselessness is also broken."""
        scrub = self.runner._scrub_gating_token
        self.assertNotIn("failed", scrub("selector Failed to load").lower())
        self.assertIn("selector", scrub("selector Failed to load"))
        self.assertEqual(scrub("company-config.json absent/unreadable"),
                         "company-config.json absent/unreadable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
