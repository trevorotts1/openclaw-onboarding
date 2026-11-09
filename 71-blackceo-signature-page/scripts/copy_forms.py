#!/usr/bin/env python3
"""The one registry of copy forms the Skill 71 image pipeline accepts.

A form is a canonical section sequence with its machine-readable spec in
references/copy-specs/. Standard (12 sections) and Long-Form (15) are the two
landing-page forms; every other page role that takes the four image stages
adds ONE spec file and ONE row here, and the pipeline (section-count check,
request builder, wireframe build spec, composition roles, Design Board) reads
the form from the spec. There is no second pipeline per page type.

Library only; never calls a provider and never reads a secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = SKILL_ROOT / "references" / "copy-specs"

SPEC_FILES = {
    "standard": "standard-v6.json",
    "long-form": "long-form-v6.json",
    "product-selection": "product-selection-v1.json",
    "thank-you": "thank-you-v1.json",  # the thank-you page (page_role thank_you): five sections, scripts/page_role.py reads its wireframe wording
    "upsell": "upsell-v6.json",  # the upsell page (page_roles upsell_1, upsell_2): eight sections
    # FIX-01 Stage A: the checkout page's own five-section spec. The checkout wrapper's
    # --page-version "checkout" must name a form this one registry defines. Registered after
    # the three page types that must stay first (tests/test_product_selection_form.py pins
    # FORMS[:3]); a form's position carries no behaviour.
    "checkout": "roles/checkout.json",
}
FORMS = tuple(SPEC_FILES)
LANDING_FORMS = ("standard", "long-form")
NO_STEPS_FORMS = ("product-selection",)  # forms with no 7-step section: the negative block drops its step rule

# FIX-14: the accepted spellings that are NOT a separator variant of a registry key. A closed
# set: the canonical key stays the registry's, and an alias only renames an accepted input.
# There is no second registry of versions; SPEC_FILES remains the one contract.
ALIASES = {"signature-upsell-eight-section": "upsell"}


class UnknownCopyProfile(LookupError):
    """A copy_profile names no form this registry defines (FIX-14: fail closed, never a default)."""


def spec_path(form: str) -> Path:
    return SPEC_DIR / SPEC_FILES[form]


def load_spec(form: str) -> dict:
    return json.loads(spec_path(form).read_text(encoding="utf-8"))


def form_for_role(page_role) -> str | None:
    """The non-landing form a page role's images are built from (spec `page_role`, or one of the
    spec's `page_roles` when a form serves several roles, as the upsell form serves upsell_1 and
    upsell_2), else None."""
    for form in FORMS:
        if form in LANDING_FORMS:
            continue
        spec = load_spec(form)
        if page_role == spec.get("page_role") or page_role in (spec.get("page_roles") or ()):
            return form
    return None


def slug(value) -> str:
    """THE normaliser (FIX-14): lower-case, collapse every run outside [a-z0-9] to one hyphen,
    apply the closed ALIASES table. Both spelling boundaries use this one function: the
    copy_profile intake boundary (resolve_profile) and the page-role boundary
    (page_role.validate_page_role). "" for an empty value."""
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return ALIASES.get(text, text)


def norm(value) -> str | None:
    """The registry key a copy_profile or page-role spelling names, or None (FIX-14).

    `slug` normalises the spelling; this is the one registry lookup on top of it: an exact
    key, else the key after an optional -vN version suffix. The key set of SPEC_FILES is
    never widened: the intake and route-graph spelling is normalised into it.

    "Product Selection", "product_selection", "product-selection-v1" -> "product-selection".
    """
    text = slug(value)
    if not text:
        return None
    if text in SPEC_FILES:
        return text
    base = re.sub(r"-v\d+$", "", text)
    return base if base in SPEC_FILES else None


def resolve_profile(value) -> str:
    """The form a copy_profile names; UnknownCopyProfile quoting the rejected value on a miss.

    Every accepted intake resolves to exactly one registered form and nothing resolves to a
    default (FIX-14). Called by launch_context.py at the intake boundary.
    """
    form = norm(value)
    if form is None:
        raise UnknownCopyProfile(
            f"copy_profile {value!r} is not one of {', '.join(FORMS)}; this registry has no "
            "version for it and there is no default")
    return form


if __name__ == "__main__":
    raise SystemExit("copy_forms.py is a library; see scripts/stage_executor.py")
