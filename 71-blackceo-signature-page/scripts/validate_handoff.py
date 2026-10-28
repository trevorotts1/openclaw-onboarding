#!/usr/bin/env python3
"""Verify the signature page's funnel handoff on the built page (Item 32).

  python3 scripts/validate_handoff.py <run_dir>

Wired as a validator of the responsive-html stage in
references/stage-contract.json. The handoff contract (update plan
Item 32) is recorded at intake in intake.json's funnel_handoff (written
by scripts/write_intake.py): the Convert and Flow form's identity (name
and object id), the pop behavior, and the step order (signature page,
then product selection page, then order form page). This check verifies,
on the built page (responsive-html/index.html):

- the intake record exists: a run with no form identity must carry the
  explicit missing-input record; no record at all fails, because a
  silent placeholder is not a handoff;
- the copy manifest (copy/copy-manifest.json) carries a primary CTA
  entry whose handoff type is form_pop, naming the button inspected;
- the page's primary CTA is wired to the named form object: the element
  itself references the form's object id, or (for a button) the page
  does; a primary CTA that is a placeholder anchor ("#", "#join", any
  in-page fragment) or an external link fails by name;
- the page references the named form object id somewhere in its markup
  or scripts: the pop targets the named GHL form object, never a
  hand-rolled substitute.

When intake records the missing input, a placeholder primary CTA is
carried under that recorded flag (printed here, never silent) and this
check passes; the flag is the run's own record, not this check's
invention. The live proof (the button actually opens the named form,
and a test submission lands and routes onward) is the funnel-completion
receipt's, verified by scripts/validate_funnel_completion.py.

Exit 0 pass, 1 fail, 2 usage error.
"""
import json
import re
import sys
from pathlib import Path

STEP_ORDER = ["signature_page", "product_selection_page", "order_form_page"]
BEHAVIOR = "form_pop"

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
    failures = []
    intake = load_json(run_dir / "intake.json")
    if not isinstance(intake, dict):
        return ["intake.json is missing or unreadable: the funnel handoff "
                "record lives at intake (scripts/write_intake.py)"]
    handoff = intake.get("funnel_handoff")
    if not isinstance(handoff, dict):
        return ["intake.json records no funnel_handoff: the signature "
                "page's funnel handoff must be recorded at intake (the "
                "form identity via scripts/write_intake.py "
                "--handoff-form-name/--handoff-form-id, or the explicit "
                "missing input via --handoff-missing-reason); a silent "
                "placeholder is not a handoff"]
    if handoff.get("behavior") not in (None, BEHAVIOR):
        failures.append(f"funnel_handoff.behavior is "
                        f"{handoff.get('behavior')!r}; the signature "
                        f"page's handoff behavior is the form pop "
                        f"({BEHAVIOR!r})")
    if handoff.get("step_order") not in (None, STEP_ORDER):
        failures.append(f"funnel_handoff.step_order is "
                        f"{handoff.get('step_order')!r}; the recorded step "
                        f"order is {STEP_ORDER} (signature page, then "
                        f"product selection page, then order form page)")

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
              f"input (form identity missing: {reason.strip()}); a "
              f"placeholder primary CTA on this page is carried under that "
              f"flag, never silently")
        return []

    form = handoff.get("form")
    if not isinstance(form, dict) or not form.get("name") \
            or not form.get("form_id"):
        failures.append("funnel_handoff.form must carry the form's name AND "
                        "object id (the identity is both); record it with "
                        "scripts/write_intake.py --handoff-form-name and "
                        "--handoff-form-id, or record the explicit missing "
                        "input")
        return failures
    form_name, form_id = form["name"], form["form_id"]

    manifest = load_json(run_dir / "copy" / "copy-manifest.json")
    if not isinstance(manifest, dict):
        failures.append("copy/copy-manifest.json is missing or unreadable: "
                        "the primary CTA entry (handoff_type form_pop) is "
                        "what names the button this check inspects")
        return failures
    ctas = manifest.get("ctas")
    primaries = [e for e in ctas if isinstance(e, dict)
                 and e.get("primary") is True] if isinstance(ctas, list) \
        else []
    if not primaries:
        failures.append("copy manifest carries no primary CTA entry: the "
                        "primary CTA (handoff_type form_pop) must be marked "
                        "\"primary\": true in copy/copy-manifest.json")
        return failures
    if len(primaries) > 1:
        failures.append(f"copy manifest marks {len(primaries)} primary CTA "
                        f"entries; the page has exactly one primary CTA")
        return failures
    primary = primaries[0]
    if primary.get("handoff_type") != BEHAVIOR:
        failures.append(f"the copy manifest's primary CTA carries "
                        f"handoff_type {primary.get('handoff_type')!r}; the "
                        f"primary CTA's handoff is the form pop (form_pop)")
        return failures
    label = primary.get("label")
    if not (isinstance(label, str) and label.strip()):
        failures.append("the copy manifest's primary CTA entry names no "
                        "label: the label is how the built page's primary "
                        "CTA is found")
        return failures

    found = find_primary_element(html, label)
    if found is None:
        failures.append(f"no element carries the primary CTA {label!r} "
                        f"from the copy manifest: the page's primary CTA is "
                        f"the button that must pop the named form")
        return failures
    tag, attrs, markup = found
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
