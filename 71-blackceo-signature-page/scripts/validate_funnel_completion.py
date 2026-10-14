#!/usr/bin/env python3
"""Verify the funnel-completion sub-stage inside ghl-install-test (Item 32).

  python3 scripts/validate_funnel_completion.py <run_dir>

Reads ghl-install-test/funnel-completion.json (the per-object receipt) and
ghl-install-test/clickthrough.json (the live visitor journey record) and
checks them against references/funnel-completion-checklist.md:

- the sub-stage is required whenever the intake publish target is GHL, or
  any funnel step binds an externally hosted page by embed; otherwise the
  receipt file records status "not_applicable" citing the intake values;
- every object carries its own rail, and the rails are Amendment 5A's FINAL
  rails (from the primary-source research, not preference): browser rail
  for funnel creation, steps and ordering, step bindings, form creation
  and attachment, pop-ups, click actions, order-form binding, and product
  attachment inside an order-form page; API rail for product creation,
  funnel redirects, custom values, and tags;
- creation is idempotent: an existence check by name and role runs BEFORE
  any create, and the receipt records it per object; creating a duplicate
  of an object that already exists is a checklist failure endpoint;
- the order-form step renders product and price in the live click-through;
- the click-through carries SOP Stage 13's two rules by name: a shared
  form is submitted only ONCE with a designated test contact, and sales
  are verified in test mode only, never by an unauthorized live charge.

The forms array in funnel-completion.json is the SOLE source of the form
IDs Item 31's hand-off carries; the gate enforces that equality at close.
"""
import json
import sys
from pathlib import Path

# Amendment 5A final rails: object kind -> the only rail allowed.
RAIL_BY_KIND = {
    "funnel": "browser",
    "step": "browser",
    "form": "browser",
    "popup": "browser",
    "click_action": "browser",
    "order_form": "browser",
    "product": "api",
    "redirect": "api",
    "custom_value": "api",
    "tag": "api",
}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_true(v):
    return v is True


def check_rail(obj, kind, label, failures):
    want = RAIL_BY_KIND[kind]
    if obj.get("rail") != want:
        failures.append(f"{label}: rail must be \"{want}\" (Amendment 5A final "
                        f"rails), got {obj.get('rail')!r}")


def check_created(obj, label, failures):
    """created: true/false per object, with the existence check that ran
    before any create recorded. created without a prior existence check is
    the duplicate-creation failure mode."""
    if not isinstance(obj.get("created"), bool):
        failures.append(f"{label}: `created` must be recorded as true/false")
    if obj.get("existence_check") is not True:
        failures.append(f"{label}: no existence check recorded before create; "
                        f"an existing object must be reused, never duplicated")


def validate(run_dir):
    failures = []
    intake = load_json(run_dir / "intake.json") or {}
    publish_target = intake.get("publish_target")
    fc_path = run_dir / "ghl-install-test" / "funnel-completion.json"
    fc = load_json(fc_path)
    if fc is None:
        return [f"missing or unreadable per-object receipt: {fc_path.relative_to(run_dir)} "
                f"(the funnel-completion sub-stage leaves this record on every "
                f"run, including a not_applicable one)"]
    if fc.get("status") == "not_applicable":
        if publish_target == "ghl":
            failures.append("funnel-completion recorded not_applicable but "
                            "intake.publish_target is \"ghl\": the sub-stage is "
                            "required for every GHL publish target")
        if not fc.get("reason"):
            failures.append("not_applicable funnel-completion record names no reason")
        return failures

    funnel = fc.get("funnel")
    if not isinstance(funnel, dict) or not funnel.get("funnel_id"):
        failures.append("funnel-completion.funnel with a funnel_id is required")
        funnel = funnel or {}
    check_rail(funnel, "funnel", "funnel", failures)
    check_created(funnel, "funnel", failures)

    steps = fc.get("steps")
    if not isinstance(steps, list) or not steps:
        failures.append("funnel-completion.steps must list the funnel steps in order")
        steps = []
    orders = [s.get("order") for s in steps if isinstance(s, dict)]
    if orders != list(range(1, len(steps) + 1)):
        failures.append(f"funnel steps are not in consecutive intended order "
                        f"(order fields: {orders})")
    step_names = set()
    has_embed_step = False
    for s in steps:
        label = f"step {s.get('name')!r}"
        step_names.add(s.get("name"))
        check_rail(s, "step", label, failures)
        binding = s.get("binding") or {}
        if binding.get("kind") == "ghl_page":
            if not binding.get("page_id"):
                failures.append(f"{label}: ghl_page binding names no page_id")
        elif binding.get("kind") == "external_embed":
            has_embed_step = True
            if not binding.get("embed_url"):
                failures.append(f"{label}: external_embed binding names no embed_url")
        else:
            failures.append(f"{label}: binding.kind must be \"ghl_page\" or "
                            f"\"external_embed\", got {binding.get('kind')!r}")
    if publish_target != "ghl" and not has_embed_step and steps:
        failures.append("funnel-completion completed the sub-stage but the intake "
                        "target is not GHL and no step binds an external embed: "
                        "record not_applicable instead")
    if fc.get("status") not in (None, "complete"):
        failures.append(f"funnel-completion.status must be \"complete\" for an "
                        f"applicable run, got {fc.get('status')!r}")

    forms = fc.get("forms") or []
    form_ids = set()
    for f in forms:
        label = f"form {f.get('name')!r}"
        check_rail(f, "form", label, failures)
        check_created(f, label, failures)
        if not f.get("form_id"):
            failures.append(f"{label}: form_id missing (Item 31's hand-off takes "
                            f"its form IDs from this array only)")
        form_ids.add(f.get("form_id"))
        if f.get("attached_to_step") not in step_names:
            failures.append(f"{label}: attached_to_step {f.get('attached_to_step')!r} "
                            f"is not one of the funnel steps")

    for p in fc.get("popups") or []:
        label = f"popup {p.get('name')!r}"
        check_rail(p, "popup", label, failures)
        check_created(p, label, failures)
        if p.get("step") not in step_names:
            failures.append(f"{label}: step {p.get('step')!r} is not one of the funnel steps")
        if not p.get("trigger_element"):
            failures.append(f"{label}: no trigger_element recorded (the pop-up must "
                            f"be wired to the element that opens it)")

    for c in fc.get("click_actions") or []:
        label = f"click action {c.get('element')!r} on step {c.get('step')!r}"
        check_rail(c, "click_action", label, failures)
        if not is_true(c.get("verified_by_clickthrough")):
            failures.append(f"{label}: verified_by_clickthrough is not true; a click "
                            f"action is evidence only when the live journey clicked it")

    products = fc.get("products") or []
    product_ids = set()
    product_by_id = {}
    for pr in products:
        label = f"product {pr.get('name')!r}"
        check_rail(pr, "product", label, failures)
        check_created(pr, label, failures)
        if not pr.get("product_id"):
            failures.append(f"{label}: product_id missing")
        product_ids.add(pr.get("product_id"))
        product_by_id[pr.get("product_id")] = pr
        if pr.get("price") is None or not pr.get("currency"):
            failures.append(f"{label}: price and currency must be recorded")

    order_steps = {s.get("name") for s in steps if s.get("type") == "order"}
    bound_steps = set()
    for o in fc.get("order_forms") or []:
        label = f"order form on step {o.get('step')!r}"
        check_rail(o, "order_form", label, failures)
        if not is_true(o.get("bound")):
            failures.append(f"{label}: bound is not true")
        if o.get("step") not in step_names:
            failures.append(f"{label}: step is not one of the funnel steps")
        bound_steps.add(o.get("step"))
        for pid in o.get("product_ids") or []:
            if pid not in product_ids:
                failures.append(f"{label}: product {pid!r} is not in the products array")
    for name in order_steps - bound_steps:
        failures.append(f"order step {name!r} has no bound order form")

    for coll, kind in (("redirects", "redirect"), ("custom_values", "custom_value"),
                       ("tags", "tag")):
        for obj in fc.get(coll) or []:
            check_rail(obj, kind, f"{kind} {obj.get('name')!r}", failures)

    payment = fc.get("payment")
    if not isinstance(payment, dict) or not isinstance(payment.get("provider_present"), bool):
        failures.append("funnel-completion.payment.provider_present (boolean) is "
                        "required; presence only, never credential material")
    elif order_steps and payment.get("provider_present") is not True:
        failures.append("the funnel sells through an order step but "
                        "payment.provider_present is false")

    failures.extend(check_clickthrough(run_dir, fc, steps))
    return failures


def check_clickthrough(run_dir, fc, steps):
    failures = []
    ct = load_json(run_dir / "ghl-install-test" / "clickthrough.json")
    if ct is None:
        return ["missing live click-through record: ghl-install-test/clickthrough.json "
                "(the sub-stage closes on a clicked visitor journey, not on setup "
                "claims)"]
    if fc.get("steps") and not ct.get("steps_visited"):
        failures.append("clickthrough.steps_visited is empty")
    sub = ct.get("form_submission") or {}
    if is_true(sub.get("performed")):
        if sub.get("submissions_count") != 1:
            failures.append("clickthrough submitted the shared form "
                            f"{sub.get('submissions_count')!r} times; SOP Stage 13: "
                            f"submit a shared form only ONCE, with a designated "
                            f"test contact")
        if not sub.get("test_contact_id"):
            failures.append("clickthrough form submission names no designated "
                            "test contact (SOP Stage 13)")
    if ct.get("live_charge_made") is True:
        failures.append("clickthrough.live_charge_made is true; SOP Stage 13: "
                        "verify sales in test mode only, never by an unauthorized "
                        "live charge")
    order = ct.get("order_step") or {}
    has_order_step = any(s.get("type") == "order" for s in steps)
    if has_order_step:
        if not is_true(order.get("rendered")):
            failures.append("clickthrough did not render the order step")
        products = {p.get("product_id"): p for p in fc.get("products") or []}
        shown = products.get(order.get("product_id"))
        if shown is None:
            failures.append("clickthrough order step shows no product from the "
                            "receipt's products array (the order step must render "
                            "product and price)")
        else:
            try:
                if float(order.get("price")) != float(shown.get("price")):
                    failures.append(f"clickthrough order step price {order.get('price')!r} "
                                    f"does not match the product's recorded price "
                                    f"{shown.get('price')!r}")
            except (TypeError, ValueError):
                failures.append("clickthrough order step price is not numeric")
    if any(s.get("type") in ("booking", "calendar") for s in steps):
        booking = ct.get("booking_step") or {}
        if not (is_true(booking.get("rendered")) and is_true(booking.get("calendar_shown"))):
            failures.append("clickthrough did not render the booking step's calendar")
    for shot in ct.get("screenshots") or []:
        if not (run_dir / shot).is_file():
            failures.append(f"clickthrough names a screenshot that is not on disk: {shot}")
    return failures


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: validate_funnel_completion.py <run_dir>")
        return 2
    run_dir = Path(argv[0]).resolve()
    if not run_dir.exists():
        print(f"FAIL: run_dir does not exist: {run_dir}")
        return 2
    failures = validate(run_dir)
    if failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
        return 1
    print("PASS: funnel-completion receipt and live click-through verified "
          "(steps bound, forms attached, rails per Amendment 5A, order step "
          "renders product and price)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
