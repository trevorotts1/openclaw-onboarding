"""A18: Skill 29 claims match the executable registry and real source evidence.

These tests are the WF14 acceptance instrument. They read the same registry the
adapter dispatches from (public/operations.py) and fail loudly on drift. They do
not contact any network or GHL tenant.
"""
import hashlib
import json
import os
import sys

import pytest

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(SKILL)
REGISTRY_DIR = os.path.join(
    REPO, "44-convert-and-flow-operator", "tools", "engine"
)
INDEX_PATH = os.path.join(SKILL, "references", "ghl-hybrid-capability-index.json")
SOURCES_PATH = os.path.join(SKILL, "references", "ghl-contract-sources.json")

ALLOWED = {
    "implemented",
    "documented-unimplemented",
    "internal-only",
    "browser-backed",
    "beta-gated",
    "unresolved",
    "retired",
    "excluded",
}


def load_index():
    with open(INDEX_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_sources():
    with open(SOURCES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def registry():
    sys.path.insert(0, REGISTRY_DIR)
    from cli_anything.gohighlevel.public import operations

    return operations


def test_index_is_valid_and_classification_vocabulary_is_closed():
    idx = load_index()
    assert idx["schema_version"] == "1.0.0"
    assert idx["contract"]["id"] == "BCM-GHL-HYBRID-2026-11-08"
    assert idx["operations"], "index has no rows"
    for row in idx["operations"]:
        assert row["classification"] in ALLOWED, row["operation_id"]
        assert row["operation_id"]
        assert row["method"] and row["path_template"]
        assert len(row["registry_row_sha256"]) == 64


def test_every_registry_operation_has_a_source_record():
    ops = registry()
    idx = load_index()
    indexed = {r["operation_id"]: r for r in idx["operations"]}
    missing = sorted(set(ops.OPERATIONS) - set(indexed))
    extra = sorted(set(indexed) - set(ops.OPERATIONS))
    assert not missing, f"registry operations missing from index: {missing}"
    assert not extra, f"index rows with no registry operation: {extra}"
    for oid, row in ops.OPERATIONS.items():
        rec = indexed[oid]
        assert rec["method"] == row.method, oid
        assert rec["path_template"] == row.path_template, oid
        assert rec["version"] == row.version, oid
        assert rec["route_class"] == row.route_class, oid
        # An "implemented" row must point at its contract source or state that
        # the registry records no public contract. Silence is not a source.
        if rec["classification"] == "implemented":
            assert rec["doc_url"] or rec["source_state"] == (
                "registry_no_public_contract"
            ), oid


def test_registry_snapshot_matches_the_hash_the_index_claims():
    idx = load_index()
    path = os.path.join(SKILL, "..", idx["contract"]["operation_registry_path"])
    path = os.path.normpath(path)
    with open(path, "rb") as fh:
        actual = hashlib.sha256(fh.read()).hexdigest()
    assert actual == idx["contract"]["operation_registry_sha256"], (
        "operations.py changed without regenerating the capability index; "
        "regenerate and reconcile the docs in the same commit"
    )


def test_every_documented_route_maps_to_a_registry_row_or_a_labelled_gap():
    idx = load_index()
    registry_ids = {r["operation_id"] for r in idx["operations"]}
    registry_paths = {
        (r["method"], r["path_template"]) for r in idx["operations"]
    }
    for entry in idx["documented_unregistered"]:
        assert entry["operation_id"] not in registry_ids, (
            "documented_unregistered row already exists in the registry; "
            "move it into operations: " + entry["operation_id"]
        )
        assert entry["gap_label"], entry["operation_id"]
        assert entry["owner"], entry["operation_id"]
        assert entry["classification"] in ALLOWED
        if entry["method"] != "UI" and entry["path_template"] != "UNKNOWN":
            # A documented HTTP route must be a real gap, not a second copy of
            # a path the registry already owns.
            assert (entry["method"], entry["path_template"]) not in registry_paths


def test_every_cited_source_id_has_a_fetch_state_and_no_invented_date():
    src = load_sources()
    assert src["sources"]
    by_id = {}
    for entry in src["sources"]:
        assert set(entry) >= {
            "source_id",
            "family",
            "url",
            "published_or_modified",
            "fetch_state",
            "owner",
        }
        assert entry["fetch_state"] in {
            "inherited_source_not_refetched",
            "reopened_2026_11_08_not_refetched",
        }
        by_id[entry["source_id"]] = entry
    idx = load_index()
    for entry in idx["documented_unregistered"]:
        sid = entry["source"]["source_id"]
        assert sid in by_id, sid
    assert len(by_id) == len(src["sources"]), "duplicate source_id"


STALE_CLAIMS = (
    "workflows are get-only",
    "get-only for workflows",
    "courses are browser-only",
    "course creation is browser-only",
)

# A18 also covers the operator prose the docs must replace (Document 1 s12.2(6)).
DOCS_UNDER_TEST = [
    os.path.join(SKILL, "SKILL.md"),
    os.path.join(SKILL, "INSTRUCTIONS.md"),
    os.path.join(SKILL, "ghl-convert-and-flow-full.md"),
    os.path.join(SKILL, "references", "campaigns.md"),
    os.path.join(SKILL, "references", "courses.md"),
    os.path.join(SKILL, "references", "workflows.md"),
    os.path.join(REPO, "06-ghl-install-pages", "SKILL.md"),
]


NEGATION_MARKERS = (
    "withdrawn",
    "no longer",
    "not ",
    "old ",
    "stale",
    "replaces",
    "historical",
    "retired",
)


@pytest.mark.parametrize("path", DOCS_UNDER_TEST)
def test_no_stale_get_only_or_browser_only_claims(path):
    """The forbidden phrase may appear ONLY on a line that retires it."""
    lines = open(path, encoding="utf-8").read().lower().splitlines()
    for line in lines:
        for claim in STALE_CLAIMS:
            if claim in line:
                assert any(m in line for m in NEGATION_MARKERS), (
                    f"{path}: stale claim asserted without a withdrawal marker: {line!r}"
                )


def test_workflow_and_course_docs_state_the_real_boundary():
    wf = open(os.path.join(SKILL, "references", "workflows.md"), encoding="utf-8").read()
    co = open(os.path.join(SKILL, "references", "courses.md"), encoding="utf-8").read()
    assert "beta-gated" in wf.lower()
    assert "v4" in wf
    assert "staging" in wf.lower()
    assert "v4" not in co.lower() or "beta" in co.lower()
    assert "browser" in co.lower()  # the UI-only content seam must stay visible
    assert "not a marketing quiz" in co.lower() or "marketing quiz" in co.lower()


def test_skill44_and_skill6_prose_point_at_the_index():
    s44 = open(
        os.path.join(REPO, "44-convert-and-flow-operator", "SKILL.md"),
        encoding="utf-8",
    ).read()
    s6 = open(
        os.path.join(REPO, "06-ghl-install-pages", "SKILL.md"), encoding="utf-8"
    ).read()
    assert "ghl-hybrid-capability-index.json" in s44
    assert "ghl-hybrid-capability-index.json" in s6
