#!/usr/bin/env python3
"""A62 clause 4 round trip: an explicit mode survives install/update.

THE DEFECT THIS LOCKS (UND-062, settled 2026-09-27 at 44f272fa)
  A62's fourth clause — "Explicit modes survive install/update" — was
  UNSATISFIED-BY-CONSTRUCTION. There was no store of a mode value anywhere on
  a box (no config key, no env var, no installer write), so install/update had
  nothing to preserve and ``modes.preserve_explicit_mode()`` was a pure,
  unit-tested helper with ZERO production callers. Spec line 373 requires the
  clause, so a client's explicit ``off`` (the emergency JEV kill switch) had
  no durable representation at all: a release default could not overwrite it
  because there was nothing to overwrite.

WHAT THIS SUITE PROVES (and what it refuses to claim)
  1. ROUND TRIP: write ``off`` to the store, run the install-path receipt and
     the update-path receipt against a throwaway box root, read back ``off``.
     Repeated for legacy and shadow.
  2. THE STORE IS NOT WRITTEN BY EITHER PATH. Bytes and mtime are compared
     before/after both receipts — "preserved" is proven by nothing having
     written, not by a merge that ran correctly once.
  3. KNOWN-GOOD CONTROL, on the instrument: a box with NO store reports the
     release default and says so. If the control also reported PRESERVED, the
     receipt would be printing a constant and case 1 would pass for free.
     A second control sets an explicit ``auto`` (valid mode, non-default
     choice) and requires it be reported as stored, not as the default.
  4. CORRUPT is fail-loud and NON-DESTRUCTIVE: an invalid value returns 1,
     prints the value and the consequence, and leaves the file byte-identical.
     Silently resetting a client's ``off`` to ``auto`` is the worst possible
     outcome here, so it must be impossible, not merely unlikely.
  5. ENV OVERRIDE outranks the file (so an operator can pin a mode fleet-wide
     without editing every box) and is reported as coming from the env.
  6. BOTH INSTALLER SCRIPTS CALL THE RECEIPT: the tagged blocks exist in
     install.sh AND update-skills.sh. A store nobody checks is a comment —
     which is exactly the failure class this clause was in.

METHOD. Hermetic: ``mktemp -d`` for both the box root and a private HOME; the
receipt runs as a subprocess exactly as the installers invoke it. No network,
no box state, no client, no secrets. The canonical modes module is loaded from
the repo's own shared-utils/, so the receipt is proven against the REAL
authority — not a stub that could drift from it.

Run: python3 -m pytest tests/unit/test_a62_mode_survives_install_update.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECEIPT = REPO / "scripts" / "decision-engine-mode.py"
SHARED_UTILS = REPO / "shared-utils"
INSTALL_SH = REPO / "install.sh"
UPDATE_SKILLS_SH = REPO / "update-skills.sh"

STORE_NAME = "decision-engine-mode.conf"


class ModeStoreRoundTrip(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="a62-mode-home-"))
        self.box = Path(tempfile.mkdtemp(prefix="a62-mode-box-"))
        self.store = self.box / STORE_NAME
        self.env = dict(os.environ)
        self.env["HOME"] = str(self.home)
        self.env.pop("OPENCLAW_DECISION_ENGINE_MODE", None)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.box, ignore_errors=True)

    def _receipt(self, *, env=None):
        return subprocess.run(
            [sys.executable, str(RECEIPT),
             "--shared-utils", str(SHARED_UTILS),
             "--oc-config", str(self.box), "--assert-preserved"],
            capture_output=True, text=True, env=env or self.env, check=False)

    def _write(self, value):
        self.store.write_text(value + "\n", encoding="utf-8")

    # ── 1 + 2: round trip, and the store is untouched by both paths ─────────

    def test_explicit_modes_survive_both_paths_byte_for_byte(self):
        for mode in ("off", "legacy", "shadow", "auto"):
            with self.subTest(mode=mode):
                self._write(mode)
                before = self.store.read_bytes()
                before_stat = self.store.stat()
                rc = self._receipt()
                self.assertEqual(
                    rc.returncode, 0,
                    f"receipt failed for stored {mode!r}: {rc.stderr}")
                # The RECEIPT names the stored mode; it never prints the default.
                self.assertIn(repr(mode), rc.stdout)
                self.assertNotIn("no explicit decision-engine mode stored",
                                 rc.stdout)
                # Preserved = nothing wrote. Bytes AND mtime.
                self.assertEqual(self.store.read_bytes(), before,
                                 "store bytes changed across the receipt path")
                self.assertEqual(self.store.stat().st_mtime_ns,
                                 before_stat.st_mtime_ns,
                                 "store mtime changed: something wrote it")
                self.assertEqual(self.store.read_text(encoding="utf-8").strip(),
                                 mode)

    # ── 3: controls on the instrument ───────────────────────────────────────

    def test_no_store_control_reports_the_release_default(self):
        self.assertFalse(self.store.exists())
        rc = self._receipt()
        self.assertEqual(rc.returncode, 0, rc.stderr)
        self.assertIn("no explicit decision-engine mode stored", rc.stdout)
        self.assertIn("'auto'", rc.stdout)
        self.assertFalse(self.store.exists(),
                         "a box with no store must not have one created")

    def test_explicit_auto_is_reported_as_stored_not_as_default(self):
        """Control: 'auto' is BOTH a valid mode and the release default.

        A receipt that keyed off the VALUE instead of the SOURCE would report
        a stored explicit 'auto' as 'no store'. Requires the source to be
        genuinely distinguished.
        """
        self._write("auto")
        rc = self._receipt()
        self.assertEqual(rc.returncode, 0, rc.stderr)
        self.assertIn("preserved", rc.stdout)
        self.assertNotIn("no explicit decision-engine mode stored", rc.stdout)

    def test_bad_shared_utils_is_an_unprovable_receipt_never_a_pass(self):
        rc = subprocess.run(
            [sys.executable, str(RECEIPT),
             "--shared-utils", str(self.box / "nope"),
             "--oc-config", str(self.box), "--assert-preserved"],
            capture_output=True, text=True, env=self.env, check=False)
        self.assertEqual(rc.returncode, 2,
                         "a missing modes module must not report success")
        self.assertIn("cannot load the canonical modes module", rc.stderr)

    # ── 4: corrupt is loud and non-destructive ──────────────────────────────

    def test_corrupt_value_fails_loud_and_is_never_rewritten(self):
        self._write("turbo")
        before = self.store.read_bytes()
        rc = self._receipt()
        self.assertEqual(rc.returncode, 1, rc.stdout)
        self.assertIn("CORRUPT", rc.stderr)
        self.assertIn("'turbo'", rc.stderr)
        self.assertIn("Nothing was written", rc.stderr)
        self.assertEqual(self.store.read_bytes(), before,
                         "a corrupt store must be left exactly as found")

    def test_empty_store_fails_loud(self):
        self.store.write_text("\n", encoding="utf-8")
        rc = self._receipt()
        self.assertEqual(rc.returncode, 1, rc.stdout)
        self.assertIn("CORRUPT", rc.stderr)

    # ── 5: env outranks the file ────────────────────────────────────────────

    def test_env_override_outranks_the_store(self):
        self._write("off")
        env = dict(self.env)
        env["OPENCLAW_DECISION_ENGINE_MODE"] = "legacy"
        rc = self._receipt(env=env)
        self.assertEqual(rc.returncode, 0, rc.stderr)
        self.assertIn("from $OPENCLAW_DECISION_ENGINE_MODE", rc.stdout)
        self.assertIn("'legacy'", rc.stdout)
        self.assertEqual(self.store.read_text(encoding="utf-8").strip(), "off",
                         "the env override must not rewrite the stored value")

    # ── 6: both installers call it, inside the right block ──────────────────

    def test_both_installers_carry_the_receipt_call(self):
        for path in (INSTALL_SH, UPDATE_SKILLS_SH):
            with self.subTest(installer=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("DECISION-MODE-PRESERVE-BEGIN", text,
                              f"{path.name} has no mode-preserve block")
                self.assertIn("decision-engine-mode.py", text,
                              f"{path.name} never calls the receipt")
                begin = text.index("DECISION-MODE-PRESERVE-BEGIN")
                end = text.index("DECISION-MODE-PRESERVE-END")
                block = text[begin:end]
                self.assertIn("--assert-preserved", block)
                # The failure path must not abort a fleet roll.
                self.assertIn("_DEM_RC=$?", block)
                self.assertNotIn("exit 1", block,
                                 "a corrupt mode store must not abort a roll")

    def test_receipt_runs_after_the_canonical_core_lands(self):
        """Ordering, both paths: the receipt must not precede the core.

        A receipt checked before shared-utils lands would describe the
        previous release's modes module, or fail rc 2 and report an unproven
        receipt on a healthy box.
        """
        install = INSTALL_SH.read_text(encoding="utf-8")
        self.assertLess(
            install.index("decision core verified in"),
            install.index("DECISION-MODE-PRESERVE-BEGIN"),
            "install.sh checks the mode receipt before the decision core")
        update = UPDATE_SKILLS_SH.read_text(encoding="utf-8")
        self.assertLess(
            update.index("shared-utils refreshed in"),
            update.index("DECISION-MODE-PRESERVE-BEGIN"),
            "update-skills.sh checks the mode receipt before shared-utils")


if __name__ == "__main__":
    unittest.main(verbosity=2)
