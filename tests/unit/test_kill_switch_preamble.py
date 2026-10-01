#!/usr/bin/env python3
"""KIL-001 kill switch: mode off => preamble NOT prepended; auto => prepended.

THE GAP (first-hand): extensions/ceo-routing-doctrine/dist/index.js wired
api.on('before_prompt_build', ...) to prepend ROUTING_PREAMBLE
UNCONDITIONALLY — no mode read anywhere in the file. ~/.openclaw/
decision-engine-mode.conf (one word, first line: auto|shadow|legacy|off)
truly switched nothing off.

WHAT THIS SUITE PROVES (all against the REAL plugin hook, node subprocess;
mode via env + throwaway OC_CONFIG dirs; no network, no box state):
  1. mode off => V4.3 preamble NOT prepended (card-for-everything instead).
  2. mode auto => V4.3 preamble prepended.
  3. flipping off->auto restores WITHOUT redeploy (read happens per prompt
     build, not at load time).
  4. corrupt mode value fails LOUD (hook throws; nothing injected).
  5. stamp helper honours the switch: off strips managed blocks, keeps owner
     bytes; auto stamps; corrupt fails loud (exit 2, nothing written).
  6. KNOWN-GOOD CONTROL: default (no env, no store) is auto + V4.3 — if the
     control also reported the fallback, the hook would return a constant.

FALLBACK (ii) card-for-everything: no pre-V4 auto-routing path exists in this
tree (the legacy protocol predates V4.3 and is not a versioned prior
preamble), so there is no known-good previous behaviour to restore. Mode
off/legacy instead routes every request to exactly one board card; the owner
is never asked to pick a department.

Run: python3 -m pytest tests/unit/test_kill_switch_preamble.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "extensions" / "ceo-routing-doctrine" / "dist" / "index.js"
POLICY_HELPER = REPO / "shared-utils" / "ceo_execution_policy.py"
VERIFY_SH = REPO / "scripts" / "verify-routing.sh"
RUNNER = REPO / "shared-utils" / "fleet_refresh_runner.py"

HOOK_SCRIPT = (
    "const {default:plugin}=await import(process.argv[1]); let hook;"
    "plugin({on:(name,fn)=>{if(name==='before_prompt_build')hook=fn;}});"
    "(async()=>{const r=await hook({prompt:'probe'},{agentId:'ceo'});"
    "process.stdout.write(r.prependSystemContext);})();"
)

# Split so this file's own source is not itself a grep hit for the carrier
# test (same trick as test_ceo_execution_policy.py).
V43_HEADING = "Task intake and assigned execution" + " (V4.3)"
FALLBACK_HEADING = "card for everything"


def _hook(env_extra=None, oc_config=None):
    """Run the REAL plugin hook; return (preamble, stderr). Raises on throw."""
    env = dict(os.environ)
    env.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
    env.pop("OC_CONFIG", None)
    # Hermetic home: no live store leaks in (missing dir => default auto).
    with tempfile.TemporaryDirectory() as home:
        env["HOME"] = home
        if env_extra:
            env.update(env_extra)
        if oc_config is not None:
            env["OC_CONFIG"] = str(oc_config)
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", HOOK_SCRIPT, str(DIST)],
            capture_output=True, text=True, env=env, cwd=str(REPO),
        )
        return proc


def _preamble(proc):
    assert proc.returncode == 0, f"hook threw: {proc.stderr[:300]}"
    return proc.stdout


class KillSwitchPreambleTests(unittest.TestCase):
    def test_control_default_is_auto_v43(self):
        """KNOWN-GOOD CONTROL: no env, no store => auto => V4.3 prepended."""
        out = _preamble(_hook())
        self.assertIn(V43_HEADING, out)
        self.assertNotIn(FALLBACK_HEADING, out)

    def test_mode_auto_prepends(self):
        out = _preamble(_hook({"OPENCLAW_DECISION_ENGINE_MODE": "auto"}))
        self.assertIn(V43_HEADING, out)

    def test_mode_shadow_prepends(self):
        out = _preamble(_hook({"OPENCLAW_DECISION_ENGINE_MODE": "shadow"}))
        self.assertIn(V43_HEADING, out)

    def test_mode_off_not_prepended(self):
        out = _preamble(_hook({"OPENCLAW_DECISION_ENGINE_MODE": "off"}))
        self.assertNotIn(V43_HEADING, out)
        self.assertIn(FALLBACK_HEADING, out)
        self.assertIn("mc-route.sh task", out)

    def test_mode_legacy_not_prepended(self):
        """off/legacy share the same no-JEV engine: neither gets V4.3."""
        out = _preamble(_hook({"OPENCLAW_DECISION_ENGINE_MODE": "legacy"}))
        self.assertNotIn(V43_HEADING, out)
        self.assertIn(FALLBACK_HEADING, out)

    def test_mode_from_store_file(self):
        """Same order as scripts/decision-engine-mode.py: file beats default."""
        with tempfile.TemporaryDirectory() as cfg:
            (Path(cfg) / "decision-engine-mode.conf").write_text("off\n")
            out = _preamble(_hook(oc_config=cfg))
            self.assertNotIn(V43_HEADING, out)
            self.assertIn(FALLBACK_HEADING, out)

    def test_env_beats_store_file(self):
        with tempfile.TemporaryDirectory() as cfg:
            (Path(cfg) / "decision-engine-mode.conf").write_text("off\n")
            out = _preamble(_hook({"OPENCLAW_DECISION_ENGINE_MODE": "auto"}, cfg))
            self.assertIn(V43_HEADING, out)

    def test_flip_off_to_auto_restores_without_redeploy(self):
        """Read happens per prompt build, not at load: same dist file."""
        with tempfile.TemporaryDirectory() as cfg:
            store = Path(cfg) / "decision-engine-mode.conf"
            store.write_text("off\n")
            self.assertNotIn(V43_HEADING, _preamble(_hook(oc_config=cfg)))
            store.write_text("auto\n")
            self.assertIn(V43_HEADING, _preamble(_hook(oc_config=cfg)))

    def test_corrupt_mode_fails_loud(self):
        """Corrupt value throws (fail loud); nothing injected, no silent on."""
        proc = _hook({"OPENCLAW_DECISION_ENGINE_MODE": "bogus"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CORRUPT", proc.stderr + proc.stdout)

    def test_corrupt_store_file_fails_loud(self):
        with tempfile.TemporaryDirectory() as cfg:
            (Path(cfg) / "decision-engine-mode.conf").write_text("bogus\n")
            proc = _hook(oc_config=cfg)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("CORRUPT", proc.stderr + proc.stdout)


class KillSwitchStampTests(unittest.TestCase):
    def _run_helper(self, target, kind="CEO_ORCHESTRATOR_RULE", oc_config=None, extra_env=None):
        env = dict(os.environ)
        env.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
        env.pop("OC_CONFIG", None)
        with tempfile.TemporaryDirectory() as home:
            env["HOME"] = home
            if extra_env:
                env.update(extra_env)
            cmd = [sys.executable, str(POLICY_HELPER), str(target), "--kind", kind]
            if oc_config is not None:
                cmd += ["--oc-config", str(oc_config)]
            return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(REPO))

    def test_stamp_auto_writes_block(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "SOUL.md"
            target.write_text("Owner mission\n")
            with tempfile.TemporaryDirectory() as cfg:
                rc = self._run_helper(target, oc_config=cfg)
                self.assertEqual(rc.returncode, 0, rc.stderr)
                self.assertIn("CEO_ORCHESTRATOR_RULE_V4_3", target.read_text())
                self.assertIn("Owner mission", target.read_text())

    def test_stamp_off_strips_block_keeps_owner(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "SOUL.md"
            target.write_text("Owner mission\n")
            with tempfile.TemporaryDirectory() as cfg:
                self._run_helper(target, oc_config=cfg)
                self.assertIn("CEO_ORCHESTRATOR_RULE_V4_3", target.read_text())
                (Path(cfg) / "decision-engine-mode.conf").write_text("off\n")
                rc = self._run_helper(target, oc_config=cfg)
                self.assertEqual(rc.returncode, 0, rc.stderr)
                text = target.read_text()
                self.assertNotIn("CEO_ORCHESTRATOR_RULE_V4_3", text)
                self.assertIn("Owner mission", text)

    def test_stamp_corrupt_fails_loud_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "SOUL.md"
            before = "Owner mission\n"
            target.write_text(before)
            with tempfile.TemporaryDirectory() as cfg:
                (Path(cfg) / "decision-engine-mode.conf").write_text("bogus\n")
                rc = self._run_helper(target, oc_config=cfg)
                self.assertNotEqual(rc.returncode, 0)
                self.assertIn("CORRUPT", rc.stdout + rc.stderr)
                self.assertEqual(target.read_text(), before)


class KillSwitchChainStepTests(unittest.TestCase):
    def test_chain_step_is_variable_name_presence_only(self):
        """The off-path support must be a runtime callable, never a marker
        string: _verify_loaded branches on _kill_active(), not on grep."""
        src = RUNNER.read_text()
        self.assertIn("def _resolve_kill_mode(", src)
        self.assertIn("def _kill_active(", src)
        self.assertIn("_kill_active(paths)", src)
        self.assertIn('"kill_mode"', src)

    def test_verify_gates_honour_kill(self):
        src = VERIFY_SH.read_text()
        self.assertIn('KILL_ACTIVE=1', src)
        self.assertIn('must be ABSENT', src)
        self.assertIn('SUPPORTED', src)

    def test_mode_authority_is_plugin_json_not_modes_py(self):
        """openclaw.plugin.json is THE mode authority, not modes.py: the
        plugin + helper resolve modes locally; modes.py owns JEV path
        semantics (EFFECTIVE_JEV/EFFECTIVE_NO_JEV), never prompt/stamp text."""
        helper = POLICY_HELPER.read_text()
        self.assertIn("the mode authority is openclaw.plugin.json", helper)
        self.assertNotIn("from decision_engine import", helper)
        self.assertNotIn("preserve_explicit_mode", helper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
