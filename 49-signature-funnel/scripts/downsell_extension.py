#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""downsell_extension.py - derive the Skill 81 D1 result extension (DTY-05/06/07/13).

Nothing in the launcher used to produce the D1 result extension or the trial
disclosure: the operator (or the AI) staged both by hand, so a trial D1 could
be labelled one_time, the page could state any price, and the wrapper only
compared one number. This module DERIVES both documents from three things the
run already holds and that are checked elsewhere: the validated D1 page copy,
the launch record's offers, and the hash-verified route graph. Nothing is
attested by the operator, so there is nothing to forge.

What it checks, all fail-closed, each problem prefixed with a named code:

  price-not-in-record     the page states a currency amount that is not this
                          D1 offer's due-now, renewal or schedule amount
                          (D1 only, never "any offer in the launch")
  price-not-on-page       the page never states the due-now amount
  missing-renewal-terms   a trial/recurring/installment page lacks the renewal
                          amount, the interval, or a cancellation statement
                          (or the trial length a trial must state)
  D1-OFFER-REGRANTS-MAIN  D1 grants an entitlement a main or bump offer grants
  D1-EXTENSION-*          a staged (hand-authored) extension disagrees with
                          what the page and record say; the message names the
                          field, e.g. "billing_type mismatch"

entitlements_removed_vs_u1 is computed from the U1 and D1 offers
(offer_difference_inputs) and the base-purchase check runs over EVERY main and
bump offer, so it no longer disappears when a launch has two mains.

Wiring (the wrapper, owned elsewhere): when no --extension is staged call
derive(); when one is staged pass it as `staged` so it is cross-checked; feed
validate_offer_difference the tuple from offer_difference_inputs(); write the
returned documents with dump() so the bytes are reproducible.

Deterministic, stdlib only. Exit 0 ok, 2 fail-closed, 3 usage.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

EXIT_OK, EXIT_FAILCLOSED, EXIT_USAGE = 0, 2, 3
CANONICAL_HEADING = "When Time Runs Out"
PROSE_HEADING = "When Times Run Out"
UI_STATES_REF = "references/native-action-states.md#states"
NON_ONE_TIME = ("trial", "recurring", "installment")
DIFFERENCE_KINDS = ("reduced_scope", "lower_total_price",
                    "changed_payment_terms", "changed_access_terms")
ZERO_DECIMAL = ("JPY", "KRW", "VND", "CLP")  # currencies with no minor unit


class ExtensionError(ValueError):
    """Fail-closed refusal; `problems` are '<code>: <detail>' strings."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def dump(doc: Any) -> str:
    """The one serialization: sorted keys, so equal inputs give equal bytes."""
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# The page and the record
# ---------------------------------------------------------------------------
def page_object(copy_doc: Any) -> Dict[str, Any]:
    if isinstance(copy_doc, dict) and isinstance(copy_doc.get("page"), dict):
        return copy_doc["page"]
    return copy_doc if isinstance(copy_doc, dict) else {}


def _sections(page: Mapping[str, Any]) -> List[Dict[str, Any]]:
    s = page.get("sections")
    return [x if isinstance(x, dict) else {} for x in s] \
        if isinstance(s, list) else []


def _surface(page: Mapping[str, Any]) -> str:
    """Every customer-visible string: headings, bodies, CTA labels, missed
    items, the decline label."""
    out: List[str] = []
    for s in _sections(page):
        out += [s.get("heading"), s.get("body"),
                (s.get("cta") or {}).get("label")
                if isinstance(s.get("cta"), dict) else None]
        if isinstance(s.get("missed_out_items"), list):
            out += s["missed_out_items"]
    d = page.get("decline_action")
    if isinstance(d, dict):
        out.append(d.get("label"))
    return "\n".join(x for x in out if isinstance(x, str))


def _offer(launch: Mapping[str, Any], slot: str) -> Optional[Dict[str, Any]]:
    hits = [o for o in launch.get("offers") or []
            if isinstance(o, dict) and o.get("slot") == slot]
    return hits[0] if len(hits) == 1 else None


def _price(offer: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    prices = [p for p in offer.get("prices") or [] if isinstance(p, dict)]
    approved = [p for p in prices
                if p.get("approval_status") in ("approved", "provided")]
    if len(approved) == 1:
        return approved[0]
    return prices[0] if len(prices) == 1 else None


def _schedule(price: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [r for r in price.get("schedule") or []
            if isinstance(r, dict) and _int(r.get("amount_minor"))]


def _allowed_amounts(price: Mapping[str, Any]) -> List[int]:
    """This D1 offer's own due-now, renewal and schedule amounts."""
    amounts = {r["amount_minor"] for r in _schedule(price)}
    if _int(price.get("amount_minor")):
        amounts.add(price["amount_minor"])
    return sorted(amounts)


# ---------------------------------------------------------------------------
# Currency amounts stated on the page
# ---------------------------------------------------------------------------
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
_CODES = r"(?:usd|eur|gbp|cad|aud|jpy)"
_AMOUNT_PATTERNS = [
    re.compile(r"[$€£¥]\s?" + _NUM),
    re.compile(r"\b" + _NUM + r"\s?" + _CODES + r"\b", re.I),
    re.compile(r"\b" + _CODES + r"\s?" + _NUM, re.I),
    re.compile(r"\b" + _NUM + r"[\s-]?(?:dollars?|bucks?)\b", re.I),
]
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
          "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
          "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
          "seventy": 70, "eighty": 80, "ninety": 90}


def stated_amounts(text: str, currency: str = "USD") -> List[Tuple[str, Decimal]]:
    """(source text, amount in MINOR units) for every currency figure in the
    text: $27, $27.00, 1,997 USD, USD 27, 27 dollars, twenty-seven dollars."""
    unit = Decimal(1) if currency in ZERO_DECIMAL else Decimal(100)
    found: List[Tuple[str, Decimal]] = []
    for pat in _AMOUNT_PATTERNS:
        for m in pat.finditer(text):
            whole, frac = m.group(1).replace(",", ""), m.group(2) or "0"
            found.append((m.group(0).strip(),
                          Decimal(f"{whole}.{frac}") * unit))
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    for i, w in enumerate(words):
        if w in ("dollar", "dollars", "buck", "bucks") and i \
                and words[i - 1] in _WORDS:
            v = _WORDS[words[i - 1]]
            if i > 1 and _WORDS.get(words[i - 2], 0) >= 20 and v < 10:
                v += _WORDS[words[i - 2]]
            found.append((" ".join(words[max(0, i - 2):i + 1]),
                          Decimal(v) * unit))
    return found


_INTERVAL = re.compile(
    r"\b(?:per|a|each|every)\s+(?:\d+\s+)?(?:day|week|month|quarter|year)s?\b"
    r"|\b(?:daily|weekly|monthly|quarterly|yearly|annually)\b"
    r"|/\s?(?:mo|month|week|year)\b", re.I)
_TRIAL_LEN = re.compile(r"\b(\d+)[\s-]?(day|week|month)s?\b", re.I)


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text)
            if s.strip()]


def _money(minor: int, currency: str) -> str:
    return f"{minor} {currency}" if currency in ZERO_DECIMAL \
        else f"{minor / 100:.2f} {currency}"


def check_page_against_price(page: Mapping[str, Any],
                             price: Mapping[str, Any]) -> List[str]:
    """DTY-07: the page may state only this D1's own amounts, must state its
    due-now amount, and a non-one-time page must state the renewal amount, the
    interval and a cancellation statement."""
    text, problems = _surface(page), []
    currency = price.get("currency") or "USD"
    allowed = _allowed_amounts(price)
    stated = stated_amounts(text, currency)
    for src, minor in stated:
        if minor not in allowed:
            problems.append(
                f"price-not-in-record: the page states {src!r} "
                f"({minor} minor units), which is not a due-now, renewal or "
                f"schedule amount of this D1 offer (approved: {allowed})")
    amounts = {m for _, m in stated}
    due = price.get("amount_minor")
    if _int(due) and due not in amounts and not (
            due == 0 and re.search(r"\bfree\b", text, re.I)):
        problems.append(
            f"price-not-on-page: the page never states the due-now amount "
            f"{_money(due, currency)}; the client would approve a design "
            "that hides the price")
    if price.get("billing_type") in NON_ONE_TIME:
        sched, missing = _schedule(price), []
        if not sched:
            missing.append("renewal amount (the record's price has no "
                           "schedule row to state)")
        elif sched[-1]["amount_minor"] not in amounts:
            missing.append(
                f"renewal amount {_money(sched[-1]['amount_minor'], currency)}")
        # the interval must sit in a sentence about money or renewal:
        # "weekly trainings" is content, not a billing interval
        if not any(_INTERVAL.search(s) for s in _sentences(text)
                   if stated_amounts(s, currency)
                   or re.search(r"\brenew", s, re.I)):
            missing.append("billing interval")
        if not re.search(r"\bcancel", text, re.I):
            missing.append("cancellation statement")
        if price.get("billing_type") == "trial" \
                and not _TRIAL_LEN.search(text):
            missing.append("trial length")
        if missing:
            problems.append(
                f"missing-renewal-terms: the {price['billing_type']} D1 page "
                "does not state its " + ", ".join(missing))
    return problems


# ---------------------------------------------------------------------------
# DTY-13: offer difference inputs and the entitlement guards
# ---------------------------------------------------------------------------
def _ids(offer: Optional[Mapping[str, Any]]) -> List[str]:
    v = (offer or {}).get("entitlement_ids")
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def entitlements_removed_vs_u1(u1: Mapping[str, Any],
                               d1: Mapping[str, Any]) -> List[str]:
    """What U1 grants that D1 does not, in U1 order (casefolded compare)."""
    have = {x.casefold() for x in _ids(d1)}
    return [x for x in _ids(u1) if x.casefold() not in have]


def offer_difference_inputs(launch: Mapping[str, Any],
                            sidecar: Mapping[str, Any]):
    """(u1, d1, base) for validate_offer_difference: d1 carries the sidecar's
    difference_kind and rationale AND the computed entitlements_removed_vs_u1;
    base is ONE synthetic offer holding every main and bump entitlement, so the
    base-purchase check runs for a multi-main launch too (it used to skip)."""
    u1, d1 = _offer(launch, "upsell_1"), _offer(launch, "downsell_1")
    if u1 is None or d1 is None:
        raise ExtensionError(["offer-slot: the launch record needs exactly "
                              "one upsell_1 and one downsell_1 offer"])
    d1x = copy.deepcopy(d1)
    d1x["difference_kind"] = sidecar.get("difference_kind")
    d1x["rationale"] = sidecar.get("rationale")
    d1x["entitlements_removed_vs_u1"] = entitlements_removed_vs_u1(u1, d1)
    held: List[str] = []
    for o in launch.get("offers") or []:
        if isinstance(o, dict) and o.get("slot") in ("main", "bump"):
            held += _ids(o)
    return u1, d1x, {"slot": "main", "entitlement_ids": held}


def check_regrants_main(launch: Mapping[str, Any]) -> List[str]:
    """A D1 that grants what any main or bump already grants is the main
    product again at a lower price, not an alternative."""
    d1 = _offer(launch, "downsell_1") or {}
    mine = {x.casefold() for x in _ids(d1)}
    problems = []
    for o in launch.get("offers") or []:
        if isinstance(o, dict) and o.get("slot") in ("main", "bump"):
            shared = sorted(x for x in _ids(o) if x.casefold() in mine)
            if shared:
                problems.append(
                    f"D1-OFFER-REGRANTS-MAIN: D1 grants {shared}, which "
                    f"{o.get('slot')} offer {o.get('offer_id')!r} already "
                    "grants; a downsell must be a genuine alternative")
    return problems


# ---------------------------------------------------------------------------
# The route graph
# ---------------------------------------------------------------------------
def route_result(graph: Mapping[str, Any], page_id: Any) -> Dict[str, Any]:
    role = {n.get("page_id"): n.get("role") for n in graph.get("nodes") or []
            if isinstance(n, dict)}
    if role.get(page_id) != "downsell_1":
        raise ExtensionError([f"route-graph: no downsell_1 node {page_id!r}"])
    paid = [e.get("to") for e in graph.get("edges") or []
            if isinstance(e, dict) and e.get("from") == page_id
            and e.get("event") == "payment_succeeded"]
    if len(paid) != 1 or role.get(paid[0]) not in ("upsell_2", "thank_you"):
        raise ExtensionError(
            [f"route-graph: the D1 node needs exactly one payment_succeeded "
             f"edge into upsell_2 or thank_you; found {len(paid)}"])
    target = role[paid[0]]
    return {"success_target": target, "decline_target": "thank_you",
            "u2_entry_context": "from_downsell_1",
            "canonical_u2_page_id": paid[0] if target == "upsell_2" else None}


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------
def _disclosure_audit(page, price) -> Dict[str, Any]:
    text = _surface(page)
    sched = _schedule(price)
    non_one = price.get("billing_type") in NON_ONE_TIME
    return {"billing_type": price["billing_type"],
            "due_now_minor": price.get("amount_minor"),
            "renewal_amount_minor": sched[-1]["amount_minor"]
            if non_one and sched else None,
            "renewal_date_or_rule": sched[-1].get("due")
            if non_one and sched else None,
            "cancellation_terms_present":
                bool(re.search(r"\bcancel", text, re.I))}


def build_disclosure(page: Mapping[str, Any],
                     price: Mapping[str, Any]) -> Dict[str, Any]:
    """The trial/recurring disclosure document validate_trial_disclosure reads,
    taken from the page's own sentences and the record's schedule."""
    text, sents = _surface(page), _sentences(_surface(page))
    cancel = [s for s in sents if re.search(r"\bcancel", s, re.I)]
    access = [s for s in cancel if re.search(r"\baccess\b", s, re.I)] \
        or [s for s in sents if re.search(r"\baccess\b", s, re.I)]
    interval = next((m for s in sents if stated_amounts(s) or re.search(
        r"\brenew", s, re.I) for m in [_INTERVAL.search(s)] if m), None)
    length = _TRIAL_LEN.search(text)
    audit = _disclosure_audit(page, price)
    return {"due_now_minor": audit["due_now_minor"],
            "trial_length": length.group(0) if length
            and price["billing_type"] == "trial" else "none",
            "renewal_amount_minor": audit["renewal_amount_minor"],
            "renewal_date_or_rule": audit["renewal_date_or_rule"],
            "interval": interval.group(0) if interval else None,
            "cancellation_terms": cancel[0] if cancel else None,
            "access_implications": access[0] if access else None}


def derive(request: Mapping[str, Any], launch: Mapping[str, Any],
           graph: Mapping[str, Any], copy_doc: Any,
           sidecar: Mapping[str, Any],
           staged: Any = None) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Return (extension, disclosure-or-None), or raise ExtensionError naming
    every problem. `staged` is an operator-authored extension, if any: it is
    never trusted, only cross-checked against what was derived."""
    problems: List[str] = []
    page = page_object(copy_doc)
    d1 = _offer(launch, "downsell_1")
    price = _price(d1) if d1 else None
    if price is None or price.get("billing_type") not in (
            "one_time", *NON_ONE_TIME):
        raise ExtensionError(
            ["offer-price: the record's D1 offer needs exactly one price "
             "choice with a billing_type"])
    problems += check_page_against_price(page, price)
    problems += check_regrants_main(launch)
    kind = sidecar.get("difference_kind")
    if kind not in DIFFERENCE_KINDS or _blank(sidecar.get("rationale")):
        problems.append(
            "difference-kind: the sidecar needs a recorded difference_kind "
            "and rationale")
    secs = _sections(page)
    heading = (secs[7].get("heading") or "").strip().rstrip(":").strip() \
        if len(secs) == 8 and isinstance(secs[7].get("heading"), str) else None
    if heading != CANONICAL_HEADING:
        problems.append(
            f"heading-normalization: section 8 heading is {heading!r}; the "
            f"page must show {CANONICAL_HEADING!r}")
    ctas = [s.get("cta") if isinstance(s.get("cta"), dict) else {}
            for s in secs]
    decline = page.get("decline_action")
    decline_ref = decline.get("action_ref") \
        if isinstance(decline, dict) else None
    if len(secs) != 8 or any(_blank(c.get("action_ref")) for c in ctas) \
            or _blank(decline_ref):
        problems.append("cta-map: the page needs 8 sections each with a CTA "
                        "action_ref, and a decline action_ref")
    try:
        route = route_result(graph, request.get("page_id"))
    except ExtensionError as exc:
        problems += exc.problems
    if problems:
        raise ExtensionError(problems)

    u1 = _offer(launch, "upsell_1") or {}
    removed = entitlements_removed_vs_u1(u1, d1)
    kept = {x.casefold() for x in _ids(u1)}
    scope = ("; ".join(str(x) for x in d1.get("deliverables") or [])
             or "no deliverables recorded")
    cur = price.get("currency") or "USD"
    audit = _disclosure_audit(page, price)
    ext = {
        "refined_offer_description":
            f"{d1.get('display_name') or d1.get('offer_id')}: {scope}. "
            f"{_money(price['amount_minor'], cur)} due now"
            if _int(price.get("amount_minor")) else
            f"{d1.get('display_name') or d1.get('offer_id')}: {scope}.",
        "ui_states_ref": UI_STATES_REF,
        # ponytail: objection_addressed reuses the recorded rationale; add a
        # sidecar key if the difference table ever records them separately.
        "difference_matrix": {
            "difference_kind": kind, "rationale": sidecar["rationale"],
            "objection_addressed": sidecar["rationale"],
            "entitlements_u1_only": removed,
            "entitlements_d1_only": [x for x in _ids(d1)
                                     if x.casefold() not in kept]},
        "disclosure_audit": audit,
        "cta_map": [{"section": i, "action_ref": c["action_ref"]}
                    for i, c in enumerate(ctas, 1)],
        "decline_action_ref": decline_ref,
        "source_profile_mapping": [
            {"derived_section": n, "original_sections": [str(n)]}
            for n in range(1, 8)] + [
            {"derived_section": 8, "original_sections": ["12-replaced"]}],
        "heading_normalization": {
            "canonical_display": CANONICAL_HEADING,
            "corpus_prose_form": PROSE_HEADING,
            "corpus_sample_form": CANONICAL_HEADING, "recorded": True},
        "route_result": route,
    }
    if staged is not None:
        stale = check_staged(staged, ext)
        if stale:
            raise ExtensionError(stale)
    disclosure = build_disclosure(page, price) \
        if price["billing_type"] in NON_ONE_TIME else None
    return ext, disclosure


def check_staged(staged: Any, derived: Mapping[str, Any]) -> List[str]:
    """DTY-06: a staged extension must say what the page and record say."""
    if isinstance(staged, dict) and isinstance(
            staged.get("downsell_result_extension"), dict):
        staged = staged["downsell_result_extension"]
    if not isinstance(staged, dict):
        return ["D1-EXTENSION-MALFORMED: the staged extension is not an object"]
    got_a = staged.get("disclosure_audit") \
        if isinstance(staged.get("disclosure_audit"), dict) else {}
    want_a = derived["disclosure_audit"]
    out = []
    if got_a.get("billing_type") != want_a["billing_type"]:
        out.append(
            f"D1-EXTENSION-BILLING-TYPE-MISMATCH: billing_type mismatch: the "
            f"staged extension says {got_a.get('billing_type')!r} but the "
            f"approved D1 price is {want_a['billing_type']!r}")
    for key in ("due_now_minor", "renewal_amount_minor",
                "renewal_date_or_rule", "cancellation_terms_present"):
        if got_a.get(key) != want_a[key]:
            out.append(f"D1-EXTENSION-DISCLOSURE-MISMATCH: {key} mismatch: "
                       f"staged {got_a.get(key)!r}, derived {want_a[key]!r}")
    for key in ("cta_map", "decline_action_ref", "route_result"):
        if staged.get(key) != derived[key]:
            out.append(f"D1-EXTENSION-{key.upper().replace('_', '-')}-"
                       f"MISMATCH: {key} mismatch: the staged value does not "
                       "match the page and route graph")
    return out


# ---------------------------------------------------------------------------
# Command line: derive and write the extension (and disclosure) files
# ---------------------------------------------------------------------------
def _load(path: str, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExtensionError([f"input: cannot load {what} {path}: {exc}"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("request", "launch", "route-graph", "copy", "enrichment",
                 "out"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--staged-extension",
                    help="operator-authored extension to cross-check")
    ap.add_argument("--disclosure-out",
                    help="where to write the trial/recurring disclosure")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    try:
        ext, disclosure = derive(
            _load(args.request, "request"), _load(args.launch, "launch"),
            _load(args.route_graph, "route graph"),
            _load(args.copy, "copy"), _load(args.enrichment, "enrichment"),
            _load(args.staged_extension, "staged extension")
            if args.staged_extension else None)
        Path(args.out).write_text(dump(ext), encoding="utf-8")
        if disclosure is not None and args.disclosure_out:
            Path(args.disclosure_out).write_text(dump(disclosure),
                                                 encoding="utf-8")
    except ExtensionError as exc:
        for p in exc.problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    print(json.dumps({"extension": args.out,
                      "sha256": hashlib.sha256(
                          Path(args.out).read_bytes()).hexdigest()}))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
