"""S44-08 timing comparator proofs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from timing import compare_timing

CONTRACT = {
    "slug": "nurture", "allow_multiple": True,
    "waits": [{"step": "wait-3d", "mode": "duration",
               "offset_seconds": 259200, "timezone": "America/New_York",
               "past_due": "send_immediately"}],
}
EXPORT = {
    "allowMultiple": True,
    "steps": [{"name": "send-1", "type": "email"},
              {"name": "wait-3d", "type": "wait",
               "duration_seconds": 259200}],
}


class TimingTests(unittest.TestCase):
    def test_unverifiable_fields_are_not_called_ok(self):
        out = compare_timing(CONTRACT, EXPORT)
        # duration matches; timezone/past-due are not echoed by this
        # export, so the verdict must say so, not claim a full match
        self.assertEqual(out["verdict"], "MATCH_WITH_UNVERIFIABLE_FIELDS")
        tz = next(f for f in out["fields"]
                  if f["field"] == "wait:wait-3d:timezone")
        self.assertEqual(tz["ok"], "UNVERIFIABLE")

    def test_offset_drift_is_a_mismatch(self):
        export = {"allowMultiple": True, "steps": [
            {"name": "wait-3d", "type": "wait", "duration_seconds": 86400}]}
        out = compare_timing(CONTRACT, export)
        self.assertEqual(out["verdict"], "MISMATCH")

    def test_reentry_drift_is_a_mismatch(self):
        export = dict(EXPORT, allowMultiple=False)
        out = compare_timing(CONTRACT, export)
        self.assertEqual(out["verdict"], "MISMATCH")
        f = next(x for x in out["fields"] if x["field"] == "allow_multiple")
        self.assertEqual((f["expected"], f["observed"]), (True, False))

    def test_event_anchored_wait_never_degrades_to_duration(self):
        contract = {"slug": "w", "allow_multiple": False, "waits": [
            {"step": "wait-cart", "mode": "event_anchored",
             "offset_seconds": 3600, "timezone": "UTC",
             "past_due": "skip"}]}
        # an API export that claims a duration for it is a mismatch
        export = {"allowMultiple": False, "steps": [
            {"name": "wait-cart", "type": "wait",
             "duration_seconds": 3600}]}
        out = compare_timing(contract, export)
        self.assertEqual(out["verdict"], "MISMATCH")
        # and with no API step, the lane routing is the expected state
        out2 = compare_timing(contract,
                              {"allowMultiple": False, "steps": []})
        lane = next(f for f in out2["fields"]
                    if f["field"] == "wait:wait-cart:lane")
        self.assertTrue(lane["ok"])

    def test_undeclared_export_wait_is_a_mismatch(self):
        export = {"allowMultiple": True, "steps": [
            {"name": "wait-3d", "type": "wait", "duration_seconds": 259200},
            {"name": "wait-secret", "type": "wait",
             "duration_seconds": 60}]}
        out = compare_timing(CONTRACT, export)
        self.assertEqual(out["verdict"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
