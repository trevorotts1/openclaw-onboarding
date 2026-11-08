#!/usr/bin/env python3
"""S80 production page builder for the Upsell 1, Downsell 1 and Upsell 2 slots.

WHAT THIS IS
------------
`render_pages.py` next door is the TEST ONLY local renderer: three fixture
bundles, neutral styling, no brand, no native ids, refuses without
``--test-only``. It stays exactly as it is (L2 local rendered proof).

This module is the PRODUCTION constructor. It builds the three extra-offer
pages - U1 (``upsell_1``), D1 (``downsell_1``) and U2 (``upsell_2``) - as full
publishable HTML documents, and it refuses to build anything it cannot bind.

ONE APPROVED ROUTE GRAPH
------------------------
Every route on every page is READ from the approved route graph compiled by
Skill 49 (``49-signature-funnel/scripts/compile_launch_route.py``). This
module never plans a route: it validates the graph (dangling edges, duplicate
edges, unguarded paid edges, missing commerce edges) and reads the paid /
explicit-decline target of each offer slot. The same graph is what
``ghl_order_elements.build_order_plan`` reads for the native buttons and what
the workflow delivery consumes, so all three agree by construction.

DISTINCT SLOT IDENTITY
----------------------
Each slot gets its own page (its own route-graph page id) and its own offer
binding from the approved launch record's ``offers[].slot``. Two upsells can
never share a key: the page files, the manifest entries, the button markup and
the route links are all keyed by slot.

NATIVE PURCHASE ACTIONS ONLY
----------------------------
Every purchase CTA is a ``<button>`` carrying the native one-click action
bound to the slot's verified ``native_product_id`` / ``native_price_id`` in
the native payment session. It has NO href and does not navigate. A link that
navigates to a thank-you page is not a purchase action and is refused. The
explicit-decline control is the only navigation on the page; it carries
``data-charges="false"`` and points at the graph's decline edge.

PENDING/FAILED IS NOT DECLINE
-----------------------------
The pages carry the state behaviour on the page (``data-disabled-states``)
and each state's approved banner copy in the manifest. A failed or pending
payment never renders as a decline and never routes anywhere.

Routes implemented (from the graph, stated for the reader):
  main paid -> U1; U1 paid -> U2; U1 declined -> D1; D1 paid -> the SAME U2;
  D1 declined -> thank-you; U2 paid or declined -> thank-you.

USAGE
-----
  python3 build_production_pages.py \
      --launch <approved-launch-record.json> \
      --route-graph <approved-route-graph.json> \
      --checkout-family order_upsell_v2_funnel \
      --copy upsell_1=<copy.json> --copy upsell_2=<copy.json> \
      --downsell-page <d1-page.json> \
      --brand <brand-tokens.json> \
      --out-dir <dir>

Only the slots the launch record enables are built. Missing native ids, a
missing page for an enabled slot, diverging CTA refs, or an unsupported
billing term each fail closed with a named error and write nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The production pages keep the SAME design contract as the local renders:
# one stylesheet and one set of state banners, imported rather than copied so
# the two can never drift.
from render_pages import CSS, CTA_DISABLED_STATES, STATE_BANNERS  # noqa: E402

SLOT_U1 = "upsell_1"
SLOT_D1 = "downsell_1"
SLOT_U2 = "upsell_2"
EXTRA_SLOTS = (SLOT_U1, SLOT_D1, SLOT_U2)

CHECKOUT_FAMILIES = {
    "order_upsell_v2_funnel": {
        "surface": "form_v2_funnel_same_domain",
        "native_element": "order_upsell_forms_step",
    },
    "store_upsell_website": {
        "surface": "website_page",
        "native_element": "native_upsell_element",
    },
}

PAID_GUARD_PREFIX = "verified_"
DECLINE_GUARD = "no_charge_decline"
PENDING_BEHAVIOR = ("retain_current_purchase_state_until_resolved_or_"
                    "explicit_decline")

NATIVE_PURCHASE = "one_click_purchase"
NATIVE_SESSION = "native"

# Currencies whose minor unit is 2 decimals, and the zero-decimal set. A
# currency outside both is refused rather than printed with a guessed
# exponent (same discipline as 82's renderer).
_TWO_DECIMAL = set(
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BMD BND BOB BRL "
    "BSD BTN BWP BYN BZD CAD CDF CHF CNY COP CRC CUP CVE CZK DKK DOP DZD EGP "
    "ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GTQ GYD HKD HNL HTG HUF IDR ILS "
    "INR IRR JMD KES KGS KHR KPW KYD KZT LAK LBP LKR LRD LSL MAD MDL MGA MKD "
    "MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD PAB PEN "
    "PGK PHP PKR PLN QAR RON RSD RUB SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD "
    "SSP STN SVC SYP SZL THB TJS TMT TOP TRY TTD TWD TZS UAH USD UYU UZS VES "
    "WST XCD YER ZAR ZMW ZWL".split())
_ZERO_DECIMAL = set(
    "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF".split())
_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


class PageBuildError(RuntimeError):
    """The page cannot be built honestly. Never a warning: nothing is written."""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ── approved route graph (read-only) ─────────────────────────────────────────

def read_route_graph(graph: dict) -> dict:
    """READ the approved graph. Returns ``{role: {page_id, accept, decline}}``.

    A reader, never a planner: every value returned is a value the graph
    carries. Refuses dangling edges, a repeated page id or role, duplicate
    commerce edges, unguarded paid edges, and a slot without both a paid and
    an explicit-decline edge.
    """
    if not isinstance(graph, dict):
        raise PageBuildError("route graph is not an object")
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise PageBuildError("route graph carries no nodes")
    if not isinstance(edges, list):
        raise PageBuildError("route graph carries no edges")
    role_of = {}
    by_role = {}
    for node in nodes:
        pid = str(node.get("page_id") or "").strip()
        role = str(node.get("role") or "").strip()
        if not pid or not role:
            raise PageBuildError(f"route graph node is incomplete: {node!r}")
        if pid in role_of:
            raise PageBuildError(f"route graph repeats page id {pid!r}")
        if role in by_role:
            raise PageBuildError(f"route graph repeats role {role!r}")
        role_of[pid] = role
        by_role[role] = {"page_id": pid, "accept": None, "decline": None}
    for edge in edges:
        frm, to = edge.get("from"), edge.get("to")
        if frm not in role_of or to not in role_of:
            raise PageBuildError(f"route graph edge is dangling: {edge!r}")
        event, guard = edge.get("event"), edge.get("guard")
        if event not in ("payment_succeeded", "explicit_decline"):
            continue  # entry edges are other pages' business
        role = role_of[frm]
        key = "accept" if event == "payment_succeeded" else "decline"
        if by_role[role][key] is not None:
            raise PageBuildError(
                f"route graph carries a second {event} edge from {role!r}")
        if not isinstance(guard, str) or not guard.strip():
            raise PageBuildError(f"route graph edge {edge!r} names no guard")
        if key == "accept" and not guard.startswith(PAID_GUARD_PREFIX):
            raise PageBuildError(
                f"paid edge from {role!r} carries guard {guard!r}; a paid "
                "route needs a verified_* guard")
        if key == "decline" and guard != DECLINE_GUARD:
            raise PageBuildError(
                f"decline edge from {role!r} carries guard {guard!r}; a "
                f"decline route must be {DECLINE_GUARD!r}")
        by_role[role][key] = {"event": event, "target_role": role_of[to],
                              "target_page_id": to, "guard": guard}
    for slot_role in EXTRA_SLOTS:
        route = by_role.get(slot_role)
        if route and not (route["accept"] and route["decline"]):
            raise PageBuildError(
                f"route graph has {slot_role!r} without both a paid and an "
                "explicit-decline edge")
    return by_role


def graph_hash(graph: dict) -> str:
    """The route-graph hash of record: the same serialization Skill 49's
    compiler uses, so it equals the launch record's ``route_graph_hash``."""
    return hashlib.sha256(
        (json.dumps(graph, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    ).hexdigest()


# ── approved launch record offers ───────────────────────────────────────────

def offers_by_slot(launch: dict) -> dict:
    """``offers[]`` from the approved launch record, keyed by slot.

    A missing native product/price is a refusal, never a placeholder: the
    page's purchase button charges exactly these ids.
    """
    offers = launch.get("offers") if isinstance(launch, dict) else None
    if not isinstance(offers, list) or not offers:
        raise PageBuildError("launch record carries no offers")
    out = {}
    for offer in offers:
        slot = str(offer.get("slot") or "").strip()
        if not slot:
            raise PageBuildError(f"offer carries no slot: {offer!r}")
        if slot in out:
            raise PageBuildError(f"launch record repeats slot {slot!r}")
        prices = offer.get("prices") or []
        price = prices[0] if prices else {}
        out[slot] = {
            "display_name": offer.get("display_name"),
            "native_product_id": str(offer.get("native_product_id") or ""),
            "native_price_id": str(price.get("native_price_id") or ""),
            "amount_minor": price.get("amount_minor"),
            "currency": str(price.get("currency") or ""),
            "billing_type": price.get("billing_type") or "one_time",
            "schedule": price.get("schedule") or [],
            "test_only": bool(offer.get("test_only")),
        }
    return out


def _format_amount(amount_minor, currency: str) -> str:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) \
            or amount_minor < 0:
        raise PageBuildError(f"amount_minor is not a non-negative integer: "
                             f"{amount_minor!r}")
    if currency in _ZERO_DECIMAL:
        exponent = 0
    elif currency in _TWO_DECIMAL:
        exponent = 2
    else:
        raise PageBuildError(
            f"currency {currency!r} has no supported minor-unit exponent for "
            "a disclosure; refusing to guess one")
    whole, frac = divmod(amount_minor, 10 ** exponent)
    major = f"{whole:,}.{frac:0{exponent}d}" if exponent else f"{whole:,}"
    symbol = _CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{major}" if symbol else f"{currency} {major}"


def disclosure_for(slot: str, offer: dict) -> str:
    """The exact-terms sentence rendered adjacent to every purchase CTA.

    Built ONLY from the approved launch record's verified price fields. A
    term the builder cannot state exactly (installments, an unlabelled
    recurring price) is refused, never flattened.
    """
    amount = _format_amount(offer.get("amount_minor"), offer.get("currency"))
    billing = offer.get("billing_type")
    if billing in ("installment", "installments"):
        raise PageBuildError(
            f"{slot}: installment billing has no native price shape on this "
            "surface; refusing to flatten it into one charge")
    if billing == "one_time":
        return (f"One-time charge of {amount}, charged to your original "
                "payment method when you accept. No further charges for "
                "this offer.")
    schedule = [e for e in offer.get("schedule") or [] if isinstance(e, dict)]
    if not schedule:
        raise PageBuildError(
            f"{slot}: {billing} price carries no schedule, so the full "
            "obligation cannot be disclosed")
    terms = "; ".join(
        str(e.get("due") or e.get("label") or "")
        + (f" at {_format_amount(e.get('amount_minor'), offer.get('currency'))}"
           if isinstance(e.get("amount_minor"), int)
           and e.get("amount_minor") != offer.get("amount_minor") else "")
        for e in schedule)
    if billing == "trial_then_recurring":
        return (f"{amount} today, then {terms}. Charged to your original "
                "payment method when you accept. Cancel before a renewal to "
                "stop future charges.")
    if billing == "recurring":
        return (f"Recurring charge of {amount} — {terms}. Charged to your "
                "original payment method when you accept; cancel before a "
                "renewal to stop future charges.")
    raise PageBuildError(f"{slot}: billing_type {billing!r} is not a native "
                         "term this page can disclose exactly")


# ── copy documents ──────────────────────────────────────────────────────────

def _require_identical_cta(slot: str, refs, expected_ref):
    distinct = sorted({r for r in refs if r})
    if len(distinct) != 1:
        raise PageBuildError(
            f"{slot}: the page's CTAs name {distinct}; exactly one guarded "
            "native action per page is required")
    if expected_ref and distinct[0] != expected_ref:
        raise PageBuildError(
            f"{slot}: CTA action ref {distinct[0]!r} is not the page's "
            f"declared action ref {expected_ref!r}")


def sections_from_upsell_copy(slot: str, doc: dict) -> list:
    """Normalize Skill 80's eight-section copy document."""
    sections = doc.get("sections")
    if not isinstance(sections, list) or len(sections) != 8:
        raise PageBuildError(f"{slot}: the copy document must carry exactly "
                             f"8 sections, got {len(sections or [])}")
    _require_identical_cta(
        slot, [((s.get("cta") or {}).get("action_ref")) for s in sections],
        doc.get("accept_action_ref"))
    out = []
    for index, section in enumerate(sections, 1):
        if section.get("number") != index:
            raise PageBuildError(
                f"{slot}: section {section.get('number')!r} is out of order")
        cta = section.get("cta") or {}
        if cta.get("href") or section.get("href"):
            raise PageBuildError(
                f"{slot}: section {index} carries a navigating href as its "
                "purchase control; a purchase action is native")
        out.append({
            "number": index,
            "key": section.get("key") or f"section_{index}",
            "heading": section.get("heading"),
            "body": section.get("body"),
            "bullets": section.get("bullets") or [],
            "reasons": section.get("reasons") or [],
            "cta_text": cta.get("text"),
        })
    return out


def sections_from_downsell_page(slot: str, page: dict) -> list:
    """Normalize Skill 81's D1 page document (role-keyed sections)."""
    sections = page.get("sections")
    if not isinstance(sections, list) or len(sections) != 8:
        raise PageBuildError(f"{slot}: the D1 page must carry exactly 8 "
                             f"sections, got {len(sections or [])}")
    _require_identical_cta(
        slot, [((s.get("cta") or {}).get("action_ref")) for s in sections],
        "native-d1-action")
    closing = sections[-1]
    if closing.get("heading") != "When Time Runs Out" \
            or len(closing.get("missed_out_items") or []) != 7:
        raise PageBuildError(
            f"{slot}: the closing section must be 'When Time Runs Out' with "
            "exactly 7 missed-out items")
    out = []
    for index, section in enumerate(sections, 1):
        cta = section.get("cta") or {}
        if cta.get("href") or section.get("href"):
            raise PageBuildError(
                f"{slot}: section {index} carries a navigating href as its "
                "purchase control; a purchase action is native")
        bullets = section.get("missed_out_items") or []
        out.append({
            "number": index,
            "key": section.get("role") or f"section_{index}",
            "heading": section.get("heading"),
            "body": section.get("body"),
            "bullets": bullets,
            "reasons": [] if bullets else [],
            "cta_text": cta.get("label"),
        })
    return out


# ── page rendering ──────────────────────────────────────────────────────────

def _brand_block(brand: dict) -> tuple:
    colors = (brand or {}).get("colors") or {}
    name = (brand or {}).get("brand_name") or (brand or {}).get("name") or ""
    return name, colors


def _brand_css(colors: dict) -> str:
    def token(key, default):
        value = colors.get(key) if isinstance(colors, dict) else None
        if isinstance(value, str) and value.strip() and len(value) <= 40 \
                and ";" not in value and "}" not in value:
            return value.strip()
        return default

    return (":root{--ink:%s;--paper:%s;--tint:%s;--accent:%s}"
            % (token("text", "#212631"), token("background", "#fffdf8"),
               token("tint", "#eef3fd"), token("primary", "#2456c8")))


def _cta_html(slot: str, copy_doc: dict, section: dict, offer: dict,
              family: str, disclosure: str, primary: bool) -> str:
    attrs = (
        ' type="button" class="cta%s"'
        ' data-native-action="%s"'
        ' data-native-element="%s"'
        ' data-page-id="%s"'
        ' data-slot="%s"'
        ' data-product-id="%s"'
        ' data-price-id="%s"'
        ' data-payment-session="%s"'
        ' data-action-ref="%s"'
    ) % (
        " primary" if primary else "",
        NATIVE_PURCHASE,
        _esc(CHECKOUT_FAMILIES[family]["native_element"]),
        _esc(copy_doc["page_id"]),
        _esc(slot),
        _esc(offer["native_product_id"]),
        _esc(offer["native_price_id"]),
        NATIVE_SESSION,
        _esc(copy_doc["action_ref"]),
    )
    if primary:
        attrs += ' id="primary-cta"'
    return (
        '<div class="cta-block"><button%s>%s</button>'
        '<p class="disclosure">%s</p></div>'
        % (attrs, _esc(section["cta_text"]), _esc(disclosure))
    )


def render_page(slot: str, copy_doc: dict, route: dict, offer: dict,
                brand: dict, family: str, acknowledgement: str,
                test_only: bool) -> str:
    """One publishable page for one slot."""
    disclosure = disclosure_for(slot, offer)
    is_d1 = slot == SLOT_D1
    title = "%s" % (copy_doc.get("offer_name") or offer["display_name"] or slot)
    disabled = " ".join(sorted(CTA_DISABLED_STATES))
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',
        "<title>%s</title>" % _esc(title),
        "<style>%s%s</style>" % (CSS, _brand_css(brand.get("colors"))),
        "</head>",
        "<body data-page-id=\"%s\" data-slot=\"%s\" data-checkout-family=\"%s\" "
        "data-disabled-states=\"%s\">"
        % (_esc(copy_doc["page_id"]), _esc(slot), _esc(family), _esc(disabled)),
        "<main>",
    ]
    if test_only:
        # A test-location page must never be mistaken for a live one.
        parts.append(
            '<div class="test-banner">TEST LOCATION - this page was built '
            "from a launch record marked test_only and is not live.</div>")
    brand_name, _ = _brand_block(brand)
    if brand_name:
        parts.append('<p class="entry-tag">%s</p>' % _esc(brand_name))
    if acknowledgement:
        parts.append('<div class="ack" data-ack="%s">%s</div>'
                     % (_esc(slot), _esc(acknowledgement)))
    for section in copy_doc["sections"]:
        number = section["number"]
        classes = []
        if number == 1:
            classes.append("hero")
        if number % 2 == 0:
            classes.append("alt")
        parts.append(
            '<section data-section-number="%d" data-section-key="%s" '
            'class="%s">'
            % (number, _esc(section["key"]), " ".join(classes)))
        parts.append('<p class="entry-tag">%s - section %d of 8</p>'
                     % ("Required alternative" if is_d1 else "Optional extra",
                        number))
        parts.append("<h2>%s</h2>" % _esc(section["heading"]))
        parts.append("<p>%s</p>" % _esc(section["body"]))
        if section.get("bullets"):
            parts.append("<ul>")
            parts.extend("<li>%s</li>" % _esc(b) for b in section["bullets"])
            parts.append("</ul>")
        if section.get("reasons"):
            parts.append('<ol class="reasons">')
            parts.extend("<li>%s</li>" % _esc(r) for r in section["reasons"])
            parts.append("</ol>")
        parts.append(_cta_html(slot, copy_doc, section, offer, family,
                               disclosure, primary=(number == 1)))
        parts.append("</section>")
    decline = route["decline"]
    parts.append("<footer>")
    parts.append(
        '<a class="decline" href="#route-%s" data-route-event="%s" '
        'data-route-guard="%s" data-route-page-id="%s" data-charges="false">'
        "%s</a>"
        % (_esc(decline["target_page_id"]), _esc(decline["event"]),
           _esc(decline["guard"]), _esc(decline["target_page_id"]),
           _esc("No thanks - continue with my current order" if is_d1
                else "No thanks - continue without this extra")))
    parts.append(
        '<p class="disclosure">Choosing no thanks never charges you. '
        "Your original purchase stays complete either way.</p>")
    parts.append("</footer>")
    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


# ── build ───────────────────────────────────────────────────────────────────

def build(launch: dict, graph: dict, family: str, copies: dict,
          downsell_page: dict, brand: dict) -> dict:
    """Build every enabled extra slot. Returns ``{pages, manifest}``; writes
    nothing (the CLI writes)."""
    if family not in CHECKOUT_FAMILIES:
        raise PageBuildError(
            f"checkout_family {family!r} is not one of "
            f"{sorted(CHECKOUT_FAMILIES)}")
    extras = launch.get("extras") or {}
    enabled = [s for s in EXTRA_SLOTS if extras.get(s) is True]
    if not enabled:
        raise PageBuildError("the launch record enables no extra offer")
    routes = read_route_graph(graph)
    recorded = launch.get("route_graph_hash")
    if recorded and recorded != graph_hash(graph):
        raise PageBuildError(
            "the route graph is not the one the approved launch record binds: "
            f"graph hash {graph_hash(graph)} != recorded {recorded}")
    for slot in EXTRA_SLOTS:
        if slot not in enabled and slot in routes:
            raise PageBuildError(
                f"the route graph carries {slot!r} but the launch record does "
                "not enable it; the graph is not this launch's graph")
    offers = offers_by_slot(launch)
    pages = {}
    manifest = []
    for slot in enabled:
        route = routes.get(slot)
        if not route:
            raise PageBuildError(
                f"{slot}: enabled in the launch record but absent from the "
                "approved route graph")
        offer = offers.get(slot) or {}
        if not offer.get("native_product_id") or not offer.get("native_price_id"):
            raise PageBuildError(
                f"{slot}: the approved launch record carries no native "
                "product/price for this slot; a page with no bindable "
                "purchase action is not built")
        if slot == SLOT_D1:
            page_doc = downsell_page.get("page") if "page" in downsell_page \
                else downsell_page
            sections = sections_from_downsell_page(slot, page_doc)
            offer_name = offer.get("display_name")
            action_ref = "native-d1-action"
            acknowledgement = (
                "Your original purchase is confirmed and stays complete. "
                "This is a different option from the one you just declined.")
        else:
            doc = copies.get(slot)
            if not isinstance(doc, dict):
                raise PageBuildError(f"{slot}: no copy document supplied")
            if doc.get("instance") != slot:
                raise PageBuildError(
                    f"{slot}: the copy document is for {doc.get('instance')!r}")
            sections = sections_from_upsell_copy(slot, doc)
            offer_name = doc.get("offer_name")
            action_ref = doc.get("accept_action_ref")
            acknowledgement = ""
            if slot == SLOT_U2:
                entry = launch.get("u2_entry_context")
                if entry == "from_upsell_1":
                    acknowledgement = (
                        "Your Upsell 1 purchase is confirmed (%s). This is the "
                        "next optional extra." % (
                            offers.get(SLOT_U1, {}).get("display_name")
                            or "your previous extra"))
                elif entry == "from_downsell_1":
                    acknowledgement = (
                        "Your alternative offer purchase is confirmed (%s). "
                        "This is the next optional extra." % (
                            offers.get(SLOT_D1, {}).get("display_name")
                            or "your alternative offer"))
                else:
                    raise PageBuildError(
                        "upsell_2: the launch record names no entry context "
                        "(from_upsell_1 or from_downsell_1); the page's "
                        "acknowledgement must be truthful on both paths")
        copy_doc = {
            "page_id": route["page_id"],
            "offer_name": offer_name,
            "action_ref": action_ref,
            "sections": sections,
        }
        html_text = render_page(slot, copy_doc, route, offer, brand, family,
                                acknowledgement,
                                bool(launch.get("test_only")))
        pages[slot] = html_text
        manifest.append({
            "slot": slot,
            "page_id": route["page_id"],
            "file": "%s.html" % slot,
            "sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            "native_product_id": offer["native_product_id"],
            "native_price_id": offer["native_price_id"],
            "payment_session": NATIVE_SESSION,
            "purchase_action": NATIVE_PURCHASE,
            "checkout_family": family,
            "native_element": CHECKOUT_FAMILIES[family]["native_element"],
            "disclosure": disclosure_for(slot, offer),
            "routes": {
                "on_payment_succeeded": route["accept"],
                "on_explicit_decline": route["decline"],
                "on_payment_failed": {
                    "is_decline": False, "is_acceptance": False,
                    "behaviour": PENDING_BEHAVIOR},
                "on_payment_pending": {
                    "is_decline": False, "is_acceptance": False,
                    "behaviour": PENDING_BEHAVIOR},
            },
            "disabled_states": sorted(CTA_DISABLED_STATES),
            "state_banners": {k: STATE_BANNERS[k] for k in STATE_BANNERS},
            "test_only": bool(launch.get("test_only")),
        })
    return {
        "pages": pages,
        "manifest": {
            "schema": "s80-production-pages/1",
            "launch_id": launch.get("launch_id"),
            "revision": launch.get("revision"),
            "route_graph_hash": graph_hash(graph),
            "checkout_family": family,
            "payment_recovery": {"behaviour": PENDING_BEHAVIOR,
                                 "is_decline": False, "is_acceptance": False},
            "pages": manifest,
        },
    }


def write_pages(out_dir: Path, built: dict) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for slot, text in built["pages"].items():
        target = out_dir / ("%s.html" % slot)
        target.write_text(text, encoding="utf-8")
        written.append(str(target))
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(built["manifest"], indent=2) + "\n", encoding="utf-8")
    written.append(str(manifest_path))
    return written


# ── self-check (no test framework) ──────────────────────────────────────────

def _repo_root() -> Path:
    """The directory that holds the numbered skill folders. Works in BOTH
    distributions: the onboarding tree (``<root>/49-signature-funnel``) and
    999 (``<root>/.claude/skills/49-signature-funnel``)."""
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents)[:8]:
        for prefix in (parent, parent / ".claude" / "skills"):
            if (prefix / "49-signature-funnel" / "scripts"
                    / "compile_launch_route.py").is_file():
                return prefix
    raise PageBuildError(
        "cannot locate the 49-signature-funnel skill from %s; the production "
        "builder needs the route-graph compiler" % here)


def _selftest(out_dir: Path) -> int:
    """Build the three slots from the shipped approved-shape fixtures. Uses
    the real Skill 49 compiler for the graph so the pages are proven against
    the compiler's own output, not a hand-written graph."""
    repo = _repo_root()
    sys.path.insert(0, str(repo / "49-signature-funnel" / "scripts"))
    import compile_launch_route as compiler  # noqa: E402

    launch = load_json(repo / "49-signature-funnel" / "scripts" / "fixtures"
                       / "finalized-launch-record-signature-launch-l4.json")
    launch["u2_entry_context"] = "from_upsell_1"
    graph = compiler.compile_route(launch)
    copies = {
        SLOT_U1: load_json(repo / "80-signature-upsell" / "components"
                           / "80-signature-upsell" / "fixtures"
                           / "copy-upsell1-public.valid.json"),
        SLOT_U2: load_json(repo / "80-signature-upsell" / "components"
                           / "80-signature-upsell" / "fixtures"
                           / "copy-upsell2-public.valid.json"),
    }
    downsell = load_json(repo / "81-signature-downsell" / "fixtures"
                         / "valid-downsell-page.json")
    brand = {"brand_name": "SELFTEST BRAND",
             "colors": {"primary": "#2456c8", "text": "#212631"}}
    built = build(launch, graph, "order_upsell_v2_funnel", copies, downsell,
                  brand)
    errors = []
    pages = built["manifest"]["pages"]
    slots = [p["slot"] for p in pages]
    if slots != [SLOT_U1, SLOT_D1, SLOT_U2]:
        errors.append(f"built slots wrong: {slots}")
    page_ids = [p["page_id"] for p in pages]
    if len(page_ids) != len(set(page_ids)):
        errors.append(f"page ids are not distinct: {page_ids}")
    by_slot = {p["slot"]: p for p in pages}
    if by_slot[SLOT_U1]["page_id"] != "signature-launch-l4-UPSELL_1" \
            or by_slot[SLOT_D1]["page_id"] != "signature-launch-l4-DOWNSELL_1" \
            or by_slot[SLOT_U2]["page_id"] != "signature-launch-l4-UPSELL_2":
        errors.append(f"page ids are not the graph's node ids: {page_ids}")
    for slot, page in by_slot.items():
        text = built["pages"][slot]
        for needed in ('data-native-action="one_click_purchase"',
                       'data-product-id="%s"' % page["native_product_id"],
                       'data-price-id="%s"' % page["native_price_id"],
                       'data-payment-session="native"'):
            if needed not in text:
                errors.append(f"{slot}: markup lacks {needed}")
        if 'data-slot="%s"' % slot not in text:
            errors.append(f"{slot}: markup does not carry its own slot")
        if 'href="https://' in text or '<a class="cta' in text:
            errors.append(f"{slot}: a purchase control navigates")
    if by_slot[SLOT_U1]["routes"]["on_payment_succeeded"]["target_role"] \
            != SLOT_U2:
        errors.append("U1 paid does not route to U2")
    if by_slot[SLOT_U1]["routes"]["on_explicit_decline"]["target_role"] \
            != SLOT_D1:
        errors.append("U1 decline does not route to D1")
    if by_slot[SLOT_D1]["routes"]["on_payment_succeeded"]["target_page_id"] \
            != by_slot[SLOT_U2]["page_id"]:
        errors.append("D1 paid does not route to the SAME U2")
    if by_slot[SLOT_U2]["routes"]["on_payment_succeeded"]["target_role"] \
            != "thank_you":
        errors.append("U2 paid does not route to thank-you")
    if 'data-charges="false"' not in built["pages"][SLOT_U1]:
        errors.append("the decline control does not declare no charge")
    if "Upsell 1 purchase is confirmed" not in built["pages"][SLOT_U2]:
        errors.append("U2 does not acknowledge the verified U1 purchase")
    # A second entry context is a different acknowledgement, same page.
    launch_d1 = dict(launch, u2_entry_context="from_downsell_1")
    built_d1 = build(launch_d1, graph, "order_upsell_v2_funnel", copies,
                     downsell, brand)
    d1_text = built_d1["pages"][SLOT_U2]
    if "Upsell 1 purchase is confirmed" in d1_text \
            or "alternative offer purchase is confirmed" not in d1_text:
        errors.append("U2 on the D1 path wrongly claims a U1 purchase")
    if built_d1["manifest"]["pages"][2]["page_id"] \
            != by_slot[SLOT_U2]["page_id"]:
        errors.append("U2 is not one canonical page across both entry paths")
    # Fail-closed probes.
    probes = [
        ("no route graph node",
         lambda: build(launch, {**graph, "nodes": [
             n for n in graph["nodes"] if n["role"] != SLOT_D1]},
             "order_upsell_v2_funnel", copies, downsell, brand)),
        ("no native price",
         lambda: build(launch, graph, "order_upsell_v2_funnel", copies,
                       downsell, brand)),
        ("wrong family",
         lambda: build(launch, graph, "not_a_family", copies, downsell,
                       brand)),
    ]
    try:
        probes[0][1]()
        errors.append("a missing route node was not refused")
    except PageBuildError:
        pass
    try:
        probes[2][1]()
        errors.append("an unknown checkout family was not refused")
    except PageBuildError:
        pass
    stripped = {**launch, "offers": [
        dict(o, native_product_id=None) if o["slot"] == SLOT_D1 else o
        for o in launch["offers"]]}
    try:
        build(stripped, graph, "order_upsell_v2_funnel", copies, downsell,
              brand)
        errors.append("a slot with no native product was not refused")
    except PageBuildError:
        pass
    try:
        build(dict(launch, u2_entry_context=None), graph,
              "order_upsell_v2_funnel", copies, downsell, brand)
        errors.append("U2 without an entry context was not refused")
    except PageBuildError:
        pass

    written = write_pages(out_dir, built)
    for path in written:
        if not Path(path).is_file():
            errors.append(f"missing output {path}")
    if errors:
        for e in errors:
            print("  FAIL: %s" % e, file=sys.stderr)
        print("[selftest] FAIL - %d error(s)" % len(errors), file=sys.stderr)
        return 1
    print("[selftest] PASS - %d production pages built (%s)"
          % (len(built["pages"]), ", ".join(written)))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--launch")
    parser.add_argument("--route-graph")
    parser.add_argument("--checkout-family", default="order_upsell_v2_funnel")
    parser.add_argument("--copy", action="append", default=[],
                        metavar="SLOT=PATH")
    parser.add_argument("--downsell-page")
    parser.add_argument("--brand")
    parser.add_argument("--out-dir")
    args = parser.parse_args(argv)

    if not args.out_dir:
        print("--out-dir is required (no temp directory is created)",
              file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    if args.selftest:
        return _selftest(out_dir)
    if not (args.launch and args.route_graph and args.downsell_page):
        print("--launch, --route-graph and --downsell-page are required",
              file=sys.stderr)
        return 2
    copies = {}
    for item in args.copy:
        slot, _, path = item.partition("=")
        if not path:
            print("--copy needs SLOT=PATH, got %r" % item, file=sys.stderr)
            return 2
        copies[slot] = load_json(path)
    try:
        built = build(load_json(args.launch), load_json(args.route_graph),
                      args.checkout_family, copies,
                      load_json(args.downsell_page),
                      load_json(args.brand) if args.brand else {})
    except PageBuildError as exc:
        print("FAIL-CLOSED: %s" % exc, file=sys.stderr)
        return 2
    for path in write_pages(out_dir, built):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
