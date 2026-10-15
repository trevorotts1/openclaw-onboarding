"""Static evidence record comparison tests (MG-043, D-EVIDENCE-REWRITE).

Drives the compiled TypeScript helper (runtime/tests/evidence-record.ts)
through its scenario CLI and pins both directions of the MG-043
static-record pattern:

- lenient about run bookkeeping only: wall-clock keys (generatedAt,
  probedAt, lockTimestamp), ISO timestamps embedded in prose, and
  absolute paths that differ only in the checkout prefix (including a
  foreign worktree's prefix, and paths inside error messages);
- strict about everything else: a changed measurement, a changed hash,
  or a missing key must produce a diff that names the field.

Requires the runtime package to be built (npm run build); skips with an
explicit reason when dist is absent, so a bare Python run never reports
this coverage as a silent pass. The fast gate (tests/ci/run-fast-gate.sh)
builds before running the Python suite.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
HELPER = SKILL_ROOT / "runtime" / "dist" / "tests" / "evidence-record.js"
REPO_ROOT = "/home/tester/checkout"


def compare(record: dict, derived: dict) -> dict:
    scenario = {"record": record, "derived": derived, "repoRoot": REPO_ROOT}
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False
    ) as handle:
        json.dump(scenario, handle)
        scenario_path = handle.name
    try:
        out = subprocess.run(
            ["node", str(HELPER), scenario_path],
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        Path(scenario_path).unlink(missing_ok=True)
    return json.loads(out.stdout)


BASE = {
    "item": "MG-006",
    "generatedAt": "2026-10-14T05:29:45.496Z",
    "runtime": {"engineVersion": "4.0.535", "lockTimestamp": "2026-10-14T05:18:24.404Z"},
    "proof": {"widths": [480, 720, 1200], "fraction": 0.42},
    "video": {"path": REPO_ROOT + "/shared-utils/motion-render-runtime/.runtime/x/final.mp4", "sha256": "abc123"},
}


@unittest.skipUnless(HELPER.exists(), "runtime not built: npm run build in runtime/ first")
class EvidenceRecordComparisonTests(unittest.TestCase):
    def test_identical_records_match(self):
        result = compare(BASE, dict(BASE))
        self.assertTrue(result["ok"], result)

    def test_volatile_keys_and_prose_timestamps_are_bookkeeping(self):
        derived = json.loads(json.dumps(BASE))
        derived["generatedAt"] = "2027-01-01T00:00:00.000Z"
        derived["runtime"]["lockTimestamp"] = "2027-01-01T00:00:00.000Z"
        derived["note"] = "probe recorded at 2027-01-01T00:00:00.000Z sharp"
        record = json.loads(json.dumps(BASE))
        record["note"] = "probe recorded at 2026-10-14T05:29:45.496Z sharp"
        result = compare(record, derived)
        self.assertTrue(result["ok"], result)

    def test_checkout_prefix_only_difference_matches(self):
        record = json.loads(json.dumps(BASE))
        record["video"]["path"] = (
            "/home/other/workspace/wt-mg006/shared-utils/motion-render-runtime/.runtime/x/final.mp4"
        )
        record["message"] = (
            "Job at /home/other/wt/72-motion-video-plus/tests failed validation"
        )
        derived = json.loads(json.dumps(BASE))
        derived["message"] = "Job at " + REPO_ROOT + "/72-motion-video-plus/tests failed validation"
        result = compare(record, derived)
        self.assertTrue(result["ok"], result)

    def test_changed_measurement_fails_and_names_the_field(self):
        derived = json.loads(json.dumps(BASE))
        derived["proof"]["widths"] = [481, 720, 1200]
        result = compare(BASE, derived)
        self.assertFalse(result["ok"])
        self.assertTrue(any("$.proof.widths[0]" in d for d in result["diffs"]), result)

    def test_changed_hash_fails(self):
        derived = json.loads(json.dumps(BASE))
        derived["video"]["sha256"] = "def456"
        result = compare(BASE, derived)
        self.assertFalse(result["ok"])

    def test_missing_key_fails(self):
        derived = json.loads(json.dumps(BASE))
        del derived["proof"]["fraction"]
        result = compare(BASE, derived)
        self.assertFalse(result["ok"])
        self.assertTrue(any("fraction" in d for d in result["diffs"]), result)


if __name__ == "__main__":
    unittest.main()
