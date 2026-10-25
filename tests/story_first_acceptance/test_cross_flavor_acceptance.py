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


def test_absent_capabilities_are_not_applicable_and_name_the_owing_unit():
    by_behavior = {c["behavior"]: c for c in _cells()}
    for behavior in ("Notion migration", "paid compatibility"):
        cell = by_behavior[behavior]
        assert cell["status"] == "NOT_APPLICABLE", (behavior, cell["status"])
        na = cell["not_applicable"]
        assert na["missing_capability"], behavior
        assert na["owed_by"], behavior
        assert na["blocked_by"], behavior
        # the scan still ran and still reported what it saw
        assert any("absent" in line for line in cell["observations"]), behavior


def test_cells_release_their_own_repository():
    for cell in _cells():
        release = cell["repository_release"]
        assert release["own_repository_released"] is True, cell["behavior"]
        assert release["foreign_repository_modules_loaded"] == [], cell["behavior"]
        assert release["all_paths_inside_own_repository"] is True, cell["behavior"]


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


def test_extracted_tree_is_measurable_only_when_named_by_its_revision():
    with tempfile.TemporaryDirectory() as tmp:
        anonymous = os.path.join(tmp, "tree")
        os.makedirs(anonymous)
        assert RA.revision_gate(anonymous)["status"] == "REFUSED"
        pinned = os.path.join(tmp, "pins", "999-setup", RA.N999_PIN_REVISION, "skill")
        os.makedirs(pinned)
        gate = RA.revision_gate(pinned)
        assert gate["status"] == "PINNED_REVISION", gate
        assert gate["revision"] == RA.N999_PIN_REVISION


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
