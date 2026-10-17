#!/usr/bin/env python3
"""DEFECT 5: judge_take's word consumers accept BOTH aligned-word shapes --
canonical {word,start,end} (lyric_timing.normalize_aligned_words) and raw
Suno {word,startS,endS} -- with identical timing. Run:
    python3 core/sung_hook/test_timing_word_shapes.py
"""
import os
import sys

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CORE)
from audio_c3.lyric_timing import normalize_aligned_words  # noqa: E402
from song_contract import song_contract as SC              # noqa: E402
from sung_hook import hook_placement as HP                 # noqa: E402
import sung_hook as SH                                     # noqa: E402

HOOK = "come home to beacon"
SEGS = [{"delivery": "sung", "start": 0.0, "end": 40.0, "source": "measured"}]
RAW = [{"word": ("[Hook]\n" if k == 0 else "") + w + " ",
        "startS": t + k * 0.5, "endS": t + k * 0.5 + 0.4}
       for t in (5.0, 15.0, 25.0) for k, w in enumerate(HOOK.split())]
CANON = normalize_aligned_words(RAW)
assert CANON[0] == {"word": "[Hook]\ncome ", "start": 5.0, "end": 5.4}, CANON[0]
assert not any("startS" in w for w in CANON)

for name, words in (("canonical", CANON), ("raw startS/endS", RAW)):
    r = SH.measure(HOOK, words, SEGS, 3)                     # KeyError('startS') before
    assert r["times_s"] == [5.0, 15.0, 25.0] and r["verdict"] == "PASS", (name, r)
    secs = HP.returned_sections(words)
    assert [s for _, s in secs] == [5.0, 15.0, 25.0], (name, secs)
    seq = [(SH.words(w["word"]) or [""])[-1] for w in words]
    assert SC._sung_hits(tuple(HOOK.split()), seq, words, SEGS) == 3, name
    assert SC._sung_hits(tuple(HOOK.split()), seq, words,
                         [dict(SEGS[0], delivery="spoken")]) == 0, name   # gate still bites
    print("PASS %s: hook times %s, sections %s" % (name, r["times_s"], [s for _, s in secs]))
