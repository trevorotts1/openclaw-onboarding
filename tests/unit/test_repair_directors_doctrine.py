#!/usr/bin/env python3
"""repair-directors-doctrine.py: directors, doctrine and the AI CEO playbook on
an existing box. Every test builds a throwaway box under a temp dir and runs the
real CLI against it; no real workspace is read or written.

Run: python3 tests/unit/test_repair_directors_doctrine.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "23-ai-workforce-blueprint"
SCRIPT = SKILL / "scripts" / "repair" / "repair-directors-doctrine.py"
MARKER = "<!-- DIRECTOR-DOCTRINE:v1 BEGIN -->"
FILLER = ("This paragraph is ordinary department playbook prose that stands in "
          "for a real, substantive procedure written by the department.\n") * 60


def snapshot(root):
    """{relative path: sha256} for every file and symlink under root."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() or p.is_symlink():
            data = os.readlink(p).encode() if p.is_symlink() else p.read_bytes()
            out[str(p.relative_to(root))] = hashlib.sha256(data).hexdigest()
    return out


class Box:
    """A fake box: <tmp>/workspace/{departments,company-config.json,openclaw.json}."""

    def __init__(self, tmp, config=None):
        self.ws = Path(tmp) / "workspace"
        self.depts = self.ws / "departments"
        self.depts.mkdir(parents=True)
        (self.ws / "USER.md").write_text("owner profile\n")
        (self.ws / "TOOLS.md").write_text("tools\n")
        self.cfg = self.ws / "company-config.json"
        self.cfg.write_text(json.dumps(config if config is not None else {
            "companyName": "Acme Co", "ownerName": "Pat", "aiCeoName": "Zed"}))
        self.oc = self.ws / "openclaw.json"
        self.oc.write_text('{"agents": {"defaults": {"model": "keep-me"}}}')

    def role(self, dept, folder, text=None):
        d = self.depts / dept / folder
        d.mkdir(parents=True, exist_ok=True)
        if text is not None:
            (d / "how-to.md").write_text(text)
        return d / "how-to.md"

    def run(self, *flags):
        env = dict(os.environ, ROLE_LIBRARY_PATH=str(SKILL))
        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--json", "--departments-dir", str(self.depts),
             "--config", str(self.cfg), *flags],
            capture_output=True, text=True, env=env)
        try:
            rep = json.loads(r.stdout)
        except ValueError:
            rep = None
        return r.returncode, rep, r.stderr


class TestRepairDirectorsDoctrine(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.box = Box(self._t.name)

    def test_headless_library_dept_gets_library_director_with_names(self):
        self.box.role("crm", "01-crm-platform-administrator", FILLER)
        rc, rep, err = self.box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(rep["directors_created"]), 1)
        self.assertTrue(rep["directors_created"][0]["source"].startswith("library:crm/"))
        how_to = self.box.depts / "crm" / "00-director-of-crm" / "how-to.md"
        text = how_to.read_text()
        self.assertGreaterEqual(len(text.encode()), 3072)
        self.assertNotIn("{{AI_CEO_NAME}}", text)
        self.assertIn("Zed", text)
        self.assertTrue((how_to.parent / "IDENTITY.md").is_file())

    def test_headless_unknown_dept_gets_generic_scaffold(self):
        self.box.role("zz-custom", "01-analyst", FILLER)
        rc, rep, err = self.box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(rep["directors_created"][0]["source"], "scaffold")
        text = (self.box.depts / "zz-custom" / "00-director-of-zz-custom" / "how-to.md").read_text()
        self.assertIn("Zed", text)
        self.assertIn("Acme Co", text)
        self.assertIn("Chain of Command", text)
        self.assertNotIn("{{", text)

    def test_doctrine_appended_once_and_old_bytes_preserved(self):
        original = "# Director of Widgets\n\n" + FILLER
        path = self.box.role("widgets", "00-director-of-widgets", original)
        rc, rep, err = self.box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(rep["doctrine_appended"], ["widgets/00-director-of-widgets/how-to.md"])
        new = path.read_text()
        self.assertTrue(new.startswith(original))
        self.assertEqual(new.count(MARKER), 1)
        self.assertIn("Zed", new)
        self.assertNotIn("{{AI_CEO_NAME}}", new)
        after_first = snapshot(self.box.ws)
        rc, rep, err = self.box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(rep["doctrine_appended"], [])
        self.assertEqual(rep["directors_created"], [])
        self.assertEqual(snapshot(self.box.ws), after_first)

    def test_head_of_playbook_also_gets_doctrine(self):
        path = self.box.role("audio", "01-head-of-audio-production", "# Head\n\n" + FILLER)
        rc, rep, _ = self.box.run()
        self.assertEqual(rc, 0)
        self.assertEqual(path.read_text().count(MARKER), 1)

    def test_playbook_with_doctrine_headings_is_untouched(self):
        text = ("# Director of X\n\n" + FILLER + "\n## Chain of Command\n\nrules\n"
                "\n## Ephemeral Worker Doctrine\n\nrules\n")
        path = self.box.role("x", "00-director-of-x", text)
        before = path.read_bytes()
        rc, rep, _ = self.box.run()
        self.assertEqual(rc, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(rep["doctrine_already_present"], 1)

    def test_placeholder_director_is_skipped_and_reported(self):
        stub = "# Director\n\n[ROUTED — WORK HANDLED BY GENERAL-TASK]\n" + FILLER
        path = self.box.role("x", "00-director-of-x", stub)
        thin = self.box.role("y", "00-director-of-y", "# thin\n")
        before = (path.read_bytes(), thin.read_bytes())
        rc, rep, _ = self.box.run()
        self.assertEqual(rc, 0)
        self.assertEqual((path.read_bytes(), thin.read_bytes()), before)
        self.assertEqual(len(rep["doctrine_skipped"]), 2)

    def test_ceo_playbook_created_from_library_under_config_name(self):
        self.box.role("crm", "00-director-of-crm", FILLER + "\n## Chain of Command\n## Ephemeral\n")
        rc, rep, err = self.box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(rep["ceo_playbook"], "created")
        path = self.box.depts / "ai-ceo" / "01-ai-ceo-zed" / "how-to.md"
        text = path.read_text()
        self.assertGreaterEqual(len(text.encode()), 3072)
        self.assertIn("Zed", text)
        self.assertIn("Pat", text)
        self.assertNotIn("{{AI_CEO_NAME}}", text)
        self.assertIn("Chain of Command", text)

    def test_existing_ceo_playbook_is_kept(self):
        mine = "# My own CEO playbook\n\n" + FILLER
        path = self.box.role("ai-ceo", "01-ai-ceo-someone", mine)
        rc, rep, _ = self.box.run()
        self.assertEqual(rc, 0)
        self.assertEqual(rep["ceo_playbook"], "exists")
        self.assertEqual(path.read_text(), mine)
        self.assertFalse((self.box.depts / "ai-ceo" / "01-ai-ceo-zed").exists())

    def test_no_configured_name_falls_back_to_neutral_label_never_a_persona(self):
        box = Box(self._t.name + "/b", config={"companyName": "Acme Co"})
        box.role("zz-custom", "01-analyst", FILLER)
        rc, rep, err = box.run()
        self.assertEqual(rc, 0, err)
        self.assertEqual(rep["ai_ceo_name_source"], "default")
        out = (box.depts / "ai-ceo" / "01-ai-ceo" / "how-to.md").read_text()
        self.assertIn("AI CEO", out)
        for persona in ("Stephanie", "Stefanie"):
            self.assertNotIn(persona, out)
            self.assertNotIn(persona, json.dumps(rep))

    def test_agent_name_is_used_when_no_explicit_ceo_name(self):
        box = Box(self._t.name + "/c", config={"agentName": "Quill"})
        box.role("zz-custom", "01-analyst", FILLER)
        rc, rep, _ = box.run()
        self.assertEqual(rc, 0)
        self.assertEqual(rep["ai_ceo_name_source"], "agentName")
        self.assertTrue((box.depts / "ai-ceo" / "01-ai-ceo-quill" / "how-to.md").is_file())

    def test_dry_run_writes_nothing_but_reports_the_work(self):
        self.box.role("crm", "01-crm-platform-administrator", FILLER)
        self.box.role("widgets", "00-director-of-widgets", FILLER)
        before = snapshot(self.box.ws)
        rc, rep, err = self.box.run("--dry-run")
        self.assertEqual(rc, 0, err)
        self.assertEqual(snapshot(self.box.ws), before)
        self.assertEqual(len(rep["directors_created"]), 1)
        self.assertEqual(len(rep["doctrine_appended"]), 1)
        self.assertEqual(rep["ceo_playbook"], "would-create")

    def test_never_touches_openclaw_json_or_symlinked_playbooks(self):
        self.box.role("crm", "01-crm-platform-administrator", FILLER)
        real = self.box.ws / "elsewhere.md"
        real.write_text("# Director\n\n" + FILLER)
        d = self.box.depts / "linked" / "00-director-of-linked"
        d.mkdir(parents=True)
        (d / "how-to.md").symlink_to(real)
        oc_before = self.box.oc.read_bytes()
        real_before = real.read_bytes()
        rc, rep, _ = self.box.run()
        self.assertEqual(rc, 0)
        self.assertEqual(self.box.oc.read_bytes(), oc_before)
        self.assertEqual(real.read_bytes(), real_before)
        self.assertTrue((d / "how-to.md").is_symlink())

    def test_missing_departments_dir_exits_1(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--departments-dir",
                            str(Path(self._t.name) / "nope")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)

    def test_script_source_hardcodes_no_persona_name(self):
        src = SCRIPT.read_text()
        for persona in ("Stephanie", "Stefanie", "Trevor", "BlackCEO"):
            self.assertNotIn(persona, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
