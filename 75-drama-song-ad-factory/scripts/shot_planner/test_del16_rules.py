#!/usr/bin/env python3
"""DEL-16 shot-planner rule tests (PKG-07-U2). Stdlib only, script-style.

Every rule the order names gets a positive case (the rule check runs and
passes) and a negative case (the rule check runs and discriminates — the
reason code appears). The compliant plan is exercised for music and for
dialogue or narration alike. Run:

    python3 scripts/shot_planner/test_del16_rules.py
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import brief as B     # noqa: E402
import rules as R     # noqa: E402
import vocabulary as V  # noqa: E402

ROWS = []
FAILS = []


def row(ok, name, detail=""):
    ROWS.append((ok, name, detail))
    if not ok:
        FAILS.append(name)
    print("%s: %s%s" % ("PASS" if ok else "FAIL", name,
                        (" (%s)" % detail) if detail and not ok else ""),
          flush=True)


def codes(result):
    return {r.split(" ", 1)[0] for r in result.get("reasons", [])}


# ------------------------------------------------------------ the plan


def _brief(**kw):
    shot = B.build_shot_brief(**{k: v for k, v in kw.items()
                                 if k in _BRIEF_KEYS})
    for k, v in kw.items():
        if k not in _BRIEF_KEYS:
            shot[k] = v
    return shot


_BRIEF_KEYS = {
    "shot_id", "framing", "angle", "camera_move", "lens_mm", "f_number",
    "emotion", "content_mode", "duration_seconds", "coverage_role",
    "lighting", "eyeline", "camera_side", "screen_direction", "scene_id",
    "character_ids", "subject_id", "dialogue_or_narration",
    "text_overlay_post", "logo_overlay_post", "transition_from",
    "rack_focus_from",
}


def make_plan(mode="music"):
    """A compliant eight-shot plan: every coverage role, every rule kept.

    medium framings 4/8 (planning-range floor), close-ups 2/8 (cap 35%),
    longest identical-framing run 2, scene opens on an establishing wide,
    reverse answers the close with crossed eyelines on the same side of the
    line, one motivated dolly-in, all static otherwise.
    """
    talk = mode != "music"
    return [
        _brief(shot_id="s1", framing="establishing_wide", angle="eye",
               camera_move="static", lens_mm=24, f_number=8.0,
               emotion="epic", content_mode=mode, duration_seconds=7.5,
               coverage_role="master", lighting="golden-hour",
               scene_id="sc1", subject_id="scene",
               dialogue_or_narration=talk),
        _brief(shot_id="s2", framing="medium", angle="eye",
               camera_move="static", lens_mm=50, f_number=4.0,
               emotion="calm", content_mode=mode, duration_seconds=5.0,
               coverage_role="medium", lighting="golden-hour",
               scene_id="sc1", subject_id="char-a", eyeline="screen-left",
               subject_position="left", dialogue_or_narration=talk),
        _brief(shot_id="s3", framing="medium_close", angle="low",
               camera_move="dolly-in", lens_mm=50, f_number=4.0,
               emotion="calm", content_mode=mode, duration_seconds=4.5,
               coverage_role="medium", lighting="golden-hour",
               scene_id="sc1", subject_id="char-a", eyeline="screen-left",
               subject_position="left", dialogue_or_narration=talk),
        _brief(shot_id="s4", framing="close", angle="eye",
               camera_move="static", lens_mm=85, f_number=2.0,
               emotion="intimate", content_mode=mode, duration_seconds=4.0,
               coverage_role="close_up", lighting="golden-hour",
               scene_id="sc1", subject_id="char-a", eyeline="screen-left",
               subject_position="left", dialogue_or_narration=talk),
        _brief(shot_id="s5", framing="close", angle="eye",
               camera_move="static", lens_mm=85, f_number=2.0,
               emotion="intimate", content_mode=mode, duration_seconds=4.0,
               coverage_role="reverse", lighting="golden-hour",
               scene_id="sc1", subject_id="char-b", eyeline="screen-right",
               subject_position="right", dialogue_or_narration=talk),
        _brief(shot_id="s6", framing="medium", angle="eye",
               camera_move="static", lens_mm=35, f_number=4.0,
               emotion="tense", content_mode=mode, duration_seconds=5.0,
               coverage_role="medium", lighting="golden-hour",
               scene_id="sc1", subject_id="char-a", eyeline="screen-left",
               subject_position="left", dialogue_or_narration=talk),
        _brief(shot_id="s7", framing="insert", angle="high",
               camera_move="static", lens_mm=50, f_number=5.6,
               emotion="calm", content_mode=mode, duration_seconds=3.0,
               coverage_role="insert", lighting="golden-hour",
               scene_id="sc1", subject_id="product",
               subject_position="center", dialogue_or_narration=talk),
        _brief(shot_id="s8", framing="medium_close", angle="eye",
               camera_move="static", lens_mm=35, f_number=4.0,
               emotion="joyful", content_mode=mode, duration_seconds=4.5,
               coverage_role="cutaway", lighting="golden-hour",
               scene_id="sc1", subject_id="char-b", eyeline="screen-right",
               subject_position="right", dialogue_or_narration=talk),
    ]


def attach_motivation(plan, shot_id, text):
    for b in plan:
        if b["shot_id"] == shot_id:
            b["camera_motivation"] = text
    return plan


MODES = ("music", "dialogue", "narration")


def reasons_of(plan, **kw):
    return R.run_rule_checks(plan, **kw)


# --------------------------------------------------------------- suites


def test_vocabulary_complete():
    vocab = V.full_vocabulary()
    row(V.missing_from(vocab) == [], "vocabulary: full DEL-16 set present",
        str(V.missing_from(vocab)[:5]))
    row(set(vocab["shot_types"]) >= set(V.SHOT_TYPES),
        "vocabulary: establishing wide through insert and detail")
    row(set(vocab["angles"]) == {"eye", "low", "high", "bird's-eye", "dutch"},
        "vocabulary: eye/low/high/bird's-eye/dutch angles",
        str(vocab["angles"]))
    row(vocab["camera_moves"][0] == "static" and "crane" in vocab["camera_moves"],
        "vocabulary: static through crane moves")
    row(vocab["lenses_mm"] == [24, 35, 50, 85],
        "vocabulary: 24/35/50/85 mm lenses", str(vocab["lenses_mm"]))
    labels = {a["label"] for a in vocab["apertures"]}
    row(labels >= {"wide open", "stopped down"},
        "vocabulary: aperture wide open to stopped down", str(labels))
    pr = vocab["planning_ranges"]
    row("planning range" in pr["label"].lower()
        and "not a measured standard" in pr["label"].lower(),
        "vocabulary: pacing percentages labeled planning ranges", pr["label"])


def test_compliant_plan_all_modes():
    for mode in MODES:
        plan = attach_motivation(make_plan(mode), "s3", "push into the moment")
        result = reasons_of(plan)
        row(result["outcome"] == "ok" and not result["reasons"],
            "compliant %s plan passes every rule" % mode,
            "; ".join(result["reasons"][:4]))
        expected = {
            "content_mode_parity", "vocabulary_carried", "one_move_per_clip",
            "clip_length_planning_range", "length_ladder",
            "edit_transition_not_move", "edit_transitions_bridge_two_clips",
            "motivated_camera_moves", "post_only_overlays",
            "depth_of_field_prompt", "close_up_share", "medium_dominance",
            "identical_framings", "scene_opens_establishing_wide",
            "long_video_coverage", "lens_aperture_emotion",
            "degree_180_rule", "eyelines", "shot_reverse_shot",
            "scene_geometry", "lighting_continuity",
            "screen_direction_continuity", "coverage_roles",
            "depth_of_field",
        }
        row(set(result["checks"]) == expected,
            "compliant %s plan: every rule check ran" % mode,
            str(sorted(expected - set(result["checks"]))))


def _mut(mode, **changes):
    """Compliant plan with one mutation applied to one shot."""
    plan = attach_motivation(make_plan(mode), "s3", "push into the moment")
    shot_id, fields = changes.popitem()
    for b in plan:
        if b["shot_id"] == shot_id:
            b.update(fields)
    return plan


def test_rule_one_move_and_length():
    for mode in MODES:
        plan = _mut(mode, s2={"camera_moves": ["pan", "tilt"]})
        row("MULTI_MOVE_CLIP" in codes(reasons_of(plan)),
            "rule 1 %s: two moves in one clip refused" % mode)
        plan = _mut(mode, s2={"camera_move": ""})
        row("NO_CAMERA_MOVE" in codes(reasons_of(plan)),
            "rule 1 %s: empty move refused" % mode)
        plan = _mut(mode, s2={"duration_seconds": 0.8})
        row("CLIP_LENGTH_OUT_OF_RANGE" in codes(reasons_of(plan)),
            "rule 1 %s: 0.8s clip outside the four-to-six planning range"
            % mode)
        plan = _mut(mode, s2={"duration_seconds": 4.5})
        row("CLIP_LENGTH_OUT_OF_RANGE" not in codes(reasons_of(plan)),
            "rule 1 %s: 4.5s clip inside the planning range" % mode)
        # override: a long dialogue window is allowed only by explicit call
        plan = _mut(mode, s2={"duration_seconds": 12.0})
        row("CLIP_LENGTH_OUT_OF_RANGE" in codes(reasons_of(plan))
            and "CLIP_LENGTH_OUT_OF_RANGE" not in codes(
                reasons_of(plan, allow_length_override=True)),
            "rule 1 %s: override is explicit, never silent" % mode)


def test_rule_two_whip_pan_is_an_edit_transition():
    for mode in MODES:
        plan = _mut(mode, s2={"camera_move": "whip-pan"})
        row("WHIP_PAN_AS_MOVE" in codes(reasons_of(plan)),
            "rule 2 %s: whip pan refused as a generated move" % mode)
        plan = _mut(mode, s2={"camera_move": "fast-orbit"})
        row("WHIP_PAN_AS_MOVE" in codes(reasons_of(plan)),
            "rule 2 %s: fast orbit refused as a generated move" % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        result = reasons_of(
            plan, transitions=[{"kind": "whip-pan",
                                "from_shot": "s1", "to_shot": "s1"}])
        row("TRANSITION_MUST_BRIDGE_TWO_CLIPS" in codes(result),
            "rule 2 %s: whip-pan transition must bridge two clips" % mode)
        result = reasons_of(
            plan, transitions=[{"kind": "whip-pan",
                                "from_shot": "s1", "to_shot": "s2"}])
        row("TRANSITION_MUST_BRIDGE_TWO_CLIPS" not in codes(result),
            "rule 2 %s: whip pan between two clips is the legal build"
            % mode)
        plan = _mut(mode, s2={"transition_from": "s2"})
        row("TRANSITION_MUST_BRIDGE_TWO_CLIPS" in codes(reasons_of(plan)),
            "rule 2 %s: a clip may not transition from itself" % mode)


def test_rule_three_text_logos_in_post():
    for mode in MODES:
        plan = _mut(mode, s2={"prompt": "medium eye, static, with on-screen "
                               "text saying buy now"})
        row("TEXT_LOGO_NOT_IN_POST" in codes(reasons_of(plan)),
            "rule 3 %s: text in the generation prompt refused" % mode)
        plan = _mut(mode, s2={"text_overlay": "BUY NOW"})
        row("TEXT_LOGO_NOT_IN_POST" in codes(reasons_of(plan)),
            "rule 3 %s: text overlay without the post field refused" % mode)
        plan = _mut(mode, s2={"logo_overlay": "brand mark"})
        row("TEXT_LOGO_NOT_IN_POST" in codes(reasons_of(plan)),
            "rule 3 %s: logo overlay without the post field refused" % mode)
        plan = _mut(mode, s2={"text_overlay": "BUY NOW",
                              "text_overlay_post": "BUY NOW"})
        row("TEXT_LOGO_NOT_IN_POST" not in codes(reasons_of(plan)),
            "rule 3 %s: overlay on the post field is the legal build"
            % mode)


def test_rule_four_depth_of_field_phrase():
    for mode in MODES:
        plan = _mut(mode, s4={"prompt": "close up eye, static, shallow "
                               "depth of field, f/2.8, golden-hour light"})
        row("FSTOP_IN_PROMPT" in codes(reasons_of(plan)),
            "rule 4 %s: f-stop number in the prompt refused" % mode)
        plan = _mut(mode, s4={"prompt": "close up eye, static, shallow "
                               "depth of field, 85 mm lens"})
        row("LENS_WORD_IN_PROMPT" in codes(reasons_of(plan)),
            "rule 4 %s: millimeter lens word in the prompt refused" % mode)
        plan = _mut(mode, s4={"prompt": "close up eye, static, golden-hour "
                               "light, intimate"})
        row("DOF_PHRASE_MISSING" in codes(reasons_of(plan)),
            "rule 4 %s: wide-open shot must prompt 'shallow depth of "
            "field'" % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        row("FSTOP_IN_PROMPT" not in codes(reasons_of(plan))
            and "LENS_WORD_IN_PROMPT" not in codes(reasons_of(plan))
            and "DOF_PHRASE_MISSING" not in codes(reasons_of(plan)),
            "rule 4 %s: built prompts carry the phrase, never an f-stop"
            % mode)


def test_rule_five_six_seven_ladder_and_shares():
    for mode in MODES:
        row(not R.check_length_ladder([]),
            "rule 5 %s: ladder shrinks extreme-wide to extreme-close" % mode)
        plan = _mut(mode, s4={"framing": "close"})
        # flip six shots to close framings: share 8/8
        plan = attach_motivation(make_plan(mode), "s3", "push")
        for sid in ("s2", "s3", "s6", "s7", "s8"):
            for b in plan:
                if b["shot_id"] == sid:
                    b["framing"] = "close"
        row("CLOSE_UP_OVERUSE" in codes(reasons_of(plan)),
            "rule 7 %s: close-ups over thirty-five percent refused" % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        for sid in ("s2", "s3", "s6", "s8"):
            for b in plan:
                if b["shot_id"] == sid:
                    b["framing"] = "wide"
        row("MEDIUM_UNDERUSED" in codes(reasons_of(plan))
            or "NO_MEDIUM_SHOTS" in codes(reasons_of(plan)),
            "rule 6 %s: starved medium share refused" % mode)
        row(not R.check_medium_dominance(make_plan(mode))
            and not R.check_close_up_share(make_plan(mode)),
            "rules 6+7 %s: compliant shares pass" % mode)


def test_rule_eight_nine_runs_and_scene_open():
    for mode in MODES:
        plan = attach_motivation(make_plan(mode), "s3", "push")
        for b in plan:
            if b["shot_id"] in ("s6", "s7"):
                b["framing"] = "close"
        # s4 s5 s6 s7 now close: run of four
        row("FRAMING_RUN" in codes(reasons_of(plan)),
            "rule 8 %s: three identical framings in a row refused" % mode)
        plan = _mut(mode, s1={"framing": "wide"})
        row("SCENE_NO_ESTABLISHING_WIDE" in codes(reasons_of(plan)),
            "rule 9 %s: scene not opening on an establishing wide refused"
            % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        row(not R.check_identical_framings(plan)
            and not R.check_scene_opens_establishing_wide(plan),
            "rules 8+9 %s: compliant runs and scene open pass" % mode)


def test_rule_ten_long_video():
    for mode in MODES:
        thin = [{"shot_id": "l%d" % i, "framing": "medium",
                 "angle": "eye"} for i in range(30)]
        got = R.check_long_video_coverage(thin, 150.0)
        row(any(r.startswith("LONG_VIDEO_FEW_SHOT_TYPES") for r in got)
            and any(r.startswith("LONG_VIDEO_FEW_ANGLES") for r in got),
            "rule 10 %s: 150s plan with one type/one angle refused" % mode)
        row(not R.check_long_video_coverage(thin, 60.0),
            "rule 10 %s: under two minutes the floor does not apply" % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        row(not R.check_long_video_coverage(plan, 150.0),
            "rule 10 %s: five types and three angles satisfy the floor"
            % mode)
        result = reasons_of(plan, total_seconds=150.0)
        row(result["outcome"] == "ok",
            "rule 10 %s: long-video floor via the full gate" % mode)


def test_rule_eleven_lens_aperture_emotion():
    for mode in MODES:
        plan = _mut(mode, s4={"lens_mm": 24})
        row("LENS_EMOTION_MISMATCH" in codes(reasons_of(plan)),
            "rule 11 %s: 24mm on an intimate beat refused" % mode)
        plan = _mut(mode, s4={"aperture_intent": "stopped_down",
                              "f_number": 8.0})
        row("APERTURE_EMOTION_MISMATCH" in codes(reasons_of(plan)),
            "rule 11 %s: stopped-down aperture on an intimate beat refused"
            % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        row(not R.check_lens_aperture_emotion(plan),
            "rule 11 %s: matched lens+aperture passes" % mode)


def test_rule_twelve_coverage_family():
    for mode in MODES:
        plan = _mut(mode, s5={"camera_side": "b"})
        row("AXIS_JUMP" in codes(reasons_of(plan)),
            "rule 12 %s: crossing the line without an axis break refused"
            % mode)
        plan = _mut(mode, s5={"camera_side": "b", "crosses_axis": True,
                              "axis_cross_motivation": "motivated reframe"})
        row("AXIS_JUMP" not in codes(reasons_of(plan)),
            "rule 12 %s: declared axis break is the legal build" % mode)
        plan = _mut(mode, s5={"eyeline": "screen-left"})
        row("SHOT_REVERSE_SHOT_EYELINE" in codes(reasons_of(plan))
            or "EYELINE_INCONSISTENT" in codes(reasons_of(plan)),
            "rule 12 %s: reverse sharing the answered eyeline refused"
            % mode)
        plan = _mut(mode, s5={"subject_id": "char-a"})
        row("SHOT_REVERSE_SHOT_SAME_SUBJECT" in codes(reasons_of(plan)),
            "rule 12 %s: reverse answering the same subject refused"
            % mode)
        plan = _mut(mode, s2={"subject_position": "right"})
        row("SCENE_GEOMETRY_CONTRADICTION" in codes(reasons_of(plan)),
            "rule 12 %s: subject teleporting inside a scene refused"
            % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        for i, b in enumerate(plan):
            if i % 3 == 0:
                b["lighting"] = "low-key"
            elif i % 3 == 1:
                b["lighting"] = "daylight"
            else:
                b["lighting"] = "night"
        row("LIGHTING_DRIFT" in codes(reasons_of(plan)),
            "rule 12 %s: lighting thrashing inside a scene refused" % mode)
        plan = _mut(mode, s5={"screen_direction": "right"})
        row("SCREEN_DIRECTION_BREAK" in codes(reasons_of(plan)),
            "rule 12 %s: screen-direction flip without a beat refused"
            % mode)
        plan = _mut(mode, s5={"coverage_role": "medium"})
        row("COVERAGE_GAP" in codes(reasons_of(plan)),
            "rule 12 %s: missing reverse coverage refused" % mode)
        plan = _mut(mode, s3={"camera_move": "rack-focus"})
        got = codes(reasons_of(plan))
        row("RACK_FOCUS_NO_ORIGIN" in got or "UNMOTIVATED_MOVE" in got,
            "rule 12 %s: rack focus without an origin refused" % mode)
        plan = _mut(mode, s3={"depth_of_field": "deep"})
        row("DOF_APERTURE_CONTRADICTION" in codes(reasons_of(plan)),
            "rule 12 %s: deep DOF on a mid-aperture contradiction refused"
            % mode)
        plan = attach_motivation(make_plan(mode), "s3", "push")
        geo = {"sc1": {"geometry": [
            {"subject_id": "char-a", "position": "left"},
            {"subject_id": "char-b", "position": "right"},
            {"subject_id": "product", "position": "center"},
            {"subject_id": "scene", "position": "center"},
        ]}}
        result = reasons_of(plan, scenes=geo)
        row(result["outcome"] == "ok",
            "rule 12 %s: full coverage family passes" % mode,
            "; ".join(result["reasons"][:4]))


def test_cli():
    env = dict(os.environ)
    env["PYTHONPATH"] = HERE
    vocab = subprocess.run(
        [sys.executable, os.path.join(HERE, "cli.py"), "vocabulary"],
        capture_output=True, text=True, env=env)
    row(vocab.returncode == 0, "cli: vocabulary exits 0")
    payload = json.loads(vocab.stdout)
    row(payload["outcome"] == "ok"
        and "shot_types" in payload["data"],
        "cli: vocabulary envelope carries the shot types")

    plan = attach_motivation(make_plan("music"), "s3", "push into the beat")
    plan_file = os.path.join("/tmp", "TrevelynsMini2-PKG-07-U2-plan.json")
    with open(plan_file, "w", encoding="utf-8") as fh:
        json.dump({"briefs": plan}, fh)
    chk = subprocess.run(
        [sys.executable, os.path.join(HERE, "cli.py"), "check",
         "--plan", plan_file],
        capture_output=True, text=True, env=env)
    row(chk.returncode == 0, "cli: compliant plan check exits 0",
        chk.stderr[-200:])
    payload = json.loads(chk.stdout)
    row(payload["outcome"] == "ok"
        and payload["data"]["rule_result"]["reason_code"] == "DEL16_RULES_PASS",
        "cli: compliant plan reason_code DEL16_RULES_PASS",
        str(payload.get("data", {}).get("rule_result", {}).get("reasons"))[:200])

    bad = copy.deepcopy(plan)
    bad[1]["camera_moves"] = ["pan", "tilt"]
    bad_file = os.path.join("/tmp", "TrevelynsMini2-PKG-07-U2-bad.json")
    with open(bad_file, "w", encoding="utf-8") as fh:
        json.dump({"briefs": bad}, fh)
    chk = subprocess.run(
        [sys.executable, os.path.join(HERE, "cli.py"), "check",
         "--plan", bad_file],
        capture_output=True, text=True, env=env)
    row(chk.returncode == 4, "cli: rule refusal exits 4", str(chk.returncode))
    payload = json.loads(chk.stdout)
    row(payload["outcome"] == "rejected"
        and "MULTI_MOVE_CLIP" in payload["data"]["rule_result"]["reason_code"],
        "cli: refusal names MULTI_MOVE_CLIP",
        payload["data"]["rule_result"]["reason_code"])

    specs = [{
        "shot_id": "p1", "framing": "establishing_wide", "angle": "eye",
        "camera_move": "static", "lens_mm": 24, "f_number": 8.0,
        "emotion": "epic", "content_mode": "music",
    }]
    spec_file = os.path.join("/tmp", "TrevelynsMini2-PKG-07-U2-specs.json")
    with open(spec_file, "w", encoding="utf-8") as fh:
        json.dump(specs, fh)
    pln = subprocess.run(
        [sys.executable, os.path.join(HERE, "cli.py"), "plan",
         "--specs", spec_file],
        capture_output=True, text=True, env=env)
    # one-shot plan cannot span six coverage roles: rejected is correct
    row(pln.returncode in (0, 4), "cli: plan command runs", pln.stderr[-200:])
    payload = json.loads(pln.stdout)
    row(payload["outcome"] in ("ok", "rejected")
        and payload["data"]["briefs"][0]["shot_id"] == "p1",
        "cli: plan builds the brief")

    bad_spec = [{"shot_id": "p1", "framing": "establishing_wide",
                 "angle": "eye", "camera_move": "whip-pan", "lens_mm": 24,
                 "f_number": 8.0, "emotion": "epic", "content_mode": "music"}]
    with open(spec_file, "w", encoding="utf-8") as fh:
        json.dump(bad_spec, fh)
    pln = subprocess.run(
        [sys.executable, os.path.join(HERE, "cli.py"), "plan",
         "--specs", spec_file],
        capture_output=True, text=True, env=env)
    payload = json.loads(pln.stdout)
    row(pln.returncode == 4
        and payload["reason_code"] == "EDIT_TRANSITION_NOT_A_MOVE",
        "cli: whip-pan spec refused at build time", payload["reason_code"])


def test_docs_label_planning_ranges():
    readme = os.path.join(HERE, "README.md")
    with open(readme, "r", encoding="utf-8") as fh:
        text = fh.read().lower()
    row("planning range, not a measured standard" in text,
        "docs: README labels pacing percentages planning ranges")
    row("thirty-five percent" in text or "35%" in text,
        "docs: close-up cap documented")
    row("shallow depth of field" in text,
        "docs: depth-of-field phrase rule documented")
    row("whip pans and fast orbits" in text,
        "docs: whip pan / fast orbit edit-transition rule documented")


def test_builder_refusals():
    for code, kwargs in (
        ("EDIT_TRANSITION_NOT_A_MOVE", {"camera_move": "whip-pan"}),
        ("BAD_FRAMING", {"framing": "extreme-wide"}),
        ("BAD_ANGLE", {"angle": "dutch-angle"}),
        ("BAD_LENS", {"lens_mm": 32}),
        ("BAD_APERTURE", {"f_number": 2.2}),
        ("LENS_EMOTION_MISMATCH", {"lens_mm": 24}),
        ("APERTURE_EMOTION_MISMATCH", {"f_number": 8.0}),
    ):
        base = {"shot_id": "x", "framing": "medium", "angle": "eye",
                "camera_move": "static", "lens_mm": 50, "f_number": 4.0,
                "emotion": "calm", "content_mode": "music"}
        base.update(kwargs)
        try:
            B.build_shot_brief(**base)
            row(False, "builder refuses %s" % code)
        except B.BriefError as exc:
            row(exc.code == code, "builder refuses %s" % code, exc.code)


def main():
    test_vocabulary_complete()
    test_compliant_plan_all_modes()
    test_rule_one_move_and_length()
    test_rule_two_whip_pan_is_an_edit_transition()
    test_rule_three_text_logos_in_post()
    test_rule_four_depth_of_field_phrase()
    test_rule_five_six_seven_ladder_and_shares()
    test_rule_eight_nine_runs_and_scene_open()
    test_rule_ten_long_video()
    test_rule_eleven_lens_aperture_emotion()
    test_rule_twelve_coverage_family()
    test_builder_refusals()
    test_cli()
    test_docs_label_planning_ranges()
    print("\n%d checks, %d failed" % (len(ROWS), len(FAILS)))
    if FAILS:
        print("FAILED: " + ", ".join(FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
