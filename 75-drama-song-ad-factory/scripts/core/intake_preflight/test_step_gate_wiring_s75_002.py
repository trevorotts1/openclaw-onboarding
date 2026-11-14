#!/usr/bin/env python3
"""S75-002: the signed step gate is wired into the control tool.

Proves, offline and behaviourally:
  (a) `next` refuses a stage whose sealed predecessor lost a file
      (PREVIOUS_STAGE_NOT_PROVEN);
  (b) the state store's completion guard refuses a COMPLETE row that the gate
      never sealed (COMPLETION_NOT_PROVEN) and the row is left untouched;
  (c) a run created before the gate (no key) keeps the old behaviour and is
      reported as legacy-run-no-gate — no key is ever added to it;
  (d) `factory.py seal` refuses a stage whose artifacts are missing, then on a
      real seal moves that stage's own row to COMPLETE and lets `next` hand out
      the stage after it.

Run: python3 -B scripts/core/intake_preflight/test_step_gate_wiring_s75_002.py
Writes only under a temp dir; no provider, no network, no other process.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path[:0] = [str(CORE), str(HERE)]

import factory  # noqa: E402
import state_store  # noqa: E402
from test_production_process import confirmed_run, complete_stage  # noqa: E402


def cli(*argv):
    """Run the published CLI in-process and return (exit code, envelope)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = factory.main(list(argv))
    return code, json.loads(out.getvalue())


class StepGateWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="s75-002-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.previous_guard = state_store.COMPLETE_GUARD
        state_store.COMPLETE_GUARD = None
        self.addCleanup(self._restore_guard)

    def _restore_guard(self):
        state_store.COMPLETE_GUARD = self.previous_guard

    def _db(self, name):
        return self.work / name / "control" / "state.sqlite3"

    def test_a_next_refuses_a_changed_sealed_predecessor(self):
        run = self.work / "run-a"
        confirmed_run(run)
        complete_stage(run, "research")
        sealed = run / "research" / "evidence.json"
        self.assertTrue(sealed.is_file(),
                        "the sealed research artifact must exist before deletion")
        sealed.unlink()
        code, env = cli("next", "--run-dir", str(run))
        self.assertEqual(env.get("outcome"), "rejected", env)
        self.assertEqual(env.get("reason_code"), "PREVIOUS_STAGE_NOT_PROVEN", env)
        self.assertEqual(env.get("data", {}).get("stage"), "creative-strategy", env)
        self.assertEqual(code, 4)

    def test_b_guard_refuses_a_complete_row_the_gate_never_sealed(self):
        run = self.work / "run-b"
        (run / "control").mkdir(parents=True)
        with state_store.Store(self._db("run-b")) as store:
            store.init_run("run-b", list(factory.CANONICAL_STAGES))
        gate, _contract = factory._step_gate()
        self.assertIsNotNone(gate, "the step gate must be installed for this unit")
        gate.cmd_init(str(run))
        factory._install_complete_guard(run)
        with state_store.Store(self._db("run-b")) as store:
            store.transition("run-b", "research", "READY", "fixture-maker")
            store.claim("run-b", "research", "fixture-maker")
            with self.assertRaises(state_store.StoreError) as caught:
                store.transition("run-b", "research", "COMPLETE", "fixture-maker")
        self.assertEqual(caught.exception.code, "COMPLETION_NOT_PROVEN")
        with state_store.Store(self._db("run-b")) as store:
            self.assertEqual(store.get("run-b", "research")["state"], "RUNNING")

    def test_c_a_run_from_before_the_gate_stays_legacy(self):
        run = self.work / "run-c"
        (run / "control").mkdir(parents=True)
        with state_store.Store(self._db("run-c")) as store:
            store.init_run("run-c", list(factory.CANONICAL_STAGES))
            store.transition("run-c", "research", "READY", "fixture-worker")
            store.claim("run-c", "research", "fixture-worker")
            store.transition("run-c", "research", "COMPLETE", "fixture-worker")
        self.assertEqual(factory._gate_init(run, {"research": "COMPLETE"}),
                         "legacy-run-no-gate")
        gate, _contract = factory._step_gate()
        self.assertFalse(Path(gate.key_path(str(run))).exists(),
                         "a legacy run must never be given a key")

    def test_d_seal_refuses_missing_artifacts_then_seals_the_row(self):
        run = self.work / "run-d"
        confirmed_run(run)
        code, env = cli("seal", "--run-dir", str(run), "--stage", "research",
                        "--maker", "fixture-maker", "--checker", "fixture-checker")
        self.assertEqual(env.get("outcome"), "rejected", env)
        self.assertEqual(env.get("reason_code"), "ARTIFACT_MISSING", env)
        with state_store.Store(self._db("run-d")) as store:
            self.assertEqual(store.get("run-d", "research")["state"], "NOT_STARTED")
        self.assertEqual(code, 4)

        (run / "research").mkdir(parents=True, exist_ok=True)
        (run / "research" / "evidence.json").write_text(json.dumps(
            {"claims": ["a measured claim from the research lane"],
             "sources": 2}), encoding="utf-8")
        (run / "research" / "manifest.json").write_text(json.dumps(
            {"files": ["evidence.json"], "digest": "sha256:fixture"}),
            encoding="utf-8")
        (run / "research" / "bundle.json").write_text(json.dumps(
            {"bundle": "the reviewed research bundle for this run",
             "items": 3}), encoding="utf-8")
        for rel in factory.STAGE_REGISTRY["research"]["required_artifacts"]:
            path = run / rel
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"fixture": "research"}), encoding="utf-8")

        code, env = cli("seal", "--run-dir", str(run), "--stage", "research",
                        "--maker", "fixture-maker", "--checker", "fixture-checker")
        self.assertEqual(env.get("outcome"), "ok", env)
        self.assertEqual(env.get("reason_code"), "stage-sealed", env)
        with state_store.Store(self._db("run-d")) as store:
            self.assertEqual(store.get("run-d", "research")["state"], "COMPLETE")

        code, env = cli("next", "--run-dir", str(run))
        self.assertEqual(env.get("outcome"), "ok", env)
        self.assertEqual(env["data"].get("stage"), "creative-strategy", env)
        self.assertEqual(env["data"].get("step_gate"), "step-gate-active", env)


if __name__ == "__main__":
    unittest.main()
