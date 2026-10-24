#!/usr/bin/env python3
"""Tests for story_planner (S75-T09). stdlib only, no network, no model spend.

Run: python3 scripts/core/test_story_planner_s75t09.py

Required cases (S75-A09):
  * a complete plan authored through a fake dispatcher passes, and the
    dispatcher SAW the exact foundation revisions and causal beats;
  * missing cast / world / research / causal beat stops the writer BEFORE the
    dispatcher is called (dispatched is False, call count 0);
  * a scene with no causal link is refused (broken chain, blank outcome,
    non-opening first predecessor);
  * a scene below the contract minimum detail is refused (per-field floor and
    whole-scene placeholder floor), while a DIFFERENT valid scene from another
    setting passes -- proving the validator is not rejecting all variation;
  * undefined cast / stale identity revision / undefined location / stale world
    revision are refused;
  * timing stays provisional: measured lip-sync or a non-provisional timing
    basis is refused;
  * the music gate refuses an incomplete plan and a plan that already carries
    a song.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_planner as SP  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def codes(result):
    return [e["error"] for e in result["errors"]]


# --------------------------------------------------------------------------- #
# foundations
# --------------------------------------------------------------------------- #
def workshop_foundation():
    return {
        "research_bundle": {
            "bundle_id": "rb_workshop_001", "revision": 1, "digest": "sha256:aa11",
            "claims": [{"claim_id": "claim_shortfall_001"}],
        },
        "character_identity_library_snapshot": {
            "snapshot_id": "cis_001", "revision": 3, "digest": "sha256:bb22",
        },
        "episode_cast_manifest": {
            "manifest_id": "ecm_workshop_001", "revision": 2, "digest": "sha256:cc33",
            "cast": [
                {"cast_id": "char_mara_001", "identity_revision": 1,
                 "display_name": "Mara"},
                {"cast_id": "char_levi_002", "identity_revision": 1,
                 "display_name": "Levi"},
            ],
        },
        "episode_world": {
            "world_id": "world_workshop_001", "revision": 1, "digest": "sha256:dd44",
            "locations": [{"location_id": "loc_workshop_front_001"}],
        },
    }


def diner_foundation():
    """Neighbouring valid foundation: different setting, different cast."""
    return {
        "research_bundle": {
            "bundle_id": "rb_diner_002", "revision": 4, "digest": "sha256:ee55",
            "claims": [{"claim_id": "claim_lease_002"}],
        },
        "character_identity_library_snapshot": {
            "snapshot_id": "cis_002", "revision": 1, "digest": "sha256:ff66",
        },
        "episode_cast_manifest": {
            "manifest_id": "ecm_diner_002", "revision": 1, "digest": "sha256:aa77",
            "cast": [
                {"cast_id": "char_rosa_010", "identity_revision": 2, "display_name": "Rosa"},
                {"cast_id": "char_theo_011", "identity_revision": 2, "display_name": "Theo"},
            ],
        },
        "episode_world": {
            "world_id": "world_diner_002", "revision": 6, "digest": "sha256:bb88",
            "locations": [{"location_id": "loc_diner_counter_002"}],
        },
    }


BEATS = {
    "scene": "Closing time in the workshop front; the sealed payroll warning is already late.",
    "inciting_event": "Levi asks why the weekly ledger shows an empty total.",
    "opposing_action": "Mara answers with a promise instead of the notice she is holding.",
    "escalation": "Levi empties his pockets on the table, showing he already spent the float.",
    "cost": "Every further minute of concealment makes the missed payroll harder to repair.",
    "choice": "Mara puts the sealed notice on the table where Levi can read it.",
    "product_mechanism": "The partner repair process turns the warning into a dated shortfall plan.",
    "consequence": "They schedule the calls together instead of Mara carrying the notice alone.",
    "commercial_action": "Schedule an assessment of the shortfall before the next payroll run.",
}


# --------------------------------------------------------------------------- #
# scene rows
# --------------------------------------------------------------------------- #
def scene_workshop_001():
    return {
        "scene_id": "scene_workshop_001",
        "sequence": 1,
        "causal_predecessor": SP.OPENING,
        "causal_outcome": "Levi can read the notice, so the next scene must produce a dated plan",
        "dramatic_purpose": ("Expose the immediate cost of concealment and force Mara's first honest "
                             "choice in front of her partner"),
        "time": "evening closing time, one continuous evening",
        "location_id": "loc_workshop_front_001",
        "world_revision": 1,
        "cast_roles": [
            {"cast_id": "char_mara_001", "identity_revision": 1, "role": "viewpoint",
             "consequence": "Loses control of the information she was hiding"},
            {"cast_id": "char_levi_002", "identity_revision": 1, "role": "partner",
             "consequence": "Gains the fact he needs before payroll clears"},
        ],
        "immediate_want": "Mara wants one more vague promise accepted without reading the warning",
        "obstacle": "Levi's empty ledger and his direct question block that escape",
        "visible_action": ("Mara opens the envelope and places the warning beside the open ledger, "
                           "then stops straightening the tools and leaves her hands still"),
        "consequential_choice": "She gives up control of the notice instead of pulling it back",
        "emotion_before": "defensive and ashamed",
        "emotion_after": "still afraid but no longer isolated",
        "turn_trigger": ("Putting the open notice where Levi can read it shifts her from hiding to "
                         "sharing"),
        "planned_dialogue_function": ("Spoken lines admit the concealment, then a sung line carries "
                                      "the admission without resolving it"),
        "claim_ids": ["claim_shortfall_001"],
        "sound_music_intention": ("Fan clicks off before the first line; quiet room tone, then a "
                                  "restrained low instrumental bed"),
        "framing_movement_intention": ("Medium close-up on Mara inside the door, cut to Levi's hands, "
                                       "insert on the envelope, slow push to the exposed page"),
        "estimated_duration_seconds": 24,
        "timing_basis": SP.TIMING_BASIS_PROVISIONAL,
        "transition": "Match-cut the shared ledger orientation into the next scene's first action",
        "lip_sync_intention": ("Spoken words in the first shots, sung line over a cutaway; "
                               "intervals are expectations only"),
    }


def scene_workshop_002():
    return {
        "scene_id": "scene_workshop_002",
        "sequence": 2,
        "causal_predecessor": ("Levi can read the notice, so the next scene must produce a dated "
                               "plan"),
        "causal_outcome": "A dated shortfall plan exists, so the CTA can be one concrete request",
        "dramatic_purpose": ("Convert the exposed warning into a shared dated plan, so the solution "
                             "answers the actual obstacle rather than reassuring"),
        "time": "evening closing time, minutes after the notice opens",
        "location_id": "loc_workshop_front_001",
        "world_revision": 1,
        "cast_roles": [
            {"cast_id": "char_levi_002", "identity_revision": 1, "role": "viewpoint",
             "consequence": "Owns half the repair instead of waiting to be told"},
            {"cast_id": "char_mara_001", "identity_revision": 1, "role": "partner",
             "consequence": "Accepts a written date she cannot quietly move"},
        ],
        "immediate_want": "Levi wants a date and a name against every unpaid line",
        "obstacle": "Mara wants the plan kept verbal so nothing is written down",
        "visible_action": ("Levi writes the first supplier name and date in the ledger margin and "
                           "slides the pen across the table without letting go of the page"),
        "consequential_choice": "Mara writes the second date herself instead of dictating it",
        "emotion_before": "braced for a lecture",
        "emotion_after": "steady enough to act",
        "turn_trigger": "Levi writes his own name first, so the plan costs him something too",
        "planned_dialogue_function": ("Short spoken exchange sets the date; the sung hook names the "
                                      "open book once, deliberately repeated"),
        "claim_ids": ["claim_shortfall_001"],
        "sound_music_intention": ("Pen scratch and paper movement carry the beat; music drops to a "
                                  "single held note under the writing"),
        "framing_movement_intention": ("Two-shot across the ledger, then over-shoulder to the written "
                                       "date, holding the established axis"),
        "estimated_duration_seconds": 21,
        "timing_basis": SP.TIMING_BASIS_PROVISIONAL,
        "transition": "Hold on the written date and cut on the pen lifting to the single CTA",
        "lip_sync_intention": ("One spoken line mouth-visible, the repeated hook sung off camera; "
                               "expectations only, unmeasured"),
    }


def diner_plan():
    """A different valid plan: proves the validator accepts creative variation."""
    foundation = diner_foundation()
    return {
        "schema_version": SP.SCHEMA_VERSION,
        "plan_id": "plan_diner_002",
        "episode_id": "ep_diner_002",
        "status": "complete",
        "foundation": foundation,
        "foundation_revisions": {"episode_world": {"revision": 6, "digest": "sha256:bb88"}},
        "scenes": [{
            "scene_id": "scene_diner_001",
            "sequence": 1,
            "causal_predecessor": SP.OPENING,
            "causal_outcome": ("Theo has the rent letter in hand, so the next scene has to name a "
                               "real date he cannot dodge"),
            "dramatic_purpose": ("Force Rosa to name the missed rent date before she refills a "
                                 "single cup for the morning rush"),
            "time": "pre-dawn, before the diner opens",
            "location_id": "loc_diner_counter_002",
            "world_revision": 6,
            "cast_roles": [
                {"cast_id": "char_rosa_010", "identity_revision": 2, "role": "viewpoint",
                 "consequence": "Stops managing the room and starts managing the debt"},
                {"cast_id": "char_theo_011", "identity_revision": 2, "role": "co-signer",
                 "consequence": "Learns the letter is already two weeks old"},
            ],
            "immediate_want": "Rosa wants the stove lit and the letter left in her apron",
            "obstacle": "Theo has already put the envelope on the counter beside the till",
            "visible_action": ("Rosa sets down the coffee pot, wipes both hands on the towel and "
                               "opens the letter in front of Theo instead of pocketing it"),
            "consequential_choice": "She reads the date out loud rather than paraphrasing it",
            "emotion_before": "brisk and evasive",
            "emotion_after": "quiet but committed",
            "turn_trigger": "Saying the date out loud makes it a shared fact she cannot soften later",
            "planned_dialogue_function": ("Spoken date first, then the sung line turns the number "
                                          "into the promise she is making"),
            "claim_ids": ["claim_lease_002"],
            "sound_music_intention": ("Griddle hiss fades under the first line; music enters only "
                                      "after the date is spoken"),
            "framing_movement_intention": ("Wide of the empty counter, push to the envelope, then "
                                           "over Theo's shoulder onto the dated line"),
            "estimated_duration_seconds": 18,
            "timing_basis": SP.TIMING_BASIS_PROVISIONAL,
            "transition": "Cut on the towel hitting the counter into the callback scene",
            "lip_sync_intention": ("Date spoken with mouth visible, sung line over the push; "
                                   "expected intervals only"),
        }],
    }


def workshop_plan():
    foundation = workshop_foundation()
    return {
        "schema_version": SP.SCHEMA_VERSION,
        "plan_id": "plan_workshop_001",
        "episode_id": "ep_workshop_001",
        "status": "complete",
        "foundation": foundation,
        "foundation_revisions": {
            k: {"revision": (foundation.get(k) or {}).get("revision"),
                "digest": (foundation.get(k) or {}).get("digest")}
            for k in SP.FOUNDATION_KEYS
        },
        "scenes": [scene_workshop_001(), scene_workshop_002()],
    }


# --------------------------------------------------------------------------- #
# cases
# --------------------------------------------------------------------------- #
def run():
    FAILS.clear()

    # 0. both valid neighbouring foundations are complete
    check("foundation-complete", SP.validate_foundation(workshop_foundation())["outcome"] == "ok")
    check("beats-complete", SP.validate_causal_beats(BEATS)["outcome"] == "ok")

    # 1. valid workshop plan passes
    plan = workshop_plan()
    res = SP.validate_scene_plan(plan)
    check("valid-plan-accepted", res["outcome"] == "ok",
          "errors=%r" % (res["errors"][:3],))
    check("valid-plan-scene-count", res.get("scene_count") == 2, res.get("scene_count"))

    # 2. a DIFFERENT valid plan is accepted too (not rejecting all variation)
    res2 = SP.validate_scene_plan(diner_plan())
    check("neighbour-valid-plan-accepted", res2["outcome"] == "ok",
          "errors=%r" % (res2["errors"][:3],))

    # 3. dispatcher route: dispatch happened with the pinned revisions
    seen = {}

    def fake_submit(request):
        seen["request"] = request
        return {"scenes": copy.deepcopy(workshop_plan()["scenes"]),
                "plan_id": "plan_workshop_001",
                "episode_id": "ep_workshop_001",
                "status": "complete"}

    auth = SP.build_scene_plan(workshop_foundation(), BEATS, fake_submit, attempt_key="att-1")
    check("authored-plan-ok", auth["outcome"] == "ok",
          "errors=%r" % (auth["errors"][:3],))
    check("authored-dispatch-recorded", auth.get("dispatched") is True)
    check("authored-receipt-attempt", (auth.get("receipt") or {}).get("attempt_key") == "att-1")
    check("authored-request-has-cast-revision",
          ((seen.get("request") or {}).get("foundation") or {}).get(
              "episode_cast_manifest", {}).get("revision") == 2)
    check("authored-request-has-world-digest",
          ((seen.get("request") or {}).get("foundation") or {}).get(
              "episode_world", {}).get("digest") == "sha256:dd44")
    check("authored-request-carries-all-beats",
          set((seen.get("request") or {}).get("causal_story_beats") or {}) == set(SP.BEAT_FIELDS))

    # 4. missing foundation stops the writer BEFORE the dispatcher
    calls = {"n": 0}

    def counting_submit(request):
        calls["n"] += 1
        return {"scenes": []}

    for key in SP.FOUNDATION_KEYS:
        broken = workshop_foundation()
        del broken[key]
        out = SP.build_scene_plan(broken, BEATS, counting_submit, attempt_key="att-x")
        check("missing-%s-blocks" % key,
              out["outcome"] == "rejected" and out.get("dispatched") is False,
              out["reason_code"])
    check("dispatcher-never-called-on-missing-foundation", calls["n"] == 0, calls["n"])

    bad_beats = dict(BEATS)
    del bad_beats["choice"]
    out = SP.build_scene_plan(workshop_foundation(), bad_beats, counting_submit)
    check("missing-causal-beat-blocks", out["outcome"] == "rejected"
          and out.get("dispatched") is False, out["reason_code"])
    check("dispatcher-never-called-on-missing-beat", calls["n"] == 0, calls["n"])

    # 5. no causal link -> refused
    p = workshop_plan()
    p["scenes"][1]["causal_predecessor"] = "something unrelated happened earlier"
    check("broken-causal-link-refused",
          "causal-link-broken" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["causal_predecessor"] = "scene_workshop_000"
    check("opening-unlinked-refused",
          "opening-unlinked" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["causal_outcome"] = "   "
    check("blank-outcome-refused",
          "scene-field-blank" in codes(SP.validate_scene_plan(p)))

    # 6. below the contract minimum detail -> refused
    p = workshop_plan()
    p["scenes"][0]["dramatic_purpose"] = "Make it emotional."
    c = codes(SP.validate_scene_plan(p))
    check("one-line-purpose-refused",
          "scene-detail-below-minimum" in c or "purpose-quality-only" in c, c)

    p = workshop_plan()
    for f in ("visible_action", "consequential_choice", "obstacle", "immediate_want",
              "turn_trigger", "causal_outcome", "planned_dialogue_function",
              "sound_music_intention", "framing_movement_intention", "transition"):
        p["scenes"][0][f] = "stuff happens"
    check("per-field-floor-refused",
          "scene-detail-below-minimum" in codes(SP.validate_scene_plan(p)))

    # bare-floor compliance: every prose field at exactly its own minimum still
    # fails the whole-scene floor -- 65 words is a placeholder, not a scene
    p = workshop_plan()
    sc = p["scenes"][0]
    for f, floor in SP.MIN_WORDS.items():
        sc[f] = " ".join(["word"] * floor)
    body = sum(SP._words(sc.get(f)) for f in SP.MIN_WORDS)
    c = codes(SP.validate_scene_plan(p))
    check("thin-scene-placeholder-refused",
          "scene-placeholder-thin" in c and body < SP.SCENE_MIN_WORDS,
          "words=%d codes=%r" % (body, c))

    p = workshop_plan()
    del p["scenes"][0]["visible_action"]
    check("missing-field-refused", "scene-field-missing" in codes(SP.validate_scene_plan(p)))

    # 7. undefined cast / stale revisions / undefined location
    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["cast_id"] = "char_ghost_999"
    check("undefined-cast-refused", "cast-undefined" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["identity_revision"] = 7
    check("stale-identity-revision-refused",
          "cast-revision-mismatch" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][1]["location_id"] = "loc_basement_999"
    check("undefined-location-refused",
          "location-undefined" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["world_revision"] = 9
    check("stale-world-revision-refused",
          "world-revision-mismatch" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["claim_ids"] = ["claim_invented_999"]
    check("undefined-claim-refused", "claim-undefined" in codes(SP.validate_scene_plan(p)))

    # 8. timing stays provisional until the selected music
    p = workshop_plan()
    p["scenes"][0]["timing_basis"] = "measured_after_alignment"
    check("non-provisional-timing-refused",
          "timing-not-provisional" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][0]["lip_sync_intention"] = "measured intervals locked at 0-4s"
    check("measured-lipsync-refused",
          "timing-claims-measured" in codes(SP.validate_scene_plan(p)))

    # 9. sequence integrity
    p = workshop_plan()
    p["scenes"][1]["sequence"] = 3
    check("sequence-gap-refused", "sequence-gap" in codes(SP.validate_scene_plan(p)))

    p = workshop_plan()
    p["scenes"][1]["scene_id"] = p["scenes"][0]["scene_id"]
    check("duplicate-scene-id-refused",
          "scene-id-duplicate" in codes(SP.validate_scene_plan(p)))

    # 10. music gate
    gate = SP.music_gate(workshop_plan())
    check("music-gate-allows-complete-plan", gate["allowed"] is True, gate["reason_code"])

    p = workshop_plan()
    p["status"] = "draft"
    check("music-gate-refuses-incomplete-plan",
          SP.music_gate(p)["allowed"] is False)

    p = workshop_plan()
    p["lyrics"] = {"line_1": "placeholder"}
    check("music-gate-refuses-plan-carrying-song",
          SP.music_gate(p)["allowed"] is False)

    p = workshop_plan()
    p.pop("foundation")
    p.pop("foundation_revisions")
    check("unbound-plan-refused", "foundation-not-bound" in codes(SP.validate_scene_plan(p)))

    # 11. the neighbouring writers' row keys resolve (S75-T06/S75-T08 own them)
    f = workshop_foundation()
    f["episode_world"] = dict(f["episode_world"],
                              locations=[{"id": "loc_workshop_front_001"}])
    f["episode_cast_manifest"] = dict(f["episode_cast_manifest"], cast=[
        {"character_id": "char_mara_001", "identity_revision": 1},
        {"character_id": "char_levi_002", "identity_revision": 1},
    ])
    p = workshop_plan()
    p["foundation"] = f
    check("neighbour-row-keys-resolve", SP.validate_scene_plan(p)["outcome"] == "ok",
          "errors=%r" % (SP.validate_scene_plan(p)["errors"][:3],))

    # 12. the shipped schema and the validator cannot drift apart
    with open(os.path.join(HERE, "contracts", "scene-plan.schema.json"),
              "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    required = set(schema["properties"]["scenes"]["items"]["required"])
    check("schema-required-matches-validator",
          required == set(SP.SCENE_FIELDS),
          "schema-only=%r validator-only=%r"
          % (sorted(required - set(SP.SCENE_FIELDS)),
             sorted(set(SP.SCENE_FIELDS) - required)))
    check("schema-version-matches",
          schema["properties"]["schema_version"]["const"] == SP.SCHEMA_VERSION)
    check("schema-timing-basis-matches",
          schema["properties"]["scenes"]["items"]["properties"]["timing_basis"]["const"]
          == SP.TIMING_BASIS_PROVISIONAL)

    print()
    if FAILS:
        print("FAILED %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
