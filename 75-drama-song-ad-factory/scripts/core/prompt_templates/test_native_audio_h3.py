#!/usr/bin/env python3
"""H3 native-audio policy: decision on the request, echo on the receipt,
double-music detection at the layering boundary.

minimax-h3/* always returns a stereo track and the provider exposes no flag
to disable it (references/prompt-templates/models/minimax-h3.json
native_audio). The policy is therefore a POST-PROCESSING decision, never a
provider flag:

  (a) a request carries the decision; the contract default is strip;
  (b) receipt() echoes the decision, provider_can_disable False and the
      observed delivery evidence, so the mixing decision is auditable;
  (c) layering_refusal fires DOUBLE_MUSIC whenever an approved soundtrack
      rides a take that still carries generated audio (retain, or a
      strip/reduce decision whose observed take was not removed);
  (d) it stays quiet for strip/reduce once the audio is actually removed,
      and when no soundtrack is layered at all;
  (e) a missing or unknown decision fails closed at that boundary;
  (f) an unknown decision on a request raises -- a typo never silently
      becomes a strip.

Stdlib only, offline, no spend.
Run: python3 scripts/core/prompt_templates/test_native_audio_h3.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (HERE, CORE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt_templates as PT  # noqa: E402


SPEC = {"shot_id": "S02", "model": "minimax-h3/image-to-video",
        "look": "2d-hand-painted", "mode": "painted-2d",
        "shot_type": "motion-broll"}


def _block(spec):
    return PT.receipt(spec, "prompt text", {"header": 11},
                      {"verdict": "PASS", "reasons": []})


def test_default_decision_is_strip():
    assert PT.H3_NATIVE_AUDIO_DEFAULT == "strip"
    block = PT.native_audio_block(SPEC)
    assert block["decision"] == "strip"
    assert block["provider_can_disable"] is False
    assert block["enforcement"] == "post_processing"
    assert block["prompt_ambition"] == "silent"
    assert block["observed"] is None


def test_request_carries_an_explicit_decision():
    block = PT.native_audio_block({"native_audio": "reduce_music"})
    assert block["decision"] == "reduce_music"
    block = PT.native_audio_block(
        {"native_audio": {"decision": "retain", "observed":
                          {"has_audio": True, "removed": False}}})
    assert block["decision"] == "retain"
    assert block["observed"] == {"has_audio": True, "removed": False}


def test_unknown_decision_fails_closed_on_the_request():
    for bad in ("mute", "REMOVE_ALL", 7):
        try:
            PT.native_audio_block({"native_audio": bad})
        except PT.PromptTemplateError as exc:
            assert exc.code == "H3_NATIVE_AUDIO_UNKNOWN", exc.code
        else:
            raise AssertionError("accepted an unknown decision %r" % (bad,))


def test_receipt_echoes_the_decision_and_the_observation():
    rec = _block(dict(SPEC, native_audio={
        "decision": "strip",
        "observed": {"has_audio": True, "removed": True}}))
    assert rec["native_audio"]["decision"] == "strip"
    assert rec["native_audio"]["provider_can_disable"] is False
    assert rec["native_audio"]["observed"] == {"has_audio": True,
                                              "removed": True}
    # the older receipt keys are untouched
    for key in ("shot_id", "prompt_sha256", "chars", "band", "check"):
        assert key in rec


def test_strip_and_reduce_stay_quiet_once_the_audio_is_removed():
    for decision in ("strip", "reduce_music"):
        block = PT.native_audio_block(
            {"native_audio": {"decision": decision,
                              "observed": {"has_audio": True,
                                           "removed": True}}})
        assert PT.layering_refusal(block, soundtrack=True) is None


def test_no_soundtrack_is_never_a_layering_refusal():
    retained = PT.native_audio_block({"native_audio": "retain"})
    assert PT.layering_refusal(retained, soundtrack=False) is None
    assert PT.layering_refusal(None, soundtrack=False) is None


def test_unmeasured_take_is_unverified_unless_the_render_drops_its_audio():
    unmeasured = PT.native_audio_block({"native_audio": "strip"})
    # a mixer that would carry the take's audio may not guess:
    bad = PT.layering_refusal(unmeasured, soundtrack=True)
    assert bad and bad["reason_code"] == "NATIVE_AUDIO_UNVERIFIED"
    # the final assembler maps ONLY the song (clip audio is dropped), so an
    # unmeasured take is provably silent in its output.
    assert PT.layering_refusal(unmeasured, soundtrack=True,
                               audio_dropped=True) is None


def test_generated_audio_plus_soundtrack_is_double_music():
    retained = PT.native_audio_block({"native_audio": "retain"})
    bad = PT.layering_refusal(retained, soundtrack=True)
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"

    # declared strip, but the take still carries its generated track
    stale = PT.native_audio_block(
        {"native_audio": {"decision": "strip",
                          "observed": {"has_audio": True, "removed": False}}})
    bad = PT.layering_refusal(stale, soundtrack=True)
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"

    # declared reduce, but the music was never ducked out
    stale = PT.native_audio_block(
        {"native_audio": {"decision": "reduce_music",
                          "observed": {"has_audio": True, "removed": False}}})
    bad = PT.layering_refusal(stale, soundtrack=True)
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"


def test_missing_decision_fails_closed_at_the_layering_boundary():
    for absent in (None, {}, {"decision": "mute"}, {"decision": ""},
                   {"observed": {"has_audio": True, "removed": True}}):
        bad = PT.layering_refusal(absent, soundtrack=True)
        assert bad and bad["reason_code"] == "DOUBLE_MUSIC", (absent, bad)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok %s" % name)
    print("all native-audio policy tests passed")


if __name__ == "__main__":
    main()
