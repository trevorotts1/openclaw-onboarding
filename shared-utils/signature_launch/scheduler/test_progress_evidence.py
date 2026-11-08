"""F15 checks: evidence-derived completion, reports, atomic ledger updates.

Run: python3 shared-utils/signature_launch/scheduler/test_progress_evidence.py
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH = HERE.parent
ROOT = HERE.parents[2]
SHARED = ROOT / "shared-utils"
PROGRESS_FILE = LAUNCH / "progress.py"
REPORT_FILE = LAUNCH / "experience" / "launch_progress_report.py"

for path in (str(HERE), str(LAUNCH)):
    if path not in sys.path:
        sys.path.insert(0, path)

import model  # noqa: E402
import progress  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADMISSION = _load("f15_admission", LAUNCH / "admission.py")
REPORT = _load("f15_launch_progress_report", REPORT_FILE)

PLAN = {
    "launch_id": "f15-lane",
    "pages": [
        {"id": "page_a", "kind": "landing", "url": "https://example.invalid/a",
         "waits_for": []},
        {"id": "page_b", "kind": "sales", "url": "https://example.invalid/b",
         "waits_for": ["page_a"]},
        {"id": "page_c", "kind": "other", "url": "https://example.invalid/c",
         "waits_for": []},
    ],
    "email_sequences": [], "text_sets": [], "automations": [],
}


def ok(record, unit, paid=1):
    return model.envelope(
        model.VERIFIED_SUCCESS,
        evidence=ADMISSION.evidence(
            unit, record["plan_hash"],
            [ADMISSION.artifact("artifacts/%s.html" % unit, sha256="a" * 64)],
            inputs={"plan": record["plan_hash"]},
            revision=str(paid)))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.record = progress.new_progress(PLAN, clock=lambda: "2030-01-01T00:00:00Z")

    def _done(self, unit):
        progress.claim(self.record, unit, "owner-a")
        progress.complete(self.record, unit, ok(self.record, unit), owner="owner-a")

    def test_evidence_for_an_older_revision_cannot_resurrect_it(self):
        self._done("page_a")
        ADMISSION.invalidate(self.record, ["page_a"], kind="copy")
        unit = self.record["units"]["page_a"]
        self.assertEqual((unit["state"], unit["verified"], unit["revision"]),
                         ("pending", False, 2))
        report = progress.recover_report(self.record, evidence={
            "page_a": ADMISSION.evidence(
                "page_a", self.record["plan_hash"],
                [ADMISSION.artifact("artifacts/page_a.html", sha256="a" * 64)],
                inputs={"plan": self.record["plan_hash"]}, revision="1")})
        self.assertEqual(report["recovered"], [])
        self.assertEqual(self.record["units"]["page_a"]["state"], "pending")
        self.assertIn("revision", report["rejected"][0]["detail"])

    def test_complete_and_mark_refuse_old_revision_evidence(self):
        self._done("page_a")
        ADMISSION.invalidate(self.record, ["page_a"], kind="copy")
        stale = ADMISSION.evidence(
            "page_a", self.record["plan_hash"],
            [ADMISSION.artifact("artifacts/page_a.html", sha256="a" * 64)],
            inputs={"plan": self.record["plan_hash"]}, revision="1")
        progress.claim(self.record, "page_a", "owner-a")
        progress.complete(self.record, "page_a",
                          model.envelope(model.VERIFIED_SUCCESS, evidence=stale),
                          owner="owner-a")
        unit = self.record["units"]["page_a"]
        self.assertEqual((unit["state"], unit["verified"]), ("failed", False))
        self.assertIn("revision", unit["result"]["detail"])

        progress.claim(self.record, "page_a", "owner-a")
        with self.assertRaises(progress.ProgressError):
            progress.mark(self.record, "page_a", "done", owner="owner-a", evidence=stale)

    def test_a_done_flag_without_current_evidence_is_not_delivered(self):
        self._done("page_a")
        self.record["units"]["page_b"]["state"] = "done"
        self.record["units"]["page_b"]["verified"] = True
        view = progress.trusted_delivered(self.record)
        self.assertEqual(view["delivered_units"], ["page_a"])
        self.assertEqual(view["excluded"]["unverified_completion"], ["page_b"])
        self.assertEqual(view["percent"], 33.33)
        self.assertEqual(progress.percent(self.record), 33.33)

    def test_caller_percentage_is_recomputed_from_evidence(self):
        self._done("page_a")
        self.record["percent"] = 100
        progress.save(self.record, self.dir / "p.json")
        restored = progress.load(self.dir / "p.json")
        self.assertEqual(restored["percent"], 33.33)
        self.assertEqual(restored["counts"]["delivered"], 1)
        self.assertEqual(restored["counts"]["unverified_completion"], 0)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.record = progress.new_progress(PLAN, clock=lambda: "2030-01-01T00:00:00Z")

    def _done(self, unit, deployment="not_deployed"):
        progress.claim(self.record, unit, "owner-a")
        progress.complete(self.record, unit, ok(self.record, unit), owner="owner-a")
        self.record["units"][unit]["deployment"] = deployment

    def test_five_stages_are_distinct(self):
        plan = dict(PLAN)
        plan["pages"] = PLAN["pages"] + [
            {"id": "page_r", "kind": "other", "url": "https://example.invalid/r",
             "waits_for": []},
            {"id": "page_d", "kind": "other", "url": "https://example.invalid/d",
             "waits_for": []},
        ]
        record = progress.new_progress(plan, clock=lambda: "2030-01-01T00:00:00Z")
        for unit, deploy in (("page_a", "observed"), ("page_b", "draft_installed"),
                             ("page_c", "not_deployed")):
            progress.claim(record, unit, "owner-a")
            progress.complete(record, unit, ok(record, unit), owner="owner-a")
            record["units"][unit]["deployment"] = deploy
        record["units"]["page_c"]["review"] = {"ok": True}
        record["units"]["page_r"].update({"artifact": "design/page_r.pdf",
                                          "review_required": True})
        record["units"]["page_d"]["artifact"] = "artifacts/page_d.html"
        doc = progress.report(record)
        stages = {row["id"]: row["stage"] for row in doc["units"]}
        self.assertEqual(stages, {"page_a": "live", "page_b": "installed",
                                  "page_c": "approved",
                                  "page_r": "design_ready_for_review",
                                  "page_d": "draft_created"})
        text = REPORT.render(doc, shape="table")
        for phrase in ("live", "installed", "approved", "design ready for review",
                       "draft created"):
            self.assertIn(phrase, text.lower())

    def test_projection_is_the_same_facts_as_the_report(self):
        self._done("page_a")
        doc = progress.report(self.record)
        projected = REPORT.projection(doc)
        self.assertEqual(projected["percent"], doc["percent"])
        self.assertEqual(projected["delivered"], doc["delivered"])
        self.assertEqual(projected["required"], doc["required"])
        self.assertEqual([row["id"] for row in projected["units"]],
                         [row["id"] for row in doc["units"]])
        self.assertEqual(projected["event"]["percent"], doc["percent"])
        self.assertFalse(projected["editable"])

    def test_report_generation_never_dispatches_or_touches_bytes(self):
        artifact = Path(tempfile.mkdtemp(dir="/tmp", prefix="operator-BLD-002-")) / "p.html"
        artifact.write_text("built", encoding="utf-8")
        self.addCleanup(lambda: artifact.unlink(missing_ok=True))
        self.record["units"]["page_a"]["artifact"] = str(artifact)
        before = artifact.stat().st_mtime_ns
        REPORT.render(progress.report(self.record), shape="lines")
        self.assertEqual(artifact.stat().st_mtime_ns, before)


class AtomicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.file = self.dir / "progress.json"
        plan = self.dir / "plan.json"
        plan.write_text(json.dumps(PLAN), encoding="utf-8")
        subprocess.run([sys.executable, str(PROGRESS_FILE), "init", "--plan",
                        str(plan), "--file", str(self.file)],
                       check=True, capture_output=True, text=True)
        subprocess.run([sys.executable, str(PROGRESS_FILE), "claim", "--file",
                        str(self.file), "--unit", "page_a", "--owner", "owner-x"],
                       check=True, capture_output=True, text=True)

    def test_heartbeat_release_and_mark_are_lock_serialised(self):
        for name in ("heartbeat_atomic", "release_atomic", "mark_atomic"):
            self.assertTrue(callable(getattr(progress, name)), name)

        ready = threading.Event()

        def hold():
            with progress._locked(self.file):
                ready.set()
                time.sleep(1.0)

        thread = threading.Thread(target=hold)
        thread.start()
        self.assertTrue(ready.wait(timeout=5))
        child = subprocess.Popen(
            [sys.executable, str(PROGRESS_FILE), "release", "--file", str(self.file),
             "--unit", "page_a", "--owner", "owner-x"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.3)
        self.assertIsNone(child.poll(), "release wrote while the ledger lock was held")
        thread.join(timeout=10)
        out, err = child.communicate(timeout=10)
        self.assertEqual(child.returncode, 0, err or out)
        self.assertEqual(progress.load(self.file)["units"]["page_a"]["state"], "pending")

    def test_a_late_attempt_cannot_release_a_newer_unit(self):
        record = progress.load(self.file)
        progress.release(record, "page_a", "owner-x")
        progress.claim(record, "page_a", "owner-x")
        self.assertEqual(record["units"]["page_a"]["attempts"], 2)
        self.assertFalse(progress.release(record, "page_a", "owner-x",
                                          attempt=1)["released"])
        self.assertEqual(record["units"]["page_a"]["state"], "running")


if __name__ == "__main__":
    unittest.main()
