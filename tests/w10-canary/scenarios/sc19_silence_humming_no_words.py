#!/usr/bin/env python3
"""sc19_silence_humming_no_words.py — acceptance row SC-19 (S75-W10-U1).

Condition (SCENARIO-MATRIX.json, row SC-19, verbatim):
    "Silence / humming initials"

Required result (verbatim):
    "NEGATIVE: a silent or humming initial clip yields no invented words; the
     run records an explicit no-words/needs-input state instead of fabrication"

The word-timing step is the REAL ``audio_c3/lyric_timing.provide_word_timings``
of the tree under test, and the sung claim is the REAL
``singing_detector.take_verdict``. Only the provider/model are fixtures:
an in-process dispatcher that refuses instead of calling out, and a local
transcriber double that returns the zero-word result a silent/hummed clip
produces. No network, no paid provider, no channel, no graph mutation.

Modes:
  (no flag)   run the scenario and print one assertion line per check
  --dry-run   identical checks, receipt marked mode=dry-run
  selftest    re-run under deliberate defects and REQUIRE the named
              assertions to turn RED (proves the harness can fail)

Exit 0 = every assertion held; 1 = at least one failed; 2 = tooling.
"""
from __future__ import annotations

import argparse
import importlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as H  # noqa: E402

ROW = "sc19"
TITLE = "silent / humming initial clip invents no words"

RUN_ID = "runSC19"


def load_core(core):
    extra = [str(core), str(core / "audio_c3")]
    for p in extra:
        sys.path.insert(0, p)
    try:
        sd = H.load_pkg(core, "singing_detector")
        lt = importlib.import_module("lyric_timing")
    finally:
        for p in extra:
            try:
                sys.path.remove(p)
            except ValueError:
                pass
    return sd, lt


def silent_wav(path):
    """A real 44-byte PCM WAV header with zero samples (the fixture audio)."""
    header = (b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt "
              + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
              + b"data" + struct.pack("<I", 0))
    p = Path(path)
    p.write_bytes(header)
    return str(p)


class ZeroWordModel(object):
    """Transcriber double: a clip with no words returns no word rows."""

    def __init__(self, segments):
        self.segments = segments

    def transcribe(self, path, word_timestamps=True):
        return (list(self.segments), None)


def refusing_dispatcher(**kw):
    """Tier 1 must never leave the process; no provider, no network."""
    raise LYRIC_TIMING.LyricTimingError(
        "SUNO_TIMING_DISPATCH_FAILED", "fixture: provider calls are disabled")


def find_word_lists(obj, path="$"):
    """Every place a word list is attached to a result (fabrication probe)."""
    hits = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "words":
                hits.append("%s.%s=%r" % (path, key, value))
            else:
                hits.extend(find_word_lists(value, "%s.%s" % (path, key)))
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            hits.extend(find_word_lists(value, "%s[%d]" % (path, i)))
    return hits


def measure_take(lt, track, segments):
    sess = lt.WhisperSession(
        loader=lambda size, ctype: ZeroWordModel(segments),
        free_gb_probe=lambda: 64.0)
    return lt.provide_word_timings(track, dispatcher=refusing_dispatcher,
                                   whisper_session=sess, cloud=None)


def scenario(core, muts=frozenset()):
    global LYRIC_TIMING
    sd, lt = load_core(core)
    LYRIC_TIMING = lt
    c = H.Checks(ROW, TITLE)
    print("SC19 %s — tree %s%s"
          % (TITLE, core, (" [defect: %s]" % ",".join(sorted(muts)))
             if muts else ""))

    with H.Scratch() as tmp:
        tmp = Path(tmp)
        silent_path = silent_wav(tmp / "initial-silent.wav")
        hum_path = silent_wav(tmp / "initial-hum.wav")

        # ---- the silent initial clip ------------------------------------
        longest_silent = (sd.MIN_REAL_SINGING_STRETCH_S
                          if "claim_sung" in muts else 0.0)
        verdict_silent = sd.take_verdict(longest_silent)
        stretches_silent = sd.sung_stretches([])
        c.check("sc19:silent-take-not-claimed-sung",
                verdict_silent == sd.VERDICT_NO_SINGING
                and stretches_silent == [],
                "longest sung stretch=%.1fs -> verdict=%s, stretches=%s "
                "(real-singing floor %.1fs)"
                % (longest_silent, verdict_silent, stretches_silent,
                   sd.MIN_REAL_SINGING_STRETCH_S))

        silent_track = {"task_id": "t-silent", "audio_id": "a-silent",
                        "audio_path": silent_path}
        hint = None
        if "fabricate_hint" in muts:
            hint = {"words": [{"word": "hello", "start": 0.0, "end": 0.4}]}
        silent_out = lt.provide_word_timings(
            silent_track, timing_map_hint=hint,
            dispatcher=refusing_dispatcher,
            whisper_session=lt.WhisperSession(
                loader=lambda size, ctype: ZeroWordModel([]),
                free_gb_probe=lambda: 64.0),
            cloud=None)

        c.check("sc19:silent-take-yields-no-word-timestamps",
                silent_out.get("ok") is False and "timings" not in silent_out,
                "ok=%r timings_present=%s"
                % (silent_out.get("ok"), "timings" in silent_out))
        c.check("sc19:silent-take-records-explicit-no-words-state",
                silent_out.get("failure_class") == lt.CLASS_TIMESTAMPS_UNAVAILABLE
                and silent_out.get("error_code")
                == lt.CLASS_CODE[lt.CLASS_TIMESTAMPS_UNAVAILABLE]
                and bool(silent_out.get("next_action")),
                "error_code=%r failure_class=%r next_action=%s"
                % (silent_out.get("error_code"),
                   silent_out.get("failure_class"),
                   "present" if silent_out.get("next_action") else "absent"))

        # ---- the humming initial clip (a segment carrying no word rows) --
        hum_track = {"task_id": "t-hum", "audio_id": "a-hum",
                     "audio_path": hum_path}
        hum_out = measure_take(lt, hum_track, [{"words": []}])
        c.check("sc19:humming-take-yields-no-word-timestamps",
                hum_out.get("ok") is False and "timings" not in hum_out,
                "ok=%r timings_present=%s"
                % (hum_out.get("ok"), "timings" in hum_out))
        c.check("sc19:humming-take-records-explicit-no-words-state",
                hum_out.get("failure_class") == lt.CLASS_TIMESTAMPS_UNAVAILABLE
                and bool(hum_out.get("next_action")),
                "error_code=%r failure_class=%r"
                % (hum_out.get("error_code"), hum_out.get("failure_class")))

        fabricated = find_word_lists(silent_out) + find_word_lists(hum_out)
        c.check("sc19:no-word-list-is-fabricated",
                not fabricated,
                "word lists found=%d %s"
                % (len(fabricated), fabricated[:3] or "none"))

        hum_verdict = sd.take_verdict(1.0)
        c.check("sc19:hum-below-real-singing-floor-not-real-singing",
                hum_verdict == sd.VERDICT_NO_SINGING,
                "1.0s hum -> verdict=%s (floor %.1fs)"
                % (hum_verdict, sd.MIN_REAL_SINGING_STRETCH_S))
    return c


MUTATIONS = {
    "fabricate_hint": [
        "sc19:silent-take-yields-no-word-timestamps",
        "sc19:silent-take-records-explicit-no-words-state",
    ],
    "claim_sung": [
        "sc19:silent-take-not-claimed-sung",
    ],
}


def selftest(core):
    ok = True
    for name in sorted(MUTATIONS):
        c = scenario(core, frozenset([name]))
        failed = [r["name"] for r in c.failed()]
        expected = MUTATIONS[name]
        hit = [e for e in expected if e in failed]
        good = len(hit) == len(expected) and len(failed) >= 1
        ok = ok and good
        print("selftest:%s — %s; red=%s"
              % (name, "RED as required" if good
                 else "DID NOT FAIL AS EXPECTED", failed or "none"))
        print("selftest:%s — expected hit=%d/%d"
              % (name, len(hit), len(expected)))
    print("selftest — %s"
          % ("harness fails on every defect" if ok
             else "HARNESS CANNOT PROVE A FAILURE"))
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "selftest":
        args = H.add_args(description="sc19 selftest").parse_args(argv[1:])
        return selftest(H.resolve_core(args))

    ap = H.add_args(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    core = H.resolve_core(args)
    result = scenario(core)
    if args.out:
        path = Path(args.out) / "receipts"
        code = result.finish(path)
        receipt = path / "sc19.scenario.json"
        if receipt.is_file():
            doc = json.loads(receipt.read_text("utf-8"))
            doc["mode"] = "dry-run" if args.dry_run else "run"
            receipt.write_text(json.dumps(doc, indent=2) + "\n", "utf-8")
        return code
    return result.finish()


if __name__ == "__main__":
    sys.exit(main())
