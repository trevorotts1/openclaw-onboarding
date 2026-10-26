#!/usr/bin/env python3
"""Focused tests for script_writer (S75-T10 / S75-A10).

Proves the supported route actually DISPATCHES an authoring request and yields
complete authored script/lyrics from the recorded no-spend fixture -- a
validator that only opens a prewritten JSON cannot pass these.

Run: python3 -m pytest -q scripts/core/test_script_writer.py
 or: python3 scripts/core/test_script_writer.py
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import script_writer as W  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "rich_script.json")


def _fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _authored(record=None):
    return json.loads((record or _fixture())["response"]["raw_text"])


def _response(authored, response_id="fixture-response-s75-t10-001"):
    return {
        "response_id": response_id,
        "provider": "recorded-fixture",
        "model": "recorded-fixture",
        "effective_binding": {"provider": "recorded-fixture", "model": "recorded-fixture"},
        "raw_text": json.dumps(authored, sort_keys=True),
    }


def _writer(**overrides):
    record = _fixture()
    registry = W.registry_from_foundation(copy.deepcopy(record["foundation"]))
    return record, registry


def _run(record, registry, responses):
    seen = []

    def dispatch(request):
        seen.append(request)
        index = min(len(seen) - 1, len(responses) - 1)
        return responses[index]

    result = W.write(registry, dispatch, model_binding=record["model_binding"],
                     constraints=record["constraints"])
    return result, seen


def _defect_codes(defects):
    return sorted({d["code"] for d in defects})


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except W.WriterRefused as exc:
        return exc
    raise AssertionError("writer did not refuse")


# --- route-level proof ----------------------------------------------------

def test_recorded_fixture_replays_through_the_real_writer():
    record = _fixture()
    result = W.replay_fixture(record)
    assert result["dispatch_count"] == 1
    assert result["idempotent_replay"] is False
    dispatch = result["receipt"]["dispatches"][0]
    assert dispatch["response_id"] == record["expected"]["response_id"]
    assert dispatch["requested_binding"] == record["model_binding"]
    assert dispatch["raw_sha256"]
    assert result["script"]["revision"] == record["expected"]["script_revision"]
    assert result["lyrics"]["revision"] == record["expected"]["lyrics_revision"]
    assert [s["scene_id"] for s in result["script"]["payload"]["scenes"]] == \
        record["expected"]["scene_ids"]


def test_dispatch_request_carries_the_full_foundation_not_keywords():
    record = _fixture()
    request = record["request"]
    prompt = request["messages"][0]["content"]
    assert request["prompt_revision"] == W.PROMPT_REVISION
    assert request["attempt"] == 1
    assert request["idempotency_key"]
    for scene_id in record["foundation"]["scene_plan"]["scenes"]:
        assert scene_id["scene_id"] in prompt
    for cid in record["foundation"]["episode_cast_manifest"]["cast"]:
        assert cid["character_id"] in prompt
    assert "claim_001" in prompt
    for kind in W.REQUIRED_FOUNDATION:
        assert request["foundation"][kind]["digest"]


def test_authored_words_are_new_not_copied_from_the_plan():
    record, registry = _writer()
    authored = _authored(record)
    plan_text = {ln["text"] for s in registry.payload_of("scene_plan")["scenes"]
                 for field in ("spoken_dialogue", "sung_lyrics") for ln in s.get(field) or []}
    written = {ln["text"] for s in authored["scenes"]
               for field in ("spoken_dialogue", "sung_lyrics") for ln in s.get(field) or []}
    assert written and not (written & plan_text)
    assert any(ln.get("start_s") is not None for s in authored["scenes"]
               for field in ("spoken_dialogue", "sung_lyrics") for ln in s.get(field) or [])


def test_artifacts_bind_exact_foundation_digests():
    record = _fixture()
    result = W.replay_fixture(record)
    bound = result["script"]["payload"]["bound_foundation"]
    for kind in W.REQUIRED_FOUNDATION:
        assert bound[kind]["digest"] == record["request"]["foundation"][kind]["digest"]
    assert result["lyrics"]["payload"]["scene_plan_digest"] == bound["scene_plan"]["digest"]


# --- foundation gate ------------------------------------------------------

def test_missing_foundation_never_reaches_the_dispatcher():
    for missing in ("scene_plan", "character_identity_library_snapshot", "episode_cast_manifest"):
        record, registry = _writer()
        registry._artifacts.pop(missing, None)  # noqa: SLF001 - test drives the registry
        calls = []
        exc = _raises(W.write, registry, lambda req: calls.append(req),
                      model_binding=record["model_binding"],
                      constraints=record["constraints"])
        assert exc.code == "MISSING_FOUNDATION"
        assert exc.packet["kind"] == missing
        assert calls == []


def test_incomplete_cast_is_a_missing_requirement():
    record, registry = _writer()
    manifest = copy.deepcopy(registry.payload_of("episode_cast_manifest"))
    manifest["cast"][0].pop("identity_digest")
    registry.put("episode_cast_manifest", manifest)
    calls = []
    exc = _raises(W.write, registry, lambda req: calls.append(req),
                  model_binding=record["model_binding"], constraints=record["constraints"])
    assert exc.code == "INCOMPLETE_FOUNDATION"
    assert exc.packet["kind"] == "episode_cast_manifest"
    assert calls == []


def test_missing_identity_revision_stops_before_dispatch():
    record, registry = _writer()
    snapshot = copy.deepcopy(registry.payload_of("character_identity_library_snapshot"))
    snapshot["identities"]["char_levi_002"]["revision"] = 2
    registry.put("character_identity_library_snapshot", snapshot)
    calls = []
    exc = _raises(W.write, registry, lambda req: calls.append(req),
                  model_binding=record["model_binding"], constraints=record["constraints"])
    assert exc.code == "INCOMPLETE_FOUNDATION"
    assert any("char_levi_002" in f for f in exc.packet["fields"])
    assert calls == []


def test_validator_alone_cannot_claim_generated_output():
    record, registry = _writer()
    assert W.validate_authored(_authored(record), W.build_foundation(registry)) == []
    exc = _raises(W.write, registry, None, model_binding=record["model_binding"],
                  constraints=record["constraints"])
    assert exc.code == "NO_DISPATCH"
    assert registry.get("script") is None and registry.get("lyrics") is None


# --- targeted revision ----------------------------------------------------

def test_placeholder_line_triggers_targeted_revision_then_passes():
    record, registry = _writer()
    broken = _authored(record)
    broken["scenes"][0]["spoken_dialogue"][0]["text"] = "..."
    good = _authored(record)
    result, seen = _run(record, registry, [_response(broken, "r1"), _response(good, "r2")])
    assert len(seen) == 2
    assert seen[1]["attempt"] == 2
    assert seen[1]["revision"]["defects"]
    assert any(d.get("line_id") == "line_mara_001" for d in seen[1]["revision"]["defects"])
    assert result["receipt"]["attempts"] == 2
    assert result["script"]["payload"]["scenes"][0]["spoken_dialogue"][0]["text"] != "..."


def test_unchanged_defects_stop_after_two_attempts():
    record, registry = _writer()
    broken = _authored(record)
    broken["scenes"][0]["spoken_dialogue"][0]["text"] = "..."
    calls = []

    def dispatch(request):
        calls.append(request)
        return _response(broken, "r%d" % len(calls))

    exc = _raises(W.write, registry, dispatch, model_binding=record["model_binding"],
                  constraints=record["constraints"])
    assert exc.code == "UNPRODUCTIVE_REVISION"
    assert exc.packet["attempts"] == 2
    assert exc.packet["candidate"]["scenes"]
    assert len(calls) == 2


# --- semantic refusals ----------------------------------------------------

def test_spoken_opening_missing_is_named():
    record, registry = _writer()
    authored = _authored(record)
    for line in authored["scenes"][0]["spoken_dialogue"]:
        line["start_s"] = 14.0
        line["end_s"] = 16.0
    codes = _defect_codes(W.validate_authored(authored, W.build_foundation(registry)))
    assert "SPOKEN_OPENING_MISSING" in codes


def test_solution_and_transformation_are_earned():
    record, registry = _writer()
    foundation = W.build_foundation(registry)
    missing = _authored(record)
    for scene in missing["scenes"]:
        scene.pop("solution_introduced", None)
    assert "SOLUTION_MISSING" in _defect_codes(W.validate_authored(missing, foundation))

    early = _authored(record)
    early["scenes"][0]["solution_introduced"] = True
    assert "SOLUTION_UNEARNED" in _defect_codes(W.validate_authored(early, foundation))

    flat = _authored(record)
    for scene in flat["scenes"]:
        scene.pop("behavior_change", None)
    assert "TRANSFORMATION_UNSHOWN" in _defect_codes(W.validate_authored(flat, foundation))


def test_one_cta_after_the_earned_outcome():
    record, registry = _writer()
    foundation = W.build_foundation(registry)
    two = _authored(record)
    two["scenes"][1]["sung_lyrics"][0]["role"] = "cta"
    assert "CTA_COUNT" in _defect_codes(W.validate_authored(two, foundation))

    early = _authored(record)
    cta = early["scenes"][2]["spoken_dialogue"].pop()
    cta.pop("role")
    early["scenes"][0]["spoken_dialogue"].append(dict(cta, role="cta"))
    early["cta"]["line_id"] = cta["line_id"]
    assert "CTA_EARLY" in _defect_codes(W.validate_authored(early, foundation))


def test_lyric_sheet_must_reconcile_with_scene_performance():
    record, registry = _writer()
    foundation = W.build_foundation(registry)
    extra = _authored(record)
    extra["lyric_sheet"]["lines"].append({
        "line_id": "line_orphan_999", "character_id": "char_mara_001",
        "text": "a line that no scene ever performs", "section": "chorus"})
    assert "LYRIC_LINE_UNBOUND" in _defect_codes(W.validate_authored(extra, foundation))

    drift = _authored(record)
    drift["scenes"][0]["sung_lyrics"][0]["text"] = "a different draft of the same song"
    assert "LYRIC_LINE_MISSING" in _defect_codes(W.validate_authored(drift, foundation))


def test_undefined_speaker_is_refused():
    record, registry = _writer()
    foundation = W.build_foundation(registry)
    ghost = _authored(record)
    ghost["scenes"][1]["sung_lyrics"].append({
        "line_id": "line_ghost_001", "character_id": "char_ghost_009",
        "text": "nobody declared me in the cast", "start_s": 20.0, "end_s": 22.0,
        "delivery": "sung"})
    codes = _defect_codes(W.validate_authored(ghost, foundation))
    assert codes
    assert set(codes) & {"UNDEFINED_PERFORMER", "SCENE_SCHEMA"}


def test_causal_gap_is_named_with_its_pointer():
    record, registry = _writer()
    foundation = W.build_foundation(registry)
    broken = _authored(record)
    broken["scenes"][2]["causal_predecessor"] = "out_999"
    defects = W.validate_authored(broken, foundation)
    gap = [d for d in defects if d["code"] == "CAUSAL_GAP"]
    assert gap and gap[0]["pointer"] == "/scenes/2/causal_predecessor"


# --- idempotency ----------------------------------------------------------

def test_repeated_write_uses_the_ledger_and_skips_dispatch():
    record, registry = _writer()
    ledger = W.RevisionLog()
    calls = []

    def dispatch(request):
        calls.append(request)
        return _response(_authored(record))

    first = W.write(registry, dispatch, model_binding=record["model_binding"],
                    constraints=record["constraints"], ledger=ledger)
    second = W.write(registry, dispatch, model_binding=record["model_binding"],
                     constraints=record["constraints"], ledger=ledger)
    assert len(calls) == 1
    assert second["idempotent_replay"] is True
    assert second["script"]["digest"] == first["script"]["digest"]
    assert second["lyrics"]["digest"] == first["lyrics"]["digest"]


def test_changed_foundation_changes_the_idempotency_key():
    record, registry = _writer()
    first = W.build_request(W.build_foundation(registry), record["constraints"],
                            record["model_binding"])
    world = copy.deepcopy(registry.payload_of("episode_world"))
    world["wardrobe_intent"] = "Heavy canvas aprons over work shirts."
    registry.put("episode_world", world)
    second = W.build_request(W.build_foundation(registry), record["constraints"],
                             record["model_binding"])
    assert first["run_key"] != second["run_key"]


def test_module_makes_no_network_calls():
    source = open(os.path.abspath(W.__file__), encoding="utf-8").read()
    for forbidden in ("urllib", "http.client", "import socket", "from socket", "import requests"):
        assert forbidden not in source


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)
