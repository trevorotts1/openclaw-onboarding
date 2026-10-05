#!/usr/bin/env python3
"""ensure-general-task-dept.py and general-task-check.sh against throwaway workspaces.

The repair script installs the general-task department (the catch-all every unroutable
task lands in) from the shipped role library, with the box's own names. The health
check says whether the department is present with a real playbook. Both run here as
real subprocesses against a temp workspace; nothing outside the temp dir is touched.

Run: python3 -m pytest tests/unit/test_ensure_general_task_dept.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SKILL = REPO / "23-ai-workforce-blueprint"
REPAIR = SKILL / "scripts" / "repair" / "ensure-general-task-dept.py"
HEALTH = REPO / "scripts" / "health" / "general-task-check.sh"
LIB = SKILL / "templates" / "role-library" / "general-task"
ENV = dict(os.environ, OPENCLAW_PLATFORM="mac")
ENV.pop("OPENCLAW_COMPANY_CONFIG", None)
ENV.pop("ROLE_LIBRARY_PATH", None)
OWNER, COMPANY, CEO = "Pat", "Acme Test Co", "Nova"
PLACEHOLDER = "# Role how-to.md  [PENDING - FILL FROM LIBRARY]\n"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Box:
    """A throwaway box: workspace, departments tree, company config, an openclaw.json."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="gt-ensure-"))
        self.ws = self.root / "ws"
        self.dd = self.ws / "departments"
        self.dd.mkdir(parents=True)
        (self.ws / "USER.md").write_text("# user\n")
        (self.ws / "TOOLS.md").write_text("# tools\n")
        self.cfg = self.root / "company-config.json"
        self.cfg.write_text(json.dumps({"companyName": COMPANY, "ownerName": OWNER, "aiCeoName": CEO,
                                        "industry": "retail"}))
        self.oc_json = self.root / "openclaw.json"
        self.oc_json.write_text('{"agents": {"list": []}}')
        self.gt = self.dd / "general-task"

    def repair(self, *extra, ws=True):
        cmd = [sys.executable, str(REPAIR), "--company-config", str(self.cfg), *extra]
        if ws:
            cmd += ["--workspace", str(self.ws)]
        return subprocess.run(cmd, capture_output=True, text=True, env=ENV)

    def health(self):
        return subprocess.run(["bash", str(HEALTH), "--departments-dir", str(self.dd)],
                              capture_output=True, text=True, env=ENV)

    def tree(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class BoxCase(unittest.TestCase):
    def setUp(self):
        self.box = Box()
        self.addCleanup(self.box.close)


class Library(unittest.TestCase):
    """The shipped library holds the one complete general-task playbook."""

    def test_unroutable_task_handler_meets_the_floor_and_covers_the_flow(self):
        p = LIB / "unroutable-task-handler.md"
        text = p.read_text(encoding="utf-8")
        self.assertGreaterEqual(p.stat().st_size, 3072)
        self.assertEqual(sorted(set(re.findall(r"(?m)^## (\d+)\.", text)), key=int), [str(i) for i in range(1, 20)])
        self.assertIn("Persona Governance Override", text)
        for step in ("Receive and Triage", "Do It or Hand It", "SOP-NEEDED"):
            self.assertIn(step, text)
        self.assertNotRegex(text, r"(?i)PENDING.{0,4}FILL FROM LIBRARY|to be personalized|\[TBD\]|lorem ipsum|TODO: fill")
        self.assertGreaterEqual(len(re.findall(r"(?m)^\s*(?:\d+\.|[-*])\s+\S", text)), 5)

    def test_template_has_no_personal_or_client_data(self):
        text = (LIB / "unroutable-task-handler.md").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?i)\bstephanie\b|\btrevor\b|blackceo")
        self.assertNotRegex(text, r"\b\d{9,}\b")                      # no chat ids
        # no hardcoded model ids (the persona section's `gemini-search.py` script name is not a model id)
        self.assertNotRegex(text, r"(?i)claude-(?:opus|sonnet|haiku|\d)|gpt-\d|gemini-\d|deepseek|moonshot|kimi")

    def test_library_is_registered_and_every_member_is_a_real_playbook(self):
        index = json.loads((SKILL / "templates" / "role-library" / "_index.json").read_text(encoding="utf-8"))
        members = [r for r in index["roles"] if r["dept"] == "general-task"]
        self.assertIn("unroutable-task-handler", [r["slug"] for r in members])
        self.assertEqual(index["departments"]["general-task"]["count"], len(members))
        for r in members:
            self.assertGreaterEqual((SKILL / r["path"]).stat().st_size, 3072, r["slug"])


class RepairInstall(BoxCase):
    def test_dry_run_writes_nothing(self):
        before = self.box.tree()
        done = self.box.repair("--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("would-create", done.stdout)
        self.assertEqual(self.box.tree(), before)

    def test_installs_the_department_with_real_playbooks_and_the_boxs_own_names(self):
        done = self.box.repair()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        index = json.loads((SKILL / "templates" / "role-library" / "_index.json").read_text(encoding="utf-8"))
        slugs = [r["slug"] for r in index["roles"] if r["dept"] == "general-task"]
        howtos = sorted(self.box.gt.glob("*/how-to.md"))
        self.assertEqual(len(howtos), len(slugs))
        for h in howtos:
            text = h.read_text(encoding="utf-8")
            self.assertGreaterEqual(h.stat().st_size, 3072, h)
            self.assertNotRegex(text, r"(?i)PENDING.{0,4}FILL FROM LIBRARY|ROUTED.{1,6}WORK HANDLED BY GENERAL-TASK")
            self.assertNotRegex(text, r"\{\{\s*[A-Za-z0-9_]{3,}\s*\}\}", h)   # no unfilled tokens
            self.assertIn(COMPANY, text)
        folders = [h.parent.name for h in howtos]
        self.assertTrue(folders[0].startswith("00-head-of-general-task"))
        handler = next(h for h in howtos if "unroutable-task-handler" in h.parent.name)
        self.assertIn(CEO, handler.read_text(encoding="utf-8"))
        for f in ("IDENTITY.md", "SOUL.md", "TOOLS.md", "ROSTER.md", "how-to-use-this-department.md"):
            self.assertTrue((self.box.gt / f).is_file(), f)
        self.assertTrue((self.box.gt / folders[0] / "SOP" / "00-INDEX.md").is_file())

    def test_second_run_changes_nothing(self):
        self.assertEqual(self.box.repair().returncode, 0)
        digest = {p: sha(p) for p in self.box.gt.rglob("*") if p.is_file()}
        done = self.box.repair()
        self.assertEqual(done.returncode, 0)
        self.assertIn("NO CHANGE", done.stdout)
        self.assertEqual({p: sha(p) for p in self.box.gt.rglob("*") if p.is_file()}, digest)

    def test_json_report_names_every_role(self):
        done = self.box.repair("--json")
        rep = json.loads(done.stdout)
        self.assertTrue(rep["department_created"])
        self.assertEqual({r["action"] for r in rep["roles"]}, {"created"})
        self.assertEqual(rep["errors"], 0)
        self.assertGreater(rep["real_playbooks"], 0)

    def test_never_touches_openclaw_json(self):
        digest = sha(self.box.oc_json)
        self.box.repair()
        self.box.repair()
        self.assertEqual(sha(self.box.oc_json), digest)

    def test_other_departments_are_never_touched(self):
        other = self.box.dd / "sales" / "00-director-of-sales"
        other.mkdir(parents=True)
        (other / "how-to.md").write_text(PLACEHOLDER)
        digest = sha(other / "how-to.md")
        self.box.repair()
        self.assertEqual(sha(other / "how-to.md"), digest)


class RepairHeals(BoxCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.box.repair().returncode, 0)

    def test_placeholder_thin_and_empty_playbooks_are_refilled(self):
        roles = sorted(self.box.gt.glob("0*-*"))
        for role, content in zip(roles, (PLACEHOLDER, "tiny\n", "")):
            (role / "how-to.md").write_text(content)
        done = self.box.repair("--json")
        rep = json.loads(done.stdout)
        self.assertEqual(sorted(r["action"] for r in rep["roles"] if r["action"] != "kept"), ["refilled"] * 3)
        for role in roles[:3]:
            self.assertGreaterEqual((role / "how-to.md").stat().st_size, 3072)
        self.assertEqual(self.box.health().returncode, 0)

    def test_a_real_customised_playbook_is_never_overwritten(self):
        role = sorted(self.box.gt.glob("0*-*"))[0]
        mine = "# My own playbook\n" + ("Real procedure written by the owner. " * 200)
        (role / "how-to.md").write_text(mine)
        self.box.repair()
        self.assertEqual((role / "how-to.md").read_text(), mine)

    def test_a_missing_role_folder_is_recreated(self):
        victim = next(p for p in self.box.gt.glob("*-triage-classifier"))
        shutil.rmtree(victim)
        rep = json.loads(self.box.repair("--json").stdout)
        self.assertEqual([r["action"] for r in rep["roles"] if r["slug"] == "triage-classifier"], ["created"])
        self.assertTrue(any(self.box.gt.glob("*-triage-classifier/how-to.md")))

    def test_a_suffixed_department_folder_is_reused_not_duplicated(self):
        legacy = self.box.dd / "general-task-dept"
        self.box.gt.rename(legacy)
        self.assertEqual(self.box.repair().returncode, 0)
        self.assertEqual(sorted(p.name for p in self.box.dd.iterdir()), ["general-task-dept"])


class RepairFailures(BoxCase):
    def test_no_role_library_exits_1_and_writes_nothing(self):
        before = self.box.tree()
        done = self.box.repair("--skill-dir", str(self.box.root / "nope"))
        self.assertEqual(done.returncode, 1)
        self.assertIn("no role library", done.stderr)
        self.assertEqual(self.box.tree(), before)

    def test_library_templates_below_the_floor_are_reported_never_written(self):
        skill = self.box.root / "skill"
        shutil.copytree(SKILL / "scripts", skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(SKILL / "lib", skill / "lib") if (SKILL / "lib").is_dir() else None
        shutil.copytree(REPO / "shared-utils", self.box.root / "shared-utils",
                        ignore=shutil.ignore_patterns("__pycache__", "decision_engine*", "*.json"))   # crw imports it from beside the skill
        lib = skill / "templates" / "role-library"
        lib.mkdir(parents=True)
        shutil.copy(SKILL / "templates" / "role-library" / "_index.json", lib / "_index.json")
        (lib / "general-task").mkdir()
        for f in LIB.glob("*.md"):
            (lib / "general-task" / f.name).write_text("too thin\n")
        done = self.box.repair("--skill-dir", str(skill))
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertIn("unavailable", done.stdout)
        for h in self.box.gt.glob("*/how-to.md"):
            self.assertNotIn("too thin", h.read_text())


class HealthCheck(BoxCase):
    def test_pass_when_present_with_real_playbooks(self):
        self.box.repair()
        done = self.box.health()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("department-present: PASS", done.stdout)
        self.assertIn("real-playbook: PASS", done.stdout)

    def test_fail_when_the_department_is_missing(self):
        (self.box.dd / "sales").mkdir()
        done = self.box.health()
        self.assertEqual(done.returncode, 1)
        self.assertIn("department-present: FAIL", done.stdout)

    def test_fail_when_every_playbook_is_a_placeholder(self):
        self.box.repair()
        for h in self.box.gt.glob("*/how-to.md"):
            h.write_text(PLACEHOLDER)
        done = self.box.health()
        self.assertEqual(done.returncode, 1)
        self.assertIn("real-playbook: FAIL", done.stdout)
        self.assertIn("no-placeholders: FAIL", done.stdout)

    def test_fail_when_one_playbook_is_a_placeholder(self):
        self.box.repair()
        next(self.box.gt.glob("*-sop-writer/how-to.md")).write_text(PLACEHOLDER)
        done = self.box.health()
        self.assertEqual(done.returncode, 1)
        self.assertIn("real-playbook: PASS", done.stdout)
        self.assertIn("no-placeholders: FAIL", done.stdout)

    def test_a_routing_notice_is_not_a_real_playbook(self):
        self.box.repair()
        notice = "# R how-to.md  [ROUTED — WORK HANDLED BY GENERAL-TASK]\n" + ("x " * 3000)
        for h in self.box.gt.glob("*/how-to.md"):
            h.write_text(notice)
        self.assertEqual(self.box.health().returncode, 1)

    def test_undetermined_is_never_a_pass(self):
        done = subprocess.run(["bash", str(HEALTH), "--departments-dir", str(self.box.root / "none")],
                              capture_output=True, text=True, env=ENV)
        self.assertEqual(done.returncode, 5)

    def test_health_is_read_only(self):
        self.box.repair()
        before = {p: sha(p) for p in self.box.root.rglob("*") if p.is_file()}
        self.box.health()
        self.assertEqual({p: sha(p) for p in self.box.root.rglob("*") if p.is_file()}, before)

    def test_repair_then_health_round_trip_from_nothing(self):
        (self.box.dd / "sales").mkdir()
        self.assertEqual(self.box.health().returncode, 1)
        self.assertEqual(self.box.repair().returncode, 0)
        self.assertEqual(self.box.health().returncode, 0)


if __name__ == "__main__":
    unittest.main()
