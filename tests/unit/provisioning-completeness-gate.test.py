#!/usr/bin/env python3
"""
provisioning-completeness-gate.test.py — proves the false-success closer added to
shared-utils/fleet_refresh_runner.py (step_provisioning_completeness / Step 8d).

WHY THIS EXISTS
  The roll verdict (run_box) reports a box "ok" (PASS) when no step string carries
  "failed". Before this gate a box could carry the FULL SOP corpus yet ship
  placeholder branding, a stale/missing onboarding version stamp, an empty
  departments.json, and zero personas — and still report PASS (6 boxes did, one
  night). This gate hard-fails on VERSION + BRANDING + DEPARTMENTS + PERSONAS.

WHAT IS PROVEN (hermetic — LOCAL FIXTURES ONLY, never a real box):
  For every scenario we build a fixture box (mac layout under FLEET_REFRESH_ROOT),
  drive it through the runner's own path authority (_load_paths), seed a BoxResult
  in which EVERY pre-gate step passed (incl. embedding-health=pass — "full SOP"),
  then measure BOTH columns using the EXACT verdict expression run_box uses:
      has_failures = any("failed" in str(v) for v in res.steps.values())
    * BEFORE  — over the pre-gate steps      (this is what origin/main reported)
    * AFTER   — after step_provisioning_completeness runs

  (a) full SOP + placeholder branding  -> BEFORE ok / AFTER FAIL
  (b) full SOP + stale version         -> BEFORE ok / AFTER FAIL
  (b2) full SOP + missing version      -> BEFORE ok / AFTER FAIL
  (c) empty departments.json           -> BEFORE ok / AFTER FAIL
  (d) empty personas                   -> BEFORE ok / AFTER FAIL
  (e) fully-correct box                -> BEFORE ok / AFTER ok   (NO false-FAIL)
  (f) per-check breakdown is emitted   (all six check names present)
  (g) a legit client whose name merely CONTAINS "Your Company" still PASSES
      (exact-placeholder match, never a substring false-FAIL)

Run:  python3 tests/unit/provisioning-completeness-gate.test.py -v
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_RUNNER_PATH = _SHARED_UTILS / "fleet_refresh_runner.py"

# Load the runner under test as a module.
_spec = importlib.util.spec_from_file_location("fleet_refresh_runner_under_test", _RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
sys.modules["fleet_refresh_runner_under_test"] = runner
_spec.loader.exec_module(runner)

PINNED = "v20.0.74"

# Collected (scenario, before, after, expect_after) rows for the both-columns table.
_ROWS: list = []


def _old_verdict(res) -> str:
    """The EXACT verdict run_box computes for a NON-dry-run box, asserted against
    directly (not a paraphrase). Returns 'ok' or a non-ok string."""
    has_failures = any("failed" in str(v) for v in res.steps.values())
    if not has_failures:
        return "ok"
    total = len(res.steps)
    failed = sum(1 for v in res.steps.values() if "failed" in str(v))
    return "failed" if failed == total else "partial"


class ProvisioningCompletenessGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prov-gate-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        # mac layout (FLEET_REFRESH_ROOT fixture branch of _load_paths): NO
        # root/data/.openclaw marker -> mac branch is taken.
        self.home = self.tmp / "home"
        self.workspace = self.home / ".openclaw" / "workspace"
        self.master = self.home / "Downloads" / "openclaw-master-files"
        self.company_dir = self.master / "zero-human-company" / "acme-co"
        self.cc_dir = self.home / "projects" / "command-center"
        self.personas_dir = self.workspace / "data" / "coaching-personas" / "personas"
        for d in (self.workspace, self.company_dir, self.cc_dir / "config",
                  self.cc_dir / "public", self.personas_dir):
            d.mkdir(parents=True, exist_ok=True)

        # ── a fully-correct ("good") box ──
        self._write_departments(28)
        self._write_company_name("Acme Robotics")
        self._write_logo({"logoUrl": ""})            # empty logoUrl = text-SVG fallback = OK
        self._write_personas(["clockwork", "profit-first", "traction"])
        self._env_prev = os.environ.get("FLEET_REFRESH_ROOT")
        os.environ["FLEET_REFRESH_ROOT"] = str(self.tmp)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._env_prev is None:
            os.environ.pop("FLEET_REFRESH_ROOT", None)
        else:
            os.environ["FLEET_REFRESH_ROOT"] = self._env_prev

    # ── fixture writers ────────────────────────────────────────────────────
    def _write_departments(self, n):
        (self.company_dir / "departments.json").write_text(
            json.dumps([{"slug": f"dept-{i}"} for i in range(n)]))

    def _write_company_name(self, name):
        # write the name into ALL three resolution sources so the resolver's
        # fallback chain reflects a single coherent box state.
        (self.company_dir / "company-config.json").write_text(json.dumps({"name": name, "companyName": name}))
        (self.cc_dir / "config" / "company-config.json").write_text(json.dumps({"companyName": name}))
        (self.workspace / ".workforce-build-state.json").write_text(json.dumps({"companyName": name}))

    def _write_logo(self, obj):
        (self.cc_dir / "public" / "logo-config.json").write_text(json.dumps(obj))

    def _write_personas(self, slugs):
        for s in slugs:
            pd = self.personas_dir / s
            pd.mkdir(parents=True, exist_ok=True)
            (pd / "persona-blueprint.md").write_text(f"# {s}\n")

    def _clear_personas(self):
        shutil.rmtree(self.personas_dir, ignore_errors=True)
        self.personas_dir.mkdir(parents=True, exist_ok=True)

    # ── harness ────────────────────────────────────────────────────────────
    def _seed_good_result(self, onboarding_version=PINNED):
        """A BoxResult in which EVERY pre-gate step passed (incl. full SOP)."""
        res = runner.BoxResult(box="fixture-box", dry_run=False)
        res.onboarding_version = onboarding_version
        res.board = {"cc_healthy": True}
        res.steps = {
            "detect": "ok", "pin-resolve": "ok", "pull-onboarding": "ok",
            "pull-cc": "ok", "build-cc": "ok", "restart-cc": "ok",
            "sessions-reset-CEO": "ok", "verify": "ok",
            "embedding-health": "pass",          # <-- full SOP corpus present
        }
        return res

    def _run_gate(self, res):
        """Drive the gate through the runner's OWN path authority (fixture mode)
        and capture the emitted breakdown. Returns (result_dict, stderr_text)."""
        paths = runner._load_paths(_SHARED_UTILS)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            out = runner.step_provisioning_completeness(paths, res, PINNED)
        return out, buf.getvalue()

    def _measure(self, scenario, res, expect_after_ok):
        before = _old_verdict(res)
        out, err = self._run_gate(res)
        after = _old_verdict(res)
        _ROWS.append((scenario, before, after, "ok" if expect_after_ok else "FAIL"))
        return before, after, out, err

    # ── scenarios ────────────────────────────────────────────────────────────
    def test_a_placeholder_branding_fails_where_it_previously_passed(self):
        self._write_company_name("Your Company")     # the shipped CC placeholder
        res = self._seed_good_result()
        before, after, out, _ = self._measure("a: placeholder branding", res, False)
        self.assertEqual(before, "ok", "origin/main would have reported this box PASS")
        self.assertEqual(after, "partial", "gate must flip the box off ok")
        self.assertFalse(out["checks"]["BRANDING"]["ok"])
        self.assertIn("BRANDING", out["failed"])

    def test_b_stale_version_fails(self):
        res = self._seed_good_result(onboarding_version="v8.0.1")
        before, after, out, _ = self._measure("b: stale version v8.0.1", res, False)
        self.assertEqual(before, "ok")
        self.assertEqual(after, "partial")
        self.assertFalse(out["checks"]["VERSION"]["ok"])
        self.assertIn("VERSION", out["failed"])

    def test_b2_missing_version_fails(self):
        res = self._seed_good_result(onboarding_version="unknown")
        before, after, out, _ = self._measure("b2: missing version stamp", res, False)
        self.assertEqual(before, "ok")
        self.assertEqual(after, "partial")
        self.assertIn("VERSION", out["failed"])

    def test_c_empty_departments_fails(self):
        (self.company_dir / "departments.json").write_text("[]")
        res = self._seed_good_result()
        before, after, out, _ = self._measure("c: empty departments []", res, False)
        self.assertEqual(before, "ok")
        self.assertEqual(after, "partial")
        self.assertFalse(out["checks"]["DEPARTMENTS"]["ok"])
        self.assertIn("DEPARTMENTS", out["failed"])

    def test_d_empty_personas_fails(self):
        self._clear_personas()
        res = self._seed_good_result()
        before, after, out, _ = self._measure("d: empty personas", res, False)
        self.assertEqual(before, "ok")
        self.assertEqual(after, "partial")
        self.assertFalse(out["checks"]["PERSONAS"]["ok"])
        self.assertIn("PERSONAS", out["failed"])

    def test_e_fully_correct_box_still_passes(self):
        res = self._seed_good_result()
        before, after, out, _ = self._measure("e: fully-correct box", res, True)
        self.assertEqual(before, "ok")
        self.assertEqual(after, "ok", "a genuinely-fine box must NOT be false-failed")
        self.assertEqual(out["failed"], [])
        self.assertEqual(res.steps["provisioning-completeness"], "ok")
        # empty logoUrl (text-SVG fallback) must NOT fail branding
        self.assertTrue(out["checks"]["BRANDING"]["ok"])

    def test_f_breakdown_is_emitted(self):
        res = self._seed_good_result()
        out, err = self._run_gate(res)
        for name in ("VERSION", "BRANDING", "DEPARTMENTS", "PERSONAS", "SOP", "CC-SERVE"):
            self.assertIn(name + ":", out["breakdown"], f"{name} missing from breakdown")
        self.assertIn("provisioning-completeness:", err)

    def test_g_legit_name_containing_placeholder_substring_passes(self):
        # EXACT-placeholder match only — a real client named with the substring
        # must never be false-failed.
        self._write_company_name("Your Company Solutions LLC")
        res = self._seed_good_result()
        _, after, out, _ = self._measure("g: legit name w/ substring", res, True)
        self.assertEqual(after, "ok")
        self.assertTrue(out["checks"]["BRANDING"]["ok"])

    def test_h_logo_missing_at_provisioned_cc_fails_branding(self):
        # CC config present (real name) but logo-config.json absent => half-seeded CC.
        (self.cc_dir / "public" / "logo-config.json").unlink()
        res = self._seed_good_result()
        _, after, out, _ = self._measure("h: CC present, logo-config absent", res, False)
        self.assertEqual(after, "partial")
        self.assertFalse(out["checks"]["BRANDING"]["ok"])
        self.assertIn("BRANDING", out["failed"])


@unittest.skipIf(os.environ.get("PROV_GATE_NO_TABLE"), "table disabled")
class ZZ_PrintBothColumns(unittest.TestCase):
    """Runs last (alpha-sorted 'ZZ') to print the FAIL-before / PASS-after table."""
    def test_zz_print_table(self):
        if not _ROWS:
            self.skipTest("no rows collected")
        print("\n" + "=" * 74)
        print("  FAIL-BEFORE / PASS-AFTER  (verdict via run_box's exact has_failures test)")
        print("=" * 74)
        print(f"  {'scenario':<34} {'BEFORE':>8}   {'AFTER':>8}   {'expect':>8}")
        print("  " + "-" * 70)
        n_flip = 0
        for scen, before, after, expect in _ROWS:
            flip = " <-- flips" if before == "ok" and after != "ok" else ""
            if before == "ok" and after != "ok":
                n_flip += 1
            print(f"  {scen:<34} {before:>8}   {after:>8}   {expect:>8}{flip}")
        print("  " + "-" * 70)
        print(f"  boxes that FLIPPED from PASS(before) to FAIL(after): {n_flip}")
        print("=" * 74)


if __name__ == "__main__":
    unittest.main(verbosity=2)
