#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dispatch_modes.py — L14/UL-020: explicit page_only and turnkey_launch.

Synthetic-local only: no network, no provider, no live send. Every lane
adapter is a local Python process that echoes its request; every page
executor is dispatch_launch's own simulated L0 executor.

Run: python3 -m pytest 49-signature-funnel/scripts/test_dispatch_modes.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import compile_launch_route as clr  # noqa: E402
import dispatch_launch as dl  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

from datetime import datetime, timezone  # noqa: E402

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PAGE_KEYS = ("landing", "sales", "product_selection", "checkout",
             "upsell_1", "upsell_2", "downsell_1", "thank_you")


def _offer(oid, slot, amount, excludes=()):
    return {"offer_id": oid, "slot": slot, "display_name": oid,
            "deliverables": ["x"], "exclusions": [],
            "entitlement_ids": [oid.lower()], "requires": [],
            "excludes": list(excludes), "native_product_id": None,
            "prices": [{"price_choice_id": f"{oid}-USD", "currency": "USD",
                        "amount_minor": amount, "billing_type": "one_time",
                        "native_price_id": None, "schedule": [],
                        "terms_source": None, "approval_status": "approved"}],
            "source_kind": "test_fixture", "source_ref": "test-dispatch-modes",
            "test_only": True}


def _launch():
    launch = {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
              "launch_id": "X", "revision": 1, "journey_mode": "multiple_options",
              "status": "approved", "brand_ref": "B", "brand_hash": "H",
              "route_graph_ref": "", "route_graph_hash": "",
              "plan_approval_ref": "APPR-1",
              "offers": [_offer("M1", "main", 1000), _offer("M2", "main", 2000),
                         _offer("BP", "bump", 500),
                         _offer("U1", "upsell_1", 3000, ["D1"]),
                         _offer("D1", "downsell_1", 1500, ["U1"]),
                         _offer("U2", "upsell_2", 4000)],
              "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True},
              "bump_enabled": True, "image_provider": "agnes",
              "source_refs": [], "test_only": True}
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = "route-graph:X:rev1"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    return launch


def _approval(launch):
    return {"schema_version": "1.0", "approval_id": "APPR-1",
            "subject_type": "launch_plan_build",
            "subject_hash": vlp.plan_document_hash(launch),
            "owner_identity_ref": "client-1", "source_message_ref": "m-1",
            "recorded_at": NOW, "scope": ["launch_plan_build"],
            "revoked": False,
            "verification_class": "recorded_consent_not_cryptographically_sealed"}


def _plan(launch):
    return {
        "schema_version": "1.0.0",
        "launch_id": launch["launch_id"],
        "offer": {"name": "M1 / M2", "price_usd": 10.0, "currency": "USD",
                  "payment_plans": False},
        "launch_calendar": {"launch_at": "2026-11-27T13:00:00Z",
                            "doors_open_at": "2026-11-27T13:00:00Z",
                            "doors_close_at": "2026-12-02T03:00:00Z",
                            "timezone": "America/New_York"},
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "pages": [{"id": f"page_{k}", "kind": "landing", "url": None,
                   "waits_for": []} for k in PAGE_KEYS],
        "email_sequences": [{"id": "email_main_launch", "kind": "main_launch",
                             "provider": "skill50", "email_count": 10,
                             "draft_only": True, "waits_for": ["page_sales"]}],
        "text_sets": [{"id": "text_launch", "draft_only": True,
                       "waits_for": ["email_main_launch"]}],
        "automations": [{"id": "automation_welcome", "draft_only": True,
                         "waits_for": ["page_thank_you"]}],
    }


LANE_IDS = ("email_main_launch", "text_launch", "automation_welcome")

CONSUMER = """\
import json, sys
req = json.load(open(sys.argv[1]))
res = {"schema_version": "1.0", "tenant_id": req["tenant_id"],
       "location_id": req["location_id"], "launch_id": req["launch_id"],
       "revision": req["revision"], "request_id": req["request_id"],
       "input_hash": req["input_hash"], "page_id": req["page_id"],
       "status": "authored", "artifacts": [],
       "author_session": "synthetic-lane", "reviewer_session": None,
       "independent_review": False, "proof_class": "L0", "blockers": [],
       "native_bindings_ref": None, "test_only": req["test_only"]}
json.dump(res, open(sys.argv[2], "w"))
"""

BAD_CONSUMER = "import json, sys\njson.dump({'bogus': True}, open(sys.argv[2], 'w'))\n"


def _adapters(tmp_path, body=CONSUMER, ids=LANE_IDS):
    script = tmp_path / "lane_consumer.py"
    script.write_text(body, encoding="utf-8")
    return {"adapters": {uid: {"command": [sys.executable, str(script),
                                           "{request}", "{result}"]}
                         for uid in ids}}


def _turnkey(tmp_path, launch, approval, plan, adapters, **overrides):
    kwargs = dict(client_identity_ref="client-1", worker_identity_ref="worker-9",
                  mode=dl.MODE_TURNKEY_LAUNCH, launch_plan=plan,
                  lane_adapters=adapters,
                  out_dir=tmp_path / "out",
                  executor=dl._simulated_executor("synthetic"))
    kwargs.update(overrides)
    return dl.dispatch(launch, approval, **kwargs)


def test_mode_is_explicit_and_refuses_unknown():
    launch, approval = _launch(), None
    approval = _approval(launch)
    with pytest.raises(dl.DispatchError, match="explicit and never inferred"):
        dl.dispatch(launch, approval, client_identity_ref="client-1",
                    worker_identity_ref="worker-9", mode="auto")


def test_page_only_is_the_default_and_does_not_dispatch_a_plan(tmp_path):
    launch = _launch()
    m = dl.dispatch(launch, _approval(launch), client_identity_ref="client-1",
                    worker_identity_ref="worker-9", out_dir=tmp_path / "out",
                    launch_plan=_plan(launch))
    assert m["mode"] == dl.MODE_PAGE_ONLY
    assert m["launch_plan"]["plan_state"] == "not_dispatched"
    assert "lane_results" not in m
    assert not (tmp_path / "out" / "progress.json").exists()


def test_turnkey_requires_the_full_plan_and_a_page_executor(tmp_path):
    launch = _launch()
    with pytest.raises(dl.DispatchError, match="FULL approved launch plan"):
        dl.dispatch(launch, _approval(launch), client_identity_ref="client-1",
                    worker_identity_ref="worker-9", mode=dl.MODE_TURNKEY_LAUNCH,
                    out_dir=tmp_path / "out")
    with pytest.raises(dl.DispatchError, match="requires a page executor"):
        dl.dispatch(launch, _approval(launch), client_identity_ref="client-1",
                    worker_identity_ref="worker-9", mode=dl.MODE_TURNKEY_LAUNCH,
                    launch_plan=_plan(launch), lane_adapters=_adapters(tmp_path),
                    out_dir=tmp_path / "out")


def test_turnkey_blocks_a_missing_lane_adapter_by_name(tmp_path):
    launch = _launch()
    adapters = _adapters(tmp_path, ids=("email_main_launch", "text_launch"))
    with pytest.raises(dl.DispatchError, match="automation_welcome"):
        _turnkey(tmp_path, launch, _approval(launch), _plan(launch), adapters)


def test_turnkey_blocks_a_plan_that_omits_a_page_unit(tmp_path):
    launch = _launch()
    plan = _plan(launch)
    plan["pages"] = [p for p in plan["pages"] if p["id"] != "page_sales"]
    with pytest.raises(dl.DispatchError, match="page_sales"):
        _turnkey(tmp_path, launch, _approval(launch), plan, _adapters(tmp_path))


def test_turnkey_runs_every_unit_and_writes_durable_progress(tmp_path):
    launch = _launch()
    m = _turnkey(tmp_path, launch, _approval(launch), _plan(launch),
                 _adapters(tmp_path))
    assert m["execution"] == "executed"
    assert len(m["results"]) == 7
    assert {r["unit_id"] for r in m["lane_results"]} == set(LANE_IDS)
    assert all(r["status"] == "authored" for r in m["lane_results"])
    progress = json.loads((tmp_path / "out" / "progress.json").read_text())
    assert progress["schema"] == dl.PROGRESS_SCHEMA
    for uid in LANE_IDS:
        assert progress["units"][uid]["status"] == "done"
    assert progress["units"]["page_sales"]["status"] == "done"


def test_turnkey_resume_skips_unchanged_units(tmp_path):
    launch = _launch()
    _turnkey(tmp_path, launch, _approval(launch), _plan(launch), _adapters(tmp_path))
    # A second run with adapters that would fail if invoked: every unit must be
    # skipped from the durable progress, never executed again.
    failing = _adapters(tmp_path, body="import sys; sys.exit(9)")
    m = _turnkey(tmp_path, launch, _approval(launch), _plan(launch), failing)
    assert all(r["status"] == "skipped_done" for r in m["lane_results"])
    assert m.get("page_resume", {}).get("skipped_roles")


def test_turnkey_resume_reruns_only_a_changed_unit(tmp_path):
    launch = _launch()
    plan = _plan(launch)
    _turnkey(tmp_path, launch, _approval(launch), plan, _adapters(tmp_path))
    plan["text_sets"][0]["note"] = "the client amended this text set"
    m = _turnkey(tmp_path, launch, _approval(launch), plan, _adapters(tmp_path))
    status = {r["unit_id"]: r["status"] for r in m["lane_results"]}
    assert status["text_launch"] == "authored"
    assert status["email_main_launch"] == "skipped_done"
    assert status["automation_welcome"] == "skipped_done"


def test_turnkey_refuses_a_result_that_does_not_echo_its_request(tmp_path):
    launch = _launch()
    with pytest.raises(dl.DispatchError, match="receipt validation"):
        _turnkey(tmp_path, launch, _approval(launch), _plan(launch),
                 _adapters(tmp_path, body=BAD_CONSUMER))
    progress = json.loads((tmp_path / "out" / "progress.json").read_text())
    assert progress["units"]["email_main_launch"]["status"] == "failed"


def test_turnkey_blocks_a_waits_for_cycle_by_name(tmp_path):
    launch = _launch()
    plan = _plan(launch)
    plan["email_sequences"][0]["waits_for"] = ["text_launch"]
    plan["text_sets"][0]["waits_for"] = ["email_main_launch"]
    with pytest.raises(dl.DispatchError, match="cycle"):
        _turnkey(tmp_path, launch, _approval(launch), plan, _adapters(tmp_path))
