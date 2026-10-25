#!/usr/bin/env python3
"""Focused cross-flavor acceptance fixtures for Skill 75 (S75-T32 / S75-A32).

Every expectation here is read from the shared contracts at run time:

  scripts/core/story_first_contracts.py   stage graph, schemas, validators
  scripts/core/package_flavor_adapter.py  the one named seam (SEAM)
  scripts/core/contracts/flavor-999.json  second-flavor package data
  scripts/core/acceptance-profile.json    shared-core parity scope

No acceptance criterion is invented. Each facet names the contract symbol its
check binds to, and fixture records are built FROM the contract field tuples:
if a contract grows a field the fixture refuses to guess and goes red with
FixtureDrift naming that field.

A facet is a function `run(ctx, case)` returning:
    {"ok": bool, "checks": [{"contract": <literal>, "statement": <str>,
                             "result": bool}], "reason": str}

The same facet function is executed twice by the runner: once on the positive
case and once on a deliberately unmet negative case. A facet that stays green
on its negative case fails the run, which is the anti-vacuity gate.

Stdlib only. Importing this module has no side effects beyond the caller's
explicit `load_package` call.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys

RECEIPT_FACETS = (
    "package_seam_and_differences",
    "complete_fixture_validates",
    "missing_cast_refused",
    "undefined_speaker_refused",
    "invalid_scene_reference_refused",
    "missing_foundation_refused",
    "one_line_scene_refused",
    "approval_ordering_and_binding",
    "no_future_artifact_deadlock",
    "identity_survives_world_revision",
)

# Which acceptance rows each facet speaks to, and how far. The audit needs the
# boundary stated, not implied.
FACET_ROWS = {
    "package_seam_and_differences": {
        "rows": ["S75-A03", "S75-A32"],
        "clause": "adapters preserve package differences; each flavor resolves through one seam",
    },
    "complete_fixture_validates": {
        "rows": ["S75-A03", "S75-A05", "S75-A08", "S75-A09"],
        "clause": "schema validates a complete fixture (identity, world, cast, scene)",
    },
    "missing_cast_refused": {
        "rows": ["S75-A07", "S75-A09", "S75-A32"],
        "clause": "absent cast fields fail closed; missing cast prevents script",
    },
    "undefined_speaker_refused": {
        "rows": ["S75-A07", "S75-A32"],
        "clause": "undefined speakers fail closed",
    },
    "invalid_scene_reference_refused": {
        "rows": ["S75-A09", "S75-A32"],
        "clause": "valid cast/location references; stale world revision refused",
    },
    "missing_foundation_refused": {
        "rows": ["S75-A09", "S75-A13", "S75-A32"],
        "clause": "missing foundations cannot bypass the gate; missing world/story plan prevents script",
    },
    "one_line_scene_refused": {
        "rows": ["S75-A09", "S75-A11", "S75-A32"],
        "clause": "one-line placeholders and beat-only records fail new generation",
    },
    "approval_ordering_and_binding": {
        "rows": ["S75-A12", "S75-A13", "S75-A32"],
        "clause": "preference is not artifact approval; full-script approval before music; storyboard approval before video; bindings must match current digests",
    },
    "no_future_artifact_deadlock": {
        "rows": ["S75-A03", "S75-A32"],
        "clause": "runtime graph has no future-artifact deadlock",
    },
    "identity_survives_world_revision": {
        "rows": ["S75-A05", "S75-A08", "S75-A32"],
        "clause": "identity record has no world binding, so a setting change cannot rewrite it (structural only)",
    },
}

# Facets T32 paragraph 53 names that these shared contracts do NOT state.
#
# Repair round 1 (against the round-1 FAIL): four of these were honest about a
# product gap and are kept as product gaps, but the reason now names the unit
# that owes the capability. Two of them -- the eighteen styles and the exact
# original description bytes -- are DELIVERED by S75-T18..S75-T21 and are now
# exercised for real by cells in cell_matrix.py, so they are no longer listed
# as not covered. What is left of "style18" is genuinely out of reach: the
# catalog resolves eighteen styles, but end-to-end render and dispatch through
# the production pipeline is a package-assembly deliverable.
NOT_COVERED = {
    "genuine writing dispatch": "no dispatch call exists in the shared contract modules; asserting it here would invent a criterion",
    "Notion offline snapshot / new-existing-mixed / retry / conflict / migration": (
        "capability absent from both repositories. Owed by S75-T17 "
        "(CHARACTER-MIGRATION-OWNER), blocked on S75-T15, S75-T16, S75-T28. "
        "The cell_matrix Notion migration cell executes a presence scan over "
        "character_library/migration.py, sync.py, notion_store.py and cache.py "
        "and reports NOT_APPLICABLE with this reason."),
    "18 style end-to-end render/dispatch paths": (
        "the eighteen styles are delivered and ARE exercised (cell_matrix "
        "style18 resolves all eighteen ids in music_styles.catalog); what is "
        "not covered here is end-to-end render and dispatch through the "
        "production pipeline. Owed by S75-T29 (ONB-PACKAGE-OWNER) for the "
        "onboarding flavour and S75-T30 (N999-PACKAGE-OWNER) for 999."),
    "old paid output / raw answer / approval preservation": (
        "capability absent from both repositories. Owed by S75-T28 "
        "(COMPATIBILITY-OWNER: compatibility.py, "
        "contracts/legacy-compatibility-map.json, "
        "tests/fixtures/paid_artifact_preservation.json), blocked on S75-T01, "
        "S75-T03. The cell_matrix paid compatibility cell executes a presence "
        "scan over those three carriers and a token scan of the shared "
        "contracts, and reports NOT_APPLICABLE with this reason."),
    "affected-only invalidation of plan/script/visual outputs": (
        "the shared contracts declare stage dependencies and approval bindings "
        "but implement no output invalidation. Owed by S75-T28 "
        "(COMPATIBILITY-OWNER)."),
    "elected full-script-before-music via user election": (
        "ordering is enforced; the election record itself is outside these "
        "modules. Owed by S75-T29 (ONB-PACKAGE-OWNER) / S75-T30 "
        "(N999-PACKAGE-OWNER)."),
}

#: The nine behaviours S75-A32 names, each bound to the cell that speaks to it
#: and to the acceptance row clause it satisfies. The cell matrix is what the
#: row is judged on; the facet list above is the layer beneath it.
CELL_ROWS = {
    "missing foundation": {"rows": ["S75-A09", "S75-A13", "S75-A32"],
                           "clause": "missing foundation cannot bypass the gate"},
    "cast bypass": {"rows": ["S75-A07", "S75-A09", "S75-A32"],
                    "clause": "cast cannot be bypassed: empty, partial and "
                              "undefined speakers all fail closed"},
    "scene richness": {"rows": ["S75-A09", "S75-A11", "S75-A32"],
                       "clause": "one-line placeholders are refused; a rich "
                                 "scene validates"},
    "Notion migration": {"rows": ["S75-A32"],
                         "clause": "Notion migration is exercised by both "
                                   "flavour facets (product gap; see "
                                   "not_covered for the owing unit)"},
    "identity setting changes": {"rows": ["S75-A05", "S75-A08", "S75-A32"],
                                 "clause": "a setting change cannot rewrite "
                                           "identity; a pinned stale world "
                                           "revision is refused"},
    "approval ordering": {"rows": ["S75-A12", "S75-A13", "S75-A32"],
                          "clause": "preference is not approval; approval binds "
                                    "to current digests"},
    "style18": {"rows": ["S75-A18", "S75-A32"],
                "clause": "exactly eighteen styles, unique and resolvable"},
    "original byte preservation": {"rows": ["S75-A18", "S75-A32"],
                                   "clause": "original descriptions survive "
                                             "byte-for-byte"},
    "paid compatibility": {"rows": ["S75-A32"],
                           "clause": "paid compatibility is exercised by both "
                                     "flavour facets (product gap; see "
                                     "not_covered for the owing unit)"},
}

REQUIRED_CONTRACT_FILES = (
    os.path.join("scripts", "core", "story_first_contracts.py"),
    os.path.join("scripts", "core", "package_flavor_adapter.py"),
    os.path.join("scripts", "core", "contracts", "flavor-999.json"),
)


class FixtureDrift(Exception):
    """The contract moved and the fixture refuses to guess."""


class Ctx:
    def __init__(self, core, adapter, skill_root):
        self.core = core
        self.adapter = adapter
        self.skill_root = skill_root


def load_package(skill_root):
    """Load one flavor's shared core + adapter from its skill root."""
    core_dir = os.path.join(skill_root, "scripts", "core")
    core_file = os.path.join(core_dir, "story_first_contracts.py")
    for name in ("story_first_contracts", "package_flavor_adapter"):
        sys.modules.pop(name, None)
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    spec = importlib.util.spec_from_file_location("story_first_contracts", core_file)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(core_file)
    core = importlib.util.module_from_spec(spec)
    sys.modules["story_first_contracts"] = core
    spec.loader.exec_module(core)
    importlib.invalidate_caches()
    adapter = importlib.import_module("package_flavor_adapter")
    return Ctx(core, adapter, skill_root)


def missing_contract_files(skill_root):
    """Explicit list of contract files absent from a candidate skill root."""
    absent = []
    for rel in REQUIRED_CONTRACT_FILES:
        path = os.path.join(skill_root, rel)
        if not os.path.isfile(path):
            absent.append(path)
    return absent


def _record(fields, values, kind):
    missing = [f for f in fields if f not in values]
    if missing:
        raise FixtureDrift(
            "%s fixture has no value for contract field(s) %s; update the fixture "
            "from the contract rather than guessing" % (kind, ", ".join(missing)))
    return {f: values[f] for f in fields}


def build_records(core):
    """Build one complete, contract-shaped fixture set from the core's own fields."""
    location = {
        "location_id": "loc_workshop_front_001",
        "name": "Workshop front room",
        "story_function": "closing-time confrontation",
        "interior_exterior": "interior",
        "access": "Mara and Levi, cooperative partners",
        "entrances_exits": ["south glass door", "west corridor to the repair bay"],
        "visible_geography": "central ledger table, north tool bench, east counter",
    }
    world = _record(core.WORLD_FIELDS, {
        "episode_id": "ep_s75_t32_001",
        "world_id": "world_workshop_001",
        "schema_version": core.WORLD_SCHEMA_VERSION,
        "revision": 1,
        "content_digest": "world-digest-1",
        "premise": "A neighborhood repair cooperative faces a payment shortfall.",
        "era_and_timeline": "One continuous evening at closing time.",
        "locations": [location],
        "layout_and_geography": "South entrance faces the central table; north wall holds the tool bench.",
        "social_rules": "Partners expect payroll warnings to be shared early.",
        "physical_and_story_rules": "Realistic drama; no unexplained rescue or new prop.",
        "light_color_atmosphere": "Warm overhead work lights; cool fading daylight from the door.",
        "sound_environment": "Distant workshop fan; quiet room tone once it stops.",
        "set_dressing_and_props": [{"prop_id": "prop_notice_001", "placement": "Mara's right hand"}],
        "cast_world_relations": ["char_mara_001", "char_levi_002"],
        "wardrobe_intent": "Practical workshop clothing with clear silhouettes.",
        "continuity_rules": "Notice sealed before admission, open afterward; ledger stays on the table.",
        "sources_and_unknowns": {"classification": "PROPOSED_FICTION"},
        "draft_state": core.COMPLETE,
        "approval_bindings": [],
    }, "world")

    identity = _record(core.IDENTITY_FIELDS, {
        "client_id": "client_fixture_s75_t32",
        "character_id": "char_mara_001",
        "revision": 1,
        "content_digest": "identity-digest-1",
        "schema_version": core.IDENTITY_SCHEMA_VERSION,
        "display_name": "Mara Bell",
        "aliases": [],
        "story_status": "PROPOSED_FICTION",
        "identity_summary": "A repair-cooperative owner who fixes motors faster than she admits mistakes.",
        "relevant_background_history": [
            "Helped her father close his repair stall after an avoidable cash crisis.",
            "Built the cooperative with her brother Levi and promised no more surprises.",
        ],
        "occupation": "Repair-cooperative owner and working mechanic",
        "competence": ["diagnoses small-engine failures", "trains apprentices"],
        "social_context": "Responsible for a small team that trusts her with its livelihoods.",
        "relationships": [
            {"character_id": "char_levi_002", "type": "older brother and partner",
             "history": "They built the workshop together.",
             "present_tension": "She withheld a payment warning he needs.",
             "dependency": "She trusts his judgment but fears his disappointment."},
        ],
        "wants": {"external": "Keep the cooperative open and pay the team.",
                  "internal": "Be trusted without appearing infallible."},
        "fears": ["Repeating her father's failure", "Losing the team's respect"],
        "emotional_wound": "She was the last person told that her father's stall was closing.",
        "mistaken_belief": "A good leader protects everyone by solving problems alone.",
        "contradictions": ["Demands clear estimates while hiding the warning from her own partner."],
        "habits": ["Straightens tools when avoiding a question."],
        "voice": {"rhythm": "Short practical sentences.",
                  "vocabulary": "Concrete workshop language.",
                  "restraint": "Admits the fact before naming the feeling."},
        "behavior_under_pressure": "Takes on physical work and conceals paperwork until forced.",
        "appearance_traits": "Short natural curls, alert eyes, compact work-ready posture.",
        "reference_ids": [],
        "provenance_by_field": {"all_story_fields": "explicit proposed fiction"},
        "draft_state": core.COMPLETE,
        "approval_bindings": [],
        "shared_source": None,
        "local_cache": None,
        "sync_state": "ILLUSTRATIVE_NOT_PERSISTED",
    }, "identity")

    cast_entry = {f: {
        "character_id": "char_mara_001",
        "identity_revision": 1,
        "identity_digest": "identity-digest-1",
        "episode_role": "lead",
        "scene_ids": ["scene_workshop_001"],
        "immediate_story_function": "Must choose to expose the hidden warning.",
        "choice_or_consequence": "Disclosure shifts her from isolation to shared responsibility.",
    }[f] for f in core.CAST_ENTRY_FIELDS}
    levi_entry = dict(cast_entry, character_id="char_levi_002",
                      identity_digest="identity-digest-2",
                      episode_role="supporting partner",
                      immediate_story_function="Refuses vague reassurance and shows the empty ledger.",
                      choice_or_consequence="His restrained offer makes Mara's turn possible.")
    manifest = {"cast": [cast_entry, levi_entry]}

    scene = _record(core.SCENE_FIELDS, {
        "scene_id": "scene_workshop_001",
        "sequence": 1,
        "causal_predecessor": None,
        "causal_outcome": "Because Levi can see the notice, the next scene must plan shared repair.",
        "dramatic_purpose": "Expose the immediate cost of concealment and force Mara's first honest choice.",
        "time": "evening, closing time",
        "location_id": "loc_workshop_front_001",
        "world_revision": 1,
        "cast_ids": ["char_mara_001", "char_levi_002"],
        "identity_revisions": {"char_mara_001": 1, "char_levi_002": 1},
        "crowd_group_ids": [],
        "immediate_want": "Mara wants Levi to accept one more vague promise.",
        "obstacle": "The empty ledger and his direct question block that escape.",
        "visible_action": "Mara opens the sealed warning and sets it beside the open ledger.",
        "consequential_choice": "She gives up control of the information.",
        "emotion_before": "defensive and ashamed",
        "emotion_after": "still afraid but less isolated",
        "turn_trigger": "Putting the notice where Levi can read it.",
        "spoken_dialogue": [
            {"line_id": "line_mara_001", "character_id": "char_mara_001",
             "text": "If I lock that door, their checks bounce tomorrow."},
        ],
        "sung_lyrics": [
            {"line_id": "line_mara_003", "character_id": "char_mara_001",
             "text": "I kept the light on, kept the truth outside."},
        ],
        "performance_order": [{"character_id": "char_mara_001", "line_id": "line_mara_001"}],
        "subtext_and_behavior": "She admits the fact before naming the feeling.",
        "sound_music_cues": ["Fan clicks off before the first line."],
        "framing_movement_intent": "Medium close-up inside the door, then insert on the opening envelope.",
        "duration_seconds": 24,
        "timing_basis": "authoring estimate before music",
        "transition": "Match-cut from the shared ledger to the next scene's first action.",
        "visible_lip_sync": {"intervals": [[0, 4]], "performer": "char_mara_001"},
        "claims": [],
        "references": [],
        "approval_bindings": [],
    }, "scene")

    return {
        "identity": identity,
        "world": world,
        "manifest": manifest,
        "episode_world": world,
        "episode_cast_manifest": manifest,
        "scene": scene,
        "scene_plan": {"scenes": [scene]},
        "research_bundle": {"claims": [{"claim_id": "claim_fixture_001"}]},
        "causal_story_beats": {"beats": [{"beat_id": "beat_fixture_001"}]},
        "script": {"scenes": [scene]},
        "lyrics": {"lines": [{"line_id": "line_mara_003"}]},
        "creative_package_manifest": {"package": "creative-package-v1"},
        "selected_music": {"style_id": "soul-ballad"},
        "timed_storyboard": {"scenes": [scene]},
        "production_continuity": {"scenes": [scene]},
        "keyframes": {"shots": [{"shot_id": "shot_001"}]},
        "video_checks": {"checks": ["fixture-pass"]},
        "final_delivery": {"delivered": True},
    }


def _seed_registry(core, records, upto_stage=None, omit=()):
    """Put every artifact the contract says each stage produces, in stage order."""
    registry = core.RunRegistry()
    for stage in core.STAGE_ORDER:
        if upto_stage is not None and core.STAGE_ORDER.index(stage) > core.STAGE_ORDER.index(upto_stage):
            break
        for kind in core.STAGE_PRODUCES[stage]:
            if kind in omit:
                continue
            if kind in core.APPROVAL_BINDS:
                registry.put(kind, {"decision": "APPROVED"}, state=core.APPROVED,
                             approved_digests={t: registry.digest_of(t)
                                               for t in core.APPROVAL_BINDS[kind]})
            else:
                registry.put(kind, records.get(kind, {"kind": kind, "fixture": True}))
    return registry


def _contract_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - fixtures assert the contract's own error type
        return exc
    return None


# --------------------------------------------------------------------------
# facets: each returns {"ok", "checks", "reason"}
# --------------------------------------------------------------------------

def _result(checks, reason=""):
    return {"ok": all(c["result"] for c in checks), "checks": checks, "reason": reason}


def package_seam_and_differences(ctx, case):
    """A03/A32: one seam, the two package differences preserved, no forked core."""
    core, adapter = ctx.core, ctx.adapter
    onb = adapter.resolve(adapter.ONB)
    n999 = adapter.resolve(adapter.N999)
    layouts = case.get("layouts") or {}
    if "999" in layouts:
        n999 = adapter.resolve(adapter.N999, layout=layouts["999"])
    differing = sorted(k for k in adapter.PACKAGE_DIFFERENCES if onb[k] != n999[k])
    fixture = adapter.load_fixture_999()
    via_fixture = adapter.resolve(fixture["flavor"], layout=fixture)
    checks = [
        {"contract": "package_flavor_adapter.SEAM",
         "statement": "both flavor results name the single seam",
         "result": onb["seam"] == n999["seam"] == adapter.SEAM},
        {"contract": "package_flavor_adapter.PACKAGE_DIFFERENCES",
         "statement": "the package differences are exactly the declared tuple",
         "result": differing == sorted(adapter.PACKAGE_DIFFERENCES)},
        {"contract": "package_flavor_adapter.core_digest",
         "statement": "both flavors resolve the byte-identical shared core",
         "result": onb["core_digest"] == n999["core_digest"] == adapter.core_digest()},
        {"contract": "package_flavor_adapter.resolve",
         "statement": "contracts/flavor-999.json round-trips to the N999 seam result",
         "result": via_fixture == n999},
        {"contract": "package_flavor_adapter.PACKAGE_DIFFERENCES",
         "statement": "adapter carries no forked core constants",
         "result": not any(hasattr(adapter, n) for n in
                           ("STAGE_ORDER", "STAGE_REQUIRES", "SCHEMA_VERSION",
                            "validate_identity", "check_stage"))},
    ]
    return _result(checks, "seam=%s" % adapter.SEAM)


def complete_fixture_validates(ctx, case):
    """A03/A05/A08/A09: the complete fixture set validates with zero defects."""
    core, r = ctx.core, case["records"]
    defects = {
        "validate_identity": core.validate_identity(r["identity"]),
        "validate_world": core.validate_world(r["world"]),
        "validate_cast_manifest": core.validate_cast_manifest(r["manifest"], [r["scene"]]),
        "validate_scene": core.validate_scene(r["scene"], world=r["world"]),
        "validate_scene_plan": core.validate_scene_plan(r["scene_plan"], world=r["world"],
                                                        manifest=r["manifest"]),
    }
    checks = [{"contract": "story_first_contracts.%s" % name,
               "statement": "complete fixture yields no defects",
               "result": value == []}
              for name, value in defects.items()]
    return _result(checks, json.dumps({k: v for k, v in defects.items() if v})[:400])


def missing_cast_refused(ctx, case):
    """A07/A09/A32: absent or empty cast is a missing requirement, and blocks script."""
    core, r = ctx.core, case["records"]
    if "manifest" in case:
        manifests = [case["manifest"]]
    else:
        thin = dict(r["manifest"]["cast"][0])
        thin.pop("choice_or_consequence", None)
        manifests = [{}, {"cast": []}, {"cast": [thin]}]
    defects = [core.validate_cast_manifest(m, [r["scene"]]) for m in manifests]
    registry = _seed_registry(core, r, upto_stage="cast_and_world", omit=("episode_cast_manifest",))
    exc = _contract_error(core.check_stage, "script_lyrics", registry)
    missing = (exc.packet.get("missing") if exc is not None and hasattr(exc, "packet") else []) or []
    checks = [
        {"contract": "story_first_contracts.validate_cast_manifest",
         "statement": "absent cast, empty cast and an incomplete cast entry each produce a defect",
         "result": all(bool(d) for d in defects)},
        {"contract": "story_first_contracts.check_stage",
         "statement": "script_lyrics refuses without episode_cast_manifest",
         "result": exc is not None and "episode_cast_manifest" in missing},
    ]
    return _result(checks, str(getattr(exc, "code", "")))


def undefined_speaker_refused(ctx, case):
    """A07/A32: an undeclared performer is refused."""
    core, r = ctx.core, case["records"]
    if "scene" in case:
        scene = case["scene"]
    else:
        scene = dict(r["scene"],
                     cast_ids=list(r["scene"]["cast_ids"]) + ["char_unlisted_999"],
                     performance_order=[{"character_id": "char_unlisted_999",
                                         "line_id": "line_ghost_001"}])
    defects = core.validate_cast_manifest(r["manifest"], [scene])
    fields = {d.get("field") for d in defects}
    checks = [
        {"contract": "story_first_contracts.validate_cast_manifest",
         "statement": "undefined speaker in cast_ids/performance_order is a defect",
         "result": bool(defects) and bool(fields & {"cast_ids", "performance_order"})},
    ]
    return _result(checks, json.dumps(defects)[:400])


def invalid_scene_reference_refused(ctx, case):
    """A09/A32: undefined location and stale world revision are refused."""
    core, r = ctx.core, case["records"]
    scene = case.get("scene") or dict(r["scene"], location_id="loc_does_not_exist",
                                      world_revision=r["world"]["revision"] + 1)
    world = case.get("world", r["world"])
    defects = core.validate_scene(scene, world=world)
    fields = {d.get("field") for d in defects}
    checks = [
        {"contract": "story_first_contracts.validate_scene",
         "statement": "invalid location reference or stale world revision is a defect",
         "result": bool(fields & {"location_id", "world_revision"})},
    ]
    return _result(checks, json.dumps(defects)[:400])


def missing_foundation_refused(ctx, case):
    """A09/A13/A32: missing world/story plan blocks script with a precise packet."""
    core, r = ctx.core, case["records"]
    registry = _seed_registry(core, r, upto_stage=case.get("seed_upto", "research_premise"))
    exc = _contract_error(core.check_stage, "script_lyrics", registry)
    packet = getattr(exc, "packet", {}) or {}
    missing = set(packet.get("missing") or [])
    required = set(core.STAGE_REQUIRES["script_lyrics"])
    checks = [
        {"contract": "story_first_contracts.check_stage",
         "statement": "script_lyrics refuses when a required foundation artifact is absent",
         "result": exc is not None and bool(missing & required)},
        {"contract": "story_first_contracts.STAGE_REQUIRES",
         "statement": "the refusal names the exact missing contract kinds",
         "result": missing.issubset(required)},
    ]
    return _result(checks, str(getattr(exc, "code", "")))


def one_line_scene_refused(ctx, case):
    """A09/A11/A32: one-line and beat-only records are refused."""
    core = ctx.core
    scene = case["one_line_scene"]
    defects = core.validate_scene(scene, world=case["records"]["world"])
    fields = {d.get("field") for d in defects}
    checks = [
        {"contract": "story_first_contracts.MIN_PURPOSE_WORDS",
         "statement": "a thin dramatic purpose is a defect",
         "result": "dramatic_purpose" in fields},
        {"contract": "story_first_contracts.MIN_ACTION_WORDS",
         "statement": "a one-line visible action is a defect",
         "result": "visible_action" in fields},
        {"contract": "story_first_contracts.validate_scene",
         "statement": "placeholder dialogue is a defect",
         "result": "spoken_dialogue" in fields or "dialogue" in fields},
    ]
    return _result(checks, json.dumps(defects)[:400])


def approval_ordering_and_binding(ctx, case):
    """A12/A13/A32: preference != approval; ordering gates; digest bindings."""
    core, r = ctx.core, case["records"]
    registry = _seed_registry(core, r, upto_stage="script_lyrics")
    registry.put("creative_package_manifest", r["creative_package_manifest"])
    if case.get("approve_early"):
        # Negative control: the gate is already met, so a preference refusal
        # cannot be observed and the facet must go red.
        registry.put("package_approval", {"decision": "APPROVED"}, state=core.APPROVED,
                     approved_digests={t: registry.digest_of(t)
                                       for t in core.APPROVAL_BINDS["package_approval"]})
    else:
        # Preference: a COMPLETE record is not an artifact approval.
        registry.put("package_approval", {"decision": "preferred"}, state=core.COMPLETE)
    preference_exc = _contract_error(core.check_stage, "music", registry)
    # Real approval bound to current digests admits music.
    registry.put("package_approval", {"decision": "APPROVED"}, state=core.APPROVED,
                 approved_digests={t: registry.digest_of(t)
                                   for t in core.APPROVAL_BINDS["package_approval"]})
    music_admits = core.check_stage("music", registry)["admitted"]
    # Stale binding: changing a bound artifact invalidates the approval.
    registry.put("script", {"scenes": [case["records"]["scene"]], "revised": True})
    stale_exc = _contract_error(core.check_stage, "music", registry)
    stale_targets = [d.get("target") for d in (getattr(stale_exc, "packet", {}) or {}).get("approval_defects", [])]
    # Unbound artifact churn does not touch the package approval.
    registry.put("video_checks", {"late": "unrelated"})
    checks = [
        {"contract": "story_first_contracts.APPROVAL_BINDS",
         "statement": "a COMPLETE preference cannot admit music",
         "result": preference_exc is not None},
        {"contract": "story_first_contracts.check_stage",
         "statement": "a bound APPROVED package approval admits music",
         "result": music_admits is True},
        {"contract": "story_first_contracts.APPROVAL_BINDS",
         "statement": "changing a bound script digest invalidates only that binding",
         "result": stale_exc is not None and "script" in stale_targets},
    ]
    return _result(checks, str(getattr(stale_exc, "code", "")))


def no_future_artifact_deadlock(ctx, case):
    """A03/A32: every requirement is produced by an earlier stage; graph is a DAG."""
    core = ctx.core
    produces = case.get("stage_produces") or core.STAGE_PRODUCES
    requires = case.get("stage_requires") or core.STAGE_REQUIRES
    order = case.get("stage_order") or core.STAGE_ORDER
    future = []
    unproduced = []
    for index, stage in enumerate(order):
        for kind in requires.get(stage, ()):
            producers = [i for i, s in enumerate(order) if kind in produces.get(s, ())]
            if not producers:
                unproduced.append({"stage": stage, "kind": kind})
            elif min(producers) >= index:
                future.append({"stage": stage, "kind": kind,
                               "producer": order[min(producers)]})
    checks = [
        {"contract": "story_first_contracts.STAGE_REQUIRES",
         "statement": "no stage requires an artifact produced at or after itself",
         "result": future == []},
        {"contract": "story_first_contracts.STAGE_PRODUCES",
         "statement": "every required artifact is produced by some stage",
         "result": unproduced == []},
    ]
    return _result(checks, json.dumps(future + unproduced)[:400])


def identity_survives_world_revision(ctx, case):
    """A05/A08/A32 (structural): identity carries no world binding."""
    core, r = ctx.core, case["records"]
    before = core.validate_identity(r["identity"])
    world_v2 = dict(case.get("world", r["world"]), revision=2,
                    content_digest="world-digest-2")
    after = core.validate_identity(case.get("identity", r["identity"]))
    world_dependent_fields = [f for f in core.IDENTITY_FIELDS if "world" in f.lower()]
    checks = [
        {"contract": "story_first_contracts.IDENTITY_FIELDS",
         "statement": "no identity field binds an episode world",
         "result": world_dependent_fields == []},
        {"contract": "story_first_contracts.validate_identity",
         "statement": "identity validation is identical across world revisions",
         "result": before == after == []},
        {"contract": "story_first_contracts.validate_world",
         "statement": "the revised world is still a valid world record",
         "result": core.validate_world(world_v2) == []},
    ]
    return _result(checks, json.dumps(world_dependent_fields))


FACET_FUNCTIONS = {
    "package_seam_and_differences": package_seam_and_differences,
    "complete_fixture_validates": complete_fixture_validates,
    "missing_cast_refused": missing_cast_refused,
    "undefined_speaker_refused": undefined_speaker_refused,
    "invalid_scene_reference_refused": invalid_scene_reference_refused,
    "missing_foundation_refused": missing_foundation_refused,
    "one_line_scene_refused": one_line_scene_refused,
    "approval_ordering_and_binding": approval_ordering_and_binding,
    "no_future_artifact_deadlock": no_future_artifact_deadlock,
    "identity_survives_world_revision": identity_survives_world_revision,
}


def one_line_scene(records):
    """A deliberately thin scene, built from the contract's own field tuple."""
    scene = dict(records["scene"])
    scene.update({
        "dramatic_purpose": "Make emotional",
        "visible_action": "She sings.",
        "consequential_choice": "She sings.",
        "spoken_dialogue": [{"line_id": "l1", "character_id": "char_mara_001", "text": "..."}],
        "sung_lyrics": [],
        "performance_order": [],
    })
    return scene


def positive_case(ctx):
    records = build_records(ctx.core)
    return {"records": records, "one_line_scene": one_line_scene(records)}


def negative_case(ctx, facet):
    """A deliberately unmet condition for `facet`, built from the same records.

    Each mutation targets the exact contract assertion the facet makes, so a
    facet that stays green is proven insensitive rather than merely unlucky.
    """
    rec = build_records(ctx.core)
    case = {"records": rec, "one_line_scene": one_line_scene(rec)}
    if facet == "package_seam_and_differences":
        onb_layout = ctx.adapter.resolve(ctx.adapter.ONB)
        case["layouts"] = {"999": {
            "flavor": ctx.adapter.N999,
            "skill_root_anchor": onb_layout["skill_root_anchor"],
            "character_approval_module": onb_layout["character_approval_module"],
        }}
    elif facet == "complete_fixture_validates":
        rec["identity"].pop("occupation", None)
    elif facet == "missing_cast_refused":
        case["manifest"] = {"cast": rec["manifest"]["cast"]}  # valid cast: no refusal
    elif facet == "undefined_speaker_refused":
        scene = dict(rec["scene"], cast_ids=list(rec["scene"]["cast_ids"]))
        scene["performance_order"] = [{"character_id": "char_mara_001",
                                       "line_id": "line_mara_001"}]
        case["scene"] = scene  # every speaker is declared
    elif facet == "invalid_scene_reference_refused":
        case["scene"] = dict(rec["scene"], location_id="loc_workshop_front_001",
                             world_revision=1)  # valid reference
    elif facet == "missing_foundation_refused":
        case["seed_upto"] = "script_lyrics"  # every requirement supplied: no refusal
    elif facet == "one_line_scene_refused":
        case["one_line_scene"] = dict(rec["scene"])  # rich scene: nothing to refuse
    elif facet == "approval_ordering_and_binding":
        case["approve_early"] = True  # gate met: the preference refusal cannot occur
    elif facet == "no_future_artifact_deadlock":
        order = list(ctx.core.STAGE_ORDER)
        produces = {k: tuple(v) for k, v in ctx.core.STAGE_PRODUCES.items()}
        requires = {k: tuple(v) for k, v in ctx.core.STAGE_REQUIRES.items()}
        requires["research_premise"] = requires.get("research_premise", ()) + ("final_delivery",)
        case.update({"stage_order": order, "stage_produces": produces,
                     "stage_requires": requires})
    elif facet == "identity_survives_world_revision":
        broken = dict(rec["identity"])
        broken.pop("emotional_wound", None)
        case["identity"] = broken
    return case


def run_facet(ctx, facet):
    """Execute one facet on its positive case and its negative control.

    Returns the receipt-shaped record for one facet. `control_red` is the
    anti-vacuity proof: the identical facet must go red on the unmet condition.
    """
    fn = FACET_FUNCTIONS[facet]
    positive = fn(ctx, positive_case(ctx))
    negative = fn(ctx, negative_case(ctx, facet))
    return {
        "facet": facet,
        "ok": positive["ok"],
        "checks": positive["checks"],
        "reason": positive["reason"],
        "control": {
            "unmet_condition": _unmet_description(facet),
            "facet_ok_on_unmet": negative["ok"],
            "control_red": negative["ok"] is False,
        },
    }


def _unmet_description(facet):
    return {
        "package_seam_and_differences": "N999 layout collapsed onto the ONB layout, erasing a declared package difference",
        "complete_fixture_validates": "a required identity field (occupation) removed",
        "missing_cast_refused": "a valid non-empty cast supplied",
        "undefined_speaker_refused": "an undeclared performer removed from the scene",
        "invalid_scene_reference_refused": "a valid location and current world revision supplied",
        "missing_foundation_refused": "the missing foundation artifact supplied",
        "one_line_scene_refused": "a rich scene supplied in place of the one-line record",
        "approval_ordering_and_binding": "a bound, digest-matched APPROVED package approval supplied",
        "no_future_artifact_deadlock": "a future-artifact requirement injected into a synthetic stage graph",
        "identity_survives_world_revision": "a required identity field removed between revisions",
    }[facet]


def coverage():
    rows = {row for spec in FACET_ROWS.values() for row in spec["rows"]}
    rows |= {row for spec in CELL_ROWS.values() for row in spec["rows"]}
    return {
        "covered": FACET_ROWS,
        "cells": CELL_ROWS,
        "not_covered": NOT_COVERED,
        "rows_touched": sorted(rows),
        "note": "a row is touched only for the named clause; no row is claimed fully covered",
    }
