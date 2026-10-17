"""CafExecutor proofs against recorded CLI transcripts (fake runner).

The transcripts mirror the engine's real output contracts (doctor text
verdicts + exit codes; build stats JSON; export read-back; QC JSON).
No live engine is touched.
"""
import json
import sys
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

BUILD_OK = (0, "", json.dumps({
    "workflow_id": "wf-123", "errors": [], "notes": [],
    "workflows_created": 1}))
EXPORT_OK = (0, json.dumps({
    "id": "wf-123", "status": "draft",
    "triggers": [{"id": "t1", "type": "contact_tag"}],
    "steps": [{"id": "s1"}, {"id": "s2"}], "allowMultiple": True}), "")
QC_OK = (0, json.dumps({"rubric": 9.2}), "")


def scripted_runner(script):
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        key = tuple(argv[1:3]) if len(argv) > 2 else (argv[1],)
        return script[key]

    run.calls = calls
    return run


class CafExecutorTests(unittest.TestCase):
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
            ("workflows", "build"): BUILD_OK,
            ("workflows", "export"): EXPORT_OK,
            ("workflows", "qc"): QC_OK,
        }
        runner = scripted_runner(script)
        ex = CafExecutor(runner=runner)
        res = ex.build({"folder": "F", "welcome": {"name": "W"}})
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["workflow_id"], "wf-123")
        self.assertEqual(res["export"]["id"], "wf-123")
        self.assertEqual(res["qc_exit_code"], 0)
        self.assertEqual(res["rubric"], 9.2)
        # the export was queried by the id the build actually returned
        export_call = next(c for c in runner.calls if "export" in c)
        self.assertIn("wf-123", export_call)

    def test_build_unparseable_is_failure(self):
        script = {("workflows", "build"): (1, "", "boom: traceback")}
        ex = CafExecutor(runner=scripted_runner(script))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        self.assertEqual(res["exit_code"], 1)
        self.assertIsNone(res["workflow_id"])
        self.assertIn("unparseable", res["errors"][0])

    def test_export_failure_blocks_success(self):
        script = {
            ("workflows", "build"): BUILD_OK,
            ("workflows", "export"): (1, "", "export exploded"),
        }
        ex = CafExecutor(runner=scripted_runner(script))
        res = ex.build({"folder": "F", "w": {"name": "W"}})
        self.assertIsNone(res["export"])
        self.assertTrue(any("read-back" in e for e in res["errors"]))

    def test_dependencies_against_ledger(self, tmp=None):
        import tempfile
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
