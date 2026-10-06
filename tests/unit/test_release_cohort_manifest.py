#!/usr/bin/env python3
"""Release-cohort manifest instance tests (JEV spec 1.1, 14.8/17.4; ACC-054).

Proves the COMMITTED instance, not a fixture:
  * <repo root>/release-cohort.json validates against the REAL D34
    validator (shared-utils/decision_engine/modes/cohort.py);
  * its onb_sha/cc_sha/versions match the live repo contracts
    (/version and cc-compat.json), so the pair cannot silently drift;
  * train.check_release_cohort() reads the instance and REFUSES a
    mismatched pair — a mutated manifest (wrong cc_sha) is rejected;
  * train.promote() records the verified pair and refuses a drifted one;
  * a malformed instance fails the loader closed.

Run: python3 -m pytest tests/unit/test_release_cohort_manifest.py -q
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
_SHARED = _REPO_ROOT / "shared-utils"
assert _SHARED.is_dir(), "shared-utils missing: %s" % _SHARED
sys.path.insert(0, str(_SHARED))

from decision_engine_train import (  # noqa: E402
    COHORT_MANIFEST_RELPATH,
    INDEPENDENT_ROUTE,
    _load_cohort_manifest,
    attach_integration_qc,
    check_release_cohort,
    enqueue,
    new_state,
    promote,
    record_tests,
    tick,
)

_MANIFEST_PATH = _REPO_ROOT / COHORT_MANIFEST_RELPATH
_COHORT_PY = _SHARED / "decision_engine" / "modes" / "cohort.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cohort = _load("rc_cohort", _COHORT_PY)


def _passing_results():
    return {"checks": [{"name": "unit", "status": "pass"},
                       {"name": "integration", "status": "pass"}]}


def _receipt(sha):
    return {"sha": sha, "verdict": "PASS", "reviewer": "sonnet-qc-1",
            "reviewer_route": INDEPENDENT_ROUTE}


def _promotable(state, repo="onb"):
    enqueue(state, repo, "D01", "a", _receipt("a"))
    batch_id = tick(state, repo, 900, owner="t:onb")["batch_id"]
    record_tests(state, repo, batch_id, "int-1", _passing_results())
    attach_integration_qc(state, repo, batch_id, "sonnet-qc-1",
                          INDEPENDENT_ROUTE, "PASS")
    return batch_id


class ManifestInstance(unittest.TestCase):
    def test_instance_is_committed(self):
        self.assertTrue(_MANIFEST_PATH.is_file(),
                        "missing committed instance at %s" % _MANIFEST_PATH)

    def test_instance_validates_against_real_validator(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        ok, errors = cohort.validate_cohort(manifest)
        self.assertTrue(ok, "validator rejected the instance: %s" % errors)

    def test_instance_shas_are_exact_40_hex(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        for key in ("onb_sha", "cc_sha"):
            self.assertTrue(cohort.is_hex_sha(manifest[key]),
                            "%s not exact 40-hex: %r" % (key, manifest[key]))
        self.assertEqual(manifest["onb_sha"], manifest["onb_sha"].lower())
        self.assertEqual(manifest["cc_sha"], manifest["cc_sha"].lower())

    def test_instance_versions_match_live_repo_contracts(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        onb_version = (_REPO_ROOT / "version").read_text(
            encoding="utf-8").strip()
        compat = json.loads(
            (_REPO_ROOT / "cc-compat.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["onb_version"], onb_version)
        self.assertEqual(manifest["cc_version"],
                         compat["commandCenter"]["pinnedTag"])
        self.assertEqual(manifest["contract"], _bridge_version())

    def test_pairing_check_rejects_a_drifted_cc_sha(self):
        """The exact-pair gate, which validate_cohort does not do on its own.

        validate_cohort checks SHAPE only, so a wrong-but-well-formed
        cc_sha passes it. The pairing evaluation is what rejects drift.
        """
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["cc_sha"] = "b" * 40
        ok, _ = cohort.validate_cohort(manifest)
        self.assertTrue(ok, "shape check is expected to accept 40-hex")
        verdict = cohort.evaluate_pairing(
            pairing="new_new", onb_sha=manifest["onb_sha"],
            cc_sha=manifest["cc_sha"],
            tested_pairs=[(manifest["onb_sha"], manifest["cc_sha"])],
            handshake_ok=True)
        self.assertEqual(verdict["behavior"], cohort.BEHAVIOR_FULL_CONTRACT)
        drifted = cohort.evaluate_pairing(
            pairing="new_new", onb_sha=manifest["onb_sha"],
            cc_sha=manifest["cc_sha"],
            tested_pairs=[("a" * 40, "b" * 40)], handshake_ok=True)
        self.assertEqual(drifted["behavior"], cohort.BEHAVIOR_COMPAT_FALLBACK)
        self.assertFalse(drifted["exact_match"])

    def test_mutated_pair_fails_the_equality_check(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["cc_sha"] = "b" * 40
        tested = [(manifest["onb_sha"], manifest["cc_sha"])]
        verdict = cohort.evaluate_pairing(
            pairing="new_new", onb_sha="a" * 40,
            cc_sha=manifest["cc_sha"], tested_pairs=tested,
            handshake_ok=True)
        self.assertEqual(verdict["behavior"], cohort.BEHAVIOR_COMPAT_FALLBACK)
        self.assertFalse(verdict["exact_match"])


def _bridge_version():
    """The shared decision-bridge contract version (canonical source)."""
    import re
    src = (_SHARED / "decision-engine.py").read_text(encoding="utf-8")
    return re.search(r'^BRIDGE_SCHEMA_VERSION = "([^"]+)"', src,
                     re.MULTILINE).group(1)


class Loader(unittest.TestCase):
    def test_loader_returns_the_committed_instance(self):
        manifest = _load_cohort_manifest()
        self.assertIsInstance(manifest, dict)
        self.assertTrue(cohort.is_hex_sha(manifest["onb_sha"]))

    def test_loader_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_load_cohort_manifest(d))

    def test_loader_refuses_a_malformed_instance(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
            manifest["cc_sha"] = "not-a-sha"
            (Path(d) / COHORT_MANIFEST_RELPATH).write_text(
                json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cc_sha"):
                _load_cohort_manifest(d)


class ReleaseGate(unittest.TestCase):
    def test_gate_fails_closed_when_the_handshake_is_unproven(self):
        with self.assertRaisesRegex(ValueError, "handshake_failed"):
            check_release_cohort()

    def test_gate_accepts_the_committed_instance(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(check_release_cohort(handshake_ok=True), manifest)

    def test_gate_refuses_a_drifted_cc_sha(self):
        """THE MUTATED-MANIFEST PROOF: wrong cc_sha is rejected, not absorbed."""
        drifted = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        drifted["cc_sha"] = "b" * 40
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / COHORT_MANIFEST_RELPATH).write_text(
                json.dumps(drifted), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "half-promoted"):
                check_release_cohort(d)

    def test_gate_refuses_a_drifted_pairing_kind(self):
        with self.assertRaisesRegex(ValueError, "half-promoted"):
            check_release_cohort(None, pairing="old_new")

    def test_gate_refuses_a_shape_invalid_instance(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / COHORT_MANIFEST_RELPATH).write_text(
                json.dumps({"onb_sha": "a" * 40}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cohort manifest invalid"):
                check_release_cohort(d)

    def test_gate_returns_none_when_no_instance_exists(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(check_release_cohort(d))


class PromotionConsumer(unittest.TestCase):
    def test_promote_carries_the_gate_record_into_the_manifest(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        state = new_state()
        batch_id = _promotable(state)
        record = promote(state, "onb", batch_id, "main-2", pairing="new_new",
                         handshake_ok=True,
                         cohort=check_release_cohort(
                             handshake_ok=True))["promotion"]["cohort"]
        self.assertTrue(record["checked"])
        self.assertEqual(record["behavior"], "full_contract")
        self.assertEqual(record["cc_sha"], manifest["cc_sha"])

    def test_promote_refuses_a_drifted_cc_sha(self):
        """Fails closed: no promotion record is written on a bad pair."""
        state = new_state()
        batch_id = _promotable(state)
        drifted = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        drifted["cc_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "half-promoted"):
            promote(state, "onb", batch_id, "main-2", cohort=drifted,
                    pairing="new_new")
        self.assertIsNone(state["batches"]["onb/%s" % batch_id].get("promotion"))

    def test_promote_refuses_an_invalid_manifest(self):
        state = new_state()
        batch_id = _promotable(state)
        with self.assertRaisesRegex(ValueError, "cohort manifest invalid"):
            promote(state, "onb", batch_id, "main-2",
                    cohort={"onb_sha": "a" * 40}, pairing="new_new")

    def test_promote_without_cohort_stays_visible_absence(self):
        """Unchanged pre-existing path: absence recorded, not silent."""
        state = new_state()
        batch_id = _promotable(state)
        record = promote(state, "onb", batch_id, "main-2")["promotion"]["cohort"]
        self.assertFalse(record["checked"])
        self.assertEqual(record["reason"], "no_cohort_manifest")

    def test_gate_refuses_a_candidate_the_instance_does_not_describe(self):
        """A53: the instance describes THIS candidate, not just some pair.

        The self-matching manifest is internally consistent in both
        directions, so only the candidate binding rejects a different
        revision of the same release.
        """
        with self.assertRaisesRegex(ValueError, "not the pair"):
            check_release_cohort(handshake_ok=True, repository="onb",
                                 candidate_sha="f" * 40)

    def test_gate_accepts_the_candidate_the_instance_names(self):
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            check_release_cohort(handshake_ok=True, repository="onb",
                                 candidate_sha=manifest["onb_sha"]),
            manifest)

    def test_gate_refuses_an_unbound_candidate_argument(self):
        """Both arguments bind together; half a binding fails closed."""
        with self.assertRaisesRegex(ValueError, "both repository and"):
            check_release_cohort(handshake_ok=True, repository="onb")

    def test_gate_refuses_a_repository_outside_the_pair(self):
        with self.assertRaisesRegex(ValueError, "not part of the"):
            check_release_cohort(handshake_ok=True, repository="elsewhere",
                                 candidate_sha="f" * 40)

    def test_gate_without_a_candidate_argument_keeps_instance_scope(self):
        """Omitting the binding leaves the historical instance-only check."""
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(check_release_cohort(handshake_ok=True), manifest)


class PromotionCandidateBinding(unittest.TestCase):
    """A53: the gate GOVERNS activation through promote(), not only in isolation.

    Every test above proves check_release_cohort() in isolation. These prove
    the wiring: promote() itself refuses, and the state is left unactivated.
    """

    def _promotable_for(self, integration_sha):
        """An eligible batch whose candidate is exactly ``integration_sha``."""
        state = new_state()
        enqueue(state, "onb", "D01", integration_sha,
                _receipt(integration_sha))
        batch_id = tick(state, "onb", 900, owner="t:onb")["batch_id"]
        record_tests(state, "onb", batch_id, integration_sha,
                     _passing_results())
        attach_integration_qc(state, "onb", batch_id, "sonnet-qc-1",
                              INDEPENDENT_ROUTE, "PASS")
        return state, batch_id

    def test_promote_refuses_a_candidate_the_committed_instance_does_not_describe(self):
        """A different revision of the same release is a different candidate."""
        instance = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        other = "f" * 40
        self.assertNotEqual(other, instance["onb_sha"])
        state, batch_id = self._promotable_for(other)
        with self.assertRaisesRegex(ValueError, "not the pair"):
            promote(state, "onb", batch_id, "main-2",
                    cohort=check_release_cohort(handshake_ok=True),
                    pairing="new_new", handshake_ok=True)
        self.assertIsNone(state["batches"]["onb/%s" % batch_id].get("promotion"))
        self.assertNotEqual(state["windows"]["onb"]["last_outcome"], "promoted")

    def test_promote_adopts_the_committed_instance_for_the_named_candidate(self):
        instance = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        state, batch_id = self._promotable_for(instance["onb_sha"])
        record = promote(state, "onb", batch_id, "main-2",
                         cohort=check_release_cohort(handshake_ok=True),
                         pairing="new_new",
                         handshake_ok=True)["promotion"]["cohort"]
        self.assertTrue(record["checked"])
        self.assertEqual(record["behavior"], "full_contract")
        self.assertEqual(record["onb_sha"], instance["onb_sha"])

    def test_promote_without_cohort_still_refuses_a_non_named_candidate(self):
        """Adopt-or-refuse, adopt arm: no cohort passed, instance is consulted."""
        instance = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        other = "f" * 40
        self.assertNotEqual(other, instance["onb_sha"])
        state, batch_id = self._promotable_for(other)
        with self.assertRaisesRegex(ValueError, "not the pair"):
            promote(state, "onb", batch_id, "main-2",
                    pairing="new_new", handshake_ok=True)
        self.assertIsNone(state["batches"]["onb/%s" % batch_id].get("promotion"))

    def test_promote_without_cohort_adopts_the_named_candidate(self):
        """Control for the arm above: the named candidate still activates."""
        instance = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        state, batch_id = self._promotable_for(instance["onb_sha"])
        record = promote(state, "onb", batch_id, "main-2",
                         pairing="new_new",
                         handshake_ok=True)["promotion"]["cohort"]
        self.assertTrue(record["checked"])
        self.assertEqual(record["onb_sha"], instance["onb_sha"])


if __name__ == "__main__":
    unittest.main()
