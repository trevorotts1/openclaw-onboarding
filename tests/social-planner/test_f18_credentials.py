#!/usr/bin/env python3
"""
Unit tests for shared-utils/social_planner_credentials.py — F18 one documented
credential resolver for the social planner skills.

Proves the QC-F18 setup at the resolver layer:
  * explicit precedence: config field > canonical env name > Skill 44 resolver
  * conflicting values FAIL CLOSED: config vs env both set and DIFFERENT raises
    CredentialConflictError (the stale-config-key cross-client risk)
  * redacted diagnostics: the report and diagnose() output NEVER contain a
    credential value — source + status only
  * placeholder rejection: PASTE_REAL_TOKEN-shaped values never resolve
  * absent credential: status 'missing', value None, remedy named without keys
  * valid environment-only setup passes (env-only PIT + location resolve OK)

Run:
    python3 -m unittest tests.social-planner.test_f18_credentials -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent          # tests/social-planner/
_REPO_ROOT = _HERE.parent.parent                 # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"

sys.path.insert(0, str(_SHARED_UTILS))

import social_planner_credentials as sprc  # noqa: E402


def clean_env(**overrides):
    """An env mapping with the GHL canonical names stripped, then overridden."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GOHIGHLEVEL") and k not in ("GHL_API_KEY", "GHL_LOCATION_ID", "LOCATION_ID")}
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


class TestPrecedence(unittest.TestCase):
    def test_config_beats_env_when_both_agree(self):
        """Precedence applies to AGREED values; disagreement is the conflict error."""
        creds, report = sprc.resolve_planner_credentials(
            {"pit": "agreed-pit-value", "locationId": "agreed-loc-value"},
            env=clean_env(GOHIGHLEVEL_API_KEY="agreed-pit-value", GOHIGHLEVEL_LOCATION_ID="agreed-loc-value"),
        )
        self.assertEqual(creds["pit"], "agreed-pit-value")
        self.assertEqual(creds["location_id"], "agreed-loc-value")
        self.assertEqual(report["pit"]["source"], "config")
        self.assertEqual(report["location_id"]["source"], "config")

    def test_env_used_when_config_absent(self):
        creds, report = sprc.resolve_planner_credentials(
            {}, env=clean_env(GOHIGHLEVEL_API_KEY="env-pit-value-1", GOHIGHLEVEL_LOCATION_ID="env-loc-value-1"))
        self.assertEqual(creds["pit"], "env-pit-value-1")
        self.assertEqual(creds["location_id"], "env-loc-value-1")
        self.assertEqual(report["pit"]["source"], "env")

    def test_environment_only_setup_passes(self):
        """QC-F18: a valid environment-only setup passes."""
        creds, report = sprc.resolve_planner_credentials(
            {"brandName": "Brand"}, env=clean_env(
                GOHIGHLEVEL_API_KEY="real-pit-value-123", GOHIGHLEVEL_LOCATION_ID="loc-abcdef123"))
        self.assertEqual(creds["pit"], "real-pit-value-123")
        self.assertEqual(creds["location_id"], "loc-abcdef123")
        self.assertTrue(all(e["status"] == "ok" for e in report.values()))


class TestConflictFailsClosed(unittest.TestCase):
    def test_config_env_conflict_raises(self):
        """QC-F18: mismatched config/environment identities fail safely."""
        with self.assertRaises(sprc.CredentialConflictError):
            sprc.resolve_planner_credentials(
                {"pit": "config-pit-value"}, env=clean_env(GOHIGHLEVEL_API_KEY="env-pit-different"))

    def test_location_conflict_raises(self):
        with self.assertRaises(sprc.CredentialConflictError):
            sprc.resolve_planner_credentials(
                {"locationId": "loc-AAAA-1111"}, env=clean_env(GOHIGHLEVEL_LOCATION_ID="loc-BBBB-2222"))

    def test_conflict_error_never_carries_values(self):
        try:
            sprc.resolve_planner_credentials(
                {"pit": "config-pit-secret-value"}, env=clean_env(GOHIGHLEVEL_API_KEY="env-pit-secret-value"))
        except sprc.CredentialConflictError as exc:
            message = str(exc)
            self.assertNotIn("config-pit-secret-value", message)
            self.assertNotIn("env-pit-secret-value", message)
        else:
            self.fail("expected CredentialConflictError")


class TestRedaction(unittest.TestCase):
    def test_report_never_contains_values(self):
        _creds, report = sprc.resolve_planner_credentials(
            {"pit": "super-secret-pit-x", "locationId": "super-secret-loc-x"},
            env=clean_env())
        self.assertNotIn("super-secret-pit-x", repr(report))
        self.assertNotIn("super-secret-loc-x", repr(report))

    def test_diagnose_never_contains_values(self):
        creds, report = sprc.resolve_planner_credentials(
            {"pit": "diag-secret-pit-x", "locationId": None}, env=clean_env())
        lines = sprc.diagnose(report)
        joined = "\n".join(lines)
        self.assertNotIn("diag-secret-pit-x", joined)
        self.assertNotIn(str(creds.get("pit") or ""), joined)


class TestPlaceholderAndMissing(unittest.TestCase):
    def test_placeholder_rejected(self):
        creds, report = sprc.resolve_planner_credentials(
            {"pit": "PASTE_REAL_TOKEN"}, env=clean_env())
        self.assertIsNone(creds["pit"])
        self.assertEqual(report["pit"]["status"], "placeholder")

    def test_missing_credential_reports_remedy_without_keys(self):
        creds, report = sprc.resolve_planner_credentials({}, env=clean_env())
        self.assertIsNone(creds["pit"])
        self.assertIsNone(creds["location_id"])
        self.assertEqual(report["pit"]["status"], "missing")
        lines = sprc.diagnose(report)
        joined = "\n".join(lines)
        self.assertIn("GOHIGHLEVEL_API_KEY", joined, "remedy must name the canonical env var")
        self.assertIn("GOHIGHLEVEL_LOCATION_ID", joined)


class TestSkill44Tier(unittest.TestCase):
    def test_skill44_third_tier_used_when_config_env_empty(self):
        """Tier 3: Skill 44 canonical resolver resolves when tiers 1-2 are empty."""
        fake = type("M", (), {"resolve_key": staticmethod(
            lambda s: "skill44-pit-token-xyz" if s == "ghl" else "skill44-loc-id-xyz")})
        with patch.object(sprc, "_load_canon_resolver", return_value=fake), \
             patch.object(sprc, "_env_canonical", return_value=None):
            # Production path: env=None consults the canon + tier 3. Both tiers
            # 1-2 are stubbed empty here so the test is host-independent.
            creds, report = sprc.resolve_planner_credentials({}, env=None)
        self.assertEqual(creds["pit"], "skill44-pit-token-xyz")
        self.assertEqual(creds["location_id"], "skill44-loc-id-xyz")
        self.assertEqual(report["pit"]["source"], "skill44")

    def test_env_tier_precedes_skill44(self):
        """Tier 2 wins over tier 3 when the canonical env name resolves."""
        fake = type("M", (), {"resolve_key": staticmethod(lambda s: "skill44-pit-token-xyz")})
        with patch.object(sprc, "_load_canon_resolver", return_value=fake), \
             patch.object(sprc, "_env_canonical", return_value="env-tier-wins-123"):
            creds, report = sprc.resolve_planner_credentials({}, env=None)
        self.assertEqual(creds["pit"], "env-tier-wins-123")
        self.assertEqual(report["pit"]["source"], "env")


if __name__ == "__main__":
    unittest.main()