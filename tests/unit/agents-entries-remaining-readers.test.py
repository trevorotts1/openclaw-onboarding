#!/usr/bin/env python3
"""Class A (sweep): the remaining agent-roster readers found by grep also handle
`agents.entries` (OpenClaw 2026.9.x, keyed by id, no "id" in the body).

Each case runs the script's REAL code (the embedded Python heredoc, or the
module function) against an entries-only fixture; every case fails on the tree
before this change. Hermetic: temp files only, no openclaw call.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def heredoc(path, opener_regex, marker):
    """The body of the first heredoc in `path` whose opening line matches."""
    text = (REPO / path).read_text()
    m = re.search(opener_regex + r"[^\n]*<<'" + marker + r"'[^\n]*\n(.*?)\n" + marker + r"\n", text, re.S)
    assert m, f"heredoc {marker} not found in {path}"
    return m.group(1)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str((REPO / path).parent))
    spec.loader.exec_module(mod)
    return mod


class RemainingReaders(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.cfg = self.tmp / "openclaw.json"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data):
        self.cfg.write_text(json.dumps(data))

    def py(self, code, *args, **env):
        return subprocess.run([sys.executable, "-", *args], input=code, capture_output=True,
                              text=True, env=dict(os.environ, **env), timeout=30)

    def test_wire_scripts_resolve_main_workspace_from_entries(self):
        self.write({"agents": {"defaults": {"workspace": "/wrong"},
                               "entries": {"main": {"workspace": "/right"}}}})
        for wire in ("07-kie-setup", "63-agnes-image", "64-agnes-video",
                     "66-kie-image", "67-kie-video", "68-kie-audio"):
            code = heredoc(f"{wire}/wire.sh", r'ws="\$\(OC_JSON="\$ocjson" python3 -', "PY")
            r = self.py(code, OC_JSON=str(self.cfg))
            self.assertEqual(r.stdout.strip(), "/right", f"{wire}: {r.stdout!r} {r.stderr}")

    def test_onboarding_state_resolves_main_workspace_from_entries(self):
        self.write({"agents": {"entries": {"main": {"workspace": "/right"}}}})
        code = heredoc("scripts/onboarding-state.sh", r'ws="\$\(OC_JSON="\$OBS_OC_JSON" python3 -', "PYEOF")
        r = self.py(code, OC_JSON=str(self.cfg))
        self.assertEqual(r.stdout.strip(), "/right", r.stderr)

    def test_qc_platform_facts_resolves_main_workspace_from_entries(self):
        home = self.tmp / "oc"
        home.mkdir()
        (home / "openclaw.json").write_text(json.dumps({"agents": {"entries": {"main": {"workspace": "/right"}}}}))
        text = (REPO / "scripts/qc-assert-platform-facts-stamped.sh").read_text()
        body = text.split("# Step 2:", 1)[1].split('python3 -c "', 1)[1].split('" 2>/dev/null', 1)[0]
        r = self.py(body.replace("$OC_ROOT", str(home)))
        self.assertEqual(r.stdout.strip(), "/right", r.stderr)

    def test_provider_capability_scans_see_entries_multimodal(self):
        self.write({"agents": {"defaults": {}, "entries": {"dept-x": {
            "memory": {"search": {"provider": "ollama", "multimodal": {"enabled": True}}}}}}})
        code = heredoc("scripts/smoke-test-provider-capabilities.sh", r"CONFIG_READ=\$\(python3 -", "PYEOF")
        out = json.loads(self.py(code, str(self.cfg)).stdout)
        self.assertEqual(out["multimodal_agents"], ["dept-x"])
        code = heredoc("scripts/qc-assert-provider-capability-invariants.sh", r"ANALYSIS_RESULT=\$\(python3 -", "PYEOF")
        out = self.py(code, str(self.cfg)).stdout
        self.assertIn("agent=dept-x", out)

    def test_grant_ceo_consent_edits_entries_ceo(self):
        self.write({"agents": {"entries": {"main": {"tools": {"deny": ["exec"], "allow": ["read"]}}}}})
        code = heredoc("scripts/grant-ceo-consent.sh", r'MODE="\$_mode"', "PYEOF")
        r = self.py(code, str(self.cfg), MODE="consented", GATED_JSON="",
                    GATE_BACKUP=str(self.tmp / "gate.json"))
        self.assertIn("CONSENTED:main", r.stdout, r.stderr)
        agents = json.loads(self.cfg.read_text())["agents"]
        self.assertNotIn("list", agents)
        self.assertNotIn("tools", agents["entries"]["main"])

    def test_select_model_lists_entries_models(self):
        mod = load("shared-utils/select_model.py", "select_model_t")
        found = mod._list_available_models({"agents": {"entries": {"dept-x": {"model": "ollama-cloud/glm-5.3"}}}})
        self.assertIn("ollama-cloud/glm-5.3", found)

    def test_model_sovereignty_scans_entries(self):
        mod = load("shared-utils/assert_model_sovereignty.py", "ams_t")
        self.write({"agents": {"entries": {"dept-x": {"model": "ollama-cloud/glm-5.3"}}}})
        _offenders, scanned = mod.scan_config(str(self.cfg))
        self.assertIn("dept-x", [s["agent"] for s in scanned])

    def test_register_routing_dept_sees_entries_registration(self):
        self.write({"agents": {"entries": {"dept-podcast": {"workspace": "/w"}}}})
        r = subprocess.run([sys.executable, str(REPO / "32-command-center-setup/scripts/register-routing-dept.py"),
                            "--dept", "podcast", "--config", str(self.cfg),
                            "--registry", str(self.tmp / "registry.json"), "--dry-run"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already registered (agent id: dept-podcast)", r.stdout + r.stderr)


    def test_run_full_install_phase4_counts_entries(self):
        self.write({"agents": {"entries": {"main": {}, "dept-sales": {}, "dept-ops": {}}}})
        text = (REPO / "32-command-center-setup/scripts/run-full-install.sh").read_text()
        code = re.search(r"AGENT_COUNT=\$\(python3 -c '(.*?)' \"\$OC_ROOT/openclaw.json\"", text).group(1)
        r = subprocess.run([sys.executable, "-c", code, str(self.cfg)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout, "3", r.stderr)

    def test_verify_wiring_registration_reads_entries(self):
        self.write({"agents": {"entries": {"dept-sales": {"workspace": "/w/sales"}}}})
        text = (REPO / "23-ai-workforce-blueprint/scripts/verify-wiring.sh").read_text()
        ids_f = re.search(r"AGENT_IDS_IN_CFG=\$\(jq -r '(.*?)' ", text).group(1)
        ws_f = re.search(r"REG_WORKSPACE=\$\(jq -r --arg aid \"\$EXPECTED_AGENT_ID\" \\\n\s*'(.*?)' \\", text).group(1)
        ids = subprocess.run(["jq", "-r", ids_f, str(self.cfg)], capture_output=True, text=True).stdout.split()
        ws = subprocess.run(["jq", "-r", "--arg", "aid", "dept-sales", ws_f, str(self.cfg)],
                            capture_output=True, text=True).stdout.strip()
        self.assertEqual((ids, ws), (["dept-sales"], "/w/sales"))

    def test_qc_system_integrity_counts_entries_directors(self):
        self.write({"agents": {"entries": {"main": {}, "dept-sales": {}, "dept-ops": {}}}})
        text = (REPO / "scripts/qc-system-integrity.sh").read_text()
        code = re.search(r'DIR_AGENTS=\$\(OC_JSON="\$OCJSON" python3 -c "(.*?)" 2>/dev/null\)', text).group(1)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, OC_JSON=str(self.cfg)), timeout=30)
        self.assertEqual(r.stdout.strip(), "2", r.stderr)

    def test_podcast_installer_sees_entries_agent(self):
        self.write({"agents": {"entries": {"dept-podcast": {"agentDir": "/a/dept-podcast"}}}})
        text = (REPO / "58-podcast-production-engine/scripts/install-podcast-department.sh").read_text()
        code = text.split("entry_present() {", 1)[1].split("<<'PYEOF'\n", 1)[1].split("\nPYEOF", 1)[0]
        env = dict(os.environ, IPC_CONFIG_FILE=str(self.cfg), IPC_AGENT_ID="dept-podcast")
        self.assertEqual(self.py(code, **{k: env[k] for k in ("IPC_CONFIG_FILE", "IPC_AGENT_ID")}).returncode, 0)

    def test_add_department_inline_fallback_writes_entries_never_list(self):
        if Path("/data/.openclaw").exists():
            self.skipTest("/data/.openclaw exists on this host")
        sys.path.insert(0, str(REPO / "32-command-center-setup" / "scripts"))
        import test_add_department_runtime as t
        home = self.tmp / "home"
        oc_root, _db = t._make_fixture(home)
        (oc_root / "openclaw.json").write_text(json.dumps(
            {"agents": {"entries": {"main": {"workspace": "/x/main"}}}}))
        script = t._isolated_scripts_copy(home, drop="materialize-dept-agents.sh")
        r = t._run_add_department(home, "podcast", "Podcast", script=script)
        agents = json.loads((oc_root / "openclaw.json").read_text())["agents"]
        self.assertNotIn("list", agents, r.stdout + r.stderr)
        entry = agents["entries"].get("dept-podcast")
        self.assertIsInstance(entry, dict, r.stdout + r.stderr)
        self.assertNotIn("id", entry)
        self.assertNotIn("memorySearch", entry)
        self.assertIn("search", entry.get("memory", {}))
        self.assertEqual(agents.get("ownership"), "explicit")

if __name__ == "__main__":
    unittest.main()
