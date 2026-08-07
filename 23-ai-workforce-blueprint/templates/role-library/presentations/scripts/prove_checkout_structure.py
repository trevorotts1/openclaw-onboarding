#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_checkout_structure.py — fail-closed prover for the lean CHECKOUT page
(presentations upsell pipeline, GAUNTLET-LOOP DESIGN-OPUS §10.3 / F6).

Enforces the SACRED lean-checkout structure declared in
scripts/structure/checkout_structure.json, IN ORDER, and asserts the page actually
contains every mandatory element the design demands:

  * offer-summary / order summary                            -> AF-PRES-CHECKOUT-SUMMARY-MISSING
  * a real order form with EMAIL + FULL-NAME fields          -> AF-PRES-CHECKOUT-FIELDS-MISSING
  * the price                                                -> AF-PRES-CHECKOUT-PRICE-MISSING
  * the guarantee                                            -> AF-PRES-CHECKOUT-GUARANTEE-MISSING
  * trust badges (>= structure trust_badge_min)              -> AF-PRES-CHECKOUT-TRUST-MISSING
  * a single dominant submit CTA                             -> AF-PRES-CHECKOUT-CTA-MISSING / -MULTI-CTA
  * the 8 canonical sections present in canonical order      -> AF-PRES-CHECKOUT-SECTION-{COUNT,MISSING,UNKNOWN,ORDER}
  * per-section stripped-word band (measured, self-report
    ignored)                                                 -> AF-PRES-CHECKOUT-SECTION-BAND
  * payment card fields ONLY when the checkout is LIVE
    (F6 honest degradation: lead-capture mode still requires
    the payment-fields SECTION but not the card inputs)      -> AF-PRES-CHECKOUT-PAYMENT-MISSING

Two input modes (both fail-closed):
  --html   <checkout page HTML fragment>   — element-ledger assertions on the page itself.
  --ledger <copy_ledger.json>              — copy-ledger assertions (Skill 56 pattern) over
                                             assets whose stage == "checkout".

stdlib only. Exit 0 = pass, 2 = violation (autofail), 3 = usage/IO (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_EMPTY = "AF-PRES-CHECKOUT-EMPTY"
AF_SUMMARY = "AF-PRES-CHECKOUT-SUMMARY-MISSING"
AF_FIELDS = "AF-PRES-CHECKOUT-FIELDS-MISSING"
AF_PAYMENT = "AF-PRES-CHECKOUT-PAYMENT-MISSING"
AF_PRICE = "AF-PRES-CHECKOUT-PRICE-MISSING"
AF_GUARANTEE = "AF-PRES-CHECKOUT-GUARANTEE-MISSING"
AF_TRUST = "AF-PRES-CHECKOUT-TRUST-MISSING"
AF_CTA = "AF-PRES-CHECKOUT-CTA-MISSING"
AF_MULTI_CTA = "AF-PRES-CHECKOUT-MULTI-CTA"
AF_COUNT = "AF-PRES-CHECKOUT-SECTION-COUNT"
AF_SECTION_MISSING = "AF-PRES-CHECKOUT-SECTION-MISSING"
AF_UNKNOWN = "AF-PRES-CHECKOUT-SECTION-UNKNOWN"
AF_ORDER = "AF-PRES-CHECKOUT-SECTION-ORDER"
AF_BAND = "AF-PRES-CHECKOUT-SECTION-BAND"
AF_STRUCTURE = "AF-PRES-CHECKOUT-STRUCTURE-LOAD"

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR / "structure" / "checkout_structure.json"


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _strip_tags(blob: Any) -> str:
    return _TAG_RE.sub(" ", str(blob or ""))


def _stripped_words(blob: Any) -> int:
    text = _strip_tags(blob)
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def _phrase_present(norm_text: str, phrase: str) -> bool:
    p = _norm(phrase)
    if not p or not norm_text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", norm_text) is not None


def _load_canonical() -> Dict[str, Any]:
    return json.loads(STRUCTURE.read_text(encoding="utf-8"))


def _sections(canon: Dict[str, Any]) -> List[Dict[str, Any]]:
    return canon["sections"]


def _attr_pos(html: str, sid: str) -> Optional[int]:
    """Earliest HTML-attribute position that NAMES the section (class/id/data-section attr
    or the tag itself, e.g. <header>/<footer>). This is the PRIMARY, unambiguous detector —
    a `class="trust"` on the real section beats the word 'trust bar' in the nav chrome."""
    raw = html.lower()
    attr_patterns = [
        rf'class="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'id="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'data-section="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'<{re.escape(sid)}(?=[\s>])',
    ]
    found: List[int] = []
    for pat in attr_patterns:
        m = re.search(pat, raw)
        if m:
            found.append(m.start())
    return min(found) if found else None


def _phrase_first_pos(norm_text: str, entry: Dict[str, Any]) -> Optional[int]:
    """Earliest occurrence of any id/alias for a section in the normalized text (fallback)."""
    phrases = [entry["id"]] + list(entry.get("aliases", []))
    found: List[int] = []
    for ph in phrases:
        m = re.search(r"(?<![a-z0-9])" + re.escape(_norm(ph)) + r"(?![a-z0-9])", norm_text)
        if m:
            found.append(m.start())
    return min(found) if found else None


def _body(html: str) -> str:
    """Return the <body>...</body> slice; fall back to the whole document so GHL
    code-block fragments (which are body-only) still work. Excludes <head>/<title> so
    'Secure Checkout' in the title can never masquerade as a page section."""
    low = html.lower()
    m = re.search(r"<body[^>]*>(.*)</body>", low, re.S)
    if m:
        return html[m.start(1):m.end(1)]
    m = re.search(r"</head[^>]*>", low, re.S)
    if m:
        return html[m.end():]
    return html


def _section_pos(html: str, norm_text: str, entry: Dict[str, Any]) -> Optional[int]:
    """Primary = HTML attribute/tag naming the section id; fallback = phrase markers.
    Phrase fallback is body-scoped so <head>/<title> text never counts as a section."""
    apos = _attr_pos(html, entry["id"])
    if apos is not None:
        return apos
    return _phrase_first_pos(_norm(_strip_tags(_body(html))), entry)


def _field_present(html: str, field_id: str, aliases: List[str]) -> bool:
    """A form field counts as present if an input/textarea/select carries the field id
    (name/id/data-field/type attr) OR a visible label/phrase names it. Checked against RAW
    html so attribute patterns (name=\"email\", type=\"email\") are seen."""
    raw = html.lower()
    attr_patterns = [
        rf'name="{re.escape(field_id)}"',
        rf'id="{re.escape(field_id)}"',
        rf'data-field="{re.escape(field_id)}"',
    ]
    # `type="email"` self-identifies the email field only.
    if field_id == "email":
        attr_patterns.append(r'type="email"')
    for pat in attr_patterns:
        if re.search(pat, raw):
            return True
    norm = _norm(_strip_tags(html))
    return any(_phrase_present(norm, a) for a in aliases)


# ---------------------------------------------------------------------------
# HTML-mode evaluation (element-ledger on the page itself).
# ---------------------------------------------------------------------------
def _verify_html(html: str, canon: Dict[str, Any], degraded: bool = False) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    body_html = _body(html)
    norm = _norm(_strip_tags(body_html))
    if _stripped_words(body_html) < 20:
        return [(AF_EMPTY, "checkout page has no meaningful body copy (fail-closed)")]

    sections = _sections(canon)
    canon_ids = [s["id"] for s in sections]

    # 1) all canonical sections present.
    present: Dict[str, int] = {}
    for sec in sections:
        pos = _section_pos(body_html, norm, sec)
        if pos is None:
            fails.append((AF_SECTION_MISSING,
                          f"canonical checkout section {sec['id']!r} absent from the page "
                          f"(no id/alias attribute or phrase found)"))
        else:
            present[sec["id"]] = pos

    # 2) section order = canonical ascending.
    positions = [(s, present[s]) for s in canon_ids if s in present]
    for i in range(1, len(positions)):
        if positions[i][1] < positions[i - 1][1]:
            fails.append((AF_ORDER,
                          f"sections out of canonical order: {positions[i - 1][0]!r} (pos "
                          f"{positions[i - 1][1]}) before {positions[i][0]!r} (pos "
                          f"{positions[i][1]})"))
            break

    # 3) mandatory elements (the design's lean-checkout core).
    by_id = {s["id"]: s for s in sections}
    if _section_pos(body_html, norm, by_id["offer-summary"]) is None:
        fails.append((AF_SUMMARY, "no offer/order summary block on the checkout page"))
    if _section_pos(body_html, norm, by_id["price"]) is None:
        fails.append((AF_PRICE, "no price / order-total displayed on the checkout page"))
    if _section_pos(body_html, norm, by_id["guarantee"]) is None:
        fails.append((AF_GUARANTEE, "no money-back guarantee / risk-reversal on the checkout page"))

    # 4) order form with email + full-name fields.
    form_spec = canon.get("order_form_fields", {})
    for req in form_spec.get("required", []):
        if not _field_present(html, req["id"], req.get("aliases", [])):
            fails.append((AF_FIELDS, f"order form missing required field {req['id']!r}"))

    # 5) payment card fields — only when the checkout is LIVE (not --degraded).
    pay_fields = form_spec.get("payment_required_when_live", [])
    html_is_degraded = degraded or _norm(html).find("not_configured") != -1
    if not html_is_degraded:
        missing_pay = [f["id"] for f in pay_fields
                       if not _field_present(html, f["id"], f.get("aliases", []))]
        if missing_pay:
            fails.append((AF_PAYMENT, f"live checkout missing payment field(s): {missing_pay}"))

    # 6) trust badges >= structure floor.
    trust_min = int(canon.get("trust_badge_min", 2) or 0)
    trust_phrases = list(by_id["trust"].get("aliases", []))
    trust_hits = sum(1 for ph in trust_phrases if _phrase_present(norm, ph))
    if trust_hits < trust_min:
        fails.append((AF_TRUST,
                      f"only {trust_hits} trust signals found, structure requires >= {trust_min}"))

    # 7) CTA: at least one dominant submit CTA, no CTA clutter (> 3 CTA markers).
    cta = by_id["submit-cta"]
    cta_phrases = [cta["id"]] + list(cta.get("aliases", []))
    cta_hits = sum(1 for ph in cta_phrases if _phrase_present(norm, ph))
    if cta_hits == 0:
        fails.append((AF_CTA, "no submit / order-now CTA on the checkout page"))
    elif cta_hits > 3:
        fails.append((AF_MULTI_CTA,
                      f"{cta_hits} CTA markers found — a lean checkout carries one dominant CTA"))

    # 8) whole-page stripped-word floor = sum of per-section word_mins (measured, self-report
    #    ignored). A lean checkout with real copy clears this easily; a stub cannot.
    total_floor = sum(int(s.get("word_min", 0) or 0) for s in sections)
    wc = _stripped_words(html)
    if wc < total_floor:
        fails.append((AF_BAND,
                      f"checkout page has {wc} stripped words, under the {total_floor}-word "
                      f"aggregate floor"))
    return fails


# ---------------------------------------------------------------------------
# Ledger-mode evaluation (Skill 56 copy-ledger pattern).
# ---------------------------------------------------------------------------
def _match_section(name: str, sections: List[Dict[str, Any]]) -> Optional[str]:
    n = _norm(name)
    if not n:
        return None
    for sec in sections:
        if n == sec["id"]:
            return sec["id"]
    for sec in sections:
        for alias in sec.get("aliases", []):
            a = _norm(alias)
            if a and (a in n or n in a):
                return sec["id"]
    return None


def _section_copy(sec: Any) -> str:
    if not isinstance(sec, dict):
        return ""
    for k in ("copy", "text", "body", "content", "html"):
        v = sec.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _verify_ledger_asset(asset: Dict[str, Any], sections: List[Dict[str, Any]],
                         vlabel: str) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    secs = asset.get("sections")
    if not isinstance(secs, list) or not secs:
        return [(AF_SECTION_MISSING, f"variant {vlabel}: no sections declared")]

    canon_ids = [s["id"] for s in sections]
    word_min_by_id = {s["id"]: s.get("word_min") for s in sections}
    resolved: List[str] = []
    for s in secs:
        name = s.get("name") if isinstance(s, dict) else s
        cid = _match_section(name, sections)
        if cid is None:
            fails.append((AF_UNKNOWN, f"variant {vlabel}: section {name!r} matches no canonical "
                                      f"checkout section"))
            continue
        resolved.append(cid)
        floor = word_min_by_id.get(cid)
        if isinstance(floor, int) and floor > 0:
            wc = _stripped_words(_section_copy(s))
            if wc < floor:
                fails.append((AF_BAND, f"variant {vlabel}: section {cid!r} has {wc} stripped "
                                       f"words, under the {floor}-word floor"))

    if len(secs) != len(canon_ids):
        fails.append((AF_COUNT, f"variant {vlabel}: {len(secs)} sections, expected "
                                f"{len(canon_ids)}"))

    seen = set(resolved)
    for cid in canon_ids:
        if cid not in seen:
            fails.append((AF_SECTION_MISSING, f"variant {vlabel}: canonical section {cid!r} absent"))

    firstseen: List[str] = []
    for cid in resolved:
        if cid not in firstseen:
            firstseen.append(cid)
    if firstseen != [c for c in canon_ids if c in seen]:
        fails.append((AF_ORDER, f"variant {vlabel}: sections not in canonical checkout order "
                                f"(got {firstseen})"))
    return fails


def _verify_ledger(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    items = ledger.get("assets")
    if items is None and isinstance(ledger, dict):
        items = ledger.get("pages")
    if not isinstance(items, list):
        return [(AF_EMPTY, "ledger has no assets/pages list (cannot prove; fail-closed)")]
    stage_assets = [a for a in items if isinstance(a, dict) and _norm(a.get("stage")) == "checkout"]
    if not stage_assets:
        return [(AF_EMPTY, "no checkout-stage assets in the ledger (cannot prove; fail-closed)")]

    sections = _sections(_load_canonical())
    required = _load_canonical().get("variants_required", ["a", "b"])
    by_variant: Dict[str, Dict[str, Any]] = {}
    for a in stage_assets:
        by_variant[_norm(a.get("variant"))] = a

    fails: List[Tuple[str, str]] = []
    for v in required:
        if v not in by_variant:
            fails.append((AF_COUNT, f"checkout variant {v!r} missing (both {required} required)"))
            continue
        fails.extend(_verify_ledger_asset(by_variant[v], sections, v))
    return fails


# ---------------------------------------------------------------------------
# Front door.
# ---------------------------------------------------------------------------
def _emit(source: str, failures: List[Tuple[str, str]], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "presentations-checkout-structure", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Presentations :: lean CHECKOUT structure ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — 8 canonical sections in order + offer summary, price, guarantee, "
              "order form (email+name), trust badges, single submit CTA.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


def prove_html(path: str, as_json: bool = False, degraded: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"HTML file not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        html = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _emit(str(p), [("USAGE", f"cannot read HTML: {exc}")], as_json)
        return EXIT_USAGE
    try:
        canon = _load_canonical()
    except (ValueError, OSError) as exc:
        _emit(str(p), [(AF_STRUCTURE, f"cannot load checkout_structure.json: {exc}")], as_json)
        return EXIT_USAGE
    failures = _verify_html(html, canon, degraded=degraded)
    _emit(str(p), failures, as_json)
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove_ledger(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"ledger not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        ledger = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse ledger JSON: {exc}")], as_json)
        return EXIT_USAGE
    try:
        canon = _load_canonical()
    except (ValueError, OSError) as exc:
        _emit(str(p), [(AF_STRUCTURE, f"cannot load checkout_structure.json: {exc}")], as_json)
        return EXIT_USAGE
    failures = _verify_ledger(ledger)
    _emit(str(p), failures, as_json)
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test — must DISCRIMINATE: clean inputs pass, broken inputs fail.
# ---------------------------------------------------------------------------
_VALID_BLOCKS = {
    "header": '<header><nav>Secure Checkout · Trust bar · SSL · Lock icon</nav></header>',
    "offer-summary": ('<section class="offer-summary"><h2>Order Summary</h2>'
                      '<p>What you get: the full presentation, the workbook, and lifetime '
                      'updates. This order summary lists every item in the package so you '
                      'know exactly what you are buying before you complete the '
                      'transaction.</p></section>'),
    "price": ('<section class="price"><h3>Order Total</h3>'
              '<p>One-time price: $97.00. This is the investment for the complete package '
              'and the total you will be charged today.</p></section>'),
    "order-form": ('<section class="order-form"><h2>Billing / Order Form</h2>'
                   '<form id="checkout-form" action="/checkout">'
                   '<label>Email Address <input type="email" name="email" /></label>'
                   '<label>Full Name <input type="text" name="full_name" /></label>'
                   '</form></section>'),
    "payment-fields": ('<section class="payment-fields"><h3>Payment Details</h3>'
                       '<label>Card Number <input type="text" name="card_number" /></label>'
                       '<label>Expiry <input type="text" name="expiry" /></label>'
                       '<label>CVV <input type="text" name="cvv" /></label></section>'),
    "guarantee": ('<section class="guarantee"><h2>Money-Back Guarantee</h2>'
                  '<p>30-day money-back guarantee: if you are not delighted, contact '
                  'support for a full refund. This is the risk-reversal that makes the '
                  'purchase a no-brainer.</p></section>'),
    "trust": ('<section class="trust"><h2>Trust Badges / Secure Checkout</h2>'
              '<p>SSL encrypted checkout. 256-bit encryption. Privacy policy link.</p></section>'),
    "submit-cta": ('<section class="submit-cta"><button type="submit" '
                   'class="checkout-button">Complete Order</button></section>'),
    "footer": '<footer>Privacy · Terms · Copyright</footer>',
}

_CANON_ORDER = ["header", "offer-summary", "price", "order-form", "payment-fields",
                "guarantee", "trust", "submit-cta"]


def _valid_checkout_html() -> str:
    return "<!doctype html><html><head><title>Secure Checkout</title></head><body>" + \
        "".join(_VALID_BLOCKS[k] for k in _CANON_ORDER + ["footer"]) + "</body></html>"


def _valid_degraded_checkout_html() -> str:
    """F6 lead-capture mode: email+name order form, payment-fields SECTION present, but no
    card inputs; carries an honest 'not_configured' receipt marker."""
    html = _valid_checkout_html()
    html = html.replace(_VALID_BLOCKS["payment-fields"],
                        ('<section class="payment-fields"><h3>Payment Details</h3>'
                         '<p>stripe: not_configured — this checkout collects the order; '
                         'live payments will be wired once Stripe is connected.</p></section>'))
    html = html.replace('<label>Card Number <input type="text" name="card_number" /></label>'
                        '<label>Expiry <input type="text" name="expiry" /></label>'
                        '<label>CVV <input type="text" name="cvv" /></label>', "")
    return html


def _html_without(blocks_to_remove: List[str]) -> str:
    html = _valid_checkout_html()
    for k in blocks_to_remove:
        html = html.replace(_VALID_BLOCKS[k], "")
    return html


def _html_reordered() -> str:
    """Move price AFTER the order form: header, offer-summary, order-form, payment-fields,
    price, guarantee, trust, submit-cta."""
    order = ["header", "offer-summary", "order-form", "payment-fields", "price",
             "guarantee", "trust", "submit-cta"]
    return "<!doctype html><html><head><title>Secure Checkout</title></head><body>" + \
        "".join(_VALID_BLOCKS[k] for k in order + ["footer"]) + "</body></html>"


def self_test() -> int:
    ok = True

    def check_pass(name: str, fails: List[Tuple[str, str]]) -> None:
        nonlocal ok
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:20s} -> exit "
              f"{EXIT_PASS if good else EXIT_AUTOFAIL}" + ("" if good else f" ({fails})"))

    def check_fail(name: str, fails: List[Tuple[str, str]], expect: str) -> None:
        nonlocal ok
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} "
              f"(want {expect})")

    canon = _load_canonical()
    sections = _sections(canon)

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("html-complete", _verify_html(_valid_checkout_html(), canon))
    check_pass("html-degraded-f6", _verify_html(_valid_degraded_checkout_html(), canon,
                                                degraded=True))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    check_fail("missing-summary",
               _verify_html(_html_without(["offer-summary"]), canon), AF_SUMMARY)
    check_fail("missing-price", _verify_html(_html_without(["price"]), canon), AF_PRICE)
    check_fail("missing-guarantee",
               _verify_html(_html_without(["guarantee"]), canon), AF_GUARANTEE)
    check_fail("missing-email",
               _verify_html(_html_without(["order-form"]), canon), AF_FIELDS)
    check_fail("missing-name",
               _verify_html(_html_without(["order-form"]), canon), AF_FIELDS)
    # Live checkout stripped of card fields (no degraded marker) -> AF_PAYMENT.
    no_pay = _valid_checkout_html().replace(_VALID_BLOCKS["payment-fields"],
                                            '<section class="payment-fields"></section>')
    check_fail("missing-payment-live", _verify_html(no_pay, canon), AF_PAYMENT)
    # Trust section stripped AND header/footer trust tokens removed.
    low_trust = _html_without(["trust"])
    low_trust = low_trust.replace("Secure Checkout · Trust bar · SSL · Lock icon", "Nav bar")
    low_trust = low_trust.replace("Privacy · Terms · Copyright", "Copyright")
    check_fail("missing-trust", _verify_html(low_trust, canon), AF_TRUST)
    check_fail("missing-cta", _verify_html(_html_without(["submit-cta"]), canon), AF_CTA)
    check_fail("order-swapped", _verify_html(_html_reordered(), canon), AF_ORDER)

    # --- ledger-mode fixtures (Skill 56 copy-ledger shape) ---
    _COPY = ("This is the order summary section copy and it is long enough to clear every "
             "sacred word band without any artificial padding to satisfy the measured floor "
             "so that the prover sees real substance here.")

    def ledger_asset(variant: str, names: Optional[List[str]] = None) -> Dict[str, Any]:
        nm = names if names is not None else [s["id"] for s in sections]
        return {"stage": "checkout", "variant": variant, "type": "page",
                "asset_key": f"jane-doe__glow-method__checkout__page__v01{variant}",
                "sections": [{"order": i + 1, "name": n, "copy": _COPY}
                             for i, n in enumerate(nm)]}

    check_pass("ledger-both-variants", _verify_ledger({"assets": [ledger_asset("a"),
                                                                  ledger_asset("b")]}))
    check_fail("ledger-missing-b", _verify_ledger({"assets": [ledger_asset("a")]}), AF_COUNT)
    seven = [s["id"] for s in sections][:7]
    check_fail("ledger-seven-sections",
               _verify_ledger({"assets": [ledger_asset("a", seven)]}), AF_COUNT)
    swapped = [s["id"] for s in sections]
    swapped[3], swapped[4] = swapped[4], swapped[3]  # order-form <-> payment-fields
    check_fail("ledger-swapped",
               _verify_ledger({"assets": [ledger_asset("a", swapped)]}), AF_ORDER)
    check_fail("ledger-empty", _verify_ledger({"assets": []}), AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the lean CHECKOUT structure.")
    ap.add_argument("--html", help="path to a checkout page HTML fragment")
    ap.add_argument("--ledger", help="path to a copy_ledger.json (Skill 56 pattern)")
    ap.add_argument("--degraded", action="store_true",
                    help="checkout is in F6 degraded lead-capture mode (no live card fields)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.html and args.ledger:
        print("USAGE ERROR: pass --html OR --ledger, not both.")
        return EXIT_USAGE
    if args.html:
        return prove_html(args.html, as_json=args.json, degraded=args.degraded)
    if args.ledger:
        return prove_ledger(args.ledger, as_json=args.json)
    print("USAGE ERROR: pass --html <file> | --ledger <file> (or --self-test).")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
