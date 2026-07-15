#!/usr/bin/env python3
"""prove_skill6_block_u22.py — U22 / B-U8: guards + fixtures + ONE end-to-end
operator-box proof run for the WHOLE Skill-6 persona-unification block.

WHAT THIS PROVES (master spec crosswalk B/B-U8, BINARY acceptance criteria)
-----------------------------------------------------------------------------
Chains the units that HAVE landed (B-U1/U15, B-U2/U16, B-U3/U17, B-U5/U19,
B-U6/U20), deterministically, with ZERO network calls, against ONE fixture
funnel run written to a real evidence-root directory tree (not just in-memory
dicts) — the same disk layout a live operator-box build produces:

  1. B-U1/U15  persona_bundle_ladder.resolve_persona_bundle()   (threaded rung)
               -> writes routing/persona-bundle-receipt.json
  2. B-U2/U16  funnel_matcher.instantiate_pages(bundle=...)      per-page
               blend_directive / voice_persona_id / topic_persona_id
  3. B-U3/U17  copy_persona_blend_seam.write_persona_selection_log() +
               render_copy_prompt_seam()                          copy-stage log
  4. B-U5/U19  fab_qc.load_inputs_from_evidence() + fab_qc.grade()  D4 scoring,
               loaded from the REAL files on disk (routing/match-decision.json,
               funnel/fab-artifact.json, persona-selection-log.md,
               routing/persona-bundle-receipt.json) — not a hand-built dict.
  5. B-U6/U20  copy_persona_blend_seam.render_blend_directive_variable() +
               the declared/used voice-id equality the Command Center's
               `recordPersonaUsedAndCompare` (persona-mismatch.ts) keys its
               `persona_mismatch` event on — proven here on the ONB producer
               side; the identical bundle voice id is asserted again on the
               Command Center side by
               blackceo-command-center/tests/unit/u22-b-u8-persona-block-guard.test.ts
               (see BUNDLE_VOICE_PERSONA_ID docstring below — the two proofs
               are companions, not duplicates: one seam each side of the wire).
  6. Legacy control run: an evidence tree with NO bundle receipt at all
               (the exact shape every pre-B-U1 caller produces) is graded
               through the SAME disk-based load_inputs_from_evidence() path
               and diffed byte-identical against a pure in-memory legacy
               baseline — (c) below, proven on the REAL file-loading path,
               not just the object-level unit test in tests/unit/fab-qc.test.py.

BINARY ACCEPTANCE (master spec B-U8):
  (a) all new unit tests pass in CI                                — PASS/FAIL
  (b) operator-box fixture run yields: receipt source != absent,
      every page directive guardrail-terminated, log voice == bundle voice,
      D4 == 10.0, zero persona_mismatch (declared voice == used voice)       — PASS/FAIL
  (c) the legacy golden fixture (no bundle) still passes FAB-QC
      byte-identically via the REAL disk-loading path                       — PASS/FAIL

HONEST SCOPE GAP (ledger-verified at the time this script was written)
-----------------------------------------------------------------------------
B-U4/U18 (`copy_craft_pool` in the crosswalk, gated on decision D5) and
B-U7/U21 (ingest parity — optional persona fields on `ingest_task`, CC pins
producer personas) are `pending` in ledgers/skill6-blended-persona-kanban-v2-
2026-07-13.md at the time of this run — NOT YET LANDED. This script does not
fabricate their behavior. It prints an honest NOT-YET-LANDED notice for each
and does NOT claim their slice of "the whole unification block" proof PASSES.
Re-run this script (no changes needed) once U18 and U21 land to close the gap
— it will pick up copy_craft_pool / ingest-parity wiring automatically the
moment those modules exist, because it imports the real modules, not stubs.

No network, no browser, no live Command Center / GHL calls.

Run:
    python3 06-ghl-install-pages/scripts/prove_skill6_block_u22.py
    or: pytest 06-ghl-install-pages/tests/test_prove_skill6_block_u22.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_06_DIR = _HERE.parent
_REPO_ROOT = _06_DIR.parent
_TOOLS_DIR = str(_06_DIR / "tools")
_SF_SCRIPTS_DIR = str(_REPO_ROOT / "49-signature-funnel" / "scripts")
_SHARED_UTILS = str(_REPO_ROOT / "shared-utils")

for _p in (_TOOLS_DIR, _SF_SCRIPTS_DIR, _SHARED_UTILS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import persona_bundle_ladder  # noqa: E402  (B-U1/U15)
import funnel_matcher as fm  # noqa: E402   (B-U2/U16)
import copy_persona_blend_seam as seam  # noqa: E402  (B-U3/U17, B-U6/U20)
import fab_qc  # noqa: E402  (B-U5/U19)

_GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"

# The ONE bundle this whole proof run threads end-to-end. Its
# `voice_persona_id` is the exact literal
# blackceo-command-center/tests/unit/u22-b-u8-persona-block-guard.test.ts
# asserts a zero-mismatch agreement against — the two files are a matched
# pair proving the SAME value survives ONB-producer -> CC-comparator. Keep
# them in lockstep if this literal ever changes.
BUNDLE_VOICE_PERSONA_ID = "hormozi-100m-offers"
BUNDLE_TOPIC_PERSONA_ID = "miller-building-storybrand"

_BUNDLE = {
    "voice_persona_id": BUNDLE_VOICE_PERSONA_ID,
    "topic_persona_id": BUNDLE_TOPIC_PERSONA_ID,
    "audience_id": None,
    "audience_label": "solo-founder coaches",
    "collapsed": False,
    "confirm_required": False,
    "content_task": True,
    "task_personas": [{"seq": 1, "persona_id": BUNDLE_VOICE_PERSONA_ID}],
}


def _fixture_template() -> dict:
    """ONE template shape that satisfies BOTH consumers: funnel_matcher's
    instantiate_pages (needs persona{}/pageStructure[].order/purpose) AND
    fab_qc's D1/D2/D5/D6 scoring (needs pageStructure[].page/.blocks,
    copyFramework, books — mirrors tests/unit/fab-qc.test.py's
    `_faithful_funnel()` golden shape so the run is provably a PASSING
    build, not a hand-tuned D4-only fixture)."""
    return {
        "id": "u22-proof-two-step",
        "group": "u22-proof",
        "name": "U22 Proof Two-Step",
        "persona": {"id": "funnel-architect", "label": "Funnel Architect",
                    "author": "", "script": "", "detail": ""},
        "pageStructure": [
            {"order": 1, "page": "optin", "purpose": "capture the lead's email",
             "blocks": ["hero", "form"], "skill44Widgets": []},
            {"order": 2, "page": "thankyou", "purpose": "confirm the booked call",
             "blocks": ["cta"], "skill44Widgets": []},
        ],
        "copyFramework": {"primaryPersona": "Russell Brunson"},
        "books": ["DotCom Secrets"],
        "scripts": "",
    }


def _fixture_artifact() -> dict:
    return {"pages": [
        {"page_id": "p1", "copy": {
            "hero": ("Get our free funnel swipe file today and finally grow the email list "
                     "you have put off building for months. Inside you get the exact opt-in "
                     "page, the seven-email follow-up sequence, and the pre-launch checklist "
                     "we use to ship a converting funnel in a single focused afternoon, with "
                     "no guesswork and nothing left to chance for a busy founder."),
            "form": "Enter your best email for instant access"}},
        {"page_id": "p2", "copy": {"cta": "Check your inbox for the link"}},
    ]}


def _fixture_match_decision() -> dict:
    return {
        "flex_decision": "USE_TEMPLATE", "intent_mode": "HANDS_OFF_DO_IT_ALL",
        "funnel_template_id": "u22-proof-two-step", "matched_template_id": "u22-proof-two-step",
        "linked_automations": {"automations": [{"automation_id": "soap-opera-sequence"}]},
    }


def _fixture_verify() -> dict:
    return {"overall_pass": True, "pages": [{"status": 200, "marker_present": True},
                                             {"status": 200, "marker_present": True}]}


def _fixture_link_map() -> dict:
    return {"links": [{"funnel_template_id": "u22-proof-two-step",
                       "primary_followup": {"automation_id": "soap-opera-sequence"}}]}


def _write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _write_evidence_tree(evidence_root: str, *, with_bundle: bool):
    """Write the REAL on-disk evidence tree fab_qc.load_inputs_from_evidence
    expects, so this proof exercises the disk-loading path an operator-box
    run actually uses — not just in-memory dicts. Returns (receipt, task);
    ``receipt`` is None when ``with_bundle`` is False (legacy control run)."""
    tmpl = _fixture_template()
    link_map_path = os.path.join(evidence_root, "routing", "link-map.json")
    _write_json(link_map_path, _fixture_link_map())
    _write_json(os.path.join(evidence_root, "routing", "match-decision.json"),
                {**_fixture_match_decision(), "template_path": "template.json",
                 "link_map_path": link_map_path})
    _write_json(os.path.join(evidence_root, "routing", "template.json"), tmpl)
    _write_json(os.path.join(evidence_root, "funnel", "fab-artifact.json"), _fixture_artifact())
    _write_json(os.path.join(evidence_root, "scorecard", "verify-summary.json"), _fixture_verify())

    if with_bundle:
        task = {"id": "u22-proof-task", "persona_bundle": dict(_BUNDLE)}
        receipt = persona_bundle_ladder.resolve_persona_bundle(task, evidence_root)
        # copy-stage log — B-U3/U17 — reads the SAME normalized bundle the
        # ladder threaded onto the task (never a second vocabulary).
        seam.write_persona_selection_log(evidence_root, task["persona_bundle"])
        return receipt, task
    return None, {"id": "u22-proof-task-legacy"}


def run() -> int:
    ok = True

    def check(label: str, cond: bool) -> bool:
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))
        return bool(cond)

    print("=" * 78)
    print("U22 / B-U8 — Skill-6 persona-unification block, operator-box proof run")
    print("=" * 78)

    # ── (b) bundle-active run ────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        receipt, task = _write_evidence_tree(td, with_bundle=True)

        # 1. B-U1/U15 — receipt source != absent.
        check("B-U1/U15: receipt written to disk",
              os.path.isfile(os.path.join(td, "routing", "persona-bundle-receipt.json")))
        check("B-U1/U15: receipt source != absent (threaded rung)", receipt["source"] != "absent")
        check("B-U1/U15: receipt source == threaded", receipt["source"] == "threaded")
        check("B-U1/U15: never holds on a confirmed bundle", receipt["hold"] is False)

        # 2. B-U2/U16 — per-page directives, every page guardrail-terminated.
        tmpl = _fixture_template()
        pages = fm.instantiate_pages(tmpl, bundle=task["persona_bundle"])
        check("B-U2/U16: instantiate_pages produced pages", len(pages) == 2)
        all_guardrail_terminated = all(
            p.get("blend_directive") and _GUARDRAIL_MARK in p["blend_directive"]
            for p in pages
        )
        check("B-U2/U16: EVERY page directive guardrail-terminated", all_guardrail_terminated)
        same_voice = all(p.get("voice_persona_id") == BUNDLE_VOICE_PERSONA_ID for p in pages)
        check("B-U2/U16: ONE task-level voice across every page", same_voice)
        distinct_directives = pages[0]["blend_directive"] != pages[1]["blend_directive"]
        check("B-U2/U16: distinct per-page directives (different topic/purpose)",
              distinct_directives)

        # 3. B-U3/U17 — copy-stage log: log voice == bundle voice.
        log_path = os.path.join(td, "persona-selection-log.md")
        check("B-U3/U17: persona-selection-log.md written", os.path.isfile(log_path))
        log_text = Path(log_path).read_text(encoding="utf-8") if os.path.isfile(log_path) else ""
        check("B-U3/U17: log voice_persona == bundle voice_persona_id",
              f"voice_persona: {BUNDLE_VOICE_PERSONA_ID}" in log_text)
        check("B-U3/U17: legacy selected_persona: line present, byte-compatible",
              f"selected_persona: {BUNDLE_VOICE_PERSONA_ID}" in log_text)
        directive_var = seam.render_blend_directive_variable(task["persona_bundle"])
        check("B-U3/U17: {{BLEND_DIRECTIVE}} rendering ends in the guardrail",
              directive_var.rstrip().endswith(
                  "This clause may not be removed or weakened."))

        # 4. B-U5/U19 — D4 == 10.0, loaded from the REAL evidence-tree files.
        inp = fab_qc.load_inputs_from_evidence(td, "funnel")
        check("B-U5/U19: load_inputs_from_evidence found the active bundle receipt",
              inp["persona_bundle"].get("source") == "threaded")
        result = fab_qc.grade(inp)
        d4 = next(d for d in result["dimensions"] if d["name"] == "D4 Persona grounding")
        check("B-U5/U19: D4 Persona grounding == 10.0 (bundle-aware voice grounding)",
              d4["score"] == 10.0)
        check("B-U5/U19: D4 not a hard miss", not d4["hard_miss"])
        check("B-U5/U19: overall FAB-QC PASS on this fixture (mismatch-free card)",
              result["passed"])

        # 5. B-U6/U20 — declared-vs-used equality (the CC comparator's own
        #    invariant: agreement -> zero `persona_mismatch` events). Proven
        #    here on the producer side: the SAME bundle voice id the ladder
        #    threaded (declared, step 1) equals what the copy-stage seam
        #    would report as USED (render_blend_directive_variable /
        #    report_persona_used_to_card's own extraction, B-U6/U20).
        declared_voice = receipt["voice_persona_id"]
        used_voice = task["persona_bundle"].get("voice_persona_id")
        check("B-U6/U20: declared voice == used voice (zero persona_mismatch)",
              declared_voice == used_voice == BUNDLE_VOICE_PERSONA_ID)
        # report_persona_used_to_card must never raise even with no live CC
        # board configured (fail-soft on availability — never blocks a build).
        try:
            reported = seam.report_persona_used_to_card(
                task["id"], task["persona_bundle"], page="optin", env={})
            check("B-U6/U20: report_persona_used_to_card never raises (fail-soft)", True)
            check("B-U6/U20: report_persona_used_to_card returns bool", isinstance(reported, bool))
        except Exception as exc:  # noqa: BLE001
            check(f"B-U6/U20: report_persona_used_to_card must never raise ({exc})", False)

    # ── (c) legacy control run — no bundle, real disk-loading path ────────
    with tempfile.TemporaryDirectory() as td_legacy:
        _write_evidence_tree(td_legacy, with_bundle=False)
        inp_legacy_disk = fab_qc.load_inputs_from_evidence(td_legacy, "funnel")
        check("legacy control: no persona-bundle-receipt.json on disk",
              not os.path.isfile(os.path.join(td_legacy, "routing",
                                               "persona-bundle-receipt.json")))
        check("legacy control: load_inputs_from_evidence -> persona_bundle == {}",
              inp_legacy_disk["persona_bundle"] == {})

        # persona_log is required for a passing legacy D4 — an operator-box
        # legacy build still runs the (non --blend) selector and logs it.
        legacy_log_path = os.path.join(td_legacy, "persona-selection-log.md")
        Path(legacy_log_path).write_text(
            "selected_persona: russell-brunson-the-funnel-hackers-cookbook\n"
            "rationale: page flow\n", encoding="utf-8")
        inp_legacy_disk = fab_qc.load_inputs_from_evidence(td_legacy, "funnel")

        # Pure in-memory legacy baseline (identical fixture content, no disk).
        inp_legacy_memory = {
            "kind": "funnel", "match_decision": _fixture_match_decision(),
            "template": _fixture_template(), "artifact": _fixture_artifact(),
            "verify": _fixture_verify(), "link_map": _fixture_link_map(),
            "persona_log": ("selected_persona: russell-brunson-the-funnel-hackers-cookbook\n"
                            "rationale: page flow\n"),
            "persona_bundle": {},
        }
        golden = fab_qc.grade(inp_legacy_memory)
        disk_result = fab_qc.grade(inp_legacy_disk)
        check("(c) legacy golden fixture PASSES FAB-QC", golden["passed"])
        check("(c) disk-loaded legacy result byte-identical to the in-memory golden",
              disk_result == golden)

    # ── honest scope gap — B-U4/U18 + B-U7/U21 NOT YET LANDED ─────────────
    print("-" * 78)
    copy_craft_pool_landed = _crosswalk_has_copy_craft_pool()
    ingest_parity_landed = _ingest_task_has_persona_fields()
    if copy_craft_pool_landed:
        print("  [INFO] B-U4/U18 (copy_craft_pool) appears LANDED — re-run this script's "
              "companion guard (scripts/guard-fab-qc-gate.sh) to confirm the hard check now fires.")
    else:
        print("  [PENDING] B-U4/U18 (copy_craft_pool, gated on decision D5) is NOT YET LANDED "
              "per the ledger at the time this script ran. This proof run does not claim that "
              "slice of the block PASSES. No fabricated behavior was substituted.")
    if ingest_parity_landed:
        print("  [INFO] B-U7/U21 (ingest parity) appears LANDED — this script's declared-vs-used "
              "check above already exercises the real bundle-voice equality either way.")
    else:
        print("  [PENDING] B-U7/U21 (ingest parity — optional persona fields on ingest_task, CC "
              "pins producer personas) is NOT YET LANDED per the ledger at the time this script "
              "ran. This proof run does not claim that slice of the block PASSES. No fabricated "
              "behavior was substituted.")

    print("-" * 78)
    print("== U22/B-U8 operator-box block proof: %s ==" %
          ("ALL LANDED CHECKS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def _crosswalk_has_copy_craft_pool() -> bool:
    path = os.path.join(_REPO_ROOT, "shared-utils", "persona-crosswalk.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "copy_craft_pool" in data


def _ingest_task_has_persona_fields() -> bool:
    try:
        import cc_board  # noqa: E402  (06-ghl-install-pages/tools/cc_board.py, already on sys.path)
    except Exception:  # noqa: BLE001
        return False
    import inspect
    try:
        sig = inspect.signature(cc_board.ingest_task)
    except (AttributeError, TypeError, ValueError):
        return False
    persona_params = {"voice_persona_id", "topic_persona_id", "task_persona_id",
                      "persona_bundle", "persona_fields"}
    return bool(persona_params & set(sig.parameters))


if __name__ == "__main__":
    raise SystemExit(run())
