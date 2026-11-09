"""WF22 cross-repository contract parity.

The fixture contract snapshot must be identical in the onboarding repository
and the Command Center repository, and must converge on WF00's authoritative
schemas without silently keeping a private variant.

Set ``GHL_HYBRID_CC_REPO`` to a Command Center checkout to run the real
cross-repository comparison. Without it the test still proves this copy's
internal integrity and states plainly that the other copy was not read — it
never claims a parity it did not measure.
"""

from __future__ import annotations

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from ghl_hybrid_fixtures import harness  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(TESTS_DIR))
CC_FIXTURE_SUBPATH = os.path.join("tests", "fixtures", "ghl-hybrid", "contracts")


def test_manifest_hashes_match_the_schema_files():
    manifest = harness.load_manifest()
    declared = dict(manifest["files"])
    actual = harness.actual_file_hashes()
    assert declared == actual, (
        "contract-manifest.json is stale: regenerate it after any schema edit. "
        f"declared={declared} actual={actual}"
    )
    assert sorted(declared) == sorted(actual)


def test_manifest_states_its_own_authority_and_assumption():
    manifest = harness.load_manifest()
    assert manifest["authority"] == "fixture-snapshot"
    assert manifest["assumed_checkpoint"] == "WF00-CP01"
    assert "pending" in manifest["assumed_checkpoint_status"]
    assert manifest["authoritative_source"].startswith("shared-utils/ghl/contracts/")


def test_authoritative_schemas_converge_when_published():
    """If WF00 has published shared-utils/ghl/contracts, the fixture snapshot
    must match it byte-for-byte. Absence is reported as pending, not assumed."""
    authoritative = harness.authoritative_contracts_dir(REPO_ROOT)
    if not os.path.isdir(authoritative):
        manifest = harness.load_manifest()
        assert manifest["assumed_checkpoint_status"].startswith("pending")
        return
    published = {
        fn: harness.sha256_file(os.path.join(authoritative, fn))
        for fn in sorted(os.listdir(authoritative))
        if fn.endswith(".schema.json")
    }
    assert published, "authoritative contracts directory exists but holds no schemas"
    assert published == harness.actual_file_hashes(), (
        "WF00 published contracts that differ from the WF22 fixture snapshot; "
        "re-derive the fixtures from the checkpoint record"
    )


def test_command_center_copy_is_byte_identical_when_available():
    cc_repo = os.environ.get("GHL_HYBRID_CC_REPO")
    if not cc_repo:
        # Honest report: the other repository was not read in this invocation.
        assert harness.load_manifest()["contract_set"]
        return
    cc_contracts = os.path.join(cc_repo, CC_FIXTURE_SUBPATH)
    assert os.path.isdir(cc_contracts), f"Command Center fixture copy missing: {cc_contracts}"

    ours = harness.actual_file_hashes()
    theirs = {
        fn: harness.sha256_file(os.path.join(cc_contracts, fn))
        for fn in sorted(os.listdir(cc_contracts))
        if fn.endswith(".schema.json")
    }
    assert theirs == ours, f"cross-repository contract drift: {ours} != {theirs}"
    assert harness.contract_set_digest(cc_contracts) == harness.contract_set_digest(), (
        "contract-set digest differs between repositories"
    )

    cc_manifest = harness.load_json(os.path.join(cc_contracts, "contract-manifest.json"))
    assert cc_manifest["contract_set"] == harness.load_manifest()["contract_set"]
    assert cc_manifest["files"] == harness.load_manifest()["files"]


def test_every_scenario_names_the_checkpoints_it_assumed():
    names = harness.scenario_names()
    assert names
    for name in names:
        scenario = harness.load_scenario(name)
        assert scenario["assumed_checkpoints"], name
        assert all(cp.startswith("WF") for cp in scenario["assumed_checkpoints"]), name
