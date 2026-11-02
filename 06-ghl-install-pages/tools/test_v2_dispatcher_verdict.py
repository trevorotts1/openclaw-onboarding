"""Offline tests for U-skill06-01 (S06-01 / S06-07 / S06-08 / S06-21).

  S06-01  a failing build is STATE_FAILED and never pushed to the Command Center as
          'verified'; the production path runs verify_all(live=True, expected_location_id)
          and ghl_gate.require_pass.
  S06-07  the engine selector runs in dispatch_one before the template matcher; a Black
          Friday request routes to Skill 83 (not 56) and routing/match-decision.json is written.
  S06-08  a verified dispatch writes build_receipt.json from the verify evidence.
  S06-21  a funnel job without routing/p2-gate.json (approval record) is HELD (WAITING) and the
          builder never runs; the board handoff event goes out through cc_board.

No network, no browser, no live GHL: verify_all / require_pass are monkeypatched.

Run: python3 -m pytest 06-ghl-install-pages/tools/test_v2_dispatcher_verdict.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import cc_board  # noqa: E402
import funnel_engine_selector as sel  # noqa: E402
import ghl_gate  # noqa: E402
import ghl_verify  # noqa: E402
import v2_dispatcher as d  # noqa: E402

BF_REQUEST = ("Black Friday launch with landing page, product selection, checkout order form "
              "with order bump, upsell, downsell and thank you page")
LOC = "LOCfixture0000"


def _task(**kw):
    t = {"id": "t1", "brand": "Fixture Co", "location_id": LOC, "reprobe": True, "has_copy": "yes"}
    t.update(kw)
    return t


def _builder(calls=None):
    def b(task, root):
        if calls is not None:
            calls.append(1)
        return {"pages": [{"step": "checkout", "route_node": "checkout", "preview_url": "https://p.test/c",
                           "marker": "m"}], "location_gate_ok": True, "duration_s": 1.0}
    return b


@pytest.fixture
def prod(monkeypatch):
    """Production path (live=True, no injected verifier) with verify_all / require_pass faked."""
    s = {"verify_kwargs": None, "require_pass": 0, "board": [], "overall": False, "rc": 1}

    def fake_verify_all(run_dir, pages, **kw):
        s["verify_kwargs"] = kw
        raw = [{"step": "checkout", "preview_url": "https://p.test/c", "PASS": s["overall"]}]
        return {"raw": raw, "trust": "LIVE", "summary": {
            "overall_pass": s["overall"], "passed": int(s["overall"]), "total": 1, "trust": "LIVE",
            "run_nonce": "n1"}}

    def fake_require_pass(root):
        s["require_pass"] += 1
        return s["rc"]

    monkeypatch.setattr(ghl_verify, "verify_all", fake_verify_all)
    monkeypatch.setattr(ghl_gate, "require_pass", fake_require_pass)
    monkeypatch.setattr(d, "_board_push", lambda task, state: s["board"].append(state))
    return s


# ── S06-01 ───────────────────────────────────────────────────────────────────

def test_failing_build_is_failed_and_board_never_sees_verified(tmp_path, prod):
    r = d.dispatch_one(_task(), str(tmp_path), builder=_builder())
    assert r.state == d.STATE_FAILED and not r
    assert prod["require_pass"] == 1
    assert prod["verify_kwargs"]["live"] is True
    assert prod["verify_kwargs"]["expected_location_id"] == LOC
    assert "verified" not in prod["board"] and prod["board"][-1] == "FAILED"
    rec = json.load(open(tmp_path / "routing" / "task-record.json"))
    assert rec["state"] == "FAILED"
    assert not (tmp_path / "build_receipt.json").exists()


def test_overall_fail_is_failed_even_when_gate_rc_zero(tmp_path, prod):
    prod["rc"] = 0  # gate says fine, summary says overall_pass False -> still FAILED
    r = d.dispatch_one(_task(), str(tmp_path), builder=_builder())
    assert r.state == d.STATE_FAILED and prod["board"][-1] == "FAILED"


def test_injected_verifier_overall_false_is_failed(tmp_path, monkeypatch):
    pushes = []
    monkeypatch.setattr(d, "_board_push", lambda task, state: pushes.append(state))
    r = d.dispatch_one(_task(), str(tmp_path), builder=_builder(),
                       verifier=lambda root, pages, **kw: {"summary": {"overall_pass": False}})
    assert r.state == d.STATE_FAILED and "verified" not in pushes


# ── S06-08 ───────────────────────────────────────────────────────────────────

def test_verified_dispatch_writes_build_receipt_from_verify_evidence(tmp_path, prod, monkeypatch):
    prod["overall"], prod["rc"] = True, 0
    monkeypatch.setattr(d, "_fab_overlay", lambda root: {"ran": True, "passed": True, "score": 9.1})
    r = d.dispatch_one(_task(), str(tmp_path), builder=_builder())
    assert r.state == d.STATE_VERIFIED and prod["board"][-1] == "verified"
    rc = json.load(open(tmp_path / "build_receipt.json"))
    assert rc["qc_score"] == 9.1 and rc["verify_overall_pass"] is True and rc["run_nonce"] == "n1"
    assert rc["pages"] == [{"page_type": "checkout", "step": "checkout",
                            "preview_url": "https://p.test/c", "verified": True}]
    assert json.load(open(tmp_path / "routing" / "task-record.json"))["build_receipt_path"].endswith(
        "build_receipt.json")


def test_receipt_has_no_qc_score_when_fab_did_not_run(tmp_path, prod):
    prod["overall"], prod["rc"] = True, 0
    d.dispatch_one(_task(), str(tmp_path), builder=_builder())
    assert json.load(open(tmp_path / "build_receipt.json"))["qc_score"] is None


# ── S06-07 ───────────────────────────────────────────────────────────────────

def test_selector_routes_black_friday_to_83_over_56():
    dec = sel.select_engine(BF_REQUEST, sel.load_registry())
    assert dec["decision"] == "ROUTE_TO_ENGINE" and dec["engine_id"] == "black-friday-launcher"


def test_selector_leaves_other_requests_alone_and_honours_launch_mode():
    reg = sel.load_registry()
    assert sel.select_engine("build me a signature funnel", reg)["engine_id"] == "signature-funnel"
    assert sel.select_engine("write my direct response sales page with order bump copy",
                             reg)["engine_id"] == "sales-page-assets"
    assert sel.select_engine("I want to launch my webinar", reg)["decision"] == "NO_ENGINE_MATCH"
    assert sel.select_engine({"text": "do it", "launch_mode": "black_friday_launch"},
                             reg)["engine_id"] == "black-friday-launcher"


def test_dispatch_one_writes_match_decision_from_selector(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "_board_push", lambda task, state: None)
    task = _task(brief=BF_REQUEST)
    called = []
    d.dispatch_one(task, str(tmp_path), builder=_builder(),
                   verifier=lambda root, pages, **kw: {"summary": {"overall_pass": True}},
                   step0_matcher=lambda t, r: called.append(1) or {"decision": "USE_TEMPLATE"})
    md = json.load(open(tmp_path / "routing" / "match-decision.json"))
    assert md["flex_decision"] == "ROUTE_TO_ENGINE" and md["engine_id"] == "black-friday-launcher"
    assert task["funnel_engine"] == "black-friday-launcher"
    assert called == []  # the template matcher does not overwrite the engine receipt


# ── S06-21 ───────────────────────────────────────────────────────────────────

def test_funnel_without_p2_receipt_is_waiting_and_builder_never_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "_board_push", lambda task, state: None)
    ran = []
    t = _task(job_type="funnel")
    t.pop("has_copy")
    r = d.dispatch_one(t, str(tmp_path), builder=_builder(ran))
    assert r.state == d.STATE_WAITING and ran == []
    assert "p2-gate.json" in r.reason


@pytest.mark.parametrize("body", [{"approved": True}, {"approved": False, "approval_ref": "r1"}, "not-json"])
def test_funnel_with_unapproved_p2_receipt_is_waiting(tmp_path, monkeypatch, body):
    monkeypatch.setattr(d, "_board_push", lambda task, state: None)
    (tmp_path / "routing").mkdir()
    (tmp_path / "routing" / "p2-gate.json").write_text(body if isinstance(body, str) else json.dumps(body))
    t = _task(job_type="funnel")
    t.pop("has_copy")
    assert d.dispatch_one(t, str(tmp_path), builder=_builder()).state == d.STATE_WAITING


def test_funnel_with_p2_approval_proceeds_and_emits_board_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "_board_push", lambda task, state: None)
    sent = []
    monkeypatch.setattr(cc_board, "post_handoff_event", lambda tid, ev, **kw: sent.append((tid, ev)) or True)
    (tmp_path / "routing").mkdir()
    (tmp_path / "routing" / "p2-gate.json").write_text(
        json.dumps({"approved": True, "approval_ref": "appr-1"}))
    t = _task(job_type="funnel")
    t.pop("has_copy")
    r = d.dispatch_one(t, str(tmp_path), builder=_builder(),
                       verifier=lambda root, pages, **kw: {"summary": {"overall_pass": True}})
    assert r.state == d.STATE_VERIFIED
    assert sent and sent[0][0] == "t1"
    assert sent[0][1]["from_dept"] == "web-development" and sent[0][1]["to_dept"] == "crm"
    assert json.load(open(tmp_path / "routing" / "board-handoff.json"))["delivered"] is True


def test_funnel_with_client_supplied_copy_is_not_p2_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "_board_push", lambda task, state: None)
    r = d.dispatch_one(_task(job_type="funnel"), str(tmp_path), builder=_builder(),
                       verifier=lambda root, pages, **kw: {"summary": {"overall_pass": True}})
    assert r.state == d.STATE_VERIFIED


def test_cc_board_post_handoff_event_rides_activities(monkeypatch):
    got = {}
    monkeypatch.setattr(cc_board, "post_activity",
                        lambda tid, typ, msg, metadata=None, **kw: got.update(t=tid, typ=typ, m=metadata) or True)
    ev = {"from_dept": "web-development", "to_dept": "crm", "artifact": "a", "job_id": "j"}
    assert cc_board.post_handoff_event("t9", ev) is True and got["t"] == "t9" and got["m"] == {"handoff": ev}
    assert cc_board.post_handoff_event("t9", {"from_dept": "x"}) is False
