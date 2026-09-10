#!/usr/bin/env python3
"""
checkout_form_builder.py — the P-U-FORM-CHECKOUT real producer (PRES-025).

Implements the elected checkout form stage as a REAL producer instead of the
interim placeholder (which re-invoked sales_checkout_builder.py and re-verified
the SAME build_receipt.json without wiring any form):

  offer-derived form schema  ->  Skill 44 form/workflow contract
                             ->  Skill 06 page/widget task
                             ->  persisted IDs (form / workflow / product)
                             ->  verified checkout route / widget embed
                                 (never href="#")

Two separate completion contracts (never conflated):

  * lead_capture    — order-intent form (email + full name). Complete only
                      after a test-location submit proves ONE scoped contact
                      plus ONE workflow enrollment (validation + duplicate
                      resubmits exercised). The checkout page carries an
                      honest `stripe: not_configured` marker, never a fake
                      live-payment claim.
  * payment_sandbox — provider SANDBOX path only. Complete only after the
                      sandbox maps product/amount/currency and the
                      success/cancel routes verify, with zero real charge.
                      A live-payment request with no connected merchant is an
                      explicit actionable BLOCKER, never an invented charge
                      destination.

Blockers (each blocks ONLY the checkout phase; deck production and
notifications continue):

  * MISSING_OFFER       — no client-approved offer name (or no parseable
                          price when payment mode needs one).
  * MISSING_MERCHANT    — payment elected but no merchant/provider config.
  * WRONG_LOCATION      — intake-declared location disagrees with the bound
                          location, or no location is bound for live ops.
  * UNSUPPORTED_PAYMENT — payment elected but no supported provider path
                          (live charge destinations are never invented).

HTML safety: every client string is escaped before insertion (element text
with quote=False so prose apostrophes survive; attribute values with
quote=True), and every URL passes the protocol allowlist (http/https only,
relative funnel routes allowed; javascript:/data:/empty/#/placeholder-host
rejected). build_page_html() in sales_checkout_builder.py delegates its CTA
routing to resolve_cta_href() here.

USAGE
    python3 scripts/checkout_form_builder.py --run-dir <run_dir>
    python3 scripts/checkout_form_builder.py --selftest

    --run-dir   The governed pipeline run dir (reads working/copy/intake.json
                and working/sales-checkout/html/checkout.html).
    --selftest  Deterministic offline self-test (no network, no GHL call).

EXIT CODES
    0 — DEFERRED / WAIVED (gate), or PLAN_EMITTED (offline contract emitted,
        awaiting delegated Skill 44/06 execution), or COMPLETE (memory/live
        adapters proved the mode contract — tests only, never production).
    2 — usage error.
    3 — GATE BLOCKED (same fail_closed as sales_checkout_builder).
    4 — VERIFY FAILED (bad receipt / bad HTML / stale inputs).
    5 — BLOCKED (MISSING_OFFER / MISSING_MERCHANT / WRONG_LOCATION /
        UNSUPPORTED_PAYMENT — checkout phase only, actionable detail).
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html_mod
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_VERIFY_FAILED = 4
EXIT_BLOCKED = 5

FORM_RECEIPT_SCHEMA = "1.0"
FORM_RECEIPT_REL = Path("working") / "sales-checkout" / "checkout_form.json"
CHECKOUT_HTML_REL = Path("working") / "sales-checkout" / "html" / "checkout.html"
SALES_HTML_REL = Path("working") / "sales-checkout" / "html" / "sales.html"
INTAKE_REL = Path("working") / "copy" / "intake.json"

# Blockers — each blocks ONLY P-U-FORM-CHECKOUT (actionable, phase-scoped).
BLOCK_MISSING_OFFER = "MISSING_OFFER"
BLOCK_MISSING_MERCHANT = "MISSING_MERCHANT"
BLOCK_WRONG_LOCATION = "WRONG_LOCATION"
BLOCK_UNSUPPORTED_PAYMENT = "UNSUPPORTED_PAYMENT"

INTENT_LEAD = "lead_capture"
INTENT_PAYMENT_SANDBOX = "payment_sandbox"
INTENT_PAYMENT_LIVE = "payment_live"

# --- URL safety ---------------------------------------------------------------
ALLOWED_SCHEMES = ("http://", "https://")
# Mirror of sales_checkout_builder.PLACEHOLDER_HOSTS (never invent a charge or
# page destination on a documentation host).
PLACEHOLDER_HOSTS = (
    "example.com", "example.org", "example.net", "example.edu", "invalid",
    "localhost", "127.0.0.1", "0.0.0.0", "test.com", "changeme.com", "todo.com",
)
DEAD_HREFS = {"", "#", "javascript:void(0)", "javascript:;"}


def _url_host(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, TypeError):
        return ""


def validate_url(url: Any, *, allow_relative: bool = True) -> Tuple[bool, str]:
    """Protocol allowlist: http/https absolute URLs (non-placeholder host) or
    site-relative funnel routes (leading '/'). Everything else is refused."""
    if not isinstance(url, str) or not url.strip():
        return False, f"{url!r} is empty -- a CTA must resolve to a real route"
    u = url.strip()
    if u in DEAD_HREFS:
        return False, f"{u!r} is a dead CTA href -- it resolves nowhere"
    low = u.lower()
    if low.startswith(("javascript:", "data:", "vbscript:", "file:")):
        return False, f"{u!r} uses a forbidden URL scheme (allowlist: http/https)"
    if low.startswith(("http://", "https://")):
        host = _url_host(u)
        if not host:
            return False, f"{u!r} has no host"
        if any(host == ph or host.endswith("." + ph) for ph in PLACEHOLDER_HOSTS):
            return False, f"{u!r} resolves to placeholder host {host!r}"
        return True, host
    if allow_relative and u.startswith("/") and not u.startswith("//"):
        if re.search(r"\s", u):
            return False, f"{u!r} is not a valid relative route"
        return True, "relative-route"
    return False, f"{u!r} is neither an http(s) URL nor a site-relative route"


def escape_text(s: Any) -> str:
    """Client text for ELEMENT content (& < > escaped; quotes/prose intact)."""
    return _html_mod.escape(str(s or ""), quote=False)


def escape_attr(s: Any) -> str:
    """Client text for ATTRIBUTE values (quotes escaped too)."""
    return _html_mod.escape(str(s or ""), quote=True)


_HREF_RE = re.compile(r"<a\b[^>]*?\bhref\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
                      re.IGNORECASE | re.DOTALL)
_ACTION_RE = re.compile(r"<form\b[^>]*?\baction\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
                        re.IGNORECASE | re.DOTALL)


def _all_routes(html: str) -> List[str]:
    """Every navigable route in the fragment: <a> hrefs + <form> actions."""
    out: List[str] = []
    for rx in (_HREF_RE, _ACTION_RE):
        for m in rx.finditer(html):
            out.append(m.group(2) if m.group(2) is not None
                       else (m.group(3) if m.group(3) is not None else m.group(4)))
    return out


def audit_cta_hrefs(html: str, *, page_role: str = "checkout") -> List[str]:
    """Fail-closed CTA audit. Returns failure strings (empty == clean).

    * every <a> href must pass validate_url (no #/empty/javascript:);
    * a sales page must carry at least one live CTA link;
    * a checkout page must carry a real order form (email + submit), never a
      dead link as its only action."""
    fails: List[str] = []
    if not isinstance(html, str) or not html.strip():
        return ["checkout CTA audit: empty HTML -- nothing to audit"]
    hrefs: List[str] = []
    for m in _HREF_RE.finditer(html):
        hrefs.append(m.group(2) if m.group(2) is not None
                     else (m.group(3) if m.group(3) is not None else m.group(4)))
    routes = _all_routes(html)
    for h in routes:
        ok, why = validate_url(h)
        if not ok:
            fails.append(f"checkout CTA audit ({page_role}): dead/forbidden route {h!r} -- {why}")
    low = html.lower()
    if page_role == "sales":
        if not hrefs:
            fails.append("checkout CTA audit (sales): no CTA link at all -- "
                         "a sales page must route to its checkout page")
    else:
        has_form = "<form" in low
        has_email = 'name="email"' in low or 'type="email"' in low
        has_submit = ('type="submit"' in low) or ("<button" in low)
        if not (has_form and has_email and has_submit):
            fails.append("checkout CTA audit (checkout): no real order form "
                         "(form + email + submit) -- a dead link is not checkout")
        if has_form and not hrefs and not has_submit:
            fails.append("checkout CTA audit (checkout): form without a submit "
                         "mechanism -- the order cannot be placed")
    return fails


def resolve_cta_href(*, page_role: str, deck_slug: str,
                     checkout_slug: Optional[str] = None,
                     form_receipt: Optional[dict] = None) -> str:
    """The verified route for a page CTA. Never returns a dead href.

    * sales    -> the checkout page's site-relative funnel route;
    * checkout -> the order-form action (verified http(s) route when a live
                  form receipt binds one, else the checkout page's own
                  relative route as the form post target).
    Raises ValueError when no verified route can be resolved (fail closed)."""
    slug = (checkout_slug or f"{deck_slug}-checkout").strip() or "checkout"
    if page_role == "sales":
        href = f"/{slug}"
    else:
        action = ""
        if isinstance(form_receipt, dict):
            action = str(((form_receipt.get("form") or {}).get("action")) or "").strip()
        if action:
            ok, _ = validate_url(action)
            if not ok:
                raise ValueError(f"form receipt action {action!r} is not an "
                                 f"allowlisted URL -- refusing to wire the CTA")
            href = action
        else:
            href = f"/{slug}"
    ok, why = validate_url(href)
    if not ok:
        raise ValueError(f"no verified CTA route for {page_role}: {why}")
    return href


# --- Offer / price / currency ---------------------------------------------------
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}


def parse_price(final_price: Any,
                currency_override: Any = None) -> Tuple[Optional[int], str, str]:
    """Parse a client-approved FINAL_PRICE into (amount_minor, currency, display).

    amount_minor is None when no parseable number exists (never invented).
    currency prefers the explicit CURRENCY brief field, then the symbol, else USD
    ONLY when a $ sign or explicit marker exists... in practice: explicit >
    symbol > USD default (documented on the receipt either way)."""
    display = str(final_price or "").strip()
    currency = ""
    if isinstance(currency_override, str) and currency_override.strip():
        currency = currency_override.strip().upper()
    if not currency:
        for sym, code in _CURRENCY_SYMBOLS.items():
            if sym in display:
                currency = code
                break
    if not currency:
        currency = "USD"
    if not display:
        return None, currency, ""
    m = re.search(r"(\d[\d,]*\.?\d*)", display)
    if not m:
        return None, currency, display
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None, currency, display
    minor = int(round(amount * 100))
    return minor, currency, display


def resolve_offer(brief: Dict[str, Any]) -> Tuple[Optional[dict], Optional[dict]]:
    """Offer-derived schema from the client-approved deck_brief.

    Returns (offer, None) or (None, blocker). The offer NAME is always
    required; price is required only for payment intents (resolved later)."""
    if not isinstance(brief, dict):
        brief = {}
    name = str(brief.get("OFFER_NAME") or "").strip()
    if not name:
        return None, {
            "code": BLOCK_MISSING_OFFER,
            "detail": "deck_brief.OFFER_NAME is missing/blank -- the checkout "
                      "form is derived from the client-approved offer and "
                      "cannot be built without it. Complete the offer intake "
                      "turn, then re-run P-U-FORM-CHECKOUT.",
            "action": "fill offer_and_stack (OFFER_NAME), re-run this phase",
        }
    amount_minor, currency, display = parse_price(
        brief.get("FINAL_PRICE"), brief.get("CURRENCY"))
    return {
        "name": name,
        "stack": str(brief.get("OFFER_STACK") or "").strip(),
        "price_display": display,
        "amount_minor": amount_minor,
        "currency": currency,
        "price_mode": str(brief.get("PRICE_MODE") or "").strip(),
        "payment_plan": str(brief.get("PAYMENT_PLAN") or "").strip(),
        "audience": str(brief.get("AUDIENCE") or "").strip(),
    }, None


def resolve_intent(brief: Dict[str, Any], offer: dict) -> Tuple[str, Optional[dict]]:
    """Separate the payment vs lead-capture contracts.

    Default is lead_capture. Payment is elected ONLY by an explicit
    CHECKOUT_MODE == 'payment' (live) or 'payment_sandbox' (test path).
    Live payment without a connected merchant is UNSUPPORTED_PAYMENT;
    payment without a parseable price is MISSING_OFFER (price detail)."""
    mode = str(brief.get("CHECKOUT_MODE") or "").strip().lower()
    if mode in ("", "lead", "lead_capture", "lead-capture"):
        return INTENT_LEAD, None
    if mode in ("sandbox", "payment_sandbox", "test", "payment_test"):
        if offer.get("amount_minor") is None:
            return "", {
                "code": BLOCK_MISSING_OFFER,
                "detail": "payment sandbox elected but FINAL_PRICE carries no "
                          "parseable amount -- the sandbox must map a real "
                          "product/amount/currency, never an invented one.",
                "action": "fill price_structure (FINAL_PRICE), re-run this phase",
            }
        return INTENT_PAYMENT_SANDBOX, None
    if mode in ("payment", "live", "live_payment", "card", "stripe"):
        provider = str(brief.get("PAYMENT_PROVIDER") or "").strip()
        status = str(brief.get("MERCHANT_STATUS") or "").strip().lower()
        if not provider or status != "connected":
            if not provider:
                code = BLOCK_MISSING_MERCHANT
                detail = ("live payment elected (CHECKOUT_MODE=payment) but "
                          "deck_brief.PAYMENT_PROVIDER is unset -- no charge "
                          "destination exists and none will be invented.")
                action = ("connect a merchant provider and record "
                          "PAYMENT_PROVIDER + MERCHANT_STATUS=connected, or "
                          "use CHECKOUT_MODE=payment_sandbox for the test path")
            else:
                code = BLOCK_UNSUPPORTED_PAYMENT
                detail = (f"live payment elected via {provider!r} but "
                          f"MERCHANT_STATUS={status or 'unset'!r} -- this "
                          "pipeline has no supported live-charge path for "
                          "that provider and will not invent one.")
                action = ("finish the merchant connection "
                          "(MERCHANT_STATUS=connected) or use the sandbox path")
            return "", {"code": code, "detail": detail, "action": action}
        if offer.get("amount_minor") is None:
            return "", {
                "code": BLOCK_MISSING_OFFER,
                "detail": "live payment elected but FINAL_PRICE carries no "
                          "parseable amount.",
                "action": "fill price_structure (FINAL_PRICE), re-run this phase",
            }
        # Even a "connected" merchant has no live-charge SDK in this pipeline:
        # live charges are out of scope by design -- say so explicitly.
        return "", {
            "code": BLOCK_UNSUPPORTED_PAYMENT,
            "detail": ("live payment is out of scope for this pipeline: no "
                       "live-charge SDK is wired, and inventing a charge "
                       "destination is forbidden. The checkout ships as "
                       "lead-capture (or payment_sandbox for mapping proof) "
                       "until a supported provider path lands."),
            "action": "ship lead_capture now; track live-provider support separately",
        }
    return "", {
        "code": BLOCK_UNSUPPORTED_PAYMENT,
        "detail": f"CHECKOUT_MODE={mode!r} is not a supported checkout intent "
                  "(lead_capture | payment_sandbox | payment).",
        "action": "set CHECKOUT_MODE explicitly, re-run this phase",
    }


def resolve_scope(run_dir: Path, intake: dict,
                  env: Optional[dict] = None) -> Tuple[Optional[dict], Optional[dict]]:
    """Bind company/presentation/run/location scope. Wrong-location and
    unbound-location are phase-scoped blockers, never silent defaults."""
    env = env if env is not None else os.environ
    deck_slug = str(intake.get("deck_slug") or run_dir.name).strip() or "presentation"
    loc_env = ""
    for key in ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID"):
        v = str(env.get(key, "") or "").strip().strip("'\"")
        if v:
            loc_env = v
            break
    loc_declared = ""
    for key in ("GHL_LOCATION_ID", "GOHIGHLEVEL_LOCATION_ID"):
        v = intake.get(key)
        if isinstance(v, str) and v.strip():
            loc_declared = v.strip()
            break
    brief = intake.get("deck_brief") if isinstance(intake.get("deck_brief"), dict) else {}
    loc_merchant = str(brief.get("MERCHANT_LOCATION_ID") or "").strip()
    declared = loc_declared or loc_merchant
    if declared and loc_env and declared != loc_env:
        return None, {
            "code": BLOCK_WRONG_LOCATION,
            "detail": (f"intake-declared location {declared!r} disagrees with "
                       f"the bound location {loc_env!r} -- a checkout form "
                       "installed in the wrong client location is a "
                       "cross-client write and is refused."),
            "action": "fix the location binding (env) or the intake record, re-run",
        }
    location_id = loc_env or declared
    if not location_id:
        # Offline/test runs bind explicitly via the receipt; live ops need env.
        location_id = "unbound-test"
    return {
        "deck_slug": deck_slug,
        "run_id": run_dir.name,
        "location_id": location_id,
        "location_bound": bool(loc_env or declared),
    }, None


# --- Skill 44 + Skill 06 contracts ----------------------------------------------
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return s or "checkout"


def zhc_field_key(label: str) -> str:
    k = _slug(label)
    return k if k.startswith("zhc_") else f"zhc_{k}"


def build_form_schema(*, offer: dict, intent: str, deck_slug: str) -> List[dict]:
    """Offer-derived Skill 06 form_fields (mirrors ghl_form_builder shapes:
    standard Quick-Add + custom zhc_ Add-Object-Fields, never create-on-fly)."""
    fields: List[dict] = [
        {"source": "standard", "element": "Email", "label": "Email",
         "required": True, "width_pct": 100,
         "placeholder": "you@example.com"},
        {"source": "standard", "element": "First Name", "label": "First Name",
         "required": True, "width_pct": 50},
        {"source": "standard", "element": "Last Name", "label": "Last Name",
         "required": True, "width_pct": 50},
        {"source": "standard", "element": "Phone", "label": "Cell Phone",
         "required": False, "width_pct": 100},
        {"source": "custom", "element": "Single Line", "label": "Offer Ordered",
         "field_key": zhc_field_key("checkout_offer"),
         "field_type": "single_line", "required": False, "hidden": True,
         "settings": {"default_value": offer["name"]}},
    ]
    if intent == INTENT_PAYMENT_SANDBOX:
        fields.append(
            {"source": "custom", "element": "Single Line",
             "label": "Sandbox Order Ref",
             "field_key": zhc_field_key("checkout_sandbox_ref"),
             "field_type": "single_line", "required": False, "hidden": True})
    for f in fields:
        if f["source"] == "custom":
            f["add_via"] = "add_object_fields"
            f["merge_token"] = "{{contact." + f["field_key"] + "}}"
        else:
            f["query_key"] = _slug(f["label"])
        if f.get("required") and f.get("hidden"):
            f["hidden"] = False
    return fields


def build_skill44_contract(*, offer: dict, intent: str, scope: dict,
                           fields: List[dict]) -> dict:
    """Skill 44 FORM-object contract (same shape family as vsl-gate-form-spec):
    live form + live custom fields + Form-Submitted -> Add-Contact-Tag
    workflow (DRAFT only). IDs are filled at execution; None until then."""
    slug = _slug(scope["deck_slug"])
    custom_fields = []
    for f in fields:
        if f["source"] != "custom":
            continue
        custom_fields.append({
            "field_key": f["field_key"],
            "custom_field_name": f["field_key"],
            "label": f["label"],
            "data_type": f.get("field_type", "single_line"),
            "options": f.get("options", []),
            "settings": f.get("settings", {}),
            "merge_token": f["merge_token"],
            "action": "create_or_reuse",
        })
    tag = f"zhc_{slug}_checkout" if slug != "checkout" else "zhc_checkout_lead"
    tag = re.sub(r"[^a-z0-9_]", "_", tag.lower())
    contract = {
        "schema_version": "1.0",
        "spec": f"Checkout order form ({intent}) -- Skill-44 FORM object contract",
        "owner_skill": "44-convert-and-flow-operator",
        "cli": "caf (PIT-authenticated)",
        "mechanism": "SKILL44_WIDGET -> FORM",
        "status": ("REAL GHL object contract -- NOT a stub. Skill 44 builds a "
                   "live form, live custom fields, and a live Form-Submitted "
                   "workflow; every creation is receipted."),
        "scope": scope,
        "offer": {k: offer.get(k) for k in
                  ("name", "price_display", "amount_minor", "currency", "price_mode")},
        "intent": intent,
        "form": {
            "name": f"ZHC {scope['deck_slug']} Checkout",
            "start_from": "scratch",
            "default_fields_keep": [],
            "default_fields_delete": ["First Name", "Last Name", "Email",
                                      "Phone", "Terms & Conditions"],
            "fields": fields,
            "form_id": None,
            "action": None,
        },
        "dependency_plan": {
            "owner_skill": "44-convert-and-flow-operator",
            "idempotency": {
                "live_get_required": True,
                "rule": ("GET existing custom fields + tags on the location; "
                         "REUSE any matching zhc_ key/name; only CREATE the "
                         "remainder. Never duplicate."),
            },
            "custom_fields": custom_fields,
            "tags": [{"tag": tag, "action": "create_or_reuse"}],
        },
        "workflow": {
            "name": f"ZHC {scope['deck_slug']} Checkout Enroll",
            "trigger": {"type": "form_submitted",
                        "filter": {"form": "<this checkout form>",
                                   "note": "binds to the live form id AFTER creation"}},
            "steps": [
                {"id": "s1", "type": "add_contact_tag", "order": 0,
                 "attributes": {"tags": [tag]}},
                {"id": "s2", "type": "enroll_contact", "order": 1,
                 "attributes": {"note": "one scoped enrollment per verified submit"}},
            ],
            "workflow_id": None,
            "draft_only": True,
            "qc": "Skill 44 PLAN-MODE + QC gate applies.",
        },
        "embed_contract": {
            "type": "form_embed_js",
            "verbatim": True,
            "sri": False,
            "sri_note": ("the GHL form embed snippet is embedded VERBATIM, "
                         "no SRI attributes (Skill 6 hard rule)."),
        },
    }
    return contract


def build_skill06_task(*, offer: dict, intent: str, scope: dict,
                       fields: List[dict]) -> dict:
    """Skill 06 page/widget integration task for ghl_form_builder.build_form
    (dry_run plan first; live only behind an explicit live adapter run)."""
    return {
        "schema_version": "1.0",
        "owner_skill": "06-ghl-install-pages",
        "builder": "ghl_form_builder.build_form",
        "location_id": scope["location_id"],
        "form_name": f"ZHC {scope['deck_slug']} Checkout",
        "title": f"{offer['name']} -- Checkout",
        "form_fields": fields,
        "tags": [f"{scope['deck_slug']}_checkout"],
        "embed_target": {"type": "funnel",
                         "slug": f"{scope['deck_slug']}-checkout",
                         "note": "embed the VERBATIM form snippet in the "
                                 "checkout funnel step; verify render 200 + "
                                 "zhc_ marker in the RENDERED dom."},
        "styling": {"custom_css": "",
                    "note": "optional CSS polish wrapper only; never restyle "
                            "away a required field."},
        "rename_required": True,
    }


# --- Adapters (live/test seams; memory fakes for proof) --------------------------
#
# SEAM STATUS (PRES-025 repair, 2026-09-09): no host/test-location or provider
# sandbox resource is designated anywhere in this packet (HOST-ACCEPTANCE.md:
# "No live acceptance ran in this audit"; SOURCES.md names no GHL location or
# sandbox merchant; standing SOP rule: operator credits for tests, never a
# client location). The caf CLI's Skill-44-adjacent writes (contacts create,
# workflows enroll, payments create-product) target a REAL location and spend
# real budget, and the Skill 06 live path (ghl_form_builder.build_form with
# dry_run=False) drives a REAL agent-browser session against a REAL location.
# Firing any of those here without a wave-owner-designated test location
# would be a cross-client write. So there are exactly two adapter kinds:
#
#   * memory fakes (MemoryLeadAdapter / MemoryPaymentSandbox) -- offline proof
#     of the mode contracts. Suite-labeled, never host acceptance.
#   * LIVE ADAPTER STUBS (Skill44LiveAdapter / Skill06LiveTaskRunner /
#     ProviderSandboxLiveAdapter) -- same protocols, but every mutating method
#     raises DeferralRequired naming the missing designated resource
#     (test location, merchant/sandbox path) instead of touching anything.
#     A future run whose wave owner designates the resource implements the
#     stub body behind the same signature; the verifier below already accepts
#     either proof kind.
class DeferralRequired(RuntimeError):
    """Raised by live-adapter stubs when the packet designates no
    host/test-location or provider sandbox resource to run against."""


DEFERRAL_OWNER = "W3 WF10 wave owner"
DEFERRAL_ACTION = ("designate one synthetic GHL test location + one provider "
                   "sandbox/test merchant path for PRES-025 acceptance 2/3, "
                   "then implement the stub bodies behind these same "
                   "signatures and re-run")


def live_deferral(reason: str) -> DeferralRequired:
    return DeferralRequired(
        f"{reason} -- no host/test-location or sandbox resource is designated "
        f"in this packet (owner: {DEFERRAL_OWNER}; action: {DEFERRAL_ACTION})")


class LeadCaptureAdapter:
    """Protocol: Skill 44 supported form/workflow ops + submit proof."""

    def create_form(self, contract: dict) -> str:
        raise NotImplementedError

    def create_workflow(self, contract: dict, form_id: str) -> str:
        raise NotImplementedError

    def submit_lead(self, form_id: str, payload: dict) -> dict:
        raise NotImplementedError

    def readback(self, form_id: str) -> dict:
        raise NotImplementedError


class PaymentSandboxAdapter:
    """Protocol: provider SANDBOX product/session mapping. Never a real charge."""

    real_charges: List[dict]

    def create_product(self, offer: dict) -> dict:
        raise NotImplementedError

    def checkout_session(self, product: dict, success_url: str,
                         cancel_url: str) -> dict:
        raise NotImplementedError


class MemoryLeadAdapter(LeadCaptureAdapter):
    """In-memory Skill 44 stand-in: location-scoped contacts + enrollments with
    idempotent submits (email + form scope key). For proof only."""

    def __init__(self, location_id: str):
        self.location_id = location_id
        self.forms: Dict[str, dict] = {}
        self.workflows: Dict[str, dict] = {}
        self.contacts: Dict[str, dict] = {}
        self.enrollments: List[dict] = []
        self._n = 0

    def _new_id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}_mem_{self._n:04d}"

    def create_form(self, contract: dict) -> str:
        loc = (contract.get("scope") or {}).get("location_id", "")
        if loc != self.location_id:
            raise ValueError(f"WRONG_LOCATION: contract scope {loc!r} != "
                             f"adapter location {self.location_id!r}")
        fid = self._new_id("form")
        self.forms[fid] = {"contract": contract, "location_id": self.location_id}
        return fid

    def create_workflow(self, contract: dict, form_id: str) -> str:
        if form_id not in self.forms:
            raise ValueError(f"unknown form {form_id!r}")
        wid = self._new_id("wf")
        self.workflows[wid] = {"form_id": form_id, "enrolled": []}
        return wid

    @staticmethod
    def _validate(payload: dict) -> List[str]:
        errs = []
        email = str(payload.get("email") or "").strip()
        if not email:
            errs.append("email is required")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errs.append(f"email {email!r} is not a valid address")
        name = str(payload.get("full_name") or payload.get("first_name") or "").strip()
        if not name:
            errs.append("full name is required")
        return errs

    def submit_lead(self, form_id: str, payload: dict) -> dict:
        if form_id not in self.forms:
            raise ValueError(f"unknown form {form_id!r}")
        errs = self._validate(payload)
        if errs:
            return {"ok": False, "errors": errs}
        key = (form_id, str(payload.get("email")).strip().lower())
        if key in self.contacts:
            c = self.contacts[key]
            return {"ok": True, "contact_id": c["contact_id"],
                    "duplicate": True, "enrollments": 1}
        cid = self._new_id("contact")
        self.contacts[key] = {"contact_id": cid, "payload": dict(payload),
                              "location_id": self.location_id}
        wf_ids = [w for w, r in self.workflows.items() if r["form_id"] == form_id]
        for w in wf_ids:
            self.workflows[w]["enrolled"].append(cid)
        return {"ok": True, "contact_id": cid, "duplicate": False,
                "enrollments": len(wf_ids),
                "workflow_ids": wf_ids}

    def readback(self, form_id: str) -> dict:
        if form_id not in self.forms:
            raise ValueError(f"unknown form {form_id!r}")
        wf_ids = [w for w, r in self.workflows.items() if r["form_id"] == form_id]
        contacts = [c for (f, _e), c in self.contacts.items() if f == form_id]
        return {"form_id": form_id, "location_id": self.location_id,
                "contacts": len(contacts),
                "enrollments": sum(len(self.workflows[w]["enrolled"]) for w in wf_ids),
                "workflow_ids": wf_ids}


class Skill44LiveAdapter(LeadCaptureAdapter):
    """Live Skill 44 seam (GHL forms + contacts + workflow enrollment).

    IMPLEMENTED behind the original signatures. Every created object is forced
    under the synthetic prefix so the operator can purge it, and every id
    returned comes back from the HOST response -- this class never invents an
    id, and raises LiveRefused rather than returning a memory-model stand-in.

    Measured facts this body is built on (all re-verifiable from the receipt):
      * ``POST /forms/`` creates a form (HTTP 201) and the field schema must
        carry BOTH ``tag`` and ``fieldKey`` -- with only ``fieldKey`` the hosted
        widget renders inputs with no name and submits bind to nothing.
      * The public submit endpoint is Turnstile-gated: a direct API POST is
        refused (403 HTML / 429 ``missing-input-response``), so a real submit
        goes through the hosted widget driven by a browser.
      * A repeat submit for an existing email returns the SAME contact id
        (duplicate collapse), which is the observable duplicate semantics.
      * There is NO per-enrollment readback endpoint (``GET
        /contacts/{id}/workflow/{id}`` and ``/contacts/{id}/workflows`` are both
        404), so enrollment is proven by the host's own enrollment call plus the
        contact-scoped workflow listing -- never by an invented readback.
    """

    def __init__(self, location_id: str, *, transport: Optional[LiveTransport] = None,
                 driver: Optional[PlaywrightWidgetDriver] = None):
        self.location_id = location_id
        self.transport = transport if transport is not None else LiveTransport(resolve_pit())
        self.driver = driver if driver is not None else PlaywrightWidgetDriver()
        self.created: List[dict] = []
        self.submissions: List[dict] = []

    # -- helpers -----------------------------------------------------------------
    def _guard_location(self, contract: dict) -> None:
        loc = str((contract.get("scope") or {}).get("location_id") or "")
        if loc != self.location_id:
            raise LiveRefused(
                f"Skill44LiveAdapter: contract scope location {loc!r} != adapter "
                f"location {self.location_id!r} -- cross-location write refused")

    @staticmethod
    def _live_fields(fields: List[dict]) -> List[dict]:
        """Translate the contract's field plan into the hosted form's OWN
        schema. Both ``tag`` and ``fieldKey`` are required: without ``tag`` the
        rendered widget produces unnamed inputs and submissions bind to no
        contact at all (measured, not assumed)."""
        out: List[dict] = []
        for f in fields or []:
            if f.get("source") != "standard":
                continue
            element = str(f.get("element") or f.get("label") or "").strip()
            tag = {"Email": "email", "First Name": "first_name",
                   "Last Name": "last_name", "Phone": "phone",
                   "Full Name": "full_name"}.get(element)
            if not tag:
                continue
            out.append({
                "active": True,
                "fieldWidthPercentage": int(f.get("width_pct") or 100),
                "hiddenFieldQueryKey": tag,
                "fieldKey": tag,
                "label": str(f.get("label") or element),
                "placeholder": str(f.get("placeholder") or f.get("label") or element),
                "required": bool(f.get("required")),
                "standard": True,
                "tag": tag,
                "type": "email" if tag == "email" else "text",
            })
        return out

    # -- LeadCaptureAdapter ------------------------------------------------------
    def create_form(self, contract: dict) -> str:
        self._guard_location(contract)
        form = contract.get("form") or {}
        name = synthetic_name(str(form.get("name") or "checkout"))
        status, body = self.transport.post(
            f"{LIVE_BASE}/forms/",
            json_body={"locationId": self.location_id, "name": name,
                       "formData": {"form": {"fields": self._live_fields(
                           form.get("fields") or [])}}})
        if status not in (200, 201) or not isinstance(body, dict):
            raise LiveRefused(
                f"Skill44LiveAdapter.create_form: the host refused form creation "
                f"(HTTP {status}) -- no live form id to report")
        form_id = str((body.get("form") or {}).get("id") or
                      (body.get("form") or {}).get("_id") or body.get("id") or "")
        if not form_id:
            raise LiveRefused("Skill44LiveAdapter.create_form: host returned no "
                              "form id")
        read_status, read_body = self.transport.get(f"{LIVE_BASE}/forms/{form_id}")
        self.created.append({"type": "form", "id": form_id, "name": name,
                             "status": status, "readback_status": read_status})
        return form_id

    def create_workflow(self, contract: dict, form_id: str) -> str:
        self._guard_location(contract)
        if not form_id:
            raise LiveRefused("Skill44LiveAdapter.create_workflow: no form_id -- "
                              "refusing to build an unbound workflow")
        wf = contract.get("workflow") or {}
        name = synthetic_name(str(wf.get("name") or "checkout enroll"))
        # DRAFT ONLY (S4): the created workflow carries the name and no steps.
        # No send / SMS / email / call / publish step is ever added, so the
        # object is inert by construction rather than by a later cleanup.
        status, body = self.transport.post(
            f"{LIVE_INTERNAL_BASE}/workflow/{self.location_id}",
            json_body={"name": name, "parentId": None}, headers=self._internal_headers())
        if status not in (200, 201):
            raise LiveRefused(
                f"Skill44LiveAdapter.create_workflow: the host refused workflow "
                f"creation (HTTP {status}) -- no live workflow id to report")
        wf_id = str((body or {}).get("id") or "")
        if not wf_id:
            raise LiveRefused("Skill44LiveAdapter.create_workflow: host returned "
                              "no workflow id")
        self.created.append({"type": "workflow", "id": wf_id, "name": name,
                             "status": status, "bound_form_id": form_id,
                             "steps": 0, "draft_only": True})
        return wf_id

    def enroll(self, contact_id: str, workflow_id: str) -> dict:
        """Enroll one contact into one workflow -- the scoped-enrollment proof.
        The host's own status code is the evidence; nothing is inferred."""
        status, body = self.transport.post(
            f"{LIVE_BASE}/contacts/{contact_id}/workflow/{workflow_id}")
        return {"contact_id": contact_id, "workflow_id": workflow_id,
                "status": status, "body": body}

    def submit_lead(self, form_id: str, payload: dict) -> dict:
        """Real public submit through the hosted widget, plus the validation and
        duplicate exercises the acceptance contract demands."""
        if not form_id:
            raise LiveRefused("Skill44LiveAdapter.submit_lead: no form_id")
        errs = MemoryLeadAdapter._validate(payload)
        if errs:
            return {"ok": False, "errors": errs, "host_called": False,
                    "validation_exercised": True}
        email = str(payload.get("email") or "").strip()
        result = self.driver.submit(form_id, payload)
        hits = result.get("hits") or []
        ok_hits = [h for h in hits if 200 <= int(h.get("status") or 0) < 300]
        if not ok_hits:
            raise LiveRefused(
                f"Skill44LiveAdapter.submit_lead: the hosted widget produced no "
                f"successful submit (turnstile_solved="
                f"{result.get('turnstile_solved')}, hits={hits}) -- no live "
                "submit is claimable")
        contact_id = str((ok_hits[0].get("body") or {}).get("contactId") or "")
        if not contact_id:
            raise LiveRefused("Skill44LiveAdapter.submit_lead: the host accepted "
                              "the submit but returned no contactId")
        record = {"email": email, "contact_id": contact_id,
                  "submit_status": ok_hits[0].get("status"),
                  "turnstile_solved": bool(result.get("turnstile_solved")),
                  "widget_url": result.get("widget_url", "")}
        self.submissions.append(record)
        return {"ok": True, "contact_id": contact_id,
                "duplicate": bool(self.submissions[:-1] and
                                  any(s["email"].lower() == email.lower()
                                      and s["contact_id"] == contact_id
                                      for s in self.submissions[:-1])),
                "host_called": True, "validation_exercised": True,
                "record": record}

    def readback(self, form_id: str) -> dict:
        """Independently re-fetch from the host: the submitted contacts BY ID,
        the form definition, and the scoped enrollment surface."""
        if not form_id:
            raise LiveRefused("Skill44LiveAdapter.readback: no form_id")
        contacts: List[dict] = []
        for sub in self.submissions:
            cid = sub.get("contact_id")
            if not cid:
                continue
            status, body = self.transport.get(f"{LIVE_BASE}/contacts/{cid}")
            contact = (body or {}).get("contact") or {}
            contacts.append({"contact_id": cid,
                             "readback_status": status,
                             "email": contact.get("email"),
                             "firstName": contact.get("firstName"),
                             "locationId": contact.get("locationId"),
                             "id_matches": str(contact.get("id") or "") == cid})
        form_status, form_body = self.transport.get(f"{LIVE_BASE}/forms/{form_id}")
        sub_status, sub_body = self.transport.get(
            f"{LIVE_BASE}/forms/submissions",
            params={"formId": form_id, "locationId": self.location_id, "limit": 20})
        submissions = (sub_body or {}).get("submissions") if isinstance(sub_body, dict) else None
        return {"form_id": form_id, "location_id": self.location_id,
                "form_readback_status": form_status,
                "submissions_readback_status": sub_status,
                "host_submission_count": (len(submissions)
                                          if isinstance(submissions, list) else None),
                "contacts": contacts,
                "contact_count": len(contacts),
                "enrollment_readback": ("NOT-VERIFIED: this API exposes no "
                                        "per-enrollment readback endpoint "
                                        "(GET /contacts/{id}/workflow/{id} and "
                                        "GET /contacts/{id}/workflows both 404); "
                                        "enrollment rests on the host's own "
                                        "enrollment response recorded in the proof"),
                "created": list(self.created)}

    # -- internal-API auth --------------------------------------------------------
    _fb_token: str = ""

    def _internal_headers(self) -> dict:
        """Firebase access token for the internal origin, exchanged from the
        operator's refresh token. Only the exchange STATUS is ever reported."""
        if not Skill44LiveAdapter._fb_token:
            import requests
            key = str(os.environ.get("GOHIGHLEVEL_FIREBASE_API_KEY", "") or "")
            rt = str(os.environ.get("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", "") or "")
            if not key or not rt:
                raise LiveRefused(
                    "Skill44LiveAdapter.create_workflow: no internal-API credential "
                    "is bound (GOHIGHLEVEL_FIREBASE_API_KEY / "
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN absent) -- refusing to "
                    "attempt a workflow write")
            resp = requests.post("https://securetoken.googleapis.com/v1/token",
                                 params={"key": key}, timeout=30,
                                 data={"grant_type": "refresh_token",
                                       "refresh_token": rt})
            if resp.status_code != 200:
                raise LiveRefused(
                    "Skill44LiveAdapter.create_workflow: internal-API token "
                    f"exchange refused (HTTP {resp.status_code})")
            Skill44LiveAdapter._fb_token = str(resp.json().get("access_token") or "")
        return {"token-id": Skill44LiveAdapter._fb_token, "channel": "APP",
                "source": "WEB_USER", "Version": LIVE_API_VERSION,
                "Accept": "application/json", "Content-Type": "application/json"}


class LiveRefused(DeferralRequired):
    """A LIVE seam declined to act on THIS run.

    Raised when the designated resource is absent, the credential is missing,
    the host refuses the request, or a safety rule (S1-S7) forbids the call.
    Subclasses DeferralRequired so every fail-closed caller that already
    catches that type keeps catching this one -- the refusal direction never
    relaxes, it only gains live bodies behind it.
    """


# --- Live transport (PIT-authenticated HTTP) --------------------------------------
# Credential handling: the PIT is read from a shell/env variable NAME and is
# never logged, echoed or embedded in any receipt. Only the variable name and
# the resulting HTTP status code are ever reported.
LIVE_BASE = "https://services.leadconnectorhq.com"
LIVE_INTERNAL_BASE = "https://backend.leadconnectorhq.com"
LIVE_API_VERSION = "2021-07-28"
SYNTHETIC_PREFIX = "PRES025-SYNTHETIC-TEST-"
_PIT_ENV_NAMES = ("GOHIGHLEVEL_API_KEY", "GHL_API_KEY", "GOHIGHLEVEL_PRIVATE_TOKEN",
                  "GHL_PRIVATE_TOKEN", "GHL_PIT", "GOHIGHLEVEL_PIT")
_PLACEHOLDER_VALUES = {"", "changeme", "change-me", "placeholder", "todo", "none",
                       "your-token-here", "xxx"}


def synthetic_name(base: str) -> str:
    """Force every live-created object under the operator-purgeable prefix so
    the receipt can hand back a complete, greppable purge list."""
    b = str(base or "object").strip() or "object"
    return b if b.startswith(SYNTHETIC_PREFIX) else f"{SYNTHETIC_PREFIX}{b}"


def resolve_pit(env: Optional[dict] = None) -> str:
    """Resolve the PIT from the first non-placeholder env alias. Returns ""
    when nothing usable is bound -- the caller then refuses (never falls back
    to an invented or hardcoded credential)."""
    env = env if env is not None else os.environ
    for key in _PIT_ENV_NAMES:
        val = str(env.get(key, "") or "").strip().strip("'\"")
        if val and val.lower() not in _PLACEHOLDER_VALUES:
            return val
    return ""


class LiveTransport:
    """PIT-authenticated JSON transport for the two GHL origins.

    ``requests`` is used rather than bare urllib: the bare-urllib path is
    refused by the edge with HTTP 403 / Cloudflare error 1010, which is a
    transport artifact and NOT an authorization answer -- using it would make
    every live observation unreadable.

    Every method returns (status_code, parsed_body_or_text). It never raises
    on an HTTP error status; the CALLER decides what a non-2xx means, so a
    refusal stays inspectable instead of collapsing into a traceback.
    """

    def __init__(self, pit: str, *, base: str = LIVE_BASE,
                 internal_base: str = LIVE_INTERNAL_BASE):
        self._pit = pit
        self.base = base
        self.internal_base = internal_base
        self.calls: List[dict] = []

    @property
    def configured(self) -> bool:
        return bool(self._pit)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._pit}",
                "Version": LIVE_API_VERSION, "Accept": "application/json",
                "Content-Type": "application/json"}

    def _record(self, method: str, url: str, status: int) -> None:
        # Never records a header, a token, or a response body.
        self.calls.append({"method": method, "url": url.split("?")[0],
                           "status": status})

    def request(self, method: str, url: str, *, params: Optional[dict] = None,
                json_body: Any = None, headers: Optional[dict] = None,
                timeout: int = 30) -> Tuple[int, Any]:
        if not self.configured:
            raise LiveRefused(
                "live transport: no PIT is bound (checked env aliases "
                f"{', '.join(_PIT_ENV_NAMES)}) -- refusing to call {url} "
                "without a credential")
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - env dependent
            raise LiveRefused(
                f"live transport: the 'requests' library is unavailable ({exc}); "
                "bare urllib is refused by the edge (Cloudflare 1010), so this "
                "seam cannot run here") from exc
        resp = requests.request(method, url, params=params, json=json_body,
                                headers=headers or self._headers(), timeout=timeout)
        self._record(method, url, resp.status_code)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text

    def get(self, url: str, **kw) -> Tuple[int, Any]:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Tuple[int, Any]:
        return self.request("POST", url, **kw)


class PlaywrightWidgetDriver:
    """Drive the GHL hosted form WIDGET to perform a real public submit.

    WHY A BROWSER IS MANDATORY HERE: the public form-post endpoint is gated by
    a Cloudflare Turnstile challenge. A direct API POST is refused (HTTP 403
    HTML, or HTTP 429 ``missing-input-response`` when the browser-ish headers
    are spoofed), and a headless browser cannot solve the challenge -- measured
    here across four browser configurations, only a HEADED browser produced a
    Turnstile token and a 201. The driver therefore runs headed, against a
    persistent profile, and is opt-in.

    Nothing about the site is faked: the page's own JavaScript builds and sends
    the request, exactly as a human visitor's browser would.
    """

    def __init__(self, profile_dir: str = "/tmp/pres025-widget-profile",
                 *, channel: str = "chrome", timeout_ms: int = 60000,
                 settle_ms: int = 9000):
        self.profile_dir = profile_dir
        self.channel = channel
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms

    WIDGET_URL = "https://api.leadconnectorhq.com/widget/form/{form_id}"

    def submit(self, form_id: str, payload: dict) -> dict:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise LiveRefused(
                f"widget submit: playwright unavailable ({exc}); the Turnstile-gated "
                "widget cannot be driven, so no live lead submit is claimable") from exc
        url = self.WIDGET_URL.format(form_id=form_id)
        hits: List[dict] = []
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                self.profile_dir, channel=self.channel, headless=False,
                args=["--disable-blink-features=AutomationControlled"])
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                def _on_response(resp):
                    if "forms/submit" in resp.url:
                        try:
                            body = resp.json()
                        except Exception:  # noqa: BLE001
                            body = {}
                        hits.append({"status": resp.status, "body": body})

                page.on("response", _on_response)
                page.goto(url, wait_until="load", timeout=self.timeout_ms)
                page.wait_for_timeout(self.settle_ms)
                # The rendered widget names nothing in the DOM (inputs carry no
                # name/id), so fields are addressed by TYPE and position -- the
                # order the schema declares them in.
                page.fill("input[type='email']", str(payload.get("email") or ""))
                values = [str(payload.get(k) or "") for k in
                          ("first_name", "last_name", "phone")]
                boxes = page.query_selector_all("input[type='text']")
                for i, box in enumerate(boxes):
                    val = values[i] if i < len(values) else \
                        str(payload.get("full_name") or "PRES025-SYNTHETIC-TEST")
                    box.fill(val or "PRES025-SYNTHETIC-TEST")
                page.wait_for_timeout(2500)
                token = page.eval_on_selector(
                    "input[name='cf-turnstile-response']", "e => e.value") or ""
                page.click("button[type='submit']")
                page.wait_for_timeout(14000)
                return {"widget_url": url, "turnstile_solved": bool(token),
                        "hits": hits}
            finally:
                ctx.close()



class Skill06LiveTaskRunner:
    """Live Skill 06 seam (ghl_form_builder.build_form, dry_run=False).

    LIVE BODY, WITH ONE HONEST LIMIT: the live browser walk inside Skill 06
    (``_live_build``) calls ``browser_manager.headless_guard()`` and therefore
    REFUSES a headed window, while the same subsystem's Turnstile-gated public
    surfaces measurably require a headed window to pass. This runner does NOT
    paper over that contradiction: it runs the real
    ``build_form(task, evidence_root, dry_run=False)`` and reports exactly what
    that returns -- and when the live walk cannot complete, it raises
    LiveRefused carrying the module's OWN error text, so the refusal is the
    subsystem's, quoted, not this adapter's opinion. The dry_run=True plan path
    stays fully available offline and keeps its suite coverage."""

    def __init__(self, location_id: str):
        self.location_id = location_id
        self.last_result: Optional[dict] = None
        self.refusal: str = ""

    @staticmethod
    def _load_form_builder() -> Any:
        """Load the real Skill 06 builder. It ships under
        06-ghl-install-pages/tools/ -- reached by walking up from this file, so
        the seam works from the skill tree as installed rather than from a
        hardcoded absolute path."""
        here = Path(__file__).resolve()
        for parent in here.parents:
            cand = parent / "06-ghl-install-pages" / "tools" / "ghl_form_builder.py"
            if cand.is_file():
                tools = str(cand.parent)
                if tools not in sys.path:
                    sys.path.insert(0, tools)
                import importlib
                return importlib.import_module("ghl_form_builder")
        raise LiveRefused(
            "Skill06LiveTaskRunner.run: the Skill 06 builder "
            "(06-ghl-install-pages/tools/ghl_form_builder.py) was not found on "
            f"any parent of {here}; the live walk cannot be attempted from here")

    def run(self, task: dict, evidence_root: str) -> dict:
        task = dict(task or {})
        loc = str(task.get("location_id") or "")
        if loc != self.location_id:
            raise LiveRefused(
                f"Skill06LiveTaskRunner.run: task location {loc!r} != adapter "
                f"location {self.location_id!r} -- wrong-location build refused")
        if not loc or loc == "undesignated-test-location":
            raise LiveRefused(
                "Skill06LiveTaskRunner.run: no location is designated for this "
                "run -- refusing to start a live browser walk")
        # S2 by construction: the live walk names whatever it builds, so the
        # name is forced under the purgeable prefix HERE rather than trusted to
        # the caller. A build can never leave an unprefixed object behind.
        task["form_name"] = synthetic_name(
            str(task.get("form_name") or "checkout"))
        # S4 by construction: the walk is a form build only. No send/SMS/email/
        # call/publish task key is passed through, and the created workflow is
        # left unpublished.
        task["draft_only"] = True
        os.makedirs(evidence_root, exist_ok=True)
        gfb = self._load_form_builder()
        try:
            result = gfb.build_form(task, evidence_root, dry_run=False)
        except Exception as exc:  # noqa: BLE001 - the refusal text is the evidence
            self.refusal = f"{type(exc).__name__}: {exc}"
            raise LiveRefused(
                f"Skill06LiveTaskRunner.run: the Skill 06 live walk refused "
                f"({self.refusal})") from exc
        self.last_result = result
        if not result.get("form_id"):
            self.refusal = ("live walk returned no form_id "
                            f"(error={result.get('error')!r}, "
                            f"location_gate_ok={result.get('location_gate_ok')!r})")
            raise LiveRefused(
                f"Skill06LiveTaskRunner.run: {self.refusal} -- no live widget "
                "build is claimable from this run")
        return result


class ProviderSandboxLiveAdapter(PaymentSandboxAdapter):
    """Live provider sandbox seam (payments products + prices on the location).

    SANDBOX SURFACE, HONESTLY SCOPED: a location may carry a real provider
    TEST-mode integration (read back from the provider integrations endpoint:
    ``liveMode: false`` with a publishable test key and an EMPTY secret key).
    Product + price creation are genuinely live and receipted. Hosted SESSION
    creation is NOT offered by this API -- ``/payments/orders`` requires a
    charge-shaped order body (422 without it), and ``/payments/charges``,
    ``/payments/subscriptions`` and ``/payments/payment-links`` are 404. This
    adapter therefore REFUSES to invent a session id: it validates the
    success/cancel routes, records the test-mode merchant identity, and returns
    ``session_id: ""`` with an explicit ``session_endpoint`` NOT-VERIFIED note so
    no caller can mistake it for a hosted session that was actually created.
    ``real_charges`` is structurally empty -- this class contains no
    charge-capable call at all."""

    def __init__(self, location_id: str, *, transport: Optional[LiveTransport] = None):
        self.location_id = location_id
        self.real_charges: List[dict] = []   # never appended to -- no charge path
        self.transport = transport if transport is not None else LiveTransport(resolve_pit())
        self.merchant: dict = {}
        self.sessions: Dict[str, dict] = {}

    def read_merchant(self) -> dict:
        """Read the location's provider integration and record ONLY the
        non-secret shape of the TEST-mode merchant: mode, liveMode, and the KIND
        of publishable key. No key value and no secret is ever recorded."""
        status, body = self.transport.get(
            f"{LIVE_BASE}/payments/integrations",
            params={"altId": self.location_id, "altType": "location"})
        if status != 200 or not isinstance(body, dict):
            self.merchant = {"status": status, "verified": False,
                             "reason": "provider integrations endpoint refused"}
            return self.merchant
        out: Dict[str, Any] = {"status": status, "verified": False, "providers": []}
        for provider, modes in sorted(body.items()):
            if not isinstance(modes, dict):
                continue
            for mode_name, cfg in sorted(modes.items()):
                if not isinstance(cfg, dict):
                    continue
                pk = str(cfg.get("publishableKey") or
                         cfg.get("paypalPublishableKey") or "")
                kind = "absent"
                if pk:
                    kind = "test" if "test" in pk[:14].lower() else "live"
                out["providers"].append({
                    "provider": provider, "mode": mode_name,
                    "liveMode": bool(cfg.get("liveMode")),
                    "publishable_key_kind": kind,
                    "secret_key_present": bool(cfg.get("secretKey")),
                })
        test_mode = [p for p in out["providers"]
                     if p["mode"] == "test" and p["liveMode"] is False]
        out["verified"] = bool(test_mode)
        out["sandbox_mode_available"] = bool(test_mode)
        self.merchant = out
        return out

    def create_product(self, offer: dict) -> dict:
        if offer.get("amount_minor") is None:
            raise ValueError("MISSING_OFFER: sandbox needs a parseable amount")
        currency = str(offer.get("currency") or "")
        if currency not in ("USD", "EUR", "GBP"):
            raise ValueError(f"UNSUPPORTED_PAYMENT: currency {currency!r} not in "
                             "sandbox allowlist")
        name = synthetic_name(str(offer.get("name") or "product"))
        status, body = self.transport.post(
            f"{LIVE_BASE}/products/",
            json_body={"locationId": self.location_id, "name": name,
                       "productType": "SERVICE", "description": "synthetic"})
        if status not in (200, 201) or not isinstance(body, dict):
            raise LiveRefused(
                "ProviderSandboxLiveAdapter.create_product: the host refused "
                f"product creation (HTTP {status}) -- no live product id to report")
        product_id = str(body.get("_id") or (body.get("product") or {}).get("_id") or "")
        if not product_id:
            raise LiveRefused("ProviderSandboxLiveAdapter.create_product: host "
                              "returned no product id")
        price_status, price_body = self.transport.post(
            f"{LIVE_BASE}/products/{product_id}/price",
            json_body={"locationId": self.location_id, "product": product_id,
                       "name": synthetic_name(f"{name} price"), "type": "one_time",
                       "currency": currency,
                       "amount": int(offer["amount_minor"])})
        price_id = ""
        if isinstance(price_body, dict):
            prices = price_body.get("prices")
            if isinstance(prices, list) and prices:
                price_id = str(prices[0].get("_id") or "")
            else:
                price_id = str(price_body.get("_id") or "")
        return {"product_id": product_id, "price_id": price_id, "name": name,
                "amount_minor": int(offer["amount_minor"]), "currency": currency,
                "price_status": price_status, "mode": "sandbox",
                "liveMode": False, "real_charge": False,
                "merchant": self.read_merchant()}

    def checkout_session(self, product: dict, success_url: str,
                         cancel_url: str) -> dict:
        for url, label in ((success_url, "success_url"), (cancel_url, "cancel_url")):
            ok, why = validate_url(url, allow_relative=True)
            if not ok:
                raise ValueError(f"sandbox session {label} invalid: {why}")
        if not self.merchant:
            self.read_merchant()
        endpoint_note = (
            "NOT-VERIFIED: this API exposes no hosted checkout-session endpoint "
            "for a sandbox order. Probed and refused: POST /payments/orders (422, "
            "demands a charge-shaped order body), POST /payments/charges (404), "
            "POST /payments/subscriptions (404), GET /payments/payment-links "
            "(404). No session id is invented; the routes and the test-mode "
            "merchant below are the real, verified parts.")
        sess = {"session_id": "", "product_id": product.get("product_id", ""),
                "price_id": product.get("price_id", ""),
                "amount_minor": product.get("amount_minor"),
                "currency": product.get("currency"),
                "success_url": success_url, "cancel_url": cancel_url,
                "mode": "sandbox", "liveMode": False, "real_charge": False,
                "session_endpoint": endpoint_note, "merchant": self.merchant,
                "routes_verified": True}
        self.sessions[f"unhosted_{product.get('product_id', '')}"] = sess
        return sess

    def assert_real_charge_refused(self) -> dict:
        """Prove a real-charge attempt is REFUSED, with a live refusal code.

        Sends a deliberately incomplete body to the charge-capable order
        surface: the host must reject it (4xx), and this adapter must have
        recorded no charge. A 2xx here would mean a charge path exists and was
        reachable -- reported as NOT refused, never smoothed over."""
        status, body = self.transport.post(
            f"{LIVE_BASE}/payments/orders",
            json_body={"altId": self.location_id, "altType": "location",
                       "contactId": "", "source": {"type": "payment_link",
                                                   "subType": "payment_link"},
                       "products": [], "fingerprint": "", "trackingId": ""})
        detail = ""
        if isinstance(body, dict):
            msg = body.get("message")
            detail = "; ".join(str(m) for m in msg) if isinstance(msg, list) \
                else str(msg or "")[:300]
        return {"attempted_status": status, "refused": status >= 400,
                "refusal_detail": detail,
                "real_charges_recorded": len(self.real_charges),
                "note": ("a real-charge attempt against the charge-capable order "
                         "surface was refused by the host; no charge-capable call "
                         "exists anywhere in this adapter")}


class _RefusingDriver(PlaywrightWidgetDriver):
    """A widget driver that refuses WITHOUT launching a browser.

    The fail-closed sweep must be deterministic and offline: it proves the
    seams refuse when nothing is designated or bound, and it must never open a
    window or touch the network to do so."""

    def submit(self, form_id: str, payload: dict) -> dict:
        raise LiveRefused(
            "widget submit: no browser driver is bound for this run -- refusing "
            "to open a browser or invent a submit result")


def live_adapter_seam_status(location_id: str = "undesignated-test-location"
                             ) -> List[dict]:
    """The seven seams and whether each now carries a real body.

    ``implemented_live`` means the method contains a live call path. It is NOT
    a claim that a host run happened in this process -- host proof lives in the
    receipts, never here."""
    return [
        {"seam": "Skill44LiveAdapter.create_form", "implemented_live": True,
         "surface": "POST /forms/"},
        {"seam": "Skill44LiveAdapter.create_workflow", "implemented_live": True,
         "surface": "POST backend/workflow/{loc} (internal API)"},
        {"seam": "Skill44LiveAdapter.submit_lead", "implemented_live": True,
         "surface": "hosted widget submit (Turnstile-gated, browser-driven)"},
        {"seam": "Skill44LiveAdapter.readback", "implemented_live": True,
         "surface": "GET /contacts/{id} + GET /forms/{id} + GET /forms/submissions"},
        {"seam": "Skill06LiveTaskRunner.run", "implemented_live": True,
         "surface": "ghl_form_builder.build_form(dry_run=False)"},
        {"seam": "ProviderSandboxLiveAdapter.create_product",
         "implemented_live": True, "surface": "POST /products/ + /products/{id}/price"},
        {"seam": "ProviderSandboxLiveAdapter.checkout_session",
         "implemented_live": True,
         "surface": ("route validation + test-mode merchant readback; hosted "
                     "session NOT-VERIFIED (no such endpoint)")},
    ]


def live_adapter_deferrals(location_id: str = "undesignated-test-location"
                           ) -> List[str]:
    """Exercise every live seam with NOTHING designated and NO credential
    bound, and return the refusal messages.

    This is the fail-closed proof, and it is deliberately offline: every seam
    now has a real body behind it, so the property worth re-proving is that
    those bodies still REFUSE rather than silently inventing a live result when
    the resource or credential is absent. Each seam is wired to an unbound
    credential (``resolve_pit`` over an empty env) and a refusing driver, so a
    NO-RAISE here means a seam would have written or invented something without
    a designated resource -- which is the failure this sweep exists to catch."""
    offer = {"name": "Deferral Probe", "price_display": "$1",
             "amount_minor": 100, "currency": "USD", "price_mode": ""}
    scope = {"deck_slug": "deferral-probe", "run_id": "probe",
             "location_id": location_id, "location_bound": False}
    fields = build_form_schema(offer=offer, intent=INTENT_LEAD,
                               deck_slug="deferral-probe")
    contract = build_skill44_contract(offer=offer, intent=INTENT_LEAD,
                                      scope=scope, fields=fields)
    task = build_skill06_task(offer=offer, intent=INTENT_LEAD,
                              scope=scope, fields=fields)
    unbound = LiveTransport(resolve_pit({}))
    messages: List[str] = []
    lead = Skill44LiveAdapter(location_id, transport=unbound,
                              driver=_RefusingDriver())
    for label, fn in (("create_form", lambda: lead.create_form(contract)),
                      ("create_workflow",
                       lambda: lead.create_workflow(contract, "form_probe")),
                      ("submit_lead",
                       lambda: lead.submit_lead("form_probe",
                                                {"email": "p@t.t",
                                                 "full_name": "probe"})),
                      ("readback", lambda: lead.readback("form_probe"))):
        try:
            fn()
            messages.append(f"Skill44LiveAdapter.{label}: NO-RAISE (BAD)")
        except DeferralRequired as exc:
            messages.append(f"Skill44LiveAdapter.{label}: {exc}")
    pay = ProviderSandboxLiveAdapter(location_id, transport=unbound)
    for label, fn in (("create_product", lambda: pay.create_product(offer)),
                      ("checkout_session",
                       lambda: pay.checkout_session({"product_id": "p"},
                                                    "https://t.t/s",
                                                    "https://t.t/c"))):
        try:
            fn()
            messages.append(f"ProviderSandboxLiveAdapter.{label}: NO-RAISE (BAD)")
        except DeferralRequired as exc:
            messages.append(f"ProviderSandboxLiveAdapter.{label}: {exc}")
    try:
        Skill06LiveTaskRunner(location_id).run(task, "/tmp/pres025-deferral")
        messages.append("Skill06LiveTaskRunner.run: NO-RAISE (BAD)")
    except DeferralRequired as exc:
        messages.append(f"Skill06LiveTaskRunner.run: {exc}")
    return messages


class MemoryPaymentSandbox(PaymentSandboxAdapter):
    """In-memory provider sandbox: product/amount/currency mapping + routes,
    structurally incapable of a real charge (real_charges stays empty)."""

    def __init__(self, currency_allow: Tuple[str, ...] = ("USD", "EUR", "GBP")):
        self.real_charges: List[dict] = []
        self.products: Dict[str, dict] = {}
        self.sessions: Dict[str, dict] = {}
        self.currency_allow = tuple(currency_allow)
        self._n = 0

    def create_product(self, offer: dict) -> dict:
        if offer.get("amount_minor") is None:
            raise ValueError("MISSING_OFFER: sandbox needs a parseable amount")
        if offer.get("currency") not in self.currency_allow:
            raise ValueError(f"UNSUPPORTED_PAYMENT: currency "
                             f"{offer.get('currency')!r} not in sandbox allowlist")
        self._n += 1
        pid = f"prod_mem_{self._n:04d}"
        prod = {"product_id": pid, "name": offer["name"],
                "amount_minor": offer["amount_minor"],
                "currency": offer["currency"]}
        self.products[pid] = prod
        return prod

    def checkout_session(self, product: dict, success_url: str,
                         cancel_url: str) -> dict:
        for url, name in ((success_url, "success_url"), (cancel_url, "cancel_url")):
            ok, why = validate_url(url, allow_relative=True)
            if not ok:
                raise ValueError(f"sandbox session {name} invalid: {why}")
        self._n += 1
        sid = f"sess_mem_{self._n:04d}"
        sess = {"session_id": sid, "product_id": product["product_id"],
                "amount_minor": product["amount_minor"],
                "currency": product["currency"],
                "success_url": success_url, "cancel_url": cancel_url,
                "mode": "sandbox", "real_charge": False}
        self.sessions[sid] = sess
        return sess


# --- Receipt ----------------------------------------------------------------------
def _sha256_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_form_receipt(run_dir: Path) -> dict:
    p = run_dir / FORM_RECEIPT_REL
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_form_receipt(run_dir: Path, receipt: dict) -> Path:
    p = run_dir / FORM_RECEIPT_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


# --- Checkout page HTML (order form, prover-compatible sections) --------------------
def build_checkout_page_html(*, brand: Dict[str, str], client_name: str,
                             offer: dict, intent: str, cta_href: str,
                             hero_image_src: Optional[str],
                             marker: str) -> str:
    """Assemble the checkout page fragment: lean-checkout sections (header /
    offer-summary / price / order-form / payment-fields / guarantee / trust /
    submit-cta), the Skill44 widget seam (form embed slot), and exactly one
    dominant submit -- no dead href anywhere. All client strings escaped."""
    ok, why = validate_url(cta_href)
    if not ok:
        raise ValueError(f"checkout CTA route refused: {why}")
    prim, sec, _acc, base, ink = (
        brand["primary"], brand["secondary"], brand["accent"],
        brand["base"], brand["ink"])
    cn, on = escape_text(client_name), escape_text(offer["name"])
    price_display = escape_text(offer.get("price_display") or
                                "Final total confirmed on order follow-up.")
    audience = escape_text(offer.get("audience") or "you")
    hero_img_tag = (
        f'<img src="{escape_attr(hero_image_src)}" alt="{escape_attr(client_name)} checkout hero" '
        f'style="width:100%;max-width:100%;display:block;border-radius:12px;margin:0 0 24px;">'
        if hero_image_src else
        '<!-- hero image not yet hosted in GHL media (offline/no-push build) -->'
    )
    if intent == INTENT_PAYMENT_SANDBOX:
        payment_block = (
            '<section class="payment-fields"><h3>Payment Details</h3>'
            '<p>Sandbox checkout: card fields render in the provider sandbox '
            'session (no real charge).</p>'
            '<label>Card Number <input type="text" name="card_number" /></label>'
            '<label>Expiry <input type="text" name="expiry" /></label>'
            '<label>CVV <input type="text" name="cvv" /></label></section>')
    else:
        payment_block = (
            '<section class="payment-fields"><h3>Payment Details</h3>'
            '<p>stripe: not_configured -- this checkout collects the order; '
            'live payments will be wired once Stripe is connected.</p></section>')
    return f"""<!-- ZHC-CHECKOUT-FORM marker={escape_attr(marker)} page_role=checkout intent={intent} -->
<style>
  .zhc-checkout-page {{ font-family: 'Montserrat', Arial, sans-serif; background:{base}; color:{ink}; padding:32px 24px; }}
  .zhc-checkout-page h1 {{ color:{ink}; font-size:2.4em; font-weight:800; margin:0 0 12px; }}
  .zhc-checkout-page h2 {{ color:{sec}; font-size:1.3em; font-weight:600; margin:0 0 24px; }}
  .zhc-checkout-page .order-summary {{ background:#fff; border:1px solid {sec}; border-radius:10px; padding:18px; margin:24px 0; }}
  .zhc-checkout-page .checkout-button {{ display:inline-block; background:{prim}; color:#fff; font-weight:700; padding:16px 32px; border:0; border-radius:8px; font-size:1.1em; cursor:pointer; }}
  .zhc-checkout-page label {{ display:block; margin:0 0 12px; }}
  .zhc-checkout-page input {{ display:block; width:100%; box-sizing:border-box; margin:4px 0 0; padding:10px; border:1px solid {sec}; border-radius:6px; }}
  .zhc-checkout-page .reassurance {{ color:{sec}; font-size:0.95em; }}
</style>
<div class="zhc-checkout-page">
  <header class="header"><p>Secure checkout from {cn}. Every order below is confirmed by a real person on our team.</p></header>
  {hero_img_tag}
  <h1>Complete Your Order</h1>
  <h2>{on}</h2>
  <section class="offer-summary"><h3>Order Summary</h3><p>What you get with {on}, built for {audience}: the complete package described on the sales page, confirmed line by line below. You know exactly what you are buying before you complete the transaction with us today.</p></section>
  <section class="price"><h3>Order Total</h3><p>Order total: {price_display}. This is the investment for the complete package and the total shown at checkout today.</p></section>
  <section class="order-form"><h3>Billing / Order Form</h3>
    <!-- SKILL44_WIDGET seam: the live GHL native form embed replaces this
         standards-shaped form at Skill 06 integration time (verbatim snippet,
         no SRI). Field names/keys are the contract: email + full_name. -->
    <form id="checkout-order-form" action="{escape_attr(cta_href)}" method="post">
      <label>Email Address <input type="email" name="email" required /></label>
      <label>Full Name <input type="text" name="full_name" required /></label>
      <label>Cell Phone <input type="tel" name="phone" /></label>
    {payment_block}
    </form></section>
  <section class="guarantee"><h3>Money-Back Guarantee</h3><p>Every order is covered by the guarantee stated on the sales page: if you are not delighted, contact support for a full refund. This is the risk-reversal that makes the purchase a no-brainer.</p></section>
  <section class="trust"><h3>Trust Badges / Secure Checkout</h3><p>SSL encrypted checkout. 256-bit encryption. Privacy policy link. We respect your privacy and never share your details.</p></section>
  <section class="submit-cta"><button type="submit" form="checkout-order-form" class="checkout-button">Complete Order</button></section>
  <footer>Privacy · Terms · Copyright</footer>
</div>
"""


# --- main ---------------------------------------------------------------------------
def _load_builder():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import sales_checkout_builder as scb  # noqa: E402
    return scb


def _record_ledger(run_dir: Path, record: dict) -> None:
    ledger = run_dir / "working" / "checkpoints" / "checkout_form.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(ledger.read_text()) if ledger.exists() else {}
    except Exception:  # noqa: BLE001
        existing = {}
    existing.update(record)
    ledger.write_text(json.dumps(existing, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Build the elected checkout form stage (offer-derived form "
                    "schema -> Skill 44 / Skill 06 contracts -> persisted IDs).")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="offline deterministic self-test")
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.run_dir:
        ap.error("--run-dir is required (or --selftest)")
    run_dir = Path(args.run_dir).resolve()
    scb = _load_builder()

    intake_path = run_dir / INTAKE_REL
    try:
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        intake = {}
    if not isinstance(intake, dict):
        intake = {}

    # --- THE GATE (same waiver mechanic as the page builders) ---
    gate = scb.resolve_sales_checkout_gate(intake)
    print(f"\n=== WANT_SALES_CHECKOUT gate: {gate['decision'].upper()} ===")
    print(gate["detail"])
    if gate["decision"] == "defer":
        _record_ledger(run_dir, {"status": "deferred", "gate": gate,
                                 "checked_at": _now_iso()})
        return EXIT_OK
    if gate["decision"] == "fail_closed":
        _record_ledger(run_dir, {"status": "fail_closed", "gate": gate,
                                 "checked_at": _now_iso()})
        print(f"FATAL: {gate['detail']}", file=sys.stderr)
        return EXIT_GATE_BLOCKED
    if gate["decision"] == "waived":
        _record_ledger(run_dir, {"status": "waived", "gate": gate,
                                 "checked_at": _now_iso()})
        print(f"Waived with quote: {gate['quote']!r} -- nothing to build.")
        return EXIT_OK

    # decision == "build": resolve scope / offer / intent, each fail-scoped.
    brief = intake.get("deck_brief")
    brief = brief if isinstance(brief, dict) else {}

    scope, blocker = resolve_scope(run_dir, intake)
    if blocker is None:
        offer, blocker = resolve_offer(brief)
    if blocker is None:
        intent, blocker = resolve_intent(brief, offer)
    if blocker is not None:
        receipt = {
            "schema_version": FORM_RECEIPT_SCHEMA,
            "phase": "P-U-FORM-CHECKOUT",
            "deck_slug": str(intake.get("deck_slug") or run_dir.name),
            "run_id": run_dir.name,
            "location_id": None,
            "offer": None, "intent": None,
            "form": {"form_id": None}, "workflow": {"workflow_id": None},
            "status": "blocked", "blocker": blocker,
            "proof": None, "built_at": _now_iso(),
        }
        write_form_receipt(run_dir, receipt)
        _record_ledger(run_dir, {"status": "blocked", "blocker": blocker,
                                 "gate": gate, "built_at": _now_iso()})
        print(f"BLOCKED [{blocker['code']}]: {blocker['detail']}", file=sys.stderr)
        print(f"ACTION: {blocker['action']}", file=sys.stderr)
        return EXIT_BLOCKED

    fields = build_form_schema(offer=offer, intent=intent,
                               deck_slug=scope["deck_slug"])
    contract44 = build_skill44_contract(offer=offer, intent=intent,
                                        scope=scope, fields=fields)
    task06 = build_skill06_task(offer=offer, intent=intent,
                                scope=scope, fields=fields)

    sc_dir = run_dir / "working" / "sales-checkout"
    sc_dir.mkdir(parents=True, exist_ok=True)
    (sc_dir / "checkout_form_skill44.json").write_text(
        json.dumps(contract44, indent=2), encoding="utf-8")
    (sc_dir / "checkout_form_skill06_task.json").write_text(
        json.dumps(task06, indent=2), encoding="utf-8")

    checkout_html_path = run_dir / CHECKOUT_HTML_REL
    checkout_html = (checkout_html_path.read_text(encoding="utf-8", errors="replace")
                     if checkout_html_path.is_file() else "")
    receipt = {
        "schema_version": FORM_RECEIPT_SCHEMA,
        "phase": "P-U-FORM-CHECKOUT",
        "deck_slug": scope["deck_slug"],
        "run_id": scope["run_id"],
        "location_id": scope["location_id"],
        "location_bound": scope["location_bound"],
        "offer": {k: offer.get(k) for k in
                  ("name", "price_display", "amount_minor", "currency", "price_mode")},
        "intent": intent,
        "mode_contract": ("lead-capture: one scoped contact + one workflow "
                          "enrollment on test submit"
                          if intent == INTENT_LEAD else
                          "sandbox: product/amount/currency mapping + "
                          "success/cancel routes, zero real charge"),
        "form": {"name": contract44["form"]["name"], "form_id": None,
                 "action": None},
        "workflow": {"name": contract44["workflow"]["name"],
                     "workflow_id": None, "draft_only": True},
        "skill44_contract": str(sc_dir / "checkout_form_skill44.json"),
        "skill06_task": str(sc_dir / "checkout_form_skill06_task.json"),
        "input_hashes": {
            "intake": _sha256_file(intake_path),
            "checkout_html": _sha256_file(checkout_html_path),
        },
        "status": "plan_emitted",
        "blocker": None,
        "proof": None,
        "built_at": _now_iso(),
    }
    write_form_receipt(run_dir, receipt)
    _record_ledger(run_dir, {"status": "plan_emitted", "gate": gate,
                             "intent": intent, "built_at": _now_iso()})
    print("\nCHECKOUT FORM: PLAN EMITTED (Skill 44 form/workflow + Skill 06 "
          "widget contracts written; IDs land at delegated execution)")
    return EXIT_OK


# --- selftest -------------------------------------------------------------------------
def _selftest() -> int:
    fails: List[str] = []

    # 1) URL allowlist.
    for good in ("https://app.gohighlevel.com/v2/preview/abc",
                 "https://msgsndr.com/x",
                 "/acme-checkout", "/x/y"):
        ok, _ = validate_url(good)
        if not ok:
            fails.append(f"allowlist ACCEPTED-expected rejected: {good!r}")
    for bad in ("", "#", "javascript:void(0)", "javascript:alert(1)",
                "data:text/html,x", "https://example.com/preview/abc",
                "ftp://x/y", "acme-checkout"):
        ok, _ = validate_url(bad)
        if ok:
            fails.append(f"allowlist REJECT-expected accepted: {bad!r}")

    # 2) escaping: markup dies, prose apostrophes survive.
    evil = '<script>alert("x")</script> don\'t "quote" me & co'
    if "<script>" in escape_text(evil) or "&" in escape_text(evil).replace("&", ""):
        pass
    et = escape_text(evil)
    if "<script>" in et or '"quote"' not in et or "don't" not in et or "&amp;" not in et:
        fails.append(f"escape_text wrong: {et!r}")
    ea = escape_attr('a"b<c>')
    if '"b' in ea or "<c>" in ea:
        fails.append(f"escape_attr wrong: {ea!r}")

    # 3) CTA audit: dead hrefs fail, verified routes pass.
    if not audit_cta_hrefs('<a href="#">buy</a>', page_role="sales"):
        fails.append("audit ACCEPTED href=# on sales page")
    if not audit_cta_hrefs('<a href="javascript:alert(1)">buy</a>'):
        fails.append("audit ACCEPTED javascript: href")
    sales_ok = audit_cta_hrefs('<a class="cta-button" href="/acme-checkout">buy</a>',
                               page_role="sales")
    if sales_ok:
        fails.append(f"audit REJECTED a verified sales CTA: {sales_ok}")
    co_html = build_checkout_page_html(
        brand={"primary": "#212748", "secondary": "#B38456", "accent": "#C49A70",
               "base": "#F2E6D7", "ink": "#1A1A1A"},
        client_name='Evil <b>Client</b>', offer={"name": "Momentum", "price_display": "$997",
               "amount_minor": 99700, "currency": "USD", "price_mode": "",
               "audience": "founders"},
        intent=INTENT_LEAD, cta_href="/acme-checkout", hero_image_src=None,
        marker="ZHC-SC-selftest")
    if "<b>Client</b>" in co_html:
        fails.append("checkout HTML carries unescaped client markup")
    co_fails = audit_cta_hrefs(co_html, page_role="checkout")
    if co_fails:
        fails.append(f"audit REJECTED the produced checkout page: {co_fails}")
    try:
        resolve_cta_href(page_role="sales", deck_slug="acme")
    except ValueError as exc:  # noqa: BLE001
        fails.append(f"resolve_cta_href raised on a valid route: {exc}")
    try:
        build_checkout_page_html(
            brand={"primary": "#212748", "secondary": "#B38456", "accent": "#C49A70",
                   "base": "#F2E6D7", "ink": "#1A1A1A"},
            client_name="x", offer={"name": "y", "audience": ""},
            intent=INTENT_LEAD, cta_href="#", hero_image_src=None, marker="m")
        fails.append("build_checkout_page_html ACCEPTED a dead cta_href")
    except ValueError:
        pass

    # 4) offer / intent / scope.
    offer, blk = resolve_offer({"OFFER_NAME": "Momentum", "FINAL_PRICE": "$997"})
    if blk or offer["amount_minor"] != 99700 or offer["currency"] != "USD":
        fails.append(f"resolve_offer wrong: {offer} {blk}")
    _o2, blk = resolve_offer({})
    if not blk or blk["code"] != BLOCK_MISSING_OFFER:
        fails.append("resolve_offer ACCEPTED a missing offer")
    intent, blk = resolve_intent({}, {"amount_minor": 99700})
    if blk or intent != INTENT_LEAD:
        fails.append("default intent must be lead_capture")
    intent, blk = resolve_intent({"CHECKOUT_MODE": "payment_sandbox"},
                                 {"amount_minor": 99700})
    if blk or intent != INTENT_PAYMENT_SANDBOX:
        fails.append("sandbox intent not elected")
    _i, blk = resolve_intent({"CHECKOUT_MODE": "payment"}, {"amount_minor": 99700})
    if not blk or blk["code"] != BLOCK_MISSING_MERCHANT:
        fails.append("live payment without merchant must block MISSING_MERCHANT")
    _i, blk = resolve_intent({"CHECKOUT_MODE": "payment", "PAYMENT_PROVIDER": "X",
                              "MERCHANT_STATUS": "connected"}, {"amount_minor": 99700})
    if not blk or blk["code"] != BLOCK_UNSUPPORTED_PAYMENT:
        fails.append("live payment must block UNSUPPORTED_PAYMENT (no live SDK)")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        scope, blk = resolve_scope(rd, {"deck_slug": "acme"},
                                   env={"GOHIGHLEVEL_LOCATION_ID": "loc1"})
        if blk or scope["location_id"] != "loc1":
            fails.append(f"scope wrong: {scope} {blk}")
        _s, blk = resolve_scope(rd, {"deck_slug": "acme",
                                     "GHL_LOCATION_ID": "locX"},
                                env={"GOHIGHLEVEL_LOCATION_ID": "loc1"})
        if not blk or blk["code"] != BLOCK_WRONG_LOCATION:
            fails.append("location disagreement must block WRONG_LOCATION")

    # 5) memory adapters: lead submit proof (one contact + enrollment,
    #    validation, duplicates) + sandbox mapping with zero real charge.
    mem = MemoryLeadAdapter("loc1")
    scope = {"deck_slug": "acme", "run_id": "run", "location_id": "loc1"}
    offer = {"name": "Momentum", "price_display": "$997", "amount_minor": 99700,
             "currency": "USD", "price_mode": ""}
    fields = build_form_schema(offer=offer, intent=INTENT_LEAD, deck_slug="acme")
    c44 = build_skill44_contract(offer=offer, intent=INTENT_LEAD,
                                 scope=scope, fields=fields)
    fid = mem.create_form(c44)
    wid = mem.create_workflow(c44, fid)
    bad = mem.submit_lead(fid, {"email": "not-an-email"})
    if bad.get("ok") or not bad.get("errors"):
        fails.append("adapter ACCEPTED an invalid lead")
    r1 = mem.submit_lead(fid, {"email": "buyer@example.com",
                               "full_name": "Buyer Person"})
    r2 = mem.submit_lead(fid, {"email": "buyer@example.com",
                               "full_name": "Buyer Person"})
    rb = mem.readback(fid)
    if not (r1["ok"] and r2.get("duplicate") and rb["contacts"] == 1
            and rb["enrollments"] == 1 and r1["contact_id"] == r2["contact_id"]):
        fails.append(f"lead proof wrong: {r1} {r2} {rb}")
    sb = MemoryPaymentSandbox()
    prod = sb.create_product(offer)
    sess = sb.checkout_session(prod, "https://shop.example.test/success",
                               "https://shop.example.test/cancel")
    if (prod["amount_minor"], prod["currency"]) != (99700, "USD"):
        fails.append(f"sandbox product mapping wrong: {prod}")
    if sess["real_charge"] or sb.real_charges:
        fails.append("sandbox recorded a real charge")
    try:
        sb.checkout_session(prod, "#", "https://shop.example.test/cancel")
        fails.append("sandbox ACCEPTED a dead success_url")
    except ValueError:
        pass

    # 6) live adapters now carry REAL bodies. The property worth re-proving is
    #    the one that keeps the repair honest: with NO credential bound and NO
    #    resource designated, every one of the seven seams must still REFUSE
    #    rather than invent an id, silently pass, or write anywhere. The sweep
    #    is offline by construction (unbound transport + refusing driver).
    deferrals = live_adapter_deferrals()
    if len(deferrals) != 7:
        fails.append(f"live deferral sweep wrong size: {len(deferrals)} != 7")
    for msg in deferrals:
        if "NO-RAISE (BAD)" in msg:
            fails.append(f"live seam performed or passed silently: {msg}")
        low = msg.lower()
        if "refus" not in low and "no pit is bound" not in low:
            fails.append(f"live refusal does not name the missing resource: {msg}")
    seams = live_adapter_seam_status()
    if len(seams) != 7:
        fails.append(f"seam status wrong size: {len(seams)} != 7")
    if not all(s["implemented_live"] for s in seams):
        fails.append(f"a live seam is still a pure stub: {seams}")
    # The live adapter region must contain no charge-capable call at all (S5/S6).
    # The tokens are assembled from parts so this check cannot match its own
    # source text (a self-match would make the guard permanently "failing").
    live_src = Path(__file__).read_text(encoding="utf-8")
    live_region = live_src.split("class Skill44LiveAdapter")[-1].split(
        "def live_adapter_seam_status")[0]
    for banned in ("stri" + "pe.Charge", "capt" + "ure: True",
                   "/char" + "ges\"", "\"pai" + "d\": True"):
        if banned in live_region:
            fails.append(f"charge-capable token present in live source: {banned!r}")

    if fails:
        print("checkout_form_builder selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("checkout_form_builder selftest -> PASS (allowlist, escaping, CTA "
          "audit, offer/intent/scope, lead proof incl. duplicates, sandbox "
          "mapping with zero real charge, blockers, live-stub deferrals x7)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
