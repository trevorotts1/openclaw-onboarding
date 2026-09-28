#!/usr/bin/env python3
"""Skill 23 build is non-destructive on a box that already has departments + agents.

1. Shared core files (AGENTS.md / TOOLS.md / USER.md) in a department are REAL-FILE
   copies (N29). An existing real, non-empty file is kept byte-identical; a symlink
   is migrated to a real copy; nothing is ever re-pointed at the workspace root.
2. Agent registration never writes or alters the model on an agent already in the
   config, and never touches agents.defaults.
3. An agents.entries box stays agents.entries: re-running registration adds no
   agents.list rows and no second entry for a department already registered.

Run: python3 tests/unit/test_skill23_build_nondestructive.py
"""
import copy
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "23-ai-workforce-blueprint" / "scripts"
CORE = ("AGENTS.md", "TOOLS.md", "USER.md")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BW = _load("bw_nondestructive_test", SCRIPTS / "build-workforce.py")
CRW = _load("crw_nondestructive_test", SCRIPTS / "create_role_workspaces.py")


class _Box(unittest.TestCase):
    """A fixture box: canonical core files at the workspace root + a departments tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.ws = base / "workspace"
        self.depts = self.ws / "company" / "departments"
        self.depts.mkdir(parents=True)
        (base / ".openclaw").mkdir()  # sandbox OpenClaw root: nothing touches the real HOME
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(base)
        for f in CORE:
            (self.ws / f).write_text(f"canonical {f}\n" * 50)
        self._saved = {k: getattr(BW, k) for k in ("WORKSPACE_ROOT", "DEPARTMENTS_DIR", "COMPANY_SLUG",
                                                   "_resolve_main_agent_workspace", "_agent_dir_for",
                                                   "flush_dept_defaults_artifact")}
        BW.WORKSPACE_ROOT = str(self.ws)
        BW.DEPARTMENTS_DIR = str(self.depts)
        BW.COMPANY_SLUG = "fixture-co"
        BW._resolve_main_agent_workspace = lambda: str(self.ws)
        BW._agent_dir_for = lambda aid: str(base / "state" / "agents" / aid / "agent")
        BW.flush_dept_defaults_artifact = lambda: None

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(BW, k, v)
        os.environ["HOME"] = self._home
        self._tmp.cleanup()

    def build_dept(self, dept_id):
        BW.create_department_workspace(dept_id, {"name": dept_id.title(), "head": f"{dept_id} head",
                                                 "description": f"{dept_id} work"},
                                       {"company_name": "Fixture Co"})
        return self.depts / dept_id


class TestDepartmentCoreFiles(_Box):
    def test_existing_real_core_files_stay_real_and_byte_identical(self):
        d = self.depts / "marketing"
        d.mkdir()
        owner = {f: f"owner-tuned {f} for this department\n".encode() for f in CORE}
        for f, data in owner.items():
            (d / f).write_bytes(data)
        for _ in range(2):  # a re-run must be just as non-destructive
            self.build_dept("marketing")
            for f, data in owner.items():
                self.assertFalse((d / f).is_symlink(), f"{f} was replaced by a symlink")
                self.assertEqual((d / f).read_bytes(), data, f"{f} content changed")

    def test_new_department_gets_real_copies(self):
        d = self.build_dept("sales")
        for f in CORE:
            self.assertFalse((d / f).is_symlink(), f"{f} is a symlink (N29 forbids)")
            self.assertEqual((d / f).read_bytes(), (self.ws / f).read_bytes())

    def test_symlinked_core_file_is_migrated_to_real_copy(self):
        d = self.depts / "finance"
        d.mkdir()
        for f in CORE:
            (d / f).symlink_to(self.ws / f)
        self.build_dept("finance")
        for f in CORE:
            self.assertFalse((d / f).is_symlink())
            self.assertEqual((d / f).read_bytes(), (self.ws / f).read_bytes())
            self.assertFalse((self.ws / f).is_symlink(), "canonical must never be touched")


class TestRoleFolderCoreFiles(_Box):
    def test_role_folder_real_files_kept_and_new_roles_get_copies(self):
        d = self.depts / "marketing"
        role = d / "01-content-writer"
        role.mkdir(parents=True)
        (role / "TOOLS.md").write_text("owner role tools\n")
        (role / "USER.md").symlink_to(self.ws / "USER.md")
        CRW.augment_all_existing_role_folders(d, self.ws)
        self.assertEqual((role / "TOOLS.md").read_text(), "owner role tools\n")
        self.assertFalse((role / "USER.md").is_symlink())
        self.assertEqual((role / "USER.md").read_bytes(), (self.ws / "USER.md").read_bytes())
        new = CRW.create_role_workspace(d, "Brand Strategist", self.ws, {"slug": "brand-strategist", "number": 2})
        for f in ("TOOLS.md", "USER.md"):
            self.assertFalse((Path(new) / f).is_symlink())
            self.assertEqual((Path(new) / f).read_bytes(), (self.ws / f).read_bytes())


class TestScaffoldAgentFiles(_Box):
    def test_scaffold_keeps_real_files_and_never_symlinks(self):
        d = self.depts / "ops"
        d.mkdir()
        (d / "AGENTS.md").write_text("owner agents\n")
        (d / "TOOLS.md").symlink_to(self.ws / "TOOLS.md")
        script = ROOT / "32-command-center-setup" / "scripts" / "scaffold-agent-files.sh"
        r = subprocess.run(["bash", str(script), "--agent-slug", "ops", "--agent-name", "Ops Head",
                            "--department", "ops", "--workspace-dir", str(d), "--shared-root", str(self.ws)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((d / "AGENTS.md").read_text(), "owner agents\n")
        for f in CORE:
            self.assertFalse((d / f).is_symlink(), f"{f} is a symlink")
        self.assertEqual((d / "USER.md").read_bytes(), (self.ws / "USER.md").read_bytes())
        self.assertEqual((d / "TOOLS.md").read_bytes(), (self.ws / "TOOLS.md").read_bytes())


class TestAgentRegistration(_Box):
    EXPLICIT = {"primary": "ollama/owner-picked:cloud", "fallbacks": ["ollama/owner-fallback:cloud"]}

    def _register(self, cfg, depts):
        for dept_id in depts:
            (self.depts / dept_id).mkdir(exist_ok=True)
            BW.add_agent_to_config(cfg, dept_id, {"head": f"{dept_id} head"})

    def test_existing_agent_model_untouched_list_schema(self):
        cfg = {"agents": {"defaults": {"model": {"primary": "ollama/box-default:cloud"}},
                          "list": [{"id": "dept-marketing", "workspace": str(self.depts / "marketing"),
                                    "model": copy.deepcopy(self.EXPLICIT)}]}}
        defaults = copy.deepcopy(cfg["agents"]["defaults"])
        self._register(cfg, ["marketing"])
        self.assertEqual(cfg["agents"]["list"][0]["model"], self.EXPLICIT)
        self.assertEqual(cfg["agents"]["defaults"], defaults)
        self.assertEqual(len(cfg["agents"]["list"]), 1)

    def test_existing_agent_model_untouched_entries_schema(self):
        cfg = {"agents": {"defaults": {"model": {"primary": "ollama/box-default:cloud"}},
                          "list": [],
                          "entries": {"dept-marketing": {"workspace": str(self.depts / "marketing"),
                                                         "model": copy.deepcopy(self.EXPLICIT)},
                                      "dept-sales": {"workspace": str(self.depts / "sales"),
                                                     "model": "ollama/owner-string-pin:cloud"}}}}
        before = copy.deepcopy(cfg)
        self._register(cfg, ["marketing", "sales"])
        self.assertEqual(cfg, before, "an already-registered entries box must be a byte-level no-op")

    def test_department_registered_under_another_key_is_left_alone(self):
        # The box serves departments/marketing from an entry keyed "marketing" with
        # the owner's own model. The build must not add a second dept-marketing
        # entry (duplicate registration) carrying a build-resolved model.
        cfg = {"agents": {"list": [],
                          "entries": {"marketing": {"workspace": str(self.depts / "marketing"),
                                                    "model": copy.deepcopy(self.EXPLICIT)}}}}
        before = copy.deepcopy(cfg)
        for _ in range(2):
            self._register(cfg, ["marketing"])
            self.assertEqual(cfg, before)
        self.assertFalse(BW._missing_dept_agents(cfg, {"dept-marketing"}))

    def test_entries_box_second_run_adds_no_duplicates(self):
        cfg = {"agents": {"entries": {"main": {"workspace": str(self.ws)},
                                      "dept-marketing": {"workspace": str(self.depts / "marketing")}}}}
        self._register(cfg, ["marketing", "sales"])
        first = copy.deepcopy(cfg)
        self.assertNotIn("list", cfg["agents"])
        self.assertIn("dept-sales", cfg["agents"]["entries"])
        self.assertNotIn("id", cfg["agents"]["entries"]["dept-sales"])
        self._register(cfg, ["marketing", "sales"])
        self.assertEqual(cfg, first, "second build run must be a no-op")
        workspaces = [e.get("workspace") for e in cfg["agents"]["entries"].values()]
        self.assertEqual(len(workspaces), len(set(workspaces)), "duplicate registration of one workspace")


class TestNewAgentsInheritModelAndConfigValidates(_Box):
    DEFAULTS = {"model": {"primary": "ollama-cloud/owner-default:cloud", "fallbacks": ["ollama-cloud/owner-fb:cloud"]},
                "workspace": "OWNER"}
    DEPTS = ["master-orchestrator", "marketing", "presentations", "quality-control", "graphics"]

    def _post_build_cfg(self):
        cfg = {"agents": {"defaults": copy.deepcopy(self.DEFAULTS),
                          "entries": {"main": {"workspace": str(self.ws)}}}}
        for dept_id in self.DEPTS:
            (self.depts / dept_id).mkdir(exist_ok=True)
            BW.add_agent_to_config(cfg, dept_id, {"head": f"{dept_id} head"})
        return cfg

    def test_new_agents_get_no_model_and_defaults_untouched(self):
        cfg = self._post_build_cfg()
        self.assertEqual(cfg["agents"]["defaults"], self.DEFAULTS)
        for dept_id in self.DEPTS:
            entry = cfg["agents"]["entries"][f"dept-{dept_id}"]
            self.assertNotIn("model", entry, f"dept-{dept_id} must inherit agents.defaults")
            self.assertEqual(entry["subagents"], {"allowAgents": ["*"]})
        self.assertNotRegex(str(cfg["agents"]["entries"]), r"(ollama|openrouter)(-cloud)?/",
                            "the build must never write a model id into openclaw.json")

    def test_build_source_never_writes_agents_defaults(self):
        import re
        src = (SCRIPTS / "build-workforce.py").read_text()
        self.assertIsNone(re.search(r'setdefault\(\s*["\']defaults["\']|\[["\']defaults["\']\]\s*\[[^\]]+\]\s*=', src),
                          "build-workforce.py writes into agents.defaults")

    def test_post_build_config_passes_openclaw_config_validate(self):
        import json
        import shutil
        oc = shutil.which("openclaw")
        if not oc:
            if os.environ.get("REQUIRE_OPENCLAW_VALIDATE") == "1":
                self.fail("REQUIRE_OPENCLAW_VALIDATE=1 but no openclaw CLI on PATH")
            self.skipTest("openclaw CLI not on PATH (the no-model / no-defaults tests above still gate CI)")
        cfg = self._post_build_cfg()
        cfg["agents"]["defaults"]["workspace"] = str(self.ws)

        def validate(doc):
            d = Path(self._tmp.name) / "validate"
            (d / ".openclaw").mkdir(parents=True, exist_ok=True)
            p = d / ".openclaw" / "openclaw.json"
            p.write_text(json.dumps(doc))
            env = dict(os.environ, HOME=str(d), OPENCLAW_STATE_DIR=str(d / ".openclaw"),
                       OPENCLAW_CONFIG_PATH=str(p))
            r = subprocess.run([oc, "config", "validate", "--json"], capture_output=True, text=True,
                               env=env, timeout=120)
            out = json.loads(r.stdout[r.stdout.index("{"):])
            self.assertEqual(Path(out["path"]).resolve(), p.resolve(), "validated the wrong file")
            return out

        # Control: the instrument must reject the key the old build wrote.
        bad = copy.deepcopy(cfg)
        bad["agents"]["defaults"]["tools"] = {"allow": ["*"]}
        self.assertFalse(validate(bad)["valid"], "validator did not reject agents.defaults.tools")
        result = validate(cfg)
        self.assertTrue(result["valid"], result.get("issues"))


class TestMaterializeDeptAgents(unittest.TestCase):
    """The build's wiring-repair step (Skill 32 materialize-dept-agents.sh) on an entries box."""

    def test_no_duplicate_for_department_registered_under_another_key(self):
        import json
        with tempfile.TemporaryDirectory() as h:
            oc = Path(h) / ".openclaw"
            ws = oc / "workspace"
            for d in ("marketing", "sales"):
                (ws / "departments" / d).mkdir(parents=True)
                (ws / "departments" / d / "SOUL.md").write_text("soul\n")
            for f in CORE:
                (ws / f).write_text(f"canonical {f}\n")
            (ws / "departments" / "marketing" / "AGENTS.md").write_text("owner agents\n")
            (ws / ".workforce-build-state.json").write_text('{"interviewComplete": true}')
            owned = {"workspace": str(ws / "departments" / "marketing"),
                     "model": {"primary": "ollama/owner-picked:cloud"}}
            cfg_path = oc / "openclaw.json"
            cfg_path.write_text(json.dumps({"agents": {"entries": {"main": {"workspace": str(ws)},
                                                                   "marketing": owned}}}))
            script = ROOT / "32-command-center-setup" / "scripts" / "materialize-dept-agents.sh"
            for _ in range(2):
                r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                                   env=dict(os.environ, HOME=h))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            agents = json.loads(cfg_path.read_text())["agents"]
            self.assertNotIn("list", agents)
            self.assertEqual(sorted(agents["entries"]), ["dept-sales", "main", "marketing"])
            self.assertEqual(agents["entries"]["marketing"], owned)
            self.assertNotIn("model", agents["entries"]["dept-sales"])
            self.assertEqual((ws / "departments" / "marketing" / "AGENTS.md").read_text(), "owner agents\n")
            for f in CORE:
                p = ws / "departments" / "sales" / f
                self.assertFalse(p.is_symlink(), f"sales/{f} is a symlink")
                self.assertEqual(p.read_text(), f"canonical {f}\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
