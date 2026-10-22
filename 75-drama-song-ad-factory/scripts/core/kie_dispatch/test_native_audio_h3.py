#!/usr/bin/env python3
"""H3 native-audio gate at dispatch: an unusable decision never reaches spend.

minimax-h3 cannot be asked for silence (references/prompt-templates/models/
minimax-h3.json native_audio), so the mixing decision must be a recorded one
on the request or its prompt receipt:

  (a) an unknown decision (request-side or receipt-side) is refused
      H3_NATIVE_AUDIO_UNKNOWN before the ledger and before Skill 74;
  (b) a legacy receipt written before this policy carries no native_audio
      block and stays dispatchable -- the layering boundary is what fails
      closed, not an old receipt;
  (c) a request that declares soundtrack_layering fails closed when no
      decision can be audited, and refuses DOUBLE_MUSIC on retain;
  (d) non-H3 models are untouched.

Offline, stdlib only, no spend: the gate is pure.
Run: python3 scripts/core/kie_dispatch/test_native_audio_h3.py
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

H3 = "minimax-h3/text-to-video"


def _receipt(**extra):
    rec = {"prompt_sha256": "0" * 64, "check": {"verdict": "PASS"}}
    rec.update(extra)
    return rec


def test_a_legacy_receipt_without_the_block_stays_dispatchable():
    request = {"prompt_receipt": _receipt()}
    assert MODULE.native_audio_refusal(H3, request) is None


def test_b_unknown_request_decision_is_refused():
    bad = MODULE.native_audio_refusal(H3, {"native_audio": "mute"})
    assert bad and bad["reason_code"] == "H3_NATIVE_AUDIO_UNKNOWN"
    bad = MODULE.native_audio_refusal(
        H3, {"native_audio": {"decision": "REMOVE_ALL"}})
    assert bad and bad["reason_code"] == "H3_NATIVE_AUDIO_UNKNOWN"


def test_c_unknown_receipt_decision_is_refused():
    request = {"prompt_receipt": _receipt(
        native_audio={"decision": "mute", "provider_can_disable": False})}
    bad = MODULE.native_audio_refusal(H3, request)
    assert bad and bad["reason_code"] == "H3_NATIVE_AUDIO_UNKNOWN"


def test_d_a_recorded_decision_passes():
    for decision in ("retain", "reduce_music", "strip"):
        req = {"native_audio": {"decision": decision,
                                "provider_can_disable": False}}
        assert MODULE.native_audio_refusal(H3, req) is None, decision


def test_e_soundtrack_layering_fails_closed_without_a_decision():
    bad = MODULE.native_audio_refusal(H3, {"soundtrack_layering": True})
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"


def test_f_soundtrack_layering_over_retained_audio_is_double_music():
    req = {"native_audio": {"decision": "retain"},
           "soundtrack_layering": True}
    bad = MODULE.native_audio_refusal(H3, req)
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"


def test_g_soundtrack_layering_over_unmeasured_strip_is_unverified():
    req = {"native_audio": {"decision": "strip"},
           "soundtrack_layering": True}
    bad = MODULE.native_audio_refusal(H3, req)
    assert bad and bad["reason_code"] == "NATIVE_AUDIO_UNVERIFIED"


def test_h_soundtrack_layering_after_removal_passes():
    req = {"native_audio": {"decision": "strip",
                            "observed": {"has_audio": True,
                                         "removed": True}},
           "soundtrack_layering": True}
    assert MODULE.native_audio_refusal(H3, req) is None


def test_i_non_h3_models_are_untouched():
    assert MODULE.native_audio_refusal(
        "kling/2.5-turbo", {"native_audio": "mute",
                            "soundtrack_layering": True}) is None


def test_j_the_decision_is_read_from_the_receipt_for_THIS_prompt():
    import hashlib
    prompt = "the prompt being paid for"
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    other = _receipt(native_audio={"decision": "mute"})
    other["prompt_sha256"] = "1" * 64
    mine = _receipt(native_audio={"decision": "strip",
                                  "observed": {"has_audio": True,
                                               "removed": True}})
    mine["prompt_sha256"] = sha
    req = {"prompt_receipts": [other, mine], "soundtrack_layering": True}
    # the mismatched receipt says "mute"; the matching one says strip+removed
    assert MODULE.native_audio_refusal(H3, req, prompt) is None
    # without the prompt only the fallback is available, and "mute" refuses
    bad = MODULE.native_audio_refusal(H3, req)
    assert bad and bad["reason_code"] == "H3_NATIVE_AUDIO_UNKNOWN"


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok %s" % name)
    print("all native-audio dispatch gate tests passed")


if __name__ == "__main__":
    main()
