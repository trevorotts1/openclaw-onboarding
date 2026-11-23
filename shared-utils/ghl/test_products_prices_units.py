"""S44-14 / CHK-20 / S44-15: one money conversion, read-back, idempotency, approval.

Offline: a stateful fake GHL transport, no network, no credentials.
The CLI-path identical-body proof ($49.00 from `payments create-price` == the shared
builder's body) lives in U-skill44-05's test_build_from_automation.py (carried edit C2).
Run: python3 -m pytest shared-utils/ghl/test_products_prices_units.py -q
"""
import copy
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import capability_inventory as ci  # noqa: E402
import products_prices as pp  # noqa: E402

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


def shared_price(fake, amount_minor, currency="USD", billing="one_time", **spec_kw):
    """Create a price through the shared adapter with a bound per-action approval."""
    key = pp.LogicalKey(LOC, "price", f"t:Black Friday:{billing}:{currency}:{amount_minor}",
                        parent_logical_id="prod_1")
    adapter = pp.ProductsPricesAdapter(fake, pp.InMemoryStore(), approval_verifier=accept)
    spec = pp.PriceSpec("Black Friday", LOC, billing, currency, amount_minor, **spec_kw)
    return adapter.ensure_price(key, spec, pp.NativeProduct("prod_1", LOC, "x", "DIGITAL"),
                                approval("products.prices.create", key))


def product_key(name, ptype="DIGITAL"):
    return pp.LogicalKey(LOC, "product", f"t:{ptype}:{name}")


def seeded():
    fake = FakeGHL()
    fake.products["prod_1"] = {"_id": "prod_1", "name": "Bundle", "productType": "DIGITAL", "locationId": LOC}
    return fake


def test_49_dollars_body_comes_from_the_one_builder():
    fake = seeded()
    shared_price(fake, 4900)
    body = fake.posts()[0][2]
    assert body == pp.price_request_body(pp.PriceSpec("Black Friday", LOC, "one_time", "USD", 4900))
    assert body["amount"] == 49.0 and isinstance(body["amount"], float)  # never 4900 (a $4,900 price)


def test_jpy_uses_exponent_zero():
    fake = seeded()
    shared_price(fake, 5000, "JPY")
    assert fake.posts()[0][2]["amount"] == 5000.0
    assert pp.minor_to_api_amount(5000, 0) == 5000.0 and pp.api_amount_to_minor(5000, 0) == 5000
    assert pp.minor_to_api_amount(1500, 3) == 1.5  # KWD


@pytest.mark.parametrize("amount,currency", [(0, "USD"), (4900, "usd"), (4900, "ZZZ"), (-1, "USD")])
def test_bad_money_is_refused_before_any_call(amount, currency):
    fake = seeded()
    with pytest.raises(pp.SpecError):
        shared_price(fake, amount, currency)
    assert fake.calls == []


def test_recurring_interval_count_and_trial_are_sent_and_read_back():
    fake = seeded()
    _rec, op = shared_price(fake, 2700, billing="trial_then_recurring", recurring_interval="month",
                            recurring_interval_count=3, trial_days=7)
    body = fake.posts()[0][2]
    assert body["type"] == "recurring" and body["trialPeriod"] == 7
    assert body["recurring"] == {"interval": "month", "intervalCount": 3}
    assert op.readback == "verified"


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
        shared_price(fake, 4900)


def test_create_product_twice_creates_once_and_reads_back():
    fake = FakeGHL()
    key = product_key("Black Friday Bundle")
    spec = pp.ProductSpec("Black Friday Bundle", LOC, "DIGITAL")
    ap = approval("products.create", key)
    # a retry with empty local state: a FRESH store each time, the same remote
    first = pp.ProductsPricesAdapter(fake, pp.InMemoryStore(), approval_verifier=accept).ensure_product(key, spec, ap)
    second = pp.ProductsPricesAdapter(fake, pp.InMemoryStore(), approval_verifier=accept).ensure_product(key, spec, ap)
    assert len(fake.posts()) == 1
    assert first[0].native_product_id == second[0].native_product_id == "prod_1"
    assert first[1].readback == "verified" and second[1].readback == "reconciled"


@pytest.mark.parametrize("bad", ["none", "wrong_action", "wrong_object", "expired", "unverified"])
def test_create_product_refused_without_a_verified_bound_approval(bad):
    fake = FakeGHL()
    key = product_key("Vault")
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
    adapter = pp.ProductsPricesAdapter(fake, pp.InMemoryStore(), approval_verifier=verifier)
    with pytest.raises(pp.ApprovalRequired):
        adapter.ensure_product(key, pp.ProductSpec("Vault", LOC, "DIGITAL"), ap)
    assert fake.posts() == []


def test_no_verifier_wired_refuses_the_write():
    fake = seeded()
    key = pp.LogicalKey(LOC, "price", "t:no-verifier", parent_logical_id="prod_1")
    adapter = pp.ProductsPricesAdapter(fake, pp.InMemoryStore())  # no approval_verifier
    with pytest.raises(pp.ApprovalRequired):
        adapter.ensure_price(key, pp.PriceSpec("Black Friday", LOC, "one_time", "USD", 4900),
                             pp.NativeProduct("prod_1", LOC, "x", "DIGITAL"),
                             approval("products.prices.create", key))
    assert fake.posts() == []


def test_inventory_registers_the_documented_create_route():
    routes = ci.select_route(ci.OpClass.CREATE, resource="products")
    assert routes[0].route == "POST /products/"
    assert {r.route for r in routes} == {"POST /products/", "POST /products/{productId}/price"}
    assert ci.validate_inventory() == []


# ---- RFX-017: single-product GET says PHYSICAL for a DIGITAL product ---------------

LIST_ROUTE = "GET " + pp.ROUTES["list_products"][1]


class SplitTypeGHL(FakeGHL):
    """GET /products/{id} answers PHYSICAL (measured live 2026-11-23); the list keeps
    whatever was created unless ``list_type`` overrides it."""

    def __init__(self, single_type="PHYSICAL", list_type=None):
        super().__init__()
        self.single_type, self.list_type = single_type, list_type

    def request(self, method, path, body=None):
        r = super().request(method, path, body)
        bare = path.split("?", 1)[0].rstrip("/")
        if method == "GET" and len(bare.split("/")) == 3:
            return pp.Response(200, {**r.body, "productType": self.single_type})
        if method == "GET" and bare == "/products" and self.list_type:
            return pp.Response(200, {**r.body, "products": [
                {**p, "productType": self.list_type} for p in r.body["products"]]})
        return r


def ensure(fake, name="Workbook", ptype="DIGITAL", store=None):
    key = product_key(name, ptype)
    adapter = pp.ProductsPricesAdapter(fake, store or pp.InMemoryStore(), approval_verifier=accept)
    return adapter.ensure_product(key, pp.ProductSpec(name, LOC, ptype), approval("products.create", key))


def test_digital_read_back_physical_is_confirmed_by_the_product_list():
    fake = SplitTypeGHL()
    rec, op = ensure(fake)
    assert rec.product_type == "DIGITAL" and rec.type_confirmed_by == LIST_ROUTE
    assert op.action == "created" and op.readback == "verified" and len(fake.posts()) == 1
    assert [c[1].split("?")[0] for c in fake.calls] == ["/products/", "/products/", "/products/prod_1", "/products/"]


def test_digital_read_back_physical_and_listed_physical_fails():
    fake = SplitTypeGHL(list_type="PHYSICAL")
    store = pp.InMemoryStore()
    with pytest.raises(pp.ReadbackMismatch, match="does not confirm"):
        ensure(fake, store=store)
    assert store.get(product_key("Workbook").as_tuple()) is None


def test_only_the_row_with_this_id_and_location_confirms_the_type():
    single = {"_id": "prod_1", "name": "Workbook", "productType": "PHYSICAL", "locationId": LOC}
    rows = [{"_id": "prod_2", "name": "Workbook", "productType": "DIGITAL", "locationId": LOC},
            {"_id": "prod_1", "name": "Workbook", "productType": "DIGITAL", "locationId": "elsewhere"}]
    t = pp._FakeTransport([pp.Response(200, single), pp.Response(200, {"products": rows, "total": [{"total": 2}]})])
    adapter = pp.ProductsPricesAdapter(t, pp.InMemoryStore())
    with pytest.raises(pp.ReadbackMismatch, match="does not confirm"):
        adapter._read_product("prod_1", pp.ProductSpec("Workbook", LOC, "DIGITAL"))


@pytest.mark.parametrize("want,single", [("SERVICE", "PHYSICAL"), ("SERVICE", "DIGITAL"), ("PHYSICAL", "DIGITAL")])
def test_every_other_type_mismatch_still_fails_without_a_list_lookup(want, single):
    fake = SplitTypeGHL(single_type=single)
    with pytest.raises(pp.ReadbackMismatch, match="type readback"):
        ensure(fake, ptype=want)
    gets_after_post = [c for c in fake.calls[fake.calls.index(fake.posts()[0]):] if c[0] == "GET"]
    assert [c[1].split("?")[0] for c in gets_after_post] == ["/products/prod_1"]


def test_name_mismatch_still_fails_even_when_the_type_split_applies():
    fake = SplitTypeGHL()
    real = fake.request

    def renamed(method, path, body=None):
        r = real(method, path, body)
        if method == "GET" and len(path.split("?")[0].rstrip("/").split("/")) == 3:
            return pp.Response(200, {**r.body, "name": "Other"})
        return r

    fake.request = renamed
    with pytest.raises(pp.ReadbackMismatch, match="name readback"):
        ensure(fake)


def test_existing_exact_name_digital_product_is_reused_with_no_post():
    fake = SplitTypeGHL()
    fake.products["prod_7"] = {"_id": "prod_7", "name": "Workbook", "productType": "DIGITAL", "locationId": LOC}
    rec, op = ensure(fake)
    assert fake.posts() == []
    assert rec.native_product_id == "prod_7" and rec.type_confirmed_by == LIST_ROUTE
    assert op.action == "reused" and op.readback == "reconciled"
