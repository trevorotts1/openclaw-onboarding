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

    def _commit(self, msg="change"):
        run(self.d, "git", "add", "-A"); run(self.d, "git", "commit", "-qm", msg)

    def test_cc_pin_plus_bump_is_accepted(self):
        """A Command Center re-pin (pin-cc-tag.py) moves cc-compat pinnedTag and
        release-cohort cc_version alongside the bump: real change, accepted."""
        for f, key in (("cc-compat.json", "pinnedTag"), ("release-cohort.json", "cc_version")):
            p = self.d / f
            d = json.loads(p.read_text())
            d[key] = "v7.6.129"
            p.write_text(json.dumps(d, indent=2) + "\n")
        p = self.d / "docs/interview-launch-recovery.md"
        p.write_text(p.read_text().replace("CC v7.6.128", "CC v7.6.129"))
        self._commit("cc pin")
        r = self.guard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_non_onboarding_semver_change_is_real(self):
        cases = [
            ("cc-compat.json", lambda d: d.update(minVersion="1.2.3")),
            ("release-cohort.json", lambda d: d.update(n999_version="1.38.2")),
        ]
        for f, mut in cases:
            with self.subTest(f=f):
                run(self.d, "git", "reset", "-q", "--hard", "HEAD")
                p = self.d / f
                d = json.loads(p.read_text()); mut(d)
                p.write_text(json.dumps(d, indent=2) + "\n")
                self._commit()
                self.assertEqual(self.guard().returncode, 0)
                run(self.d, "git", "reset", "-q", "--hard", "HEAD~1")
        with self.subTest(f="agent-browser script"):
            p = self.d / "scripts/agent-browser-reaper.sh"
            p.write_text(p.read_text() + "MIN_NODE=20.11.0\n")
            self._commit()
            self.assertEqual(self.guard().returncode, 0)

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
