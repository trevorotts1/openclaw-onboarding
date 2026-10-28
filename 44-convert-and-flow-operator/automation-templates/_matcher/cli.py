#!/usr/bin/env python3
"""cli.py — build the automation index, run a flexible match, expand a funnel, selftest.

Usage:
  python3 cli.py --build-index
  python3 cli.py --match "build me a soap opera sequence for new leads"
  python3 cli.py --match "..." --mode HANDS_OFF_DO_IT_ALL --json
  python3 cli.py --expand squeeze-page             # linked automations for a funnel
  python3 cli.py --selftest
"""
from __future__ import annotations
import argparse, json, os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)                       # automation-templates/
_LINKS = os.path.join(_ROOT, "_links", "funnel-to-automation.json")
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import automation_matcher as am  # noqa: E402
import flex  # noqa: E402

INDEX_PATH = os.path.join(_HERE, "catalog-index.json")


def build_index() -> int:
    cat = am.Catalog.load(_ROOT)
    cat.save_index(INDEX_PATH)
    print(f"indexed {len(cat.templates)} automation templates")
    print(f"groups: {sorted({t['group'] for t in cat.templates})}")
    print(f"-> {INDEX_PATH}")
    return 0


def run_match(text: str, mode: str | None, as_json: bool, threshold: float) -> int:
    cat = am.Catalog.from_index(INDEX_PATH) if os.path.isfile(INDEX_PATH) else am.Catalog.load(_ROOT)
    dec = am.match_automation(text, cat, threshold=threshold, intent_mode=mode)
    if as_json:
        print(json.dumps(dec, indent=2, ensure_ascii=False)); return 0
    print(f"intent_mode : {dec['intent_mode']}  ({dec['mode_reason']})")
    print(f"decision    : {dec['decision']}   imposes={dec['imposes_on_user']} "
          f"await_confirm={dec['await_confirm']}")
    print(f"matched     : {dec['matched_template']} ({dec['matched_name']})")
    print(f"confidence  : {dec['confidence']}  (threshold {dec['threshold']})")
    print(f"rationale   : {dec['rationale']}")
    print("top:")
    for r in dec["ranked"][:5]:
        print(f"   {r['confidence']:.3f}  {r['id']:<44} {r['parts']}")
    return 0


def expand(funnel_id: str, as_json: bool) -> int:
    cat = am.Catalog.from_index(INDEX_PATH) if os.path.isfile(INDEX_PATH) else am.Catalog.load(_ROOT)
    out = am.expand_funnel_to_automations(funnel_id, link_map_path=_LINKS, catalog=cat,
                                          intent_mode=flex.MODE_HANDSOFF)
    if as_json:
        print(json.dumps(out, indent=2, ensure_ascii=False)); return 0
    if not out["found"]:
        print(f"no link entry for '{funnel_id}'"); return 1
    print(f"funnel {funnel_id} ({out['funnel_group']}) -> linked automations "
          f"(recommended, not mandatory):")
    for a in out["automations"]:
        plan = "  [plan ok]" if a.get("workflow_plan") else ""
        print(f"   {a['role']:<11} {a['category']}/{a['automation_id']}{plan}")
    return 0


# (request, mode, expected_decision, expected_template-or-None)
_CASES = [
    ("just build me the full webinar follow-up sequence", None, flex.DEC_USE,
     "webinar-registration-reminder-replay-stack"),
    ("not sure what to send new subscribers — what do you recommend?", None, flex.DEC_SUGGEST,
     "new-subscriber-indoctrination"),
    ({"text": "set up my new-lead welcome emails", "steps": ["welcome", "bond", "pitch"]},
     None, flex.DEC_HONOR_USER, None),
    ("recover abandoned carts across email and sms, you handle it", None, flex.DEC_USE,
     "abandoned-cart-multichannel-recovery"),
    ("daily seinfeld broadcast emails, just do it", None, flex.DEC_USE, "daily-seinfeld-sequence"),
    ("a re-engagement winback campaign for cold subscribers", flex.MODE_HANDSOFF, flex.DEC_USE,
     "re-engagement-winback-broadcast"),
    ("application homework and booking nurture, build the whole thing", None, flex.DEC_USE,
     "application-homework-booking-nurture"),
    ("a sourdough bread recipe blog about hydration ratios, just do it", None, flex.DEC_CREATE_NEW,
     None),
    ("scarcity deadline close, but use my exact 4-email copy", None, flex.DEC_HONOR_USER, None),
]


def selftest(threshold: float) -> int:
    cat = am.Catalog.load(_ROOT)
    print(f"catalog: {len(cat.templates)} automation templates  threshold={threshold}\n")
    ok = 0
    for req, mode, want_dec, want_tmpl in _CASES:
        dec = am.match_automation(req, cat, threshold=threshold, intent_mode=mode)
        dec_ok = dec["decision"] == want_dec
        tmpl_ok = (want_tmpl is None) or (dec["matched_template"] == want_tmpl) or \
                  (dec["decision"] == flex.DEC_HONOR_USER)  # honor-user: template is ref-only
        passed = dec_ok and tmpl_ok
        ok += passed
        # invariant: never imposes, always overridable, never blocks
        assert dec["imposes_on_user"] is False and dec["override_allowed"] is True
        flag = "ok " if passed else "FAIL"
        print(f"[{flag}] mode={dec['intent_mode']:<24} dec={dec['decision']:<16} "
              f"tmpl={str(dec['matched_template'])[:34]:<34} :: {str(req)[:40]}")
    # funnel expansion coverage: every funnel resolves to >=1 CORRECT per-variant plan.
    # SK1-49: the predicate must assert the plan built is the RIGHT variant, not merely
    # that A plan EXISTS. The old `buildable = [... if a.get("workflow_plan")]` check
    # passed as long as any plan was attached — so a cross-wired variant (the
    # soap-opera-sequence id-collision class, where the same bare id lives in two
    # categories) would still count as a pass, exactly the gap that let the bug slip.
    # Each plan's source_ref MUST live under its declared category — the same invariant
    # CI locks in tests/test_automation_matcher.py::test_all_38_funnels_expand_to_correct_variant
    # — so the CLI selftest and CI no longer diverge.
    data = json.load(open(_LINKS, encoding="utf-8"))
    exp_ok = 0
    for l in data["links"]:
        out = am.expand_funnel_to_automations(l["funnel_template_id"], link_map_path=_LINKS,
                                              catalog=cat, intent_mode=flex.MODE_HANDSOFF)
        plans = [a for a in out["automations"] if a.get("workflow_plan")]
        correct = bool(plans) and all(
            f"{a['category']}/{a['automation_id']}.json"
            in (a["workflow_plan"].get("source_ref") or "")
            for a in plans
        )
        exp_ok += bool(out["found"] and correct)
    print(f"\nmatch: {ok}/{len(_CASES)} cases passed")
    print(f"funnel-expansion: {exp_ok}/{len(data['links'])} funnels resolve to a CORRECT per-variant plan")
    allok = (ok == len(_CASES)) and (exp_ok == len(data["links"]))
    print("SELFTEST PASS" if allok else "SELFTEST FAIL")
    return 0 if allok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="automation-matcher")
    ap.add_argument("--build-index", action="store_true")
    ap.add_argument("--match", metavar="TEXT")
    ap.add_argument("--mode", choices=list(flex.MODES))
    ap.add_argument("--expand", metavar="FUNNEL_ID")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--threshold", type=float, default=am.DEFAULT_THRESHOLD)
    a = ap.parse_args(argv)
    if a.build_index:
        return build_index()
    if a.match:
        return run_match(a.match, a.mode, a.json, a.threshold)
    if a.expand:
        return expand(a.expand, a.json)
    if a.selftest:
        return selftest(a.threshold)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
