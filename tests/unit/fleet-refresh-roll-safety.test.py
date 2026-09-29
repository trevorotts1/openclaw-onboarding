#!/usr/bin/env python3
"""Roll-safety contract for shared-utils/fleet_refresh_runner.py and
scripts/make-fleet-boxes-file.py.

Hermetic: every repo, box tree and script lives under a temp dir; the health
probes that would touch live services are replaced with fakes. Run:

    python3 tests/unit/fleet-refresh-roll-safety.test.py
"""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from shutil import which as shutil_which
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
# Hermetic: no test may reach the operator's Google account or alert webhook.
os.environ["FLEET_GOOGLE_SA"] = "/nonexistent/service-account.json"
for _k in ("FLEET_STANDING_GATE_URL", "FLEET_STANDING_GATE_SECRET", "FLEET_OPERATOR_ALERT_URL"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(REPO / "shared-utils"))
import fleet_refresh_runner as fr  # noqa: E402
import fleet_notify  # noqa: E402

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

    CLEAN = {n: hc("pass") for n in fr.INTEGRITY_CHECKS}

    def gate(self, posts, after=None, integ=None, host_restart=False, pinned="vB", baseline=None):
        """Run heal_and_gate with scripted probes. `posts` is the post-update
        health seen on each loop pass (the last one repeats); fix actions are
        recorded, not executed."""
        seq = list(posts)
        self.actions = []

        def fake_probe(paths, res=None):
            if res is None:
                return after if after is not None else health()
            return seq.pop(0) if len(seq) > 1 else seq[0]

        def fake_action(act, paths, repo_root, res, ctx):
            self.actions.append(act)
            if act == "restart-gateway" and not fake_action.mac:
                return "needs-host"
            if act.startswith("rerun:"):      # like the real one: the step's own result
                return res.steps.get(act.split(":", 1)[1], "ok")
            return "ok"
        fake_action.mac = False
        integ_seq = list(integ or [self.CLEAN])
        fake_integ = lambda *a, **k: integ_seq.pop(0) if len(integ_seq) > 1 else integ_seq[0]
        self.ctx = {"pinned": pinned, "cc_tag": "v0", "force_cc": False, "host_restart": host_restart}
        with mock.patch.object(fr, "probe_health", side_effect=fake_probe), \
             mock.patch.object(fr, "probe_integrity", side_effect=fake_integ), \
             mock.patch.object(fr, "_run_heal_action", side_effect=fake_action):
            return fr.heal_and_gate(self.box.paths, self.box.onb, self.res, baseline or health(), self.ctx)

    def test_gate_pass_keeps_the_update(self):
        self.snapshot()
        self.box.apply_release_b()
        self.assertEqual(self.gate([health()]), "done")
        self.assertEqual(self.res.steps["health-gate"], "ok")
        self.assertEqual(self.res.rollback, {})
        self.assertEqual(self.actions, [])
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v2")
        self.assertFalse(self.box.deploy_log.exists())

    def test_an_unchanged_integrity_failure_is_not_re_synced_again(self):
        # A role-library mismatch that a finished update-skills pass did not fix
        # will not be fixed by a second or third 20-55 minute pass.
        self.snapshot()
        self.box.apply_release_b()
        bad = dict(self.CLEAN, **{"role-library": hc("fail")})
        self.gate([health()], integ=[bad])
        self.assertEqual(self.actions, ["rerun:pull-onboarding"])
        self.assertEqual(len(self.res.heal["attempts"]), 1)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")

    def test_fix_attempts_are_budgeted_per_roll_not_per_pass(self):
        # One box re-entered the same 1/3 -> 3/3 cycle three times in two hours.
        self.snapshot()
        self.box.apply_release_b()
        self.gate([health(cc_health="fail")])
        self.assertEqual(len(self.res.heal["attempts"]), 3)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        # the same release rolled again: no fresh three attempts for the same check
        self.res = fr.BoxResult("t", dry_run=False)
        self.snapshot()
        self.box.apply_release_b()
        self.gate([health(cc_health="fail")])
        self.assertEqual(self.actions, [])
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("already used", self.res.outcome_detail)
        # a new release gets a fresh budget, and a pass clears it
        self.res = fr.BoxResult("t", dry_run=False)
        self.snapshot()
        self.gate([health(cc_health="fail"), health()], pinned="vC")
        self.assertEqual(self.res.steps["health-gate"], "ok:healed after 1 fix attempt(s)")
        self.assertFalse((self.box.root / "fleet-refresh" / "heal-budget.json").exists())

    def test_a_config_backlog_from_before_the_update_is_still_applied(self):
        self.snapshot()
        self.box.apply_release_b()
        stale = health(config_applied="fail")
        with mock.patch.object(fr.sys, "platform", "darwin"):
            self.gate([stale, health()], baseline=stale)
        self.assertEqual(self.actions, ["restart-gateway"])
        self.assertEqual(self.res.steps["health-gate"], "ok:healed after 1 fix attempt(s)")

    def test_a_config_still_unapplied_after_its_restart_is_reported_never_rolled_back(self):
        self.snapshot()
        self.box.apply_release_b()
        with mock.patch.object(fr.sys, "platform", "darwin"):
            self.gate([health(config_applied="fail")])
        self.assertEqual(self.actions, ["restart-gateway"])   # one restart per roll, not three
        self.assertEqual(self.res.rollback, {})
        self.assertEqual(self.res.heal["config_pending"], "fake fail")
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v2")

    def test_fix_first_heals_without_rollback(self):
        self.snapshot()
        self.box.apply_release_b()
        self.gate([health(cc_health="fail"), health(cc_health="fail"), health()])
        self.assertEqual(self.res.steps["health-gate"], "ok:healed after 2 fix attempt(s)")
        self.assertEqual(self.res.rollback, {})
        self.assertEqual(self.actions, ["rebuild-cc"] * 2)
        attempts = self.res.heal["attempts"]
        self.assertEqual([a["n"] for a in attempts], [1, 2])
        self.assertIn("cc-health", attempts[0]["failing"])
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v2")

    def test_three_failed_fixes_then_everything_rolls_back(self):
        self.snapshot()
        self.box.apply_release_b()
        self.gate([health(cc_health="fail")])
        self.assertEqual(len(self.res.heal["attempts"]), 3)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("3 fix attempt(s) failed", self.res.outcome_detail)
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

    def test_rollback_saves_a_dirty_file_then_forces_the_reset(self):
        self.snapshot()
        self.box.apply_release_b()
        (self.box.cc / "scripts" / "atomic-deploy.sh").write_text("#!/usr/bin/env bash\n# patched on the box\nexit 0\n")
        self.assertTrue(fr.rollback_box(self.box.paths, self.box.onb, self.res, ["x"]), self.res.rollback)
        self.assertEqual(git(self.box.cc, "rev-parse", "HEAD"), self.box.cc_a)
        saved = next(a for a in self.res.rollback["actions"] if "local changes saved" in a).rsplit(" ", 1)[1]
        self.assertIn("# patched on the box", Path(saved, "scripts", "atomic-deploy.sh").read_text())
        self.assertIn("patched on the box", Path(saved, "changes.diff").read_text())

    def test_half_applied_step_is_retried_then_rolled_back(self):
        self.snapshot()
        self.box.apply_release_b()
        self.res.steps["pull-onboarding"] = "failed:update-skills.sh exited 1"
        self.gate([health()])
        self.assertEqual(self.actions.count("rerun:pull-onboarding"), 3)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("pull-onboarding", self.res.outcome_detail)
        self.assertEqual((self.box.skills / "01-skill" / "SKILL.md").read_text(), "v1")

    def test_content_mismatch_reruns_the_updater_then_rolls_back(self):
        self.snapshot()
        self.box.apply_release_b()
        bad = dict(self.CLEAN, **{"sop-library": hc("fail")})
        self.gate([health()], integ=[bad])
        # one full re-sync; an unchanged failure after it is not re-synced again
        self.assertEqual(self.actions.count("rerun:pull-onboarding"), 1)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertIn("sop-library", self.res.outcome_detail)

    def test_content_mismatch_fixed_by_a_rerun_keeps_the_update(self):
        self.snapshot()
        self.box.apply_release_b()
        bad = dict(self.CLEAN, **{"persona-index": hc("fail")})
        self.gate([health()], integ=[bad, self.CLEAN])
        self.assertEqual(self.res.steps["health-gate"], "ok:healed after 1 fix attempt(s)")
        self.assertEqual(self.res.rollback, {})

    def test_preexisting_content_gap_is_alerted_not_rolled_back(self):
        self.snapshot()
        self.box.apply_release_b()
        gap = dict(self.CLEAN, **{"sop-embeddings": hc("fail")})
        self.res.health["integrity_baseline"] = gap
        self.gate([health()], integ=[gap])
        self.assertEqual(self.res.steps["health-gate"], "ok")
        self.assertEqual(self.actions, [])
        self.assertEqual(self.res.rollback, {})
        self.assertIn("sop-embeddings", self.res.health["content_gaps_preexisting"])

    def test_cc_step_failure_with_unchanged_checkout_is_not_rolled_back(self):
        self.snapshot()
        self.res.steps["pull-cc"] = "failed:CC dir not found: /elsewhere"
        self.gate([health()], pinned="vA")
        self.assertEqual(self.res.steps["health-gate"], "ok")
        self.assertEqual(self.res.rollback, {})

    def test_cc_step_failure_after_the_checkout_moved_rolls_back(self):
        self.snapshot()
        self.box.apply_release_b()
        self.res.steps["build-cc"] = "failed:atomic-deploy.sh exited 2 (pre-flight/build failed; previous build left serving)"
        self.gate([health()])
        self.assertIn("rebuild-cc", self.actions)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertEqual(git(self.box.cc, "rev-parse", "HEAD"), self.box.cc_a)

    def test_container_gateway_fix_is_handed_to_the_host_and_resumes(self):
        self.snapshot()
        self.box.apply_release_b()
        with mock.patch.object(fr.sys, "platform", "linux"):
            r = self.gate([health(gateway_health="fail")], host_restart=True)
        self.assertEqual(r, "needs-host-restart")
        self.assertTrue(self.res.heal["pending_host_restart"])
        self.assertEqual(self.res.heal["attempts"][0]["actions"]["restart-gateway"], "requested from host")
        # resume from the saved state, as fleet-refresh.sh --continue-heal does
        res2, base2, ctx2 = fr.load_heal_state(Path(self.res.heal["state_path"]))
        self.assertEqual(res2.snapshot["cc"]["sha"], self.box.cc_a)
        self.assertEqual(ctx2["cc_tag"], "v0")
        self.res = res2
        self.assertEqual(self.gate([health()], host_restart=True), "done")
        self.assertEqual(self.res.steps["health-gate"], "ok:healed after 1 fix attempt(s)")

    def test_container_without_host_access_cannot_restart_the_gateway(self):
        self.snapshot()
        self.box.apply_release_b()
        self.gate([health(gateway_process="fail")], host_restart=False)
        acts = self.res.heal["attempts"][0]["actions"]
        self.assertIn("no host access", acts["restart-gateway"])
        self.assertEqual(self.res.outcome, "ROLLED_BACK")

    def test_heal_actions_follow_the_failing_checks(self):
        # No fix attempt resets the owner's session: that wiped one owner's live
        # chat 10 times in 3.5 hours. The one reset runs after the gate.
        self.assertEqual(fr.heal_actions({"gateway-health": ""}), ["restart-gateway"])
        self.assertEqual(fr.heal_actions({"telegram-getme": ""}), ["restart-gateway"])
        self.assertEqual(fr.heal_actions({"session-reset": ""}), [])
        self.assertEqual(fr.heal_actions({"role-library": "", "pull-cc": ""}),
                         ["rerun:pull-onboarding", "rerun:pull-cc"])
        self.assertEqual(fr.heal_actions({"restart-cc": ""}), ["rerun:restart-cc"])

    def test_update_skills_exit_2_is_advisory_not_a_failure(self):
        stamp = self.box.skills / ".onboarding-version"
        pinned = json.loads((self.box.onb / "cc-compat.json").read_text())["onboardingVersion"]
        (self.box.onb / "update-skills.sh").write_text(f'#!/usr/bin/env bash\necho {pinned} > "{stamp}"\nexit 2\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            fr.step_pull_onboarding(self.box.paths, self.box.onb, pinned, self.res, dry_run=False)
        self.assertTrue(self.res.steps["pull-onboarding"].startswith("ok:advisory"), self.res.steps["pull-onboarding"])
        # the per-box log says so (three boxes' logs had no pull-onboarding line at all)
        self.assertIn("step pull-onboarding: ok (advisory)", err.getvalue())
        (self.box.onb / "update-skills.sh").write_text('#!/usr/bin/env bash\nexit 1\n')
        fr.step_pull_onboarding(self.box.paths, self.box.onb, pinned, self.res, dry_run=False)
        self.assertTrue(self.res.steps["pull-onboarding"].startswith("failed"))

    def test_rollback_that_does_not_restore_health_is_failed(self):
        self.snapshot()
        self.box.apply_release_b()
        bad = health(gateway_health="fail")
        with mock.patch.object(fr.sys, "platform", "darwin"):
            self.gate([bad], after=bad)
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


class ContentIntegrity(unittest.TestCase):
    """Each post-update content check, on a fixture box, in both directions."""

    def setUp(self):
        import sqlite3
        self.sqlite3 = sqlite3
        self._td = tempfile.TemporaryDirectory()
        t = Path(self._td.name)
        self.skills, self.ws = t / "oc/skills", t / "oc/workspace"
        (self.skills / "shared-utils").mkdir(parents=True)
        for rel in ("prebuilt-index", "sop-library", "sop-embed-once"):
            (self.skills / "shared-utils" / rel).mkdir()
        (self.ws / "data/coaching-personas").mkdir(parents=True)
        self.cc = t / "cc"
        self.cc.mkdir()
        self.paths = {"root": t / "oc", "skills": self.skills, "workspace": self.ws, "cc_dir": self.cc}
        env = mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": str(t)})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self._td.cleanup()

    def manifest(self, rel, data):
        (self.skills / "shared-utils" / rel).write_text(json.dumps(data))

    def db(self, path, sql):
        con = self.sqlite3.connect(path)
        con.executescript(sql)
        con.commit()
        con.close()

    def test_persona_index_and_embeddings(self):
        self.manifest("prebuilt-index/INDEX-MANIFEST.json", {"release_tag": "pi-v2", "embedded_persona_count": 3})
        self.assertEqual(fr.ic_persona_index(self.skills, self.ws)["status"], "fail")
        (self.ws / "data/coaching-personas/.prebuilt-index-version").write_text("pi-v2\n")
        self.assertEqual(fr.ic_persona_index(self.skills, self.ws)["status"], "pass")
        self.assertEqual(fr.ic_persona_embeddings(self.skills, self.ws)["status"], "fail")   # no DB
        dbp = self.ws / "data/coaching-personas/gemini-index.sqlite"
        self.db(dbp, "CREATE TABLE embeddings (id TEXT, persona_id TEXT); INSERT INTO embeddings VALUES ('1','a');")
        self.assertEqual(fr.ic_persona_embeddings(self.skills, self.ws)["status"], "fail")
        # an honest spend-gate deferral receipt accounts for a missing persona
        rec = self.ws / "data/coaching-personas/personas/p-b"
        rec.mkdir(parents=True)
        (rec / "embedding-receipt.json").write_text(json.dumps({"status": "deferred"}))
        self.assertEqual(fr.ic_persona_embeddings(self.skills, self.ws)["status"], "fail")   # 1 + 1 < 3
        self.db(dbp, "INSERT INTO embeddings VALUES ('2','b');")
        self.assertEqual(fr.ic_persona_embeddings(self.skills, self.ws)["status"], "pass")   # 2 + 1 >= 3

    def sop_db(self, sops, embedded):
        dbp = self.cc / "mission-control.db"
        dbp.unlink(missing_ok=True)
        rows = ",".join(f"({i})" for i in range(sops))
        emb = ",".join(f"({i})" for i in range(embedded))
        self.db(dbp, "CREATE TABLE sops (id INTEGER); CREATE TABLE sop_embeddings (sop_id INTEGER);"
                     + (f"INSERT INTO sops VALUES {rows};" if sops else "")
                     + (f"INSERT INTO sop_embeddings VALUES {emb};" if embedded else ""))
        return dbp

    def test_sop_library_and_embeddings(self):
        self.manifest("sop-library/SOP-LIBRARY-MANIFEST.json", {"canonical_sop_count": 5})
        self.manifest("sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json", {"sop_count": 4})
        self.assertEqual([c["status"] for c in fr.ic_sop(self.paths, self.skills)], ["n/a", "n/a"])  # no CC DB
        self.sop_db(3, 3)
        self.assertEqual([c["status"] for c in fr.ic_sop(self.paths, self.skills)], ["fail", "fail"])
        self.sop_db(5, 3)
        self.assertEqual([c["status"] for c in fr.ic_sop(self.paths, self.skills)], ["pass", "fail"])
        self.sop_db(5, 4)
        self.assertEqual([c["status"] for c in fr.ic_sop(self.paths, self.skills)], ["pass", "pass"])

    @unittest.skipUnless(shutil_which("sqlite3"), "sqlite3 CLI needed to run the update-skills.sh probe")
    def test_sop_checks_agree_with_update_skills_probe(self):
        """Parity: the Python port and update-skills.sh's own
        _sop_library_currency_probe reach the same verdict on the same DB."""
        src = (REPO / "update-skills.sh").read_text()
        a = src.index("  _sop_library_currency_probe() {")
        b = src.index("\n  }\n", a) + 4
        su = self.skills / "shared-utils"
        for f in ("resolve_db.py",):
            (su / f).write_text((REPO / "shared-utils" / f).read_text())
        self.manifest("sop-library/SOP-LIBRARY-MANIFEST.json", {"canonical_sop_count": 5})
        self.manifest("sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json", {"sop_count": 4})
        for sops, emb in ((3, 3), (5, 3), (5, 4)):
            dbp = self.sop_db(sops, emb)
            env = {**os.environ, "DASHBOARD_DB_PATH": str(dbp), "SKILLS_DIR": str(self.skills),
                   "EXTRACTED_DIR": "/nonexistent"}
            env.pop("FLEET_REFRESH_ROOT")
            r = subprocess.run(["bash", "-c", src[a:b] + "\n_sop_library_currency_probe"],
                               capture_output=True, text=True, env=env)
            with mock.patch.dict(os.environ, {"DASHBOARD_DB_PATH": str(dbp)}):
                os.environ.pop("FLEET_REFRESH_ROOT")
                ours = fr.ic_sop(self.paths, self.skills)
            ours_ok = all(c["status"] == "pass" for c in ours)
            self.assertEqual(r.returncode == 0, ours_ok, (sops, emb, r.stdout, ours))

    def test_role_library_digest(self):
        repo = Path(self._td.name) / "clone"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts/skill-content-hash.sh").write_text((REPO / "scripts/skill-content-hash.sh").read_text())
        lib = self.skills / "23-ai-workforce-blueprint/templates/role-library"
        lib.mkdir(parents=True)
        (lib / "role.md").write_text("release text")
        out = subprocess.run(["bash", str(repo / "scripts/skill-content-hash.sh"), str(self.skills)],
                             capture_output=True, text=True).stdout
        digest = next(l.split("|")[1] for l in out.splitlines() if l.startswith("23-"))
        (self.skills / ".onboarding-content-manifest.json").write_text(json.dumps(
            {"version": "vB", "skills": {"23-ai-workforce-blueprint": digest}}))
        self.assertEqual(fr.ic_role_library(self.skills, repo, "vB")["status"], "pass")
        self.assertEqual(fr.ic_role_library(self.skills, repo, "vC")["status"], "fail")
        # prove-zhe.py's run receipt, written into the skill dir after the update:
        # run output, not a change to the library (rolled two boxes back).
        rec = self.skills / "23-ai-workforce-blueprint/scripts/receipts"
        rec.mkdir(parents=True)
        (rec / "LOCAL-2026-09-28T205230.json").write_text("{}")
        self.assertEqual(fr.ic_role_library(self.skills, repo, "vB")["status"], "pass")
        (lib / "role.md").write_text("edited on the box")
        self.assertEqual(fr.ic_role_library(self.skills, repo, "vB")["status"], "fail")

    def test_departments(self):
        started = time.time() - 5
        self.assertEqual(fr.ic_departments(self.paths, started)["status"], "n/a")
        receipt = self.ws / ".dept-intake-refresh-receipt.json"
        now = datetime.now(timezone.utc).isoformat()
        receipt.write_text(json.dumps({"ok": False, "apply": True, "at": now,
                                       "depts": [{"dept": "sales", "status": "verify_failed"}]}))
        r = fr.ic_departments(self.paths, started)
        self.assertEqual(r["status"], "fail")
        self.assertIn("sales", r["detail"])
        receipt.write_text(json.dumps({"ok": True, "apply": True, "at": now, "depts": []}))
        self.assertEqual(fr.ic_departments(self.paths, started)["status"], "pass")
        # a receipt from an older run says nothing about this one
        self.assertEqual(fr.ic_departments(self.paths, time.time() + 60)["status"], "n/a")


class MacGatewayRestart(unittest.TestCase):
    def run_with(self, kick_rc, stop_rc, loaded=True):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td, "calls")
            f = Path(td, "launchctl")
            f.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n'
                         f'case "$1" in print) exit {0 if loaded else 113};; '
                         f'kickstart) exit {kick_rc};; stop) exit {stop_rc};; esac\n')
            f.chmod(0o755)
            agents = Path(td, "Library/LaunchAgents")
            agents.mkdir(parents=True)
            (agents / "ai.openclaw.gateway.plist").write_text("<plist/>")
            with mock.patch.dict(os.environ, {"PATH": f"{td}:{os.environ['PATH']}", "HOME": td}):
                try:
                    return fr.restart_gateway_mac(), log.read_text()
                except RuntimeError as e:
                    return f"raised: {e}", log.read_text()

    def test_kickstart_then_stop_fallback(self):
        out, calls = self.run_with(0, 0)
        self.assertEqual(out, "launchctl kickstart ok")
        self.assertIn(f"kickstart -k gui/{os.getuid()}/ai.openclaw.gateway", calls)
        out, calls = self.run_with(125, 0)
        self.assertIn("launchctl stop ok", out)
        self.assertIn("stop ai.openclaw.gateway", calls)
        out, _ = self.run_with(125, 3)
        self.assertTrue(out.startswith("raised:"))
        out, calls = self.run_with(0, 0, loaded=False)
        self.assertIn("bootstrapped booted-out label", out)
        self.assertIn("bootstrap gui/", calls)
        self.assertNotIn("bootstrap", self.run_with(0, 0)[1])


class HealActionDispatch(unittest.TestCase):
    def test_gateway_restart_is_launchd_on_a_mac_and_the_host_elsewhere(self):
        res = fr.BoxResult("t", dry_run=False)
        with mock.patch.object(fr.sys, "platform", "linux"):
            self.assertEqual(fr._run_heal_action("restart-gateway", {}, Path("."), res, {}), "needs-host")
        with mock.patch.object(fr.sys, "platform", "darwin"), \
             mock.patch.object(fr, "restart_gateway_mac", return_value="launchctl kickstart ok") as rg, \
             mock.patch.object(fr, "_wait_gateway", return_value=True):
            out = fr._run_heal_action("restart-gateway", {}, Path("."), res, {})
        rg.assert_called_once()
        self.assertEqual(out, "launchctl kickstart ok; gateway healthy")

    def test_rerun_actions_call_the_real_steps(self):
        res = fr.BoxResult("t", dry_run=False)
        ctx = {"pinned": "v1", "cc_tag": "v0"}
        with mock.patch.object(fr, "step_pull_onboarding", return_value="v2") as po, \
             mock.patch.object(fr, "step_build_cc") as bc, \
             mock.patch.object(fr, "step_sessions_reset_ceo") as sr, \
             mock.patch.object(fr, "_resolve_ceo_session_key", return_value="k"):
            fr._run_heal_action("rerun:pull-onboarding", {}, Path("."), res, ctx)
            fr._run_heal_action("rebuild-cc", {}, Path("."), res, ctx)
            self.assertEqual(fr._run_heal_action("reset-session", {}, Path("."), res, ctx), "unknown action")
        po.assert_called_once()
        self.assertEqual(ctx["pinned"], "v2")
        bc.assert_called_once()
        sr.assert_not_called()   # a fix attempt never resets the owner's session


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

    def test_local_changes_are_skipped_never_pulled_over(self):
        repo, marker, new_sha = self.make_999("Downloads/999-setup")
        before = git(repo, "rev-parse", "HEAD")
        (repo / "AGENT_INSTALL.md").write_text("the owner's own edit")
        res = fr.BoxResult("t", dry_run=False)
        fr.step_update_999(res, dry_run=False)
        self.assertEqual(res.steps["update-999"], "skip:999 has local changes, not updated")
        self.assertEqual(git(repo, "rev-parse", "HEAD"), before)
        self.assertEqual((repo / "AGENT_INSTALL.md").read_text(), "the owner's own edit")
        self.assertFalse(marker.exists())

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


class CommandCenterDiscovery(unittest.TestCase):
    """The runner finds the box's OWN Command Center code checkout, and never
    touches a folder that holds the live database."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.home = Path(self._td.name)
        self.patches = [mock.patch.dict(os.environ),
                        mock.patch.object(Path, "home", return_value=self.home),
                        mock.patch.object(fr, "_port_pids", return_value=[]),
                        mock.patch.object(fr, "_run_out", return_value="")]
        for pt in self.patches:
            pt.start()
            self.addCleanup(pt.stop)
        for k in ("CC_APP_DIR", "BLACKCEO_COMMAND_CENTER_ROOT", "CC_PORT"):
            os.environ.pop(k, None)
        # the operator Mac's layout: the DB folder first in the candidate list, the code elsewhere
        self.db_dir = self.home / "projects" / "command-center"
        self.db_dir.mkdir(parents=True)
        (self.db_dir / "mission-control.db").write_bytes(b"live db")
        (self.db_dir / "mission-control.db-wal").write_bytes(b"wal")
        self.code = new_repo(self.home / "blackceo-command-center")
        commit(self.code, {"package.json": '{"version": "7.6.71"}'}, "A")
        git(self.code, "remote", "add", "origin", "https://github.com/trevorotts1/blackceo-command-center.git")

    def tearDown(self):
        self._td.cleanup()

    def db_state(self):
        return sorted((p.name, p.read_bytes()) for p in self.db_dir.iterdir())

    def test_code_checkout_is_found_past_the_database_folder(self):
        before = self.db_state()
        d, how = fr.find_cc_dir(self.home / ".openclaw")
        self.assertEqual((d, how), (self.code, "candidate list"))
        self.assertEqual(self.db_state(), before)   # the DB folder is never touched

    def test_the_process_serving_the_port_wins(self):
        other = new_repo(self.home / "clients" / "cc")
        commit(other, {"package.json": "{}"}, "A")
        git(other, "remote", "add", "origin", "git@github.com:trevorotts1/blackceo-command-center.git")
        with mock.patch.object(fr, "_port_pids", return_value=[4242]), \
             mock.patch.object(fr, "_proc_cwd", return_value=other / ".next" / "standalone"):
            self.assertEqual(fr.find_cc_dir(self.home), (other, "the process serving port 4000"))

    def test_a_contabo_root_command_center_is_a_candidate(self):
        shutil.rmtree(self.code)
        root = self.home / ".openclaw"
        cc = new_repo(root / "command-center")
        commit(cc, {"package.json": "{}"}, "A")
        git(cc, "remote", "add", "origin", "https://github.com/trevorotts1/blackceo-command-center")
        self.assertEqual(fr.find_cc_dir(root)[0], cc)

    def test_none_found_skips_the_command_center_steps_by_name(self):
        shutil.rmtree(self.code)
        self.assertEqual(fr.find_cc_dir(self.home), (None, fr.CC_NOT_FOUND))
        res = fr.BoxResult("t", dry_run=False)
        fr.step_pull_cc({"cc_dir": None}, "v1", res, dry_run=False)
        with mock.patch.object(fr, "wave5_deploy_preflight"):
            fr.step_build_cc({"cc_dir": None}, res, dry_run=False)
            fr.step_restart_cc({"cc_dir": None}, res, dry_run=False)
        for step in ("pull-cc", "build-cc", "restart-cc"):
            self.assertEqual(res.steps[step], "skip:Command Center not found on this box")


class MainSessionKey(unittest.TestCase):
    def sessions(self, rows):
        return mock.patch.object(fr, "_run_out", return_value=json.dumps({"sessions": rows}))

    def test_session_store_through_the_cli(self):
        rows = [{"key": "agent:main:rescue-reply:x-1", "updatedAt": 99},
                {"key": "agent:main:telegram:operator:direct:111", "updatedAt": 5},
                {"key": "agent:main:main", "updatedAt": 50},
                {"key": "agent:main:cron:abc", "updatedAt": 90}]
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": ""}):
            with self.sessions(rows):   # the most recently used owner session wins
                self.assertEqual(fr._resolve_ceo_session_key({"root": Path(td)}), "agent:main:main")
            rows[1]["updatedAt"] = 60
            with self.sessions(rows):
                self.assertEqual(fr._resolve_ceo_session_key({"root": Path(td)}),
                                 "agent:main:telegram:operator:direct:111")

    def test_owner_agent_is_the_telegram_bound_agent(self):
        # Many client boxes have no agent named "main": the CEO is the agent the
        # Telegram channel is bound to (e.g. dept-master-orchestrator).
        calls = []

        def run_out(cmd, timeout=10):
            calls.append(cmd[cmd.index("--agent") + 1])
            rows = {"dept-master-orchestrator": [{"key": "agent:dept-master-orchestrator:main", "updatedAt": 5},
                                                 {"key": "agent:dept-master-orchestrator:cron:x", "updatedAt": 9}]}
            return json.dumps({"sessions": rows.get(cmd[cmd.index("--agent") + 1], [])})
        with tempfile.TemporaryDirectory() as td, mock.patch.object(fr, "_run_out", side_effect=run_out), \
             mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": ""}):
            Path(td, "openclaw.json").write_text(json.dumps(
                {"bindings": [{"agentId": "rescue-bot", "match": {"channel": "telegram", "accountId": "rescue"}},
                              {"agentId": "dept-sales", "match": {"channel": "telegram", "peer": {"kind": "group", "id": "-1"}}},
                              {"agentId": "dept-master-orchestrator", "match": {"channel": "telegram", "accountId": "*"}}]}))
            self.assertEqual(fr._resolve_ceo_session_key({"root": Path(td)}), "agent:dept-master-orchestrator:main")
            self.assertEqual(calls[0], "dept-master-orchestrator")

    def test_legacy_sessions_json_still_works(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td, "agents", "main", "sessions", "sessions.json")
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps({"agent:main:telegram:direct:222": {"updatedAt": 1}, "agent:main:x": {}}))
            self.assertEqual(fr._resolve_ceo_session_key({"root": Path(td)}), "agent:main:telegram:direct:222")

    def test_nothing_found_is_none(self):
        with tempfile.TemporaryDirectory() as td, self.sessions([{"key": "agent:main:cron:1"}]), \
             mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": ""}):
            self.assertIsNone(fr._resolve_ceo_session_key({"root": Path(td)}))


class PullCcRunsTheTargetUpdater(unittest.TestCase):
    """The live checkout's update.sh is the OLD release's: it merged into the
    live tree before building (a 35-minute outage). pull-cc runs origin/main's."""

    def test_target_updater_runs(self):
        paired = json.loads((REPO / "cc-compat.json").read_text())["commandCenter"]["pinnedTag"]
        with tempfile.TemporaryDirectory() as td:
            origin = new_repo(Path(td, "origin"))
            marker = Path(td, "ran.txt")
            upd = '#!/usr/bin/env bash\necho {} > "{}"\ngit fetch -q origin main\ngit merge -q --ff-only origin/main\n'
            commit(origin, {"package.json": json.dumps({"version": paired.lstrip("v")}),
                            "update.sh": upd.format("old-live-updater", marker)}, "A")
            live = Path(td, "live")
            subprocess.run(["git", "clone", "-q", str(origin), str(live)], check=True, env=GIT_ENV)
            commit(origin, {"update.sh": upd.format("target-updater", marker), "new.txt": "x"}, "B")
            res = fr.BoxResult("t", dry_run=False)
            import cc_runtime_preflight
            with mock.patch.object(cc_runtime_preflight, "check_node"), \
                 mock.patch.object(cc_runtime_preflight, "check_checkout"):
                fr.step_pull_cc({"cc_dir": live}, paired, res, dry_run=False)
            self.assertEqual(res.steps["pull-cc"], "ok", res.errors)
            self.assertEqual(marker.read_text().strip(), "target-updater")
            self.assertTrue((live / "new.txt").is_file())

    def test_pull_cc_deploys_the_rolls_commit_not_a_later_main(self):
        paired = json.loads((REPO / "cc-compat.json").read_text())["commandCenter"]["pinnedTag"]
        with tempfile.TemporaryDirectory() as td:
            origin = new_repo(Path(td, "origin"))
            commit(origin, {"package.json": json.dumps({"version": paired.lstrip("v")}), "update.sh": "exit 0\n"}, "old")
            live = Path(td, "live")
            subprocess.run(["git", "clone", "-q", str(origin), str(live)], check=True, env=GIT_ENV)
            commit(origin, {"package.json": json.dumps({"version": paired.lstrip("v")}),
                            "update.sh": 'git merge -q --ff-only "${CC_UPDATE_TARGET:-origin/main}"\n'}, "roll")
            roll = git(origin, "rev-parse", "HEAD")
            commit(origin, {"later.txt": "merged mid-roll"}, "later")
            res = fr.BoxResult("t", dry_run=False)
            import cc_runtime_preflight
            with mock.patch.object(cc_runtime_preflight, "check_node"), \
                 mock.patch.object(cc_runtime_preflight, "check_checkout"), \
                 mock.patch.dict(os.environ, {"CC_UPDATE_TARGET": roll}):
                fr.step_pull_cc({"cc_dir": live}, paired, res, dry_run=False)
            self.assertEqual(res.steps["pull-cc"], "ok", res.errors)
            self.assertEqual(git(live, "rev-parse", "HEAD"), roll)

    def test_a_tag_only_clone_still_sees_the_latest_main(self):
        # A client Command Center cloned with a single-tag refspec: a bare
        # `git fetch origin main` never moves origin/main, and the floor check then
        # read an ancient package.json (6.0.89) and refused the update.
        paired = json.loads((REPO / "cc-compat.json").read_text())["commandCenter"]["pinnedTag"]
        with tempfile.TemporaryDirectory() as td:
            origin = new_repo(Path(td, "origin"))
            commit(origin, {"package.json": json.dumps({"version": "6.0.89"}), "update.sh": "exit 0\n"}, "old")
            git(origin, "tag", "v6.0.89")
            live = Path(td, "live")
            subprocess.run(["git", "clone", "-q", str(origin), str(live)], check=True, env=GIT_ENV)
            git(live, "config", "remote.origin.fetch", "+refs/tags/v6.0.89:refs/tags/v6.0.89")
            commit(origin, {"package.json": json.dumps({"version": paired.lstrip("v")}),
                            "update.sh": "git merge -q --ff-only origin/main\n"}, "new")
            res = fr.BoxResult("t", dry_run=False)
            import cc_runtime_preflight
            with mock.patch.object(cc_runtime_preflight, "check_node"), \
                 mock.patch.object(cc_runtime_preflight, "check_checkout"):
                fr.step_pull_cc({"cc_dir": live}, paired, res, dry_run=False)
            self.assertEqual(res.steps["pull-cc"], "ok", res.errors)
            self.assertEqual(git(live, "rev-parse", "origin/main"), git(origin, "rev-parse", "HEAD"))


class NoSpareRedeploy(unittest.TestCase):
    def test_a_current_healthy_build_is_not_rebuilt_or_restarted(self):
        with tempfile.TemporaryDirectory() as td:
            box = Box(Path(td))
            import cc_runtime_preflight
            with mock.patch.object(fr, "wave5_deploy_preflight"), \
                 mock.patch.object(cc_runtime_preflight, "check_node"), \
                 mock.patch.object(cc_runtime_preflight, "check_checkout"), \
                 mock.patch.object(fr, "_served_build_current", return_value=True), \
                 mock.patch.object(fr, "hc_cc_health", return_value=hc("pass")), \
                 mock.patch.object(fr, "_run_duck_ci_test", return_value=(True, "ok")), \
                 mock.patch.object(fr, "_run_atomic_deploy") as deploy:
                res = fr.BoxResult("t", dry_run=False)
                fr.step_build_cc(box.paths, res, dry_run=False)
                fr.step_restart_cc(box.paths, res, dry_run=False)
            deploy.assert_not_called()
            self.assertEqual((res.steps["build-cc"], res.steps["restart-cc"]), ("ok", "ok"))


class BillingHoldIsNotAFailure(unittest.TestCase):
    def test_held_update_is_skipped_and_nothing_else_changes(self):
        # update-skills.sh's fleet standing gate exits 0 without stamping when the
        # account is not current; that was retried 3 times then rolled back.
        with tempfile.TemporaryDirectory() as td:
            box = Box(Path(td))
            Path(box.onb, "update-skills.sh").write_text("#!/bin/sh\n")
            held = subprocess.CompletedProcess([], 0, "  Update held -- account not current on payments.\n", "")
            res = fr.BoxResult("t", dry_run=False)
            with mock.patch.object(fr, "_run_tree", return_value=held):
                fr.step_pull_onboarding(box.paths, box.onb, "vB", res, dry_run=False)
            self.assertEqual(res.steps["pull-onboarding"], f"skip:{fr.UPDATE_HELD}")
            self.assertNotIn("failed", str(res.steps))

    def test_a_real_failure_keeps_the_updaters_own_words(self):
        with tempfile.TemporaryDirectory() as td:
            box = Box(Path(td))
            Path(box.onb, "update-skills.sh").write_text("#!/bin/sh\n")
            bad = subprocess.CompletedProcess([], 1, "lots of output\nERROR: bootstrap could not source X\n", "")
            res = fr.BoxResult("t", dry_run=False)
            with mock.patch.object(fr, "_run_tree", return_value=bad):
                fr.step_pull_onboarding(box.paths, box.onb, "vB", res, dry_run=False)
            self.assertIn("ERROR: bootstrap could not source X", res.steps["pull-onboarding"])


class ProvisioningPathsPreferTheRealCompanyDir(unittest.TestCase):
    def test_zhc_slug_dir_wins_over_a_missing_flat_departments_json(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td, "workspace")
            slug = ws / "zero-human-company" / "some-company"
            slug.mkdir(parents=True)
            (slug / "departments.json").write_text("[]")
            (slug / "company-config.json").write_text("{}")
            got = fr._resolve_provisioning_paths({
                "workspace": ws, "company_root": Path(td, "master-files", "zero-human-company"),
                "company_dir": None, "departments_json": ws / "departments.json",
                "company_config": ws / "company-config.json"})
            self.assertEqual(got["departments_json"], slug / "departments.json")
            self.assertEqual(got["zhc_company_config"], slug / "company-config.json")

    def test_get_openclaw_paths_finds_a_workspace_zhc_company(self):
        # persona-selector and every other get_openclaw_paths() reader had the same
        # flat-path assumption for company-config.json.
        with tempfile.TemporaryDirectory() as td:
            slug = Path(td, ".openclaw", "workspace", "zero-human-company", "some-company")
            slug.mkdir(parents=True)
            (slug / "company-config.json").write_text("{}")
            out = subprocess.run(
                [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import detect_platform as d; "
                 "p = d.get_openclaw_paths(); print(p['company_config']); print(p['departments_json'])",
                 str(REPO / "shared-utils")],
                capture_output=True, text=True, env={**os.environ, "HOME": td, "OPENCLAW_PLATFORM": "",
                                                     "MASTER_FILES_DIR": "", "OPENCLAW_COMPANY_SLUG": ""})
            self.assertEqual(out.stdout.split(), [str(slug / "company-config.json"), str(slug / "departments.json")],
                             out.stderr)

    def test_build_state_found_in_the_owner_agents_own_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nova = root / "workspace-nova"
            nova.mkdir()
            (nova / ".workforce-build-state.json").write_text("{}")
            (root / "openclaw.json").write_text(json.dumps({
                "bindings": [{"agentId": "thea", "match": {"channel": "telegram", "accountId": "default"}}],
                "agents": {"entries": {"thea": {"workspace": str(nova)}}}}))
            got = fr._resolve_provisioning_paths({"root": root, "workspace": root / "workspace", "company_dir": None})
            self.assertEqual(got["build_state"], nova / ".workforce-build-state.json")

    def test_an_existing_flat_file_still_wins(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td, "workspace")
            ws.mkdir()
            (ws / "departments.json").write_text("[]")
            got = fr._resolve_provisioning_paths({"workspace": ws, "company_dir": None,
                                                 "departments_json": ws / "departments.json"})
            self.assertEqual(got["departments_json"], ws / "departments.json")


class RefreshStaleRolesNeverInventsABuild(unittest.TestCase):
    """On a box with no interview, the roll's role refresh created a roles-only
    .workforce-build-state.json the interview crons then read as a build."""

    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "refresh_stale_roles", REPO / "23-ai-workforce-blueprint/scripts/refresh-stale-roles.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_state_file_is_not_created(self):
        mod = self.load()
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(mod._apply_state_restamps(Path(td), {}, {}, {"d/r": {"source_content_sha": "x"}}))
            self.assertFalse(Path(td, ".workforce-build-state.json").exists())

    def test_an_existing_state_file_is_still_restamped(self):
        mod = self.load()
        with tempfile.TemporaryDirectory() as td:
            f = Path(td, ".workforce-build-state.json")
            f.write_text(json.dumps({"interviewComplete": True}))
            self.assertTrue(mod._apply_state_restamps(Path(td), {}, {}, {"d/r": {"source_content_sha": "x"}}))
            d = json.loads(f.read_text())
            self.assertTrue(d["interviewComplete"])
            self.assertEqual(d["artifactProvenance"]["roles"]["d/r"]["source_content_sha"], "x")


class ContaboStartupTemplate(unittest.TestCase):
    """Hostinger parity: a shell without PM2_HOME must reach the one pm2 daemon."""

    def test_links_home_pm2_moves_a_stray_aside_and_execs_the_gateway(self):
        with tempfile.TemporaryDirectory() as td:
            home, oc, bin_ = Path(td, "home"), Path(td, "oc"), Path(td, "bin")
            (home / ".pm2").mkdir(parents=True)
            (home / ".pm2" / "dump.pm2").write_text("stray")
            bin_.mkdir()
            (bin_ / "node").write_text(f'#!/bin/sh\necho "$@" > {td}/node-args\n')
            (bin_ / "pm2").write_text(f'#!/bin/sh\necho "$@ $PM2_HOME" >> {td}/pm2-calls\n')
            for f in bin_.iterdir():
                f.chmod(0o755)
            env = {"HOME": str(home), "OPENCLAW_ROOT": str(oc), "PATH": f"{bin_}:/usr/bin:/bin",
                   "PM2_RESURRECT_DELAY": "0"}
            r = subprocess.run(["bash", str(REPO / "platform/vps/contabo/container-startup.sh")],
                               env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.readlink(home / ".pm2"), str(oc / ".pm2"))
            strays = [p for p in home.iterdir() if p.name.startswith(".pm2.stray-")]
            self.assertEqual([(p / "dump.pm2").read_text() for p in strays], ["stray"])
            self.assertEqual(Path(td, "node-args").read_text().split(), ["openclaw.mjs", "gateway"])
            for _ in range(50):
                if Path(td, "pm2-calls").exists():
                    break
                time.sleep(0.1)
            self.assertEqual(Path(td, "pm2-calls").read_text().split(), ["resurrect", str(oc / ".pm2")])


class ProveZheReceiptsLiveOutsideTheSkillTree(unittest.TestCase):
    def test_receipts_go_to_the_state_dir_and_old_ones_move_out(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "prove_zhe", REPO / "23-ai-workforce-blueprint/scripts/prove-zhe.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            legacy = Path(td, "skills/23-ai-workforce-blueprint/scripts/receipts")
            legacy.mkdir(parents=True)
            (legacy / "LOCAL-old.json").write_text("{}")
            mod.LEGACY_RECEIPTS_DIR = str(legacy)
            with mock.patch.dict(os.environ, {"OPENCLAW_ROOT": td, "ZHE_RECEIPTS_DIR": ""}):
                path = mod.write_receipt({"box": "LOCAL", "ts": "2026-09-28T20:52:30+00:00"})
            state = Path(td, "state/zhe-receipts")
            self.assertEqual(Path(path).parent, state)
            self.assertEqual(sorted(p.name for p in state.iterdir()),
                             ["LOCAL-2026-09-28T205230+0000.json", "LOCAL-old.json"])
            self.assertFalse(legacy.exists(), "nothing left inside the hashed skill tree")


class CeoSessionResetOncePerRoll(unittest.TestCase):
    def test_no_owner_session_yet_is_ok_not_a_failure(self):
        res = fr.BoxResult("t", dry_run=False)
        fr.step_sessions_reset_ceo(None, res, dry_run=False)
        self.assertTrue(res.steps["sessions-reset-CEO"].startswith("ok:no owner session yet"))
        self.assertEqual(fr.hc_session_reset(res)["status"], "pass")

    def test_once_per_roll_and_never_twice_within_the_interval(self):
        with tempfile.TemporaryDirectory() as td:
            paths = {"root": Path(td)}
            calls = []

            def reset(key, res, dry_run):
                calls.append(key)
                res.step_ok("sessions-reset-CEO")
            with mock.patch.object(fr, "_resolve_ceo_session_key", return_value="agent:ceo:main"), \
                 mock.patch.object(fr, "step_sessions_reset_ceo", side_effect=reset):
                res = fr.BoxResult("t", dry_run=False)
                fr.reset_ceo_once(paths, res, False)
                fr.reset_ceo_once(paths, res, False)          # the same roll: no second reset
                self.assertEqual(calls, ["agent:ceo:main"])
                again = fr.BoxResult("t", dry_run=False)       # a re-roll minutes later
                fr.reset_ceo_once(paths, again, False)
                self.assertEqual(calls, ["agent:ceo:main"])
                self.assertIn("reset 0 min ago", again.steps["sessions-reset-CEO"])
                marker = Path(td, "fleet-refresh/.ceo-session-reset.json")
                marker.write_text(json.dumps({"agent:ceo:main": time.time() - fr.RESET_MIN_INTERVAL - 1}))
                fr.reset_ceo_once(paths, fr.BoxResult("t", dry_run=False), False)
                self.assertEqual(calls, ["agent:ceo:main"] * 2)

    def test_rollback_does_not_reset_the_session(self):
        src = (REPO / "shared-utils/fleet_refresh_runner.py").read_text()
        body = src[src.index("def rollback_box("):src.index("def _save_local_changes(")]
        self.assertNotIn("step_sessions_reset_ceo", body)


class ChecksAfterARollbackRunTheRollsCode(unittest.TestCase):
    """rollback_box resets the runner's own clone to the pre-roll commit; the
    checks that follow imported their modules lazily and ran the old release's
    code (a v25.2.3 embedding check failed a box the rolled check passes)."""

    def test_a_rewound_clone_does_not_change_the_checks(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            clone = tmp / "shared-utils"
            shutil.copytree(REPO / "shared-utils", clone)
            probe = (
                "import sys; sys.path.insert(0, sys.argv[1]); import fleet_refresh_runner\n"
                "open(sys.argv[1] + '/embedding_health.py', 'w').write('OLD_RELEASE = True\\n')\n"
                "from embedding_health import run_embedding_health\n"
                "print('roll code')\n"
            )
            r = subprocess.run([sys.executable, "-c", probe, str(clone)], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.stdout.strip(), "roll code", r.stderr[-400:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DeployedCommandCenterVersionIsReadAfterTheUpdate(unittest.TestCase):
    """Pass notes said "Command Center v7.6.63" on boxes the roll had moved to v7.6.77."""

    def test_the_version_on_disk_now_is_reported(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "package.json").write_text(json.dumps({"name": "blackceo-command-center", "version": "7.6.77"}))
            res = fr.BoxResult("t-box", False)
            res.cc_version, res.onboarding_version = "7.6.63", "v25.2.11"
            compat = json.loads((REPO / "cc-compat.json").read_text())
            fr._check_deployed({"cc_dir": tmp}, compat, "v25.2.11", res)
            self.assertEqual(res.deployed["cc"], "7.6.77")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class GatewayAppliedTheFinalConfig(unittest.TestCase):
    """Three openclaw.json writes in 32 s superseded a reload: the file carried an
    env var the live gateway never ran with, silently, for hours."""

    def check(self, answers, wait=0.0):
        seq = list(answers)
        with mock.patch.object(fr, "_run_out", side_effect=lambda *a, **k: seq.pop(0) if len(seq) > 1 else seq[0]), \
             mock.patch.object(fr.time, "sleep"):
            return fr.hc_config_applied({}, wait=wait)["status"]

    def test_verdicts(self):
        same = json.dumps({"payload": {"configRevisionHash": "h1", "appliedConfigHash": "h1", "env": {"vars": {"K": "secret"}}}})
        stale = json.dumps({"payload": {"configRevisionHash": "h2", "appliedConfigHash": "h1"}})
        self.assertEqual(self.check([same]), "pass")
        self.assertEqual(self.check([stale]), "fail")
        self.assertEqual(self.check([stale, same], wait=30), "pass")     # a reload in flight lands
        self.assertEqual(self.check([""]), "n/a")                          # older gateway: undetermined

    def test_a_stale_config_is_healed_with_a_gateway_restart(self):
        self.assertEqual(fr.heal_actions({"config-applied": ""}), ["restart-gateway"])


class LoadWarning(unittest.TestCase):
    def test_warns_over_twice_the_cores_and_stays_quiet_below(self):
        for load, expect in ((25.0, True), (3.0, False)):
            res = fr.BoxResult("t", dry_run=False)
            with mock.patch.object(fr.os, "getloadavg", return_value=(load, 0, 0)), \
                 mock.patch.object(fr.os, "cpu_count", return_value=10):
                fr.load_warning(res)
            self.assertEqual("load" in res.steps, expect)
            if expect:
                self.assertTrue(res.steps["load"].startswith("ok:advisory: load 25.0 on 10 cores"))


class RollHoldsOneCommit(unittest.TestCase):
    """A PR merged mid-roll reached the boxes that started (or self-synced) after
    it: two boxes pulled v25.2.5 on a v25.2.3 roll and were rolled back."""

    def test_roll_copy_stays_on_the_rolls_commit_after_main_moves(self):
        with tempfile.TemporaryDirectory() as td:
            origin = Path(td, "origin.git")
            origin.mkdir()
            git(origin, "init", "-q", "--bare", "-b", "main")
            seed = new_repo(Path(td, "seed"))
            commit(seed, {"shared-utils/fleet_refresh_runner.py": ""}, "roll")
            roll_sha = git(seed, "rev-parse", "HEAD")
            git(seed, "remote", "add", "origin", str(origin))
            git(seed, "push", "-q", "origin", "main")
            commit(seed, {"x": "merged mid-roll"}, "later")
            git(seed, "push", "-q", "origin", "main")
            home = Path(td, "home")
            env = {**GIT_ENV, "HOME": str(home), "FLEET_ROLL_REPO_URL": str(origin), "FLEET_ROLL_SHA": roll_sha}
            for _ in ("cloned", "updated"):
                r = subprocess.run(["bash", str(REPO / "scripts/fleet-roll-copy.sh")],
                                   capture_output=True, text=True, env=env, timeout=60)
                self.assertTrue(r.stdout.startswith("COPY "), r.stdout + r.stderr)
                self.assertEqual(git(home / ".openclaw/fleet-refresh/onboarding", "rev-parse", "HEAD"), roll_sha)

    def test_runner_never_lets_update_skills_resync_its_clone(self):
        # The roll copy, and the operator's own clone on a --local run (a reset to
        # origin/main there moved the clone the roll itself was running from).
        for sub in (("fleet-refresh", "onboarding"), ("clawd", "openclaw-onboarding")):
            self._update_skills_env_skips_self_sync(*sub)

    def _update_skills_env_skips_self_sync(self, *sub):
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td, *sub)
            copy.mkdir(parents=True)
            (copy / "update-skills.sh").write_text("")
            with mock.patch.object(fr, "_run_tree",
                                   return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
                fr.step_pull_onboarding({"root": Path(td), "skills": Path(td, "skills")}, copy, "v1",
                                        fr.BoxResult("t", dry_run=False), dry_run=False)
            self.assertEqual(run.call_args.kwargs["env"].get("OPENCLAW_UPDATE_SKIP_SELF_SYNC"), "1")


class UpdateSkillsExit8IsLaunchPendingNotAFailure(unittest.TestCase):
    """update-skills.sh exits 8 when content is current and stamped but the
    interview launch is pending. The runner failed the step and rolled a box
    back from a correct v25.2.12 to v25.1.81."""

    def run_it(self, stamp):
        with tempfile.TemporaryDirectory() as td:
            skills = Path(td, "skills"); skills.mkdir()
            (skills / ".onboarding-version").write_text(stamp + "\n")
            copy = Path(td, "onb"); copy.mkdir()
            (copy / "update-skills.sh").write_text("")
            res = fr.BoxResult("t", dry_run=False)
            done = subprocess.CompletedProcess([], 8, "", "PENDING: skills content is current; interview launch prerequisites remain unresolved")
            with mock.patch.object(fr, "_run_tree", return_value=done):
                fr.step_pull_onboarding({"root": Path(td), "skills": skills}, copy, "v25.2.12", res, dry_run=False)
            return res

    def test_a_matching_stamp_is_an_advisory(self):
        res = self.run_it("v25.2.12")
        self.assertTrue(res.steps["pull-onboarding"].startswith("ok:advisory: update-skills.sh exit 8"), res.steps)
        self.assertEqual(res.onboarding_version, "v25.2.12")

    def test_a_mismatched_stamp_still_fails(self):
        res = self.run_it("v25.1.81")
        self.assertTrue(res.steps["pull-onboarding"].startswith("failed:"), res.steps)


class UnreadableFoldersAndNoCommandCenter(unittest.TestCase):
    def test_an_unreadable_folder_fails_by_name_not_a_traceback(self):
        # macOS refused ~/Downloads to the SSH process: scandir raised EINTR.
        err = InterruptedError(4, "Interrupted system call", "/Users/x/Downloads/openclaw-master-files")
        with mock.patch.object(fr, "_load_paths", side_effect=err):
            res = fr.run_box("t", REPO / "shared-utils", REPO, dry_run=False, verify_only=False,
                             local=True, force_cc=False, expected_sha=None)
        self.assertEqual(res.outcome, "FAILED")
        self.assertIn("/Users/x/Downloads/openclaw-master-files", res.outcome_detail)
        self.assertIn("Full Disk Access", res.outcome_detail)

    def test_detect_on_a_box_without_a_command_center(self):
        res = fr.BoxResult("t", dry_run=False)
        with tempfile.TemporaryDirectory() as td:
            fr.step_detect({"root": Path(td), "cc_dir": None}, REPO, {}, res)
        self.assertEqual(res.steps["detect"], "ok")


class CommandCenterPm2Preflight(unittest.TestCase):
    """The deploy restarts the Command Center through pm2. A box where that
    cannot work fails up front, by name, with nothing changed -- not half way
    through the deploy ("Required dependency missing: pm2")."""

    def problem(self, managed, which="/usr/local/bin/pm2", pids="", alive=True, god=""):
        with mock.patch.object(fr, "cc_pm2_managed", return_value=managed), \
             mock.patch.object(fr, "_cc_pm2_ancestor", return_value=god), \
             mock.patch.object(fr.shutil, "which", return_value=which), \
             mock.patch.object(fr, "_pm2_home_daemon_alive", return_value=alive), \
             mock.patch.object(fr, "_run_out", return_value=pids):
            return fr.cc_pm2_problem()

    def test_each_way_pm2_cannot_restart_it(self):
        self.assertIsNone(self.problem(None))                          # nothing serving: the deploy starts it
        self.assertIn("not under pm2", self.problem(False))
        self.assertIn("not on this shell's PATH", self.problem(True, which=None))
        self.assertIn("PM2_HOME", self.problem(True, pids="0\n"))     # a stray empty PM2_HOME
        self.assertIsNone(self.problem(True, pids="4242\n"))
        self.assertIn("PM2_HOME", self.problem(True, pids="4242\n", alive=False))   # never spawn a daemon to ask
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"PM2_HOME": f"{td}/stray"}):
            split = self.problem(True, pids="4242\n", god=f"PM2 v7.0.4: God Daemon ({td}/.pm2)")
            self.assertIn("split PM2_HOME", split)
            os.symlink(f"{td}/.pm2", f"{td}/stray")          # the Contabo fix: $HOME/.pm2 -> PM2_HOME
            self.assertIsNone(self.problem(True, pids="4242\n", god=f"PM2 v7.0.4: God Daemon ({td}/.pm2)"))

    def test_pull_cc_refuses_before_changing_anything(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.dict(os.environ, {"FLEET_REFRESH_ROOT": ""}), \
             mock.patch.object(fr, "cc_pm2_problem", return_value="Command Center not under pm2: x"), \
             mock.patch.object(fr.subprocess, "run") as run:
            import cc_runtime_preflight
            res = fr.BoxResult("t", dry_run=False)
            with mock.patch.object(cc_runtime_preflight, "check_node"):
                fr.step_pull_cc({"cc_dir": Path(td)}, "v1", res, dry_run=False)
        run.assert_not_called()
        self.assertEqual(res.steps["pull-cc"], "failed:Command Center not under pm2: x. Nothing was changed.")


class CommandCenterOnlyFailureIsExplicit(unittest.TestCase):
    """A Command Center step that failed without changing anything is not
    rolled back (nothing to undo) -- and the result says exactly that."""

    def test_detail_names_the_real_state(self):
        res = fr.BoxResult("t", dry_run=False)
        res.onboarding_version = "v25.1.105"
        res.snapshot = {"cc": {"version": "7.6.71"}}
        res.health = {"post": {"cc-health": hc("pass")}}
        res.steps.update({"pull-onboarding": "ok", "pull-cc": "failed:not a git repository",
                          "restart-cc": "failed:package.json missing"})
        quiet = [mock.patch.object(fr, n) for n in (
            "_check_deployed", "_verify_loaded", "step_embedding_health", "step_persona_embedding_drift",
            "step_persona_grounding_health", "step_provisioning_completeness", "step_log")]
        for q in quiet:
            q.start()
            self.addCleanup(q.stop)
        fr._finish_run(res, {}, "v25.1.105", {}, Path("."), Path("."), False, False, "v7", None)
        self.assertEqual(res.outcome, "FAILED")
        self.assertTrue(res.outcome_detail.startswith(
            "onboarding updated to v25.1.105, Command Center NOT updated (still v7.6.71, healthy): pull-cc:"),
            res.outcome_detail)


class CurrentOpenClawConfigShapes(unittest.TestCase):
    def test_memory_search_is_read_from_memory_search(self):
        import embedding_health as eh
        cur = {"memory": {"search": {"provider": "gemini", "fallback": "openai"}}}
        self.assertEqual((eh._resolve_memory_search_provider(cur), eh._resolve_memory_search_fallback(cur)),
                         ("gemini", "openai"))
        old = {"agents": {"defaults": {"memorySearch": {"provider": "openai", "fallback": "none"}}}}
        self.assertEqual(eh._resolve_memory_search_provider(old), "openai")
        self.assertIsNone(eh._resolve_memory_search_provider({}))

    def test_an_advisory_is_not_a_failing_check(self):
        res = fr.BoxResult("t", dry_run=False)
        res.steps.update({"pull-onboarding": "ok:advisory: update-skills.sh exit 2 (content current)",
                          "embedding-health": "failed:no key"})
        quiet = [mock.patch.object(fr, n) for n in (
            "_check_deployed", "_verify_loaded", "step_embedding_health", "step_persona_embedding_drift",
            "step_persona_grounding_health", "step_provisioning_completeness", "step_log")]
        for q in quiet:
            q.start()
            self.addCleanup(q.stop)
        fr._finish_run(res, {}, "v1", {}, Path("."), Path("."), False, False, "v7", None)
        self.assertIn("checks failing: embedding-health", res.outcome_detail)
        self.assertIn("succeeded with advisories: pull-onboarding", res.outcome_detail)
        self.assertNotIn("checks failing: pull-onboarding", res.outcome_detail)


class UpdaterTimeoutAndDuckNode(unittest.TestCase):
    def test_timeout_kills_the_whole_process_tree(self):
        with tempfile.TemporaryDirectory() as td:
            pidf = Path(td, "child.pid")
            with self.assertRaises(subprocess.TimeoutExpired):
                fr._run_tree(["bash", "-c", f"sleep 60 & echo $! > {pidf}; wait"], timeout=2)
            pid = int(pidf.read_text())
            time.sleep(0.5)
            with self.assertRaises(ProcessLookupError):   # the orphan would keep updating the box
                os.kill(pid, 0)

    def test_duck_test_node_is_the_one_that_loads_the_native_modules(self):
        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0 if cmd[0] == "/opt/node24/bin/node" else 1)
        with mock.patch.object(fr, "_port_pids", return_value=[42]), \
             mock.patch.object(fr.os, "readlink", return_value="/opt/node24/bin/node"), \
             mock.patch.object(fr.shutil, "which", return_value="/usr/local/bin/node"), \
             mock.patch.object(fr.subprocess, "run", side_effect=run):
            self.assertEqual(fr._cc_node(Path("/cc")), "/opt/node24/bin/node")
        with mock.patch.object(fr, "_port_pids", return_value=[]), \
             mock.patch.object(fr.shutil, "which", return_value="/usr/local/bin/node"), \
             mock.patch.object(fr.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            self.assertEqual(fr._cc_node(Path("/cc")), "/usr/local/bin/node")


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
                               "--out", f"{td}/out/boxes.json", *extra], capture_output=True, text=True,
                              env={**os.environ, "HOME": td})

    def fixture(self, td):
        roster = {"boxes": {
            "mac-b": {"client": "Client Two (Mac mini)", "provider": "mac", "kind": "mac", "registry_id": "mac-b"},
            "mac-a": {"client": "Client Two (MacBook)", "provider": "mac", "kind": "mac", "registry_id": "mac-a"},
            "vps-a": {"client": "Client One", "provider": "hostinger", "kind": "vps", "registry_id": "vps-a"},
            "ctb-a": {"client": "Client Three (Example Co — Contabo)", "provider": "contabo", "kind": "contabo",
                      "registry_id": "ctb-a"},
            "op": {"client": "Operator", "provider": "operator", "kind": "local", "registry_id": "op"},
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

    def test_every_box_names_its_client(self):
        with tempfile.TemporaryDirectory() as td:
            self.fixture(td)
            r = self.run_gen(td)
            self.assertEqual(r.returncode, 0, r.stderr)
            boxes = {e["name"]: e for e in json.loads(Path(td, "out", "boxes.json").read_text())}
            self.assertEqual(boxes["vps-a"]["client"], "Client One")
            self.assertEqual(boxes["ctb-a"]["client"], "Client Three")          # business note dropped
            self.assertEqual(boxes["mac-a"]["client"], "Client Two, MacBook")   # two Macs: note kept
            self.assertEqual(boxes["mac-b"]["client"], "Client Two, Mac mini")
            self.assertIn("Client Three (Contabo), Client Two, MacBook (Mac), Client One (Hostinger)", r.stdout)
            self.assertNotIn("WARNING", r.stderr)

    def test_box_without_a_client_is_unknown_and_warned(self):
        with tempfile.TemporaryDirectory() as td:
            self.fixture(td)
            roster = json.loads(Path(td, "roster.json").read_text())
            del roster["boxes"]["vps-a"]["client"]
            Path(td, "roster.json").write_text(json.dumps(roster))
            r = self.run_gen(td)
            self.assertEqual(r.returncode, 0, r.stderr)
            boxes = {e["name"]: e for e in json.loads(Path(td, "out", "boxes.json").read_text())}
            self.assertEqual(boxes["vps-a"]["client"], "UNKNOWN CLIENT (vps-a)")
            self.assertIn("WARNING: NO CLIENT NAME for box vps-a", r.stderr)

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
        (fake / "ssh").write_text(f'#!/bin/sh\necho "$@" >> "{td}/ssh.log"\necho "COPYFAIL test box cannot reach GitHub"\n')
        for f in fake.iterdir():
            f.chmod(0o755)
        env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": td}
        return subprocess.run(["bash", str(REPO / "scripts" / "fleet-refresh.sh"), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_first_wave_only_and_summary_table(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "b.json").write_text(json.dumps([
                {"client": "Client One", "name": "first-box", "ssh_target": "c", "platform": "mac", "wave": "first"},
                {"name": "rest-box", "ssh_target": "r", "platform": "hostinger", "container": "ctr"}]))
            r = self.run_wrapper(td, "--wave", "first", "--boxes-file", f"{td}/b.json")
            self.assertIn("Queuing Client One (Mac, box first-box)", r.stdout)   # the id, once, for the log
            self.assertIn("Running on 1 box(es): Client One (Mac)", r.stdout)
            self.assertIn("Client One (Mac)  [SKIPPED", r.stdout)
            self.assertIn("fleet-refresh/onboarding", Path(td, "ssh.log").read_text())   # the roll's own copy
            self.assertNotIn("rest-box", r.stdout)
            self.assertRegex(r.stdout, r"CLIENT\s+OUTCOME")
            self.assertRegex(r.stdout, r"\n Client One \(Mac\)\s+SKIPPED\s+not updated: the roll's onboarding copy "
                                       r"could not be prepared \(test box cannot reach GitHub\)")
            self.assertEqual(r.stdout.count("first-box"), 1, r.stdout)
            row = json.loads((REPO / ".fleet-refresh-summary.json").read_text())[0]
            self.assertEqual((row["client"], row["label"]), ("Client One", "Client One (Mac)"))
            self.assertIn("UPDATED=0   ROLLED_BACK=0   FAILED=0   SKIPPED=1", r.stdout)
            self.assertIn("zsh -lc", Path(td, "ssh.log").read_text())   # Mac: login shell

            r = self.run_wrapper(td, "--wave", "rest", "--boxes-file", f"{td}/b.json")
            self.assertIn("UNKNOWN CLIENT (rest-box) (Hostinger)", r.stdout)   # no client: said loudly
            self.assertNotIn("first-box", r.stdout)
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
            # The operator's roll left client.json beside the roll copy: the box names its client.
            cj = Path(td, ".openclaw", "fleet-refresh", "client.json")
            cj.parent.mkdir(parents=True)
            cj.write_text(json.dumps({"client": "Client One", "label": "Client One (Mac)"}))
            r = run()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r"\n Client One \(Mac\)\s+UPDATED")
            row = json.loads((clone / ".fleet-refresh-summary.json").read_text())[0]
            self.assertEqual((row["client"], row["label"]), ("Client One", "Client One (Mac)"))

    def test_apply_through_ssh_and_docker_exec_quoting(self, ssh_stub=None):
        """Real shells end to end: fake ssh runs its command with sh -c, fake
        docker runs `bash -lc <script>`. Proves the nested quoting, the roll
        copy's sync to origin/main, the pre-sync SHA hand-off and the result
        pickup -- and that a stale, shallow, tag-only client clone (first in the
        old candidate list) is neither used nor changed."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            wrapper_repo = td / "operator-clone"
            (wrapper_repo / "scripts").mkdir(parents=True)
            (wrapper_repo / "shared-utils").mkdir()
            for rel in ("scripts/fleet-refresh.sh", "scripts/fleet-roll-copy.sh"):
                (wrapper_repo / rel).write_text((REPO / rel).read_text())
            (wrapper_repo / "shared-utils/fleet_refresh_runner.py").write_text("")
            (wrapper_repo / "cc-compat.json").write_text((REPO / "cc-compat.json").read_text())
            # the box: a roll copy of an origin that has moved on
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
            copy = home / ".openclaw/fleet-refresh/onboarding"
            copy.parent.mkdir(parents=True)
            subprocess.run(["git", "clone", "-q", str(origin), str(copy)], check=True, env=GIT_ENV)
            old = git(copy, "rev-parse", "HEAD")
            git(seed, "tag", "v1")
            git(seed, "push", "-q", "origin", "v1")
            # the client's own stale clone: shallow, fetching one tag only, detached
            stale = home / ".openclaw/skills/onboarding"
            subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "v1", f"file://{origin}", str(stale)],
                           check=True, env=GIT_ENV, capture_output=True)
            git(stale, "config", "remote.origin.fetch", "+refs/tags/v1:refs/tags/v1")
            stale_state = (git(stale, "rev-parse", "HEAD"), git(stale, "config", "--get-all", "remote.origin.fetch"))
            commit(seed, {"x": "2"}, "two")
            git(seed, "push", "-q", "origin", "main")
            fake = td / "bin"
            fake.mkdir()
            (fake / "curl").write_text("#!/bin/sh\necho 200\n")
            (fake / "ssh").write_text(ssh_stub or '#!/bin/sh\nfor a; do last="$a"; done\nexec sh -c "$last"\n')
            (fake / "docker").write_text('#!/bin/bash\nwhile [ "$1" != bash ]; do shift; done\nexec bash -c "$3"\n')
            for f in fake.iterdir():
                f.chmod(0o755)
            Path(td, "b.json").write_text(json.dumps([{"client": "Client One", "name": "box-1", "ssh_target": "h",
                                                       "platform": "hostinger", "container": "c-1", "wave": "first"}]))
            (wrapper_repo / "shared-utils/fleet_notify.py").write_text((REPO / "shared-utils/fleet_notify.py").read_text())
            (wrapper_repo / "shared-utils/operator_google.py").write_text(
                (REPO / "shared-utils/operator_google.py").read_text())
            env = {**GIT_ENV, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": str(home),
                   "FLEET_ROLL_REPO_URL": str(origin)}
            r = subprocess.run(["bash", str(wrapper_repo / "scripts/fleet-refresh.sh"), "--wave", "first",
                                "--boxes-file", str(td / "b.json"), "--apply"],
                               capture_output=True, text=True, env=env, timeout=120)
            self.assertIn("UPDATED=1", r.stdout, r.stdout + r.stderr)
            self.assertIn(f"Client One (Hostinger) — roll copy of onboarding: {copy} (updated)", r.stderr)
            # stub result is result=ok/UPDATED: the pass note names the client (webhook unset here: not sent)
            self.assertIn("pass note: ", r.stdout)
            self.assertIn("✅ Client One (Hostinger) updated and passed", r.stdout)
            row = json.loads((wrapper_repo / ".fleet-refresh-summary.json").read_text())[0]
            self.assertIn(f"prev={old} args=--box box-1 --shared-utils {copy}/shared-utils", row["outcome_detail"])
            self.assertIn(" --apply", row["outcome_detail"])
            self.assertEqual(git(copy, "rev-parse", "HEAD"), git(seed, "rev-parse", "HEAD"))
            self.assertEqual((git(stale, "rev-parse", "HEAD"), git(stale, "config", "--get-all", "remote.origin.fetch")),
                             stale_state)   # the client's clone: untouched
            self.assertEqual(json.loads((home / ".openclaw/fleet-refresh/client.json").read_text()),
                             {"client": "Client One", "label": "Client One (Hostinger)"})   # the box can name itself
            return row

    def test_a_dropped_ssh_session_reads_the_boxs_own_result(self):
        # The runner ignores SIGHUP and finishes on the box; the roll reported
        # three boxes that updated fine as FAILED ("ssh/runner exited 255").
        drop = ('#!/bin/sh\nfor a; do last="$a"; done\n'
                'case "$last" in *--shared-utils*) sh -c "$last" >/dev/null 2>&1; exit 255;; esac\n'
                'exec sh -c "$last"\n')
        row = self.test_apply_through_ssh_and_docker_exec_quoting(ssh_stub=drop)
        self.assertEqual(row["outcome"], "UPDATED")
        self.assertIn("read back from the box after the SSH session dropped", row["outcome_detail"])

    def host_restart_scenario(self, platform, compose_rc=0):
        """A container box whose runner first asks for a gateway restart (exit 4),
        then succeeds once resumed. Fake docker records host-side commands."""
        td = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(td)]))
        wrapper_repo = td / "operator-clone"
        (wrapper_repo / "scripts").mkdir(parents=True)
        (wrapper_repo / "shared-utils").mkdir()
        for rel in ("scripts/fleet-refresh.sh", "scripts/fleet-roll-copy.sh", "scripts/make-fleet-boxes-file.py",
                    "shared-utils/fleet_notify.py", "shared-utils/operator_google.py"):
            (wrapper_repo / rel).write_text((REPO / rel).read_text())
        (wrapper_repo / "shared-utils/fleet_refresh_runner.py").write_text("")
        (wrapper_repo / "cc-compat.json").write_text((REPO / "cc-compat.json").read_text())
        origin = td / "origin.git"
        origin.mkdir()
        git(origin, "init", "-q", "--bare", "-b", "main")
        seed = new_repo(td / "seed")
        stub = ('import json,sys\n'
                'a = sys.argv\n'
                'box = a[a.index("--box")+1]\n'
                'if "--continue-heal" in a:\n'
                '    print(json.dumps({"box": box, "result": "ok", "outcome": "UPDATED",\n'
                '        "outcome_detail": "resumed; host said: " + a[a.index("--host-restart-result")+1]\n'
                '            + ("" if "--host-restart" in a else " [no host restart offered again]")}))\n'
                '    sys.exit(0)\n'
                'assert "--host-restart" in a\n'
                'print(json.dumps({"box": box, "result": "pending_host_restart", "outcome": "PENDING",\n'
                '    "heal": {"state_path": "/tmp/heal state.json"}}))\n'
                'sys.exit(4)\n')
        commit(seed, {"shared-utils/fleet_refresh_runner.py": stub}, "one")
        git(seed, "remote", "add", "origin", str(origin))
        git(seed, "push", "-q", "origin", "main")
        home = td / "home"
        home.mkdir()   # no roll copy yet: the wrapper clones it
        fake = td / "bin"
        fake.mkdir()
        log = td / "docker.log"
        (fake / "curl").write_text("#!/bin/sh\necho 200\n")
        (fake / "ssh").write_text('#!/bin/sh\nfor a; do last="$a"; done\nexec sh -c "$last"\n')
        (fake / "docker").write_text(
            '#!/bin/bash\n'
            f'echo "$*" >> "{log}"\n'
            'case "$1" in\n'
            '  exec) while [ "$1" != bash ]; do shift; done; exec bash -c "$3" ;;\n'
            f'  inspect) case "$3" in *working_dir*) echo {td}/docker/proj ;; *service*) echo openclaw ;; *) echo true ;; esac ;;\n'
            '  restart) exit 0 ;;\n'
            f'  compose) exit {compose_rc} ;;\n'
            'esac\n')
        for f in fake.iterdir():
            f.chmod(0o755)
        Path(td, "b.json").write_text(json.dumps([{"name": "box-1", "ssh_target": "h", "platform": platform,
                                                   "container": "c-1", "wave": "first"}]))
        (td / "docker/proj").mkdir(parents=True)
        env = {**GIT_ENV, "PATH": f"{fake}:{os.environ['PATH']}", "HOME": str(home), "FLEET_ROLL_REPO_URL": str(origin)}
        r = subprocess.run(["bash", str(wrapper_repo / "scripts/fleet-refresh.sh"), "--wave", "first",
                            "--boxes-file", str(td / "b.json"), "--apply"],
                           capture_output=True, text=True, env=env, timeout=180)
        row = json.loads((wrapper_repo / ".fleet-refresh-summary.json").read_text())[0]
        return r, row, log.read_text()

    def test_hostinger_gateway_restart_is_compose_up_then_resume(self):
        r, row, docker = self.host_restart_scenario("hostinger")
        self.assertEqual(row["outcome"], "UPDATED", r.stdout + r.stderr)
        self.assertIn("inspect -f {{ index .Config.Labels \"com.docker.compose.project.working_dir\" }} c-1", docker)
        self.assertIn("compose up -d --force-recreate openclaw", docker)
        self.assertIn("docker compose up -d --force-recreate openclaw ok", row["outcome_detail"])
        self.assertNotIn("restart c-1", docker)
        self.assertIn("--host-restart", docker)

    def test_failed_host_restart_resumes_without_offering_it_again(self):
        r, row, docker = self.host_restart_scenario("hostinger", compose_rc=1)
        self.assertEqual(row["outcome"], "UPDATED", r.stdout + r.stderr)
        self.assertIn("FAILED - the host restart did not complete", row["outcome_detail"])
        self.assertIn("[no host restart offered again]", row["outcome_detail"])

    def test_contabo_gateway_restart_is_docker_restart_then_resume(self):
        r, row, docker = self.host_restart_scenario("contabo")
        self.assertEqual(row["outcome"], "UPDATED", r.stdout + r.stderr)
        self.assertIn("restart c-1", docker)
        self.assertIn("docker restart ok", row["outcome_detail"])
        self.assertNotIn("compose", docker)

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

            # Default: the roll's own copy under the OpenClaw root; the box's other clone is left alone.
            stale = Path(td, ".openclaw/skills/onboarding")
            subprocess.run(["git", "clone", "-q", str(origin), str(stale)], check=True, env=GIT_ENV)
            git(stale, "reset", "-q", "--hard", old)
            r = subprocess.run(["bash", str(REPO / "scripts" / "weekly-full-update.sh")], capture_output=True, text=True,
                               env={**GIT_ENV, "HOME": td, "FLEET_ROLL_REPO_URL": str(origin), "PATH": os.environ["PATH"]})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn(f"ARGS=--local --apply PREV= HEAD={new}", r.stdout)
            self.assertIn(f"onboarding copy {td}/.openclaw/fleet-refresh/onboarding", r.stdout)
            self.assertEqual(git(stale, "rev-parse", "HEAD"), old)


class OperatorAlert(unittest.TestCase):
    ROWS = [{"box": "box-a", "client": "Client One", "label": "Client One (Hostinger)", "outcome": "ROLLED_BACK", "outcome_detail": "3 fix attempt(s) failed; cc-health",
             "heal": {"attempts": [{}, {}, {}]}, "rollback": {"not_restored": "openclaw.json"}},
            {"box": "box-b", "outcome": "FAILED",
             "outcome_detail": "token 123456789:AAHfakefakefakefakefakefakefake1234 leaked"},
            {"box": "box-c", "outcome": "UPDATED"}]

    def test_preexisting_gap_is_alerted_as_needing_attention(self):
        rows = [{"box": "box-d", "outcome": "UPDATED", "heal": {"needs_attention": True},
                 "outcome_detail": "NEEDS ATTENTION - content gaps that were already there before this update"}]
        subject, body = fleet_notify.compose(rows, "t")
        self.assertIn("1 need attention", subject)
        self.assertIn("already there before", body)

    def test_email_only_on_the_operator_machine(self):
        with tempfile.TemporaryDirectory() as td:
            sa = Path(td, "sa.json"); sa.write_text("{}")
            with mock.patch.object(fleet_notify.operator_google, "SA_PATH", sa), \
                 mock.patch.object(fleet_notify.operator_google, "OPERATOR_MARKER", Path(td, "boxes.json")):
                self.assertFalse(fleet_notify.operator_google.available())   # a client box with an SA file
                Path(td, "boxes.json").write_text("[]")
                self.assertTrue(fleet_notify.operator_google.available())

    def test_nothing_to_say_sends_nothing(self):
        with mock.patch.object(fleet_notify, "send_telegram") as tg:
            r = fleet_notify.notify([{"box": "x", "outcome": "UPDATED"}], "t")
        self.assertFalse(r["sent"])
        tg.assert_not_called()

    def test_note_names_boxes_and_never_carries_a_secret(self):
        subject, body = fleet_notify.compose(self.ROWS, "operator roll")
        self.assertIn("1 rolled back, 1 failed", subject)
        self.assertIn("- Client One (Hostinger) rolled back (put back to how it was before the update): "
                      "3 fix attempt(s) failed; cc-health", body)
        self.assertNotIn("box-a", body)
        self.assertIn("- box box-b FAILED", body)   # a result with no client name falls back to its id
        self.assertIn("Fix attempts made before that: 3", body)
        self.assertIn("Nothing was sent to any client", body)
        self.assertNotIn("AAHfakefake", body)

    def test_sends_telegram_and_email_to_the_operator_only(self):
        with mock.patch.object(fleet_notify, "send_telegram", return_value=(True, "ok")) as tg, \
             mock.patch.object(fleet_notify.operator_google, "available", return_value=True), \
             mock.patch.object(fleet_notify.operator_google, "send_email", return_value=(True, "ok")) as em:
            fleet_notify.notify(self.ROWS, "operator roll")
        tg.assert_called_once()
        self.assertEqual(em.call_args.kwargs.get("to", fleet_notify.operator_google.OPERATOR_EMAIL),
                         fleet_notify.operator_google.OPERATOR_EMAIL)
        self.assertEqual(len(em.call_args.args), 2)   # subject, body -- recipient is the operator default

    def test_box_without_google_account_still_alerts_by_telegram(self):
        with mock.patch.object(fleet_notify, "send_telegram", return_value=(True, "ok")) as tg:
            r = fleet_notify.notify(self.ROWS, "a client box (its own update)")
        tg.assert_called_once()
        self.assertFalse(r["email"][0])

    def test_pass_note_names_the_client_and_goes_by_telegram_only(self):
        ok = {"box": "box-c", "client": "Client Two", "label": "Client Two (Contabo)", "outcome": "UPDATED",
              "result": "ok", "onboarding_version": "v1.2.3", "cc_version": "4.5.6"}
        self.assertEqual(fleet_notify.passed_note(ok),
                         "\u2705 Client Two (Contabo) updated and passed. Onboarding v1.2.3, Command Center v4.5.6")
        with mock.patch.object(fleet_notify, "send_telegram", return_value=(True, "ok")) as tg, \
             mock.patch.object(fleet_notify.operator_google, "send_email") as em:
            fleet_notify.notify_passed(ok)
        tg.assert_called_once_with(fleet_notify.passed_note(ok))
        em.assert_not_called()
        for bad in ({"outcome": "ROLLED_BACK", "result": "rolled_back"}, {"outcome": "FAILED"},
                    {"heal": {"needs_attention": True}}):
            self.assertIsNone(fleet_notify.passed_note({**ok, **bad}))
        self.assertEqual(fleet_notify.client_label({"name": "b9", "platform": "mac"}), "UNKNOWN CLIENT (b9) (Mac)")

    def test_telegram_text_survives_the_webhooks_legacy_markdown(self):
        # A lone "_" made Telegram reject the whole alert (HTTP 500 from the webhook).
        sent = {}

        class Resp:
            status = 200
            def read(self): return b'{"ok": true, "result": {"message_id": 7}}'
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def urlopen(req, timeout):
            sent["text"] = json.loads(req.data)["text"]
            return Resp()
        with mock.patch.object(fleet_notify, "alert_target", return_value=("https://x/alert", "H", "s")), \
             mock.patch.object(fleet_notify.urllib.request, "urlopen", side_effect=urlopen):
            ok = fleet_notify.send_telegram("reset refused: scripts/watchdog-cc.sh not_restored *x* [y]")
        self.assertTrue(ok[0])
        self.assertEqual(sent["text"], "reset refused: scripts/watchdog-cc.sh not\\_restored \\*x\\* \\[y]")

    def test_alert_webhook_is_derived_from_the_gate_credentials(self):
        with mock.patch.dict(os.environ, {"FLEET_STANDING_GATE_URL": "https://n8n.example/webhook/fleet-standing-check",
                                          "FLEET_STANDING_GATE_SECRET": "s"}):
            url, header, secret = fleet_notify.alert_target()
        self.assertEqual(url, "https://n8n.example/webhook/fleet-standing-alert")
        self.assertEqual(header, "X-Fleet-Standing-Secret")
        with mock.patch.object(fleet_notify, "_openclaw_env", return_value={}):
            self.assertFalse(fleet_notify.send_telegram("x")[0])   # unconfigured: no send


class BoxListDriveBackup(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("mkboxes", REPO / "scripts/make-fleet-boxes-file.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self._td = tempfile.TemporaryDirectory()
        self.m.FLEET_DIR = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_sheet_round_trip_carries_no_secret_values(self):
        entries = [{"client": "Client One", "name": "b1", "ssh_target": "root@192.0.2.9", "platform": "hostinger",
                    "container": "c1", "docker_exec_user": "node", "wave": "first"},
                   {"name": "b2", "ssh_target": "alias-2", "platform": "mac", "wave": "rest",
                    "tunnel_host": "b2.example.com", "cf_token_env_vars": "CF_X_ID CF_X_SECRET",
                    "cf_access_env_prefix": "CF_X", "cf_tunnel_id": "tun-9"}]
        text = self.m.sheet_rows(entries, {"b1": {"result": "UPDATED", "date": "2026-09-28", "nine99": "n"}})
        self.assertTrue(text.startswith("client,name,"))   # the client is the first column
        self.assertTrue(text.startswith(",".join(self.m.SHEET_COLUMNS)))
        self.assertIn("\nClient One,b1,", text)
        self.assertIn("CF_X_ID CF_X_SECRET", text)
        self.assertIn("UPDATED", text)
        back = self.m.entries_from_sheet_csv(text)
        self.assertEqual((back[1]["cf_access_env_prefix"], back[1]["cf_tunnel_id"]), ("CF_X", "tun-9"))
        self.assertEqual([(e["name"], e["ssh_target"], e["platform"], e["wave"]) for e in back],
                         [("b1", "root@192.0.2.9", "hostinger", "first"), ("b2", "alias-2", "mac", "rest")])
        self.assertEqual(back[0]["container"], "c1")
        self.assertEqual(back[0]["client"], "Client One")
        self.assertNotIn("cf_access_env_prefix", back[0])

    def test_ssh_route_reads_names_not_values(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td, "ssh")
            f.write_text("#!/bin/sh\necho 'hostname box.example.com'\n"
                         "echo 'proxycommand sh -c exec cloudflared access ssh --hostname %h "
                         "--service-token-id \"$CF_ACCESS_B_SVC_CLIENT_ID\" "
                         "--service-token-secret \"$CF_ACCESS_B_SVC_CLIENT_SECRET\"'\n")
            f.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": f"{td}:{os.environ['PATH']}"}):
                host, names = self.m._ssh_route("alias-b")
        self.assertEqual(host, "box.example.com")
        self.assertEqual(names, "CF_ACCESS_B_SVC_CLIENT_ID CF_ACCESS_B_SVC_CLIENT_SECRET")

    def test_record_roll_then_sync(self):
        summ = Path(self._td.name, "s.json")
        summ.write_text(json.dumps([
            {"box": "b1", "outcome": "ROLLED_BACK", "steps": {"update-999": "skip:999 not installed"}},
            {"box": "b2", "outcome": "UPDATED", "steps": {"update-999": "ok"}, "update_999": {"path": "/x"}},
            {"box": "local", "outcome": "UPDATED"}]))
        last = self.m.record_roll(summ)
        self.assertEqual(last["b1"]["result"], "ROLLED_BACK")
        self.assertEqual((last["b1"]["nine99"], last["b2"]["nine99"]), ("n", "y"))
        self.assertNotIn("local", last)
        self.assertEqual(stat.S_IMODE((self.m.FLEET_DIR / "last-roll.json").stat().st_mode), 0o600)
        with mock.patch.object(self.m.operator_google, "available", return_value=True), \
             mock.patch.object(self.m.operator_google, "upsert_sheet", return_value=("sheet-1", "ok")) as up:
            msg = self.m.sync_sheet([{"name": "b1", "ssh_target": "x", "platform": "hostinger"}])
        self.assertIn("refreshed", msg)
        self.assertIn("ROLLED_BACK", up.call_args.args[1])
        self.assertEqual(json.loads((self.m.FLEET_DIR / "boxes-sheet.json").read_text())["id"], "sheet-1")

    def test_a_subset_roll_publishes_the_whole_fleet_to_the_sheet(self):
        master = [{"name": f"b{i}", "ssh_target": "x", "platform": "mac"} for i in range(36)]
        (self.m.FLEET_DIR / "boxes.json").write_text(json.dumps(master))
        subset = Path(self._td.name, "boxes-roll-one.json")
        subset.write_text(json.dumps(master[:1]))
        summ = Path(self._td.name, "s1.json")
        summ.write_text(json.dumps([{"box": "b0", "outcome": "UPDATED"}]))
        with mock.patch.object(self.m, "sync_sheet", return_value="refreshed") as sync, \
             mock.patch.object(sys, "argv", ["x", "--out", str(subset), "--record-roll", str(summ)]):
            self.assertEqual(self.m.main(), 0)
        self.assertEqual(len(sync.call_args.args[0]), 36)

    def test_rebuild_from_sheet_when_the_roster_is_gone(self):
        csv_text = self.m.sheet_rows([{"name": "b1", "ssh_target": "t1", "platform": "contabo",
                                       "container": "oc-b1", "openclaw_root": "/home/node/.openclaw"}], {})
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(self.m.operator_google, "find_sheet", return_value=("sheet-1", "found")), \
             mock.patch.object(self.m.operator_google, "export_sheet_csv", return_value=(csv_text, "ok")), \
             mock.patch.object(sys, "argv", ["x", "--roster", f"{td}/missing.json", "--out", f"{td}/o/boxes.json"]):
            self.assertEqual(self.m.main(), 0)
            got = json.loads(Path(td, "o/boxes.json").read_text())
        self.assertEqual(got[0]["openclaw_root"], "/home/node/.openclaw")
        self.assertEqual(got[0]["container"], "oc-b1")


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
