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
      "manage_purchase_url": "https://..."
    }

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

import html
import re

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
_COLOR_RE = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30}|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\))$"
)
_SAFE_URL_PREFIXES = ("https://", "http://", "mailto:", "#", "/")


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
        if stripped.lower().startswith(_SAFE_URL_PREFIXES):
            return stripped
    return default


def format_amount(amount_minor, currency):
    """Integer minor units -> display amount. No floats for money math."""
    amount_minor = int(amount_minor)
    symbol = _CURRENCY_SYMBOLS.get(currency)
    major = f"{amount_minor // 100:,}.{amount_minor % 100:02d}"
    if symbol:
        return f"{symbol}{major}"
    return f"{_esc(currency)} {major}"


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


def _item_billing_text(item):
    billing = item.get("billing") or {}
    billing_type = billing.get("billing_type")
    interval = billing.get("recurring_interval")
    schedule = billing.get("schedule") or []
    if billing_type == "recurring" or interval or schedule:
        parts = ["Recurring"]
        if interval:
            parts.append(f"every {_esc(interval)}")
        text = " — ".join([parts[0], " ".join(parts[1:])]) if len(parts) > 1 \
            else parts[0]
        entries = []
        for entry in schedule:
            if not isinstance(entry, dict):
                entries.append(_esc(entry))
                continue
            label = entry.get("label") or entry.get("date") \
                or entry.get("charge_date") or "Scheduled charge"
            piece = _esc(label)
            if isinstance(entry.get("amount_minor"), int):
                piece += f": {format_amount(entry['amount_minor'], item.get('currency', ''))}"
            entries.append(piece)
        if entries:
            text += " (" + "; ".join(entries) + ")"
        return text
    return "One-time charge"


def _status_span(status):
    label = STATUS_LABELS.get(status, STATUS_LABELS["unknown"])
    return (f'<span class="ty82-status-pill ty82-status--{_esc(status)}">'
            f'{_esc(label)}</span>')


def _order_summary_section(view):
    currency = (view.get("totals") or {}).get("currency", "")
    rows = []
    for item in view.get("items") or []:
        rows.append(
            "<tr>"
            f'<th scope="row">{_esc(item.get("display_name"))}</th>'
            f"<td>{_status_span(item.get('display_status'))}</td>"
            f"<td>{_item_billing_text(item)}</td>"
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
    return f"""<section class="ty82-order" aria-labelledby="ty82-order-heading">
<h2 id="ty82-order-heading">Your order</h2>
<table class="ty82-table">
<caption>Order summary for order {_esc(view.get("order_number"))}. Amounts are the actual charges from your verified purchase record.</caption>
<thead><tr><th scope="col">Item</th><th scope="col">Status</th><th scope="col">Billing</th><th scope="col">Amount</th></tr></thead>
<tbody>
{body}
</tbody>
</table>
</section>"""


def _access_section(view):
    items_by_offer = {i.get("offer_id"): i for i in view.get("items") or []}
    blocks = []
    for block in view.get("access_blocks") or []:
        item = items_by_offer.get(block.get("offer_id")) or {}
        name = item.get("display_name") or block.get("offer_id")
        action = block.get("next_action") or "access"
        if action not in ALLOWED_CTA_CLASSES:
            action = "access"
        url = block.get("delivery_url")
        if url:
            action_html = (
                f'<a class="ty82-button ty82-button--primary" '
                f'data-cta-class="{_esc(action)}" href="{_esc(_safe_url(url))}">'
                f'{_esc(action.replace("_", " ").title())}: {_esc(name)}</a>'
            )
        else:
            action_html = (
                "<p>Access for this item is being prepared. It will also "
                "arrive by email; contact support if it does not.</p>"
            )
        blocks.append(
            f'<div class="ty82-access-block">'
            f"<h3>{_esc(name)}</h3>{action_html}</div>"
        )
    if not blocks:
        return ""
    return f"""<section class="ty82-access" aria-labelledby="ty82-access-heading">
<h2 id="ty82-access-heading">Your access</h2>
<p>These links open only what you purchased. Each destination checks your account before letting you in.</p>
{"".join(blocks)}
</section>"""


def _next_steps_section(view, brand):
    lines = []
    items_by_offer = {i.get("offer_id"): i for i in view.get("items") or []}
    if view.get("access_blocks"):
        lines.append(
            "Access for your confirmed items is ready now — use the links "
            "under “Your access”. Access also arrives by email, so you can "
            "leave this page and come back later."
        )
    for offer_id in view.get("pending_items") or []:
        name = (items_by_offer.get(offer_id) or {}).get("display_name", offer_id)
        lines.append(
            f"{_esc(name)} is still being confirmed. Delivery for it starts "
            "when its payment is confirmed, and we will email you — you do "
            "not need to buy it again."
        )
    for offer_id in view.get("failed_items") or []:
        name = (items_by_offer.get(offer_id) or {}).get("display_name", offer_id)
        lines.append(
            f"{_esc(name)} did not go through, so there is no charge or "
            "access for it. Your confirmed items above are not affected."
        )
    if not lines:
        lines.append("Your receipt and access details are also on their way to your email.")
    items_html = "".join(f"<li>{line}</li>" for line in lines)
    return f"""<section class="ty82-next" aria-labelledby="ty82-next-heading">
<h2 id="ty82-next-heading">What happens next</h2>
<ul>{items_html}</ul>
</section>"""


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
    return f"""<section class="ty82-help" aria-labelledby="ty82-help-heading">
<h2 id="ty82-help-heading">Help and your purchase</h2>
<p>Questions about this order, a charge, or your access? Support can see this order from its reference — you never need to share card details.</p>
{"".join(rendered)}
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
        url = block.get("delivery_url")
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
             "<header class=\"ty82-header\">",
             f'<h1 id="ty82-heading" class="ty82-headline">'
             f'{_esc(confirmation.get("headline") or "Your purchase")}</h1>',
             f'<div class="ty82-status" role="status" aria-live="polite">'
             f'{_status_span("paid" if confirmation_status == "confirmed" else "pending")}'
             f' <span class="ty82-confirmation-label">{_esc(status_label)}</span></div>',
             '<p class="ty82-reassurance">Thank you. This page confirms '
             'exactly what you purchased — nothing more was added, and '
             'there is nothing else to buy here.</p>',
             f'<p class="ty82-order-ref">Order reference: '
             f'{_esc(view.get("order_number"))}</p>',
             _primary_action_html(view),
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
