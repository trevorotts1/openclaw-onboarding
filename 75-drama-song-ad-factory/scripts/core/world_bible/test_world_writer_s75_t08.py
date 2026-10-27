#!/usr/bin/env python3
"""S75-T08: episode-world authoring, kept separate from reusable identity.

Run: python3 test_world_writer_s75_t08.py

Generic proposed fiction only -- no client name, no real business and no real
institution appears anywhere in the fixture or the code.

The suite proves:
  * a complete world authors through a proven dispatch, validates and seals to a
    stable digest;
  * the three SEMANTIC refusals fire by name with the offending field:
    a layout/action contradiction, an impossible timeline and an unsupported
    real-location claim, each with its accepted neighbouring valid case;
  * a world with NO locations or NO light doctrine is refused;
  * a scene pointing at an undefined location is refused;
  * a world that copies reusable identity fields into ``cast_refs`` is refused;
  * the authoring dispatch runs through the existing supported model layer with
    a deterministic no-spend transport capturing request and response provenance,
    and refuses to proceed when the dispatch cannot be proven;
  * authoring CANNOT be forged from files: a hand-written model-bindings.json
    alone, a response fixture alone, and the two together all refuse to seal,
    while a genuine injected no-spend transport seals -- because the seal is
    bound to a live dispatch handle that only a real call in THIS run returns;
  * changing the setting bumps the world revision, preserves every character
    identity ID verbatim and invalidates only plan/script/visual outputs;
  * world drafting carries no music or image prerequisite.

Round four attacks the CAPABILITY rather than the files: a reachability matrix
of every route to a handle that seals without a real transport call (the public
constructor, ``__new__``, subclasses that bypass or override ``__init__``, the
registry dict and its copies, deepcopy, pickle, a consumed handle, handle-field
rewrites, transport-kind rewrites, and every public attribute of the module and
the two classes), plus the two claims that must be DERIVED rather than asserted:
``execution`` from the transport kind that minted the handle, and
``attempt.binding_id`` recomputed from the admitted binding so a hand-forged
model-bindings.json can never have its chosen id echoed into a sealed record.
Round four's location half is also proven here: a location record must CARRY
era, social rules, lighting, layout and continuity boundaries as content --
placeholder text, a value that repeats its own field name and a repeated entry
are refused as loudly as an absent field -- while every legitimate world,
setting change and dispatch is still accepted (see Round4LocationSubstanceTests
and Round4OverRefusalTests).
"""
import copy
import hashlib
import json
import os
# pickle is used only on an object this process created, to prove an unpickled
# copy is never a live handle. Nothing here loads pickled data from a file.
import pickle
import sys
import tempfile
import unittest
import contextlib
import io

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from world_bible import world_writer as WW  # noqa: E402
from choice_card.intake_card import ai_models as AM  # noqa: E402

#: The recommended catalog pair; the checker stays independent of the builder.
BUILD_MODEL = "openrouter/xiaomi/mimo-v2.6-pro"
CHECK_MODEL = "openrouter/z-ai/glm-5.3"
#: Fixed clock so two identical fixture dispatches capture identical provenance.
FIXTURE_NOW = "2026-10-24T00:00:00+00:00"
#: Exact input artifact revisions the authoring dispatch receives.
FIXTURE_INPUTS = {
    "research_revision": "research_claims@1",
    "premise_revision": "premise@1",
    "cast_interface": ["char_mara_001@3", "char_levi_001@2"],
    "route_style_constraints": "realistic human drama",
    "known_locations": ["loc_workshop_front_001"],
    "owner_answer_refs": ["owner_answer_001"],
}


def fixture_body():
    return {
        "premise": ("A neighbourhood repair cooperative faces a payment shortfall. "
                    "Realistic human drama; admitting a hidden warning enables shared planning."),
        "fiction_classification": "proposed_fiction",
        "era": {"period": "contemporary", "time_of_day": "one continuous evening",
                "season_weather": "late spring, dry", "time_jumps": [], "span_minutes": 60},
        "locations": [
            {"location_id": "loc_workshop_front_001",
             "name": "Neighbourhood workshop, front area",
             "function": "the only room the scene plays in",
             "interior": True,
             "reality": "fiction",
             "access": "the two partners only",
             "entrances": ["south glass door"],
             "geography": "north tool bench, centre ledger table, east counter, west corridor",
             "era": {"period": "contemporary", "time_of_day": "one continuous evening"},
             "social_rules": [
                 {"rule": "no one signs the ledger on the other partner's behalf",
                  "consequence": "a line signed for another is crossed out and the count restarts"},
                 {"rule": "the sealed envelope stays shut until both are at the table",
                  "consequence": "opening it early ends the evening with nothing agreed"},
             ],
             "lighting": {"source": "overhead work lights above the ledger table",
                          "direction": "downward, warm and even",
                          "motivated_change": "the lights go off when the shop closes"},
             "layout": {"features": ["south glass door", "north tool bench",
                                     "centre ledger table", "east counter", "west corridor"],
                        "boundaries": "brick on three sides, the glazed shop front on the south",
                        "sightlines": "the ledger table is seen from the tool bench; the west "
                                      "corridor hides the south door"},
             "continuity_boundaries": {
                 "must_persist": ["the sealed envelope stays on the ledger table",
                                  "the tool bench keeps its shadow board"],
                 "may_change": ["the door sign after the scene earns it"],
             }},
        ],
        "light": {
            "doctrine": "warm overhead work lights against cool fading light from the south door; "
                        "no unexplained time-of-day change",
            "sources": [
                {"source": "overhead work lights", "direction": "downward, warm",
                 "motivated_change": "switched off when the shop closes"},
                {"source": "south glass door", "direction": "backlight, cool and fading"},
            ],
        },
        "palette": ["warm amber", "cool dusk blue", "worn timber brown"],
        "texture": ["oiled wood", "scuffed concrete", "paper envelope"],
        "sound": {"ambience": "soft room tone, a distant workshop fan",
                  "off_screen": ["fan stopping"], "silence": ["her first admission"]},
        "never_list": ["no miracle payment", "no additional people entering",
                       "no real bank document"],
        "cast_refs": [{"character_id": "char_mara_001", "identity_revision": 3},
                      {"character_id": "char_levi_001", "identity_revision": 2}],
        "continuity": {"must_persist": ["sealed envelope before the admission",
                                        "ledger stays on the table"],
                       "may_change": ["door sign after the scene earns it"],
                       "exceptions": []},
        "scenes": [{"scene_id": "scene_001", "location_id": "loc_workshop_front_001",
                    "action": "Mara crosses from the south door to the ledger table",
                    "uses": ["south glass door", "centre ledger table"],
                    "minutes_from_start": 0}],
    }


def place(location_id="loc_other_001", name="Other room", function="alternate setting",
          features=None, **overrides):
    """A complete location record: era, social rules, lighting, layout and
    continuity boundaries carried as content, never as shape alone. Stricter
    validation must still accept a real place (see Round4OverRefusalTests)."""
    features = list(features or ["a window"])
    built = {
        "location_id": location_id,
        "name": name,
        "function": function,
        "interior": True,
        "reality": "fiction",
        "access": "the two partners only",
        "entrances": [features[0]],
        "geography": "%s centre, the rest of the room around it" % features[0],
        "era": {"period": "contemporary", "time_of_day": "one continuous evening"},
        "social_rules": [
            {"rule": "only the people in the room may move what is on the table",
             "consequence": "anything moved without agreement is put back and said aloud"},
        ],
        "lighting": {"source": "the room's own overhead light",
                     "direction": "downward, warm and even"},
        "layout": {"features": features,
                   "boundaries": "walls on three sides and one door in the fourth",
                   "sightlines": "the table is seen from the door; the far corner hides it"},
        "continuity_boundaries": {
            "must_persist": ["what is on the table stays on the table"],
            "may_change": ["which chair is pulled out"],
        },
    }
    built.update(overrides)
    return built


def fixture_runner(body, requests):
    """Deterministic no-spend fixture runner: records the request it receives and
    answers with recorded response provenance. It never reaches a provider."""
    def runner(request):
        requests.append(copy.deepcopy(request))
        return {"raw": copy.deepcopy(body),
                "response_model": BUILD_MODEL,
                "resolved_provider_model": "xiaomi/mimo-v2.6-pro",
                "provider_job_id": "fixture-job-001"}
    return runner


def fixture_dispatch(body, run_dir=None, attempt_id="attempt_fixture_001", requests=None, ww=WW):
    """One no-spend dispatch through the supported model layer, on its own run dir.

    ``ww`` is the world_writer module the dispatch runs through. Most callers
    want this module's own binding; the pickle attack needs the module object
    pickle resolves by name (see attack_pickle_handle).
    """
    run_dir = run_dir or tempfile.mkdtemp(prefix="world_fixture_")
    if AM.load_bindings(run_dir) is None:
        bound = AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL,
                              runtime="claude-nine", now=FIXTURE_NOW)
        assert bound.get("ok"), bound
    requests = [] if requests is None else requests
    record = ww.dispatch_author(run_dir=run_dir, attempt_id=attempt_id, inputs=FIXTURE_INPUTS,
                                runner=ww.no_spend_transport(fixture_runner(body, requests)),
                                now=FIXTURE_NOW)
    return record, requests, run_dir


def author(body=None, revision=1):
    body = fixture_body() if body is None else body
    record, _, _ = fixture_dispatch(body)
    return WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                           revision=revision, dispatch=record)

def forged_bindings(run_dir):
    """A HAND-WRITTEN model-bindings.json: the run configuration any caller can
    put on disk. No bind_roles call produced it and no dispatch recorded it."""
    def row(mid, request_id, openclaw_id, role):
        return {"role_id": "forgedrole%s" % role, "model_id": mid, "request_id": request_id,
                "openclaw_id": openclaw_id, "route": "openrouter",
                "reasoning": {"supported": True, "effort_selector": False, "efforts": []},
                "bound_at": FIXTURE_NOW, "bound_by": "forged-by-hand",
                "dispatch": {"claude-nine": mid, "openclaw": openclaw_id,
                             "openrouter-direct": request_id, "runtime": "claude-nine",
                             "call_id": mid}}
    store = {"schema": AM.STORE_SCHEMA, "runtime": "claude-nine", "bound_at": FIXTURE_NOW,
             "bound_by": "forged-by-hand", "binding_id": "forgedbinding001", "attempts": [],
             "bindings": {"build": row(BUILD_MODEL, "xiaomi/mimo-v2.6-pro",
                                       "openrouter/xiaomi/mimo-v2.6-pro", "build"),
                          "check": row(CHECK_MODEL, "z-ai/glm-5.3",
                                       "openrouter/z-ai/glm-5.3", "check")}}
    path = os.path.join(run_dir, "model-bindings.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=1, sort_keys=True)
    return path

def forged_dispatch(body):
    """A provenance dict built entirely by hand: every field the proof checks
    ask for, and no dispatch anywhere in this run."""
    return {
        "operation": WW.DISPATCH_OPERATION,
        "handler": WW.DISPATCH_HANDLER,
        "prompt_template_revision": WW.PROMPT_TEMPLATE_REVISION,
        "execution": "no_spend_fixture",
        "inputs": copy.deepcopy(FIXTURE_INPUTS),
        "request": WW.build_author_request(FIXTURE_INPUTS),
        "request_receipt": "f" * 64,
        "response": {"response_model": BUILD_MODEL,
                     "resolved_provider_model": "xiaomi/mimo-v2.6-pro",
                     "response_provider": None, "provider_job_id": "forged-job-001",
                     "response_evidence": "response_metadata",
                     "router_receipt": "forged-router-receipt-001",
                     "raw_digest": "f" * 64},
        "attempt": {"attempt_id": "attempt_forged_001", "binding_id": "forgedbinding001",
                    "evidence": {"correlation": "f" * 64, "request_receipt": "f" * 64,
                                 "router_receipt": "forged-router-receipt-001",
                                 "response_evidence": "response_metadata"}},
        "seal": {"dispatch_handle": "f" * 64,
                 "receipt": {"transport_id": "forgedtransport", "kind": "no_spend",
                             "nonce": "f" * 32, "session": "f" * 64, "receipt_digest": "f" * 64}},
        "parsed_output": copy.deepcopy(body),
    }

def write_file_author_inputs(directory):
    """The two files a caller supplies to the CLI: the authoring inputs and a
    response fixture holding the world output and its claimed model ids."""
    inputs_path = os.path.join(directory, "inputs.json")
    fixture_path = os.path.join(directory, "response-fixture.json")
    with open(inputs_path, "w", encoding="utf-8") as handle:
        json.dump(FIXTURE_INPUTS, handle)
    with open(fixture_path, "w", encoding="utf-8") as handle:
        json.dump({"world": fixture_body(), "response_model": BUILD_MODEL,
                   "resolved_provider_model": "xiaomi/mimo-v2.6-pro",
                   "provider_job_id": "forged-job-001",
                   "router_receipt": "forged-router-receipt-001"}, handle)
    return inputs_path, fixture_path

def run_cli(args):
    """Run the CLI authoring surface and capture what it printed."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = WW.main(args)
    return code, err.getvalue()


# --- round 5: where this process's memory actually lives ----------------------
#
# The registries are no longer a module name. A caller that wants them has to
# walk the closure cells of the enforcement functions -- which is exactly the
# residue the round-5 report names as unclosable in CPython. These helpers take
# that walk ONCE so every attack below can aim at the real objects instead of a
# name that no longer exists.

def cell_value(fn, name):
    """The closure cell of ``fn`` holding ``name``, or None."""
    for free, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ()):
        if free == name:
            try:
                return cell.cell_contents
            except ValueError:  # empty cell
                return None
    return None


def enforcement_scope():
    """The private execution scope every enforcement function runs in. Nothing
    the honest path reads lives anywhere else."""
    return WW.dispatch_author.__globals__


def guard():
    return enforcement_scope()["_GUARD"]


def mint_callable():
    """The mint, reached the way a caller reaches it: through a closure cell of
    ``dispatch_author``."""
    return cell_value(WW.dispatch_author, "mint")


def registry_records():
    return cell_value(mint_callable(), "records")


def registry_sealed():
    return cell_value(type(guard()).__dict__["note_sealed"], "sealed")


def registry_transports():
    return cell_value(WW.dispatch_author, "transports")


def live_count():
    return guard().live_count()




class CompleteWorldTests(unittest.TestCase):
    def test_complete_world_authors_and_seals(self):
        record = author()
        self.assertEqual(record["kind"], WW.WORLD_KIND)
        self.assertEqual(record["schema_version"], WW.SCHEMA_VERSION)
        self.assertEqual(WW.validate(record), [])
        self.assertRegex(record["content_digest"], r"^[0-9a-f]{64}$")

    def test_digest_is_stable_and_sensitive(self):
        first = author()
        second = author()
        self.assertEqual(first["content_digest"], second["content_digest"])
        changed_body = fixture_body()
        changed_body["palette"].append("deep green")
        self.assertNotEqual(first["content_digest"], author(changed_body)["content_digest"])

    def test_world_has_no_music_or_image_prerequisite(self):
        record = author()
        for forbidden in ("music", "song", "keyframe", "image", "voice", "wardrobe"):
            self.assertNotIn(forbidden, record["dependencies"])

    def test_json_round_trip_keeps_digest(self):
        record = author()
        again = json.loads(json.dumps(record))
        self.assertEqual(WW.canonical_digest(again), record["content_digest"])
        self.assertEqual(WW.validate(again), [])


class ValidatorRefusalTests(unittest.TestCase):
    def assert_refused(self, body, needle):
        with self.assertRaises(WW.WorldError) as caught:
            author(body)
        joined = " | ".join(caught.exception.errors)
        self.assertIn(needle, joined)

    def test_no_locations_refused(self):
        body = fixture_body()
        body["locations"] = []
        del body["scenes"]
        self.assert_refused(body, "world has no locations")

    def test_missing_locations_section_refused(self):
        body = fixture_body()
        del body["locations"]
        del body["scenes"]
        self.assert_refused(body, "world has no locations")

    def test_no_light_doctrine_refused(self):
        body = fixture_body()
        del body["light"]["sources"]
        self.assert_refused(body, "world has no light doctrine")

    def test_empty_light_sources_refused(self):
        body = fixture_body()
        body["light"]["sources"] = []
        self.assert_refused(body, "world has no light doctrine")

    def test_light_without_doctrine_refused(self):
        body = fixture_body()
        del body["light"]["doctrine"]
        self.assert_refused(body, "light.doctrine is required")

    def test_undefined_location_reference_refused(self):
        body = fixture_body()
        body["scenes"] = [{"scene_id": "scene_001", "location_id": "loc_missing_001",
                           "action": "a beat plays", "uses": [], "minutes_from_start": 0}]
        self.assert_refused(body, "does not resolve to any location")

    def test_identity_leak_into_cast_refs_refused(self):
        body = fixture_body()
        body["cast_refs"][0]["background"] = "grew up on the coast"
        self.assert_refused(body, "reusable identity field")

    def test_empty_never_list_refused(self):
        body = fixture_body()
        body["never_list"] = []
        self.assert_refused(body, "never_list must be a non-empty list")

    def test_repeated_palette_value_refused(self):
        body = fixture_body()
        body["palette"] = ["warm amber", "warm amber"]
        self.assert_refused(body, "palette repeats a value")

    def test_missing_sound_refused(self):
        body = fixture_body()
        del body["sound"]["ambience"]
        self.assert_refused(body, "sound.ambience is required")


class SemanticRefusalTests(unittest.TestCase):
    """The three focused refusals: each fires by NAME with the offending field,
    and each has an accepted neighbouring valid case."""

    def assert_code_and_field(self, body, code, field):
        with self.assertRaises(WW.WorldError) as caught:
            author(body)
        named = [e for e in caught.exception.errors if code in e]
        self.assertTrue(named, "no %s in %s" % (code, caught.exception.errors))
        self.assertIn(field, named[0])

    def test_layout_action_contradiction_refused_by_name(self):
        body = fixture_body()
        body["scenes"][0]["uses"] = ["south glass door", "roof hatch"]
        self.assert_code_and_field(body, WW.CODE_LAYOUT_ACTION, "scenes[0].uses[1]")

    def test_impossible_timeline_refused_by_name(self):
        body = fixture_body()
        body["locations"].append(place(
            "loc_back_bay_001", "Repair bay, west corridor end",
            "the second room of the same evening",
            ["west corridor door", "repair bench"],
            access="the two partners only",
            era={"period": "contemporary", "time_of_day": "one continuous evening"}))
        # two different locations in the same minute, no explicit transition
        body["scenes"].append({"scene_id": "scene_002", "location_id": "loc_back_bay_001",
                               "action": "Levi steps into the bay", "uses": ["repair bench"],
                               "minutes_from_start": 0})
        self.assert_code_and_field(body, WW.CODE_IMPOSSIBLE_TIMELINE, "scenes[1].minutes_from_start")

    def test_timeline_backwards_without_transition_refused_by_name(self):
        body = fixture_body()
        body["scenes"].append({"scene_id": "scene_002", "location_id": "loc_workshop_front_001",
                               "action": "Mara returns to the door", "uses": ["south glass door"],
                               "minutes_from_start": 5})
        body["scenes"].append({"scene_id": "scene_003", "location_id": "loc_workshop_front_001",
                               "action": "an earlier beat plays", "uses": ["east counter"],
                               "minutes_from_start": 1})
        self.assert_code_and_field(body, WW.CODE_IMPOSSIBLE_TIMELINE, "scenes[2].minutes_from_start")

    def test_unsupported_real_location_claim_refused_by_name(self):
        body = fixture_body()
        body["locations"][0]["reality"] = "real"
        self.assert_code_and_field(body, WW.CODE_REAL_LOCATION, "locations[0].claim_source")

    def test_neighbouring_valid_cases_accepted(self):
        body = fixture_body()
        # a real place WITH a claim/source/owner-answer link is allowed
        body["locations"][0]["reality"] = "real"
        body["locations"][0]["claim_source"] = "owner_answer_001: the client named this address"
        # travel between two locations at increasing time is allowed
        body["locations"].append(place(
            "loc_back_bay_001", "Repair bay, west corridor end",
            "the second room of the same evening",
            ["west corridor door", "repair bench"],
            access="the two partners only",
            era={"period": "contemporary", "time_of_day": "one continuous evening"}))
        body["scenes"].append({"scene_id": "scene_002", "location_id": "loc_back_bay_001",
                               "action": "Levi carries the ledger to the bay bench",
                               "uses": ["repair bench"], "minutes_from_start": 15})
        # a backwards jump with an explicit transition is allowed
        body["scenes"].append({"scene_id": "scene_003", "location_id": "loc_workshop_front_001",
                               "action": "a flash back to the admission at the table",
                               "uses": ["centre ledger table"], "minutes_from_start": 0,
                               "transition": "deliberate flashback, motivated by the admission"})
        record = author(body)
        self.assertEqual(WW.validate(record), [])


class DispatchProvenanceTests(unittest.TestCase):
    def test_dispatch_captures_request_and_response_provenance(self):
        body = fixture_body()
        dispatch, requests, run_dir = fixture_dispatch(body)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request["operation"], WW.DISPATCH_OPERATION)
        self.assertEqual(request["handler"], WW.DISPATCH_HANDLER)
        self.assertIn("prompt_template_revision", request)
        self.assertEqual(request["inputs"], FIXTURE_INPUTS)
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        provenance = record["provenance"]
        self.assertEqual(provenance["request"], request)
        self.assertEqual(provenance["response"]["response_model"], BUILD_MODEL)
        self.assertEqual(provenance["response"]["resolved_provider_model"],
                         "xiaomi/mimo-v2.6-pro")
        self.assertEqual(provenance["response"]["provider_job_id"], "fixture-job-001")
        self.assertEqual(provenance["response"]["response_evidence"], "response_metadata")
        self.assertRegex(provenance["response"]["raw_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(provenance["request_receipt"], r"^[0-9a-f]{64}$")
        self.assertEqual(provenance["attempt"]["attempt_id"], "attempt_fixture_001")
        self.assertTrue(provenance["attempt"]["evidence"]["correlation"])
        self.assertEqual(provenance["execution"], "no_spend_fixture")
        store = AM.load_bindings(run_dir)
        self.assertEqual([a["attempt_id"] for a in store["attempts"]], ["attempt_fixture_001"])

    def test_authoring_refuses_when_dispatch_cannot_be_proven(self):
        # a body with no dispatch at all is refused: opening a JSON file is not authoring
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(fixture_body(), artifact_id="world_workshop_001", run_id="run_test_001")
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, " | ".join(caught.exception.errors))
        # a chain-alias binding has no supported correlated chain-member receipt
        # reader, so the attempt cannot be proven and authoring refuses to proceed
        run_dir = tempfile.mkdtemp(prefix="world_chain_")
        bound = AM.bind_roles(run_dir, "deepseek-chain", "haiku-chain",
                              runtime="claude-nine", now=FIXTURE_NOW)
        self.assertTrue(bound.get("ok"), bound)
        body = fixture_body()
        with self.assertRaises(WW.WorldError) as caught:
            fixture_dispatch(body, run_dir=run_dir)
        joined = " | ".join(caught.exception.errors)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, joined)
        self.assertIn("CHAIN_RESOLUTION_UNVERIFIED", joined)

    def test_world_drafting_needs_no_music_or_image_prerequisite(self):
        body = fixture_body()
        dispatch, requests, _ = fixture_dispatch(body)
        request = requests[0]
        # the authoring request carries research/premise/cast/location inputs only
        self.assertEqual(request["inputs"], FIXTURE_INPUTS)
        for forbidden in ("music", "song", "keyframe", "image", "voice", "wardrobe"):
            self.assertNotIn(forbidden, request["inputs"])
            self.assertNotIn(forbidden, dispatch["parsed_output"])
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        for forbidden in ("music", "song", "keyframe", "image", "voice", "wardrobe"):
            self.assertNotIn(forbidden, record["dependencies"])


class AntiForgeryTests(unittest.TestCase):
    """An authoring record seals on a dispatch that happened in THIS run -- never
    on files a caller can write. Each of the first three cases was a working
    forge on the previous head."""

    def assert_unproven(self, errors):
        self.assertTrue([e for e in errors if WW.CODE_DISPATCH_UNPROVEN in e],
                        "no %s in %s" % (WW.CODE_DISPATCH_UNPROVEN, errors))

    def test_forged_bindings_file_alone_cannot_author(self):
        run_dir = tempfile.mkdtemp(prefix="world_forged_")
        self.assertTrue(forged_bindings(run_dir))
        # the forged store is on disk and no dispatch was ever recorded
        self.assertEqual([a["attempt_id"] for a in AM.load_bindings(run_dir)["attempts"]], [])
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(fixture_body(), artifact_id="world_workshop_001",
                            run_id="run_test_001", dispatch=forged_dispatch(fixture_body()))
        self.assert_unproven(caught.exception.errors)

    def test_response_fixture_alone_cannot_author(self):
        body = fixture_body()
        with self.assertRaises(WW.WorldError) as caught:
            WW.dispatch_author(run_dir=tempfile.mkdtemp(prefix="world_fixture_only_"),
                               attempt_id="attempt_fixture_only_001", inputs=FIXTURE_INPUTS,
                               runner=fixture_runner(body, []), now=FIXTURE_NOW)
        self.assert_unproven(caught.exception.errors)
        self.assertIn("not a registered dispatch transport", " | ".join(caught.exception.errors))
        run_dir = tempfile.mkdtemp(prefix="world_fixture_cli_")
        inputs_path, fixture_path = write_file_author_inputs(run_dir)
        out = os.path.join(run_dir, "sealed.json")
        code, err = run_cli(["--author", inputs_path, "--run-dir", run_dir,
                             "--attempt-id", "attempt_fixture_only_001",
                             "--response-fixture", fixture_path, "--out", out])
        self.assertEqual(code, 1)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, err)
        self.assertFalse(os.path.exists(out))

    def test_forged_bindings_and_fixture_together_cannot_author(self):
        # the exact file-only echo: a hand-written model-bindings.json plus a
        # response fixture, with no dispatch anywhere in this run
        run_dir = tempfile.mkdtemp(prefix="world_forged_cli_")
        forged_bindings(run_dir)
        inputs_path, fixture_path = write_file_author_inputs(run_dir)
        out = os.path.join(run_dir, "sealed.json")
        code, err = run_cli(["--author", inputs_path, "--run-dir", run_dir,
                             "--attempt-id", "attempt_forged_001",
                             "--response-fixture", fixture_path, "--out", out])
        self.assertEqual(code, 1)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, err)
        self.assertFalse(os.path.exists(out))

    def test_record_read_back_from_a_file_cannot_author(self):
        body = fixture_body()
        dispatch, _, _ = fixture_dispatch(body)
        # exactly what opening the captured provenance from a file gives you
        opened = json.loads(json.dumps({k: v for k, v in dispatch.items() if k != "_handle"}))
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                            dispatch=opened)
        self.assert_unproven(caught.exception.errors)

    def test_one_dispatch_seals_exactly_one_record(self):
        body = fixture_body()
        dispatch, _, _ = fixture_dispatch(body)
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        self.assertEqual(WW.validate(record), [])
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(body, artifact_id="world_workshop_002", run_id="run_test_001",
                            dispatch=dispatch)
        self.assert_unproven(caught.exception.errors)

    def test_genuine_injected_no_spend_transport_seals(self):
        body = fixture_body()
        dispatch, requests, _ = fixture_dispatch(body)
        self.assertEqual(len(requests), 1)
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        self.assertEqual(WW.validate(record), [])
        seal = record["seal"]
        self.assertRegex(seal["dispatch_handle"], r"^[0-9a-f]{64}$")
        self.assertRegex(seal["receipt"]["nonce"], r"^[0-9a-f]{32}$")
        self.assertEqual(seal["receipt"]["kind"], "no_spend")
        self.assertEqual(seal["seal_digest"], WW.seal_digest(seal, record["content_digest"]))
        self.assertEqual(record["provenance"]["execution"], "no_spend_fixture")
        # the live handle never leaks into the record a file would hold
        self.assertEqual(json.loads(json.dumps(record)), record)
        self.assertNotIn("_handle", record)
        self.assertNotIn("_handle", record["provenance"])

    def test_identity_leak_refusal_covers_all_eighteen_fields(self):
        self.assertEqual(len(WW.IDENTITY_FIELDS), 18)
        for field in WW.IDENTITY_FIELDS:
            body = fixture_body()
            body["cast_refs"][0][field] = "leaked into a world record"
            with self.assertRaises(WW.WorldError) as caught:
                author(body)
            self.assertIn("reusable identity field", " | ".join(caught.exception.errors))


class SettingChangeTests(unittest.TestCase):
    def test_character_identity_survives_a_new_setting(self):
        original = author()
        new_locations = [place(
            "loc_formal_hall_001",
            "Formal civic hall, east room",
            "the meeting where the shortfall is disclosed",
            ["long table", "dais", "east corridor door", "south door"],
            access="invited guests only",
            entrances=["east corridor door", "south door"],
            geography="long table centre, dais north, doors east and south",
            era={"period": "contemporary", "time_of_day": "the evening of the meeting"},
            continuity_boundaries={
                "must_persist": ["the dais stays where the hall built it"],
                "may_change": ["how many chairs are set out"],
            })]
        result = WW.change_setting(
            original,
            locations=new_locations,
            reason="setting moved from a neighbourhood workshop to a formal civic hall",
        )
        world = result["world"]
        self.assertEqual(world["revision"], original["revision"] + 1)
        self.assertEqual(world["previous_revision"], original["revision"])
        self.assertEqual(world["cast_refs"], original["cast_refs"])
        self.assertEqual(
            result["preserved_character_identity"],
            [{"character_id": "char_mara_001", "identity_revision": 3},
             {"character_id": "char_levi_001", "identity_revision": 2}],
        )
        self.assertNotEqual(world["content_digest"], original["content_digest"])
        self.assertNotIn("scenes", world)  # the scene plan is stale with the setting
        self.assertEqual(WW.validate(world), [])

    def test_only_dependent_outputs_are_invalidated(self):
        result = WW.change_setting(
            author(),
            locations=[place()],
            reason="alternate setting for the same story",
        )
        self.assertEqual(result["invalidated"], ["scene_plan", "script", "visual_outputs"])
        for identity_surface in ("character_identity", "character_bible", "cast"):
            self.assertNotIn(identity_surface, result["invalidated"])

    def test_setting_change_without_reason_refused(self):
        with self.assertRaises(WW.WorldError):
            WW.change_setting(author(), locations=[
                place("loc_other_001", "Other room", "the alternate setting")], reason="")

    def test_setting_change_to_no_locations_refused(self):
        with self.assertRaises(WW.WorldError) as caught:
            WW.change_setting(author(), locations=[], reason="bad edit")
        self.assertIn("world has no locations", " | ".join(caught.exception.errors))

    def test_original_record_is_not_mutated(self):
        original = author()
        snapshot = copy.deepcopy(original)
        WW.change_setting(original, locations=[
            place("loc_other_001", "Other room", "the alternate setting")], reason="alternate")
        self.assertEqual(original, snapshot)


# --- round 5: the four targets the verifier named -----------------------------

class HonestPathReadsNoModuleStateTests(unittest.TestCase):
    """Target B: rewriting a module attribute must change nothing the honest
    path does -- not the digest, not the stamp, not a refusal."""

    #: names the honest path must never read at call time. The public API
    #: functions are NOT here: the test has to call those through the module.
    POISONED = ("SESSION", "EXECUTION_VALUES", "IDENTITY_FIELDS", "REQUIRED_SECTIONS",
                "SETTING_DEPENDENTS", "SCHEMA_VERSION", "WORLD_KIND", "DISPATCH_OPERATION",
                "DISPATCH_HANDLER", "PROMPT_TEMPLATE_REVISION", "MODELS_LAYER",
                "CODE_DISPATCH_UNPROVEN", "CODE_EXECUTION_STAMP", "CODE_HANDLE_MINT",
                "CODE_TRANSPORT_MINT", "CODE_BINDING_STAMP", "CODE_CONTENT_DIGEST",
                "CODE_LAYOUT_ACTION", "CODE_IMPOSSIBLE_TIMELINE", "CODE_REAL_LOCATION",
                "DispatchHandle", "DispatchTransport", "WorldError",
                "DispatchHandleMintRefused", "DispatchTransportMintRefused",
                "_GUARD", "_HANDLES", "_SEALED", "EXECUTION_BY_KIND", "_dispatch_machinery",
                "canonical_digest", "seal_digest", "_seal", "_json_digest", "_binding_identity",
                "_live_dispatch_reason", "_parent_seal_reason", "_validate_cast",
                "_dispatch_proof_errors", "_seal_proof_errors", "_load", "secrets", "hashlib")

    def setUp(self):
        self._saved = {name: (name in vars(WW), getattr(WW, name, None))
                       for name in self.POISONED}
        self._poison = object()
        for name in self.POISONED:
            setattr(WW, name, self._poison)

    def tearDown(self):
        for name, (existed, value) in self._saved.items():
            if existed:
                setattr(WW, name, value)
            else:
                vars(WW).pop(name, None)

    def test_rewriting_module_state_cannot_change_the_honest_path(self):
        baseline = author()
        rewritten = author()
        self.assertEqual(rewritten["content_digest"], baseline["content_digest"])
        self.assertEqual(rewritten["provenance"]["execution"], "no_spend_fixture")
        self.assertEqual(rewritten["provenance"]["attempt"]["binding_id"],
                         baseline["provenance"]["attempt"]["binding_id"])

    def test_rewriting_module_state_cannot_silence_a_refusal(self):
        # WW.WorldError is poisoned here on purpose: the refusal must still be
        # the REAL class, reached through the private execution scope
        real_error = enforcement_scope()["WorldError"]
        body = fixture_body()
        body["cast_refs"][0]["background"] = "grew up on the coast"
        with self.assertRaises(real_error) as caught:
            author(body)
        self.assertIn("reusable identity field", " | ".join(caught.exception.errors))
        # and the forged-binding echo still does not happen
        run_dir = tempfile.mkdtemp(prefix="world_poison_binding_")
        forged_bindings(run_dir)
        dispatch, _, _ = fixture_dispatch(fixture_body(), run_dir=run_dir,
                                          attempt_id="attempt_poison_001")
        self.assertNotEqual(dispatch["attempt"]["binding_id"], "forgedbinding001")

    def test_a_substituted_guard_is_not_the_guard_the_honest_path_uses(self):
        self.assertIs(WW._GUARD, self._poison)
        record = author()
        self.assertRegex(record["seal"]["seal_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(record["seal"]["seal_digest"],
                         enforcement_scope()["seal_digest"](record["seal"],
                                                            record["content_digest"]))


class ValidateRecomputesContentDigestTests(unittest.TestCase):
    """Target C: validate() must recompute content_digest, never trust it."""

    def test_validate_refuses_a_record_edited_after_sealing(self):
        record = author()
        edited = edited_record(record)
        self.assertNotEqual(WW.canonical_digest(edited), edited["content_digest"])
        # exactly the round-4 measurement: the stored digest is now a lie about
        # the body, and the seal still verifies against that stored digest
        self.assertEqual(edited["seal"]["seal_digest"],
                         WW.seal_digest(edited["seal"], edited["content_digest"]))
        named = [e for e in WW.validate(edited) if WW.CODE_CONTENT_DIGEST in e]
        self.assertTrue(named, "validate accepted a record edited after sealing: %s"
                        % WW.validate(edited))

    def test_a_self_consistent_forgery_still_passes_the_checksum(self):
        # honesty about what content_digest is: a checksum, not a signature. A
        # caller that recomputes both digests is caught by the PARENT seal, not
        # by validate() -- see attack_note_sealed_laundering.
        record = author()
        forged = tampered_record(record)
        self.assertEqual(WW.validate(forged), [])

    def test_the_cli_refuses_a_record_edited_after_sealing(self):
        record = author()
        edited = edited_record(record)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "world.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(edited, handle)
            code, err = run_cli(["--validate", path])
        self.assertEqual(code, 1)
        self.assertIn(WW.CODE_CONTENT_DIGEST, err)
        self.assertNotIn("OK:", err)

    def test_an_untampered_record_still_validates(self):
        record = author()
        self.assertEqual(WW.validate(record), [])
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "world.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(record, handle)
            with contextlib.redirect_stdout(out):
                code, err = run_cli(["--validate", path])
        self.assertEqual(code, 0)
        self.assertIn("OK: world record is usable", out.getvalue())

    def test_setting_change_still_refuses_a_record_edited_after_sealing(self):
        record = author()
        with self.assertRaises(WW.WorldError) as caught:
            WW.change_setting(edited_record(record), locations=[
                place("loc_other_001", "Other room", "the alternate setting")], reason="derived from an edited parent")
        named = [e for e in caught.exception.errors if WW.CODE_CONTENT_DIGEST in e]
        self.assertTrue(named, caught.exception.errors)


class DigestStabilityTests(unittest.TestCase):
    """The honest record must hash like its parent: no provenance note inside the
    digested body."""

    def test_the_provenance_note_is_outside_the_digested_body(self):
        record = author()
        body = {k: v for k, v in record.items() if k not in ("content_digest", "seal")}
        self.assertNotIn("binding_id_source", json.dumps(body))
        self.assertEqual(record["seal"].get("binding_id_source"),
                         "recomputed_from_admitted_binding")
        self.assertNotIn("binding_id_source", record["provenance"]["attempt"])
        # the recomputed id itself is still inside the digested body
        self.assertIn("binding_id", record["provenance"]["attempt"])

    def test_the_digest_is_insensible_to_the_note(self):
        record = author()
        drifted = copy.deepcopy(record)
        drifted["seal"]["binding_id_source"] = "any other note"
        self.assertEqual(record["content_digest"], WW.canonical_digest(drifted))
        self.assertEqual(WW.canonical_digest(record), record["content_digest"])

    def test_the_digest_still_moves_with_the_world_body(self):
        first = author()
        changed = fixture_body()
        changed["premise"] = changed["premise"] + " and a second sentence."
        self.assertNotEqual(first["content_digest"], author(changed)["content_digest"])


class RoundSixRegressionTests(unittest.TestCase):
    """One test per defect the round-5 verdict names. Each one is a route the
    round-5 suite either missed or aimed at the wrong object, and each one must
    FAIL on the round-5 head and PASS here."""

    def test_rewriting_the_registry_entry_cannot_un_spend_a_handle(self):
        # D1 / route 13 and C5: dict.__setitem__ on the records registry reset
        # consumed_by and the SAME handle sealed a second record.
        body, dispatch, _ = genuine_dispatch()
        first = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                dispatch=dispatch)
        handle = dispatch["_handle"]
        records = registry_records()
        landed = 0
        for obj, state in list(records.items()):
            if obj is handle:
                fresh = dict(state)
                fresh["consumed_by"] = None
                dict.__setitem__(records, obj, fresh)   # rewrite: un-spend by field
                landed += 1
                dict.__delitem__(records, obj)          # delete: un-spend by removal
                landed += 1
                dict.__setitem__(records, obj, fresh)
        self.assertEqual(landed, 2, "the handle's registry entry was not rewritten and deleted")
        # both writes landed and the entry now CLAIMS to be unspent; the spend
        # must live somewhere neither of them reaches
        try:
            still_spent = handle.consumed_by
        except WW.WorldError:
            # the entry was left deleted: the handle is no longer a handle this
            # run minted, which refuses just as hard
            still_spent = first["content_digest"]
        self.assertEqual(still_spent, first["content_digest"])
        outcome = seal_outcome(dispatch)
        self.assertTrue(outcome.startswith("REFUSED"),
                        "registry writes (%d landed) un-spent the handle: %s"
                        % (landed, outcome))

    def test_note_sealed_plus_registry_repair_cannot_launder_an_edited_record(self):
        # D2 / F4: note_sealed(new_digest, ref) together with rewriting the real
        # handle's state so consumed_by names the forged digest laundered a
        # record whose body was edited after sealing.
        body, dispatch, _ = genuine_dispatch()
        real = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                               dispatch=dispatch)
        ref = real["seal"]["dispatch_handle"]
        fake = tampered_record(real)
        records = registry_records()
        repaired = 0
        for obj, state in list(records.items()):
            if state["ref"] == ref:
                forged = dict(state)
                forged["consumed_by"] = fake["content_digest"]
                dict.__setitem__(records, obj, forged)
                repaired += 1
        self.assertEqual(repaired, 1, "the handle's registry entry was not repaired")
        try:
            guard().note_sealed(fake["content_digest"], ref)
        except BaseException:  # noqa: BLE001 -- a refusal here is one of the two outcomes
            pass
        outcome = change_setting_outcome(fake)
        self.assertTrue(outcome.startswith("REFUSED"),
                        "note_sealed plus a registry repair laundered an edited record: %s"
                        % outcome)

    def test_no_closure_map_can_relabel_a_no_spend_call_as_live(self):
        # D3 / J1: the execution stamp came from a dict named execution_by_kind
        # in dispatch_author.__closure__; rewriting it stamped 'live' onto a
        # no-spend transport.
        for cell in (WW.dispatch_author.__closure__ or ()):
            try:
                value = cell.cell_contents
            except ValueError:  # empty cell
                continue
            if type(value) is dict:
                value["no_spend"] = "live"
                value["no_spend_fixture"] = "live"
        body = fixture_body()
        dispatch, _, _ = fixture_dispatch(body)
        self.assertEqual(dispatch["execution"], "no_spend_fixture",
                         "a no-spend transport claimed the live stamp")
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        self.assertEqual(record["provenance"]["execution"], "no_spend_fixture")

    def test_a_guard_swapped_in_the_private_scope_is_not_the_guard_the_honest_path_uses(self):
        # D4 / A2: author_world.__globals__["_GUARD"] = a fake reporting a
        # fabricated state made author_world seal a hand-built dispatch whose
        # handle was a bare DispatchHandle.__new__ object.
        class FakeGuard:
            def lookup(self, handle):
                return dict(forged_state())

            def by_ref(self, ref):
                return None

            def consume(self, handle, digest):
                return None

            def note_sealed(self, digest, ref):
                return None

            def live_count(self):
                return 0

        scope = enforcement_scope()
        saved = scope.get("_GUARD", "<absent>")
        scope["_GUARD"] = FakeGuard()
        try:
            handle = WW.DispatchHandle.__new__(WW.DispatchHandle)
            outcome = seal_outcome(dispatch_around(handle))
        finally:
            if saved == "<absent>":
                scope.pop("_GUARD", None)
            else:
                scope["_GUARD"] = saved
        self.assertTrue(outcome.startswith("REFUSED"),
                        "a guard swapped in the private execution scope sealed a record: %s"
                        % outcome)

    def test_rebinding_the_handle_class_in_the_private_scope_defeats_nothing(self):
        # D5 / H3: setting author_world.__globals__["DispatchHandle"] to another
        # class made the exact-type check accept that class's instances.
        class Evil(WW.DispatchHandle):
            def __init__(self, **kwargs):
                pass

        evil = Evil()
        dict.__setitem__(registry_records(), evil, dict(forged_state()))
        scope = enforcement_scope()
        saved = scope.get("DispatchHandle", "<absent>")
        scope["DispatchHandle"] = Evil
        try:
            resolved = guard().lookup(evil)
            outcome = seal_outcome(dispatch_around(evil))
        finally:
            if saved == "<absent>":
                scope.pop("DispatchHandle", None)
            else:
                scope["DispatchHandle"] = saved
        self.assertIsNone(resolved,
                          "rebinding the handle class made the exact-type check accept a subclass")
        self.assertTrue(outcome.startswith("REFUSED"),
                        "a rebound handle class let a subclass seal: %s" % outcome)


# --- round 4: REACHABILITY of the handle-minting capability -------------------
#
# Round 3 closed the file routes and left the capability reachable through
# ``DispatchHandle()`` itself. These attacks aim at the CAPABILITY, not at file
# contents: they try to come away with a handle that seals without any real
# transport call. Every route must end REFUSED BY NAME.

HANDLE_KWARGS = {"attempt_id": "attempt_forged_001", "request_receipt": "f" * 64,
                 "receipt": {"transport_id": "forgedtransport", "kind": "live",
                             "nonce": "f" * 32, "session": "f" * 64,
                             "receipt_digest": "f" * 64},
                 "execution": "live"}


def seal_outcome(dispatch):
    """Try to seal with a forged dispatch. Never raises: returns the outcome."""
    try:
        record = WW.author_world(fixture_body(), artifact_id="world_workshop_001",
                                 run_id="run_test_001", dispatch=dispatch)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % " | ".join(caught.errors)
    except BaseException as caught:  # noqa: BLE001 -- an attack may blow up any way it likes
        return "REFUSED (%s): %s" % (type(caught).__name__, caught)
    return "ACCEPTED: sealed %s" % record["content_digest"]


def dispatch_around(handle):
    """The strongest restatement a caller can build around a handle it holds:
    every field of the proof rewritten to agree with the handle's own."""
    dispatch = forged_dispatch(fixture_body())
    dispatch["_handle"] = handle
    for restate in (lambda: dispatch["attempt"].update(attempt_id=handle.attempt_id),
                    lambda: dispatch.update(request_receipt=handle.request_receipt),
                    lambda: dispatch["seal"].update(dispatch_handle=handle.ref),
                    lambda: dispatch["seal"].update(receipt=copy.deepcopy(handle.receipt)),
                    lambda: dispatch.update(execution=handle.execution),
                    lambda: dispatch["response"].update(raw_digest=handle.raw_digest)):
        try:
            restate()
        except BaseException:  # noqa: BLE001
            pass
    return dispatch


def genuine_dispatch(ww=WW):
    """One real dispatch: the thing every attack wants WITHOUT paying for it."""
    body = fixture_body()
    dispatch, _, run_dir = fixture_dispatch(body, ww=ww)
    return body, dispatch, run_dir


def attack_constructor_forged_receipt():
    try:
        WW.DispatchHandle(**HANDLE_KWARGS)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: DispatchHandle(**forged) returned a handle"


def attack_constructor_no_arguments():
    try:
        WW.DispatchHandle()
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: DispatchHandle() returned a handle"


def attack_new_plus_attribute_stuffing():
    handle = WW.DispatchHandle.__new__(WW.DispatchHandle)
    stuffed = 0
    for name, value in (("ref", "f" * 64), ("session", WW.SESSION), ("attempt_id", "attempt_forged_001"),
                        ("request_receipt", "f" * 64), ("receipt", HANDLE_KWARGS["receipt"]),
                        ("execution", "live"), ("consumed_by", None), ("raw_digest", "f" * 64)):
        for write in (lambda: setattr(handle, name, value),
                      lambda: object.__setattr__(handle, name, value)):
            try:
                write()
                stuffed += 1
            except BaseException:  # noqa: BLE001
                pass
    outcome = seal_outcome(dispatch_around(handle))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: __new__ + %d attribute writes minted a usable handle" % stuffed
    return "REFUSED BY NAME: __new__ + %d attribute writes, then %s" % (stuffed, outcome)


def attack_subclass_super_init():
    class Evil(WW.DispatchHandle):
        pass

    try:
        Evil(**HANDLE_KWARGS)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: a subclass of DispatchHandle minted a handle through its __init__"


def attack_subclass_bypassing_init():
    class Evil(WW.DispatchHandle):
        def __init__(self, **kwargs):
            pass

    handle = Evil(**HANDLE_KWARGS)
    outcome = seal_outcome(dispatch_around(handle))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a subclass that bypasses __init__ minted a usable handle"
    return "REFUSED BY NAME: subclass bypassing __init__, then %s" % outcome


def attack_subclass_overriding_properties():
    class Evil(WW.DispatchHandle):
        ref = "f" * 64
        session = WW.SESSION
        transport_id = "forgedtransport"
        transport_kind = "live"
        execution = "live"
        attempt_id = "attempt_forged_001"
        request_receipt = "f" * 64
        receipt = HANDLE_KWARGS["receipt"]
        raw_digest = "f" * 64
        consumed_by = None

        def __init__(self, **kwargs):
            pass

    outcome = seal_outcome(dispatch_around(Evil()))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a subclass overriding the handle fields minted a usable handle"
    return "REFUSED BY NAME: subclass overriding the fields, then %s" % outcome


def attack_registry_setitem():
    class Fake:
        ref = "f" * 64

    try:
        registry_records()["f" * 64] = Fake()
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: records[ref] = fake registered a handle"


def attack_registry_writes():
    class Fake:
        ref = "f" * 64

    refused = []
    records, sealed, transports = registry_records(), registry_sealed(), registry_transports()
    for write in (lambda: records.update({"f" * 64: Fake()}),
                  lambda: records.pop("f" * 64),
                  lambda: records.clear(),
                  lambda: records.setdefault("f" * 64, Fake()),
                  lambda: records.__setitem__("f" * 64, Fake()),
                  lambda: records.__delitem__("f" * 64),
                  lambda: setattr(records, "anything", Fake()),
                  lambda: sealed.update({"0" * 64: "f" * 64}),
                  lambda: sealed.__setitem__("0" * 64, "f" * 64),
                  lambda: sealed.clear(),
                  lambda: setattr(sealed, "anything", Fake()),
                  lambda: transports.clear(),
                  lambda: transports.__setitem__("x", Fake())):
        try:
            write()
        except WW.WorldError as caught:
            refused.append(caught.errors[0].split(":")[0])
        except BaseException as caught:  # noqa: BLE001
            refused.append(type(caught).__name__)
    if refused:
        return "REFUSED BY NAME: every registry write refused (%d writes)" % len(refused)
    return "ACCEPTED: a registry write went through"


def attack_registry_dict_copy():
    class Fake:
        ref = "f" * 64

    _, dispatch, _ = genuine_dispatch()   # so the registry holds a live handle
    live = live_count()
    copied = {}
    try:
        copied = dict(registry_records())
    except BaseException:  # noqa: BLE001
        pass
    copied["f" * 64] = Fake()
    # and the copy is inert: neither the entries in it nor the one added to it
    # can be used as a dispatch handle
    forged = forged_dispatch(fixture_body())
    forged["seal"]["dispatch_handle"] = "f" * 64
    outcome = seal_outcome(forged)
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a copied registry dict minted a usable handle"
    replay = seal_outcome(dispatch_around(copied[list(copied)[0]] if copied else Fake()))
    if replay.startswith("ACCEPTED"):
        return "ACCEPTED: an entry taken from a copied registry dict sealed a record"
    return "REFUSED BY NAME: copied %d live registry entries into a writable dict and added one; %s" % (
        live, outcome.split(":")[0])


def attack_deepcopy_handle():
    _, dispatch, _ = genuine_dispatch()
    clone = copy.deepcopy(dispatch["_handle"])
    outcome = seal_outcome(dispatch_around(clone))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a deepcopy of a live handle sealed a record"
    return "REFUSED BY NAME: copy.deepcopy(handle), then %s" % outcome


def attack_pickle_handle():
    # pickle resolves a class by NAME: module of the minted handle's class must be
    # sys.modules["world_bible.world_writer"] for dumps to accept the object. In the
    # one-process full-tree pytest run, scripts/conftest.py drops the skill-tree
    # modules from sys.modules between collections and pytest then re-imports the
    # world_bible package __init__ at item setup, so sys.modules can hold a SECOND
    # world_writer module object while this test module still binds the first.
    # Mint the handle through the module object pickle will resolve -- the canonical
    # sys.modules entry, or this module's binding when no second copy exists -- so the
    # round trip exercises the deployed identity, and the unpickled clone (a fresh
    # object, no registry entry in ANY scope) must still be refused.
    canonical = sys.modules.get("world_bible.world_writer") or WW
    body, dispatch, _ = genuine_dispatch(ww=canonical)
    clone = pickle.loads(pickle.dumps(dispatch["_handle"]))
    outcome = seal_outcome(dispatch_around(clone))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: an unpickled handle sealed a record"
    return "REFUSED BY NAME: pickle round trip, then %s" % outcome


def attack_reuse_consumed_handle():
    body, dispatch, _ = genuine_dispatch()
    sealed = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                             dispatch=dispatch)
    outcome = seal_outcome(dispatch)
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a consumed handle sealed a second record %s" % sealed["content_digest"]
    return "REFUSED BY NAME: re-use of the consumed handle, then %s" % outcome


def attack_unconsume_by_attribute_write():
    body, dispatch, _ = genuine_dispatch()
    WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001", dispatch=dispatch)
    handle = dispatch["_handle"]
    cleared = 0
    for write in (lambda: setattr(handle, "consumed_by", None),
                  lambda: object.__setattr__(handle, "consumed_by", None),
                  lambda: handle.__dict__.__setitem__("consumed_by", None),
                  lambda: vars(handle).__setitem__("consumed_by", None)):
        try:
            write()
            cleared += 1
        except BaseException:  # noqa: BLE001
            pass
    # round 5 aimed at the HANDLE, where consumed_by never lived. The write that
    # mattered is the one CPython leaves open on the REGISTRY ENTRY: a raw
    # dict.__setitem__ that resets consumed_by on the state the guard reads.
    entries = 0
    records = registry_records()
    for obj, state in list(records.items()):
        if obj is handle:
            fresh = dict(state)
            fresh["consumed_by"] = None
            dict.__setitem__(records, obj, fresh)
            entries += 1
    outcome = seal_outcome(dispatch)
    if outcome.startswith("ACCEPTED"):
        return ("ACCEPTED: clearing consumed_by (%d attribute writes, %d registry entries "
                "rewritten) un-spent the handle" % (cleared, entries))
    return ("REFUSED BY NAME: %d un-consume writes and %d registry entry rewrites landed but the "
            "handle stays spent (%s)" % (cleared, entries, outcome.split(":")[0]))


def attack_mutate_handle_fields():
    body, dispatch, _ = genuine_dispatch()
    handle = dispatch["_handle"]
    landed = 0
    for name, value in (("attempt_id", "attempt_rewritten"), ("request_receipt", "f" * 64),
                        ("execution", "live"), ("raw_digest", "f" * 64),
                        ("receipt", HANDLE_KWARGS["receipt"]), ("ref", "f" * 64)):
        for write in (lambda: setattr(handle, name, value),
                      lambda: object.__setattr__(handle, name, value),
                      lambda: handle.__dict__.__setitem__(name, value)):
            try:
                write()
                landed += 1
            except BaseException:  # noqa: BLE001
                pass
    if landed:
        return "ACCEPTED: %d handle field writes landed on a live handle" % landed
    return "REFUSED BY NAME: no handle field write landed (setattr, object.__setattr__, __dict__)"


def attack_transport_kind_mutation():
    body = fixture_body()
    run_dir = tempfile.mkdtemp(prefix="world_kind_")
    AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
    runner = WW.no_spend_transport(fixture_runner(body, []))
    runner.kind = "live"
    runner._s75_live_runner = True
    try:
        WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_kind_001", inputs=FIXTURE_INPUTS,
                           runner=runner, now=FIXTURE_NOW)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: setting transport.kind relabelled a no-spend dispatch as live"


def attack_direct_transport_construction():
    try:
        WW.DispatchTransport(fixture_runner(fixture_body(), []), kind="live")
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: DispatchTransport(fn, kind='live') built a transport that claims live"


def attack_transport_subclass_forged_receipt():
    class Evil(WW.DispatchTransport):
        def __call__(self, request):
            return ({"raw": fixture_body(), "response_model": BUILD_MODEL,
                     "resolved_provider_model": "xiaomi/mimo-v2.6-pro"},
                    HANDLE_KWARGS["receipt"])

    try:
        runner = Evil(fixture_runner(fixture_body(), []), kind="live")
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    body = fixture_body()
    run_dir = tempfile.mkdtemp(prefix="world_evil_transport_")
    AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
    try:
        WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_evil_001", inputs=FIXTURE_INPUTS,
                           runner=runner, now=FIXTURE_NOW)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: a transport subclass forged the receipt and minted a handle"


def attack_assert_execution_live():
    body = fixture_body()
    run_dir = tempfile.mkdtemp(prefix="world_claim_live_")
    AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
    try:
        WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_claim_001", inputs=FIXTURE_INPUTS,
                           runner=WW.no_spend_transport(fixture_runner(body, [])),
                           now=FIXTURE_NOW, execution="live")
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    return "ACCEPTED: dispatch_author(execution='live') stamped live on a no-spend mint"


def attack_record_read_back_from_file():
    body, dispatch, _ = genuine_dispatch()
    opened = json.loads(json.dumps({k: v for k, v in dispatch.items() if k != "_handle"}))
    return seal_outcome(opened)


def attack_file_only_provenance():
    return seal_outcome(forged_dispatch(fixture_body()))


def attack_poke_public_surface():
    before = live_count()
    poked = 0
    minted = []
    targets = [(name, getattr(WW, name)) for name in dir(WW) if not name.startswith("_")]
    targets += [("DispatchHandle.%s" % name, getattr(WW.DispatchHandle, name))
                for name in dir(WW.DispatchHandle)]
    targets += [("DispatchTransport.%s" % name, getattr(WW.DispatchTransport, name))
                for name in dir(WW.DispatchTransport)]
    for name, value in targets:
        poked += 1
        for attempt in (lambda: value(), lambda: value(**HANDLE_KWARGS), lambda: value(HANDLE_KWARGS)):
            try:
                # main() parses sys.argv when it is called blind: its argparse
                # noise is not a mint path
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    got = attempt()
            except BaseException:  # noqa: BLE001
                continue
            if isinstance(got, WW.DispatchHandle):
                minted.append((name, got))
    for name, handle in minted:
        outcome = seal_outcome(dispatch_around(handle))
        if outcome.startswith("ACCEPTED"):
            return "ACCEPTED: poking %s produced a usable handle (%s)" % (name, outcome)
    return ("REFUSED BY NAME: no usable handle from poking %d public attributes (%d live handles "
            "before, %d after)" % (poked, before, live_count()))


# --- round 5: the five sealing routes the base still had, plus three the round-4
# author never disclosed. Each one is measured, not asserted.

def forged_state():
    """What a fake guard must hand back for a constructed handle to look live:
    every field agreeing with the forged dispatch built around it."""
    body = fixture_body()
    raw_digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"ref": "f" * 64, "session": WW.SESSION, "transport_id": "forgedtransport",
            "transport_kind": "no_spend", "execution": "no_spend_fixture",
            "attempt_id": "attempt_forged_001", "request_receipt": "f" * 64,
            "receipt": {"transport_id": "forgedtransport", "kind": "no_spend",
                        "nonce": "f" * 32, "session": "f" * 64, "receipt_digest": "f" * 64},
            "raw_digest": raw_digest, "consumed_by": None}


def attack_fake_guard_on_the_module():
    """Route 1: WW._GUARD = a fake exposing lookup/by_ref/consume/note_sealed/
    live_count, then DispatchHandle.__new__(DispatchHandle) is a 'live' handle."""
    class FakeGuard:
        def lookup(self, handle):
            return dict(forged_state())

        def by_ref(self, ref):
            return None

        def consume(self, handle, digest):
            return None

        def note_sealed(self, digest, ref):
            return None

        def live_count(self):
            return 0

    saved = getattr(WW, "_GUARD", "<absent>")
    WW._GUARD = FakeGuard()
    try:
        handle = WW.DispatchHandle.__new__(WW.DispatchHandle)
        outcome = seal_outcome(dispatch_around(handle))
    finally:
        if saved == "<absent>":
            del WW._GUARD
        else:
            WW._GUARD = saved
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: WW._GUARD = a fake guard made DispatchHandle.__new__ a live handle"
    return "REFUSED BY NAME: fake WW._GUARD substituted, then %s" % outcome


def attack_execution_by_kind_rewrite():
    """Route 2: rewrite the execution map so a no-spend transport stamps live."""
    saved = getattr(WW, "EXECUTION_BY_KIND", "<absent>")
    WW.EXECUTION_BY_KIND = {"no_spend": "live", "live": "live"}
    dispatch = None
    try:
        body = fixture_body()
        run_dir = tempfile.mkdtemp(prefix="world_stamp_rewrite_")
        AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
        dispatch = WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_stamp_rewrite_001",
                                      inputs=FIXTURE_INPUTS,
                                      runner=WW.no_spend_transport(fixture_runner(body, [])),
                                      now=FIXTURE_NOW)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    finally:
        if saved == "<absent>":
            del WW.EXECUTION_BY_KIND
        else:
            WW.EXECUTION_BY_KIND = saved
    if dispatch["execution"] == "live":
        return ("ACCEPTED: rewriting EXECUTION_BY_KIND stamped execution='live' on a no-spend "
                "transport")
    return ("REFUSED BY NAME: rewriting EXECUTION_BY_KIND changed nothing "
            "(execution=%r)" % dispatch["execution"])


def attack_subclass_written_into_the_registry():
    """Route 3: a DispatchHandle SUBCLASS instance written into the registry."""
    class Evil(WW.DispatchHandle):
        def __init__(self, **kwargs):
            pass

    evil = Evil()
    state = forged_state()
    try:
        registry_records()[evil] = state
    except WW.WorldError as caught:
        ordinary = "the registry refused it by name (%s)" % caught.errors[0].split(":")[0]
    else:
        ordinary = "ACCEPTED the write"
    # and the one write route CPython leaves open: a raw dict.__setitem__
    dict.__setitem__(registry_records(), evil, state)
    outcome = seal_outcome(dispatch_around(evil))
    if outcome.startswith("ACCEPTED"):
        return ("ACCEPTED: a subclass instance written into the registry sealed a record "
                "(%s)" % ordinary)
    return ("REFUSED BY NAME: %s; raw dict.__setitem__ lands but the exact-class and identity "
            "lookup refuse the subclass: %s" % (ordinary, outcome.split(":")[0]))


def attack_mint_from_the_closure():
    """Route 5: dispatch_author.__closure__ reaching 'mint'."""
    mint = mint_callable()
    if mint is None:
        return "REFUSED BY NAME: no mint is reachable from dispatch_author's closure"
    try:
        handle = mint(attempt_id="attempt_forged_001", request_receipt="f" * 64,
                      receipt=HANDLE_KWARGS["receipt"], execution="live", raw_digest="f" * 64)
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % caught.errors[0]
    outcome = seal_outcome(dispatch_around(handle))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: the mint reached through the closure produced a usable handle"
    return "REFUSED BY NAME: the mint reached through the closure, then %s" % outcome


def edited_record(record):
    """What a caller does to a sealed record: one body field edited and NOTHING
    recomputed. The stored content_digest is now a lie about the body."""
    fake = copy.deepcopy(record)
    fake["premise"] = record["premise"] + ", edited after sealing"
    return fake


def tampered_record(record):
    """The stronger forgery: one body field edited AND both digests recomputed,
    so the record validates and only the parent seal can tell. This is the shape
    route 6 needs -- it is a fabricated record that validate() cannot fault."""
    fake = copy.deepcopy(record)
    fake["premise"] = record["premise"] + ", edited after sealing"
    fake.pop("content_digest", None)
    fake["content_digest"] = WW.canonical_digest(fake)
    seal = dict(fake["seal"])
    seal["seal_digest"] = WW.seal_digest(seal, fake["content_digest"])
    fake["seal"] = seal
    return fake


def change_setting_outcome(record):
    try:
        WW.change_setting(record, locations=[
            place("loc_other_001", "Other room", "the alternate setting")], reason="derived from a fabricated parent")
    except WW.WorldError as caught:
        return "REFUSED BY NAME: %s" % " | ".join(caught.errors)
    except BaseException as caught:  # noqa: BLE001
        return "REFUSED (%s): %s" % (type(caught).__name__, caught)
    return "ACCEPTED: change_setting derived from a fabricated parent"


def attack_note_sealed_laundering():
    """Route 6: one real dispatch makes its ref public in a seal, then
    note_sealed(digest, ref) launders a fabricated record into change_setting."""
    body, dispatch, _ = genuine_dispatch()
    real = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                           dispatch=dispatch)
    ref = real["seal"]["dispatch_handle"]
    fake = tampered_record(real)
    writer = getattr(WW, "_GUARD", None) or guard()
    try:
        writer.note_sealed(fake["content_digest"], ref)
    except BaseException as caught:  # noqa: BLE001
        return "REFUSED BY NAME: note_sealed is unreachable (%s: %s)" % (
            type(caught).__name__, caught)
    return change_setting_outcome(fake)


def attack_rebuild_the_machinery():
    """Route 7: _dispatch_machinery() is a public name that rebuilds it all."""
    machinery = getattr(WW, "_dispatch_machinery", None)
    if machinery is None:
        return "REFUSED BY NAME: _dispatch_machinery is not a module name any more"
    machinery()
    return "ACCEPTED: _dispatch_machinery() rebuilt the machinery and handed back a mint path"


def attack_hash_eq_alias_a_live_entry():
    """Route 8: a subclass overriding __hash__/__eq__ aliases a live entry."""
    body, dispatch, _ = genuine_dispatch()
    target = dispatch["_handle"]

    class Evil(WW.DispatchHandle):
        def __init__(self, **kwargs):
            pass

        def __hash__(self):
            return hash(target)

        def __eq__(self, other):
            return other is target or other is self

    evil = Evil()
    aliased = guard().lookup(evil)
    if aliased is not None:
        return "ACCEPTED: a __hash__/__eq__ subclass read a live registry entry (%r)" % aliased
    outcome = seal_outcome(dispatch_around(evil))
    if outcome.startswith("ACCEPTED"):
        return "ACCEPTED: a __hash__/__eq__ subclass sealed with a live entry"
    return "REFUSED BY NAME: __hash__/__eq__ aliasing a live entry, then %s" % outcome


#: label -> attack. Each returns REFUSED BY NAME ... or ACCEPTED ... .
REACHABILITY_MATRIX = (
    ("DispatchHandle(**forged receipt)", attack_constructor_forged_receipt),
    ("DispatchHandle() no arguments", attack_constructor_no_arguments),
    ("DispatchHandle.__new__ + attribute stuffing", attack_new_plus_attribute_stuffing),
    ("subclass whose __init__ calls the base __init__", attack_subclass_super_init),
    ("subclass whose __init__ bypasses __init__", attack_subclass_bypassing_init),
    ("subclass overriding every handle property", attack_subclass_overriding_properties),
    ("_HANDLES[ref] = forged handle", attack_registry_setitem),
    ("registry writes (update/pop/clear/setdefault/add/setattr)", attack_registry_writes),
    ("copy the registry dict and use the copy", attack_registry_dict_copy),
    ("copy.deepcopy of a live handle", attack_deepcopy_handle),
    ("pickle round trip of a live handle", attack_pickle_handle),
    ("re-use a consumed handle", attack_reuse_consumed_handle),
    ("clear consumed_by and re-use", attack_unconsume_by_attribute_write),
    ("rewrite a live handle's fields", attack_mutate_handle_fields),
    ("set transport.kind = 'live' on a no-spend transport", attack_transport_kind_mutation),
    ("DispatchTransport(fn, kind='live')", attack_direct_transport_construction),
    ("transport subclass forging the receipt", attack_transport_subclass_forged_receipt),
    ("dispatch_author(execution='live') on a no-spend mint", attack_assert_execution_live),
    ("record read back from a JSON file", attack_record_read_back_from_file),
    ("file-only provenance with no dispatch at all", attack_file_only_provenance),
    ("poke every public attribute of module and classes", attack_poke_public_surface),
    # --- round 5: the five sealing routes the base still had, plus the three
    # the round-4 author never disclosed
    ("WW._GUARD = a fake guard + DispatchHandle.__new__", attack_fake_guard_on_the_module),
    ("rewrite EXECUTION_BY_KIND to stamp live on a no-spend mint", attack_execution_by_kind_rewrite),
    ("DispatchHandle subclass instance written into the registry", attack_subclass_written_into_the_registry),
    ("dispatch_author.__closure__ reaching 'mint'", attack_mint_from_the_closure),
    ("_GUARD.note_sealed(digest, ref) on a fabricated record", attack_note_sealed_laundering),
    ("_dispatch_machinery() rebuilds the whole machinery", attack_rebuild_the_machinery),
    ("subclass aliasing a live entry via __hash__/__eq__", attack_hash_eq_alias_a_live_entry),
)


class HandleReachabilityTests(unittest.TestCase):
    """No route to a usable handle without a real transport call."""

    def test_reachability_matrix_refuses_every_route(self):
        rows = []
        for label, attack in REACHABILITY_MATRIX:
            outcome = attack()
            rows.append("%-58s %s" % (label, outcome))
            self.assertTrue(outcome.startswith("REFUSED"),
                            "route %r is REACHABLE without a transport: %s" % (label, outcome))
            self.assertFalse(outcome.startswith("ACCEPTED"),
                             "route %r obtained a usable handle: %s" % (label, outcome))
        print("\nREACHABILITY MATRIX -- obtaining a handle WITHOUT a real transport")
        for row in rows:
            print("  " + row)
        print("")

    def test_every_refusal_is_named(self):
        for label, attack in REACHABILITY_MATRIX:
            outcome = attack()
            self.assertRegex(outcome, r"^REFUSED( BY NAME)?: ",
                             "route %r did not name its refusal: %s" % (label, outcome))

    def test_direct_construction_raises_the_named_error(self):
        with self.assertRaises(WW.DispatchHandleMintRefused) as caught:
            WW.DispatchHandle(**HANDLE_KWARGS)
        self.assertIn(WW.CODE_HANDLE_MINT, caught.exception.errors[0])
        self.assertEqual(caught.exception.code, WW.CODE_HANDLE_MINT)
        # and it is still a WorldError, so every existing caller catches it
        self.assertIsInstance(caught.exception, WW.WorldError)

    def test_direct_construction_registers_nothing(self):
        before = live_count()
        for build in (lambda: WW.DispatchHandle(**HANDLE_KWARGS),
                      lambda: WW.DispatchHandle(),
                      lambda: WW.DispatchTransport(fixture_runner(fixture_body(), []),
                                                   kind="live")):
            with self.assertRaises(WW.WorldError):
                build()
        self.assertEqual(live_count(), before)

    def test_registry_views_refuse_writes_by_name(self):
        # r5: the read-only views are gone as module names, and the registries
        # themselves now refuse every ordinary write BY NAME. The old test wrote
        # through WW._HANDLES / WW._SEALED; those names no longer exist, so the
        # writes below aim at the real registries reached through the documented
        # closure residue.
        for name in ("_HANDLES", "_SEALED", "_GUARD"):
            self.assertFalse(hasattr(WW, name), "%s is still a module name" % name)
        records, sealed = registry_records(), registry_sealed()
        for write in (lambda: records.__setitem__("x", "y"),
                      lambda: records.__delitem__("x"),
                      lambda: records.__setattr__("x", "y"),
                      lambda: sealed.__setitem__("x", "y"),
                      lambda: sealed.clear()):
            with self.assertRaises(WW.DispatchHandleMintRefused):
                write()

    def test_public_surface_is_pinned(self):
        """The WHOLE surface, pinned: every public name, every underscore name,
        and the one place the process memory is reachable from. A mint helper or
        a registry added to the module shows up here and has to be justified."""
        public = sorted(name for name in dir(WW) if not name.startswith("_"))
        self.assertEqual(public, sorted([
            "CHARACTER_ID_RE", "CODE_BINDING_STAMP", "CODE_CONTENT_DIGEST",
            "CODE_DISPATCH_UNPROVEN", "CODE_EXECUTION_STAMP", "CODE_HANDLE_MINT",
            "CODE_IMPOSSIBLE_TIMELINE", "CODE_LAYOUT_ACTION", "CODE_REAL_LOCATION",
            "CODE_TRANSPORT_MINT", "DISPATCH_HANDLER", "DISPATCH_OPERATION", "DispatchHandle",
            "DispatchHandleMintRefused", "DispatchTransport", "DispatchTransportMintRefused",
            "EXECUTION_VALUES", "IDENTITY_FIELDS", "LOCATION_ID_RE",
            "MODELS_LAYER", "PLACEHOLDER_TEXT", "PLACE_CARRIERS",
            "PROMPT_TEMPLATE_REVISION", "REQUIRED_SECTIONS", "SCHEMA_VERSION",
            "SESSION", "SETTING_DEPENDENTS", "WORLD_KIND", "WorldError", "annotations",
            "argparse", "author_world", "build_author_request", "canonical_digest",
            "change_setting", "copy", "dispatch_author", "hashlib", "json", "live_transport",
            "main", "no_spend_transport", "os", "re", "seal_digest", "secrets", "sys",
            "validate",
        ]))
        # the underscore surface too: helpers only, no registry and no machinery
        underscore = sorted(name for name in dir(WW) if name.startswith("_")
                            and not name.startswith("__"))
        self.assertEqual(underscore, sorted([
            "_binding_identity", "_content", "_content_list",
            "_dispatch_proof_errors", "_json_digest", "_live_dispatch_reason",
            "_load", "_nonempty", "_nonempty_list", "_norm_word",
            "_parent_seal_reason", "_seal", "_seal_proof_errors",
            "_validate_atmosphere", "_validate_cast", "_validate_era", "_validate_light",
            "_validate_locations", "_validate_never_list",
            "_validate_place_continuity", "_validate_place_era",
            "_validate_place_layout", "_validate_place_lighting",
            "_validate_place_social_rules", "_validate_scenes", "_validate_sound",
        ]))
        # no name on the module -- public or underscore -- IS the registry, the
        # sealed map, the guard or the mint
        registries = {id(registry_records()), id(registry_sealed()), id(registry_transports())}
        for name in dir(WW):
            value = getattr(WW, name)
            self.assertNotIn(id(value), registries, "%s is this process's registry" % name)
            self.assertIsNot(value, guard(), "%s is the dispatch guard" % name)
            self.assertIsNot(value, mint_callable(), "%s is the mint" % name)
        # and no name's own closure cell holds one either -- except the ONE
        # documented residue, dispatch_author's own closure
        holders = set()
        for name in dir(WW):
            value = getattr(WW, name)
            for cell in (getattr(value, "__closure__", None) or ()):
                try:
                    held = cell.cell_contents
                except ValueError:
                    continue
                if id(held) in registries:
                    holders.add(name)
        self.assertEqual(holders, {"dispatch_author"},
                         "the registries moved: %s" % sorted(holders))

    def test_the_only_mint_is_inside_dispatch_author(self):
        # the constructor refuses, the registry refuses, and the module exposes
        # no callable whose name offers a mint
        with self.assertRaises(WW.DispatchHandleMintRefused):
            WW.DispatchHandle()
        import inspect
        minters = [name for name in dir(WW) if not name.startswith("_")
                   and not inspect.isclass(getattr(WW, name))
                   and callable(getattr(WW, name)) and "mint" in name.lower()]
        self.assertEqual(minters, [])
        # r5: the mint is not a module name at all, and the one reachable copy --
        # through dispatch_author's closure cell -- refuses to register a handle
        # unless dispatch_author's own frame is the caller.
        self.assertNotIn("mint", vars(WW))
        mint = mint_callable()
        self.assertIsNotNone(mint, "the mint is not reachable even from dispatch_author")
        before = live_count()
        with self.assertRaises(WW.DispatchHandleMintRefused) as caught:
            mint(attempt_id="attempt_forged_001", request_receipt="f" * 64,
                 receipt=HANDLE_KWARGS["receipt"], execution="live", raw_digest="f" * 64)
        self.assertIn(WW.CODE_HANDLE_MINT, caught.exception.errors[0])
        self.assertEqual(live_count(), before, "the refused mint registered anyway")

    def test_reaching_the_mint_through_the_closure_is_not_a_mint(self):
        """Route 5 of the round-5 brief: dispatch_author.__closure__ reaches
        'mint'. It is reachable -- and calling it is refused BY NAME, because the
        mint only registers from inside dispatch_author's own frame."""
        mint = mint_callable()
        outcome = None
        try:
            handle = mint(attempt_id="attempt_forged_001", request_receipt="f" * 64,
                          receipt=HANDLE_KWARGS["receipt"], execution="live", raw_digest="f" * 64)
        except WW.WorldError as caught:
            outcome = "REFUSED BY NAME: %s" % caught.errors[0]
        else:
            outcome = seal_outcome(dispatch_around(handle))
        self.assertTrue(outcome.startswith("REFUSED"), outcome)
        self.assertIn(WW.CODE_HANDLE_MINT, outcome)


class ExecutionStampTests(unittest.TestCase):
    """execution is stamped from the transport kind, never asserted."""

    def test_no_spend_mint_cannot_report_live(self):
        body = fixture_body()
        dispatch, _, _ = fixture_dispatch(body)
        self.assertEqual(dispatch["execution"], "no_spend_fixture")
        self.assertEqual(dispatch["_handle"].execution, "no_spend_fixture")
        self.assertEqual(dispatch["_handle"].transport_kind, "no_spend")
        dispatch["execution"] = "live"          # the caller's assertion
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                            dispatch=dispatch)
        joined = " | ".join(caught.exception.errors)
        self.assertIn(WW.CODE_EXECUTION_STAMP, joined)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, joined)

    def test_execution_parameter_is_refused_by_name(self):
        body = fixture_body()
        run_dir = tempfile.mkdtemp(prefix="world_exec_")
        AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
        with self.assertRaises(WW.WorldError) as caught:
            WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_exec_001", inputs=FIXTURE_INPUTS,
                               runner=WW.no_spend_transport(fixture_runner(body, [])),
                               now=FIXTURE_NOW, execution="live")
        self.assertIn(WW.CODE_EXECUTION_STAMP, " | ".join(caught.exception.errors))
        # nothing was recorded: the refusal happens before the call
        self.assertEqual([a["attempt_id"] for a in AM.load_bindings(run_dir)["attempts"]], [])

    def test_live_transport_stamps_live(self):
        body = fixture_body()
        requests = []
        run_dir = tempfile.mkdtemp(prefix="world_live_kind_")
        AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
        dispatch = WW.dispatch_author(
            run_dir=run_dir, attempt_id="attempt_live_kind_001", inputs=FIXTURE_INPUTS,
            runner=WW.live_transport(fixture_runner(body, requests)), now=FIXTURE_NOW)
        self.assertEqual(dispatch["execution"], "live")
        self.assertEqual(dispatch["_handle"].execution, "live")
        # and the stamp cannot be talked down to the cheaper claim either
        dispatch["execution"] = "no_spend_fixture"
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                            dispatch=dispatch)
        self.assertIn(WW.CODE_EXECUTION_STAMP, " | ".join(caught.exception.errors))

    def test_receipt_kind_and_registration_stay_agreed(self):
        body = fixture_body()
        run_dir = tempfile.mkdtemp(prefix="world_receipt_kind_")
        AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL, runtime="claude-nine", now=FIXTURE_NOW)
        runner = WW.no_spend_transport(fixture_runner(body, []))
        dispatch = WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_receipt_001",
                                      inputs=FIXTURE_INPUTS, runner=runner, now=FIXTURE_NOW)
        self.assertEqual(dispatch["seal"]["receipt"]["kind"], "no_spend")
        self.assertEqual(dispatch["seal"]["receipt"]["kind"], dispatch["_handle"].transport_kind)
        forged = copy.deepcopy(dispatch)
        forged["seal"]["receipt"]["kind"] = "live"
        with self.assertRaises(WW.WorldError) as caught:
            WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                            dispatch=forged)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, " | ".join(caught.exception.errors))


class BindingIdentityTests(unittest.TestCase):
    """binding_id is recomputed from the admitted binding, never echoed."""

    def expected_binding_id(self):
        """The identity ai_models.bind_roles itself computes for this pair."""
        run_dir = tempfile.mkdtemp(prefix="world_binding_expect_")
        bound = AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL,
                              runtime="claude-nine", now=FIXTURE_NOW)
        assert bound.get("ok"), bound
        return bound["binding_id"]

    def test_forged_binding_id_is_not_echoed_into_provenance(self):
        body = fixture_body()
        run_dir = tempfile.mkdtemp(prefix="world_forged_binding_")
        forged_bindings(run_dir)                      # binding_id: "forgedbinding001"
        dispatch, _, run_dir = fixture_dispatch(body, run_dir=run_dir,
                                                attempt_id="attempt_forged_binding_001")
        self.assertEqual(AM.load_bindings(run_dir)["binding_id"], "forgedbinding001")
        provenance_attempt = dispatch["attempt"]
        self.assertNotEqual(provenance_attempt["binding_id"], "forgedbinding001")
        self.assertEqual(provenance_attempt["binding_id"], self.expected_binding_id())
        self.assertEqual(provenance_attempt["binding_id_source"],
                         "recomputed_from_admitted_binding")
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        self.assertEqual(record["provenance"]["attempt"]["binding_id"],
                         self.expected_binding_id())
        self.assertNotIn("forgedbinding001", json.dumps(record))
        self.assertEqual(WW.validate(record), [])

    def test_recomputed_identity_is_the_one_the_binding_content_carries(self):
        body = fixture_body()
        run_dir = tempfile.mkdtemp(prefix="world_binding_content_")
        forged_bindings(run_dir)
        dispatch, _, _ = fixture_dispatch(body, run_dir=run_dir,
                                          attempt_id="attempt_binding_content_001")
        derived = dispatch["attempt"]["binding_id"]
        doc = AM.load_bindings(run_dir)
        by_hand = hashlib.sha256(json.dumps(
            {"build": doc["bindings"]["build"]["model_id"],
             "check": doc["bindings"]["check"]["model_id"],
             "bound_at": doc["bound_at"]}, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        self.assertEqual(derived, by_hand)
        self.assertRegex(derived, r"^[0-9a-f]{16}$")

    def test_unusable_stored_binding_is_refused_by_name(self):
        run_dir = tempfile.mkdtemp(prefix="world_unusable_binding_")
        store = forged_bindings(run_dir)
        doc = json.load(open(store, encoding="utf-8"))
        doc["bindings"]["build"]["model_id"] = "nosuch/made-up-model-001"
        with open(store, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=1, sort_keys=True)
        body = fixture_body()
        with self.assertRaises(WW.WorldError) as caught:
            WW.dispatch_author(run_dir=run_dir, attempt_id="attempt_unusable_001",
                               inputs=FIXTURE_INPUTS,
                               runner=WW.no_spend_transport(fixture_runner(body, [])),
                               now=FIXTURE_NOW)
        joined = " | ".join(caught.exception.errors)
        self.assertIn(WW.CODE_BINDING_STAMP, joined)
        self.assertIn(WW.CODE_DISPATCH_UNPROVEN, joined)
        self.assertEqual([a["attempt_id"] for a in AM.load_bindings(run_dir)["attempts"]], [])


class PositiveControlTests(unittest.TestCase):
    """The genuine no-spend transport still seals everything above."""

    def test_positive_control_seals_through_the_genuine_no_spend_transport(self):
        body = fixture_body()
        dispatch, requests, run_dir = fixture_dispatch(body)
        self.assertEqual(len(requests), 1)
        record = WW.author_world(body, artifact_id="world_workshop_001", run_id="run_test_001",
                                 dispatch=dispatch)
        self.assertEqual(WW.validate(record), [])
        seal = record["seal"]
        self.assertRegex(seal["dispatch_handle"], r"^[0-9a-f]{64}$")
        self.assertRegex(seal["receipt"]["nonce"], r"^[0-9a-f]{32}$")
        self.assertEqual(seal["receipt"]["kind"], "no_spend")
        self.assertEqual(seal["seal_digest"], WW.seal_digest(seal, record["content_digest"]))
        self.assertEqual(record["provenance"]["execution"], "no_spend_fixture")
        self.assertEqual(record["provenance"]["attempt"]["binding_id"],
                         AM.load_bindings(run_dir)["binding_id"])
        self.assertEqual(record["content_digest"], WW.canonical_digest(record))
        print("\nPOSITIVE CONTROL: sealed %s on handle %s (%s, binding %s)"
              % (record["content_digest"][:16], seal["dispatch_handle"][:16],
                 record["provenance"]["execution"], record["provenance"]["attempt"]["binding_id"]))


#: Round 4 uses a catalog pair no earlier round touched.
R4_BUILD_MODEL = "ollama/deepseek-v4.1-flash"
R4_CHECK_MODEL = "ollama/agnes"
R4_NOW = "2026-10-24T06:00:00+00:00"
R4_INPUTS = {
    "research_revision": "research_claims@7",
    "premise_revision": "premise@4",
    "cast_interface": ["char_okonkwo_011@4", "char_bauer_023@2"],
    "route_style_constraints": "realistic community drama",
    "known_locations": ["loc_depot_hall_014", "loc_yard_gate_021"],
    "owner_answer_refs": ["owner_answer_014"],
}


def depot_place(location_id, name, function, entrances, geography, features,
                boundaries, sightlines, time_of_day, rules, must_persist, may_change,
                source, direction, motivated_change=None, interior=True):
    """One location record carrying the five carriers the validator must read:
    era, social rules, lighting, layout and continuity boundaries."""
    place = {
        "location_id": location_id, "name": name, "function": function,
        "interior": interior, "reality": "fiction",
        "access": "the four volunteers on the inventory rota",
        "entrances": entrances, "geography": geography,
        "era": {"period": "contemporary", "time_of_day": time_of_day},
        "social_rules": [{"rule": rule, "consequence": consequence}
                         for rule, consequence in rules],
        "lighting": {"source": source, "direction": direction},
        "layout": {"features": features, "boundaries": boundaries,
                   "sightlines": sightlines},
        "continuity_boundaries": {"must_persist": must_persist,
                                  "may_change": may_change},
    }
    if motivated_change:
        place["lighting"]["motivated_change"] = motivated_change
    return place


def depot_hall():
    return depot_place(
        "loc_depot_hall_014", "Tram depot, main hall",
        "where the volunteers count the tools they may have to give back",
        ["north roller door", "staff door to the yard"],
        "north roller door, west tool wall, centre inventory table, "
        "east parts counter, south staff door",
        ["north roller door", "west tool wall", "centre inventory table",
         "east parts counter", "south staff door"],
        "brick on three sides under a glazed roof, roller door closes the north end",
        "the inventory table is seen from the tool wall; the parts counter hides the staff door",
        "late afternoon into evening",
        [("a tool leaves the depot only against a signed inventory line",
          "an unsigned loan is repaid by the volunteer who let it go"),
         ("the lease papers stay in the office safe until the meeting",
          "reading them early turns the count into a blame meeting")],
        ["the signed inventory sheet stays open on the table",
         "the tool wall keeps its full shadow board"],
        ["the roller door position once the rain starts"],
        "sodium work lamps on the depot beams", "downward, warm and uneven",
        "yard lamps come on when the roller door closes")


def depot_gate():
    return depot_place(
        "loc_yard_gate_021", "Depot yard, gate end",
        "where the tools are loaded out and the leaving is watched",
        ["yard gate", "south staff door"],
        "yard gate west, loading strip centre, rain shelter east",
        ["yard gate", "loading strip", "rain shelter"],
        "chain-link fence on three sides, the depot wall behind the shelter",
        "the loading strip is seen from the gate; the rain shelter hides the wall door",
        "evening, after the rain",
        [("nothing leaves the yard without a second volunteer watching",
          "a lone load-out is logged as a loss and the depot closes early")],
        ["the loading strip stays clear of parked vans"],
        ["the gate padlock state after the last load"],
        "yard lamps on the fence posts", "low, cold and flat")


def depot_body():
    return {
        "premise": ("A volunteer tool library inside a disused tram depot faces the loss of its "
                    "lease. Realistic community drama; an inventory night forces the volunteers "
                    "to decide what they can replace."),
        "fiction_classification": "proposed_fiction",
        "era": {"period": "contemporary", "time_of_day": "one late afternoon into evening",
                "season_weather": "autumn, wet", "time_jumps": [], "span_minutes": 90},
        "locations": [depot_hall(), depot_gate()],
        "light": {
            "doctrine": "warm work light over the count against cold yard light at the edges; "
                        "no unexplained change of hour",
            "sources": [
                {"source": "sodium work lamps", "direction": "downward, warm and uneven",
                 "motivated_change": "half of them go out when the count ends"},
                {"source": "yard lamps", "direction": "low and cold across the gate"},
            ],
        },
        "palette": ["sodium amber", "wet grey concrete", "faded depot green"],
        "texture": ["pitted concrete", "chipped enamel", "oiled tool steel"],
        "sound": {"ambience": "rain on the glazed roof, a distant tram bell",
                  "off_screen": ["the gate being chained"], "silence": ["the last count line"]},
        "never_list": ["no miracle new lease", "no unnamed donor", "no real depot document"],
        "cast_refs": [{"character_id": "char_okonkwo_011", "identity_revision": 4},
                      {"character_id": "char_bauer_023", "identity_revision": 2}],
        "continuity": {"must_persist": ["the signed inventory sheet stays open",
                                        "the gate padlock stays on the post"],
                       "may_change": ["the roller door after the rain"],
                       "exceptions": []},
        "scenes": [{"scene_id": "scene_001", "location_id": "loc_depot_hall_014",
                    "action": "Okonkwo carries the inventory sheet from the roller door to the table",
                    "uses": ["north roller door", "centre inventory table"],
                    "minutes_from_start": 0}],
    }
def r4_runner(body, requests):
    """Deterministic no-spend runner on the R4 catalog pair: the response model
    is the bound build id and the resolved model is its provider request id."""
    def runner(request):
        requests.append(copy.deepcopy(request))
        return {"raw": copy.deepcopy(body),
                "response_model": R4_BUILD_MODEL,
                "resolved_provider_model": "deepseek-v4.1-flash",
                "provider_job_id": "r4-job-001"}
    return runner


def r4_dispatch(body, run_dir=None, attempt_id="attempt_r4_001", requests=None,
                runner_factory=None):
    """One no-spend dispatch on its own run dir, through the R4 catalog pair."""
    run_dir = run_dir or tempfile.mkdtemp(prefix="world_r4_")
    if AM.load_bindings(run_dir) is None:
        bound = AM.bind_roles(run_dir, R4_BUILD_MODEL, R4_CHECK_MODEL,
                              runtime="claude-nine", now=R4_NOW)
        assert bound.get("ok"), bound
    requests = [] if requests is None else requests
    runner = runner_factory(body, requests) if runner_factory else r4_runner(body, requests)
    runner = runner if isinstance(runner, WW.DispatchTransport) else WW.no_spend_transport(runner)
    record = WW.dispatch_author(run_dir=run_dir, attempt_id=attempt_id, inputs=R4_INPUTS,
                                runner=runner, now=R4_NOW)
    return record, requests, run_dir


def r4_author(body=None, artifact_id="world_depot_014", run_id="run_r4_001", **kw):
    body = depot_body() if body is None else body
    record, _, _ = r4_dispatch(body, **kw)
    return WW.author_world(body, artifact_id=artifact_id, run_id=run_id, dispatch=record)


def stub_place(location_id="loc_stub_001"):
    """The shape-only location a caller writes when presence is mistaken for
    validity: an id, a name, one feature and nothing that constrains anything."""
    return {"location_id": location_id, "name": "A room", "function": "a room",
            "interior": True, "reality": "fiction",
            "layout": {"features": ["a window"]}}


class Round4LocationSubstanceTests(unittest.TestCase):
    """The world validator's own proxy-for-validity disease: a location record
    must actually carry era, social rules, lighting, layout and continuity
    boundaries -- presence of a shape is not validity."""

    def assert_refused(self, body, needle):
        with self.assertRaises(WW.WorldError) as caught:
            r4_author(body)
        self.assertIn(needle, " | ".join(caught.exception.errors))

    def test_shape_only_location_refused(self):
        body = depot_body()
        body["locations"] = [stub_place()]
        body["scenes"] = [{"scene_id": "scene_001", "location_id": "loc_stub_001",
                           "action": "a beat plays", "uses": ["a window"],
                           "minutes_from_start": 0}]
        joined = ""
        for carrier in ("era", "social_rules", "lighting", "continuity_boundaries"):
            with self.assertRaises(WW.WorldError) as caught:
                r4_author(body)
            joined = " | ".join(caught.exception.errors)
            self.assertIn(carrier, joined)

    def test_empty_social_rules_refused(self):
        body = depot_body()
        body["locations"][0]["social_rules"] = []
        self.assert_refused(body, "locations[0].social_rules")

    def test_social_rule_without_consequence_refused(self):
        body = depot_body()
        del body["locations"][0]["social_rules"][0]["consequence"]
        self.assert_refused(body, "social_rules[0].consequence")

    def test_lighting_without_direction_refused(self):
        body = depot_body()
        del body["locations"][0]["lighting"]["direction"]
        self.assert_refused(body, "lighting.direction")

    def test_layout_without_boundaries_refused(self):
        body = depot_body()
        del body["locations"][0]["layout"]["boundaries"]
        self.assert_refused(body, "layout.boundaries")

    def test_continuity_boundaries_without_must_persist_refused(self):
        body = depot_body()
        body["locations"][0]["continuity_boundaries"] = {"must_persist": []}
        self.assert_refused(body, "continuity_boundaries")

    def test_era_carriers_refused_when_absent(self):
        body = depot_body()
        del body["locations"][1]["era"]
        self.assert_refused(body, "locations[1].era")

    def test_placeholder_text_is_not_world_content(self):
        body = depot_body()
        body["locations"][0]["social_rules"][0]["rule"] = "tbd"
        self.assert_refused(body, "locations[0].social_rules[0].rule")

    def test_field_name_echo_is_not_world_content(self):
        body = depot_body()
        body["locations"][0]["layout"]["sightlines"] = "sightlines"
        self.assert_refused(body, "locations[0].layout.sightlines")

    def test_repeated_entries_are_not_content(self):
        body = depot_body()
        body["locations"][0]["social_rules"] = [
            {"rule": "a tool leaves the depot only against a signed inventory line",
             "consequence": "an unsigned loan is repaid by the volunteer who let it go"},
            {"rule": "a tool leaves the depot only against a signed inventory line",
             "consequence": "an unsigned loan is repaid by the volunteer who let it go"}]
        self.assert_refused(body, "social_rules")

    def test_repeated_entrances_are_not_content(self):
        body = depot_body()
        body["locations"][1]["entrances"] = ["yard gate", "yard gate"]
        self.assert_refused(body, "entrances")


class Round4OverRefusalTests(unittest.TestCase):
    """Every legitimate shape must still be accepted: a stricter validator must
    not refuse a real world, a real setting change or a real dispatch."""

    def test_full_world_still_authors_and_validates(self):
        record = r4_author()
        self.assertEqual(WW.validate(record), [])
        self.assertEqual(WW.validate(json.loads(json.dumps(record))), [])

    def test_cli_validate_still_judgement_only(self):
        record = r4_author()
        run_dir = tempfile.mkdtemp(prefix="world_r4_cli_")
        path = os.path.join(run_dir, "world.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = WW.main(["--validate", path])
        self.assertEqual(code, 0)

    def test_real_location_with_claim_source_accepted(self):
        body = depot_body()
        body["locations"][0]["reality"] = "real"
        body["locations"][0]["claim_source"] = "owner_answer_014: the client named this address"
        self.assertEqual(WW.validate(r4_author(body)), [])

    def test_nothing_may_change_is_a_real_answer(self):
        body = depot_body()
        body["locations"][0]["continuity_boundaries"]["may_change"] = []
        self.assertEqual(WW.validate(r4_author(body)), [])

    def test_two_places_may_share_a_house_rule(self):
        # a stricter validator must not refuse a world where two places of the
        # same house genuinely carry the same rule
        body = depot_body()
        body["locations"][1]["social_rules"] = copy.deepcopy(body["locations"][0]["social_rules"])
        self.assertEqual(WW.validate(r4_author(body)), [])

    def test_travel_and_motivated_flashback_accepted(self):
        body = depot_body()
        body["scenes"].append({"scene_id": "scene_002", "location_id": "loc_yard_gate_021",
                               "action": "Bauer carries the sheet to the gate",
                               "uses": ["yard gate"], "minutes_from_start": 20})
        body["scenes"].append({"scene_id": "scene_003", "location_id": "loc_depot_hall_014",
                               "action": "a flash back to the first count line",
                               "uses": ["centre inventory table"], "minutes_from_start": 0,
                               "transition": "deliberate flashback, motivated by the sheet"})
        self.assertEqual(WW.validate(r4_author(body)), [])

    def test_setting_change_to_a_full_new_place_accepted(self):
        original = r4_author()
        new_place = depot_place(
            "loc_hall_annex_030", "Borrowed annexe, upstairs room",
            "where the count is finished after the depot is given back",
            ["stair door"], "stair door north, trestle tables centre, window wall south",
            ["stair door", "trestle tables", "window wall"],
            "plaster walls, sash window wall on the south side",
            "the trestle tables are seen from the stair door; the window wall hides the corner",
            "late evening",
            [("the count sheet is read aloud before any tool is moved",
              "moving a tool first makes the reading worthless")],
            ["the count sheet keeps its running total"],
            ["which table holds the finished boxes"],
            "one ceiling pendant", "downward, warm and single")
        result = WW.change_setting(original, locations=[new_place], reason="the depot is given back")
        world = result["world"]
        self.assertEqual(WW.validate(world), [])
        self.assertEqual(world["cast_refs"], original["cast_refs"])
        self.assertEqual(result["invalidated"], ["scene_plan", "script", "visual_outputs"])

    def test_round3_workshop_world_still_authors(self):
        self.assertEqual(WW.validate(author()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
