#!/usr/bin/env python3
"""Tests for scripts/fleet-roll/harvest-sop-drafts.py (fleet SOP draft harvester).

Hermetic: a throwaway copy of the library scripts + rubric + ONE real template
is built in a temp dir and made into a git repo. No box, no network, no real
fleet-access call, no change to the live library.

Proves: personal data / boilerplate / thin drafts are rejected, a good draft is
staged, the higher-scoring duplicate wins, an existing template is never
overwritten, an unreadable box is UNDETERMINED (not empty), zero answering
boxes fails, and the staged branch passes the library's own checks.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tarfile
import io
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "scripts" / "fleet-roll" / "harvest-sop-drafts.py"
SKILL = REPO / "23-ai-workforce-blueprint"
LIB = SKILL / "templates" / "role-library"
GOOD_SRC = LIB / "account-management" / "retention-specialist.md"

spec = importlib.util.spec_from_file_location("harvest_sop_drafts", str(TOOL))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def run(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)


def make_repo(root):
    """Minimal repo: library scripts, shared-utils, rubric, token reference, one role, git history."""
    shutil.copytree(SKILL / "scripts", root / "23-ai-workforce-blueprint" / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "archive"))
    shutil.copytree(REPO / "shared-utils", root / "shared-utils", ignore=shutil.ignore_patterns("__pycache__"))
    lib = root / "23-ai-workforce-blueprint" / "templates" / "role-library"
    (lib / "account-management").mkdir(parents=True)
    for n in ("_sop-writer.md", "_token-reference.md"):
        shutil.copy(LIB / n, lib / n)
    shutil.copy(GOOD_SRC, lib / "account-management" / "retention-specialist.md")
    (lib / "_index.json").write_text('{"roles":[],"departments":{}}\n')
    r = run(sys.executable, str(root / "23-ai-workforce-blueprint/scripts/register-library-additions.py"), "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"],
                ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base"]):
        assert run("git", *cmd, cwd=root).returncode == 0
    return root


def good_text(role="Quality Auditor"):
    """A real shipped template, retitled; passes every rubric check."""
    t = GOOD_SRC.read_text(encoding="utf-8")
    return t.replace("Retention Specialist", role, 1)


def put_draft(base, box, dept, role_slug, text, title=None, tamper=False):
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    d = Path(base) / box / dept
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.%s.draft.md" % (role_slug, sha[:8]))).write_text(text, encoding="utf-8")
    rec = {"schema": h.HARVEST_SCHEMA, "role": title or role_slug.replace("-", " ").title(), "role_slug": role_slug,
           "department": dept, "content_sha": "sha256:" + ("0" * 64 if tamper else sha)}
    (d / ("%s.%s.sop-needed.json" % (role_slug, sha[:8]))).write_text(json.dumps(rec))
    return sha[:8]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rf008-harvest-test-"))
        self.repo = make_repo(self.tmp / "repo")
        self.drafts = self.tmp / "drafts"
        self.out = self.tmp / "out"
        self.drafts.mkdir()
        self.lib = h.Library(self.repo)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *extra):
        return run(sys.executable, str(TOOL), "--repo", str(self.repo), "--from-dir", str(self.drafts),
                   "--out-dir", str(self.out), "--allow-no-roster", *extra)

    def verdict_for(self, role_slug, box=None):
        rep = json.loads((self.out / "report.json").read_text())
        rows = [d for d in rep["drafts"] if d["role_slug"] == role_slug and (box is None or d["box"] == box)]
        return rows


class RubricAndRejection(Base):
    def evaluate(self, text, tamper=False, dept="account-management", slug="quality-auditor", roster=None):
        put_draft(self.drafts, "box-a", dept, slug, text, tamper=tamper)
        _, items = h.collect_dir(self.drafts)
        return h.evaluate(items[0], self.lib, roster)

    def test_good_draft_passes(self):
        r = self.evaluate(good_text())
        self.assertEqual(r["verdict"], "PASS", r["reasons"])
        self.assertGreaterEqual(r["score"], h.PASS_SCORE)

    def test_thresholds_match_the_rubric_file(self):
        rubric = (LIB / "_sop-writer.md").read_text(encoding="utf-8")
        self.assertIn("< 7000 bytes", rubric)
        self.assertIn("< 8.5", rubric)
        self.assertIn("all 18 sections", rubric)
        self.assertEqual((h.MIN_SUBSTANCE_BYTES, h.PASS_SCORE, h.SECTION_COUNT), (7000, 8.5, 18))

    def test_boilerplate_markers_are_a_subset_of_the_author_scripts(self):
        author = (SKILL / "scripts" / "author-missing-sops.py").read_text(encoding="utf-8")
        for m in h.BOILERPLATE_MARKERS:
            self.assertIn(m, author, "marker drifted from author-missing-sops.py: %r" % m)

    def test_personal_data_is_rejected_by_class_without_echoing_it(self):
        secret_email = "jane.private@acmecorp-realclient.io"
        cases = {
            "email": "\nContact %s for details.\n" % secret_email,
            "phone": "\nCall (214) 867-5309 today.\n",
            "long-id": "\nChat id 8123456789 owns this.\n",
            "ip-address": "\nSSH to 203.0.114.77 first.\n",
            "home-path": "\nOpen /Users/someperson/notes.md now.\n",
            "private-url": "\nVisit https://acme.zerohumanworkforce.com/panel now.\n",
        }
        for cls, injected in cases.items():
            with self.subTest(cls=cls):
                self.setUp_clean()
                r = self.evaluate(good_text() + injected)
                self.assertEqual(r["verdict"], "REJECT")
                self.assertIn("personal-data:" + cls, r["reasons"])
                self.assertNotIn("realclient", json.dumps({k: v for k, v in r.items() if k != "_text"}))

    def setUp_clean(self):
        shutil.rmtree(self.drafts, ignore_errors=True)
        self.drafts.mkdir()

    def test_known_placeholders_are_not_personal_data(self):
        t = good_text() + "\nWrite to security@company.com or user@example.com; 169.254.169.254 is the metadata IP; card 555-555-5555.\n"
        self.assertEqual(h.scan_personal_data(t, None), [])

    def test_client_roster_name_is_rejected(self):
        roster = [re.compile(r"Zebulon Quarterstaff", re.I)]
        r = self.evaluate(good_text() + "\nAsk zebulon quarterstaff first.\n", roster=roster)
        self.assertIn("personal-data:roster-name", r["reasons"])

    def test_roster_loader_reads_file_and_reports_missing(self):
        f = self.tmp / "roster.txt"
        f.write_text("# comment\n\nZebulon Quarterstaff\n\\bQuill\\b\n")
        pats, why = h.load_roster(str(f))
        self.assertEqual(len(pats), 2)
        self.assertIsNone(h.load_roster(str(self.tmp / "nope.txt"))[0])

    def test_boilerplate_and_thin_drafts_rejected(self):
        r = self.evaluate(good_text() + "\n1. [Step 1 - to be personalized]\n")
        self.assertIn("boilerplate", r["reasons"])
        self.setUp_clean()
        r = self.evaluate("# Role\n\n" + "1. Do a `thing`.\n" * 30)
        self.assertTrue(any(x.startswith("below-substance-floor") for x in r["reasons"]), r["reasons"])
        self.assertTrue(any(x.startswith("below-rubric") for x in r["reasons"]))

    def test_padding_cannot_buy_a_pass(self):
        r = self.evaluate("# Role\n\n" + ("A long sentence that says nothing useful at all. " * 400))
        self.assertEqual(r["verdict"], "REJECT")
        self.assertTrue(any(x.startswith("below-rubric") for x in r["reasons"]))

    def test_unfillable_token_is_rejected(self):
        r = self.evaluate(good_text() + "\nUse {{TOTALLY_UNKNOWN_TOKEN_XYZ}} here.\n")
        self.assertTrue(any(x.startswith("unknown-token") for x in r["reasons"]), r["reasons"])

    def test_tampered_record_fails_integrity(self):
        r = self.evaluate(good_text(), tamper=True)
        self.assertIn("integrity-mismatch", r["reasons"])

    def test_missing_record_and_unknown_department_rejected(self):
        put_draft(self.drafts, "box-a", "no-such-dept", "quality-auditor", good_text())
        for f in (self.drafts / "box-a" / "no-such-dept").glob("*.sop-needed.json"):
            f.unlink()
        _, items = h.collect_dir(self.drafts)
        r = h.evaluate(items[0], self.lib, None)
        self.assertIn("missing-or-bad-record", r["reasons"])
        self.assertIn("unknown-department", r["reasons"])


class DedupeAndConflict(Base):
    def test_higher_scoring_duplicate_wins_and_lower_is_skipped(self):
        strong = good_text("Quality Auditor")
        # Drop one numbered heading: still passes the bar, scores strictly lower. Pick the heading so the
        # WEAK draft has the SMALLER hash, so a hash-order tie-break would choose wrong and fail this test.
        strong_sha = hashlib.sha256(strong.encode("utf-8")).hexdigest()
        weak = None
        for n in range(2, 18):
            cand = re.sub(r"(?m)^## %d\. " % n, "## ", strong, count=1)
            if cand != strong and hashlib.sha256(cand.encode("utf-8")).hexdigest() < strong_sha:
                weak = cand
                break
        self.assertIsNotNone(weak, "fixture could not build a lower-hash weaker draft")
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", weak)
        put_draft(self.drafts, "box-b", "account-management", "quality-auditor", strong)
        r = self.cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.verdict_for("quality-auditor")
        self.assertEqual(len(rows), 2)
        win = [x for x in rows if x["verdict"] == "PASS"]
        self.assertEqual(len(win), 1)
        self.assertEqual(win[0]["box"], "box-b")
        lose = [x for x in rows if x["verdict"] == "SKIP"][0]
        self.assertEqual(lose["reasons"], ["lower-scoring-duplicate"])
        self.assertGreater(win[0]["score"], lose["score"], "winner must be strictly higher, not a hash tie-break")
        self.assertGreaterEqual(lose["score"], h.PASS_SCORE, "loser lost on score, not on a rejection")

    def test_identical_content_on_two_boxes_collapses_to_one(self):
        t = good_text()
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", t)
        put_draft(self.drafts, "box-b", "account-management", "quality-auditor", t)
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(sorted(x["verdict"] for x in self.verdict_for("quality-auditor")), ["PASS", "SKIP"])

    def test_existing_library_role_is_never_replaced(self):
        put_draft(self.drafts, "box-a", "account-management", "retention-specialist", good_text("Retention Specialist"))
        before = (self.repo / "23-ai-workforce-blueprint/templates/role-library/account-management/retention-specialist.md").read_bytes()
        r = self.cli("--stage", "--base", "main", "--branch", "sop-harvest-test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.verdict_for("retention-specialist")[0]["reasons"], ["already-in-library"])
        self.assertEqual(run("git", "rev-parse", "--verify", "--quiet", "refs/heads/sop-harvest-test", cwd=self.repo).returncode, 1,
                         "no branch should be made when nothing survives")
        self.assertEqual(before, (self.repo / "23-ai-workforce-blueprint/templates/role-library/account-management/retention-specialist.md").read_bytes())

    def test_stage_refuses_to_clobber_a_file_that_appears_after_the_check(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text())
        _, items = h.collect_dir(self.drafts)
        res = h.evaluate(items[0], self.lib, None)
        winners = h.pick_winners([res], self.lib)
        folder = self.repo / "23-ai-workforce-blueprint/templates/role-library/account-management/quality-auditor"
        folder.mkdir(parents=True)
        (folder / "how-to.md").write_text("EXISTING\n")
        run("git", "add", "-A", cwd=self.repo)
        run("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x", cwd=self.repo)
        code, info = h.stage(self.repo, self.lib, winners, "b1", "main", h.datetime.now(h.timezone.utc))
        self.assertEqual((folder / "how-to.md").read_text(), "EXISTING\n")
        self.assertEqual(winners[0]["verdict"], "SKIP")


class Staging(Base):
    def test_staged_branch_is_one_commit_passes_library_checks_and_touches_only_new_files(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text(), title="Quality Auditor")
        r = self.cli("--stage", "--base", "main", "--branch", "sop-harvest-test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(run("git", "branch", "--show-current", cwd=self.repo).stdout.strip(), "sop-harvest-test")
        changed = sorted(run("git", "diff", "--name-only", "main..HEAD", cwd=self.repo).stdout.split())
        self.assertEqual(changed, [
            "23-ai-workforce-blueprint/templates/role-library/_index.json",
            "23-ai-workforce-blueprint/templates/role-library/account-management/quality-auditor/how-to.md"])
        self.assertEqual(run("git", "rev-list", "--count", "main..HEAD", cwd=self.repo).stdout.strip(), "1")
        self.assertEqual(run("git", "status", "--porcelain", cwd=self.repo).stdout.strip(), "")
        reg = run(sys.executable, "23-ai-workforce-blueprint/scripts/register-library-additions.py", "--check", cwd=self.repo)
        hsh = run(sys.executable, "23-ai-workforce-blueprint/scripts/hash-content-manifest.py", "--check", cwd=self.repo)
        self.assertEqual((reg.returncode, hsh.returncode), (0, 0), reg.stdout + hsh.stdout)
        idx = json.loads((self.repo / "23-ai-workforce-blueprint/templates/role-library/_index.json").read_text())
        row = [x for x in idx["roles"] if x["slug"] == "quality-auditor"][0]
        self.assertTrue(row["content_sha"].startswith("sha256:") and len(row["content_sha"]) == 71)
        self.assertEqual(idx["total_roles"], 2)
        self.assertIn("quality-auditor", idx["departments"]["account-management"]["roles"])

    def test_never_touches_version_or_changelog(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text())
        self.assertEqual(self.cli("--stage", "--base", "main", "--branch", "sop-harvest-test").returncode, 0)
        names = run("git", "diff", "--name-only", "main..HEAD", cwd=self.repo).stdout
        self.assertNotRegex(names, r"(?i)version|changelog")

    def test_stage_refuses_dirty_repo_and_missing_base_and_existing_branch(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text())
        (self.repo / "stray.txt").write_text("x")
        self.assertEqual(self.cli("--stage", "--base", "main").returncode, 3)
        (self.repo / "stray.txt").unlink()
        self.assertEqual(self.cli("--stage", "--base", "no-such-ref").returncode, 3)
        run("git", "branch", "taken", cwd=self.repo)
        self.assertEqual(self.cli("--stage", "--base", "main", "--branch", "taken").returncode, 3)

    def test_stage_without_roster_is_refused_unless_explicit(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text())
        r = run(sys.executable, str(TOOL), "--repo", str(self.repo), "--from-dir", str(self.drafts), "--out-dir", str(self.out),
                "--roster", str(self.tmp / "missing-roster.txt"), "--stage", "--base", "main", "--branch", "b2")
        self.assertEqual(r.returncode, 3)
        self.assertIn("roster", r.stderr)

    def test_report_only_mode_changes_nothing_in_the_repo(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor", good_text())
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(run("git", "status", "--porcelain", cwd=self.repo).stdout.strip(), "")
        self.assertEqual(run("git", "branch", "--list", cwd=self.repo).stdout.split(), ["*", "main"])
        self.assertTrue((self.out / "report.md").is_file())

    def test_report_never_contains_matched_personal_text(self):
        put_draft(self.drafts, "box-a", "account-management", "quality-auditor",
                  good_text() + "\nReach jane.private@acmecorp-realclient.io\n")
        self.assertEqual(self.cli().returncode, 0)
        blob = (self.out / "report.md").read_text() + (self.out / "report.json").read_text()
        self.assertNotIn("realclient", blob)
        self.assertIn("personal-data:email", blob)


class CollectionHonesty(Base):
    def test_zero_boxes_answered_is_a_tooling_failure_not_a_clean_zero(self):
        (self.drafts / "box-a").mkdir()
        r = self.cli()
        self.assertEqual(r.returncode, 0, "an empty box dir that WAS read answers 'no drafts'")
        empty = self.tmp / "emptyroot"
        empty.mkdir()
        r = run(sys.executable, str(TOOL), "--repo", str(self.repo), "--from-dir", str(empty), "--out-dir", str(self.out), "--allow-no-roster")
        self.assertEqual(r.returncode, 2)
        self.assertIn("zero boxes answered", r.stderr)

    def test_unreadable_boxes_are_undetermined_and_listed(self):
        st, items = h.ssh_collect({"slug": "box-x", "platform": "mac", "paths": [
            {"path": "P3", "route": "root@<ip:redacted>", "verdict": "REACHABLE"}]}, "/usr/bin/ssh", 5)
        self.assertEqual(items, [])
        self.assertEqual(st["status"], "NOT_COLLECTED")
        self.assertIn("UNDETERMINED", st["detail"])

    def test_route_picker_never_uses_an_unreachable_or_redacted_path(self):
        box = {"paths": [{"route": "alias:down-host", "verdict": "ROUTE_FOUND_BUT_REFUSED"},
                         {"route": "docker:c1@root@<ip:redacted>", "verdict": "REACHABLE"},
                         {"route": "alias:good-host", "verdict": "REACHABLE"}]}
        self.assertEqual(h.pick_route(box), {"host": "good-host", "container": None})
        self.assertIsNone(h.pick_route({"paths": [{"route": "alias:x", "verdict": "ROUTE_FOUND_BUT_REFUSED"}]}))

    def test_ssh_marker_logic_with_a_stub_ssh(self):
        stub = self.tmp / "ssh-stub.sh"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            body = good_text().encode()
            sha = hashlib.sha256(body).hexdigest()
            for name, data in (("account-management/qa.%s.draft.md" % sha[:8], body),
                               ("account-management/qa.%s.sop-needed.json" % sha[:8], b"{}"),
                               ("../escape.txt", b"nope"), ("account-management/readme.txt", b"ignored")):
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tf.addfile(ti, io.BytesIO(data))
        import base64
        payload = base64.b64encode(buf.getvalue()).decode()
        modes = {"ok": "echo __SOPH_DIR__; echo %s; echo __SOPH_END__" % payload,
                 "nodir": "echo __SOPH_NODIR__", "dead": "echo 'ssh: connect refused' >&2; exit 255"}
        box = {"slug": "box-s", "platform": "mac", "paths": [{"route": "alias:stub-host", "verdict": "REACHABLE"}]}
        out = {}
        for mode, body in modes.items():
            stub.write_text("#!/bin/sh\n%s\n" % body)
            stub.chmod(0o755)
            out[mode] = h.ssh_collect(box, str(stub), 10)
        self.assertEqual(out["ok"][0]["status"], "COLLECTED")
        self.assertEqual(len(out["ok"][1]), 1)
        self.assertEqual(out["ok"][0]["ignored_files"], 2, "path-escape and non-matching names must be ignored")
        self.assertEqual(out["nodir"][0]["status"], "NO_HARVEST_DIR")
        self.assertEqual(out["dead"][0]["status"], "UNDETERMINED")
        self.assertEqual(out["dead"][1], [])

    def test_ssh_is_read_only_and_headless(self):
        src = TOOL.read_text(encoding="utf-8")
        self.assertIn("BatchMode=yes", src)
        self.assertIn("UserKnownHostsFile=/dev/null", src)
        # no invocation of anything that writes to a box, publishes, or opens a pull request
        for banned in ("cloudflared access login", '"scp"', '"rsync"', 'git(repo, "push"', '"gh"', "rm -rf"):
            self.assertNotIn(banned, src, banned)
        self.assertEqual(len(re.findall(r"subprocess\.run\(", src)), 4, "unexpected new subprocess call site")
        self.assertNotIn("pm2", src)

    def test_tool_never_prints_personal_or_operator_literals(self):
        src = TOOL.read_text(encoding="utf-8")
        for banned in ("5252140759", "/Users/blackceomacmini", "Trevor", "blackceo"):
            self.assertNotIn(banned, src, banned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
