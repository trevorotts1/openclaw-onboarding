"""Proves scripts/check-no-standalone-release-pr.py rejects a pure version bump
(every file/line bump-version.sh writes, incl. release-cohort.json, the two
agent-browser scripts, README / update-skills.sh relabel lines, JSON
re-serialisation) and accepts a bump that carries a real change."""
import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "check-no-standalone-release-pr.py"
MANIFEST = ROOT / "scripts" / "version-markers.json"
OLD, NEW = "v27.1.77", "v28.0.0"

FILES = {
    "version": OLD + "\n",
    "install.sh": f'#!/bin/sh\nONBOARDING_VERSION="{OLD}"\necho hi\n',
    "update-skills.sh": f'#!/bin/sh\nONBOARDING_VERSION="{OLD}"\n# {OLD} - safe_json_edit\necho hi\n',
    "README.md": f"> **Version:** see `/version` - this repo at {OLD}.\n## Current release: {OLD}\n**Current Version: {OLD}** - x\n",
    "DIRECT-TO-AGENT-UPDATE-MESSAGE.md": f"**{OLD}**\n",
    "cc-compat.json": json.dumps({"onboardingVersion": OLD, "pinnedTag": "v7.6.128"}, indent=2) + "\n",
    "release-cohort.json": json.dumps({"onb_version": OLD, "x": [{"version": OLD}]}, indent=2) + "\n",
    "scripts/agent-browser-reaper.sh": f"#!/bin/sh\n# {OLD}\nreap\n",
    "scripts/guard-agent-browser-managed.sh": f"#!/bin/sh\n# {OLD}\nguard\n",
    "docs/interview-launch-recovery.md": f"Paired releases: onboarding {OLD} / CC v7.6.128.\n",
    "23-ai-workforce-blueprint/skill-version.txt": OLD + "\n",
    "23-ai-workforce-blueprint/templates/role-library/_index.json":
        json.dumps({"version": OLD[1:], "t": "A — B"}, indent=2, ensure_ascii=False) + "\n",
    "CHANGELOG.md": f"## [{OLD}] - old\n",
}


def run(cwd, *a):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True)


class Guard(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="standalone-rel-"))
        (self.d / "scripts").mkdir()
        shutil.copy(MANIFEST, self.d / "scripts" / "version-markers.json")
        run(self.d, "git", "init", "-q", "-b", "main")
        run(self.d, "git", "config", "user.email", "t@example.test")
        run(self.d, "git", "config", "user.name", "t")
        for f, c in FILES.items():
            p = self.d / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(c, encoding="utf-8")
        run(self.d, "git", "add", "-A")
        run(self.d, "git", "commit", "-qm", "base")
        run(self.d, "git", "checkout", "-q", "-b", "rel")
        for f, c in FILES.items():
            n = c.replace(OLD, NEW).replace(OLD[1:], NEW[1:])
            if f == "CHANGELOG.md":
                n = f"## [{NEW}] - new\n\n" + c
            if f.endswith("_index.json"):  # bumper re-serialises with ASCII escapes
                n = json.dumps(json.loads(n), indent=2) + "\n"
            (self.d / f).write_text(n, encoding="utf-8")
        run(self.d, "git", "add", "-A")
        run(self.d, "git", "commit", "-qm", "bump")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def guard(self):
        return run(self.d, sys.executable, str(GUARD), "--base", "main", "--head", "HEAD")

    def test_pure_bump_is_rejected(self):
        r = self.guard()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_bump_plus_new_file_is_accepted(self):
        (self.d / "tests").mkdir()
        (self.d / "tests" / "t.sh").write_text("echo real\n")
        run(self.d, "git", "add", "-A"); run(self.d, "git", "commit", "-qm", "fix")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_real_edit_inside_release_file_is_accepted(self):
        p = self.d / "update-skills.sh"
        p.write_text(p.read_text() + "echo a real behaviour change\n")
        run(self.d, "git", "add", "-A"); run(self.d, "git", "commit", "-qm", "fix")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_real_edit_inside_extra_ceremony_file_is_accepted(self):
        p = self.d / "scripts/agent-browser-reaper.sh"
        p.write_text(p.read_text() + "kill -9 everything\n")
        run(self.d, "git", "add", "-A"); run(self.d, "git", "commit", "-qm", "fix")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
