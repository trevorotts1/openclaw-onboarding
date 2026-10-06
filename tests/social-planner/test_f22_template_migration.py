"""QC-F22 — clean template contract + migration.

Duplicate headings (U:AN pattern) are detected; legacy starter content is
blanked in the dry-run preview; legitimate client rows/notes are preserved; a
backup is written BEFORE anything is altered on --apply.
"""
import json
import os
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SCRIPT = os.path.join(BASE, "35-social-media-planner", "scripts", "migrate-template.py")
SCHEMA = os.path.join(BASE, "35-social-media-planner", "config", "sheet-template.schema.json")
LIVE_TEMPLATE_ID = "1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c"


def run_migration(*args):
    proc = subprocess.run(["python3", SCRIPT, *args], capture_output=True, text=True, timeout=60)
    return proc


def write_fixture(tmp, doc):
    path = os.path.join(tmp, "template.json")
    with open(path, "w") as f:
        json.dump(doc, f)
    return path


def legacy_doc():
    """Mimics the live master template finding: duplicate headings in U:AN and
    a starter row with an old campaign + publication statuses."""
    return {
        "tabs": {
            "Weekly Overview": {
                "headings": ["Week Of", "Theme of the Week", "Research", "Core Content",
                             "Images", "Videos", "Facebook", "Instagram", "LinkedIn",
                             "YouTube", "TikTok", "Pinterest", "Carousels", "Blog",
                             "Podcast", "Email", "QC", "Scheduled", "Overall", "Notes",
                             "Notes"],  # duplicate in U:AN
                "rows": [
                    ["Week of Sep 7 - Sep 13, 2026", "Sample Campaign Promo", "",
                     "Your Brand Fall Launch", "", "", "Published", "Scheduled", "",
                     "", "Complete", "", "", "", "", "", "Complete", "2026-09-10",
                     "Published", "old campaign notes"],
                    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                ],
            },
            "Client Notes": {
                "headings": ["Date", "Note"],
                "rows": [
                    ["2026-09-06", "Client wants more reels this month"],  # LEGITIMATE
                ],
            },
            "Example Demos": {
                "headings": ["Demo"],
                "rows": [["Demo campaign — never copied"]],
            },
        }
    }


class TestF22TemplateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCHEMA) as f:
            cls.schema = json.load(f)

    def test_schema_versioned(self):
        self.assertRegex(self.schema["schema_version"], r"^\d+\.\d+\.\d+$")

    def test_starter_rows_must_be_empty_rule(self):
        self.assertIn("EMPTY", self.schema["starter_rows_rule"])
        self.assertIn("never", self.schema["tabs"]["Example (never copy)"].get("purpose", "").lower()
                      or "")

    def test_example_tab_never_copied(self):
        ex = self.schema["tabs"]["Example (never copy)"]
        self.assertTrue(ex.get("example_tab"))
        self.assertIs(ex.get("copied_to_clients"), False)

    def test_identity_provisioned_from_verified_identity(self):
        ident = self.schema["identity_fields"]
        for field in ("client_title", "timezone", "schema_version"):
            self.assertIn(field, ident)
        self.assertIn("verified identity", ident["client_title"])

    def test_unique_headings_declared(self):
        ov = self.schema["tabs"]["Weekly Overview"]
        self.assertTrue(ov.get("headings_unique"))
        heads = ov["headings"]
        self.assertEqual(len(heads), len(set(heads)), "contract headings must be unique")


class TestF22Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="f22-")
        with open(SCHEMA) as f:
            self.schema = json.load(f)

    def test_duplicate_headings_detected(self):
        path = write_fixture(self.tmp, legacy_doc())
        proc = run_migration("--fixture", path)
        self.assertEqual(proc.returncode, 2)  # findings need a reviewed dry-run
        self.assertIn("duplicate headings", proc.stdout)

    def test_legacy_starter_content_blank_in_dry_run(self):
        path = write_fixture(self.tmp, legacy_doc())
        proc = run_migration("--fixture", path)
        self.assertIn("blank", proc.stdout.lower())
        # The published/scheduled starter statuses are reported.
        self.assertIn("Published", proc.stdout)
        # Dry-run: the file is untouched.
        with open(path) as f:
            after = json.load(f)
        self.assertEqual(after["tabs"]["Weekly Overview"]["rows"][0][6], "Published")

    def test_client_notes_preserved_in_preview_and_apply(self):
        path = write_fixture(self.tmp, legacy_doc())
        proc = run_migration("--fixture", path)
        self.assertIn("preserve_client_rows", proc.stdout)
        proc = run_migration("--fixture", path, "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(path + ".migrated.json") as f:
            migrated = json.load(f)
        notes = migrated["tabs"]["Client Notes"]["rows"]
        self.assertEqual(notes, [["2026-09-06", "Client wants more reels this month"]],
                         "legitimate client rows/notes survive untouched")

    def test_starter_rows_blanked_on_apply(self):
        path = write_fixture(self.tmp, legacy_doc())
        proc = run_migration("--fixture", path, "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(path + ".migrated.json") as f:
            migrated = json.load(f)
        row = migrated["tabs"]["Weekly Overview"]["rows"][0]
        self.assertTrue(all(c == "" for c in row), "starter content is blanked")

    def test_example_tab_content_untouched(self):
        path = write_fixture(self.tmp, legacy_doc())
        run_migration("--fixture", path, "--apply")
        with open(path + ".migrated.json") as f:
            migrated = json.load(f)
        self.assertEqual(migrated["tabs"]["Example Demos"]["rows"],
                         [["Demo campaign — never copied"]])

    def test_backup_written_before_apply(self):
        path = write_fixture(self.tmp, legacy_doc())
        original = open(path).read()
        proc = run_migration("--fixture", path, "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        backup_path = path + ".backup.json"
        self.assertTrue(os.path.exists(backup_path), "backup must exist after apply")
        with open(backup_path) as f:
            backup = json.load(f)
        self.assertEqual(backup["document"], json.loads(original),
                         "the backup carries the EXACT pre-migration state")
        self.assertIn("backed_up_at", backup)

    def test_clean_document_needs_no_migration(self):
        path = write_fixture(self.tmp, {"tabs": {"Weekly Overview": {
            "headings": ["Week Of", "Notes"],
            "rows": [["", ""]],
        }}})
        proc = run_migration("--fixture", path)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("nothing to migrate", proc.stdout)

    def test_live_template_id_refused(self):
        proc = run_migration("--sheet-id", LIVE_TEMPLATE_ID)
        self.assertEqual(proc.returncode, 3, "the live template is never edited implicitly")
        self.assertIn("LIVE infrastructure", proc.stdout)

    def test_identity_provisioned_on_apply(self):
        path = write_fixture(self.tmp, legacy_doc())
        proc = run_migration("--fixture", path, "--apply",
                             "--client-title", "Acme Co", "--timezone", "America/New_York")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(path + ".migrated.json") as f:
            migrated = json.load(f)
        self.assertEqual(migrated["identity"]["client_title"], "Acme Co")
        self.assertEqual(migrated["identity"]["timezone"], "America/New_York")
        self.assertEqual(migrated["identity"]["schema_version"], self.schema["schema_version"])


if __name__ == "__main__":
    unittest.main()