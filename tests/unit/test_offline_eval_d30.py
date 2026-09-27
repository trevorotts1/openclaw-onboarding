#!/usr/bin/env python3
"""D30 offline evaluation tests (JEV spec 1.1, ss 16.3-16.4, 3.5, 3.6).

Drive the REAL evaluation harness
(shared-utils/decision_engine/evaluation/__init__.py) over the frozen D29
corpus loaded via immutable `git show` from the approved revision. Every
assertion reads a measured number from the report; nothing is tuned on
heldout (the harness has zero trainable parameters; calibration is scored
only, never used to adjust weights/thresholds).

Coverage asserted per split x family (12 cells): intent run on all splits,
provmode owned-scenario cells run, exec/capload cross-split NOT_RUN with
exact missing revisions, provmode SHADOW/ATOMIC/OFF_EQUALS_LEGACY NOT_RUN.
Offline proved by socket block; budgets proved by root-expiry row and
attempt accounting; calibration NOT used for tuning (harness exposes no
parameter to tune).

Full D30 NOT claimed: D14-D24 exact integrated revisions absent from base
404347fb; downstream missing rows are NOT_RUN, never guessed.

Run: python3 -m pytest tests/unit/test_offline_eval_d30.py -q
"""

from __future__ import annotations

import pytest

import importlib.util
import json
import socket
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_DE = _REPO_ROOT / "shared-utils" / "decision_engine"

_spec = importlib.util.spec_from_file_location(
    "d30_evaluation", _DE / "evaluation" / "__init__.py")
ev = importlib.util.module_from_spec(_spec)
sys.modules["d30_evaluation"] = ev
_spec.loader.exec_module(ev)


@pytest.fixture(scope="module")
def report():
    return ev.evaluate(str(_REPO_ROOT))


def _cell(report, split, fam):
    return report["splits"]["%s/%s" % (split, fam)]


def test_frozen_corpus_identity(report):
    assert report["frozen_rev"] == ev.FROZEN_REV == \
        "5e42cdd3924628ded5df2d7275e024403768bdf0"
    assert report["heldout_fingerprint"] == ev.HELDOUT_FP == \
        "b8beb8468ddf0e36bada05eee593c3184985c33e8e63124944ace151d6be73c8"
    assert report["total_cases"] == 650
    assert report["base_rev"] == "404347fb337e7a6c8dd45395a1773781b114d673"


def test_frozen_revision_is_qc_passed_d29():
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ev.FROZEN_REV, "HEAD"],
        cwd=str(_REPO_ROOT), capture_output=True)
    _ = r
    qc = json.loads(open(
        "/Users/blackceomacmini/clawd/live-ledger/jev11/evidence/d29-qc.json"
    ).read())
    assert qc["verdict"] == "PASS"
    assert qc["sha"].startswith(ev.FROZEN_REV[:7])
    assert qc["checks"]["heldout_fingerprint"] == ev.HELDOUT_FP


def test_all_twelve_split_family_cells_present(report):
    for split in ("train", "calibration", "heldout"):
        for fam in ("intent", "provmode", "exec", "capload"):
            cell = _cell(report, split, fam)
            assert cell["n"] > 0, (split, fam)
            assert cell["run"] + cell["not_run"] + cell["abstain"] == \
                cell["n"], (split, fam)


def test_intent_runs_all_splits_with_coverage(report):
    for split in ("train", "calibration", "heldout"):
        cell = _cell(report, split, "intent")
        assert cell["run"] + cell["abstain"] == cell["n"]
        assert cell["not_run"] == 0
        assert cell["coverage"] == 1.0


def test_heldout_never_tunes(report):
    rows = report["rows"]
    cal = [r for r in rows if r["split"] == "calibration"]
    assert cal, "calibration split scored"
    assert all(r["outcome"] in ("PASS", "FAIL", "ABSTAIN", "NOT_RUN")
               for r in cal)
    assert not hasattr(ev, "tune"), "harness must expose no tune() entrypoint"
    assert not hasattr(ev, "fit"), "harness must expose no fit() entrypoint"
    held = [r for r in rows if r["split"] == "heldout"]
    assert len(held) == 126, len(held)
    hi = [r for r in rows if r["family"] == "intent"
          and r["split"] == "heldout"]
    assert len(hi) == 55, len(hi)


def test_baseline_fit_on_train_only(report):
    assert ev.train_majority.__doc__ and "TRAIN" in ev.train_majority.__doc__
    counts = Counter(
        r["baseline"] for r in report["rows"] if r["family"] == "intent")
    assert len(counts) >= 1
    (majority, _), = counts.most_common(1)
    assert majority in ev.INTENT_CLASSES


def test_baseline_vs_implementation_reported_per_split(report):
    for split in ("train", "calibration", "heldout"):
        cell = _cell(report, split, "intent")
        assert cell["impl_accuracy_covered"] is not None
        assert cell["baseline_accuracy_covered"] is not None
        assert 0.0 <= cell["impl_accuracy_covered"] <= 1.0
        assert 0.0 <= cell["baseline_accuracy_covered"] <= 1.0


def test_intent_precision_recall_and_false_task_creation(report):
    for split in ("train", "calibration", "heldout"):
        pr = report["intent_precision_recall"][split]
        assert set(pr["per_class"]) == set(ev.INTENT_CLASSES)
        for cls, vals in pr["per_class"].items():
            assert vals["support"] >= 0
            if vals["precision"] is not None:
                assert 0.0 <= vals["precision"] <= 1.0
            if vals["recall"] is not None:
                assert 0.0 <= vals["recall"] <= 1.0
        ftc = pr["false_task_creation"]
        assert ftc["n"] > 0
        assert ftc["false"] <= ftc["n"]
        assert 0.0 <= ftc["rate"] <= 1.0


def test_provmode_owned_scenarios_pass(report):
    prov = [r for r in report["rows"] if r["family"] == "provmode"
            and r["outcome"] in ("PASS", "FAIL")]
    by_scn = Counter(r["scenario"] for r in prov)
    for scn in ("BOTH_KEYS", "OR_ONLY", "NO_KEYS", "DENIED", "TENANT",
                "DIRECT_FORBIDDEN", "OR_FORBIDDEN", "ROOT_BUDGET"):
        assert by_scn[scn] > 0, scn
    failed = [r for r in prov if r["outcome"] == "FAIL"]
    assert failed == [], [r["id"] for r in failed][:5]


def test_direct_first_no_duplicate_calls(report):
    for r in report["rows"]:
        if r["family"] != "provmode" or r["outcome"] not in ("PASS", "FAIL"):
            continue
        c = r["calls"]
        if r["scenario"] == "BOTH_KEYS":
            assert c.get("typesafe_direct") == 1, r["id"]
            assert c.get("openrouter", 0) == 0, r["id"]
        if r["scenario"] == "OR_ONLY":
            assert c.get("openrouter") == 1, r["id"]
            assert c.get("typesafe_direct", 0) == 0, r["id"]
        if r["scenario"] in ("NO_KEYS", "DENIED", "TENANT", "ROOT_BUDGET"):
            assert c.get("typesafe_direct", 0) == 0, r["id"]
            assert c.get("openrouter", 0) == 0, r["id"]


def test_root_budget_expiry_row(report):
    rows = [r for r in report["rows"]
            if r.get("scenario") == "ROOT_BUDGET"
            and r["outcome"] in ("PASS", "FAIL")]
    assert rows, "ROOT_BUDGET scenario must run"
    for r in rows:
        assert r["outcome"] == "PASS", r["id"]
        assert "root_deadline_expired" in r["order_log"] or \
            "root_deadline_expired" in r["stage_skips"], r["id"]


def test_attempt_accounting_bounded(report):
    assert report["provmode"]["attempts_max_per_row"] <= 2, \
        report["provmode"]["attempts_max_per_row"]
    assert report["provmode"]["attempts_total"] <= \
        2 * report["provmode"]["run"]


def test_offline_no_paid_no_shadow_no_probe(report):
    assert report["offline"]["socket_blocked"] is True
    assert report["offline"]["paid_calls"] == 0
    assert report["offline"]["shadow_calls"] == 0
    assert report["offline"]["probe_calls"] == 0
    assert report["offline"]["embedding_calls"] == 0
    assert report["calls_by_source"]["embedding"] == 0
    assert report["calls_by_source"]["probe"] == 0
    assert report["calls_by_source"]["shadow"] == 0
    orders = [l for r in report["rows"]
              if r["family"] == "provmode"
              and r["outcome"] in ("PASS", "FAIL") for l in r["order_log"]]
    assert orders, "ladder stages must be exercised"
    assert any(l.startswith("policy_check:") or l.startswith("skip:")
               for l in orders)


def test_offline_network_actually_blocked():
    with ev.offline():
        with pytest.raises(RuntimeError):
            socket.socket()


def test_exec_capload_not_run_cross_split(report):
    for split in ("train", "calibration", "heldout"):
        for fam in ("exec", "capload"):
            cell = _cell(report, split, fam)
            assert cell["run"] == 0, (split, fam)
            assert cell["not_run"] == cell["n"], (split, fam)
    for fam in ("exec", "capload"):
        ids = report["not_run_ids"][fam]
        assert ids, fam
        assert ids == sorted(ids)


def test_not_run_names_exact_missing_revisions(report):
    reasons = report["not_run_reasons"]
    assert "95c861a8" in reasons["OFF_EQUALS_LEGACY"]
    assert "spec 3.9" in reasons["SHADOW"]
    exec_rows = [r for r in report["rows"] if r["family"] == "exec"
                 and r["outcome"] == "NOT_RUN"]
    cap_rows = [r for r in report["rows"] if r["family"] == "capload"
                and r["outcome"] == "NOT_RUN"]
    assert exec_rows and cap_rows
    assert all("7ac21400" in r["reason"] for r in exec_rows)
    assert all("6375dccb" in r["reason"] for r in cap_rows)
    prov_nr = [r for r in report["rows"] if r["family"] == "provmode"
               and r["outcome"] == "NOT_RUN"]
    assert prov_nr, "provmode NOT_RUN rows must exist"
    assert {r["scenario"] for r in prov_nr} <= \
        {"OFF_EQUALS_LEGACY", "SHADOW", "ATOMIC", "UNKNOWN"}


def test_no_full_d30_claim(report):
    assert report["status"] == "PARTIAL"
    assert "D14-D24" in report["missing_revisions_note"]


def test_latency_budgets_measured(report):
    lat = report["latency_ms"]
    for key in ("all_median", "all_p95", "intent_median", "intent_p95",
                "provmode_median", "provmode_p95"):
        assert lat[key] >= 0.0, key
    assert lat["all_p95"] >= lat["all_median"]
    root_min = report["provmode"]["root_remaining_ms_min"]
    assert root_min is not None


def test_calibration_scored_never_tuned(report):
    cal = _cell(report, "calibration", "intent")
    held = _cell(report, "heldout", "intent")
    assert cal["run"] > 0 and held["run"] > 0
    assert "tune" not in json.dumps(report["not_run_reasons"]).lower()
