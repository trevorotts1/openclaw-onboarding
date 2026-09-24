#!/usr/bin/env python3
"""
tests/unit/test_credential_resolver.py — JEV-006 (spec 1.1, sections 3.3 + 3.8).

Proves client-scoped credential resolution:
  * company-scoped stores consulted BEFORE any unscoped store;
  * process env eligible ONLY when bound to requesting company or proven
    single-company installation; unscoped-on-shared never a fallback;
  * other-company stores skipped WITHOUT reading values;
  * empty / placeholder / malformed values rejected before any call;
  * presence means configured, never verified_working; spend/transmit
    permissions always False (3.8 — a credential answers neither question);
  * sanitized logs carry provider/source/state/error only, never values;
  * resolver is read-only and never touches os.environ.

Hermetic: stdlib only, no network, no filesystem, no real credentials.
Run:  python3 tests/unit/test_credential_resolver.py
      python3 -m pytest tests/unit/test_credential_resolver.py -q
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_RESOLVER_PATH = (
    _REPO_ROOT / "shared-utils" / "decision_engine" / "providers"
    / "credential_resolver.py"
)
assert _RESOLVER_PATH.is_file(), f"missing {_RESOLVER_PATH}"

_spec = importlib.util.spec_from_file_location(
    "jev_credential_resolver", _RESOLVER_PATH)
assert _spec is not None and _spec.loader is not None
cr = importlib.util.module_from_spec(_spec)
sys.modules["jev_credential_resolver"] = cr
_spec.loader.exec_module(cr)  # type: ignore

REAL_A = "sk-live-realvalueA1b2c3d4e5f6g7h8"
REAL_B = "sk-live-realvalueB9x8y7z6w5v4u3t2"


def scoped(company, values, category="company_file"):
    return {"source_category": category, "company_id": company,
            "values": dict(values)}


def unscoped(values, category="process_env"):
    return {"source_category": category, "company_id": None,
            "values": dict(values)}


class AccessCountingStore(dict):
    """Raises if 'values' is ever read: proves other-company skip is blind."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.values_reads = 0

    def get(self, key, default=None):
        if key == "values":
            self.values_reads += 1
            raise AssertionError("other-company store values were read")
        return super().get(key, default)


class TestScopeOrdering(unittest.TestCase):
    def test_company_scoped_beats_unscoped_even_when_listed_second(self):
        stores = [unscoped({cr.TYPESAFE_API_KEY: "unscoped-key-AAAABBBBCCCC"}),
                  scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A})]
        st = cr.resolve_provider_key(
            "direct", "acme", stores, {"single_company_installation": True})
        self.assertEqual(st.state, "configured")
        self.assertEqual(st.source_category, "company_file")
        self.assertTrue(st.configured)

    def test_unscoped_eligible_only_when_single_company_proven(self):
        stores = [unscoped({cr.TYPESAFE_API_KEY: REAL_A})]
        shared = cr.resolve_provider_key("direct", "acme", stores, {})
        self.assertEqual(shared.state, "rejected_unscoped")
        self.assertFalse(shared.configured)
        self.assertIn("unscoped_on_shared",
                      " ".join(shared.skipped_sources))
        proven = cr.resolve_provider_key(
            "direct", "acme", stores, {"single_company_installation": True})
        self.assertEqual(proven.state, "configured")

    def test_process_env_bound_to_company_is_scoped(self):
        stores = [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A},
                         category="process_env")]
        st = cr.resolve_provider_key("direct", "acme", stores, {})
        self.assertEqual(st.state, "configured")
        self.assertEqual(st.source_category, "process_env")

    def test_other_company_store_skipped_without_reading_values(self):
        other = AccessCountingStore(
            {"source_category": "company_file", "company_id": "globex",
             "values": {cr.TYPESAFE_API_KEY: REAL_B}})
        st = cr.resolve_provider_key("direct", "acme", [other], {})
        self.assertNotEqual(st.state, "configured")
        self.assertEqual(other.values_reads, 0)
        self.assertIn("other_company", " ".join(st.skipped_sources))

    def test_other_company_key_never_leaks_across(self):
        stores = [scoped("globex", {cr.TYPESAFE_API_KEY: REAL_B},
                         category="company_file")]
        st = cr.resolve_provider_key("direct", "acme", stores, {})
        self.assertFalse(st.configured)
        self.assertEqual(st.state, "absent")

    def test_file_env_cross_company(self):
        stores = [scoped("globex", {cr.OPENROUTER_API_KEY: REAL_B},
                         category="env_file")]
        st = cr.resolve_provider_key("openrouter", "acme", stores, {})
        self.assertFalse(st.configured)


class TestValueRejection(unittest.TestCase):
    @staticmethod
    def _state_for(value):
        return cr.resolve_provider_key(
            "direct", "acme", [scoped("acme", {cr.TYPESAFE_API_KEY: value})],
            {}).state

    def test_empty_rejected(self):
        for bad in ("", "   "):
            self.assertEqual(self._state_for(bad), "rejected_empty", repr(bad))

    def test_placeholder_rejected(self):
        for bad in ("PASTE_REAL_TOKEN", "your_key_here", "test-key-12345678",
                    "sk-exampleZZZ1234567890", "null", "TBD"):
            self.assertEqual(self._state_for(bad), "rejected_placeholder",
                             repr(bad))

    def test_malformed_rejected(self):
        for bad in ("<TODO>", "[REPLACE]", "${TYPESAFE_API_KEY}", "has space in it",
                    "abc", 12345, None):
            self.assertEqual(self._state_for(bad), "rejected_malformed",
                             repr(bad))

    def test_real_value_configured(self):
        st = cr.resolve_provider_key(
            "direct", "acme", [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A})],
            {})
        self.assertEqual(st.state, "configured")
        self.assertTrue(st.configured)
        self.assertEqual(st.key_name, cr.TYPESAFE_API_KEY)


class TestKeyNames(unittest.TestCase):
    def test_jev_alias_serves_direct_route(self):
        st = cr.resolve_provider_key(
            "direct", "acme", [scoped("acme", {cr.JEV_API_KEY: REAL_A})], {})
        self.assertEqual(st.state, "configured")
        self.assertEqual(st.key_name, cr.JEV_API_KEY)

    def test_openrouter_key_serves_openrouter_route(self):
        st = cr.resolve_provider_key(
            "openrouter", "acme",
            [scoped("acme", {cr.OPENROUTER_API_KEY: REAL_A})], {})
        self.assertEqual(st.state, "configured")

    def test_route_key_sets_disjoint_no_cross_route_use(self):
        self.assertFalse(
            set(cr.DIRECT_KEYS) & set(cr.OPENROUTER_KEYS),
            "direct/openrouter key sets must not collide")
        st = cr.resolve_provider_key(
            "direct", "acme",
            [scoped("acme", {cr.OPENROUTER_API_KEY: REAL_A})], {})
        self.assertFalse(st.configured)

    def test_unknown_route_is_error_not_raise(self):
        st = cr.resolve_provider_key("chat", "acme", [], {})
        self.assertEqual(st.state, "error")

    def test_missing_company_id_is_error_not_raise(self):
        st = cr.resolve_provider_key("direct", "  ", [], {})
        self.assertEqual(st.state, "error")


class TestPermissionsAndLogging(unittest.TestCase):
    def test_configured_is_not_verified_working(self):
        st = cr.resolve_provider_key(
            "direct", "acme", [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A})],
            {})
        self.assertTrue(st.configured)
        self.assertFalse(st.verified_working)

    def test_credential_answers_neither_permission_question(self):
        res = cr.resolve_company_credentials(
            "acme", [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A,
                                    cr.OPENROUTER_API_KEY: REAL_B})], {})
        for route, st in res.items():
            self.assertFalse(st.authorizes_spend, route)
            self.assertFalse(st.authorizes_transmit, route)

    def test_sanitized_logs_carry_no_secret_value(self):
        res = cr.resolve_company_credentials(
            "acme", [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A})], {})
        for line in cr.sanitized_summary(res):
            self.assertNotIn(REAL_A, line)
            self.assertNotIn(REAL_B, line)
        line = cr.sanitized_log_line(res["direct"])
        self.assertIn("route=direct", line)
        self.assertIn("state=configured", line)
        self.assertIn("company_file", line)

    def test_resolver_never_reads_live_process_env(self):
        source = _RESOLVER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import os", source)
        os.environ[cr.TYPESAFE_API_KEY] = REAL_A
        try:
            st = cr.resolve_provider_key("direct", "acme", [], {})
            self.assertFalse(st.configured)
        finally:
            del os.environ[cr.TYPESAFE_API_KEY]

    def test_resolve_is_read_only(self):
        stores = [scoped("acme", {cr.TYPESAFE_API_KEY: REAL_A}),
                  unscoped({cr.OPENROUTER_API_KEY: REAL_B})]
        before = copy.deepcopy(stores)
        cr.resolve_company_credentials("acme", stores, {})
        self.assertEqual(stores, before)

    def test_junk_stores_never_raise(self):
        st = cr.resolve_provider_key(
            "direct", "acme", [None, "nope", {"values": "x"}], {})
        self.assertEqual(st.state, "absent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
