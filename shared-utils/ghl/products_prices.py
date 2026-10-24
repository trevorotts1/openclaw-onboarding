"""GHL product/price creation, binding and readback adapter (stream W8, assignment W8D-U1).

Catalog creation alone is not checkout binding. This adapter owns three distinct
steps, in order, each recorded (route / location / target / readback):

1. CREATE (documented public API only) -- products and prices via the exact
   documented endpoints and payloads below. 2. BIND -- attach the returned
   native IDs to a native checkout component through the injected component IO
   (managed builder execution; see OUTSTANDING INTEGRATION). 3. READBACK --
   verify every create and every binding against authoritative GET/read state;
   a mismatch is a failure, never a silent success.

Provenance (never invented; every route cites a file or official spec):
  * Official OpenAPI spec `apps/products.json` in GoHighLevel/highlevel-api-docs
    (server https://services.leadconnectorhq.com, security: bearer /
    location access token or Private Integration Token of Sub-Account).
  * In-repo: 29-ghl-convert-and-flow/references/modules.md "products
    (27 endpoints) -- 2021-07-28", scopes products.readonly|write and
    products/prices.readonly|write; 29-ghl-convert-and-flow/references/auth.md
    lists products/prices.readonly|write. Required header Version: 2021-07-28
    (enum per the spec's per-operation parameter).
  * Exact routes used here (spec `paths`):
      POST /products/                                Create Product
      GET  /products/{productId}                     Get Product by ID
      GET  /products/                                List Products
      POST /products/{productId}/price               Create Price for a Product
      GET  /products/{productId}/price/{priceId}     Get Price by ID
      GET  /products/{productId}/price               List Prices for a Product
    Payload fields used (spec components.schemas CreateProductDto /
    CreatePriceDto / RecurringDto): name, locationId, productType (enum
    DIGITAL|PHYSICAL|SERVICE|PHYSICAL/DIGITAL), description, type (enum
    one_time|recurring), currency, amount (number, min 0), recurring
    {interval enum day|week|month|year, intervalCount}, trialPeriod (days).
    Response identity fields: product `_id`, price `_id` + `product`.

Rules encoded (GHL-DELIVERY-SPEC.md "Commerce (W8)" and "Durable execution"):
  * Terms preserved exactly: amount in integer minor units (hundredths, the
    skills/79-checkout convention -- dollars floats never cross the internal
    boundary), currency, billing type (one_time | recurring |
    trial_then_recurring, matching skills/79-checkout/order_bumps.py
    BILLING_TYPES), recurrence interval, trial days, native IDs.
  * Read before create; confirmed IDs persisted immediately under
    (location, kind, parent, logical id) -- never name alone; resume never
    duplicates products/prices and never deletes successful assets.
  * Timeout/uncertain outcome is reconciled before any retry; ambiguous
    matches are refused, never guessed. A WRITE rejected by 429/5xx is an
    uncertain outcome (UncertainWriteOutcome): it is NEVER blindly re-sent --
    reconcile runs first, and a re-send happens only after a reconcile list
    found zero candidates (reconcile-then-retry, never retry-then-reconcile).
  * Provider limits (HTTP 429) get bounded backoff and retry on reads only
    (re-send safe); denials (401/403) raise RouteDenied with no retry and NO
    route switch -- never switch tools to bypass a denial. Retired/unverified
    capability is reported incomplete, never as done.

OUTSTANDING INTEGRATION (provisional unit state):
  * Component IO for binding read/write rides managed builder execution
    (W3B iframe safeguards + W8C 06 order-component execution). The binding
    contract and its verification live here; without a component_io a binding
    is refused as unattached, never claimed bound.
  * The durable store is wired to W4A shared-utils/delivery/checkpoints.py at
    integration; the Store protocol here matches its key discipline.
  * W2B registers these confirmed documented routes in
    shared-utils/ghl/capability_inventory.py (its products_prices_undocumented_here
    restriction predates this spec-cited evidence).
  * Variant/membership/physical-inventory price features are outside the
    supported subset and are refused, never silently dropped.

Interoperability: NativePrice.as_price_ref_fields() returns exactly the
constructor fields of skills/79-checkout/order_bumps.py PriceRef, so W8C can
build CheckoutConfig from these records without re-deriving terms.

Runnable check (offline, fake transport; no network, no live charges):
    python3 -I shared-utils/ghl/products_prices.py
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

API_BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"

PRODUCT_TYPES: Tuple[str, ...] = ("DIGITAL", "PHYSICAL", "SERVICE", "PHYSICAL/DIGITAL")
BILLING_TYPES: Tuple[str, ...] = ("one_time", "recurring", "trial_then_recurring")
RECURRING_INTERVALS: Tuple[str, ...] = ("day", "week", "month", "year")

# Exact documented paths (apps/products.json). One table, never assembled ad hoc.
ROUTES: Mapping[str, Tuple[str, str]] = {
    "create_product": ("POST", "/products/"),
    "get_product": ("GET", "/products/{productId}"),
    "list_products": ("GET", "/products/"),
    "create_price": ("POST", "/products/{productId}/price"),
    "get_price": ("GET", "/products/{productId}/price/{priceId}"),
    "list_prices": ("GET", "/products/{productId}/price"),
}


class ProductsPricesError(Exception):
    """Base: any refusal or verified failure of this adapter."""


class SpecError(ProductsPricesError):
    """Invalid or unsupported requested terms. Refused before any platform call."""


class RouteDenied(ProductsPricesError):
    """401/403 denial on the documented route. Never retried, never rerouted."""


class ApiError(ProductsPricesError):
    """Non-retryable platform rejection (other 4xx) with the real status."""


class ReadbackMismatch(ProductsPricesError):
    """Readback state disagrees with what was written. Never reported as done."""


class AmbiguousReconcile(ProductsPricesError):
    """Uncertain outcome left more than one identity candidate. Refused, never guessed."""


class UnsupportedCapability(ProductsPricesError):
    """A required platform capability is unavailable/disabled here. Incomplete, never done."""


class TransportTimeout(ProductsPricesError):
    """The request may or may not have taken effect. Outcome is UNCERTAIN."""


class UncertainWriteOutcome(ProductsPricesError):
    """A WRITE was rejected by 429/5xx: the platform may or may not have applied
    it. Never blindly re-sent (a re-send can duplicate the product/price); the
    caller reconciles authoritative read state first (reconcile-then-retry)."""


@dataclass(frozen=True)
class Response:
    status: int
    body: Mapping[str, Any]


class Transport:
    """Minimal request surface. Implementations must not log credentials."""

    def request(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> Response:
        raise NotImplementedError


class UrllibTransport(Transport):
    """Documented public API transport (stdlib only). Bearer + Version headers.

    Credential handling: the access token is held privately and placed in the
    Authorization header only; it is never logged or included in error text.
    """

    def __init__(self, access_token: str, base_url: str = API_BASE,
                 version: str = API_VERSION, opener: Optional[Any] = None) -> None:
        if not isinstance(access_token, str) or not access_token.strip():
            raise SpecError("access_token must be a non-empty string")
        self._token = access_token
        self._base = base_url.rstrip("/")
        self._version = version
        self._opener = opener  # injectable for tests; defaults to urllib at call time

    def request(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> Response:
        import json as _json
        import urllib.error
        import urllib.request

        data = _json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self._base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._token)
        req.add_header("Version", self._version)
        req.add_header("Content-Type", "application/json")
        opener = self._opener or urllib.request.build_opener()
        try:
            with opener.open(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return Response(resp.status, _json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as exc:  # documented status, real body
            raw = exc.read().decode("utf-8", "replace")
            try:
                parsed: Mapping[str, Any] = _json.loads(raw) if raw.strip() else {}
            except ValueError:
                parsed = {"raw": raw[:500]}
            return Response(exc.code, parsed)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TransportTimeout(f"{method} {path}: no authoritative outcome")


# --- Terms and records -------------------------------------------------------


def _require_text(value: Any, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{what} must be a non-empty string")


def _require_minor(amount_minor: Any, what: str) -> None:
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise SpecError(f"{what} must be integer minor units (hundredths), never float dollars")
    if amount_minor < 0:
        raise SpecError(f"{what} cannot be negative; unknown price is not zero")


def minor_to_api_amount(amount_minor: int) -> float:
    """Integer hundredths -> the documented numeric `amount` field."""
    return float(Decimal(amount_minor) / 100)


def api_amount_to_minor(value: Any) -> int:
    """Documented numeric `amount` -> integer hundredths; sub-minor drift is a mismatch."""
    try:
        minor = Decimal(str(value)) * 100
    except Exception:
        raise ReadbackMismatch(f"amount is not numeric: {value!r}")
    if minor != minor.to_integral_value():
        raise ReadbackMismatch(f"amount {value!r} is not representable in integer hundredths")
    return int(minor)


@dataclass(frozen=True)
class ProductSpec:
    """Supported product terms (subset of CreateProductDto; extra features refused)."""

    name: str
    location_id: str
    product_type: str
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text(self.name, "product name")
        _require_text(self.location_id, "location_id")
        if self.product_type not in PRODUCT_TYPES:
            raise SpecError(f"product_type must be one of {PRODUCT_TYPES}, got {self.product_type!r}")


@dataclass(frozen=True)
class PriceSpec:
    """Approved price terms, integer minor units (skills/79 PriceRef discipline)."""

    name: str
    location_id: str
    billing_type: str
    currency: str
    amount_minor: int
    recurring_interval: Optional[str] = None
    trial_days: Optional[int] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text(self.name, "price name")
        _require_text(self.location_id, "location_id")
        _require_text(self.currency, "currency")
        _require_minor(self.amount_minor, "amount_minor")
        if self.billing_type not in BILLING_TYPES:
            raise SpecError(f"unknown billing_type: {self.billing_type!r}")
        if self.billing_type == "recurring":
            if self.recurring_interval not in RECURRING_INTERVALS:
                raise SpecError(f"recurring price requires recurring_interval in {RECURRING_INTERVALS}")
            if self.trial_days is not None:
                raise SpecError("recurring price must not carry trial_days")
        elif self.billing_type == "trial_then_recurring":
            if self.recurring_interval not in RECURRING_INTERVALS:
                raise SpecError(f"trial_then_recurring requires recurring_interval in {RECURRING_INTERVALS}")
            if not isinstance(self.trial_days, int) or isinstance(self.trial_days, bool) or self.trial_days < 1:
                raise SpecError("trial_then_recurring requires trial_days >= 1")
        else:  # one_time
            if self.recurring_interval is not None or self.trial_days is not None:
                raise SpecError("one_time price must not carry recurrence or trial terms")

    @property
    def is_recurring(self) -> bool:
        return self.billing_type != "one_time"


StoreKey = Tuple[str, str, str, str]  # (location_id, kind, parent_logical_id, logical_id)


@dataclass(frozen=True)
class LogicalKey:
    """Identity for durable persistence. Never name alone."""

    location_id: str
    kind: str  # "product" | "price"
    logical_id: str
    parent_logical_id: str = ""

    def __post_init__(self) -> None:
        _require_text(self.location_id, "location_id")
        if self.kind not in ("product", "price"):
            raise SpecError(f"kind must be 'product' or 'price', got {self.kind!r}")
        _require_text(self.logical_id, "logical_id")
        if self.kind == "price" and not self.parent_logical_id:
            raise SpecError("price key requires parent_logical_id (its product)")

    def as_tuple(self) -> StoreKey:
        return (self.location_id, self.kind, self.parent_logical_id, self.logical_id)


class Store:
    """Durable ID store surface (wired to W4A checkpoints at integration)."""

    def get(self, key: StoreKey) -> Optional[Mapping[str, Any]]:
        raise NotImplementedError

    def put(self, key: StoreKey, value: Mapping[str, Any]) -> None:
        raise NotImplementedError


class InMemoryStore(Store):
    """Run-scoped store; same protocol the W4A checkpoint store will satisfy."""

    def __init__(self) -> None:
        self._d: Dict[StoreKey, Mapping[str, Any]] = {}

    def get(self, key: StoreKey) -> Optional[Mapping[str, Any]]:
        return self._d.get(key)

    def put(self, key: StoreKey, value: Mapping[str, Any]) -> None:
        self._d[key] = dict(value)


@dataclass(frozen=True)
class OpRecord:
    """Every platform operation is recorded: route, location, target, readback."""

    route: str  # e.g. "POST /products/"
    location_id: str
    target: str  # native id or logical id addressed
    logical_key: StoreKey
    readback: str  # "verified" | "mismatch-refused" | "not-attempted" | "reconciled"


@dataclass(frozen=True)
class NativeProduct:
    native_product_id: str
    location_id: str
    name: str
    product_type: str


@dataclass(frozen=True)
class NativePrice:
    """Readback-verified native price with exact approved terms preserved."""

    native_price_id: str
    native_product_id: str
    name: str
    billing_type: str
    currency: str
    amount_minor: int
    recurring_interval: Optional[str] = None
    trial_days: Optional[int] = None

    def as_price_ref_fields(self) -> Dict[str, Any]:
        """Exactly the skills/79-checkout/order_bumps.py PriceRef constructor fields."""
        return {
            "native_product_id": self.native_product_id,
            "native_price_id": self.native_price_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "billing_type": self.billing_type,
            "recurring_interval": self.recurring_interval,
            "trial_days": self.trial_days,
        }


# --- Binding (catalog creation alone is not checkout binding) ----------------


@dataclass(frozen=True)
class CheckoutBinding:
    """Explicit attachment of readback-verified prices to a native checkout
    component. Bound is claimed only after component readback verification."""

    checkout_component_id: str
    main_price: NativePrice
    state: str  # "bound-verified" only after verify_binding_readback succeeds


class ComponentIO:
    """Read/write of native checkout component price references (managed builder
    execution: W3B iframe safeguards + W8C 06 order-component execution)."""

    def get_checkout_price(self, checkout_component_id: str) -> Optional[Mapping[str, Any]]:
        raise NotImplementedError

    def set_checkout_price(self, checkout_component_id: str, price_ref: Mapping[str, Any]) -> None:
        raise NotImplementedError


# --- Adapter ----------------------------------------------------------------


class ProductsPricesAdapter:
    def __init__(self, transport: Transport, store: Store, sleep: Callable[[float], None] = None,
                 max_attempts: int = 3) -> None:
        self._t = transport
        self._store = store
        self._sleep = sleep or (lambda _s: None)
        self._max = max_attempts

    # -- bounded backoff / denial handling -----------------------------------

    def _call(self, route: str, path_params: Mapping[str, str] = None,
              body: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
        method, template = ROUTES[route]
        path = template.format(**(path_params or {}))
        backoff = 1.0
        for attempt in range(1, self._max + 1):
            try:
                resp = self._t.request(method, path, body)
            except TransportTimeout:
                raise  # uncertain outcome: caller reconciles, never blind retry
            if resp.status in (401, 403):
                raise RouteDenied(f"{method} {path} denied (HTTP {resp.status}); no reroute")
            if resp.status == 429 or resp.status >= 500:
                if method != "GET":  # write: outcome uncertain, never blindly re-sent
                    raise UncertainWriteOutcome(
                        f"{method} {path} uncertain write outcome (HTTP {resp.status}); "
                        f"reconcile before any re-send")
                if attempt == self._max:
                    raise ApiError(f"{method} {path} failed after {self._max} attempts (HTTP {resp.status})")
                self._sleep(backoff)
                backoff = min(backoff * 2, 8.0)  # bounded
                continue
            if not (200 <= resp.status < 300):
                raise ApiError(f"{method} {path} rejected (HTTP {resp.status})")
            return dict(resp.body)
        raise ApiError(f"{method} {path}: exhausted attempts")

    # -- products -------------------------------------------------------------

    def ensure_product(self, key: LogicalKey, spec: ProductSpec) -> Tuple[NativeProduct, OpRecord]:
        """Read before create; create with readback; persist confirmed ID immediately;
        resume never duplicates. Uncertain create outcomes are reconciled first."""
        if key.kind != "product":
            raise SpecError("ensure_product requires a product LogicalKey")
        if spec.location_id != key.location_id:
            raise SpecError("spec.location_id must match the logical key location")

        known = self._store.get(key.as_tuple())
        if known:
            rec = self._read_product(str(known["native_product_id"]), spec)
            return rec, OpRecord(ROUTES["get_product"][0] + " " + ROUTES["get_product"][1],
                                 key.location_id, rec.native_product_id, key.as_tuple(), "verified")

        try:
            created = self._call("create_product", body={
                "name": spec.name,
                "locationId": spec.location_id,
                "productType": spec.product_type,
                **({"description": spec.description} if spec.description else {}),
            })
        except (TransportTimeout, UncertainWriteOutcome):
            rec = self._reconcile_product(key, spec)
            return rec, OpRecord(ROUTES["create_product"][0] + " " + ROUTES["create_product"][1],
                                 key.location_id, rec.native_product_id, key.as_tuple(), "reconciled")

        native_id = str(created.get("_id") or "")
        if not native_id:
            raise ReadbackMismatch("create product response carries no _id")
        rec = self._read_product(native_id, spec)  # readback verifies before the ID is trusted
        self._store.put(key.as_tuple(), {"native_product_id": rec.native_product_id})
        return rec, OpRecord(ROUTES["create_product"][0] + " " + ROUTES["create_product"][1],
                             key.location_id, rec.native_product_id, key.as_tuple(), "verified")

    def _read_product(self, native_id: str, spec: ProductSpec) -> NativeProduct:
        body = self._call("get_product", {"productId": native_id})
        got_id = str(body.get("_id") or "")
        if got_id != native_id:
            raise ReadbackMismatch(f"product readback id {got_id!r} != requested {native_id!r}")
        if str(body.get("name") or "") != spec.name:
            raise ReadbackMismatch(f"product {native_id} name readback {body.get('name')!r} != {spec.name!r}")
        if str(body.get("productType") or "") != spec.product_type:
            raise ReadbackMismatch(f"product {native_id} type readback {body.get('productType')!r} != {spec.product_type!r}")
        if str(body.get("locationId") or "") != spec.location_id:
            raise ReadbackMismatch(f"product {native_id} location readback {body.get('locationId')!r} != {spec.location_id!r}")
        return NativeProduct(native_id, spec.location_id, spec.name, spec.product_type)

    def _reconcile_product(self, key: LogicalKey, spec: ProductSpec) -> NativeProduct:
        """Timeout after send: list by identity (location+name+type, never name
        alone), adopt exactly one match, refuse ambiguity, recreate on zero."""
        listed = self._call("list_products", body={"locationId": spec.location_id})
        candidates = [p for p in (listed.get("products") or [])
                      if str(p.get("name") or "") == spec.name
                      and str(p.get("productType") or "") == spec.product_type
                      and str(p.get("locationId") or "") == spec.location_id]
        if len(candidates) > 1:
            raise AmbiguousReconcile(
                f"product {spec.name!r} at {spec.location_id}: {len(candidates)} identity candidates; refusing to guess")
        if not candidates:
            created = self._call("create_product", body={
                "name": spec.name, "locationId": spec.location_id, "productType": spec.product_type,
                **({"description": spec.description} if spec.description else {}),
            })
            native_id = str(created.get("_id") or "")
            if not native_id:
                raise ReadbackMismatch("recreate product response carries no _id")
        else:
            native_id = str(candidates[0].get("_id") or "")
        rec = self._read_product(native_id, spec)
        self._store.put(key.as_tuple(), {"native_product_id": rec.native_product_id})
        return rec

    # -- prices ---------------------------------------------------------------

    def ensure_price(self, key: LogicalKey, spec: PriceSpec, product: NativeProduct) -> Tuple[NativePrice, OpRecord]:
        """Same discipline as ensure_product, parented by the native product."""
        if key.kind != "price":
            raise SpecError("ensure_price requires a price LogicalKey")
        if spec.location_id != key.location_id:
            raise SpecError("spec.location_id must match the logical key location")

        known = self._store.get(key.as_tuple())
        if known:
            rec = self._read_price(product, str(known["native_price_id"]), spec)
            return rec, OpRecord(ROUTES["get_price"][0] + " " + ROUTES["get_price"][1],
                                 key.location_id, rec.native_price_id, key.as_tuple(), "verified")

        body = self._price_payload(spec)
        try:
            created = self._call("create_price", {"productId": product.native_product_id}, body)
        except (TransportTimeout, UncertainWriteOutcome):
            rec = self._reconcile_price(key, spec, product)
            return rec, OpRecord(ROUTES["create_price"][0] + " " + ROUTES["create_price"][1],
                                 key.location_id, rec.native_price_id, key.as_tuple(), "reconciled")

        native_id = str(created.get("_id") or "")
        if not native_id:
            raise ReadbackMismatch("create price response carries no _id")
        rec = self._read_price(product, native_id, spec)
        self._store.put(key.as_tuple(), {"native_price_id": rec.native_price_id})
        return rec, OpRecord(ROUTES["create_price"][0] + " " + ROUTES["create_price"][1],
                             key.location_id, rec.native_price_id, key.as_tuple(), "verified")

    def _price_payload(self, spec: PriceSpec) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": spec.name,
            "locationId": spec.location_id,
            "currency": spec.currency,
            "amount": minor_to_api_amount(spec.amount_minor),
            "type": "one_time" if spec.billing_type == "one_time" else "recurring",
        }
        if spec.description:
            payload["description"] = spec.description
        if spec.recurring_interval:
            payload["recurring"] = {"interval": spec.recurring_interval, "intervalCount": 1}
        if spec.trial_days is not None:
            payload["trialPeriod"] = spec.trial_days
        return payload

    def _read_price(self, product: NativeProduct, native_id: str, spec: PriceSpec) -> NativePrice:
        body = self._call("get_price", {"productId": product.native_product_id, "priceId": native_id})
        got_id = str(body.get("_id") or "")
        if got_id != native_id:
            raise ReadbackMismatch(f"price readback id {got_id!r} != requested {native_id!r}")
        if str(body.get("product") or "") != product.native_product_id:
            raise ReadbackMismatch(f"price {native_id} parent readback {body.get('product')!r} != {product.native_product_id!r}")
        amount_minor = api_amount_to_minor(body.get("amount"))
        if amount_minor != spec.amount_minor:
            raise ReadbackMismatch(f"price {native_id} amount readback {amount_minor} != {spec.amount_minor} minor")
        if str(body.get("currency") or "") != spec.currency:
            raise ReadbackMismatch(f"price {native_id} currency readback {body.get('currency')!r} != {spec.currency!r}")
        want_type = "one_time" if spec.billing_type == "one_time" else "recurring"
        if str(body.get("type") or "") != want_type:
            raise ReadbackMismatch(f"price {native_id} type readback {body.get('type')!r} != {want_type!r}")
        if spec.recurring_interval:
            recurring = body.get("recurring") or {}
            if str(recurring.get("interval") or "") != spec.recurring_interval:
                raise ReadbackMismatch(f"price {native_id} interval readback {recurring.get('interval')!r} != {spec.recurring_interval!r}")
        raw_trial = body.get("trialPeriod")
        if raw_trial is None:
            readback_trial = None  # omitted: equal only when the spec expects no trial
        elif isinstance(raw_trial, bool) or not isinstance(raw_trial, (int, float)) or int(raw_trial) != raw_trial:
            raise ReadbackMismatch(f"price {native_id} trialPeriod readback {raw_trial!r} is not an integer day count")
        else:
            readback_trial = int(raw_trial)
        if readback_trial != spec.trial_days:
            raise ReadbackMismatch(f"price {native_id} trialPeriod readback {readback_trial!r} != spec trial_days {spec.trial_days!r}")
        return NativePrice(
            native_price_id=native_id,
            native_product_id=product.native_product_id,
            name=spec.name,
            billing_type=spec.billing_type,
            currency=spec.currency,
            amount_minor=spec.amount_minor,
            recurring_interval=spec.recurring_interval,
            trial_days=readback_trial,
        )

    def _reconcile_price(self, key: LogicalKey, spec: PriceSpec, product: NativeProduct) -> NativePrice:
        listed = self._call("list_prices", {"productId": product.native_product_id})
        want_type = "one_time" if spec.billing_type == "one_time" else "recurring"
        candidates = []
        for p in (listed.get("prices") or []):
            try:
                minor = api_amount_to_minor(p.get("amount"))
            except ReadbackMismatch:
                continue
            if (str(p.get("name") or "") == spec.name
                    and str(p.get("type") or "") == want_type
                    and str(p.get("currency") or "") == spec.currency
                    and minor == spec.amount_minor):
                candidates.append(p)
        if len(candidates) > 1:
            raise AmbiguousReconcile(
                f"price {spec.name!r} on {product.native_product_id}: {len(candidates)} identity candidates; refusing to guess")
        if not candidates:
            created = self._call("create_price", {"productId": product.native_product_id}, self._price_payload(spec))
            native_id = str(created.get("_id") or "")
            if not native_id:
                raise ReadbackMismatch("recreate price response carries no _id")
        else:
            native_id = str(candidates[0].get("_id") or "")
        rec = self._read_price(product, native_id, spec)
        self._store.put(key.as_tuple(), {"native_price_id": rec.native_price_id})
        return rec

    # -- binding --------------------------------------------------------------

    def bind_price_to_checkout(self, checkout_component_id: str, price: NativePrice,
                               component_io: Optional[ComponentIO]) -> CheckoutBinding:
        """Attach a readback-verified price to a native checkout component and
        verify the attachment by component readback. Catalog creation alone is
        not checkout binding: without component IO the binding is refused as
        unattached (capability incomplete), never claimed bound."""
        _require_text(checkout_component_id, "checkout_component_id")
        if not isinstance(price, NativePrice):
            raise SpecError("bind_price_to_checkout requires a readback-verified NativePrice")
        if component_io is None:
            raise UnsupportedCapability(
                "native checkout component attachment unavailable (managed builder execution "
                "not wired: W3B/W8C integration); catalog IDs alone are NOT checkout binding")
        ref = price.as_price_ref_fields()
        component_io.set_checkout_price(checkout_component_id, ref)
        observed = component_io.get_checkout_price(checkout_component_id)
        if not isinstance(observed, Mapping):
            raise ReadbackMismatch(f"checkout component {checkout_component_id} readback missing after bind")
        for field_name, want in ref.items():
            got = observed.get(field_name)
            if got != want:
                raise ReadbackMismatch(
                    f"checkout component {checkout_component_id} {field_name} readback {got!r} != {want!r}")
        return CheckoutBinding(checkout_component_id, price, "bound-verified")


# --- Assert-based self-check (offline; fake transport and component IO) ------


class _FakeTransport(Transport):
    """Scripted responses; records every call. No network in the check."""

    def __init__(self, script: Sequence[Any]) -> None:
        self._script = list(script)
        self.calls: List[Tuple[str, str, Optional[Mapping[str, Any]]]] = []

    def request(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> Response:
        self.calls.append((method, path, body))
        action = self._script.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class _FakeComponentIO(ComponentIO):
    def __init__(self, initial: Optional[Mapping[str, Any]] = None,
                 drift_on_read: Optional[Mapping[str, Any]] = None) -> None:
        self.state: Optional[Dict[str, Any]] = dict(initial) if initial else None
        self._drift = dict(drift_on_read or {})  # simulates a component that stores wrong values

    def get_checkout_price(self, checkout_component_id: str) -> Optional[Mapping[str, Any]]:
        return {**self.state, **self._drift} if self.state else None

    def set_checkout_price(self, checkout_component_id: str, price_ref: Mapping[str, Any]) -> None:
        self.state = dict(price_ref)


def _self_check() -> int:
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, what
        checks += 1

    def refused(fn, exc, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except exc:
            checks += 1
            return
        raise AssertionError(f"expected {exc.__name__}: {what}")

    sleeps: List[float] = []
    loc = "loc_1"

    product_body = {"_id": "prod_1", "locationId": loc, "name": "Vault Access", "productType": "DIGITAL"}

    # 1. Create product: POST /products/ then GET readback, ID persisted under the logical key.
    t1 = _FakeTransport([Response(200, product_body), Response(200, product_body)])
    store = InMemoryStore()
    a = ProductsPricesAdapter(t1, store, sleep=sleeps.append)
    key_p = LogicalKey(loc, "product", "funnelA.main.product")
    rec, op = a.ensure_product(key_p, ProductSpec("Vault Access", loc, "DIGITAL"))
    ok(rec.native_product_id == "prod_1", "create product returns native id")
    ok(t1.calls[0][0:2] == ("POST", "/products/"), "create uses documented POST /products/ route")
    ok(t1.calls[1][0:2] == ("GET", "/products/prod_1"), "readback uses documented GET /products/{productId}")
    ok(store.get(key_p.as_tuple()) == {"native_product_id": "prod_1"}, "confirmed ID persisted under logical key")
    ok(op.readback == "verified" and op.target == "prod_1", "operation record carries route/location/target/readback")

    # 2. Resume: store hit means readback only, never a second create.
    t2 = _FakeTransport([Response(200, product_body)])
    a2 = ProductsPricesAdapter(t2, store, sleep=sleeps.append)
    rec2, _ = a2.ensure_product(key_p, ProductSpec("Vault Access", loc, "DIGITAL"))
    ok(rec2 == rec and len(t2.calls) == 1 and t2.calls[0][0] == "GET", "resume never duplicates the product")

    # 3. Price create: amount is integer minor units internally, documented numeric field on the wire.
    price_body = {"_id": "price_1", "product": "prod_1", "name": "Pay in full", "type": "one_time",
                  "currency": "USD", "amount": 97.5}
    t3 = _FakeTransport([Response(200, price_body), Response(200, price_body)])
    a3 = ProductsPricesAdapter(t3, store, sleep=sleeps.append)
    key_r = LogicalKey(loc, "price", "funnelA.main.price", parent_logical_id="funnelA.main.product")
    prec, pop = a3.ensure_price(key_r, PriceSpec("Pay in full", loc, "one_time", "USD", 9750), rec)
    ok(prec.amount_minor == 9750 and prec.currency == "USD", "price terms preserved in integer minor units")
    sent = t3.calls[0][2]
    ok(sent["amount"] == 97.5 and sent["type"] == "one_time", "wire amount/type match documented CreatePriceDto")
    ok(t3.calls[0][0:2] == ("POST", "/products/prod_1/price"), "price create uses documented /products/{productId}/price")
    ok(pop.readback == "verified", "price create readback verified")

    # 4. Recurring + trial mapping onto documented fields (recurring{interval,intervalCount},
    #    trialPeriod), with trialPeriod READ BACK and verified (happy path: readback matches).
    rec_body = {"_id": "price_2", "product": "prod_1", "name": "Monthly", "type": "recurring",
                "currency": "USD", "amount": 27.0, "recurring": {"interval": "month", "intervalCount": 1}}
    rec_body_ok = dict(rec_body, trialPeriod=7)
    t4 = _FakeTransport([Response(200, rec_body_ok), Response(200, rec_body_ok)])
    a4 = ProductsPricesAdapter(t4, store, sleep=sleeps.append)
    key_m = LogicalKey(loc, "price", "funnelA.monthly.price", parent_logical_id="funnelA.main.product")
    mrec, _ = a4.ensure_price(
        key_m, PriceSpec("Monthly", loc, "trial_then_recurring", "USD", 2700,
                         recurring_interval="month", trial_days=7), rec)
    sent4 = t4.calls[0][2]
    ok(sent4["type"] == "recurring" and sent4["recurring"] == {"interval": "month", "intervalCount": 1},
       "recurring terms map to documented RecurringDto")
    ok(sent4["trialPeriod"] == 7, "trial maps to documented trialPeriod days")
    ok(mrec.billing_type == "trial_then_recurring" and mrec.trial_days == 7 and mrec.recurring_interval == "month",
       "billing terms preserved for skills/79 PriceRef interop")
    ok(mrec.trial_days == rec_body_ok["trialPeriod"], "NativePrice.trial_days comes from the readback, not the request")
    ok(mrec.as_price_ref_fields()["native_price_id"] == "price_2",
       "as_price_ref_fields exposes skills/79 PriceRef constructor fields")

    # 5. Readback drift is a failure: ID is not stored, mismatch raised.
    drift_body = dict(price_body, _id="price_9", amount=96.0)
    t5 = _FakeTransport([Response(200, drift_body), Response(200, drift_body)])
    a5 = ProductsPricesAdapter(t5, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a5.ensure_price(LogicalKey(loc, "price", "x", parent_logical_id="funnelA.main.product"),
                                    PriceSpec("Pay in full", loc, "one_time", "USD", 9750), rec),
            ReadbackMismatch, "amount drift on readback")
    ok(a5._store.get((loc, "price", "funnelA.main.product", "x")) is None, "mismatched ID is never persisted")

    # 6. Uncertain outcome (timeout on create) reconciles before retry: one candidate adopted, zero recreated.
    t6 = _FakeTransport([TransportTimeout("boom"),
                         Response(200, {"products": [product_body], "total": 1}),
                         Response(200, product_body)])
    a6 = ProductsPricesAdapter(t6, InMemoryStore(), sleep=sleeps.append)
    rec6, op6 = a6.ensure_product(LogicalKey(loc, "product", "p6"), ProductSpec("Vault Access", loc, "DIGITAL"))
    ok(rec6.native_product_id == "prod_1" and op6.readback == "reconciled", "timeout reconciles to the single identity candidate")
    t6b = _FakeTransport([TransportTimeout("boom"),
                          Response(200, {"products": [], "total": 0}),
                          Response(200, product_body),
                          Response(200, product_body)])
    a6b = ProductsPricesAdapter(t6b, InMemoryStore(), sleep=sleeps.append)
    rec6b, _ = a6b.ensure_product(LogicalKey(loc, "product", "p6b"), ProductSpec("Vault Access", loc, "DIGITAL"))
    ok(rec6b.native_product_id == "prod_1" and t6b.calls[2][0] == "POST", "zero candidates recreates once after reconcile")

    # 7. Ambiguous reconcile is refused, never guessed.
    twin = dict(product_body, _id="prod_2")
    t7 = _FakeTransport([TransportTimeout("boom"),
                         Response(200, {"products": [product_body, twin], "total": 2})])
    a7 = ProductsPricesAdapter(t7, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a7.ensure_product(LogicalKey(loc, "product", "p7"), ProductSpec("Vault Access", loc, "DIGITAL")),
            AmbiguousReconcile, "two identity candidates")

    # 8. 429 on a READ is retried with bounded backoff (re-send is safe there);
    #    denial gets neither retry nor reroute.
    store8 = InMemoryStore()
    store8.put(key_p.as_tuple(), {"native_product_id": "prod_1"})
    t8 = _FakeTransport([Response(429, {}), Response(429, {}), Response(200, product_body)])
    a8 = ProductsPricesAdapter(t8, store8, sleep=sleeps.append)
    rec8, _ = a8.ensure_product(key_p, ProductSpec("Vault Access", loc, "DIGITAL"))
    ok(rec8.native_product_id == "prod_1" and len(sleeps) == 2, "429 on read retried with bounded backoff")
    ok(all(s <= 8.0 for s in sleeps), "backoff stays bounded")
    t9 = _FakeTransport([Response(403, {"message": "denied"})])
    a9 = ProductsPricesAdapter(t9, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a9.ensure_product(LogicalKey(loc, "product", "p9"), ProductSpec("Vault Access", loc, "DIGITAL")),
            RouteDenied, "403 denial")
    ok(len(t9.calls) == 1, "denial is never retried and never rerouted")

    # 9. Binding: without component IO it is refused (catalog != binding); with it,
    #    write + readback verification; drifted component readback is a mismatch.
    refused(lambda: a.bind_price_to_checkout("chk_1", prec, None),
            UnsupportedCapability, "bind without component IO")
    comp = _FakeComponentIO()
    binding = a.bind_price_to_checkout("chk_1", prec, comp)
    ok(binding.state == "bound-verified" and binding.checkout_component_id == "chk_1",
       "bind writes the component and verifies readback")
    ok(comp.state == prec.as_price_ref_fields(), "component holds exactly the approved price refs")
    comp_drift = _FakeComponentIO(drift_on_read={"native_price_id": "price_evil"})
    refused(lambda: a.bind_price_to_checkout("chk_2", prec, comp_drift),
            ReadbackMismatch, "component readback drift")

    # 10. Spec guards: floats/bools/negatives and unsupported terms refused before any call.
    refused(lambda: PriceSpec("x", loc, "one_time", "USD", 27.0), SpecError, "float amount")
    refused(lambda: PriceSpec("x", loc, "one_time", "USD", True), SpecError, "bool amount")
    refused(lambda: PriceSpec("x", loc, "one_time", "USD", -1), SpecError, "negative amount")
    refused(lambda: PriceSpec("x", loc, "recurring", "USD", 100), SpecError, "recurring without interval")
    refused(lambda: PriceSpec("x", loc, "one_time", "USD", 100, recurring_interval="month"), SpecError, "one_time with recurrence")
    refused(lambda: ProductSpec("x", loc, "SUBSCRIPTION"), SpecError, "unsupported productType")
    refused(lambda: LogicalKey(loc, "price", "x"), SpecError, "price key without parent")

    # 11. A 429/5xx on a WRITE is an uncertain outcome: raised at once so reconcile
    #     runs first -- NEVER a blind re-send (a duplicate product/price could
    #     result). Transport calls are counted: exactly one per write attempt.
    tw = _FakeTransport([Response(503, {}), Response(503, {}), Response(503, {})])
    aw = ProductsPricesAdapter(tw, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: aw._call("create_product", body={
        "name": "Vault Access", "locationId": loc, "productType": "DIGITAL"}),
            UncertainWriteOutcome, "503 on create write is an uncertain outcome")
    ok(len(tw.calls) == 1, "503 on write: exactly one transport call, never a blind retry")
    t429w = _FakeTransport([Response(429, {}), Response(429, {})])
    a429w = ProductsPricesAdapter(t429w, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a429w._call("create_price", {"productId": "prod_1"}, {"name": "x"}),
            UncertainWriteOutcome, "429 on create write is an uncertain outcome")
    ok(len(t429w.calls) == 1, "429 on write: exactly one transport call, never a blind retry")

    # 12. Reconcile-then-retry: the 5xx create surfaces as an uncertain outcome and
    #     the reconcile list runs BEFORE any write re-send (adopted candidate: zero
    #     re-sends; a re-send happens only after a zero-candidate list).
    t11 = _FakeTransport([Response(503, {}),
                          Response(200, {"products": [product_body], "total": 1}),
                          Response(200, product_body)])
    a11 = ProductsPricesAdapter(t11, InMemoryStore(), sleep=sleeps.append)
    rec11, op11 = a11.ensure_product(LogicalKey(loc, "product", "p11"), ProductSpec("Vault Access", loc, "DIGITAL"))
    posts11 = [c for c in t11.calls if c[0] == "POST"]
    ok(op11.readback == "reconciled" and rec11.native_product_id == "prod_1",
       "5xx create reconciles to the single identity candidate")
    ok(len(posts11) == 1 and t11.calls[1][0] == "GET",
       "reconcile list runs before any write re-send (exactly one POST)")

    # 13. trialPeriod is verified on readback like every other field: drift is a
    #     mismatch, absent readback with a requested trial is a mismatch, and an
    #     unrequested trial is a mismatch (omitted + spec-none is equal, check 3/4).
    drift_trial = dict(rec_body, _id="price_3", trialPeriod=14)
    t12 = _FakeTransport([Response(200, drift_trial), Response(200, drift_trial)])
    a12 = ProductsPricesAdapter(t12, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a12.ensure_price(LogicalKey(loc, "price", "p12", parent_logical_id="funnelA.main.product"),
                                     PriceSpec("Monthly", loc, "trial_then_recurring", "USD", 2700,
                                               recurring_interval="month", trial_days=7), rec),
            ReadbackMismatch, "trialPeriod drift on readback")
    absent_trial = dict(rec_body, _id="price_4")
    t13 = _FakeTransport([Response(200, absent_trial), Response(200, absent_trial)])
    a13 = ProductsPricesAdapter(t13, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a13.ensure_price(LogicalKey(loc, "price", "p13", parent_logical_id="funnelA.main.product"),
                                     PriceSpec("Monthly", loc, "trial_then_recurring", "USD", 2700,
                                               recurring_interval="month", trial_days=7), rec),
            ReadbackMismatch, "absent trialPeriod with a requested trial is a mismatch")
    unrequested_trial = dict(price_body, _id="price_5", trialPeriod=3)
    t14 = _FakeTransport([Response(200, unrequested_trial), Response(200, unrequested_trial)])
    a14 = ProductsPricesAdapter(t14, InMemoryStore(), sleep=sleeps.append)
    refused(lambda: a14.ensure_price(LogicalKey(loc, "price", "p14", parent_logical_id="funnelA.main.product"),
                                     PriceSpec("Pay in full", loc, "one_time", "USD", 9750), rec),
            ReadbackMismatch, "unrequested trialPeriod on readback is a mismatch")
    ok(a12._store.get((loc, "price", "funnelA.main.product", "p12")) is None
       and a13._store.get((loc, "price", "funnelA.main.product", "p13")) is None
       and a14._store.get((loc, "price", "funnelA.main.product", "p14")) is None,
       "trial-period mismatches never persist an ID")

    return checks


if __name__ == "__main__":
    n = _self_check()
    print(f"self-check OK ({n} assertions)")
