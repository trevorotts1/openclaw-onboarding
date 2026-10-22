#!/usr/bin/env python3
"""H3 native audio at the final assembly: no song over a live generated track.

The assembler maps ONLY the song's audio (clip audio is dropped), so a
timeline that carries a take's native_audio evidence is audited before the
render: retain refuses DOUBLE_MUSIC, an unmeasured strip/reduce take is quiet
because this render provably drops the clip channel, and a take whose
evidence says the audio was NOT removed refuses. Timelines with no
native_audio key assemble exactly as before.

Stdlib only, offline, no spend.
Run: python3 scripts/core/final_assembler/test_native_audio_h3.py
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

A = importlib.import_module("final_assembler.assembler")


def _tl(*segments):
    return {"segments": [dict(src="clip-%d.mp4" % i, dur=2.0, **seg)
                         for i, seg in enumerate(segments)]}


def test_legacy_timeline_without_the_key_is_untouched():
    assert A._native_audio_layering(_tl({}, {})) is None


def test_retained_generated_audio_refuses():
    bad = A._native_audio_layering(
        _tl({"native_audio": {"decision": "retain"}}))
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"
    assert bad["segment"] == "clip-0.mp4"


def test_unremoved_generated_audio_refuses():
    bad = A._native_audio_layering(_tl({"native_audio": {
        "decision": "strip",
        "observed": {"has_audio": True, "removed": False}}}))
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"


def test_strip_and_reduce_are_quiet_once_removed():
    for decision in ("strip", "reduce_music"):
        tl = _tl({"native_audio": {"decision": decision,
                                   "observed": {"has_audio": True,
                                                "removed": True}}})
        assert A._native_audio_layering(tl) is None, decision


def test_unmeasured_take_is_quiet_because_this_render_drops_clip_audio():
    # the assembler maps only [aout] (the song); clip audio is never mapped,
    # so an unmeasured take cannot double up here.
    assert A._native_audio_layering(
        _tl({"native_audio": {"decision": "strip"}})) is None


def test_missing_decision_fails_closed():
    bad = A._native_audio_layering(_tl({"native_audio": {}}))
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"


def test_one_bad_segment_among_good_ones_refuses():
    tl = _tl({"native_audio": {"decision": "strip",
                               "observed": {"has_audio": True,
                                            "removed": True}}},
             {"native_audio": {"decision": "retain"}})
    bad = A._native_audio_layering(tl)
    assert bad and bad["reason_code"] == "DOUBLE_MUSIC"
    assert bad["segment"] == "clip-1.mp4"


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok %s" % name)
    print("all native-audio assembler tests passed")


if __name__ == "__main__":
    main()
