#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_bundle.py — fail-closed prover for the Direct-Response BUILD BUNDLE (Skill 56).
Validates the Track-2 funnel-manifest.json against Skill 6's documented handoff contract
(PRD §5.2) AND every asset key against the §4 labeling grammar (which Skill 56 OWNS).
NO AI, stdlib only.

WHAT IT ENFORCES:
  * a manifest with >= 1 step exists (else fail-closed).        -> AF-SP56-BUNDLE-EMPTY
  * a sub-account / location id is present.                     -> AF-SP56-BUNDLE-LOCATION
  * funnel + step names carry the ZHC UPPERCASE prefix (R4).    -> AF-SP56-BUNDLE-ZHC
  * every asset_key / run_id parses the labeling grammar (R1-R3,
    with NO model name in any label).                           -> AF-SP56-BUNDLE-LABEL-GRAMMAR
  * every PAGE step has a fragment_path.                        -> AF-SP56-BUNDLE-FRAGMENT
  * every PAGE step carries method-decision inputs.             -> AF-SP56-BUNDLE-METHOD
  * every PAGE step carries copy_tokens or copy_md_path.        -> AF-SP56-BUNDLE-COPYTOKENS
  * a global SEO block: founder_name, >=3 keywords, description,
    canonical, language == 'en'.                                -> AF-SP56-BUNDLE-SEO
  * a thank-you step is present (gap closed vs legacy).         -> AF-SP56-BUNDLE-THANKYOU
  * the bump asset routes to the Skill 44 seam as copy, not a page. -> AF-SP56-BUNDLE-BUMP-ROUTE

stdlib only. Exit 0 = pass, exit 2 = autofail, exit 3 = usage/IO (still fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_EMPTY = "AF-SP56-BUNDLE-EMPTY"
AF_LOCATION = "AF-SP56-BUNDLE-LOCATION"
AF_ZHC = "AF-SP56-BUNDLE-ZHC"
AF_LABEL = "AF-SP56-BUNDLE-LABEL-GRAMMAR"
AF_FRAGMENT = "AF-SP56-BUNDLE-FRAGMENT"
AF_METHOD = "AF-SP56-BUNDLE-METHOD"
AF_COPYTOKENS = "AF-SP56-BUNDLE-COPYTOKENS"
AF_SEO = "AF-SP56-BUNDLE-SEO"
AF_THANKYOU = "AF-SP56-BUNDLE-THANKYOU"
AF_BUMP = "AF-SP56-BUNDLE-BUMP-ROUTE"

_SCRIPT_DIR = Path(__file__).resolve().parent
GRAMMAR = _SCRIPT_DIR.parent / "structure" / "labeling-grammar.json"

_DEFAULT_LABEL_RX = re.compile(
    r"^(?P<client>[a-z0-9][a-z0-9-]*)__(?P<funnel>[a-z0-9][a-z0-9-]*)__"
    r"(?P<stage>[a-z0-9][a-z0-9-]*)__(?P<type>[a-z0-9][a-z0-9-]*)__v(?P<version>[0-9]{2})(?P<variant>[a-z]?)$")
_DEFAULT_RUNID_RX = re.compile(
    r"^(?P<client>[a-z0-9][a-z0-9-]*)__(?P<funnel>[a-z0-9][a-z0-9-]*)__run-(?P<date>[0-9]{8})-(?P<seq>[0-9]{2})$")

# model tokens that must NEVER appear in a label (rule R1)
_MODEL_TOKENS = ("claude", "gemini", "gpt", "anthropic", "openai", "llama", "mistral")


def _grammar() -> Tuple[re.Pattern, re.Pattern, set, set]:
    try:
        g = json.loads(GRAMMAR.read_text(encoding="utf-8"))
        label_rx = re.compile(g["regex"])
        runid_rx = re.compile(g["run_id_regex"])
        stages = set(g.get("stage_vocabulary", []))
        types = set(g.get("type_vocabulary", []))
        return label_rx, runid_rx, stages, types
    except Exception:  # noqa: BLE001 — fail-closed to embedded defaults
        return _DEFAULT_LABEL_RX, _DEFAULT_RUNID_RX, set(), set()


def _valid_label(key: str, rx: re.Pattern, stages: set, types: set) -> Tuple[bool, str]:
    if not isinstance(key, str) or not key:
        return False, "empty/non-string label"
    low = key.lower()
    for tok in _MODEL_TOKENS:
        if tok in low:
            return False, f"label carries model token {tok!r} (rule R1: no model names in labels)"
    m = rx.match(key)
    if not m:
        return False, "does not parse <client>__<funnel>__<stage>__<type>__vNN<variant>"
    if stages and m.group("stage") not in stages:
        return False, f"stage {m.group('stage')!r} not in the stage vocabulary"
    if types:
        t = m.group("type")
        base = re.sub(r"-\d+$", "", t)  # img-03 -> img, email-07 -> email
        if base not in types:
            return False, f"type {t!r} not in the type vocabulary"
    return True, ""


def _is_zhc(name: Any) -> bool:
    return isinstance(name, str) and name.strip().startswith("ZHC ")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip().lower()


def evaluate(manifest: Any) -> List[Tuple[str, str]]:
    if not isinstance(manifest, dict):
        return [(AF_EMPTY, "manifest root is not a JSON object")]
    label_rx, runid_rx, stages, types = _grammar()
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        return [(AF_EMPTY, "manifest has no steps (cannot prove the bundle; fail-closed)")]

    fails: List[Tuple[str, str]] = []

    # sub-account / location id
    if not (manifest.get("location_id") or manifest.get("sub_account") or manifest.get("subaccount_id")):
        fails.append((AF_LOCATION, "no sub-account / location id (Skill 6 sub-account gate REFUSES on mismatch)"))

    # run_id grammar
    rid = manifest.get("run_id")
    if rid is not None and not runid_rx.match(str(rid)):
        fails.append((AF_LABEL, f"run_id {rid!r} does not parse the run-id grammar"))

    # funnel name ZHC
    if not _is_zhc(manifest.get("funnel_name")):
        fails.append((AF_ZHC, f"funnel_name {manifest.get('funnel_name')!r} lacks the ZHC UPPERCASE prefix"))

    # global SEO block
    seo = manifest.get("seo")
    if not isinstance(seo, dict):
        fails.append((AF_SEO, "no global seo block (founder_name / keywords / description / canonical / language)"))
    else:
        if not (isinstance(seo.get("founder_name"), str) and seo["founder_name"].strip()):
            fails.append((AF_SEO, "seo.founder_name missing — Skill 6 validate_founder_name HALTs the build"))
        kws = seo.get("keywords")
        if not (isinstance(kws, list) and len([k for k in kws if isinstance(k, str) and k.strip()]) >= 3):
            fails.append((AF_SEO, "seo.keywords must have >= 3 researched keywords"))
        if not (isinstance(seo.get("description"), str) and seo["description"].strip()):
            fails.append((AF_SEO, "seo.description missing/empty"))
        if not (isinstance(seo.get("canonical"), str) and seo["canonical"].strip()):
            fails.append((AF_SEO, "seo.canonical missing/empty"))
        if _norm(seo.get("language")) != "en":
            fails.append((AF_SEO, f"seo.language must be 'en', got {seo.get('language')!r}"))

    has_thank_you = False
    for st in steps:
        if not isinstance(st, dict):
            fails.append((AF_EMPTY, "a step entry is not an object"))
            continue
        stage = _norm(st.get("stage"))
        key = st.get("asset_key", "")
        okl, why = _valid_label(key, label_rx, stages, types)
        if not okl:
            fails.append((AF_LABEL, f"step asset_key {key!r}: {why}"))
        if not _is_zhc(st.get("step_name")):
            fails.append((AF_ZHC, f"step {key or stage!r}: step_name lacks the ZHC prefix"))

        if stage in ("thankyou", "thank-you"):
            has_thank_you = True

        if stage == "bump":
            # bump routes to the Skill 44 seam as copy, not a page
            if _norm(st.get("route")) not in ("skill44_widget", "skill44widget", "skill-44-widget"):
                fails.append((AF_BUMP, f"bump step must route to the Skill 44 seam (route=SKILL44_WIDGET), got {st.get('route')!r}"))
            if not (st.get("copy_md_path") or st.get("copy_tokens")):
                fails.append((AF_COPYTOKENS, "bump step missing copy_md_path / copy_tokens"))
            continue

        # PAGE steps (everything except the bump) need fragment + method + copy fidelity
        if not (isinstance(st.get("fragment_path"), str) and st["fragment_path"].strip()):
            fails.append((AF_FRAGMENT, f"step {key or stage!r}: missing fragment_path (rawCustomCode must be a fragment)"))
        md = st.get("method_decision")
        if not (isinstance(md, dict) and md):
            fails.append((AF_METHOD, f"step {key or stage!r}: missing method_decision inputs (Skill 6 Phase-5 classifier)"))
        ct, cmp = st.get("copy_tokens"), st.get("copy_md_path")
        if not ((isinstance(ct, list) and ct) or (isinstance(cmp, str) and cmp.strip())):
            fails.append((AF_COPYTOKENS, f"step {key or stage!r}: missing copy_tokens / copy_md_path (verify_page fidelity)"))

    if not has_thank_you:
        fails.append((AF_THANKYOU, "no thank-you step — every funnel must terminate on a thank-you page (gap closed)"))

    return fails


def decide_exit(failures) -> int:
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def prove(path: str, as_json: bool = False) -> int:
    p = Path(path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"manifest not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        manifest = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), [("USAGE", f"cannot read/parse manifest JSON: {exc}")], as_json)
        return EXIT_USAGE
    failures = evaluate(manifest)
    _emit(str(p), failures, as_json)
    return decide_exit(failures)


def _emit(source: str, failures, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "sales-page-assets-bundle", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Sales Page Assets :: BUILD BUNDLE (labels + Skill 6 manifest contract) ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — labels parse the grammar; the funnel-manifest satisfies the Skill 6 contract.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test.
# ---------------------------------------------------------------------------
def _page_step(order, stage, variant=""):
    v = variant
    return {
        "order": order, "stage": stage, "variant": v,
        "step_name": f"ZHC glow-method {stage} v01{v}",
        "asset_key": f"jane-doe__glow-method__{stage}__page__v01{v}",
        "fragment_path": f"pages/jane-doe__glow-method__{stage}__page__v01{v}.fragment.html",
        "method_decision": {"classification": "SIMPLE", "route": "DIRECT"},
        "copy_tokens": ["headline token", "cta token"],
    }


def _valid_manifest() -> Dict[str, Any]:
    return {
        "funnel_manifest": "sales-page-assets",
        "run_id": "jane-doe__glow-method__run-20260702-01",
        "location_id": "loc_ABC123",
        "funnel_name": "ZHC jane-doe glow-method v01",
        "seo": {"founder_name": "Jane Doe",
                "keywords": ["glow method", "skincare ritual", "founder skincare"],
                "description": "The Glow Method sales funnel.",
                "canonical": "https://example.com/glow-method", "language": "en"},
        "media": {"folder": "jane-doe__glow-method",
                  "cdn_map": {"jane-doe__glow-method__main__img-01__v01": "https://msgsndr-media/x.png"}},
        "steps": [
            _page_step(1, "main", "a"),
            _page_step(2, "main", "b"),
            _page_step(3, "upsell-1", "a"),
            _page_step(4, "downsell-1"),
            _page_step(5, "high-ticket"),
            {"order": 6, "stage": "bump", "step_name": "ZHC glow-method bump v01",
             "asset_key": "jane-doe__glow-method__bump__copy__v01",
             "route": "SKILL44_WIDGET", "copy_md_path": "copy/jane-doe__glow-method__bump__copy__v01.md"},
            {"order": 7, "stage": "thank-you", "variant": "",
             "step_name": "ZHC glow-method thank-you v01",
             "asset_key": "jane-doe__glow-method__thank-you__page__v01",
             "fragment_path": "pages/jane-doe__glow-method__thank-you__page__v01.fragment.html",
             "method_decision": {"classification": "SIMPLE", "route": "DIRECT"},
             "copy_md_path": "copy/thank-you.md"},
        ],
    }


def self_test() -> int:
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        fails = evaluate(fixture)
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:16s} -> exit {decide_exit(fails)}"
              + ("" if good else f" (unexpected: {fails})"))

    def check_fail(name, fixture, expect):
        nonlocal ok
        fails = evaluate(fixture)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} (want {expect})")

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("full-bundle", _valid_manifest())

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    f = _valid_manifest(); f["steps"][0]["asset_key"] = "jane-doe__glow-method__main__claude__v01a"
    check_fail("model-name-in-label", f, AF_LABEL)

    f = _valid_manifest(); f["funnel_name"] = "jane-doe glow-method v01"
    check_fail("no-zhc-funnel", f, AF_ZHC)

    f = _valid_manifest(); f["seo"]["keywords"] = ["only-one"]
    check_fail("too-few-keywords", f, AF_SEO)

    f = _valid_manifest(); del f["seo"]["founder_name"]
    check_fail("no-founder-name", f, AF_SEO)

    f = _valid_manifest(); f["steps"][0].pop("fragment_path")
    check_fail("no-fragment", f, AF_FRAGMENT)

    f = _valid_manifest(); f["steps"][0].pop("method_decision")
    check_fail("no-method", f, AF_METHOD)

    f = _valid_manifest(); f["steps"] = [s for s in f["steps"] if _norm(s.get("stage")) != "thank-you"]
    check_fail("no-thank-you", f, AF_THANKYOU)

    f = _valid_manifest()
    for s in f["steps"]:
        if _norm(s.get("stage")) == "bump":
            s["route"] = "DIRECT"
    check_fail("bump-wrong-route", f, AF_BUMP)

    f = _valid_manifest(); f.pop("location_id")
    check_fail("no-location", f, AF_LOCATION)

    check_fail("no-steps", {"funnel_name": "ZHC x y v01", "steps": []}, AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the BUILD BUNDLE (labels + Skill 6 contract).")
    ap.add_argument("--manifest", help="path to funnel-manifest.json")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.manifest:
        print("USAGE ERROR: pass --manifest <funnel-manifest.json> (or --self-test).")
        return EXIT_USAGE
    return prove(args.manifest, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
