#!/usr/bin/env python3
"""FAULT-11 / F20: prove refresh-dept-intake.py actually refreshes a stale
department intake/ tree from the role-library template AND preserves a
genuine client-local override. Hermetic — builds its own scratch library +
workspace fixture, never touches a real skill install or the live box.

Exercises the REAL delivery function (mirror_dept_intake / main()), not a
string-presence check on update-skills.sh. Revert refresh-dept-intake.py's
_refresh_bank_file()/mirror_dept_intake() logic to a no-op (or delete the
script's --apply wiring) and test_stale_bank_is_refreshed_on_apply MUST fail
-- see also test_no_delivery_mechanism_is_the_default_broken_state, which
pins the ORIGINAL bug (a stale bank sitting untouched forever with no
delivery path at all) as a regression tripwire.
"""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_MODULE_PATH = _HERE / "refresh-dept-intake.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refresh_dept_intake_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


rdi = _load_module()

OLD_BANK = json.dumps({"version": "1.5.0", "questions": ["q1", "q2"]}, indent=2)
NEW_BANK = json.dumps(
    {"version": "1.6.0", "questions": ["q1", "q2", "named_methodology_1", "named_methodology_2"]},
    indent=2,
)
CLIENT_EDITED_BANK = json.dumps({"version": "1.5.0-client-edit", "questions": ["custom"]}, indent=2)


class RefreshDeptIntakeFixture(unittest.TestCase):
    """Builds a scratch role-library + client workspace on disk, matching the
    real on-disk shape: <library>/<dept>/intake/... and
    <workspace>/departments/<Dept>/intake/... ."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)

        self.library_root = root / "library"
        self.lib_intake = self.library_root / "testdept" / "intake"
        self.lib_intake.mkdir(parents=True)
        (self.lib_intake / "deck-intake-questions.json").write_text(NEW_BANK, encoding="utf-8")
        (self.lib_intake / "upsell-questions.json").write_text('{"v": "1.0.0"}', encoding="utf-8")

        app = self.lib_intake / "interview-app"
        (app / "worker" / "src").mkdir(parents=True)
        (app / "worker" / "src" / "index.js").write_text("// canonical worker v2\n", encoding="utf-8")
        (app / "pages").mkdir(parents=True, exist_ok=True)
        (app / "pages" / "questions.json").write_text('{"snapshot": "v2"}', encoding="utf-8")

        self.workspace = root / "workspace"
        self.dept_dir = self.workspace / "departments" / "testdept"
        self.dept_dir.mkdir(parents=True)
        # A materialized department always has scripts/ + a build script per
        # resolve_dept_dir()'s real-world callers; not required by
        # resolve_dept_dir() itself, but keeps the fixture realistic.
        (self.dept_dir / "scripts").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _apply(self):
        return rdi.main(["--workspace", str(self.workspace), "--library", str(self.library_root), "--apply"])

    def _dry_run(self):
        return rdi.main(["--workspace", str(self.workspace), "--library", str(self.library_root)])


class TestStaleBankRefresh(RefreshDeptIntakeFixture):
    """THE FAULT-11 CASE: a materialized department already has an intake/
    dir with a stale bank (no provenance record -- exactly the state of the
    real box the fault was filed against) and NO delivery mechanism has ever
    touched it before."""

    def setUp(self):
        super().setUp()
        self.dept_intake = self.dept_dir / "intake"
        self.dept_intake.mkdir()
        (self.dept_intake / "deck-intake-questions.json").write_text(OLD_BANK, encoding="utf-8")

    def test_stale_bank_is_refreshed_on_apply(self):
        rc = self._apply()
        self.assertEqual(rc, 0, "a clean refresh must exit 0")
        dest = self.dept_intake / "deck-intake-questions.json"
        self.assertEqual(dest.read_text(encoding="utf-8"), NEW_BANK,
                          "stale dept intake/ bank was NOT refreshed from the library template -- "
                          "this is FAULT-11 itself: the delivery mechanism did not ship the fix")

    def test_stale_bank_refresh_is_backed_up_not_destroyed(self):
        self._apply()
        backups = list(self.dept_intake.glob("deck-intake-questions.json.bak-intake-refresh-*"))
        self.assertEqual(len(backups), 1, "exactly one backup of the pre-refresh bank must exist")
        self.assertEqual(backups[0].read_text(encoding="utf-8"), OLD_BANK,
                          "the backup must hold the EXACT pre-refresh bytes")

    def test_dry_run_writes_nothing(self):
        rc = self._dry_run()
        self.assertEqual(rc, 0)
        dest = self.dept_intake / "deck-intake-questions.json"
        self.assertEqual(dest.read_text(encoding="utf-8"), OLD_BANK,
                          "dry-run (no --apply) must never mutate the destination")
        self.assertFalse((self.dept_intake / rdi._PROVENANCE_FILENAME).exists(),
                          "dry-run must not write a provenance sidecar either")

    def test_second_apply_run_is_idempotent_no_new_backup(self):
        self._apply()
        first_backups = set(self.dept_intake.glob("deck-intake-questions.json.bak-intake-refresh-*"))
        rc = self._apply()
        self.assertEqual(rc, 0)
        second_backups = set(self.dept_intake.glob("deck-intake-questions.json.bak-intake-refresh-*"))
        self.assertEqual(first_backups, second_backups,
                          "a second run against an already-current bank must be a no-op "
                          "(no new backup, no re-copy)")

    def test_new_question_bank_upsell_file_is_fresh_installed(self):
        # upsell-questions.json never existed on this dept before -- fresh install path.
        self._apply()
        dest = self.dept_intake / "upsell-questions.json"
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"), '{"v": "1.0.0"}')

    def test_canonical_interview_app_source_is_mirrored(self):
        self._apply()
        dest = self.dept_intake / "interview-app" / "worker" / "src" / "index.js"
        self.assertTrue(dest.is_file(), "interview-app/ canonical source must be mirrored too")
        self.assertEqual(dest.read_text(encoding="utf-8"), "// canonical worker v2\n")

    def test_receipt_and_status_line_report_success(self):
        rc = self._apply()
        self.assertEqual(rc, 0)
        receipt_path = self.workspace / ".dept-intake-refresh-receipt.json"
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["failed_inscope"], 0)


class TestClientLocalOverridePreserved(RefreshDeptIntakeFixture):
    """A genuine client edit made AFTER a real delivery must survive the next
    roll untouched -- HARD RULE #3 of F20's brief."""

    def setUp(self):
        super().setUp()
        self.dept_intake = self.dept_dir / "intake"
        self.dept_intake.mkdir()
        (self.dept_intake / "deck-intake-questions.json").write_text(OLD_BANK, encoding="utf-8")
        # An additive-bucket local override: the client's own regenerated
        # pages/questions.json snapshot, different from the library's.
        pages = self.dept_intake / "interview-app" / "pages"
        pages.mkdir(parents=True)
        (pages / "questions.json").write_text('{"snapshot": "client-local"}', encoding="utf-8")

    def test_post_delivery_edit_is_preserved_not_overwritten(self):
        # Roll 1: delivers NEW_BANK and establishes provenance (the box's
        # first-ever contact with this mechanism -- the FAULT-11 case).
        rc1 = self._apply()
        self.assertEqual(rc1, 0)
        dest = self.dept_intake / "deck-intake-questions.json"
        self.assertEqual(dest.read_text(encoding="utf-8"), NEW_BANK)

        # The client now hand-edits the delivered bank.
        dest.write_text(CLIENT_EDITED_BANK, encoding="utf-8")

        # The library ships yet another new version.
        even_newer = json.dumps({"version": "1.7.0", "questions": ["q1", "q2", "q3"]}, indent=2)
        (self.lib_intake / "deck-intake-questions.json").write_text(even_newer, encoding="utf-8")

        # Roll 2: must NOT clobber the client's edit.
        rc2 = self._apply()
        self.assertEqual(rc2, 0, "a preserved override must never fail the run")
        self.assertEqual(dest.read_text(encoding="utf-8"), CLIENT_EDITED_BANK,
                          "a genuine post-delivery client edit was overwritten -- "
                          "HARD RULE #3 violation")

    def test_additive_json_snapshot_is_never_overwritten(self):
        self._apply()
        dest = self.dept_intake / "interview-app" / "pages" / "questions.json"
        self.assertEqual(dest.read_text(encoding="utf-8"), '{"snapshot": "client-local"}',
                          "an additive .json the client already has must be preserved as-is")


class TestNotMaterializedIsBenignSkip(RefreshDeptIntakeFixture):
    def setUp(self):
        super().setUp()
        # Remove the materialized department entirely.
        import shutil
        shutil.rmtree(self.dept_dir)

    def test_missing_department_is_a_benign_skip_not_a_failure(self):
        rc = self._apply()
        self.assertEqual(rc, 0, "a department the box never had must be a benign skip, not rc 3")
        self.assertFalse((self.workspace / "departments" / "testdept").exists())


class TestNonVacuousRegressionTripwire(RefreshDeptIntakeFixture):
    """Pins the ORIGINAL bug: with no delivery mechanism at all (simulated by
    calling mirror_dept_intake with an intake_target that mirror never
    touches -- i.e. proving the OLD world, pre-fix, never changed the file),
    a stale bank stays stale forever. This test does not call the fix; it
    documents the failure mode the fix closes, so a future revert of
    mirror_dept_intake's bank-refresh branch is caught by
    TestStaleBankRefresh.test_stale_bank_is_refreshed_on_apply above, not by
    this one (this one only proves the fixture itself is real: doing
    nothing leaves the bank stale)."""

    def setUp(self):
        super().setUp()
        self.dept_intake = self.dept_dir / "intake"
        self.dept_intake.mkdir()
        (self.dept_intake / "deck-intake-questions.json").write_text(OLD_BANK, encoding="utf-8")

    def test_untouched_fixture_stays_stale(self):
        dest = self.dept_intake / "deck-intake-questions.json"
        self.assertEqual(dest.read_text(encoding="utf-8"), OLD_BANK)


if __name__ == "__main__":
    unittest.main()
