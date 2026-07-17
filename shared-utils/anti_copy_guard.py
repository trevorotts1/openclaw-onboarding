#!/usr/bin/env python3
"""anti_copy_guard.py — A-U10 (master unit U10): anti-copy guard, the
deterministic twin of A-U9's exemplar injection.

WHY THIS EXISTS
----------------
A-U9 (``exemplar_injection.py``) puts a gold-standard sample in front of the
writer at write time, wrapped in a CALIBRATION-ONLY clause: "never copy their
wording, their topic, or their phrasing." A clause is not an enforcement
mechanism. A-U10 is the enforcement mechanism: a deterministic, key-free,
model-free similarity check between the BUILT OUTPUT and every exemplar that
was shown to the writer for that deliverable. Output that similarity-matches
an injected exemplar above a fixed ceiling is a **hard miss** — exactly the
mechanical twin of the persona-impersonation guardrail (a hard, deterministic
floor a weighted score can never average away).

METHOD — character-shingle Jaccard / containment (master spec v2 A.9's own
build text). No model, no key, no network: this runs identically on a bare
checkout with zero dependencies (acceptance (c)). Two metrics are computed
per (output, exemplar) pair and the CEILING check uses the MAX of the two:

  - Jaccard:      |shingles(output) ∩ shingles(exemplar)| / |union|
                  Symmetric near-duplicate measure. Weak whenever one side is
                  much LARGER than the other (a multi-section exemplar file
                  vs. one short built copy slot) — the union is dominated by
                  the larger side and dilutes a genuine match away.
  - Containment:  |shingles(output) ∩ shingles(exemplar)| / |shingles(output)|
                  "How much of the OUTPUT was drawn from the exemplar." This
                  is the forensic direction that matters for copy-through: a
                  short built slot (e.g. just a `hero` field) that is
                  word-for-word one section of a much longer, multi-section
                  exemplar file still scores ~1.0 containment — Jaccard alone
                  would dilute that verbatim lift away against the
                  exemplar's other, untouched sections.

CEILING — SIMILARITY_CEILING = 0.55 (character 5-grams). Calibrated against
the actual shipped A-U9 exemplar (06-ghl-install-pages/exemplars/lead/
clarity-call-optin/gold-output.md, the WHOLE multi-section file, exactly what
a caller reading ``gold_output_path`` gets): a copy-through fixture (one
section of that exemplar — its hero + sub-head — reproduced with cosmetic
word-level edits: swapped nouns, a reordered clause, synonym swaps) scores
0.873 max-similarity; a genuinely fresh fixture on the identical topic (a
different lead-magnet optin, same length class, zero shared phrasing) scores
0.289. 0.55 sits with real margin on both sides of that gap (0.32 above,
0.26 below). The value is asserted by ``tests/unit/u10-anti-copy-guard.test.py``
(acceptance (d) — a PR that silently drifts the ceiling fails that CI guard,
re-derived against the live on-disk exemplar, not a hand-copied snippet) and
mirrored in ``scripts/guard-fab-qc-gate.sh``.

REVERT — one flag. ``ANTI_COPY_GUARD_ENABLED=0`` makes ``guard_enabled()``
return False and every entry point below becomes an inert no-op (``hard_miss``
always False) — no code revert required, matching Page-QC v2's own
flag-gated revert posture (``PAGE_QC_ENABLED``).

DEGRADE POSTURE (mirrors A-U9's own contract): no exemplar packs supplied,
or no output text supplied, or the flag is off → the guard is a clean no-op,
never a fabricated pass/fail. There is no such thing as a hard miss with
nothing to compare against.

stdlib-only, deterministic, no network, no key — runs identically on every
box (mirrors ``exemplar_injection.py`` / ``fab_qc.py``'s posture).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))

# Character-shingle size (5-grams) — small enough to catch cosmetic-edit
# copy-through, large enough that unrelated prose on the same general topic
# does not collide by chance (calibrated in the module docstring above).
CHAR_SHINGLE_K = 5

# The similarity ceiling (max of Jaccard / containment). Above this vs ANY
# injected exemplar = hard miss. See module docstring for the calibration
# proof. Locked by tests/unit/u10-anti-copy-guard.test.py — changing this
# value without updating that test's asserted constant fails CI.
SIMILARITY_CEILING = 0.55

# REVERT lever (background A.9 build text: "the check is one guarded
# function in the Quality-Control path behind a flag -> flip off, revert").
ENV_FLAG = "ANTI_COPY_GUARD_ENABLED"


def guard_enabled() -> bool:
    """True unless the operator has explicitly set ANTI_COPY_GUARD_ENABLED=0.
    Default ON — this is a standing guard, not an opt-in probe (mirrors the
    persona-impersonation guardrail's always-on fail-closed posture)."""
    return os.environ.get(ENV_FLAG, "1").strip() != "0"


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Character-shingle Jaccard / containment — the deterministic core
# --------------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    """Lowercase + collapse all whitespace runs to a single space + strip.
    Deliberately NOT punctuation-stripping: punctuation is part of a writer's
    phrasing fingerprint and helps, not hurts, near-duplicate detection."""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def shingles(text: str, k: int = CHAR_SHINGLE_K) -> set:
    """Character k-gram set of the normalized text. A text shorter than k
    normalizes to a single one-element set (never an empty comparison unit
    for non-empty input) so short slots (a headline, a CTA) still compare
    honestly instead of vanishing from the check."""
    norm = _normalize(text)
    if not norm:
        return set()
    if len(norm) < k:
        return {norm}
    return {norm[i:i + k] for i in range(len(norm) - k + 1)}


def jaccard(a: set, b: set) -> float:
    """Symmetric near-duplicate measure. 0.0 when both sets are empty (no
    signal, never treated as "identical")."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def containment(sub: set, whole: set) -> float:
    """Fraction of `sub`'s shingles that also appear in `whole` — a generic,
    direction-explicit primitive. 0.0 when `sub` is empty. Callers pick the
    direction that answers their actual question; ``similarity()`` below
    uses ``containment(output, exemplar)`` — "how much of the OUTPUT came
    from the exemplar" — the forensic direction for a copy-through check
    (see module docstring)."""
    if not sub:
        return 0.0
    return len(sub & whole) / len(sub)


def similarity(output_text: str, exemplar_text: str, k: int = CHAR_SHINGLE_K) -> dict:
    """Jaccard + containment(output-in-exemplar) for one (output, exemplar)
    pair, plus their max (the value the ceiling check applies to)."""
    out_sh = shingles(output_text, k)
    ex_sh = shingles(exemplar_text, k)
    j = jaccard(out_sh, ex_sh)
    c = containment(out_sh, ex_sh)
    return {"jaccard": round(j, 4), "containment": round(c, 4), "max": round(max(j, c), 4)}


# --------------------------------------------------------------------------- #
# Pack-level check — one output text vs every injected exemplar pack
# --------------------------------------------------------------------------- #
def _exemplar_text(pack: dict) -> Optional[str]:
    """A pack dict may carry the text directly (``text``) or a path to read it
    from (``gold_output_path``, the shape ``exemplar_injection.discover_packs``
    / ``select_exemplars`` already return). Returns None (skip, never raise)
    when neither is present or the file cannot be read."""
    text = pack.get("text")
    if text is not None:
        return str(text)
    path = pack.get("gold_output_path")
    if path and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
    return None


def check_text_against_exemplars(output_text: str, exemplar_packs: list, *,
                                  ceiling: float = SIMILARITY_CEILING,
                                  k: int = CHAR_SHINGLE_K) -> dict:
    """Check ONE output text against every supplied exemplar pack. Returns a
    receipt-shaped dict — deterministically ordered (worst similarity
    first) so the highest-risk match always leads the evidence."""
    results = []
    for pack in exemplar_packs:
        text = _exemplar_text(pack)
        if not text or not text.strip():
            continue
        sim = similarity(output_text, text, k=k)
        results.append({
            "exemplar_id": pack.get("exemplar_id") or pack.get("gold_output_path") or "unknown",
            **sim,
            "breach": sim["max"] > ceiling,
        })
    results.sort(key=lambda r: -r["max"])
    breached = [r["exemplar_id"] for r in results if r["breach"]]
    return {
        "ceiling": ceiling,
        "results": results,
        "hard_miss": bool(breached),
        "breached_exemplars": breached,
    }


# --------------------------------------------------------------------------- #
# Top-level guard — every built text vs every injected exemplar, flag-gated
# --------------------------------------------------------------------------- #
def anti_copy_check(output_texts: list, exemplar_packs: list, *,
                     ceiling: float = SIMILARITY_CEILING,
                     k: int = CHAR_SHINGLE_K) -> dict:
    """The guard's single entry point (fab-QC hard-miss family). Deterministic,
    stdlib-only, no network/key (acceptance (c)) — runs identically on every
    box. Degrades to a clean no-op (never a fabricated verdict) when the flag
    is off, or there is nothing to compare: empty ``output_texts``, empty
    ``exemplar_packs``, or every exemplar pack unreadable."""
    if not guard_enabled():
        return {"enabled": False, "ceiling": ceiling, "hard_miss": False,
                "breached_exemplars": [], "per_text": []}
    per_text = []
    any_breach = False
    all_breached: set = set()
    for i, text in enumerate(output_texts or []):
        if not text or not str(text).strip():
            continue
        res = check_text_against_exemplars(text, exemplar_packs or [], ceiling=ceiling, k=k)
        res["text_index"] = i
        per_text.append(res)
        if res["hard_miss"]:
            any_breach = True
            all_breached.update(res["breached_exemplars"])
    return {"enabled": True, "ceiling": ceiling, "hard_miss": any_breach,
            "breached_exemplars": sorted(all_breached), "per_text": per_text}


# --------------------------------------------------------------------------- #
# Receipt — routing/anti-copy-guard.json (receipts, never claims; also the
# evidence the Section-B semantic judge (Page-QC v2) can read)
# --------------------------------------------------------------------------- #
def write_anti_copy_receipt(evidence_root: str, result: dict) -> dict:
    """Write the guard's verdict to ``routing/anti-copy-guard.json`` — an
    honest receipt is written on EVERY call, including a disabled-flag or
    nothing-to-compare no-op result, so "the guard did not run" is itself
    auditable (mirrors A-U9's own no-match receipt posture)."""
    routing = os.path.join(evidence_root, "routing")
    os.makedirs(routing, exist_ok=True)
    path = os.path.join(routing, "anti-copy-guard.json")
    doc = dict(result)
    doc["generated_at"] = _ts()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return doc


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="A-U10 anti-copy guard — similarity ceiling vs injected exemplars")
    ap.add_argument("--output", help="path to a built output text file")
    ap.add_argument("--exemplar", action="append", default=[],
                     help="path to an exemplar gold-output.md (repeatable)")
    ap.add_argument("--ceiling", type=float, default=SIMILARITY_CEILING)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", action="store_true", help="exit non-zero on a hard miss")
    a = ap.parse_args(argv)

    if not a.output or not a.exemplar:
        ap.error("--output and >=1 --exemplar are required")
        return 2

    with open(a.output, encoding="utf-8") as f:
        output_text = f.read()
    packs = [{"exemplar_id": p, "gold_output_path": p} for p in a.exemplar]
    result = anti_copy_check([output_text], packs, ceiling=a.ceiling)

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"anti-copy-guard: ceiling={result['ceiling']} hard_miss={result['hard_miss']}")
        for pt in result["per_text"]:
            for r in pt["results"]:
                flag = "BREACH" if r["breach"] else "ok"
                print(f"  [{flag}] {r['exemplar_id']}: jaccard={r['jaccard']} "
                      f"containment={r['containment']} max={r['max']}")
    if a.gate and result["hard_miss"]:
        return 1
    return 0


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) > 1:
        raise SystemExit(main(_sys.argv[1:]))

    # Offline self-test — no network, no key. Uses a self-contained fixture
    # that mirrors the shape of a real shipped exemplar (a multi-section
    # gold-output.md) so the containment(output-in-exemplar) direction is
    # exercised the same way it is in production (a short built copy slot
    # checked against a much longer, multi-section exemplar file) — never a
    # network/disk dependency, per acceptance (c).
    ok = True

    def check(label, cond):
        global ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    exemplar_text = (
        "# Exemplar — lead / clarity-call-optin\n\n"
        "## Hero\n\n"
        "Stop Guessing Which Offer To Build Next. A free 20-minute Clarity Call "
        "where we map the one offer your existing audience is already asking "
        "you for, so you stop building things nobody asked for and start "
        "building the thing they'll actually pay for.\n\n"
        "## Sub-head\n\n"
        "You already have the raw material: the DMs, the comments, the "
        "questions piling up in your inbox. Most coaches never go back and "
        "read them as a pattern. We do.\n\n"
        "## What you walk away with\n\n"
        "- The single most-requested outcome hiding in your last 90 days.\n"
        "- A one-sentence offer draft you can post today.\n"
        "- The one thing quietly talking your best-fit buyer out of booking.\n\n"
        "## CTA\n\n"
        "Grab one of this week's Clarity Call slots — no pitch, no deck, "
        "just the pattern in your own messages, named out loud."
    )
    # Copy-through: ONE section (the hero) reproduced with cosmetic edits —
    # exactly what a single built copy slot looks like when lifted from a
    # much longer multi-section exemplar.
    copy_through = (
        "Stop Guessing Which Offer To Build Next Right Now. A free 20-minute "
        "Discovery Call where we map the one offer your current audience is "
        "already asking you for, so you stop building stuff nobody asked for "
        "and start building the thing they will actually pay for."
    )
    fresh = (
        "Your Best Clients Already Told You What To Sell. Book a complimentary "
        "fifteen-minute Momentum Session and we'll dig through the questions "
        "your community keeps sending you, then hand back the exact program "
        "idea hiding inside them, so your next launch is built on proof."
    )

    check("ceiling separates copy-through from fresh with real margin",
          similarity(copy_through, exemplar_text)["max"] > SIMILARITY_CEILING
          and similarity(fresh, exemplar_text)["max"] < SIMILARITY_CEILING)

    pack = {"exemplar_id": "fixture/self-test", "text": exemplar_text}
    r_copy = anti_copy_check([copy_through], [pack])
    check("(a) copy-through fixture is hard-failed", r_copy["hard_miss"] is True)
    check("(a) breach names the right exemplar id",
          r_copy["breached_exemplars"] == ["fixture/self-test"])

    r_fresh = anti_copy_check([fresh], [pack])
    check("(b) genuinely fresh fixture passes", r_fresh["hard_miss"] is False)

    r_empty_packs = anti_copy_check([copy_through], [])
    check("no exemplar packs -> clean no-op, never a fabricated hard miss",
          r_empty_packs["hard_miss"] is False)

    os.environ[ENV_FLAG] = "0"
    r_disabled = anti_copy_check([copy_through], [pack])
    check("(REVERT) flag off -> inert no-op even on a copy-through text",
          r_disabled["enabled"] is False and r_disabled["hard_miss"] is False)
    os.environ.pop(ENV_FLAG, None)

    print("== anti_copy_guard self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)
