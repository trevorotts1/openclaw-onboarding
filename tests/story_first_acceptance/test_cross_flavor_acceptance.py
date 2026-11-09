#!/usr/bin/env python3
"""Self-checks for the cross-flavor acceptance fixtures (S75-T32).

These are the checks that keep the fixtures honest:
  * every facet is green on ONB and RED on its deliberately unmet condition;
  * a missing candidate flavor is UNAVAILABLE, never a pass;
  * a receipt cannot self-issue an acceptance PASS;
  * a receipt about a different head is refused;
  * fixture drift is loud instead of guessed.

Run: python3 -m pytest -q tests/story_first_acceptance/test_cross_flavor_acceptance.py
 or: python3 tests/story_first_acceptance/test_cross_flavor_acceptance.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
ONB_ROOT = os.path.join(REPO_ROOT, "75-drama-song-ad-factory")
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_fixtures as F  # noqa: E402
import provenance as PV  # noqa: E402
import receipt as R  # noqa: E402

HEAD = "0" * 40
BASE = "1" * 40


def _ctx():
    return F.load_package(ONB_ROOT)


def _receipt(**overrides):
    fields = dict(
        flavor="onboarding",
        repository="trevorotts1/openclaw-onboarding",
        candidate={"repository": "trevorotts1/openclaw-onboarding", "commit": HEAD,
                   "branch": "s75/T32", "checkout_commit": HEAD,
                   "head_verified_at_execution": True,
                   "worktree_clean_excluding_receipts": True},
        harness={"repository": "trevorotts1/openclaw-onboarding",
                 "commit": HEAD, "branch": "s75/T32"},
        base={"repository": "trevorotts1/openclaw-onboarding",
              "ref": "origin/main", "commit": BASE},
        contracts={"skill_root": ONB_ROOT, "core_module": "story_first_contracts",
                   "adapter_module": "package_flavor_adapter", "seam": "package_flavor_adapter.resolve",
                   "core_digest": "d", "core_schema_version": "v", "stage_count": 11,
                   "file_digests": {}},
        dependencies={"python": "3"},
        executed=[{"facet": "package_seam_and_differences", "ok": True, "checks": 5,
                   "negative_control": {"unmet_condition": "collapsed layout",
                                        "facet_ok_on_unmet": False, "control_red": True}}],
        not_executed=[],
        literal_binding={"seam": "package_flavor_adapter.resolve",
                         "contract_module": "story_first_contracts",
                         "contract_files": ["scripts/core/story_first_contracts.py"]},
        checks={"facets_green": 1, "facets_red": 0, "controls_red": 1, "controls_green": 0},
        execution_verdict="PASS",
        unaffected_proof={"method": "one process per flavor", "cross_flavor_blocking": False},
        coverage={"covered": {}, "not_covered": {}, "rows_touched": []},
        author="S75-T32 builder (deepseek-chain)",
    )
    fields.update(overrides)
    return R.build(**fields)


def test_every_facet_green_and_control_red_on_onb():
    ctx = _ctx()
    red = []
    for facet in F.RECEIPT_FACETS:
        result = F.run_facet(ctx, facet)
        if not result["ok"]:
            red.append("%s stayed red on its positive case: %s" % (facet, result["reason"]))
        if not result["control"]["control_red"]:
            red.append("%s stayed GREEN on its unmet condition (vacuous fixture)" % facet)
    assert red == [], red


def test_missing_candidate_is_unavailable_not_pass():
    with tempfile.TemporaryDirectory() as empty:
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "facet_runner.py"),
             "--skill-root", empty, "--flavor", "999", "--facet", "all"],
            capture_output=True, text=True)
    assert proc.returncode == 2, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "UNAVAILABLE"
    assert len(payload["missing_sources_checked"]) == len(F.REQUIRED_CONTRACT_FILES)
    assert all(path.startswith(empty) for path in payload["missing_sources_checked"])


def test_receipt_cannot_self_issue_acceptance_pass():
    receipt = _receipt()
    assert receipt["acceptance"]["verdict"] == "PENDING_INDEPENDENT_CHECK"
    forged = json.loads(json.dumps(receipt))
    forged["acceptance"]["verdict"] = "PASS"
    forged["acceptance"]["checker"] = None
    try:
        R.validate(forged)
    except R.ReceiptError as exc:
        assert "checker" in str(exc)
    else:
        raise AssertionError("a self-issued acceptance PASS was accepted")


def test_receipt_accepts_named_distinct_checker():
    receipt = _receipt(checker="opus-chain reviewer #2")
    assert receipt["acceptance"]["verdict"] == "PASS"
    assert receipt["acceptance"]["checker_distinct_from_author"] is True


def test_receipt_refuses_unverified_head():
    try:
        _receipt(candidate={"repository": "r", "commit": HEAD, "branch": "b",
                            "checkout_commit": HEAD,
                            "head_verified_at_execution": False,
                            "worktree_clean_excluding_receipts": True})
    except R.ReceiptError as exc:
        assert "head_verified" in str(exc)
    else:
        raise AssertionError("a receipt about another head was accepted")


def test_unavailable_receipt_records_null_candidate():
    receipt = _receipt(execution_verdict="UNAVAILABLE",
                       candidate={"repository": "trevorotts1/999-setup", "commit": None,
                                  "branch": "unit/W77S-999-vendor",
                                  "checkout_commit": "2" * 40,
                                  "head_verified_at_execution": False,
                                  "worktree_clean_excluding_receipts": True},
                       not_executed=[{"facet": "all", "reason": "candidate skill root lacks contracts"}])
    assert receipt["candidate"]["commit"] is None
    assert receipt["acceptance"]["verdict"] == "UNAVAILABLE"
    try:
        _receipt(execution_verdict="UNAVAILABLE",
                 candidate={"repository": "trevorotts1/999-setup", "commit": HEAD,
                            "branch": "b", "checkout_commit": HEAD,
                            "head_verified_at_execution": False,
                            "worktree_clean_excluding_receipts": True},
                 not_executed=[{"facet": "all", "reason": "x"}])
    except R.ReceiptError as exc:
        assert "null" in str(exc)
    else:
        raise AssertionError("UNAVAILABLE was allowed to claim a candidate commit it never ran")


def test_receipt_refuses_green_control():
    try:
        _receipt(checks={"facets_green": 1, "facets_red": 0,
                         "controls_red": 0, "controls_green": 1})
    except R.ReceiptError as exc:
        assert "controls" in str(exc)
    else:
        raise AssertionError("a vacuous fixture set was accepted")


def test_fixture_drift_is_loud():
    try:
        F._record(("field_a", "field_b"), {"field_a": 1}, "demo")
    except F.FixtureDrift as exc:
        assert "field_b" in str(exc)
    else:
        raise AssertionError("a contract field with no fixture value was silently skipped")


def test_records_cover_every_contract_field():
    ctx = _ctx()
    records = F.build_records(ctx.core)
    assert set(records["identity"]) == set(ctx.core.IDENTITY_FIELDS)
    assert set(records["world"]) == set(ctx.core.WORLD_FIELDS)
    assert set(records["scene"]) == set(ctx.core.SCENE_FIELDS)
    assert all(f in records["manifest"]["cast"][0] for f in ctx.core.CAST_ENTRY_FIELDS)


def test_coverage_names_only_contract_rows():
    coverage = F.coverage()
    assert coverage["rows_touched"], "no acceptance row is claimed"
    for row in coverage["rows_touched"]:
        assert row.startswith("S75-A"), row
    assert "S75-A32" in coverage["rows_touched"]
    assert coverage["not_covered"], "the uncovered T32 facets must be stated"


# --- the eighteen S75-A32 cells (repair round 1) ---------------------------
# The round-1 verdict was FAIL because nine of the eighteen cells executed
# nothing. These checks are the ones that make that defect impossible to
# repeat silently: a cell either executes and reports, or it is refused.

import cell_matrix as C  # noqa: E402


def _onb_target():
    return C.Target("onboarding", "trevorotts1/openclaw-onboarding", ONB_ROOT)


def _cells():
    return C.run_cells(_onb_target())


def _valid_cells():
    """Nine minimal well-formed cells, for the refusal tests."""
    out = []
    for behavior in C.BEHAVIORS:
        out.append({
            "cell_id": "onboarding::%s" % behavior,
            "flavor": "onboarding",
            "behavior": behavior,
            "repository": "trevorotts1/openclaw-onboarding",
            "skill_root": ONB_ROOT,
            "executed": True,
            "status": "OBSERVED_PASS",
            "instrument": "demo",
            "checks": [],
            "observations": ["ran and observed something"],
            "known_good_control": {"pass": True, "expected": "known answer"},
            "negative_control": {"unmet_condition": "x", "observed": False,
                                 "control_red": True},
            "repository_release": {"own_repository_released": True,
                                   "identity_proven": True,
                                   "proven_repository": "trevorotts1/openclaw-onboarding",
                                   "release_refused": None,
                                   "foreign_repository_modules_loaded": []},
        })
    return out


def test_every_cell_executes_and_reports_an_observation():
    red = []
    for cell in _cells():
        if cell["executed"] is not True:
            red.append("%s executed nothing" % cell["behavior"])
        if not cell["observations"]:
            red.append("%s reported no observation" % cell["behavior"])
        if cell["known_good_control"]["pass"] is not True:
            red.append("%s has no passing known-good control" % cell["behavior"])
    assert red == [], red


def test_delivered_style18_and_byte_preservation_are_exercised_not_skipped():
    """S75-T18..T21 shipped both of these; a cell claiming otherwise is a lie."""
    by_behavior = {c["behavior"]: c for c in _cells()}
    for behavior in ("style18", "original byte preservation"):
        cell = by_behavior[behavior]
        assert cell["status"] == "OBSERVED_PASS", (behavior, cell["status"],
                                                   cell["observations"])
        assert cell["checks"], behavior


def test_dependency_behaviours_leave_the_row_and_name_their_owning_rows():
    """The arbiter's narrowing: this unit cannot exercise another unit's code."""
    by_behavior = {c["behavior"]: c for c in _cells()}
    for behavior in ("Notion migration", "paid compatibility"):
        assert behavior not in by_behavior, (
            "%r is still exercised by S75-T32; it belongs to another row" % behavior)
        assert behavior not in C.BEHAVIORS, behavior
        excluded = C.EXCLUDED_BEHAVIORS[behavior]
        assert excluded["moved_to_row"].startswith("S75-A"), excluded
        assert excluded["owed_by"].startswith("S75-T"), excluded
        assert excluded["reason"], excluded
    assert len(C.BEHAVIORS) == 7, C.BEHAVIORS
    assert len(by_behavior) == 7, by_behavior


def test_cells_release_their_own_repository():
    """The release claim is re-proved here, not re-read from the claim itself.

    Round 4 proved the old test could not fail: `foreign` was computed only
    against OTHER roots, so a planted directory became "own" and the test
    re-asserted the booleans `_release` had just computed. The oracle is now an
    independent provenance read of the same root.
    """
    proof = C.provenance.resolve(ONB_ROOT, "trevorotts1/openclaw-onboarding")
    assert proof["identity_proven"] is True, proof
    for cell in _cells():
        release = cell["repository_release"]
        assert release["identity_proven"] is True, cell["behavior"]
        assert release["proven_repository"] == proof["remote"], cell["behavior"]
        assert release["provenance"]["revision"] == proof["revision"], cell["behavior"]
        assert release["provenance"]["digest"] == proof["digest"], cell["behavior"]
        assert release["own_repository_released"] is True, cell["behavior"]
        assert release["release_refused"] is None, cell["behavior"]
        assert release["foreign_repository_modules_loaded"] == [], cell["behavior"]
        assert release["all_paths_inside_own_repository"] is True, cell["behavior"]


def test_a_planted_directory_cannot_mint_a_release_claim():
    """The round-4 spoof, executed: os.path.isdir must decide nothing.

    A directory holding real skill bytes, named as the 999 flavour's root, used
    to produce a green `own_repository_released` for trevorotts1/999-setup. It
    must now be REFUSED, with the reason on the record, and the cells that run
    there must refuse the claim themselves.
    """
    with tempfile.TemporaryDirectory() as tmp:
        planted = os.path.join(tmp, ".claude", "skills", "drama-song-ad-factory")
        os.makedirs(planted)
        with open(os.path.join(planted, "SKILL.md"), "w") as fh:
            fh.write("# planted bytes, no provenance\n")
        target = C.Target("999", "trevorotts1/999-setup", planted)
        assert target.identity_proven is False, target.provenance
        assert target.provenance["refusals"], target.provenance
        assert target.provenance["proven_repository"] is None, target.provenance
        cells = C.run_cells(target)
        assert len(cells) == 7, cells
        for cell in cells:
            release = cell["repository_release"]
            assert release["identity_proven"] is False, cell["behavior"]
            assert release["own_repository_released"] is False, cell["behavior"]
            assert release["release_refused"], cell["behavior"]
        forged = _valid_cells()
        forged[0]["repository_release"] = dict(cells[0]["repository_release"])
        try:
            _receipt(cells=forged)
        except R.ReceiptError as exc:
            assert "identity" in str(exc), str(exc)
        else:
            raise AssertionError("a release claim without provenance was accepted")


def test_a_root_from_another_repository_cannot_borrow_the_name():
    """Remote + revision + digest must match the DECLARED repository, not just exist."""
    proof = C.provenance.resolve(ONB_ROOT, "trevorotts1/999-setup")
    assert proof["identity_proven"] is False, proof
    assert any("origin is trevorotts1/openclaw-onboarding" in line
               for line in proof["refusals"]), proof["refusals"]


# --- both facets, all nine, each one able to fail (repair round 4) ---------
# Round 3 shipped the cells for one flavor only and round 1 re-derived them on
# a branch that never carried the pin fix. These three checks are the ones that
# make "both facets exercise the full check set" and "each check can fail"
# measurable rather than asserted: eighteen cells, nine per flavor, every one
# with checks of its own, and every one shown red when its condition is broken.

FACET_FLAVORS = ("onboarding", "999")

def _facet_target(flavor):
    return C.facet_target(flavor, REPO_ROOT)

def _facet_cells(flavor):
    return C.run_cells(_facet_target(flavor))

def test_both_facets_execute_all_seven_narrowed_cells():
    """Seven narrowed behaviours x two flavors = fourteen cells, all executed."""
    seen = []
    for flavor in FACET_FLAVORS:
        cells = _facet_cells(flavor)
        assert [c["behavior"] for c in cells] == list(C.BEHAVIORS), (
            flavor, [c["behavior"] for c in cells])
        for cell in cells:
            seen.append((flavor, cell["behavior"]))
            assert cell["flavor"] == flavor, cell["cell_id"]
            assert cell["executed"] is True, (flavor, cell["behavior"])
            assert cell["observations"], (flavor, cell["behavior"])
            assert cell["checks"], ("%s reported no executed check" % cell["cell_id"])
            assert cell["known_good_control"]["pass"] is True, cell["cell_id"]
            # clause 2, per cell: fourteen proven releases, not fourteen labels
            release = cell["repository_release"]
            assert release["identity_proven"] is True, cell["cell_id"]
            assert release["own_repository_released"] is True, cell["cell_id"]
    assert len(seen) == 14, seen
    assert len(set(seen)) == 14, seen

def test_every_cell_can_be_shown_failing():
    """A check that cannot go red is a line in a list, not a check."""
    dead = []
    for flavor in FACET_FLAVORS:
        for cell in _facet_cells(flavor):
            if cell["negative_control"]["control_red"] is not True:
                dead.append("%s::%s never went red on its unmet condition"
                            % (flavor, cell["behavior"]))
    assert dead == [], dead

def test_each_facet_records_its_own_package_binding():
    """Each facet resolves the seam itself and states what it is bound to."""
    onb = _facet_target("onboarding").binding()
    n999 = _facet_target("999").binding()
    assert onb["flavor"] == "onboarding" and n999["flavor"] == "999"
    assert onb["core_digest_matches_seam"] is True, onb
    assert n999["core_digest_matches_seam"] is True, n999
    assert onb["skill_root_anchor"] != n999["skill_root_anchor"], (onb, n999)
    assert onb["character_approval_module"] != n999["character_approval_module"], (
        onb, n999)
    # Each facet states the identity it can PROVE. The onboarding facet runs in
    # this repository, so its provenance is read from git and proves the declared
    # remote, revision and digest.
    assert onb["identity_proven"] is True, onb["provenance"]
    assert onb["provenance"]["remote"] == "trevorotts1/openclaw-onboarding", onb
    assert onb["provenance"]["revision"] and onb["provenance"]["digest"], onb
    # 999 has no provisioned anchor in this checkout; the record says so rather
    # than presenting the shared core as a 999 package. It is therefore bound to
    # the onboarding repository's bytes -- which it PROVES -- and its own release
    # claim is refused. Round 4's hard-coded "shared-core" assertion is gone: it
    # passed only while the anchor was missing and could not see a spoof.
    assert n999["package_layout_provisioned"] is False, n999
    assert n999["root_source"] == "shared-core", n999
    assert n999["package_layout_missing"], n999
    assert n999["repository"] == "trevorotts1/openclaw-onboarding", n999
    assert n999["identity_proven"] is True, n999["provenance"]
    assert n999["provenance"]["proven_repository"] != "trevorotts1/999-setup", n999


def _forget_modules_under(path):
    """Drop modules imported from a temp tree so a later facet re-imports its own."""
    root = os.path.realpath(path)
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and os.path.realpath(filename).startswith(root + os.sep):
            del sys.modules[name]


def test_a_provisioned_anchor_without_provenance_is_refused_not_relabelled():
    """The seam path takes the round-4 spoof head on: a 999 anchor that is not 999."""
    with tempfile.TemporaryDirectory() as repo:
        prefix = os.path.join(repo, "75-drama-song-ad-factory")
        os.makedirs(prefix)
        # the real shared core, so the SEAM resolves; only the 999 anchor is planted
        shutil.copytree(os.path.join(ONB_ROOT, "scripts"),
                        os.path.join(prefix, "scripts"))
        anchor = os.path.join(repo, ".claude", "skills", "drama-song-ad-factory")
        os.makedirs(anchor)
        with open(os.path.join(anchor, "SKILL.md"), "w") as fh:
            fh.write("# planted 999 anchor\n")
        try:
            target = C.facet_target("999", repo_root=repo)
        finally:
            _forget_modules_under(repo)
        assert target.root_source == "unproven-anchor", target.root_source
        assert target.package_layout_provisioned is False, target.binding()
        assert target.identity_proven is False, target.provenance
        assert target.provenance["refusals"], target.provenance
        release = C._release(target, C._snapshot(), [os.path.join(anchor, "SKILL.md")])
        assert release["own_repository_released"] is False, release
        assert "999-setup" in release["repository"], release


def test_receipt_refuses_a_cell_that_executed_nothing():
    cells = _valid_cells()
    cells[0]["executed"] = False
    cells[0]["observations"] = []
    try:
        _receipt(cells=cells)
    except R.ReceiptError as exc:
        assert "executed nothing" in str(exc)
    else:
        raise AssertionError("a receipt with an inert cell was accepted")


def test_receipt_refuses_not_applicable_without_the_owing_unit():
    cells = _valid_cells()
    cells[3]["status"] = "NOT_APPLICABLE"
    cells[3]["not_applicable"] = {"missing_capability": "something"}
    try:
        _receipt(cells=cells)
    except R.ReceiptError as exc:
        assert "owes" in str(exc)
    else:
        raise AssertionError("a NOT_APPLICABLE cell with no owing unit was accepted")


def test_receipt_refuses_a_cell_count_mismatch():
    cells = _valid_cells()
    try:
        _receipt(cells=cells,
                 checks={"facets_green": 1, "facets_red": 0,
                         "controls_red": 1, "controls_green": 0,
                         "cells_total": 9, "cells_pass": 8,
                         "cells_fail": 0, "cells_not_applicable": 1})
    except R.ReceiptError as exc:
        assert "cells" in str(exc)
    else:
        raise AssertionError("cell counts that disagree with the cells were accepted")


def test_cell_instruments_discriminate():
    """A control that cannot go red is worthless; prove the predicates can."""
    assert C.selfcheck() is True

# --- the two style18 breakages the arbiter carried as an open limit --------
# S75-T32-ARBITER.md, "Stated limits": the falsifiability instrument detected
# ten of twelve planted breakages; the two it missed were style18 —
# "choice_rows() renders 17 of 18 rows" and "validate_catalog() hard-wired to
# 18". These checks close that gap, each with the breakage planted.

def _catalog_module(tag):
    """A fresh import of this repository's catalog, never the shared instance."""
    return C._load_module(os.path.join(ONB_ROOT, C.CATALOG_REL),
                          "s75_t32_style18_%s" % tag)


def test_validate_catalog_derives_its_count_and_refuses_a_short_catalog():
    """A validator hard-wired to 18 accepts a catalog that lost a record."""
    real = _catalog_module("derive")
    ids = tuple(real.style_ids())
    # Known-good: the shipped validator accepts all eighteen.
    assert real.validate_catalog() == len(ids) == 18
    # The breakage: one record gone. A derived validator must refuse it.
    real.CATALOG.pop(ids[-1])
    refused = False
    try:
        real.validate_catalog()
    except real.CatalogError as exc:
        refused = exc.code == "BAD_CATALOG"
    assert refused, "validate_catalog accepted a catalog missing %r" % (ids[-1],)
    # The exact arbiter breakage: the same function replaced by a literal 18
    # cannot refuse, so the assertion above is what catches it.
    hard_wired = _catalog_module("hardwired")
    hard_wired.CATALOG.pop(ids[-1])
    hard_wired.validate_catalog = lambda: 18
    assert hard_wired.validate_catalog() == 18, (
        "the planted hard-wired validator should return its literal")


def test_style18_choice_rows_cover_the_eighteenth_row():
    """Counting eighteen dicts is not rendering eighteen rows."""
    module = _catalog_module("rows")
    ids = tuple(module.style_ids())
    rows = module.choice_rows()
    assert len(rows) == 18, len(rows)
    assert C._choice_rows_well_formed(ids, rows) is True
    last = rows[17]
    assert last["style_id"] == ids[17], (last["style_id"], ids[17])
    assert last["label"].strip(), "the eighteenth row has no label"
    assert last["description"].strip(), "the eighteenth row has no description"
    # The breakage: the eighteenth row renders empty. A length-only check
    # stays green; the row predicate must red.
    module.CATALOG[ids[17]]["description"] = ""
    broken = module.choice_rows()
    assert len(broken) == 18, "the planted breakage changed the row count"
    assert C._choice_rows_well_formed(ids, broken) is False, (
        "the eighteenth row rendered empty and was accepted")


def test_style18_predicate_reds_each_named_breakage_alone():
    """Each breakage, planted by itself, reds an otherwise-green carrier."""
    ids = tuple("s%02d" % i for i in range(18))
    green = C._style18_checks(ids, 18, 18, 18, 18, True, True)
    assert C._result(green) is True
    short_validate = C._style18_checks(ids, 18, 18, 17, 18, True, True)
    assert C._result(short_validate) is False, "a validate count one short passed"
    broken_row = C._style18_checks(ids, 18, 18, 18, 18, False, True)
    assert C._result(broken_row) is False, "a broken choice row passed"


def test_validate_catalog_refuses_a_max_styles_that_disagrees():
    """MAX_STYLES 17 against 18 names is a short catalog wearing a smaller label."""
    module = _catalog_module("maxstyles")
    assert module.validate_catalog() == len(module.STYLE_IDS) == 18
    module.MAX_STYLES = 17
    refused = False
    try:
        module.validate_catalog()
    except module.CatalogError as exc:
        refused = exc.code == "BAD_CATALOG" and "MAX_STYLES declares 17" in str(exc)
    assert refused, "validate_catalog accepted MAX_STYLES 17 against 18 names"


def test_validate_catalog_refuses_catalog_keys_out_of_order():
    """Same records, different key order, is drift the count check cannot see."""
    module = _catalog_module("keyorder")
    keys = list(module.CATALOG)
    assert tuple(keys) == tuple(module.STYLE_IDS)
    moved = keys[-1]
    reordered = {moved: module.CATALOG[moved]}
    reordered.update({k: v for k, v in module.CATALOG.items() if k != moved})
    module.CATALOG = reordered
    refused = False
    try:
        module.validate_catalog()
    except module.CatalogError as exc:
        refused = exc.code == "BAD_CATALOG" and "keys differ" in str(exc)
    assert refused, "validate_catalog accepted catalog keys out of STYLE_IDS order"


# --- the demonstration script --------------------------------------------
# demonstrate_checks.py is the runnable form of "every cell can be shown red".
# It was written against a run_cells(broken=True) API that no longer exists, so
# it died with a TypeError while the suite stayed green. These two checks keep
# it alive and keep it able to fail.

import demonstrate_checks as D  # noqa: E402


def _run_demonstration(argv):
    """Call the demonstration script and return (rc, captured stdout)."""
    out = []
    sink = type("Sink", (), {"write": lambda self, text: out.append(text),
                             "flush": lambda self: None})()
    original = sys.stdout
    sys.stdout = sink
    try:
        rc = D.main(argv)
    finally:
        sys.stdout = original
    return rc, "".join(out)


def test_demonstration_shows_both_sides_of_every_cell():
    rc, text = _run_demonstration(["--json"])
    assert rc == 0, text[-800:]
    payload = json.loads(text)
    assert payload["all_demonstrated"] is True, text[-800:]
    assert len(payload["rows"]) == 14, len(payload["rows"])
    assert {r["flavor"] for r in payload["rows"]} == {"onboarding", "999"}
    assert {r["behavior"] for r in payload["rows"]} == set(C.BEHAVIORS)


def test_demonstration_refuses_a_cell_that_never_went_red():
    """A cell whose control stayed green is not a demonstrated check."""
    real = C.run_cells

    def blind(target):
        cells = real(target)
        cells[0]["negative_control"] = dict(cells[0]["negative_control"],
                                           control_red=False)
        return cells

    C.run_cells = blind
    try:
        rc, text = _run_demonstration(["--json", "--flavors", "onboarding"])
    finally:
        C.run_cells = real
    assert rc == 1, text[-800:]
    payload = json.loads(text)
    assert payload["all_demonstrated"] is False
    assert payload["rows"][0]["failable"] is False


# --- the revision pin (repair round 3) ------------------------------------
# Round 3 measured six of nine N999 cells from a working tree sitting 55 commits
# behind its own origin/main. These checks are the ones that make a silent stale
# resolution impossible: take the pin out and they go red.

import run_acceptance as RA  # noqa: E402


def _git_run(path, *args):
    return subprocess.run(["git", "-C", path] + list(args),
                          capture_output=True, text=True, check=True)


def _seed_tree(path):
    """A one-commit worktree whose origin/main already holds that commit."""
    os.makedirs(path)
    _git_run(path, "init", "-q")
    _git_run(path, "config", "user.email", "s75-t32@example.invalid")
    _git_run(path, "config", "user.name", "S75-T32 self-check")
    # provenance requires a remote: a worktree with no origin cannot say WHICH
    # repository it is, and an identity-free root cannot release anything.
    _git_run(path, "remote", "add", "origin",
             "https://github.com/trevorotts1/openclaw-onboarding.git")
    with open(os.path.join(path, "skill.txt"), "w") as fh:
        fh.write("head\n")
    _git_run(path, "add", "skill.txt")
    _git_run(path, "commit", "-q", "-m", "seed")
    head = _git_run(path, "rev-parse", "HEAD").stdout.strip()
    _git_run(path, "update-ref", "refs/remotes/origin/main", head)
    return head


def test_resolve_flavors_refuses_a_dirty_checkout():
    """A dirty root is refused, and the refusal records why."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "skill")
        _seed_tree(root)
        with open(os.path.join(root, "skill.txt"), "a") as fh:
            fh.write("uncommitted drift\n")
        flavors = RA.resolve_flavors(
            tmp, types.SimpleNamespace(onb_skill_root=root, n999_skill_root=None),
            ["onboarding"])
        gate = flavors["onboarding"]["revision_gate"]
        assert gate["status"] == "REFUSED", gate
        assert any("dirty" in line for line in gate["violations"]), gate["violations"]
        payload = RA.run_flavor("onboarding", flavors["onboarding"])
        assert payload["status"] == "UNAVAILABLE", payload["status"]
        assert payload["reason"].startswith("REFUSED"), payload["reason"]
        assert payload["revision_gate"]["violations"], "a refusal that states no reason is silent"
        # and the refusal survives into the receipt, where it cannot be missed
        receipt = RA.build_receipt(
            "onboarding", root,
            types.SimpleNamespace(base_ref="origin/main", candidate=None,
                                  author="S75-T32 self-check", checker=None),
            payload,
            {"repository": "trevorotts1/openclaw-onboarding", "skill_root": root},
            flavors["onboarding"])
        assert receipt["execution"]["verdict"] == "UNAVAILABLE"
        assert receipt["candidate"]["commit"] is None
        assert receipt["candidate"]["revision_gate"]["status"] == "REFUSED"
        assert any("REFUSED" in row["reason"] for row in receipt["not_executed"])


def test_resolve_flavors_refuses_a_stale_non_origin_revision():
    """The round-3 defect exactly: a clean tree that origin has never seen."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "skill")
        _seed_tree(root)                      # origin/main == HEAD here
        with open(os.path.join(root, "skill.txt"), "a") as fh:
            fh.write("55 commits of drift\n")
        _git_run(root, "add", "skill.txt")
        _git_run(root, "commit", "-q", "-m", "drift not on origin")
        flavors = RA.resolve_flavors(
            tmp, types.SimpleNamespace(onb_skill_root=root, n999_skill_root=None),
            ["onboarding"])
        gate = flavors["onboarding"]["revision_gate"]
        assert gate["status"] == "REFUSED", gate
        assert gate["is_origin_revision"] is False, gate
        assert gate["at_origin_main"] is False, gate
        assert any("origin" in line for line in gate["violations"]), gate["violations"]
        payload = RA.run_flavor("onboarding", flavors["onboarding"])
        assert payload["reason"].startswith("REFUSED"), payload["reason"]


def test_resolve_flavors_accepts_a_clean_origin_revision():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "skill")
        _seed_tree(root)
        gate = RA.revision_gate(root)
        assert gate["status"] in ("AT_ORIGIN_MAIN", "ORIGIN_REVISION"), gate
        assert gate["violations"] == [], gate["violations"]


def test_extracted_tree_is_measurable_only_when_its_bytes_are_pinned():
    """A revision-shaped directory name is a label. The pin must carry the bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        anonymous = os.path.join(tmp, "tree")
        os.makedirs(anonymous)
        assert RA.revision_gate(anonymous)["status"] == "REFUSED"

        pinned = os.path.join(tmp, "pins", "999-setup", RA.N999_PIN_REVISION, "skill")
        os.makedirs(pinned)
        with open(os.path.join(pinned, "SKILL.md"), "w") as fh:
            fh.write("# the pinned bytes\n")
        # named by its revision, but the pin declares no digest: REFUSED
        bare = RA.revision_gate(pinned, "trevorotts1/999-setup",
                                RA.PINS["999"])
        assert bare["status"] == "REFUSED", bare
        assert any("no tree digest" in line for line in bare["violations"]), bare

        # with the digest pinned, the same tree is attributable
        digest = PV.file_digest(pinned)
        assert digest
        attributed = RA.revision_gate(
            pinned, "trevorotts1/999-setup",
            dict(RA.PINS["999"], digest=digest))
        assert attributed["status"] == "PINNED_REVISION", attributed
        assert attributed["revision"] == RA.N999_PIN_REVISION


def test_default_n999_root_is_pinned_to_a_revision_not_a_live_tree():
    """THE PIN. Remove it - or point the default back at ~/999-setup - and this fails."""
    assert RA._pinned_revision_of(RA.N999_PIN_ROOT) == RA.N999_PIN_REVISION
    assert RA.N999_PIN_ROOT == os.path.join(HERE, "pins", "999-setup",
                                            RA.N999_PIN_REVISION)
    default = os.path.join(RA.N999_PIN_ROOT, ".claude", "skills",
                           "drama-song-ad-factory")
    candidates = RA.default_n999_candidates(
        types.SimpleNamespace(n999_skill_root=None))
    built_in = [c for c in candidates
                if c not in (None, os.environ.get("S75_999_SKILL_ROOT"))]
    assert built_in == [default], built_in


def test_receipt_takes_the_candidate_revision_from_the_pin():
    """An extracted tree has no git; the pin is its revision. Get it from the gate.

    Two states, both asserted: a pinned tree whose digest is NOT declared is
    REFUSED (no candidate, the refusal carried); a pinned tree whose digest
    matches is PINNED_REVISION and its revision reaches the receipt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        checkout = os.path.join(tmp, "checkout")
        _seed_tree(checkout)
        root = os.path.join(tmp, "pins", "999-setup", RA.N999_PIN_REVISION, "skill")
        os.makedirs(root)
        with open(os.path.join(root, "SKILL.md"), "w") as fh:
            fh.write("# pinned\n")
        digest = PV.file_digest(root)
        original = RA.PINS["999"]["digest"]
        args = types.SimpleNamespace(onb_skill_root=None, n999_skill_root=root)
        try:
            RA.PINS["999"]["digest"] = None
            refused = RA.resolve_flavors(tmp, args, ["999"])["999"]
            assert refused["revision_gate"]["status"] == "REFUSED", refused
            assert refused["revision_gate"]["provenance"]["identity_proven"] is False

            RA.PINS["999"]["digest"] = digest
            info = RA.resolve_flavors(tmp, args, ["999"])["999"]
            assert info["revision_gate"]["status"] == "PINNED_REVISION", info["revision_gate"]
            receipt = RA.build_receipt(
                "999", checkout,
                types.SimpleNamespace(base_ref="origin/main", candidate=None,
                                      author="S75-T32 self-check",
                                      checker="opus-chain reviewer #2"),
                {"status": "PASS", "facets": [], "cells": _valid_cells(),
                 "skill_root": root},
                {"repository": "trevorotts1/999-setup", "skill_root": root}, info)
            assert receipt["candidate"]["commit"] == RA.N999_PIN_REVISION
            assert receipt["candidate"]["revision_gate"]["status"] == "PINNED_REVISION"
            assert receipt["candidate"]["repository_identity"]["identity_proven"] is True
        finally:
            RA.PINS["999"]["digest"] = original


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)
