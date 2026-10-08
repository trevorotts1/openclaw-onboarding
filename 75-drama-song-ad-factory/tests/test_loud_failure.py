"""No silent failure: a failing gate must show up in the receipt (empty HOME safe)."""
import os
import sys
import tempfile
import unittest

CORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "core")
for sub in ("", "batch_mode", "final_assembler", "cc_sync"):
    sys.path.insert(0, os.path.normpath(os.path.join(CORE, sub)))

import loud_failure  # noqa: E402


class LoudFailure(unittest.TestCase):
    def setUp(self):
        loud_failure.reset()

    def test_failure_flips_ok_receipt_and_is_named(self):
        r = loud_failure.attach({"outcome": "ok", "reason_code": "ASSEMBLED"})
        self.assertEqual(r["outcome"], "ok")
        loud_failure.fail("GATE_BROKE", "face check could not run")
        r = loud_failure.attach({"outcome": "ok", "reason_code": "ASSEMBLED"})
        self.assertEqual(r["outcome"], "error")
        self.assertEqual(r["failures"][0]["code"], "GATE_BROKE")
        self.assertIn("face check could not run", r["next_action"])

    def test_warning_stays_ok_but_is_listed(self):
        loud_failure.warn("COMMAND_CENTER_UNREACHABLE", "board down")
        r = loud_failure.attach({"outcome": "ok"})
        self.assertEqual(r["outcome"], "ok")
        self.assertEqual(r["warnings"][0]["code"], "COMMAND_CENTER_UNREACHABLE")

    def test_real_gate_unreadable_brief_reaches_receipt(self):
        from batch_mode import isolation
        missing = os.path.join(tempfile.mkdtemp(), "nope.json")
        isolation._read_brief({"brief": missing})
        r = loud_failure.attach({"outcome": "ok"})
        self.assertEqual(r["outcome"], "error")
        self.assertEqual(r["failures"][0]["code"], "BRIEF_UNREADABLE")

    def test_cc_sync_outage_prints_warning_in_receipt(self):
        import cc_sync
        def down(method, path, payload):
            raise cc_sync.TransportOutage("down")
        ob = cc_sync.Outbox(":memory:", workspace="w", sender=down)
        ob.enqueue_create("job1", "Show", [{"slug": "s1"}], "w")
        ob.flush()
        r = loud_failure.attach({"outcome": "ok"})
        self.assertEqual(r["outcome"], "ok")
        self.assertEqual(r["warnings"][0]["code"], "COMMAND_CENTER_UNREACHABLE")


if __name__ == "__main__":
    unittest.main()
