import os
import tempfile
import unittest

from fakes import K, MODEL, make, std_routes

REQ = {"model": MODEL, "input": {"prompt": "a leaf", "resolution": "1K"}}


class Modes(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def test_shadow_never_submits(self):
        a, tr, c = make(self.tmp, std_routes(), mode="shadow")
        for fn in (lambda: a.cmd_submit(REQ), lambda: a.cmd_run(REQ, self.tmp)):
            r = fn()
            self.assertEqual(r["state"], "skipped")
            self.assertTrue(r["fallback_used"])
            self.assertIn("shadow: dispatch via existing static path", r["warnings"])
        self.assertEqual(tr.n("POST", "createTask"), 0)
        self.assertEqual(tr.n("GET", "recordInfo"), 0)

    def test_shadow_diagnostics_still_run(self):
        a, tr, c = make(self.tmp, std_routes(), mode="shadow")
        self.assertEqual(a.cmd_validate(MODEL, REQ["input"])["state"], "validated")
        self.assertEqual(a.cmd_discover("image")["state"], "success")
        self.assertEqual(a.cmd_schema(MODEL)["state"], "success")
        self.assertTrue(os.listdir(os.path.join(self.tmp, "cache", "receipts")))

    def test_off_never_submits_and_makes_no_calls(self):
        a, tr, c = make(self.tmp, std_routes(), mode="off")
        r = a.cmd_submit(REQ)
        self.assertEqual((r["state"], r["fallback_used"]), ("skipped", False))
        self.assertIn("adapter off: use static path", r["warnings"])
        self.assertEqual(a.cmd_run(REQ, self.tmp)["state"], "skipped")
        self.assertEqual(tr.calls, [])
        self.assertEqual(a.cmd_validate(MODEL, REQ["input"])["state"], "validated")  # diagnostics allowed

    def test_active_submits(self):
        a, tr, c = make(self.tmp, std_routes(), mode="active")
        r = a.cmd_submit(REQ)
        self.assertEqual((r["state"], r["task_id"]), ("queued", "T1"))
        self.assertEqual(tr.n("POST", "createTask"), 1)

    def test_dry_run_never_submits_even_active(self):
        a, tr, c = make(self.tmp, std_routes(), mode="active")
        r = a.cmd_submit(REQ, dry_run=True)
        self.assertEqual(r["state"], "validated")
        self.assertEqual(tr.n("POST", "createTask"), 0)

    def test_default_is_shadow_and_bad_value_falls_back(self):
        a = K.Adapter(env={"HOME": self.tmp})
        self.assertEqual(a.mode, "shadow")
        b = K.Adapter(env={"HOME": self.tmp, "KIE_LIVE_ADAPTER_MODE": "turbo"})
        self.assertEqual(b.mode, "shadow")
        self.assertTrue(b.warnings)

    def test_mode_file_precedence(self):
        oc = os.path.join(self.tmp, "oc")
        os.makedirs(oc)
        with open(os.path.join(oc, "kie-live-adapter-mode.conf"), "w") as f:
            f.write("active\n")
        self.assertEqual(K.Adapter(env={"HOME": self.tmp, "OC_CONFIG": oc}).mode, "active")
        self.assertEqual(K.Adapter(env={"HOME": self.tmp, "OC_CONFIG": oc, "KIE_LIVE_ADAPTER_MODE": "off"}).mode, "off")
        self.assertEqual(K.Adapter(env={"HOME": self.tmp, "OC_CONFIG": os.path.join(oc, "openclaw.json")}).mode, "active")

    def test_validation_failure_in_active_blocks(self):
        a, tr, c = make(self.tmp, std_routes(), mode="active")
        self.assertEqual(a.cmd_submit({"model": MODEL, "input": {"resolution": "1K"}})["state"], "fail")
        self.assertEqual(tr.n("POST", "createTask"), 0)


if __name__ == "__main__":
    unittest.main()
