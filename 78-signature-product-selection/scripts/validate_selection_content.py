#!/usr/bin/env python3
"""validate_selection_content.py - Skill 78 copy gate (S78-04).

Fails authored selection copy before publication when it contains:
- an unproven popularity / best-seller / savings / scarcity claim without
  claim-specific evidence (doc 08 s4). Evidence must name the exact claim
  phrase it supports, inside the same copy block (claim_evidence). A
  document-level evidence_refs list is a bibliography and exempts nothing.
- an ambiguous scope term ("VIP support", "premium access", "and more",
  generic prestige words) with no concrete definition of what it means in
  the same block (doc 08 s5).
- a displayed price that differs from the approved catalog price for that
  offer (wrong displayed price is an automatic fail, doc 08 s10 / doc 16
  s8). Currency parsing uses each currency's own minor-unit exponent.
- a hidden material exclusion: every exclusion in the catalog must appear
  verbatim in the visible copy blocks for that offer.
- payment language: CTAs say "Choose [package]", never "Buy now", and the
  selection page collects no payment details.

Copy document shape (JSON):
  {"blocks": [{"offer_id": "MAIN-PRO", "text": "...",
               "claim_evidence": {"most popular": "evidence-ref"}}],
   "evidence_refs": ["bibliography only"]}

Usage:
  validate_selection_content.py <copy.json> <launch.json>
  validate_selection_content.py --self-test
Exit: 0 pass, 2 violation, 3 fail-closed error.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection_core import (  # noqa: E402
    Violation, currency_exponent, format_money, scan_claims, validate_catalog,
)
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402

SYMBOL_CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
MONEY_RE = re.compile(r"([$€£¥])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2,3}))?")
CODE_MONEY_RE = re.compile(r"\b([A-Z]{3})\s(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,3}))?")
KNOWN_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD",
    "MXN", "SGD", "HKD", "NOK", "KRW", "TRY", "ZAR", "PLN", "THB", "IDR",
    "BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND", "BIF", "CLP", "DJF",
    "GNF", "ISK", "KMF", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}

V_PRICE_MISMATCH = "S78-COPY-PRICE-MISMATCH"
V_HIDDEN_EXCLUSION = "S78-HIDDEN-EXCLUSION"
V_AMBIGUOUS = "S78-AMBIGUOUS-COPY"

AMBIGUOUS_TERMS = [
    "vip support",
    "premium access",
    "premium support",
    "and more",
    "world-class",
    "best-in-class",
    "top-notch",
    "everything you need",
]


def _money_to_minor(symbol: str, whole: str, frac):
    currency = SYMBOL_CURRENCIES[symbol]
    exp = currency_exponent(currency)
    digits = whole.replace(",", "")
    if exp == 0:
        return int(digits)
    frac = (frac or "") + "0" * exp
    return int(digits) * (10 ** exp) + int(frac[:exp])


def _code_money_to_minor(code: str, whole: str, frac):
    exp = currency_exponent(code)
    digits = whole.replace(",", "")
    if exp == 0:
        if frac:
            return None
        return int(digits)
    frac = (frac or "") + "0" * exp
    if len(frac) > exp and frac[exp:].strip("0"):
        return None
    return int(digits) * (10 ** exp) + int(frac[:exp])


def validate_content(copy_doc, launch):
    validate_catalog(launch)
    mains = {o["offer_id"]: o for o in launch["offers"] if o.get("slot") == "main"}
    text_by_offer = {}
    for block in copy_doc.get("blocks", []):
        oid = block.get("offer_id")
        if oid not in mains:
            raise Violation("S78-SELECTION-UNKNOWN-OFFER", f"Copy block for unapproved offer {oid!r}.")
        text = block.get("text", "")
        scan_claims(text, claim_evidence=block.get("claim_evidence") or {})
        low = text.lower()
        if "buy now" in low:
            raise Violation("S78-CTA-PAYMENT-LANGUAGE", "Selection CTA must say 'Choose [package]'; clicking selects, it does not buy.")
        if "card number" in low or "credit card" in low:
            raise Violation("S78-PAYMENT-COLLECTION", "Selection page must not collect payment details.")
        for term in AMBIGUOUS_TERMS:
            if term in low and "means" not in low and "defined as" not in low:
                raise Violation(
                    V_AMBIGUOUS,
                    f"Copy for {oid!r} uses ambiguous scope term {term!r} without defining "
                    "what it means in concrete scope; define it or replace it with deliverables.",
                )
        text_by_offer.setdefault(oid, []).append(text)
    for oid, offer in mains.items():
        if oid not in text_by_offer:
            continue  # no copy blocks for this offer: nothing to check here
        joined = "\n".join(text_by_offer.get(oid, []))
        approved_minors = {int(p["amount_minor"]) for p in offer["prices"]}
        for m in MONEY_RE.finditer(joined):
            minor = _money_to_minor(m.group(1), m.group(2), m.group(3))
            if minor not in approved_minors:
                expected = ", ".join(
                    format_money(a, offer["prices"][0]["currency"]) for a in sorted(approved_minors)
                )
                raise Violation(
                    V_PRICE_MISMATCH,
                    f"Copy for {oid!r} displays {m.group(0)} but approved prices are {expected}; "
                    "a wrong displayed price is an automatic fail.",
                )
        offer_currencies = {p["currency"] for p in offer["prices"]}
        for m in CODE_MONEY_RE.finditer(joined):
            code = m.group(1)
            if code not in KNOWN_CURRENCY_CODES:
                continue
            minor = _code_money_to_minor(code, m.group(2), m.group(3))
            if code not in offer_currencies or minor is None or minor not in approved_minors:
                expected = ", ".join(
                    format_money(a, offer["prices"][0]["currency"]) for a in sorted(approved_minors)
                )
                raise Violation(
                    V_PRICE_MISMATCH,
                    f"Copy for {oid!r} displays {m.group(0)} but approved prices are {expected}; "
                    "a wrong displayed price is an automatic fail.",
                )
        for ex in offer.get("exclusions", []):
            if ex not in joined:
                raise Violation(
                    V_HIDDEN_EXCLUSION,
                    f"Material exclusion {ex!r} for {oid!r} does not appear verbatim in the visible copy; "
                    "exclusions are never hidden, including on mobile.",
                )
    return True


def self_test():
    good = {"blocks": [
        {"offer_id": "MAIN-A", "text": "Choose TEST ONLY A. Includes base-a only. No private reviews. $97.00 one time."},
        {"offer_id": "MAIN-B", "text": "Choose TEST ONLY B. Get personal feedback - includes two private review sessions. $197.00 one time."},
    ], "evidence_refs": []}
    assert validate_content(good, SELF_TEST_LAUNCH)
    for blocks, code in [
        ([{"offer_id": "MAIN-B", "text": "Our most popular package!"}], "S78-UNPROVEN-CLAIM"),
        ([{"offer_id": "MAIN-A", "text": "No private reviews. Most popular, $97.00.", "evidence_refs": ["unrelated"]},
          {"offer_id": "MAIN-B", "text": "$197.00"}], "S78-UNPROVEN-CLAIM"),
        ([{"offer_id": "MAIN-B", "text": "Only $150.00 today."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "USD 150.00 today."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "EUR 197.00 today."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "$19700 flat."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "USD 19700.00 flat."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "$19,700 flat."}], V_PRICE_MISMATCH),
        ([{"offer_id": "MAIN-B", "text": "Buy now and save!"}], "S78-CTA-PAYMENT-LANGUAGE"),
        ([{"offer_id": "MAIN-B", "text": "$197.00. Includes VIP support and more."}], V_AMBIGUOUS),
        ([{"offer_id": "MAIN-A", "text": "$97.00 one time."},
          {"offer_id": "MAIN-B", "text": "$197.00"}], V_HIDDEN_EXCLUSION),
        ([{"offer_id": "MAIN-Z", "text": "Choose TEST ONLY Z."}], "S78-SELECTION-UNKNOWN-OFFER"),
    ]:
        try:
            validate_content({"blocks": blocks, "evidence_refs": ["doc-level-only"]}, SELF_TEST_LAUNCH)
        except Violation as v:
            assert v.code == code, (v.code, code)
        else:
            raise AssertionError(f"copy was not rejected with {code}")
    # Claim-specific, block-level evidence DOES exempt the exact claim.
    ok_claim = {"blocks": [
        {"offer_id": "MAIN-A", "text": "No private reviews. $97.00. Most popular.",
         "claim_evidence": {"most popular": "registrations-Q3-report"}},
        {"offer_id": "MAIN-B", "text": "$197.00"}], "evidence_refs": []}
    assert validate_content(ok_claim, SELF_TEST_LAUNCH)
    # Zero-decimal catalog: an unseparated JPY amount parses whole, not truncated.
    import copy as _copy
    jpy_launch = _copy.deepcopy(SELF_TEST_LAUNCH)
    for offer in jpy_launch["offers"]:
        for p in offer["prices"]:
            p["currency"] = "JPY"
    jpy_copy = {"blocks": [
        {"offer_id": "MAIN-A", "text": "No private reviews. JPY 9700 one time."},
        {"offer_id": "MAIN-B", "text": "JPY 19700 one time."}], "evidence_refs": []}
    assert validate_content(jpy_copy, jpy_launch)
    try:
        validate_content({"blocks": [
            {"offer_id": "MAIN-A", "text": "No private reviews. JPY 970 one time."},
            {"offer_id": "MAIN-B", "text": "JPY 19700 one time."}], "evidence_refs": []}, jpy_launch)
    except Violation as v:
        assert v.code == V_PRICE_MISMATCH, v.code
    else:
        raise AssertionError("truncated JPY amount was not rejected")
    print("validate_selection_content --self-test: PASS (per-block claim evidence; doc-level bypass, price mismatch, hidden exclusion, ambiguity, CTA rejections)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: validate_selection_content.py <copy.json> <launch.json>", file=sys.stderr)
        return 3
    try:
        validate_content(json.loads(Path(args[0]).read_text()), json.loads(Path(args[1]).read_text()))
    except Violation as v:
        print(f"VIOLATION [{v.code}]: {v.message}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print("CONTENT PASS: copy facts match the approved catalog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
