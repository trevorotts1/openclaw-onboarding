"""S44-14 / CHK-20 / S44-15: one money conversion, read-back, idempotency, approval.

Offline: a stateful fake GHL transport, no network, no credentials.
Run: python3 -m pytest shared-utils/ghl/test_products_prices_units.py -q
"""
import copy
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.abspath(os.path.join(_HERE, "..", "..", "44-convert-and-flow-operator", "tools", "engine"))
for _p in (_HERE, _ENGINE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capability_inventory as ci  # noqa: E402
from cli_anything.gohighlevel.utils import ghl_client  # noqa: E402

pp = ghl_client._products_prices()  # the one module instance the CLI path uses

LOC = "loc_test"
FAR_FUTURE = 4102444800


class FakeGHL(pp.Transport):
    """Minimal stateful GHL products API: creates, lists and gets what it was given."""

    def __init__(self):
        self.products = {}
        self.prices = {}
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        bare = path.split("?", 1)[0].rstrip("/")
        parts = bare.split("/")  # ['', 'products', id?, 'price', pid?]
        if method == "POST" and bare == "/products":
            pid = f"prod_{len(self.products) + 1}"
            self.products[pid] = {"_id": pid, **body}
            return pp.Response(201, self.products[pid])
        if method == "GET" and bare == "/products":
            rows = list(self.products.values())
            return pp.Response(200, {"products": rows, "total": len(rows)})
        if method == "GET" and len(parts) == 3:
            return pp.Response(200, self.products[parts[2]])
        if method == "POST" and len(parts) == 4 and parts[3] == "price":
            rid = f"price_{len(self.prices) + 1}"
            self.prices[rid] = {"_id": rid, "product": parts[2], **body}
            return pp.Response(201, self.prices[rid])
        if method == "GET" and len(parts) == 4 and parts[3] == "price":
            rows = [p for p in self.prices.values() if p["product"] == parts[2]]
            return pp.Response(200, {"prices": rows, "total": len(rows)})
        if method == "GET" and len(parts) == 5:
            return pp.Response(200, self.prices[parts[4]])
        raise AssertionError(f"unexpected {method} {path}")

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def approval(action, key):
    return {"kind": pp.APPROVAL_KIND, "location_id": key.location_id, "action": action,
            "object_key": ":".join(key.as_tuple()), "plan_sha256": "ab" * 32,
            "approver": "client", "expiry": FAR_FUTURE}


def accept(_record):
    return True


def cli_price(fake, amount_minor, currency="USD", **kw):
    """The Skill 44 CLI path: ghl_client.create_price with the per-action approval."""
    key = ghl_client._price_key(ghl_client._products_prices(), LOC, "prod_1", "Black Friday",
                                kw.get("billing", "one_time"), currency, amount_minor)
    kw.pop("billing", None)
    return ghl_client.create_price("prod_1", "Black Friday", amount_minor, currency,
                                   approval=approval("products.prices.create", key),
                                   approval_verifier=accept, location_id=LOC, transport=fake, **kw)


def shared_price(fake, amount_minor, currency="USD"):
    key = pp.LogicalKey(LOC, "price", "shared", parent_logical_id="prod_1")
    adapter = pp.ProductsPricesAdapter(fake, pp.InMemoryStore(), approval_verifier=accept)
    spec = pp.PriceSpec("Black Friday", LOC, "one_time", currency, amount_minor)
    return adapter.ensure_price(key, spec, pp.NativeProduct("prod_1", LOC, "x", "DIGITAL"),
                                approval("products.prices.create", key))


def seeded():
    fake = FakeGHL()
    fake.products["prod_1"] = {"_id": "prod_1", "name": "Bundle", "productType": "DIGITAL", "locationId": LOC}
    return fake


def test_49_dollars_is_the_identical_body_from_cli_and_shared_module():
    a, b = seeded(), seeded()
    cli_price(a, 4900)
    shared_price(b, 4900)
    assert a.posts()[0][1:] == b.posts()[0][1:]
    assert a.posts()[0][2]["amount"] == 49.0  # major units, never 4900 (a $4,900 price)


def test_jpy_uses_exponent_zero():
    fake = seeded()
    cli_price(fake, 5000, "JPY")
    assert fake.posts()[0][2]["amount"] == 5000.0
    assert pp.minor_to_api_amount(5000, 0) == 5000.0 and pp.api_amount_to_minor(5000, 0) == 5000
    assert pp.minor_to_api_amount(1500, 3) == 1.5  # KWD


@pytest.mark.parametrize("amount,currency", [(0, "USD"), (4900, "usd"), (4900, "ZZZ"), (-1, "USD")])
def test_bad_money_is_refused_before_any_call_on_both_paths(amount, currency):
    fake = seeded()
    with pytest.raises(pp.SpecError):
        cli_price(fake, amount, currency)
    with pytest.raises(pp.SpecError):
        shared_price(fake, amount, currency)
    assert fake.calls == []


def test_recurring_interval_count_and_trial_are_sent_and_read_back():
    fake = seeded()
    out = cli_price(fake, 2700, recurring_interval="month", recurring_interval_count=3, trial_days=7,
                    price_type="recurring", billing="trial_then_recurring")
    body = fake.posts()[0][2]
    assert body["type"] == "recurring" and body["trialPeriod"] == 7
    assert body["recurring"] == {"interval": "month", "intervalCount": 3}
    assert out["readback"] == "verified"


def test_price_readback_mismatch_is_refused():
    fake = seeded()
    real = fake.request

    def drift(method, path, body=None):
        r = real(method, path, body)
        if method == "GET" and "/price/" in path:
            return pp.Response(200, {**r.body, "amount": 1.0})
        return r

    fake.request = drift
    with pytest.raises(pp.ReadbackMismatch):
        cli_price(fake, 4900)


def test_create_product_twice_creates_once_and_reads_back():
    fake = FakeGHL()
    key = ghl_client._product_key(ghl_client._products_prices(), LOC, "Black Friday Bundle", "DIGITAL")
    ap = approval("products.create", key)
    kw = dict(approval=ap, approval_verifier=accept, location_id=LOC, transport=fake)
    first = ghl_client.create_product("Black Friday Bundle", "DIGITAL", **kw)
    second = ghl_client.create_product("Black Friday Bundle", "DIGITAL", **kw)  # a retry, empty local state
    assert len(fake.posts()) == 1
    assert first["id"] == second["id"] == "prod_1"
    assert first["readback"] == "verified" and second["readback"] == "reconciled"


@pytest.mark.parametrize("bad", ["none", "wrong_action", "wrong_object", "expired", "unverified"])
def test_create_product_refused_without_a_verified_bound_approval(bad):
    fake = FakeGHL()
    key = ghl_client._product_key(ghl_client._products_prices(), LOC, "Vault", "DIGITAL")
    ap = approval("products.create", key)
    verifier = accept
    if bad == "none":
        ap = None
    elif bad == "wrong_action":
        ap["action"] = "products.prices.create"
    elif bad == "wrong_object":
        ap["object_key"] = "someone:else"
    elif bad == "expired":
        ap["expiry"] = 1
    else:
        verifier = lambda _r: False  # noqa: E731
    with pytest.raises(pp.ApprovalRequired):
        ghl_client.create_product("Vault", "DIGITAL", approval=ap, approval_verifier=verifier,
                                  location_id=LOC, transport=fake)
    assert fake.posts() == []


def test_no_verifier_wired_refuses_the_write():
    fake = seeded()
    fake = seeded()
    key = ghl_client._price_key(pp, LOC, "prod_1", "Black Friday", "one_time", "USD", 4900)
    with pytest.raises(pp.ApprovalRequired):
        ghl_client.create_price("prod_1", "Black Friday", 4900, approval=approval("products.prices.create", key),
                                location_id=LOC, transport=fake)
    assert fake.posts() == []


def test_inventory_registers_the_documented_create_route():
    routes = ci.select_route(ci.OpClass.CREATE, resource="products")
    assert routes[0].route == "POST /products/"
    assert {r.route for r in routes} == {"POST /products/", "POST /products/{productId}/price"}
    assert ci.validate_inventory() == []
