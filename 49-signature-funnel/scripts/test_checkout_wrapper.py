#!/usr/bin/env python3
"""checkout_wrapper.py tests: dispatch's checkout request through the REAL Skill 71 pipeline.

Stages S49's own dispatch emission (compile_launch_route, dispatch_launch.build_requests) over the
fixture launch, then runs the wrapper as the checkout adapter command with the stub provider (no
network, no paid call). Proves:
  * the run is admitted through shared_page_service.py and the intake records page_role checkout
    and the client's design style;
  * the three design stages build from the checkout manuscript on the five-section structure and
    produce desktop and mobile wireframes plus desktop and mobile mockups (20 images);
  * the placed page-result validates against collect_launch_receipts.validate_result, is capped at
    authored / L0, has no native binding, and names the native-form and stub blockers;
  * the adapter's own command (launch-adapters.example.json, no --model) runs to a valid result
    once the staged design-prose-checkout.json is in the work dir, and the wrapper refuses without it;
  * fail-closed, with no result left behind: a request for another role, a missing manuscript, a
    manuscript that names card fields, a section-count mismatch.

Run: python3 test_checkout_wrapper.py [-v]
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402
import dispatch_launch as dispatch_mod  # noqa: E402
import collect_launch_receipts as receipts  # noqa: E402
from test_landing_bridge import fixture_launch, dump  # noqa: E402

REPO = HERE.parents[1]
S71 = REPO / "71-blackceo-signature-page"
WRAPPER = HERE / "checkout_wrapper.py"
MANUSCRIPT = S71 / "tests" / "fixtures" / "copy_examples" / "checkout-example.md"
BRAND_RAW = (S71 / "assets" / "brand" / "blackceo-brand.json").read_bytes()


class CheckoutWrapperCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s49-checkout-wrapper-")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.td, ignore_errors=True))
        launch, _approval = fixture_launch()
        launch["brand_hash"] = hashlib.sha256(BRAND_RAW).hexdigest()
        graph = clr.compile_route(launch)
        launch["route_graph_hash"] = clr.graph_hash(graph)
        requests = {r["page_role"]: r for r in dispatch_mod.build_requests(
            launch, graph, copy_profile="standard", allowed_write_target="local_only")}
        self.request = requests["checkout"]
        self.launch_path = self.td / "launch.json"
        self.launch_path.write_bytes(dump(launch))
        self.request_path = self.td / "request-checkout.json"
        self.request_path.write_bytes(dump(self.request))
        self.graph_path = self.td / "route-graph.json"
        self.graph_path.write_bytes(clr.serialize_graph(graph))
        self.brand_path = self.td / "brand-src.json"
        self.brand_path.write_bytes(BRAND_RAW)
        self.result_path = self.td / "result-checkout.json"
        self.run_dir = self.td / "checkout-run"

    def wrap(self, request_path=None, manuscript=MANUSCRIPT, extra=()):
        cmd = [sys.executable, str(WRAPPER), "--request", str(request_path or self.request_path),
               "--result", str(self.result_path), "--manuscript", str(manuscript),
               "--launch", str(self.launch_path), "--route-graph", str(self.graph_path),
               "--brand-file", str(self.brand_path), "--brand-owner", "blackceo",
               "--image-cap", "2", "--run-dir", str(self.run_dir), "--model", "STUB-NO-MODEL", *extra]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


class TestEndToEnd(CheckoutWrapperCase):
    def test_wrapper_builds_the_checkout_design_stages_through_skill_71(self):
        proc = self.wrap(extra=("--design-style", "C"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts.validate_result(result, self.request), [])
        self.assertEqual((result["status"], result["proof_class"]), ("authored", "L0"))
        self.assertIsNone(result["native_bindings_ref"])
        self.assertFalse(result["independent_review"])
        self.assertTrue(any("Skill 06" in b for b in result["blockers"]))
        self.assertTrue(any("stub provider" in b for b in result["blockers"]))
        intake = json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))
        self.assertEqual(intake["launch"]["page_role"], "checkout")
        self.assertEqual(intake["design_style"], "C")
        names = [Path(a["path"]).relative_to(self.run_dir).as_posix() for a in result["artifacts"]]
        for stage in ("desktop-wireframe", "mobile-tablet"):
            self.assertEqual(sorted(n for n in names if n.startswith(f"{stage}/section-")),
                             [f"{stage}/section-0{i}.png" for i in range(1, 6)])
        for platform in ("desktop", "mobile"):
            self.assertEqual(sorted(n for n in names if n.startswith(f"visual-mockup/{platform}/")),
                             [f"visual-mockup/{platform}/part-0{i}.png" for i in range(1, 6)])
        for stage in ("desktop-wireframe", "mobile-tablet", "visual-mockup"):
            built = json.loads((self.run_dir / f"production-request-{stage}.json").read_text(encoding="utf-8"))
            self.assertEqual([s["section_id"] for s in built["sections"]], list("12345"))
            self.assertEqual(built["page_role"], "checkout")
        for a in result["artifacts"]:
            self.assertEqual(hashlib.sha256(Path(a["path"]).read_bytes()).hexdigest(), a["sha256"])


class TestFailClosed(CheckoutWrapperCase):
    def refused(self, proc, text):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(text, proc.stderr)
        self.assertFalse(self.result_path.exists())

    def test_a_stale_result_is_removed_when_the_run_is_refused(self):
        self.result_path.write_text("{}")
        self.refused(self.wrap(manuscript=self.td / "nope.md"), "manuscript")

    def test_request_for_another_role_is_refused(self):
        other = dict(self.request, page_role="landing", assigned_skill=71)
        path = self.td / "request-landing.json"
        path.write_bytes(dump(other))
        self.refused(self.wrap(request_path=path), "serves 'checkout'")

    def test_manuscript_naming_card_fields_is_refused(self):
        bad = self.td / "bad.md"
        bad.write_text(MANUSCRIPT.read_text(encoding="utf-8").replace(
            "Enter your details below", "Enter your card number and CVC below"), encoding="utf-8")
        self.refused(self.wrap(manuscript=bad), "native checkout form only")

    def test_a_landing_shaped_manuscript_fails_the_section_count(self):
        landing = S71 / "tests" / "fixtures" / "copy_examples" / "standard-path-b.md"
        self.refused(self.wrap(manuscript=landing), "5 canonical sections")
        self.assertFalse(any((self.run_dir / "desktop-wireframe").glob("*.png")))


def measured_design_prose(chars=14500):
    """Unique pseudo-sentences standing in for a run's measured design system (the size of a real one)."""
    syl = ["ba", "ke", "lo", "mi", "su", "ta", "ve", "zo", "ri", "na"]
    words = [a + b + c + d for a in syl for b in syl for c in syl for d in syl]
    text, state = [], 7
    while sum(len(t) + 1 for t in text) < chars:
        sentence = []
        for _ in range(12):
            state = (state * 1103515245 + 12345) % 2147483648
            sentence.append(words[state % len(words)])
        text.append(" ".join(sentence) + ".")
    return {"rules_md": "\n".join(text)}


class TestAdapterCommand(CheckoutWrapperCase):
    """Runs the checkout adapter command exactly as launch-adapters.example.json spells it: no --model."""

    def adapter_cmd(self):
        raw = json.loads((HERE.parent / "launch-adapters.example.json").read_text(encoding="utf-8"))
        subs = {"{request}": self.request_path, "{result}": self.result_path, "{work_dir}": self.td,
                "/path/to/49-signature-funnel": HERE.parent, "/path/to/71-blackceo-signature-page": S71,
                "<approved brand file>": self.brand_path, "<recorded brand owner>": "blackceo",
                "<image cap>": "2", "<A|B|C>": "C"}
        cmd = []
        for arg in raw["adapters"]["checkout"]["command"]:
            for key, value in subs.items():
                arg = arg.replace(key, str(value))
            cmd.append(arg)
        self.assertNotIn("--model", cmd)
        self.assertIn("--design-prose", cmd)
        (self.td / "copy-checkout.md").write_text(MANUSCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        return cmd

    def test_adapter_command_with_staged_design_prose_and_no_model_succeeds(self):
        (self.td / "design-prose-checkout.json").write_text(json.dumps(measured_design_prose()), encoding="utf-8")
        proc = subprocess.run(self.adapter_cmd(), capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(self.result_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts.validate_result(result, self.request), [])
        self.assertEqual(len([a for a in result["artifacts"] if "/visual-mockup/" in a["path"] and a["path"].endswith(".png")]), 10)

    def test_adapter_command_without_the_staged_design_prose_fails_closed(self):
        proc = subprocess.run(self.adapter_cmd(), capture_output=True, text=True, timeout=600)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("design-prose-checkout.json", proc.stderr)
        self.assertFalse(self.result_path.exists())


if __name__ == "__main__":
    unittest.main()
