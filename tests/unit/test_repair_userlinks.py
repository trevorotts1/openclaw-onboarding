#!/usr/bin/env python3
"""repair-userlinks.py: broken USER.md symlinks are re-pointed, nothing else moves.

Covers 23-ai-workforce-blueprint/scripts/repair/repair-userlinks.py:

  * a broken link in a department is re-pointed to that department's real USER.md
    (department preferred over the workspace file);
  * with no usable department USER.md, the workspace USER.md is the fallback;
  * a department USER.md that is itself broken is settled first (shallowest
    first), so its roles then land on it;
  * a link with no usable replacement is reported "unresolved", left exactly as
    it was, and the exit code is 3;
  * regular USER.md files, healthy links and other broken links are never touched;
  * idempotent: a second run finds nothing and changes nothing (same inodes);
  * --dry-run writes nothing and plans exactly what the real run then does;
  * --json emits the report counts; exit codes 0 / 1 / 3 hold;
  * a 641-link fixture gives 640 repaired + 1 left unresolved.

Every fixture is synthetic and built inside the test's own temporary directory.
The script is always pointed at it with --workspace / --departments-dir (or the
function arguments); no real workspace or box path is ever read or written.

Run: python3 tests/unit/test_repair_userlinks.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "23-ai-workforce-blueprint" / "scripts" / "repair" / "repair-userlinks.py"
NAME = "USER.md"
GONE = "no-such-dir/USER.md"  # dangling link target used by every fixture


def _load():
    spec = importlib.util.spec_from_file_location("repair_userlinks", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RU = _load()


def snapshot(base):
    """Everything under base: links by target + inode + mtime, files by bytes."""
    snap = {}
    for root, dirs, files in os.walk(base, followlinks=False):
        for n in dirs + files:
            p = Path(root) / n
            rel = str(p.relative_to(base))
            st = os.lstat(p)
            if p.is_symlink():
                snap[rel] = ("link", os.readlink(p), st.st_ino, st.st_mtime_ns)
            elif p.is_dir():
                snap[rel] = ("dir",)
            else:
                snap[rel] = ("file", p.read_bytes())
    return snap


class _Box(unittest.TestCase):
    """A throwaway workspace: <tmp>/ws/{USER.md, departments/<dept>/<role>/}."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(os.path.realpath(self._td.name))
        self.ws = self.tmp / "ws"
        self.deps = self.ws / "departments"
        self.deps.mkdir(parents=True)

    def role(self, dept, role):
        d = self.deps / dept / role
        d.mkdir(parents=True, exist_ok=True)
        return d

    def broken(self, dept, role):
        link = self.role(dept, role) / NAME
        link.symlink_to(GONE)
        return link

    def cli(self, *extra, workspace=True):
        env = {k: v for k, v in os.environ.items() if k != "OPENCLAW_WORKSPACE"}
        args = [sys.executable, str(SCRIPT)]
        if workspace:
            args += ["--workspace", str(self.ws), "--departments-dir", str(self.deps)]
        return subprocess.run(args + list(extra), capture_output=True, text=True,
                              env=env, timeout=120)


class TestTargetPreference(_Box):
    def test_department_user_md_preferred_over_workspace(self):
        (self.ws / NAME).write_text("workspace user\n")
        self.role("sales", "closer")
        (self.deps / "sales" / NAME).write_text("sales user\n")
        link = self.broken("sales", "closer")

        rep = RU.run(self.ws, self.deps, dry_run=False)

        self.assertEqual((rep["broken_found"], rep["to_department"],
                          rep["to_workspace"], rep["unresolved"]), (1, 1, 0, 0))
        self.assertEqual(rep["items"][0]["via"], "department")
        self.assertEqual(link.read_text(), "sales user\n")
        self.assertEqual(Path(os.path.realpath(link)), self.deps / "sales" / NAME)

    def test_workspace_user_md_is_the_fallback(self):
        (self.ws / NAME).write_text("workspace user\n")
        link = self.broken("ops", "planner")  # ops has no USER.md of its own

        rep = RU.run(self.ws, self.deps, dry_run=False)

        self.assertEqual((rep["broken_found"], rep["to_department"],
                          rep["to_workspace"], rep["unresolved"]), (1, 0, 1, 0))
        self.assertEqual(rep["items"][0]["via"], "workspace")
        self.assertEqual(link.read_text(), "workspace user\n")
        self.assertEqual(Path(os.path.realpath(link)), self.ws / NAME)

    def test_broken_department_user_md_settles_first_then_roles_follow_it(self):
        (self.ws / NAME).write_text("workspace user\n")
        dept_link = self.deps / "legal" / NAME
        self.role("legal", "counsel")
        dept_link.symlink_to(GONE)  # the department's own USER.md is broken too
        role_link = self.broken("legal", "counsel")

        rep = RU.run(self.ws, self.deps, dry_run=False)

        # department file -> workspace; its role then -> the (now real) department file
        self.assertEqual((rep["broken_found"], rep["to_department"],
                          rep["to_workspace"], rep["unresolved"]), (2, 1, 1, 0))
        self.assertEqual(dept_link.read_text(), "workspace user\n")
        self.assertEqual(role_link.read_text(), "workspace user\n")
        self.assertEqual(Path(os.path.realpath(role_link)), self.ws / NAME)

    def test_new_link_is_relative_and_survives_a_moved_box(self):
        (self.ws / NAME).write_text("workspace user\n")
        self.broken("ops", "planner")
        RU.run(self.ws, self.deps, dry_run=False)
        link = self.deps / "ops" / "planner" / NAME
        self.assertFalse(os.path.isabs(os.readlink(link)))

        moved = self.tmp / "ws-moved"
        self.ws.rename(moved)
        self.assertEqual((moved / "departments/ops/planner" / NAME).read_text(),
                         "workspace user\n")

    def test_self_referencing_link_counts_as_broken_and_is_repaired(self):
        (self.ws / NAME).write_text("workspace user\n")
        link = self.role("ops", "loopy") / NAME
        link.symlink_to(NAME)  # points at itself: a loop, not a file
        rep = RU.run(self.ws, self.deps, dry_run=False)
        self.assertEqual(rep["broken_found"], 1)
        self.assertEqual(link.read_text(), "workspace user\n")


class TestUnresolved(_Box):
    def test_no_replacement_is_reported_and_left_untouched(self):
        link = self.broken("ops", "planner")  # no dept USER.md, no workspace USER.md
        before = snapshot(self.ws)

        rep = RU.run(self.ws, self.deps, dry_run=False)

        self.assertEqual((rep["broken_found"], rep["unresolved"],
                          rep["to_department"], rep["to_workspace"]), (1, 1, 0, 0))
        item = rep["items"][0]
        self.assertEqual(item["action"], "unresolved")
        self.assertIsNone(item["target"])
        self.assertEqual(item["link"], os.path.join("ops", "planner", NAME))
        self.assertTrue(link.is_symlink() and not os.path.exists(link))
        self.assertEqual(snapshot(self.ws), before)  # byte-for-byte, inode-for-inode

    def test_cli_exit_code_3_and_message_when_unresolved(self):
        self.broken("ops", "planner")
        r = self.cli()
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("1 unresolved", r.stdout)
        self.assertIn("unresolved", r.stdout.splitlines()[0])

    def test_cli_exit_code_0_when_everything_resolves(self):
        (self.ws / NAME).write_text("workspace user\n")
        self.broken("ops", "planner")
        r = self.cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0 unresolved", r.stdout)

    def test_cli_exit_code_1_when_departments_dir_missing(self):
        r = self.cli("--departments-dir", str(self.tmp / "nope"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("departments dir not found", r.stderr)


class TestNothingElseIsTouched(_Box):
    def test_regular_files_healthy_links_and_other_names_are_never_modified(self):
        (self.ws / NAME).write_text("workspace user\n")
        (self.deps / "sales").mkdir()
        (self.deps / "sales" / NAME).write_text("sales user\n")

        real = self.role("sales", "real") / NAME
        real.write_text("hand-written role file\n")
        healthy = self.role("sales", "healthy") / NAME
        healthy.symlink_to(os.path.relpath(self.deps / "sales" / NAME, healthy.parent))
        other = self.role("sales", "other") / "NOTES.md"
        other.symlink_to(GONE)  # broken, but not named USER.md
        self.broken("sales", "target")  # the only one that must change

        before = snapshot(self.ws)
        rep = RU.run(self.ws, self.deps, dry_run=False)
        after = snapshot(self.ws)

        self.assertEqual(rep["broken_found"], 1)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        self.assertEqual(changed, {os.path.join("departments", "sales", "target", NAME)})
        self.assertEqual(real.read_text(), "hand-written role file\n")
        self.assertFalse(real.is_symlink())
        self.assertTrue(other.is_symlink() and not os.path.exists(other))

    def test_no_temp_link_is_left_behind(self):
        (self.ws / NAME).write_text("workspace user\n")
        for i in range(5):
            self.broken("ops", "r%d" % i)
        RU.run(self.ws, self.deps, dry_run=False)
        leftovers = [p for p in self.ws.rglob(".USER.md.repair-*")]
        self.assertEqual(leftovers, [])

    def test_skip_dirs_are_not_walked(self):
        (self.ws / NAME).write_text("workspace user\n")
        skipped = self.deps / "sales" / "node_modules" / "pkg"
        skipped.mkdir(parents=True)
        (skipped / NAME).symlink_to(GONE)
        rep = RU.run(self.ws, self.deps, dry_run=False)
        self.assertEqual(rep["broken_found"], 0)
        self.assertTrue((skipped / NAME).is_symlink())


class TestIdempotent(_Box):
    def _build(self):
        (self.ws / NAME).write_text("workspace user\n")
        (self.deps / "a").mkdir()
        (self.deps / "a" / NAME).write_text("a user\n")
        self.broken("a", "role1")
        self.broken("b", "role1")
        self.role("c", "role1")
        (self.deps / "c" / NAME).symlink_to(GONE)
        self.broken("c", "role1")

    def test_second_run_changes_nothing(self):
        self._build()
        first = RU.run(self.ws, self.deps, dry_run=False)
        self.assertEqual(first["broken_found"], 4)
        settled = snapshot(self.ws)

        second = RU.run(self.ws, self.deps, dry_run=False)

        self.assertEqual((second["broken_found"], second["to_department"],
                          second["to_workspace"], second["unresolved"],
                          second["errors"], second["items"]), (0, 0, 0, 0, 0, []))
        self.assertEqual(snapshot(self.ws), settled)  # same targets, same inodes, same mtimes

    def test_second_cli_run_reports_zero_and_exits_0(self):
        self._build()
        self.assertEqual(self.cli("--json").returncode, 0)
        before = snapshot(self.ws)
        r = self.cli("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["broken_found"], 0)
        self.assertEqual(snapshot(self.ws), before)


class TestDryRun(_Box):
    def _build(self):
        (self.ws / NAME).write_text("workspace user\n")
        (self.deps / "a").mkdir()
        (self.deps / "a" / NAME).write_text("a user\n")
        self.broken("a", "role1")
        self.broken("a", "role2")
        self.broken("b", "role1")
        self.broken("d", "role1")
        (self.deps / "d" / NAME).symlink_to(GONE)

    def test_dry_run_writes_nothing(self):
        self._build()
        before = snapshot(self.ws)
        rep = RU.run(self.ws, self.deps, dry_run=True)
        self.assertEqual(snapshot(self.ws), before)
        self.assertTrue(rep["dry_run"])
        self.assertEqual(rep["broken_found"], 5)
        self.assertTrue(all(i["action"] == "would-repoint" for i in rep["items"]))

    def test_dry_run_cli_writes_nothing_and_labels_output(self):
        self._build()
        before = snapshot(self.ws)
        r = self.cli("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY-RUN", r.stdout)
        self.assertIn("would-repoint", r.stdout)
        self.assertEqual(snapshot(self.ws), before)

    def test_dry_run_plans_exactly_what_the_real_run_does(self):
        self._build()
        plan = RU.run(self.ws, self.deps, dry_run=True)
        real = RU.run(self.ws, self.deps, dry_run=False)
        keys = ("broken_found", "to_department", "to_workspace", "unresolved", "errors")
        self.assertEqual({k: plan[k] for k in keys}, {k: real[k] for k in keys})
        self.assertEqual([(i["link"], i["target"], i["via"]) for i in plan["items"]],
                         [(i["link"], i["target"], i["via"]) for i in real["items"]])
        self.assertTrue(all(i["action"] == "repointed" for i in real["items"]))

    def test_dry_run_reports_unresolved_without_failing_the_walk(self):
        self.broken("ops", "planner")
        rep = RU.run(self.ws, self.deps, dry_run=True)
        self.assertEqual((rep["broken_found"], rep["unresolved"]), (1, 1))
        self.assertEqual(self.cli("--dry-run").returncode, 3)


class TestJsonReport(_Box):
    def test_json_counts_and_items(self):
        (self.ws / NAME).write_text("workspace user\n")
        (self.deps / "a").mkdir()
        (self.deps / "a" / NAME).write_text("a user\n")
        self.broken("a", "role1")   # -> department
        self.broken("a", "role2")   # -> department
        self.broken("b", "role1")   # -> workspace

        r = self.cli("--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)

        self.assertEqual({k: rep[k] for k in ("broken_found", "to_department",
                                              "to_workspace", "unresolved", "errors")},
                         {"broken_found": 3, "to_department": 2, "to_workspace": 1,
                          "unresolved": 0, "errors": 0})
        self.assertIs(rep["dry_run"], False)
        self.assertEqual(rep["workspace"], str(self.ws))
        self.assertEqual(rep["departments_dir"], str(self.deps))
        by_link = {i["link"]: i for i in rep["items"]}
        self.assertEqual(set(by_link), {os.path.join("a", "role1", NAME),
                                        os.path.join("a", "role2", NAME),
                                        os.path.join("b", "role1", NAME)})
        self.assertEqual(by_link[os.path.join("b", "role1", NAME)]["via"], "workspace")
        self.assertEqual(by_link[os.path.join("a", "role1", NAME)]["via"], "department")
        self.assertTrue(all(i["action"] == "repointed" for i in rep["items"]))

    def test_json_dry_run_flag_and_unresolved_count(self):
        self.broken("ops", "planner")
        r = self.cli("--json", "--dry-run")
        self.assertEqual(r.returncode, 3, r.stderr)
        rep = json.loads(r.stdout)
        self.assertIs(rep["dry_run"], True)
        self.assertEqual((rep["broken_found"], rep["unresolved"]), (1, 1))
        self.assertEqual(rep["items"][0]["action"], "unresolved")
        self.assertIsNone(rep["items"][0]["target"])

    def test_json_output_is_only_json(self):
        self.broken("ops", "planner")
        r = self.cli("--json")
        json.loads(r.stdout)  # raises if anything else is printed to stdout


class TestScale(_Box):
    def test_641_links_give_640_repaired_and_1_left_unresolved(self):
        # No workspace USER.md. 16 departments x 40 roles each have a department
        # USER.md to point at (640). One role sits in a department with none: kept.
        for d in range(16):
            dept = "dept%02d" % d
            (self.deps / dept).mkdir()
            (self.deps / dept / NAME).write_text("user %d\n" % d)
            for r in range(40):
                self.broken(dept, "role%02d" % r)
        orphan = self.broken("orphan", "role00")

        before = snapshot(self.ws)
        plan = RU.run(self.ws, self.deps, dry_run=True)
        self.assertEqual(snapshot(self.ws), before)
        self.assertEqual((plan["broken_found"], plan["unresolved"]), (641, 1))

        r = self.cli("--json")
        self.assertEqual(r.returncode, 3, r.stderr)
        rep = json.loads(r.stdout)
        self.assertEqual((rep["broken_found"], rep["to_department"], rep["to_workspace"],
                          rep["unresolved"]), (641, 640, 0, 1))
        self.assertTrue(orphan.is_symlink() and not os.path.exists(orphan))
        self.assertEqual((self.deps / "dept07" / "role13" / NAME).read_text(), "user 7\n")

        again = json.loads(self.cli("--json").stdout)  # idempotent: only the orphan remains
        self.assertEqual((again["broken_found"], again["unresolved"]), (1, 1))
        self.assertEqual(again["to_department"] + again["to_workspace"], 0)


class TestSelftest(_Box):
    def test_builtin_selftest_passes(self):
        r = self.cli("--selftest", workspace=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("selftest ok", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
