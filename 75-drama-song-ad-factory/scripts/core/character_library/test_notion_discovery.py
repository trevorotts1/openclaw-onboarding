#!/usr/bin/env python3
"""S75-T14: Notion discovery and the new/existing/mixed cast choice.

Synthetic fixture only. No client workspace, credential or Notion call.
Run: python3 test_notion_discovery.py
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL = os.path.dirname(os.path.dirname(CORE))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_library import notion_adapter as NA  # noqa: E402

FIXTURE = os.path.join(SKILL, "tests", "fixtures", "notion_discovery.json")
FAKE_TOKEN = "ntn_fixture_SECRET_must_never_surface"


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class FakeConnection:
    """Stands in for the stored authorized connection. Holds a fake token only
    to prove the adapter never reaches for it."""

    connection_ref = "secure-connection-handle-only"
    api_version = NA.NOTION_API_VERSION

    def __init__(self, fx, scenario="single"):
        self.fx = fx
        self.scenario = scenario
        self.calls = []
        self.token = FAKE_TOKEN

    def _batch(self, batches, cursor):
        if cursor is None:
            return batches[0]
        for i, b in enumerate(batches):
            if i and batches[i - 1].get("next_cursor") == cursor:
                return b
        raise AssertionError("fixture has no batch for cursor %r" % cursor)

    def call(self, op, payload):
        self.calls.append({"op": op, "payload": payload})
        if op == "search":
            return self._batch(self.fx["search"][self.scenario], payload.get("start_cursor"))
        if op == "query_data_source":
            return self._batch(self.fx["catalog"]["existing"], payload.get("start_cursor"))
        if op == "read_page":
            page_id = payload["page_id"]
            return self.fx["read_pages"].get(page_id) or self.fx["created_page"]
        if op == "create_page":
            self.created = payload
            return self.fx["created_page"]
        raise AssertionError("unexpected operation %r" % op)


class DeadConnection:
    connection_ref = "secure-connection-handle-only"

    def call(self, op, payload):
        raise OSError("connection refused")


def registry_for(fx, page_id="page-fixture-library"):
    return {
        "schema": NA.SCHEMA_REGISTRY,
        "client_namespace": fx["client_namespace"],
        "connection_ref": "secure-connection-handle-only",
        "library_page_id": page_id,
        "data_source_id": "fixture-data-source-id",
        "schema_version": NA.SCHEMA_IDENTITY,
        "integration_api_version": NA.NOTION_API_VERSION,
        "catalog_revision": "",
        "sync_state": "IN_SYNC",
    }


class Discovery(unittest.TestCase):
    def setUp(self):
        self.fx = load_fixture()

    def test_existing_library_resolves_by_stored_id_first(self):
        conn = FakeConnection(self.fx)
        reg, trace = NA.resolve_client_library(
            conn, self.fx["client_namespace"], registry_for(self.fx))
        self.assertEqual(reg["library_page_id"], "page-fixture-library")
        self.assertEqual([c["op"] for c in conn.calls], ["read_page"])
        self.assertEqual(trace[-1]["step"], "resolved_by_stored_id")

    def test_duplicate_title_never_selects_another_client_library(self):
        conn = FakeConnection(self.fx, scenario="single")
        reg, trace = NA.resolve_client_library(conn, self.fx["client_namespace"])
        self.assertEqual(reg["library_page_id"], "page-fixture-library")
        self.assertEqual(reg["client_namespace"], self.fx["client_namespace"])
        self.assertEqual(trace[-1]["step"], "resolved_by_search")

    def test_two_matching_libraries_held_for_one_location_choice(self):
        conn = FakeConnection(self.fx, scenario="duplicate")
        with self.assertRaises(NA.AmbiguousLibrary) as caught:
            NA.resolve_client_library(conn, self.fx["client_namespace"])
        self.assertEqual(len(caught.exception.candidates), 2)
        result = NA.discover(conn, self.fx["client_namespace"])
        self.assertEqual(result["status"], "AMBIGUOUS_LOCATION")
        self.assertEqual(len(result["candidates"]), 2)

    def test_first_use_creates_inside_authorized_parent(self):
        conn = FakeConnection(self.fx, scenario="empty")
        result = NA.discover(conn, self.fx["client_namespace"],
                             parent_page_id=self.fx["parent_page_id"])
        self.assertEqual(result["status"], "FIRST_USE")
        self.assertFalse(result["library_ready"])
        self.assertNotIn("create_page", [c["op"] for c in conn.calls])

        reg, _ = NA.create_library(conn, self.fx["client_namespace"],
                                  self.fx["parent_page_id"])
        self.assertEqual(reg["library_page_id"], "page-created-fixture-library")
        self.assertEqual(reg["data_source_id"], "fixture-created-data-source-id")
        self.assertEqual(conn.created["parent"]["page_id"], self.fx["parent_page_id"])
        for call in conn.calls:
            blob = json.dumps(call).lower()
            self.assertNotIn("workspace", blob)          # no new-workspace API
            self.assertNotIn("create_workspace", blob)

    def test_first_use_without_authorized_parent_is_refused(self):
        conn = FakeConnection(self.fx, scenario="empty")
        with self.assertRaises(NA.DiscoveryError):
            NA.create_library(conn, self.fx["client_namespace"], "")
        self.assertEqual(conn.calls, [])

    def test_missing_connection_asks_for_reconnect_and_writes_nothing(self):
        for conn in (None, DeadConnection(), object()):
            with self.assertRaises(NA.ConnectionUnavailable) as caught:
                NA.discover(conn, self.fx["client_namespace"])
            message = str(caught.exception).lower()
            self.assertIn("secure connection", message)
            self.assertNotIn("api key", message)

    def test_catalog_is_fully_paginated_and_drafts_are_listed(self):
        conn = FakeConnection(self.fx)
        catalog, trace = NA.list_character_revisions(conn, registry_for(self.fx))
        self.assertEqual(catalog["pages_read"], 3)
        self.assertEqual(len(catalog["characters"]), 4)
        self.assertEqual(trace[-1]["step"], "catalog_read")
        draft = [c for c in catalog["characters"] if c["name"] == "Tobias Reed"][0]
        self.assertEqual(draft["approval_state"], "DRAFT")
        self.assertFalse(draft["has_reference_image"])
        self.assertEqual(draft["identity_revision"], "r1")
        names = [c["name"] for c in catalog["characters"]]
        self.assertEqual(names.count("Mara Vale"), 2)  # same name, distinct people

    def test_launch_offers_new_existing_mixed_and_catalog(self):
        conn = FakeConnection(self.fx)
        result = NA.discover(conn, self.fx["client_namespace"], registry_for(self.fx))
        self.assertEqual(result["status"], "READY")
        self.assertTrue(result["library_ready"])
        choice = result["choice"]
        self.assertEqual([o["mode"] for o in choice["options"]],
                         [NA.MODE_NEW, NA.MODE_EXISTING, NA.MODE_MIXED])
        self.assertEqual(choice["recommended"], NA.MODE_NEW)
        self.assertEqual(len(choice["catalog"]), 4)
        changed = NA.discover(conn, self.fx["client_namespace"], registry_for(self.fx),
                              previous_mode=NA.MODE_MIXED,
                              previous_ids=["char-fixture-mara"])
        self.assertEqual(changed["choice"]["recommended"], NA.MODE_MIXED)
        self.assertEqual(changed["choice"]["previous_choice"]["character_ids"],
                         ["char-fixture-mara"])
        self.assertEqual(len(changed["choice"]["catalog"]), 4)   # catalog always shown

    def test_existing_mode_requires_a_saved_pick(self):
        conn = FakeConnection(self.fx)
        catalog, _ = NA.list_character_revisions(conn, registry_for(self.fx))
        with self.assertRaises(NA.DiscoveryError):
            NA.resolve_cast_selection(NA.MODE_EXISTING, catalog)
        with self.assertRaises(NA.DiscoveryError):
            NA.resolve_cast_selection(NA.MODE_EXISTING, catalog,
                                      selected_character_ids=["char-not-mine"])
        with self.assertRaises(NA.DiscoveryError):
            NA.resolve_cast_selection("whatever", catalog)

    def test_mixed_cast_reuses_ids_and_creates_only_new_people(self):
        conn = FakeConnection(self.fx)
        catalog, _ = NA.list_character_revisions(conn, registry_for(self.fx))
        sel = NA.resolve_cast_selection(
            NA.MODE_MIXED, catalog,
            selected_character_ids=["char-fixture-mara"],
            new_characters=[{"name": "Nia Cole", "role": "supporting"}])
        self.assertEqual(sel["selection_mode"], NA.MODE_MIXED)
        self.assertEqual([c["character_id"] for c in sel["reused"]], ["char-fixture-mara"])
        self.assertEqual(sel["reused"][0]["identity_revision"], "r2")
        self.assertEqual(sel["new"][0]["name"], "Nia Cole")
        snapshot, manifest = NA.build_snapshot_and_manifest(
            registry_for(self.fx), catalog, sel)
        self.assertEqual(snapshot["client_namespace"], self.fx["client_namespace"])
        self.assertTrue(snapshot["snapshot_id"].startswith("snap-"))
        self.assertEqual(manifest["snapshot_digest"], NA._digest(snapshot))
        self.assertEqual([c["origin"] for c in manifest["cast"]], ["existing", "new"])
        self.assertTrue(manifest["complete"])

    def test_no_secret_reaches_trace_result_or_error(self):
        conn = FakeConnection(self.fx)
        result = NA.discover(conn, self.fx["client_namespace"], registry_for(self.fx))
        self.assertNotIn(FAKE_TOKEN, json.dumps(result))
        self.assertNotIn(FAKE_TOKEN, json.dumps(NA.resolve_cast_selection(
            NA.MODE_NEW, result["catalog"],
            new_characters=[{"name": "Nia Cole"}])))
        self.assertEqual(NA.scrub({"token": FAKE_TOKEN, "ok": 1}), {"ok": 1})
        with self.assertRaises(NA.DiscoveryError):
            NA.save_registry(os.path.join(HERE, ".should-not-exist.json"),
                             {"schema": NA.SCHEMA_REGISTRY, "token": FAKE_TOKEN})
        self.assertFalse(os.path.exists(os.path.join(HERE, ".should-not-exist.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
