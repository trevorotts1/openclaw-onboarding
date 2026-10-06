#!/usr/bin/env python3
"""D20 SOP-slot/hint propagation tests (JEV spec 1.1, ss 8.9/8.10; 4.5).
Proves, against the REAL shared-utils/decision_engine/parts/__init__.py:
  * parts are caller-supplied with declared-first sources only — JEV never
    originates a part (jev_*/unknown source rejected);
  * kind is caller-supplied and never defaulted/inferred — an SOP slot is
    never treated as a comm part or agent task (missing/unknown kind
    rejected); comm/agent distinction preserved verbatim;
  * per-part identity (scope_id/seq/goal/conversion_goal) required, with
    conversion_goal empty allowed when unresolved (D02 mirror);
  * same-input four-ways agree: single/combined/blended/producer consumed
    sets must match exactly — differing hint sets raise an explicit mismatch
    naming the divergent paths (never a silent pick);
  * slot/hint repair: a missing hint yields an explicit bind directive
    (directive count == missing count; never silently dropped);
  * single-decomposition guard and slot/hint check are the REAL D19
    functions (identity, not reimplementation);
  * D02 round-trip: ``emit_bundle_scope_goal`` materializes validated parts
    into a REAL ``envelope_committed.json`` carrier proven through the REAL
    ``contracts/schema.py`` validators (never reimplemented) — emitted
    bundle AND envelope validate True; D02-shape negatives (over-the-10
    cap, goal-source drift, missing/dup row seq) surface as REAL
    ``(False, errors)`` results.

Run: pytest tests/unit/test_part_propagation.py -q
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


parts = _load("d20_parts_under_test", _DE / "parts" / "__init__.py")
# SAME loader name as parts/__init__.py uses internally ("d20_collapse_policy"):
# sys.modules returns the one D19 module object, so identity below proves
# import-not-reimplement (distinct names would exec a second copy).
cp = _load("d20_collapse_policy", _DE / "personas" / "collapse_policy.py")


def _part(**over):
    base = {
        "part_id": "part-1",
        "kind": "sop_slot",
        "source": "sop_slot",
        "scope_id": "scope-A",
        "seq": 1,
        "goal": "onboard new member",
        "conversion_goal": "book a call",
        "consumed_hints": ["hint-a", "hint-b"],
    }
    base.update(over)
    return base


class DeclaredFirst(unittest.TestCase):
    def test_good_parts_all_kinds_and_sources(self):
        for kind in ("sop_slot", "comm_part", "agent_task"):
            for source in ("sop_slot", "page_structure", "campaign_manifest"):
                ok, errs = parts.validate_part(_part(kind=kind, source=source))
                self.assertTrue(ok, f"{kind}/{source}: {errs}")

    def test_jev_originated_source_rejected(self):
        for bad in ("jev_generated", "blend", "planner", "jev", ""):
            ok, errs = parts.validate_part(_part(source=bad))
            self.assertFalse(ok)
            self.assertTrue(errs)

    def test_source_missing_rejected(self):
        p = _part()
        del p["source"]
        ok, errs = parts.validate_part(p)
        self.assertFalse(ok)
        self.assertTrue(any("source" in e for e in errs))


class KindNeverDefaulted(unittest.TestCase):
    def test_missing_kind_rejected_never_inferred(self):
        p = _part()
        del p["kind"]
        ok, errs = parts.validate_part(p)
        self.assertFalse(ok)
        self.assertTrue(any("kind" in e for e in errs))

    def test_unknown_kind_rejected(self):
        for bad in ("slot", "combined", "blended", "page", ""):
            ok, errs = parts.validate_part(_part(kind=bad))
            self.assertFalse(ok)

    def test_sop_slot_stays_sop_slot(self):
        ok, _ = parts.validate_part(_part(kind="sop_slot"))
        self.assertTrue(ok)
        # kind travels verbatim — module exposes no generator/expander
        self.assertNotIn("expand", dir(parts))
        self.assertNotIn("generate", dir(parts))


class PerPartIdentity(unittest.TestCase):
    def test_conversion_goal_empty_allowed_when_unresolved(self):
        ok, errs = parts.validate_part(_part(conversion_goal=""))
        self.assertTrue(ok, errs)

    def test_conversion_goal_nonstring_rejected(self):
        ok, errs = parts.validate_part(_part(conversion_goal=None))
        self.assertFalse(ok)
        self.assertTrue(errs)

    def test_seq_zero_rejected(self):
        ok, _ = parts.validate_part(_part(seq=0))
        self.assertFalse(ok)

    def test_blank_scope_and_goal_rejected(self):
        ok, _ = parts.validate_part(_part(scope_id="  "))
        self.assertFalse(ok)
        ok, _ = parts.validate_part(_part(goal=""))
        self.assertFalse(ok)

    def test_bad_hints_rejected(self):
        ok, _ = parts.validate_part(_part(consumed_hints=["ok", ""]))
        self.assertFalse(ok)
        ok, _ = parts.validate_part(_part(consumed_hints="hint-a"))
        self.assertFalse(ok)

    def test_validator_never_raises(self):
        for bad in (None, "nope", 42, ["list"]):
            ok, errs = parts.validate_part(bad)
            self.assertFalse(ok)
            self.assertTrue(errs)


class FourWayAgreement(unittest.TestCase):
    def test_same_input_four_ways_agree(self):
        out = parts.assert_four_way_agreement(
            scope_id="scope-A",
            single=["hint-a", "hint-b"],
            combined=["hint-b", "hint-a"],  # order-insensitive
            blended=["hint-a", "hint-b"],
            producer=["hint-a", "hint-b"],
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["scope_id"], "scope-A")
        self.assertEqual(out["consumed"], ["hint-a", "hint-b"])
        self.assertEqual(out["paths"], ["single", "combined", "blended", "producer"])

    def test_differing_hint_sets_raise_naming_divergent_path(self):
        with self.assertRaises(ValueError) as ctx:
            parts.assert_four_way_agreement(
                scope_id="scope-A",
                single=["hint-a", "hint-b"],
                combined=["hint-a"],  # dropped hint-b
                blended=["hint-a", "hint-b"],
                producer=["hint-a", "hint-b"],
            )
        msg = str(ctx.exception)
        self.assertIn("combined", msg)
        self.assertIn("scope-A", msg)

    def test_extra_hint_on_one_path_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parts.assert_four_way_agreement(
                scope_id="scope-A",
                single=["hint-a"],
                combined=["hint-a"],
                blended=["hint-a"],
                producer=["hint-a", "hint-sneaky"],
            )
        self.assertIn("producer", str(ctx.exception))

    def test_bad_scope_raises_never_silent(self):
        with self.assertRaises(ValueError):
            parts.assert_four_way_agreement(
                scope_id="", single=[], combined=[],
                blended=[], producer=[],
            )

    def test_malformed_hints_raise(self):
        with self.assertRaises(ValueError):
            parts.assert_four_way_agreement(
                scope_id="scope-A", single="hint-a",
                combined=["hint-a"], blended=["hint-a"],
                producer=["hint-a"],
            )


class SlotHintRepair(unittest.TestCase):
    def test_missing_hint_yields_explicit_bind_directive(self):
        out = parts.repair_slot_bindings(
            ["slot-a", "slot-b"], ["slot-a"], scope_id="scope-A"
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["missing"], ["slot-b"])
        self.assertEqual(len(out["directives"]), len(out["missing"]))
        self.assertIn("slot-b", out["directives"][0])
        self.assertIn("never silently drop", out["directives"][0])

    def test_clean_bindings_no_directives(self):
        out = parts.repair_slot_bindings(["slot-a"], ["slot-a"], scope_id="s")
        self.assertTrue(out["ok"])
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["directives"], [])

    def test_undeclared_hints_surfaced(self):
        out = parts.repair_slot_bindings(["slot-a"], ["slot-a", "hint-x"])
        self.assertEqual(out["undeclared"], ["hint-x"])

    def test_malformed_input_raises_never_silent(self):
        with self.assertRaises(ValueError):
            parts.repair_slot_bindings("nope", ["slot-a"])
        with self.assertRaises(ValueError):
            parts.repair_slot_bindings(["slot-a"], "nope")
        with self.assertRaises(ValueError):
            parts.repair_slot_bindings(["", "slot-a"], ["slot-a"])


class D19ReuseNotReimplementation(unittest.TestCase):
    def test_single_decomposition_is_d19(self):
        # Reuse = attribute assignment from the REAL D19 module object (same
        # sys.modules entry "d20_collapse_policy" the parts package loads),
        # so identity proves import-not-reimplement.
        self.assertIs(parts.assert_single_decomposition, cp.assert_single_decomposition)
        src = (_DE / "parts" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn(
            "assert_single_decomposition = _cp.assert_single_decomposition", src
        )
        self.assertNotIn("def assert_single_decomposition", src)
        out = parts.assert_single_decomposition("blend")
        self.assertTrue(out["ok"])
        with self.assertRaises(ValueError):
            parts.assert_single_decomposition(["blend", "planner"])

    def test_slot_hint_check_is_d19(self):
        self.assertIs(
            parts.check_slot_hint_propagation, cp.check_slot_hint_propagation
        )
        out = parts.check_slot_hint_propagation(["slot-a", "slot-b"], ["slot-a"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["missing"], ["slot-b"])


class D02RoundTripRealValidators(unittest.TestCase):
    """scope/seq/goal/conversion-goal survive a REAL D02 round-trip.

    ``emit_bundle_scope_goal`` materializes validated parts into a REAL
    ``envelope_committed.json`` carrier; the REAL ``contracts/schema.py``
    validators (imported, never redefined) accept the emitted bundle AND
    envelope. D02-shape negatives surface as REAL ``(False, errors)``
    results — never silent accepts.
    """

    @classmethod
    def setUpClass(cls):
        # SAME loader name as parts/__init__.py uses internally
        # ("decision_engine_contracts_schema"): sys.modules returns the one
        # schema module object, so identity below proves
        # import-not-reimplement (distinct names would exec a second copy).
        cls.schema = _load(
            "decision_engine_contracts_schema", _DE / "contracts" / "schema.py"
        )
        cls.fixture_path = _DE / "contracts" / "fixtures" / "envelope_committed.json"
        cls.carrier = json.loads(cls.fixture_path.read_text(encoding="utf-8"))

    def _parts(self, n=2, conversion_goal="book a call"):
        return [
            _part(
                part_id=f"part-{i}",
                seq=i,
                scope_id="scope-A",
                goal="onboard new member",
                conversion_goal=conversion_goal,
            )
            for i in range(1, n + 1)
        ]

    def test_validators_are_real_not_redefined(self):
        self.assertIs(parts._de_schema, self.schema)
        src = (_DE / "parts" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("def validate_envelope", src)
        self.assertNotIn("def validate_persona_bundle", src)
        self.assertTrue(callable(self.schema.validate_envelope))
        self.assertTrue(callable(self.schema.validate_persona_bundle))

    def test_fixture_carrier_itself_valid_control(self):
        ok_b, errs_b = self.schema.validate_persona_bundle(
            self.carrier["personaBundle"], company_id=self.carrier.get("companyId")
        )
        self.assertTrue(ok_b, errs_b)
        ok_e, errs_e = self.schema.validate_envelope(self.carrier)
        self.assertTrue(ok_e, errs_e)

    def test_emitted_bundle_and_envelope_validate_true(self):
        out = parts.emit_bundle_scope_goal(self._parts(2))
        ok_b, errs_b = self.schema.validate_persona_bundle(
            out["bundle"], company_id=self.carrier.get("companyId")
        )
        self.assertTrue(ok_b, errs_b)
        ok_e, errs_e = self.schema.validate_envelope(out["envelope"])
        self.assertTrue(ok_e, errs_e)

    def test_scope_seq_goal_provenance_survives(self):
        out = parts.emit_bundle_scope_goal(self._parts(3))
        rows = out["bundle"]["task_personas"]
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3])
        self.assertEqual([r["part"] for r in rows], ["part-1", "part-2", "part-3"])
        for r in rows:
            self.assertIn("scope-A", r["why"])
            self.assertIn("onboard new member", r["why"])
        self.assertEqual(out["bundle"]["conversion_goal"], "book a call")
        self.assertEqual(out["bundle"]["resolved_goal"]["value"], "book a call")

    def test_unresolved_conversion_goal_stays_empty(self):
        out = parts.emit_bundle_scope_goal(self._parts(2, conversion_goal=""))
        self.assertEqual(out["bundle"]["conversion_goal"], "")
        self.assertEqual(out["bundle"]["resolved_goal"]["value"], "")
        ok_b, errs_b = self.schema.validate_persona_bundle(
            out["bundle"], company_id=self.carrier.get("companyId")
        )
        self.assertTrue(ok_b, errs_b)

    def test_fixture_file_never_mutated(self):
        before = self.fixture_path.read_text(encoding="utf-8")
        parts.emit_bundle_scope_goal(self._parts(2))
        after = self.fixture_path.read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_over_ten_cap_is_real_d02_false(self):
        out = parts.emit_bundle_scope_goal(self._parts(11))
        ok_b, errs_b = self.schema.validate_persona_bundle(out["bundle"])
        self.assertFalse(ok_b)
        self.assertTrue(any("exceed" in e for e in errs_b))

    def test_goal_source_drift_is_real_d02_false(self):
        out = parts.emit_bundle_scope_goal(self._parts(2))
        drifted = copy.deepcopy(out["bundle"])
        drifted["goal_source"] = "asked"
        ok_b, errs_b = self.schema.validate_persona_bundle(drifted)
        self.assertFalse(ok_b)

    def test_missing_row_seq_is_real_d02_false(self):
        out = parts.emit_bundle_scope_goal(self._parts(2))
        broken = copy.deepcopy(out["bundle"])
        del broken["task_personas"][0]["seq"]
        ok_b, _ = self.schema.validate_persona_bundle(broken)
        self.assertFalse(ok_b)

    def test_duplicate_row_seq_is_real_d02_false(self):
        out = parts.emit_bundle_scope_goal(self._parts(2))
        broken = copy.deepcopy(out["bundle"])
        broken["task_personas"][1]["seq"] = broken["task_personas"][0]["seq"]
        ok_b, _ = self.schema.validate_persona_bundle(broken)
        self.assertFalse(ok_b)

    def test_bad_propagation_raises_never_silent(self):
        dup = self._parts(2)
        dup[1]["seq"] = dup[0]["seq"]
        with self.assertRaises(ValueError):
            parts.emit_bundle_scope_goal(dup)
        with self.assertRaises(ValueError):
            parts.emit_bundle_scope_goal([])
        with self.assertRaises(ValueError):
            parts.emit_bundle_scope_goal("nope")

    def test_every_part_field_carries_verbatim_on_its_row(self):
        # A26: each caller-supplied part field survives the emit round trip
        # VERBATIM as a row-level extension — not only as prose inside `why`.
        p = _part(
            part_id="part-α1",
            kind="agent_task",
            source="campaign_manifest",
            scope_id="scope:beta/2026",
            goal='send "first touch" —\tnewline-safe',
            conversion_goal="book a call",
            consumed_hints=["hint-a", "hint-b"],
        )
        out = parts.emit_bundle_scope_goal([p])
        row = out["bundle"]["task_personas"][0]
        for key, want in (
            ("part", p["part_id"]),
            ("seq", p["seq"]),
            ("kind", p["kind"]),
            ("source", p["source"]),
            ("scope_id", p["scope_id"]),
            ("goal", p["goal"]),
            ("conversion_goal", p["conversion_goal"]),
            ("consumed_hints", p["consumed_hints"]),
        ):
            self.assertEqual(row[key], want, f"row lost/changed {key}")
        ok_b, errs_b = self.schema.validate_persona_bundle(
            out["bundle"], company_id=self.carrier.get("companyId"))
        self.assertTrue(ok_b, errs_b)

    def test_goal_whitespace_never_coerced(self):
        # spec 8.11: preserve explicit goal values; no silent coercion on the
        # emit path (regression: the bundle-level value was previously
        # .strip()ed while rows kept the raw string).
        out = parts.emit_bundle_scope_goal(
            self._parts(1, conversion_goal="  book a call  "))
        self.assertEqual(out["bundle"]["conversion_goal"], "  book a call  ")
        self.assertEqual(out["bundle"]["resolved_goal"]["value"],
                         "  book a call  ")


if __name__ == "__main__":
    unittest.main()
