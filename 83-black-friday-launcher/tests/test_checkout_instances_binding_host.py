"""Issue 31 (WP-17b): Skill 83 is the first host of Skill 78's binding validator.

checkout_instances.build reaches Skill 78 only through emit_binding_plan.emit_plan; that function runs
validate_selection_binding.validate_plan on the plan it returns. These cases drive the real 83 path
(not a copy of it) and fail if the validator stops being reached or its refusal stops being carried.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checkout_instances  # noqa: E402
from test_checkout_instances import COMMERCIAL, prepared  # noqa: E402


class BindingValidatorHostTests(unittest.TestCase):
    def test_build_runs_the_s78_binding_validator_on_the_plan_it_returns(self):
        normalized, graph, launch = prepared("multiple_options")
        emit = checkout_instances._s78("emit_binding_plan")
        with mock.patch.object(emit, "validate_plan", wraps=emit.validate_plan) as spy:
            built = checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        spy.assert_called_once()
        self.assertEqual(spy.call_args.args[0], built["binding_plan"])
        self.assertEqual(built["violations"], [])

    def test_folded_levels_reaches_it_too(self):
        # 83 passes the launch through; the per-offer route is judged on its targets, whatever the journey
        normalized, graph, launch = prepared("folded_levels")
        emit = checkout_instances._s78("emit_binding_plan")
        with mock.patch.object(emit, "validate_plan", wraps=emit.validate_plan) as spy:
            checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        spy.assert_called_once()

    def test_a_validator_refusal_surfaces_as_a_checkout_instance_error_with_its_code(self):
        normalized, graph, launch = prepared("multiple_options")
        emit = checkout_instances._s78("emit_binding_plan")
        refusal = emit.Violation("S78-SELECTION-PRICE-DRIFT", "drift found by the binding validator")
        with mock.patch.object(emit, "validate_plan", side_effect=refusal):
            with self.assertRaises(checkout_instances.CheckoutInstanceError) as ctx:
                checkout_instances.build(normalized, graph, launch, COMMERCIAL)
        self.assertEqual(ctx.exception.code, "S78-SELECTION-PRICE-DRIFT")


if __name__ == "__main__":
    unittest.main()
