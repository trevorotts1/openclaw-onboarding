#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENF-01 / IMG-03 / UPS-25: the plan validator trusts only an approval the
platform verifier confirms, and a paid budget approval carries its cap.

Run: python3 -m pytest 49-signature-funnel/scripts/test_validate_launch_plan_approval.py -q
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("vlp49_approval", HERE / "validate_launch_plan.py")
vlp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vlp)

CLIENT, WORKER = "client:acme", "worker:s49"


def _offer(oid, slot, deliverables):
    return {"offer_id": oid, "slot": slot, "display_name": oid,
            "deliverables": deliverables, "exclusions": [],
            "entitlement_ids": [oid.lower()], "requires": [], "excludes": [],
            "native_product_id": None,
            "prices": [{"price_choice_id": oid + "-USD", "currency": "USD",
                        "amount_minor": 1000, "billing_type": "one_time",
                        "native_price_id": None, "schedule": [],
                        "approval_status": "approved"}],
            "source_kind": "owner", "source_ref": "t", "test_only": True}


def _plan(offers=None, extras=None):
    return {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
            "launch_id": "X", "revision": 1, "journey_mode": "single_simple",
            "status": "approved", "brand_ref": "B", "brand_hash": "H",
            "route_graph_ref": "r", "route_graph_hash": "h",
            "plan_approval_ref": "APPR-1",
            "offers": offers or [_offer("M", "main", ["m"])],
            "extras": extras or {"upsell_1": False, "downsell_1": False, "upsell_2": False},
            "bump_enabled": False, "image_provider": "agnes",
            "source_refs": [], "test_only": True}


def _record(plan, kind, **over):
    rec = {"schema_version": "1.0", "approval_id": "MINTED-0001", "kind": kind,
           "plan_hash": vlp.plan_document_hash(plan), "client_identity": CLIENT,
           "source_message_ref": "tg-123", "scope": [kind],
           "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
           "revoked": False, "verification_class": "authenticated_platform_record"}
    rec.update(over)
    return rec


class _Refused(Exception):
    pass


@pytest.fixture
def platform(monkeypatch):
    """Stand-in for approval_record.verify: only ids the 'platform' minted pass,
    whatever the caller's dict says; plan hash, kind and cap are compared to the
    minted record (the real module does the same against Command Center)."""
    minted = {}

    def verify(aid, kind, plan_hash, scope, *, client_identity=None, cap=None,
               test_only=False, record=None):
        rec = minted.get(aid)
        if rec is None:
            raise _Refused("APPROVAL-NOT-FROM-AUTHORITY")
        if rec["kind"] != kind or rec["plan_hash"] != plan_hash:
            raise _Refused("APPROVAL-KIND/HASH")
        if cap is not None:
            have = rec.get("cap") or {}
            if have.get("currency") != cap["currency"] or cap["cap_minor"] > have.get("cap_minor", -1):
                raise _Refused("APPROVAL-SCOPE")
        return {"approval_id": aid, "plan_hash": plan_hash, "authority": "command-center"}

    monkeypatch.setattr(vlp, "_approval_verifier", lambda: SimpleNamespace(
        verify=verify, ApprovalRefused=_Refused, ApprovalUnavailable=OSError))
    return minted


def test_hand_written_approval_file_is_refused(tmp_path):
    plan = _plan()
    f = tmp_path / "approval.json"
    f.write_text(json.dumps(_record(plan, "launch_plan_build", approval_id="made-up-ref",
                                    client_identity="whoever", source_message_ref="fake-msg")))
    for approval in (json.loads(f.read_text()), str(f)):
        with pytest.raises(vlp.ApprovalError, match="approval not verified against platform record"):
            vlp.assert_plan_build_approved(plan, approval, client_identity_ref=CLIENT,
                                           worker_identity_ref=WORKER)


def test_only_a_verified_record_passes(platform):
    plan = _plan()
    platform["MINTED-0001"] = _record(plan, "launch_plan_build")
    out = vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref=CLIENT,
                                         worker_identity_ref=WORKER)
    assert out["verification_class"] == "authenticated_platform_record"
    # the caller's dict contents are never trusted, only its id
    with pytest.raises(vlp.ApprovalError, match="not verified"):
        vlp.assert_plan_build_approved(plan, {"approval_id": "MINTED-9999"}, client_identity_ref=CLIENT,
                                       worker_identity_ref=WORKER)
    # a changed plan no longer matches the minted hash
    plan["revision"] = 2
    with pytest.raises(vlp.ApprovalError, match="not verified"):
        vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref=CLIENT,
                                       worker_identity_ref=WORKER)


def test_worker_cannot_self_approve(platform):
    plan = _plan()
    platform["MINTED-0001"] = _record(plan, "launch_plan_build")
    with pytest.raises(vlp.ApprovalError, match="self-approval"):
        vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref=CLIENT,
                                       worker_identity_ref=CLIENT)


def test_paid_asset_budget_needs_verified_record_with_cap(platform):
    plan = _plan()
    platform["MINTED-0001"] = _record(plan, "paid_asset_budget",
                                      cap={"cap_minor": 20000, "currency": "USD"})
    ask = dict(client_identity_ref=CLIENT, worker_identity_ref=WORKER)
    out = vlp.assert_scoped_approval(plan, "MINTED-0001", "paid_asset_budget",
                                     cap={"cap_minor": 15000, "currency": "USD"}, **ask)
    assert (out["approval_id"], out["cap_minor"], out["currency"]) == ("MINTED-0001", 15000, "USD")
    for bad in (None, {"cap_minor": 15000}, {"cap_minor": 99999, "currency": "USD"},
                {"cap_minor": 100, "currency": "EUR"}, {"cap_minor": 10.5, "currency": "USD"}):
        with pytest.raises(vlp.ApprovalError):
            vlp.assert_scoped_approval(plan, "MINTED-0001", "paid_asset_budget", cap=bad, **ask)
    with pytest.raises(vlp.ApprovalError, match="not verified"):
        vlp.assert_scoped_approval(plan, {"approval_id": "made-up", "cap": {"cap_minor": 10**9, "currency": "USD"}},
                                   "paid_asset_budget", cap={"cap_minor": 1, "currency": "USD"}, **ask)


def test_identities_are_required(platform):
    plan = _plan()
    platform["MINTED-0001"] = _record(plan, "launch_plan_build")
    with pytest.raises(TypeError):
        vlp.assert_plan_build_approved(plan, "MINTED-0001")
    with pytest.raises(vlp.ApprovalError, match="no client identity"):
        vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref="",
                                       worker_identity_ref=WORKER)
    with pytest.raises(vlp.ApprovalError, match="no worker identity"):
        vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref=CLIENT,
                                       worker_identity_ref=" ")
    with pytest.raises(vlp.ApprovalError, match="self-approval"):
        vlp.assert_plan_build_approved(plan, "MINTED-0001", client_identity_ref=CLIENT,
                                       worker_identity_ref=CLIENT)


def test_plan_build_approval_is_not_a_scoped_approval(platform):
    with pytest.raises(vlp.ApprovalError):
        vlp.assert_scoped_approval(_plan(), "MINTED-0001", "launch_plan_build",
                                   client_identity_ref=CLIENT, worker_identity_ref=WORKER)


def test_local_test_record_needs_explicit_test_only_and_test_plan():
    if not vlp._APPROVAL_RECORD.is_file():
        pytest.skip("shared-utils approval_record.py not in this tree yet")
    plan = _plan()
    rec = _record(plan, "launch_plan_build")
    # live mode: the dict is not an approval (Command Center would have to mint it)
    with pytest.raises(vlp.ApprovalError, match="not verified"):
        vlp.assert_plan_build_approved(plan, rec, client_identity_ref=CLIENT, worker_identity_ref=WORKER)
    out = vlp.assert_plan_build_approved(plan, rec, client_identity_ref=CLIENT,
                                       worker_identity_ref=WORKER, test_only=True)
    assert out["verification_class"] == "local_test_record"
    plan["test_only"] = False
    with pytest.raises(vlp.ApprovalError, match="test_only"):
        vlp.assert_plan_build_approved(plan, rec, client_identity_ref=CLIENT,
                                       worker_identity_ref=WORKER, test_only=True)


def test_u2_must_differ_from_u1_d1_and_main():
    extras = {"upsell_1": True, "downsell_1": False, "upsell_2": True}
    u1, u2 = _offer("U1", "upsell_1", ["Coaching Call"]), _offer("U2", "upsell_2", [" coaching call "])
    plan = _plan([_offer("M", "main", ["m"]), u1, u2], extras)
    assert any("U2 must differ" in f for f in vlp.validate_launch(plan))
    u2["deliverables"] = ["Workbook"]
    assert vlp.validate_launch(plan) == []
    u2["deliverables"] = ["m"]
    assert any("main offer" in f for f in vlp.validate_launch(plan))
