#!/usr/bin/env python3
"""F06 — per-account plan tests (unittest, parameterized, no network).

Contract: discovered_account.json (per-account plan; no platform-level
collapse; unfamiliar labels allowed with declared capabilities).

Proves:
  * Facebook posts when Instagram is absent (one platform's absence never
    blocks the run — healthy accounts proceed).
  * Two Facebook accounts retain SEPARATE results (IDs preserved).
  * A previously UNKNOWN platform label with declared capabilities plans fine.
  * Every account removed/expired in turn -> that account degrades
    (needs_reconnect/failed/skipped), all other enabled healthy accounts stay
    ready.
  * No podcast/blog/email dependency blocks unrelated social output.
  * platformsExcluded entries stay excluded (never silently re-enabled).
  * Connected-but-unconfigured channels are WARNING-level per-account rows,
    never a global block.
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "57-social-media-in-a-box" / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pg = _load("preflight_gate")


def _cfg(platforms=("facebook", "instagram"), accounts=None, **extra):
    cfg = {
        "brandName": "Brand One", "pit": "pit-set", "locationId": "loc123", "userId": "user123",
        "openrouterKey": "set", "openrouterModel": "google/gemini-2.0-flash-001",
        "openrouterFallbacks": ["meta-llama/llama-3.1-70b", "mistralai/mistral-large"],
        "kieKey": "set", "geminiKey": "set", "platforms": list(platforms),
        "postTypes": ["post"], "timezone": "America/New_York", "status": "Paid",
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0, "ghlTokenValid": True},
    }
    if accounts is not None:
        cfg["probes"]["connectedAccounts"] = accounts
    cfg.update(extra)
    return cfg


def _accounts(rows):
    return [{"account_id": a, "platform": p, "account_name": n} for a, p, n in rows]


class TestAccountPlanShapes(unittest.TestCase):
    """Parameterized over discovered account IDs incl. multiple accounts per
    platform and one unfamiliar platform label."""

    def _plan(self, cfg, accounts):
        fails, summary = pg.reconcile_connected_accounts(cfg, accounts)
        return summary

    def test_two_facebook_accounts_separate_rows(self):
        summary = self._plan(_cfg(platforms=["facebook"]), _accounts([
            ("fb-1", "facebook", "Main FB"), ("fb-2", "facebook", "Second FB")]))
        rows = summary["accounts"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["account_id"] for r in rows), ["fb-1", "fb-2"])
        self.assertEqual(summary["ready_accounts"], ["fb-1", "fb-2"])
        for r in rows:
            self.assertEqual(r["health"], "ready")
            self.assertIn("post", r["supported_formats"])

    def test_instagram_absent_facebook_proceeds_no_block(self):
        cfg = _cfg(platforms=["facebook", "instagram"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        fails = pg.evaluate(cfg, live=False)
        self.assertEqual(fails, [])  # the run is NOT blocked
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(summary["ready_accounts"], ["fb-1"])
        self.assertEqual(summary["unmet_configured_platforms"], ["instagram"])  # reported, not blocking

    def test_unfamiliar_platform_label_with_declared_capabilities(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]) + [
                       {"account_id": "zz-1", "platform": "fizzle", "account_name": "Fizzle",
                        "capabilities": ["fizzle-blast", "fizzle-echo"]}])
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        zz = [r for r in summary["accounts"] if r["account_id"] == "zz-1"][0]
        # connected-but-unconfigured: a WARNING row, not a block; capabilities carried as formats
        self.assertEqual(zz["health"], "skipped")
        self.assertIn("unconfigured", (zz["exclusion_reason"] or ""))
        self.assertIn("fizzle-blast", zz["supported_formats"])

    def test_unfamiliar_label_when_enabled_plans_ready(self):
        cfg = _cfg(platforms=["facebook", "fizzle"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]) + [
                       {"account_id": "zz-1", "platform": "fizzle", "account_name": "Fizzle",
                        "capabilities": ["fizzle-blast"]}])
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        zz = [r for r in summary["accounts"] if r["account_id"] == "zz-1"][0]
        self.assertEqual(zz["health"], "ready")
        self.assertEqual(zz["supported_formats"], ["fizzle-blast"])


class TestPerAccountDegrade(unittest.TestCase):
    """QC-F06: remove/expire each account in turn; the others still execute."""

    def _all_ready(self, accounts):
        cfg = _cfg(platforms=["facebook", "instagram"], accounts=_accounts(accounts))
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(summary["ready_accounts"], [a[0] for a in accounts])
        self.assertEqual(pg.evaluate(cfg, live=False), [])

    def test_each_account_removed_in_turn(self):
        # remove fb-1
        cfg = _cfg(platforms=["facebook", "instagram"],
                   accounts=_accounts([("fb-2", "facebook", "Second FB"),
                                       ("ig-1", "instagram", "Main IG")]))
        fails, summary = pg.reconcile_connected_accounts(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(fails, [])
        self.assertEqual(summary["ready_accounts"], ["fb-2", "ig-1"])
        self.assertEqual(summary["unmet_configured_platforms"], [])  # fb-2 still covers facebook
        # remove ig-1
        cfg = _cfg(platforms=["facebook", "instagram"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB"),
                                       ("fb-2", "facebook", "Second FB")]))
        fails, summary = pg.reconcile_connected_accounts(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(fails, [])
        self.assertEqual(summary["ready_accounts"], ["fb-1", "fb-2"])
        self.assertEqual(summary["unmet_configured_platforms"], ["instagram"])

    def test_expired_account_marks_only_itself(self):
        cfg = _cfg(platforms=["facebook", "instagram"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB"),
                                       ("ig-1", "instagram", "Main IG")]))
        cfg["probes"]["accountHealth"] = {"ig-1": "needs_reconnect"}
        fails = pg.evaluate(cfg, live=False)
        self.assertEqual(fails, [])  # one expired account never blocks the run
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        by_id = {r["account_id"]: r for r in summary["accounts"]}
        self.assertEqual(by_id["ig-1"]["health"], "needs_reconnect")
        self.assertEqual(by_id["fb-1"]["health"], "ready")

    def test_disconnected_account_state_is_not_ready(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        cfg["probes"]["accountHealth"] = {"fb-1": "failed"}
        _rows, summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(summary["ready_accounts"], [])
        self.assertEqual(summary["unmet_configured_platforms"], ["facebook"])


class TestNoCrossDependencyBlocks(unittest.TestCase):
    """No podcast/blog/email dependency blocks unrelated social output."""

    def test_podcast_unconfigured_does_not_block_social(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        cfg["podcast"] = False  # fold off: never required
        self.assertEqual(pg.evaluate(cfg, live=False), [])

    def test_no_fold_toggles_run_social_only(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        for k in ("newsletter", "blog", "engage", "podcast"):
            cfg.pop(k, None)
        self.assertEqual(pg.evaluate(cfg, live=False), [])


class TestExclusionsAndWarnings(unittest.TestCase):
    def test_excluded_channels_stay_excluded(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB"),
                                       ("x-1", "twitter", "Brand X")]),
                   platformsExcluded=["twitter"])
        fails, summary = pg.reconcile_connected_accounts(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(fails, [])
        x = [r for r in summary["accounts"] if r["account_id"] == "x-1"][0]
        self.assertEqual(x["health"], "skipped")
        self.assertIn("platformsExcluded", x["exclusion_reason"])
        # excluded platforms are never re-enabled into the enabled set
        self.assertNotIn("twitter", summary["enabled_platforms"])

    def test_connected_but_unconfigured_is_warning_not_block(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB"),
                                       ("x-1", "twitter", "Brand X")]))
        self.assertEqual(pg.evaluate(cfg, live=False), [])  # no block
        fails, summary = pg.reconcile_connected_accounts(cfg, cfg["probes"]["connectedAccounts"])
        self.assertEqual(fails, [])
        x = [r for r in summary["accounts"] if r["account_id"] == "x-1"][0]
        self.assertEqual(x["health"], "skipped")
        self.assertIn("unconfigured", (x["exclusion_reason"] or ""))
        # surfaced as a visible warning in the summary
        self.assertTrue(any("twitter" in w or "x-1" in w for w in summary["warnings"]))

    def test_report_shape_carries_account_plan(self):
        import tempfile, os
        cfg = _cfg(platforms=["facebook"], accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        with tempfile.TemporaryDirectory() as td:
            report = os.path.join(td, "report.json")
            pg._write_report(report, cfg, [])
            rec = json.loads(Path(report).read_text(encoding="utf-8"))
            self.assertTrue(rec["account_plan"]["per_account"])
            self.assertEqual(rec["account_plan"]["ready_accounts"], ["fb-1"])
            # back-compat platform mirror present
            self.assertIn("facebook", rec["connected_accounts"]["live_connected"])

    def test_contract_fields_match_discovered_account_json(self):
        cfg = _cfg(platforms=["facebook"],
                   accounts=_accounts([("fb-1", "facebook", "Main FB")]))
        rows, _summary = pg.build_account_plan(cfg, cfg["probes"]["connectedAccounts"])
        row = rows[0]
        for field in ("account_id", "platform", "account_name", "capabilities", "health",
                      "supported_formats"):
            self.assertIn(field, row)
        self.assertIn(row["health"], ("ready", "skipped", "needs_reconnect", "retrying", "failed"))


if __name__ == "__main__":
    unittest.main()