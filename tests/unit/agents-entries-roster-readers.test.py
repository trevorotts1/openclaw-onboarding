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
import shutil
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
    def run_heartbeat(self, **extra):
        env = dict(self.env, OC_JSON=str(self.cfg), LOG_FILE=str(self.tmp / "hb.log"), **extra)
        return subprocess.run(["bash", str(REPO / "scripts/ensure-heartbeat-defaults.sh")],
                              capture_output=True, text=True, env=env, timeout=60)

    def stub_openclaw_hb(self, schema, set_rc, version="OpenClaw 2026.11.4 (test)"):
        """An `openclaw` stub for ensure-heartbeat-defaults.sh. Logs argv plus
        the isolation env to openclaw.argv. `config schema` prints a schema whose
        agents.defaults has heartbeat (schema="accepted"), lacks it ("retired"),
        or fails ("fail"); `config set` exits set_rc; `--version` prints version."""
        bindir = self.tmp / "bin"
        bindir.mkdir(exist_ok=True)
        log = self.tmp / "openclaw.argv"
        hb = ', "heartbeat": {}' if schema == "accepted" else ""
        doc = '{"properties": {"agents": {"properties": {"defaults": {"properties": {"model": {}%s}}}}}}' % hb
        (self.tmp / "schema.json").write_text(doc)
        stub = bindir / "openclaw"
        stub.write_text(
            "#!/bin/sh\n"
            f'echo "$* | HOME=$OPENCLAW_HOME STATE=$OPENCLAW_STATE_DIR CFG=$OPENCLAW_CONFIG_PATH" >> "{log}"\n'
            'case "$1 $2" in\n'
            f'  "config schema") [ "{schema}" = fail ] && exit 1; cat "{self.tmp / "schema.json"}"; exit 0 ;;\n'
            f'  "config set") exit {set_rc} ;;\n'
            f'  "--version "*) printf \'%b\\n\' "{version}"; exit 0 ;;\n'
            "esac\n"
            "exit 0\n")
        stub.chmod(0o755)
        self.env["PATH"] = f"{bindir}:{os.environ['PATH']}"
        return log

    def calls(self, log):
        return log.read_text().splitlines() if log.exists() else []

    def hb_sets(self, log):
        return [c for c in self.calls(log) if c.startswith("config set") and "heartbeat" in c.split(" | ")[0]]

    def path_without_openclaw(self):
        """PATH with bash/python3 but no openclaw anywhere on it."""
        bindir = self.tmp / "noclaw"
        bindir.mkdir(exist_ok=True)
        (bindir / "python3").symlink_to(sys.executable)
        for tool in ("bash", "cat", "cp", "rm", "mktemp", "grep", "head", "sort", "tr"):
            found = shutil.which(tool)
            if found:
                (bindir / tool).symlink_to(found)
        return str(bindir)

    def test_ensure_heartbeat_cli_writes_entries_path(self):
        log = self.stub_openclaw_hb("accepted", set_rc=0)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = "\n".join(self.calls(log))
        self.assertIn("config set agents.entries.main.heartbeat.every", argv)
        self.assertNotIn("agents.list", argv)
        self.assertIn("Heartbeat config keys accepted", r.stdout)

    def test_ensure_heartbeat_probe_runs_isolated(self):
        log = self.stub_openclaw_hb("accepted", set_rc=0)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        self.run_heartbeat()
        probe = [c for c in self.calls(log) if c.startswith("config schema")]
        self.assertEqual(len(probe), 1, self.calls(log))
        self.assertNotIn(str(self.home), probe[0])
        self.assertIn("hb-capability.", probe[0])

    def test_ensure_heartbeat_retired_schema_writes_nothing(self):
        # The schema answer wins over a version that would say "accepted".
        log = self.stub_openclaw_hb("retired", set_rc=1)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        before = self.cfg.read_bytes()
        r = self.run_heartbeat(FLEET_OC_VERSION_OVERRIDE="2026.11.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hb_sets(log), [])
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertIn("retired on this OpenClaw build", r.stdout)
        self.assertNotIn("Python fallback", r.stdout + r.stderr)

    def test_ensure_heartbeat_retired_with_legacy_keys_advises_doctor(self):
        log = self.stub_openclaw_hb("retired", set_rc=1)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w", "heartbeat": {"every": "6h"}}}}})
        before = self.cfg.read_bytes()
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hb_sets(log), [])
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertIn("openclaw doctor --fix", r.stderr)

    def test_ensure_heartbeat_cli_refusal_never_falls_back_to_python(self):
        # Replaces the old test that pinned the defect: a CLI refusal used to
        # drop into the Python fallback and write the key anyway.
        log = self.stub_openclaw_hb("accepted", set_rc=1)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        before = self.cfg.read_bytes()
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertNotIn("Python fallback", r.stdout)
        self.assertIn("openclaw refused the per-agent heartbeat block", r.stderr)
        self.assertTrue(self.hb_sets(log), "the CLI write must still be attempted")

    def test_ensure_heartbeat_schema_fail_version_cutoff(self):
        for version, writes in (("2026.11.5", False), ("2026.11.4", True)):
            with self.subTest(version=version):
                log = self.stub_openclaw_hb("fail", set_rc=0, version=f"OpenClaw {version} (test)")
                log.unlink(missing_ok=True)
                self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
                r = self.run_heartbeat()
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(bool(self.hb_sets(log)), writes, self.calls(log))

    def test_ensure_heartbeat_version_scan_skips_banner_line(self):
        log = self.stub_openclaw_hb(
            "fail", set_rc=0,
            version='openclaw: Retrying with cached runtime\nOpenClaw 2026.11.5 (test)')
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hb_sets(log), [])
        self.assertIn("2026.11.5", r.stdout)

    def test_ensure_heartbeat_unknown_capability_writes_nothing(self):
        log = self.stub_openclaw_hb("fail", set_rc=0, version="no version here")
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        before = self.cfg.read_bytes()
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hb_sets(log), [])
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertIn("Heartbeat capability unknown", r.stderr)

    def test_ensure_heartbeat_python_fallback_only_without_cli(self):
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        self.cfg.chmod(0o640)
        self.env["PATH"] = self.path_without_openclaw()
        r = self.run_heartbeat(FLEET_OC_VERSION_OVERRIDE="2026.11.4")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Python fallback (openclaw CLI absent)", r.stdout)
        agents = self.read_cfg()["agents"]
        self.assertNotIn("list", agents)
        self.assertEqual(agents["entries"]["main"]["heartbeat"]["every"], "6h")
        self.assertEqual(self.cfg.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.cfg.parent.glob(".hb-fallback.*")), [])

    def test_ensure_heartbeat_no_cli_retired_version_writes_nothing(self):
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/w"}}}})
        before = self.cfg.read_bytes()
        self.env["PATH"] = self.path_without_openclaw()
        r = self.run_heartbeat(FLEET_OC_VERSION_OVERRIDE="2026.11.5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cfg.read_bytes(), before)

    def test_ensure_heartbeat_vps_data_path_same_gate(self):
        # Docker/VPS boxes keep the config under /data/.openclaw; OC_JSON points
        # there. Same branches must hold on that layout.
        vps = self.tmp / "data" / ".openclaw"
        vps.mkdir(parents=True)
        self.cfg = vps / "openclaw.json"
        log = self.stub_openclaw_hb("retired", set_rc=1)
        self.write_cfg({"agents": {"entries": {"main": {"workspace": "/data/w"}}}})
        before = self.cfg.read_bytes()
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.hb_sets(log), [])
        self.assertEqual(self.cfg.read_bytes(), before)
        log.unlink()
        self.stub_openclaw_hb("accepted", set_rc=0)
        r = self.run_heartbeat()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("config set agents.entries.main.heartbeat.every", "\n".join(self.calls(log)))

    def test_pixel_hook_registers_into_entries_never_list(self):
        self.stub_openclaw(0)  # its trailing `openclaw config validate`
        # Fixture models a configured client box: a configured default model
        # (agents.defaults.model) is what 28-configure-pixel-hook.sh resolves
        # when no pixel-specific choice exists.
        self.write_cfg({"agents": {"defaults": {"model": "ollama-cloud/x"},
                                   "entries": {"main": {"model": "ollama-cloud/x"}}}})
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
        # Same configured-default fixture as the entries case above.
        self.write_cfg({"agents": {"defaults": {"model": "ollama-cloud/x"},
                                   "list": [{"id": "main", "model": "ollama-cloud/x"}]}})
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
