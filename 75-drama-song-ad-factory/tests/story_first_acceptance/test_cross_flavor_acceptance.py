#!/usr/bin/env python3
"""Dual-facet acceptance tests for S75-T32 / S75-A32.

Every one of the nine checks the acceptance row names is exercised against both
package flavors, through the flavor seam, against production code. Each check is
also proved failable: the condition it exists to detect is deliberately broken
and the cell must report FAIL; restored, it must report PASS.

Run:
    python3 -m pytest -q 75-drama-song-ad-factory/tests/story_first_acceptance
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cell_matrix as M  # noqa: E402
import run_acceptance as RUN  # noqa: E402

FLAVORS = ("onboarding", "999")

#: The nine checks exactly as the acceptance row names them, in row order.
ROW_CHECKS = (
    "missing_foundation",
    "cast_bypass",
    "scene_richness",
    "notion_migration",
    "identity_setting_change",
    "approval_ordering",
    "style18",
    "original_byte_preservation",
    "paid_compatibility",
)

#: What one production facet reports on its own, with no injected provider:
#: the seven checks whose modules exist run, and the two whose owning modules
#: do not exist at this head are named as blocked dependencies -- never skipped.
EXPECTED_STATUS = dict(
    {name: M.PASS for name in M.RUNNABLE_CELLS},
    **{name: M.BLOCKED for name in M.PROVIDER_CELLS}
)


# --- reference and broken providers for the two owed modules --------------
# These live in the test module only. They are not production modules and they
# are not pretended to be: the production facet reports the real absence.

def reference_migrate(library, dry_run=False, rollback=False):
    """A conforming implementation of the declared migration protocol."""
    if dry_run:
        return {"library": copy.deepcopy(library), "applied": False}
    if rollback:
        return {"library": copy.deepcopy(library), "applied": False}
    best = {}
    for character in library["characters"]:
        cid = character["character_id"]
        if cid not in best or character["revision"] > best[cid]["revision"]:
            best[cid] = copy.deepcopy(character)
    return {"library": {"characters": [best[k] for k in sorted(best)]},
            "applied": True}


def broken_migrate(library, dry_run=False, rollback=False):
    """Non-idempotent: every call duplicates the first character."""
    out = copy.deepcopy(library)
    out["characters"].append(copy.deepcopy(out["characters"][0]))
    return {"library": out, "applied": not dry_run}


def reference_classify(record):
    """A conforming implementation of the declared compatibility protocol."""
    legacy = record.get("schema") != "s75.scene.v1"
    return {
        "state": "COMPATIBILITY_LIMITED" if legacy else "COMPATIBLE",
        "readable": True,
        "regenerated": False,
    }


def broken_classify(record):
    """Regenerates paid legacy artifacts and calls them compatible."""
    return {"state": "COMPATIBLE", "readable": True, "regenerated": True}


PROVIDERS = {
    ("notion_migration", "good"): reference_migrate,
    ("notion_migration", "bad"): broken_migrate,
    ("paid_compatibility", "good"): reference_classify,
    ("paid_compatibility", "bad"): broken_classify,
}


# --- the matrix keeps all nine checks for both flavors --------------------

def test_required_checks_match_the_acceptance_row():
    assert ROW_CHECKS == M.REQUIRED_CHECKS
    assert M.cell_ids() == ROW_CHECKS
    assert len(ROW_CHECKS) == 9
    assert set(M.RUNNABLE_CELLS) | set(M.PROVIDER_CELLS) == set(ROW_CHECKS)
    assert not (set(M.RUNNABLE_CELLS) & set(M.PROVIDER_CELLS))


def test_both_flavors_resolve_through_the_single_seam():
    seen = {}
    for flavor in FLAVORS:
        facet = M.Facet(flavor)
        binding = facet.binding()
        assert binding["flavor"] == flavor
        assert binding["seam"] == "package_flavor_adapter.resolve"
        assert binding["core_digest_matches_seam"] is True
        assert binding["core_module"] == "story_first_contracts"
        seen[flavor] = binding
    # The flavors are genuinely distinct package facts over the same core bytes.
    assert (seen["onboarding"]["skill_root_anchor"]
            != seen["999"]["skill_root_anchor"])
    assert seen["onboarding"]["character_approval_present"] is True
    assert seen["999"]["character_approval_module"] is None
    assert seen["onboarding"]["core_sha256"] == seen["999"]["core_sha256"]


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("cell", ROW_CHECKS)
def test_cell_runs_for_every_facet(flavor, cell):
    facet = M.Facet(flavor)
    result = M.run_cell(cell, facet)
    assert result["cell"] == cell
    assert result["status"] == EXPECTED_STATUS[cell], result
    assert result["expected"], "a check with no stated expectation is not a check"
    if result["status"] == M.PASS:
        assert result["observed"], "a pass with no observation is not a pass"


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("cell", M.RUNNABLE_CELLS)
def test_cell_fails_when_its_condition_is_broken_then_passes_restored(flavor, cell):
    facet = M.Facet(flavor)
    broken = M.run_cell(cell, facet, broken=True)
    assert broken["status"] == M.FAIL, (
        "%s cannot fail for %s; it is not a check" % (cell, flavor))
    restored = M.run_cell(cell, facet)
    assert restored["status"] == M.PASS, restored


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("cell", M.PROVIDER_CELLS)
def test_dependency_cell_passes_with_a_conforming_provider(flavor, cell):
    facet = M.Facet(flavor)
    result = M.run_cell(cell, facet, provider=PROVIDERS[(cell, "good")])
    assert result["status"] == M.PASS, result


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("cell", M.PROVIDER_CELLS)
def test_dependency_cell_fails_with_a_broken_provider(flavor, cell):
    facet = M.Facet(flavor)
    result = M.run_cell(cell, facet, provider=PROVIDERS[(cell, "bad")])
    assert result["status"] == M.FAIL, (
        "%s cannot fail for %s; it is not a check" % (cell, flavor))


@pytest.mark.parametrize("flavor", FLAVORS)
@pytest.mark.parametrize("cell", M.PROVIDER_CELLS)
def test_blocked_cell_names_owner_and_exact_missing_path(flavor, cell):
    facet = M.Facet(flavor)
    result = M.run_cell(cell, facet)
    assert result["status"] == M.BLOCKED
    assert result["missing"], "a blocked cell must name the path it is waiting for"
    for path in result["missing"]:
        assert path.startswith(facet.core_dir)
        assert not os.path.exists(path)
    assert result["observed"]["owned_by"] in ("S75-T17", "S75-T28")


def test_style18_restores_the_production_catalog_after_a_break():
    facet = M.Facet("onboarding")
    catalog = facet.load("music_styles/catalog.py")
    before = list(catalog.style_ids())
    result = M.run_cell("style18", facet, broken=True)
    assert result["status"] == M.FAIL
    assert result["observed"]["restored"] is True
    assert list(catalog.style_ids()) == before
    assert M.run_cell("style18", facet)["status"] == M.PASS


# --- each facet releases its own repository -------------------------------

def test_each_facet_releases_its_own_repository(tmp_path):
    written = RUN.run(FLAVORS, str(tmp_path))
    assert [os.path.basename(p) for p, _ in written] == ["onboarding.json",
                                                         "999.json"]
    records = {}
    for path, record in written:
        stored = json.loads(open(path, encoding="utf-8").read())
        assert stored == json.loads(json.dumps(record))
        assert stored["schema"] == M.RELEASE_SCHEMA
        assert stored["repository"]["release_file"] == os.path.basename(path)
        assert stored["repository"]["name"]
        assert stored["repository"]["revision"]
        assert stored["binding"]["seam"] == "package_flavor_adapter.resolve"
        assert stored["counts"]["total"] == 9
        assert len(stored["cells"]) == 9
        records[stored["facet"]] = stored
    # Each facet carries its own package facts, not a copy of its sibling's.
    assert records["onboarding"]["repository"]["package_anchor"] != \
        records["999"]["repository"]["package_anchor"]
    assert records["onboarding"]["repository"]["package_layout_provisioned"] is True
    assert records["999"]["repository"]["package_layout_provisioned"] is False
    assert records["onboarding"]["binding"]["core_sha256"] == \
        records["999"]["binding"]["core_sha256"]


def test_a_facet_releases_without_the_sibling(tmp_path):
    written = RUN.run(("999",), str(tmp_path))
    assert len(written) == 1
    assert os.path.basename(written[0][0]) == "999.json"
    assert not os.path.exists(str(tmp_path / "onboarding.json"))
    record = json.loads(open(written[0][0], encoding="utf-8").read())
    assert record["counts"]["total"] == 9
    assert [c["cell"] for c in record["cells"]] == list(ROW_CHECKS)


def test_one_facet_failure_does_not_move_the_sibling_status(tmp_path):
    solo = RUN.run(("999",), str(tmp_path / "solo"))[0][1]
    broken = RUN.run(("onboarding",), str(tmp_path / "broken"), broken=True)[0][1]
    assert broken["release_status"] == M.FAIL
    assert broken["counts"]["fail"] == len(M.RUNNABLE_CELLS)
    after = RUN.run(("999",), str(tmp_path / "after"))[0][1]
    assert after["release_status"] == solo["release_status"]
    assert after["counts"] == solo["counts"]
    assert [c["status"] for c in after["cells"]] == \
        [c["status"] for c in solo["cells"]]


def test_release_is_deterministic(tmp_path):
    first = RUN.run(("onboarding",), str(tmp_path / "a"))[0][1]
    second = RUN.run(("onboarding",), str(tmp_path / "b"))[0][1]
    assert first["cells"] == second["cells"]
    assert first["binding"] == second["binding"]
    assert first["repository"]["revision"] == second["repository"]["revision"]


def test_release_names_an_exact_revision_or_unavailable():
    revision = M.repository_revision()
    assert revision == "UNAVAILABLE" or (
        len(revision) == 40 and all(c in "0123456789abcdef" for c in revision))
