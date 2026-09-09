#!/usr/bin/env python3
"""F07 — Make weekly invitations restart every week.

QC-F07 matrix (unittest, NO network, fake clock):
  1. Four unanswered local weeks: each new week gets EXACTLY ONE invitation,
     bounded reminders (never more than MAX_REMINDERS), and a visible
     disposition at cutoff.
  2. DST change (America/New_York, Nov 1 2026): the local week boundary
     shifts with the zone, and the cycle key stays unique per local week.
  3. Service restart (fresh module state, same files): no duplicate
     invitation for the same week; the state survives.
  4. Late reply: a theme answer arriving after cutoff records on ITS OWN
     cycle — never overwrites another week, never creates duplicate posts.
  5. Skip-this-week closes only that cycle; next week still gets an
     invitation.
  6. Pause-reminders is an explicit preference and stops reminders without
     consuming anything else.
  7. Evergreen publishing requires a recorded standing approval; without it
     the outcome is a draft + the ask repeats next week.

Run:  python3 -m unittest tests.social-planner.test_f07_cycle_service -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SERVICE_PATH = _REPO_ROOT / "shared-utils" / "social_cycle_service.py"
assert _SERVICE_PATH.is_file(), _SERVICE_PATH


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scs = _load("social_cycle_service_f07", _SERVICE_PATH)


def _env():
    d = tempfile.mkdtemp()
    return {"SOCIAL_CYCLE_STATE_DIR": d}


# Fake clock: 2026-09-06 is a Sunday (a local week start), 12:00 UTC.
T_W1 = 1788696000000  # 2026-09-06T12:00:00Z (Sunday)
HOUR = 3600 * 1000
DAY = 24 * HOUR


class Recorder:
    """Records every send; optionally fails deliveries."""

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def __call__(self, payload):
        if self.fail:
            return False
        self.sent.append(payload)
        return True


class TestF07CycleService(unittest.TestCase):
    def test_four_unanswered_weeks_one_invitation_each_bounded_reminders(self):
        env = _env()
        rec = Recorder()
        # Week 1 starts 2026-09-06 (Sunday) local NY.
        t = 1788696000000
        weeks = []
        for i in range(4):
            ws = scs.week_start_local(t, "America/New_York")
            weeks.append(ws)
            r = scs.advance_cycle("co-a", t, send=rec, env=env)
            self.assertEqual(r["action"], "invite", f"week {i}: {r}")
            # A second advance in the same week NEVER re-invites.
            r2 = scs.advance_cycle("co-a", t + 5 * 60_000, send=rec, env=env)
            self.assertIn(r2["action"], ("none", "retry"), r2)
            # Reminders: fire every cadence tick up to the bound.
            invites_before = len(rec.sent)
            for k in range(10):
                scs.send_due_reminder(
                    "co-a", ws, rec,
                    now_ms=t + (8 + k * 8) * HOUR,
                    env=env)
            # Only invitation (1) + bounded reminders per week.
            week_msgs = len([p for p in rec.sent if p.get("week_start") == ws])
            self.assertEqual(
                week_msgs, 1 + scs.MAX_REMINDERS,
                f"week {i}: {week_msgs} messages (want 1 invitation + {scs.MAX_REMINDERS} reminders)")
            # Cutoff disposition is visible. For i >= 1 the successor's lead
            # time has already arrived, so the same advance may legitimately
            # roll next_cycle instead — either way the prior week must end
            # with a visible disposition.
            cutoff_r = scs.advance_cycle("co-a", t + 36 * HOUR, send=rec, env=env)
            self.assertIn(cutoff_r["action"], ("cutoff", "next_cycle"), cutoff_r)
            cyc_after = scs.get_cycle("co-a", ws, env=env)
            self.assertEqual(cyc_after["state"], "closed", cyc_after["state"])
            self.assertTrue(cyc_after["disposition"], "a visible disposition is required")
            self.assertIn("draft", cyc_after["disposition"], "no standing approval -> draft + ask again")
            t += 7 * DAY

        self.assertEqual(len(set(weeks)), 4, "four distinct local weeks")
        # One invitation per company/week across all four weeks.
        self.assertEqual(len(rec.sent), 4 * (1 + scs.MAX_REMINDERS))

    def test_dst_change_week_boundary_stays_local(self):
        env = _env()
        rec = Recorder()
        # America/New_York: DST ends 2026-11-01 (EDT -> EST). The Sunday
        # BEFORE (Oct 25) and AFTER (Nov 1) are distinct local weeks; the
        # boundary computed through the zone must not drift a day.
        t_before = 1792929600000  # 2026-10-25T12:00:00Z (Sunday, before the DST end)
        ws_before = scs.week_start_local(t_before, "America/New_York")
        self.assertEqual(ws_before, "2026-10-25", ws_before)
        t_after = t_before + 7 * DAY
        ws_after = scs.week_start_local(t_after, "America/New_York")
        self.assertEqual(ws_after, "2026-11-01", ws_after)
        # Cross the DST instant itself (Nov 1, 05:00Z is 1AM EDT -> 1AM EST):
        t_instant = t_after + 5 * HOUR
        self.assertEqual(scs.week_start_local(t_instant, "America/New_York"), ws_after)
        # Cycles on both sides are distinct and each gets its own invitation.
        r1 = scs.advance_cycle("co-dst", t_before, send=rec, env=env)
        r2 = scs.advance_cycle("co-dst", t_after, send=rec, env=env)
        self.assertEqual(r1["action"], "invite")
        self.assertEqual(r2["action"], "invite")
        c1 = scs.get_cycle("co-dst", ws_before, env=env)
        c2 = scs.get_cycle("co-dst", ws_after, env=env)
        self.assertNotEqual(c1["cycle_id"], c2["cycle_id"])

    def test_restart_no_duplicate_invitation(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws = scs.week_start_local(t, "America/New_York")
        r1 = scs.advance_cycle("co-r", t, send=rec, env=env)
        self.assertEqual(r1["action"], "invite")
        # "Restart": reload the module from scratch (fresh in-memory state) —
        # the DURABLE files must carry the state.
        fresh = _load("social_cycle_service_f07_restart", _SERVICE_PATH)
        r2 = fresh.advance_cycle("co-r", t + 3 * DAY, send=rec, env=env)
        self.assertIn(r2["action"], ("none", "cutoff"), r2)
        invites = [p for p in rec.sent if p.get("week_start") == ws]
        self.assertEqual(len(invites), 1, "restart must not re-invite the same week")

    def test_late_reply_never_overwrites_another_week(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws1 = scs.week_start_local(t, "America/New_York")
        r1 = scs.advance_cycle("co-l", t, send=rec, env=env)
        # Week 1 closes by cutoff.
        scs.advance_cycle("co-l", t + 36 * HOUR, send=rec, env=env)
        closed = scs.get_cycle("co-l", ws1, env=env)
        self.assertEqual(closed["state"], "closed")
        # Week 2 invited.
        t2 = t + 7 * DAY
        ws2 = scs.week_start_local(t2, "America/New_York")
        scs.advance_cycle("co-l", t2, send=rec, env=env)
        # LATE reply to week 1 (after its cutoff).
        late = scs.apply_response(closed["cycle_id"], {"kind": "theme", "theme": "Autumn"},
                                  now_ms=t2 + DAY, env=env)
        self.assertTrue(late["ok"], late)
        # Week 2's row is untouched.
        w2 = scs.get_cycle("co-l", ws2, env=env)
        self.assertEqual(w2["state"], "invited")
        self.assertIsNone(w2["selected_fallback"])
        # Week 1 records the late answer without reopening another week.
        w1 = scs.get_cycle("co-l", ws1, env=env)
        self.assertEqual(w1["disposition"], "late_theme_recorded")

    def test_skip_closes_only_that_week(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws1 = scs.week_start_local(t, "America/New_York")
        r = scs.advance_cycle("co-s", t, send=rec, env=env)
        cid = r["cycle_id"]
        rr = scs.apply_response(cid, {"kind": "skip"}, now_ms=t + HOUR, env=env)
        self.assertEqual(rr["effect"], "skipped_this_week_only")
        # Next week STILL gets an invitation (created independently).
        t2 = t + 7 * DAY
        ws2 = scs.week_start_local(t2, "America/New_York")
        r2 = scs.advance_cycle("co-s", t2, send=rec, env=env)
        self.assertEqual(r2["action"], "invite", "next week must be created after a skip")
        self.assertNotIn(r2["cycle_id"], (cid,))
        w1 = scs.get_cycle("co-s", ws1, env=env)
        self.assertEqual(w1["state"], "skipped")

    def test_pause_is_explicit_preference(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws = scs.week_start_local(t, "America/New_York")
        r = scs.advance_cycle("co-p", t, send=rec, env=env)
        cid = r["cycle_id"]
        # Silence does NOT pause: reminders still fire.
        rr = scs.send_due_reminder("co-p", ws, rec, now_ms=t + 9 * HOUR, env=env)
        self.assertEqual(rr["action"], "sent")
        # Explicit pause stops reminders.
        scs.apply_response(cid, {"kind": "pause", "until": None}, now_ms=t + 10 * HOUR, env=env)
        rr2 = scs.send_due_reminder("co-p", ws, rec, now_ms=t + 17 * HOUR, env=env)
        self.assertEqual(rr2["action"], "skip", rr2)
        self.assertEqual(rr2["reason"], "paused")

    def test_evergreen_requires_recorded_standing_approval(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws = scs.week_start_local(t, "America/New_York")
        r = scs.advance_cycle("co-e", t, send=rec, env=env)
        cid = r["cycle_id"]
        # No standing approval recorded: evergreen -> draft + ask again.
        rr = scs.apply_response(cid, {"kind": "evergreen"}, now_ms=t + HOUR, env=env)
        self.assertEqual(rr["effect"], "draft_awaiting_approval")
        w = scs.get_cycle("co-e", ws, env=env)
        self.assertEqual(w["disposition"], "draft_awaiting_approval")
        # Next week is still created (ask repeats).
        t2 = t + 7 * DAY
        r2 = scs.advance_cycle("co-e", t2, send=rec, env=env)
        self.assertEqual(r2["action"], "invite")
        # WITH a recorded standing approval: evergreen publishes.
        scs2 = scs
        ws2 = scs2.week_start_local(t2, "America/New_York")
        r3 = scs2.advance_cycle("co-e", t2, send=rec, env=env)
        cyc2 = scs2.get_cycle("co-e", ws2, env=env)
        with open(Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "co-e" / "cycles.json") as fh:
            data = json.load(fh)
        data[ws2]["standing_approval"] = "evergreen"
        with open(Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "co-e" / "cycles.json", "w") as fh:
            json.dump(data, fh)
        rr2 = scs2.apply_response(cyc2["cycle_id"], {"kind": "evergreen"}, now_ms=t2 + HOUR, env=env)
        self.assertEqual(rr2["effect"], "evergreen_published")

    def test_unique_company_week_one_invitation_per_week(self):
        env = _env()
        rec = Recorder()
        t = 1788696000000
        ws = scs.week_start_local(t, "America/New_York")
        # Two engines ensure+invite the same (company, week): collapse to ONE.
        a = scs.ensure_cycle("co-u", ws, env=env)
        b = scs.ensure_cycle("co-u", ws, env=env)
        self.assertEqual(a["cycle_id"], b["cycle_id"])
        self.assertFalse(b["created"])
        scs.send_invitation("co-u", ws, rec, now_ms=t, env=env)
        scs.send_invitation("co-u", ws, rec, now_ms=t + HOUR, env=env)
        week_msgs = [p for p in rec.sent if p.get("week_start") == ws]
        self.assertEqual(len(week_msgs), 1, "exactly one invitation per company/week")


if __name__ == "__main__":
    unittest.main()