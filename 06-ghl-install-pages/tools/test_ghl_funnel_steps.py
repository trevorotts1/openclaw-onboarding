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


# ---- concrete driver (RestCanvasFunnelDriver) -------------------------------
import re  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

# TEST-ONLY capture: invented strings, never a real GHL surface (CHK-19 is open).
SYN_CAPTURE = {
    "synthetic": True,
    "step_types": {"landing": "syn_landing", "order_form": "syn_order_form", "upsell": "syn_upsell",
                   "downsell": "syn_downsell", "thank_you": "syn_thank_you"},
    "attach_price": {"method": "POST", "path": "/syn/p/{step_id}/price",
                     "body": {"product": "{product_id}", "price": "{price_id}"}},
    "place_element": {"method": "POST", "path": "/syn/p/{step_id}/el",
                      "body": {"type": "{kind}", "price": "{price_id}", "checked": "{default_checked}"}},
    "set_action": {"method": "POST", "path": "/syn/p/{step_id}/act",
                   "body": {"which": "{action}", "goTo": "{target_step_id}"}},
    "payment_status": {"method": "GET", "path": "/syn/pay?l={location_id}",
                       "connected_path": "stripe.on", "provider_path": "stripe.name"},
    "read_back_fields": {"steps_path": "data.steps", "step_page_id_path": "pages.0",
                         "step_type_path": "type", "price_ids_path": "prices",
                         "elements_path": "elements", "element_kind": "type",
                         "element_price_id": "price", "element_default_checked": "checked",
                         "accept_target_path": "act.accept", "decline_target_path": "act.decline"},
}


class SynGhl:
    """In-memory GHL: answers the driver's fetch JS from what was written."""

    def __init__(self):
        self.evals, self.steps, self.pages, self.create_bodies = [], [], {}, []

    def __call__(self, js):
        self.evals.append(js)
        m = re.search(r'fetch\("([^"]+)", \{method:"(\w+)"', js)
        b = re.search(r"JSON\.stringify\((.*)\)\}\);", js)
        method, url = m.group(2), urlsplit(m.group(1))
        body = json.loads(b.group(1)) if b else None
        path = url.path
        if path == "/funnels/funnel/create-step":
            self.create_bodies.append(body)
            pid = f"pg{len(self.steps) + 1}"
            self.steps.append({"type": body["step"]["type"], "pages": [pid]})
            self.pages[pid] = {"prices": [], "elements": [], "act": {}}
            seg = ["funnel_pages", pid]
            return {"status": 201, "ok": True, "body": {"page": {"_ref": {"_path": {"segments": seg}}}}}
        if path.startswith("/funnels/funnel/fetch/"):
            return {"status": 200, "ok": True, "body": {"data": {"steps": self.steps}}}
        if path.startswith("/funnels/page/"):
            return {"status": 200, "ok": True, "body": self.pages[path.rsplit("/", 1)[1]]}
        if path.startswith("/syn/pay"):
            return {"status": 200, "ok": True, "body": {"stripe": {"on": True, "name": "stripe"}}}
        page = self.pages[path.split("/")[3]]
        if path.endswith("/price"):
            page["prices"].append(body["price"])
        elif path.endswith("/el"):
            page["elements"].append({"type": body["type"], "price": body["price"], "checked": body["checked"]})
        else:
            page["act"][body["which"]] = body["goTo"]
        return {"status": 200, "ok": True, "body": {}}


def test_concrete_driver_implements_contract():
    for name in ("payment_provider_status", "create_step", "attach_price", "place_element",
                 "set_action", "read_back", "preflight"):
        assert callable(getattr(fs.RestCanvasFunnelDriver, name))


def test_concrete_driver_refuses_without_capture(launch, tmp_path):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    ghl = SynGhl()
    d = fs.RestCanvasFunnelDriver(run_eval=ghl, location_id=LOC, capture=None)
    with pytest.raises(fs.CommerceCaptureRequired, match="CAPTURE-GATE:CHK-19"):
        _install(plan, d)
    assert ghl.evals == []
    # a synthetic capture is refused in production mode (allow_synthetic False) too
    with pytest.raises(fs.CommerceCaptureRequired, match="synthetic_fixture"):
        _install(plan, fs.RestCanvasFunnelDriver(ghl, LOC, SYN_CAPTURE))
    assert ghl.evals == []
    p = tmp_path / "cap.json"
    p.write_text(json.dumps(SYN_CAPTURE))
    with pytest.raises(fs.CommerceCaptureRequired, match="synthetic_fixture"):
        fs.load_commerce_capture(str(p))
    p.write_text(json.dumps({k: v for k, v in SYN_CAPTURE.items() if k != "synthetic"}))
    assert fs.load_commerce_capture(str(p))["step_types"]["upsell"] == "syn_upsell"


def test_concrete_driver_end_to_end_on_synthetic_capture(launch):
    graph, offers, catalog = launch
    plan = fs.build_funnel_plan(graph, offers, catalog)
    ghl = SynGhl()
    d = fs.RestCanvasFunnelDriver(ghl, LOC, SYN_CAPTURE, allow_synthetic=True)
    out = _install(plan, d)
    assert out["ready"] is True and out["mismatches"] == [] and out["manual_gates"] == []
    assert {b["step"]["type"] for b in ghl.create_bodies} == set(SYN_CAPTURE["step_types"].values())
    assert "optin_funnel_page" not in json.dumps(ghl.create_bodies)
    by = {r["step_id"]: r for r in out["readback"]["steps"]}
    ids = {s["role"]: out["step_ids"][s["page_id"]] for s in plan["steps"]}
    assert [by[ids[r]]["type"] for r in ("checkout", "upsell_1", "downsell_1", "thank_you")] == [
        "order_form", "upsell", "downsell", "thank_you"]
    assert sorted(by[ids["checkout"]]["price_ids"]) == [
        "price_MAIN-ELITE", "price_MAIN-ESS", "price_MAIN-PRO"]
    assert {"kind": "order_bump", "price_id": "price_BUMP", "default_checked": False} in by[ids["checkout"]]["elements"]
    u1 = next(s for s in plan["steps"] if s["role"] == "upsell_1")
    assert by[ids["upsell_1"]]["accept_target"] == out["step_ids"][u1["accept_to"]]
    assert by[ids["upsell_1"]]["decline_target"] == out["step_ids"][u1["decline_to"]]
    # no captured payment route -> connected None -> named manual gate (fail closed)
    cap = {k: v for k, v in SYN_CAPTURE.items() if k != "payment_status"}
    out2 = _install(plan, fs.RestCanvasFunnelDriver(SynGhl(), LOC, cap, allow_synthetic=True))
    assert out2["manual_gates"] == [fs.PAYMENT_GATE] and out2["ready"] is False
