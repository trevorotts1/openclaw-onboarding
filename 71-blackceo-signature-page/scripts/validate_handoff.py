#!/usr/bin/env python3
"""Verify the signature page's funnel handoff on the built page (Item 32).

  python3 scripts/validate_handoff.py <run_dir>

Wired as a validator of the responsive-html stage in
references/stage-contract.json. The required handoff is derived from the
page kind's declared action (intake.json's page_kind, read through
scripts/page_kinds.py and references/page-kinds.json), because the two
landing kinds hand off differently:

- action "form" (the signature landing / opt-in page): the handoff
  contract (update plan Item 32) is recorded at intake in intake.json's
  funnel_handoff (written by scripts/write_intake.py): the Convert and
  Flow form's identity (name and object id), the pop behavior, and the
  step order (signature page, then product selection page, then order
  form page). The copy manifest's primary CTA is a form_pop, the page's
  primary CTA is wired to the named form object, and the page references
  the named form object id somewhere in its markup or scripts.
- action "checkout" (the signature sales page): every button leads to
  the client's checkout page or payment link, so no form identity and no
  product-selection/order-form sequence applies. The copy manifest's
  primary CTA is an external_link, and the page's primary CTA is an
  anchor to an absolute http(s) checkout/payment link: never a fragment
  or placeholder. When intake records the destination (funnel_handoff.
  checkout_url, funnel_handoff.checkout.url, or intake.json
  checkout_url), the page's link must be that destination.

A run that declares no page_kind keeps the form route (the contract this
check shipped with). This check verifies, on the built page
(responsive-html/index.html):

- on the form route, the intake record exists: a run with no form
  identity must carry the explicit missing-input record; no record at
  all fails, because a silent placeholder is not a handoff;
- the copy manifest (copy/copy-manifest.json) carries exactly one
  primary CTA entry whose handoff type the page kind requires, naming
  the button inspected;
- the primary CTA's destination satisfies that requirement: the named
  form object on the form route (a placeholder anchor, any in-page
  fragment, or an external link fails by name), an absolute external
  checkout destination on the checkout route (a fragment, a relative or
  non-http(s) link fails by name);
- on the form route, the page references the named form object id
  somewhere in its markup or scripts.

When intake records the missing input, a placeholder primary CTA is
carried under that recorded flag (printed here, never silent) and this
check passes; the flag is the run's own record, not this check's
invention. The live proof (the button actually opens the named form, or
the checkout page takes payment, and the journey lands and routes
onward) is the funnel-completion receipt's, verified by
scripts/validate_funnel_completion.py.

Exit 0 pass, 1 fail, 2 usage error.
"""
import json
import re
import sys
from pathlib import Path

import page_kinds

STEP_ORDER = ["signature_page", "product_selection_page", "order_form_page"]
BEHAVIOR = "form_pop"
FORM_ROUTE = "form"
CHECKOUT_ROUTE = "checkout"
EXTERNAL_LINK = "external_link"
CHECKOUT_URL_RE = re.compile(r"^https?://[^/\s?#]+(?:[/?#]\S*)?$", re.I)

ELEMENT_RE = re.compile(r"<(a|button)\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)
INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"href\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
VALUE_RE = re.compile(r"value\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", re.I)
TYPE_RE = re.compile(r"type\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def norm_text(value):
    return " ".join(TAG_RE.sub(" ", value).split()).casefold()


def first_group(match):
    if match is None:
        return None
    for g in match.groups():
        if g is not None:
            return g
    return None


def handoff_route(intake):
    """The handoff this run's page kind requires. page-kinds.json declares each
    kind's action; a run with no page_kind on record keeps the Item 32 form
    route. Returns the route dict, or {"error": ...} for an unknown kind."""
    if not intake.get("page_kind"):
        return {"kind": None, "action": FORM_ROUTE,
                "primary_handoff_type": BEHAVIOR,
                "behavior": BEHAVIOR, "step_order": STEP_ORDER,
                "requirement": "the primary CTA's handoff is the form pop "
                               "(form_pop)"}
    try:
        kind = page_kinds.entry(intake["page_kind"])
    except page_kinds.KindError as exc:
        return {"error": str(exc)}
    handoff = kind.get("handoff") if isinstance(kind.get("handoff"), dict) else {}
    action = kind.get("action")
    if action == CHECKOUT_ROUTE:
        requirement = ("a sales page's primary CTA is the client's checkout "
                       "page or payment link (external_link), never the form pop")
    else:
        requirement = ("the primary CTA's handoff is the form pop (form_pop)")
    return {"kind": page_kinds.normalize(intake["page_kind"]),
            "action": action,
            "primary_handoff_type": handoff.get("primary_handoff_type"),
            "behavior": handoff.get("behavior"),
            "step_order": handoff.get("step_order"),
            "requirement": requirement}


def declared_checkout(intake, handoff):
    """The checkout destination recorded at intake, or None."""
    checkout = handoff.get("checkout")
    values = [handoff.get("checkout_url"),
              checkout.get("url") if isinstance(checkout, dict) else None,
              intake.get("checkout_url")]
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def norm_url(value):
    return value.strip().rstrip("/")


def find_primary_element(html, label):
    """Return (tag, attrs, markup) of the element carrying the primary
    CTA's label, or None."""
    want = norm_text(label)
    for m in ELEMENT_RE.finditer(html):
        if norm_text(m.group(3)) == want:
            return m.group(1).lower(), m.group(2), m.group(0)
    for m in INPUT_RE.finditer(html):
        tag = m.group(0)
        if (first_group(TYPE_RE.search(tag)) or "").lower() not in (
                "submit", "button"):
            continue
        if norm_text(first_group(VALUE_RE.search(tag)) or "") == want:
            return "input", tag, tag
    return None


def validate(run_dir):
    intake = load_json(run_dir / "intake.json")
    if not isinstance(intake, dict):
        return ["intake.json is missing or unreadable: the funnel handoff "
                "record lives at intake (scripts/write_intake.py)"]
    route = handoff_route(intake)
    if route.get("error"):
        return [route["error"]]
    checkout = route["action"] == CHECKOUT_ROUTE
    handoff = intake.get("funnel_handoff")
    if not isinstance(handoff, dict):
        if not checkout:
            return ["intake.json records no funnel_handoff: the signature "
                    "page's funnel handoff must be recorded at intake (the "
                    "form identity via scripts/write_intake.py "
                    "--handoff-form-name/--handoff-form-id, or the explicit "
                    "missing input via --handoff-missing-reason); a silent "
                    "placeholder is not a handoff"]
        # A sales page's handoff is its checkout link, not a form identity:
        # with no record on file the destination is verified on the page.
        handoff = {}
    failures = []
    if not checkout:
        if handoff.get("behavior") not in (None, route["behavior"]):
            failures.append(f"funnel_handoff.behavior is "
                            f"{handoff.get('behavior')!r}; the signature "
                            f"page's handoff behavior is the form pop "
                            f"({route['behavior']!r})")
        if handoff.get("step_order") not in (None, route["step_order"]):
            failures.append(f"funnel_handoff.step_order is "
                            f"{handoff.get('step_order')!r}; the recorded step "
                            f"order is {route['step_order']} (signature page, "
                            f"then product selection page, then order form "
                            f"page)")

    page_path = run_dir / "responsive-html" / "index.html"
    if not page_path.is_file():
        failures.append("responsive-html/index.html is missing: the built "
                        "page is what this check verifies")
        return failures
    html = page_path.read_text(encoding="utf-8", errors="replace")

    if handoff.get("status") == "missing_input":
        reason = handoff.get("reason")
        if not (isinstance(reason, str) and reason.strip()):
            failures.append("funnel_handoff records status \"missing_input\" "
                            "but names no reason: the explicit missing input "
                            "carries its reason")
            return failures
        if failures:
            return failures
        print(f"PASS: funnel handoff carried under the recorded missing "
              f"input ({handoff.get('missing') or 'handoff destination'} "
              f"missing: {reason.strip()}); a placeholder primary CTA on this "
              f"page is carried under that flag, never silently")
        return []

    form = handoff.get("form")
    if not checkout and (not isinstance(form, dict) or not form.get("name")
                         or not form.get("form_id")):
        failures.append("funnel_handoff.form must carry the form's name AND "
                        "object id (the identity is both); record it with "
                        "scripts/write_intake.py --handoff-form-name and "
                        "--handoff-form-id, or record the explicit missing "
                        "input")
        return failures
    form_name = form.get("name") if isinstance(form, dict) else None
    form_id = form.get("form_id") if isinstance(form, dict) else None
    expect = route.get("primary_handoff_type") or BEHAVIOR

    manifest = load_json(run_dir / "copy" / "copy-manifest.json")
    if not isinstance(manifest, dict):
        failures.append("copy/copy-manifest.json is missing or unreadable: "
                        f"the primary CTA entry (handoff_type {expect}) is "
                        f"what names the button this check inspects")
        return failures
    ctas = manifest.get("ctas")
    primaries = [e for e in ctas if isinstance(e, dict)
                 and e.get("primary") is True] if isinstance(ctas, list) \
        else []
    if not primaries:
        failures.append("copy manifest carries no primary CTA entry: the "
                        f"primary CTA (handoff_type {expect}) must be marked "
                        "\"primary\": true in copy/copy-manifest.json")
        return failures
    if len(primaries) > 1:
        failures.append(f"copy manifest marks {len(primaries)} primary CTA "
                        f"entries; the page has exactly one primary CTA")
        return failures
    primary = primaries[0]
    if primary.get("handoff_type") != expect:
        failures.append(f"the copy manifest's primary CTA carries "
                        f"handoff_type {primary.get('handoff_type')!r}; "
                        f"{route['requirement']}")
        return failures
    label = primary.get("label")
    if not (isinstance(label, str) and label.strip()):
        failures.append("the copy manifest's primary CTA entry names no "
                        "label: the label is how the built page's primary "
                        "CTA is found")
        return failures

    found = find_primary_element(html, label)
    if found is None:
        wants = ("the page's primary CTA is the link that carries the "
                 "client's checkout" if checkout else
                 "the button that must pop the named form")
        failures.append(f"no element carries the primary CTA {label!r} "
                        f"from the copy manifest: {wants}")
        return failures
    tag, attrs, markup = found

    if checkout:
        declared = declared_checkout(intake, handoff)
        if tag != "a":
            failures.append(
                f"primary CTA {label!r} is a <{tag}>, not a link: a sales "
                f"page's primary CTA is an anchor to the client's checkout "
                f"page or payment link")
            return failures
        href = first_group(HREF_RE.search(attrs))
        destination = href.strip() if isinstance(href, str) else ""
        if destination == "" or destination.startswith("#"):
            failures.append(
                f"primary CTA {label!r} is a placeholder link "
                f"(href={href!r}), not the client's checkout page or payment "
                f"link: a placeholder destination fails the production "
                f"publish path unless intake recorded it as an explicit "
                f"missing input")
            return failures
        if not CHECKOUT_URL_RE.match(destination):
            failures.append(
                f"primary CTA {label!r} points at {destination!r}, which is "
                f"not an absolute http(s) checkout destination: a sales "
                f"page's button leads to the client's checkout page or "
                f"payment link")
            return failures
        if declared is not None and norm_url(declared) != norm_url(destination):
            failures.append(
                f"primary CTA {label!r} points at {destination!r}, not the "
                f"checkout destination recorded at intake ({declared!r}): "
                f"the page must lead where the run's handoff says it does")
            return failures
        if failures:
            return failures
        print(f"PASS: funnel handoff verified (page kind {route['kind']!r} "
              f"action checkout; copy manifest primary CTA {label!r} typed "
              f"{expect}; the page's primary CTA is the checkout link "
              f"{destination!r}"
              + (f", the destination recorded at intake" if declared
                 else ", no destination recorded at intake for comparison")
              + "; no placeholder destination, no form pop required)")
        return []

    if tag == "a":
        # The placeholder test applies to the primary CTA's href
        # regardless of what else the element's markup carries (Item 32
        # review, defect D1): an anchor whose href is a placeholder
        # destination fails by name even when the same element references
        # the named form object; only the recorded missing-input flag
        # (handled above) carries a placeholder.
        href = first_group(HREF_RE.search(attrs))
        if href is not None and (href.strip() == ""
                                 or href.strip().startswith("#")):
            failures.append(
                f"primary CTA {label!r} is a placeholder link "
                f"(href={href!r}), not the form pop against the named "
                f"form {form_name!r} ({form_id}): a placeholder "
                f"destination fails the production publish path unless "
                f"intake recorded it as an explicit missing input")
            return failures
    if form_id not in markup:
        if tag == "a":
            href = first_group(HREF_RE.search(attrs))
            if href is None:
                failures.append(
                    f"primary CTA {label!r} is an anchor with no href and "
                    f"no reference to the named form {form_name!r} "
                    f"({form_id}): it cannot pop the form")
            elif href.strip() == "" or href.strip().startswith("#"):
                failures.append(
                    f"primary CTA {label!r} is a placeholder link "
                    f"(href={href!r}), not the form pop against the named "
                    f"form {form_name!r} ({form_id}): a placeholder "
                    f"destination fails the production publish path unless "
                    f"intake recorded it as an explicit missing input")
            else:
                failures.append(
                    f"primary CTA {label!r} links away from the page "
                    f"(href={href!r}), not the form pop against the named "
                    f"form {form_name!r} ({form_id})")
            return failures
    if form_id not in html:
        failures.append(f"the page never references the named form object "
                        f"{form_id!r} ({form_name!r}): the primary CTA's pop "
                        f"must target the form recorded at intake, not a "
                        f"hand-rolled substitute")
        return failures
    if failures:
        return failures
    print(f"PASS: funnel handoff verified (intake form {form_name!r} "
          f"({form_id}), behavior form_pop, step order signature page -> "
          f"product selection page -> order form page; copy manifest "
          f"primary CTA {label!r} typed form_pop; the page's primary CTA "
          f"is wired to the named form object; no placeholder destination)")
    return []


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: validate_handoff.py <run_dir>")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
