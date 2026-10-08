#!/usr/bin/env python3
"""Pitch-shift ban tests (owner D22a / Decision 36, plan 6.12 item 3).

Deterministic, mocked, zero spend: synthetic tones (inline samples only --
no media file is ever written), unittest.mock for the pitch estimator, no
network module, no provider call, no money. Dual-mode -- runs under plain
python3 (assert-based, non-zero exit on failure) and under pytest.

Run:  python3 core/qc_voice_match/pitch_ban/test_pitch_ban.py
  or: python3 -m pytest core/qc_voice_match/pitch_ban/
Env:  PITCH_BAN_FIXTURE_DIR keeps the JSON scratch files somewhere durable
      (default /tmp/AF-ECHO-U3-fixtures).
"""
from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # core/

import qc_voice_match as V                       # noqa: E402  parent package
import qc_voice_match.qc_voice_match as PV       # noqa: E402  parent impl
import qc_gate as G                              # noqa: E402  sibling checker
from qc_voice_match import pitch_ban as M        # noqa: E402  unit under test

RATE = 8000
SECONDS = 0.5
CLI = os.path.join(HERE, "pitch_ban.py")
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % str(detail)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ------------------------------------------------------------- fixtures ----

def synth(f0, harmonics=(1.0, 0.5, 0.3), seconds=SECONDS, rate=RATE):
    """Deterministic int16 tone. No randomness anywhere, no file written."""
    n = int(rate * seconds)
    out = []
    for i in range(n):
        t = i / rate
        v = 0.0
        for k, amp in enumerate(harmonics, start=1):
            v += amp * math.sin(2.0 * math.pi * f0 * k * t)
        v /= max(len(harmonics), 1)
        out.append(int(max(-1.0, min(1.0, v)) * 32000))
    return out


def fixture_dir():
    d = os.environ.get("PITCH_BAN_FIXTURE_DIR") or os.path.join(
        tempfile.gettempdir(),
        "%s-AF-ECHO-U3-fixtures" % socket.gethostname())
    os.makedirs(d, exist_ok=True)
    return d


def line(line_id, speaker, gender, onscreen, intended=None, samples=None,
         sample_rate=None, wav=None, **extra):
    rec = {"line_id": line_id, "speaker": speaker, "gender": gender,
           "onscreen": onscreen}
    if intended is not None:
        rec["intended_hz"] = intended
    if wav:
        rec["wav_path"] = wav
    if samples is not None:
        rec["samples"] = samples
        rec["sample_rate"] = sample_rate if sample_rate is not None else RATE
    rec.update(extra)
    return rec


def report(lines, characters=None, registry=None, run_id="run-pb-1",
           stage="audio", schema_version=None):
    r = {"schema_version": schema_version or PV.SCHEMA_VERSION,
         "run_id": run_id, "stage": stage, "lines": lines}
    if characters is not None:
        r["characters"] = characters
    if registry is not None:
        r["registry"] = registry
    return r


def codes(result):
    return sorted({f["code"] for f in result["evidence"]["failures"]})


def hz_for(cents, reference=100.0):
    return reference * (2.0 ** (cents / 1200.0))


# ------------------------------------------- rule 2/3: the verdict table ----

def test_shift_verdict_table():
    cases = [
        (0.0, ""),
        (40.0, ""),                      # inside the drift window
        (-49.0, ""),
        (60.0, "PITCH_MISMATCH"),        # drift, not a clean transposition
        (100.0, "PITCH_MISMATCH"),       # one semitone: ambiguous, rejected
        (200.0, "PITCH_SHIFTED_MISMATCH"),
        (-300.0, "PITCH_SHIFTED_MISMATCH"),
        (300.0, "PITCH_SHIFTED_MISMATCH"),   # the D22a "+3 semitones" line
        (1300.0, "PITCH_SHIFTED_MISMATCH"),
        (1200.0, "OCTAVE_MISMATCH"),
        (-1200.0, "OCTAVE_MISMATCH"),
        (2400.0, "OCTAVE_MISMATCH"),
    ]
    for cents, want in cases:
        v = M.shift_verdict(100.0, hz_for(cents))
        check("verdict %+.0f cents -> %r" % (cents, want or "match"),
              v["code"] == want and v["ok"] == (want == ""),
              "%s / %s" % (v["code"], v["detail"]))
    v = M.shift_verdict(None, 100.0)
    check("missing reference undeterminable",
          v["ok"] is False and v["code"] == "PITCH_UNDETERMINABLE", v)
    check("cents_between is signed", M.cents_between(100.0, 200.0) == 1200.0,
          M.cents_between(100.0, 200.0))


def test_transposed_match_rejected_never_accepted():
    # D22a incident: a +3 semitone take that still sits in the male band.
    l = line("L1", "friend", "male", "friend", intended=100.0,
             samples=synth(100.0), sample_rate=RATE)
    transposed = hz_for(300.0, 100.0)                    # 118.92 Hz
    import unittest.mock as mock
    with mock.patch.object(PV, "measure_pitch_hz", return_value=transposed):
        r = M.evaluate(report([l]))
    check("transposed take rejected", r["outcome"] == "rejected", codes(r))
    check("transposed take named PITCH_SHIFTED_MISMATCH",
          "PITCH_SHIFTED_MISMATCH" in codes(r), codes(r))
    check("transposed take never reported as a match",
          "PITCH_BAN_OK" not in r["reason_code"], r["reason_code"])
    f = M.check_match(100.0, transposed, line_id="L1")
    check("primitive refuses the transposition",
          f is not None and f["code"] == "PITCH_SHIFTED_MISMATCH", f)
    # The shift rule also fires when the parent band check would pass it.
    check("parent band would have let it through",
          "PITCH_RANGE" not in codes(r), codes(r))
    for shift in (200.0, -300.0, 600.0, 1000.0):
        g = M.check_match(100.0, hz_for(shift, 100.0))
        check("%+.0f cents transposition rejected" % shift,
              g is not None and g["code"] == "PITCH_SHIFTED_MISMATCH", g)


def test_octave_displacement_is_mismatch_never_match():
    check("octave up is a mismatch",
          M.check_match(100.0, 200.0)["code"] == "OCTAVE_MISMATCH")
    check("octave down is a mismatch",
          M.check_match(200.0, 100.0)["code"] == "OCTAVE_MISMATCH")
    import unittest.mock as mock
    l = line("L1", "Chanel", "female", "Chanel", intended=200.0,
             samples=synth(200.0), sample_rate=RATE)
    with mock.patch.object(PV, "measure_pitch_hz", return_value=400.0):
        r = M.evaluate(report([l]))
    check("evaluate rejects the octave take",
          r["outcome"] == "rejected" and "OCTAVE_MISMATCH" in codes(r),
          codes(r))
    with mock.patch.object(PV, "measure_pitch_hz", return_value=100.0):
        r2 = M.evaluate(report([l]))
    check("octave-down take rejected too",
          r2["outcome"] == "rejected" and "OCTAVE_MISMATCH" in codes(r2),
          codes(r2))


def test_octave_down_inside_claimed_band_still_rejected():
    # Female design pitch 170 Hz taken an octave down = 85 Hz. The line
    # claims male, so the D17 band check passes it -- the octave guard is
    # what rejects it (D17 + D22a: octave displacement is a mismatch).
    import unittest.mock as mock
    l = line("L1", "Chanel", "male", "Chanel", samples=synth(85.0),
             sample_rate=RATE)
    chars = [{"id": "Chanel", "gender": "female", "pitch_center": 170.0}]
    with mock.patch.object(PV, "measure_pitch_hz", return_value=85.0):
        r = M.evaluate(report([l], characters=chars))
    check("in-band octave take rejected",
          r["outcome"] == "rejected" and "OCTAVE_MISMATCH" in codes(r),
          codes(r))
    check("band check alone did NOT catch it",
          "PITCH_RANGE" not in codes(r), codes(r))


def test_matching_take_passes_and_drift_tolerance():
    import unittest.mock as mock
    l = line("L1", "Chanel", "female", "Chanel", intended=200.0,
             samples=synth(200.0), sample_rate=RATE)
    with mock.patch.object(PV, "measure_pitch_hz", return_value=200.6):
        r = M.evaluate(report([l]))
    check("in-tolerance take passes", r["outcome"] == "ok", codes(r))
    check("ok run reason is PITCH_BAN_OK", r["reason_code"] == "PITCH_BAN_OK",
          r["reason_code"])
    with mock.patch.object(PV, "measure_pitch_hz", return_value=208.0):
        r2 = M.evaluate(report([l]))
    check("66 cent drift rejected as PITCH_MISMATCH",
          r2["outcome"] == "rejected" and "PITCH_MISMATCH" in codes(r2),
          codes(r2))
    check("drift boundary 49 cents accepted",
          M.check_match(100.0, hz_for(49.0)) is None)
    check("drift boundary 51 cents rejected",
          M.check_match(100.0, hz_for(51.0))["code"] == "PITCH_MISMATCH")


# ------------------------------------------------ rule 1: declared shifts ---

def test_declared_shift_refused_everywhere():
    clean = [{"pitch_shift_semitones": 0.0}, {"pitch_shift_semitones": 0},
             {"pitch_shift_semitones": None}, {}, {"semitone_offset": 0},
             {"pitch_shift_semitones": "0.0"}]
    for rec in clean:
        check("provably-zero %r accepted" % rec,
              M.refuse_pitch_shift(rec) == [], M.refuse_pitch_shift(rec))
    dirty = [
        ({"pitch_shift_semitones": 2.5}, "pitch_shift_semitones"),
        ({"pitch_shift_semitones": -1}, "pitch_shift_semitones"),
        ({"transpose_semitones": 12}, "transpose_semitones"),
        ({"semitones": "3"}, "semitones"),
        ({"semitones": "up a bit"}, "semitones"),
        ({"pitch_shift_semitones": True}, "pitch_shift_semitones"),
        ({"voices": {"hr": {"pitch_shift_semitones": 2.5}}}, "voices.hr"),
    ]
    for rec, needle in dirty:
        errs = M.refuse_pitch_shift(rec, "registry")
        check("non-zero %r refused" % (rec,),
              len(errs) == 1 and errs[0]["code"] == "PITCH_SHIFT_REFUSED"
              and needle in errs[0]["detail"]
              and "D22a" in errs[0]["detail"], errs)
    l = line("L1", "Chanel", "female", "Chanel", intended=200.0,
             samples=synth(200.0), sample_rate=RATE,
             pitch_shift_semitones=2.5)
    r = M.evaluate(report([l]))
    check("line record shift refused by evaluate",
          "PITCH_SHIFT_REFUSED" in codes(r), codes(r))
    failures, _ = M.check_line(l, {})
    check("line record shift refused by check_line",
          any(f["code"] == "PITCH_SHIFT_REFUSED" for f in failures), failures)
    check("non-record input fail-closed",
          M.refuse_pitch_shift("pitch_shift_semitones=2")[0]["code"]
          == "PITCH_SHIFT_REFUSED")


def test_registry_records_never_pitch_shift():
    voices = {
        "chanel": {"character_id": "chanel", "voice_id": "v1",
                   "gender": "female", "pitch_center": 190.0},
        "hr": {"character_id": "hr", "voice_id": "v2", "gender": "male",
               "pitch_center": 110.0},
    }
    reg = {"voices": voices}
    check("clean registry proves shift-free",
          M.registry_records_never_pitch_shift(reg) == [],
          M.registry_records_never_pitch_shift(reg))
    voices["hr"]["pitch_shift_semitones"] = 2.5
    errs = M.registry_records_never_pitch_shift(reg)
    check("shifted registry entry named by path",
          len(errs) == 1 and errs[0]["code"] == "PITCH_SHIFT_REFUSED"
          and "voices.hr" in errs[0]["detail"], errs)
    check("malformed registry fail-closed",
          M.registry_records_never_pitch_shift("nope")[0]["code"]
          == "REGISTRY_INVALID")
    r = M.evaluate(report(
        [line("L1", "Chanel", "female", "Chanel", intended=190.0,
              samples=synth(190.0), sample_rate=RATE)],
        registry=reg))
    check("evaluate refuses a shifted registry",
          "PITCH_SHIFT_REFUSED" in codes(r), codes(r))


# ------------------------------------------------- D17 delegation + close --

def test_intended_from_character_registry():
    import unittest.mock as mock
    l = line("L1", "Chanel", "female", "Chanel",
             samples=synth(200.0), sample_rate=RATE)
    chars = [{"id": "Chanel", "gender": "female", "pitch_center": 200.0}]
    with mock.patch.object(PV, "measure_pitch_hz", return_value=200.0):
        r = M.evaluate(report([l], characters=chars))
    check("registry pitch_center used as intended",
          r["outcome"] == "ok", codes(r))
    hz, status, source = M.intended_pitch(l, M.char_index(report(
        [l], characters=chars)))
    check("intended resolved from registry key",
          status == "ok" and hz == 200.0 and "pitch_center" in str(source),
          (hz, status, source))


def test_missing_intended_fails_closed():
    l = line("L1", "Chanel", "female", "Chanel",
             samples=synth(200.0), sample_rate=RATE)
    r = M.evaluate(report([l]))
    check("no intended pitch -> INTENDED_PITCH_UNKNOWN",
          "INTENDED_PITCH_UNKNOWN" in codes(r), codes(r))
    check("UNAVAILABLE never becomes PASS", r["outcome"] == "rejected",
          r["outcome"])
    try:
        M.refuse_before_assembly(r)
        check("assembly refused", False)
    except M.AssemblyBlocked as e:
        check("assembly refused", str(e) == r["reason_code"], str(e))
    l2 = dict(l)
    l2["intended_hz"] = "loud"
    check("invalid intended fail-closed",
          M.intended_pitch(l2)[1] == "invalid", M.intended_pitch(l2))


def test_parent_range_speaker_distinctness_still_enforced():
    import unittest.mock as mock
    with mock.patch.object(PV, "measure_pitch_hz", return_value=200.0):
        r = M.evaluate(report([line("L1", "HR_rep", "male", "HR_rep",
                                    intended=110.0, samples=synth(110.0),
                                    sample_rate=RATE)]))
    check("parent band check still fires",
          "PITCH_RANGE" in codes(r) and r["outcome"] == "rejected", codes(r))
    with mock.patch.object(PV, "measure_pitch_hz", return_value=110.0):
        r2 = M.evaluate(report([line("L1", "HR_rep", "male", "Chanel",
                                     intended=110.0, samples=synth(110.0),
                                     sample_rate=RATE)]))
    check("parent speaker rule still fires",
          "SPEAKER_MISMATCH" in codes(r2), codes(r2))
    with mock.patch.object(PV, "measure_pitch_hz", return_value=120.0):
        r3 = M.evaluate(report(
            [line("L1", "a", "male", "a", intended=120.0,
                  samples=synth(120.0), sample_rate=RATE)],
            characters=[{"id": "a", "gender": "male", "pitch_hz": 120.0},
                        {"id": "b", "gender": "male", "pitch_hz": 124.0}]))
    check("parent same-gender distinctness still fires",
          "SAME_GENDER_NOT_DISTINCT" in codes(r3), codes(r3))


def test_missing_audio_and_silence_fail_closed():
    r = M.evaluate(report([line("L1", "Chanel", "female", "Chanel",
                                intended=200.0,
                                wav="/definitely/not/here.wav")]))
    check("missing audio fail-closed",
          "AUDIO_MISSING" in codes(r) and r["outcome"] == "rejected",
          codes(r))
    r2 = M.evaluate(report([line("L1", "Chanel", "female", "Chanel",
                                 intended=200.0, samples=[0] * (RATE // 2),
                                 sample_rate=RATE)]))
    check("silence fail-closed",
          "PITCH_UNAVAILABLE" in codes(r2), codes(r2))


def test_report_schema_gate():
    for bad in (None, [], "x"):
        try:
            M.evaluate(bad)
            check("structural %r rejected" % (bad,), False)
        except M.VoiceMatchError as e:
            check("structural %r rejected" % (bad,), e.code == "BAD_INPUT",
                  e.code)
    try:
        M.evaluate(report([line("L", "s", "male", "s")],
                          schema_version="blackceo.nope/v1"))
        check("foreign schema rejected", False)
    except M.VoiceMatchError as e:
        check("foreign schema rejected", e.code == "BAD_INPUT", e.code)
    try:
        M.evaluate({"schema_version": PV.SCHEMA_VERSION, "stage": "audio",
                    "lines": [line("L", "s", "male", "s")]})
        check("missing run_id rejected", False)
    except M.VoiceMatchError as e:
        check("missing run_id rejected", e.code == "BAD_INPUT", e.code)


def test_mocked_estimator_wiring():
    import unittest.mock as mock
    l = line("L1", "Chanel", "female", "Chanel", intended=200.0,
             samples=synth(200.0), sample_rate=RATE)
    with mock.patch.object(PV, "measure_pitch_hz", return_value=None):
        r = M.evaluate(report([l]))
    check("estimator None -> fail-closed",
          r["outcome"] == "rejected" and "PITCH_UNAVAILABLE" in codes(r),
          codes(r))
    with mock.patch.object(PV, "measure_pitch_hz", return_value=200.0):
        r2 = M.evaluate(report([l]))
    check("estimator 200 -> pass", r2["outcome"] == "ok", codes(r2))
    with mock.patch.object(PV, "measure_pitch_hz", return_value=189.4):
        r3 = M.evaluate(report([l]))
    check("estimator one semitone down -> rejected",
          r3["outcome"] == "rejected", codes(r3))
    # Inline samples, no file: the real estimator measures the synth tone.
    real = M.evaluate(report([line("L2", "HR_rep", "male", "HR_rep",
                                   intended=110.0, samples=synth(110.0),
                                   sample_rate=RATE)]))
    check("real estimator on synth 110 Hz passes",
          real["outcome"] == "ok",
          "%s %s" % (codes(real), real["evidence"]["measured_hz"]))


def test_qc_gate_integration_and_refusal():
    ok = M.evaluate(report([line("L1", "Chanel", "female", "Chanel",
                                 intended=200.0, samples=synth(200.0),
                                 sample_rate=RATE)]))
    bad = M.evaluate(report([line("L1", "Chanel", "female", "Chanel",
                                  intended=400.0, samples=synth(200.0),
                                  sample_rate=RATE)]))
    reviewer = {"identity": "pitch_ban/1.0.0", "session": "t1",
                "authority": "owner-decision-D22a"}
    rec_ok = M.to_qc_record(ok, reviewer)
    rec_bad = M.to_qc_record(bad, reviewer)
    check("pass record validates in qc_gate",
          G.validate_record(rec_ok) is None, G.validate_record(rec_ok))
    check("fail record validates in qc_gate",
          G.validate_record(rec_bad) is None, G.validate_record(rec_bad))
    check("check_id is pitch-ban", rec_ok["check_id"] == "pitch-ban",
          rec_ok["check_id"])
    makers = {"pitch-ban": "suno_generator"}
    g_ok = G.evaluate("run-pb-1", "audio", [rec_ok], makers, ["audio"])
    g_bad = G.evaluate("run-pb-1", "audio", [rec_bad], makers, ["audio"])
    check("qc_gate PASS when the voice matches",
          g_ok["gate"] == "PASS", g_ok)
    check("qc_gate FAIL when the take is displaced",
          g_bad["gate"] == "FAIL", g_bad)


def test_cli_ok_rejected_and_error():
    measured = PV.measure_pitch_hz(synth(110.0), RATE)
    ok_rep = report([line("L1", "HR_rep", "male", "HR_rep",
                          intended=measured, samples=synth(110.0),
                          sample_rate=RATE)])
    bad_rep = report([line("L1", "HR_rep", "male", "HR_rep",
                           intended=measured * 2.0, samples=synth(110.0),
                           sample_rate=RATE)])
    d = fixture_dir()
    ok_path = os.path.join(d, "report-ok.json")
    bad_path = os.path.join(d, "report-octave.json")
    rec_path = os.path.join(d, "record.json")
    for path, body in ((ok_path, ok_rep), (bad_path, bad_rep)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(body, f)
    p1 = subprocess.run([sys.executable, CLI, "check", "--report", ok_path],
                        capture_output=True, text=True)
    check("cli exit 0 on a matching take", p1.returncode == 0,
          (p1.returncode, p1.stdout[:300], p1.stderr[:300]))
    check("cli emits PITCH_BAN_OK", "PITCH_BAN_OK" in p1.stdout, p1.stdout[:200])
    p2 = subprocess.run(
        [sys.executable, CLI, "check", "--report", bad_path,
         "--qc-record", rec_path], capture_output=True, text=True)
    check("cli exit 5 on an octave-displaced take", p2.returncode == 5,
          (p2.returncode, p2.stdout[:300]))
    check("cli names the mismatch", "OCTAVE_MISMATCH" in p2.stdout,
          p2.stdout[:400])
    if os.path.exists(rec_path):
        with open(rec_path, encoding="utf-8") as f:
            rec = json.load(f)
        check("qc-record file written and valid",
              G.validate_record(rec) is None and rec["verdict"] == "FAIL",
              G.validate_record(rec))
    else:
        check("qc-record file written and valid", False, "missing")
    p3 = subprocess.run([sys.executable, CLI, "check",
                         "--report", "/definitely/not/here.json"],
                        capture_output=True, text=True)
    check("cli exit 1 on unreadable report", p3.returncode == 1,
          p3.returncode)


def test_determinism_zero_spend_and_no_media():
    import unittest.mock as mock
    l = line("L1", "Chanel", "female", "Chanel", intended=200.0,
             samples=synth(200.0), sample_rate=RATE)
    rep = report([l])
    with mock.patch.object(PV, "measure_pitch_hz", return_value=400.0):
        a = json.dumps(M.evaluate(rep), sort_keys=True)
        b = json.dumps(M.evaluate(rep), sort_keys=True)
    check("evaluate deterministic", a == b)
    s1 = M.shift_verdict(100.0, 118.92)
    s2 = M.shift_verdict(100.0, 118.92)
    check("verdict deterministic", s1 == s2, (s1, s2))
    low = open(os.path.join(HERE, "pitch_ban.py"), encoding="utf-8").read()
    low = low.lower()
    # Zero spend: no network client, no subprocess, no paid-dispatch hook.
    for needle in ("urllib", "requests", "http.client", "subprocess",
                   "socket", "/users/", "/home/", "spend_ledger", "kie",
                   "openai", "pm2"):
        check("module source has no %r" % needle, needle not in low, needle)
    # No media file may exist in the owned directory.
    media = [f for f in os.listdir(HERE)
             if f.lower().endswith((".wav", ".mp3", ".mp4", ".png", ".jpg",
                                    ".jpeg", ".mov", ".srt"))]
    check("owned dir holds no media file", media == [], media)


def test_never_applies_a_shift():
    low = open(os.path.join(HERE, "pitch_ban.py"), encoding="utf-8").read()
    low = low.lower()
    # No code path may pitch-shift a voice: this unit only ever refuses.
    for needle in ("asetrate", "rubberband", "def pitch_shift", "resample(",
                   "wsola", "time_stretch", "atempo"):
        check("module never applies %r" % needle, needle not in low, needle)
    check("every entry point refuses a declared shift",
          M.refuse_pitch_shift({"pitch_shift_semitones": 1}) != []
          and M.registry_records_never_pitch_shift(
              {"voices": {"x": {"pitch_shift_semitones": 1.0}}}) != []
          and any(f["code"] == "PITCH_SHIFT_REFUSED"
                  for f in M.check_line(
                      line("L", "s", "male", "s", pitch_shift_semitones=1),
                      {})[0]))
    check("shift_verdict never returns a match for a displacement",
          all(M.shift_verdict(100.0, hz_for(c))["ok"] is False
              for c in (200.0, 300.0, 1200.0, -1200.0)))


def test_constants_match_owner_D17():
    check("D17 ranges are the parent's object (one source of truth)",
          M.PITCH_RANGES_HZ is V.PITCH_RANGES_HZ)
    check("male band", M.PITCH_RANGES_HZ["male"] == (85.0, 155.0))
    check("female band", M.PITCH_RANGES_HZ["female"] == (165.0, 255.0))
    check("same-gender separation is 15 Hz",
          M.SAME_GENDER_MIN_SEPARATION_HZ == 15.0
          == V.SAME_GENDER_MIN_SEPARATION_HZ)
    check("drift tolerance is half a semitone",
          M.DRIFT_TOLERANCE_CENTS == 50.0, M.DRIFT_TOLERANCE_CENTS)
    check("min shift is 2 semitones", M.MIN_SHIFT_SEMITONES == 2)


TESTS = [
    test_shift_verdict_table,
    test_transposed_match_rejected_never_accepted,
    test_octave_displacement_is_mismatch_never_match,
    test_octave_down_inside_claimed_band_still_rejected,
    test_matching_take_passes_and_drift_tolerance,
    test_declared_shift_refused_everywhere,
    test_registry_records_never_pitch_shift,
    test_intended_from_character_registry,
    test_missing_intended_fails_closed,
    test_parent_range_speaker_distinctness_still_enforced,
    test_missing_audio_and_silence_fail_closed,
    test_report_schema_gate,
    test_mocked_estimator_wiring,
    test_qc_gate_integration_and_refusal,
    test_cli_ok_rejected_and_error,
    test_determinism_zero_spend_and_no_media,
    test_never_applies_a_shift,
    test_constants_match_owner_D17,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s"
                  % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d tests passed (mocked + synth fixtures, zero spend)"
          % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
