"""Regression tests for the layer-8 executor defect (A16 run 7,
2026-10-18): CafExecutor.build() extracted the created workflow's ID
from stats keys the engine CLI never emits ("workflow_id", "id",
"created"[0].id). The REAL contract — utils/workflow_builder.py
WorkflowBuilder.build() stats, printed verbatim by
gohighlevel_cli._emit_build_result under --json — carries created IDs
ONLY in stats["workflow_ids"], a {plan-key: id} map, alongside
workflows_created / steps_saved / triggers_created / errors / notes /
start_time / end_time / api_calls / folder_id.

Lane FIX-EXECUTOR's fake runner emitted the executor's EXPECTED shape,
so the whole suite stayed green while the real seam was broken. These
tests feed the REAL stats shape (copied key-for-key from the builder's
stats dict) through build() with a scripted runner, closing that gap:
any future drift between the CLI's emitted stats and the executor's
extraction fails here, loudly.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from caf_executor import CafExecutor  # noqa: E402

SLUG = "sequence-signature-launch-landing-10"
WF_ID = "1bd5df2d-bc3d-45a8-9070-e525e85a8512"
OTHER_ID = "203052ec-5df8-4e50-a85b-c2df6576cd6e"

PLAN = {
    "folder": "Email Engine — Drafts",
    SLUG: {"name": f"{SLUG} (DRAFT)", "templates": []},
}


def real_stats(workflow_ids, errors=None, notes=None):
    """The builder's stats dict, key-for-key as emitted by the CLI."""
    return {
        "workflows_created": len(workflow_ids),
        "steps_saved": 19 if workflow_ids else 0,
        "triggers_created": len(workflow_ids),
        "errors": errors or [],
        "notes": notes or [],
        "start_time": 1760000000.0,
        "end_time": 1760000012.5,
        "api_calls": 7,
        "workflow_ids": workflow_ids,
        "folder_id": "folder-0001",
    }


class ScriptedRunner:
    """Runner double scripted on the REAL CLI surfaces: build stats
    JSON on stdout, export JSON written to the --out file, QC JSON
    from the bash -c invocation."""

    def __init__(self, build_code, build_stats, qc_code=0):
        self.build_code = build_code
        self.build_stats = build_stats
        self.qc_code = qc_code
        self.calls = []

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        if argv[0] == "bash":
            return (self.qc_code,
                    json.dumps({"rubric": {"weighted_floor": 9.1,
                                           "weighted_ceiling": 9.4}}),
                    "")
        if "build" in argv:
            return (self.build_code, json.dumps(self.build_stats), "")
        if "export" in argv:
            out_path = argv[argv.index("--out") + 1]
            wf_id = argv[argv.index("--workflow-id") + 1]
            Path(out_path).write_text(json.dumps({
                "id": wf_id,
                "status": "draft",
                "triggers": [{"type": "contact_tag",
                              "tag": f"email-engine:{SLUG}"}],
                "workflowData": {
                    "templates": [{"id": "step-1", "type": "email"}],
                    "allowMultiple": False,
                },
            }))
            return (0, "", "")
        raise AssertionError(f"unexpected argv: {argv}")

    def saw(self, verb):
        return any(verb in call for call in self.calls)


def make_executor(runner):
    qc = tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False)
    qc.write("#!/bin/bash\n")
    qc.close()
    return CafExecutor(caf_path="/tmp/caf", runner=runner,
                       qc_script=qc.name)


class RealStatsShapeTests(unittest.TestCase):

    def test_success_extracts_id_and_runs_export_and_qc(self):
        runner = ScriptedRunner(0, real_stats({SLUG: WF_ID}))
        result = make_executor(runner).build(dict(PLAN))
        self.assertEqual(result["workflow_id"], WF_ID)
        self.assertEqual(result["errors"], [])
        self.assertIsNotNone(result["export"])
        self.assertEqual(result["export"]["id"], WF_ID)
        self.assertEqual(result["export"]["status"], "draft")
        self.assertEqual(result["qc_exit_code"], 0)
        self.assertEqual(result["rubric"], 9.1)
        self.assertTrue(runner.saw("export"))

    def test_plan_slug_preferred_when_map_has_other_entries(self):
        runner = ScriptedRunner(
            0, real_stats({SLUG: WF_ID, "some-other-slug": OTHER_ID}))
        result = make_executor(runner).build(dict(PLAN))
        self.assertEqual(result["workflow_id"], WF_ID)

    def test_single_entry_map_fallback(self):
        # If the map is ever keyed by display name instead of plan
        # key, a single created workflow is still unambiguous.
        runner = ScriptedRunner(
            0, real_stats({f"{SLUG} (DRAFT)": WF_ID}))
        result = make_executor(runner).build(dict(PLAN))
        self.assertEqual(result["workflow_id"], WF_ID)
        self.assertTrue(runner.saw("export"))

    def test_multi_entry_no_plan_match_fails_closed(self):
        runner = ScriptedRunner(
            0, real_stats({"slug-a": OTHER_ID, "slug-b": WF_ID}))
        result = make_executor(runner).build(dict(PLAN))
        self.assertIsNone(result["workflow_id"])
        self.assertIsNone(result["export"])
        self.assertFalse(runner.saw("export"))

    def test_failed_build_extracts_shell_id_but_never_exports(self):
        # Run-6 shape: shell created (id present in the map), step-save
        # rejected, CLI exits 1. The ID is now recorded as evidence,
        # but a failed build must never proceed to export/QC.
        stats = real_stats({SLUG: OTHER_ID},
                           errors=["step-save PUT failed (HTTP 400)"])
        runner = ScriptedRunner(1, stats)
        result = make_executor(runner).build(dict(PLAN))
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["workflow_id"], OTHER_ID)
        self.assertEqual(result["errors"],
                         ["step-save PUT failed (HTTP 400)"])
        self.assertIsNone(result["export"])
        self.assertIsNone(result["qc_exit_code"])
        self.assertFalse(runner.saw("export"))

    def test_legacy_top_level_key_still_extracts(self):
        stats = real_stats({})
        stats["workflow_id"] = WF_ID
        runner = ScriptedRunner(0, stats)
        result = make_executor(runner).build(dict(PLAN))
        self.assertEqual(result["workflow_id"], WF_ID)
        self.assertTrue(runner.saw("export"))


if __name__ == "__main__":
    unittest.main()
