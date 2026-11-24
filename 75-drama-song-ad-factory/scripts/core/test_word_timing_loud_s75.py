"""S75 word-timing guards (findings D7, A1).

1. PREREQS pre-fetches the EXACT model the code loads -- 'small', never the
   English-only variant -- as the run user, with cache ownership.
2. A take with no word timings RAISES a loud WORD_TIMING_UNAVAILABLE warning,
   so a run cannot look clean while the opening vocal line is unmeasurable.
"""
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import loud_failure  # noqa: E402
import song_transports  # noqa: E402


def test_prereqs_prefetch_the_small_model():
    with open(os.path.join(SKILL, "PREREQS.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    entry = [e for e in doc["prerequisites"]
             if e["id"] == "faster-whisper-optional"]
    assert len(entry) == 1, "expected exactly one faster-whisper-optional entry"
    satisfy = entry[0]["satisfy"]
    assert "WhisperModel('small'" in satisfy, "pre-fetch must name 'small'"
    assert "small.en" not in satisfy, "the English-only variant is not the model"
    assert "run user" in satisfy, "pre-fetch must run as the run user"
    assert "huggingface" in satisfy.lower(), "cache ownership must be stated"


def test_missing_word_timing_warns_loudly():
    loud_failure.reset()
    try:
        import numpy as np

        stub = types.ModuleType("singing_detector")
        stub.detect_track = lambda path: {"sung_seconds_indexes": [],
                                          "runtime_s": 1}
        sys.modules["singing_detector"] = stub
        orig = song_transports._decode_mono
        song_transports._decode_mono = \
            lambda path, sr=16000: np.zeros(16000, dtype="float32")
        try:
            measure = song_transports.make_measure(
                timings=lambda t: {"error": "WHISPER_MODEL_LOAD_FAILED"})
            measure({"audio_path": "x.mp3"})
        finally:
            song_transports._decode_mono = orig
    finally:
        sys.modules.pop("singing_detector", None)
    codes = [e["code"] for e in loud_failure.entries()]
    assert "WORD_TIMING_UNAVAILABLE" in codes, \
        "empty word timing must leave a loud entry, got %r" % (codes,)


if __name__ == "__main__":
    test_prereqs_prefetch_the_small_model()
    test_missing_word_timing_warns_loudly()
    print("test_word_timing_loud_s75: 2 passed")
