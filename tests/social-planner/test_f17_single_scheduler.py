#!/usr/bin/env python3
"""F17 — Choose one scheduler and retire incompatible legacy paths.

QC-F17 matrix (unittest, NO network):
  1. Install/upgrade twice with BOTH legacy triggers present: exactly one
     engine owner + one future schedule per company; no duplicate invitation.
  2. Both cron scripts are forwarding adapters: their prompts contain NO
     multi-hour wait and NO noon/6PM fallback instructions; the durable
     cycle service owns the cadence.
  3. Restart after upgrade produces no duplicate invitation (durable
     ownership record survives; legacy names are superseded).
  4. Legacy sheet layout: the versioned-schema contract is documented as
     superseded in the n8n export README (no silent Sheet1 tab reads).

Run:  python3 -m unittest tests.social-planner.test_f17_single_scheduler -v
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SERVICE_PATH = _REPO_ROOT / "shared-utils" / "social_cycle_service.py"
_SCRIPT_35 = _REPO_ROOT / "35-social-media-planner" / "scripts" / "register-weekly-cron.sh"
_SCRIPT_57 = _REPO_ROOT / "57-social-media-in-a-box" / "scripts" / "register-social-cron.sh"
_N8N_README = _REPO_ROOT / "35-social-media-planner" / "config" / "n8n" / "README.md"
assert _SERVICE_PATH.is_file() and _SCRIPT_35.is_file() and _SCRIPT_57.is_file()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scs = _load("social_cycle_service_f17", _SERVICE_PATH)


def _env():
    d = tempfile.mkdtemp()
    return {"SOCIAL_CYCLE_STATE_DIR": d}


class TestF17SingleScheduler(unittest.TestCase):
    def test_install_twice_with_both_legacy_triggers_yields_one_owner(self):
        env = _env()
        # "Install twice" with both legacy paths present: the durable engine
        # claims ownership, then each LEGACY trigger claims in turn — the
        # durable engine's claim always wins (legacy claims demote only
        # non-active rows of OTHER engines and are themselves demoted by the
        # durable claim re-asserting).
        r1 = scs.claim_engine_ownership("co-f17", engine="cc-cycle-service", env=env)
        self.assertTrue(r1["claimed"])
        r2 = scs.claim_engine_ownership("co-f17", engine="skill35-weekly-theme",
                                        scheduler_name="openclaw-cron", env=env)
        self.assertTrue(r2["claimed"])
        r3 = scs.claim_engine_ownership("co-f17", engine="social-media-weekly-theme",
                                        scheduler_name="openclaw-cron", env=env)
        self.assertTrue(r3["claimed"])
        # The durable engine re-asserts (the tick's ownership stamp does this)
        # and stamps the future next_run_at.
        r4 = scs.claim_engine_ownership("co-f17", engine="cc-cycle-service",
                                        next_run_at="2030-01-01T00:00:00Z", env=env)
        v = scs.verify_engine_ownership(env)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["companies"], 1)
        self.assertEqual(v["active_owners"], 1, v)
        self.assertEqual(v["superseded"], 2, v)  # both legacy names superseded

        # Exactly one active owner with a future next_run_at.
        with open(Path(env["SOCIAL_CYCLE_STATE_DIR"]) / "engine-ownership.json") as fh:
            rows = json.load(fh)["rows"]
        active = [r for r in rows if r["state"] == "active"]
        self.assertEqual(len(active), 1)
        self.assertTrue(active[0]["next_run_at"], "one future schedule required")

    def test_restart_produces_no_duplicate_invitation(self):
        env = _env()
        sent = []
        # "Install" (claim) then invite; restart (fresh module) then claim
        # again + advance: still exactly one invitation for the week.
        t = 1788696000000
        scs.claim_engine_ownership("co-r17", env=env)
        ws = scs.week_start_local(t, "America/New_York")
        scs.advance_cycle("co-r", t, send=lambda p: sent.append(p) or True, env=env)
        fresh = _load("social_cycle_service_f17_restart", _SERVICE_PATH)
        fresh.claim_engine_ownership("co-r", env=env)
        fresh.advance_cycle("co-r", t + 3 * 3600_000, send=lambda p: sent.append(p) or True, env=env)
        invites = [p for p in sent if p.get("week_start") == ws]
        self.assertEqual(len(invites), 1, "restart must not duplicate the invitation")
        v = fresh.verify_engine_ownership(env)
        self.assertTrue(v["ok"], v)

    def test_cron_prompts_contain_no_cadence_prose(self):
        # F07's defect was the cadence living in the prompt. Both adapters'
        # CRON_MESSAGE must NOT contain the noon/6PM fallback ladder or any
        # "wait up to" instruction; the durable service owns the timing.
        s35 = _SCRIPT_35.read_text(encoding="utf-8")
        s57 = _SCRIPT_57.read_text(encoding="utf-8")
        banned = ["Wait up to 1 hour", "12:00 PM", "6:00 PM", "ask once more"]
        for name, text in (("skill35", s35), ("skill57", s57)):
            for phrase in banned:
                self.assertNotIn(phrase, text, f"{name} still carries legacy cadence prose: {phrase}")
        # And both must name the durable service / forwarding-adapter posture.
        self.assertIn("forwarding adapter", s35)
        self.assertIn("forwarding adapter", s57)
        self.assertIn("durable cycle service", s35)
        self.assertIn("durable cycle service", s57)

    def test_verify_paths_exist_on_both_adapters(self):
        # --verify is the F17 forwarding-adapter check; both scripts expose it
        # and honor SOCIAL_CYCLE_STATE_DIR.
        for path in (_SCRIPT_35, _SCRIPT_57):
            text = path.read_text(encoding="utf-8")
            self.assertIn("--verify", text)
        # Run both against an empty state dir: exit 5 (not claimed yet) —
        # never a crash.
        empty = tempfile.mkdtemp()
        for path in (_SCRIPT_35, _SCRIPT_57):
            r = subprocess.run(
                ["bash", str(path), "--verify"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "SOCIAL_CYCLE_STATE_DIR": empty},
            )
            self.assertEqual(r.returncode, 5, f"{path.name}: {r.stderr}")
        # With a healthy record: exit 0.
        own = Path(empty) / "engine-ownership.json"
        own.write_text(json.dumps({"rows": [{
            "id": "o1", "company_id": "co-x", "engine": "cc-cycle-service",
            "state": "active", "next_run_at": "2030-01-01T00:00:00Z",
        }]}), encoding="utf-8")
        for path in (_SCRIPT_35, _SCRIPT_57):
            r = subprocess.run(
                ["bash", str(path), "--verify"],
                capture_output=True, text=True,
                env={**__import__("os").environ, "SOCIAL_CYCLE_STATE_DIR": empty},
            )
            self.assertEqual(r.returncode, 0, f"{path.name}: {r.stderr}")
            self.assertIn("ok=True", r.stdout + r.stderr)

    def test_n8n_weekly_theme_trigger_documented_superseded(self):
        # The n8n export README documents the supersession + versioned-schema
        # requirement (deployment-phase disable).
        text = _N8N_README.read_text(encoding="utf-8")
        self.assertIn("VXRfHv2UT6QbD7Sg", text, "the live trigger must be named")
        self.assertIn("SUPERSEDED", text)
        self.assertIn("schema_version", text, "versioned-schema requirement documented")
        self.assertIn("DEPLOYMENT-PHASE", text.upper())


if __name__ == "__main__":
    unittest.main()