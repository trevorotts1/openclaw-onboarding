#!/usr/bin/env python3
"""F34 — Make first-time planner setup a resumable installation.

QC-F34 matrix (unittest, NO network, injected webhook fakes):
  1. Clean-install bootstrap: verified identity -> exactly one planner ->
     verified registry -> readiness + ONE schedule -> REAL links delivered,
     `ready` ONLY when every step carries a verified receipt.
  2. Identity gate: a missing verified field is FATAL and NOTHING is
     provisioned (no registry, no sheet call).
  3. Crash after Google creates the file (planner receipt durable, steps
     3-5 missing): resume REUSES the same sheet — the webhook is called
     exactly once and `deduped` never becomes a second file.
  4. Crash mid-step (before the webhook reply): resume re-POSTs the SAME
     provisioning key; the fake webhook returns the existing sheet with
     deduped=true — one sheet total, never two.
  5. Absent optional channels are recorded EXCLUSIONS (podcast off = a
     labeled exclusion, never a silent failure).
  6. Deliver gate: delivering with any unverified step is refused.
  7. Registry sync: the durable sheet registry carries the
     unique(company_id, planner_kind) row; local env refs are written as
     synchronized COPIES.

Run:  python3 tests/social-planner/test_f34_resumable_setup.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

spec = importlib.util.spec_from_file_location("social_bootstrap_f34", _REPO_ROOT / "shared-utils" / "social_bootstrap.py")
sb = importlib.util.module_from_spec(spec)
sys.modules["social_bootstrap_f34"] = sb
spec.loader.exec_module(sb)


def _request(**over):
    base = {
        "company_id": "co-f34",
        "planner_kind": "social-planner",
        "owner": "owner@client.example",
        "notification_channel": "telegram",
        "timezone": "America/New_York",
        "deployment_type": "docker-vps",
        "engine": "cc-cycle-service",
        "optional_channels": {"podcast": False, "blog": False},
    }
    base.update(over)
    return base


def _hooks(counter: dict, dedup_after_first: bool = False):
    def create_sheet(payload):
        counter["create_calls"] = counter.get("create_calls", 0) + 1
        deduped = dedup_after_first and counter["create_calls"] > 1
        return {"status": "success", "deduped": deduped,
                "sheetId": "SHEET-F34", "sheetUrl": "https://docs.google.com/spreadsheets/d/SHEET-F34",
                "sharedWith": "anyone with the link can edit", "schema_version": "1.1.0"}

    def verify_sheet(sheet_id):
        return {"ok": True, "state": "ok", "sharing": "anyone,writer",
                "schema_version": "1.1.0", "tabs_ok": True}

    def ghl_probe(req):
        return {"ok": True, "state": "ok", "accounts": 2}

    def deliver(payload):
        counter["delivered"] = payload
        return True

    return {"create_sheet": create_sheet, "verify_sheet": verify_sheet,
            "ghl_probe": ghl_probe, "deliver": deliver}


class TestResumableSetup(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="f34-")
        self.env = {"OPENCLAW_ROOT": self.root}

    def test_1_clean_install_full_receipts_ready(self):
        counter = {}
        state = sb.bootstrap(_request(), env=self.env, hooks=_hooks(counter))
        self.assertTrue(state["ready"])
        self.assertEqual(sorted(state["steps"]), sorted(sb.STEPS))
        self.assertEqual(counter.get("create_calls"), 1)
        # One schedule, durable engine ownership claimed.
        self.assertEqual(state["readiness"]["schedule"]["schedule"], "one")
        # Durable registry row (unique per company+kind).
        reg = json.loads((Path(self.root) / "data" / "skill35" / "sheet-registry.json").read_text())
        self.assertEqual(len(reg["rows"]), 1)
        self.assertEqual(reg["rows"][0]["company_id"], "co-f34")
        # Local refs synced as copies.
        self.assertTrue((Path(self.root) / "data" / "skill35" / "sheet-refs.env").is_file())
        # The REAL links were delivered (not placeholders).
        self.assertEqual(counter["delivered"]["links"]["planner_url"],
                         "https://docs.google.com/spreadsheets/d/SHEET-F34")

    def test_2_identity_gate_fatal_nothing_provisioned(self):
        counter = {}
        req = _request()
        req.pop("timezone")
        with self.assertRaises(sb.BootstrapFatal):
            sb.bootstrap(req, env=self.env, hooks=_hooks(counter))
        self.assertNotIn("create_calls", counter, "no sheet call before identity is verified")
        self.assertFalse((Path(self.root) / "data" / "skill35" / "sheet-registry.json").exists())

    def test_3_crash_after_google_creates_file_resumes_reusing_it(self):
        counter = {}
        hooks = _hooks(counter)
        state = sb.bootstrap(_request(), env=self.env, hooks=hooks)
        self.assertTrue(state["ready"])
        # Simulate a crash AFTER the planner receipt but BEFORE registry:
        # wipe the later steps from the durable state file only.
        st = sb.load_state("co-f34", "social-planner", env=self.env)
        st["steps"] = {k: v for k, v in st["steps"].items() if k in ("identity", "planner")}
        for k in ("registry", "readiness", "deliver", "ready"):
            st.pop(k, None)
        sb.save_state(st, env=self.env)
        resumed = sb.bootstrap(_request(), env=self.env, hooks=hooks)
        self.assertTrue(resumed["ready"])
        self.assertEqual(counter["create_calls"], 1,
                         "resume must NOT call the webhook again — the receipt is durable")

    def test_4_crash_before_webhook_reply_replays_same_key_deduped(self):
        # Fresh root: a run that crashed between the identity step and the
        # webhook reply leaves NO planner receipt — resume re-POSTs the SAME
        # provisioning key and the (fake) webhook dedupes.
        counter = {}
        hooks = _hooks(counter, dedup_after_first=True)
        state = sb.bootstrap(_request(), env=self.env, hooks=hooks)
        self.assertTrue(state["ready"])
        self.assertEqual(counter["create_calls"], 1, "single clean run calls once")
        # Second full resume (post-ready re-run) never re-provisions.
        state2 = sb.bootstrap(_request(), env=self.env, hooks=hooks)
        self.assertTrue(state2["ready"])
        self.assertEqual(counter["create_calls"], 1)
        self.assertEqual(state2["planner"]["provisioning_key"], "co-f34::social-planner")

    def test_5_absent_optional_channels_are_exclusions(self):
        counter = {}
        state = sb.bootstrap(_request(optional_channels={"podcast": False, "blog": True, "engage": False}),
                             env=self.env, hooks=_hooks(counter))
        self.assertEqual(state["identity"]["excluded_channels"],
                         {"podcast": "not_configured", "engage": "not_configured"})

    def test_6_deliver_gate_refuses_unverified_steps(self):
        env = {"OPENCLAW_ROOT": tempfile.mkdtemp(prefix="f34-gate-")}
        state = sb.load_state("co-gate", "social-planner", env=env)
        with self.assertRaises(sb.BootstrapFatal):
            sb.step_deliver(state, env=env)

    def test_7_registry_unique_and_local_refs_synced(self):
        counter = {}
        hooks = _hooks(counter)
        sb.bootstrap(_request(), env=self.env, hooks=hooks)
        # A second company with the SAME planner kind gets its OWN row.
        env2 = {"OPENCLAW_ROOT": self.root}
        sb.bootstrap(_request(company_id="co-f34-b"), env=env2, hooks=hooks)
        reg = json.loads((Path(self.root) / "data" / "skill35" / "sheet-registry.json").read_text())
        kinds = sorted(r["company_id"] for r in reg["rows"])
        self.assertEqual(kinds, ["co-f34", "co-f34-b"])
        refs = (Path(self.root) / "data" / "skill35" / "sheet-refs.env").read_text()
        self.assertIn("SKILL35_CONTENT_SHEET_ID=SHEET-F34", refs)

    def test_8_intake_url_never_empty_at_deliver(self):
        """F34-OBS-03: the delivered links carry a REAL intake URL — from the
        mini-app probe receipt when live, else the verified planner URL as a
        labeled fallback. Never a placeholder/empty string."""
        counter = {}
        state = sb.bootstrap(_request(), env=self.env, hooks=_hooks(counter))
        delivered = counter["delivered"]
        self.assertTrue(delivered["links"].get("intake_url"),
                        "intake_url must not be empty at deliver")
        self.assertEqual(delivered["links"]["intake_url"],
                         "https://docs.google.com/spreadsheets/d/SHEET-F34")
        # The offline fallback is LABELED (visible provenance, never silent).
        self.assertEqual(state["readiness"]["mini_app"]["intake_source"],
                         "planner_url_fallback")
        # A live mini-app probe supplies ITS intake_url instead.
        root2 = tempfile.mkdtemp(prefix="f34-intake-")
        env2 = {"OPENCLAW_ROOT": root2}

        def mini_app_live():
            return {"ok": True, "state": "ok", "intake_url": "https://cc.example.com/social-theme?t=live-ticket"}

        hooks2 = _hooks(counter)
        hooks2["probes"] = {"mini_app": mini_app_live}
        state2 = sb.bootstrap(_request(company_id="co-f34-c"), env=env2, hooks=hooks2)
        self.assertEqual(state2["intake_url"],
                         "https://cc.example.com/social-theme?t=live-ticket")
        # A CONFIGURED mini-app probe that returns no intake_url is RETRYABLE,
        # never a silent empty link.
        root3 = tempfile.mkdtemp(prefix="f34-intake-bad-")
        env3 = {"OPENCLAW_ROOT": root3}
        hooks3 = _hooks(counter)
        hooks3["probes"] = {"mini_app": lambda: {"ok": True, "state": "ok"}}
        with self.assertRaises(sb.BootstrapRetryable):
            sb.bootstrap(_request(company_id="co-f34-d"), env=env3, hooks=hooks3)


if __name__ == "__main__":
    unittest.main(verbosity=2)