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
        candidate_commit=HEAD,
        candidate_branch="s75/T32",
        head_verified=True,
        worktree_clean=True,
        base_ref="origin/main",
        base_commit=BASE,
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
        _receipt(head_verified=False)
    except R.ReceiptError as exc:
        assert "head_verified" in str(exc)
    else:
        raise AssertionError("a receipt about another head was accepted")


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
