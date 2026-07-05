#!/usr/bin/env python3
"""prove_web_pages.py — website-craft page-floor prover (stdlib-only, model-free).

The funnel-craft cluster proves the SACRED funnel bands with
`49-signature-funnel/scripts/prove_sf_copy.py`; multi-page websites had NO copy
contract at all. This is the website-craft equivalent: a deterministic,
provider-neutral floor gate that MEASURES stripped text on a website copy ledger
and fails CLOSED with named `AF-WEB-*` codes. It never calls a model and never
trusts a self-reported count (mirrors the funnel prover's "measure, don't trust"
rule).

Contract (the ledger the Conversion Copywriter produces, per SOP-WEB-02):

    {
      "brand": "<brand>",
      "brand_voice_source": "brand-voice-lock.md"                 # or a provisional
                            | "provisional:skill-55-product-bio"  # lock derived from
                            | "provisional:skill-52-brand-intel",  # 55/52 (SOP-WEB-02 §1b)
      "persona_selection_log": "persona-selection-log.md",
      "pages": [
        {"page_type": "home",     "name": "Home",     "sections": [{"role": "character", "text": "..."}, ...]},
        {"page_type": "services", "name": "Services", "services": [{"name": "...", "text": "..."}, ...]},
        {"page_type": "about",    "name": "About",    "text": "..."},
        {"page_type": "faq",      "name": "FAQ",      "faqs": [{"q": "...", "a": "..."}, ...]}
      ]
    }

Floors (SOP-WEB-02 — the machine bar):
  * home     — StoryBrand SB7 wireframe: all 7 roles present (character, problem,
               guide, plan, call_to_action, success, stakes); page >= 250 words.
  * services — each service block >= 400 stripped words.
  * about    — >= 500 stripped words.
  * faq      — >= 8 Q&A pairs, each question AND answer non-empty.

A missing brand-voice anchor (neither a lock nor a provisional lock) is
AF-WEB-VOICE-UNANCHORED — never author voice-unanchored copy (SOP-WEB-02 §1b).
A missing persona-selection log is AF-WEB-PERSONA-LOG (persona Step 0).

Exit 0 = every present page cleared its floor. Any AF-WEB-* = fix + re-run.

Usage:
  python3 prove_web_pages.py <website_copy_ledger.json>
  python3 prove_web_pages.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any


# ── Floors (adjustable constants table; SOP-WEB-02 is the source of truth) ─────
HOME_MIN_WORDS = 250
SERVICE_MIN_WORDS = 400
ABOUT_MIN_WORDS = 500
FAQ_MIN_PAIRS = 8

# The StoryBrand SB7 role set the Home page must cover (aliases accepted).
SB7_ROLES = {
    "character": ("character", "hero", "customer"),
    "problem": ("problem", "villain", "pain"),
    "guide": ("guide", "authority", "empathy"),
    "plan": ("plan", "steps", "process"),
    "call_to_action": ("call_to_action", "cta", "action"),
    "success": ("success", "transformation", "outcome"),
    "stakes": ("stakes", "failure", "what_s_at_stake", "whats_at_stake"),
}


def _strip_words(text: str) -> int:
    """Count words in STRIPPED text (markdown/punctuation-insensitive, whitespace
    never satisfies a floor)."""
    if not isinstance(text, str):
        return 0
    cleaned = re.sub(r"[#>*_`~\-\|\[\]\(\)]", " ", text)
    return len([w for w in re.split(r"\s+", cleaned.strip()) if w])


def _canonical_role(raw: str) -> str | None:
    r = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    for canon, aliases in SB7_ROLES.items():
        if r == canon or r in aliases:
            return canon
    return None


def _check_home(page: dict, defects: list) -> None:
    name = page.get("name", "Home")
    sections = page.get("sections") or []
    present = set()
    total_words = 0
    for sec in sections:
        role = _canonical_role(sec.get("role", ""))
        if role:
            present.add(role)
        total_words += _strip_words(sec.get("text", ""))
    missing = [r for r in SB7_ROLES if r not in present]
    if missing:
        defects.append(f"AF-WEB-HOME-SB7: '{name}' missing StoryBrand roles: {', '.join(missing)}")
    if total_words < HOME_MIN_WORDS:
        defects.append(f"AF-WEB-HOME-THIN: '{name}' has {total_words} words (< {HOME_MIN_WORDS})")


def _check_services(page: dict, defects: list) -> None:
    name = page.get("name", "Services")
    services = page.get("services") or []
    if not services:
        defects.append(f"AF-WEB-SERVICES-EMPTY: '{name}' declares no service blocks")
        return
    for svc in services:
        sname = svc.get("name", "<unnamed service>")
        wc = _strip_words(svc.get("text", ""))
        if wc < SERVICE_MIN_WORDS:
            defects.append(
                f"AF-WEB-SERVICE-THIN: service '{sname}' has {wc} words (< {SERVICE_MIN_WORDS})"
            )


def _check_about(page: dict, defects: list) -> None:
    name = page.get("name", "About")
    wc = _strip_words(page.get("text", ""))
    if wc < ABOUT_MIN_WORDS:
        defects.append(f"AF-WEB-ABOUT-THIN: '{name}' has {wc} words (< {ABOUT_MIN_WORDS})")


def _check_faq(page: dict, defects: list) -> None:
    name = page.get("name", "FAQ")
    faqs = page.get("faqs") or []
    valid = [qa for qa in faqs
             if str(qa.get("q", "")).strip() and str(qa.get("a", "")).strip()]
    if len(valid) < FAQ_MIN_PAIRS:
        defects.append(
            f"AF-WEB-FAQ-COUNT: '{name}' has {len(valid)} complete Q&A pairs (< {FAQ_MIN_PAIRS})"
        )


_CHECKERS = {
    "home": _check_home,
    "services": _check_services,
    "about": _check_about,
    "faq": _check_faq,
}


def evaluate(ledger: dict) -> list:
    """Return the list of AF-WEB-* defect strings (empty == pass)."""
    defects: list = []

    # Brand-voice anchor (SOP-WEB-02 §1b): a real lock OR a provisional lock.
    voice = str(ledger.get("brand_voice_source", "")).strip().lower()
    if not (voice.endswith("brand-voice-lock.md")
            or "brand-voice-lock" in voice
            or voice.startswith("provisional:")):
        defects.append("AF-WEB-VOICE-UNANCHORED: no brand-voice-lock.md and no provisional lock "
                       "derived from Skill 55 Product Bio / Skill 52 brand intelligence")

    # Persona Step 0 (shared with funnel-craft): a persona-selection log must be named.
    if not str(ledger.get("persona_selection_log", "")).strip():
        defects.append("AF-WEB-PERSONA-LOG: persona-selection-log.md not referenced "
                       "(the Conversion Copywriter persona Step 0 did not run)")

    pages = ledger.get("pages")
    if not isinstance(pages, list) or not pages:
        defects.append("AF-WEB-NO-PAGES: ledger has no pages array")
        return defects

    for page in pages:
        pt = str(page.get("page_type", "")).strip().lower()
        checker = _CHECKERS.get(pt)
        if checker is None:
            # Unknown page types are not floored here, but must not be silently lost.
            defects.append(f"AF-WEB-UNKNOWN-PAGETYPE: '{page.get('name', pt or '?')}' "
                           f"has unrecognized page_type {pt!r}")
            continue
        checker(page, defects)

    return defects


def prove(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"AF-WEB-LEDGER-UNREADABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    defects = evaluate(ledger)
    if defects:
        print(f"FAIL — {len(defects)} website copy floor violation(s):", file=sys.stderr)
        for d in defects:
            print(f"  x {d}", file=sys.stderr)
        return 1
    print("PASS — every present website page cleared its SOP-WEB-02 floor.")
    return 0


# ── Embedded self-test (a passing + a failing fixture) ─────────────────────────
def _selftest() -> int:
    failures: list = []

    def _home(sections):
        return {"page_type": "home", "name": "Home", "sections": sections}

    sb7_full = [
        {"role": "character", "text": " ".join(["word"] * 40)},
        {"role": "problem", "text": " ".join(["word"] * 40)},
        {"role": "guide", "text": " ".join(["word"] * 40)},
        {"role": "plan", "text": " ".join(["word"] * 40)},
        {"role": "cta", "text": " ".join(["word"] * 40)},
        {"role": "success", "text": " ".join(["word"] * 40)},
        {"role": "stakes", "text": " ".join(["word"] * 40)},
    ]
    good = {
        "brand": "Fictional Soap Co",
        "brand_voice_source": "provisional:skill-55-product-bio",
        "persona_selection_log": "persona-selection-log.md",
        "pages": [
            _home(sb7_full),
            {"page_type": "services", "name": "Services",
             "services": [{"name": "Deep Clean", "text": " ".join(["word"] * 400)}]},
            {"page_type": "about", "name": "About", "text": " ".join(["word"] * 500)},
            {"page_type": "faq", "name": "FAQ",
             "faqs": [{"q": f"Q{i}", "a": f"A{i}"} for i in range(8)]},
        ],
    }
    if evaluate(good):
        failures.append(f"good fixture should PASS, got: {evaluate(good)}")

    # Bad: missing SB7 role, thin service, short about, only 3 FAQs, no voice/persona.
    bad = {
        "pages": [
            _home(sb7_full[:-2]),  # drop success + stakes
            {"page_type": "services", "name": "Services",
             "services": [{"name": "Thin", "text": " ".join(["word"] * 50)}]},
            {"page_type": "about", "name": "About", "text": " ".join(["word"] * 100)},
            {"page_type": "faq", "name": "FAQ",
             "faqs": [{"q": "Q", "a": "A"}, {"q": "Q", "a": "A"}, {"q": "Q", "a": "A"}]},
        ],
    }
    bad_defects = evaluate(bad)
    for needed in ("AF-WEB-HOME-SB7", "AF-WEB-SERVICE-THIN", "AF-WEB-ABOUT-THIN",
                   "AF-WEB-FAQ-COUNT", "AF-WEB-VOICE-UNANCHORED", "AF-WEB-PERSONA-LOG"):
        if not any(d.startswith(needed) for d in bad_defects):
            failures.append(f"bad fixture should raise {needed}; got {bad_defects}")

    if failures:
        print("SELF-TEST FAIL", file=sys.stderr)
        for f in failures:
            print(f"  x {f}", file=sys.stderr)
        return 1
    print("SELF-TEST PASS — prove_web_pages floors enforced (pass + fail fixtures).")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    sys.exit(prove(sys.argv[1]))
