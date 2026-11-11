"""thank_you_host.py proofs (harmony issue 6).

Runs Skill 82's real adapter, resolver and validators over Skill 82's own
test fixtures, then feeds the two files the host wrote to Skill 49's real
translator in non-design mode. All data is TEST ONLY.
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SIGLAUNCH = HERE.parent
REPO = HERE.parents[3]
S82 = REPO / "82-signature-thank-you"
S49_SCRIPTS = REPO / "49-signature-funnel" / "scripts"
for p in (SIGLAUNCH, S82 / "scripts", S82 / "tests"):
    sys.path.insert(0, str(p))

import test_event_adapter as ea  # noqa: E402  (module only: its tests are not collected here)
import test_thank_you as tty  # noqa: E402
import thank_you_host as host  # noqa: E402
import validate_thank_you  # noqa: E402

KEY = {"S82_SNAPSHOT_HMAC_KEY": ea.FIXTURE_KEY}
FILES = {host.RESULT_NAME, host.MANIFEST_NAME, host.SNAPSHOT_NAME,
         host.MAP_NAME, host.RENDER_NAME}


def events(*offer_sets):
    return [ea.make_event(f"TEST-EVT-H{i}", ea.ORDER_1, list(o))
            for i, o in enumerate(offer_sets, 1)]


def envelope(snapshot):
    return {"tenant_id": snapshot["tenant_id"], "launch_id": snapshot["launch_id"],
            "contact_ref": "TEST-CONTACT", "entitlement_version": "ev1:" + "a" * 64,
            "entitlements": tty.make_fulfillment(snapshot)}


def snapshot_of(evs, **kw):
    return ea.build_snapshot(evs, journey_ids=ea.JOURNEYS, offer_catalog=ea.OFFERS,
                             revision=ea.LAUNCH["revision"], **kw)


class ThankYouHostTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, KEY)
        p.start()
        self.addCleanup(p.stop)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.out = Path(td.name) / "work"
        self.evs = events(["MAIN-A", "BUMP"], ["U1"])
        self.snap = snapshot_of(self.evs)
        self.env = envelope(self.snap)

    def run_host(self, evs=None, env=None, **kw):
        kw.setdefault("offer_catalog", ea.OFFERS)
        kw.setdefault("revision", ea.LAUNCH["revision"])
        return host.host(self.evs if evs is None else evs,
                         self.env if env is None else env, self.out, **kw)

    def request(self):
        req = json.loads((S49_SCRIPTS / "fixtures" / "page-request.json").read_text())
        req.update(tenant_id=self.snap["tenant_id"], location_id=self.snap["location_id"],
                   launch_id=self.snap["launch_id"], revision=self.snap["revision"],
                   test_only=True)
        return req

    def translate(self):
        (self.out / "page-request.json").write_text(json.dumps(self.request()))
        return subprocess.run(
            [sys.executable, str(S49_SCRIPTS / "translate_thank_you_result.py"),
             str(self.out / "page-request.json"), str(self.out / "page-result.json"),
             str(self.out), "--author-session", "fixture-dispatch-session"],
            capture_output=True, text=True, env={**os.environ, **KEY})

    def test_writes_both_files_and_translator_accepts_them(self):
        written = self.run_host(request=self.request())
        self.assertEqual(set(Path(p).name for p in written.values()), FILES)
        proc = self.translate()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads((self.out / "page-result.json").read_text())
        self.assertEqual(out["status"], "authored")
        self.assertEqual([a["path"] for a in out["artifacts"]], [host.RENDER_NAME])
        man = json.loads((self.out / host.MANIFEST_NAME).read_text())
        self.assertEqual(man["result_ref"], host.RESULT_NAME)
        self.assertEqual(man["provenance"]["map_ref"], host.MAP_NAME)

    def test_map_is_projected_to_paid_entitlements(self):
        env = copy.deepcopy(self.env)
        env["entitlements"]["ghost-entitlement"] = {
            "state": "granted", "delivery_url": None, "next_action": "access"}
        self.run_host(env=env)
        written = json.loads((self.out / host.MAP_NAME).read_text())
        self.assertNotIn("ghost-entitlement", written["entitlements"])
        self.assertEqual(self.translate().returncode, 0)

    def test_tampered_snapshot_after_write_is_refused_by_translator(self):
        self.run_host()
        path = self.out / host.SNAPSHOT_NAME
        path.write_text(path.read_text() + " ")
        proc = self.translate()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("snapshot_sha256", proc.stderr)

    def test_pitch_bearing_view_is_refused_and_nothing_written(self):
        pitched = copy.deepcopy(ea.OFFERS)
        pitched["U1"]["display_name"] = "Upgrade now - one more thing"
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(offer_catalog=pitched)
        self.assertIn("no_pitch_scan", str(cm.exception))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_validator_errors_refuse_and_nothing_written(self):
        with mock.patch.object(validate_thank_you, "validate_thank_you",
                               return_value=["a13_test: unpurchased item shown"]):
            with self.assertRaises(host.HostRefused) as cm:
                self.run_host()
        self.assertIn("a13_test", str(cm.exception))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_edited_snapshot_is_refused_by_resolver(self):
        edited = copy.deepcopy(self.snap)
        edited["line_items"][0]["amount_minor"] = 1
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(evs=edited)
        self.assertIn("snapshot_integrity_failed", str(cm.exception))

    def test_request_identity_mismatch_is_refused(self):
        req = self.request()
        req["tenant_id"] = "SOME-OTHER-TENANT"
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(request=req)
        self.assertIn("identity_mismatch", str(cm.exception))

    def test_request_test_only_flag_mismatch_is_refused_and_nothing_written(self):
        self.assertIs(self.snap["test_only"], True)
        req = self.request()
        req["test_only"] = False
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(request=req)
        self.assertIn("identity: page-request test_only=False", str(cm.exception))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_bare_map_is_refused(self):
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(env=self.env["entitlements"])
        self.assertIn("envelope", str(cm.exception))

    def test_live_event_without_s44_store_is_refused(self):
        live = [ea.live_event()]
        with self.assertRaises(host.HostRefused) as cm:
            self.run_host(evs=live)
        self.assertIn("evidence_store_required", str(cm.exception))

    def test_cli_exit_codes(self):
        d = self.out.parent
        (d / "e.json").write_text(json.dumps(self.evs))
        (d / "m.json").write_text(json.dumps(self.env))
        (d / "c.json").write_text(json.dumps(ea.OFFERS))
        cmd = [sys.executable, str(SIGLAUNCH / "thank_you_host.py"),
               "--snapshot", str(d / "e.json"), "--map", str(d / "m.json"),
               "--out-dir", str(self.out), "--offer-catalog", str(d / "c.json")]
        ok = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **KEY})
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(FILES, {p.name for p in self.out.iterdir()})
        (d / "m.json").write_text(json.dumps(self.env["entitlements"]))
        bad = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **KEY})
        self.assertEqual(bad.returncode, 2)
        self.assertIn("THANK-YOU HOST REFUSED", bad.stderr)


if __name__ == "__main__":
    unittest.main()
