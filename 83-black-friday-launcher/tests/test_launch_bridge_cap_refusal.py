"""F8 on the launcher path: launch_bridge.run() calls Skill 49's dispatch() as a library, so an image cap
below what the page set needs must be refused up front and named AF-LAUNCH-BRIDGE-DISPATCH, not run (the
free stub ran every page past the cap) and not escape as a traceback. Free: the fake consumer answers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_lane83_dispatch import payload, run_dispatch  # noqa: E402  (also puts the skill root on sys.path)
from launcher_core import launch_bridge  # noqa: E402


_SPOOL = {}


def setUpModule():
    # Building a package appends launch events to ~/.openclaw/data/signature-launch/events-spool when no ingest
    # URL is set. Send them to a temp folder, so nothing in this module (or in a child launcher it starts,
    # which inherits the variable) writes into the real home folder.
    _SPOOL["dir"] = tempfile.TemporaryDirectory()
    _SPOOL["env"] = mock.patch.dict(os.environ, {"LAUNCH_EVENTS_SPOOL": _SPOOL["dir"].name})
    _SPOOL["env"].start()


def tearDownModule():
    _SPOOL["env"].stop()
    _SPOOL["dir"].cleanup()


class ACapBelowThePlanIsRefusedThroughTheBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "run"

    def test_a_one_image_cap_is_named_and_nothing_is_built(self):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            run_dispatch(payload("elevation", image_cap=1), self.out)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-BRIDGE-DISPATCH")
        self.assertIn("smaller than this launch needs", ctx.exception.detail)
        self.assertIn("Nothing was started", ctx.exception.detail)
        self.assertEqual(list((self.out / "dispatch").glob("result-*.json")), [])
        self.assertEqual(list((self.out / "pieces").glob("*.json")) if (self.out / "pieces").is_dir() else [], [])

    def test_the_default_cap_still_builds_every_page(self):
        report = run_dispatch(payload("elevation"), self.out)
        self.assertIn("checkout", report["pages"])


if __name__ == "__main__":
    unittest.main()
