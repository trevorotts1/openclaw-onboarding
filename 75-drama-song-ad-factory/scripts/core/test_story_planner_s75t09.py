#!/usr/bin/env python3
"""Tests for story_planner (S75-T09). stdlib only, no network, no model spend.

Run: python3 -m pytest --collect-only -q test_story_planner_s75t09.py
     python3 -m pytest -q test_story_planner_s75t09.py
     python3 story_planner.py selftest   (same cases, hand-rolled runner)

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
    revision are refused, and an EMPTY location (or cast / claim) set fails
    closed instead of silently disabling resolution;
  * timing stays provisional: measured lip-sync or a non-provisional timing
    basis is refused;
  * the music gate refuses an incomplete plan and a plan that already carries
    a song;
  * revision identity is TYPE-STRICT (round 4): a revision is a non-empty
    string, and every falsy or non-string spelling (False, True, 0, 0.0, [],
    {}, None, "", whitespace, an object) refuses by name at every consumption
    site -- world revision, scene world_revision, cast identity_revision and
    the foundation pins -- while an exactly-matching string still validates
    and opens the music gate.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_planner as SP  # noqa: E402


def codes(result):
    return [e["error"] for e in result["errors"]]


# --------------------------------------------------------------------------- #
# foundations
# --------------------------------------------------------------------------- #
def workshop_foundation():
    return {
        "research_bundle": {
            "bundle_id": "rb_workshop_001", "revision": "1", "digest": "sha256:aa11",
            "claims": [{"claim_id": "claim_shortfall_001"}],
        },
        "character_identity_library_snapshot": {
            "snapshot_id": "cis_001", "revision": "3", "digest": "sha256:bb22",
        },
        "episode_cast_manifest": {
            "manifest_id": "ecm_workshop_001", "revision": "2", "digest": "sha256:cc33",
            "cast": [
                {"cast_id": "char_mara_001", "identity_revision": "1",
                 "display_name": "Mara"},
                {"cast_id": "char_levi_002", "identity_revision": "1",
                 "display_name": "Levi"},
            ],
        },
        "episode_world": {
            "world_id": "world_workshop_001", "revision": "1", "digest": "sha256:dd44",
            "locations": [{"location_id": "loc_workshop_front_001"}],
        },
    }


def diner_foundation():
    """Neighbouring valid foundation: different setting, different cast."""
    return {
        "research_bundle": {
            "bundle_id": "rb_diner_002", "revision": "4", "digest": "sha256:ee55",
            "claims": [{"claim_id": "claim_lease_002"}],
        },
        "character_identity_library_snapshot": {
            "snapshot_id": "cis_002", "revision": "1", "digest": "sha256:ff66",
        },
        "episode_cast_manifest": {
            "manifest_id": "ecm_diner_002", "revision": "1", "digest": "sha256:aa77",
            "cast": [
                {"cast_id": "char_rosa_010", "identity_revision": "2", "display_name": "Rosa"},
                {"cast_id": "char_theo_011", "identity_revision": "2", "display_name": "Theo"},
            ],
        },
        "episode_world": {
            "world_id": "world_diner_002", "revision": "6", "digest": "sha256:bb88",
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
        "world_revision": "1",
        "cast_roles": [
            {"cast_id": "char_mara_001", "identity_revision": "1", "role": "viewpoint",
             "consequence": "Loses control of the information she was hiding"},
            {"cast_id": "char_levi_002", "identity_revision": "1", "role": "partner",
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
        "world_revision": "1",
        "cast_roles": [
            {"cast_id": "char_levi_002", "identity_revision": "1", "role": "viewpoint",
             "consequence": "Owns half the repair instead of waiting to be told"},
            {"cast_id": "char_mara_001", "identity_revision": "1", "role": "partner",
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
        "foundation_revisions": {
            k: {"revision": (foundation.get(k) or {}).get("revision"),
                "digest": (foundation.get(k) or {}).get("digest")}
            for k in SP.FOUNDATION_KEYS
        },
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
            "world_revision": "6",
            "cast_roles": [
                {"cast_id": "char_rosa_010", "identity_revision": "2", "role": "viewpoint",
                 "consequence": "Stops managing the room and starts managing the debt"},
                {"cast_id": "char_theo_011", "identity_revision": "2", "role": "co-signer",
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
# cases -- every case is a pytest-collectable test_* function with real asserts,
# and run() below re-executes the same functions for `story_planner.py selftest`
# --------------------------------------------------------------------------- #
def test_foundation_and_beats_complete():
    assert SP.validate_foundation(workshop_foundation())["outcome"] == "ok"
    assert SP.validate_causal_beats(BEATS)["outcome"] == "ok"


def test_valid_plans_accepted():
    plan = workshop_plan()
    res = SP.validate_scene_plan(plan)
    assert res["outcome"] == "ok", "errors=%r" % (res["errors"][:3],)
    assert res.get("scene_count") == 2, res.get("scene_count")

    # a DIFFERENT valid plan is accepted too (not rejecting all variation)
    res2 = SP.validate_scene_plan(diner_plan())
    assert res2["outcome"] == "ok", "errors=%r" % (res2["errors"][:3],)


def test_dispatched_plan_carries_pinned_revisions():
    seen = {}

    def fake_submit(request):
        seen["request"] = request
        return {"scenes": copy.deepcopy(workshop_plan()["scenes"]),
                "plan_id": "plan_workshop_001",
                "episode_id": "ep_workshop_001",
                "status": "complete"}

    auth = SP.build_scene_plan(workshop_foundation(), BEATS, fake_submit, attempt_key="att-1")
    assert auth["outcome"] == "ok", "errors=%r" % (auth["errors"][:3],)
    assert auth.get("dispatched") is True
    assert (auth.get("receipt") or {}).get("attempt_key") == "att-1"
    assert ((seen.get("request") or {}).get("foundation") or {}).get(
        "episode_cast_manifest", {}).get("revision") == "2"
    assert ((seen.get("request") or {}).get("foundation") or {}).get(
        "episode_world", {}).get("digest") == "sha256:dd44"
    assert set((seen.get("request") or {}).get("causal_story_beats") or {}) == set(SP.BEAT_FIELDS)


def test_missing_foundation_blocks_before_dispatch():
    calls = {"n": 0}

    def counting_submit(request):
        calls["n"] += 1
        return {"scenes": []}

    for key in SP.FOUNDATION_KEYS:
        broken = workshop_foundation()
        del broken[key]
        out = SP.build_scene_plan(broken, BEATS, counting_submit, attempt_key="att-x")
        assert out["outcome"] == "rejected" and out.get("dispatched") is False, \
            "missing-%s did not block: %s" % (key, out["reason_code"])
    assert calls["n"] == 0, calls["n"]

    bad_beats = dict(BEATS)
    del bad_beats["choice"]
    out = SP.build_scene_plan(workshop_foundation(), bad_beats, counting_submit)
    assert out["outcome"] == "rejected" and out.get("dispatched") is False, out["reason_code"]
    assert calls["n"] == 0, calls["n"]


def test_broken_causal_link_refused():
    p = workshop_plan()
    p["scenes"][1]["causal_predecessor"] = "something unrelated happened earlier"
    assert "causal-link-broken" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][0]["causal_predecessor"] = "scene_workshop_000"
    assert "opening-unlinked" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][0]["causal_outcome"] = "   "
    assert "scene-field-blank" in codes(SP.validate_scene_plan(p))


def test_below_contract_minimum_detail_refused():
    p = workshop_plan()
    p["scenes"][0]["dramatic_purpose"] = "Make it emotional."
    c = codes(SP.validate_scene_plan(p))
    assert "scene-detail-below-minimum" in c or "purpose-quality-only" in c, c

    p = workshop_plan()
    for f in ("visible_action", "consequential_choice", "obstacle", "immediate_want",
              "turn_trigger", "causal_outcome", "planned_dialogue_function",
              "sound_music_intention", "framing_movement_intention", "transition"):
        p["scenes"][0][f] = "stuff happens"
    assert "scene-detail-below-minimum" in codes(SP.validate_scene_plan(p))

    # bare-floor compliance: every prose field at exactly its own minimum still
    # fails the whole-scene floor -- 65 words is a placeholder, not a scene
    p = workshop_plan()
    sc = p["scenes"][0]
    for f, floor in SP.MIN_WORDS.items():
        sc[f] = " ".join(["word"] * floor)
    body = sum(SP._words(sc.get(f)) for f in SP.MIN_WORDS)
    c = codes(SP.validate_scene_plan(p))
    assert "scene-placeholder-thin" in c and body < SP.SCENE_MIN_WORDS, \
        "words=%d codes=%r" % (body, c)

    p = workshop_plan()
    del p["scenes"][0]["visible_action"]
    assert "scene-field-missing" in codes(SP.validate_scene_plan(p))


def test_undefined_cast_and_stale_revision_refused():
    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["cast_id"] = "char_ghost_999"
    assert "cast-undefined" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["identity_revision"] = "7"
    assert "cast-revision-mismatch" in codes(SP.validate_scene_plan(p))


def test_undefined_location_and_stale_world_revision_refused():
    p = workshop_plan()
    p["scenes"][1]["location_id"] = "loc_basement_999"
    assert "location-undefined" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][0]["world_revision"] = "9"
    assert "world-revision-mismatch" in codes(SP.validate_scene_plan(p))


def test_undefined_claim_refused():
    p = workshop_plan()
    p["scenes"][0]["claim_ids"] = ["claim_invented_999"]
    assert "claim-undefined" in codes(SP.validate_scene_plan(p))


def test_empty_reference_sets_fail_closed():
    """An empty/absent set must NOT switch validation off (S75-A09 class fix)."""
    for mutate, code in (
            (lambda f: f["episode_world"].update(locations=[]), "world-locations-empty"),
            (lambda f: f["episode_world"].update(locations=None), "world-locations-empty"),
            (lambda f: f["episode_world"].pop("locations"), "world-locations-empty"),
            (lambda f: f["episode_cast_manifest"].update(cast=[]), "cast-manifest-empty"),
            (lambda f: f["research_bundle"].update(claims=[]), "research-claims-empty")):
        p = workshop_plan()
        mutate(p["foundation"])
        c = codes(SP.validate_scene_plan(p))
        assert code in c, "expected %s, got %r" % (code, c)
        assert "location-undefined" in c or code != "world-locations-empty", \
            "empty locations must fail every scene reference: %r" % (c,)
        assert SP.validate_scene_plan(p)["outcome"] == "rejected"

    # blank / missing location_id is refused as well as an unknown one
    for bad in ("", None, 7):
        p = workshop_plan()
        p["scenes"][0]["location_id"] = bad
        assert "location-undefined" in codes(SP.validate_scene_plan(p)), bad


def test_timing_stays_provisional():
    p = workshop_plan()
    p["scenes"][0]["timing_basis"] = "measured_after_alignment"
    assert "timing-not-provisional" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][0]["lip_sync_intention"] = "measured intervals locked at 0-4s"
    assert "timing-claims-measured" in codes(SP.validate_scene_plan(p))


def test_sequence_integrity():
    p = workshop_plan()
    p["scenes"][1]["sequence"] = 3
    assert "sequence-gap" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][1]["scene_id"] = p["scenes"][0]["scene_id"]
    assert "scene-id-duplicate" in codes(SP.validate_scene_plan(p))


def test_music_gate():
    gate = SP.music_gate(workshop_plan())
    assert gate["allowed"] is True, gate["reason_code"]

    p = workshop_plan()
    p["status"] = "draft"
    assert SP.music_gate(p)["allowed"] is False

    p = workshop_plan()
    p["lyrics"] = {"line_1": "placeholder"}
    assert SP.music_gate(p)["allowed"] is False

    p = workshop_plan()
    p.pop("foundation")
    p.pop("foundation_revisions")
    assert "foundation-not-bound" in codes(SP.validate_scene_plan(p))


def test_neighbour_row_keys_resolve():
    """S75-T06/S75-T08 own those row keys; both spellings resolve."""
    f = workshop_foundation()
    f["episode_world"] = dict(f["episode_world"],
                              locations=[{"id": "loc_workshop_front_001"}])
    f["episode_cast_manifest"] = dict(f["episode_cast_manifest"], cast=[
        {"character_id": "char_mara_001", "identity_revision": "1"},
        {"character_id": "char_levi_002", "identity_revision": "1"},
    ])
    p = workshop_plan()
    p["foundation"] = f
    res = SP.validate_scene_plan(p)
    assert res["outcome"] == "ok", "errors=%r" % (res["errors"][:3],)


def test_schema_matches_validator():
    with open(os.path.join(HERE, "contracts", "scene-plan.schema.json"),
              "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    required = set(schema["properties"]["scenes"]["items"]["required"])
    assert required == set(SP.SCENE_FIELDS), \
        "schema-only=%r validator-only=%r" % (sorted(required - set(SP.SCENE_FIELDS)),
                                              sorted(set(SP.SCENE_FIELDS) - required))
    assert schema["properties"]["schema_version"]["const"] == SP.SCHEMA_VERSION
    assert (schema["properties"]["scenes"]["items"]["properties"]["timing_basis"]["const"]
            == SP.TIMING_BASIS_PROVISIONAL)


def test_world_revision_absence_is_refused():
    """A world with NO revision must not disable the binding check (S75-A09).

    The named defect: scene world_revision=99 against an unversioned world used
    to validate ok and reach music_gate allowed.
    """
    p = workshop_plan()
    del p["foundation"]["episode_world"]["revision"]
    p["foundation_revisions"]["episode_world"] = {"digest": "sha256:dd44"}
    p["scenes"][0]["world_revision"] = "99"
    p["scenes"][1]["world_revision"] = "99"
    c = codes(SP.validate_scene_plan(p))
    assert SP.validate_scene_plan(p)["outcome"] == "rejected", c
    assert "world-revision-missing" in c and "world-revision-unbound" in c, c
    assert "world-revision-mismatch" not in c, c  # nothing to compare against
    gate = SP.music_gate(p)
    assert gate["allowed"] is False, gate["reason_code"]

    # a scene that binds no world revision is refused too
    p = workshop_plan()
    p["scenes"][0]["world_revision"] = None
    assert "world-revision-unbound" in codes(SP.validate_scene_plan(p))

    # the declared-revision path still discriminates
    p = workshop_plan()
    p["scenes"][0]["world_revision"] = "99"
    assert "world-revision-mismatch" in codes(SP.validate_scene_plan(p))


def test_cast_identity_revision_absence_is_refused():
    """Neither side declaring an identity revision is a refusal, not a match."""
    p = workshop_plan()
    for row in p["foundation"]["episode_cast_manifest"]["cast"]:
        row.pop("identity_revision")
    for sc in p["scenes"]:
        for role in sc["cast_roles"]:
            role.pop("identity_revision")
    res = SP.validate_scene_plan(p)
    assert res["outcome"] == "rejected", res["errors"][:3]
    assert "cast-revision-missing" in codes(res)

    # a scene role that binds nothing against a declared manifest revision
    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["identity_revision"] = None
    assert "cast-revision-missing" in codes(SP.validate_scene_plan(p))

    # the declared path still discriminates
    p = workshop_plan()
    p["scenes"][0]["cast_roles"][0]["identity_revision"] = "7"
    assert "cast-revision-mismatch" in codes(SP.validate_scene_plan(p))


def test_foundation_revision_pins_reconciled():
    """The plan's pin must match the artifacts it validates against."""
    p = workshop_plan()
    p["foundation_revisions"]["episode_world"]["revision"] = "5"
    assert "foundation-revision-mismatch" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["foundation_revisions"]["research_bundle"]["digest"] = "sha256:ffff"
    assert "foundation-digest-mismatch" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    del p["foundation_revisions"]["episode_cast_manifest"]
    assert "foundation-revision-unpinned" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["foundation_revisions"] = {}
    assert "foundation-revisions-missing" in codes(SP.validate_scene_plan(p))

    # an artifact with no revision cannot be pinned, and must not be skipped
    p = workshop_plan()
    del p["foundation"]["research_bundle"]["revision"]
    c = codes(SP.validate_scene_plan(p))
    assert "artifact-revision-missing" in c and "foundation-revision-mismatch" not in c, c


def test_empty_foundation_blocks_before_dispatch():
    """An empty foundation set stops the writer BEFORE the dispatcher."""
    calls = {"n": 0}

    def counting_submit(request):
        calls["n"] += 1
        return {"scenes": []}

    for mutate, code in (
            (lambda f: f["research_bundle"].update(claims=[]), "research-claims-empty"),
            (lambda f: f["episode_cast_manifest"].update(cast=[]), "cast-manifest-empty"),
            (lambda f: f["episode_world"].update(locations=[]), "world-locations-empty")):
        f = workshop_foundation()
        mutate(f)
        out = SP.build_scene_plan(f, BEATS, counting_submit, attempt_key="att-e")
        assert out["outcome"] == "rejected" and out.get("dispatched") is False, \
            "%s dispatched: %s" % (code, out.get("reason_code"))
        assert code in [e["error"] for e in out["errors"]], (code, out["errors"][:2])
    assert calls["n"] == 0, calls["n"]


def test_optional_guards_fail_closed():
    """No guard in this family may treat absence as permission to skip a check."""
    p = workshop_plan()
    p["scenes"][0]["visible_action"] = 24
    assert "scene-field-not-text" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["scenes"][1]["causal_predecessor"] = "  "
    assert "causal-predecessor-missing" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    del p["schema_version"]
    assert "schema-version-missing" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    del p["status"]
    gate = SP.music_gate(p)
    assert gate["allowed"] is False and "plan-not-complete" in codes(gate), gate["reason_code"]

    # an explicitly EMPTY argument must fail closed, never fall back to the
    # plan's own foundation and silently pass
    res = SP.validate_scene_plan(workshop_plan(), cast_manifest={})
    assert "cast-manifest-empty" in codes(res) and res["outcome"] == "rejected"

    # a non-object scene list member must not crash the causal pass
    p = workshop_plan()
    p["scenes"] = ["not-a-scene"]
    assert SP.validate_scene_plan(p)["outcome"] == "rejected"


# --------------------------------------------------------------------------- #
# revision identity is TYPE-STRICT, never truthiness (S75-T09 round 4)
# --------------------------------------------------------------------------- #
#: Every type the truthiness bug used to smuggle past the blank check: falsy
#: scalars, truthy non-strings, empties, whitespace and plain objects. NONE of
#: these is a declared revision; each must refuse BY NAME at every consumption
#: site. A declared revision is a non-empty string and nothing else.
BAD_REVISIONS = (False, True, 0, 0.0, [], {}, None, "", "   ", b"1", ("1",),
                 object())


def test_revision_predicate_is_type_strict():
    """One predicate, no truthiness: declared means non-empty string."""
    for bad in BAD_REVISIONS:
        assert SP._is_revision(bad) is False, repr(bad)
    for good in ("1", "rev-17", "false", "0", "  x  "):
        assert SP._is_revision(good) is True, repr(good)


def test_revision_equality_is_type_strict():
    """0 can never satisfy False; 'false' is a value, False is not a revision."""
    assert SP._same_revision(0, False) is False
    assert SP._same_revision(False, 0) is False
    assert SP._same_revision("false", False) is False
    assert SP._same_revision("1", 1) is False
    assert SP._same_revision(1, True) is False
    assert SP._same_revision("1", "1 ") is False   # exact, never stripped-equal
    assert SP._same_revision(False, False) is False  # undeclared never matches
    assert SP._same_revision(0, 0) is False
    assert SP._same_revision("rev-1", "rev-1") is True


def test_world_revision_type_matrix_refused():
    """world revision / scene world_revision / pin, matching and not.

    The round-3 bypass shape: world 'revision': false, scenes
    'world_revision': false, matching pins, and music_gate still allowed.
    """
    for bad in BAD_REVISIONS:
        # (a) matching falsy/non-str on every side -- the bypass family
        p = workshop_plan()
        p["foundation"]["episode_world"]["revision"] = bad
        p["foundation_revisions"]["episode_world"]["revision"] = bad
        for sc in p["scenes"]:
            sc["world_revision"] = bad
        res = SP.validate_scene_plan(p)
        c = codes(res)
        assert res["outcome"] == "rejected", (repr(bad), c[:3])
        assert ("world-revision-missing" in c or "world-revision-unbound" in c
                or "artifact-revision-missing" in c), (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)

        # (b) only the scene side is that type -- refused, never a mismatch
        p = workshop_plan()
        for sc in p["scenes"]:
            sc["world_revision"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "world-revision-unbound" in c, (repr(bad), c[:3])
        assert "world-revision-mismatch" not in c, (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)

        # (c) only the world side is that type -- refused, never a mismatch
        p = workshop_plan()
        p["foundation"]["episode_world"]["revision"] = bad
        p["foundation_revisions"]["episode_world"]["revision"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "world-revision-missing" in c, (repr(bad), c[:3])
        assert "world-revision-mismatch" not in c, (repr(bad), c[:3])

        # (d) the pin alone is that type against a declared artifact
        p = workshop_plan()
        p["foundation_revisions"]["episode_world"]["revision"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "foundation-pin-revision-invalid" in c, (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)


def test_cast_identity_revision_type_matrix_refused():
    """identity_revision on the role AND on the manifest row, matching or not."""
    for bad in BAD_REVISIONS:
        # matching bad on both sides must never read as a match
        p = workshop_plan()
        for row in p["foundation"]["episode_cast_manifest"]["cast"]:
            row["identity_revision"] = bad
        for sc in p["scenes"]:
            for role in sc["cast_roles"]:
                role["identity_revision"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "cast-revision-missing" in c, (repr(bad), c[:3])
        assert "cast-revision-mismatch" not in c, (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)

        # one side only
        p = workshop_plan()
        p["scenes"][0]["cast_roles"][0]["identity_revision"] = bad
        assert "cast-revision-missing" in codes(SP.validate_scene_plan(p)), repr(bad)

        p = workshop_plan()
        p["foundation"]["episode_cast_manifest"]["cast"][0]["identity_revision"] = bad
        assert "cast-revision-missing" in codes(SP.validate_scene_plan(p)), repr(bad)


def test_foundation_pin_type_matrix_refused():
    """A pin carries a declared string revision/digest or it refuses."""
    for bad in BAD_REVISIONS:
        p = workshop_plan()
        p["foundation_revisions"]["research_bundle"]["digest"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "foundation-revision-undigested" in c, (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)

        p = workshop_plan()
        p["foundation"]["research_bundle"]["digest"] = bad
        p["foundation_revisions"]["research_bundle"]["digest"] = bad
        c = codes(SP.validate_scene_plan(p))
        assert "artifact-digest-missing" in c, (repr(bad), c[:3])
        assert SP.music_gate(p)["allowed"] is False, repr(bad)


def test_zero_never_satisfies_false():
    """The exact bypass family: 0 == False cross-matched one value."""
    for world_rev, scene_rev, pin_rev in ((False, 0, 0), (0, False, 0),
                                          (False, False, 0), (0.0, False, False),
                                          (False, 0.0, 0.0)):
        p = workshop_plan()
        p["foundation"]["episode_world"]["revision"] = world_rev
        p["foundation_revisions"]["episode_world"]["revision"] = pin_rev
        for sc in p["scenes"]:
            sc["world_revision"] = scene_rev
        res = SP.validate_scene_plan(p)
        c = codes(res)
        assert res["outcome"] == "rejected", (world_rev, scene_rev, c[:3])
        assert SP.music_gate(p)["allowed"] is False, (world_rev, scene_rev)
        assert ("world-revision-missing" in c or "world-revision-unbound" in c), \
            (world_rev, scene_rev, c[:3])


def test_declared_string_revisions_still_match():
    """Control: legitimate string revisions match exactly and the gate opens."""
    ok = workshop_plan()
    assert SP.validate_scene_plan(ok)["outcome"] == "ok"
    assert SP.music_gate(ok)["allowed"] is True

    for rev in ("rev-17", "false", "0", "1"):
        p = workshop_plan()
        p["foundation"]["episode_world"]["revision"] = rev
        p["foundation_revisions"]["episode_world"]["revision"] = rev
        for sc in p["scenes"]:
            sc["world_revision"] = rev
        res = SP.validate_scene_plan(p)
        assert res["outcome"] == "ok", (rev, res["errors"][:3])
        assert SP.music_gate(p)["allowed"] is True, rev

    # a stale but DECLARED revision is a mismatch, not an absence
    p = workshop_plan()
    p["scenes"][0]["world_revision"] = "rev-17"
    p["scenes"][1]["world_revision"] = "rev-17"
    assert "world-revision-mismatch" in codes(SP.validate_scene_plan(p))


def test_non_dict_artifacts_refuse_by_name():
    """A non-object artifact is a NAMED refusal, never an AttributeError."""
    for name, kw in (("episode_cast_manifest", "cast_manifest"),
                     ("episode_world", "world"),
                     ("research_bundle", "research")):
        res = SP.validate_scene_plan(workshop_plan(), **{kw: "not-an-object"})
        assert res["outcome"] == "rejected", name
        assert "artifact-not-an-object" in codes(res), (name, codes(res)[:3])
        gate = SP.music_gate(workshop_plan(), **{kw: ["not-an-object"]})
        assert gate["allowed"] is False, name

    p = workshop_plan()
    p["foundation"]["episode_world"] = 7
    assert "artifact-not-an-object" in codes(SP.validate_scene_plan(p))

    p = workshop_plan()
    p["foundation"]["character_identity_library_snapshot"] = "oops"
    assert SP.validate_scene_plan(p)["outcome"] == "rejected"

    p = workshop_plan()
    p["foundation_revisions"]["episode_world"] = "oops"
    assert "foundation-revision-unpinned" in codes(SP.validate_scene_plan(p))

    # the authoring path names the refusal too, and dispatches nothing
    calls = {"n": 0}

    def counting_submit(request):
        calls["n"] += 1
        return {"scenes": []}

    f = workshop_foundation()
    f["episode_cast_manifest"] = ["not-an-object"]
    out = SP.build_scene_plan(f, BEATS, counting_submit, attempt_key="att-obj")
    assert out["outcome"] == "rejected" and out.get("dispatched") is False, out["reason_code"]
    assert calls["n"] == 0, calls["n"]
    assert "artifact-not-an-object" in [e["error"] for e in out["errors"]], out["errors"][:2]


def test_empty_research_claims_still_block_before_dispatch():
    """Empty research claims block the writer BEFORE any submit, calls=0."""
    calls = {"n": 0}

    def counting_submit(request):
        calls["n"] += 1
        return {"scenes": []}

    f = workshop_foundation()
    f["research_bundle"]["claims"] = []
    out = SP.build_scene_plan(f, BEATS, counting_submit, attempt_key="att-claims")
    assert out["outcome"] == "rejected" and out.get("dispatched") is False, out["reason_code"]
    assert "research-claims-empty" in [e["error"] for e in out["errors"]], out["errors"][:2]
    assert calls["n"] == 0, calls["n"]


TESTS = [v for k, v in sorted(globals().items())
         if k.startswith("test_") and callable(v)]


def run():
    """Selftest entry point (`python3 story_planner.py selftest`)."""
    fails = []
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report and keep going
            fails.append("%s: %s" % (fn.__name__, exc))
            print("FAIL: %s (%s)" % (fn.__name__, exc))
        else:
            print("ok: %s" % fn.__name__)
    print()
    if fails:
        print("FAILED %d test(s)" % len(fails))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
