"""Accessible HTML renderer for the Skill 82 terminal thank-you page
(S82-04 layout/copy profiles, S82-06 delayed/pending/error states).

Input is the order view produced by scripts/thank_you_resolver.py
(schemas/order-view.schema.json) plus simple brand tokens:

    {
      "brand_name": "Example Brand",
      "colors": {"primary": "#...", "accent": "#...",
                 "background": "#...", "text": "#..."},
      "support": {"label": "Contact support",
                  "email": "support@example.test" | "url": "https://..."},
      "manage_purchase_url": "https://...",
      "hero_image": {"src": "https://...", "shape": "rect" | "circle"}   # optional
    }

``hero_image`` is the page's one celebration image (Skill 71 slot TY-IMG-01,
see hero_image_from_map and references/wireframe-mockup-layout.md). It is
decorative (empty alt text), placed in the header of the normal confirmation
layout only, never in an error or reconciling fragment, so the built page
matches the approved mockup without ever carrying order data in an image.

Output is ONE self-contained HTML fragment (a <section class="ty82"> with
its own namespaced <style>; every class is prefixed ``ty82-``). It is a
fragment, not a full document, so hosting guidance that belongs to the
host page (no-store cache headers, robots noindex meta) is emitted as
HTML comments at the top of the fragment — see references/states.md.
A robots tag alone is NOT the security boundary; the host must also send
``Cache-Control: private, no-store`` and the access destinations must
independently authorize the buyer (spec 12 sections 6 and 8).

Renderer modes (``state`` argument, or keys on the view):

- normal (default): the confirmation layout of spec 12 section 4.
- ``reconciling``: delayed-event reconciliation (spec section 5). Bounded
  automatic rechecks (delays in RETRY_DELAYS_SECONDS, then stop) with a
  manual "Check again" action, a confirmation-email access fallback and
  a support route. Refreshing NEVER initiates a purchase.
- ``outage_cached``: provider outage. Only previously verified cached
  view data is shown, and items that could not be re-checked are listed
  under an explicit "Unresolved items" label.
- ``error``: one of ``wrong_order_reference``, ``stale_session``,
  ``native_read_failure``. Error fragments contain NO order data and
  never a fake/sample receipt — only an explanation and a support
  fallback.

Every action rendered is an <a> or <button> carrying a
``data-cta-class`` attribute whose value is one of the allowed no-pitch
classifications (references/no-pitch-policy.md section 2). Nothing in
this renderer can initiate a new charge or present a new offer.

All untrusted text (display names, brand strings, URLs) is escaped with
html.escape; URLs are restricted to http/https/mailto/fragment schemes.

Stdlib only. Deterministic: no clock, no randomness, no network.
"""

import urllib.parse
import functools
import html
import json
import re
from pathlib import Path

# Allowed CTA classifications (spec 12 section 7; no-pitch policy section 2).
ALLOWED_CTA_CLASSES = {
    "access",
    "download",
    "manage_purchase",
    "support",
    "schedule_included_service",
    "noncommercial_next_step",
}

# Bounded reconciliation policy (spec 12 section 5): an initial render plus
# at most this many automatic rechecks, waiting RETRY_DELAYS_SECONDS[i]
# before recheck i+1. After the budget is exhausted the page stops
# refreshing and points at the email/support fallback. Never unbounded.
RETRY_DELAYS_SECONDS = (5, 15, 30, 60)
MAX_RECONCILIATION_CHECKS = 1 + len(RETRY_DELAYS_SECONDS)

STATUS_LABELS = {
    "paid": "Paid",
    "pending": "Pending",
    "failed": "Failed",
    "requires_customer_action": "Action needed",
    "refunded": "Refunded",
    "partially_refunded": "Partially refunded",
    "unknown": "Confirming",
}

CONFIRMATION_LABELS = {
    "confirmed": "Confirmed",
    "partially_pending": "Partly pending",
    "pending": "Pending",
    "attention_required": "Needs attention",
    "refund_applied": "Refund applied",
    "partially_refunded": "Partially refunded",
}

ERROR_KINDS = ("wrong_order_reference", "stale_session", "native_read_failure")

_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}

# ISO 4217 minor-unit exponents (DTY-33). Mirrors the zero- and three-decimal
# entries of MINOR_UNIT_EXPONENTS in 80-signature-upsell/components/adapters/
# adapter_common.py; tests/test_render_thank_you.py fails if the two drift.
# A currency not listed here is refused, never printed with a guessed exponent
# (CLF and UYW carry four decimals and are deliberately unsupported).
_CURRENCY_EXPONENTS = {
    **dict.fromkeys(
        "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF".split(), 0),
    **dict.fromkeys("BHD IQD JOD KWD LYD OMR TND".split(), 3),
    **dict.fromkeys(
        "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BMD BND BOB BRL BSD BTN "
        "BWP BYN BZD CAD CDF CHF CNY COP CRC CUP CVE CZK DKK DOP DZD EGP ERN ETB EUR FJD "
        "FKP GBP GEL GHS GIP GMD GTQ GYD HKD HNL HTG HUF IDR ILS INR IRR JMD KES KGS KHR "
        "KPW KYD KZT LAK LBP LKR LRD LSL MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN "
        "MYR MZN NAD NGN NIO NOK NPR NZD PAB PEN PGK PHP PKR PLN QAR RON RSD RUB SAR SBD "
        "SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TOP TRY TTD TWD "
        "TZS UAH USD UYU UZS VES WST XCD YER ZAR ZMW ZWL".split(), 2),
}
_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\))$"
)
_SAFE_URL_PREFIXES = ("https://", "mailto:", "#", "/")


def _esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def _color(value, default):
    """Brand colors are untrusted input: accept only simple color tokens."""
    if isinstance(value, str) and _COLOR_RE.match(value.strip()):
        return value.strip()
    return default


def _safe_url(value, default="#"):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("//", "/\\")):  # protocol-relative: leaves the page's own origin
            return default
        if stripped.lower().startswith(_SAFE_URL_PREFIXES):
            return stripped
    return default


def _https_access_url(value):
    """A delivery link is shown only when it is an absolute https URL with a host (DTY-18)."""
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlparse(value.strip())
    return value.strip() if parsed.scheme == "https" and parsed.netloc else None


def format_amount(amount_minor, currency):
    """Integer minor units -> display amount using the currency's own exponent
    (JPY 0, USD 2, KWD 3). No floats for money math; an unknown currency is refused."""
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor < 0:
        raise ValueError(f"amount_minor must be a non-negative integer: {amount_minor!r}")
    exponent = _CURRENCY_EXPONENTS.get(currency)
    if exponent is None:
        raise ValueError(f"unsupported currency: {currency!r}")
    whole, frac = divmod(amount_minor, 10 ** exponent)
    major = f"{whole:,}.{frac:0{exponent}d}" if exponent else f"{whole:,}"
    symbol = _CURRENCY_SYMBOLS.get(currency)
    return f"{symbol}{major}" if symbol else f"{currency} {major}"


def _brand_support(brand):
    brand = brand or {}
    support = brand.get("support") or {}
    if not isinstance(support, dict):
        support = {}
    label = (support.get("label") or brand.get("support_label")
             or "Contact support")
    href = support.get("url") or brand.get("support_url")
    email = support.get("email") or brand.get("support_email") \
        or brand.get("support_contact")
    if not href and email:
        href = f"mailto:{email}"
    return label, _safe_url(href, "#support")


def _support_link(brand, css_class="ty82-button ty82-button--secondary"):
    label, href = _brand_support(brand)
    return (f'<a class="{css_class}" data-cta-class="support" '
            f'href="{_esc(href)}">{_esc(label)}</a>')


HERO_SLOT_ID = "TY-IMG-01"


def hero_image_from_map(image_map, slot_id=HERO_SLOT_ID, shape="rect"):
    """The hero image brand token from Skill 71's image-map-upload/image-map.json (either
    dialect: an ``images`` list whose entries carry id or master_id and asset_file,
    asset_path, file or filename), or None when the map has no entry for the slot."""
    entries = image_map.get("images") if isinstance(image_map, dict) else None
    for entry in entries or []:
        if not isinstance(entry, dict) or slot_id not in (entry.get("id"), entry.get("master_id")):
            continue
        for key in ("asset_file", "asset_path", "file", "filename"):
            if entry.get(key):
                return {"src": str(entry[key]), "shape": shape}
    return None


def _hero_html(brand):
    """The page's one celebration image: decorative, from a safe URL, or nothing."""
    hero = (brand or {}).get("hero_image")
    src = _safe_url(hero.get("src"), "") if isinstance(hero, dict) else ""
    if not src:
        return ""
    shape = "circle" if hero.get("shape") == "circle" else "rect"
    return (f'<figure class="ty82-hero ty82-hero--{shape}">'
            f'<img src="{_esc(src)}" alt=""></figure>')


def _style_block(brand):
    colors = (brand or {}).get("colors") or {}
    primary = _color(colors.get("primary"), "#1a56db")
    accent = _color(colors.get("accent"), "#057a55")
    background = _color(colors.get("background"), "#ffffff")
    text = _color(colors.get("text"), "#111111")
    return f"""<style>
.ty82 {{ --ty82-primary: {primary}; --ty82-accent: {accent};
  --ty82-background: {background}; --ty82-text: {text};
  background: var(--ty82-background); color: var(--ty82-text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5; max-width: 44rem; margin: 0 auto; padding: 1rem; }}
.ty82 * {{ box-sizing: border-box; }}
.ty82-headline {{ font-size: 1.6rem; margin: 0 0 .5rem; }}
.ty82-reassurance {{ margin: 0 0 1rem; }}
.ty82-hero {{ margin: 0 0 1rem; }}
.ty82-hero img {{ display: block; max-width: 100%; height: auto; }}
.ty82-hero--circle img {{ border-radius: 50%; }}
.ty82-order-ref {{ font-weight: 600; }}
.ty82-button {{ display: inline-block; padding: .6rem 1rem; border-radius: .375rem;
  border: 2px solid var(--ty82-primary); text-decoration: none; font-weight: 600;
  margin: .25rem .5rem .25rem 0; }}
.ty82-button:focus-visible, .ty82 a:focus-visible, .ty82 button:focus-visible
  {{ outline: 3px solid var(--ty82-accent); outline-offset: 2px; }}
.ty82-button--primary {{ background: var(--ty82-primary); color: #ffffff; }}
.ty82-button--secondary {{ background: transparent; color: var(--ty82-primary); }}
.ty82-status-pill {{ display: inline-block; padding: .1rem .6rem; border-radius: 999px;
  font-size: .85rem; font-weight: 700; border: 2px solid currentColor; }}
.ty82-status--paid {{ color: #046c4e; }}
.ty82-status--pending, .ty82-status--unknown,
.ty82-status--requires_customer_action {{ color: #92400e; }}
.ty82-status--failed {{ color: #b91c1c; }}
.ty82-status--refunded, .ty82-status--partially_refunded {{ color: #4b5563; }}
.ty82-table {{ border-collapse: collapse; width: 100%; }}
.ty82-table th, .ty82-table td {{ text-align: left; padding: .5rem;
  border-bottom: 1px solid #d1d5db; vertical-align: top; }}
.ty82-table caption {{ text-align: left; font-weight: 600; padding: .5rem 0; }}
.ty82-access-block {{ border: 1px solid #d1d5db; border-radius: .5rem;
  padding: .75rem 1rem; margin: .5rem 0; }}
.ty82-cards {{ display: grid; gap: .75rem;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); }}
.ty82-icon {{ color: var(--ty82-primary); }}
.ty82-steps {{ padding-left: 1.5rem; }}
.ty82-steps li {{ margin: .5rem 0; }}
.ty82-close {{ margin-top: 1rem; }}
.ty82-signature {{ font-family: "Snell Roundhand", "Segoe Script", cursive;
  font-size: 1.6rem; margin: 0; }}
.ty82-banner {{ border: 2px solid #92400e; border-radius: .5rem;
  padding: .75rem 1rem; margin: 1rem 0; }}
.ty82-spinner {{ display: inline-block; width: 1rem; height: 1rem;
  border: 3px solid #d1d5db; border-top-color: var(--ty82-primary);
  border-radius: 50%; animation: ty82-spin 1s linear infinite; }}
@keyframes ty82-spin {{ to {{ transform: rotate(360deg); }} }}
@media (prefers-reduced-motion: reduce) {{ .ty82-spinner {{ animation: none; }} }}
@media (max-width: 40rem) {{ .ty82-table th, .ty82-table td {{ padding: .4rem .25rem; }}
  .ty82-button {{ display: block; text-align: center; }} }}
</style>"""


_HOSTING_GUIDANCE = """<!--
  ty82 hosting guidance (spec 12 section 8): the host page MUST send
  "Cache-Control: private, no-store" for this receipt and SHOULD carry
  <meta name="robots" content="noindex, nofollow">. A robots tag alone is
  NOT privacy: never link to this page with customer data in the URL, and
  never treat this fragment as the security boundary for access — every
  destination linked below must independently authorize the buyer.
-->"""


TERMS_UNAVAILABLE = "terms unavailable - contact support"

# billing_type -> the word that leads the Billing cell. A missing type with no
# terms is the one-time default; any other type is rendered from its own terms
# or refused (DTY-17: never "One-time charge" over a trial or an installment).
_BILLING_LEAD = {
    "recurring": "Recurring",
    "trial_then_recurring": "Recurring",
    "installment": "Installments",
    "installments": "Installments",
    "trial": "Trial",
}


def _schedule_entry(entry, currency):
    """One verified schedule row as text, or None when it cannot be shown completely.
    Rows carry label and/or a date (``due``; ``date``/``charge_date`` are aliases)."""
    if not isinstance(entry, dict):
        return _esc(entry) if entry else None
    when = entry.get("due") or entry.get("date") or entry.get("charge_date")
    label = entry.get("label")
    amount = entry.get("amount_minor")
    money = format_amount(amount, currency) if isinstance(amount, int) else None
    if label:
        piece = _esc(label)
        if when and str(when) not in str(label):
            piece += f" ({_esc(when)})"
        return piece + (f": {money}" if money else "")
    if when:
        return f"{money} on {_esc(when)}" if money else _esc(when)
    return None


def _item_billing_text(item, default_currency=""):
    billing = item.get("billing") or {}
    billing_type = billing.get("billing_type") or None
    interval = billing.get("recurring_interval")
    schedule = billing.get("schedule") or []
    if billing_type in (None, "one_time") and not (interval or schedule):
        return "One-time charge"
    lead = _BILLING_LEAD.get(billing_type) or (
        "Recurring" if billing_type is None else None)
    if lead is None or not (interval or schedule) or not isinstance(schedule, list):
        return TERMS_UNAVAILABLE
    currency = item.get("currency") or default_currency
    entries = [_schedule_entry(entry, currency) for entry in schedule]
    if None in entries or (lead != "Recurring" and not entries):
        return TERMS_UNAVAILABLE
    every = f" — every {_esc(interval)}" if interval else ""
    if lead == "Trial":
        days = billing.get("trial_days")
        head = f"Trial ({_esc(days)} days)" if days else "Trial period"
        return f"{head}, then {'; '.join(entries)}" + (
            f" (renews every {_esc(interval)})" if interval else "")
    return f"{lead}{every}" + (f" ({'; '.join(entries)})" if entries else "")


def _status_span(status):
    label = STATUS_LABELS.get(status, STATUS_LABELS["unknown"])
    return (f'<span class="ty82-status-pill ty82-status--{_esc(status)}">'
            f'{_esc(label)}</span>')


_TWIN_PATH = (Path(__file__).resolve().parents[2] / "71-blackceo-signature-page"
              / "references" / "copy-specs" / "thank-you-v1.json")
_TWIN_FALLBACK = {
    "names": {"1": "Confirmation and welcome", "2": "Order summary", "3": "Access",
              "4": "What happens next", "5": "Help, manage and close"},
    "steps": (4, 6), "close_max": 170,
}


@functools.lru_cache(maxsize=1)
def _twin():
    """Section names, step bounds and signed-close cap from thank-you-v1.json, the
    one file the mockup stages also read (DTY-24). The built-in values are the same
    ones, used only when the Skill 71 checkout is absent; the tests pin them together."""
    try:
        spec = json.loads(_TWIN_PATH.read_text(encoding="utf-8"))
        sections = {s["id"]: s for s in spec["sections"]}
        steps = sections["4"]["step_rules"]["step_count"]
        return {"names": {i: s["name"] for i, s in sections.items()},
                "steps": (steps["min"], steps["max"]),
                "close_max": sections["5"]["limits"][0]["max"]}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return _TWIN_FALLBACK


def _section_attrs(number):
    return f'data-ty82-section="{number}" data-ty82-section-name="{_esc(_twin()["names"][number])}"'


# Headlines for an order whose main purchase is not paid (DTY-32): the resolver's
# "confirmed purchases" wording is only true over a paid main.
_UNPAID_MAIN_HEADLINES = {
    "failed": "Your main purchase did not go through. Each item below is labeled "
              "with its own status, and only items marked Paid were charged.",
    "refunded": "A refund was applied to your main purchase. Each item below is "
                "labeled with its current state.",
    "partially_refunded": "Part of your main purchase was refunded. Each item below "
                          "is labeled with its current state.",
}
_UNPAID_MAIN_DEFAULT = ("Your main purchase is still being processed. Each item "
                        "below is labeled with its own status.")


def _honest_headline(view):
    headline = (view.get("confirmation") or {}).get("headline") or "Your purchase"
    if "confirmed" not in headline.lower():
        return headline
    main = next((i for i in view.get("items") or [] if i.get("slot") == "main"), {})
    status = main.get("display_status")
    if status == "paid":
        return headline
    return _UNPAID_MAIN_HEADLINES.get(status, _UNPAID_MAIN_DEFAULT)


def _order_summary_section(view):
    currency = (view.get("totals") or {}).get("currency", "")
    rows = []
    for item in view.get("items") or []:
        rows.append(
            "<tr>"
            f'<th scope="row">{_esc(item.get("display_name"))}</th>'
            f"<td>{_status_span(item.get('display_status'))}</td>"
            f"<td>{_item_billing_text(item, currency)}</td>"
            f'<td>{format_amount(item.get("amount_minor", 0), item.get("currency", currency))}</td>'
            "</tr>"
        )
    totals = view.get("totals") or {}
    total_rows = [
        f'<tr><th scope="row">Total paid</th><td colspan="2"></td>'
        f'<td>{format_amount(totals.get("paid_total_minor", 0), currency)}</td></tr>'
    ]
    if totals.get("pending_total_minor"):
        total_rows.append(
            '<tr><th scope="row">Pending (not yet confirmed)</th>'
            '<td colspan="2"></td>'
            f'<td>{format_amount(totals["pending_total_minor"], currency)}</td></tr>'
        )
    body = "\n".join(rows + total_rows)
    return f"""<section class="ty82-order" {_section_attrs("2")} aria-labelledby="ty82-order-heading">
<h2 id="ty82-order-heading">Your order</h2>
<table class="ty82-table">
<caption>Order summary for order {_esc(view.get("order_number"))}. Amounts are the actual charges from your verified purchase record.</caption>
<thead><tr><th scope="col">Item</th><th scope="col">Status</th><th scope="col">Billing</th><th scope="col">Amount</th></tr></thead>
<tbody>
{body}
</tbody>
</table>
</section>"""


_ICONS = {
    "access": '<path d="M7 11V8a5 5 0 0 1 9-3M5 11h14v9H5z"/>',
    "download": '<path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/>',
    "schedule_included_service": '<path d="M4 6h16v14H4zM4 11h16M9 3v4m6-4v4"/>',
    "pending": '<path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 5v5l3 2"/>',
}


def _icon(kind):
    return ('<svg class="ty82-icon" aria-hidden="true" viewBox="0 0 24 24" width="32" '
            'height="32" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{_ICONS[kind]}</svg>')


def _access_section(view):
    """Section 3: one icon card per paid item. A paid item whose access is not
    granted yet says so (DTY-32) instead of staying silent."""
    items = view.get("items") or []
    names = {i.get("offer_id"): i.get("display_name") for i in items}
    blocks = {}
    for block in view.get("access_blocks") or []:
        blocks.setdefault(block.get("offer_id"), []).append(block)
    offers = [i.get("offer_id") for i in items if i.get("display_status") == "paid"]
    offers += [o for o in blocks if o not in offers]
    cards = []
    for offer_id in offers:
        name = names.get(offer_id) or offer_id
        buttons, kind = [], "pending"
        for block in blocks.get(offer_id, []):
            url = _https_access_url(block.get("delivery_url"))
            if not url:
                continue
            action = block.get("next_action") or "access"
            if action not in ALLOWED_CTA_CLASSES:
                action = "access"
            kind = kind if buttons else action
            buttons.append(
                f'<a class="ty82-button ty82-button--primary" '
                f'data-cta-class="{_esc(action)}" href="{_esc(_safe_url(url))}">'
                f'{_esc(action.replace("_", " ").title())}: {_esc(name)}</a>')
        if not buttons:
            buttons = ["<p>Status: paid, access being prepared. It will also arrive "
                       "by email; contact support if it does not.</p>"]
        cards.append(
            '<div class="ty82-access-block">'
            f'{_icon(kind if kind in _ICONS else "access")}<h3>{_esc(name)}</h3>'
            f'<p>Your access to this purchase.</p>{"".join(buttons)}</div>')
    body = "".join(cards) or ("<p>Access for each item appears here once it is paid "
                              "and ready.</p>")
    return f"""<section class="ty82-access" {_section_attrs("3")} aria-labelledby="ty82-access-heading">
<h2 id="ty82-access-heading">Your access</h2>
<p>These links open only what you purchased. Each destination checks your account before letting you in.</p>
<div class="ty82-cards">{body}</div>
</section>"""


def _next_steps(view):
    """Four to six numbered steps (twin: section 4), each from the verified view."""
    items = {i.get("offer_id"): i for i in view.get("items") or []}

    def name(offer_id):
        return _esc((items.get(offer_id) or {}).get("display_name", offer_id))

    steps = ["Check your email: your receipt and access details are on their way."]
    if view.get("access_blocks"):
        steps.append("Use the links under “Your access” to start. Access also "
                     "arrives by email, so you can leave this page and come back later.")
    else:
        steps.append("Watch your email for your access details; access is being "
                     "prepared and nothing more is needed from you.")
    pending = [o for o in view.get("pending_items") or []]
    if pending:
        steps.append(" ".join(
            f"{name(o)} is still being confirmed. Delivery for it starts when its "
            "payment is confirmed, and we will email you — you do not need to buy "
            "it again." for o in pending))
    failed = [o for o in view.get("failed_items") or []]
    if failed:
        unaffected = ("Your paid items above are not affected."
                      if any(i.get("display_status") == "paid" for i in items.values())
                      else "Nothing was charged for it.")
        steps.append(" ".join(
            f"{name(o)} did not go through, so there is no charge or access for it."
            for o in failed) + f" {unaffected}")
    steps.append(f"Keep your order reference ({_esc(view.get('order_number'))}) "
                 "handy if you need help.")
    steps.append("Use Contact support or Manage your purchase below if anything "
                 "looks wrong.")
    return steps[:_twin()["steps"][1]]


def _next_steps_section(view, brand):
    items_html = "".join(f"<li>{step}</li>" for step in _next_steps(view))
    return f"""<section class="ty82-next" {_section_attrs("4")} aria-labelledby="ty82-next-heading">
<h2 id="ty82-next-heading">What happens next</h2>
<ol class="ty82-steps">{items_html}</ol>
</section>"""


_DEFAULT_CLOSE = ("Thank you for choosing us. We are glad you are here, and we are "
                  "ready to help with anything you need.")


def _signed_close_html(brand):
    """The short signed note of thanks (twin: section 5, up to 170 characters)."""
    note = brand.get("closing_note")
    if not isinstance(note, str) or not note.strip() or len(note) > _twin()["close_max"]:
        note = _DEFAULT_CLOSE
    signature = brand.get("signature") or brand.get("brand_name") or brand.get("name") \
        or "The team"
    return (f'<div class="ty82-close"><p class="ty82-close-note">{_esc(note)}</p>'
            f'<p class="ty82-signature">{_esc(signature)}</p></div>')


def _manage_support_section(view, brand):
    manage_url = _safe_url(
        (brand or {}).get("manage_purchase_url"), "#manage-purchase")
    ctas = [c for c in view.get("ctas") or []
            if not c.get("entitlement_id")]
    rendered = []
    seen = set()
    for cta in ctas:
        cls = cta.get("classification")
        if cls not in ALLOWED_CTA_CLASSES or cls in seen:
            continue
        seen.add(cls)
        if cls == "support":
            rendered.append(_support_link(brand))
        elif cls == "manage_purchase":
            rendered.append(
                f'<a class="ty82-button ty82-button--secondary" '
                f'data-cta-class="manage_purchase" href="{_esc(manage_url)}">'
                f'{_esc(cta.get("label") or "Manage your purchase")}</a>'
            )
        else:
            rendered.append(
                f'<span class="ty82-note">{_esc(cta.get("label"))}</span>')
    if "support" not in seen:
        rendered.append(_support_link(brand))
    return f"""<section class="ty82-help" {_section_attrs("5")} aria-labelledby="ty82-help-heading">
<h2 id="ty82-help-heading">Help and your purchase</h2>
<p>Questions about this order, a charge, or your access? Support can see this order from its reference — you never need to share card details.</p>
{"".join(rendered)}
{_signed_close_html(brand or {})}
</section>"""


def _reconciling_banner(state, brand):
    retry = (state or {}).get("retry") or {}
    attempt = retry.get("attempt", 1)
    max_attempts = retry.get("max_attempts", MAX_RECONCILIATION_CHECKS)
    next_delay = retry.get("next_retry_seconds")
    if next_delay is None and isinstance(attempt, int) \
            and 1 <= attempt <= len(RETRY_DELAYS_SECONDS):
        next_delay = RETRY_DELAYS_SECONDS[attempt - 1]
    delay_text = (f" The next automatic check is in about "
                  f"{_esc(next_delay)} seconds.") if next_delay else ""
    return f"""<section class="ty82-banner ty82-reconciling" aria-labelledby="ty82-reconciling-heading">
<h2 id="ty82-reconciling-heading"><span class="ty82-spinner" aria-hidden="true"></span> Confirming your purchase</h2>
<p>Your payment is still being confirmed, so some items may not be listed yet. This page checks again on its own — check {_esc(attempt)} of {_esc(max_attempts)}.{delay_text}</p>
<p>You do not need to pay again, and checking again never starts another purchase. If confirming takes more than a few minutes, use the access link in your confirmation email or contact support.</p>
<p><button type="button" class="ty82-button ty82-button--secondary" data-cta-class="noncommercial_next_step" data-ty82-action="recheck">Check again now</button>
{_support_link(brand)}</p>
</section>"""


def _outage_banner(view, brand):
    items_by_offer = {i.get("offer_id"): i for i in (view or {}).get("items") or []}
    unresolved_ids = []
    for offer_id in (view or {}).get("pending_items") or []:
        unresolved_ids.append(offer_id)
    for offer_id in (view or {}).get("failed_items") or []:
        unresolved_ids.append(offer_id)
    for item in (view or {}).get("items") or []:
        if item.get("display_status") in ("pending", "unknown",
                                          "requires_customer_action"):
            if item.get("offer_id") not in unresolved_ids:
                unresolved_ids.append(item.get("offer_id"))
    if unresolved_ids:
        entries = []
        for offer_id in unresolved_ids:
            item = items_by_offer.get(offer_id) or {}
            name = item.get("display_name", offer_id)
            label = STATUS_LABELS.get(item.get("display_status"), "Unresolved")
            entries.append(f"<li>{_esc(name)} — {_esc(label)}</li>")
        unresolved_html = (
            '<h3>Unresolved items</h3><ul>' + "".join(entries) + "</ul>")
    else:
        unresolved_html = (
            "<p>Every purchased item is listed below from the last "
            "confirmed copy; none are waiting on a re-check.</p>")
    return f"""<section class="ty82-banner ty82-outage" aria-labelledby="ty82-outage-heading">
<h2 id="ty82-outage-heading">Some details could not be refreshed</h2>
<p>Our order service is having trouble, so you are seeing the last confirmed copy of your order. Nothing below is a guess: it is your verified purchase record as last saved.</p>
{unresolved_html}
<p>{_support_link(brand)}</p>
</section>"""


def _primary_action_html(view):
    """The first granted access block is the primary next action."""
    items_by_offer = {i.get("offer_id"): i for i in view.get("items") or []}
    for block in view.get("access_blocks") or []:
        url = _https_access_url(block.get("delivery_url"))
        if not url:
            continue
        action = block.get("next_action") or "access"
        if action not in ALLOWED_CTA_CLASSES:
            action = "access"
        item = items_by_offer.get(block.get("offer_id")) or {}
        name = item.get("display_name") or block.get("offer_id")
        return (f'<p class="ty82-primary-action">'
                f'<a class="ty82-button ty82-button--primary" '
                f'data-cta-class="{_esc(action)}" href="{_esc(_safe_url(url))}">'
                f'Start here: {_esc(name)}</a></p>')
    return ""


def render_order_view(view, brand=None, state=None):
    """Render a resolved order view (normal mode, plus state banners)."""
    brand = brand or {}
    state = state or {}
    mode = state.get("mode") or ("reconciling" if view.get("reconciling")
                                 else "normal")
    confirmation = view.get("confirmation") or {}
    confirmation_status = confirmation.get("status")
    if confirmation_status not in CONFIRMATION_LABELS:
        # Fail closed (F-01): the order-view schema constrains
        # confirmation.status to exactly the CONFIRMATION_LABELS enum,
        # so any other value (or a missing status) is invalid input.
        # Never fall back to a "Confirmed" label for a status we do not
        # recognize — that rendered a confirmation claim next to a
        # pending pill. Mirrors render_error / render_state_fragment,
        # which raise on unknown kinds.
        raise ValueError(
            f"unknown confirmation status: {confirmation_status!r}")
    status_label = CONFIRMATION_LABELS[confirmation_status]
    brand_name = (brand.get("brand_name") or brand.get("name") or "")
    brand_html = (f'<p class="ty82-brand">{_esc(brand_name)}</p>'
                  if brand_name else "")
    parts = [_HOSTING_GUIDANCE,
             '<section class="ty82" aria-labelledby="ty82-heading">',
             _style_block(brand),
             brand_html,
             f'<header class="ty82-header" {_section_attrs("1")}>',
             f'<h1 id="ty82-heading" class="ty82-headline">'
             f'{_esc(_honest_headline(view))}</h1>',
             f'<div class="ty82-status" role="status" aria-live="polite">'
             f'{_status_span("paid" if confirmation_status == "confirmed" else "pending")}'
             f' <span class="ty82-confirmation-label">{_esc(status_label)}</span></div>',
             '<p class="ty82-reassurance">Thank you. This page confirms '
             'exactly what you purchased — nothing more was added, and '
             'there is nothing else to buy here.</p>',
             f'<p class="ty82-order-ref">Order reference: '
             f'{_esc(view.get("order_number"))}</p>',
             _primary_action_html(view),
             _hero_html(brand),
             "</header>"]
    if mode == "reconciling":
        parts.append(_reconciling_banner(state, brand))
    if mode == "outage_cached" or view.get("cached"):
        parts.append(_outage_banner(view, brand))
    parts.append(_order_summary_section(view))
    parts.append(_access_section(view))
    parts.append(_next_steps_section(view, brand))
    parts.append(_manage_support_section(view, brand))
    parts.append("</section>")
    return "\n".join(p for p in parts if p)


_ERROR_COPY = {
    "wrong_order_reference": (
        "We could not find that order reference",
        "The order link may be incomplete, mistyped, or for a different "
        "store. Use the full link in your confirmation email — guessing an "
        "order number will not open a receipt, and we never show a sample "
        "receipt or someone else's order in its place.",
        False,
    ),
    "stale_session": (
        "Your session has expired",
        "For your privacy, this receipt is only shown to the signed-in "
        "buyer for a short time. Sign in again from your confirmation "
        "email link and your order will be here. Nothing about your "
        "purchase has changed.",
        False,
    ),
    "native_read_failure": (
        "We could not load your order just now",
        "Our order service did not answer, so we cannot show your receipt "
        "yet. Your purchase is not affected and you do not need to buy "
        "anything again. You can try once more, or use the access link in "
        "your confirmation email.",
        True,
    ),
}


def render_error(error_kind, brand=None, state=None):
    """Render an error fragment: explanation + support fallback only.

    Contains NO order data, NO amounts, and never a fake sample receipt.
    """
    if error_kind not in ERROR_KINDS:
        raise ValueError(f"unknown error kind: {error_kind!r}")
    brand = brand or {}
    heading, body, can_retry = _ERROR_COPY[error_kind]
    retry_html = ""
    if can_retry:
        retry_html = (
            '<p><button type="button" class="ty82-button '
            'ty82-button--secondary" data-cta-class="noncommercial_next_step" '
            'data-ty82-action="recheck">Try again</button></p>')
    return "\n".join([
        _HOSTING_GUIDANCE,
        '<section class="ty82" aria-labelledby="ty82-error-heading">',
        _style_block(brand),
        '<div class="ty82-status" role="alert">'
        f'<h1 id="ty82-error-heading" class="ty82-headline">{_esc(heading)}</h1>'
        f"<p>{_esc(body)}</p></div>",
        retry_html,
        '<section class="ty82-help" aria-labelledby="ty82-help-heading">'
        '<h2 id="ty82-help-heading">Get help with this order</h2>'
        "<p>Support can find your order from your confirmation email — "
        "you never need to share card details.</p>"
        f"<p>{_support_link(brand)}</p></section>",
        "</section>",
    ])


def render_state_fragment(kind, brand=None, state=None):
    """Render a standalone state fragment (no order view available yet)."""
    state = dict(state or {})
    if kind == "reconciling":
        return "\n".join([
            _HOSTING_GUIDANCE,
            '<section class="ty82" aria-labelledby="ty82-reconciling-heading">',
            _style_block(brand or {}),
            _reconciling_banner(state, brand or {}),
            "</section>",
        ])
    if kind in ERROR_KINDS:
        return render_error(kind, brand, state)
    raise ValueError(f"unknown state fragment kind: {kind!r}")


def render_thank_you(view=None, brand=None, state=None):
    """Render the thank-you fragment for a view and/or renderer state.

    state keys:
      mode: "normal" | "reconciling" | "outage_cached" | "error"
      error_kind: one of ERROR_KINDS (mode "error")
      retry: {"attempt": int, "max_attempts": int,
              "next_retry_seconds": int}
    A view may also carry "reconciling": true or "cached": true.
    """
    brand = brand or {}
    state = state or {}
    mode = state.get("mode")
    if mode == "error" or state.get("error_kind"):
        return render_error(state.get("error_kind") or "native_read_failure",
                            brand, state)
    if view is None:
        if mode == "reconciling":
            return render_state_fragment("reconciling", brand, state)
        raise ValueError(
            "render_thank_you requires an order view (or an explicit "
            "reconciling/error state); it never invents a receipt")
    return render_order_view(view, brand, state)


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", help="order-view JSON from the resolver")
    parser.add_argument("--brand", help="brand tokens JSON")
    parser.add_argument("--state", help="renderer state JSON")
    parser.add_argument("-o", "--output", help="write here instead of stdout")
    args = parser.parse_args(argv)

    def _load(path):
        if not path:
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    output = render_thank_you(_load(args.view), _load(args.brand),
                              _load(args.state))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
