#!/usr/bin/env python3
"""Build the mini-app questions_payload from the CANONICAL intake JSONs.

SINGLE SOURCE OF TRUTH: the app never hardcodes a question. It renders the
exact prompt/help/kind/allowed_values/value_labels from:

  standard  -> 23-ai-workforce-blueprint/templates/role-library/presentations/
               intake/deck-intake-questions.json
               + intake/upsell-questions.json (the sales/checkout + VSL yes-no)
  signature -> 51-signature-presentation/intake/sp-8-questions.json
               (Skill 51's SACRED 8, q1..q8 + the frame-selection question)

The curated 7-9 core question set for the app is selected by `--questions`
(comma-separated ids) or defaults to the id list in this script. Edit the JSONs,
not this script, to change what a client is asked. The app's questions.json is
generated from this so the shipped UI is a snapshot of the canonical source.

The signature set is not curated: it is the whole sp-8 spec, asked as Skill 51
defines it. Its path here is the port of the miniapp builder's `--set signature`
(FIX-PLAN Item 13, step S8): the miniapp builder was the only signature payload
builder, and the capability now lives in the live app's builder too, so the
deprecated tree is no longer the sole holder of it.

Usage:
  build_questions_payload.py --run-id RUN123 [--out payload.json]
  build_questions_payload.py --set signature --run-id RUN123 [--out payload.json]
  build_questions_payload.py --selftest
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Fields carried straight through from the JSON question objects to the UI.
# refuse_values/refuse_message ride through so the FRONTEND can refuse the
# other axis's vocabulary at the point the client types it, instead of only
# on the box in intake_writer. Same fields, same spelling, as the bank's
# subfield annotations -- see _project_run_mode_question.
_PASSTHROUGH = ("id", "order", "prompt", "help", "kind", "required",
                "allowed_values", "value_labels", "default",
                "conditional_on", "ask_if", "block_gate", "storeOn", "key",
                "refuse_values", "refuse_message")

# The curated core set the Presentation Interview app asks. Cap 21 binds the
# set excluding the declined-reason waiver follow-ups; a follow-up (asked
# only when its toggle is answered "no") rides on its toggle and does not
# count against the cap -- the selftest pins that shape per follow-up.
# (The counted set stood at exactly 20 before Item 34; the motion toggle
# is a required election asked on every run, so it counts, and its reason
# follow-up rides excluded like every other follow-up. Cap is 21.)
# Every id must exist in deck-intake-questions.json, upsell-questions.json, or
# APP_ONLY_QUESTIONS below.
DEFAULT_CURATED = [
    "presentation_type",          # type-picker (order 0) -- MUST be first, see selftest guard
    "offer_name",                 # company/offer
    "named_methodology",          # branded method name (order 17.5) -- FIX-PITCH-ANTI-FAB,
                                   # feeds pitch_engines_check.chk_branded_method; unconditional
                                   # (no ask_if), so it must stay curated in QUICK mode too
    "transformation_promise",     # transformation promise
    "time_to_result",             # time-to-result (order 33.5) -- FIX-PITCH-ANTI-FAB, feeds
                                   # pitch_engines_check.chk_time_to_result; same reasoning
    "audience",                   # audience
    "cta_action",                 # CTA
    "brand_primary",              # logo check
    "image_links",                # image-link capture (app-only)
    "tone",                       # tone
    "final_price",                # price
    "speech_speed_preference",    # speech speed (order 7.5)
    "want_sales_checkout",        # new sales/checkout yes-no (order 7.6)
    "sales_checkout_declined_reason",  # U026 waiver follow-up (order 7.61) --
                                   # conditional_on want_sales_checkout = "no";
                                   # the client's VERBATIM reason. Without it in
                                   # the minted payload the hosted flow never
                                   # asks, so a hosted "no" could never carry
                                   # the waiver the builder gate requires
                                   # (FIX-PLAN Item 12).
    "want_vsl_page",              # new VSL yes-no (order 7.7)
    "vsl_page_declined_reason",   # U026 waiver follow-up (order 7.71) --
                                   # conditional_on want_vsl_page = "no"; same
                                   # verbatim discipline as the sales/checkout
                                   # reason above.
    "want_motion_graphics",       # Item 34 motion election yes-no (order 7.8)
    "motion_graphics_declined_reason",  # its conditional waiver follow-up (7.81)
    "want_email_sequences",       # Skill 50 email election yes-no (order 7.9)
    "email_sequences_declined_reason",  # its conditional waiver follow-up (7.91)
    "run_mode",                   # FIX 11 run mode (projected from the bank's
                                   # resource_plan.run_mode subfield) -- the
                                   # hosted app's only way to reach Ultra
    # FIX 62: Ollama Cloud plan choice
    "ollama_plan",
    # FIX 61.2: client model picks (projected from bank subfields, like run_mode)
    "deepseek_variant",
    "openrouter_model",
    "client_notes",               # extras
]

# Questions the APP asks that have no canonical deck-intake counterpart (they are
# capture UX, not driver fields). brand_primary (logo check) exists canonically;
# image_links is the app's image-link capture and stores under deck_brief.IMAGE_LINKS.
#: The app-facing wording for the projected run-mode question. Only the
#: CLIENT-FACING copy lives here: the vocabulary (allowed_values),
#: refuse_values and refuse_message are read from the bank by
#: _project_run_mode_question below, never restated. The bank cannot supply a
#: prompt for this one because run_mode is a SUBFIELD of the merged
#: resource_plan turn, whose single prompt covers six subfields at once -- a
#: standalone question needs its own sentence, and that sentence is app UX.
RUN_MODE_APP_COPY = {
    "id": "run_mode",
    "section": "deck-intake",
    "order": 11.5,
    "prompt": "How hard should we run the BUILD of this deck — Ultra, Standard, or Economy?",
    "help": ("This is about the BUILD, not this interview. Ultra runs at the "
             "highest concurrency and the strongest model mix (fastest, most "
             "expensive); Standard is the department default; Economy runs "
             "leaner and cheaper. Skip this and you get Standard — we never "
             "put a run on Ultra unless you asked for it. Note: 'quick' and "
             "'in-depth' belong to a different question (how long this "
             "interview is) and are not answers here."),
    "kind": "text",
    # NOT deck_brief: a run mode is an EXECUTION axis, not deck content (the
    # bank subfield's own note). pre_presentation_capture.RUN_MODE is a
    # location presentation-intake-poll.sh's read_run_mode() already reads.
    "storeOn": "pre_presentation_capture.RUN_MODE",
    "value_labels": {
        "ultra": "Ultra: the strongest models you choose, up to 16x faster",
        "standard": "Standard — the department default",
        "economy": "Economy — leaner and cheaper",
    },
    "required": False,
    "block_gate": False,
}

#: Where the run-mode vocabulary comes from, stated once.
RUN_MODE_BANK_QUESTION = "resource_plan"
RUN_MODE_BANK_SUBFIELD = "run_mode"

#: FIX 62: App-facing copy for the Ollama Cloud plan choice.
OLLAMA_PLAN_APP_COPY = {
    "id": "ollama_plan",
    "section": "deck-intake",
    "order": 11.55,
    "prompt": "Are you on the Ollama Cloud $20/month or $100/month plan?",
    "help": ("The $20 plan runs 3 at once; the $100 plan runs 8 at once. "
             "Shown only when Ollama Cloud is selected."),
    "kind": "text",
    "storeOn": "pre_presentation_capture.OLLAMA_PLAN",
    "value_labels": {
        "$20/month": "$20/month — 3 at once",
        "$100/month": "$100/month — 8 at once",
    },
    "required": False,
    "block_gate": False,
}

#: FIX 61.2: App-facing copy for the DeepSeek variant pick (projected from
#: the bank's resource_plan.deepseek_variant subfield, like run_mode).
DEEPSEEK_VARIANT_APP_COPY = {
    "id": "deepseek_variant",
    "section": "deck-intake",
    "order": 11.6,
    "prompt": "Which DeepSeek variant for the heavy writing — Flash or Pro?",
    "help": ("Flash is fast and cheap; Pro is the strongest. "
             "This sets your workhorse model."),
    "kind": "text",
    "storeOn": "pre_presentation_capture.DEEPSEEK_VARIANT",
    "value_labels": {
        "flash": "Flash — fast and cheap",
        "pro": "Pro — strongest",
    },
    "required": False,
    "block_gate": False,
}

#: FIX 61.2: App-facing copy for the OpenRouter model pick (projected from
#: the bank's resource_plan.openrouter_model subfield, like run_mode).
OPENROUTER_MODEL_APP_COPY = {
    "id": "openrouter_model",
    "section": "deck-intake",
    "order": 11.7,
    "prompt": "Which OpenRouter model should Ultra use? (e.g. z-ai/glm-5.3-flash)",
    "help": ("In Ultra mode this model replaces any Ollama-routed step. "
             "Free text — paste any OpenRouter model id."),
    "kind": "text",
    "storeOn": "pre_presentation_capture.OPENROUTER_MODEL",
    "required": False,
    "block_gate": False,
}

#: Used ONLY when the canonical bank is unreachable (the standalone app
#: checkout). A mirror, and test_payload.py fails if it drifts from the bank.
RUN_MODE_FALLBACK_VOCABULARY = {
    "allowed_values": ["ultra", "standard", "economy"],
    "default": "",
    "refuse_values": ["quick", "in-depth", "in_depth", "indepth"],
    "refuse_message": (
        "run mode got interview-depth vocabulary {value}. The RUN-MODE axis "
        "(FIX 11) is ultra|standard|economy and decides how the deck is BUILT "
        "(concurrency, ceiling, model mix); the INTERVIEW-DEPTH axis (FIX "
        "30/36 standard_mode, --intake-depth) is quick|in-depth and decides "
        "how much of this interview you are asked. The two axes are never "
        "interchangeable and never share a slot."),
}


def _project_run_mode_question(pool: list) -> dict:
    """Project the bank's resource_plan.run_mode SUBFIELD into a standalone
    app question.

    FIX 11 wired the run mode through the bank, deck-intake-driver.py and
    presentation-intake-poll.sh, but the hosted app had no run-mode handling of
    any kind -- so a client using it could not declare one, and every hosted
    run executed standard while every surface reported success. This is the
    question that closes it.

    It is a projection, not a new question: the vocabulary, the refused
    interview-depth words and the refusal message are read from the bank
    subfield -- the source of truth -- so the two paths can never disagree
    about what a legal run mode is. Only the client-facing sentence is the
    app's (RUN_MODE_APP_COPY). When the bank is unreachable the mirrored
    fallback is used; test_payload.py pins the two together.
    """
    q = dict(RUN_MODE_APP_COPY)
    ann = {}
    for row in pool:
        if row.get("id") == RUN_MODE_BANK_QUESTION:
            ann = (row.get("subfields") or {}).get(RUN_MODE_BANK_SUBFIELD) or {}
            break
    if ann.get("enum"):
        q["allowed_values"] = [str(v).strip().lower() for v in ann["enum"]]
        q["default"] = ann.get("default", "")
        q["refuse_values"] = list(ann.get("refuse_values") or [])
        q["refuse_message"] = ann.get("refuse_message") or ""
    else:
        q.update(RUN_MODE_FALLBACK_VOCABULARY)
    return q


APP_ONLY_QUESTIONS = {
    "image_links": {
        "id": "image_links",
        "section": "deck-intake",
        "order": 6,
        "prompt": "Paste any image links you want used in the deck. (Optional — add up to 5.)",
        "help": "Product photos, headshots, brand imagery. We source images through the approved image pipeline; links here are used as grounded references.",
        "kind": "image_links",
        "storeOn": "deck_brief.IMAGE_LINKS",
        "required": False,
        "block_gate": False,
        "default": [],
    },
}



def _project_subfield_question(pool: list, app_copy: dict, subfield: str) -> dict:
    """Project a bank resource_plan SUBFIELD into a standalone app question.

    FIX 61.2: generic version of _project_run_mode_question for the model-pick
    subfields (deepseek_variant, openrouter_model). The vocabulary comes from
    the bank subfield; only the client-facing copy is the app's.
    """
    q = dict(app_copy)
    ann = {}
    for row in pool:
        if row.get("id") == "resource_plan":
            ann = (row.get("subfields") or {}).get(subfield) or {}
            break
    if ann.get("enum"):
        q["allowed_values"] = [str(v).strip().lower() for v in ann["enum"]]
        q["default"] = ann.get("default", "")
    return q

def _project_question(q: dict) -> dict:
    out = {}
    for k in _PASSTHROUGH:
        if k in q and q[k] is not None:
            out[k] = q[k]
    out.setdefault("kind", "text")
    out.setdefault("required", True)
    return out


def load_specs(root: pathlib.Path) -> tuple[dict, dict, dict | None]:
    """Load the canonical deck-intake + upsell question specs from the repo.

    Returns (merged_spec, empty_spec, store_target). The storeTarget table maps
    short field keys (e.g. "OFFER_NAME") to their qualified intake.json sections
    (e.g. "deck_brief.OFFER_NAME").

    Fallback: when the repo tree is not reachable (e.g. running from the
    standalone app checkout), the app's own questions.json snapshot is used —
    it is generated FROM these canonical files, so it is a valid source.
    """
    intake_dir = (root / "23-ai-workforce-blueprint" / "templates" / "role-library"
                  / "presentations" / "intake")
    standard = intake_dir / "deck-intake-questions.json"
    upsell = intake_dir / "upsell-questions.json"
    merged: dict = {"questions": []}
    store_target: dict | None = None
    if standard.is_file():
        spec = json.loads(standard.read_text(encoding="utf-8"))
        merged["questions"] = spec.get("questions", [])
        store_target = spec.get("storeTarget")
    if upsell.is_file():
        merged["questions"] += json.loads(upsell.read_text(encoding="utf-8")).get("questions", [])
    else:
        # Fallback snapshot (app checkout): pages/questions.json is the curated
        # projection of the canonical files. When root is the payload/ dir (the
        # standalone app layout), the snapshot sits one level up at app/pages.
        for cand in (root / "pages" / "questions.json",
                     root.parent / "pages" / "questions.json",
                     root.parent / "questions.json"):
            if not merged["questions"] and cand.is_file():
                merged["questions"] = json.loads(cand.read_text(encoding="utf-8")).get("questions", [])
                break
    # App-only capture questions (image-link capture) — merged into the pool so
    # the curated set can reference them even when not present in a JSON file.
    merged["questions"] += list(APP_ONLY_QUESTIONS.values())
    return merged, {"questions": merged["questions"]}, store_target


def default_signature_path(root: pathlib.Path) -> pathlib.Path:
    """Skill 51's sp-8-questions.json: the signature set's canonical home."""
    return root / "51-signature-presentation" / "intake" / "sp-8-questions.json"


def load_signature_spec(root: pathlib.Path,
                        sp_file: str | None = None) -> dict | None:
    """Load Skill 51's sp-8-questions.json, or None when it is unreachable.

    The signature set has no curated-id selection and no snapshot fallback:
    it is the whole spec (q1..q8 in the spec's order, plus the
    frame-selection question). None (not an empty spec) signals
    "unreachable", so a signature request against a tree without Skill 51
    fails loudly instead of minting an empty payload, exactly as the
    miniapp builder behaved.
    """
    path = pathlib.Path(sp_file) if sp_file else default_signature_path(root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_signature_payload(run_id: str, signature_spec: dict | None) -> dict:
    """Build the signature payload from Skill 51's sp-8-questions.json.

    Ported from the miniapp builder (FIX-PLAN Item 13, step S8), with that
    builder's behavior as the reference: the eight questions ride in the
    spec's own order and the frame-selection question is appended last.

    The projection is THIS builder's (_project_question), not the
    miniapp's: the fields this app routes on ride through, so each
    question keeps the spec's own storeOn key (q1_title ..
    q8_anything_else, and signature_frame for the frame question). Those
    keys are sp_intake record keys, not deck-intake field keys, so the
    storeTarget table does not qualify them and they are never rewritten;
    spec internals outside the passthrough set (for example q7's note)
    are dropped, as with every other question this builder projects.
    """
    if signature_spec is None:
        raise ValueError("signature set requested but sp-8-questions.json not loaded")
    qs = sorted(signature_spec.get("questions", []),
                key=lambda q: q.get("order", 0))
    questions = [_project_question(q) for q in qs]
    frame = signature_spec.get("frame_selection_question")
    if frame:
        questions.append(_project_question(frame))
    if not questions:
        raise ValueError("no questions produced — check the source JSON")
    return {
        "run_id": run_id,
        "question_set": "signature",
        "source": "sp-8-questions.json",
        "questions": questions,
    }


def build_curated_payload(run_id: str, specs: dict, curated_ids: list[str],
                          store_target: dict | None = None) -> dict:
    by_id = {q.get("id"): q for q in specs.get("questions", [])}
    # FIX 11: run_mode is a PROJECTION of the bank's resource_plan.run_mode
    # subfield (see _project_run_mode_question), not a question row any JSON
    # carries -- so it is built HERE, where every caller passes through, rather
    # than in load_specs, which is only ONE of the ways a pool gets assembled
    # (test_payload.py builds its own from the canonical files). A curated id
    # that resolves on one path and raises on the other is a trap.
    rm_id = RUN_MODE_APP_COPY["id"]
    if rm_id in curated_ids and rm_id not in by_id:
        by_id[rm_id] = _project_run_mode_question(specs.get("questions", []))
    # FIX 61.2/62: project the model-pick subfields, same pattern as run_mode.
    for _copy, _sub in ((DEEPSEEK_VARIANT_APP_COPY, "deepseek_variant"),
                        (OPENROUTER_MODEL_APP_COPY, "openrouter_model"),
                        (OLLAMA_PLAN_APP_COPY, "ollama_plan")):
        _id = _copy["id"]
        if _id in curated_ids and _id not in by_id:
            by_id[_id] = _project_subfield_question(
                specs.get("questions", []), _copy, _sub)
    missing = [i for i in curated_ids if i not in by_id]
    if missing:
        raise ValueError(f"curated ids not found in canonical JSONs: {missing}")
    # Order follows the CURATED list (the app's flow), not raw JSON order — the
    # app asks company/offer → promise → audience → CTA → logo → images → tone →
    # price → speech → sales/checkout → VSL → extras.
    questions = []
    for i in curated_ids:
        q = _project_question(by_id[i])
        # Qualify storeOn via the canonical storeTarget table
        # (e.g. "OFFER_NAME" -> "deck_brief.OFFER_NAME") so the frontend can
        # route each answer into the right intake.json section.
        so = q.get("storeOn")
        if so and store_target and so in store_target:
            q["storeOn"] = store_target[so]
        questions.append(q)
    return {
        "run_id": run_id,
        "question_set": "standard",
        "source": "deck-intake-questions.json + upsell-questions.json (curated)",
        "questions": questions,
    }


def selftest() -> int:
    root = _project_root(pathlib.Path(__file__).parent)
    ok = True
    specs, _, store_target = load_specs(root)
    if specs.get("questions"):
        payload = build_curated_payload("RUNTEST", specs, DEFAULT_CURATED, store_target)
        ids = [q["id"] for q in payload["questions"]]
        # Cap 21 binds the set WITHOUT the declined-reason waiver follow-ups.
        # A waiver follow-up rides on its toggle (asked only on a "no") and
        # is pinned individually below instead of counted against the cap.
        # (Other conditional questions, e.g. the pitch_included pair, are
        # ordinary curated questions and stay inside the count, as before.)
        waiver_followups = [q for q in payload["questions"]
                            if q["id"].endswith("_declined_reason")]
        assert len(ids) - len(waiver_followups) <= 21, \
            "curated set must respect cap 21 (excluding waiver follow-ups)"
        for q in waiver_followups:
            assert q.get("conditional_on", {}).get("equals") == "no", q
            assert str(q.get("storeOn", "")).startswith("pre_presentation_capture."), q
            assert q.get("required") is True, q
        assert len(ids) >= 7, "curated set must keep 7-9 core"
        assert ids[0] == "presentation_type", "first standard question must be the type-picker (presentation_type)"
        assert "speech_speed_preference" in ids, "speech-speed question must be included"
        assert "want_sales_checkout" in ids, "sales/checkout yes-no must be included"
        assert "want_vsl_page" in ids, "VSL yes-no must be included"
        # FIX-PLAN Item 12: the hosted payload must ASK both declined-reason
        # questions, conditional on a "no", storing to the canonical nested
        # location the builder gates read first. Without these, the verbatim
        # waiver was unobtainable on the hosted path.
        for _rid, _toggle, _field in (
                ("sales_checkout_declined_reason", "want_sales_checkout",
                 "SALES_CHECKOUT_DECLINED_REASON"),
                ("vsl_page_declined_reason", "want_vsl_page",
                 "VSL_PAGE_DECLINED_REASON")):
            assert _rid in ids, f"U026 declined-reason question {_rid} must be included"
            _q = next(q for q in payload["questions"] if q["id"] == _rid)
            assert _q.get("conditional_on") == {"id": _toggle, "equals": "no"}, _q
            assert _q.get("storeOn") == f"pre_presentation_capture.{_field}", _q
            assert _q.get("required") is True, _q
        assert "want_email_sequences" in ids, "Skill 50 email election yes-no must be included"
        em = next(q for q in payload["questions"] if q["id"] == "want_email_sequences")
        assert em.get("storeOn") == "pre_presentation_capture.WANT_EMAIL_SEQUENCES", f"email toggle storeOn not qualified: {em.get('storeOn')}"
        assert em.get("default") == "no", "the email election defaults to NO (opt-in only)"
        emr = next(q for q in payload["questions"] if q["id"] == "email_sequences_declined_reason")
        assert emr.get("storeOn") == "pre_presentation_capture.EMAIL_SEQUENCES_DECLINED_REASON", f"email reason storeOn not qualified: {emr.get('storeOn')}"
        assert emr.get("conditional_on") == {"id": "want_email_sequences", "equals": "no"}, emr
        assert "want_motion_graphics" in ids, "Item 34 motion election yes-no must be included"
        mg = next(q for q in payload["questions"] if q["id"] == "want_motion_graphics")
        assert mg.get("storeOn") == "pre_presentation_capture.WANT_MOTION_GRAPHICS", f"motion toggle storeOn not qualified: {mg.get('storeOn')}"
        assert mg.get("default") == "no", "the motion election defaults to NO (opt-in only)"
        mgr = next(q for q in payload["questions"] if q["id"] == "motion_graphics_declined_reason")
        assert mgr.get("storeOn") == "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON", f"motion reason storeOn not qualified: {mgr.get('storeOn')}"
        assert mgr.get("conditional_on") == {"id": "want_motion_graphics", "equals": "no"}, mgr
        assert "run_mode" in ids, "FIX 11 run-mode question must be included"
        rm = next(q for q in payload["questions"] if q["id"] == "run_mode")
        assert rm["allowed_values"] == ["ultra", "standard", "economy"], rm
        assert rm.get("default") == "", "undeclared is undeclared, never ultra"
        assert "quick" in [str(v).lower() for v in rm.get("refuse_values", [])]
        assert all("prompt" in q and q["prompt"] for q in payload["questions"]), "every question needs a prompt"
        offer = next(q for q in payload["questions"] if q["id"] == "offer_name")
        assert offer.get("storeOn") == "deck_brief.OFFER_NAME", f"offer storeOn not qualified: {offer.get('storeOn')}"
        print(f"[selftest] curated OK: {len(ids)} questions ({ids})")
    else:
        print("[selftest] SKIP curated (canonical JSONs not found)", file=sys.stderr)
    sig_spec = load_signature_spec(root)
    if sig_spec is not None:
        sig_payload = build_signature_payload("RUNTEST", sig_spec)
        sids = [q["id"] for q in sig_payload["questions"]]
        assert sids[:8] == [f"q{i}" for i in range(1, 9)], sids
        assert sids[-1] == "frame_selection", sids
        assert len(sids) == 9, f"signature payload should have 9 questions, got {len(sids)}"
        assert all("prompt" in q and q["prompt"] for q in sig_payload["questions"]), "every signature question needs a prompt"
        frame_q = sig_payload["questions"][-1]
        assert frame_q.get("allowed_values") == ["rulebook", "vault", "quest", "original"], frame_q
        assert frame_q.get("storeOn") == "signature_frame", frame_q
        print(f"[selftest] signature OK: {len(sids)} questions ({sids})")
    else:
        print("[selftest] SKIP signature (sp-8-questions.json not found)", file=sys.stderr)
    print("[selftest] PASS" if ok else "[selftest] FAIL")
    return 0 if ok else 1


def _project_root(start: pathlib.Path) -> pathlib.Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "23-ai-workforce-blueprint").is_dir():
            return parent
    return start


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--set", dest="qset", choices=["standard", "signature"],
                    default="standard",
                    help="question set to build (default standard, the curated "
                         "set; signature is Skill 51's SACRED 8 from "
                         "sp-8-questions.json, ported in FIX-PLAN Item 13 S8)")
    ap.add_argument("--questions", default=",".join(DEFAULT_CURATED), help="comma-separated curated ids (standard set only)")
    ap.add_argument("--sp-file", default=None, help="override path to sp-8-questions.json (signature set only)")
    ap.add_argument("--out", default=None, help="write payload here (default stdout)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.run_id:
        print("error: --run-id is required", file=sys.stderr)
        return 2
    root = _project_root(pathlib.Path(__file__).parent)
    if args.qset == "signature":
        sig_spec = load_signature_spec(root, args.sp_file)
        if sig_spec is None:
            where = args.sp_file or default_signature_path(root)
            print(f"error: cannot find sp-8-questions.json at {where}", file=sys.stderr)
            return 3
        payload = build_signature_payload(args.run_id, sig_spec)
    else:
        specs, _, store_target = load_specs(root)
        curated = [x.strip() for x in args.questions.split(",") if x.strip()]
        payload = build_curated_payload(args.run_id, specs, curated, store_target)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(payload['questions'])} questions)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
