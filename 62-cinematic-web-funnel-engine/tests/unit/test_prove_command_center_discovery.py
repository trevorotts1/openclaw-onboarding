#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_command_center_discovery.py — offline unit tests for
scripts/prove_command_center_discovery.py (Skill 62, U23: Command Center
ZERO-CHANGE discovery proof, spec Section 2.2 "Default ruling" / Section
21.2 "Conditional Command Center changes", checklist item 24, ledger U23).

NOT a CWFE-MANIFEST.json phase gate — this module is a standalone,
repeatable prover, the same family as `funnel_engine_selector.py
--self-test` (U22), never wired into the P0-P16 run.

Fast/offline tests here exercise every piece of logic that does NOT require
Node, network, or an external `blackceo-command-center` checkout:
`onboarding_repo_root()` resolution, `sha256_file()`, `build_fixture()`
success and fail-closed paths, `validate_cc_repo()`'s five independent
fail-closed checks, `run_harness()`'s stdout/JSON parsing and pass/fail
rollup (driven entirely by a fake `subprocess.run`, never a real `node`
process), and `evaluate()`'s usage-error / pass / fail / evidence-write
paths.

The real, live proof — importing this repository's actual, unmodified,
shipped `SKILL.md` into a real, freshly-cloned `blackceo-command-center`
checkout and calling its real `matchSkillsForTask()` through the Node/tsx
harness (`scripts/lib/cc_discovery_harness.mjs`) — requires an
operator-supplied `--cc-repo` (a throwaway clone; this script never
auto-clones, never assumes, never touches the live `~/command-center/app`)
and is proven by this module's own `--self-test` plus a manual, evidence-
recording `--cc-repo <throwaway-clone> --run-dir <dir>` invocation, mirroring
the split every other toolchain-touching unit in this skill already uses
(e.g. `test_prove_site.py` / `tests/integration/test_site_build_integration.py`).
This unit's live run is a proof step, not a fixture this suite can commit to
running unattended — an automated engine-suite run must stay fully offline
and network-free like every other unit's test discovery run.

Run with:
  python3 -m unittest discover -s 62-cinematic-web-funnel-engine/tests/unit -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"

for _p in (str(_SKILL_DIR), str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prove_command_center_discovery as pccd  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class TestOnboardingRepoRoot(unittest.TestCase):
    def test_resolves_to_real_repo_root(self) -> None:
        root = pccd.onboarding_repo_root()
        self.assertTrue((root / "23-ai-workforce-blueprint" / "skill-department-map.json").exists())
        self.assertEqual(root, _SKILL_DIR.parent)

    def test_own_skill_dir_constant_points_at_this_skill(self) -> None:
        self.assertEqual(pccd._SKILL_DIR.name, "62-cinematic-web-funnel-engine")
        self.assertTrue((pccd._SKILL_DIR / "SKILL.md").exists())


class TestSha256File(unittest.TestCase):
    def test_hash_matches_hashlib_directly(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory(prefix="cwfe-u23-sha-") as tmp:
            p = Path(tmp) / "f.txt"
            p.write_bytes(b"deterministic content for U23 hashing test\n")
            expected = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(pccd.sha256_file(p), expected)

    def test_different_content_yields_different_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cwfe-u23-sha-diff-") as tmp:
            a = Path(tmp) / "a.txt"
            b = Path(tmp) / "b.txt"
            a.write_bytes(b"content a")
            b.write_bytes(b"content b")
            self.assertNotEqual(pccd.sha256_file(a), pccd.sha256_file(b))


class TestBuildFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-u23-fixture-")
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "dest"

    def test_copies_real_files_byte_identical(self) -> None:
        root = pccd.onboarding_repo_root()
        fixture_root, dept_map_copy = pccd.build_fixture(root, self.dest)

        own_src = pccd._SKILL_DIR / "SKILL.md"
        own_copy = fixture_root / pccd._SKILL_DIR.name / "SKILL.md"
        self.assertTrue(own_copy.exists())
        self.assertEqual(pccd.sha256_file(own_copy), pccd.sha256_file(own_src))

        real_map = root / "23-ai-workforce-blueprint" / "skill-department-map.json"
        self.assertTrue(dept_map_copy.exists())
        self.assertEqual(pccd.sha256_file(dept_map_copy), pccd.sha256_file(real_map))

        for neighbor in pccd._NEIGHBOR_SKILLS:
            n_src = root / neighbor / "SKILL.md"
            n_copy = fixture_root / neighbor / "SKILL.md"
            self.assertTrue(n_copy.exists(), f"missing neighbor fixture copy: {n_copy}")
            self.assertEqual(pccd.sha256_file(n_copy), pccd.sha256_file(n_src))

    def test_fails_closed_on_bogus_onboarding_root(self) -> None:
        bogus_root = Path(self._tmp.name) / "not-a-real-onboarding-checkout"
        bogus_root.mkdir()
        with self.assertRaises(pccd.DiscoveryProofError):
            pccd.build_fixture(bogus_root, self.dest / "out")

    def test_fails_closed_when_dept_map_missing(self) -> None:
        # A root that has the neighbor skill dirs and this skill's own
        # SKILL.md but no skill-department-map.json must still fail
        # closed rather than silently emitting an incomplete fixture.
        root = pccd.onboarding_repo_root()
        fake_root = Path(self._tmp.name) / "fake-root"
        (fake_root / pccd._SKILL_DIR.name).mkdir(parents=True)
        shutil.copyfile(root / pccd._SKILL_DIR.name / "SKILL.md", fake_root / pccd._SKILL_DIR.name / "SKILL.md")
        for neighbor in pccd._NEIGHBOR_SKILLS:
            (fake_root / neighbor).mkdir(parents=True)
            shutil.copyfile(root / neighbor / "SKILL.md", fake_root / neighbor / "SKILL.md")
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.build_fixture(fake_root, self.dest / "out2")
        self.assertIn("skill-department-map.json", str(ctx.exception))

    def test_fails_closed_when_neighbor_skill_missing(self) -> None:
        root = pccd.onboarding_repo_root()
        fake_root = Path(self._tmp.name) / "fake-root-no-neighbor"
        (fake_root / pccd._SKILL_DIR.name).mkdir(parents=True)
        shutil.copyfile(root / pccd._SKILL_DIR.name / "SKILL.md", fake_root / pccd._SKILL_DIR.name / "SKILL.md")
        (fake_root / "23-ai-workforce-blueprint").mkdir(parents=True)
        shutil.copyfile(
            root / "23-ai-workforce-blueprint" / "skill-department-map.json",
            fake_root / "23-ai-workforce-blueprint" / "skill-department-map.json",
        )
        # Deliberately omit every neighbor skill dir.
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.build_fixture(fake_root, self.dest / "out3")
        self.assertIn("neighbor skill fixture missing", str(ctx.exception))


class TestValidateCcRepo(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-u23-validate-")
        self.addCleanup(self._tmp.cleanup)

    def _make_shaped_repo(self, *, pkg_name: str = "mission-control", with_tsx: bool = True) -> Path:
        repo = Path(self._tmp.name) / f"cc-{pkg_name}-{with_tsx}"
        (repo / "src" / "lib").mkdir(parents=True)
        (repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (repo / "package.json").write_text(json.dumps({"name": pkg_name}), encoding="utf-8")
        if with_tsx:
            (repo / "node_modules" / "tsx").mkdir(parents=True)
        return repo

    def test_fails_closed_when_path_does_not_exist(self) -> None:
        with self.assertRaises(pccd.DiscoveryProofError):
            pccd.validate_cc_repo(Path(self._tmp.name) / "does-not-exist")

    def test_fails_closed_when_context_pack_missing(self) -> None:
        repo = Path(self._tmp.name) / "no-context-pack"
        repo.mkdir()
        (repo / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.validate_cc_repo(repo)
        self.assertIn("context-pack.ts", str(ctx.exception))

    def test_fails_closed_when_package_json_missing(self) -> None:
        repo = Path(self._tmp.name) / "no-package-json"
        (repo / "src" / "lib").mkdir(parents=True)
        (repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.validate_cc_repo(repo)
        self.assertIn("package.json", str(ctx.exception))

    def test_fails_closed_on_wrong_package_name(self) -> None:
        repo = self._make_shaped_repo(pkg_name="some-other-app")
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.validate_cc_repo(repo)
        self.assertIn("mission-control", str(ctx.exception))

    def test_fails_closed_when_tsx_absent(self) -> None:
        repo = self._make_shaped_repo(with_tsx=False)
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.validate_cc_repo(repo)
        self.assertIn("npm install", str(ctx.exception))

    def test_fails_closed_when_node_not_on_path(self) -> None:
        repo = self._make_shaped_repo()
        orig_which = shutil.which
        try:
            shutil.which = lambda name: None if name == "node" else orig_which(name)  # type: ignore[assignment]
            with self.assertRaises(pccd.DiscoveryProofError) as ctx:
                pccd.validate_cc_repo(repo)
            self.assertIn("node", str(ctx.exception))
        finally:
            shutil.which = orig_which  # type: ignore[assignment]

    def test_passes_with_bin_tsx_variant(self) -> None:
        # tsx can be present either as node_modules/tsx or node_modules/.bin/tsx
        repo = Path(self._tmp.name) / "bin-tsx-variant"
        (repo / "src" / "lib").mkdir(parents=True)
        (repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (repo / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        (repo / "node_modules" / ".bin").mkdir(parents=True)
        (repo / "node_modules" / ".bin" / "tsx").write_text("#!/bin/sh\n", encoding="utf-8")
        if shutil.which("node") is None:
            self.skipTest("node not on PATH in this environment")
        pccd.validate_cc_repo(repo)  # must not raise


class TestRunHarness(unittest.TestCase):
    """Drives run_harness()'s stdout/JSON parsing and pass/fail rollup
    entirely through a fake subprocess.run — never spawns a real `node`
    process, matching the offline-only discipline of this test file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-u23-run-harness-")
        self.addCleanup(self._tmp.cleanup)
        self.cc_repo = Path(self._tmp.name) / "fake-cc"
        (self.cc_repo / "src" / "lib").mkdir(parents=True)
        (self.cc_repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (self.cc_repo / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        (self.cc_repo / "node_modules" / "tsx").mkdir(parents=True)
        self.run_dir = Path(self._tmp.name) / "run"

        self._orig_run = subprocess.run
        self.addCleanup(lambda: setattr(subprocess, "run", self._orig_run))

    def test_clean_pass_parses_and_reports_all_checks(self) -> None:
        good = json.dumps({
            "overall": "PASS",
            "checks": [{"name": "a", "pass": True, "detail": ""}, {"name": "b", "pass": True, "detail": ""}],
        })
        subprocess.run = lambda *a, **k: _FakeCompletedProcess(good, 0)  # type: ignore[assignment]
        passed, evidence, detail = pccd.run_harness(self.cc_repo, self.run_dir)
        self.assertTrue(passed)
        self.assertEqual(evidence["overall"], "PASS")
        self.assertIn("2/2 checks passed", detail)

    def test_genuine_mismatch_reports_first_failing_check(self) -> None:
        bad = json.dumps({
            "overall": "FAIL",
            "checks": [{"name": "a", "pass": True, "detail": ""}, {"name": "b", "pass": False, "detail": "mismatch xyz"}],
        })
        subprocess.run = lambda *a, **k: _FakeCompletedProcess(bad, 1)  # type: ignore[assignment]
        passed, evidence, detail = pccd.run_harness(self.cc_repo, self.run_dir)
        self.assertFalse(passed)
        self.assertIn("b", detail)
        self.assertIn("mismatch xyz", detail)

    def test_usage_error_from_harness_raises_discovery_proof_error(self) -> None:
        usage = json.dumps({"overall": "USAGE_ERROR", "detail": "module shape drift"})
        subprocess.run = lambda *a, **k: _FakeCompletedProcess(usage, 3)  # type: ignore[assignment]
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.run_harness(self.cc_repo, self.run_dir)
        self.assertIn("module shape drift", str(ctx.exception))

    def test_empty_stdout_raises_discovery_proof_error(self) -> None:
        subprocess.run = lambda *a, **k: _FakeCompletedProcess("", 1, stderr="node crashed")  # type: ignore[assignment]
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.run_harness(self.cc_repo, self.run_dir)
        self.assertIn("no stdout", str(ctx.exception))

    def test_invalid_json_stdout_raises_discovery_proof_error(self) -> None:
        subprocess.run = lambda *a, **k: _FakeCompletedProcess("{not valid json", 1)  # type: ignore[assignment]
        with self.assertRaises(pccd.DiscoveryProofError):
            pccd.run_harness(self.cc_repo, self.run_dir)

    def test_timeout_raises_discovery_proof_error(self) -> None:
        def _raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="node", timeout=120)

        subprocess.run = _raise_timeout  # type: ignore[assignment]
        with self.assertRaises(pccd.DiscoveryProofError) as ctx:
            pccd.run_harness(self.cc_repo, self.run_dir)
        self.assertIn("timed out", str(ctx.exception))

    def test_env_never_leaks_embedding_keys_to_subprocess(self) -> None:
        captured_env = {}

        def _capture(*a, **k):
            captured_env.update(k.get("env") or {})
            good = json.dumps({"overall": "PASS", "checks": []})
            return _FakeCompletedProcess(good, 0)

        subprocess.run = _capture  # type: ignore[assignment]
        import os

        os.environ["OPENAI_API_KEY"] = "sk-should-never-reach-harness"
        try:
            pccd.run_harness(self.cc_repo, self.run_dir)
        finally:
            del os.environ["OPENAI_API_KEY"]
        self.assertNotIn("OPENAI_API_KEY", captured_env)


class TestEvaluate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cwfe-u23-evaluate-")
        self.addCleanup(self._tmp.cleanup)
        self._orig_run = subprocess.run
        self.addCleanup(lambda: setattr(subprocess, "run", self._orig_run))

    def test_no_cc_repo_is_usage_error_never_a_false_pass(self) -> None:
        run_dir = Path(self._tmp.name) / "run"
        passed, detail = pccd.evaluate(run_dir, None)
        self.assertFalse(passed)
        self.assertTrue(detail.startswith("USAGE ERROR"))
        self.assertFalse((run_dir / "cc-discovery-evidence.json").exists())

    def test_pass_writes_evidence_file(self) -> None:
        cc_repo = Path(self._tmp.name) / "fake-cc"
        (cc_repo / "src" / "lib").mkdir(parents=True)
        (cc_repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (cc_repo / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        (cc_repo / "node_modules" / "tsx").mkdir(parents=True)
        good = json.dumps({"overall": "PASS", "checks": [{"name": "a", "pass": True, "detail": ""}]})
        subprocess.run = lambda *a, **k: _FakeCompletedProcess(good, 0)  # type: ignore[assignment]

        run_dir = Path(self._tmp.name) / "run"
        passed, detail = pccd.evaluate(run_dir, cc_repo)
        self.assertTrue(passed)
        evidence_path = run_dir / "cc-discovery-evidence.json"
        self.assertTrue(evidence_path.exists())
        recorded = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(recorded["overall"], "PASS")

    def test_fail_still_writes_evidence_file(self) -> None:
        cc_repo = Path(self._tmp.name) / "fake-cc-fail"
        (cc_repo / "src" / "lib").mkdir(parents=True)
        (cc_repo / "src" / "lib" / "context-pack.ts").write_text("export {};\n", encoding="utf-8")
        (cc_repo / "package.json").write_text(json.dumps({"name": "mission-control"}), encoding="utf-8")
        (cc_repo / "node_modules" / "tsx").mkdir(parents=True)
        bad = json.dumps({"overall": "FAIL", "checks": [{"name": "a", "pass": False, "detail": "nope"}]})
        subprocess.run = lambda *a, **k: _FakeCompletedProcess(bad, 1)  # type: ignore[assignment]

        run_dir = Path(self._tmp.name) / "run"
        passed, detail = pccd.evaluate(run_dir, cc_repo)
        self.assertFalse(passed)
        self.assertTrue((run_dir / "cc-discovery-evidence.json").exists())

    def test_usage_setup_error_writes_no_evidence_file(self) -> None:
        # A setup failure (e.g. --cc-repo not a CC checkout) never reached the
        # harness at all, so there is nothing real to record — must not
        # fabricate an evidence file for a proof that never ran.
        not_cc = Path(self._tmp.name) / "not-a-cc-repo"
        not_cc.mkdir()
        run_dir = Path(self._tmp.name) / "run"
        passed, detail = pccd.evaluate(run_dir, not_cc)
        self.assertFalse(passed)
        self.assertTrue(detail.startswith("USAGE ERROR"))
        self.assertFalse((run_dir / "cc-discovery-evidence.json").exists())


class TestModuleSelfTest(unittest.TestCase):
    """The module ships its own comprehensive offline --self-test (see
    prove_command_center_discovery.py's _self_test()); this confirms it is
    callable as a library function and returns True, giving one fast
    regression tripwire without duplicating every assertion it already
    makes internally."""

    def test_self_test_passes(self) -> None:
        self.assertTrue(pccd._self_test())


if __name__ == "__main__":
    unittest.main()
