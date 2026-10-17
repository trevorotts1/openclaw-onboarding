#!/usr/bin/env python3
"""render_selection_preview.py - Skill 78 local preview renderer (S78-04).

Renders a selection plan (from build_selection_plan.py) into one responsive
HTML file labelled LOCAL ONLY. This proves layout and semantics; it is not an
installed page and proves nothing about native handoff correctness (doc 08
section 8).

Live-default contract (doc 08 s6, references/selection-ui-contract.md):
NOTHING is pre-selected. The plan's recommendation is a badge and a reason,
never a checked control. The static preview ships four states:
- default: no radio checked, no card marked selected;
- selected: exactly one radio checked (the plan's published recommendation
  in this fixture), and data-selected on exactly that card;
- error: nothing checked, nothing marked, the alert banner shown;
- reconfirm: the terms-changed banner shown.
A small progressive-enhancement script keeps data-selected in sync with the
checked radio and opens the comparison disclosure on wide viewports while
leaving it closed on narrow ones; without the script the page still works
with native controls and the disclosure opens by hand. Material exclusions
render outside any disclosure in every state.

Money formatting uses each currency's own minor-unit exponent via
selection_core.format_money (doc 02 s3): JPY 9700 renders as JPY 9,700,
never as a two-decimal amount.

Usage:
  render_selection_preview.py <plan.json> <out.html> [--state default|selected|error|reconfirm]
  render_selection_preview.py --self-test
Exit: 0 ok, 2 plan is a decline or invalid, 3 fail-closed error.
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection_core import format_money  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402

CSS_PATH = Path(__file__).resolve().parents[1] / "components" / "selection-ui" / "selection.css"

SYNC_SCRIPT = """<script>
// Progressive enhancement only; the form works without it.
// 1) Keep data-selected in sync with whichever radio is selected.
// 2) Open the comparison disclosure on wide viewports, closed on narrow.
(function () {
  var form = document.querySelector("form.sl78-form");
  function sl78SyncSelected() {
    document.querySelectorAll(".sl78-offer").forEach(function (card) {
      var radio = card.querySelector('input[name="sl78-selection"]');
      card.dataset.selected = radio && radio.checked ? "true" : "false";
    });
  }
  if (form) {
    form.addEventListener("change", sl78SyncSelected);
    sl78SyncSelected();
  }
  var details = document.querySelector(".sl78-matrix-wrap");
  function sl78SyncDetails() {
    if (details) { details.open = window.innerWidth >= 641; }
  }
  sl78SyncDetails();
  window.addEventListener("resize", sl78SyncDetails);
})();
</script>"""


def price_line(price):
    base = format_money(price["amount_minor"], price["currency"])
    if price["billing_type"] == "installment" and price.get("schedule"):
        parts = ", ".join(
            f"{format_money(r['amount_minor'], price['currency'])} {html.escape(str(r['due']))}"
            for r in price["schedule"]
        )
        return f"{base} total, paid as: {parts}"
    if price["billing_type"] == "recurring":
        if price.get("schedule"):
            parts = ", ".join(
                f"{format_money(r['amount_minor'], price['currency'])} {html.escape(str(r['due']))}"
                for r in price["schedule"]
            )
            return f"{base}, recurring, paid as: {parts}"
        if price.get("recurring_interval"):
            return f"{base} every {html.escape(str(price['recurring_interval']))}, recurring"
        return f"{base}, recurring"
    if price["billing_type"] == "trial":
        if price.get("trial_terms"):
            return f"{base}, trial: {html.escape(str(price['trial_terms']))}"
        if price.get("terms_source"):
            return f"{base}, trial terms: {html.escape(str(price['terms_source']))}"
        return f"{base}, trial"
    return f"{base}, one time"


def _schedule_controls(offer):
    """Billing-schedule choice: with more than one approved price choice,
    the visitor picks one with its own radio group; the choice is part of
    the selection and binds at handoff. With one choice, the price line
    alone is shown."""
    prices = offer["prices"]
    if len(prices) < 2:
        return "".join(f'<p class="sl78-price">{html.escape(price_line(p))}</p>' for p in prices)
    items = []
    for p in prices:
        pid = html.escape(p["price_choice_id"])
        items.append(
            f'<label class="sl78-schedule-option">'
            f'<input type="radio" name="sl78-schedule-{html.escape(offer["offer_id"])}" value="{pid}"> '
            f"{html.escape(price_line(p))}</label>"
        )
    return (
        '<fieldset class="sl78-schedule"><legend>Choose how to pay</legend>'
        + "".join(items) + "</fieldset>"
    )


def render(plan, *, state="default"):
    if state not in ("default", "selected", "error", "reconfirm"):
        raise ValueError(f"Unknown preview state {state!r}.")
    if plan.get("outcome") != "plan":
        raise ValueError("Only a selection plan can be rendered; a decline renders no page.")
    css = CSS_PATH.read_text()
    rec = plan.get("recommendation") or {}
    rec_offer = rec.get("offer_id") if rec.get("placement") == "published" else None
    # Only the explicit "selected" state checks a control; default, error,
    # and reconfirm all start from the live default: nothing selected.
    checked_offer = rec_offer if state == "selected" else None
    offers_html = []
    for offer in plan["offers_in_order"]:
        oid = html.escape(offer["offer_id"])
        name = html.escape(offer["display_name"])
        is_checked = offer["offer_id"] == checked_offer
        selected = ' data-selected="true"' if is_checked else ""
        checked = " checked" if is_checked else ""
        badge = ""
        if offer["offer_id"] == rec_offer:
            badge = (
                '<span class="sl78-recommended-badge">Recommended</span> '
                f'<span class="sl78-rec-reason">{html.escape(rec.get("reason", ""))}</span>'
            )
        fit = ""
        if offer.get("intended_buyer"):
            fit += f'<p class="sl78-fit">Best for: {html.escape(offer["intended_buyer"])}</p>'
        if offer.get("primary_outcome"):
            fit += f'<p class="sl78-outcome">{html.escape(offer["primary_outcome"])}</p>'
        inclusions = "".join(f"<li>{html.escape(d)}</li>" for d in offer["deliverables"])
        limited = "".join(
            f"<li>{html.escape(e.get('item') if isinstance(e, dict) else e)}"
            f"{' (' + html.escape(e['note']) + ')' if isinstance(e, dict) and e.get('note') else ''} (limited)</li>"
            for e in offer.get("limited_deliverables", [])
        )
        conditional = "".join(
            f"<li>{html.escape(e.get('item') if isinstance(e, dict) else e)}"
            f"{' - ' + html.escape(e['condition']) if isinstance(e, dict) and e.get('condition') else ''} (conditional)</li>"
            for e in offer.get("conditional_deliverables", [])
        )
        exclusions = "".join(f"<li>{html.escape(e)}</li>" for e in offer["exclusions"])
        excl_block = f'<p class="sl78-exclusions">Not included:</p><ul>{exclusions}</ul>' if exclusions else ""
        offers_html.append(
            f'<label class="sl78-offer"{selected}>'
            f'<input type="radio" name="sl78-selection" value="{oid}"{checked}> '
            f"<strong>{name}</strong> {badge}{fit}"
            f"<ul>{inclusions}{limited}{conditional}</ul>{excl_block}{_schedule_controls(offer)}"
            f'<span class="sl78-cta">Choose {name}</span>'
            f"</label>"
        )
    matrix = plan["comparison_matrix"]
    names = matrix.get("offer_names", {})
    header = "".join(
        f"<th scope=\"col\">{html.escape(names.get(o, o))}</th>" for o in matrix["offer_ids_in_order"]
    )
    cell_text = {"included": "Included", "not_included": "Not included", "limited": "Limited", "conditional": "Conditional"}
    rows = []
    for row in matrix["rows"]:
        cells = []
        for o in matrix["offer_ids_in_order"]:
            state_txt = cell_text[row["cells"][o]]
            note = (row.get("notes") or {}).get(o)
            cells.append(f"<td>{state_txt}{' (' + html.escape(note) + ')' if note else ''}</td>")
        rows.append(f"<tr><th scope=\"row\">{html.escape(row['dimension_item'])}</th>{''.join(cells)}</tr>")
    all_exclusions = "".join(
        f"<li>{html.escape(names.get(e['offer_id'], e['offer_id']))}: {html.escape(e['exclusion'])}</li>"
        for e in matrix["exclusions"]
    )
    excl_section = (
        f'<section class="sl78-all-exclusions"><h2>Important exclusions</h2><ul>{all_exclusions}</ul></section>'
        if all_exclusions else ""
    )
    faq = plan.get("faq") or []
    faq_section = ""
    if faq:
        items = "".join(
            f"<details><summary>{html.escape(str(f.get('question', '')))}</summary>"
            f"<p>{html.escape(str(f.get('answer', '')))}</p></details>" for f in faq
        )
        faq_section = f'<section class="sl78-faq"><h2>Questions</h2>{items}</section>'
    trust = plan.get("trust_items") or []
    trust_section = (
        f'<section class="sl78-trust"><h2>Good to know</h2><ul>'
        + "".join(f"<li>{html.escape(str(t))}</li>" for t in trust) + "</ul></section>"
        if trust else ""
    )
    banner = ""
    if state == "error":
        banner = '<p class="sl78-error" id="sl78-error" role="alert">Choose a package to continue.</p>'
    elif state == "reconfirm":
        banner = (
            '<p class="sl78-reconfirm" role="alert">The terms for your selected package changed. '
            "Review the current terms and confirm before continuing.</p>"
        )
    describedby = ' aria-describedby="sl78-error"' if state == "error" else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Choose your package - LOCAL ONLY preview</title>
<style>{css}</style>
</head>
<body>
<!-- LOCAL ONLY PREVIEW: appearance evidence only, not an installed page, not handoff proof. State: {state}. -->
<main class="sl78-selection">
<h1>Choose the package that fits you</h1>
<p>You showed interest, so here are the exact options, what each one includes, and what each one costs.</p>
{banner}
<form class="sl78-form" method="post" action="#" novalidate>
<fieldset class="sl78-offers"{describedby}>
<legend>Packages</legend>
{''.join(offers_html)}
</fieldset>
<details class="sl78-matrix-wrap">
<summary>Compare packages side by side</summary>
<table class="sl78-matrix">
<tr><th scope="col">Included</th>{header}</tr>
{''.join(rows)}
</table>
</details>
{excl_section}
{trust_section}
{faq_section}
<button type="submit" class="sl78-continue">Continue</button>
</form>
</main>
{SYNC_SCRIPT}
</body>
</html>
"""


def self_test():
    plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
    doc = render(plan)
    assert 'name="sl78-selection"' in doc
    # Live default: nothing pre-selected, in markup or data attributes.
    assert doc.count(" checked") == 0, "default state must check nothing"
    assert 'sl78-offer" data-selected="true"' not in doc
    assert "Choose TEST ONLY B" in doc
    details = doc.split("<details", 1)[1].split("</details>", 1)[0]
    assert "No private reviews" not in details
    assert "No private reviews" in doc
    assert "card number" not in doc.lower()
    sel = render(plan, state="selected")
    assert sel.count(" checked") == 1 and 'sl78-offer" data-selected="true"' in sel
    assert "sl78SyncSelected" in sel and "sl78SyncDetails" in sel
    err = render(plan, state="error")
    assert err.count(" checked") == 0 and 'sl78-offer" data-selected="true"' not in err
    assert 'role="alert"' in err and "Choose a package to continue." in err
    rec = render(plan, state="reconfirm")
    assert "terms for your selected package changed" in rec
    # Currency exponent: JPY minor units render with no decimals.
    import copy as _copy
    jpy_launch = _copy.deepcopy(SELF_TEST_LAUNCH)
    for offer in jpy_launch["offers"]:
        offer["prices"][0]["currency"] = "JPY"
    jpy = render(build_plan(jpy_launch))
    assert "¥9,700" in jpy and "¥19,700" in jpy, jpy[jpy.find("sl78-price") - 50:jpy.find("sl78-price") + 120]
    # Multi-price offer renders a schedule choice control.
    multi_launch = _copy.deepcopy(SELF_TEST_LAUNCH)
    multi_launch["offers"][0]["prices"].append(
        {"price_choice_id": "MAIN-A-USD-INST", "currency": "USD", "amount_minor": 9700,
         "billing_type": "installment", "native_price_id": "TEST-PRICE-A2",
         "schedule": [{"amount_minor": 4850, "due": "today"}, {"amount_minor": 4850, "due": "in 30 days"}],
         "terms_source": None, "approval_status": "approved"})
    multi = render(build_plan(multi_launch))
    assert 'name="sl78-schedule-MAIN-A"' in multi
    print("render_selection_preview --self-test: PASS (nothing pre-selected by default, explicit selected state, JPY exponent rendering, schedule choice control, exclusions outside disclosure, error/reconfirm states)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: render_selection_preview.py <plan.json> <out.html> [--state default|selected|error|reconfirm]", file=sys.stderr)
        return 3
    state = "default"
    if "--state" in argv:
        state = argv[argv.index("--state") + 1]
    try:
        plan = json.loads(Path(args[0]).read_text())
        out = render(plan, state=state)
    except ValueError as v:
        print(f"VIOLATION: {v}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    Path(args[1]).write_text(out)
    print(f"Wrote LOCAL ONLY preview: {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
