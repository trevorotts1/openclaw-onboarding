#!/usr/bin/env python3
"""D24 producer bundle + dispatch parity tests (JEV spec 1.1, ss 10.5/10.6; A26/A35/A37/A38).

Proves, against the REAL producer/producer_bundle.py plus the REAL D02
contracts/schema.py and D20 parts validators (no reimplemented logic):
  * producer full-bundle reuse validates company/provenance/versions/schema/
    hash/confirmation through D02, then reuses with every D02 field
    preserved (A38 positive; A26 preservation);
  * bare persona IDs and ID-only dicts rejected as forged confirmation
    (A38 negative);
  * stale revisions/hashes refuse to overwrite a newer task decision and
    unconfirmed bundles refuse to bypass persona confirmation;
  * same unchanged re-dispatch reuses committed selection; changed scope/
    input/bundle creates an auditable next revision (A35);
  * auto and manual dispatch receive the same snapshot + renderer refs and
    are told re-selection is prohibited; operator locks force rescore,
    never a stale-blend coexistence (A37).

Run: pytest tests/unit/test_producer_bundle.py -q
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_DE = _SHARED / "decision_engine"
_FIX = _DE / "contracts" / "fixtures"
sys.path.insert(0, str(_SHARED))


def _load(name, path):
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


prod = _load("d24_producer_under_test", _DE / "producer" / "producer_bundle.py")
# REAL D02 validators (identity, not reimplementation).
de = _load("d24_producer_schema_check",
           _DE / "contracts" / "schema.py")
# REAL D20 part validator.
parts = _load("d24_producer_parts_check", _DE / "parts" / "__init__.py")

COMPANY = "fixture-co"
CATALOG = "1.4"


def _env(name="envelope_committed.json"):
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


def _part(**over):
    base = {
        "part_id": "part-1",
        "kind": "sop_slot",
        "source": "sop_slot",
        "scope_id": "scope-A",
        "seq": 1,
        "goal": "onboard new member",
        "conversion_goal": "book a call",
        "consumed_hints": ["hint-a"],
    }
    base.update(over)
    return base


class ProducerReuse(unittest.TestCase):
    def test_full_bundle_reuses_with_every_d02_field_preserved(self):
        env = _env()
        ok, errs, bundle = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG,
            head_revision=1, input_hash="sha256:fixture-input-content")
        self.assertTrue(ok, errs)
        self.assertEqual(sorted(bundle.keys()),
                         sorted(env["personaBundle"].keys()))
        for key in ("mode", "persona_id", "topic", "blend_directive",
                    "conversion_goal", "goal_source", "catalog_version",
                    "confirm_required", "task_personas", "voice",
                    "resolved_audience", "resolved_goal", "rationale"):
            self.assertEqual(bundle[key], env["personaBundle"][key],
                             f"bundle field {key} lost")
        ok_b, errs_b = de.validate_persona_bundle(bundle, company_id=COMPANY)
        self.assertTrue(ok_b, errs_b)

    def test_mechanical_bundle_reuses(self):
        env = _env("envelope_mechanical.json")
        ok, errs, bundle = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG)
        self.assertTrue(ok, errs)
        self.assertTrue(bundle["no_persona_required"])

    def test_unknown_optional_extension_preserved(self):
        env = _env()
        env["x_future_optional"] = {"note": "additive"}
        env["personaBundle"]["x_bundle_future"] = "kept"
        ok, errs, bundle = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG)
        self.assertTrue(ok, errs)
        self.assertEqual(bundle["x_bundle_future"], "kept")

    def test_no_reselection_signal(self):
        self.assertNotIn("select", dir(prod))
        self.assertNotIn("reselect", dir(prod))


class ForgedConfirmation(unittest.TestCase):
    def test_bare_id_list_rejected(self):
        ok, errs, bundle = prod.ingest_producer_bundle(
            ["persona-alpha"], company_id=COMPANY, catalog_version=CATALOG)
        self.assertFalse(ok)
        self.assertIsNone(bundle)
        self.assertTrue(any("forged confirmation" in e for e in errs), errs)

    def test_bare_id_string_rejected(self):
        ok, errs, bundle = prod.ingest_producer_bundle(
            "persona-alpha", company_id=COMPANY, catalog_version=CATALOG)
        self.assertFalse(ok)
        self.assertIsNone(bundle)
        self.assertTrue(any("forged confirmation" in e for e in errs), errs)

    def test_id_only_dict_rejected(self):
        ok, errs, bundle = prod.ingest_producer_bundle(
            {"persona_id": "persona-alpha"}, company_id=COMPANY,
            catalog_version=CATALOG)
        self.assertFalse(ok)
        self.assertIsNone(bundle)
        self.assertTrue(any("forged confirmation" in e for e in errs), errs)

    def test_unconfirmed_bundle_refuses_bypass(self):
        env = _env()
        bundle = env["personaBundle"]
        bundle["resolved_audience"] = dict(bundle["resolved_audience"])
        bundle["resolved_audience"]["source"] = "asked"
        bundle["resolved_audience"]["confirm_required"] = True
        bundle["confirm_required"] = True
        ok, errs, out = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG)
        self.assertFalse(ok)
        self.assertIsNone(out)
        self.assertTrue(any("confirmation" in e for e in errs), errs)

    def test_company_mismatch_rejected(self):
        env = _env()
        ok, errs, out = prod.ingest_producer_bundle(
            env, company_id="other-co", catalog_version=CATALOG)
        self.assertFalse(ok)
        self.assertIsNone(out)
        self.assertTrue(any("company mismatch" in e for e in errs), errs)

    def test_version_mismatch_rejected(self):
        env = _env()
        ok, errs, out = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version="9.9")
        self.assertFalse(ok)
        self.assertIsNone(out)
        self.assertTrue(any("version mismatch" in e for e in errs), errs)

    def test_stale_revision_refuses_overwrite(self):
        env = _env()
        env["decisionRevision"] = 0
        ok, errs, out = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG,
            head_revision=1, input_hash="sha256:fixture-input-content")
        self.assertFalse(ok)
        self.assertIsNone(out)
        self.assertTrue(any("stale producer decision" in e for e in errs),
                        errs)

    def test_stale_input_hash_refuses_overwrite(self):
        env = _env()
        ok, errs, out = prod.ingest_producer_bundle(
            env, company_id=COMPANY, catalog_version=CATALOG,
            head_revision=1, input_hash="sha256:something-newer")
        self.assertFalse(ok)
        self.assertIsNone(out)
        self.assertTrue(any("stale producer input" in e for e in errs), errs)

    def test_validator_never_raises_on_garbage(self):
        for bad in (None, 42, [], {"decisionId": "x"}):
            ok, errs, out = prod.ingest_producer_bundle(
                bad, company_id=COMPANY, catalog_version=CATALOG)
            self.assertFalse(ok)
            self.assertTrue(errs)
            self.assertIsNone(out)


class PerPartExtensions(unittest.TestCase):
    def test_parts_map_to_rows_with_scope_goal_extensions(self):
        out = prod.parts_to_bundle([
            _part(),
            _part(part_id="part-2", kind="comm_part",
                  source="page_structure", seq=2, goal="nurture",
                  conversion_goal=""),
        ])
        rows = out["bundle"]["task_personas"]
        self.assertEqual([r["seq"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["scope_id"], "scope-A")
        self.assertEqual(rows[0]["goal"], "onboard new member")
        self.assertEqual(rows[0]["conversion_goal"], "book a call")
        self.assertEqual(out["bundle"]["conversion_goal"], "book a call")
        self.assertEqual(out["bundle"]["resolved_goal"]["value"], "book a call")
        ok, errs = de.validate_envelope(out["envelope"])
        self.assertTrue(ok, errs)

    def test_empty_conversion_goals_stay_empty(self):
        out = prod.parts_to_bundle([
            _part(conversion_goal=""),
            _part(part_id="part-2", seq=2, conversion_goal="  "),
        ])
        self.assertEqual(out["bundle"]["conversion_goal"], "")
        self.assertEqual(out["bundle"]["resolved_goal"]["value"], "")
        ok, errs = de.validate_envelope(out["envelope"])
        self.assertTrue(ok, errs)

    def test_bad_part_raises_through_real_d20_validator(self):
        with self.assertRaises(ValueError):
            prod.parts_to_bundle([_part(source="jev_generated")])

    def test_duplicate_seq_raises(self):
        with self.assertRaises(ValueError):
            prod.parts_to_bundle([_part(), _part(part_id="part-2")])

    def test_empty_parts_raises(self):
        with self.assertRaises(ValueError):
            prod.parts_to_bundle([])

    def test_cap_enforced(self):
        with self.assertRaises(ValueError):
            prod.parts_to_bundle([
                _part(part_id="p-%d" % i, seq=i + 1) for i in range(11)])

    def test_d02_shape_negatives_surface_as_real_d02_errors(self):
        out = prod.parts_to_bundle([_part()])
        bad = copy.deepcopy(out["bundle"])
        row = dict(bad["task_personas"][0])
        del row["seq"]
        bad["task_personas"] = [row]
        ok, errs = de.validate_persona_bundle(bad, company_id=COMPANY)
        self.assertFalse(ok)
        self.assertTrue(any("seq" in e for e in errs), errs)


class Redispatch(unittest.TestCase):
    def test_unchanged_reuses_committed(self):
        env = _env()
        res = prod.check_redispatch(env, copy.deepcopy(env))
        self.assertTrue(res["reuse"])
        self.assertEqual(res["revision"], env["decisionRevision"])

    def test_scope_change_revises(self):
        env = _env()
        cand = copy.deepcopy(env)
        cand["scopeId"] = "scope-other"
        res = prod.check_redispatch(env, cand)
        self.assertFalse(res["reuse"])
        self.assertIn("scope_changed", res["reason"])
        self.assertEqual(res["revision"], env["decisionRevision"] + 1)

    def test_input_change_revises(self):
        env = _env()
        cand = copy.deepcopy(env)
        cand["inputHash"] = "sha256:other"
        res = prod.check_redispatch(env, cand)
        self.assertFalse(res["reuse"])
        self.assertIn("input_changed", res["reason"])

    def test_bundle_change_revises(self):
        env = _env()
        cand = copy.deepcopy(env)
        cand["bundleHash"] = "sha256:other"
        res = prod.check_redispatch(env, cand)
        self.assertFalse(res["reuse"])
        self.assertIn("bundle_changed", res["reason"])

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            prod.check_redispatch({}, _env())


class DispatchParity(unittest.TestCase):
    def test_auto_manual_same_snapshot_and_refs(self):
        env = _env()
        d1 = prod.prepare_dispatch(env, mode="auto")
        d2 = prod.prepare_dispatch(env, mode="manual")
        self.assertTrue(d1["dispatched"])
        self.assertTrue(d2["dispatched"])
        self.assertTrue(d1["reselect_prohibited"])
        self.assertTrue(d2["reselect_prohibited"])
        self.assertTrue(d1["selection_assigned"])
        self.assertEqual(d1["snapshot"], d2["snapshot"])
        self.assertEqual(d1["renderer_load_references"],
                         d2["renderer_load_references"])

    def test_renderer_covers_all_applicable_roles(self):
        env = _env()
        got = prod.prepare_dispatch(env, mode="auto")
        refs = got["renderer_load_references"]
        bundle = env["personaBundle"]
        self.assertIn(bundle["persona_id"], refs)
        for row in bundle["task_personas"]:
            self.assertIn(row["persona_id"], refs)
        self.assertIn(bundle["fallbacks"]["governance"], refs)
        self.assertIn(bundle["fallbacks"]["default_persona"], refs)

    def test_operator_lock_forces_rescore(self):
        env = _env()
        got = prod.prepare_dispatch(env, mode="auto",
                                    operator_lock_persona_id="someone-else")
        self.assertFalse(got["dispatched"])
        self.assertTrue(got["needs_rescore"])
        self.assertIn("contradicts", got["reason"])

    def test_matching_lock_dispatches(self):
        env = _env()
        got = prod.prepare_dispatch(
            env, mode="manual",
            operator_lock_persona_id=env["personaBundle"]["persona_id"])
        self.assertTrue(got["dispatched"])

    def test_uncommitted_dispatch_refused(self):
        env = _env("envelope_mechanical.json")
        with self.assertRaises(ValueError):
            prod.prepare_dispatch(env, mode="auto")

    def test_bad_mode_refused(self):
        with self.assertRaises(ValueError):
            prod.prepare_dispatch(_env(), mode="shadow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
