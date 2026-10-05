#!/usr/bin/env python3
"""Fleet roll on a 9Router box: 999 runs ONLY `--skills-only`, behind a checksum guard.

Hermetic: every home, repo, fake ssh and fake 999 installer lives in a temp dir;
the real ~/.9router and ~/.claude are never read. Run:

    python3 tests/unit/nine-router-skills-only-roll.test.py

THE REGRESSION that must stay red-capable: test_9router_path_takes_only_skills_only
fails the moment the 9Router path hands the 999 installer anything but exactly
`--skills-only` (or reaches the link/full-installer path at all).
"""
import contextlib
import http.server
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
os.environ["FLEET_GOOGLE_SA"] = "/nonexistent/service-account.json"
for _k in ("FLEET_STANDING_GATE_URL", "FLEET_STANDING_GATE_SECRET", "FLEET_OPERATOR_ALERT_URL"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(REPO / "shared-utils"))
import fleet_refresh_runner as fr  # noqa: E402
import nine_router_guard as nrg  # noqa: E402

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True, env=GIT_ENV).stdout.strip()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def health_server(port):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/api/health" else 404)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield
    finally:
        srv.shutdown()
        srv.server_close()


# Fake 999 installer. Records every invocation's argv; `main` is what a FULL
# install would run. FAKE_MUTATE=<path under HOME> makes --skills-only touch a
# file, to prove the checksum guard notices.
FAKE_INSTALLER = r'''#!/usr/bin/env bash
set -euo pipefail
# supports: --skills-only
MARK="__MARK__"
link_skills_into_root() { echo "LINK-PATH-RAN $1" >> "$MARK"; }
bundled_skills() { sed -e "/^$/d" "$REPO_ROOT/CONTROL/bundled-skills.txt"; }
main() {
  echo "ARGV:$*" >> "$MARK"
  if [ "${1:-}" = "--skills-only" ]; then
    [ -z "${FAKE_MUTATE:-}" ] || echo changed >> "$HOME/$FAKE_MUTATE"
    exit 0
  fi
  echo "FULL-ORCHESTRATOR-RAN" >> "$MARK"
}
main "$@"
'''


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.mark = self.tmp / "marker.txt"
        self.port = free_port()           # nothing listens here unless a test starts a server
        p = mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": str(self.tmp), "NINEROUTER_PORT": str(self.port),
                                         "HOME": str(self.home)})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.addCleanup(self._td.cleanup)

    def make_999(self, where="Downloads/999-setup", installer=None):
        origin = self.tmp / "gh" / "trevorotts1" / "999-setup.git"
        origin.mkdir(parents=True)
        git(origin, "init", "-q", "--bare", "-b", "main")
        seed = self.tmp / "seed"
        seed.mkdir()
        git(seed, "init", "-q", "-b", "main")
        files = {".claude/skills/nine-router-setup/scripts/setup-macos.sh":
                 (installer or FAKE_INSTALLER).replace("__MARK__", str(self.mark)),
                 "AGENT_INSTALL.md": "x", "CONTROL/bundled-skills.txt": "nine-router-setup\n"}
        for rel, txt in files.items():
            (seed / rel).parent.mkdir(parents=True, exist_ok=True)
            (seed / rel).write_text(txt)
        git(seed, "add", "-A")
        subprocess.run(["git", "-C", str(seed), "commit", "-q", "-m", "one"], check=True, env=GIT_ENV)
        git(seed, "remote", "add", "origin", str(origin))
        git(seed, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", str(origin), str(self.home / where)], check=True, env=GIT_ENV)
        return self.home / where

    def make_9router_files(self, with_launcher=True):
        nr = self.home / ".9router"
        (nr / "db").mkdir(parents=True)
        (nr / "jwt-secret").write_text("not-a-real-secret")
        c = sqlite3.connect(nr / "db/data.sqlite")
        c.executescript("""
            create table settings(id integer primary key, data text);
            insert into settings values (1, '{"authMode":"x"}');
            create table providerConnections(id integer primary key, provider text, authType text, name text,
                email text, priority int, isActive int, data text, createdAt text, updatedAt text);
            insert into providerConnections values (1,'p','k','n','e',1,1,'{"apiKey":"k1","lastErrorAt":"t0","backoffLevel":0}','a','b');
            create table usageHistory(id integer primary key, v text);
            create table _meta(key text primary key, value text);
            insert into _meta values ('totalRequestsLifetime','1'), ('schemaVersion','5');
        """)
        c.commit()
        c.close()
        if with_launcher:
            b = self.home / ".local/bin"
            b.mkdir(parents=True)
            (b / "claude-nine").write_text("#!/bin/sh\n")

    def argv_lines(self):
        return self.mark.read_text().splitlines() if self.mark.exists() else []


class Detection(Base):
    def test_none(self):
        d = nrg.detect(self.home, timeout=1)
        self.assertEqual((d["class"], d["skills_only"]), ("none", False))

    def test_all_three_signals(self):
        self.make_9router_files()
        with health_server(self.port):
            d = nrg.detect(self.home, timeout=2)
        self.assertEqual(d["signals"], {"dir": True, "launcher": True, "answering": True})
        self.assertEqual((d["class"], d["skills_only"]), ("9router", True))

    def test_router_down_is_still_a_9router_box(self):
        # dir + launcher present, router not answering: must NOT fall onto the link path.
        self.make_9router_files()
        d = nrg.detect(self.home, timeout=1)
        self.assertEqual(d["signals"]["answering"], False)
        self.assertEqual((d["class"], d["skills_only"]), ("partial", True))

    def test_each_single_signal_counts(self):
        (self.home / ".9router").mkdir()
        self.assertTrue(nrg.detect(self.home, timeout=1)["skills_only"])


class RollStep(Base):
    def run_step(self, dry_run=False):
        res = fr.BoxResult("t", dry_run=dry_run)
        fr.step_update_999(res, dry_run=dry_run)
        return res

    def test_9router_path_takes_only_skills_only(self):
        """THE REGRESSION: the 9Router path may run the installer with exactly --skills-only."""
        self.make_9router_files()
        self.make_999()
        res = self.run_step()
        self.assertEqual(res.steps["update-999"], "ok", res.steps)
        lines = self.argv_lines()
        self.assertEqual([l for l in lines if l.startswith("ARGV:")], ["ARGV:--skills-only"], lines)
        self.assertNotIn("FULL-ORCHESTRATOR-RAN", lines)
        self.assertFalse([l for l in lines if l.startswith("LINK-PATH-RAN")], "link path reached on a 9Router box")
        argv = res.update_999["skills_only"]["argv"]          # [shell, installer, *args]
        self.assertEqual((len(argv), argv[2:]), (3, ["--skills-only"]), argv)
        self.assertEqual(nrg.SKILLS_ONLY_ARGS, ["--skills-only"])

    def test_non_9router_box_keeps_existing_link_path(self):
        # no ~/.9router, no launcher, nothing answering -> unchanged behavior: link path, no --skills-only.
        self.make_999(installer=FAKE_INSTALLER.replace('main "$@"', 'main "$@"'))
        res = self.run_step()
        self.assertEqual(res.steps["update-999"], "ok", res.steps)
        self.assertEqual(res.update_999["9router"]["class"], "none")
        lines = self.argv_lines()
        self.assertTrue([l for l in lines if l.startswith("LINK-PATH-RAN")], lines)
        self.assertFalse([l for l in lines if l.startswith("ARGV:")], "installer main() must not run on the link path")

    def test_dry_run_changes_nothing_on_a_9router_box(self):
        self.make_9router_files()
        self.make_999()
        res = self.run_step(dry_run=True)
        self.assertIn("would run --skills-only only", res.steps["update-999"])
        self.assertEqual(self.argv_lines(), [])

    def test_installer_without_skills_only_flag_is_never_run(self):
        self.make_9router_files()
        old = FAKE_INSTALLER.replace("# supports: --skills-only\n", "").replace('"--skills-only"', '"--nope"').replace("--skills-only", "--nope")
        self.make_999(installer=old)
        res = self.run_step()
        self.assertTrue(res.steps["update-999"].startswith("skip:9Router box"), res.steps)
        self.assertEqual(self.argv_lines(), [])   # not even --skills-only, and never the full installer


class Guard(Base):
    def test_unchanged_files_match(self):
        self.make_9router_files()
        a = nrg.snapshot(self.home)
        m, bad = nrg.compare(a, nrg.snapshot(self.home))
        self.assertEqual((bad, m > 0), ([], True))

    def test_router_runtime_noise_is_not_a_mismatch(self):
        self.make_9router_files()
        a = nrg.snapshot(self.home)
        c = sqlite3.connect(self.home / ".9router/db/data.sqlite")
        c.execute("""update providerConnections set data='{"apiKey":"k1","lastErrorAt":"t9","backoffLevel":3}'""")
        c.execute("insert into usageHistory values (1,'x')")
        c.execute("update _meta set value='99' where key='totalRequestsLifetime'")
        c.commit()
        c.close()
        self.assertEqual(nrg.compare(a, nrg.snapshot(self.home))[1], [])

    def test_config_change_is_a_mismatch_and_values_are_not_printed(self):
        self.make_9router_files()
        a = nrg.snapshot(self.home)
        c = sqlite3.connect(self.home / ".9router/db/data.sqlite")
        c.execute("""update settings set data='{"authMode":"y"}'""")
        c.commit()
        c.close()
        (self.home / ".local/bin/claude-nine").write_text("#!/bin/sh\n# edited\n")
        m, bad = nrg.compare(a, nrg.snapshot(self.home))
        self.assertEqual(sorted(bad), ["db:settings", "launcher/claude-nine"])

    def test_skills_only_that_touches_the_router_is_a_mismatch(self):
        self.make_9router_files()
        repo = self.make_999()
        with mock.patch.dict(os.environ, {"FAKE_MUTATE": ".9router/jwt-secret"}):
            g = nrg.skills_only_guarded(repo, self.home)
        self.assertEqual((g["status"], g["mismatched"]), ("mismatch", ["9router/jwt-secret"]))

    def test_cli_prints_counts_only(self):
        self.make_9router_files()
        repo = self.make_999()
        env = {**os.environ, "FAKE_MUTATE": ".local/bin/claude-nine"}
        r = subprocess.run([sys.executable, str(REPO / "shared-utils/nine_router_guard.py"), "skills-only", "--repo", str(repo)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"checksums: \d+ MATCH, 1 MISMATCH")
        self.assertIn("MISMATCH: launcher/claude-nine", r.stdout)
        self.assertNotRegex(r.stdout, r"[0-9a-f]{32}")        # no digest ever printed


class RollRollsBackOnMismatch(Base):
    def test_mismatch_marks_box_failed_and_rolls_back(self):
        self.make_9router_files()
        self.make_999()
        calls = []
        patches = [
            mock.patch.object(fr, "step_detect"), mock.patch.object(fr, "step_pin_resolve", return_value="v1"),
            mock.patch.object(fr, "probe_health", return_value={}), mock.patch.object(fr, "probe_integrity", return_value={}),
            mock.patch.object(fr, "wave5_deploy_preflight"), mock.patch.object(fr, "take_snapshot", return_value=True),
            mock.patch.object(fr, "step_pull_onboarding", return_value="v1"),
            mock.patch.object(fr, "step_pull_cc", side_effect=lambda *a, **k: calls.append("pull-cc")),
            mock.patch.object(fr, "rollback_box", side_effect=lambda p, r, res, reasons: calls.append(("rollback", reasons)) or True),
            mock.patch.object(fr, "heal_and_gate", side_effect=lambda *a, **k: calls.append("gate") or "done"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        res = fr.BoxResult("t", dry_run=False)
        with mock.patch.dict(os.environ, {"FAKE_MUTATE": ".9router/jwt-secret"}):
            out = fr._run_box_body(res, {"commandCenter": {}}, "v1", {"root": self.tmp, "cc_dir": None},
                                   REPO / "shared-utils", REPO, False, False, True, False)
        self.assertEqual((out.outcome, out.result), ("FAILED", "failed"))
        self.assertIn("box rolled back", out.outcome_detail)
        self.assertEqual([c[0] for c in calls if isinstance(c, tuple)], ["rollback"])
        self.assertIn("9Router guard", calls[0][1][0])
        self.assertNotIn("pull-cc", calls)       # nothing runs after the guard trips
        self.assertTrue(out.steps["update-999"].startswith("failed"))


class FrontDoor(Base):
    """update-skills.sh -> lib-frontdoor.sh frontdoor_update_999 (the other 999 call site)."""

    def run_fd(self, repo):
        script = f'''set -u; cd "{REPO}"; source shared-utils/lib-frontdoor.sh
frontdoor_update_999; echo "RC=$?"'''
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home), "PATH": os.environ["PATH"]})

    def test_9router_box_gets_only_skills_only(self):
        self.make_9router_files()
        repo = self.make_999("999-setup")
        r = self.run_fd(repo)
        self.assertIn("RC=0", r.stdout, r.stdout + r.stderr)
        lines = self.argv_lines()
        self.assertEqual([l for l in lines if l.startswith("ARGV:")], ["ARGV:--skills-only"], lines)
        self.assertFalse([l for l in lines if l.startswith("LINK-PATH-RAN")], lines)
        self.assertIn("MATCH", r.stdout)

    def test_9router_box_with_modified_router_file_fails(self):
        self.make_9router_files()
        repo = self.make_999("999-setup")
        r = subprocess.run(["bash", "-c", f'cd "{REPO}"; source shared-utils/lib-frontdoor.sh; frontdoor_update_999; echo "RC=$?"'],
                           capture_output=True, text=True,
                           env={**os.environ, "HOME": str(self.home), "FAKE_MUTATE": ".9router/jwt-secret"})
        self.assertIn("RC=3", r.stdout, r.stdout + r.stderr)
        self.assertIn("MISMATCH", r.stdout + r.stderr)

    def test_mismatch_labels_reach_the_roll_through_the_marker_file(self):
        self.make_9router_files()
        self.make_999("999-setup")
        marker = self.tmp / "guard-mark.txt"
        marker.write_text("")
        r = subprocess.run(["bash", "-c", f'cd "{REPO}"; source shared-utils/lib-frontdoor.sh; frontdoor_update_999; echo "RC=$?"'],
                           capture_output=True, text=True,
                           env={**os.environ, "HOME": str(self.home), "FAKE_MUTATE": ".9router/jwt-secret",
                                "NINE_ROUTER_GUARD_MARK": str(marker)})
        self.assertIn("RC=3", r.stdout, r.stdout + r.stderr)
        self.assertEqual(marker.read_text().strip(), "9router/jwt-secret")      # label only, never a digest

    def test_non_9router_box_keeps_link_path(self):
        repo = self.make_999("999-setup")
        r = self.run_fd(repo)
        self.assertIn("RC=0", r.stdout, r.stdout + r.stderr)
        self.assertFalse([l for l in self.argv_lines() if l.startswith("ARGV:")])


class UnreachableBoxIsSkippedAndListed(Base):
    def test_ssh_255_is_skipped_not_failed_and_named(self):
        wr = self.tmp / "operator-clone"
        (wr / "scripts").mkdir(parents=True)
        (wr / "shared-utils").mkdir()
        for rel in ("scripts/fleet-refresh.sh", "scripts/fleet-roll-copy.sh", "scripts/make-fleet-boxes-file.py",
                    "shared-utils/fleet_notify.py", "shared-utils/operator_google.py"):
            (wr / rel).write_text((REPO / rel).read_text())
        (wr / "shared-utils/fleet_refresh_runner.py").write_text("")
        (wr / "cc-compat.json").write_text((REPO / "cc-compat.json").read_text())
        fake = self.tmp / "bin"
        fake.mkdir()
        (fake / "ssh").write_text("#!/bin/sh\nexit 255\n")
        (fake / "ssh").chmod(0o755)
        boxes = self.tmp / "b.json"
        boxes.write_text(json.dumps([{"client": "Client One", "name": "box-1", "ssh_target": "h",
                                      "platform": "mac", "wave": "first"}]))
        r = subprocess.run(["bash", str(wr / "scripts/fleet-refresh.sh"), "--wave", "first", "--boxes-file", str(boxes), "--apply"],
                           capture_output=True, text=True, timeout=120,
                           env={**GIT_ENV, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": str(self.home)})
        out = r.stdout + r.stderr
        row = json.loads((wr / ".fleet-refresh-summary.json").read_text())[0]
        self.assertEqual((row["outcome"], row.get("unreachable")), ("SKIPPED", True), out)
        self.assertIn("SKIPPED=1", out)
        self.assertIn("UNREACHABLE (skipped, not updated): 1 - Client One (Mac)", out)


class OneRunnerPerBox(unittest.TestCase):
    def test_roll_starts_one_job_per_box_and_locks_the_box(self):
        sh = (REPO / "scripts/fleet-refresh.sh").read_text()
        self.assertEqual(sh.count("{ run_box_ssh \"$box\" || true; finish_box \"$box\"; } &"), 1)   # one backgrounded job / box
        self.assertIn('for box in "${FINAL_BOXES[@]}"; do\n  echo "[fleet-refresh] Queuing', sh)
        self.assertIn("_BoxLock(paths[\"root\"])", (REPO / "shared-utils/fleet_refresh_runner.py").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=1)
