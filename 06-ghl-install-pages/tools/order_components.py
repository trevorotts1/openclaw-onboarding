"""Native order-component execution for GHL delivery — Skill 06 (06-ghl-install-pages).

Binds REAL checkout component IDs to REAL product/price IDs during managed
builder execution, and verifies every mutation by component read-back.
Governing sources:

  * 06-ghl-install-pages/GHL-DELIVERY-SPEC.md, "Commerce (W8) — native reality, no counterfeit
    controls": products/prices attach their returned native IDs to native
    checkout components; catalog creation is NOT checkout binding; bumps
    attach to the right native checkout with accurate terms and intentional
    selection state (never silently preselected extra purchase); native
    totals add/remove; the selected component family's multiple-bump and
    recurring-product limits are respected; NO raw card collection/storage,
    token copying, replayed charges, or simulated payment success.
  * GHL-DELIVERY-SPEC.md, "Confirmed gaps" #2: states must be SET to the
    requested true/false AND read back — never blind-toggle.
  * shared-utils/ghl/products_prices.py (W8D): `ComponentIO` names THIS
    module as its managed-builder execution side. `CheckoutComponentIO`
    here implements that exact surface (`get_checkout_price` /
    `set_checkout_price`) so `ProductsPricesAdapter.bind_price_to_checkout`
    can verify attachment against real component state. Price references
    carry exactly `NativePrice.as_price_ref_fields()` keys.
  * 79-signature-order-form/scripts/order_bumps.py (W8A): billing-type vocabulary,
    approved-catalog/accurate-terms law, family bump limits and explicit
    selection semantics; mirrored structurally here because unit branches
    do not import each other (single-writer merge process).
  * shared-utils/browser/iframe_router.py (W3B): every operation targets an
    EXPLICIT tab + frame; an ambiguous frame or duplicate component id is a
    refusal, never a first-match pick.

This module performs no network calls and no charges of its own. The native
side is an `OrderComponentDriver`; `BrowserManagerDriver` below is the one
concrete driver. It reaches the editor ONLY through
06-ghl-install-pages/tools/browser_manager.sh (the single agent-browser
gateway), and it executes against `ManagedEditorBridge` — the PRODUCTION
page-side adapter. The bridge is generated from ONE live-captured element map
(route + page-data path + element property paths) and installs a real
`window.__ocOrderComponents` that reads the page record, fetches the signed
page-data blob, projects native elements, applies a patch and autosaves the
draft. Nothing about the element shape is invented: an absent capture, an
absent path or an absent adapter is capability incomplete, never "done".

TOTALS ARE AUTHORITATIVE. GHL/payment totals own the quote. The module reads
the platform's own supported breakdown (subtotal, discounts, tax, shipping,
total, currency) and refuses when it does not reconcile with the bound line
items. An omitted tax/discount/shipping component is never assumed zero.

Moved here from skills/06-ghl-delivery/ (that path is now a thin re-export).

Run the assert-based self-check (replays a recorded browser_manager.sh
transcript through BrowserManagerDriver):

    python3 -I 06-ghl-install-pages/tools/order_components.py
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Sequence, Tuple

__all__ = [
    "OrderComponentError",
    "SpecError",
    "ComponentNotFound",
    "AmbiguousTarget",
    "ReadbackMismatch",
    "UnsupportedState",
    "CardDataRefused",
    "AdapterUnavailable",
    "PRICE_REF_FIELDS",
    "BILLING_TYPES",
    "QUOTE_BREAKDOWN_FIELDS",
    "FrameScope",
    "PriceRef",
    "BumpAttach",
    "ComponentFamily",
    "OpRecord",
    "BindRecord",
    "OrderComponentDriver",
    "ManagedEditorBridge",
    "BrowserManagerDriver",
    "CheckoutComponentIO",
    "OrderComponentExecutor",
    "validate_price_ref",
    "price_ref_from_terms",
    "assert_quote_breakdown",
    "validate_managed_adapter_capture",
    "load_managed_adapter_capture",
    "assert_no_card_data",
]

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class OrderComponentError(Exception):
    """Base: any execution the order-component contract forbids."""

class SpecError(OrderComponentError):
    """Malformed input: field sets, billing terms, booleans, identities."""

class ComponentNotFound(OrderComponentError):
    """The requested native component id does not exist in the target frame."""

class AmbiguousTarget(OrderComponentError):
    """More than one component matches (duplicate ids across frames/components).
    Refused rather than resolved by first-match."""

class ReadbackMismatch(OrderComponentError):
    """Component state after a set does not equal the requested state.
    The mismatch is never persisted as success and never claimed bound."""

class UnsupportedState(OrderComponentError):
    """Family limits or requested states the declared capability forbids."""

class CardDataRefused(OrderComponentError):
    """Raw card data must never be collected, stored, or written."""

class AdapterUnavailable(OrderComponentError):
    """No usable managed GHL editor adapter here: the native surface cannot be
    read or written. Capability incomplete — never reported as done."""

# ---------------------------------------------------------------------------
# Price references — exactly W8D NativePrice.as_price_ref_fields() keys
# ---------------------------------------------------------------------------

PRICE_REF_FIELDS = (
    "native_product_id",
    "native_price_id",
    "amount_minor",
    "currency",
    "billing_type",
    "recurring_interval",
    "trial_days",
)

BILLING_TYPES = ("one_time", "recurring", "trial_then_recurring")

#: Approved F08 terms the native price surface cannot express. Recognised so the
#: refusal names the real reason; such a term is NEVER flattened into one_time.
UNSUPPORTED_BILLING_TERMS = ("installment", "installments")
RECURRING_INTERVALS = ("day", "week", "month", "year")
BILLING_NOT_NATIVE = (
    "installment billing has no native CreatePriceDto shape on this surface "
    "(products_prices.BILLING_TYPES is one_time|recurring|trial_then_recurring); "
    "refusing to flatten an installment offer into one_time")

#: The platform's own supported quote breakdown. Every one is REQUIRED on read
#: back: an omitted component is unsupported, never silently zero.
QUOTE_BREAKDOWN_FIELDS = ("currency", "subtotal_minor", "discounts",
                          "tax_minor", "shipping_minor", "total_minor")

# ── Managed editor adapter capture ───────────────────────────────────────────
# One live capture describes where the native commerce elements live on the
# funnel order-form page. With it the bridge reads/writes the REAL page data;
# without it no commerce operation runs (CAPTURE-GATE:CHK-19).
MANAGED_ADAPTER_SCHEMA = "skill6-managed-order-adapter/1"
ADAPTER_ROUTE_KEYS = ("page_read", "autosave")
ADAPTER_PATH_KEYS = ("components", "component_id", "component_kind",
                     "main_price", "bumps", "field_states", "native_totals",
                     "action")
ADAPTER_KIND_KEYS = ("checkout",)

# Key SEGMENTS (tokens), never substrings: "company_name" and "japan" are
# fine, "pan", "card_number", "cardNumber", "billing-cvv" are not.
_CARD_KEY_TOKENS = frozenset({
    "cardnumber", "pan", "cvv", "cvc", "cvv2", "cvc2", "securitycode",
    "expiry", "expmonth", "expyear", "track1", "track2",
})
_KEY_SPLIT_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# 13-19 digits, optionally grouped by single spaces or hyphens.
_PAN_RUN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _require_text(value: Any, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{what} must be a non-empty string")


def _require_bool(value: Any, what: str) -> None:
    if not isinstance(value, bool):
        raise SpecError(f"{what} must be an explicit boolean, never {value!r}")


def _require_minor_units(value: Any, what: str) -> None:
    # bool is an int subclass; a boolean amount is always a mistake.
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpecError(f"{what} must be integer minor units, never float dollars")
    if value < 0:
        raise SpecError(f"{what} cannot be negative; unknown price is not zero")


# ---------------------------------------------------------------------------
# Core value types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameScope:
    """Explicit tab + frame identity (W3B). No defaults: an operation that
    does not know where it points has no business executing."""

    tab_id: str
    frame_id: str

    def __post_init__(self) -> None:
        _require_text(self.tab_id, "tab_id")
        _require_text(self.frame_id, "frame_id")


@dataclass(frozen=True)
class PriceRef:
    """A real native product/price reference with exact verified terms.
    Field set is exactly the W8D `NativePrice.as_price_ref_fields()` contract;
    extras are refused so invented fields can never reach a native component."""

    native_product_id: str
    native_price_id: str
    amount_minor: int
    currency: str
    billing_type: str = "one_time"
    recurring_interval: Optional[str] = None
    trial_days: Optional[int] = None

    def __post_init__(self) -> None:
        _require_text(self.native_product_id, "native_product_id")
        _require_text(self.native_price_id, "native_price_id")
        _require_minor_units(self.amount_minor, "amount_minor")
        _require_text(self.currency, "currency")
        if self.billing_type not in BILLING_TYPES:
            raise SpecError(f"unknown billing_type: {self.billing_type}")
        if self.billing_type == "recurring":
            _require_text(self.recurring_interval or "", "recurring_interval for recurring price")
            if self.trial_days is not None:
                raise SpecError("recurring price must not carry trial_days")
        elif self.billing_type == "trial_then_recurring":
            _require_text(self.recurring_interval or "",
                          "recurring_interval for trial_then_recurring price")
            if not isinstance(self.trial_days, int) or isinstance(self.trial_days, bool) \
                    or self.trial_days < 1:
                raise SpecError("trial_then_recurring price requires trial_days >= 1")
        else:
            if self.recurring_interval is not None or self.trial_days is not None:
                raise SpecError("one_time price must not carry recurrence terms")

    @property
    def is_recurring(self) -> bool:
        return self.billing_type != "one_time"

    def as_fields(self) -> Dict[str, Any]:
        """Exactly the wire mapping W8D writes to a checkout component."""
        return {
            "native_product_id": self.native_product_id,
            "native_price_id": self.native_price_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "billing_type": self.billing_type,
            "recurring_interval": self.recurring_interval,
            "trial_days": self.trial_days,
        }


def validate_price_ref(ref: Mapping[str, Any]) -> PriceRef:
    """Accept exactly PRICE_REF_FIELDS — no missing keys, no invented keys."""
    if not isinstance(ref, Mapping):
        raise SpecError("price ref must be a mapping")
    missing = [k for k in PRICE_REF_FIELDS if k not in ref]
    extra = [k for k in ref if k not in PRICE_REF_FIELDS]
    if missing:
        raise SpecError(f"price ref missing fields: {missing}")
    if extra:
        raise SpecError(f"price ref carries invented fields: {extra}")
    return PriceRef(**{k: ref[k] for k in PRICE_REF_FIELDS})


def price_ref_from_terms(terms: Mapping[str, Any], *, native_product_id: str,
                         native_price_id: str, amount_minor: int,
                         currency: str) -> PriceRef:
    """Build a PriceRef from APPROVED F08 billing terms, carried verbatim.

    ``terms`` is what the offer record holds: ``billing_type`` plus, for the
    recurring shapes, ``recurring_interval`` and ``trial_days``. An absent
    ``billing_type`` is refused — it is never defaulted to ``one_time``, because
    that is exactly the flattening that changes what the buyer is charged. An
    installment term is refused with the real reason.
    """
    if not isinstance(terms, Mapping):
        raise SpecError("billing terms must be a mapping; an absent term is never one_time")
    billing = str(terms.get("billing_type") or "").strip()
    if not billing:
        raise SpecError(
            "billing terms carry no billing_type — refusing to assume one_time")
    if billing in UNSUPPORTED_BILLING_TERMS:
        raise SpecError(BILLING_NOT_NATIVE)
    if billing not in BILLING_TYPES:
        raise SpecError(
            f"billing_type {billing!r} is not one of {BILLING_TYPES}; supply the "
            "approved native term, never a shorthand that has to be guessed")
    interval = terms.get("recurring_interval")
    interval = str(interval).strip() if interval is not None else None
    trial = terms.get("trial_days")
    if billing in ("recurring", "trial_then_recurring"):
        if interval not in RECURRING_INTERVALS:
            raise SpecError(
                f"{billing} price requires recurring_interval in {RECURRING_INTERVALS}")
        if billing == "recurring" and trial is not None:
            raise SpecError("recurring price must not carry trial_days")
        if billing == "trial_then_recurring" and (
                not isinstance(trial, int) or isinstance(trial, bool) or trial < 1):
            raise SpecError("trial_then_recurring price requires trial_days >= 1")
    else:
        if interval or trial is not None:
            raise SpecError("one_time price must not carry recurrence or trial terms")
    return PriceRef(native_product_id, native_price_id, amount_minor, currency,
                    billing, interval if billing != "one_time" else None,
                    trial if billing == "trial_then_recurring" else None)


@dataclass(frozen=True)
class BumpAttach:
    """One order-bump attachment. No selection field on purpose: a bump is
    attached UNSELECTED; selection is explicit later state (W8A law)."""

    offer_id: str
    headline: str
    benefit_explanation: str
    price: PriceRef
    disclosure_text: Optional[str] = None  # required for recurring/trial bumps

    def __post_init__(self) -> None:
        _require_text(self.offer_id, "offer_id")
        _require_text(self.headline, "headline")
        _require_text(self.benefit_explanation, "benefit_explanation")
        if self.price.is_recurring:
            _require_text(self.disclosure_text or "", "disclosure_text for recurring/trial bump")

    def as_fields(self) -> Dict[str, Any]:
        return {
            "offer_id": self.offer_id,
            "headline": self.headline,
            "benefit_explanation": self.benefit_explanation,
            "disclosure_text": self.disclosure_text,
            "price": self.price.as_fields(),
            "selected": False,
        }


@dataclass(frozen=True)
class ComponentFamily:
    """Native checkout component family limits, declared by the caller from
    the W2 capability inventory. This module never invents platform limits
    (structural twin of skills/79-checkout ComponentFamily)."""

    name: str
    max_bumps: int
    allows_recurring_bumps: bool

    def __post_init__(self) -> None:
        _require_text(self.name, "family name")
        if not isinstance(self.max_bumps, int) or isinstance(self.max_bumps, bool) \
                or self.max_bumps < 0:
            raise SpecError("max_bumps must be an integer >= 0 (0 = bumps unsupported)")
        _require_bool(self.allows_recurring_bumps, "allows_recurring_bumps")


@dataclass(frozen=True)
class OpRecord:
    """Every execution operation recorded: route, location, target, readback."""

    route: str  # e.g. "component.set_state"
    tab_id: str
    frame_id: str
    target: str  # native component id addressed
    readback: str  # "verified" | "mismatch-refused" | "not-attempted"


@dataclass(frozen=True)
class BindRecord:
    """Outcome of one bind/attach. `state` is "bound-verified" ONLY after
    component read-back verification succeeded."""

    checkout_component_id: str
    state: str
    op: OpRecord


# ---------------------------------------------------------------------------
# Driver seam — managed builder execution supplied by the caller
# ---------------------------------------------------------------------------

class OrderComponentDriver(Protocol):
    """Native component read/write on ONE explicit tab + frame. Implementations
    live in managed browser execution (W3B iframe safeguards, W3C runtime
    adapters). Ambiguity is surfaced by raising, never by picking."""

    def list_components(self, scope: FrameScope) -> Sequence[Mapping[str, Any]]:
        """All components in the frame, each at least {"component_id", "kind"}."""
        ...

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        """Full component state, or None when the id does not exist."""
        ...

    def set_state(self, scope: FrameScope, component_id: str, patch: Mapping[str, Any]) -> None:
        """Apply a patch to the component. Verification is NOT the driver's job."""
        ...


def _key_is_card_field(key: Any) -> bool:
    parts = [p.lower() for p in _KEY_SPLIT_RE.findall(str(key))]
    # single segments plus adjacent pairs joined ("card"+"number", "exp"+"month")
    candidates = set(parts) | {a + b for a, b in zip(parts, parts[1:])}
    return not candidates.isdisjoint(_CARD_KEY_TOKENS)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def assert_no_card_data(payload: Any, _path: str = "payload") -> None:
    """Fail closed: raw card data never reaches a native component.

    Refuses (a) a key whose segments name card data, at any depth including
    inside lists, and (b) any string value holding a Luhn-valid 13-19 digit
    run, whatever its key. ponytail: strings only (a card number sent as an
    int is not scanned: 13+ digit ints are timestamps/ids far more often);
    a Luhn-valid 13-digit id in free text is a false positive, refused safe.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if _key_is_card_field(key):
                raise CardDataRefused(f"card-data field refused: {key}")
            assert_no_card_data(value, f"{_path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            assert_no_card_data(item, f"{_path}[{i}]")
    elif isinstance(payload, str):
        for run in _PAN_RUN_RE.findall(payload):
            digits = re.sub(r"\D", "", run)
            if _luhn_ok(digits):
                raise CardDataRefused(f"card-number-like value refused at {_path}")


# ---------------------------------------------------------------------------
# W8D ComponentIO surface (managed-builder side named W8C)
# ---------------------------------------------------------------------------

class CheckoutComponentIO:
    """Implements shared-utils/ghl/products_prices.py `ComponentIO`
    (`get_checkout_price` / `set_checkout_price`) over the driver seam, so
    `ProductsPricesAdapter.bind_price_to_checkout` attaches real prices to a
    real checkout component id and verifies them against real read-back."""

    def __init__(self, executor: "OrderComponentExecutor") -> None:
        self._ex = executor

    def get_checkout_price(self, checkout_component_id: str) -> Optional[Mapping[str, Any]]:
        state = self._ex.read_component(checkout_component_id)
        if state is None:
            return None
        ref = state.get("main_price")
        return ref if isinstance(ref, Mapping) else None

    def set_checkout_price(self, checkout_component_id: str, price_ref: Mapping[str, Any]) -> None:
        self._ex.bind_main_price(checkout_component_id, validate_price_ref(price_ref))


# ---------------------------------------------------------------------------
# Native quote breakdown — GHL/payment totals are authoritative
# ---------------------------------------------------------------------------

def _int_minor(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReadbackMismatch(f"{what} must be integer minor units >= 0, got {value!r}")
    return value


def assert_quote_breakdown(totals: Mapping[str, Any], *, currency: str,
                           subtotal_minor: int) -> Dict[str, Any]:
    """Reconcile the platform's OWN quote breakdown against the bound lines.

    The supported breakdown is subtotal + discounts + tax + shipping -> total in
    one currency. Every component is required: a platform that omits tax,
    discounts or shipping has an UNSUPPORTED breakdown here, and an omitted
    component is never read as zero. Nothing is recomputed into existence — the
    check is arithmetic on the numbers the platform reported.
    """
    if not isinstance(totals, Mapping):
        raise UnsupportedState("native totals are absent; there is no quote to compare")
    missing = [k for k in QUOTE_BREAKDOWN_FIELDS if k not in totals]
    if missing:
        raise UnsupportedState(
            f"native totals omit the supported quote breakdown fields {missing}; an "
            "omitted tax/discount/shipping component is never assumed zero")
    got_currency = totals.get("currency")
    if got_currency != currency:
        raise ReadbackMismatch(
            f"native totals currency {got_currency!r} != bound currency {currency!r}")
    got_subtotal = _int_minor(totals.get("subtotal_minor"), "subtotal_minor")
    if got_subtotal != subtotal_minor:
        raise ReadbackMismatch(
            f"native subtotal {got_subtotal} != bound line subtotal {subtotal_minor}")
    raw_discounts = totals.get("discounts")
    if not isinstance(raw_discounts, Sequence) or isinstance(raw_discounts, (str, bytes)):
        raise UnsupportedState("native totals discounts must be a list")
    discounts: list = []
    for entry in raw_discounts:
        if not isinstance(entry, Mapping):
            raise UnsupportedState("native totals discount entry is not a mapping")
        amount = _int_minor(entry.get("amount_minor"), "discount amount_minor")
        code = entry.get("code")
        discounts.append({"code": None if code is None else str(code),
                          "amount_minor": amount})
    discount_total = sum(d["amount_minor"] for d in discounts)
    tax = _int_minor(totals.get("tax_minor"), "tax_minor")
    shipping = _int_minor(totals.get("shipping_minor"), "shipping_minor")
    total = _int_minor(totals.get("total_minor"), "total_minor")
    if discount_total > got_subtotal:
        raise ReadbackMismatch(
            f"discounts {discount_total} exceed the subtotal {got_subtotal}")
    expected_total = got_subtotal - discount_total + tax + shipping
    if total != expected_total:
        raise ReadbackMismatch(
            f"native total {total} != subtotal {got_subtotal} - discounts "
            f"{discount_total} + tax {tax} + shipping {shipping} = {expected_total}")
    return {"subtotal_minor": got_subtotal, "discounts": tuple(discounts),
            "discount_total_minor": discount_total, "tax_minor": tax,
            "shipping_minor": shipping, "total_minor": total}


# ---------------------------------------------------------------------------
# Managed editor adapter capture (CAPTURE-GATE:CHK-19)
# ---------------------------------------------------------------------------

def _ok_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_managed_adapter_capture(capture: Any) -> Sequence[str]:
    """Problems with a managed-adapter element map; [] means usable. Pure."""
    if not isinstance(capture, Mapping):
        return tuple(ADAPTER_ROUTE_KEYS) + ("paths", "element_kinds",
                                            "page_data_url_path")
    bad: list = []
    for key in ADAPTER_ROUTE_KEYS:
        route = capture.get(key)
        if not (isinstance(route, Mapping)
                and route.get("method") in ("GET", "POST", "PUT")
                and _ok_str(route.get("path"))
                and str(route["path"]).startswith("/")):
            bad.append(key)
    paths = capture.get("paths")
    if not (isinstance(paths, Mapping)
            and all(_ok_str(paths.get(k)) for k in ADAPTER_PATH_KEYS)):
        bad.append("paths")
    kinds = capture.get("element_kinds")
    if not (isinstance(kinds, Mapping)
            and all(_ok_str(kinds.get(k)) for k in ADAPTER_KIND_KEYS)):
        bad.append("element_kinds")
    if not _ok_str(capture.get("page_data_url_path")):
        bad.append("page_data_url_path")
    return tuple(bad)


def load_managed_adapter_capture(path: str) -> Dict[str, Any]:
    """The only production ingress for an element map: refuses synthetic/invalid."""
    try:
        with open(path, encoding="utf-8") as fh:
            capture = json.load(fh)
    except (OSError, ValueError) as exc:
        raise AdapterUnavailable(
            f"managed adapter capture unreadable: {type(exc).__name__}") from None
    if isinstance(capture, Mapping) and capture.get("synthetic"):
        raise AdapterUnavailable("CAPTURE-GATE:CHK-19:synthetic_fixture")
    bad = validate_managed_adapter_capture(capture)
    if bad:
        raise AdapterUnavailable(
            "; ".join(f"CAPTURE-GATE:CHK-19:{k}" for k in bad))
    return dict(capture)


# ---------------------------------------------------------------------------
# The one concrete driver: browser_manager.sh `eval` (the single gateway)
# ---------------------------------------------------------------------------

_MANAGER = Path(__file__).resolve().with_name("browser_manager.sh")

# The page-side function this driver installs and calls. The body is generated
# from the captured element map (below); it reads the page record with the
# staged SPA token, fetches the signed page-data blob, projects the native
# elements and autosaves a draft after a patch. No selector or property path is
# written here — every path comes from the capture.
_MANAGED_BRIDGE_JS = r"""(function (cfg) {
  const dig = (o, p) => String(p).split('.').reduce(
    (a, k) => (a && typeof a === 'object' && k in a) ? a[k] : undefined, o);
  const put = (o, p, v) => {
    const ks = String(p).split('.');
    let cur = o;
    for (let i = 0; i < ks.length - 1; i++) {
      if (!cur[ks[i]] || typeof cur[ks[i]] !== 'object') { cur[ks[i]] = {}; }
      cur = cur[ks[i]];
    }
    cur[ks[ks.length - 1]] = v;
  };
  const authHeaders = () => Object.assign({}, cfg.headers,
    {'token-id': window[cfg.tokenGlobal]});
  const fill = (path) => String(path)
    .replace('{page_id}', cfg.pageId)
    .replace('{location_id}', cfg.locationId)
    .replace('{funnel_id}', cfg.funnelId || '');
  async function readBlob() {
    const rec = await fetch(cfg.pageRead.path, {
      method: cfg.pageRead.method, headers: authHeaders()});
    if (!rec.ok) { throw new Error('page-read:' + rec.status); }
    const page = await rec.json();
    const url = dig(page, cfg.pageDataUrlPath);
    if (!url) { throw new Error('page-data-url-missing'); }
    const data = await fetch(url);
    if (!data.ok) { throw new Error('page-data:' + data.status); }
    const body = await data.json();
    const blob = (body && body.pageData) ? body.pageData : body;
    return {page: page, blob: blob};
  }
  function rows(blob) { return dig(blob, cfg.paths.components) || []; }
  function ident(row) { return String(dig(row, cfg.paths.component_id) || ''); }
  function find(blob, id) { return rows(blob).find((r) => ident(r) === String(id)); }
  function project(row) {
    return {
      main_price: dig(row, cfg.paths.main_price),
      bumps: dig(row, cfg.paths.bumps) || [],
      field_states: dig(row, cfg.paths.field_states) || {},
      native_totals: dig(row, cfg.paths.native_totals),
      action: dig(row, cfg.paths.action)
    };
  }
  async function save(blob) {
    const body = {
      funnelId: cfg.funnelId || dig(blob, 'funnelId') || '',
      pageData: blob,
      pageVersion: Number(dig(blob, 'pageVersion') || 0) + 1,
      pageType: 'draft',
      manualSave: true,
      integrations: dig(blob, 'integrations') || {}
    };
    const res = await fetch(fill(cfg.autosave.path), {
      method: cfg.autosave.method,
      headers: Object.assign(authHeaders(), {'Content-Type': 'application/json'}),
      body: JSON.stringify(body)});
    if (!res.ok) { throw new Error('autosave:' + res.status); }
    return res.status;
  }
  async function readPage() {
    const rec = await fetch(fill(cfg.pageRead.path), {
      method: cfg.pageRead.method, headers: authHeaders()});
    if (!rec.ok) { throw new Error('page-read:' + rec.status); }
    return rec.json();
  }
  return async function (req) {
    try {
      const page = await readPage();
      const url = dig(page, cfg.pageDataUrlPath);
      if (!url) { throw new Error('page-data-url-missing'); }
      const data = await fetch(url);
      if (!data.ok) { throw new Error('page-data:' + data.status); }
      const body = await data.json();
      const blob = (body && body.pageData) ? body.pageData : body;
      if (req.op === 'list_components') {
        return {ok: true, result: rows(blob).map(
          (r) => ({component_id: ident(r),
                   kind: String(dig(r, cfg.paths.component_kind) || '')}))};
      }
      if (req.op === 'get_state') {
        const row = find(blob, req.component_id);
        return {ok: true, result: row ? project(row) : null};
      }
      if (req.op === 'set_state') {
        const row = find(blob, req.component_id);
        if (!row) { return {ok: false, error: 'component-not-found'}; }
        const patch = req.patch || {};
        for (const key of Object.keys(patch)) {
          const path = cfg.paths[key];
          if (!path) { return {ok: false, error: 'path-not-captured:' + key}; }
          put(row, path, patch[key]);
        }
        await save(blob);
        return {ok: true, result: null};
      }
      return {ok: false, error: 'unknown-op:' + String(req.op)};
    } catch (e) {
      return {ok: false, error: String((e && e.message) || e)};
    }
  };
})(%s)"""


def _manager_runner(manager: Path = _MANAGER, timeout: int = 120) -> Callable[[Sequence[str]], str]:
    def run(argv: Sequence[str]) -> str:
        proc = subprocess.run(["bash", str(manager), *argv], capture_output=True,
                              text=True, timeout=timeout)
        if proc.returncode != 0:  # stderr may carry session detail: report the code only
            raise OrderComponentError(
                f"browser_manager.sh {argv[0]} failed with exit code {proc.returncode}")
        return proc.stdout
    return run


class ManagedEditorBridge:
    """The production in-page adapter for the GHL funnel order-form step.

    ``capture`` is ONE live element map (``load_managed_adapter_capture``):
    the page-read route, the autosave route, the signed page-data URL path, the
    element list path and the per-element property paths. ``install_js()``
    defines ``window.__ocOrderComponents`` from those paths alone; with no
    capture there is no adapter and every operation is capability incomplete.
    """

    def __init__(self, capture: Mapping[str, Any], *, location_id: str,
                 page_id: str, funnel_id: str = "") -> None:
        bad = validate_managed_adapter_capture(capture)
        if bad:
            raise AdapterUnavailable(
                "; ".join(f"CAPTURE-GATE:CHK-19:{k}" for k in bad))
        _require_text(location_id, "location_id")
        _require_text(page_id, "page_id")
        self.capture = dict(capture)
        self.location_id = location_id
        self.page_id = page_id
        self.funnel_id = str(funnel_id or "")

    def _config(self) -> Dict[str, Any]:
        return {
            "locationId": self.location_id,
            "pageId": self.page_id,
            "funnelId": self.funnel_id,
            "pageRead": self.capture["page_read"],
            "autosave": self.capture["autosave"],
            "pageDataUrlPath": self.capture["page_data_url_path"],
            "paths": self.capture["paths"],
            "kinds": self.capture["element_kinds"],
            "tokenGlobal": self.capture.get("token_global") or "__VT",
            "headers": self.capture.get("headers") or {
                "channel": "APP", "source": "WEB_USER", "version": "2021-07-28"},
        }

    def install_js(self) -> str:
        """Real JS defining ``window.__ocOrderComponents`` from the capture."""
        return "window.__ocOrderComponents=" + (
            _MANAGED_BRIDGE_JS % json.dumps(self._config(), sort_keys=True)) + ";"

    def request_js(self, request: Mapping[str, Any]) -> str:
        """The eval expression that calls the installed adapter ONCE."""
        return (
            "(async () => { const f = window.__ocOrderComponents;"
            " if (typeof f !== 'function')"
            " return JSON.stringify({ok:false,error:'adapter-not-installed'});"
            f" const r = await f({json.dumps(dict(request), sort_keys=True)});"
            " return JSON.stringify(r); })()")


class BrowserManagerDriver:
    """OrderComponentDriver over `browser_manager.sh eval` on one explicit
    tab + frame, executing through the REAL managed editor adapter.

    ``bridge`` is a `ManagedEditorBridge` (production) — or any object exposing
    the same ``install_js``/``request_js`` pair. With no bridge bound the
    driver refuses every operation: an empty injected global is not an adapter
    and is never reported as a completed operation. ``runner(argv) -> stdout``
    is injectable so a recorded transcript can replay the gateway.
    """

    def __init__(self, runner: Optional[Callable[[Sequence[str]], str]] = None,
                 *, bridge: Optional[Any] = None,
                 installed: bool = False) -> None:
        self._run = runner or _manager_runner()
        self._bridge = bridge
        self._installed = bool(installed) and bridge is not None

    def install(self) -> None:
        """Install the page-side adapter ONCE on the current page."""
        if self._bridge is None:
            raise AdapterUnavailable(
                "no managed GHL editor adapter is bound — bind "
                "ManagedEditorBridge(capture, location_id, page_id); an empty "
                "injected bridge is not a production adapter")
        if self._installed:
            return
        out = self._run(["eval", "--", self._bridge.install_js()])
        if not str(out or "").strip():
            raise AdapterUnavailable(
                "the managed editor adapter did not install (empty eval reply)")
        self._installed = True

    def _call(self, scope: FrameScope, op: str, **args: Any) -> Any:
        if self._bridge is None:
            raise AdapterUnavailable(
                f"{op}: no managed GHL editor adapter is bound — the native "
                "commerce surface cannot be read or written")
        self.install()
        request = {"op": op, "tab_id": scope.tab_id, "frame_id": scope.frame_id,
                   **args}
        out = self._run(["eval", "--", self._bridge.request_js(request)])
        try:
            reply = json.loads(out)
            if isinstance(reply, str):  # agent-browser prints a JSON string result quoted
                reply = json.loads(reply)
        except ValueError:
            raise OrderComponentError(f"{op}: reply is not JSON") from None
        if not isinstance(reply, Mapping) or not isinstance(reply.get("ok"), bool):
            raise OrderComponentError(f"{op}: malformed adapter reply")
        if not reply["ok"]:
            code = str(reply.get("error"))
            if code == "ambiguous":
                raise AmbiguousTarget(f"{op}: adapter reports duplicate component ids")
            if code == "component-not-found":
                raise ComponentNotFound(f"{op}: component id not present in the page")
            if code == "adapter-not-installed":
                raise AdapterUnavailable(
                    f"{op}: the page adapter is not installed on this page")
            if code.startswith("path-not-captured:"):
                raise AdapterUnavailable(
                    f"{op}: CAPTURE-GATE:CHK-19:{code.split(':', 1)[1]} is not in "
                    "the captured element map")
            raise OrderComponentError(f"{op}: adapter refused: {code}")
        return reply.get("result")

    def list_components(self, scope: FrameScope) -> Sequence[Mapping[str, Any]]:
        return tuple(self._call(scope, "list_components") or ())

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        return self._call(scope, "get_state", component_id=component_id)

    def set_state(self, scope: FrameScope, component_id: str, patch: Mapping[str, Any]) -> None:
        assert_no_card_data(patch)
        self._call(scope, "set_state", component_id=component_id, patch=dict(patch))


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class OrderComponentExecutor:
    """Executes order-component configuration on one explicit frame.

    Every mutation: validate -> set the requested state -> READ BACK ->
    compare -> record. A read-back mismatch raises ReadbackMismatch and is
    recorded "mismatch-refused"; nothing is ever claimed bound on drift."""

    def __init__(self, driver: OrderComponentDriver, scope: FrameScope,
                 family: ComponentFamily) -> None:
        if not all(hasattr(driver, m) for m in ("list_components", "get_state", "set_state")):
            raise SpecError("driver must implement the OrderComponentDriver surface")
        if not isinstance(scope, FrameScope):
            raise SpecError("scope must be an explicit FrameScope (never a first tab)")
        if not isinstance(family, ComponentFamily):
            raise SpecError("family limits must be declared (W2 capability inventory)")
        self._driver = driver
        self._scope = scope
        self._family = family
        self._ops: list = []

    @property
    def ops(self) -> Tuple[OpRecord, ...]:
        """Every executed operation, in order, success and refusal alike."""
        return tuple(self._ops)

    # -- targeting ----------------------------------------------------------

    def resolve_component(self, component_id: str, kind: str = "checkout") -> Mapping[str, Any]:
        """Exactly one match on the real native id inside the explicit frame.
        Zero -> ComponentNotFound. Duplicates -> AmbiguousTarget. Wrong kind
        -> SpecError. The first listed component is never picked."""
        _require_text(component_id, "checkout_component_id")
        _require_text(kind, "component kind")
        matches = [c for c in self._driver.list_components(self._scope)
                   if isinstance(c, Mapping) and c.get("component_id") == component_id]
        if not matches:
            raise ComponentNotFound(
                f"component {component_id!r} not present in frame {self._scope.frame_id!r}")
        if len(matches) > 1:
            raise AmbiguousTarget(
                f"{len(matches)} components share id {component_id!r} in frame "
                f"{self._scope.frame_id!r}; refusing first-match")
        found = matches[0]
        if found.get("kind") != kind:
            raise SpecError(
                f"component {component_id!r} is kind {found.get('kind')!r}, not {kind!r}")
        return found

    def read_component(self, component_id: str) -> Optional[Mapping[str, Any]]:
        return self._driver.get_state(self._scope, component_id)

    def find_component(self, kind: str) -> str:
        """The id of the ONE component of this kind in the frame. Zero ->
        ComponentNotFound; more than one -> AmbiguousTarget (never first-match).
        Used when the caller knows the element KIND but not its native id."""
        _require_text(kind, "component kind")
        matches = [c for c in self._driver.list_components(self._scope)
                   if isinstance(c, Mapping) and c.get("kind") == kind]
        if not matches:
            raise ComponentNotFound(
                f"no component of kind {kind!r} in frame {self._scope.frame_id!r}")
        if len(matches) > 1:
            raise AmbiguousTarget(
                f"{len(matches)} components of kind {kind!r} in frame "
                f"{self._scope.frame_id!r}; refusing first-match")
        return str(matches[0].get("component_id"))

    # -- verified writes ----------------------------------------------------

    def _write_verified(self, route: str, component_id: str,
                        patch: Mapping[str, Any],
                        verify: Any) -> BindRecord:
        """Set -> read back -> verify. Every attempt is recorded; a mismatch
        re-raises its precise cause after recording "mismatch-refused", and
        success is claimed "bound-verified" only on exact read-back."""
        assert_no_card_data(patch)
        self._driver.set_state(self._scope, component_id, dict(patch))
        observed = self._driver.get_state(self._scope, component_id)
        try:
            verify(observed)
        except OrderComponentError:
            self._ops.append(OpRecord(
                route, self._scope.tab_id, self._scope.frame_id,
                component_id, "mismatch-refused"))
            raise
        record = OpRecord(
            route, self._scope.tab_id, self._scope.frame_id,
            component_id, "verified")
        self._ops.append(record)
        return BindRecord(component_id, "bound-verified", record)

    @staticmethod
    def _verify_fields(component_id: str, observed: Optional[Mapping[str, Any]],
                       want: Mapping[str, Any], where: str) -> None:
        if not isinstance(observed, Mapping):
            raise ReadbackMismatch(
                f"component {component_id} readback missing after set ({where})")
        got = observed.get(where)
        if not isinstance(got, Mapping):
            raise ReadbackMismatch(
                f"component {component_id} {where} readback missing after set")
        for key, value in want.items():
            if got.get(key) != value:
                raise ReadbackMismatch(
                    f"component {component_id} {where}.{key} readback "
                    f"{got.get(key)!r} != {value!r}")

    # -- main price binding -------------------------------------------------

    def bind_main_price(self, checkout_component_id: str,
                        price: PriceRef) -> BindRecord:
        """Attach a real readback-verified price to a real checkout component
        id and verify the attachment by component read-back. Catalog IDs
        alone are never binding; a readback mismatch raises and binds nothing."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(price, PriceRef):
            raise SpecError("bind_main_price requires a validated PriceRef")
        want = price.as_fields()
        return self._write_verified(
            "component.bind_main_price", checkout_component_id,
            {"main_price": want},
            lambda observed: self._verify_fields(
                checkout_component_id, observed, want, "main_price"))

    # -- order bumps --------------------------------------------------------

    def _current_bumps(self, checkout_component_id: str) -> Tuple[Mapping[str, Any], ...]:
        state = self.read_component(checkout_component_id)
        if not isinstance(state, Mapping):
            return ()
        bumps = state.get("bumps")
        if not isinstance(bumps, Sequence) or isinstance(bumps, (str, bytes)):
            return ()
        return tuple(b for b in bumps if isinstance(b, Mapping))

    def attach_bump(self, checkout_component_id: str, bump: BumpAttach) -> BindRecord:
        """Attach an approved bump to the right native checkout, UNSELECTED.
        Family limits (multiple-bump, recurring-product) are enforced here."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(bump, BumpAttach):
            raise SpecError("attach_bump requires a BumpAttach")
        current = self._current_bumps(checkout_component_id)
        if len(current) >= self._family.max_bumps:
            raise UnsupportedState(
                f"family {self._family.name} allows at most {self._family.max_bumps} "
                f"bump(s); refusing attach of {bump.offer_id}")
        if bump.price.is_recurring and not self._family.allows_recurring_bumps:
            raise UnsupportedState(
                f"family {self._family.name} does not allow recurring-product bumps "
                f"(bump {bump.offer_id})")
        state = self.read_component(checkout_component_id) or {}
        main = state.get("main_price") if isinstance(state, Mapping) else None
        if isinstance(main, Mapping) and main.get("currency") not in (None, bump.price.currency):
            raise SpecError(
                f"bump {bump.offer_id} currency {bump.price.currency} does not match "
                f"checkout currency {main.get('currency')}")
        seen_prices = {b.get("price", {}).get("native_price_id") for b in current
                       if isinstance(b.get("price"), Mapping)}
        seen_offers = {b.get("offer_id") for b in current}
        if bump.offer_id in seen_offers:
            raise SpecError(f"duplicate bump offer_id {bump.offer_id}; never charge twice")
        if bump.price.native_price_id in seen_prices:
            raise SpecError(
                f"duplicate native price {bump.price.native_price_id}; never charge twice")
        new_bumps = [dict(b) for b in current] + [bump.as_fields()]
        return self._write_verified(
            "component.attach_bump", checkout_component_id,
            {"bumps": new_bumps},
            lambda observed: self._verify_bumps(
                checkout_component_id, observed, new_bumps))

    @staticmethod
    def _verify_bumps(component_id: str, observed: Optional[Mapping[str, Any]],
                      new_bumps: Sequence[Mapping[str, Any]]) -> None:
        if not isinstance(observed, Mapping):
            raise ReadbackMismatch(f"component {component_id} readback missing after set")
        got_list = observed.get("bumps")
        if not isinstance(got_list, Sequence) or isinstance(got_list, (str, bytes)):
            raise ReadbackMismatch(f"component {component_id} bumps readback missing")
        if len(got_list) != len(new_bumps):
            raise ReadbackMismatch(
                f"component {component_id} bump count {len(got_list)} != {len(new_bumps)}")
        for got, expect in zip(got_list, new_bumps):
            if not isinstance(got, Mapping):
                raise ReadbackMismatch("bump readback entry is not a mapping")
            for key, value in expect.items():
                if key == "selected":
                    continue  # intentional selection verified below
                if got.get(key) != value:
                    raise ReadbackMismatch(
                        f"component {component_id} bump {expect.get('offer_id')} "
                        f"{key} readback {got.get(key)!r} != {value!r}")
            if got.get("selected") is not expect.get("selected"):
                if expect.get("selected") is False:
                    # intentional selection state: never silently preselected
                    raise ReadbackMismatch(
                        f"bump {expect.get('offer_id')} attached preselected "
                        f"({got.get('selected')!r}); extra purchase refused")
                raise ReadbackMismatch(
                    f"bump {expect.get('offer_id')} selected readback "
                    f"{got.get('selected')!r} != {expect.get('selected')!r}")

    def set_bump_selected(self, checkout_component_id: str, offer_id: str,
                          selected: bool) -> BindRecord:
        """Explicit, intentional select/deselect with read-back. Idempotent
        by state; unknown offers are refused, never silently ignored."""
        self.resolve_component(checkout_component_id, "checkout")
        _require_text(offer_id, "offer_id")
        _require_bool(selected, "selection change")
        current = self._current_bumps(checkout_component_id)
        target = [b for b in current if b.get("offer_id") == offer_id]
        if not target:
            raise SpecError(f"offer {offer_id} is not a bump of {checkout_component_id}")
        new_bumps = []
        for bump in current:
            entry = dict(bump)
            if entry.get("offer_id") == offer_id:
                entry["selected"] = selected
            new_bumps.append(entry)
        return self._write_verified(
            "component.set_bump_selected", checkout_component_id,
            {"bumps": new_bumps},
            lambda observed: self._verify_bumps(checkout_component_id, observed, new_bumps))

    # -- required/hidden field states (set AND read back, never blind) -------

    def set_field_state(self, checkout_component_id: str, field_key: str,
                        required: Optional[bool] = None,
                        hidden: Optional[bool] = None) -> BindRecord:
        """Set requested Required/Hidden states to the given true/false AND
        read them back. A blind toggle is impossible: nothing is written
        without an explicit requested value, nothing is accepted without
        read-back equality."""
        self.resolve_component(checkout_component_id, "checkout")
        _require_text(field_key, "field_key")
        if required is None and hidden is None:
            raise SpecError("set_field_state requires at least one requested state")
        patch: Dict[str, Any] = {"field_states": {field_key: {}}}
        want: Dict[str, Any] = {}
        if required is not None:
            _require_bool(required, "required")
            want["required"] = required
        if hidden is not None:
            _require_bool(hidden, "hidden")
            want["hidden"] = hidden
        patch["field_states"][field_key] = dict(want)

        def verify(observed: Optional[Mapping[str, Any]]) -> None:
            if not isinstance(observed, Mapping):
                raise ReadbackMismatch(f"component {checkout_component_id} readback missing")
            states = observed.get("field_states")
            if not isinstance(states, Mapping) or field_key not in states:
                raise ReadbackMismatch(
                    f"component {checkout_component_id} field {field_key} state missing")
            got = states.get(field_key)
            if not isinstance(got, Mapping):
                raise ReadbackMismatch(f"field {field_key} state is not a mapping")
            for key, value in want.items():
                if got.get(key) is not value:
                    raise ReadbackMismatch(
                        f"field {field_key} {key} readback {got.get(key)!r} != {value!r}")

        return self._write_verified(
            "component.set_field_state", checkout_component_id, patch, verify)

    # -- configured purchase action -----------------------------------------

    def set_action(self, checkout_component_id: str, action: str,
                   target_step_id: str) -> BindRecord:
        """Configure the element's purchase action and read it back."""
        self.resolve_component(checkout_component_id, "checkout")
        _require_text(action, "action")
        _require_text(target_step_id, "target_step_id")
        want = {"kind": action, "target_step_id": target_step_id}
        return self._write_verified(
            "component.set_action", checkout_component_id, {"action": want},
            lambda observed: self._verify_fields(
                checkout_component_id, observed, want, "action"))

    # -- native totals ------------------------------------------------------

    def read_native_totals(self, checkout_component_id: str,
                           quantity: int = 1) -> Dict[str, Any]:
        """Reconcile the platform's OWN quote against the bound prices.

        GHL/payment totals are authoritative: the platform's reported subtotal
        must equal the bound line items (main x quantity + explicitly selected
        bumps), and its own supported breakdown (discounts, tax, shipping,
        currency) must reconcile to its own total. Nothing is recomputed into
        existence; an omitted component is unsupported, never zero; no payment
        outcome is ever simulated."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise SpecError("quantity must be an integer >= 1")
        state = self.read_component(checkout_component_id)
        if not isinstance(state, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} state missing")
        main = state.get("main_price")
        if not isinstance(main, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} main_price unbound")
        main_ref = validate_price_ref(main)
        expected_items: list = [("main", main_ref.amount_minor * quantity)]
        expected_subtotal = expected_items[0][1]
        for bump in self._current_bumps(checkout_component_id):
            price = bump.get("price")
            if not isinstance(price, Mapping):
                raise ReadbackMismatch(f"bump {bump.get('offer_id')} price unbound")
            if bump.get("selected") is True:
                ref = validate_price_ref(price)
                expected_items.append((bump.get("offer_id"), ref.amount_minor))
                expected_subtotal += ref.amount_minor
        totals = state.get("native_totals")
        if not isinstance(totals, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} native_totals missing")
        breakdown = assert_quote_breakdown(
            totals, currency=main_ref.currency, subtotal_minor=expected_subtotal)
        return {"currency": main_ref.currency,
                "line_items": tuple(expected_items),
                **breakdown}


# ---------------------------------------------------------------------------
# Assert-based self-check (offline; fake driver — no network, no charges)
# ---------------------------------------------------------------------------

class _FakeDriver:
    """In-memory native components. `drift` simulates a component that stores
    the wrong value (read-back differs from what was written)."""

    def __init__(self, catalog: Sequence[Mapping[str, Any]],
                 states: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        self.catalog = [dict(c) for c in catalog]
        self.states: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in (states or {}).items()
        }
        self.drift: Dict[str, Dict[str, Any]] = {}
        self.calls: list = []
        for cid, st in list(self.states.items()):
            if "native_totals" not in st:  # a seeded breakdown is deliberate
                self._recompute_totals(cid)

    def list_components(self, scope: FrameScope) -> Sequence[Mapping[str, Any]]:
        self.calls.append(("list", scope.tab_id, scope.frame_id))
        return tuple(dict(c) for c in self.catalog)

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        self.calls.append(("get", scope.tab_id, scope.frame_id, component_id))
        stored = self.states.get(component_id)
        if stored is None:
            return None
        return {**stored, **self.drift.get(component_id, {})}

    def set_state(self, scope: FrameScope, component_id: str,
                  patch: Mapping[str, Any]) -> None:
        self.calls.append(("set", scope.tab_id, scope.frame_id, component_id, dict(patch)))
        self.states.setdefault(component_id, {}).update(dict(patch))
        self._recompute_totals(component_id)

    def _recompute_totals(self, component_id: str) -> None:
        """A well-behaved native checkout owns its totals: subtotal from the main
        line plus explicitly selected bumps, then its own discounts/tax/shipping
        to a total. Recomputed on every state change."""
        st = self.states[component_id]
        main = st.get("main_price")
        if not isinstance(main, Mapping) or not isinstance(main.get("amount_minor"), int):
            return
        subtotal = main["amount_minor"]
        for bump in st.get("bumps") or []:
            price = bump.get("price") if isinstance(bump, Mapping) else None
            if isinstance(price, Mapping) and bump.get("selected") is True \
                    and isinstance(price.get("amount_minor"), int):
                subtotal += price["amount_minor"]
        discounts = list(st.get("quote_discounts") or [])
        tax = int(st.get("quote_tax_minor") or 0)
        shipping = int(st.get("quote_shipping_minor") or 0)
        total = subtotal - sum(int(d.get("amount_minor") or 0) for d in discounts) \
            + tax + shipping
        st["native_totals"] = {"currency": main.get("currency"),
                               "subtotal_minor": subtotal,
                               "discounts": discounts,
                               "tax_minor": tax,
                               "shipping_minor": shipping,
                               "total_minor": total}


class _PreselectDriver(_FakeDriver):
    """A buggy platform component that reports every bump as selected —
    the silent-extra-purchase failure the contract must refuse."""

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        state = super().get_state(scope, component_id)
        if state is None:
            return None
        bumps = state.get("bumps") or []
        return {**state, "bumps": [{**b, "selected": True} for b in bumps]}


class _ReplayRunner:
    """browser_manager.sh stand-in for the self-check: answers the bridge
    INSTALL and replays a RECORDED transcript of [request, reply] pairs in
    order, failing on any call that departs from it."""

    def __init__(self, transcript: Sequence[Any]) -> None:
        self._tape = list(transcript)
        self.calls = 0
        self.installs = 0

    def __call__(self, argv: Sequence[str]) -> str:
        assert argv[0] == "eval" and argv[1] == "--", f"unexpected argv {list(argv)[:2]}"
        expr = argv[2]
        if expr.startswith("window.__ocOrderComponents="):
            self.installs += 1
            return "function"
        marker = "await f("
        assert marker in expr, "a request must call the installed adapter"
        start = expr.index(marker) + len(marker)
        end = expr.index(");", start)
        request = json.loads(expr[start:end])
        assert self.calls < len(self._tape), "call beyond the recorded transcript"
        want, reply = self._tape[self.calls]
        assert request == want, f"call {self.calls} departs from the recording"
        self.calls += 1
        return json.dumps(json.dumps(reply))  # agent-browser prints the string result quoted


# One fixture element map (shape only — the live capture is owner-open, see
# GHL-DELIVERY-SPEC.md "Proof levels"). It is used by the self-check to prove
# the adapter is GENERATED from a capture, never that the capture is live.
_FIXTURE_ADAPTER_CAPTURE = {
    "schema": MANAGED_ADAPTER_SCHEMA,
    "page_read": {"method": "GET", "path": "/funnels/page/{page_id}?locationId={location_id}"},
    "autosave": {"method": "POST", "path": "/funnels/builder/autosave/{page_id}"},
    "page_data_url_path": "pageDataDownloadUrl",
    "paths": {
        "components": "elements",
        "component_id": "id",
        "component_kind": "type",
        "main_price": "mainPrice",
        "bumps": "orderBumps",
        "field_states": "fieldStates",
        "native_totals": "nativeTotals",
        "action": "action",
    },
    "element_kinds": {"checkout": "order_form"},
}


# Recorded 2026-11-02 from the in-memory bridge model (no live browser):
# bind_main_price on chk_real_1 (resolve -> set -> read back). Fixture level
# only: the real order-form step has not been live-captured yet
# (GHL-DELIVERY-SPEC.md, "Proof levels").
RECORDED_BIND = json.loads('''[
 [{"frame_id": "frame_1", "op": "list_components", "tab_id": "tab_1"}, {"ok": true, "result": [{"component_id": "chk_real_1", "kind": "checkout"}, {"component_id": "form_real_9", "kind": "order_form"}]}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "set_state", "patch": {"main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}}, "tab_id": "tab_1"}, {"ok": true, "result": null}],
 [{"component_id": "chk_real_1", "frame_id": "frame_1", "op": "get_state", "tab_id": "tab_1"}, {"ok": true, "result": {"bumps": [], "main_price": {"amount_minor": 4900, "billing_type": "one_time", "currency": "USD", "native_price_id": "price_1", "native_product_id": "prod_1", "recurring_interval": null, "trial_days": null}, "native_totals": {"currency": "USD", "total_minor": 4900}}}]
]''')


def _price(product: str = "prod_1", price_id: str = "price_1",
           amount: int = 4900, currency: str = "USD",
           billing: str = "one_time", interval: Optional[str] = None,
           trial: Optional[int] = None) -> PriceRef:
    return PriceRef(product, price_id, amount, currency, billing, interval, trial)


def _self_check() -> int:
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, f"FAIL: {what}"
        checks += 1

    def refused(exc: type, fn: Any, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except exc:
            checks += 1
            return
        except Exception as other:  # noqa: BLE001
            raise AssertionError(f"FAIL: {what}: wrong error {other!r}")
        raise AssertionError(f"FAIL: {what}: accepted, expected {exc.__name__}")

    scope = FrameScope("tab_1", "frame_1")

    # 1 — price reference contract (exact W8D field set)
    ref = _price()
    ok(set(ref.as_fields()) == set(PRICE_REF_FIELDS), "price ref fields == W8D as_price_ref_fields")
    ok(validate_price_ref(ref.as_fields()) == ref, "round trip via validate_price_ref")
    refused(SpecError, lambda: validate_price_ref({k: v for k, v in ref.as_fields().items()
                                                   if k != "trial_days"}), "missing field refused")
    refused(SpecError, lambda: validate_price_ref({**ref.as_fields(), "surcharge": 1}),
            "invented field refused")
    refused(SpecError, lambda: _price(amount=True), "boolean amount refused")
    refused(SpecError, lambda: _price(amount=-1), "negative amount refused")
    refused(SpecError, lambda: _price(billing="recurring"), "recurring without interval refused")
    refused(SpecError, lambda: _price(billing="trial_then_recurring"),
            "trial without trial_days refused")
    refused(SpecError, lambda: _price(billing="weekly"), "unknown billing_type refused")
    refused(SpecError, lambda: _price(billing="one_time", trial=7), "one_time with trial refused")

    # 2 — raw card data never accepted
    ok(assert_no_card_data({"main_price": ref.as_fields()}) is None, "clean payload passes")
    refused(CardDataRefused, lambda: assert_no_card_data({"card_number": "4111"}),
            "card_number refused")
    refused(CardDataRefused, lambda: assert_no_card_data({"payment": {"cvv": "123"}}),
            "nested cvv refused")
    # CHK-22: token-matched keys, Luhn-scanned values, lists traversed
    ok(assert_no_card_data({"company_name": "Acme", "japan": "x", "span": 1}) is None,
       "company_name / substring-'pan' keys allowed")
    refused(CardDataRefused, lambda: assert_no_card_data({"items": [{"cardnumber": "x"}]}),
            "cardnumber key inside a list refused")
    refused(CardDataRefused, lambda: assert_no_card_data({"cardNumber": "x"}), "camelCase key refused")
    refused(CardDataRefused, lambda: assert_no_card_data({"note": "pay 4111 1111 1111 1111 ok"}),
            "Luhn-valid card number under a harmless key refused")
    refused(CardDataRefused, lambda: assert_no_card_data({"items": ["4111-1111-1111-1111"]}),
            "card number inside a list refused")
    ok(assert_no_card_data({"note": "order 4111111111111112"}) is None,
       "digit run failing Luhn allowed")

    # 3 — explicit scope only
    refused(SpecError, lambda: FrameScope("", "frame_1"), "empty tab_id refused")
    refused(SpecError, lambda: OrderComponentExecutor(_FakeDriver([]), "tab_1",
                                                      ComponentFamily("f", 2, False)),
            "non-FrameScope refused")

    # 4 — targeting: real ids, no first-match
    catalog = [{"component_id": "chk_real_1", "kind": "checkout"},
               {"component_id": "form_real_9", "kind": "order_form"}]
    driver = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex = OrderComponentExecutor(driver, scope, ComponentFamily("checkout_v2", 2, False))
    ok(ex.resolve_component("chk_real_1")["kind"] == "checkout", "unique real id resolves")
    refused(ComponentNotFound, lambda: ex.resolve_component("chk_missing"),
            "missing component id refused")
    refused(SpecError, lambda: ex.resolve_component("form_real_9", "checkout"),
            "wrong component kind refused")
    ok(ex.find_component("checkout") == "chk_real_1",
       "kind lookup resolves the one checkout component")
    refused(ComponentNotFound, lambda: ex.find_component("lead_capture"),
            "an absent component kind is refused")
    dup = _FakeDriver(catalog + [{"component_id": "chk_real_1", "kind": "checkout"}])
    ex_dup = OrderComponentExecutor(dup, scope, ComponentFamily("checkout_v2", 2, False))
    refused(AmbiguousTarget, lambda: ex_dup.resolve_component("chk_real_1"),
            "duplicate component id refused, never first-match")
    refused(AmbiguousTarget, lambda: ex_dup.find_component("checkout"),
            "duplicate component kind refused, never first-match")

    # 5 — bind real price to real checkout component id, verified by read-back
    rec = ex.bind_main_price("chk_real_1", _price())
    ok(rec.state == "bound-verified", "bind claims bound-verified")
    ok(rec.op.readback == "verified" and rec.op.target == "chk_real_1",
      "op record names real target + verified readback")
    ok(driver.states["chk_real_1"]["main_price"]["native_price_id"] == "price_1",
      "real price id persisted on real component id")
    refused(SpecError, lambda: ex.bind_main_price("chk_real_1", ref.as_fields()),
            "raw mapping refused by bind (must be PriceRef)")

    # 6 — read-back drift is refused and never claimed bound
    drift = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    drift.drift["chk_real_1"] = {
        "main_price": {**ref.as_fields(), "native_price_id": "price_EVIL"}}
    ex_drift = OrderComponentExecutor(drift, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_drift.bind_main_price("chk_real_1", _price()),
            "drifted main price readback refused")
    ok(ex_drift.ops[-1].readback == "mismatch-refused", "mismatch recorded, not verified")

    # 7 — bump attach: unselected, family limits, accurate terms
    bump = BumpAttach("offer_a", "Headline", "Because reasons", _price("prod_2", "price_2", 900))
    rec = ex.attach_bump("chk_real_1", bump)
    ok(rec.state == "bound-verified", "bump attach verified")
    stored_bumps = driver.states["chk_real_1"]["bumps"]
    ok(stored_bumps[0]["selected"] is False, "bump attached UNSELECTED (never preselected)")
    ok(stored_bumps[0]["price"]["native_price_id"] == "price_2", "bump carries real price id")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_a", "H", "B", _price("prod_3", "price_3", 500))),
        "duplicate offer_id refused")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_2", "price_2", 900))),
        "duplicate native price refused (never charge twice)")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_3", "price_3", 500, "EUR"))),
        "bump currency mismatch refused")
    refused(SpecError, lambda: BumpAttach("offer_b", "H", "B",
                                          _price("prod_3", "price_3", 500, billing="recurring",
                                                 interval="month")),
            "recurring bump without disclosure refused")
    refused(UnsupportedState, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B",
                                 _price("prod_3", "price_3", 500, billing="recurring",
                                        interval="month", trial=None),
                                 disclosure_text="Recurring terms")),
            "recurring bump on non-recurring family refused")
    ex1 = OrderComponentExecutor(_FakeDriver(
        catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}}),
        scope, ComponentFamily("checkout_v1", 1, False))
    ex1.attach_bump("chk_real_1", bump)
    refused(UnsupportedState, lambda: ex1.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_3", "price_3", 500))),
        "family max_bumps=1 second attach refused")
    ok(OrderComponentExecutor(_FakeDriver(catalog), scope,
                              ComponentFamily("checkout_v2", 2, False))._family.max_bumps == 2,
       "family limits taken as declared (never invented)")

    # 8 — a component that attaches preselected is refused
    pre = _PreselectDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex_pre = OrderComponentExecutor(pre, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_pre.attach_bump("chk_real_1", bump),
            "preselected bump readback refused (no silent extra purchase)")

    # 9 — explicit selection state, read back
    rec = ex.set_bump_selected("chk_real_1", "offer_a", True)
    ok(rec.state == "bound-verified", "explicit select verified")
    ok(driver.states["chk_real_1"]["bumps"][0]["selected"] is True, "selection state persisted")
    refused(SpecError, lambda: ex.set_bump_selected("chk_real_1", "offer_zzz", True),
            "unknown offer select refused")
    refused(SpecError, lambda: ex.set_bump_selected("chk_real_1", "offer_a", "yes"),
            "non-boolean selection refused")
    flip = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [bump.as_fields()]}})
    ex_flip = OrderComponentExecutor(flip, scope, ComponentFamily("checkout_v2", 2, False))
    flip.drift["chk_real_1"] = {"bumps": [bump.as_fields()]}
    refused(ReadbackMismatch, lambda: ex_flip.set_bump_selected("chk_real_1", "offer_a", True),
            "selection readback drift refused")

    # 10 — Required/Hidden set AND read back; blind toggle impossible
    rec = ex.set_field_state("chk_real_1", "email", required=True, hidden=False)
    ok(rec.state == "bound-verified", "field state set+readback verified")
    ok(driver.states["chk_real_1"]["field_states"]["email"] == {"required": True, "hidden": False},
       "explicit true/false persisted for both states")
    refused(SpecError, lambda: ex.set_field_state("chk_real_1", "email"),
            "no requested state refused (blind toggle impossible)")
    refused(SpecError, lambda: ex.set_field_state("chk_real_1", "email", required="true"),
            "non-boolean required refused")
    hid = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex_hid = OrderComponentExecutor(hid, scope, ComponentFamily("checkout_v2", 2, False))
    hid.drift["chk_real_1"] = {"field_states": {"email": {"required": False, "hidden": False}}}
    refused(ReadbackMismatch,
            lambda: ex_hid.set_field_state("chk_real_1", "email", required=True),
            "field state readback drift refused")

    # 10b — the configured purchase action is set AND read back
    rec = ex.set_action("chk_real_1", "accept", "step_next")
    ok(rec.state == "bound-verified", "purchase action configured and read back")
    ok(driver.states["chk_real_1"]["action"] ==
       {"kind": "accept", "target_step_id": "step_next"},
       "action target persisted on the real component")
    act_drift = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": []}})
    ex_act = OrderComponentExecutor(act_drift, scope,
                                    ComponentFamily("checkout_v2", 2, False))
    act_drift.drift["chk_real_1"] = {
        "action": {"kind": "accept", "target_step_id": "step_wrong"}}
    refused(ReadbackMismatch,
            lambda: ex_act.set_action("chk_real_1", "accept", "step_next"),
            "action readback drift refused")

    # 11 — native totals: the platform's OWN full breakdown reconciles
    totals = ex.read_native_totals("chk_real_1")
    ok(totals["total_minor"] == 4900 + 900 and totals["subtotal_minor"] == 5800
       and totals["currency"] == "USD", "totals = main + selected bump, minor units")
    ok(totals["line_items"] == (("main", 4900), ("offer_a", 900)), "native line items exact")
    ok(totals["tax_minor"] == 0 and totals["shipping_minor"] == 0
       and totals["discount_total_minor"] == 0,
       "breakdown components are read from the platform, not assumed")
    priced = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [],
        "quote_discounts": [{"code": "BLACKFRIDAY", "amount_minor": 500}],
        "quote_tax_minor": 300, "quote_shipping_minor": 700}})
    ex_priced = OrderComponentExecutor(priced, scope, ComponentFamily("checkout_v2", 2, False))
    tb = ex_priced.read_native_totals("chk_real_1")
    ok(tb["subtotal_minor"] == 4900 and tb["discount_total_minor"] == 500
       and tb["tax_minor"] == 300 and tb["shipping_minor"] == 700
       and tb["total_minor"] == 4900 - 500 + 300 + 700,
       "discount + tax + shipping reconcile to the platform total")
    ex.set_bump_selected("chk_real_1", "offer_a", False)
    ok(ex.read_native_totals("chk_real_1")["total_minor"] == 4900,
       "deselect removes the bump line (native add/remove)")
    tot_drift = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [],
        "native_totals": {"currency": "USD", "subtotal_minor": 4900,
                          "discounts": [], "tax_minor": 0,
                          "shipping_minor": 0, "total_minor": 1}}})
    ex_tot = OrderComponentExecutor(tot_drift, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_tot.read_native_totals("chk_real_1"),
            "a platform total that does not reconcile is refused")
    tot_partial = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [],
        "native_totals": {"currency": "USD", "subtotal_minor": 4900,
                          "discounts": [], "total_minor": 4900}}})
    ex_partial = OrderComponentExecutor(tot_partial, scope, ComponentFamily("checkout_v2", 2, False))
    refused(UnsupportedState, lambda: ex_partial.read_native_totals("chk_real_1"),
            "an omitted tax/shipping component is unsupported, never zero")
    tot_currency = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [],
        "native_totals": {"currency": "EUR", "subtotal_minor": 4900,
                          "discounts": [], "tax_minor": 0,
                          "shipping_minor": 0, "total_minor": 4900}}})
    ex_cur = OrderComponentExecutor(tot_currency, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_cur.read_native_totals("chk_real_1"),
            "quote currency mismatch refused")
    refused(SpecError, lambda: ex.read_native_totals("chk_real_1", 0), "quantity 0 refused")

    # 12 — W8D ComponentIO interop (products_prices.bind_price_to_checkout seam)
    io = CheckoutComponentIO(ex)
    ok(io.get_checkout_price("chk_real_1") == ref.as_fields(),
       "ComponentIO get returns the real bound price fields")
    ok(io.get_checkout_price("chk_absent") is None, "ComponentIO get on unknown id returns None")
    io.set_checkout_price("chk_real_1", _price("prod_1", "price_9", 7700).as_fields())
    observed = io.get_checkout_price("chk_real_1")
    # exact comparison loop W8D runs after set_checkout_price:
    want = _price("prod_1", "price_9", 7700).as_fields()
    ok(isinstance(observed, Mapping) and all(observed.get(k) == v for k, v in want.items()),
       "W8D bind comparison loop passes against real component state")
    io_drift = CheckoutComponentIO(OrderComponentExecutor(
        _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields()}}), scope,
        ComponentFamily("checkout_v2", 2, False)))
    io_drift._ex._driver.drift["chk_real_1"] = {
        "main_price": {**want, "amount_minor": 1}}
    got = io_drift.get_checkout_price("chk_real_1")
    drift_caught = not all(got.get(k) == v for k, v in want.items())
    ok(drift_caught, "W8D bind comparison loop catches component drift")

    # 13 — every executed operation is recorded
    ok(all(op.readback in ("verified", "mismatch-refused", "not-attempted")
           for op in ex.ops), "op readback vocabulary honored")
    ok(any(op.readback == "mismatch-refused" for op in ex_drift.ops),
       "refusals recorded, not silently dropped")

    # 14 — the concrete driver installs + replays the managed editor adapter
    replay = _ReplayRunner(RECORDED_BIND)
    bridge = ManagedEditorBridge(_FIXTURE_ADAPTER_CAPTURE,
                                 location_id="LOC_TEST", page_id="page_1")
    driver = BrowserManagerDriver(replay, bridge=bridge)
    ex_rec = OrderComponentExecutor(driver, scope,
                                    ComponentFamily("checkout_v2", 2, False))
    rec = ex_rec.bind_main_price("chk_real_1", _price())
    ok(rec.state == "bound-verified" and replay.calls == len(RECORDED_BIND),
       "managed adapter replays the recording and bind is read-back verified")
    ok(replay.installs == 1, "the page adapter is installed exactly once")
    install_js = bridge.install_js()
    ok("window.__ocOrderComponents=" in install_js
       and _FIXTURE_ADAPTER_CAPTURE["page_read"]["path"] in install_js
       and _FIXTURE_ADAPTER_CAPTURE["autosave"]["path"] in install_js,
       "the adapter is generated from the captured routes, not an empty global")
    ok("await f(" in bridge.request_js({"op": "list_components"}),
       "requests call the installed adapter")
    refused(AdapterUnavailable,
            lambda: BrowserManagerDriver(lambda argv: json.dumps({"ok": True})
                                        ).list_components(scope),
            "no bound adapter is capability incomplete, never done")
    refused(AdapterUnavailable,
            lambda: ManagedEditorBridge({**_FIXTURE_ADAPTER_CAPTURE, "page_read": {}},
                                        location_id="LOC_TEST", page_id="page_1"),
            "a capture without the page route is refused")
    refused(AdapterUnavailable,
            lambda: load_managed_adapter_capture("/nonexistent/capture.json"),
            "an absent capture file is capability incomplete")
    refused(OrderComponentError,
            lambda: BrowserManagerDriver(
                lambda argv: "<html>", bridge=bridge, installed=True
            ).get_state(scope, "chk_real_1"),
            "non-JSON reply refused")
    refused(AmbiguousTarget,
            lambda: BrowserManagerDriver(
                lambda argv: json.dumps({"ok": False, "error": "ambiguous"}),
                bridge=bridge, installed=True).get_state(scope, "chk_real_1"),
            "adapter-reported duplicate ids refused")
    refused(ComponentNotFound,
            lambda: BrowserManagerDriver(
                lambda argv: json.dumps({"ok": False, "error": "component-not-found"}),
                bridge=bridge, installed=True).get_state(scope, "chk_missing"),
            "an absent component id is not-found, never an empty state")
    refused(CardDataRefused,
            lambda: BrowserManagerDriver(
                _ReplayRunner([]), bridge=bridge, installed=True
            ).set_state(scope, "chk_real_1", {"note": "4111111111111111"}),
            "driver refuses card data before any call")

    # 15 — approved billing terms carried verbatim; never flattened
    monthly = price_ref_from_terms(
        {"billing_type": "recurring", "recurring_interval": "month"},
        native_product_id="prod_1", native_price_id="price_m",
        amount_minor=2700, currency="USD")
    ok(monthly.billing_type == "recurring" and monthly.recurring_interval == "month",
       "recurring terms carried verbatim")
    trial = price_ref_from_terms(
        {"billing_type": "trial_then_recurring", "recurring_interval": "week",
         "trial_days": 7},
        native_product_id="prod_1", native_price_id="price_t",
        amount_minor=1900, currency="USD")
    ok(trial.trial_days == 7 and trial.recurring_interval == "week",
       "trial-then-recurring terms carried verbatim")
    refused(SpecError, lambda: price_ref_from_terms(
        {"billing_type": "installment", "installment_count": 3},
        native_product_id="prod_1", native_price_id="price_i",
        amount_minor=3000, currency="USD"),
        "installment is refused, never flattened")
    refused(SpecError, lambda: price_ref_from_terms(
        {}, native_product_id="prod_1", native_price_id="price_x",
        amount_minor=100, currency="USD"),
        "an absent billing_type is never assumed one_time")
    refused(SpecError, lambda: price_ref_from_terms(
        {"billing_type": "recurring"}, native_product_id="prod_1",
        native_price_id="price_y", amount_minor=100, currency="USD"),
        "recurring without an interval refused")

    print(f"OK order_components self-check: {checks} assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
