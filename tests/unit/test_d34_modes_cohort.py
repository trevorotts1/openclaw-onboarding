#!/usr/bin/env python3
"""D34 mode preservation + cohort validator tests (JEV spec 1.1, s 3.6/14.8/17.3-17.4, A59-A63).

Proves, against the REAL shared-utils/decision_engine/modes/ modules
(no reimplemented logic):
  * explicit off/legacy/shadow survive install/update; release default
    applies only with no explicit override (3.6);
  * off/legacy yield equivalent normalized no-JEV decisions, ZERO JEV
    traffic (A62);
  * unapproved auto reports true no-JEV path with typed denial, never
    "missing credentials" (A59); auto/shadow->off fences in-flight
    recommendations without rewriting committed snapshots (A63);
  * shadow can never commit (A61/A63); sample gate is pure predicate;
  * cohort manifest pins EXACT tested ONB+CC SHAs; untested/half pair
    stays compat fallback, never activates (A43/A50/A53);
  * rollback is mode=off on installed version, history retained (17.4);
  * no network/socket/subprocess imports; parity with D02 mode enum.

Run: python3 -m pytest tests/unit/test_d34_modes_cohort.py -q
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_MODES_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
             / "modes" / "modes.py")
_COHORT_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "modes" / "cohort.py")
_SCHEMA_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "contracts" / "schema.py")
_COMMIT_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "commit" / "commit.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


modes = _load("d34_modes", _MODES_PY)
cohort = _load("d34_cohort", _COHORT_PY)
schema = _load("d34_schema", _SCHEMA_PY)
commit = _load("d34_commit", _COMMIT_PY)

ONB_SHA = "a" * 40
CC_SHA = "b" * 40
OTHER_SHA = "c" * 40


class ExplicitPreservation(unittest.TestCase):
    def test_each_explicit_mode_survives_release_default(self):
        for mode in ("off", "legacy", "shadow", "auto"):
            self.assertEqual(
                modes.preserve_explicit_mode("auto", mode, True), mode)

    def test_no_stored_mode_takes_release_default(self):
        self.assertEqual(
            modes.preserve_explicit_mode("auto", None, False), "auto")

    def test_non_explicit_stored_yields_to_default(self):
        self.assertEqual(
            modes.preserve_explicit_mode("auto", "legacy", False), "auto")

    def test_unknown_mode_fails_loudly(self):
        with self.assertRaises(ValueError):
            modes.preserve_explicit_mode("auto", "turbo", True)
        with self.assertRaises(ValueError):
            modes.preserve_explicit_mode("turbo", None, False)

    def test_modes_enum_matches_d02(self):
        self.assertEqual(tuple(modes.MODES), tuple(schema.CONFIGURED_MODE_ENUM))


class EffectivePath(unittest.TestCase):
    def test_unapproved_auto_honest_no_jev_typed_denial(self):
        for spend, transmit, reason in (
                (False, True, "not_authorized"),
                (True, False, "data_not_permitted"),
                (False, False, "not_authorized")):
            got = modes.resolve_effective_path(
                "auto", spend_ok=spend, transmit_ok=transmit)
            self.assertEqual(got["effective_path"], "no_jev")
            self.assertEqual(got["reason"], reason)
            self.assertNotIn("credential", got["reason"])

    def test_legacy_off_shadow_authoritative_no_jev(self):
        self.assertEqual(modes.resolve_effective_path(
            "legacy", spend_ok=True, transmit_ok=True)["effective_path"],
            "no_jev")
        self.assertEqual(modes.resolve_effective_path(
            "off", spend_ok=True, transmit_ok=True)["effective_path"],
            "no_jev")
        shadow = modes.resolve_effective_path(
            "shadow", spend_ok=True, transmit_ok=True)
        self.assertEqual(shadow["effective_path"], "no_jev")

    def test_approved_auto_eligible(self):
        got = modes.resolve_effective_path(
            "auto", spend_ok=True, transmit_ok=True)
        self.assertEqual(got["effective_path"], "jev")
        self.assertEqual(got["reason"], "eligible")


class ZeroTraffic(unittest.TestCase):
    def test_off_legacy_zero_traffic(self):
        self.assertFalse(modes.jev_traffic_permitted("off"))
        self.assertFalse(modes.jev_traffic_permitted("legacy"))

    def test_off_legacy_equivalent_normalized(self):
        first = {"persona_id": "p1", "voice": "v", "configuredMode": "off",
                 "effectivePath": "no_jev", "skipReason": "mode_off"}
        second = {"persona_id": "p1", "voice": "v", "configuredMode": "legacy",
                   "effectivePath": "no_jev", "skipReason": "mode_legacy"}
        self.assertFalse(modes.jev_traffic_permitted("off"))
        self.assertTrue(modes.decisions_equivalent(first, second))
        # differing substance is NOT equivalent
        third = dict(second, voice="other")
        self.assertFalse(modes.decisions_equivalent(first, third))


class Fencing(unittest.TestCase):
    def _fenced_store(self):
        store = commit.fresh_state(input_hash="h1")
        token = commit.issue_fence_token(store)
        return store, token

    def test_mode_change_fences_inflight_committed_untouched(self):
        store, token = self._fenced_store()
        rev = commit.cas_commit(
            store, 0, {"decisionId": "d1", "inputHash": "h1",
                       "fence_token": token}, {"board": 1})
        self.assertEqual(rev, 1)
        store["fence"] = modes.bump_fence(store["fence"], mode_changed=True)
        with self.assertRaises(commit.FencedError) as ctx:
            commit.check_fence(store, token)
        self.assertIn("mode_changed", str(ctx.exception))
        # committed decision still intact, running path unaffected
        self.assertEqual(store["decision"]["decisionId"], "d1")
        self.assertEqual(store["decision_revision"], 1)

    def test_pure_twin_matches_d23(self):
        store, token = self._fenced_store()
        self.assertIsNone(modes.fence_reason(token, store["fence"]))
        self.assertFalse(modes.is_fenced(token, store["fence"]))
        new_fence = modes.bump_fence(store["fence"], policy_changed=True)
        self.assertEqual(
            modes.fence_reason(token, new_fence), "policy_changed")
        self.assertTrue(modes.is_fenced(token, new_fence))
        # bumping neither leaves the token valid
        same = modes.bump_fence(store["fence"])
        self.assertIsNone(modes.fence_reason(token, same))

    def test_rollback_fences_inflight_keeps_history(self):
        store, token = self._fenced_store()
        commit.cas_commit(store, 0, {"decisionId": "d1", "inputHash": "h1",
                                     "fence_token": token}, {})
        snap = commit.start_execution(store)
        config = {"mode": "auto", "budgets": {"x": 1}}
        new_config, new_fence, prev = modes.rollback_to_off(
            config, store["fence"])
        self.assertEqual((new_config["mode"], prev), ("off", "auto"))
        self.assertEqual(new_config["previous_mode"], "auto")
        self.assertEqual(new_config["budgets"], {"x": 1})
        store["fence"] = new_fence
        with self.assertRaises(commit.FencedError):
            commit.check_fence(store, token)
        # history retained: decision + running snapshot untouched
        self.assertEqual(store["decision"]["decisionId"], "d1")
        self.assertEqual(snap["decisionId"], "d1")
        self.assertEqual(config["mode"], "auto")  # caller input not mutated


class ShadowRules(unittest.TestCase):
    def test_shadow_commit_always_refused(self):
        with self.assertRaises(modes.ShadowCommitError):
            modes.refuse_shadow_commit({"winner": "p1"})

    def test_shadow_sample_gate_predicate(self):
        ok, reason = modes.shadow_sample_allowed(
            sample_rate=0.5, draw=0.1, quota_remaining=5,
            in_flight=0, max_in_flight=1, permission_ok=True)
        self.assertTrue(ok)
        self.assertEqual(reason, "sampled")
        cases = [
            dict(sample_rate=0.0, draw=0.0, quota_remaining=5,
                 in_flight=0, max_in_flight=1, permission_ok=True),
            dict(sample_rate=0.5, draw=0.1, quota_remaining=0,
                 in_flight=0, max_in_flight=1, permission_ok=True),
            dict(sample_rate=0.5, draw=0.1, quota_remaining=5,
                 in_flight=1, max_in_flight=1, permission_ok=True),
            dict(sample_rate=0.5, draw=0.1, quota_remaining=5,
                 in_flight=0, max_in_flight=1, permission_ok=False),
        ]
        for kw in cases:
            allowed, why = modes.shadow_sample_allowed(**kw)
            self.assertFalse(allowed)
            self.assertTrue(why)

    def test_shadow_dedup_key_stable(self):
        kw = dict(company="c1", scope="s1", input_hash="h",
                   stage="dept", candidate_version="v1",
                   policy_version="p1", model_version="m1", epoch="e7")
        self.assertEqual(modes.shadow_dedup_key(**kw),
                         modes.shadow_dedup_key(**kw))
        other = dict(kw, epoch="e8")
        self.assertNotEqual(modes.shadow_dedup_key(**kw),
                            modes.shadow_dedup_key(**other))
        with self.assertRaises(ValueError):
            modes.shadow_dedup_key(**dict(kw, epoch=""))


class CohortValidator(unittest.TestCase):
    def _manifest(self):
        return {"onb_sha": ONB_SHA, "cc_sha": CC_SHA,
                "onb_version": "1.4.0", "cc_version": "2.1.0",
                "contract": "jev-1.1"}

    def test_valid_manifest(self):
        ok, errors = cohort.validate_cohort(self._manifest())
        self.assertTrue(ok)
        self.assertEqual(errors, [])

    def test_bad_sha_rejected(self):
        for bad in ("abc", "A" * 40, "z" * 40, OTHER_SHA[:39], None, 42):
            m = self._manifest()
            m["onb_sha"] = bad
            ok, errors = cohort.validate_cohort(m)
            self.assertFalse(ok)
            self.assertTrue(errors)

    def test_exact_pair_full_contract_only_with_handshake(self):
        tested = [(ONB_SHA, CC_SHA)]
        full = cohort.evaluate_pairing(
            pairing="new_new", onb_sha=ONB_SHA, cc_sha=CC_SHA,
            tested_pairs=tested, handshake_ok=True)
        self.assertEqual(full["behavior"], "full_contract")
        no_handshake = cohort.evaluate_pairing(
            pairing="new_new", onb_sha=ONB_SHA, cc_sha=CC_SHA,
            tested_pairs=tested, handshake_ok=False)
        self.assertEqual(no_handshake["behavior"], "compat_fallback")

    def test_half_promoted_pair_never_activates(self):
        tested = [(ONB_SHA, CC_SHA)]
        changed = cohort.evaluate_pairing(
            pairing="new_new", onb_sha=OTHER_SHA, cc_sha=CC_SHA,
            tested_pairs=tested, handshake_ok=True)
        self.assertEqual(changed["behavior"], "compat_fallback")
        self.assertFalse(changed["exact_match"])
        # changed SHA invalidates prior approval: not in tested set
        self.assertNotIn((OTHER_SHA, CC_SHA), tested)

    def test_mixed_version_pairings_fall_back(self):
        tested = [(ONB_SHA, CC_SHA)]
        old_cc = cohort.evaluate_pairing(
            pairing="new_old", onb_sha=ONB_SHA, cc_sha=OTHER_SHA,
            tested_pairs=tested, handshake_ok=True)
        self.assertEqual(old_cc["behavior"], "compat_fallback")
        self.assertIn("legacy", old_cc["reason"])
        old_onb = cohort.evaluate_pairing(
            pairing="old_new", onb_sha=OTHER_SHA, cc_sha=CC_SHA,
            tested_pairs=tested, handshake_ok=True)
        self.assertEqual(old_onb["behavior"], "compat_fallback")
        self.assertIn("fallback", old_onb["reason"])
        with self.assertRaises(ValueError):
            cohort.evaluate_pairing(
                pairing="old_old", onb_sha=ONB_SHA, cc_sha=CC_SHA,
                tested_pairs=tested)

    def test_rollback_compat_gate(self):
        ok, _ = cohort.check_rollback_compat("1.4.0", "1.3.2")
        self.assertTrue(ok)
        bad, reason = cohort.check_rollback_compat("2.0.0", "1.9.9")
        self.assertFalse(bad)
        self.assertTrue(reason)
        bad2, _ = cohort.check_rollback_compat("nope", "1.0.0")
        self.assertFalse(bad2)


class NoForbiddenImports(unittest.TestCase):
    def test_modes_cohort_no_network_or_os(self):
        for path in (_MODES_PY, _COHORT_PY):
            tree = ast.parse(path.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split(".")[0])
            for banned in ("socket", "urllib", "http", "ssl",
                           "subprocess", "os", "sqlite3", "sys"):
                self.assertNotIn(banned, imported, "%s in %s" % (banned, path))


if __name__ == "__main__":
    unittest.main()
