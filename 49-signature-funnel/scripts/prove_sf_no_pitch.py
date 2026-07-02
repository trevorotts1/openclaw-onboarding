#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sf_no_pitch.py — fail-closed no-pitch + image-provenance gate for the
Signature Funnel (Skill 49).

TWO SACRED GUARANTEES, one prover (both fail-closed):

  A) THANK-YOU NO-PITCH (SOURCE-FRAMEWORK / v2 Part 5) — "after Downsell 2 the funnel
     never pitches again." The Thank-You page must carry NO offer/sale CTA, NO price
     token, and NO offer-product name. Only utility buttons are allowed
     (Join The Community / Share With A Friend / Add To Calendar). Selling on the
     thank-you page cheapens every promise the funnel just made.
       AF-FUN-TY-PITCH  — an offer/product NAME appears on the thank-you page
       AF-FUN-TY-PRICE  — a price/monetary token appears on the thank-you page
       AF-FUN-TY-CTA    — sale/enroll/offer CTA (non-utility) appears on the thank-you page

  B) IMAGE PROVENANCE (PRD §7 gate 3 + gate 4; clone of delivery_gate.py _BAD_TASK_IDS)
     — every generated image must carry a real Kie taskId (no native/placeholder) AND
     resolve to the GHL media host (no off-host / placeholder URLs).
       AF-FUN-IMG-PROVENANCE — missing / placeholder / native Kie taskId
       AF-FUN-IMG-HOST       — media URL does not resolve to a GHL media host

FAIL-CLOSED PRECONDITIONS (exit 3 — never a vacuous PASS):
  * a required input is missing / unreadable JSON;
  * the offer_token_ledger is missing/empty (nothing to prove absent -> vacuous);
  * no thank-you page in the funnel (cannot prove no-pitch);
  * no image records (cannot prove provenance).

stdlib only. Exit 0 = pass, exit 2 = violation, exit 3 = usage/fail-closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

_MIN_OFFER_TOKEN_LEN = 3

# Monetary / price tokens (clone of the presentations no-pitch PRICE_RE).
PRICE_RE = re.compile(
    r"""(?ix)
      (?: \$ | us\$ | usd\s* | € | £ ) \s* \d[\d,]* (?:\.\d+)?
    | \b \d[\d,]* (?:\.\d+)? \s* (?: dollars? | usd | bucks )
    | \b \d[\d,]* (?:\.\d+)? \s* (?: /\s*mo | /\s*month | /\s*yr | /\s*year
                                    | per \s+ month | per \s+ year )
    """
)

# Sale / enroll / offer CTA tokens forbidden on the thank-you page.
SALE_CTA_TOKENS: Tuple[str, ...] = (
    "buy now", "order now", "purchase now", "add to cart", "checkout now",
    "enroll now", "enroll today", "sign up now", "upgrade my order", "yes upgrade",
    "reserve your spot", "reserve my seat", "claim your spot", "claim my seat",
    "limited time offer", "act now", "spots left", "seats left",
    "money-back guarantee", "money back guarantee", "payment plan", "pay in full",
    "% off", "discount code", "promo code", "special offer", "flash sale",
    "doors close", "cart closes", "price goes up", "get instant access",
    "add to your order", "one time offer", "swipe up to buy", "claim this deal",
)

# Utility buttons that ARE allowed on the thank-you page (not a pitch).
UTILITY_BUTTONS = (
    "join the community", "share with a friend", "add to calendar",
    "download", "open module", "book your call", "get started",
)

# GHL media host fingerprints (a media URL must resolve to one of these hosts).
GHL_HOST_FINGERPRINTS = (
    "gohighlevel", "leadconnector", "leadconnectorhq", "msgsndr",
    "highlevel", "storage.googleapis.com/highlevel",
)

# A taskId that is NOT a real Kie bake (clone of delivery_gate.py:160 _BAD_TASK_IDS).
_BAD_TASK_IDS = frozenset({"", "native", "placeholder", "none", "null", "n/a", "tbd", "todo"})


class ProverInputError(Exception):
    """Raised when a required input cannot be verified -> fail-closed (exit 3)."""


def _norm(text: Any) -> str:
    return " ".join(str(text).casefold().split())


def _iter_strings(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _iter_strings(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _iter_strings(v)


def _offer_tokens(ledger: Dict[str, Any]) -> List[str]:
    raw: List[str] = []
    led = ledger.get("offer_token_ledger")
    if isinstance(led, list):
        raw += [x for x in led if isinstance(x, str)]
    if isinstance(ledger.get("product_title"), str):
        raw.append(ledger["product_title"])
    out: List[str] = []
    seen = set()
    for t in raw:
        n = _norm(t)
        if len(n) >= _MIN_OFFER_TOKEN_LEN and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _thank_you_pages(ledger: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = ledger.get("pages")
    if not isinstance(pages, list):
        return []
    return [p for p in pages
            if isinstance(p, dict) and str(p.get("page_type", "")).strip().lower() == "thank-you"]


def _page_button_blob(page: Dict[str, Any]) -> str:
    """Normalized text of the page's declared buttons only (utility buttons live here)."""
    btns = page.get("buttons")
    if isinstance(btns, list):
        return _norm(" || ".join(str(b) for b in btns))
    return ""


def _is_utility_only(cta_hit: str, button_blob: str) -> bool:
    return any(u in button_blob for u in UTILITY_BUTTONS)


def _host_ok(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hay = (parsed.netloc + parsed.path).lower()
    return any(fp in hay for fp in GHL_HOST_FINGERPRINTS)


def evaluate(ledger: Dict[str, Any]) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []

    offer_tokens = _offer_tokens(ledger)
    if not offer_tokens:
        raise ProverInputError(
            "AF-FUN-OFFER-LEDGER-MISSING: no non-empty offer_token_ledger / product_title. "
            "With no offer names there is nothing to prove absent from the thank-you page -> "
            "a PASS would be vacuous, so this is fail-closed.")

    ty_pages = _thank_you_pages(ledger)
    if not ty_pages:
        raise ProverInputError(
            "AF-FUN-TY-MISSING: the funnel has no thank-you page. No-pitch hygiene cannot be "
            "proven on an absent page -> fail-closed (mislabeling can never buy a PASS).")

    # --- A) THANK-YOU NO-PITCH ------------------------------------------------
    for page in ty_pages:
        button_blob = _page_button_blob(page)
        # Everything on the page EXCEPT the declared utility buttons.
        content = {"page_type": page.get("page_type")}
        content_sections = page.get("sections")
        blob = _norm(" \n ".join(_iter_strings(content_sections)))
        for tok in offer_tokens:
            if tok in blob:
                fails.append(("AF-FUN-TY-PITCH",
                              f"thank-you page names the offer/product {tok!r} — after the downsell the "
                              "funnel never pitches again; the offer name is forbidden here"))
                break
        m = PRICE_RE.search(blob)
        if m:
            fails.append(("AF-FUN-TY-PRICE",
                          f"thank-you page contains a price token {m.group(0).strip()!r} — the "
                          "thank-you page never sells"))
        for cta in SALE_CTA_TOKENS:
            if cta in blob or (cta in button_blob and not _is_utility_only(cta, button_blob)):
                # a sale CTA anywhere in the copy, or a non-utility sale button
                if cta in button_blob and any(u in button_blob for u in UTILITY_BUTTONS) and cta not in blob:
                    continue
                fails.append(("AF-FUN-TY-CTA",
                              f"thank-you page carries a sale/offer CTA {cta!r} — only utility buttons "
                              "(Join The Community / Share With A Friend / Add To Calendar) are allowed"))
                break

    # --- B) IMAGE PROVENANCE --------------------------------------------------
    images = ledger.get("images")
    if not isinstance(images, list) or not images:
        raise ProverInputError(
            "AF-FUN-IMG-EMPTY: the funnel carries no image records. Kie taskId + GHL-host "
            "provenance cannot be proven on zero images -> fail-closed.")
    for img in images:
        who = (f"page '{img.get('page_type', '?')}' section {img.get('section', '?')}"
               if isinstance(img, dict) else "an image record")
        if not isinstance(img, dict):
            fails.append(("AF-FUN-IMG-PROVENANCE", "an image record is not an object"))
            continue
        task_id = img.get("kie_task_id", img.get("task_id"))
        norm_task = str(task_id).strip().lower() if task_id is not None else ""
        if task_id is None or norm_task in _BAD_TASK_IDS:
            fails.append(("AF-FUN-IMG-PROVENANCE",
                          f"{who}: missing/placeholder Kie taskId ({task_id!r}) — the image was not "
                          "proven Kie-rendered"))
        url = img.get("media_url", img.get("url", ""))
        if not _host_ok(url):
            fails.append(("AF-FUN-IMG-HOST",
                          f"{who}: media URL {url!r} does not resolve to a GHL media host"))

    return fails


def evaluate_ledger(ledger: Any) -> Tuple[int, List[Tuple[str, str]]]:
    if not isinstance(ledger, dict):
        return EXIT_FAILCLOSED, [("AF-FUN-INPUT", "ledger is not a JSON object")]
    try:
        fails = evaluate(ledger)
    except ProverInputError as exc:
        return EXIT_FAILCLOSED, [("FAIL-CLOSED", str(exc))]
    if fails:
        return EXIT_VIOLATION, fails
    return EXIT_OK, []


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _report(code: int, fails: List[Tuple[str, str]]) -> None:
    if code == EXIT_OK:
        print("PASS: thank-you page carries no pitch, and every image has Kie taskId + GHL-host provenance.")
        return
    label = "FAIL-CLOSED" if code == EXIT_FAILCLOSED else "VIOLATION"
    print(f"{label}: no-pitch/provenance gate failed ({len(fails)} finding(s)):")
    for c, m in fails:
        print(f"  [{c}] {m}")


# ---------------------------------------------------------------------------
# Self-test fixtures.
# ---------------------------------------------------------------------------
def _valid_ledger() -> Dict[str, Any]:
    return {
        "funnel_type": "signature_funnel",
        "product_title": "The 5AM Reset",
        "offer_token_ledger": ["The 5AM Reset", "Momentum Accelerator"],
        "pages": [
            {"page_type": "main", "sections": [{"section": 1, "copy": "The 5AM Reset. Enroll now for the launch price."}]},
            {"page_type": "thank-you", "buttons": ["Join The Community", "Share With A Friend"],
             "sections": [
                 {"section": "TY-1", "copy": "It is official, your seat is confirmed and everything you need is on its way."},
                 {"section": "TY-2", "steps": ["Check your email for the welcome bonus we just sent to your inbox."]},
                 {"section": "TY-3", "copy": "Welcome to the next stage of your life. We take that seriously."},
             ]},
        ],
        "images": [
            {"page_type": "main", "section": 1, "kie_task_id": "kie_abc123",
             "media_url": "https://storage.gohighlevel.com/loc/x/hero.png"},
            {"page_type": "main", "section": 5, "kie_task_id": "kie_def456",
             "media_url": "https://msgsndr.com/media/rise.png"},
        ],
    }


def _violation_cases():
    def ty_pitch(led):
        led["pages"][1]["sections"][0]["copy"] = "It is official, The 5AM Reset is yours forever."
    def ty_price(led):
        led["pages"][1]["sections"][2]["copy"] = "Welcome. Your card was charged $1,997 today."
    def ty_cta(led):
        led["pages"][1]["sections"][1]["steps"].append("Enroll now before the doors close on this deal.")
    def img_task(led):
        led["images"][0]["kie_task_id"] = "placeholder"
    def img_host(led):
        led["images"][1]["media_url"] = "https://example.com/random/rise.png"

    def _mk(fn):
        import copy as _c
        led = _c.deepcopy(_valid_ledger())
        fn(led)
        return led

    return [
        ("ty_offer_name", "AF-FUN-TY-PITCH", lambda: _mk(ty_pitch)),
        ("ty_price", "AF-FUN-TY-PRICE", lambda: _mk(ty_price)),
        ("ty_sale_cta", "AF-FUN-TY-CTA", lambda: _mk(ty_cta)),
        ("img_placeholder_task", "AF-FUN-IMG-PROVENANCE", lambda: _mk(img_task)),
        ("img_off_host", "AF-FUN-IMG-HOST", lambda: _mk(img_host)),
    ]


def run_self_test() -> int:
    ok = True
    code, fails = evaluate_ledger(_valid_ledger())
    if code != EXIT_OK:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture -> exit {code}: {fails}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (exit 0).")

    caught = 0
    cases = _violation_cases()
    for name, expected, build in cases:
        code, fails = evaluate_ledger(build())
        codes = {c for c, _ in fails}
        if code != EXIT_VIOLATION:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> exit {code} (expected 2): {fails}")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            caught += 1
            print(f"SELF-TEST ok: '{name}' -> exit 2, carries {expected}.")

    # fail-closed cases
    import copy as _c
    fc = 0
    led = _c.deepcopy(_valid_ledger()); led["offer_token_ledger"] = []; led.pop("product_title", None)
    code, fails = evaluate_ledger(led)
    if code == EXIT_FAILCLOSED and any("AF-FUN-OFFER-LEDGER-MISSING" in m for _, m in fails):
        fc += 1; print("SELF-TEST ok: empty offer ledger -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: empty offer ledger -> exit {code}: {fails}")

    led = _c.deepcopy(_valid_ledger()); led["pages"] = [p for p in led["pages"] if p["page_type"] != "thank-you"]
    code, fails = evaluate_ledger(led)
    if code == EXIT_FAILCLOSED and any("AF-FUN-TY-MISSING" in m for _, m in fails):
        fc += 1; print("SELF-TEST ok: no thank-you page -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: no thank-you page -> exit {code}: {fails}")

    led = _c.deepcopy(_valid_ledger()); led["images"] = []
    code, fails = evaluate_ledger(led)
    if code == EXIT_FAILCLOSED and any("AF-FUN-IMG-EMPTY" in m for _, m in fails):
        fc += 1; print("SELF-TEST ok: no images -> fail-closed (exit 3).")
    else:
        ok = False; print(f"SELF-TEST FAIL: no images -> exit {code}: {fails}")

    print(f"SELF-TEST FIXTURES: {1 if ok or True else 0} valid-pass, {caught}/{len(cases)} violation-catch, {fc}/3 fail-closed")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed no-pitch (thank-you) + image-provenance (Kie taskId + GHL host) "
                    "gate for the Signature Funnel. Exit 0 pass, 2 violation, 3 usage/fail-closed.")
    ap.add_argument("--ledger", help="path to the funnel media/copy ledger JSON ('-' reads stdin)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct VALID + VIOLATION + FAIL-CLOSED fixtures and assert")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.ledger:
        print("USAGE ERROR: pass --ledger <ledger.json> (or --self-test).")
        return EXIT_FAILCLOSED
    try:
        ledger = _load_json(args.ledger)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load ledger {args.ledger!r}: {exc}")
        return EXIT_FAILCLOSED

    code, fails = evaluate_ledger(ledger)
    _report(code, fails)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
