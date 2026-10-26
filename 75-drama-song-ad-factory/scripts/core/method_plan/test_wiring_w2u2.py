"""S75X-W2-U2 wiring check: the blueprint projections populate the REAL
downstream inputs (shot planner, storyboard review, music request).

Run: python3 -I scripts/core/method_plan/test_wiring_w2u2.py   (or pytest)
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (CORE, os.path.join(CORE, "intake_preflight")):
    if p not in sys.path:
        sys.path.insert(0, p)

import method_plan.method_plan as MP                    # noqa: E402
import music_director as MD                             # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "blueprint-90s.json")
METHOD = {"purpose": "campaign", "chosen_length_s": 90,
          "gates": {g: "planned" for g in "ABCDEF"}}


def _bp():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_request_turns_carry_reason_and_audible():
    turns = MD.blueprint_request_inputs(_bp())["turns"]
    assert len(turns) == 4
    for name, t in turns.items():
        assert t.get("reason"), (name, t)
        assert any((t.get("audible_change") or {}).values()), (name, t)
        assert any(t.get(k) for k in MP.AUDIBLE_FIELDS), (name, t)


def test_shot_planner_input_from_blueprint():
    import shot_planner.shot_planner as SP
    seeds = SP.shots_from_blueprint(_bp(), METHOD)
    assert seeds == MP.shot_seeds(_bp(), METHOD) and seeds
    assert all(s["shot_id"] and "unresolved" in s for s in seeds)


def test_storyboard_review_input_from_blueprint():
    import storyboard_director.approval_runner as AR
    with tempfile.TemporaryDirectory() as run:
        os.makedirs(os.path.join(run, "creative"))
        with open(os.path.join(run, "creative", "blueprint.json"), "w") as f:
            json.dump(_bp(), f)
        filled = AR._method_contracts(run, {})
        assert filled.get("SB-07", {}).get("necessity"), filled
        kept = AR._method_contracts(run, {"SB-07": {"necessity": "operator kept"}})
        assert kept["SB-07"]["necessity"] == "operator kept"
        assert kept["SB-07"].get("treatment") == filled["SB-07"].get("treatment")
        # no blueprint on disk: the review sees the run's contracts unchanged
        assert AR._method_contracts("/nonexistent-run", {"a": {"x": 1}}) == {"a": {"x": 1}}


def test_factory_wires_seeds_turns_and_receipt():
    import factory as F
    with tempfile.TemporaryDirectory() as run:
        os.makedirs(os.path.join(run, "creative"))
        os.makedirs(os.path.join(run, "music"))
        with open(os.path.join(run, "creative", "blueprint.json"), "w") as f:
            json.dump(_bp(), f)
        with open(os.path.join(run, "music", "req.json"), "w") as f:
            json.dump({"estimated_cost": 1}, f)
        out = F._pace_into_music(run, METHOD)
        req = json.load(open(os.path.join(run, "music", "req.json")))
        assert out["available"] and req["turns"] == \
            MP.music_request_input(_bp(), METHOD)["turns"]
        assert req["pace_order"] and req["true_at_beat"]
        assert all(t.get("reason") for t in req["turns"])
        seeds = F._seeds_into_storyboard(run, METHOD)
        on_disk = json.load(open(os.path.join(run, "storyboard",
                                              "shot-seeds.json")))
        assert seeds["written"] and len(on_disk["seeds"]) == seeds["seeds"]
        block = F._method_plan_block(run, METHOD)
        assert block["production_map"]["turns"]
        assert block["storyboard_input"]["cards"]
        assert block["shot_seeds"] == on_disk["seeds"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok  ", name)
    print("all wiring checks ok")
