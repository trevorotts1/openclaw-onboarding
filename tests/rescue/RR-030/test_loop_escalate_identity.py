#!/usr/bin/env python3
"""tests/rescue/RR-030/test_loop_escalate_identity.py   (RR plan fix F17)

Skill 61 must name the box by its canonical fleet slug, never a hostname.
  1. FLEET_STANDING_BOX_SLUG=test-box  -> payload boxName == box == 'test-box';
     clientName falls back to the slug, or FLEET_STANDING_CLIENT_LABEL when set.
  2. A hostname-shaped `box` argument is replaced by the slug.
  3. install.sh with no slug set (no --box)        -> refuses, exit 4, nothing installed.
  4. install.sh with a hostname-shaped --box       -> refuses, exit 4.
  5. install.sh with FLEET_STANDING_BOX_SLUG set   -> gets past the identity step
     (stops at the sandboxed --no-cron path; ledger meta box == slug).
Offline: no network, no openclaw binary, sandboxed state dirs.
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "61-loop-protection-system"
sys.path.insert(0, str(SKILL / "scripts"))

def _clean_env(**extra):
    e = {k: v for k, v in os.environ.items()
         if k not in ("FLEET_STANDING_BOX_SLUG", "RR_BOX_SLUG", "FLEET_STANDING_CLIENT_LABEL",
                      "LOOP_OPENCLAW_ROOT", "LOOP_STATE_DIR")}
    e.update(extra)
    return e

class Identity(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        for k in ("FLEET_STANDING_BOX_SLUG", "RR_BOX_SLUG", "FLEET_STANDING_CLIENT_LABEL"):
            os.environ.pop(k, None)
        self.td = tempfile.TemporaryDirectory(prefix="rr030-id-")
        os.environ["LOOP_OPENCLAW_ROOT"] = self.td.name       # no real openclaw.json is read
        os.environ["LOOP_STATE_DIR"] = os.path.join(self.td.name, "lp")
        import importlib, loop_identity, loop_escalate
        importlib.reload(loop_identity); importlib.reload(loop_escalate)
        self.esc = loop_escalate

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._saved); self.td.cleanup()

    def _payload(self, box):
        return self.esc.build_payload(box=box, loop_class="LP-B1", finding="f", evidence_path="p",
                                      proposed_fix="x", why="y", action_needed="z")

    def test_slug_env_sets_boxname_and_clientname(self):
        os.environ["FLEET_STANDING_BOX_SLUG"] = "test-box"
        p = self._payload("Jennifers-Mini.lan")
        self.assertEqual(p["boxName"], "test-box"); self.assertEqual(p["box"], "test-box")
        self.assertEqual(p["machine"]["box"], "test-box")
        self.assertEqual(p["clientName"], "test-box")
        self.assertEqual(p["message"], p["finding"])          # RR-SENDER-FIX field kept

    def test_client_label_used_when_set(self):
        os.environ["FLEET_STANDING_BOX_SLUG"] = "test-box"
        os.environ["FLEET_STANDING_CLIENT_LABEL"] = "TEST Client Co"
        self.assertEqual(self._payload("test-box")["clientName"], "TEST Client Co")

    def test_rr_box_slug_fallback(self):
        os.environ["RR_BOX_SLUG"] = "rr-slug-box"
        self.assertEqual(self._payload("Mac.fios-router.home")["boxName"], "rr-slug-box")

    def test_openclaw_json_fallback(self):
        Path(self.td.name, "openclaw.json").write_text(
            json.dumps({"env": {"vars": {"FLEET_STANDING_BOX_SLUG": "json-box"}}}))
        self.assertEqual(self._payload("x.local")["boxName"], "json-box")

    def test_explicit_good_box_kept_without_env(self):
        self.assertEqual(self._payload("box-example")["boxName"], "box-example")

    def test_hostname_shapes_refused(self):
        import loop_identity as li
        for bad in ("Mac.fios-router.home", "Jennifers-Mini.lan", "x.local", "a1b2c3d4e5f6",
                    "", "TBD", "unknown", "N/A", "box"):
            self.assertIsNotNone(li.problem(bad), bad)
        for good in ("test-box", "vps-janet-pinkney", "rescue-karen-vaughn", "oc-sheila"):
            self.assertIsNone(li.problem(good), good)

def _install(*args, **env):
    td = tempfile.mkdtemp(prefix="rr030-inst-")
    e = _clean_env(LOOP_OPENCLAW_ROOT=td + "/oc", LOOP_STATE_DIR=td + "/lp", LOOP_ALLOW_ROOT="1", **env)
    os.makedirs(td + "/oc", exist_ok=True)
    r = subprocess.run(["bash", str(SKILL / "install.sh"), "--no-cron", *args],
                       env=e, capture_output=True, text=True, timeout=120)
    return r, td

class InstallIdentity(unittest.TestCase):
    def test_refuses_with_nothing_set(self):
        r, td = _install()
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stderr)
        self.assertFalse(os.path.exists(td + "/lp/loop.db"), "ledger created despite refusal")

    def test_refuses_hostname_shaped_box_arg(self):
        r, td = _install("--box", "Jennifers-Mini.lan")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(td + "/lp/loop.db"))

    def test_accepts_slug_from_env(self):
        r, td = _install(FLEET_STANDING_BOX_SLUG="test-box")
        self.assertNotEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(td + "/lp/loop.db"), r.stdout + r.stderr)
        import sqlite3
        c = sqlite3.connect(td + "/lp/loop.db")
        self.assertEqual(c.execute("select value from meta where key='box'").fetchone()[0], "test-box")

if __name__ == "__main__":
    unittest.main(verbosity=2)
