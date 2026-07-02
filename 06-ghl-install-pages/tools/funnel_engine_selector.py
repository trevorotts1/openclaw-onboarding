#!/usr/bin/env python3
"""funnel_engine_selector.py — SHARED STEP-0 funnel-BUILD engine selector for Skill 6.

PURPOSE
-------
Before the template-first funnel matcher runs (tools/funnel_matcher.py), decide
WHICH specialist AUTHORING ENGINE (if any) owns a "build me a funnel" request.
Some funnels are not generic page-plans — they are a specific, IP-gated product
with their own SACRED copy/image contract and their own fail-closed pipeline:

  * Skill 49 (signature-funnel) — the Trevor Otts 12-section Hero + 3/5/7 funnel.
  * Skill 56 (sales-page-assets) — PLANNED second entry (direct-response / VSL).

This selector reads ``funnel-engines/registry.json`` (the ONE registry every such
engine registers itself into), scores the request against each engine's match
block, and returns:

  * decision = ROUTE_TO_ENGINE  -> the caller invokes that engine's canonical
      fail-closed entry shell (the engine authors copy+images, then delegates the
      GHL media + funnel/page build BACK to Skill 6 — Skill 6 stays the ONE GHL
      delivery rail).
  * decision = NO_ENGINE_MATCH  -> the caller FALLS THROUGH to the existing
      template-first funnel matcher + generic Skill-6 build. Never blocks.

DESIGN CONTRACT (mirrors funnel_matcher.py)
-------------------------------------------
* stdlib-only, deterministic, no network, no model. Lexical scorer.
* GUIDE, never a gate: a below-threshold score never prevents a build, and an
  explicit user desire ("build the signature funnel") routes by name.
* EXTENSIBLE WITHOUT CODE CHANGE: a new engine is one appended object in
  registry.json engines[]. This module discovers it automatically. Skill 56 will
  register the second entry; no edit here is needed for it to be selectable.
* Skill 6 is the ONE GHL delivery rail. This selector only picks the AUTHORING
  engine; the engine delegates delivery back to Skill 6.

USAGE
    python3 funnel_engine_selector.py --match "build me a signature funnel"
    python3 funnel_engine_selector.py --list
    python3 funnel_engine_selector.py --self-test

Or from Python::

    from funnel_engine_selector import load_registry, select_engine, step0_select_engine
    reg = load_registry()
    decision = select_engine("build my 12-section signature funnel", reg)
    if decision["decision"] == "ROUTE_TO_ENGINE":
        run(decision["engine"]["entry"])   # the canonical fail-closed shell
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

# --------------------------------------------------------------------------- #
# Paths / config
# --------------------------------------------------------------------------- #
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../06-.../tools
_SKILL_DIR = os.path.dirname(_THIS_DIR)                          # .../06-ghl-install-pages
_DEFAULT_REGISTRY = os.path.join(_SKILL_DIR, "funnel-engines", "registry.json")

DEFAULT_THRESHOLD = 0.55        # confidence (0..1) to ROUTE_TO_ENGINE
_CONF_DENOM = 6.0               # raw-score -> confidence normaliser (matches funnel_matcher)

# raw-score weights (kept in the same family as funnel_matcher for consistency)
_W_NAME = 6.0                   # a registered engine NAME appears verbatim in the request
_W_KW_FULL = 3.0               # a whole keyword phrase matched
_W_KW_PART = 1.0               # a keyword phrase partially matched (>=60% tokens)
_W_SIGNAL = 0.30               # per signal-token overlap (capped)
_W_ANTI = -4.0                 # an anti-signal phrase matched (penalty)
_CAP_SIGNAL = 2.0

DEC_ROUTE = "ROUTE_TO_ENGINE"
DEC_NONE = "NO_ENGINE_MATCH"

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "or", "my", "me", "i", "we",
    "our", "your", "you", "with", "in", "on", "at", "is", "are", "be", "want",
    "need", "build", "make", "create", "get", "got", "into", "that", "this",
    "it", "so", "can", "will", "do", "have", "has", "page", "funnel", "funnels",
    "new",
}


# --------------------------------------------------------------------------- #
# Tokenisation
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in raw if t not in _STOPWORDS and len(t) > 1]


def _content_tokens(text: str) -> set[str]:
    return set(_tokens(text))


def _request_text(request: Any) -> str:
    if isinstance(request, str):
        return _norm(request)
    if isinstance(request, dict):
        parts = [str(request.get(k, "")) for k in
                 ("text", "brief", "goal", "intent", "description", "ask",
                  "message", "funnel_type", "type")]
        return _norm(" ".join(p for p in parts if p))
    return _norm(str(request or ""))


def _phrase_hit(phrase: str, req_text: str, req_tokens: set[str]) -> float:
    """1.0 full hit, 0.5 partial (>=60% content tokens present), else 0."""
    phrase_n = _norm(phrase)
    if not phrase_n:
        return 0.0
    if phrase_n in req_text:
        return 1.0
    ptoks = _content_tokens(phrase)
    if not ptoks:
        return 0.0
    if len(ptoks & req_tokens) / len(ptoks) >= 0.6:
        return 0.5
    return 0.0


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def load_registry(path: str | None = None) -> dict:
    """Load the funnel-engine registry. Returns {} (never raises) if unreadable —
    a missing/broken registry means 'no specialist engines', i.e. always fall
    through to the template matcher. Selection must never block a build."""
    p = path or os.environ.get("GHL_FUNNEL_ENGINE_REGISTRY") or _DEFAULT_REGISTRY
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"engines": [], "default_engine": None, "_source": p, "_loaded": False}
    if not isinstance(data, dict):
        return {"engines": [], "default_engine": None, "_source": p, "_loaded": False}
    data.setdefault("engines", [])
    data["_source"] = p
    data["_loaded"] = True
    return data


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #
def score_engine(engine: dict, req_text: str, req_tokens: set[str]) -> dict:
    """Raw score + per-signal breakdown for one engine against the request."""
    match = engine.get("match", {}) or {}
    parts: dict[str, float] = {}

    # explicit NAME hit (strongest; an explicit desire always routes)
    name_hit = 0.0
    for nm in match.get("names", []):
        if _norm(nm) and _norm(nm) in req_text:
            name_hit = _W_NAME
            break
    if name_hit:
        parts["name"] = name_hit

    # keyword phrases
    kw = 0.0
    for phrase in match.get("keywords", []):
        h = _phrase_hit(phrase, req_text, req_tokens)
        kw += _W_KW_FULL if h == 1.0 else (_W_KW_PART if h else 0.0)
    if kw:
        parts["keywords"] = round(kw, 3)

    # signal-token overlap (capped)
    sig_tokens = _content_tokens(" ".join(match.get("signals", [])))
    s = min(_CAP_SIGNAL, _W_SIGNAL * len(sig_tokens & req_tokens))
    if s:
        parts["signals"] = round(s, 3)

    # anti-signals (penalty)
    anti = 0.0
    for phrase in match.get("anti_signals", []):
        if _phrase_hit(phrase, req_text, req_tokens) == 1.0:
            anti += _W_ANTI
    if anti:
        parts["antiSignal"] = round(anti, 3)

    raw = sum(parts.values())
    return {"id": engine.get("id"), "name": engine.get("name"),
            "skill": engine.get("skill"), "raw": round(raw, 3), "parts": parts}


def _confidence(raw: float) -> float:
    return max(0.0, min(1.0, raw / _CONF_DENOM))


# --------------------------------------------------------------------------- #
# Select
# --------------------------------------------------------------------------- #
def select_engine(request: Any, registry: dict | None = None, *,
                  threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Score every registered engine against ``request`` and return a decision.

    decision is ROUTE_TO_ENGINE (a specialist engine owns this funnel) or
    NO_ENGINE_MATCH (fall through to the template-first matcher). Each engine may
    pin its own ``confidence_threshold`` in the registry; otherwise ``threshold``
    applies. Never raises; a matcher failure must not block a build."""
    registry = registry if registry is not None else load_registry()
    engines = registry.get("engines", []) or []
    req_text = _request_text(request)
    req_tokens = _content_tokens(req_text)

    scored = []
    for eng in engines:
        sc = score_engine(eng, req_text, req_tokens)
        eng_thr = float(eng.get("confidence_threshold", threshold))
        sc["confidence"] = round(_confidence(sc["raw"]), 4)
        sc["threshold"] = eng_thr
        sc["priority"] = int(eng.get("priority", 0))
        sc["confident"] = bool(sc["confidence"] >= eng_thr and sc["raw"] > 0)
        sc["_engine"] = eng
        scored.append(sc)

    # rank: confident first, then priority, then confidence, then id (stable)
    scored.sort(key=lambda s: (not s["confident"], -s["priority"],
                               -s["confidence"], str(s["id"])))
    best = scored[0] if scored else None
    ranked = [{"id": s["id"], "skill": s["skill"], "confidence": s["confidence"],
               "raw": s["raw"], "threshold": s["threshold"],
               "confident": s["confident"], "parts": s["parts"]} for s in scored]

    if best and best["confident"]:
        eng = best["_engine"]
        return {
            "decision": DEC_ROUTE,
            "engine": {k: v for k, v in eng.items() if not k.startswith("_")},
            "engine_id": best["id"],
            "skill": best["skill"],
            "entry": eng.get("entry"),
            "confidence": best["confidence"],
            "threshold": best["threshold"],
            "score_parts": best["parts"],
            "ranked": ranked,
            "delivery_rail": eng.get("delivery_rail", "06-ghl-install-pages"),
            "rationale": (f"'{best['name']}' (skill {best['skill']}) confidence="
                          f"{best['confidence']} >= threshold {best['threshold']}. "
                          f"Route the funnel build to its canonical entry "
                          f"({eng.get('entry')}); it authors copy+images then "
                          f"delegates GHL delivery back to Skill 6."),
            "ts": _ts(),
        }
    return {
        "decision": DEC_NONE,
        "engine": None,
        "engine_id": None,
        "ranked": ranked,
        "rationale": ("No registered funnel-build engine cleared its confidence "
                      "threshold. Fall through to the template-first funnel "
                      "matcher (funnel_matcher.step0_match) + generic Skill-6 build. "
                      "A below-threshold score never blocks a build."),
        "ts": _ts(),
    }


def step0_select_engine(task: dict, evidence_root: str, *,
                        registry_path: str | None = None,
                        threshold: float = DEFAULT_THRESHOLD) -> dict:
    """STEP-0 engine selector — the front of the funnel-build flow.

    Runs BEFORE the template-first funnel matcher. Reads the board ``task``,
    selects the owning engine (if any), writes ``routing/funnel-engine-match.json``
    + appends to ``routing/funnel-engine-decisions.jsonl``, and stamps the task:

      * ROUTE_TO_ENGINE -> task['funnel_engine'] = <id>, task['funnel_engine_entry']
        = <canonical shell>. The caller invokes that shell; the engine delegates
        GHL delivery back to Skill 6.
      * NO_ENGINE_MATCH -> task is untouched; the caller proceeds to step0_match
        (template-first) as before.

    Never raises into the build loop (selection is advisory glue)."""
    try:
        registry = load_registry(registry_path)
        request = {
            "text": task.get("brief", "") or task.get("text", ""),
            "goal": task.get("goal", ""),
            "funnel_type": task.get("funnel_type", task.get("type", "")),
            "explicit_funnel": task.get("explicit_funnel", ""),
        }
        decision = select_engine(request, registry, threshold=threshold)

        routing = os.path.join(evidence_root, "routing")
        os.makedirs(routing, exist_ok=True)
        with open(os.path.join(routing, "funnel-engine-match.json"), "w",
                  encoding="utf-8") as f:
            json.dump(decision, f, indent=2)
        with open(os.path.join(routing, "funnel-engine-decisions.jsonl"), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": decision.get("ts", _ts()),
                "decision": decision["decision"],
                "engine_id": decision.get("engine_id"),
                "confidence": decision.get("confidence"),
                "request": request,
            }, ensure_ascii=False) + "\n")

        if decision["decision"] == DEC_ROUTE:
            task["funnel_engine"] = decision["engine_id"]
            task["funnel_engine_skill"] = decision["skill"]
            task["funnel_engine_entry"] = decision["entry"]
            task["funnel_engine_delivery_rail"] = decision.get("delivery_rail")
        return decision
    except Exception as exc:  # noqa: BLE001 — selection must never block a build
        return {"decision": DEC_NONE, "engine": None,
                "reason": f"selector error: {type(exc).__name__}: {exc}"}


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Self-test (deterministic; no network, no model)
# --------------------------------------------------------------------------- #
def _self_test() -> int:
    reg = load_registry()
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # registry loads and carries the signature-funnel entry
    check("registry loaded", reg.get("_loaded") is True)
    ids = {e.get("id") for e in reg.get("engines", [])}
    check("signature-funnel registered", "signature-funnel" in ids)

    # explicit name routes to the signature engine
    d1 = select_engine("build me a signature funnel for my coaching offer", reg)
    check("explicit 'signature funnel' -> ROUTE_TO_ENGINE",
          d1["decision"] == DEC_ROUTE and d1["engine_id"] == "signature-funnel")

    # a strong keyword cluster routes too
    d2 = select_engine(
        "I need the 12-section hero with upsell and downsell and a thank-you page", reg)
    check("12-section hero + upsell/downsell -> ROUTE_TO_ENGINE",
          d2["decision"] == DEC_ROUTE)

    # a generic funnel request does NOT hijack -> falls through
    d3 = select_engine("set up a basic webinar registration funnel", reg)
    check("generic webinar request -> NO_ENGINE_MATCH (falls through)",
          d3["decision"] == DEC_NONE)

    # empty request never routes
    d4 = select_engine("", reg)
    check("empty request -> NO_ENGINE_MATCH", d4["decision"] == DEC_NONE)

    # a broken/missing registry never raises and yields NO_ENGINE_MATCH
    d5 = select_engine("signature funnel please", {"engines": []})
    check("no engines registered -> NO_ENGINE_MATCH", d5["decision"] == DEC_NONE)

    print("\nSELF-TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Shared STEP-0 funnel-build engine selector (Skill 6).")
    ap.add_argument("--match", metavar="TEXT", help="Score a request and print the decision.")
    ap.add_argument("--list", action="store_true", help="List registered engines.")
    ap.add_argument("--registry", default=None, help="Path to registry.json.")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--self-test", action="store_true", help="Run the deterministic self-test.")
    ap.add_argument("--json", action="store_true", help="Raw JSON output for --match/--list.")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    reg = load_registry(args.registry)

    if args.list:
        out = [{"id": e.get("id"), "skill": e.get("skill"), "name": e.get("name"),
                "entry": e.get("entry"), "priority": e.get("priority", 0)}
               for e in reg.get("engines", [])]
        print(json.dumps(out, indent=2) if args.json else
              "\n".join(f"- {o['id']} ({o['skill']}): {o['name']} -> {o['entry']}"
                        for o in out) or "(no engines registered)")
        return 0

    if args.match:
        decision = select_engine(args.match, reg, threshold=args.threshold)
        if args.json:
            print(json.dumps(decision, indent=2))
        else:
            print(f"decision : {decision['decision']}")
            if decision["decision"] == DEC_ROUTE:
                print(f"engine   : {decision['engine_id']} ({decision['skill']})")
                print(f"entry    : {decision['entry']}")
                print(f"confidence: {decision['confidence']} (>= {decision['threshold']})")
            print(f"rationale: {decision['rationale']}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
