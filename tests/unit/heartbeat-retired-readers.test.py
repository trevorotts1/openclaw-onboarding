#!/usr/bin/env python3
"""Heartbeat readers on OpenClaw 2026.11.5+ (FRF-005).

OpenClaw 2026.11.5 retired heartbeat config: `openclaw doctor --fix` moves each
monitor into an automation job and deletes agents.defaults.heartbeat from
openclaw.json. Readers must treat the missing key on that build as "retired",
never as drift or failure. A box still on 2026.11.4 or earlier keeps the old
behavior: a heartbeat key that disappears there is real drift.

Hermetic: temp dirs only, no openclaw call, no live config.
Run: python3 tests/unit/heartbeat-retired-readers.test.py -v
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EWS = REPO / "60-zhc-early-warning-system" / "scripts"
sys.path.insert(0, str(EWS))
import ews_baseline as B  # noqa: E402
import ews_common as C  # noqa: E402
import ews_sentinel as S  # noqa: E402

HB_PATHS = ("agents.defaults.heartbeat.every", "agents.defaults.heartbeat.model")


def cfg(version=None, heartbeat=True):
    defaults = {"model": {"primary": "ollama-cloud/glm-5.2:cloud",
                          "fallbacks": ["ollama-cloud/minimax-m3:cloud"]}}
    if heartbeat:
        defaults["heartbeat"] = {"every": "6h", "model": "ollama-cloud/glm-5.2:cloud"}
    c = {"agents": {"defaults": defaults},
         "models": {"providers": {"ollama-cloud": {}}}}
    if version:
        c["meta"] = {"lastTouchedVersion": version}
    return c


class HeartbeatRetiredReaders(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._env = {k: os.environ.get(k)
                     for k in ("EWS_STATE_DIR", "EWS_CONFIG_PATH", "EWS_OPENCLAW_ROOT")}
        os.environ["EWS_OPENCLAW_ROOT"] = str(self.tmp)  # never read a real ~/.openclaw
        os.environ["EWS_STATE_DIR"] = str(self.tmp / "ews")
        os.environ["EWS_CONFIG_PATH"] = str(self.tmp / "openclaw.json")
        # pinned while the box was on 2026.11.4, heartbeat block present
        self.baseline = B.build_baseline(cfg("2026.11.4"))

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def diff(self, live):
        return {d["path"]: d for d in B.compute_diff(self.baseline, live)}

    # -- version detection -------------------------------------------------
    def test_version_gate(self):
        self.assertTrue(C.heartbeat_retired(cfg("2026.11.5")))
        self.assertTrue(C.heartbeat_retired(cfg("2027.1.0")))
        self.assertFalse(C.heartbeat_retired(cfg("2026.11.4")))
        self.assertFalse(C.heartbeat_retired(cfg()))  # unknown version is never retired

    # -- EWS baseline diff (S1/S4/S10 engine + the companion audit) ---------
    def test_missing_heartbeat_on_2026_11_5_is_retired_not_drift(self):
        d = self.diff(cfg("2026.11.5", heartbeat=False))
        for p in HB_PATHS:
            self.assertEqual(d[p]["direction"], "retired", d[p])
            self.assertFalse(d[p]["changed"], d[p])
            self.assertFalse(d[p]["dangerous"], d[p])

    def test_missing_heartbeat_on_2026_11_4_is_still_drift(self):
        d = self.diff(cfg("2026.11.4", heartbeat=False))
        for p in HB_PATHS:
            self.assertEqual(d[p]["direction"], "removed", d[p])
            self.assertTrue(d[p]["changed"], d[p])

    def test_retired_gate_never_hides_other_removed_keys(self):
        live = cfg("2026.11.5", heartbeat=False)
        del live["agents"]["defaults"]["model"]
        d = self.diff(live)
        self.assertEqual(d["agents.defaults.model.primary"]["direction"], "removed")
        self.assertTrue(d["agents.defaults.model.primary"]["changed"])

    # -- EWS sentinel S5 ----------------------------------------------------
    def test_s5_is_quiet_when_heartbeat_retired(self):
        sig = C.load_signatures()
        billing = C.load_skill_config("billing-models.json")
        f = S.sig_s5(cfg("2026.11.5", heartbeat=False), [], billing, "client", sig=sig)
        self.assertEqual(f, [])

    # -- scripts/verify-model-pins.py ---------------------------------------
    def test_verify_model_pins_clean_without_heartbeat_block(self):
        p = self.tmp / "pins.json"
        p.write_text(json.dumps(cfg("2026.11.5", heartbeat=False)))
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "verify-model-pins.py"),
                            "--config", str(p), "--json"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertFalse([x for x in out["fatal"] + out["warnings"] if "heartbeat" in x["where"]], out)


if __name__ == "__main__":
    unittest.main()
