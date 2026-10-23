#!/usr/bin/env python3
"""sc14_timing_fallback.py — acceptance row SC-14 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-14, verbatim):
    "Enabled timing fallback"

Required result (verbatim):
    "NEGATIVE: when the timing path is unavailable the enabled fallback is
     used and the receipt records fallback_used=true; the run never reports
     the primary timing path as successful"

Proves, against the REAL core module of the tree under test
(audio_c3.lyric_timing):

  * with tier 1 (Suno timestamped lyrics) unavailable, the ENABLED tier-2
    local fallback produces the timings, and the receipt says so: source
    ``faster-whisper-local``, evidence tier 2, the tier-1 error code named;
  * the receipt never reports the primary path as successful on a fallback
    run: source is not ``suno-timestamped-lyrics``, the tier is not 1, and no
    tier-1 hint is stamped;
  * the fallback measures real words with a confidence block, opens exactly
    ONE governed local model, and makes zero paid generation calls;
  * the control run (a complete tier-1 hint) reports tier 1 with zero local
    loads, so the fallback is not unconditional;
  * the LITERAL acceptance field ``fallback_used`` does not exist on the
    receipt at this vector. That assertion is printed RED and named, because
    the matrix asks for that exact field and the implementation records the
    equivalent facts under ``source`` + ``evidence.tier``. This row is
    therefore NOT a pass; see the final line.

Only the provider is a fixture: an in-process dispatcher that raises the
tier-1 failure, an in-process model object, and a scratch audio path. No
network, no paid provider, no live channel, no graph mutation, no subprocess.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  selftest    re-run under deliberate fixture defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc14"
TITLE = "enabled timing fallback (tier 2 used, primary never reported)"
T1_DOWN = "SUNO_TIMESTAMPS_UNAVAILABLE"
SUNO = "suno-timestamped-lyrics"
LOCAL = "faster-whisper-local"

# --------------------------------------------------------------------------
def load_core(core):
    # the module's import prints a load-governor line; keep it out of the
    # assertion stream so one line means one check
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        LT = H.load_pkg(core, "audio_c3.lyric_timing")
    return LT

class _Word(object):
    def __init__(self, word, start, end, probability):
        self.word, self.start, self.end = word, start, end
        self.probability = probability

class _Segment(object):
    def __init__(self, words):
        self.words = words

class _Model(object):
    def __init__(self, words):
        self._words = words

    def transcribe(self, path, word_timestamps=False):
        return iter([_Segment(self._words)]), object()

def make_loader(LT, empty=False):
    words = [] if empty else [_Word("hello", 1.0, 1.4, 0.9)]
    def loader(model_size, compute_type="int8"):
        return _Model(words)
    return loader

def tier1_down(*args, **kwargs):
    raise _T1Error

def tier1_up_factory(tmp):
    """A dispatcher whose saved KIE doc carries alignedWords (tier 1 works)."""
    doc = Path(tmp) / "kie-timed-lyrics.json"
    doc.write_text(json.dumps({"alignedWords": [
        {"word": "hello", "startS": 1.0, "endS": 1.4}]}), encoding="utf-8")
    def dispatch(**kwargs):
        return {"outcome": "ok", "reason_code": "OK",
                "evidence": {"saved_paths": [str(doc)]}}
    return dispatch

# --------------------------------------------------------------------------
def scenario(core, muts=frozenset()):
    LT = load_core(core)
    global _T1Error
    _T1Error = LT.LyricTimingError(T1_DOWN, "tier 1 unavailable (fixture)",
                                   LT.CLASS_TIMESTAMPS_UNAVAILABLE)
    c = H.Checks(ROW, TITLE)
    print("SC14 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        audio = tmp / "take.wav"
        audio.write_bytes(b"RIFF....WAVEfmt ")
        track = {"task_id": "t1", "audio_id": "a1", "audio_path": str(audio)}

        dispatcher = tier1_up_factory(tmp) if "tier1_available" in muts \
            else tier1_down
        # the module's own selftest seam: a fixed free-RAM probe, so the row
        # tests the TIER FALLBACK and not this box's current RAM pressure
        session = LT.WhisperSession(loader=make_loader(LT, empty=("no_words" in muts)),
                                    free_gb_probe=lambda: 16.0)
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            env = LT.provide_word_timings(track, dispatcher=dispatcher,
                                          whisper_session=session)
        timings = env.get("timings") or {}
        evidence = timings.get("evidence") or {}
        counts = evidence.get("counts") or {}
        words = timings.get("words") or []

        if "two_loads" in muts:
            timings["local_model_loads"] = 2
            evidence["loads"] = 2
        if "label_primary" in muts:
            timings["source"] = SUNO

        c.check("sc14:primary-path-unavailable-named",
                env.get("ok") is True
                and evidence.get("tier1_error") == T1_DOWN,
                "ok=%s tier1_error=%s error_code=%s"
                % (env.get("ok"), evidence.get("tier1_error"),
                   env.get("error_code")))
        c.check("sc14:fallback-tier-used",
                timings.get("source") == LOCAL and evidence.get("tier") == 2,
                "source=%s tier=%s"
                % (timings.get("source"), evidence.get("tier")))
        c.check("sc14:primary-path-never-reported-successful",
                timings.get("source") != SUNO
                and evidence.get("tier") != 1
                and evidence.get("hint") is not True,
                "source=%s tier=%s hint=%s"
                % (timings.get("source"), evidence.get("tier"),
                   evidence.get("hint")))
        c.check("sc14:fallback-measured-words-with-confidence",
                len(words) == 1 and words[0].get("word") == "hello"
                and float(words[0].get("start")) == 1.0
                and float(words[0].get("end")) == 1.4
                and isinstance(evidence.get("confidence"), dict),
                "words=%s confidence=%s"
                % (words, evidence.get("confidence")))
        c.check("sc14:one-governed-local-model-load",
                timings.get("local_model_loads") == 1
                and evidence.get("loads") == 1,
                "local_model_loads=%s evidence.loads=%s"
                % (timings.get("local_model_loads"), evidence.get("loads")))
        c.check("sc14:zero-paid-generation-on-fallback",
                counts.get("music_generation_calls") == 0
                and counts.get("paid_analysis_calls") == 0,
                "counts=%s" % (counts,))

        # ---- control: a complete tier-1 hint is used, zero local loads ----
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            hint_env = LT.provide_word_timings(
                track, timing_map_hint={"words": [{"word": "hello",
                                                  "start": 1.0, "end": 1.4}]})
        hint = hint_env.get("timings") or {}
        c.check("sc14:primary-path-used-and-labelled-when-available",
                hint_env.get("ok") is True and hint.get("source") == SUNO
                and (hint.get("evidence") or {}).get("tier") == 1
                and hint.get("local_model_loads") == 0,
                "source=%s tier=%s loads=%s"
                % (hint.get("source"),
                   (hint.get("evidence") or {}).get("tier"),
                   hint.get("local_model_loads")))

        # ---- the literal acceptance field -------------------------------
        literal = timings.get("fallback_used", evidence.get("fallback_used"))
        c.check("sc14:receipt-records-fallback-used",
                literal is True,
                "fallback_used field absent: receipt records source=%r "
                "evidence.tier=%r instead; the matrix asks for the literal "
                "boolean" % (timings.get("source"), evidence.get("tier")))
    return c

# --------------------------------------------------------------------------
# selftest — deliberate fixture defects must turn the named assertions RED.
# sc14:receipt-records-fallback-used is the known GAP assertion: it is RED in
# every run by design, so it is excluded from the mutation expectations.
# --------------------------------------------------------------------------
GAP = "sc14:receipt-records-fallback-used"
MUTATIONS = {
    "tier1_available": [
        "sc14:primary-path-unavailable-named",
        "sc14:fallback-tier-used",
        "sc14:primary-path-never-reported-successful",
        "sc14:fallback-measured-words-with-confidence",
    ],
    "no_words": [
        "sc14:fallback-tier-used",
        "sc14:fallback-measured-words-with-confidence",
        "sc14:one-governed-local-model-load",
    ],
    "two_loads": [
        "sc14:one-governed-local-model-load",
    ],
    "label_primary": [
        "sc14:fallback-tier-used",
        "sc14:primary-path-never-reported-successful",
    ],
}

def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed() if r["name"] != GAP]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and bool(failed)
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good else "DID NOT FAIL AS EXPECTED",
                 failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s (known gap assertion %s stays red in every run)"
          % ("harness fails on all four defects" if ok
             else "HARNESS CANNOT PROVE A FAILURE", GAP))
    return 0 if ok else 1

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc14 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))
    args = H.add_args(description=__doc__).parse_args(argv)
    c = scenario(H.resolve_core(args))
    code = c.finish(args.out)
    if code and [r for r in c.failed() if r["name"] == GAP]:
        print("sc14: GAP — the literal fallback_used field is absent at this "
              "vector; the row is not a pass")
    return code

if __name__ == "__main__":
    sys.exit(main())
