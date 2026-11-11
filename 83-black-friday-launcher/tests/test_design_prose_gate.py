"""Issue 9 enforcement: Skill 83 refuses a design-prose file Skill 45's composer did not write.

A hand-typed design-prose.json (no design_intelligence.sha256), an edited one and one composed against Skill 45
files that have since changed are all refused, at assembly (build_dispatch_config) and again when the run starts
(the check-design-prose step that heads the thank_you chain). A file from shared-utils/signature_launch/design_prose.py
passes. Free and offline.
"""
from __future__ import annotations

import contextlib
import io
import json
import shlex
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "routes"), str(HERE)]

import adapters  # noqa: E402
import substrate  # noqa: E402
from test_adapters_config import Inputs, segments, stamped_checkout  # noqa: E402

HAND_TYPED = {"notes": "bold and gold", "traits": "", "rules_md": "Make it look great. " * 50}


def composed() -> dict:
    module = substrate.load("shared-utils/signature_launch/design_prose.py", "launcher_design_prose")
    return module.compose({}, "A", None, roles=["thank_you"])


class DesignProseGateTests(unittest.TestCase):
    def stage(self, doc, name="design-prose.json") -> Path:
        inputs = Inputs(self)
        path = inputs.root / "work" / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return inputs

    def test_a_composed_file_in_the_dispatch_folder_is_accepted(self):
        inputs = self.stage(composed())
        config = inputs.build()
        first = segments(config["adapters"]["thank_you"]["command"][2])[0]
        self.assertEqual(Path(first[1]).name, "adapters.py")
        self.assertEqual(first[2], "compose-design-prose")

    def test_a_hand_typed_file_in_the_dispatch_folder_is_refused_by_name(self):
        inputs = self.stage(HAND_TYPED)
        with self.assertRaisesRegex(adapters.AdapterError, "AF-DI-PROSE.*no design_intelligence.sha256"):
            inputs.build()

    def test_a_hand_typed_checkout_file_is_refused(self):
        inputs = self.stage(HAND_TYPED, "design-prose-checkout.json")
        with self.assertRaisesRegex(adapters.AdapterError, "AF-DI-PROSE"):
            inputs.build()

    def test_a_named_thank_you_file_that_is_hand_typed_is_refused(self):
        inputs = self.stage(HAND_TYPED, "mine.json")
        with self.assertRaisesRegex(adapters.AdapterError, "thank_you_design_prose: AF-DI-PROSE"):
            inputs.build(thank_you_design_prose=inputs.root / "work" / "mine.json")

    def test_a_composed_file_edited_afterwards_is_refused(self):
        doc = composed()
        doc["rules_md"] += "\nOne more rule typed in by hand."
        with self.assertRaisesRegex(adapters.AdapterError, "edited after it was composed"):
            self.stage(doc).build()

    def test_a_rules_json_block_typed_in_after_composing_is_refused(self):
        doc = composed()
        doc["rules_json"] = '{"typed": "by hand"}'
        with self.assertRaisesRegex(adapters.AdapterError, "edited after it was composed"):
            self.stage(doc).build()

    def test_the_run_step_refuses_a_hand_typed_file_and_passes_a_composed_one(self):
        inputs = self.stage(HAND_TYPED)
        bad = inputs.root / "work" / "design-prose.json"
        self.assertEqual(adapters.main(["check-design-prose", "--file", str(bad)]), 3)
        bad.write_text(json.dumps(composed()), encoding="utf-8")
        self.assertEqual(adapters.main(["check-design-prose", "--file", str(bad)]), 0)
        self.assertEqual(adapters.main(["check-design-prose", "--file", str(bad.with_name("absent.json"))]), 3)

    def test_the_compose_step_fails_closed_with_rc_3_on_a_missing_launch_file_and_exits_0_on_a_valid_one(self):
        inputs = Inputs(self)
        out = inputs.root / "work" / "composed.json"
        argv = ["compose-design-prose", "--style", "A", "--role", "thank_you", "--out", str(out)]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = adapters.main(argv + ["--launch", str(inputs.root / "absent-launch.json")])
        self.assertEqual(rc, 3)
        self.assertIn("FAIL-CLOSED", err.getvalue())
        self.assertFalse(out.exists())
        self.assertEqual(adapters.main(argv + ["--launch", str(inputs.kwargs["launch_record"])]), 0)  # control
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()


class ComposedAtTheLaunchTests(unittest.TestCase):
    """Issue 9: no chain input is operator-staged. The launch composes the design prose itself, appends the run's
    measured design system inside the composer (so the digest covers it), and refuses any later edit."""

    MEASURED = "The measured scale is eight pixels. Headings are set in the brand serif at 56 pixels."

    def built(self, **over):
        inputs = Inputs(self)
        measured = inputs.root / "measured.txt"
        measured.write_text(self.MEASURED, encoding="utf-8")
        config = inputs.build(measured_design_system=measured, **over)
        return inputs, config

    def check(self, path: Path) -> int:
        return adapters.main(["check-design-prose", "--file", str(path)])

    def test_the_build_writes_the_design_prose_with_the_measured_design_system_and_it_passes_the_check(self):
        inputs, _ = self.built()
        path = inputs.root / "work" / "design-prose.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(doc["rules_md"].endswith(self.MEASURED))  # appended inside the composer
        self.assertEqual(doc["design_intelligence"]["roles"], ["thank_you"])
        self.assertEqual(self.check(path), 0)

    def test_the_build_writes_the_checkout_prose_too(self):
        inputs = Inputs(self)
        manuscript, request = stamped_checkout(inputs.root)  # the order form's copy is Skill 79's stamped output (issue 12)
        checkout = {"manuscript": manuscript, "checkout_request": request, "brand_file": inputs.write("b.md"),
                    "brand_owner": "o", "image_cap": 1, "design_style": "B"}
        inputs.build(checkout_design=checkout)
        doc = json.loads((inputs.root / "work" / "design-prose-checkout.json").read_text(encoding="utf-8"))
        self.assertEqual((doc["design_intelligence"]["roles"], doc["design_intelligence"]["style"]), (["checkout"], "B"))
        self.assertEqual(self.check(inputs.root / "work" / "design-prose-checkout.json"), 0)

    def test_an_edit_after_the_launch_appended_the_measured_design_system_is_refused(self):
        inputs, _ = self.built()
        path = inputs.root / "work" / "design-prose.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["rules_md"] += "\nA late measured value, appended without re-stamping."
        path.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.check(path), 3)
        with self.assertRaisesRegex(adapters.AdapterError, "AF-DI-PROSE.*edited after it was composed"):
            adapters._require_design_prose("design-prose.json", path)

    def test_a_hand_written_file_staged_after_the_build_is_replaced_when_the_chain_runs(self):
        inputs, config = self.built()
        path = inputs.root / "work" / "design-prose.json"
        path.write_text(json.dumps(HAND_TYPED), encoding="utf-8")
        self.assertEqual(self.check(path), 3)  # the staged file alone is refused
        steps = segments(config["adapters"]["thank_you"]["command"][2])[:2]  # compose, then check: the chain's head
        script = " && ".join(shlex.join(step) for step in steps)
        run = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotEqual(doc["rules_md"], HAND_TYPED["rules_md"])
        self.assertTrue(doc["rules_md"].endswith(self.MEASURED))
        self.assertEqual(self.check(path), 0)

    def test_a_measured_design_system_that_is_not_a_file_is_refused(self):
        inputs = Inputs(self)
        with self.assertRaisesRegex(adapters.AdapterError, "measured_design_system: no file"):
            inputs.build(measured_design_system=inputs.root / "absent.txt")

    def test_the_real_launch_path_hands_the_measured_design_system_to_the_build(self):
        from launcher_core import launch_bridge  # noqa: PLC0415
        seen = {}
        adapter_inputs = {"bridge_config": "b", "author_session": "s", "copy": {}, "journey": {}, "enrichment": {},
                          "measured_design_system": "m.txt"}
        image_inputs = {"brand_file": "f", "brand_owner": "o", "image_cap": 1, "design_style": "A",
                        "executor_provider": "stub", "allow_paid": False}
        with self.assertRaisesRegex(launch_bridge.BridgeError, "never staged by hand"):  # issue 12 refusal stays
            launch_bridge._bind_adapters(adapters, {**adapter_inputs, "checkout_manuscript": "c.md"}, Path("out"),
                                         Path("l.json"), image_inputs, Path("i.json"), Path("o.json"))
        # The order form's copy now comes from Skill 79's emitter (proven in test_checkout_manuscript_emitted), so the
        # request file and the emitter are the two seams stood in for here; the measured design system is what is checked.
        with mock.patch.object(adapters, "build_dispatch_config", lambda **kw: seen.update(kw) or {"adapters": {}}), \
                mock.patch.object(adapters, "emit_checkout_manuscript", lambda **kw: Path(kw["out"])), \
                mock.patch.object(launch_bridge, "_checkout_request_file",
                                  lambda out_dir, launch_path: Path(out_dir) / "checkout-request.json"):
            launch_bridge._bind_adapters(adapters, adapter_inputs, Path("out"), Path("l.json"), image_inputs,
                                         Path("i.json"), Path("o.json"))
        self.assertEqual(seen["measured_design_system"], "m.txt")
