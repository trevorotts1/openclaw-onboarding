#!/usr/bin/env python3
"""F15 (Critical, owner order 2026-10-08): the four choices are always asked
before launch, in plain words -- and no paid job starts on an unanswered card.

Proves, behaviourally (manual 02-FIX-AND-IMPROVE-MANUAL.md F15 + ADDENDUM 4):

  * card_gate: a card missing any answer -> CARD_UNANSWERED listing that
    field; all four answered -> stamped receipt with a UTC 'at';
  * a brief-launched run (complete brief, zero intake questions, and the
    resume-no-changes path) without card answers refuses paid dispatch:
    intake pauses with CARD_UNANSWERED, preflight refuses, kie_dispatch
    refuses -- fail-closed;
  * the length menu contains 60/90/120/180/300/600, 2 minutes placed
    between 90 s and 3 minutes, with the owner's F15 note;
  * the 2-minute price rows derive from the SAME rate the 90 s rows use:
    every 2-minute figure is recomputed in this test from the published
    "Rates used" rates and must equal the printed table exactly.

Run: python3 scripts/core/style_defaults/test_card_gate_f15.py
stdlib only; no network, no provider, $0 spend.
"""
import json
import math
import re
import subprocess
import sys
import tempfile
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent                                       # scripts/core/
SKILL = CORE.parent.parent                               # 75-drama-song-ad-factory/
PRICE_MENU = SKILL / "references" / "price-menu.md"
sys.path.insert(0, str(CORE))                            # core/ on path
sys.path.insert(0, str(CORE / "kie_dispatch"))           # kie_dispatch.py
sys.path.insert(0, str(CORE / "intake_preflight"))       # intake.py / preflight.py

from style_defaults import card_gate as CG                # noqa: E402
from style_defaults import defaults as D                  # noqa: E402
from style_defaults import answers_recorded, answered_stamped, CardGateError  # noqa: E402

import kie_dispatch as KD                                 # noqa: E402
import intake as I                                        # noqa: E402
import preflight as P                                     # noqa: E402

FACTORY = SKILL / "scripts" / "core" / "intake_preflight" / "factory.py"

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

ANSWERS = {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
           "length": 120, "video_model": "MiniMax H3 768P"}

# ------------------------------------------------------------- gate --------

def test_missing_any_answer_lists_field():
    for f in CG.CARD_REQUIRED_FIELDS:
        card = {k: v for k, v in ANSWERS.items() if k != f}
        ok, refusal = answers_recorded(card)
        check("missing %s -> refused" % f, ok is None and
              refusal["reason_code"] == "CARD_UNANSWERED", repr(refusal))
        check("refusal lists %s" % f,
              refusal["missing"] == [f], repr(refusal["missing"]))
    ok, refusal = answers_recorded(None)
    check("no card at all -> CARD_UNANSWERED with all four fields",
          ok is None and refusal["missing"] == list(CG.CARD_REQUIRED_FIELDS),
          repr(refusal))
    # the plain refusal spellings never pass
    blanks = {"video_style": "", "audio_style": "none",
              "length": "no choice", "video_model": "unanswered"}
    ok, refusal = answers_recorded(blanks)
    check("blank/refusal spellings -> CARD_UNANSWERED",
          ok is None and refusal["reason_code"] == "CARD_UNANSWERED",
          repr(refusal))

def test_stamped_receipt_utc():
    when = datetime(2026, 10, 8, 14, 30, 5, tzinfo=timezone.utc)
    receipt = answered_stamped(ANSWERS, "Trevor Otts", when)
    check("receipt keys answers/who/at",
          set(receipt) == {"answers", "who", "at"}, repr(receipt))
    check("answers carried verbatim", receipt["answers"] == ANSWERS,
          repr(receipt["answers"]))
    check("who recorded", receipt["who"] == "Trevor Otts", receipt["who"])
    check("at is UTC 'Z' stamp", receipt["at"] == "2026-10-08T14:30:05Z",
          receipt["at"])
    receipt2 = answered_stamped(ANSWERS, "Trevor Otts",
                                datetime(2026, 10, 8, 9, 0, 0))  # naive -> UTC
    check("naive when stamped as UTC", receipt2["at"] == "2026-10-08T09:00:00Z",
          receipt2["at"])
    receipt3 = answered_stamped(ANSWERS, "Trevor Otts", 1780776000)
    check("epoch seconds stamped in UTC", receipt3["at"].endswith("Z")
          and len(receipt3["at"]) == 20, receipt3["at"])
    try:
        answered_stamped({"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                          "length": 60}, "Trevor", datetime.now(timezone.utc))
        check("stamped refuses an unanswered card", False, "no refusal raised")
    except CardGateError as e:
        check("stamped refuses an unanswered card",
              e.code == "CARD_UNANSWERED", str(e))

# ------------------------------------------- gate through the dispatchers --

BRIEF = {"schema_version": "blackceo.campaign/v1",
         "offer": "The 90-Day Mind Reset book, https://example.test",
         "audience": "Women 35-55 rebuilding after a setback",
         "action": "Buy the book at the link",
         "budget_minor": 2500, "budget_currency": "credits",
         "assets": "https://example.test/cover.jpg",
         "placement": "9:16, 60 seconds"}

def test_intake_complete_brief_still_waits_on_card():
    # A brief that answers all three story questions still does not launch:
    # with zero questions left the F15 card gate turns the 'ok' into a
    # CARD_UNANSWERED wait.
    r = I.evaluate(dict(BRIEF), {})
    check("complete brief with no card -> waiting (F15 gate, not complete)",
          r.get("outcome") == "waiting" and r.get("reason_code") == "CARD_UNANSWERED",
          "%s/%s" % (r.get("outcome"), r.get("reason_code")))
    check("gate names the card next-action",
          r.get("next_action") == CG.CARD_NEXT_ACTION,
          repr(r.get("next_action")))
    qs = [q["id"] for q in r.get("questions") or []]
    check("no intake questions asked (brief is complete)", qs == [], repr(qs))
    # and no paid-work go: outcome is never 'ok'
    check("outcome never 'ok'", r.get("outcome") != "ok", r.get("outcome"))
    # a thin brief still asks its <=3 story questions first (24.3: the cap
    # is about the story questions; the card comes at approval)
    thin = I.evaluate({"offer": "A candle shop"}, {})
    ids = [q["id"] for q in thin.get("questions") or []]
    check("thin brief still asked the bundled questions",
          thin.get("reason_code") == "missing-essentials" and ids,
          "%s/%s %s" % (thin.get("outcome"), thin.get("reason_code"), ids))

def test_intake_resume_without_card_waits():
    # Same-digest resume, no outstanding decisions, no card: the F15 gate
    # turns what was 'ok' into a CARD_UNANSWERED wait.
    fields, prov = I.normalize(dict(BRIEF), {})
    summary, digest = I.summarize(fields)
    r = I.evaluate(dict(BRIEF), {}, resume_state={
        "digest": digest, "summary": summary, "outstanding": []})
    check("resume-no-changes path gated without card",
          r.get("outcome") == "waiting" and r.get("reason_code") == "CARD_UNANSWERED",
          "%s/%s" % (r.get("outcome"), r.get("reason_code")))
    # same digest with an outstanding decision waits on those decisions
    # (card or not) -- a resume never re-asks the card inside this path
    r2 = I.evaluate(dict(BRIEF), {}, resume_state={
        "digest": digest, "summary": summary, "outstanding": ["Pick the look"]})
    check("outstanding path stays waiting",
          r2.get("outcome") == "waiting"
          and r2.get("reason_code") == "resume-outstanding-decisions",
          "%s/%s" % (r2.get("outcome"), r2.get("reason_code")))

def test_intake_with_recorded_card_proceeds():
    # A resume with the SAME digest and no outstanding decisions, plus the
    # recorded card, proceeds (resume-no-changes); without the card it waits.
    fields, prov = I.normalize(dict(BRIEF), {})
    summary, digest = I.summarize(fields)
    stamped = CG.answered_stamped(ANSWERS, "Trevor", datetime.now(timezone.utc))
    r = I.evaluate(dict(BRIEF), {}, resume_state={
        "digest": digest, "summary": summary, "outstanding": [],
        "card_receipt": stamped})
    check("recorded card + no changes -> intake proceeds",
          r.get("reason_code") == "resume-no-changes",
          repr(r.get("reason_code")))
    r2 = I.evaluate(dict(BRIEF), {}, resume_state={
        "digest": digest, "summary": summary, "outstanding": []})
    check("same resume without card -> CARD_UNANSWERED",
          r2.get("reason_code") == "CARD_UNANSWERED",
          repr(r2.get("reason_code")))

def test_preflight_refuses_paid_work_without_card():
    r = P.check({"profile": "drama-9x16-60s", "auth": {"scope": "campaign"},
                 "summary_digest": "t", "run_state": {}})
    check("preflight paid check without card -> CARD_UNANSWERED",
          r.get("reason_code") == "CARD_UNANSWERED", repr(r.get("reason_code")))
    check("preflight refusal names missing fields",
          sorted(r.get("missing") or []) == sorted(CG.CARD_REQUIRED_FIELDS),
          repr(r.get("missing")))
    r2 = P.check({"profile": "drama-9x16-60s", "auth": {"scope": "campaign"},
                  "summary_digest": "t",
                  "card_receipt": CG.answered_stamped(
                      ANSWERS, "Trevor", datetime.now(timezone.utc))})
    check("preflight with recorded card passes",
          r2.get("outcome") == "ok", "%s/%s" % (r2.get("outcome"),
                                                r2.get("reason_code")))

def test_dispatch_refuses_paid_job_without_card():
    env = KD.dispatch(model="minimax/h3-768p", request={}, save_dir="/tmp",
                      ledger_db=":memory:", run_id="f15t", logical_key="k",
                      attempt_id="a", estimated_cost=100,
                      runner=lambda *a, **k: (1, None, "unused"))
    check("dispatch refuses paid job: CARD_UNANSWERED",
          env.get("reason_code") == "CARD_UNANSWERED", repr(env.get("reason_code")))
    check("dispatch outcome waiting, nothing reserved",
          env.get("outcome") == "waiting", repr(env.get("outcome")))
    check("generated is False",
          (env.get("evidence") or {}).get("generated") is False,
          repr(env.get("evidence")))

def test_cli_preflight_gated():
    with tempfile.TemporaryDirectory() as tmp:
        auth = os.path.join(tmp, "auth.json")
        with open(auth, "w", encoding="utf-8") as fh:
            json.dump({"scope": "campaign"}, fh)
        run = subprocess.run(
            [sys.executable, str(FACTORY), "preflight", "--root", tmp,
             "--storage-dir", tmp, "--profile", "drama-9x16-60s",
             "--auth-file", auth, "--summary-digest", "t"],
            capture_output=True, text=True)
        env = json.loads(run.stdout)
        check("CLI preflight without card -> CARD_UNANSWERED",
              env.get("reason_code") == "CARD_UNANSWERED",
              "%s (exit %s, stderr %s)" % (env.get("reason_code"),
                                           run.returncode,
                                           run.stderr.strip()[:160]))
        receipt = os.path.join(tmp, "card.json")
        with open(receipt, "w", encoding="utf-8") as fh:
            json.dump(CG.answered_stamped(ANSWERS, "Trevor",
                                          datetime.now(timezone.utc)), fh)
        run2 = subprocess.run(
            [sys.executable, str(FACTORY), "preflight", "--root", tmp,
             "--storage-dir", tmp, "--profile", "drama-9x16-60s",
             "--auth-file", auth, "--summary-digest", "t",
             "--card-receipt-file", receipt],
            capture_output=True, text=True)
        env2 = json.loads(run2.stdout)
        check("CLI preflight with recorded card passes",
              env2.get("outcome") == "ok" and env2.get("reason_code") == "preflight-pass",
              "%s/%s" % (env2.get("outcome"), env2.get("reason_code")))

# ------------------------------------------------------- length menu -------

def test_length_menu_six_values():
    check("length options exactly 60/90/120/180/300/600",
          D.LENGTH_OPTIONS_S == (60, 90, 120, 180, 300, 600),
          repr(D.LENGTH_OPTIONS_S))
    check("2 minutes sits between 90 s and 3 minutes",
          D.LENGTH_OPTIONS_S.index(120) == D.LENGTH_OPTIONS_S.index(90) + 1
          and D.LENGTH_OPTIONS_S.index(180) == D.LENGTH_OPTIONS_S.index(120) + 1,
          repr(D.LENGTH_OPTIONS_S))
    gate_lines = CG.length_picks()
    two = [l for l in gate_lines if l.startswith("2 minutes")]
    check("card length menu offers 2 minutes", len(two) == 1, repr(gate_lines))
    check("2-minute line carries the F15 note",
          two and CG.LENGTH_MENU_NOTE in two[0], repr(two))
    check("60 s marked RECOMMENDED",
          any(l.startswith("60 seconds (RECOMMENDED)") for l in gate_lines),
          repr(gate_lines))

def test_price_menu_has_2minute_section():
    text = PRICE_MENU.read_text(encoding="utf-8")
    check("price-menu has '### 2 minutes'", "### 2 minutes" in text, "")
    check("price-menu carries the F15 note",
          "2 minutes is new, added by F15" in text
          or "New (F15, owner order 2026-10-08)" in text, "")
    data = CG.parse_price_menu(text)
    rows = data.get("2 minutes") or []
    check("2-minute table parsed with 18 model rows", len(rows) == 18,
          str(len(rows)))

# ------------------------------------- 2-minute rows derive from 90 s rate --

def _recompute(kind, rate, res):
    """Same published formula every table uses (menu's own assumptions):
    per-second models: 120 s x rate; Veo: ceil(120/8) clips x clip price;
    Gemini: ceil(120/10) clips; keyframes = shots x $0.02; one Suno V6
    generation $0.06; both shapes doubles video+keyframes, music once;
    retakes = 20% of one shape's video+keyframes."""
    if kind == "veo":
        shots = math.ceil(120 / 8); video = shots * rate
    elif kind == "gemi":
        shots = math.ceil(120 / 10); video = shots * rate
    else:
        shots = math.ceil(120 / 15); video = 120 * rate
    kf = shots * 0.02
    return (round(video + kf + 0.06, 2), round(2 * video + 2 * kf + 0.06, 2),
            round(0.2 * (video + kf), 2), shots)

def test_2min_rows_equal_90s_rate_derivation():
    text = PRICE_MENU.read_text(encoding="utf-8")
    rates = {"Veo 3.1 Fast 720p": ("veo", 0.30), "Veo 3.1 Fast 1080p": ("veo", 0.325),
             "Veo 3.1 Quality 720p": ("veo", 1.25), "Veo 3.1 Quality 1080p": ("veo", 1.275),
             "HappyHorse 1.1 720p": ("ps", 0.1125), "HappyHorse 1.1 1080p": ("ps", 0.145),
             "MiniMax H3 768P": ("ps", 0.04), "MiniMax H3 2K": ("ps", 0.065),
             "Kling 3.0 Omni 720p": ("ps", 0.07), "Kling 3.0 Omni 1080p": ("ps", 0.09),
             "Gemini Omni Flash 1.1": ("gemi", 0.63),
             "Seedance 2.5 720p": ("ps", 0.315), "Seedance 2.5 1080p": ("ps", 0.79),
             "Wan 3.0 720p": ("ps", 0.08), "Wan 3.0 1080p": ("ps", 0.16),
             "Kling 3.0 720p": ("ps", 0.07), "Kling 3.0 1080p": ("ps", 0.09),
             "Seedance 2.0 Mini 720p": ("ps", 0.041)}
    resmap = {"MiniMax H3 768P": "768P (no 720p)", "MiniMax H3 2K": "2K (no 1080p)",
              "Gemini Omni Flash 1.1": "720p and 1080p (same price)",
              "Seedance 2.5 720p": "720p", "Seedance 2.5 1080p": "1080p",
              "Veo 3.1 Fast 720p": "720p", "Veo 3.1 Fast 1080p": "1080p",
              "Veo 3.1 Quality 720p": "720p", "Veo 3.1 Quality 1080p": "1080p",
              "HappyHorse 1.1 720p": "720p", "HappyHorse 1.1 1080p": "1080p",
              "Kling 3.0 Omni 720p": "720p", "Kling 3.0 Omni 1080p": "1080p",
              "Wan 3.0 720p": "720p", "Wan 3.0 1080p": "1080p",
              "Kling 3.0 720p": "720p (std)", "Kling 3.0 1080p": "1080p (pro)",
              "Seedance 2.0 Mini 720p": "720p (no 1080p)"}
    data = CG.parse_price_menu(text)
    got2 = {((r["model"]) + " " + r["resolution"].split(" (")[0] if r["model"] != "Gemini Omni Flash 1.1"
             else r["model"]): r for r in data["2 minutes"]}
    bad = []
    for key, (kind, rate) in rates.items():
        want_one, want_both, want_ret, want_shots = _recompute(kind, rate, None)
        row = got2.get(key)
        if row is None:
            bad.append("%s: row missing from 2-minute table" % key)
            continue
        if (row["one_shape"], row["both_shapes"], row["retakes"]) != (want_one, want_both, want_ret):
            bad.append("%s: printed (%.2f, %.2f, +%.2f) != derived (%.2f, %.2f, +%.2f)"
                       % (key, row["one_shape"], row["both_shapes"], row["retakes"],
                          want_one, want_both, want_ret))
        if row["shots"] != want_shots:
            bad.append("%s: shots %s != %d" % (key, row["shots"], want_shots))
        if row["resolution"] != resmap.get(key):
            bad.append("%s: resolution %r != %r" % (key, row["resolution"], resmap.get(key)))
    check("every 2-minute row derives from the SAME rate the 90 s rows use",
          not bad, "; ".join(bad[:4]))
    # spot proof against the 90-second table itself: 90 s MiniMax = $3.78
    # derives from the same $0.04/s: 90*0.04 + 6*0.02 + 0.06 = 3.78
    mm90 = [r for r in data["90 seconds"]
            if r["model"] == "MiniMax H3" and r["resolution"].startswith("768P")][0]
    derived90 = round(90 * 0.04 + 6 * 0.02 + 0.06, 2)
    check("90 s rate rule reproduced ($3.78 from $0.04/s)",
          mm90["one_shape"] == derived90 == 3.78,
          "%s vs %.2f" % (mm90["one_shape"], derived90))
    mm2 = [r for r in data["2 minutes"]
           if r["model"] == "MiniMax H3" and r["resolution"].startswith("768P")][0]
    derived2 = round(120 * 0.04 + 8 * 0.02 + 0.06, 2)
    check("2-minute MiniMax row derives from the SAME $0.04/s rate ($5.02)",
          mm2["one_shape"] == derived2 == 5.02,
          "%s vs %.2f" % (mm2["one_shape"], derived2))
    check("2-minute and 90-second MiniMax share one rate (120/90 x base)",
          abs(mm2["one_shape"] - derived2) < 0.005
          and abs(mm90["one_shape"] - derived90) < 0.005
          and round((derived2 - 0.06) / (derived90 - 0.06), 4) == round(120 / 90, 4),
          "%.4f != 1.3333" % ((derived2 - 0.06) / (derived90 - 0.06)))

# -------------------------------------------------------- card render ------

def test_card_renders_plain_sentences_and_recommended():
    card = CG.render_card()
    vs = card["video_style"]
    check("five looks, one plain line each", len(vs) == 5, repr(vs))
    check("every video-style line ends with a period",
          all(l.rstrip().endswith(".") for l in vs), repr(vs))
    check("Lifelike 3D shown RECOMMENDED",
          vs[0].startswith("Lifelike 3D (RECOMMENDED) = "), repr(vs[0]))
    au = card["audio_style"]
    check("three music styles, one plain line each", len(au) == 3, repr(au))
    check("Soul Rise line is a plain 'sounds like' sentence",
          au[2].startswith("Soul Rise = ") and au[2].rstrip().endswith(".")
          and "upbeat" in au[2], repr(au[2]))
    check("Soul Ballad shown RECOMMENDED",
          au[0].startswith("Soul Ballad (RECOMMENDED) = "), repr(au[0]))
    vm = card["video_model"]
    check("video-model menu lists every approved model for 60 seconds",
          len(vm) == 18, repr(vm))
    check("MiniMax H3 768P line marked RECOMMENDED",
          any(l.startswith("MiniMax H3") and "(RECOMMENDED)" in l
              and "768P" in l for l in vm), repr(vm[6]))
    check("every model line carries a price and one plain sentence",
          all("$" in l and l.rstrip().endswith(".") for l in vm), repr(vm[:2]))
    check("Seedance 2.5 1080p PREMIUM marker travels with its line",
          any("Seedance 2.5 (PREMIUM)" in l and "1080p" in l for l in vm),
          repr(vm))
    check("card note records the 24.3 ruling",
          "three-question cap applies to the story questions only"
          in card["note"], repr(card["note"]))

def test_243_note_in_spec():
    spec = (SKILL / "references" / "choice-card-spec.md").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", spec)
    check("choice-card-spec carries the 24.3 conflict note",
          "the card is one step with four picks" in flat
          and "three-question cap applies to the story questions only" in flat, "")
    instr = (SKILL / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    check("INSTRUCTIONS.md:215 no longer says 'from the brief, else 60 seconds'",
          "from the brief, else 60 seconds" not in instr, "")
    check("INSTRUCTIONS length row offers 2 minutes",
          "60 seconds, 90 seconds, 2 minutes, 3 minutes, 5 minutes" in instr, "")

# ---------------------------------------------------------------------------

def main():
    for t in [test_missing_any_answer_lists_field,
              test_stamped_receipt_utc,
              test_intake_complete_brief_still_waits_on_card,
              test_intake_resume_without_card_waits,
              test_intake_with_recorded_card_proceeds,
              test_preflight_refuses_paid_work_without_card,
              test_dispatch_refuses_paid_job_without_card,
              test_cli_preflight_gated,
              test_length_menu_six_values,
              test_price_menu_has_2minute_section,
              test_2min_rows_equal_90s_rate_derivation,
              test_card_renders_plain_sentences_and_recommended,
              test_243_note_in_spec]:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all F15 card-gate tests passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())