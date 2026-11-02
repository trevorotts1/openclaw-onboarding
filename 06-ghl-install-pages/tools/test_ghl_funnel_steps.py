"""S06-02: funnel commerce planner/installer against the real Skill 83 elevation route graph."""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LAUNCHER = os.path.join(HERE, "..", "..", "83-black-friday-launcher")
sys.path.append(LAUNCHER)

import ghl_funnel_steps as fs  # noqa: E402
from launcher_core import intake as launch_intake, route  # noqa: E402

LOC = "TEST-LOCATION"


def _intake():
    with open(os.path.join(LAUNCHER, "fixtures", "elevation", "intake.json"), encoding="utf-8") as f:
        return launch_intake.validate(json.load(f))


@pytest.fixture
def launch():
    it = _intake()
    graph = route.compile_route(it)
    catalog = {o["offer_id"]: {"product_id": "prod_" + o["offer_id"],
                               "price_id": "price_" + o["offer_id"],
                               "amount_minor": o["price"]["amount_minor"]}
               for o in it["offers"]}
    return graph, it["offers"], catalog


class FakeDriver:
    """In-memory funnel: records writes, reads them back as stored."""

    def __init__(self, connected=True, corrupt=None):
        self.connected, self.corrupt, self.steps, self.n, self.writes = connected, corrupt, {}, 0, 0

    def payment_provider_status(self, location_id):
        return {"connected": self.connected, "provider": "stripe"}

    def create_step(self, funnel_id, name, step_type):
        self.n += 1
        self.writes += 1
        sid = f"step{self.n}"
        self.steps[sid] = {"step_id": sid, "type": step_type, "price_ids": [], "elements": [],
                           "accept_target": None, "decline_target": None}
        return sid

    def attach_price(self, sid, product_id, price_id):
        self.writes += 1
        self.steps[sid]["price_ids"].append(price_id)

    def place_element(self, sid, kind, price_id, default_checked):
        self.writes += 1
        self.steps[sid]["elements"].append(
            {"kind": kind, "price_id": price_id, "default_checked": default_checked})

    def set_action(self, sid, action, target):
        self.writes += 1
        self.steps[sid][action + "_target"] = target

    def read_back(self, funnel_id):
        steps = copy.deepcopy(list(self.steps.values()))
        if self.corrupt:
            self.corrupt(steps)
        return {"steps": steps}


def _approval(plan, **kw):
    rec = {"scope": "publish", "location_id": LOC, "plan_hash_prefix": plan["plan_hash"][:8]}
    rec.update(kw)
    return rec


def _install(plan, driver, approval="ok", verifier=lambda r: True):
    return fs.install_funnel(plan, driver, "F1", LOC,
                             _approval(plan) if approval == "ok" else approval, verifier)


def test_plan_native_types_prices_and_targets_from_route_graph(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    by = {s["role"]: s for s in plan["steps"]}
    assert [s["type"] for s in plan["steps"]] == [
        "landing", "landing", "order_form", "upsell", "downsell", "upsell", "thank_you"]
    assert sorted(p["price_id"] for p in by["checkout"]["prices"]) == [
        "price_MAIN-ELITE", "price_MAIN-ESS", "price_MAIN-PRO"]
    assert by["checkout"]["bump"]["price_id"] == "price_BUMP"
    assert by["upsell_1"]["prices"][0]["price_id"] == "price_U1"
    for s in plan["steps"]:
        if s["type"] in ("upsell", "downsell"):
            out = {e["event"]: e["to"] for e in graph["edges"] if e["from"] == s["page_id"]}
            assert (s["accept_to"], s["decline_to"]) == (out["payment_succeeded"], out["explicit_decline"])


def test_install_reads_back_and_is_ready(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    d = FakeDriver()
    out = _install(plan, d)
    assert out["mismatches"] == [] and out["manual_gates"] == [] and out["ready"] is True
    u1 = d.steps[out["step_ids"][next(s["page_id"] for s in plan["steps"] if s["role"] == "upsell_1")]]
    assert u1["accept_target"] == out["step_ids"][next(
        s["page_id"] for s in plan["steps"] if s["role"] == "upsell_2")]
    assert u1["decline_target"] == out["step_ids"][next(
        s["page_id"] for s in plan["steps"] if s["role"] == "downsell_1")]
    chk = d.steps[out["step_ids"][next(s["page_id"] for s in plan["steps"] if s["role"] == "checkout")]]
    assert {"kind": "order_bump", "price_id": "price_BUMP", "default_checked": False} in chk["elements"]


def test_readback_mismatches_block_ready(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)

    def swap_decline(steps):
        ups = [s for s in steps if s["type"] == "upsell"]
        ups[0]["decline_target"] = "wrong"
        for s in steps:
            for e in s["elements"]:
                if e["kind"] == "order_bump":
                    e["default_checked"] = True

    out = _install(plan, FakeDriver(corrupt=swap_decline))
    assert out["ready"] is False
    assert any("decline_target" in m for m in out["mismatches"])
    assert any("unchecked" in m for m in out["mismatches"])


def test_missing_payment_provider_is_named_manual_gate_and_blocks_ready(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    out = _install(plan, FakeDriver(connected=False))
    assert out["manual_gates"] == [fs.PAYMENT_GATE] and out["ready"] is False
    assert fs.payment_gate(None) == fs.PAYMENT_GATE
    assert fs.payment_gate({"connected": "yes"}) == fs.PAYMENT_GATE


@pytest.mark.parametrize("approval", [
    None,
    {"scope": "read", "location_id": LOC},
    {"scope": "publish", "location_id": "OTHER"},
    {"scope": "automation_write", "location_id": LOC, "plan_hash_prefix": "deadbeef"},
])
def test_write_refused_without_valid_approval_record(launch, approval):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    d = FakeDriver()
    with pytest.raises(fs.ApprovalRefused):
        fs.install_funnel(plan, d, "F1", LOC, approval, lambda r: True)
    assert d.writes == 0


def test_write_refused_when_verifier_missing_or_rejects(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    for v in (None, lambda r: False):
        d = FakeDriver()
        with pytest.raises(fs.ApprovalRefused):
            _install(plan, d, verifier=v)
        assert d.writes == 0


def test_plan_refuses_invented_or_disagreeing_prices(launch):
    graph, offers, catalog = launch
    missing = {k: v for k, v in catalog.items() if k != "U1"}
    with pytest.raises(fs.FunnelPlanError):
        fs.build_funnel_plan(graph, offers, missing)
    wrong = copy.deepcopy(catalog)
    wrong["BUMP"]["amount_minor"] += 1
    with pytest.raises(fs.FunnelPlanError):
        fs.build_funnel_plan(graph, offers, wrong)
