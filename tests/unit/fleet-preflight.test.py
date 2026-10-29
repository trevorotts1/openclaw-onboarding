#!/usr/bin/env python3
"""Weekly-update pre-flight contract: shared-utils/fleet_preflight.py, its wiring in
update-skills.sh and shared-utils/fleet_refresh_runner.py, and the rule that no
update step touches a skill folder the repo does not ship.

Hermetic: every box tree is a temp dir, the Telegram CLI is a stub on PATH, the
provider smoke checks are replaced, the clock is a seam (FLEET_PREFLIGHT_NOW).

    python3 tests/unit/fleet-preflight.test.py
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
for _k in ("FLEET_STANDING_GATE_URL", "FLEET_STANDING_GATE_SECRET", "FLEET_PREFLIGHT_NOW",
           "FLEET_PREFLIGHT_FREE_BYTES", "FLEET_PREFLIGHT_MEM_FREE_PCT", "FLEET_PREFLIGHT_MAC_LEVEL",
           "FLEET_PREFLIGHT_PSI_SOME", "FLEET_PREFLIGHT_PSI_FULL", "FLEET_PROVIDER_STANDING_FILE",
           "FLEET_PREFLIGHT_RUN_ID", "FLEET_PREFLIGHT_NO_SEND"):
    os.environ.pop(_k, None)
import fleet_preflight as fp  # noqa: E402
import fleet_refresh_runner as runner  # noqa: E402

ORIG_SMOKE = fp._repo_smoke   # Base replaces it with a fake; one test needs the real classifier

GIB = 1024 ** 3
OWNER = "424242424"


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


class Box:
    """A throwaway OpenClaw root with an owner chat and a stub `openclaw` CLI."""

    def __init__(self, owner=OWNER, hold=False):
        self.tmp = Path(tempfile.mkdtemp(prefix="fleet-preflight-"))
        self.root = self.tmp / ".openclaw"
        (self.root / "workspace").mkdir(parents=True)
        (self.root / "openclaw.json").write_text("{}")
        st = {"ownerChat": owner} if owner else {}
        if hold:
            st["ownerSendsHold"] = True
        (self.root / "workspace" / ".workforce-build-state.json").write_text(json.dumps(st))
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.sent = self.tmp / "sent.jsonl"
        cli = self.bin / "openclaw"
        cli.write_text(
            "#!/usr/bin/env python3\nimport json,sys\n"
            "a=sys.argv[1:]\n"
            "t=a[a.index('--target')+1]; m=a[a.index('--message')+1]\n"
            f"open({str(self.sent)!r},'a').write(json.dumps({{'to':t,'text':m}})+'\\n')\n"
            "print(json.dumps({'ok':True,'payload':{'ok':True,'messageId':'7','chatId':t,'channel':'telegram'}}))\n")
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
        self.env = mock.patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}"})
        self.env.start()

    def messages(self):
        return [json.loads(l) for l in self.sent.read_text().splitlines()] if self.sent.exists() else []

    def close(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.box = Box()
        self.addCleanup(self.box.close)
        p = mock.patch.dict(os.environ, {}, clear=False)
        p.start(); self.addCleanup(p.stop)
        for k in ("FLEET_PREFLIGHT_NOW", "FLEET_PREFLIGHT_FREE_BYTES", "FLEET_PREFLIGHT_MEM_FREE_PCT",
                  "FLEET_PREFLIGHT_MAC_LEVEL", "FLEET_PREFLIGHT_PSI_SOME", "FLEET_PREFLIGHT_PSI_FULL"):
            os.environ.pop(k, None)
        os.environ["FLEET_PROVIDER_STANDING_FILE"] = str(self.box.root / "provider-standing.json")
        # No test may reach a real provider: the repo smoke checks are replaced.
        m = mock.patch.object(fp, "_repo_smoke", return_value=None)
        m.start(); self.addCleanup(m.stop)
        # Quiet memory by default so each test isolates one check.
        os.environ.update(FLEET_PREFLIGHT_MEM_FREE_PCT="60", FLEET_PREFLIGHT_MAC_LEVEL="1",
                          FLEET_PREFLIGHT_FREE_BYTES=str(50 * GIB))

    def run_pf(self, phase="checks", standing="unknown", rid="r1"):
        return fp.run(phase, self.box.root, standing, True, rid)


class Constants(unittest.TestCase):
    def test_enforce_date_is_the_named_constant_and_matches_the_shell_copy(self):
        self.assertEqual(fp.FLEET_PREFLIGHT_ENFORCE_FROM.isoformat(), "2026-11-05")
        sh = (REPO / "update-skills.sh").read_text()
        self.assertEqual(re.findall(r'^FLEET_PREFLIGHT_ENFORCE_FROM="([\d-]+)"', sh, re.M), ["2026-11-05"])

    def test_storage_minimum_is_captures_plus_installs_plus_margin(self):
        self.assertEqual(fp.STORAGE_MIN_FREE_BYTES, 4 * GIB)
        self.assertGreaterEqual(fp.STORAGE_MIN_FREE_BYTES,
                                fp.STORAGE_CAPTURES_MAX_BYTES + fp.STORAGE_SAFETY_MARGIN_BYTES)

    def test_every_client_facing_string_says_convert_and_flow_only(self):
        texts = [fp.GRACE_TEXT] + [fp.note_text(i, "OpenRouter", g) for i in ("storage", "memory", "standing", "provider")
                                   for g in (True, False)]
        for t in texts:
            self.assertNotRegex(t, r"(?i)gohighlevel|\bghl\b|high level")
        for t in texts[1:]:
            self.assertTrue(t.rstrip().endswith("- Steph, BlackCEO Fleet Manager"))


class Storage(Base):
    def test_enough_space_proceeds(self):
        self.assertEqual(self.run_pf()["status"], "proceed")

    def test_low_space_pauses_even_in_the_grace_week(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-10-30"
        os.environ["FLEET_PREFLIGHT_FREE_BYTES"] = str(fp.STORAGE_MIN_FREE_BYTES - 1)
        r = self.run_pf()
        self.assertEqual((r["status"], r["pause_reasons"]), ("paused-preflight", ["storage"]))
        self.assertEqual(r["checks"]["storage"]["required_bytes"], fp.STORAGE_MIN_FREE_BYTES)

    def test_exactly_the_minimum_proceeds(self):
        os.environ["FLEET_PREFLIGHT_FREE_BYTES"] = str(fp.STORAGE_MIN_FREE_BYTES)
        self.assertEqual(self.run_pf()["status"], "proceed")


class Memory(Base):
    def heavy(self, **env):
        os.environ.update(env)
        return self.run_pf(rid=env.get("rid", "r1"))

    def test_mac_warn_and_critical_levels_are_heavy(self):
        for lvl in ("2", "4"):
            os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = lvl
            self.assertEqual(self.run_pf(rid=f"lvl{lvl}")["pause_reasons"], ["memory pressure"])

    def test_normal_level_is_fine(self):
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "1"
        self.assertEqual(self.run_pf()["status"], "proceed")

    def test_low_free_percentage_is_heavy(self):
        os.environ["FLEET_PREFLIGHT_MEM_FREE_PCT"] = "9"
        self.assertEqual(self.run_pf()["status"], "paused-preflight")
        os.environ["FLEET_PREFLIGHT_MEM_FREE_PCT"] = "10"
        self.assertEqual(self.run_pf(rid="r2")["status"], "proceed")

    def test_linux_pressure_stall_thresholds(self):
        os.environ.update(FLEET_PREFLIGHT_PSI_SOME="26.0")
        self.assertEqual(self.run_pf(rid="a")["status"], "paused-preflight")
        os.environ.update(FLEET_PREFLIGHT_PSI_SOME="25.0", FLEET_PREFLIGHT_PSI_FULL="5.1")
        self.assertEqual(self.run_pf(rid="b")["status"], "paused-preflight")
        os.environ.update(FLEET_PREFLIGHT_PSI_SOME="25.0", FLEET_PREFLIGHT_PSI_FULL="5.0")
        self.assertEqual(self.run_pf(rid="c")["status"], "proceed")

    def test_retry_is_bounded_and_a_calm_run_resets_it(self):
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "2"
        outs = [self.run_pf(rid=f"run{i}")["status"] for i in range(fp.MEMORY_MAX_DEFERRALS + 1)]
        self.assertEqual(outs, ["paused-preflight"] * fp.MEMORY_MAX_DEFERRALS + ["proceed"])
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "1"
        self.assertEqual(self.run_pf(rid="calm")["status"], "proceed")
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "2"
        self.assertEqual(self.run_pf(rid="again")["status"], "paused-preflight")

    def test_two_phases_of_one_run_count_as_one_deferral(self):
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "2"
        self.run_pf("early", rid="same"); self.run_pf("checks", rid="same")
        n = json.loads((self.box.root / "fleet-preflight" / "memory-deferrals.json").read_text())["count"]
        self.assertEqual(n, 1)


class Standing(Base):
    def test_grace_week_warns_and_notifies_but_does_not_pause(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-04T23:59:59Z"
        r = self.run_pf("standing", "blocked")
        self.assertEqual((r["status"], r["grace_active"], r["checks"]["standing"]["status"]), ("proceed", True, "warn"))
        (msg,) = self.box.messages()
        self.assertIn(fp.GRACE_TEXT, msg["text"])
        self.assertEqual(msg["to"], OWNER)

    def test_from_the_enforce_date_it_pauses(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-05"
        r = self.run_pf("standing", "blocked")
        self.assertEqual((r["status"], r["pause_reasons"]), ("paused-preflight", ["account standing"]))
        self.assertNotIn(fp.GRACE_TEXT, self.box.messages()[0]["text"])

    def test_allowed_sends_nothing(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        self.assertEqual(self.run_pf("standing", "allowed")["status"], "proceed")
        self.assertEqual(self.box.messages(), [])


class Providers(Base):
    def standing_file(self, **entries):
        stamp = os.environ.get("FLEET_PREFLIGHT_NOW", "2026-11-06") + "T00:00:00Z"
        (self.box.root / "provider-standing.json").write_text(json.dumps(
            {k: {"status": v, "checked_at": stamp, "detail": "x"} for k, v in entries.items()}))

    def test_providers_without_a_check_or_a_source_are_external_check_not_wired_and_do_not_block(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        r = self.run_pf()
        pv = r["checks"]["providers"]
        for p in ("ollama", "agnes", "kie"):
            self.assertEqual(pv[p]["status"], "external-check-not-wired")
        self.assertEqual((pv["gemini"]["status"], pv["openrouter"]["status"]), ("not-configured", "not-configured"))
        self.assertEqual(r["status"], "proceed")

    def test_external_fail_pauses_after_the_enforce_date_and_only_warns_before(self):
        self.standing_file(kie="fail")
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        self.assertEqual(self.run_pf()["pause_reasons"], ["kie.ai standing"])
        shutil.rmtree(self.box.root / "fleet-preflight")
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-10-30"
        self.standing_file(kie="fail")
        r = self.run_pf()
        self.assertEqual((r["status"], r["checks"]["providers"]["kie"]["enforced"]), ("proceed", False))
        self.assertIn(fp.GRACE_TEXT, self.box.messages()[-1]["text"])

    def test_external_ok_is_consumed(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        self.standing_file(agnes="ok")
        self.assertEqual(self.run_pf()["checks"]["providers"]["agnes"]["status"], "ok")

    def test_a_stale_external_result_is_ignored(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        (self.box.root / "provider-standing.json").write_text(json.dumps(
            {"ollama": {"status": "fail", "checked_at": "2026-10-01T00:00:00Z"}}))
        r = self.run_pf()
        self.assertEqual((r["status"], r["checks"]["providers"]["ollama"]["status"]), ("proceed", "external-check-not-wired"))

    def test_repo_smoke_auth_failure_is_a_fail_and_a_network_blip_is_only_a_warn(self):
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-06"
        with mock.patch.object(fp, "_repo_smoke", side_effect=lambda p, r: ("fail", "HTTP Error 429: quota") if p == "gemini" else None):
            self.assertEqual(self.run_pf()["pause_reasons"], ["the Gemini API key standing"])
        shutil.rmtree(self.box.root / "fleet-preflight")
        with mock.patch.object(fp, "_repo_smoke", side_effect=lambda p, r: ("warn", "timed out") if p == "gemini" else None):
            r = self.run_pf()
            self.assertEqual((r["status"], r["checks"]["providers"]["gemini"]["status"]), ("proceed", "warn"))

    def test_the_smoke_classifier_never_calls_a_timeout_an_auth_failure(self):
        def eh(msg):
            return mock.Mock(load_openclaw_json=lambda r: {}, _get_api_key=lambda k, c=None: "k" * 30,
                             _smoke_embed_google=lambda k: (False, msg))
        for msg, want in (("smoke FAILED: TimeoutError: timed out", "warn"),
                          ("smoke FAILED: HTTPError: HTTP Error 402: Payment Required, insufficient credit", "fail"),
                          ("smoke FAILED: HTTPError: HTTP Error 403: Forbidden", "fail")):
            with mock.patch.dict(sys.modules, {"embedding_health": eh(msg)}):
                self.assertEqual(ORIG_SMOKE("gemini", self.box.root)[0], want, msg)
        with mock.patch.dict(sys.modules, {"embedding_health": eh("x")}):
            with mock.patch.object(sys.modules["embedding_health"], "_get_api_key", lambda k, c=None: None):
                self.assertIsNone(ORIG_SMOKE("gemini", self.box.root))


class Notices(Base):
    def storage_low(self):
        os.environ["FLEET_PREFLIGHT_FREE_BYTES"] = "1"

    def test_one_note_per_issue_per_week_through_the_clients_own_agent(self):
        self.storage_low()
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-02"   # Monday, ISO week 45
        r1 = self.run_pf(rid="a"); r2 = self.run_pf(rid="b")
        self.assertEqual((r1["notices"]["storage"], r2["notices"]["storage"]), ("sent", "already-noted-this-week"))
        self.assertEqual(len(self.box.messages()), 1)
        txt = self.box.messages()[0]["text"]
        self.assertIn("I'll let you know so your AI can help you free up space", txt)
        self.assertTrue(txt.endswith("- Steph, BlackCEO Fleet Manager"))
        os.environ["FLEET_PREFLIGHT_NOW"] = "2026-11-09"   # next ISO week: one more
        self.assertEqual(self.run_pf(rid="c")["notices"]["storage"], "sent")

    def test_memory_note_text(self):
        os.environ["FLEET_PREFLIGHT_MAC_LEVEL"] = "2"
        self.run_pf()
        t = self.box.messages()[0]["text"].lower()
        self.assertTrue("busy" in t and "waiting so nothing gets interrupted" in t and "try again" in t, t)

    def test_weekly_cap(self):
        self.storage_low()
        os.environ.update(FLEET_PREFLIGHT_MAC_LEVEL="2", FLEET_PREFLIGHT_NOW="2026-11-06")
        (self.box.root / "provider-standing.json").write_text(json.dumps(
            {"kie": {"status": "fail", "checked_at": "2026-11-06T00:00:00Z"}}))
        r = self.run_pf()
        self.assertEqual(sorted(r["notices"].values()), ["sent", "sent", "weekly-note-cap"])
        self.assertEqual(len(self.box.messages()), fp.NOTE_CAP_PER_WEEK)

    def test_an_operator_chat_is_refused(self):
        self.box.close(); self.box = Box(owner="6771245262"); self.addCleanup(self.box.close)
        os.environ["FLEET_PROVIDER_STANDING_FILE"] = str(self.box.root / "provider-standing.json")
        self.storage_low()
        self.assertEqual(self.run_pf()["notices"]["storage"], "refused-operator-chat")
        self.assertEqual(self.box.messages(), [])

    def test_owner_sends_hold_silences_the_note_but_not_the_pause(self):
        self.box.close(); self.box = Box(hold=True); self.addCleanup(self.box.close)
        os.environ["FLEET_PROVIDER_STANDING_FILE"] = str(self.box.root / "provider-standing.json")
        self.storage_low()
        r = self.run_pf()
        self.assertEqual((r["status"], r["notices"]["storage"]), ("paused-preflight", "owner-sends-hold"))
        self.assertEqual(self.box.messages(), [])

    def test_no_owner_chat_sends_nothing(self):
        self.box.close(); self.box = Box(owner=""); self.addCleanup(self.box.close)
        os.environ["FLEET_PROVIDER_STANDING_FILE"] = str(self.box.root / "provider-standing.json")
        self.storage_low()
        self.assertEqual(self.run_pf()["notices"]["storage"], "no-owner-chat")

    def test_a_failed_send_is_not_recorded_so_the_next_run_retries(self):
        self.storage_low()
        (self.box.bin / "openclaw").write_text("#!/bin/sh\nexit 1\n")
        self.assertEqual(self.run_pf(rid="a")["notices"]["storage"], "send-unverified")
        (self.box.bin / "openclaw").write_text(
            "#!/usr/bin/env python3\nimport json,sys\na=sys.argv[1:];t=a[a.index('--target')+1]\n"
            "print(json.dumps({'ok':True,'payload':{'ok':True,'messageId':'9','chatId':t,'channel':'telegram'}}))\n")
        self.assertEqual(self.run_pf(rid="b")["notices"]["storage"], "sent")


class Cli(Base):
    def cli(self, *a, **env):
        e = {**os.environ, **env, "OPENCLAW_ROOT": str(self.box.root)}
        return subprocess.run([sys.executable, str(REPO / "shared-utils/fleet_preflight.py"), *a, "--no-notify"],
                              capture_output=True, text=True, env=e)

    def test_exit_10_and_the_marker_line_when_paused(self):
        r = self.cli("--phase", "early", FLEET_PREFLIGHT_FREE_BYTES="1")
        self.assertEqual(r.returncode, 10)
        self.assertIn("FLEET-PREFLIGHT-PAUSED: storage", r.stdout)
        self.assertEqual(json.loads((self.box.root / "fleet-preflight/status.json").read_text())["status"], "paused-preflight")

    def test_exit_0_when_clear(self):
        self.assertEqual(self.cli("--phase", "early").returncode, 0)

    def test_an_internal_error_fails_open(self):
        with mock.patch.object(fp, "run", side_effect=RuntimeError("boom")):
            self.assertEqual(fp.main(["--phase", "early", "--root", str(self.box.root)]), 0)


class Wiring(unittest.TestCase):
    def test_runner_parses_the_marker_and_counts_client_skills_apart(self):
        self.assertEqual(runner._preflight_reasons("x\nFLEET-PREFLIGHT-PAUSED: storage, memory pressure\n"), "storage, memory pressure")
        self.assertEqual(runner._preflight_reasons("nothing"), "")
        t = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, t, True)
        repo, skills = t / "repo", t / "skills"
        for d in ("01-a", "02-b-ARCHIVED"):
            (repo / d).mkdir(parents=True)
        for d in ("01-a", "02-b", "58-ghl-page-rebuild", "01-a.bak-roll-1", "not-a-skill"):
            (skills / d).mkdir(parents=True)
        self.assertEqual(runner._client_extra_skills(skills, repo), ["58-ghl-page-rebuild"])

    def test_runner_pauses_before_the_snapshot(self):
        t = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, t, True)
        (t / "root").mkdir()
        res = runner.BoxResult("b", False)
        with mock.patch.dict(os.environ, {"FLEET_PREFLIGHT_FREE_BYTES": "1", "FLEET_PREFLIGHT_NO_SEND": "1",
                                          "FLEET_PREFLIGHT_MEM_FREE_PCT": "60", "FLEET_PREFLIGHT_MAC_LEVEL": "1"}):
            why = runner.step_preflight_early({"root": str(t / "root")}, REPO / "shared-utils", res)
        self.assertEqual(why, "storage")
        self.assertEqual(res.preflight["status"], "paused-preflight")

    def test_update_skills_runs_the_preflight_after_the_gate_and_before_install(self):
        sh = (REPO / "update-skills.sh").read_text()
        a, b, c = (sh.index(x) for x in ("\nfleet_standing_gate\n", "\nfleet_preflight_checks\n", "TEMP_EXTRACT=\"/tmp/openclaw-onboarding-update\""))
        self.assertLess(a, b); self.assertLess(b, c)
        self.assertIn("FLEET-PREFLIGHT-PAUSED", (REPO / "shared-utils/fleet_preflight.py").read_text())


class ShellBlock(Base):
    """The FLEET-PREFLIGHT-V1 block of update-skills.sh, extracted and run for real."""

    def run_block(self, helper=True, **env):
        sh = (REPO / "update-skills.sh").read_text()
        blk = sh[sh.index("#=== BEGIN FLEET-PREFLIGHT-V1 ==="):sh.index("#=== END FLEET-PREFLIGHT-V1 ===")]
        blk = blk.replace("\nfleet_preflight_checks\n", "\n")   # the call site; invoked below
        f = self.box.tmp / "blk.sh"
        f.write_text(blk + '\nfleet_preflight_checks\necho __AFTER__\n')
        if helper:
            (self.box.root / "skills").mkdir(exist_ok=True)
            link = self.box.root / "skills" / "shared-utils"
            if not link.exists():
                link.symlink_to(REPO / "shared-utils")
        e = {**os.environ, "OPENCLAW_ROOT": str(self.box.root), "OC_CONFIG": str(self.box.root),
             "HOME": str(self.box.tmp), "FLEET_PREFLIGHT_NO_SEND": "1", **env}
        return subprocess.run(["bash", str(f)], capture_output=True, text=True, env=e)

    def test_paused_box_prints_the_marker_exits_0_and_runs_nothing_after(self):
        r = self.run_block(FLEET_PREFLIGHT_FREE_BYTES="1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("FLEET-PREFLIGHT-PAUSED: storage", r.stdout)
        self.assertNotIn("__AFTER__", r.stdout)

    def test_clear_box_goes_on(self):
        r = self.run_block()
        self.assertEqual(r.returncode, 0)
        self.assertIn("__AFTER__", r.stdout)

    def test_missing_helper_fails_open(self):
        r = self.run_block(helper=False, FLEET_PREFLIGHT_FREE_BYTES="1")
        self.assertIn("proceeding (fail open)", r.stdout)
        self.assertIn("__AFTER__", r.stdout)

    def test_bypass(self):
        r = self.run_block(FLEET_PREFLIGHT_FREE_BYTES="1", FLEET_PREFLIGHT_BYPASS="1")
        self.assertIn("__AFTER__", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
