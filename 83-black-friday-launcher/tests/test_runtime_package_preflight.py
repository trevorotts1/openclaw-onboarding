"""The launcher installs a missing runtime package itself, silently, before it builds anything.

A client's agent once opened with "jsonschema isn't importable ... want me to install it?". The
client is never asked: dependencies.ensure_runtime_packages installs the package under
sys.executable, re-checks it with a real import, and only a package that still fails reaches
`require`, which tells the operator, not the client.

Hermetic: the package is a throwaway module in a temp dir and the installer is a stub, so no
pip, no network and nothing outside the temp dir is touched. Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import cli, dependencies  # noqa: E402

FAKE = "bf83_throwaway_pkg"  # not a real package: it can never be installed by accident


class RuntimePackagePreflight(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        manifest = self.dir / "dependencies.json"
        manifest.write_text(json.dumps({"target": "test", "entries": [
            {"id": "runtime-fake", "kind": "runtime_package", "ref": FAKE, "required": True,
             "why": "test"}]}), encoding="utf-8")
        patch = mock.patch.object(dependencies, "MANIFEST", manifest)
        patch.start()
        self.addCleanup(patch.stop)
        sys.path.insert(0, str(self.dir))
        self.addCleanup(lambda: sys.path.remove(str(self.dir)))
        self.addCleanup(lambda: sys.modules.pop(FAKE, None))
        self.specs: list = []

    def externally_managed_pip(self, pip_present: bool = True):
        """A fake `python -m pip` for a Homebrew/Debian interpreter (PEP 668): plain and --user installs are
        refused, `--target` works. Records every command line."""
        self.cmds: list = []

        def run(cmd, **kwargs):
            self.cmds.append(list(cmd))
            if not pip_present:
                return subprocess.CompletedProcess(cmd, 1, b"", b"No module named pip")
            if "--target" not in cmd:
                return subprocess.CompletedProcess(cmd, 1, b"", b"error: externally-managed-environment")
            target = Path(cmd[cmd.index("--target") + 1])
            (target / f"{FAKE}.py").write_text("VALUE = 1\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return mock.patch.object(dependencies.subprocess, "run", run)

    def use_pydeps_folder(self) -> Path:
        folder = self.dir / "pydeps" / "pyX.Y"
        env = mock.patch.dict(os.environ, {"OC_PYDEPS_DIR": str(folder)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), [p for p in sys.path if p != str(folder)]))
        return folder

    def test_on_an_externally_managed_python_the_install_is_pip_target_into_the_pydeps_folder(self):
        folder = self.use_pydeps_folder()
        with self.externally_managed_pip(), contextlib.redirect_stderr(io.StringIO()):
            report = dependencies.ensure_runtime_packages()  # the REAL installer, with a fake pip
        self.assertEqual(len(self.cmds), 1, self.cmds)  # one install, no tier ladder
        cmd = self.cmds[0]
        self.assertEqual(cmd[:4], [sys.executable, "-m", "pip", "install"])
        self.assertEqual(cmd[cmd.index("--target") + 1], str(folder))
        self.assertIn("--upgrade", cmd)
        for forbidden in ("--break-system-packages", "--user"):
            self.assertNotIn(forbidden, cmd)
        self.assertEqual(cmd[-1], FAKE)
        self.assertEqual(report["blockers"], [])  # the folder was put on sys.path and the real import worked
        self.assertEqual(sys.path[0], str(folder))

    def test_a_python_with_no_pip_is_a_plain_operator_message_and_nothing_is_bootstrapped(self):
        folder = self.use_pydeps_folder()
        real = dependencies.ensure_runtime_packages
        with self.externally_managed_pip(pip_present=False), \
                mock.patch.object(dependencies, "ensure_runtime_packages", lambda root=None: real(root)), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(dependencies.DependencyError) as ctx:
            dependencies.require()
        self.assertEqual(len(self.cmds), 1)
        message = str(ctx.exception)
        self.assertIn("python3 -m launcher_core.cli dependencies --install", message)
        self.assertIn(str(folder), message)
        self.assertIn("python3-pip", message)
        self.assertIn("never --break-system-packages", message)

    def installer(self, succeeds: bool):
        def install(spec: str) -> bool:
            self.specs.append(spec)
            if succeeds:  # what a successful pip install leaves behind
                (self.dir / f"{FAKE}.py").write_text("VALUE = 1\n", encoding="utf-8")
            return succeeds
        return install

    def test_a_missing_package_is_installed_and_the_report_is_green(self):
        with contextlib.redirect_stderr(io.StringIO()):
            report = dependencies.ensure_runtime_packages(install=self.installer(True))
        self.assertEqual(self.specs, [FAKE])
        self.assertEqual(report["blockers"], [])

    def test_a_present_package_is_never_reinstalled(self):  # control: the installer is not always firing
        (self.dir / f"{FAKE}.py").write_text("VALUE = 1\n", encoding="utf-8")
        importlib.invalidate_caches()
        report = dependencies.ensure_runtime_packages(install=self.installer(True))
        self.assertEqual(self.specs, [])
        self.assertEqual(report["blockers"], [])

    def test_a_failed_install_still_blocks_and_the_message_is_for_the_operator(self):
        real = dependencies.ensure_runtime_packages
        with mock.patch.object(dependencies, "ensure_runtime_packages",
                               lambda root=None: real(root, install=self.installer(False))):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(dependencies.DependencyError) as ctx:
                dependencies.require()
        message = str(ctx.exception)
        self.assertIn("AF-LAUNCH-DEPENDENCY", message)
        self.assertIn("Nothing was built", message)
        self.assertIn("for the operator, not the client", message)
        self.assertIn(sys.executable, message)

    def setup_note(self, **kwargs) -> str:
        """What ensure_runtime_packages tells the operator on stderr."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            dependencies.ensure_runtime_packages(**kwargs)
        return err.getvalue()

    def test_a_successful_install_says_it_was_installed(self):
        note = self.setup_note(install=self.installer(True))
        self.assertIn("was installed automatically", note)
        self.assertNotIn("could NOT", note)

    def test_a_failed_install_never_claims_success(self):  # S3: it used to print "installed" whatever pip did
        note = self.setup_note(install=self.installer(False))
        self.assertIn("could NOT be installed automatically", note)
        self.assertIn(FAKE, note)  # names the package, for the operator
        self.assertIn("python3 -m launcher_core.cli dependencies --install", note)
        self.assertNotIn("was installed automatically", note)

    def test_an_install_that_reports_success_but_leaves_the_package_unimportable_is_not_success(self):
        note = self.setup_note(install=lambda spec: True)  # pip "succeeded" and nothing importable appeared
        self.assertIn("could NOT be installed automatically", note)
        self.assertNotIn("was installed automatically", note)

    def test_a_python_with_no_pip_reports_the_failure_not_success(self):
        self.use_pydeps_folder()
        with self.externally_managed_pip(pip_present=False):
            note = self.setup_note()  # the REAL installer, with no pip behind it
        self.assertIn("could NOT be installed automatically", note)
        self.assertNotIn("was installed automatically", note)

    def test_commands_that_import_the_package_run_the_repair_and_read_only_ones_do_not(self):
        manifest = self.dir / "package-manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        with mock.patch.object(dependencies, "ensure_runtime_packages") as ensure, \
                mock.patch.object(cli.checks, "check_package", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["check", "--manifest", str(manifest), "--root", str(self.dir)]), 0)
            self.assertEqual(ensure.call_count, 1)
            self.assertEqual(cli.main(["seams"]), 0)
            self.assertEqual(ensure.call_count, 1)  # seams reads data only

    def test_the_dependencies_report_and_the_questions_command_never_start_the_repair(self):
        # `dependencies` only reports (its own --install is the one sanctioned fix) and `questions` reads the
        # shared question bank; neither imports a runtime package, so neither may start an install first.
        with mock.patch.object(dependencies, "ensure_runtime_packages") as ensure, \
                mock.patch.object(cli, "cmd_questions", return_value=0) as questions, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["dependencies", "--root", str(self.dir)]), 0)
            self.assertEqual(cli.main(["questions"]), 0)
            self.assertEqual(questions.call_count, 1)  # the command really ran
            self.assertEqual(ensure.call_count, 0)


if __name__ == "__main__":
    unittest.main()
