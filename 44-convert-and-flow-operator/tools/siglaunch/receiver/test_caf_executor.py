"""CafExecutor proofs against recorded CLI transcripts (fake runner).

The transcripts mirror the engine's REAL output contracts, verified
against the installed CLI's --help surface (2026-10-17): doctor text
verdicts + exit codes; build stats JSON on stdout under the top-level
--json option with `--experimental ... build --from-plan`; the export
read-back written to the `--out` FILE by `workflows export
--workflow-id/--out` (native shape: name/workflowData.templates); the
AC20 snapshot from `caf --json workflows list` (JSON array payload);
and per-build QC from the skill-root qc-built-workflow.sh (exit code +
rubric.weighted_floor in its --json output) — there is no `workflows
qc` verb. No live engine is touched.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from caf_executor import CafExecutor

DOCTOR_PASS = (0, "PASS doctor: adapter healthy; contract probe OK.", "")
DOCTOR_TOKEN_WARN = (0, "", "WARN doctor: Firebase token absent or dead "
                            "(token_health). Reads are unaffected...")
DOCTOR_UNCONFIGURED = (0, "", "WARN doctor: GoHighLevel credentials/"
                              "location not configured — probe skipped.")
DOCTOR_FAIL = (1, "", "FAIL doctor: contract drift or hard failure "
                      "(builder_step). Workflow writes are degraded...")

# With the top-level --json option the build stats land on stdout.
BUILD_OK = (0, json.dumps({
    "workflow_id": "wf-123", "errors": [], "notes": [],
    "workflows_created": 1}), "")

# Native export shape (what `workflows export --out` writes): the
# workflow definition rides in workflowData.templates; the trigger is
# a step node, not a top-level triggers list.
NATIVE_EXPORT = {
    "id": "wf-123",
    "name": "Welcome",
    "status": "draft",
    "allowMultiple": False,
    "workflowData": {
        "templates": [
            {"id": "t1", "type": "tagAdded",
             "tag": "siglaunch:purchased:main"},
            {"id": "s1", "type": "EMAIL", "name": "Welcome email"},
            {"id": "s2", "type": "WAIT"},
        ],
    },
}

QC_OK = (0, json.dumps({
    "workflow_id": "wf-123", "overall_mechanical": "PASS",
    "rubric": {"weighted_floor": 9.35, "weighted_ceiling": 9.9,
               "ship_threshold": 8.5}}), "")


def _classify(argv):
    """Key a fake-runner call on the subcommand actually invoked,
    not on argv positions (top-level options precede the group)."""
    if argv[:2] == ["bash", "-c"]:
        return "qc"
    if "doctor" in argv:
        return "doctor"
    if "workflows" in argv:
        rest = argv[argv.index("workflows") + 1:]
        for sub in ("build", "export", "list"):
            if sub in rest:
                return sub
    return None


def scripted_runner(script):
    calls = []

    def run(argv, timeout):
        calls.append(list(argv))
        handler = script[_classify(argv)]
        if callable(handler):
            return handler(argv)
        return handler

    run.calls = calls
    return run


def export_writes(payload):
    """Fake `workflows export`: writes the export JSON to the --out
    path, exactly like the real command, and returns clean streams."""
    def _run(argv):
        out_path = argv[argv.index("--out") + 1]
        Path(out_path).write_text(json.dumps(payload))
        return (0, "", "")
    return _run


class CafExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # A stand-in QC script FILE (existence is all the adapter
        # checks; the fake runner never executes it).
        self.qc_path = Path(self.tmp.name) / "qc-built-workflow.sh"
        self.qc_path.write_text("# fake qc script for tests\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_classification(self):
        cases = [
            (DOCTOR_PASS, "healthy"),
            (DOCTOR_TOKEN_WARN, "absent-or-dead"),
            (DOCTOR_UNCONFIGURED, "absent"),
            (DOCTOR_FAIL, "degraded"),
            ((0, "total garbage", ""), "degraded"),  # unknown = fail-closed
        ]
        for transcript, expected in cases:
            ex = CafExecutor(runner=lambda a, t, tr=transcript: tr)
            self.assertEqual(ex.probe()["token_state"], expected,
                             f"transcript {transcript!r}")

    def test_build_round_trip(self):
        script = {
            "build": BUILD_OK,
            "export": export_writes(NATIVE_EXPORT),
            "qc": QC_OK,
        }
        runner = scripted_runner(script)
        ex = CafExecutor(runner=runner, qc_script=str(self.qc_path))
        res = ex.build({"folder": "F", "welcome": {"name": "W"}})
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["workflow_id"], "wf-123")
        self.assertEqual(res["export"]["id"], "wf-123")
        self.assertEqual(res["export_raw"], NATIVE_EXPORT)
        self.assertEqual(res["qc_exit_code"], 0)
        self.assertEqual(res["rubric"], 9.35)
        # build argv: top-level --json/--experimental BEFORE the
        # workflows group; the plan goes through --from-plan
        build_call = next(c for c in runner.calls
                          if _classify(c) == "build")
        wf_at = build_call.index("workflows")
        self.assertEqual(build_call[1:wf_at], ["--json", "--experimental"])
        self.assertEqual(build_call[wf_at + 1], "build")
        self.assertIn("--from-plan", build_call)
        # the export was queried by the id the build actually returned,
        # with an --out file path (no stdout read-back, no --json flag)
        export_call = next(c for c in runner.calls
                           if _classify(c) == "export")
        self.assertEqual(
            export_call[export_call.index("--workflow-id") + 1], "wf-123")
        self.assertIn("--out", export_call)
        self.assertNotIn("--json", export_call)
        # QC ran through bash -c with the script path, the workflow id,
        # and --json (so the rubric can be parsed mechanically)
        qc_call = next(c for c in runner.calls if _classify(c) == "qc")
        self.assertIn("qc-built-workflow.sh", qc_call[2])
        self.assertIn("wf-123", qc_call[2])
        self.assertIn("--json", qc_call[2])

    def test_build_unparseable_is_failure(self):
        script = {"build": (1, "", "boom: traceback")}
        ex = CafExecutor(runner=scripted_runner(script),
                         qc_script=str(self.qc_path))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        self.assertEqual(res["exit_code"], 1)
        self.assertIsNone(res["workflow_id"])
        self.assertIn("unparseable", res["errors"][0])

    def test_export_failure_blocks_success(self):
        script = {
            "build": BUILD_OK,
            "export": (1, "", "export exploded"),
        }
        ex = CafExecutor(runner=scripted_runner(script),
                         qc_script=str(self.qc_path))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        self.assertIsNone(res["export"])
        self.assertTrue(any("read-back" in e for e in res["errors"]))

    def test_export_normalization_native_shape(self):
        script = {
            "build": BUILD_OK,
            "export": export_writes(NATIVE_EXPORT),
            "qc": QC_OK,
        }
        ex = CafExecutor(runner=scripted_runner(script),
                         qc_script=str(self.qc_path))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        exp = res["export"]
        self.assertEqual(exp["id"], "wf-123")
        self.assertEqual(exp["status"], "draft")
        self.assertEqual(exp["allowMultiple"], False)
        # steps come from workflowData.templates, passed through raw
        self.assertEqual(exp["steps"],
                         NATIVE_EXPORT["workflowData"]["templates"])
        # the tagAdded trigger step normalizes to contact_tag + tag
        self.assertEqual(exp["triggers"], [
            {"type": "contact_tag", "tag": "siglaunch:purchased:main"}])

    def test_export_normalization_top_level_triggers(self):
        payload = {
            "status": "draft",
            "triggers": [{"id": "t9", "type": "form_submitted"}],
            "steps": [{"id": "s1", "type": "EMAIL"}],
            "allowMultiple": True,
        }
        script = {
            "build": BUILD_OK,
            "export": export_writes(payload),
            "qc": QC_OK,
        }
        ex = CafExecutor(runner=scripted_runner(script),
                         qc_script=str(self.qc_path))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        exp = res["export"]
        # no id anywhere in the export: falls back to the build's id
        self.assertEqual(exp["id"], "wf-123")
        self.assertEqual(exp["triggers"], [{"type": "form_submitted"}])
        self.assertEqual(exp["steps"], payload["steps"])
        self.assertEqual(exp["allowMultiple"], True)

    def test_qc_unavailable_is_recorded_not_faked(self):
        # caf_path in an isolated tree whose derived skill root
        # (parents[2] of the caf file) holds no qc-built-workflow.sh
        # -> honest unavailable note, no fabricated pass
        with tempfile.TemporaryDirectory() as other:
            caf_path = str(Path(other) / "x" / "y" / "caf")
            script = {
                "build": BUILD_OK,
                "export": export_writes(NATIVE_EXPORT),
            }
            runner = scripted_runner(script)
            ex = CafExecutor(caf_path=caf_path, runner=runner)
            res = ex.build({"folder": "F", "w": {"name": "W"}})
            self.assertIsNone(res["qc_exit_code"])
            self.assertIsNone(res["rubric"])
            self.assertTrue(any("qc surface unavailable" in n
                                for n in res["notes"]))
            # and no QC invocation was attempted against a missing script
            self.assertFalse(any(_classify(c) == "qc"
                                 for c in runner.calls))

    def test_snapshot_list_round_trip(self):
        payload = [{"id": "wf-1", "status": "draft"},
                   {"id": "wf-2", "status": "published"}]
        runner = scripted_runner({"list": (0, json.dumps(payload), "")})
        snap_dir = str(Path(self.tmp.name) / "snaps")
        ex = CafExecutor(runner=runner, snapshot_dir=snap_dir)
        self.assertTrue(ex.snapshot("LOC1", "welcome"))
        files = list(Path(snap_dir).glob("LOC1-welcome-*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text()), payload)
        # list argv: top-level --json, then the workflows group
        self.assertEqual(runner.calls[0][1:],
                         ["--json", "workflows", "list"])

    def test_snapshot_failure_is_false(self):
        snap_dir = str(Path(self.tmp.name) / "snaps")
        runner = scripted_runner({"list": (1, "", "boom")})
        ex = CafExecutor(runner=runner, snapshot_dir=snap_dir)
        self.assertFalse(ex.snapshot("LOC1", "welcome"))
        # exit 0 but no JSON value anywhere: unreadable = abort
        runner2 = scripted_runner({"list": (0, "not json at all", "")})
        ex2 = CafExecutor(runner=runner2, snapshot_dir=snap_dir)
        self.assertFalse(ex2.snapshot("LOC1", "welcome"))

    def test_dependencies_against_ledger(self, tmp=None):
        with tempfile.TemporaryDirectory() as d:
            ledger = Path(d) / "ledger.json"
            ledger.write_text(json.dumps({
                "LOC1": {"tags": ["siglaunch:purchased:main"],
                         "fields": [], "products": []}}))
            ex = CafExecutor(runner=lambda a, t: (0, "", ""),
                             provisioning_ledger=str(ledger))
            wf = {"requires": {"tags": ["siglaunch:purchased:main",
                                        "siglaunch:purchased:bump"]}}
            self.assertEqual(ex.dependencies_present("LOC1", wf),
                             ["tag:siglaunch:purchased:bump"])
            self.assertEqual(ex.dependencies_present("LOC1", {}), [])
            # no ledger configured = unverifiable, reported as missing
            ex2 = CafExecutor(runner=lambda a, t: (0, "", ""))
            missing = ex2.dependencies_present("LOC1", wf)
            self.assertEqual(len(missing), 1)
            self.assertIn("cannot be verified", missing[0])


if __name__ == "__main__":
    unittest.main()
