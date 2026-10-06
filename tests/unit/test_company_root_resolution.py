#!/usr/bin/env python3
"""One company-root resolution order on every layout, build state first.

A build that writes its company somewhere the QC / reconcile / materialize
readers do not look never completes: qc-completeness audits a stale tree,
completionVerification stays pending and buildCompletedAt is never written.

Layouts (each case failed before this fix):
  * Mac, build wrote ~/Downloads/openclaw-master-files/zero-human-company/<slug>
    while ~/clawd exists (the Skill-23 lib resolver answered ~/clawd, and the QC
    template guard rejected every openclaw-master-files path)
  * Mac, same build tree without ~/clawd and without a build state
  * Hostinger /data: /data/openclaw-master-files/zero-human-company/<slug>
  * Contabo /home/node (/data -> /home/node): the master-files root is empty and
    the workforce is <workspace>/zero-human-company/<slug>
  * a box with BOTH floor-fill stubs in <workspace>/departments and the build's
    tree: the checker and the repairer follow the build state, not the stubs

Run: python3 tests/unit/test_company_root_resolution.py
"""
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "23-ai-workforce-blueprint" / "scripts"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SHARED = _load("dp_shared_test", ROOT / "shared-utils" / "detect_platform.py")
LIB = _load("dp_lib_test", ROOT / "23-ai-workforce-blueprint" / "lib" / "detect_platform.py")
QCP = _load("qc_paths_test", SCRIPTS / "_qc_paths.py")
MODS = (SHARED, LIB)


def _company(root, slug="acme-co", depts=("marketing", "sales")):
    c = Path(root) / slug
    for d in depts:
        (c / "departments" / d).mkdir(parents=True, exist_ok=True)
    return c


def _state(workspace, company):
    Path(workspace).mkdir(parents=True, exist_ok=True)
    (Path(workspace) / ".workforce-build-state.json").write_text(
        json.dumps({"companySlug": company.name, "companyRoot": str(company)}))


class _Env(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(os.path.realpath(self._tmp.name))
        self.home = self.base / "home"
        (self.home / ".openclaw" / "workspace").mkdir(parents=True)
        self._saved_env = {k: os.environ.get(k) for k in (
            "HOME", "OPENCLAW_PLATFORM", "OPENCLAW_COMPANY_SLUG", "MASTER_FILES_DIR",
            "WORKFORCE_BUILD_STATE_FILE")}
        for k in self._saved_env:
            os.environ.pop(k, None)
        os.environ["HOME"] = str(self.home)
        self._saved_data = [m.DATA_ROOT for m in MODS if hasattr(m, "DATA_ROOT")]
        self.data = self.base / "nodata"  # no VPS volume unless a test builds one
        for m in MODS:
            m.DATA_ROOT = self.data

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for m, v in zip(MODS, self._saved_data):
            m.DATA_ROOT = v
        self._tmp.cleanup()

    @property
    def ws(self):
        return self.home / ".openclaw" / "workspace"

    def company_dirs(self):
        return [m.get_openclaw_paths()["company_dir"] for m in MODS]

    def qc_company_info(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / "_qc_company_info.py")],
                           capture_output=True, text=True,
                           env=dict(os.environ, SCRIPT_DIR=str(SCRIPTS)))
        return json.loads(r.stdout)


class TestMacLayouts(_Env):
    def test_master_files_build_with_clawd_present_and_build_state(self):
        (self.home / "clawd" / "zero-human-company" / "old-stale-co" / "departments").mkdir(parents=True)
        build = _company(self.home / "Downloads" / "openclaw-master-files" / "zero-human-company")
        _state(self.ws, build)
        self.assertEqual(self.company_dirs(), [build, build])
        info = self.qc_company_info()
        self.assertEqual(info["departments_dir"], str(build / "departments"), info)

    def test_master_files_build_without_clawd_or_state(self):
        build = _company(self.home / "Downloads" / "openclaw-master-files" / "zero-human-company")
        self.assertEqual(self.company_dirs(), [build, build])
        info = self.qc_company_info()
        self.assertEqual(info["company_root"], str(build), info)
        self.assertEqual(info["departments_dir"], str(build / "departments"), info)

    def test_build_tree_wins_over_floor_fill_stubs_in_workspace(self):
        (self.ws / "departments" / "marketing").mkdir(parents=True)
        (self.ws / "departments" / "sales").mkdir(parents=True)
        build = _company(self.home / "Downloads" / "openclaw-master-files" / "zero-human-company")
        _state(self.ws, build)
        self.assertEqual(QCP.live_departments_dir(data_openclaw=self.data / ".openclaw", home=self.home),
                         build / "departments")
        self.assertEqual(QCP.departments_root_for(self.ws), build / "departments")
        self.assertEqual(self.qc_company_info()["departments_dir"], str(build / "departments"))

    def test_no_build_state_keeps_the_live_workspace_tree(self):
        (self.ws / "departments" / "marketing").mkdir(parents=True)
        self.assertEqual(QCP.departments_root_for(self.ws), self.ws / "departments")

    def test_genuine_template_dir_is_still_not_a_company(self):
        tpl = self.home / "Downloads" / "openclaw-master-files" / "23-ai-workforce-blueprint" / "templates"
        (tpl / "departments" / "marketing").mkdir(parents=True)
        (tpl / "departments" / "sales").mkdir(parents=True)
        _state(self.ws, tpl)  # a build state pointing into the template tree
        info = self.qc_company_info()
        self.assertNotIn("openclaw-master-files/23-ai-workforce-blueprint", json.dumps(info))


class TestVpsLayouts(_Env):
    def _vps(self, data):
        for m in MODS:
            m.DATA_ROOT = data
        (data / ".openclaw" / "workspace").mkdir(parents=True, exist_ok=True)
        return data / ".openclaw" / "workspace"

    def test_hostinger_data_master_files(self):
        data = self.base / "data"
        ws = self._vps(data)
        build = _company(data / "openclaw-master-files" / "zero-human-company")
        self.assertEqual(self.company_dirs(), [build, build])
        _state(ws, build)
        self.assertEqual(self.company_dirs(), [build, build])

    def test_contabo_home_node_workspace_tree(self):
        home_node = self.base / "home-node"
        (home_node / "openclaw-master-files" / "zero-human-company").mkdir(parents=True)  # empty
        data = self.base / "data"
        data.symlink_to(home_node)  # /data -> /home/node on these boxes
        ws = self._vps(data)
        build = _company(ws / "zero-human-company")
        self.assertEqual(self.company_dirs(), [build, build])
        _state(ws, build)
        self.assertEqual(self.company_dirs(), [build, build])
        self.assertEqual(QCP.departments_root_for(ws), build / "departments")


class TestOneResolver(unittest.TestCase):
    def test_both_detect_platform_copies_share_the_resolver_verbatim(self):
        for fn in ("build_state_company", "known_company_roots", "resolve_active_company_dir"):
            self.assertEqual(inspect.getsource(getattr(SHARED, fn)), inspect.getsource(getattr(LIB, fn)), fn)

    def test_explicit_slug_never_falls_back_to_another_tenant(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "zhc"
            _company(root, "other-co")
            os.environ["OPENCLAW_COMPANY_SLUG"] = "acme-co"
            try:
                self.assertIsNone(SHARED.resolve_active_company_dir(root, workspace=Path(t) / "ws"))
            finally:
                os.environ.pop("OPENCLAW_COMPANY_SLUG")


if __name__ == "__main__":
    unittest.main(verbosity=2)
