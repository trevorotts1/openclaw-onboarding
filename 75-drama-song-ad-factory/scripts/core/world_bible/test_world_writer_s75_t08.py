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
"""
import copy
import json
import os
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
             "layout": {"features": ["south glass door", "north tool bench",
                                     "centre ledger table", "east counter", "west corridor"]}},
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


def fixture_dispatch(body, run_dir=None, attempt_id="attempt_fixture_001", requests=None):
    """One no-spend dispatch through the supported model layer, on its own run dir."""
    run_dir = run_dir or tempfile.mkdtemp(prefix="world_fixture_")
    if AM.load_bindings(run_dir) is None:
        bound = AM.bind_roles(run_dir, BUILD_MODEL, CHECK_MODEL,
                              runtime="claude-nine", now=FIXTURE_NOW)
        assert bound.get("ok"), bound
    requests = [] if requests is None else requests
    record = WW.dispatch_author(run_dir=run_dir, attempt_id=attempt_id, inputs=FIXTURE_INPUTS,
                                runner=WW.no_spend_transport(fixture_runner(body, requests)),
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
        body["locations"].append({
            "location_id": "loc_back_bay_001", "name": "Repair bay, west corridor end",
            "function": "the second room of the same evening", "interior": True,
            "reality": "fiction", "access": "the two partners only",
            "layout": {"features": ["west corridor door", "repair bench"]}})
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
        body["locations"].append({
            "location_id": "loc_back_bay_001", "name": "Repair bay, west corridor end",
            "function": "the second room of the same evening", "interior": True,
            "reality": "fiction", "access": "the two partners only",
            "layout": {"features": ["west corridor door", "repair bench"]}})
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
        new_locations = [{
            "location_id": "loc_formal_hall_001",
            "name": "Formal civic hall, east room",
            "function": "the meeting where the shortfall is disclosed",
            "interior": True,
            "reality": "fiction",
            "access": "invited guests only",
            "entrances": ["east corridor door"],
            "geography": "long table centre, dais north, doors east and south",
            "layout": {"features": ["long table", "dais", "east corridor door", "south door"]},
        }]
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
            locations=[{"location_id": "loc_other_001", "name": "Other room",
                        "function": "alternate setting", "interior": True,
                        "reality": "fiction",
                        "layout": {"features": ["a window"]}}],
            reason="alternate setting for the same story",
        )
        self.assertEqual(result["invalidated"], ["scene_plan", "script", "visual_outputs"])
        for identity_surface in ("character_identity", "character_bible", "cast"):
            self.assertNotIn(identity_surface, result["invalidated"])

    def test_setting_change_without_reason_refused(self):
        with self.assertRaises(WW.WorldError):
            WW.change_setting(author(), locations=[
                {"location_id": "loc_other_001", "name": "Other", "function": "x",
                 "interior": True, "reality": "fiction",
                 "layout": {"features": ["a window"]}}], reason="")

    def test_setting_change_to_no_locations_refused(self):
        with self.assertRaises(WW.WorldError) as caught:
            WW.change_setting(author(), locations=[], reason="bad edit")
        self.assertIn("world has no locations", " | ".join(caught.exception.errors))

    def test_original_record_is_not_mutated(self):
        original = author()
        snapshot = copy.deepcopy(original)
        WW.change_setting(original, locations=[
            {"location_id": "loc_other_001", "name": "Other", "function": "x",
             "interior": True, "reality": "fiction",
             "layout": {"features": ["a window"]}}], reason="alternate")
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main(verbosity=2)
