#!/usr/bin/env python3
"""emit_checkout_manuscript.py - Skill 79 order-form copy as Skill 71's five-section manuscript.

The order form is the one page whose copy carries money. This writes it from the approved Skill 79
checkout request, so a person never types a price, a bump name or a guarantee into a file by hand:

  Section 1  Offer or selected package   what the launch record says the buyer gets (and does not get)
  Section 2  Offer details and price     the request's main price, in the launch record's own currency
  Section 3  Order bump                  only when the request carries a bump
  Section 4  Guarantee and terms         the approved guarantee, terms and consent text, verbatim
  Section 5  Secure checkout             the role's fixed button and microcopy (no commercial fact)

Inputs: --request (the Skill 79 checkout request), --launch (the Skill 49 launch record: offer names,
deliverables, exclusions), --checkout-terms (the 83 intake's approved checkout_terms block, ref and
verbatim text). Nothing is invented: a name, price, term or consent line that the inputs do not hold
refuses the run. The first lines stamp `source_request_sha256` (the sha256 of the request file bytes);
Skill 49's checkout_wrapper.py (CHK-13) refuses a manuscript whose stamp is not the staged request's sha.

Usage:
  emit_checkout_manuscript.py --request R.json --launch L.json --checkout-terms T.json --out copy-checkout.md
Exit: 0 written, 2 refused (no file is left behind), 3 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
_OFFER_MAPPER = HERE.parents[1] / "shared-utils" / "signature_launch_contract" / "offer_mapper.py"
TERMS_KEYS = ("guarantee_text", "terms_text", "consent_text")
BUTTON = "[CTA BUTTON: Complete my order]"
MICROCOPY = "[CTA MICROCOPY: Your payment is processed securely. You will see a confirmation right away.]"


class EmitError(ValueError):
    pass


def _offer_mapper():
    mod = sys.modules.get("offer_mapper")
    if mod is None:
        if not _OFFER_MAPPER.is_file():
            raise EmitError("the shared offer mapper is not installed, so the price cannot be written in its currency")
        spec = importlib.util.spec_from_file_location("offer_mapper", _OFFER_MAPPER)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["offer_mapper"] = mod
        spec.loader.exec_module(mod)
    return mod


def _load(path: str, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EmitError(f"{what}: cannot read {path}: {exc}")


def _offer(launch: Dict[str, Any], offer_id: Any, what: str) -> Dict[str, Any]:
    found = next((o for o in launch.get("offers") or [] if isinstance(o, dict) and o.get("offer_id") == offer_id), None)
    if found is None or not str(found.get("display_name") or "").strip():
        raise EmitError(f"{what} {offer_id!r} has no named offer in the launch record")
    return found


def _price(block: Any, what: str) -> str:
    one_payment = isinstance(block, dict) and block.get("billing_type") == "one_time"
    amount = block.get("amount_minor") if isinstance(block, dict) else None
    if not (one_payment and isinstance(amount, int) and not isinstance(amount, bool) and amount > 0):
        raise EmitError(f"{what} is not a positive one_time price in minor units; payment plans are not "
                        "supported in this release")
    return _offer_mapper().format_money(amount, block["currency"])


def _items(values: Any) -> List[str]:
    return [v.strip() for v in values or [] if isinstance(v, str) and v.strip()]


def build(request: Dict[str, Any], launch: Dict[str, Any], terms: Dict[str, Any], request_sha256: str) -> str:
    """The manuscript text for one checkout request."""
    if not isinstance(terms, dict) or any(not isinstance(terms.get(k), str) or not terms[k].strip()
                                          for k in TERMS_KEYS):
        raise EmitError(f"the approved checkout_terms block needs {', '.join(TERMS_KEYS)} (verbatim text)")
    main = _offer(launch, request.get("main_offer_id"), "main offer")
    name, price = main["display_name"].strip(), _price(request.get("main_price"), "main_price")
    included, excluded = _items(main.get("deliverables")), _items(main.get("exclusions"))
    if not included:
        raise EmitError(f"main offer {main['offer_id']!r} lists no deliverables in the launch record to say what is included")
    one = ["Here is exactly what you are getting today.", f"{name} includes {', '.join(included)}."]
    if excluded:
        one.append(f"It does not include {', '.join(excluded)}.")
    sections = [
        ("1: Offer or selected package", one),
        ("2: Offer details and price", [f"{name}, one payment of {price}.", f"Due today: {price}."]),
    ]
    bump = request.get("bump")
    if isinstance(bump, dict):
        bump_offer = _offer(launch, bump.get("offer_id"), "bump offer")
        copy = [s.strip() for s in (bump.get("headline"), bump.get("benefit_explanation")) if isinstance(s, str) and s.strip()]
        sections.append(("3: Order bump", [f"Yes, add the {bump_offer['display_name'].strip()} to my order.",
                                           " ".join(copy + [f"One-time price of {_price(bump.get('price'), 'bump price')}."])]))
    sections += [("4: Guarantee and terms", [terms[k].strip() for k in TERMS_KEYS]),
                 ("5: Secure checkout", ["Enter your details below to complete your order.", BUTTON, MICROCOPY])]
    out = ["# Order form page", "", f"<!-- source_request_sha256: {request_sha256} -->", ""]
    for heading, paragraphs in sections:
        out += [f"## Section {heading}", ""]
        for paragraph in paragraphs:
            out += [paragraph, ""]
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for flag in ("request", "launch", "checkout-terms", "out"):
        ap.add_argument(f"--{flag}", required=True)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code else 0
    out = Path(args.out)
    try:
        digest = hashlib.sha256(Path(args.request).read_bytes()).hexdigest()
        terms = _load(args.checkout_terms, "checkout_terms")
        if isinstance(terms, dict):  # the block itself, or a document holding it
            terms = terms.get("checkout_terms", terms)
        text = build(_load(args.request, "checkout request"), _load(args.launch, "launch record"), terms, digest)
    except (EmitError, KeyError, OSError) as exc:
        out.unlink(missing_ok=True)  # a refused run leaves no manuscript to be mistaken for a good one
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(json.dumps({"manuscript": str(out), "source_request_sha256": digest}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
