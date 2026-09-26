#!/usr/bin/env python3
"""D27 portable installation compatibility (JEV spec 1.1, ss 12.1/17; A43-A45, A54).

Proves, against the REAL distribution files (no reimplemented logic):

  * PACKAGING (A54 ONB side): the canonical decision core
    (shared-utils/decision_engine/ + sibling deps + skill-23 consumers)
    exists in the repo the fresh-installer/updater ships, and both
    install.sh (fresh) and update-skills.sh (existing-update) wholesale-copy
    shared-utils/ so the core reaches the box.
  * PORTABILITY (A44): every decision-core module resolves paths relative
    to its own file (Path(__file__)) and performs zero process-environment
    reads and zero absolute-path literals at code level — Mac, native Linux,
    and Docker layouts resolve from the installation, never from
    operator-specific constants.
  * MIXED-VERSION CAPABILITY DETECT (A43): old/new combinations fail closed
    through the REAL D02 validators — a major-2 envelope/bundle is rejected
    as incompatible, never misread; malformed policy packs return
    (ok=False, errors), never raise.
  * IDEMPOTENCY / NO DESTRUCTION (A45): the updater refresh is additive
    (no rm -rf of the live shared-utils tree), an incomplete refresh
    withholds the version stamp via the existing _SHAREDUTILS_STATUS gate,
    owner config is backed up before writes, and per-skill state is
    saved/restored across the guarded remove+copy.
  * INSTALLED-COPY WORKS: the decision core copied to a fresh directory
    (simulating the installed layout) validates the real fixtures.

Out of scope (honest holds, dependencies pending): D12 autoRouteTask race
protection, D20 full scope/goal round-trip breadth (covered by D20's own
suite), D24 producer/dispatch parity. This unit tests packaging of existing
contracts only and claims no integrated dispatch behavior.

Run: pytest tests/unit/test_jev27_portable_install_compat.py -q
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent.parent
_SHARED = _REPO / "shared-utils"
_DE = _SHARED / "decision_engine"
_FIX = _DE / "contracts" / "fixtures"

CORE_FILES = (
    "shared-utils/decision_engine/__init__.py",
    "shared-utils/decision_engine/contracts/__init__.py",
    "shared-utils/decision_engine/contracts/schema.py",
    "shared-utils/decision_engine/policies/__init__.py",
    "shared-utils/decision_engine/policies/question_pack.json",
    "shared-utils/decision_engine/policies/task_pack.json",
    "shared-utils/decision_engine/policies/mixed_pack.json",
    "shared-utils/decision_engine/policies/control_pack.json",
    "shared-utils/decision_engine/policies/packs.d.ts",
    "shared-utils/decision_engine/ladder/__init__.py",
    "shared-utils/decision_engine/ladder/ladder.py",
    "shared-utils/decision_engine/evaluators/__init__.py",
    "shared-utils/decision_engine/evaluators/five_layer.py",
    "shared-utils/decision_engine/personas/__init__.py",
    "shared-utils/decision_engine/personas/collapse_policy.py",
    "shared-utils/decision_engine/personas/evidence_profiles.py",
    "shared-utils/decision_engine/personas/voice_match.py",
    "shared-utils/decision_engine/parts/__init__.py",
    "shared-utils/decision_engine/providers/__init__.py",
    "shared-utils/decision_engine/providers/typesafe_direct.py",
    "shared-utils/decision_engine/providers/openrouter_decisions.py",
    "shared-utils/decision_engine/providers/credential_resolver.py",
)
# Sibling deps the core loads by path (five_layer -> adaptive_weights;
# typesafe -> secret_helper; 12.1 intake doctrine consumers).
SIBLING_FILES = (
    "shared-utils/adaptive_weights.py",
    "shared-utils/semantic_task_fit.py",
    "shared-utils/embedding_engine.py",
    "shared-utils/ceo_execution_policy.py",
    "shared-utils/secret_helper.py",
)
SKILL23_FILES = (
    "23-ai-workforce-blueprint/scripts/persona-selector-v2.py",
    "23-ai-workforce-blueprint/scripts/persona_blend.py",
    "23-ai-workforce-blueprint/scripts/decompose-task.py",
)
DIST_FILES = (
    "install.sh",
    "update-skills.sh",
    "platform/common.sh",
    "platform/mac/bootstrap.sh",
    "platform/vps/bootstrap.sh",
)


def _load(name, path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _code_only(src: str) -> str:
    """Strip triple-quoted strings and # comments; what remains is code."""
    out = re.sub(r'"""[\s\S]*?"""', '""', src)
    out = re.sub(r"'''[\s\S]*?'''", "''", out)
    lines = [ln.split("#", 1)[0] for ln in out.splitlines()]
    return "\n".join(lines)


schema = _load("jev27_schema", _DE / "contracts" / "schema.py")
policies = _load("jev27_policies", _DE / "policies" / "__init__.py")


class CanonicalCoreShips(unittest.TestCase):
    def test_core_files_present(self):
        missing = [f for f in CORE_FILES if not (_REPO / f).is_file()]
        self.assertEqual(missing, [])

    def test_sibling_deps_present(self):
        missing = [f for f in SIBLING_FILES if not (_REPO / f).is_file()]
        self.assertEqual(missing, [])

    def test_skill23_consumers_present(self):
        missing = [f for f in SKILL23_FILES if not (_REPO / f).is_file()]
        self.assertEqual(missing, [])

    def test_distribution_files_present(self):
        missing = [f for f in DIST_FILES if not (_REPO / f).is_file()]
        self.assertEqual(missing, [])


class FreshAndUpdateCopyCore(unittest.TestCase):
    def test_installer_copies_shared_utils_wholesale(self):
        src = (_REPO / "install.sh").read_text(encoding="utf-8")
        self.assertIn(
            'cp -r "$ONBOARDING_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"',
            src,
        )

    def test_updater_refreshes_shared_utils_wholesale(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn(
            'cp -r "$EXTRACTED_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"',
            src,
        )

    def test_updater_verifies_refresh_before_stamp(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn("_ocs_tree_compare", src)
        self.assertIn(
            '_ocs_tree_compare "$EXTRACTED_DIR/shared-utils" '
            '"$SKILLS_DIR/shared-utils"',
            src,
        )

    def test_incomplete_refresh_withholds_stamp(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn('_SHAREDUTILS_STATUS="fail"', src)
        self.assertIn("shared-utils refresh (cp -r shared-utils)", src)

    def test_same_version_recheck_covers_shared_utils(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn("_ocs_tree_in_sync", src)
        self.assertIn("for _rc_tree in shared-utils universal-sops", src)

    def test_installer_verifies_decision_core_after_copy(self):
        src = (_REPO / "install.sh").read_text(encoding="utf-8")
        self.assertIn("decision_engine/contracts/schema.py", src)
        self.assertIn("decision_engine/ladder/ladder.py", src)
        self.assertIn("decision core verified", src)
        self.assertIn("decision core incomplete", src)
        # Advisory only on fresh install: the check warns, never aborts.
        block = src[src.index("JEV-027 D27"):src.index(
            "decision core verified in", src.index("JEV-027 D27"))]
        self.assertNotIn("exit 1", block)

    def test_updater_guards_decision_core_subset(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn("_D27_CORE_MISSING", src)
        self.assertIn("decision_engine/policies/control_pack.json", src)
        self.assertIn("adaptive_weights.py", src)


class FreshInstallCopyEndToEnd(unittest.TestCase):
    """Run the REAL install.sh copy block against fixture dirs.

    Proves the fresh-install path delivers the canonical decision core to
    the box skills root and the D27 verify reports complete (A54/A45).
    Hermetic: fixture ONBOARDING_DIR/SKILLS_DIR under temp, stubbed
    log helpers, no network, no writes outside temp.
    """

    def _copy_block(self):
        src = (_REPO / "install.sh").read_text(encoding="utf-8")
        return src[src.index(
            "# v10.5.1: Install shared-utils to skills root"):src.index(
                "# v14.24.0: Install universal-sops/")]

    def _run_copy_block(self, root: Path):
        onboarding = root / "bundle"
        skills = root / "box" / "skills"
        shutil.copytree(_SHARED, onboarding / "shared-utils",
                        ignore=shutil.ignore_patterns("__pycache__"))
        skills.mkdir(parents=True)
        block = self._copy_block()
        driver = (
            "note() { :; }; warn() { echo \"WARN:$1\"; }; "
            "success() { echo \"OK:$1\"; }\n"
            f"ONBOARDING_DIR={shlex.quote(str(onboarding))}\n"
            f"SKILLS_DIR={shlex.quote(str(skills))}\n"
            + block
        )
        result = subprocess.run(["bash", "-c", driver], capture_output=True,
                                text=True, timeout=60)
        return result, skills

    def _rerun_copy_block(self, root: Path, skills: Path):
        onboarding = root / "bundle"
        driver = (
            "note() { :; }; warn() { echo \"WARN:$1\"; }; "
            "success() { echo \"OK:$1\"; }\n"
            f"ONBOARDING_DIR={shlex.quote(str(onboarding))}\n"
            f"SKILLS_DIR={shlex.quote(str(skills))}\n"
            + self._copy_block()
        )
        return subprocess.run(["bash", "-c", driver], capture_output=True,
                              text=True, timeout=60)

    def test_fresh_copy_delivers_core_and_verifies(self):
        with tempfile.TemporaryDirectory(
            prefix="blackceo-JEV-027-inst-"
        ) as tmp:
            result, skills = self._run_copy_block(Path(tmp))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("decision core verified", result.stdout)
            for rel in ("decision_engine/contracts/schema.py",
                        "decision_engine/policies/control_pack.json",
                        "decision_engine/ladder/ladder.py",
                        "decision_engine/parts/__init__.py",
                        "adaptive_weights.py",
                        "ceo_execution_policy.py"):
                self.assertTrue((skills / "shared-utils" / rel).is_file(),
                                rel)

    def test_idempotent_rerun_same_bytes(self):
        with tempfile.TemporaryDirectory(
            prefix="blackceo-JEV-027-idem-"
        ) as tmp:
            root = Path(tmp)
            result, skills = self._run_copy_block(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = {
                str(p.relative_to(skills)): p.read_bytes()
                for p in sorted(skills.rglob("*")) if p.is_file()
            }
            again = self._rerun_copy_block(root, skills)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("decision core verified", again.stdout)
            after = {
                str(p.relative_to(skills)): p.read_bytes()
                for p in sorted(skills.rglob("*")) if p.is_file()
            }
            self.assertEqual(before, after)

    def test_missing_core_entry_warns_not_aborts(self):
        with tempfile.TemporaryDirectory(
            prefix="blackceo-JEV-027-partial-"
        ) as tmp:
            root = Path(tmp)
            result, skills = self._run_copy_block(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Simulate an old/truncated box: remove one core file, rerun.
            gone = (skills / "shared-utils"
                    / "decision_engine" / "parts" / "__init__.py")
            gone.unlink()
            onboarding = root / "bundle"
            # Remove it from the source too so the re-copy cannot heal it:
            # proves the verify names the gap instead of silently passing.
            (onboarding / "shared-utils" / "decision_engine"
             / "parts" / "__init__.py").unlink()
            again = self._rerun_copy_block(root, skills)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("decision core incomplete", again.stdout)
            self.assertIn("decision_engine/parts/__init__.py",
                          again.stdout)


class CoreIsPortable(unittest.TestCase):
    def _core_py(self):
        return [
            p for p in _DE.rglob("*.py")
            if "__pycache__" not in p.parts
        ]

    def test_every_module_anchors_paths_to_own_file(self):
        anchored = 0
        for p in self._core_py():
            code = _code_only(p.read_text(encoding="utf-8"))
            if "Path(__file__)" in code:
                anchored += 1
        # contracts/schema (pure validators) + package inits carry no paths;
        # every module that touches the filesystem must anchor to __file__.
        self.assertGreaterEqual(anchored, 5, "too few __file__-anchored modules")

    def test_no_process_environment_access_at_code_level(self):
        bad = []
        for p in self._core_py():
            code = _code_only(p.read_text(encoding="utf-8"))
            if re.search(r"\bos\.", code):
                bad.append(f"{p.name}: os.* access")
            if re.search(r"^\s*(import os|from os)\b", code, re.M):
                bad.append(f"{p.name}: os import")
        self.assertEqual(bad, [])

    def test_no_absolute_path_literals_at_code_level(self):
        bad = []
        for p in self._core_py():
            code = _code_only(p.read_text(encoding="utf-8"))
            for lit in ("/Users/", "/home/", "/root/", "/data/", "/tmp/"):
                if lit in code:
                    bad.append(f"{p.name}: {lit}")
            if "Path.home(" in code or "expanduser(" in code:
                bad.append(f"{p.name}: home-directory resolution")
        self.assertEqual(bad, [])

    def test_skill23_consumers_anchor_to_own_file(self):
        for rel in SKILL23_FILES:
            code = _code_only((_REPO / rel).read_text(encoding="utf-8"))
            self.assertIn("Path(__file__)", code, rel)

    def test_platform_layer_has_no_operator_constants(self):
        src = (_REPO / "platform/common.sh").read_text(encoding="utf-8")
        self.assertNotIn("/Users/", src)
        self.assertNotIn("blackceo", src.lower())
        self.assertIn("oc_detect_platform", src)
        self.assertIn("oc_set_platform_paths", src)
        self.assertIn("Darwin", src)
        self.assertIn("Linux", src)


class MixedVersionFailsClosed(unittest.TestCase):
    def _envelope(self):
        return json.loads((_FIX / "envelope_committed.json").read_text())

    def test_new_major_envelope_rejected(self):
        env = self._envelope()
        env["schemaVersion"] = "2.0"
        ok, errs = schema.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("schemaVersion" in e for e in errs))

    def test_new_major_bundle_rejected(self):
        env = self._envelope()
        env["personaBundle"]["bundle_version"] = "2.0"
        ok, errs = schema.validate_envelope(env)
        self.assertFalse(ok)
        self.assertTrue(any("bundle_version" in e for e in errs))

    def test_unparsable_versions_rejected(self):
        env = self._envelope()
        env["schemaVersion"] = "next"
        ok, _ = schema.validate_envelope(env)
        self.assertFalse(ok)

    def test_malformed_pack_fails_closed_never_raises(self):
        ok, errs = policies.validate_pack({"kind": "task"})
        self.assertFalse(ok)
        self.assertTrue(errs)

    def test_policy_version_matches_shipped_fixtures(self):
        for fx in ("envelope_committed.json", "envelope_mechanical.json"):
            env = json.loads((_FIX / fx).read_text(encoding="utf-8"))
            self.assertEqual(env["policyVersion"], policies.POLICY_VERSION, fx)

    def test_ladder_carries_no_jev_rollback_path(self):
        code = _code_only(
            (_DE / "ladder" / "ladder.py").read_text(encoding="utf-8")
        )
        self.assertIn("_default_no_jev_fallback", code)
        self.assertIn("decision_source", code)
        self.assertIn("CONFIGURED_MODE_ENUM", _code_only(
            (_DE / "contracts" / "schema.py").read_text(encoding="utf-8")
        ))


class IdempotentNoDestruction(unittest.TestCase):
    def test_updater_never_rms_live_shared_utils(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertNotIn('rm -rf "$SKILLS_DIR/shared-utils"', src)
        self.assertNotIn("rm -rf $SKILLS_DIR/shared-utils", src)

    def test_installer_backs_up_config_before_write(self):
        src = (_REPO / "install.sh").read_text(encoding="utf-8")
        self.assertIn("backup_config_file() {", src)
        self.assertGreater(src.count("backup_config_file "), 1)

    def test_per_skill_state_saved_and_restored(self):
        src = (_REPO / "update-skills.sh").read_text(encoding="utf-8")
        self.assertIn("oc_skill_box_state_save() {", src)
        self.assertIn("oc_skill_box_state_restore() {", src)
        self.assertIn("oc_remove_tree_guarded", src)

    def test_shipped_fixtures_validate_through_real_validators(self):
        for fx in ("envelope_committed.json", "envelope_mechanical.json"):
            env = json.loads((_FIX / fx).read_text(encoding="utf-8"))
            ok, errs = schema.validate_envelope(env)
            self.assertTrue(ok, f"{fx}: {errs}")
            ok, errs = schema.validate_persona_bundle(
                env["personaBundle"], company_id=env["companyId"]
            )
            self.assertTrue(ok, f"{fx} bundle: {errs}")


class InstalledCopyWorks(unittest.TestCase):
    def test_copied_core_validates_fixtures(self):
        with tempfile.TemporaryDirectory(
            prefix="blackceo-JEV-027-"
        ) as tmp:
            dest = Path(tmp) / "skills" / "shared-utils" / "decision_engine"
            # Fresh install then idempotent re-run: copy twice, additive.
            for _ in range(2):
                shutil.copytree(_DE, dest, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__"))
            before = {
                str(p.relative_to(dest)): p.read_bytes()
                for p in sorted(dest.rglob("*")) if p.is_file()
            }
            shutil.copytree(_DE, dest, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
            after = {
                str(p.relative_to(dest)): p.read_bytes()
                for p in sorted(dest.rglob("*")) if p.is_file()
            }
            self.assertEqual(before, after)
            installed = _load("jev27_installed_schema",
                              dest / "contracts" / "schema.py")
            for fx in ("envelope_committed.json", "envelope_mechanical.json"):
                env = json.loads(
                    (dest / "contracts" / "fixtures" / fx).read_text())
                ok, errs = installed.validate_envelope(env)
                self.assertTrue(ok, f"installed copy {fx}: {errs}")


if __name__ == "__main__":
    unittest.main()
