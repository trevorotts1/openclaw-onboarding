"""Runnable checks for the KIE official agent docs port (unit KIE-U0).

Five checks, no skips, standard library only:

  1. the digest names every source URL, the fetch date 2026-10-09 and both
     vendor archive fingerprints;
  2. kie-common-rules.md carries rule 14 (vendor skills and KIE as a chat
     provider are both never), the kie.ai/logs line and the 402 top-up line,
     and the TOOLS never-line is present in CORE_UPDATES.md and wire.sh;
  3. 07 INSTRUCTIONS.md no longer claims the three-days upload retention;
  4. version strings and CHANGELOG entries exist for skills 07, 74, 66, 68;
  5. qc-kie-setup.sh is report-only: run against a temp box it leaves the box
     byte-identical, and its two planted findings print without mutating.

Run:  python3 07-kie-setup/tests/test_official_docs_port.py
  or: python3 -m unittest discover -s 07-kie-setup/tests -p 'test_*.py'
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(SKILL_DIR, ".."))

DIGEST = os.path.join(SKILL_DIR, "references", "kie-official-agent-docs-digest.md")
RULES = os.path.join(SKILL_DIR, "references", "kie-common-rules.md")
INSTRUCTIONS = os.path.join(SKILL_DIR, "INSTRUCTIONS.md")
CORE_UPDATES = os.path.join(SKILL_DIR, "CORE_UPDATES.md")
WIRE = os.path.join(SKILL_DIR, "wire.sh")
QC = os.path.join(SKILL_DIR, "qc-kie-setup.sh")

SOURCE_URLS = [
    "https://docs.kie.ai/ai-agent/overview.md",
    "https://docs.kie.ai/ai-agent/install-kie-models.md",
    "https://docs.kie.ai/ai-agent/what-can-do.md",
    "https://docs.kie.ai/ai-agent/install-kie-chat-agents.md",
    "https://docs.kie.ai/ai-agent/claude-code.md",
    "https://docs.kie.ai/ai-agent/codex-cli.md",
    "https://docs.kie.ai/ai-agent/grok-build.md",
    "https://docs.kie.ai/ai-agent/troubleshooting.md",
    "https://docs.kie.ai/ai-agent/changelog.md",
    "https://kie.ai/.well-known/agent-skills/index.json",
]

FINGERPRINTS = {
    "kie-models": "f6247b73",       # f6247b734033fad6ba75e0875bc105e2307c9b7e7790317a26c1b68838209f22
    "kie-chat-agents": "f1cbf185",  # f1cbf185af32ff7162dd67d9d257cd527e79846d94cae804e2bb83e08a47e8b0
}

SKILL_VERSIONS = {
    "07-kie-setup": "7.2.0",
    "74-kie-live-adapter": "1.1.6",
    "66-kie-image": "2.2.2",
    "68-kie-audio": "2.3.1",
}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def tree_digest(root):
    """sha256 of every regular file under root: relative path, mode, bytes."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as fh:
                blob = fh.read()
            rows.append("%s|%o|%s" % (
                rel, os.stat(full).st_mode & 0o777,
                hashlib.sha256(blob).hexdigest()))
    return "\n".join(rows)


class TestDigest(unittest.TestCase):
    """1. digest names every source URL, fetch date and both fingerprints."""

    def setUp(self):
        self.text = read(DIGEST)

    def test_every_source_url_named(self):
        missing = [u for u in SOURCE_URLS if u not in self.text]
        self.assertEqual(missing, [], "digest missing source URLs: %s" % missing)

    def test_fetch_date_2026_10_09(self):
        self.assertIn("2026-10-09", self.text)
        self.assertRegex(self.text, r"(?i)fetch(?:ed| date)[^\n]*2026-10-09")

    def test_both_archive_fingerprints(self):
        for name, prefix in FINGERPRINTS.items():
            self.assertIn(prefix, self.text, "digest missing %s fingerprint %s"
                          % (name, prefix))
        # the prefixes must appear as full sha256 values, not bare words
        self.assertRegex(self.text, r"f6247b73[0-9a-f]{56}")
        self.assertRegex(self.text, r"f1cbf185[0-9a-f]{56}")


class TestCommonRules(unittest.TestCase):
    """2. rule 14, kie.ai/logs line, 402 top-up line, TOOLS never-lines."""

    def setUp(self):
        self.rules = read(RULES)

    def test_rule_14_present(self):
        self.assertRegex(self.rules, r"(?m)^## 14\. ")

    def test_rule_14_forbids_vendor_skills(self):
        block = self.rules.split("## 14.", 1)[1]
        self.assertIn("npx skills add https://kie.ai", block)
        self.assertRegex(block, r"(?i)never install")
        self.assertIn("74-kie-live-adapter/scripts/vendor_skill_probe.sh", block)

    def test_rule_14_forbids_kie_chat_provider(self):
        block = self.rules.split("## 14.", 1)[1]
        self.assertIn("api.kie.ai/anthropic", block)
        self.assertRegex(block, r"(?i)never offer KIE as a chat provider")

    def test_kie_ai_logs_line(self):
        self.assertIn("kie.ai/logs", self.rules)

    def test_402_top_up_line(self):
        self.assertIn("402", self.rules)
        self.assertIn("kie.ai/pricing", self.rules)

    def test_tools_never_line_in_core_updates_and_wire(self):
        never = ("KIE: skill 74 is the only paid door. Never install KIE's "
                 "vendor agent skills or point a coding agent at "
                 "api.kie.ai/anthropic.")
        self.assertIn(never, read(CORE_UPDATES), "CORE_UPDATES.md missing TOOLS never-line")
        self.assertIn(never, read(WIRE), "wire.sh missing TOOLS never-line")


class TestInstructionsRetention(unittest.TestCase):
    """3. INSTRUCTIONS.md no longer carries the three-days upload claim."""

    def test_no_three_days_upload_claim(self):
        text = read(INSTRUCTIONS)
        self.assertNotIn("deleted after 3 days", text)
        self.assertNotRegex(text, r"(?i)uploaded files[^\n]*3 days")

    def test_24_hours_claim_present(self):
        self.assertIn("deleted after 24 hours", read(INSTRUCTIONS))


class TestVersionsAndChangelogs(unittest.TestCase):
    """4. version strings and CHANGELOG entries for all four skills."""

    def test_skill_version_files(self):
        for skill, version in SKILL_VERSIONS.items():
            path = os.path.join(REPO, skill, "skill-version.txt")
            self.assertEqual(read(path).strip(), "v" + version,
                             "%s skill-version.txt not v%s" % (skill, version))

    def test_skill_md_frontmatter(self):
        for skill, version in SKILL_VERSIONS.items():
            text = read(os.path.join(REPO, skill, "SKILL.md"))
            self.assertRegex(
                text, r"(?m)^version: v%s\s*$" % re.escape(version),
                "%s SKILL.md frontmatter not v%s" % (skill, version))

    def test_changelog_entries(self):
        for skill, version in SKILL_VERSIONS.items():
            text = read(os.path.join(REPO, skill, "CHANGELOG.md"))
            pattern = r"(?m)^## \[v?%s\]" % re.escape(version)
            self.assertRegex(text, pattern,
                             "%s CHANGELOG.md missing a %s entry" % (skill, version))


class TestQcReportOnly(unittest.TestCase):
    """5. qc-kie-setup.sh reports findings and never mutates a temp box."""

    def _seed_box(self, home):
        secrets = os.path.join(home, ".openclaw", "secrets")
        os.makedirs(secrets, exist_ok=True)
        env_path = os.path.join(secrets, ".env")
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write("KIE_API_KEY=qc-report-only-fixture\n")
        os.chmod(env_path, 0o600)
        # planted positive control (a): a vendor skill folder
        vendor = os.path.join(home, ".claude", "skills", "kie-models")
        os.makedirs(vendor, exist_ok=True)
        with open(os.path.join(vendor, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("# planted vendor skill fixture\n")
        # planted positive control (b): a settings.json pointing at KIE
        claude = os.path.join(home, ".claude")
        with open(os.path.join(claude, "settings.json"), "w", encoding="utf-8") as fh:
            fh.write(json_env({"ANTHROPIC_BASE_URL": "https://api.kie.ai/anthropic"}))

    def test_report_only_and_positive_controls(self):
        home = tempfile.mkdtemp(prefix="kie-u0-qcbox-")
        try:
            self._seed_box(home)
            before = tree_digest(home)
            env = dict(os.environ,
                       HOME=home,
                       KIE_QC_OFFLINE="1",
                       KIE_API_KEY="qc-report-only-fixture",
                       OPENCLAW_WORKSPACE=os.path.join(home, "workspace"),
                       PYTHONDONTWRITEBYTECODE="1")
            env.pop("CLAUDE_CONFIG_DIR", None)
            proc = subprocess.run(
                ["/bin/bash", QC], env=env, capture_output=True, text=True,
                cwd=SKILL_DIR, timeout=180)
            after = tree_digest(home)
            self.assertEqual(before, after,
                             "qc-kie-setup.sh mutated the temp box")
            out = proc.stdout + proc.stderr
            self.assertIn("Report-only box findings", out)
            self.assertRegex(out, r"FINDING: vendor skill folder present")
            self.assertRegex(out, r"FINDING: settings env points at KIE")
            self.assertNotIn("rm -rf", out)
        finally:
            shutil.rmtree(home, ignore_errors=True)


def json_env(env):
    import json
    return json.dumps({"env": env})


if __name__ == "__main__":
    unittest.main(verbosity=2)
