#!/usr/bin/env python3
"""Class A: scripts that read or write the agent roster must handle BOTH shapes.

OpenClaw 2026.9.x keeps agents under `agents.entries` (object keyed by id, no
"id" inside the body); older builds used `agents.list[]`. A reader that only
walks agents.list sees ZERO agents on a migrated box, and a writer that creates
agents.list there makes the gateway refuse to start (`agents: Unrecognized key
"list"`). Every case below runs the REAL script against an entries-shaped
fixture and fails on the pre-fix tree.

Hermetic: HOME is a temp dir, no live openclaw is ever invoked (a stub is put
first on PATH where a script would call it).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EntriesRoster(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        (self.home / ".openclaw").mkdir(parents=True)
        self.cfg = self.home / ".openclaw" / "openclaw.json"
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("OC_JSON", "FLEET_REFRESH_ROOT", "OPENCLAW_CONFIG_PATH")}
        self.env["HOME"] = str(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def write_cfg(self, data):
        self.cfg.write_text(json.dumps(data, indent=2))

    def read_cfg(self):
        return json.loads(self.cfg.read_text())

    def stub_openclaw(self, rc):
        """An `openclaw` stub that logs its argv and exits rc."""
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        log = self.tmp / "openclaw.argv"
        stub = bindir / "openclaw"
        stub.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit {rc}\n')
        stub.chmod(0o755)
        self.env["PATH"] = f"{bindir}:{os.environ['PATH']}"
        return log

    # -- readers -----------------------------------------------------------
    def test_refresh_build_state_resolves_departments_tree_from_entries(self):
        mod = load("23-ai-workforce-blueprint/scripts/refresh-build-state-from-index.py", "rbs")
        tree = self.tmp / "company" / "departments"
        (tree / "sales").mkdir(parents=True)
        self.write_cfg({"agents": {"entries": {
            "main": {"workspace": str(self.tmp / "ws")},
            "dept-sales": {"workspace": str(tree / "sales")}}}})
        self.assertEqual(mod._config_derived_departments_dir(self.cfg, ["sales"]), tree)

    def test_verify_model_pins_sees_entries_agents(self):
        self.write_cfg({"models": {"providers": {"ollama-cloud": {}}},
                        "agents": {"entries": {"dept-web": {"model": "ollama/kimi-k2.6:cloud"}}}})
        r = subprocess.run([sys.executable, str(REPO / "scripts/verify-model-pins.py"),
                            "--config", str(self.cfg), "--json"],
                           capture_output=True, text=True, env=self.env, timeout=30)
        out = json.loads(r.stdout)
        self.assertEqual(out["agents"], 1, r.stdout)
        self.assertEqual(r.returncode, 1, "the unregistered 'ollama' pin must be FATAL")
        self.assertTrue(any("dept-web" in f["where"] for f in out["fatal"]), out["fatal"])

    def test_resolve_injected_core_files_uses_entries_workspace(self):
        mod = load("shared-utils/resolve_injected_core_files.py", "ricf")
        ws = self.tmp / "main-ws"
        ws.mkdir()
        self.write_cfg({"agents": {"defaults": {"workspace": str(self.tmp / "other")},
                                   "entries": {"main": {"workspace": str(ws)}}}})
        r = mod.resolve_injected_core_files("main", openclaw_config=self.cfg,
                                            openclaw_root=self.home / ".openclaw")
        self.assertEqual(r["resolved_from"], "agents.entries[main].workspace")
        self.assertEqual(Path(r["workspace"]).resolve(), ws.resolve())

    def test_dedup_agents_md_inline_fallback_uses_entries_workspace(self):
        mod = load("scripts/dedup-agents-md.py", "dedup")
        mod._find_shared_utils = lambda _d: None  # force the inline fallback
        ws = self.tmp / "main-ws"
        self.write_cfg({"agents": {"entries": {"main": {"workspace": str(ws)}}}})
        os.environ["OC_JSON"] = str(self.cfg)
        try:
            path, src = mod.resolve_agents_md("main", None)
        finally:
            del os.environ["OC_JSON"]
        self.assertEqual(src, "agents.entries[main].workspace")
        self.assertEqual(path, ws / "AGENTS.md")

    def test_pre_july14_check_finds_dying_model_in_entries_memory_search(self):
        self.write_cfg({"agents": {"entries": {"main": {
            "memory": {"search": {"model": "gemini-embedding-001"}}}}}})
        r = subprocess.run(["bash", str(REPO / "scripts/pre-july14-embedding-migration-check.sh")],
                           capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(r.returncode, 7, r.stdout + r.stderr)
        self.assertIn("agents.entries.main.memory.search", r.stdout)

    # -- writers -----------------------------------------------------------
    def run_heartbeat(self):
        env = dict(self.env, OC_JSON=str(self.cfg), LOG_FILE=str(self.tmp / "hb.log"))
        return subprocess.run(["bash", str(REPO / "scripts/ensure-heartbeat-defaults.sh")],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_ensure_heartbeat_cli_writes_entries_path(self):
        log = self.stub_openclaw(0)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = log.read_text() if log.exists() else ""
        self.assertIn("config set agents.entries.main.heartbeat.every", argv)
        self.assertNotIn("agents.list", argv)

    def test_ensure_heartbeat_python_fallback_writes_entries_never_list(self):
        self.stub_openclaw(1)  # CLI write fails -> Python fallback
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        agents = self.read_cfg()["agents"]
        self.assertNotIn("list", agents)
        self.assertEqual(agents["entries"]["main"]["heartbeat"]["every"], "6h")

    def test_pixel_hook_registers_into_entries_never_list(self):
        self.stub_openclaw(0)  # its trailing `openclaw config validate`
        self.write_cfg({"agents": {"entries": {"main": {"model": "ollama-cloud/x"}}}})
        env = dict(self.env, CONFIG_FILE=str(self.cfg), HOOKS_TOKEN="fixture-hooks-token",
                   SECRETS_ENV_FILE=str(self.tmp / "secrets.env"))
        r = subprocess.run(["bash", str(REPO / "38-conversational-ai-system/scripts/28-configure-pixel-hook.sh")],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        agents = self.read_cfg()["agents"]
        self.assertNotIn("list", agents)
        self.assertEqual(agents["entries"]["pixel-concierge"]["name"], "Pixel Concierge")
        self.assertNotIn("id", agents["entries"]["pixel-concierge"])
        self.assertEqual(agents.get("ownership"), "explicit")

    def test_legacy_list_shape_still_written_as_list(self):
        self.stub_openclaw(0)
        self.write_cfg({"agents": {"list": [{"id": "main", "model": "ollama-cloud/x"}]}})
        env = dict(self.env, CONFIG_FILE=str(self.cfg), HOOKS_TOKEN="fixture-hooks-token",
                   SECRETS_ENV_FILE=str(self.tmp / "secrets.env"))
        r = subprocess.run(["bash", str(REPO / "38-conversational-ai-system/scripts/28-configure-pixel-hook.sh")],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        agents = self.read_cfg()["agents"]
        self.assertNotIn("entries", agents)
        self.assertEqual([a["id"] for a in agents["list"]], ["main", "pixel-concierge"])


if __name__ == "__main__":
    unittest.main()
