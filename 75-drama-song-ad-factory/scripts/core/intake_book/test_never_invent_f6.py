#!/usr/bin/env python3
"""Part F F6 (manual 02, F6, Critical): briefs and orchestrators never invent.

Proves, behaviourally:
  * a brief with an invented style ('upbeat tropical EDM') refuses
    BRIEF_INVENTED_FIELD, naming the field -- the brief compiler runs the
    check where the brief compiles (intake_book.evaluate + the CLI path);
  * the menu's Soul Rise alias passes: 'upbeat' resolves to soul-rise
    (documented alias, manual F6: "upbeat" = the menu's Soul Rise);
  * menu words pass on every menu-typed field: style id, style label,
    look id, look label, every offered length spelling, the D15 share band;
  * invented numbers refuse (77 seconds, an 80% share);
  * invented gates refuse -- including a gate list mixing a real gate with
    a private one an orchestrator could use to skip a real approval;
  * free-text fields are never judged (offer/audience stay free);
  * a run cannot animate before storyboard approval is recorded:
    kie_dispatch.dispatch refuses a video job with no storyboard record
    (STORYBOARD_NOT_APPROVED), refuses one whose shots are not
    storyboard_approved, and a run with approval recorded (14.1 gate open)
    passes the entry check.

Run: python3 core/intake_book/test_never_invent_f6.py
stdlib only, no network, no provider, no paid calls.
"""
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import intake_book as IB                                # noqa: E402
import kie_dispatch as D                                # noqa: E402
import storyboard_director as SD                        # noqa: E402
import spend_ledger as L                                # noqa: E402

KD = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# Part 1: the brief compiler check ----------------------------------------

def test_invented_style_refuses():
    r = IB.reject_any_invented({"style": "upbeat tropical EDM"})
    check("invented style refuses BRIEF_INVENTED_FIELD",
          r is not None and r["reason_code"] == IB.BRIEF_INVENTED_FIELD
          and r["invented_fields"] == ["style"], r)
    # Same verdict through the full compile path: evaluate refuses before it
    # opens a single question.
    env = IB.evaluate({"style": "upbeat tropical EDM",
                       "offer": "Book X by A -- get it at y"})
    check("evaluate refuses the invented brief before questions",
          env["outcome"] == "rejected"
          and env["reason_code"] == "BRIEF_INVENTED_FIELD"
          and not env["questions"], (env["outcome"], env["reason_code"],
                                     len(env["questions"])))
    # And through the CLI envelope (the path an orchestrator actually runs).
    tmp = tempfile.mkdtemp(prefix="f6-cli-")
    bf = os.path.join(tmp, "brief.json")
    with open(bf, "w", encoding="utf-8") as f:
        json.dump({"style": "upbeat tropical EDM",
                   "offer": "Book X by A -- get it at y"}, f)
    cli = os.path.join(CORE, "intake_book", "book.py")
    proc = subprocess.run([sys.executable, cli, "--brief-file", bf,
                           "--run-id", "f6-cli"],
                          capture_output=True, text=True)
    out = json.loads(proc.stdout)
    check("CLI compile refuses with invented_fields in the envelope",
          out["outcome"] == "rejected"
          and out["reason_code"] == "BRIEF_INVENTED_FIELD"
          and out["data"].get("invented_fields") == ["style"],
          (out["outcome"], out["reason_code"]))
    check("CLI exit code is the factory rejected code 4", proc.returncode == 4,
          proc.returncode)


def test_soul_rise_alias_passes():
    r = IB.reject_any_invented({"style": "upbeat"})
    check("documented alias 'upbeat' -> Soul Rise passes the check", r is None,
          r)
    env = IB.evaluate({"style": "upbeat",
                       "offer": "Book X by A -- get it at y"})
    check("alias brief compiles past the F6 check (asks its question)",
          env["reason_code"] != "BRIEF_INVENTED_FIELD"
          and env["outcome"] == "waiting", (env["outcome"],
                                            env["reason_code"]))
    check("alias binds to the menu's soul-rise id",
          IB.STYLE_ALIASES.get("upbeat") == "soul-rise")


def test_menu_values_pass_and_invented_numbers_refuse():
    ok = {"style": ["Soul Rise", "soul-rise", "R&B Flow", "soul-ballad"],
          "look": ["Lifelike 3D", "canvas-to-3d", "Sketch to Life"],
          "length": ["60s", "90", "3m", "600", 180, 90],
          "length_option": [60, 90, 180, 300, 600],
          "target_length_s": [60, 90, 180, 300, 600],
          "spoken_share": [0.40, 0.45, 0.55]}
    for key, values in ok.items():
        for v in values:
            check("menu value passes: %s=%r" % (key, v),
                  IB.reject_any_invented({key: v}) is None,
                  IB.reject_any_invented({key: v}))
    for brief in ({"style": "upbeat tropical EDM"},
                  {"length": 77}, {"length": "77 seconds"},
                  {"length_option": 240}, {"target_length_s": 120},
                  {"spoken_share": 0.80}, {"spoken_share": 10},
                  {"music_style": "lofi chill beats"},
                  {"look": "neon cyberpunk"}):
        r = IB.reject_any_invented(brief)
        check("invented value refuses: %r" % brief, r is not None,
              (r or {}).get("reason_code"))
    check("free-text fields are never judged",
          IB.reject_any_invented({"offer": "Read it tonight",
                                  "audience": "moms who never sleep",
                                  "pain_or_transformation": "peace of mind"}
                                 ) is None)


def test_invented_gates_refuse():
    check("real gate list passes",
          IB.reject_any_invented(
              {"gates": "storyboard approval, adversarial review"}) is None)
    check("one real gate passes", IB.reject_any_invented(
        {"gates": "storyboard approval"}) is None)
    r = IB.reject_any_invented({"gates": "my own early animation gate"})
    check("invented gate refuses", r is not None
          and r["invented_fields"] == ["gates"], r)
    r = IB.reject_any_invented(
        {"gates": "storyboard approval, my own private skip"})
    check("mixed list (real + invented) refuses fail-closed", r is not None,
          r)


# Part 2: no animation before storyboard approval -------------------------

OBJ = [
    "mom closes the laptop and picks up the ringing phone",
    "daughter leaves the exam hall holding the untouched paper",
    "mom reads the daughter note at the kitchen table",
    "mom opens the front door and hugs the daughter",
    "mom presses the book into the daughter hands",
]
LOC = ["kitchen", "exam-hall", "kitchen-table", "front-door", "doorway"]
CAM = ["close-up handheld", "wide static", "over-shoulder pan",
       "medium two-shot", "low-angle push"]


def _shot(idx, obj, vis="background", constraints=()):
    sid = "s%d" % (idx + 1)
    return {"shot_id": sid, "song_start": idx * 8.0,
            "song_end": idx * 8.0 + 8.0, "lyric_line_ids": ["L%s" % sid],
            "story_stage": "opening", "visual_objective": obj,
            "character_ids": ["c1"], "wardrobe_ids": ["blue-top"],
            "location_id": LOC[idx], "product_visibility": vis,
            "camera_direction": CAM[idx], "reference_assets": [],
            "image_model_capability_request": {"capabilities": ["i2v"]},
            "video_model_capability_request": {"capabilities": ["i2v"]},
            "continuity_constraints": list(constraints),
            "negative_constraints": ["no invented text"],
            "cost_estimate": 100, "qc_requirements": ["faces match reference"],
            "status": "storyboard_approved"}


def _contract(i, sid):
    return {"lyric_text": "line %d" % i,
            "viewer_understanding": "she moves from stuck to helped",
            "character_action": "she acts at shot %s" % sid,
            "visible_emotion": "worry lifting to relief",
            "change_from_prior": "prior state changes here",
            "treatment": "literal-repeat", "necessity": "carries the beat"}


def _approved_plan():
    shots = [
        _shot(0, OBJ[0]),
        _shot(1, OBJ[1]),
        _shot(2, OBJ[2]),
        _shot(3, OBJ[3], vis="featured"),
        _shot(4, OBJ[4]),
    ]
    contracts = {s["shot_id"]: _contract(i, s["shot_id"])
                 for i, s in enumerate(shots)}
    review = SD.adversarial_review(shots, contracts,
                                   {"duration_seconds": 45})
    return shots, review


def test_no_approval_refuses_animation():
    shots, review = _approved_plan()
    check("approved fixture passes the 14.1 gate",
          SD.video_spend_allowed(shots, review)["allowed"] is True)

    req = {"model": "kling-v2-video", "request_kind": "video",
           "input": {"prompt": "p" * 200}}

    def _never(*_a, **_k):
        raise AssertionError("no provider call may happen before approval")

    env = KD.dispatch(model="kling-v2-video", request=dict(req),
                      save_dir="/tmp/f6-no-save", ledger_db="/tmp/f6-none.db",
                      run_id="f6-a", logical_key="k", attempt_id="a",
                      estimated_cost=100, runner=_never)
    check("video job with NO storyboard record refuses STORYBOARD_NOT_APPROVED",
          env["outcome"] == "rejected"
          and env["reason_code"] == "STORYBOARD_NOT_APPROVED",
          (env["outcome"], env["reason_code"], env.get("next_action")))

    # Draft (unapproved) shots refuse too.
    drafts = [dict(s, status="draft") for s in shots]
    req2 = dict(req, storyboard={"shots": drafts, "review": review})
    env2 = KD.dispatch(model="kling-v2-video", request=req2,
                       save_dir="/tmp/f6-no-save", ledger_db="/tmp/f6-none.db",
                       run_id="f6-b", logical_key="k", attempt_id="a",
                       estimated_cost=100, runner=_never)
    check("video job with unapproved shots refuses through the 14.1 gate",
          env2["outcome"] == "rejected"
          and env2["reason_code"] == "STORYBOARD_NOT_APPROVED"
          and "storyboard-not-approved"
          in json.dumps(env2.get("evidence") or {}), (env2["outcome"],
                                                      env2["reason_code"]))

    # Failed adversarial review refuses even with approved shots.
    _, review_fail = _approved_plan()
    review_fail["outcome"] = "fail"
    req3 = dict(req, storyboard={"shots": shots, "review": review_fail})
    env3 = KD.dispatch(model="kling-v2-video", request=req3,
                       save_dir="/tmp/f6-no-save", ledger_db="/tmp/f6-none.db",
                       run_id="f6-c", logical_key="k", attempt_id="a",
                       estimated_cost=100, runner=_never)
    check("failed adversarial review still blocks (14.1 gate)",
          env3["outcome"] == "rejected"
          and env3["reason_code"] == "STORYBOARD_NOT_APPROVED",
          (env3["outcome"], env3["reason_code"]))


def test_recorded_approval_passes_entry_check():
    shots, review = _approved_plan()
    ok = KD.check_storyboard_approval(
        None, None, {"model": "kling-v2-video", "request_kind": "video",
                     "storyboard": {"shots": shots, "review": review}})
    check("run with approval recorded passes the entry check", ok is None, ok)


def test_non_video_jobs_untouched():
    check("music job needs no storyboard record",
          KD.check_storyboard_approval(
              None, None, {"model": "suno-v5",
                           "input": {"prompt": "song"}}) is None)
    check("image job needs no storyboard record",
          KD.check_storyboard_approval(
              None, None, {"model": "gpt-image-2-5",
                           "input": {"prompt": "a"}}) is None)


def main():
    test_invented_style_refuses()
    test_soul_rise_alias_passes()
    test_menu_values_pass_and_invented_numbers_refuse()
    test_invented_gates_refuse()
    test_no_approval_refuses_animation()
    test_recorded_approval_passes_entry_check()
    test_non_video_jobs_untouched()
    print("-" * 60)
    if FAILS:
        print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL PASS: F6 never-invent + storyboard approval gate proven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())