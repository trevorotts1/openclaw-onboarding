#!/usr/bin/env python3
"""F18 repair round 1: Skill 57 path fails closed on credential conflict.

QC D-F18-01: preflight_gate._get_secret caught CredentialConflictError in a
broad `except Exception` and silently fell back to config-wins. These tests
reproduce the exact QC repro (cfg pit=config-pit-VALUE + env
GOHIGHLEVEL_API_KEY=env-pit-DIFFERENT) against the SHIPPED
57-social-media-in-a-box/scripts/preflight_gate.py and prove it now BLOCKS
with AF-SM-CRED-CONFLICT (values never printed), while the
resolver-absent fallback keeps its historical behavior.

Run:
    python3 -m unittest tests.social-planner.test_f18_skill57_conflict -v
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_GATE_PATH = (_REPO_ROOT / "57-social-media-in-a-box" / "scripts"
              / "preflight_gate.py")
assert _GATE_PATH.is_file(), f"preflight_gate.py not found at {_GATE_PATH}"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "preflight_gate_under_test", _GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["preflight_gate_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


pg = _load_gate()

CONFIG_PIT = "config-pit-VALUE"
ENV_PIT = "env-pit-DIFFERENT"


def _conflict_env(**overrides):
    """os.environ with the GHL PIT aliases stripped, then overridden."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GOHIGHLEVEL_API_KEY", "GHL_PRIVATE_INTEGRATION_TOKEN",
                        "GHL_API_KEY", "GHL_PIT", "HIGHLEVEL_API_KEY",
                        "HIGHLEVEL_TOKEN", "GHL_PRIVATE_TOKEN",
                        "CONVERTFLOW_API_KEY", "CONVERTANDFLOW_API_KEY",
                        "CONVERT_AND_FLOW_API_KEY", "CONVERTFLOW_PIT",
                        "CONVERTANDFLOW_PIT")}
    env.update(overrides)
    return env


def _ready_cfg():
    return {
        "brandName": "Brand One", "pit": CONFIG_PIT, "locationId": "loc123",
        "userId": "user123", "openrouterKey": "set",
        "openrouterModel": "google/gemini-2.0-flash-001",
        "openrouterFallbacks": ["meta-llama/llama-3.1-70b",
                                "mistralai/mistral-large"],
        "kieKey": "set", "geminiKey": "set", "platforms": ["facebook"],
        "postTypes": ["post"], "timezone": "America/New_York",
        "status": "Paid",
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0,
                   "ghlTokenValid": True,
                   "connectedAccounts": ["facebook"]},
    }


class TestSkill57ConflictFailsClosed(unittest.TestCase):
    """Exact QC repro: config pit + different env PIT must BLOCK."""

    def test_get_secret_surfaces_conflict(self):
        with mock.patch.dict(os.environ, _conflict_env(
                GOHIGHLEVEL_API_KEY=ENV_PIT), clear=True):
            with self.assertRaises(pg._CredentialConflict) as ctx:
                pg._get_secret({"pit": CONFIG_PIT}, "pit", "GHL_API_KEY")
        message = str(ctx.exception)
        self.assertNotIn(CONFIG_PIT, message)
        self.assertNotIn(ENV_PIT, message)
        self.assertIn("GOHIGHLEVEL_API_KEY", message)

    def test_evaluate_live_blocked_with_conflict_code(self):
        with mock.patch.dict(os.environ, _conflict_env(
                GOHIGHLEVEL_API_KEY=ENV_PIT), clear=True):
            with mock.patch.object(
                    pg, "_http_get_json",
                    side_effect=AssertionError("no network in unit test")):
                fails = pg.evaluate(_ready_cfg(), live=True)
        codes = [c for c, _ in fails]
        self.assertIn("AF-SM-CRED-CONFLICT", codes)
        self.assertEqual(pg.decide_exit(fails), pg.EXIT_AUTOFAIL)
        joined = " ".join(m for _, m in fails)
        self.assertNotIn(CONFIG_PIT, joined)
        self.assertNotIn(ENV_PIT, joined)

    def test_resolver_absent_fallback_intact(self):
        """ImportError (no shared-utils) keeps historical config-then-env."""
        import builtins
        _real_import = builtins.__import__

        def _no_resolver(name, *args, **kwargs):
            if name == "social_planner_credentials":
                raise ImportError("No module named social_planner_credentials "
                                  "(absent fallback test)")
            return _real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=_no_resolver):
            self.assertEqual(
                pg._get_secret({"pit": CONFIG_PIT}, "pit", "GHL_API_KEY"),
                CONFIG_PIT)
            with mock.patch.dict(os.environ, _conflict_env(
                    GOHIGHLEVEL_API_KEY=ENV_PIT, GHL_API_KEY=ENV_PIT),
                    clear=True):
                self.assertEqual(
                    pg._get_secret({}, "pit", "GHL_API_KEY"), ENV_PIT)


if __name__ == "__main__":
    unittest.main()
