#!/usr/bin/env python3
"""Mocked tests for sheet schema 1.3.0 (Owner D27 / D35, plan 6.15).

Offline, stdlib only, zero paid calls, zero network, zero media. One test per
acceptance rule:

  * schema_version is bumped 1.2.0 -> 1.3.0 and still N.N.N;
  * the five drama-song fields sit on Weekly Overview -- style chosen, status,
    KIE cost, video link, channels posted -- after the columns A-U that 1.2.0
    already used, so migration moves no existing cell;
  * config/sheet-template.schema.json carries the 1.3.0 contract and the
    drama_song field block that names each column's webhook key;
  * the heading upgrade refuses anything it does not recognise, by name;
  * no transport / no KIE client / Skill 74 only path / no operator paths.

Run: python3 core/smp/sheet_schema_130/test_sheet_schema_130.py
"""
import ast
import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sheet_schema_130 as ss  # noqa: E402

MODULE_FILES = ("sheet_schema_130.py", "__init__.py")
MODULE_SOURCES = tuple(os.path.join(HERE, name) for name in MODULE_FILES)
CONTRACT = ss.find_contract()
MODULE = os.path.join(HERE, "sheet_schema_130.py")


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, MODULE, *args],
        capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


def load_contract():
    with open(CONTRACT) as handle:
        return json.load(handle)


def synthetic_contract():
    """A structurally complete 1.3.0 contract built from the module constants.

    Used where the tree carries no copy of the real contract (the build-root
    artifact mirror), so the mutation battery still runs instead of skipping.
    """
    return {
        "schema_version": ss.SCHEMA_VERSION,
        "tabs": {
            "Weekly Overview": {
                "frozen_headings_row": 1,
                "frozen_columns": 0,
                "headings": list(ss.WEEKLY_OVERVIEW_HEADINGS),
                "headings_unique": True,
                "status_columns": list(ss.WEEKLY_OVERVIEW_STATUS_COLUMNS),
                "wrap_text": True,
            },
            "This Week": {"headings": list(ss.THIS_WEEK_HEADINGS), "width": 8},
            "Posts": {"headings": ["row_key", "state"]},
            "Images": {"headings": ["asset_key"]},
            "Videos": {"headings": ["video_key"]},
            "Example (never copy)": {"example_tab": True,
                                     "copied_to_clients": False},
        },
        "drama_song": {
            "introduced_in": ss.SCHEMA_VERSION,
            "tab": "Weekly Overview",
            "technical_column": {"heading": ss.TECHNICAL_HEADING,
                                 "index": ss.TECHNICAL_INDEX,
                                 "column": ss.TECHNICAL_COLUMN},
            "fields": [dict(field) for field in ss.DRAMA_SONG_FIELDS],
        },
        "status_colors": {"statuses": [{"label": "Complete", "color": "#b7e1cd",
                                        "color_label": "green — done"}]},
        "formatting_contract": {"conditional_format_rules": "TEXT_EQ only"},
    }


def base_contract():
    """The contract the mutation battery edits: the shipped one when the tree
    has it, the synthetic twin otherwise."""
    return load_contract() if CONTRACT is not None else synthetic_contract()


class VersionTests(unittest.TestCase):
    def test_schema_version_is_bumped_to_1_3_0(self):
        self.assertEqual(ss.SCHEMA_VERSION, "1.3.0")

    def test_schema_version_is_still_semver(self):
        self.assertRegex(ss.SCHEMA_VERSION, r"^\d+\.\d+\.\d+$")

    def test_previous_version_is_the_one_being_migrated_from(self):
        self.assertEqual(ss.PREVIOUS_SCHEMA_VERSION, "1.2.0")

    def test_source_cites_the_owner_decision(self):
        self.assertIn("D27", ss.SOURCE)
        self.assertIn("6.15", ss.SOURCE)


class OverviewLayoutTests(unittest.TestCase):
    def test_overview_is_26_columns(self):
        self.assertEqual(len(ss.WEEKLY_OVERVIEW_HEADINGS), 26)
        self.assertEqual(ss.OVERVIEW_ROW_WIDTH, 26)

    def test_columns_a_to_t_are_the_1_2_0_layout_unchanged(self):
        """Migration safety: existing cells keep their meaning."""
        self.assertEqual(ss.WEEKLY_OVERVIEW_HEADINGS[:20], ss.HEADINGS_1_2_0)
        self.assertEqual(len(ss.HEADINGS_1_2_0), 20)
        self.assertEqual(ss.HEADINGS_1_2_0[0], "Week Of")
        self.assertEqual(ss.HEADINGS_1_2_0[19], "Notes")

    def test_technical_column_stays_at_index_20(self):
        """cycle_id holds the row-append upsert key; it must not move."""
        self.assertEqual(ss.TECHNICAL_INDEX, 20)
        self.assertEqual(ss.TECHNICAL_COLUMN, "U")
        self.assertEqual(ss.WEEKLY_OVERVIEW_HEADINGS[20], "cycle_id")

    def test_drama_song_columns_follow_the_technical_column(self):
        for field in ss.DRAMA_SONG_FIELDS:
            self.assertEqual(
                ss.WEEKLY_OVERVIEW_HEADINGS[field["index"]], field["heading"])
            self.assertEqual(field["column"], ss._column_letter(field["index"]))

    def test_drama_song_indexes_run_v_to_z(self):
        self.assertEqual([f["index"] for f in ss.DRAMA_SONG_FIELDS],
                         [21, 22, 23, 24, 25])
        self.assertEqual([f["column"] for f in ss.DRAMA_SONG_FIELDS],
                         ["V", "W", "X", "Y", "Z"])

    def test_headings_are_unique(self):
        self.assertEqual(len(ss.WEEKLY_OVERVIEW_HEADINGS),
                         len(set(ss.WEEKLY_OVERVIEW_HEADINGS)))

    def test_ready_header_readback_stays_the_first_twenty(self):
        """Verify Ready Headers reads A1:T1 -- bit-identical pre/post 1.3.0."""
        self.assertEqual(ss.HEADER_READBACK_HEADINGS, ss.HEADINGS_1_2_0)
        self.assertEqual(
            ss.WEEKLY_OVERVIEW_HEADINGS[:20], ss.HEADER_READBACK_HEADINGS)

    def test_column_letter_helper(self):
        self.assertEqual(ss._column_letter(0), "A")
        self.assertEqual(ss._column_letter(20), "U")
        self.assertEqual(ss._column_letter(25), "Z")
        self.assertEqual(ss._column_letter(26), "AA")

    def test_this_week_view_stays_compact(self):
        self.assertEqual(len(ss.THIS_WEEK_HEADINGS), 8)
        self.assertIn("Needs Attention", ss.THIS_WEEK_HEADINGS)


class DramaSongFieldTests(unittest.TestCase):
    """style chosen, status, KIE cost, video link, channels posted."""

    def test_exactly_five_fields_declared(self):
        self.assertEqual(len(ss.DRAMA_SONG_FIELDS), 5)

    def test_field_headings_carry_the_owner_work_items(self):
        headings = [f["heading"] for f in ss.DRAMA_SONG_FIELDS]
        self.assertEqual(headings, [
            "Drama Song Style",
            "Drama Song Status",
            "KIE Cost (cents)",
            "Drama Song Video Link",
            "Drama Song Channels Posted",
        ])

    def test_field_kinds(self):
        kinds = {f["key"]: f["kind"] for f in ss.DRAMA_SONG_FIELDS}
        self.assertEqual(kinds["drama_song_style"], "text")
        self.assertEqual(kinds["drama_song_status"], "status")
        self.assertEqual(kinds["kie_cost_cents"], "integer")
        self.assertEqual(kinds["drama_song_video_url"], "url")
        self.assertEqual(kinds["drama_song_channels"], "text_list")

    def test_webhook_keys_are_unique_and_url_free_of_host(self):
        keys = [f["key"] for f in ss.DRAMA_SONG_FIELDS]
        self.assertEqual(len(keys), len(set(keys)))
        for key in keys:
            self.assertRegex(key, r"^[a-z][a-z0-9_]*$")

    def test_kie_cost_is_whole_usd_cents(self):
        cost = ss.drama_song_fields_by_key()["kie_cost_cents"]
        self.assertEqual(cost["unit"], "usd_cents")
        self.assertEqual(cost["kind"], "integer")

    def test_video_link_is_raw_text_not_a_formula(self):
        video = ss.drama_song_fields_by_key()["drama_song_video_url"]
        self.assertEqual(video["kind"], "url")
        self.assertNotIn("IMAGE", video["source"].upper())

    def test_status_field_is_wired_as_a_status_column(self):
        self.assertIn("Drama Song Status", ss.WEEKLY_OVERVIEW_STATUS_COLUMNS)
        self.assertEqual(ss.WEEKLY_OVERVIEW_STATUS_COLUMNS,
                         ("QC", "Overall", "Drama Song Status"))

    def test_every_field_names_its_weekly_overview_cell(self):
        for field in ss.DRAMA_SONG_FIELDS:
            for attr in ("heading", "key", "kind", "index", "column", "source"):
                self.assertIn(attr, field)
                self.assertTrue(field[attr] is not None and
                                field[attr] != "")


class UpgradeHeadingsTests(unittest.TestCase):
    def test_upgrade_from_the_1_2_0_twenty_cell_row(self):
        up = ss.upgrade_headings(list(ss.HEADINGS_1_2_0))
        self.assertEqual(tuple(up), ss.WEEKLY_OVERVIEW_HEADINGS)
        self.assertEqual(len(up), 26)

    def test_upgrade_from_the_1_2_0_twenty_one_cell_row_moves_no_cell(self):
        old = list(ss.HEADINGS_1_2_0) + ["cycle_id"]
        up = ss.upgrade_headings(old)
        # Every cell that existed before keeps its index: migration appends.
        for index, value in enumerate(old):
            self.assertEqual(up[index], value, "cell %d moved" % index)
        self.assertEqual(len(up), 26)

    def test_upgrade_is_idempotent_on_a_1_3_0_row(self):
        first = ss.upgrade_headings(list(ss.WEEKLY_OVERVIEW_HEADINGS))
        second = ss.upgrade_headings(first)
        self.assertEqual(first, second)

    def test_upgrade_refuses_a_row_it_does_not_recognise_by_name(self):
        with self.assertRaises(ss.SheetSchemaError) as ctx:
            ss.upgrade_headings(["Week Of", "Notes"])
        self.assertIn("HEADINGS_NOT_MIGRATABLE", str(ctx.exception))

    def test_upgrade_refuses_when_the_technical_column_is_relabelled(self):
        old = list(ss.HEADINGS_1_2_0) + ["_row_key"]
        with self.assertRaises(ss.SheetSchemaError) as ctx:
            ss.upgrade_headings(old)
        self.assertIn("HEADINGS_NOT_MIGRATABLE", str(ctx.exception))


class ValidateContractTests(unittest.TestCase):
    def test_shipped_contract_matches_1_3_0(self):
        if CONTRACT is None:
            self.skipTest(
                "sheet-template.schema.json is not shipped beside this tree "
                "(build-root artifact mirror); contract checks run in the "
                "openclaw-onboarding worktree")
        self.assertEqual(ss.validate_contract(load_contract()), [])

    def test_shipped_contract_is_recognised_as_1_3_0(self):
        if CONTRACT is None:
            self.skipTest("contract not shipped beside this tree")
        self.assertTrue(ss.is_1_3_0(load_contract()))

    def test_synthetic_twin_is_a_valid_1_3_0_contract(self):
        """The mutation battery starts from a green base in every tree."""
        self.assertEqual(ss.validate_contract(synthetic_contract()), [])

    def _mutated(self, mutate, expected_fragment):
        # Edits the shipped contract where the tree carries one, otherwise the
        # synthetic twin -- the battery must never become a no-op skip.
        doc = base_contract()
        mutate(doc)
        failures = ss.validate_contract(doc)
        self.assertTrue(failures, "mutation produced no failure")
        self.assertTrue(
            any(expected_fragment in failure for failure in failures),
            "expected %r in %r" % (expected_fragment, failures))

    def test_old_schema_version_is_refused(self):
        self._mutated(lambda d: d.update(schema_version="1.2.0"),
                      "SCHEMA_VERSION_NOT_1_3_0")

    def test_a_dropped_drama_song_field_is_refused(self):
        def drop(doc):
            doc["tabs"]["Weekly Overview"]["headings"].remove(
                "Drama Song Video Link")
        self._mutated(drop, "DRAMA_SONG_HEADING_MISSING")

    def test_a_reordered_drama_song_field_is_refused(self):
        def reorder(doc):
            heads = doc["tabs"]["Weekly Overview"]["headings"]
            heads[21], heads[24] = heads[24], heads[21]
        self._mutated(reorder, "DRAMA_SONG_INDEX_WRONG")

    def test_moving_the_technical_column_is_refused(self):
        def move(doc):
            doc["tabs"]["Weekly Overview"]["headings"][20] = "Drama Song Style"
        self._mutated(move, "TECHNICAL_COLUMN_MOVED")

    def test_drifting_the_1_2_0_prefix_is_refused(self):
        def drift(doc):
            doc["tabs"]["Weekly Overview"]["headings"][19] = "Client Notes"
        self._mutated(drift, "OVERVIEW_PREFIX_DRIFT")

    def test_a_duplicate_heading_is_refused(self):
        def dupe(doc):
            doc["tabs"]["Weekly Overview"]["headings"][25] = "Notes"
        self._mutated(dupe, "OVERVIEW_HEADINGS_DUPLICATE")

    def test_removing_the_status_column_is_refused(self):
        def strip(doc):
            doc["tabs"]["Weekly Overview"]["status_columns"] = ["QC", "Overall"]
        self._mutated(strip, "STATUS_COLUMNS_NOT_1_3_0")

    def test_missing_drama_song_block_is_refused(self):
        def nuke(doc):
            doc.pop("drama_song", None)
        self._mutated(nuke, "DRAMA_SONG_BLOCK_MISSING")

    def test_widening_this_week_is_refused(self):
        def widen(doc):
            doc["tabs"]["This Week"]["headings"].append("Extra")
        self._mutated(widen, "THIS_WEEK_VIEW_DRIFT")

    def test_non_object_document_is_refused(self):
        self.assertEqual(ss.validate_contract(None), ["CONTRACT_NOT_AN_OBJECT"])
        self.assertEqual(ss.validate_contract([1, 2]), ["CONTRACT_NOT_AN_OBJECT"])


class CliTests(unittest.TestCase):
    def test_headings_flag_prints_the_1_3_0_row(self):
        rc, out, _ = run_cli("--headings")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), list(ss.WEEKLY_OVERVIEW_HEADINGS))

    def test_validate_shipped_contract_is_green(self):
        if CONTRACT is None:
            self.skipTest("contract not shipped beside this tree")
        rc, out, err = run_cli("--validate")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("0 failure(s)", out)

    def test_validate_a_mutated_contract_exits_1(self):
        doc = base_contract()
        doc["schema_version"] = "1.2.0"
        with tempfile.TemporaryDirectory(prefix="smp-w2u1-") as tmp:
            path = os.path.join(tmp, "contract.json")
            with open(path, "w") as handle:
                json.dump(doc, handle)
            rc, out, _ = run_cli("--validate", path)
        self.assertEqual(rc, 1)
        self.assertIn("SCHEMA_VERSION_NOT_1_3_0", out)

    def test_validate_an_absent_contract_exits_2(self):
        rc, _, err = run_cli("--validate", "/nonexistent/sheet-template.json")
        self.assertEqual(rc, 2)
        self.assertIn("CONTRACT_NOT_FOUND", err)

    def test_version_flag_reports_both_versions(self):
        rc, out, err = run_cli("--version")
        self.assertEqual(rc, 0)
        text = out + err
        self.assertIn("1.3.0", text)
        self.assertIn("1.2.0", text)


class ZeroPaidCallsTests(unittest.TestCase):
    """The suite touches temp dirs and pure functions; a socket must not open."""

    def test_work_completes_with_socket_stubbed_to_raise(self):
        def explode(*args, **kwargs):
            raise AssertionError("PAID_CALL: socket opened by schema 1.3.0")
        real = socket.socket
        socket.socket = explode
        try:
            doc = synthetic_contract()
            ss.upgrade_headings(list(ss.HEADINGS_1_2_0))
            ss.validate_contract(doc)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                ss.main(["--headings"])
        finally:
            socket.socket = real

    def test_module_imports_no_transport(self):
        forbidden = {"requests", "urllib", "http", "httpx", "socket",
                     "subprocess", "ssl", "ftplib", "telnetlib", "xmlrpc"}
        for path in MODULE_SOURCES:
            tree = ast.parse(open(path).read(), filename=path)
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module.split(".")[0])
            self.assertFalse(names & forbidden,
                             "%s imports transport: %r" % (path, names & forbidden))

    def test_module_has_no_os_system_or_kie_client(self):
        banned = ("os.system", "os.popen", "pty.spawn", "kie_dispatch",
                  "spend_ledger", "kie_live_adapter", "createTask", "kie.ai",
                  "74-kie", "anthropic", "openai")
        for path in MODULE_SOURCES:
            text = open(path).read()
            for token in banned:
                self.assertNotIn(token, text,
                                 "%s carries %s" % (path, token))


class StaticHygieneTests(unittest.TestCase):
    def test_module_sources_parse(self):
        for path in MODULE_SOURCES:
            ast.parse(open(path).read(), filename=path)

    def test_module_source_has_no_operator_path(self):
        for path in MODULE_SOURCES:
            self.assertNotIn("/Users/", open(path).read(), path)

    def test_unit_ships_only_python_sources(self):
        shipped = sorted(
            name for name in os.listdir(HERE)
            if name != "__pycache__" and not name.startswith("."))
        self.assertEqual(shipped, ["__init__.py", "sheet_schema_130.py",
                                   "test_sheet_schema_130.py"])
        media = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
                 ".mp3", ".wav", ".m4a", ".srt", ".pdf")
        for name in shipped:
            self.assertTrue(name.endswith(".py"), "non-python shipped: %s" % name)
            self.assertFalse(name.endswith(media), "media file shipped: %s" % name)

    def test_package_re_exports_the_contract_surface(self):
        tree = ast.parse(open(os.path.join(HERE, "__init__.py")).read())
        exported = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(
                    node.targets[0], "id", None) == "__all__":
                exported = {elt.value for elt in node.value.elts}
        for name in ("SCHEMA_VERSION", "WEEKLY_OVERVIEW_HEADINGS",
                     "DRAMA_SONG_FIELDS", "validate_contract",
                     "upgrade_headings"):
            self.assertIn(name, exported)


if __name__ == "__main__":
    unittest.main(verbosity=2)
