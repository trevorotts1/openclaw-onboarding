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
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = SKILL_ROOT / "references" / "copy-specs"

SPEC_FILES = {
    "standard": "standard-v6.json",
    "long-form": "long-form-v6.json",
    "product-selection": "product-selection-v1.json",
    "thank-you": "thank-you-v1.json",  # the thank-you page (page_role thank_you): five sections, scripts/page_role.py reads its wireframe wording
    "upsell": "upsell-v6.json",  # the upsell page (page_roles upsell_1, upsell_2): eight sections
}
FORMS = tuple(SPEC_FILES)
LANDING_FORMS = ("standard", "long-form")
NO_STEPS_FORMS = ("product-selection",)  # forms with no 7-step section: the negative block drops its step rule


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


def norm(value) -> str | None:
    """"Product Selection", "product_selection", "product-selection-v1" -> "product-selection"."""
    text = "".join(c for c in str(value or "").lower() if c.isalpha())
    for form in FORMS:
        key = "".join(c for c in form if c.isalpha())
        if text in (key, key + "v6", key + "v1"):
            return form
    return None


if __name__ == "__main__":
    raise SystemExit("copy_forms.py is a library; see scripts/stage_executor.py")
