#!/usr/bin/env python3
"""Unit tests for shared-utils/fab_artifact.py — the FAB-artifact PRODUCER (D4 closure).

Proves the producer normalises a REAL build result (funnel pages / automation workflow export)
into the build/fab-artifact.json shape the FAB-QC scorer reads, that emit() does not clobber an
existing artifact, and — end-to-end — that a produced automation artifact is actually scoreable by
fab_qc (so qc-built-workflow.sh --fab genuinely fires on a real build instead of a hand fixture).

Run:
    python3 tests/unit/fab-artifact.test.py
    or: pytest tests/unit/fab-artifact.test.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
assert _SHARED.is_dir(), f"shared-utils not found at {_SHARED}"
sys.path.insert(0, str(_SHARED))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fab_artifact = _load("fab_artifact")
fab_qc = _load("fab_qc")


class TestFunnelProducer(unittest.TestCase):
    def test_copy_taken_from_build_pages(self):
        task = {"funnel_template_id": "squeeze-page",
                "template_match": {"decision": "USE_TEMPLATE", "matched_template": "squeeze-page"},
                "pages": [{"name": "Opt-In"}, {"name": "Thank You"}]}
        build = {"pages": [{"name": "Opt-In", "copy": {"hero": "Real headline copy goes here today"}},
                           {"name": "Thank You", "copy": {"cta": "Check your inbox for the link now"}}]}
        art = fab_artifact.build_funnel_artifact(task, build)
        self.assertEqual(art["kind"], "funnel")
        self.assertEqual(art["funnel_template_id"], "squeeze-page")
        self.assertEqual(art["flex_decision"], "USE_TEMPLATE")
        self.assertEqual(len(art["pages"]), 2)
        self.assertIn("Real headline", art["pages"][0]["copy"]["hero"])

    def test_assembles_copy_from_loose_fields_and_blocks(self):
        build = {"pages": [{"name": "Home", "headline": "Big promise here for you",
                            "blocks": [{"type": "cta", "text": "Buy now and save big today"}]}]}
        art = fab_artifact.build_funnel_artifact({}, build)
        copy = art["pages"][0]["copy"]
        self.assertEqual(copy["headline"], "Big promise here for you")
        self.assertEqual(copy["cta"], "Buy now and save big today")

    def test_falls_back_to_plan_copy_when_build_page_bare(self):
        task = {"pages": [{"name": "Opt-In", "copy": {"hero": "Plan-level copy survived to artifact"}}]}
        build = {"pages": [{"name": "Opt-In", "preview_url": "u", "marker": "m"}]}  # no copy
        art = fab_artifact.build_funnel_artifact(task, build)
        self.assertIn("Plan-level copy", art["pages"][0]["copy"]["hero"])


class TestAutomationProducer(unittest.TestCase):
    def _export(self, bodies):
        return {"steps": [{"type": "EMAIL", "subject": f"Subject {i}", "body": b}
                          for i, b in enumerate(bodies)]
                + [{"type": "WAIT", "delay": "1 day"}]}  # wait node carries no copy -> dropped

    def test_steps_and_copy_from_export(self):
        export = self._export(["Welcome aboard, here is what happens next for you today",
                               "Day two: the story behind why we built this whole thing"])
        art = fab_artifact.build_automation_artifact(export, {"matched_template_id": "soap-opera",
                                                              "flex_decision": "USE_TEMPLATE"})
        self.assertEqual(art["kind"], "automation")
        self.assertEqual(len(art["steps"]), 2)          # WAIT dropped
        self.assertEqual(art["steps"][0]["channel"], "email")
        self.assertIn("Welcome aboard", art["steps"][0]["copy"])
        self.assertIn("Subject 0", art["steps"][0]["copy"])

    def test_nested_attributes_copy(self):
        export = {"actions": [{"type": "SMS", "attributes": {"message": "Quick text from a friend here now"}}]}
        art = fab_artifact.build_automation_artifact(export, {})
        self.assertEqual(art["steps"][0]["channel"], "sms")
        self.assertIn("Quick text", art["steps"][0]["copy"])


class TestEmit(unittest.TestCase):
    def test_emit_writes_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as d:
            r1 = fab_artifact.emit(d, {"kind": "funnel", "pages": [{"copy": {"a": "x"}}]})
            self.assertTrue(r1["emitted"])
            self.assertTrue(Path(d, "build", "fab-artifact.json").is_file())
            # second emit must NOT clobber
            r2 = fab_artifact.emit(d, {"kind": "funnel", "pages": []})
            self.assertFalse(r2["emitted"])
            art = json.load(open(Path(d, "build", "fab-artifact.json")))
            self.assertEqual(len(art["pages"]), 1)      # original survived
            # overwrite=True clobbers
            r3 = fab_artifact.emit(d, {"kind": "funnel", "pages": []}, overwrite=True)
            self.assertTrue(r3["emitted"])


class TestEndToEndAutomationScoreable(unittest.TestCase):
    """The whole D4 point: a produced automation artifact is scoreable by fab_qc — so the
    --fab overlay fires on a real build, not a hand fixture."""

    def test_produced_artifact_is_scored_by_fab_qc(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "routing").mkdir()
            # a real-ish template with a 2-step sequence + the matched receipt + persona log
            tmpl = {"sequence": [{"channel": "email"}, {"channel": "email"}],
                    "copy_persona": {"primary": "Russell Brunson"}, "source_books": ["DotCom Secrets"]}
            (root / "routing" / "matched-template.json").write_text(json.dumps(tmpl))
            (root / "routing" / "match-decision.json").write_text(json.dumps({
                "matched_template_id": "soap-opera", "template_path": "matched-template.json",
                "intent_mode": "HANDS_OFF_DO_IT_ALL", "flex_decision": "USE_TEMPLATE"}))
            (root / "persona-selection-log.md").write_text("selected_persona: russell-brunson\n")
            (root / "qc").mkdir()
            (root / "qc" / "wf-checklist.json").write_text(json.dumps(
                {"items": [{"id": "WF-3", "status": "PASS"}, {"id": "WF-7", "status": "PASS"}]}))
            export = {"steps": [
                {"type": "EMAIL", "subject": "Welcome", "body": "Welcome aboard, here is exactly what happens next today"},
                {"type": "EMAIL", "subject": "Day two", "body": "The story behind why we built this whole thing for you"}]}
            wf_path = root / "export.json"
            wf_path.write_text(json.dumps(export))

            # PRODUCER: emit the artifact from the export (this is what qc-built-workflow.sh --fab does)
            rc = fab_artifact.main(["--evidence", str(root), "--kind", "automation",
                                    "--workflow", str(wf_path), "--quiet"])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "build" / "fab-artifact.json").is_file())

            # SCORER: fab_qc reads the produced artifact and scores it (>= 8.5, real copy)
            inp = fab_qc.load_inputs_from_evidence(str(root), "automation")
            self.assertEqual(len(inp["artifact"]["steps"]), 2)
            res = fab_qc.grade(inp)
            self.assertTrue(res["passed"], res)
            self.assertGreaterEqual(res["score"], 8.5)

    def test_thin_produced_artifact_fails_d2(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "routing").mkdir()
            tmpl = {"sequence": [{"channel": "email"}], "copy_persona": {"primary": "Brunson"}}
            (root / "routing" / "matched-template.json").write_text(json.dumps(tmpl))
            (root / "routing" / "match-decision.json").write_text(json.dumps({
                "matched_template_id": "x", "template_path": "matched-template.json",
                "intent_mode": "HANDS_OFF_DO_IT_ALL", "flex_decision": "USE_TEMPLATE"}))
            (root / "persona-selection-log.md").write_text("selected_persona: brunson\n")
            (root / "qc").mkdir()
            (root / "qc" / "wf-checklist.json").write_text(json.dumps({"items": [{"id": "WF-3", "status": "PASS"}]}))
            export = {"steps": [{"type": "EMAIL", "subject": "TBD", "body": "[BODY]"}]}  # placeholder
            wf_path = root / "export.json"
            wf_path.write_text(json.dumps(export))
            fab_artifact.main(["--evidence", str(root), "--kind", "automation",
                               "--workflow", str(wf_path), "--quiet"])
            inp = fab_qc.load_inputs_from_evidence(str(root), "automation")
            res = fab_qc.grade(inp)
            self.assertFalse(res["passed"])
            self.assertIn("D2 Copy substance", res["hard_misses"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
