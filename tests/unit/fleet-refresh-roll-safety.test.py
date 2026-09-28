#!/usr/bin/env python3
"""Roll-safety contract for shared-utils/fleet_refresh_runner.py and
scripts/make-fleet-boxes-file.py.

Hermetic: every repo, box tree and script lives under a temp dir; the health
probes that would touch live services are replaced with fakes. Run:

    python3 tests/unit/fleet-refresh-roll-safety.test.py
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
import fleet_refresh_runner as fr  # noqa: E402

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=GIT_ENV).stdout.strip()


def commit(repo, files, msg):
    for rel, content in files.items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        if rel.endswith(".sh"):
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def new_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    return path


def hc(status):
    return {"status": status, "detail": f"fake {status}"}


def health(**over):
    base = {n: hc("pass") for n in ("gateway-process", "gateway-health", "telegram-getme", "cc-health")}
    base.update({k.replace("_", "-"): hc(v) for k, v in over.items()})
    return base


class Box:
    """A box on disk: OpenClaw root with skills, an onboarding clone, a Command
    Center checkout whose atomic-deploy.sh records how it was called."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.root = tmp / "oc"
        self.skills = self.root / "skills"
        self.skills.mkdir(parents=True)
        (self.root / "openclaw.json").write_text("{}")
        self.onb = new_repo(tmp / "onboarding")
        self.onb_a = commit(self.onb, {
            "01-skill/SKILL.md": "v1",
            "cc-compat.json": (REPO / "cc-compat.json").read_text(),
        }, "A")
        self.cc = new_repo(tmp / "cc")
        self.deploy_log = tmp / "deploy.log"
        self.cc_a = commit(self.cc, {
            "package.json": '{"version": "1.0.0"}',
            "scripts/atomic-deploy.sh": f'#!/usr/bin/env bash\necho "$@" >> "{self.deploy_log}"\nexit 0\n',
        }, "A")
        # installed state at release A
        (self.skills / "01-skill").mkdir()
        (self.skills / "01-skill" / "SKILL.md").write_text("v1")
        (self.skills / ".onboarding-version").write_text("vA")
        (self.skills / "client-own-skill").mkdir()
        (self.skills / "client-own-skill" / "SKILL.md").write_text("mine")
        self.paths = {"root": self.root, "skills": self.skills, "cc_dir": self.cc,
                      "platform": "mac", "workspace": self.root / "workspace"}

    def apply_release_b(self):
        commit(self.onb, {"01-skill/SKILL.md": "v2"}, "B")
        commit(self.cc, {"package.json": '{"version": "2.0.0"}'}, "B")
        (self.skills / "01-skill" / "SKILL.md").write_text("v2")
        (self.skills / "01-skill" / "NEW.md").write_text("added by B")
        (self.skills / ".onboarding-version").write_text("vB")


class HealthGateAndRollback(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.box = Box(Path(self._td.name))
        self.res = fr.BoxResult("t", dry_run=False)
        self.res.steps.update({"pull-onboarding": "ok", "pull-cc": "ok", "build-cc": "ok",
                               "restart-cc": "ok", "sessions-reset-CEO": "ok"})
        patcher = mock.patch.object(fr, "_resolve_ceo_session_key", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._td.cleanup()

    def snapshot(self):
        self.assertTrue(fr.take_snapshot(self.box.paths, self.box.onb, self.res), self.res.snapshot)

    def test_snapshot_records_versions_and_only_managed_skills(self):
        self.snapshot()
        snap = self.res.snapshot
        self.assertEqual(snap["onboarding"]["sha"], self.box.onb_a)
        self.assertEqual(snap["onboarding"]["stamp"], "vA")
        self.assertEqual(snap["cc"]["sha"], self.box.cc_a)
        self.assertEqual(snap["cc"]["version"], "1.0.0")
        # the client's own skill is never in the onboarding snapshot
        self.assertEqual(snap["skills_entries"], [".onboarding-version", "01-skill"])
        self.assertTrue(Path(snap["skills_archive"]).is_file())

    def test_gate_pass_keeps_the_update(self):
        self.snapshot()
        self.box.apply_release_b()
        with mock.patch.object(fr, "probe_health", return_value=health()):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vB")
        self.assertEqual(self.res.steps["health-gate"], "ok")
        self.assertEqual(self.res.rollback, {})
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v2")
        self.assertFalse(self.box.deploy_log.exists())

    def test_gate_fail_rolls_everything_back(self):
        self.snapshot()
        self.box.apply_release_b()
        post = health(cc_health="fail")
        with mock.patch.object(fr, "probe_health", side_effect=[post, health()]):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vB")
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("cc-health", self.res.outcome_detail)
        # onboarding: clone, skill content, added files and stamp all back to A
        self.assertEqual(git(self.box.onb, "rev-parse", "HEAD"), self.box.onb_a)
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v1")
        self.assertFalse((self.box.skills / "01-skill" / "NEW.md").exists())
        self.assertEqual((self.box.skills / ".onboarding-version").read_text(), "vA")
        self.assertEqual((self.box.skills / "client-own-skill" / "SKILL.md").read_text(), "mine")
        # Command Center: checkout back to A and rebuilt/restarted AT A
        self.assertEqual(git(self.box.cc, "rev-parse", "HEAD"), self.box.cc_a)
        self.assertIn(f"--revision {self.box.cc_a}", self.box.deploy_log.read_text())
        self.assertTrue(self.res.rollback["health_restored"])

    def test_half_applied_step_rolls_back_even_when_health_is_fine(self):
        self.snapshot()
        self.box.apply_release_b()
        self.res.steps["pull-onboarding"] = "failed:update-skills.sh exited 1"
        with mock.patch.object(fr, "probe_health", return_value=health()):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vB")
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("pull-onboarding failed", self.res.outcome_detail)
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v1")

    def test_cc_step_failure_with_unchanged_checkout_is_not_rolled_back(self):
        self.snapshot()
        self.res.steps["pull-cc"] = "failed:CC dir not found: /elsewhere"
        with mock.patch.object(fr, "probe_health", return_value=health()):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vA")
        self.assertEqual(self.res.steps["health-gate"], "ok")
        self.assertEqual(self.res.rollback, {})

    def test_cc_step_failure_after_the_checkout_moved_rolls_back(self):
        self.snapshot()
        self.box.apply_release_b()
        self.res.steps["build-cc"] = "failed:atomic-deploy.sh exited 2 (pre-flight/build failed; previous build left serving)"
        with mock.patch.object(fr, "probe_health", return_value=health()):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vB")
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertEqual(git(self.box.cc, "rev-parse", "HEAD"), self.box.cc_a)

    def test_update_skills_exit_2_is_advisory_not_a_failure(self):
        stamp = self.box.skills / ".onboarding-version"
        pinned = json.loads((self.box.onb / "cc-compat.json").read_text())["onboardingVersion"]
        (self.box.onb / "update-skills.sh").write_text(f'#!/usr/bin/env bash\necho {pinned} > "{stamp}"\nexit 2\n')
        fr.step_pull_onboarding(self.box.paths, self.box.onb, pinned, self.res, dry_run=False)
        self.assertTrue(self.res.steps["pull-onboarding"].startswith("ok:advisory"), self.res.steps["pull-onboarding"])
        (self.box.onb / "update-skills.sh").write_text('#!/usr/bin/env bash\nexit 1\n')
        fr.step_pull_onboarding(self.box.paths, self.box.onb, pinned, self.res, dry_run=False)
        self.assertTrue(self.res.steps["pull-onboarding"].startswith("failed"))

    def test_rollback_that_does_not_restore_health_is_failed(self):
        self.snapshot()
        self.box.apply_release_b()
        bad = health(gateway_health="fail")
        with mock.patch.object(fr, "probe_health", side_effect=[bad, bad]):
            fr._health_gate(self.box.paths, self.box.onb, self.res, health(), "vB")
        self.assertEqual(self.res.outcome, "FAILED")
        self.assertIn("ROLLBACK INCOMPLETE", self.res.outcome_detail)
        self.assertIn("gateway-health", self.res.outcome_detail)

    def test_preexisting_failure_is_not_blamed_on_the_update(self):
        self.assertEqual(fr.health_regressions(health(telegram_getme="fail"), health(telegram_getme="fail")), [])
        self.assertEqual(fr.health_regressions(health(), health(telegram_getme="fail")), ["telegram-getme"])
        self.assertEqual(fr.health_regressions(health(cc_health="n/a"), health(cc_health="fail")), ["cc-health"])

    def test_session_reset_check(self):
        r = fr.BoxResult("t", dry_run=False)
        r.steps["sessions-reset-CEO"] = "ok"
        self.assertEqual(fr.hc_session_reset(r)["status"], "pass")
        r.steps["sessions-reset-CEO"] = "failed:gateway call returned error: {}"
        self.assertEqual(fr.hc_session_reset(r)["status"], "fail")
        r.steps["sessions-reset-CEO"] = "failed:CEO session key unresolved; cannot reset."
        self.assertEqual(fr.hc_session_reset(r)["status"], "n/a")
        r.steps["sessions-reset-CEO"] = "failed:openclaw not on PATH"
        self.assertEqual(fr.hc_session_reset(r)["status"], "n/a")

    def test_no_snapshot_space_means_no_update(self):
        with mock.patch.object(fr.shutil, "disk_usage", return_value=mock.Mock(free=1)):
            self.assertFalse(fr.take_snapshot(self.box.paths, self.box.onb, self.res))
        self.assertIn("free", self.res.snapshot["error"])


class BuildFailureKeepsOldBuild(unittest.TestCase):
    """atomic-deploy.sh builds in a private candidate dir: exit 2 means the live
    build was never touched. build-cc must report that, and the gate must then
    roll the checkout back so source and serving build agree again."""

    def test_exit_2_is_reported_as_old_build_serving(self):
        with tempfile.TemporaryDirectory() as td:
            cc = Path(td)
            (cc / "scripts").mkdir()
            (cc / "scripts" / "atomic-deploy.sh").write_text("#!/usr/bin/env bash\nexit 2\n")
            res = fr.BoxResult("t", dry_run=False)
            with mock.patch.object(fr, "wave5_deploy_preflight"), \
                 mock.patch("cc_runtime_preflight.check_node"), \
                 mock.patch("cc_runtime_preflight.check_checkout"):
                fr.step_build_cc({"cc_dir": cc}, res, dry_run=False)
            self.assertTrue(res.steps["build-cc"].startswith("failed:"))
            self.assertIn("previous build left serving", res.steps["build-cc"])
            self.assertIn("build-cc", fr._MUTATING_STEPS)


class Update999(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        env = mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": str(self.tmp)})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)   # restored by patch.dict

    def tearDown(self):
        self._td.cleanup()

    def make_999(self, where):
        origin = self.tmp / "gh" / "trevorotts1" / "999-setup.git"
        origin.mkdir(parents=True)
        git(origin, "init", "-q", "--bare", "-b", "main")
        seed = new_repo(self.tmp / "seed")
        marker = self.tmp / "linked.txt"
        installer = (
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            f'link_skills_into_root() {{ echo "linked $1 from $REPO_ROOT" >> "{marker}"; }}\n'
            'bundled_skills() { sed -e "/^$/d" "$REPO_ROOT/CONTROL/bundled-skills.txt"; }\n'
            f'main() {{ echo FULL-ORCHESTRATOR-RAN >> "{marker}"; }}\n'
            'main "$@"\n'
        )
        commit(seed, {".claude/skills/nine-router-setup/scripts/setup-macos.sh": installer,
                      "AGENT_INSTALL.md": "x", "CONTROL/bundled-skills.txt": "nine-router-setup\n"}, "one")
        git(seed, "remote", "add", "origin", str(origin))
        git(seed, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", str(origin), str(self.home / where)], check=True, env=GIT_ENV)
        new_sha = commit(seed, {"README.md": "newer"}, "two")
        git(seed, "push", "-q", "origin", "main")
        return self.home / where, marker, new_sha

    def test_absent_is_skipped_never_installed(self):
        res = fr.BoxResult("t", dry_run=False)
        fr.step_update_999(res, dry_run=False)
        self.assertEqual(res.steps["update-999"], "skip:999 not installed")
        self.assertEqual(list(self.home.iterdir()), [])

    def test_archive_extract_is_left_alone(self):
        d = self.home / "Documents/999-setup-main"
        for rel in ("AGENT_INSTALL.md", "CONTROL/bundled-skills.txt", fr._999_INSTALLER):
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text('main "$@"\n')
        res = fr.BoxResult("t", dry_run=False)
        fr.step_update_999(res, dry_run=False)
        self.assertIn("archive extract", res.steps["update-999"])
        self.assertTrue(res.steps["update-999"].startswith("skip:"))

    def test_installed_copy_under_dot_claude_is_not_a_checkout(self):
        skill = self.home / ".claude/skills/nine-router-setup/scripts"
        skill.mkdir(parents=True)
        (skill / "setup-macos.sh").write_text('main "$@"\n')
        self.assertIsNone(fr._find_999_checkout())

    def test_present_is_pulled_and_its_installer_skill_step_rerun(self):
        repo, marker, new_sha = self.make_999("Downloads/999-setup")
        res = fr.BoxResult("t", dry_run=False)
        fr.step_update_999(res, dry_run=False)
        self.assertEqual(res.steps["update-999"], "ok", res.errors)
        self.assertEqual(git(repo, "rev-parse", "HEAD"), new_sha)
        self.assertEqual(res.update_999["to_sha"], new_sha)
        ran = marker.read_text()
        self.assertIn(f"linked {self.home}/.claude from {repo}", ran)
        self.assertNotIn("FULL-ORCHESTRATOR-RAN", ran)   # no model call, no provider rewiring

    def test_hand_managed_skill_copy_is_not_relinked(self):
        repo, marker, new_sha = self.make_999("Downloads/999-setup")
        (self.home / ".claude/skills/nine-router-setup").mkdir(parents=True)   # a real dir, not a link
        res = fr.BoxResult("t", dry_run=False)
        fr.step_update_999(res, dry_run=False)
        self.assertEqual(git(repo, "rev-parse", "HEAD"), new_sha)              # still pulled
        self.assertIn("hand-managed", res.steps["update-999"])
        self.assertFalse(marker.exists())                                      # links untouched

    def test_found_through_the_installed_skill_link(self):
        repo, _marker, _sha = self.make_999("somewhere/unusual/999-setup")
        (self.home / ".claude/skills").mkdir(parents=True)
        (self.home / ".claude/skills/nine-router-setup").symlink_to(repo / ".claude/skills/nine-router-setup")
        self.assertEqual(fr._find_999_checkout().resolve(), repo.resolve())

    def test_dry_run_does_not_pull(self):
        repo, _marker, _sha = self.make_999("Documents/999-setup")
        before = git(repo, "rev-parse", "HEAD")
        res = fr.BoxResult("t", dry_run=True)
        fr.step_update_999(res, dry_run=True)
        self.assertTrue(res.steps["update-999"].startswith("skip:dry-run"))
        self.assertEqual(git(repo, "rev-parse", "HEAD"), before)


class TelegramProbe(unittest.TestCase):
    def test_getme_only_and_token_never_reported(self):
        tok = "123456:SECRET-TOKEN-VALUE"
        cfg = {"channels": {"telegram": {"accounts": {"a": {"botToken": "${TG_TOK}"},
                                                      "off": {"enabled": False, "botToken": "x:y"}}}}}
        calls = []

        def fake_get(url, timeout=10):
            calls.append(url)
            return 200, json.dumps({"ok": True, "result": {"username": "examplebot"}})

        with tempfile.TemporaryDirectory() as td, \
             mock.patch.dict(os.environ, {"TG_TOK": tok}), \
             mock.patch.object(fr, "_http_get", side_effect=fake_get):
            (Path(td) / "openclaw.json").write_text(json.dumps(cfg))
            r = fr.hc_telegram_getme({"root": Path(td)})
        self.assertEqual(r["status"], "pass")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].endswith("/getMe"))
        self.assertNotIn(tok, json.dumps(r))

    def test_rejected_token(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(fr, "_http_get", return_value=(401, "")):
            (Path(td) / "openclaw.json").write_text(json.dumps(
                {"channels": {"telegram": {"botToken": "1:abc"}}}))
            r = fr.hc_telegram_getme({"root": Path(td)}, wait=0)
        self.assertEqual(r["status"], "fail")
        self.assertNotIn("1:abc", r["detail"])


class BoxLock(unittest.TestCase):
    def test_second_run_on_a_box_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = fr._BoxLock(Path(td)), fr._BoxLock(Path(td))
            self.assertIsNone(a.acquire())
            self.assertIn("running", b.acquire())
            a.release()
            self.assertIsNone(b.acquire())
            b.release()


class BoxesFileGenerator(unittest.TestCase):
    GEN = REPO / "scripts" / "make-fleet-boxes-file.py"

    def run_gen(self, td, *extra):
        return subprocess.run([sys.executable, str(self.GEN), "--roster", f"{td}/roster.json",
                               "--registry", f"{td}/registry.json", "--pins", f"{td}/pins.json",
                               "--out", f"{td}/out/boxes.json", *extra], capture_output=True, text=True)

    def fixture(self, td):
        roster = {"boxes": {
            "mac-b": {"provider": "mac", "kind": "mac", "registry_id": "mac-b"},
            "mac-a": {"provider": "mac", "kind": "mac", "registry_id": "mac-a"},
            "vps-a": {"provider": "hostinger", "kind": "vps", "registry_id": "vps-a"},
            "ctb-a": {"provider": "contabo", "kind": "contabo", "registry_id": "ctb-a"},
            "op": {"provider": "operator", "kind": "local", "registry_id": "op"},
        }}
        registry = {"boxes": {
            "mac-a": {"ssh_alias": "alias-a", "tunnel_id": "tun-1", "svc_env_prefix": "CF_X"},
            "mac-b": {"ssh_alias": "alias-b"},
            "vps-a": {"ssh_target": "root@192.0.2.1", "container": "vps-a-openclaw-1"},
            "ctb-a": {"ssh_target": "contabo-host", "container": "oc-ctb-a"},
            "op": {},
        }}
        pins = {"boxes": {"ctb-a": {"openclaw_root": "/home/node/.openclaw"}}}
        for name, data in (("roster", roster), ("registry", registry), ("pins", pins)):
            Path(td, f"{name}.json").write_text(json.dumps(data))

    def test_generates_waves_transport_and_mode_600(self):
        with tempfile.TemporaryDirectory() as td:
            self.fixture(td)
            r = self.run_gen(td)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = Path(td, "out", "boxes.json")
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            boxes = {e["name"]: e for e in json.loads(out.read_text())}
            self.assertNotIn("op", boxes)   # operator box is rolled with --local
            self.assertEqual(boxes["mac-a"]["cf_tunnel_id"], "tun-1")
            self.assertEqual(boxes["mac-a"]["cf_access_env_prefix"], "CF_X")
            self.assertEqual(boxes["vps-a"]["container"], "vps-a-openclaw-1")
            self.assertEqual(boxes["vps-a"]["docker_exec_user"], "node")
            self.assertEqual(boxes["ctb-a"]["openclaw_root"], "/home/node/.openclaw")
            self.assertEqual(boxes["ctb-a"]["platform"], "contabo")
            first = sorted(n for n, e in boxes.items() if e["wave"] == "first")
            self.assertEqual(first, ["ctb-a", "mac-a", "vps-a"])   # one per platform
            self.assertEqual(boxes["mac-b"]["wave"], "rest")

    def test_first_wave_override_and_unroutable_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            self.fixture(td)
            reg = json.loads(Path(td, "registry.json").read_text())
            reg["boxes"]["mac-a"] = {}
            Path(td, "registry.json").write_text(json.dumps(reg))
            r = self.run_gen(td, "--first", "mac-b")
            self.assertEqual(r.returncode, 2)
            self.assertIn("UNROUTABLE", r.stderr)
            boxes = {e["name"]: e for e in json.loads(Path(td, "out", "boxes.json").read_text())}
            self.assertEqual([n for n, e in boxes.items() if e["wave"] == "first"], ["mac-b"])

    def test_refuses_to_write_into_a_git_tree(self):
        with tempfile.TemporaryDirectory() as td:
            self.fixture(td)
            r = subprocess.run([sys.executable, str(self.GEN), "--roster", f"{td}/roster.json",
                                "--registry", f"{td}/registry.json", "--out", str(REPO / "boxes.json")],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertFalse((REPO / "boxes.json").exists())


class WrapperWaves(unittest.TestCase):
    """fleet-refresh.sh end to end with fake curl/ssh: only the chosen wave is
    dispatched, and the run ends with the one-screen outcome table."""

    def run_wrapper(self, td, *args):
        fake = Path(td, "bin")
        fake.mkdir(exist_ok=True)
        (fake / "curl").write_text("#!/bin/sh\necho 200\n")                 # Wave-5 preflight: present
        (fake / "ssh").write_text(f'#!/bin/sh\necho "$@" >> "{td}/ssh.log"\necho "NONE /x/openclaw-onboarding"\n')
        for f in fake.iterdir():
            f.chmod(0o755)
        env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": td}
        return subprocess.run(["bash", str(REPO / "scripts" / "fleet-refresh.sh"), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_first_wave_only_and_summary_table(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "b.json").write_text(json.dumps([
                {"name": "first-box", "ssh_target": "c", "platform": "mac", "wave": "first"},
                {"name": "rest-box", "ssh_target": "r", "platform": "hostinger", "container": "ctr"}]))
            r = self.run_wrapper(td, "--wave", "first", "--boxes-file", f"{td}/b.json")
            self.assertIn("first-box", r.stdout)
            self.assertNotIn("rest-box", r.stdout)
            self.assertRegex(r.stdout, r"first-box\s+SKIPPED\s+no onboarding clone")
            self.assertIn("UPDATED=0   ROLLED_BACK=0   FAILED=0   SKIPPED=1", r.stdout)
            self.assertIn("zsh -lc", Path(td, "ssh.log").read_text())   # Mac: login shell

            r = self.run_wrapper(td, "--wave", "rest", "--boxes-file", f"{td}/b.json")
            self.assertIn("rest-box", r.stdout)
            self.assertNotIn("first-box ", r.stdout)
            self.assertIn("docker exec -u 'node'  'ctr' bash -lc", Path(td, "ssh.log").read_text())

    def test_local_apply_refuses_a_dev_checkout(self):
        # A throwaway clone whose runner is a stub: nothing real can be applied.
        with tempfile.TemporaryDirectory() as td:
            clone = new_repo(Path(td, "clone"))
            stub = 'import json,sys; print(json.dumps({"box": "local", "result": "ok", "outcome": "UPDATED"}))\n'
            commit(clone, {"scripts/fleet-refresh.sh": (REPO / "scripts/fleet-refresh.sh").read_text(),
                           "shared-utils/fleet_refresh_runner.py": stub,
                           "cc-compat.json": (REPO / "cc-compat.json").read_text()}, "one")
            fake = Path(td, "bin")
            fake.mkdir()
            (fake / "curl").write_text("#!/bin/sh\necho 200\n")
            (fake / "curl").chmod(0o755)
            env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": td}
            run = lambda: subprocess.run(["bash", str(clone / "scripts/fleet-refresh.sh"), "--local", "--apply"],
                                         capture_output=True, text=True, env=env, timeout=120)
            git(clone, "checkout", "-q", "-b", "feature")
            r = run()
            self.assertEqual(r.returncode, 1)
            self.assertIn("clean onboarding clone on main", r.stderr)
            git(clone, "checkout", "-q", "main")
            (clone / "cc-compat.json").write_text("{}")
            r = run()
            self.assertEqual(r.returncode, 1)
            self.assertIn("uncommitted changes", r.stderr)
            git(clone, "checkout", "-q", "--", "cc-compat.json")
            r = run()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("UPDATED=1", r.stdout)

    def test_apply_through_ssh_and_docker_exec_quoting(self):
        """Real shells end to end: fake ssh runs its command with sh -c, fake
        docker runs `bash -lc <script>`. Proves the nested quoting, the clone
        sync to origin/main, the pre-sync SHA hand-off and the result pickup."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            wrapper_repo = td / "operator-clone"
            (wrapper_repo / "scripts").mkdir(parents=True)
            (wrapper_repo / "shared-utils").mkdir()
            (wrapper_repo / "scripts/fleet-refresh.sh").write_text((REPO / "scripts/fleet-refresh.sh").read_text())
            (wrapper_repo / "shared-utils/fleet_refresh_runner.py").write_text("")
            (wrapper_repo / "cc-compat.json").write_text((REPO / "cc-compat.json").read_text())
            # the box: a clone of an origin that has moved on
            origin = td / "origin.git"
            origin.mkdir()
            git(origin, "init", "-q", "--bare", "-b", "main")
            seed = new_repo(td / "seed")
            stub = ('import json,os,sys\n'
                    'print("banner from a login shell")\n'
                    'print(json.dumps({"box": sys.argv[sys.argv.index("--box")+1], "result": "ok", "outcome": "UPDATED",\n'
                    '  "outcome_detail": "prev=" + os.environ.get("FLEET_PREV_ONBOARDING_SHA", "") + " args=" + " ".join(sys.argv[1:])}))\n')
            commit(seed, {"shared-utils/fleet_refresh_runner.py": stub}, "one")
            git(seed, "remote", "add", "origin", str(origin))
            git(seed, "push", "-q", "origin", "main")
            home = td / "home"
            box_clone = home / "clawd/openclaw-onboarding"
            box_clone.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(box_clone)], check=True, env=GIT_ENV)
            old = git(box_clone, "rev-parse", "HEAD")
            commit(seed, {"x": "2"}, "two")
            git(seed, "push", "-q", "origin", "main")
            fake = td / "bin"
            fake.mkdir()
            (fake / "curl").write_text("#!/bin/sh\necho 200\n")
            (fake / "ssh").write_text('#!/bin/sh\nfor a; do last="$a"; done\nexec sh -c "$last"\n')
            (fake / "docker").write_text('#!/bin/bash\nwhile [ "$1" != bash ]; do shift; done\nexec bash -c "$3"\n')
            for f in fake.iterdir():
                f.chmod(0o755)
            Path(td, "b.json").write_text(json.dumps([{"name": "box-1", "ssh_target": "h", "platform": "hostinger",
                                                       "container": "c-1", "wave": "first"}]))
            env = {**GIT_ENV, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": str(home)}
            r = subprocess.run(["bash", str(wrapper_repo / "scripts/fleet-refresh.sh"), "--wave", "first",
                                "--boxes-file", str(td / "b.json"), "--apply"],
                               capture_output=True, text=True, env=env, timeout=120)
            self.assertIn("UPDATED=1", r.stdout, r.stdout + r.stderr)
            row = json.loads((wrapper_repo / ".fleet-refresh-summary.json").read_text())[0]
            self.assertIn(f"prev={old} args=--box box-1 --shared-utils {box_clone}/shared-utils", row["outcome_detail"])
            self.assertIn(" --apply", row["outcome_detail"])
            self.assertEqual(git(box_clone, "rev-parse", "HEAD"), git(seed, "rev-parse", "HEAD"))

    def test_bad_wave_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            r = self.run_wrapper(td, "--wave", "bogus")
            self.assertEqual(r.returncode, 1)
            self.assertIn("--wave must be first or rest", r.stderr)


class WeeklyFullUpdate(unittest.TestCase):
    def test_syncs_clone_then_runs_the_operator_roll_locally(self):
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td, "origin.git")
            origin.mkdir()
            git(origin, "init", "-q", "--bare", "-b", "main")
            seed = new_repo(Path(td, "seed"))
            commit(seed, {"scripts/fleet-refresh.sh":
                          'echo "ARGS=$* PREV=$FLEET_PREV_ONBOARDING_SHA HEAD=$(git -C "$(dirname "$0")/.." rev-parse HEAD)"\n'},
                   "one")
            git(seed, "remote", "add", "origin", str(origin))
            git(seed, "push", "-q", "origin", "main")
            clone = Path(td, "clone")
            subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, env=GIT_ENV)
            old = git(clone, "rev-parse", "HEAD")
            new = commit(seed, {"x": "2"}, "two")
            git(seed, "push", "-q", "origin", "main")
            r = subprocess.run(["bash", str(REPO / "scripts" / "weekly-full-update.sh")], capture_output=True,
                               text=True, env={**GIT_ENV, "ONBOARDING_CLONE": str(clone), "HOME": td})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"ARGS=--local --apply PREV={old} HEAD={new}", r.stdout)


class SundayCronHeal(unittest.TestCase):
    """update-skills.sh repoints every box's existing Sunday cron script at
    scripts/weekly-full-update.sh (the operator roll's exact path)."""

    def heal(self, td, url):
        src = (REPO / "update-skills.sh").read_text()
        start = src.index("CANONICAL_UPDATER_URL=")
        end = src.index("heal_weekly_cron_updater() {")
        script = Path(td, "restart")
        script.write_text(f'#!/bin/bash\nUPDATE_SCRIPT_URL="{url}"\ncurl -fsSL "$UPDATE_SCRIPT_URL"\n')
        harness = ("oc_backup_precheck_disk() { return 0; }\noc_backup_size_kb() { echo 1; }\n"
                   "oc_backup_prune() { :; }\n" + src[start:end] + f'\nheal_one_weekly_cron_updater "{script}"\n')
        r = subprocess.run(["bash", "-c", harness], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return script.read_text()

    def test_repoints_both_older_urls_and_leaves_others(self):
        base = "https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/"
        full = base + "scripts/weekly-full-update.sh"
        with tempfile.TemporaryDirectory() as td:
            self.assertIn(full, self.heal(td, base + "update-skills.sh"))
            self.assertIn(full, self.heal(td, base + "scripts/update-skills.sh"))
            self.assertIn(full, self.heal(td, full))
            self.assertIn("https://example.invalid/mine.sh", self.heal(td, "https://example.invalid/mine.sh"))
            self.assertNotIn("weekly-full-update", self.heal(td, "https://example.invalid/mine.sh"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
