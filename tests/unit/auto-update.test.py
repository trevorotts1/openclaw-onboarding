#!/usr/bin/env python3
"""Tue/Fri/Sun auto-update contract: scripts/auto_update.py, scripts/auto-update-run.sh,
scripts/setup-weekly-update.sh, shared-utils/auto_update_repair.py and the runner hooks.

Hermetic: every box lives under a temp dir, `openclaw` and `crontab` are stubs on PATH, time is forced with
AUTO_UPDATE_NOW_UTC, versions come from a fixture file. Nothing touches a real box, a client chat or GitHub.

    python3 tests/unit/auto-update.test.py
"""
import datetime as dt
import importlib.util
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
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "shared-utils"))
os.environ["FLEET_PREFLIGHT_BYPASS"] = "1"
for _k in ("FLEET_STANDING_GATE_URL", "FLEET_STANDING_GATE_SECRET", "FLEET_OPERATOR_ALERT_URL",
           "FLEET_AUTO_UPDATE_BEACON_URL", "OPENCLAW_OWNER_CHAT_ID", "FLEET_STANDING_BOX_SLUG"):
    os.environ.pop(_k, None)

import auto_update as au  # noqa: E402
import auto_update_repair as rep  # noqa: E402

UTC = dt.timezone.utc
CLIENT_CHAT = "7771234567"
OPERATOR_CHAT = "5252140759"

OPENCLAW_STUB = r'''#!/bin/bash
D="$STUB_DIR"
echo "$*" >> "$D/openclaw.log"
case "$1 $2" in
  "--version "*) echo "OpenClaw 2026.11.3 (stub)"; exit 0 ;;
  "message send")
    [ -f "$D/send-fails" ] && exit 1
    while [ $# -gt 0 ]; do case "$1" in --target) T="$2";; --message) M="$2";; esac; shift; done
    printf '%s\t%s\n' "$T" "$M" >> "$D/sent.log"; exit 0 ;;
  "sessions list") cat "$D/sessions.json" 2>/dev/null || echo '{"sessions":[]}'; exit 0 ;;
  "gateway call")
    case "$*" in *direct:999*) f="$D/history-999.json" ;; *) f="$D/history.json" ;; esac
    cat "$f" 2>/dev/null || echo '{"messages":[]}'; exit 0 ;;
  "cron list") cat "$D/cronlist.json" 2>/dev/null || echo '{"jobs":[]}'; exit 0 ;;
  "cron rm") echo "$3" >> "$D/cron-rm.log"; exit 0 ;;
  "cron add")
    [ -f "$D/cron-add-fails" ] && exit 1
    echo "$*" >> "$D/cron-add.log"
    case "$*" in *--help*) echo "  --command <shell>"; exit 0 ;; esac
    if [ -f "$D/cronlist-adds" ]; then :; fi
    python3 - "$D" "$@" <<'PY'
import json, sys
d, a = sys.argv[1], sys.argv[3:]
p = d + "/cronlist.json"
try: data = json.load(open(p))
except Exception: data = {"jobs": []}
cmd = a[a.index("--command") + 1] if "--command" in a else ""
data["jobs"].append({"id": "new-" + a[a.index("--name") + 1], "name": a[a.index("--name") + 1], "enabled": True,
                     "payload": {"kind": "command", "argv": ["sh", "-lc", cmd]}})
json.dump(data, open(p, "w"))
PY
    exit 0 ;;
esac
exit 0
'''

PGREP_STUB = r'''#!/bin/bash
[ -f "$STUB_DIR/no-cron-daemon" ] && exit 1
exit 0
'''

CRONTAB_STUB = r'''#!/bin/bash
F="$STUB_DIR/crontab.txt"
case "$1" in
  -l) [ -f "$F" ] || { echo "no crontab for user" >&2; exit 1; }; cat "$F" ;;
  -)  cat > "$F" ;;
esac
'''


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class BoxCase(unittest.TestCase):
    """A fake box: OpenClaw root, stubs on PATH, forced clock, fixture versions."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.home = self.tmp / "home"
        self.root = self.home / ".openclaw"
        self.skills = self.root / "skills"
        self.skills.mkdir(parents=True)
        (self.root / "openclaw.json").write_text("{}")
        self.stub = self.tmp / "stub"
        self.stub.mkdir()
        executable(self.stub / "bin" / "openclaw", OPENCLAW_STUB)
        executable(self.stub / "bin" / "crontab", CRONTAB_STUB)
        executable(self.stub / "bin" / "pgrep", PGREP_STUB)
        self.env = {"HOME": str(self.home), "OPENCLAW_ROOT": str(self.root), "STUB_DIR": str(self.stub),
                    "PATH": f"{self.stub / 'bin'}:{os.environ['PATH']}", "OPENCLAW_OWNER_CHAT_ID": CLIENT_CHAT,
                    "AUTO_UPDATE_PLATFORM": "linux", "FLEET_STANDING_BOX_SLUG": "test-box",
                    "AUTO_UPDATE_RM_DELAY": "0", "OPENCLAW_UPDATE_LEASE": str(self.tmp / "lease.lock")}
        patcher = mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._td.cleanup)
        # onboarding installed v1.0.0, Command Center installed v2.0.0
        (self.skills / ".onboarding-version").write_text("v1.0.0\n")
        self.cc = self.home / "projects" / "command-center"
        self.cc.mkdir(parents=True)
        (self.cc / "package.json").write_text('{"version": "2.0.0"}')
        self.latest = {"onboarding": "v1.0.0", "command_center": "v2.0.0"}
        self.set_latest()

    def set_latest(self, **over):
        self.latest.update(over)
        p = self.tmp / "latest.json"
        p.write_text(json.dumps(self.latest))
        os.environ["AUTO_UPDATE_LATEST_JSON"] = str(p)

    def at(self, iso: str):
        os.environ["AUTO_UPDATE_NOW_UTC"] = iso

    def sent(self):
        p = self.stub / "sent.log"
        return [l.split("\t", 1) for l in p.read_text().splitlines()] if p.exists() else []

    def beacon(self):
        return json.loads((self.skills / ".auto-update-status.json").read_text())

    def history(self, *msgs):
        (self.stub / "history.json").write_text(json.dumps({"messages": list(msgs)}))
        (self.stub / "sessions.json").write_text(json.dumps(
            {"sessions": [{"key": "agent:main:main", "updatedAt": 1}]}))

    def install_update_stub(self, rc=0, outcome="UPDATED", repair=None, cc_result=None, update_999=None, steps=None):
        """root/scripts/weekly-full-update.sh stand-in: records its env, optionally writes a fleet summary."""
        marker = self.tmp / "update-ran.txt"
        runs = self.home / ".openclaw" / "fleet" / "runs" / "r1"
        row = {"outcome": outcome, "outcome_detail": "stub", "heal": {"repair_agent": repair} if repair else {},
               "health": {"regressions": ["cc-health"] if outcome != "UPDATED" else []}}
        if update_999:
            row["update_999"] = update_999
        if steps:
            row["steps"] = steps
        cc_line = ("cat > \"$CC_UPDATE_RESULT_FILE\" <<'CCJSON'\n" + json.dumps(cc_result) + "\nCCJSON") if cc_result else ""
        body = f'''#!/bin/bash
echo "behind=$AUTO_UPDATE_BEHIND repair=$AUTO_UPDATE_REPAIR oc=$AUTO_UPDATE_OPENCLAW" > "{marker}"
mkdir -p "{runs}"
cat > "{runs}/summary.json" <<'JSON'
{json.dumps([row])}
JSON
{cc_line}
exit {rc}
'''
        executable(self.root / "scripts" / "weekly-full-update.sh", body)
        return marker


# ───────────────────────────────────────────────── schedule, DST, time zone ──

class ScheduleAndDst(unittest.TestCase):
    def test_us_dst_boundaries(self):
        off = lambda s: au.eastern_offset(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)).total_seconds() / 3600
        self.assertEqual(off("2026-03-08T06:59:59Z"), -5)    # 1:59:59 AM EST
        self.assertEqual(off("2026-03-08T07:00:00Z"), -4)    # 3:00 AM EDT
        self.assertEqual(off("2026-11-01T05:59:59Z"), -4)    # 1:59:59 AM EDT
        self.assertEqual(off("2026-11-01T06:00:00Z"), -5)    # 1:00 AM EST again
        self.assertEqual(off("2026-07-01T12:00:00Z"), -4)
        self.assertEqual(off("2026-12-25T12:00:00Z"), -5)

    def test_matches_the_system_time_zone_database_every_hour_of_two_years(self):
        try:
            from zoneinfo import ZoneInfo
            ny = ZoneInfo("America/New_York")
        except Exception:
            self.skipTest("no tzdata on this machine")
        t = dt.datetime(2026, 1, 1, tzinfo=UTC)
        while t < dt.datetime(2028, 1, 1, tzinfo=UTC):
            self.assertEqual(au.to_eastern(t), t.astimezone(ny).replace(tzinfo=None), t.isoformat())
            t += dt.timedelta(hours=1)

    def test_scheduled_days_are_tuesday_friday_sunday(self):
        days = {d: au.is_scheduled_day(dt.datetime(2026, 11, d)) for d in range(16, 23)}   # Mon 16 .. Sun 22
        self.assertEqual([d for d, ok in days.items() if ok], [17, 20, 22])

    def test_eastern_wall_clock_is_independent_of_the_box_time_zone(self):
        code = ("import sys; sys.path.insert(0, %r); import auto_update as au, datetime as dt; "
                "u = dt.datetime(2026, 11, 17, 7, 15, tzinfo=dt.timezone.utc); print(au.to_eastern(u).isoformat())"
                % str(REPO / "scripts"))
        outs = {tz: subprocess.run([sys.executable, "-c", code], env={**os.environ, "TZ": tz}, capture_output=True,
                                   text=True).stdout.strip() for tz in ("UTC", "Pacific/Auckland", "Asia/Kolkata")}
        self.assertEqual(set(outs.values()), {"2026-11-17T02:15:00"}, outs)

    def test_notice_2_15_run_2_30_plus_jitter_cutoff_5_30(self):
        d = dt.datetime
        st = {}
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 14, 59), "b", st), "idle")
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 15, 0), "b", st), "notice")
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 29, 59), "b", st), "notice")
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 30, 0), "b", st), "missed_notice")
        self.assertEqual(au.decide(d(2026, 11, 18, 2, 20), "b", st), "idle")      # Wednesday
        noticed = {"notice": {"attempted": True, "sent": True}}
        start = au.run_start_local("b", d(2026, 11, 17, 2, 0))
        self.assertTrue(d(2026, 11, 17, 2, 30) <= start < d(2026, 11, 17, 2, 45))
        self.assertEqual(au.decide(start - dt.timedelta(seconds=1), "b", noticed), "watch")
        self.assertEqual(au.decide(start, "b", noticed), "run")
        self.assertEqual(au.decide(d(2026, 11, 17, 5, 29), "b", noticed), "run")
        self.assertEqual(au.decide(d(2026, 11, 17, 5, 30), "b", noticed), "missed_run")
        self.assertEqual(au.decide(start, "b", {**noticed, "settled": "DONE"}), "idle")

    def test_a_late_notice_never_starts_the_run_before_its_fifteen_minutes_are_up(self):
        d = dt.datetime
        sent = d(2026, 11, 17, 2, 25, 10)                          # first tick after the box woke up
        at_ms = int(au.eastern_to_utc(sent).timestamp() * 1000)
        st = {"notice": {"attempted": True, "sent": True, "at_ms": at_ms}}
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 40, 9), "b", st), "watch")
        self.assertEqual(au.decide(d(2026, 11, 17, 2, 40, 10), "b", st), "run")

    def test_jitter_is_deterministic_per_box_and_day_within_15_minutes(self):
        self.assertEqual(au.jitter_seconds("a", "2026-11-17"), au.jitter_seconds("a", "2026-11-17"))
        vals = {au.jitter_seconds(f"box{i}", "2026-11-17") for i in range(200)}
        self.assertTrue(all(0 <= v < 900 for v in vals))
        self.assertGreater(len(vals), 100)

    def test_spring_forward_sunday_shifts_the_whole_window_by_an_hour(self):
        d = dt.datetime
        self.assertEqual(au.day_shift(dt.date(2026, 3, 8)), dt.timedelta(hours=1))
        self.assertEqual(au.day_shift(dt.date(2026, 3, 15)), dt.timedelta(0))
        self.assertEqual(au.decide(d(2026, 3, 8, 3, 15), "b", {}), "notice")        # 2:15 does not exist that day
        self.assertEqual(au.decide(d(2026, 3, 8, 3, 29), "b", {}), "notice")
        self.assertEqual(au.decide(d(2026, 3, 8, 3, 30), "b", {}), "missed_notice")

    def test_next_runs_lists_only_scheduled_days_in_the_future(self):
        runs = au.next_runs(dt.datetime(2026, 11, 17, 12, 0, tzinfo=UTC), "b", 3)    # Tue noon: next Fri, Sun, Tue
        self.assertEqual([r.split()[0] for r in runs], ["2026-11-20", "2026-11-22", "2026-11-24"])


# ─────────────────────────────────────────── versions: compare, skip, Mac-only 999 ──

class Versions(BoxCase):
    def test_compare(self):
        self.assertTrue(au.is_behind("v1.0.0", "v1.0.1"))
        self.assertTrue(au.is_behind("v27.1.79", "v27.1.80"))
        self.assertFalse(au.is_behind("v27.1.80", "v27.1.80"))
        self.assertFalse(au.is_behind("v28.0.0", "v27.1.80"))        # ahead is not behind
        self.assertTrue(au.is_behind(None, "v1.0.0"))                # unreadable installed: the update repairs it
        self.assertIsNone(au.is_behind("v1.0.0", None))              # unreadable latest: cannot judge

    def make_999(self, version="1.0.0"):
        d = self.home / "999-setup"
        d.mkdir()
        (d / "VERSION").write_text(version + "\n")
        subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
        return d

    def test_999_is_never_checked_on_linux_even_when_a_checkout_exists(self):
        self.make_999()
        self.set_latest(**{"999": "v1.0.1"})
        os.environ["AUTO_UPDATE_PLATFORM"] = "linux"
        v = au.check_versions(self.root)
        self.assertNotIn("999", v)
        self.assertIsNone(self.run_update_beacon("linux")["versions"]["999"])

    def test_999_is_checked_on_macos_when_installed(self):
        self.make_999()
        self.set_latest(**{"999": "v1.0.1"})
        os.environ["AUTO_UPDATE_PLATFORM"] = "darwin"
        v = au.check_versions(self.root)
        self.assertEqual(v["999"], {"installed": "v1.0.0", "latest": "v1.0.1", "behind": True, "error": None})
        self.assertEqual(au.installed_999(), "v1.0.0")           # the checkout VERSION file, not a git tag

    def test_999_is_skipped_on_a_mac_that_does_not_have_it(self):
        self.set_latest(**{"999": "v1.0.1"})
        os.environ["AUTO_UPDATE_PLATFORM"] = "darwin"
        self.assertNotIn("999", au.check_versions(self.root))

    def run_update_beacon(self, platform):
        os.environ["AUTO_UPDATE_PLATFORM"] = platform
        return au.run_update(self.root, "2026-11-17", "rid", True)

    def test_all_current_records_current_and_never_runs_the_updater(self):
        marker = self.install_update_stub()
        b = au.run_update(self.root, "2026-11-17", "rid", True)
        self.assertEqual(b["result"], "CURRENT")
        self.assertFalse(marker.exists())
        self.assertEqual(b["versions"]["onboarding"], {"before": "v1.0.0", "after": "v1.0.0"})

    def test_only_what_is_behind_is_updated(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")                   # Command Center is current
        b = au.run_update(self.root, "2026-11-17", "rid", True)
        self.assertEqual(marker.read_text().strip(), "behind=onboarding repair=1 oc=0")
        self.assertEqual(b["result"], "UPDATED")

    def test_unreadable_latest_is_deferred_not_guessed(self):
        marker = self.install_update_stub()
        (self.tmp / "latest.json").write_text(json.dumps({"onboarding": "v1.0.0"}))      # no command_center
        b = au.run_update(self.root, "2026-11-17", "rid", True)
        self.assertEqual(b["result"], "DEFERRED")
        self.assertIn("command_center", b["failing_check"])
        self.assertFalse(marker.exists())

    def test_a_pinned_release_is_what_gets_compared(self):
        (self.root / "fleet-refresh").mkdir()
        (self.root / "fleet-refresh" / "release-pin.json").write_text(json.dumps({"approved_ref": "v27.1.70"}))
        self.assertEqual(au.pinned_ref(self.root), "v27.1.70")
        (self.root / "fleet-refresh" / "release-pin.json").write_text(json.dumps({"approved_ref": "main"}))
        self.assertEqual(au.pinned_ref(self.root), "main")


class CcAnd999Results(BoxCase):
    def test_command_center_versions_come_from_its_result_file(self):
        self.install_update_stub(cc_result={"schema": "cc-update-result/1", "status": "UPDATED",
                                            "before": {"version": "2.0.0"}, "after": {"version": "2.3.1"}})
        self.set_latest(command_center="v2.3.1")
        b = au.run_update(self.root, "d", "r", True)
        self.assertEqual(b["result"], "UPDATED")
        self.assertEqual(b["versions"]["command_center"], {"before": "v2.0.0", "after": "v2.3.1"})

    def test_a_command_center_result_of_failed_is_a_failure_even_when_the_runner_says_updated(self):
        self.install_update_stub(cc_result={"status": "FAILED", "before": {"version": "2.0.0"}, "after": {"version": "2.0.0"}})
        self.set_latest(command_center="v2.3.1")
        b = au.run_update(self.root, "d", "r", True)
        self.assertEqual(b["result"], "FAILED")
        self.assertIn("Command Center", b["failing_check"])

    def test_a_command_center_step_that_exits_nonzero_with_no_result_is_failed(self):
        self.install_update_stub(rc=3, outcome="", cc_result=None)
        self.set_latest(command_center="v2.3.1")
        self.assertEqual(au.run_update(self.root, "d", "r", True)["result"], "FAILED")

    def test_the_result_file_path_is_handed_to_the_update(self):
        marker = self.tmp / "env.txt"
        executable(self.root / "scripts" / "weekly-full-update.sh", f'#!/bin/bash\necho "$CC_UPDATE_RESULT_FILE" > "{marker}"\n')
        self.set_latest(onboarding="v1.0.1")
        au.run_update(self.root, "d", "r", True)
        self.assertIn(".cc-update-result-", marker.read_text())

    def test_999_versions_come_from_the_999_updaters_result_line_via_the_runner(self):
        d = Versions.make_999(self, "1.0.0")
        self.set_latest(**{"999": "v1.1.0"})
        os.environ["AUTO_UPDATE_PLATFORM"] = "darwin"
        self.install_update_stub(update_999={"result": "UPDATED", "before": "v1.0.0", "after": "v1.1.0"})
        b = au.run_update(self.root, "d", "r", True)
        self.assertEqual(b["versions"]["999"], {"before": "v1.0.0", "after": "v1.1.0"})

    def test_a_mac_without_999_records_not_installed_not_a_failure(self):
        os.environ["AUTO_UPDATE_PLATFORM"] = "darwin"
        self.install_update_stub()
        b = au.run_update(self.root, "d", "r", True)
        self.assertEqual(b["versions"]["999"]["status"], "NOT_INSTALLED")
        self.assertEqual(b["result"], "CURRENT")

    def test_999_checkout_search_is_the_same_two_places_as_the_999_updater(self):
        self.assertEqual(au._999_CANDIDATES, ("999-setup", "Documents/999-setup"))


class OwnerNoteOnScheduledRuns(unittest.TestCase):
    """update-skills.sh's UPDATE PENDING note must not tell the agent to report to the owner on an auto-update."""

    def step6(self, run_id):
        src = (REPO / "update-skills.sh").read_text()
        a = src.index('case "${BFX_LOCK_RUN_ID:-}" in')
        b = src.index("esac", a) + 4
        r = subprocess.run(["bash", "-c", src[a:b] + '\nprintf "%s" "$_UPD_REPORT_STEP"'],
                           env={"PATH": os.environ["PATH"], "BFX_LOCK_RUN_ID": run_id}, capture_output=True, text=True)
        return r.stdout

    def test_scheduled_run_says_do_not_message_the_owner(self):
        out = self.step6("auto-update-20261118T074112Z-4242")
        self.assertIn("do NOT message the owner", out)
        self.assertNotIn("REPORT to owner", out)

    def test_fleet_roll_and_manual_runs_keep_the_owner_report(self):
        for rid in ("", "fleet-roll-123", "weekly-full-update-9"):
            self.assertIn("REPORT to owner ONLY what is verified-installed", self.step6(rid))

    def test_the_heredoc_uses_the_variable(self):
        self.assertIn("${_UPD_REPORT_STEP}", (REPO / "update-skills.sh").read_text())


# ─────────────────────────────────────────────── outcomes, rollback, no-DeepSeek ──

class Outcomes(BoxCase):
    def run_with(self, **kw):
        self.install_update_stub(**kw)
        self.set_latest(onboarding="v1.0.1")
        return au.run_update(self.root, "2026-11-17", "rid", True)

    def test_rolled_back_is_reported_with_the_failing_check(self):
        b = self.run_with(rc=2, outcome="ROLLED_BACK", repair={"model": "openrouter/x", "attempts": 3, "no_model": False})
        self.assertEqual((b["result"], b["failing_check"], b["model_used"]), ("ROLLED_BACK", "cc-health", "openrouter/x"))

    def test_failed_rollback_is_failed(self):
        self.assertEqual(self.run_with(rc=2, outcome="FAILED")["result"], "FAILED")

    def test_no_deepseek_when_repair_was_needed_and_no_model_exists(self):
        b = self.run_with(rc=2, outcome="ROLLED_BACK", repair={"model": None, "attempts": 0, "no_model": True})
        self.assertEqual(b["result"], "NO_DEEPSEEK")

    def test_skipped_by_the_updater_is_deferred(self):
        self.assertEqual(self.run_with(rc=0, outcome="SKIPPED")["result"], "DEFERRED")

    def test_busy_exit_75_is_deferred(self):
        self.assertEqual(self.run_with(rc=75, outcome="")["result"], "DEFERRED")

    def test_beacon_shape_local_files_and_history_cap(self):
        b = self.run_with(rc=0, outcome="UPDATED")
        for k in ("schema", "box", "run_at", "scheduled_day", "result", "versions", "failing_check", "model_used",
                  "notice_sent", "run_id"):
            self.assertIn(k, b)
        self.assertEqual((b["schema"], b["box"]), ("auto-update-beacon/1", "test-box"))
        self.assertRegex(b["run_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        for _ in range(205):
            au.emit_beacon(self.root, b)
        self.assertEqual(len((self.skills / ".auto-update-history.jsonl").read_text().splitlines()), 200)
        self.assertEqual(self.beacon()["result"], "UPDATED")

    def test_remote_beacon_reuses_the_existing_gate_credentials_and_alerts_only_on_trouble(self):
        os.environ["FLEET_STANDING_GATE_URL"] = "https://ops.example.invalid/webhook/fleet-standing-check"
        os.environ["FLEET_STANDING_GATE_SECRET"] = "s3cret"
        os.environ["FLEET_STANDING_GATE_HEADER"] = "X-Test"
        seen = []

        class R:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_open(req, timeout=0):
            seen.append((req.full_url, req.headers.get("X-test"), json.loads(req.data)["result"]))
            return R()
        with mock.patch.object(au.urllib.request, "urlopen", fake_open), \
                mock.patch.object(au, "_alert_operator", return_value=True) as alert:
            au.emit_beacon(self.root, au.build_beacon(self.root, "UPDATED", {}, {}, run_id="r", day="d"))
            au.emit_beacon(self.root, au.build_beacon(self.root, "ROLLED_BACK", {}, {}, run_id="r", day="d"))
        self.assertEqual(seen[0], ("https://ops.example.invalid/webhook/fleet-update-beacon", "s3cret", "UPDATED"))
        self.assertEqual(alert.call_count, 1)


# ─────────────────────────────────────────── the tick: notice, cancel, run, misses ──

class Tick(BoxCase):
    TUE_0215 = "2026-11-17T07:15:00Z"      # Tuesday 2:15 AM EST

    def test_notice_goes_once_to_the_client_owner_chat_with_the_exact_text(self):
        self.at(self.TUE_0215)
        self.assertEqual(au.tick(self.root), "notice")
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "watch")
        self.assertEqual(self.sent(), [[CLIENT_CHAT, au.NOTICE_TEXT]])
        self.assertEqual(au.NOTICE_TEXT, "Heads up: I'll start updating your system in 15 minutes (2:30 AM). "
                                         "Type cancel if you want to skip this update.")

    def test_the_operator_chat_never_receives_the_notice(self):
        os.environ["OPENCLAW_OWNER_CHAT_ID"] = OPERATOR_CHAT           # only an operator id resolvable
        self.at(self.TUE_0215)
        au.tick(self.root)
        self.assertEqual(self.sent(), [])
        self.assertFalse(json.loads((self.skills / ".auto-update-state.json").read_text())["notice"]["sent"])

    def test_nothing_happens_on_other_days_or_before_2_15(self):
        for iso in ("2026-11-18T07:15:00Z", "2026-11-17T07:14:00Z", "2026-11-19T12:00:00Z"):
            self.at(iso)
            self.assertEqual(au.tick(self.root), "idle", iso)
        self.assertEqual(self.sent(), [])

    def test_cancel_skips_this_run_replies_once_and_records_cancelled(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        self.at(self.TUE_0215)
        au.tick(self.root)
        notice_ms = int(dt.datetime(2026, 11, 17, 7, 15, tzinfo=UTC).timestamp() * 1000)
        self.history({"role": "user", "content": "cancel", "timestamp": notice_ms - 60000},         # before the notice
                     {"role": "assistant", "content": [{"type": "text", "text": "cancel"}], "timestamp": notice_ms + 1000},
                     {"role": "user", "content": [{"type": "text", "text": "Please CANCEL it"}], "timestamp": notice_ms + 120000})
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "cancelled")
        self.assertEqual(self.sent()[-1], [CLIENT_CHAT, au.CANCEL_ACK_TEXT])
        self.assertEqual(au.CANCEL_ACK_TEXT, "OK, I skipped this update. I'll try again at the next scheduled time.")
        self.assertEqual(self.beacon()["result"], "CANCELLED")
        self.at("2026-11-17T07:50:00Z")                                  # past any start time: still no run
        self.assertEqual(au.tick(self.root), "idle")
        self.assertFalse(marker.exists())
        self.assertEqual(len(self.sent()), 2)                            # one notice, one ack, nothing else
        self.at("2026-11-20T07:15:00Z")                                  # Friday: cancel was THIS run only
        self.assertEqual(au.tick(self.root), "notice")

    def test_cancel_needs_the_whole_word_and_a_user_message_after_the_notice(self):
        self.at(self.TUE_0215)
        au.tick(self.root)
        t = int(dt.datetime(2026, 11, 17, 7, 16, tzinfo=UTC).timestamp() * 1000)
        self.history({"role": "user", "content": "I cancelled my order yesterday", "timestamp": t},
                     {"role": "user", "content": "uncancel", "timestamp": t},
                     {"role": "assistant", "content": "cancel", "timestamp": t})
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "watch")

    def test_cancel_flag_file_also_cancels(self):
        self.at(self.TUE_0215)
        au.tick(self.root)
        (self.skills / ".auto-update-cancel").write_text("")
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "cancelled")

    def test_run_starts_at_2_30_plus_jitter_and_only_once(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        self.at(self.TUE_0215)
        au.tick(self.root)
        start = au.eastern_to_utc(au.run_start_local("test-box", dt.datetime(2026, 11, 17, 2, 0)))
        self.at((start - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(au.tick(self.root), "watch")
        self.assertFalse(marker.exists())
        runner = self.root / "scripts" / "auto-update-run.sh"
        runner.parent.mkdir(exist_ok=True)
        for f in ("auto-update-run.sh", "auto_update.py", "box-update-lock.sh"):
            (runner.parent / f).write_bytes((REPO / "scripts" / f).read_bytes())
        runner.chmod(0o755)
        os.environ["OPENCLAW_UPDATE_LEASE"] = str(self.tmp / "update.lock")
        self.at(start.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(au.tick(self.root), "run")
        self.assertTrue(marker.exists())
        self.assertEqual(self.beacon()["result"], "UPDATED")
        self.assertTrue(self.beacon()["notice_sent"])
        self.at((start + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(au.tick(self.root), "idle")                    # never a second run the same day

    def test_a_box_that_missed_the_notice_window_does_not_update_unannounced(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        self.at("2026-11-17T08:10:00Z")                                  # 3:10 AM, never noticed
        self.assertEqual(au.tick(self.root), "missed_notice")
        self.assertFalse(marker.exists())
        b = self.beacon()
        self.assertEqual((b["result"], b["failing_check"]), ("DEFERRED", "missed notice window"))

    def test_run_that_never_started_by_5_30_is_deferred(self):
        self.at(self.TUE_0215)
        au.tick(self.root)
        self.at("2026-11-17T10:31:00Z")                                  # 5:31 AM
        self.assertEqual(au.tick(self.root), "missed_run")
        self.assertEqual(self.beacon()["failing_check"], "missed run window")

    def test_one_tick_at_a_time(self):
        import fcntl
        g = open(self.skills / ".auto-update-tick.flock", "a+")
        fcntl.flock(g, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.at(self.TUE_0215)
        self.assertEqual(au.tick(self.root), "busy")
        g.close()


# ───────────────────────────────────────────────────────────────── the lock ──

class Lock(BoxCase):
    def run_sh(self, lock: Path, wait="2"):
        scripts = self.root / "scripts"
        scripts.mkdir(exist_ok=True)
        for f in ("auto-update-run.sh", "auto_update.py", "box-update-lock.sh"):
            (scripts / f).write_bytes((REPO / "scripts" / f).read_bytes())
        (scripts / "auto-update-run.sh").chmod(0o755)
        env = {**os.environ, "OPENCLAW_UPDATE_LEASE": str(lock), "AUTO_UPDATE_LOCK_WAIT_SECONDS": wait,
               "AUTO_UPDATE_LOCK_POLL_SECONDS": "1", "AUTO_UPDATE_DAY": "2026-11-17"}
        return subprocess.run(["bash", str(scripts / "auto-update-run.sh")], env=env, capture_output=True, text=True,
                              timeout=60)

    def test_busy_lock_is_waited_on_then_recorded_deferred_and_nothing_changes(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        lock = self.tmp / "update.lock"
        holder = subprocess.Popen(["bash", "-c", f'. "{REPO}/scripts/box-update-lock.sh"; '
                                   f'box_update_lock_acquire "{lock}" operator-roll fleet-roll /x; sleep 30'])
        try:
            for _ in range(50):
                if lock.exists() and lock.stat().st_size:
                    break
                subprocess.run(["sleep", "0.1"])
            r = self.run_sh(lock, wait="2")
        finally:
            holder.kill()
            holder.wait()
        self.assertEqual(r.returncode, 75, r.stdout + r.stderr)
        self.assertFalse(marker.exists())
        b = self.beacon()
        self.assertEqual(b["result"], "DEFERRED")
        self.assertIn("lock", b["failing_check"])

    def test_free_lock_is_taken_by_the_run_and_released_after(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        lock = self.tmp / "update.lock"
        r = self.run_sh(lock)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(marker.exists())
        self.assertFalse(lock.exists(), "the run must release the shared lease")
        self.assertEqual(self.beacon()["result"], "UPDATED")

    def test_the_update_command_inherits_the_lease_instead_of_fighting_it(self):
        lock = self.tmp / "update.lock"
        probe = self.tmp / "inherit.txt"
        executable(self.root / "scripts" / "weekly-full-update.sh", f'''#!/bin/bash
. "{REPO}/scripts/box-update-lock.sh"
box_update_lock_acquire "{lock}" child child /x; echo "rc=$?" > "{probe}"
''')
        self.set_latest(onboarding="v1.0.1")
        self.run_sh(lock)
        self.assertEqual(probe.read_text().strip(), "rc=0")


# ─────────────────────────────────────────── install: idempotent, retires old ──

class Install(BoxCase):
    OLD = ("# client's own job\n30 4 * * 1 /usr/local/bin/their-backup.sh\n"
           f"0 3 * * 0 {os.sep}home{os.sep}x/.openclaw/skills/.update-restart-if-needed\n"
           "59 23 * * 6 /home/x/.openclaw/skills/.openclaw-self-update\n")

    def seed(self):
        (self.stub / "crontab.txt").write_text(self.OLD)
        (self.skills / ".update-restart-if-needed").write_text("old")
        (self.skills / ".openclaw-self-update").write_text("old")
        (self.stub / "cronlist.json").write_text(json.dumps({"jobs": [
            {"id": "j-old-ask", "name": "weekly-onboarding-update"}, {"id": "j-old-cmd", "name": "weekly-onboarding-update"},
            {"id": "j-mine", "name": "clients-own-job"}]}))

    def crontab(self):
        return (self.stub / "crontab.txt").read_text()

    def test_old_crontab_lines_go_with_the_new_tick_and_old_jobs_wait_for_the_first_tick(self):
        self.seed()
        r = au.install(self.root, REPO / "scripts")
        ct = self.crontab()
        self.assertNotIn("update-restart-if-needed", ct)
        self.assertNotIn("openclaw-self-update", ct)
        self.assertIn("their-backup.sh", ct)
        self.assertEqual(ct.count("# openclaw-auto-update"), 1)
        self.assertIn(f"*/5 * * * * /bin/bash '{self.root}/scripts/auto-update-tick.sh'", ct)
        self.assertEqual(sorted(r["old_files_removed"]), [".openclaw-self-update", ".update-restart-if-needed"])
        # the working old openclaw jobs are NOT removed until a tick has proven the new schedule fires
        self.assertEqual(r["cron_jobs_removed"], [])
        self.assertFalse((self.stub / "cron-rm.log").exists())
        self.assertTrue(r["retire_pending"])
        for f in au.DELIVERED:
            self.assertTrue((self.root / "scripts" / f).is_file(), f)
        # the first tick (heartbeat) is the proof: now, and only now, the old jobs are retired
        self.at("2026-11-18T12:00:00Z")                      # Wednesday: the tick has nothing else to do
        au.tick(self.root)
        self.assertEqual(sorted((self.stub / "cron-rm.log").read_text().split()), ["j-old-ask", "j-old-cmd"])

    def test_failed_crontab_write_keeps_the_old_schedule_and_fails_loudly(self):
        self.seed()
        # a crontab whose write fails: -l works, "-" exits non-zero and leaves the file alone
        executable(self.stub / "bin" / "crontab", '''#!/bin/bash
F="$STUB_DIR/crontab.txt"
case "$1" in -l) cat "$F" ;; -) cat >/dev/null; exit 1 ;; esac
''')
        r = au.install(self.root, REPO / "scripts")
        self.assertIn("error", r)
        self.assertEqual(self.crontab(), self.OLD)
        self.assertTrue((self.skills / ".update-restart-if-needed").exists())
        self.assertFalse((self.stub / "cron-rm.log").exists())
        self.assertEqual(au.main(["install"]), 1)

    def test_a_write_that_cannot_be_read_back_restores_the_previous_crontab(self):
        self.seed()
        executable(self.stub / "bin" / "crontab", '''#!/bin/bash
F="$STUB_DIR/crontab.txt"
case "$1" in -l) cat "$F" ;; -) cat > "$STUB_DIR/crontab.written"; [ -f "$STUB_DIR/restored" ] || { touch "$STUB_DIR/restored"; exit 0; }; cp "$STUB_DIR/crontab.written" "$F" ;; esac
''')
        r = au.install(self.root, REPO / "scripts")        # first write "succeeds" but nothing changed: unverifiable
        self.assertIn("error", r)
        self.assertEqual(self.crontab(), self.OLD)

    def test_no_daemon_and_job_creation_fails_keeps_every_old_entry_and_exits_nonzero(self):
        self.seed()
        (self.stub / "no-cron-daemon").write_text("")
        (self.stub / "cron-add-fails").write_text("")
        r = au.install(self.root, REPO / "scripts")
        self.assertEqual(r["scheduler"], "openclaw-cron")
        self.assertIn("error", r)
        self.assertEqual(r["cron_jobs_removed"], [])
        self.assertFalse((self.stub / "cron-rm.log").exists())
        self.assertEqual(self.crontab(), self.OLD)
        self.assertTrue((self.skills / ".update-restart-if-needed").exists())

    def test_setup_script_prints_ok_only_when_the_install_worked(self):
        self.seed()
        (self.stub / "no-cron-daemon").write_text("")
        (self.stub / "cron-add-fails").write_text("")
        r = subprocess.run(["bash", str(REPO / "scripts" / "setup-weekly-update.sh")], env=os.environ.copy(),
                           capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("[OK]", r.stdout)
        self.assertIn("left exactly as it was", r.stderr)

    def test_second_install_changes_nothing(self):
        self.seed()
        au.install(self.root, REPO / "scripts")
        before = self.crontab()
        baks = sorted(self.skills.glob(".crontab.bak-auto-update-*"))
        r = au.install(self.root, REPO / "scripts")
        self.assertEqual(self.crontab(), before)
        self.assertEqual((r["crontab_changed"], r["scripts_changed"], r["old_files_removed"]), (False, [], []))
        self.assertEqual(sorted(self.skills.glob(".crontab.bak-auto-update-*")), baks)

    def test_dry_run_changes_nothing(self):
        self.seed()
        au.install(self.root, REPO / "scripts", dry_run=True)
        self.assertEqual(self.crontab(), self.OLD)
        self.assertTrue((self.skills / ".update-restart-if-needed").exists())
        self.assertFalse((self.stub / "cron-rm.log").exists())

    def test_a_crontab_binary_with_no_running_daemon_uses_the_openclaw_job(self):
        self.seed()
        (self.stub / "no-cron-daemon").write_text("")          # crontab exists, nothing running (container, gateway is PID 1)
        r = au.install(self.root, REPO / "scripts")
        self.assertEqual((r["scheduler"], r["tick_job"]), ("openclaw-cron", "created"))
        add = (self.stub / "cron-add.log").read_text()
        self.assertIn("--name auto-update-tick", add)
        self.assertIn("*/5 * * * *", add)
        self.assertIn("auto-update-tick.sh", add)
        # the tick job exists and was verified, so the old jobs are retired now
        self.assertEqual(sorted(r["cron_jobs_removed"]), ["j-old-ask", "j-old-cmd"])

    def test_macos_cron_is_fine_without_a_daemon_process_check(self):
        os.environ["AUTO_UPDATE_PLATFORM"] = "darwin"
        (self.stub / "no-cron-daemon").write_text("")
        self.assertTrue(au.cron_daemon_running())
        os.environ["AUTO_UPDATE_PLATFORM"] = "linux"
        self.assertFalse(au.cron_daemon_running())

    def test_tick_that_never_fires_falls_back_to_the_openclaw_job_after_15_minutes_then_retires_old(self):
        self.seed()
        self.at("2026-11-18T12:00:00Z")
        au.install(self.root, REPO / "scripts")
        self.assertEqual(au.selfcheck(self.root)["state"], "waiting-for-first-tick")
        self.assertFalse((self.stub / "cron-rm.log").exists())
        self.at("2026-11-18T12:16:00Z")                        # 16 minutes, no heartbeat
        out = au.selfcheck(self.root)
        self.assertEqual((out["state"], out["tick_job"]), ("fallback-to-openclaw-cron", "created"))
        self.assertEqual(sorted(out["retired"]), ["j-old-ask", "j-old-cmd"])

    def test_a_tick_that_fired_proves_the_schedule_and_no_fallback_is_made(self):
        self.seed()
        self.at("2026-11-18T12:00:00Z")
        au.install(self.root, REPO / "scripts")
        self.at("2026-11-18T12:30:00Z")
        au.tick(self.root)                                      # heartbeat
        self.assertEqual(au.selfcheck(self.root)["state"], "proven")
        self.assertFalse((self.stub / "cron-add.log").exists())

    def test_setup_script_end_to_end_in_the_sandbox(self):
        self.seed()
        for _ in range(2):
            r = subprocess.run(["bash", str(REPO / "scripts" / "setup-weekly-update.sh")], env=os.environ.copy(),
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.crontab().count("# openclaw-auto-update"), 1)
        self.assertIn("Tuesday, Friday and Sunday", r.stdout)


# ─────────────────────────────────────────────────── repair model chain ──

class ModelChain(unittest.TestCase):
    def resolver(self, have):
        def r(provider):
            return (["k-" + provider] if provider in have else []), f"https://{provider}.invalid/v1/chat/completions", {}
        return r

    def test_chain_order_is_ollama_cloud_then_openrouter_then_deepseek_direct(self):
        root = Path(tempfile.mkdtemp())
        chain = rep.provider_chain(root, self.resolver({"ollama-cloud", "openrouter", "deepseek-direct"}))
        self.assertEqual([s["provider"] for s in chain], ["ollama-cloud", "openrouter", "deepseek-direct"])
        self.assertEqual(chain[2]["model"], "deepseek-v4-flash")

    def test_only_providers_the_box_already_has_a_key_for_are_available(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual([s["provider"] for s in rep.provider_chain(root, self.resolver({"deepseek-direct"}))],
                         ["deepseek-direct"])
        self.assertEqual(rep.provider_chain(root, self.resolver(set())), [])

    def test_a_broken_resolver_is_unavailable_not_fatal(self):
        def boom(provider):
            raise RuntimeError("x")
        self.assertEqual(rep.provider_chain(Path(tempfile.mkdtemp()), boom), [])

    def test_the_boxs_own_latest_flash_model_id_wins_over_the_default(self):
        root = Path(tempfile.mkdtemp())
        (root / "openclaw.json").write_text(json.dumps({"models": {"providers": {"or": {
            "baseUrl": "https://openrouter.ai/api/v1",
            "models": [{"id": "deepseek/deepseek-v4-flash"}, {"id": "deepseek/deepseek-v4.1-flash"},
                       {"id": "deepseek/deepseek-v4.1-pro"}, {"id": "other/model"}]}}}}))
        self.assertEqual(rep.configured_flash_model(root, "openrouter.ai"), "deepseek/deepseek-v4.1-flash")
        chain = rep.provider_chain(root, self.resolver({"openrouter"}))
        self.assertEqual(chain[0]["model"], "deepseek/deepseek-v4.1-flash")

    def test_falls_through_errors_and_garbage_to_the_next_provider(self):
        chain = [{"label": "ollama-cloud/a"}, {"label": "openrouter/b"}, {"label": "deepseek-direct/c"}]
        answers = {"ollama-cloud/a": RuntimeError("down"), "openrouter/b": "I think you should reboot",
                   "deepseek-direct/c": 'Sure: {"actions": ["restart-gateway"]}'}

        def call(step, prompt):
            a = answers[step["label"]]
            if isinstance(a, Exception):
                raise a
            return a
        plan = rep.plan_actions({"gateway-health": "down"}, [], chain, call)
        self.assertEqual((plan["model"], plan["actions"]), ("deepseek-direct/c", ["restart-gateway"]))

    def test_the_model_can_only_pick_from_the_runners_own_actions(self):
        text = '{"actions": ["rm -rf /", "restart-gateway", "restart-gateway", "edit openclaw.json", "rebuild-cc", "rerun:pull-cc", "rerun:restart-cc"]}'
        self.assertEqual(rep.parse_actions(text), ["restart-gateway", "rebuild-cc", "rerun:pull-cc"])
        self.assertEqual(rep.parse_actions("no json here"), [])
        self.assertEqual(rep.parse_actions('{"actions": "restart-gateway"}'), [])

    def test_all_providers_failing_returns_no_actions_and_a_reason(self):
        plan = rep.plan_actions({}, [], [{"label": "x/y"}], lambda s, p: (_ for _ in ()).throw(OSError("net")))
        self.assertEqual((plan["model"], plan["actions"]), (None, []))
        self.assertIn("x/y", plan["error"])

    def test_secrets_are_scrubbed_from_what_the_model_sees(self):
        p = rep._prompt({"telegram-getme": "token 123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA failed"}, [])
        self.assertNotIn("AAAAAAAAAAAAAAAA", p)


# ─────────────────────────────────── runner hooks: repair agent, rollback ──

def _load_roll_safety():
    spec = importlib.util.spec_from_file_location("roll_safety", REPO / "tests" / "unit" / "fleet-refresh-roll-safety.test.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RunnerRepairAndRollback(unittest.TestCase):
    CLEAN = {"persona-index": {"status": "pass", "detail": ""}}

    def setUp(self):
        self.rs = _load_roll_safety()
        self.fr = self.rs.fr
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.box = self.rs.Box(Path(self._td.name))
        self.res = self.fr.BoxResult("t", dry_run=False)
        self.res.steps.update({"pull-onboarding": "ok", "pull-cc": "ok", "build-cc": "ok", "restart-cc": "ok"})
        for p in (mock.patch.object(self.fr, "_resolve_ceo_session_key", return_value=None),
                  mock.patch.dict(os.environ, {"AUTO_UPDATE_REPAIR": "1"})):
            p.start()
            self.addCleanup(p.stop)
        self.assertTrue(self.fr.take_snapshot(self.box.paths, self.box.onb, self.res))
        self.box.apply_release_b()
        self.actions = []

    def gate(self, posts, chain, plans):
        seq = list(posts)
        plans = list(plans)

        def probe(paths, res=None):
            if res is None:
                return self.rs.health()
            return seq.pop(0) if len(seq) > 1 else seq[0]

        def action(act, paths, repo_root, res, ctx):
            self.actions.append(act)
            return "ok"
        ctx = {"pinned": "vB", "cc_tag": "v0", "force_cc": False, "host_restart": False}
        with mock.patch.object(self.fr, "probe_health", side_effect=probe), \
             mock.patch.object(self.fr, "probe_integrity", return_value=self.CLEAN), \
             mock.patch.object(self.fr, "_run_heal_action", side_effect=action), \
             mock.patch.object(rep, "provider_chain", return_value=chain), \
             mock.patch.object(rep, "plan_actions", side_effect=lambda *a, **k: plans.pop(0) if len(plans) > 1 else plans[0]):
            return self.fr.heal_and_gate(self.box.paths, self.box.onb, self.res, self.rs.health(), ctx)

    def test_repair_agent_gets_three_attempts_after_the_mechanical_ones_then_rollback(self):
        plan = {"model": "ollama-cloud/m", "actions": ["rebuild-cc"], "error": None}
        self.gate([self.rs.health(cc_health="fail")], [{"label": "ollama-cloud/m"}], [plan])
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        ra = self.res.heal["repair_agent"]
        self.assertEqual((ra["attempts"], ra["model"], ra["no_model"]), (3, "ollama-cloud/m", False))
        self.assertEqual(self.rs.git(self.box.onb, "rev-parse", "HEAD"), self.box.onb_a)       # back on the old version
        self.assertEqual((self.box.skills / ".onboarding-version").read_text(), "vA")
        self.assertTrue(self.res.rollback["health_restored"])                                  # and WORKING

    def test_repair_agent_that_fixes_it_keeps_the_update_and_names_its_model(self):
        plan = {"model": "openrouter/m", "actions": ["rebuild-cc"], "error": None}
        # 3 mechanical attempts see the failure; the repair agent's first attempt is followed by a healthy gate
        posts = [self.rs.health(cc_health="fail")] * 4 + [self.rs.health()]
        self.gate(posts, [{"label": "openrouter/m"}], [plan])
        self.assertEqual(self.res.rollback, {})
        self.assertTrue(self.res.steps["health-gate"].startswith("ok:healed by the repair agent (openrouter/m)"))
        self.assertEqual(self.res.heal["repair_agent"]["attempts"], 1)

    def test_no_provider_means_no_repair_and_a_clean_rollback(self):
        self.gate([self.rs.health(cc_health="fail")], [], [{}])
        self.assertEqual(self.res.outcome, "ROLLED_BACK")
        self.assertTrue(self.res.heal["repair_agent"]["no_model"])
        self.assertEqual(self.res.heal["repair_agent"]["attempts"], 0)
        self.assertEqual(self.rs.git(self.box.onb, "rev-parse", "HEAD"), self.box.onb_a)

    def test_without_the_auto_update_switch_the_fleet_roll_is_unchanged(self):
        with mock.patch.dict(os.environ, {"AUTO_UPDATE_REPAIR": "0"}):
            self.gate([self.rs.health(cc_health="fail")], [{"label": "x"}], [{"model": "x", "actions": [], "error": None}])
        self.assertNotIn("repair_agent", self.res.heal)
        self.assertEqual(self.res.outcome, "ROLLED_BACK")

    def test_repos_that_are_current_are_skipped_by_the_runner(self):
        with mock.patch.dict(os.environ, {"AUTO_UPDATE_BEHIND": "onboarding"}):
            self.assertTrue(self.fr._auto_repo_current("command_center"))
            self.assertTrue(self.fr._auto_repo_current("999"))
            self.assertFalse(self.fr._auto_repo_current("onboarding"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTO_UPDATE_BEHIND", None)
            self.assertFalse(self.fr._auto_repo_current("command_center"))     # fleet roll: nothing skipped


class QcFixes(BoxCase):
    TUE = "2026-11-17T07:15:00Z"

    def history_for(self, name, *msgs):
        (self.stub / name).write_text(json.dumps({"messages": list(msgs)}))

    # 5: a notice that could not be delivered to a chat that WAS found means no 2:30 run
    def test_failed_notice_to_a_found_chat_is_retried_then_never_runs_unannounced(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        (self.stub / "send-fails").write_text("")
        self.at(self.TUE)
        au.tick(self.root)
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "notice")                       # retried, not treated as sent
        (self.stub / "send-fails").unlink()
        self.at("2026-11-17T07:25:00Z")
        self.assertEqual(au.tick(self.root), "notice")                       # delivered on the retry
        self.assertEqual(len(self.sent()), 1)

    def test_notice_never_delivered_means_deferred_not_run(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        (self.stub / "send-fails").write_text("")
        for iso in ("07:15", "07:20", "07:25"):
            self.at(f"2026-11-17T{iso}:00Z")
            au.tick(self.root)
        self.at("2026-11-17T07:45:00Z")
        self.assertEqual(au.tick(self.root), "missed_notice")
        self.assertFalse(marker.exists())
        self.assertIn("could not be delivered", self.beacon()["failing_check"])
        self.assertEqual(self.beacon()["result"], "DEFERRED")

    # 7: cancel only from the owner's chat
    def test_cancel_from_someone_else_who_can_talk_to_the_agent_is_ignored(self):
        (self.stub / "sessions.json").write_text(json.dumps({"sessions": [
            {"key": f"agent:main:telegram:direct:{CLIENT_CHAT}", "updatedAt": 1},
            {"key": "agent:main:telegram:direct:999", "updatedAt": 2}]}))
        t = int(dt.datetime(2026, 11, 17, 7, 16, tzinfo=UTC).timestamp() * 1000)
        self.history_for("history-999.json", {"role": "user", "content": "cancel", "timestamp": t})
        self.history_for("history.json")
        self.at(self.TUE)
        au.tick(self.root)
        self.at("2026-11-17T07:20:00Z")
        self.assertEqual(au.tick(self.root), "watch")
        self.history_for("history.json", {"role": "user", "content": "cancel", "timestamp": t})
        self.at("2026-11-17T07:21:00Z")
        self.assertEqual(au.tick(self.root), "cancelled")

    def test_no_dm_session_for_the_owner_means_nothing_can_cancel(self):
        (self.stub / "sessions.json").write_text(json.dumps({"sessions": [
            {"key": "agent:main:telegram:direct:999", "updatedAt": 2}]}))
        self.assertEqual(au.owner_session_keys(self.root, CLIENT_CHAT), [])
        self.assertEqual(au.owner_session_keys(self.root, "999"), ["agent:main:telegram:direct:999"])

    # 6 / 9 / 10
    def run_with(self, **kw):
        self.install_update_stub(**kw)
        self.set_latest(onboarding="v1.0.1")
        return au.run_update(self.root, "d", "r", True)

    def test_999_failure_is_not_reported_updated(self):
        b = self.run_with(steps={"update-999": "failed:auto-update-mac.sh exit 69: skills-only-failed"})
        self.assertEqual(b["result"], "FAILED")
        self.assertIn("999", b["failing_check"])

    def test_999_deferred_is_not_reported_updated(self):
        b = self.run_with(steps={"update-999": "skip:DEFERRED: another updater held the lock; 999 not changed"})
        self.assertEqual(b["result"], "DEFERRED")

    def test_999_not_applicable_skip_is_still_updated(self):
        self.assertEqual(self.run_with(steps={"update-999": "skip:999 not installed"})["result"], "UPDATED")

    def test_openclaw_cli_failure_is_not_reported_updated(self):
        b = self.run_with(steps={"openclaw-update": "failed:exit 1: boom"})
        self.assertEqual(b["result"], "FAILED")
        self.assertIn("OpenClaw", b["failing_check"])

    def test_container_gateway_restart_request_is_updated_with_restart_pending(self):
        b = self.run_with(rc=0, outcome="PENDING")
        self.assertEqual(b["result"], "UPDATED")
        self.assertIn("restart-pending", b["failing_check"])

    def test_openclaw_cli_updates_on_its_own_check_when_no_repo_is_behind(self):
        marker = self.install_update_stub()
        self.set_latest(openclaw="v2026.12.0")                     # installed (stub) is 2026.11.3
        b = au.run_update(self.root, "d", "r", True)
        self.assertEqual(marker.read_text().strip(), "behind=openclaw repair=1 oc=1")
        self.assertEqual(b["versions"]["openclaw"]["before"], "v2026.11.3")

    def test_current_openclaw_does_not_trigger_a_run(self):
        marker = self.install_update_stub()
        self.set_latest(openclaw="v2026.11.3")
        self.assertEqual(au.run_update(self.root, "d", "r", True)["result"], "CURRENT")
        self.assertFalse(marker.exists())

    # 11a: kills the RUNNING-marker mutant
    def test_a_tick_that_dies_mid_run_is_reported_failed_and_never_re_runs(self):
        marker = self.install_update_stub()
        self.set_latest(onboarding="v1.0.1")
        self.at(self.TUE)
        au.tick(self.root)
        start = au.eastern_to_utc(au.run_start_local("test-box", dt.datetime(2026, 11, 17, 2, 0)))
        self.at((start + dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        real = au.subprocess.run
        def boom(cmd, *a, **k):
            if cmd and cmd[0] == "bash" and "auto-update-run.sh" in " ".join(cmd):
                raise KeyboardInterrupt("killed mid-run")
            return real(cmd, *a, **k)
        with mock.patch.object(au.subprocess, "run", boom), self.assertRaises(KeyboardInterrupt):
            au.tick(self.root)
        self.assertEqual(json.loads((self.skills / ".auto-update-state.json").read_text())["settled"], "RUNNING")
        self.at((start + dt.timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(au.tick(self.root), "crashed")
        self.assertEqual(self.beacon()["result"], "FAILED")
        self.assertIn("did not finish", self.beacon()["failing_check"])
        self.assertFalse(marker.exists())
        self.at((start + dt.timedelta(minutes=11)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual(au.tick(self.root), "idle")

    # DST: the notice must say the real start time; one notice per day through both transitions
    def test_spring_forward_sunday_notice_says_3_30_and_nothing_fires_in_the_missing_hour(self):
        self.assertIn("(3:30 AM)", au.notice_text(dt.date(2026, 3, 8)))
        self.assertIn("(2:30 AM)", au.notice_text(dt.date(2026, 3, 15)))
        self.assertIn("(2:30 AM)", au.notice_text(dt.date(2026, 11, 1)))
        t = dt.datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
        while t < dt.datetime(2026, 3, 8, 14, 0, tzinfo=UTC):
            self.at(t.strftime("%Y-%m-%dT%H:%M:%SZ"))
            au.tick(self.root)
            t += dt.timedelta(minutes=5)
        texts = [m for _, m in self.sent()]
        self.assertEqual(len(texts), 1)
        self.assertIn("(3:30 AM)", texts[0])
        st = json.loads((self.skills / ".auto-update-state.json").read_text())
        sent_local = au.to_eastern(dt.datetime.fromtimestamp(st["notice"]["at_ms"] / 1000, tz=UTC))
        self.assertEqual((sent_local.hour, sent_local.minute // 5 * 5), (3, 15))

    def test_fall_back_sunday_gets_exactly_one_notice_at_2_15_and_the_text_says_2_30(self):
        t = dt.datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
        while t < dt.datetime(2026, 11, 1, 13, 0, tzinfo=UTC):
            self.at(t.strftime("%Y-%m-%dT%H:%M:%SZ"))
            au.tick(self.root)
            t += dt.timedelta(minutes=5)
        self.assertEqual(len(self.sent()), 1)
        self.assertIn("(2:30 AM)", self.sent()[0][1])
        st = json.loads((self.skills / ".auto-update-state.json").read_text())
        self.assertEqual(au.to_eastern(dt.datetime.fromtimestamp(st["notice"]["at_ms"] / 1000, tz=UTC)).strftime("%H:%M")[:4], "02:1")

    # migration: the old Sunday path installs the schedule after the notice window
    def test_a_box_migrated_by_the_old_sunday_run_is_labeled_migration_not_a_problem(self):
        self.at("2026-11-22T08:00:00Z")                                      # Sunday 3:00 AM, old path installing
        au.install(self.root, REPO / "scripts")
        self.at("2026-11-22T08:10:00Z")
        self.assertEqual(au.tick(self.root), "missed_notice")
        b = self.beacon()
        self.assertTrue(b["migration"])
        self.assertTrue(b["failing_check"].startswith("MIGRATION"))

    def test_a_box_that_simply_slept_through_the_window_is_not_labeled_migration(self):
        self.at("2026-11-20T12:00:00Z")
        au.install(self.root, REPO / "scripts")                              # installed days earlier
        self.at("2026-11-22T08:10:00Z")
        au.tick(self.root)
        self.assertNotIn("migration", self.beacon())
        self.assertEqual(self.beacon()["failing_check"], "missed notice window")


class Update999OwnUpdater(unittest.TestCase):
    """The runner hands 999 to the 999 repo's own updater (scripts/auto-update-mac.sh) during an auto-update."""

    def run_step(self, body, rc):
        import fleet_refresh_runner as fr
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "999-setup"
            (repo / "scripts").mkdir(parents=True)
            script = executable(repo / "scripts" / "auto-update-mac.sh", f"#!/bin/bash\n{body}\nexit {rc}\n")
            res = fr.BoxResult("t", dry_run=False)
            res.update_999 = {"path": str(repo)}
            fr._step_update_999_own(repo, script, res, False)
            return res

    def test_updated_is_ok_and_carries_the_versions(self):
        res = self.run_step('echo "AUTO-UPDATE-999 result=UPDATED before=v1.38.0 after=v1.39.0 latest=v1.39.0 rc=0 reason=-"', 0)
        self.assertEqual(res.steps["update-999"], "ok")
        self.assertEqual((res.update_999["before"], res.update_999["after"]), ("v1.38.0", "v1.39.0"))

    def test_not_a_mac_or_no_checkout_is_a_skip_not_a_failure(self):
        for rc in (64, 65):
            res = self.run_step('echo "AUTO-UPDATE-999 result=REFUSED before=- after=- latest=- rc=%d reason=not-macos"' % rc, rc)
            self.assertTrue(res.steps["update-999"].startswith("skip:"), res.steps)

    def test_busy_lock_is_a_deferral_and_a_real_failure_is_a_failure(self):
        self.assertIn("DEFERRED", self.run_step("echo AUTO-UPDATE-999 result=DEFERRED", 75).steps["update-999"])
        res = self.run_step('echo "AUTO-UPDATE-999 result=FAILED before=v1 after=v1 latest=v2 rc=69 reason=skills-only-failed"', 69)
        self.assertTrue(res.steps["update-999"].startswith("failed:"))
        self.assertIn("skills-only-failed", res.steps["update-999"])


# ─────────────────────────────────────────────────────────── wiring guards ──

class Wiring(unittest.TestCase):
    def test_nothing_registers_the_ask_first_job_any_more(self):
        us = (REPO / "update-skills.sh").read_text()
        inst = (REPO / "install.sh").read_text()
        lib = (REPO / "shared-utils" / "cron-lib.sh").read_text()
        self.assertNotIn("oc_box_update_cron_ensure", us + inst)
        self.assertNotIn("def oc_box_update_cron_ensure", lib)
        self.assertNotIn("oc_box_update_cron_ensure()", lib)
        for text in (us, inst):
            self.assertNotIn('_oc_cron_silent_main "weekly-onboarding-update"', text)
            self.assertNotIn("refresh_weekly_cron_message ", text)
        self.assertIn("setup-weekly-update.sh", us)
        self.assertIn("setup-weekly-update.sh", inst)

    def test_old_crons_are_not_written_by_the_setup_script_any_more(self):
        setup = (REPO / "scripts" / "setup-weekly-update.sh").read_text()
        self.assertNotIn("0 3 * * 0", setup.replace("# ", "").split("Usage:")[1])
        self.assertNotIn("59 23 * * 6", setup.split("Usage:")[1])

    def test_openclaw_cli_update_script_is_the_moved_saturday_script(self):
        s = (REPO / "scripts" / "openclaw-cli-update.sh").read_text()
        self.assertIn("oc-atomic-upgrade.sh", s)
        self.assertNotIn("sat-cron", s)

    def test_shell_syntax(self):
        for f in ("auto-update-tick.sh", "auto-update-run.sh", "setup-weekly-update.sh", "openclaw-cli-update.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", str(REPO / "scripts" / f)]).returncode, 0, f)
        self.assertEqual(subprocess.run(["bash", "-n", str(REPO / "update-skills.sh")]).returncode, 0)

    def test_no_em_dashes_in_the_new_files(self):
        for f in ("scripts/auto_update.py", "scripts/auto-update-tick.sh", "scripts/auto-update-run.sh",
                  "scripts/setup-weekly-update.sh", "shared-utils/auto_update_repair.py"):
            self.assertNotIn("\u2014", (REPO / f).read_text(), f)


if __name__ == "__main__":
    unittest.main(verbosity=1)
