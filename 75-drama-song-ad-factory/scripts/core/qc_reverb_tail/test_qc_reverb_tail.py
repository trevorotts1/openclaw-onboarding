#!/usr/bin/env python3
"""Mocked tests for D22a reverb-tail QC. Zero paid calls, zero media in repo.

Fixtures are synthesized here: a deterministic exponential impulse response
convolved with a generated tone, then rendered to a temp directory OUTSIDE
the repository for the wav_path leg. Nothing is downloaded, no provider is
called, no key is read.

One test per acceptance clause:
  pass fixture clears | dry cut clears | ringing fixture fails all three
  metrics | failed line queued on the Suno / Skill 74 path | TTS and foreign
  transports refused by name | only failing lines queued | sung lines gated
  too | missing anchor / bad anchor / silence / missing audio fail closed |
  wav_path agrees with inline samples | qc_gate accepts the verdict and
  blocks assembly | CLI 0 / 5 / 1 | deterministic and no spend | no media
  file, no operator path, no network import in the owned dir

Run: python3 core/qc_reverb_tail/test_qc_reverb_tail.py
Env: QCRT_FIXTURE_DIR keeps the generated WAVs somewhere durable
     (default: /tmp/lane-AF-ECHO-U2-fixtures).
"""
import atexit
import importlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import qc_gate as G                   # noqa: E402  (sibling, same core/ tree)
import qc_reverb_tail as PKG          # noqa: E402  (package under test)

MODULE = importlib.import_module("qc_reverb_tail.qc_reverb_tail")
CLI = os.path.join(HERE, "qc_reverb_tail.py")

RATE = 8000
BODY_S = 0.5
TAIL_S = 0.6
F0 = 180.0
HARMONICS = (1.0, 0.5, 0.25)
#: Deterministic IR time constants. 40 ms is a dry close-mic cut; 800 ms is
#: the ghost reverb D22a exists to catch.
PASS_TAU_S = 0.04
FAIL_TAU_S = 0.80

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % str(detail)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ------------------------------------------------------------ fixtures -----

def synth_tone(seconds, rate=RATE, f0=F0, harmonics=HARMONICS):
    """Deterministic int-free tone. No randomness anywhere."""
    n = int(rate * seconds)
    out = []
    for i in range(n):
        t = i / rate
        v = 0.0
        for k, amp in enumerate(harmonics, start=1):
            v += amp * math.sin(2.0 * math.pi * f0 * k * t)
        out.append(v / len(harmonics))
    return out

def render_ir(body, tau_s, rate=RATE, tail_s=TAIL_S):
    """Convolve ``body`` with a deterministic exponential impulse response
    ``ir[k] = exp(-k / (rate * tau))`` via the exact one-pole recursion, then
    keep ``tail_s`` of output. Same numbers on every machine, every run.
    """
    a = math.exp(-1.0 / (rate * tau_s))
    n_out = len(body) + int(rate * tail_s)
    out = []
    prev = 0.0
    for i in range(n_out):
        x = body[i] if i < len(body) else 0.0
        prev = x + a * prev
        out.append(prev)
    return out

def normalize(sig, target=0.9):
    peak = max(abs(s) for s in sig)
    if peak <= 0.0:
        return list(sig)
    return [s * target / peak for s in sig]

def fixture(tau_s=None, seconds=BODY_S, tail_s=TAIL_S):
    """A spoken-line-shaped signal: tone body, then the reverb tail.

    ``tau_s=None`` builds the dry control (hard cut, no reverb at all).
    """
    body = synth_tone(seconds)
    if tau_s is None:
        sig = body + [0.0] * int(RATE * tail_s)
    else:
        sig = render_ir(body, tau_s, tail_s=tail_s)
    return normalize(sig)

def fixture_dir():
    d = os.environ.get("QCRT_FIXTURE_DIR") or "/tmp/lane-AF-ECHO-U2-fixtures"
    os.makedirs(d, exist_ok=True)
    return d

def write_wav(path, samples, rate=RATE):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
            for s in samples))
    return path

WAVS = {}

def build_fixtures():
    """Idempotent: safe to call from the direct runner and from import."""
    if WAVS.get("_dir"):
        return WAVS
    d = fixture_dir()
    WAVS["clean"] = write_wav(os.path.join(d, "clean.wav"),
                              fixture(PASS_TAU_S))
    WAVS["dry"] = write_wav(os.path.join(d, "dry.wav"), fixture(None))
    WAVS["ringing"] = write_wav(os.path.join(d, "ringing.wav"),
                                fixture(FAIL_TAU_S))
    WAVS["_dir"] = d
    return WAVS

def cleanup_fixtures():
    """The generated WAVs never outlive the suite and never enter the repo."""
    d = WAVS.get("_dir")
    if d and not os.environ.get("QCRT_FIXTURE_DIR"):
        shutil.rmtree(d, ignore_errors=True)

# Built on import so the direct runner AND a bare pytest collection both see
# the wav_path fixtures; removed at process exit either way.
build_fixtures()
atexit.register(cleanup_fixtures)

def line(line_id, samples=None, wav=None, body_end_s=BODY_S,
         sample_rate=RATE):
    rec = {"line_id": line_id, "body_end_s": body_end_s}
    if wav:
        rec["wav_path"] = wav
    if samples is not None:
        rec["samples"] = samples
        rec["sample_rate"] = sample_rate
    return rec

def report(lines, run_id="run-rt-1", stage="audio"):
    return {"schema_version": MODULE.SCHEMA_VERSION, "run_id": run_id,
            "stage": stage, "lines": lines}

def codes(result):
    return sorted({f["code"] for f in result["evidence"]["failures"]})

def queued_ids(result):
    return [q["line_id"] for q in result["evidence"]["regen_queue"]]

# ------------------------------------------------------------ pass / fail ---

def test_pass_fixture_clean_tail():
    m = MODULE.measure_tail(fixture(PASS_TAU_S), RATE, BODY_S)
    check("clean tail measured", m is not None, str(m))
    check("clean tail reaches quiet within budget",
          m["to_quiet_ms"] is not None and m["to_quiet_ms"] <=
          MODULE.TAIL_BUDGET_MS, str(m["to_quiet_ms"]))
    check("clean tail decays fast enough",
          m["decay_db_per_s"] is not None and
          m["decay_db_per_s"] >= MODULE.MIN_DECAY_DB_PER_S,
          str(m["decay_db_per_s"]))
    check("clean tail ends quiet",
          m["end_level_db"] <= MODULE.END_LEVEL_LIMIT_DB,
          str(m["end_level_db"]))
    r = MODULE.evaluate(report([line("pass-1", samples=fixture(PASS_TAU_S))]))
    check("pass fixture outcome ok", r["outcome"] == "ok",
          "%s %s" % (r["outcome"], r["reason_code"]))
    check("pass fixture reason REVERB_TAIL_OK",
          r["reason_code"] == "REVERB_TAIL_OK", r["reason_code"])
    check("pass fixture nothing queued", r["evidence"]["regen_queue"] == [],
          str(r["evidence"]["regen_queue"]))
    check("pass fixture counted as measured",
          r["evidence"]["lines_measured"] == 1, str(r["evidence"]))
    check("pass fixture zero ringing", r["evidence"]["lines_ringing"] == 0,
          str(r["evidence"]["lines_ringing"]))

def test_dry_cut_passes():
    m = MODULE.measure_tail(fixture(None), RATE, BODY_S)
    check("dry cut reaches quiet at once", m["to_quiet_ms"] == 0.0,
          str(m["to_quiet_ms"]))
    check("dry cut has no measurable slope to complain about",
          m["decay_db_per_s"] is None or
          m["decay_db_per_s"] >= MODULE.MIN_DECAY_DB_PER_S,
          str(m["decay_db_per_s"]))
    r = MODULE.evaluate(report([line("dry-1", samples=fixture(None))]))
    check("dry cut outcome ok", r["outcome"] == "ok", r["reason_code"])

def test_fail_fixture_rings_on():
    m = MODULE.measure_tail(fixture(FAIL_TAU_S), RATE, BODY_S)
    check("ringing tail never reaches quiet",
          m["to_quiet_ms"] is None, str(m["to_quiet_ms"]))
    check("ringing tail decay is shallow",
          m["decay_db_per_s"] is not None and
          m["decay_db_per_s"] < MODULE.MIN_DECAY_DB_PER_S,
          str(m["decay_db_per_s"]))
    check("ringing tail is loud at the buffer end",
          m["end_level_db"] > MODULE.END_LEVEL_LIMIT_DB,
          str(m["end_level_db"]))
    r = MODULE.evaluate(report([line("fail-1", samples=fixture(FAIL_TAU_S))]))
    check("ringing fixture rejected", r["outcome"] == "rejected",
          r["outcome"])
    c = codes(r)
    for want in ("RINGING_TAIL", "TAIL_DECAY_TOO_SLOW", "TAIL_ENDS_LOUD"):
        check("ringing fixture fires %s" % want, want in c, str(c))
    check("ringing fixture counted",
          r["evidence"]["lines_ringing"] == 1,
          str(r["evidence"]["lines_ringing"]))
    check("ringing fixture names D22a",
          r["evidence"]["rule"] == "D22a", str(r["evidence"]["rule"]))
    check("ringing fixture next action stays in Suno",
          "Suno" in r["next_action"] and "Skill 74" in r["next_action"],
          r["next_action"])
    check("ringing fixture never mentions a TTS retry",
          "never re-try a line through a text-to-speech tool"
          in r["next_action"], r["next_action"])

# ------------------------------------------------------------ regen route ---

def test_fail_line_queued_for_suno_regen():
    r = MODULE.evaluate(report([line("fail-1", samples=fixture(FAIL_TAU_S))]))
    q = r["evidence"]["regen_queue"]
    check("failed line is queued", len(q) == 1, str(q))
    entry = q[0]
    check("queue entry names the failed line",
          entry["line_id"] == "fail-1", str(entry))
    check("queue entry outcome queued", entry["outcome"] == "queued",
          str(entry["outcome"]))
    check("queue entry records the ringing reason",
          "RINGING_TAIL" in entry["reason_code"], entry["reason_code"])
    check("queue entry says TTS never", entry["tts"] == "never",
          str(entry["tts"]))
    regen = entry["regen"]
    check("regen provider is suno", regen["provider"] == "suno",
          str(regen["provider"]))
    check("regen rides Skill 74 only",
          regen["transport"] == "skill-74-kie-live-adapter",
          str(regen["transport"]))
    check("regen endpoint is the createTask path",
          regen["endpoint"] == "POST /api/v1/jobs/createTask",
          str(regen["endpoint"]))
    check("regen model is the Suno route",
          regen["model"] == "ai-music-api/generate",
          str(regen["model"]))
    check("regen input model recorded", regen["input_model"] == "V6",
          str(regen["input_model"]))
    check("regen style is dry close-mic",
          "dry" in regen["style"] and "close-mic" in regen["style"] and
          "reverb" in regen["style"], regen["style"])
    check("regen style bans the three spoken words",
          all(w in regen["style"] for w in ("spacious", "cinematic",
                                            "choir")), regen["style"])
    check("regen style carries the expanded negative tags",
          all(w in regen["style"] for w in ("room", "wet", "shimmer",
                                            "atmospheric", "choir pad",
                                            "delay", "hall")),
          regen["style"])
    check("regen style bans pitch-shift",
          "pitch-shift" in regen["style"], regen["style"])
    check("regen carries the measured tail", "to_quiet_ms"
          in regen["metrics"], str(sorted(regen["metrics"])))
    check("regen cites D22a", regen["rule"] == "D22a", str(regen["rule"]))
    check("no regen transport errors", r["evidence"]["regen_errors"] == [],
          str(r["evidence"]["regen_errors"]))

def test_tts_and_foreign_transport_refused_by_name():
    for provider in ("elevenlabs", "ElevenLabs", "fish_audio", "kie_tts",
                     "azure_tts", "google_tts", "playht", "cartesia",
                     "openai_tts"):
        env = MODULE.regen_path("fail-1", "RINGING_TAIL", provider=provider)
        check("regen refuses %r" % provider,
              env["outcome"] == "rejected", str(env.get("outcome")))
        check("reason external-tts-refused for %r" % provider,
              env["reason_code"] == "external-tts-refused",
              env["reason_code"])
        check("refusal names %r" % provider,
              any("PROVIDER_REFUSED" in e for e in env["errors"]),
              str(env["errors"]))
        check("refusal carries no regen path", env["regen"] is None,
              str(env["regen"]))
        check("refusal still records tts never", env["tts"] == "never",
              str(env["tts"]))
    for transport in ("skill-68-kie-audio", "direct-suno", "",
                      "http-transport"):
        env = MODULE.regen_path("fail-1", "RINGING_TAIL", transport=transport)
        check("regen refuses transport %r" % transport,
              env["outcome"] == "rejected" and
              env["reason_code"] == "transport-not-skill-74",
              str(env.get("reason_code")))
    ok = MODULE.regen_path("fail-1", "RINGING_TAIL")
    check("default route accepted", ok["outcome"] == "queued",
          str(ok.get("reason_code")))
    # Queuing itself can be pointed at a voice tool and still refuses.
    r = MODULE.evaluate(report([line("fail-1", samples=fixture(FAIL_TAU_S))]))
    check("evaluate used the default Suno route",
          len(r["evidence"]["regen_queue"]) == 1 and
          r["evidence"]["regen_errors"] == [], str(r["evidence"]))

def test_sung_line_is_measured_too():
    """The brief gates the tail after EVERY vocal phrase, spoken and sung."""
    sung = line("sing-1", samples=fixture(FAIL_TAU_S))
    sung["delivery"] = "sung"
    r = MODULE.evaluate(report([sung]))
    check("sung ringing line rejected", r["outcome"] == "rejected",
          r["outcome"])
    check("sung line measured",
          r["evidence"]["lines_measured"] == 1,
          str(r["evidence"]["lines_measured"]))
    check("sung line counted as ringing",
          r["evidence"]["lines_ringing"] == 1,
          str(r["evidence"]["lines_ringing"]))
    check("sung line queued for Suno regen", queued_ids(r) == ["sing-1"],
          str(queued_ids(r)))
    spoken = line("say-1", samples=fixture(PASS_TAU_S))
    spoken["delivery"] = "spoken"
    ok = MODULE.evaluate(report([spoken]))
    check("spoken clean line still passes", ok["outcome"] == "ok",
          ok["reason_code"])

def test_mixed_report_only_failed_line_queued():
    r = MODULE.evaluate(report([
        line("good-1", samples=fixture(PASS_TAU_S)),
        line("bad-1", samples=fixture(FAIL_TAU_S)),
    ]))
    check("mixed report rejected", r["outcome"] == "rejected", r["outcome"])
    check("only the ringing line is queued", queued_ids(r) == ["bad-1"],
          str(queued_ids(r)))
    check("both lines measured", r["evidence"]["lines_measured"] == 2,
          str(r["evidence"]["lines_measured"]))
    check("one line ringing", r["evidence"]["lines_ringing"] == 1,
          str(r["evidence"]["lines_ringing"]))
    good = [p for p in r["evidence"]["per_line"] if p["line_id"] == "good-1"][0]
    bad = [p for p in r["evidence"]["per_line"] if p["line_id"] == "bad-1"][0]
    check("good line verdict ok", good["outcome"] == "ok", str(good))
    check("bad line verdict rejected", bad["outcome"] == "rejected",
          str(bad["reason_code"]))

# ------------------------------------------------------------ fail-closed ---

def raises_code(fn, code):
    try:
        fn()
    except MODULE.ReverbTailError as e:
        return e.code == code, "code=%s" % e.code
    except Exception as e:                          # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)
    return False, "no exception raised"

def test_missing_anchor_fails_closed():
    ok, detail = raises_code(
        lambda: MODULE.measure_tail(fixture(FAIL_TAU_S), RATE, None),
        "TAIL_ANCHOR_MISSING")
    check("no anchor refused", ok, detail)
    rec = dict(line("noanchor-1", samples=fixture(PASS_TAU_S)))
    del rec["body_end_s"]
    r = MODULE.evaluate(report([rec]))
    check("report without anchor rejected", r["outcome"] == "rejected",
          r["outcome"])
    check("code TAIL_ANCHOR_MISSING", "TAIL_ANCHOR_MISSING" in codes(r),
          str(codes(r)))
    check("a clean line still cannot pass without an anchor",
          r["reason_code"] != "REVERB_TAIL_OK", r["reason_code"])

def test_bad_anchor_fails_closed():
    for anchor, code in ((-0.2, "TAIL_ANCHOR_INVALID"),
                         (0, "TAIL_ANCHOR_INVALID"),
                         (99.0, "TAIL_ANCHOR_INVALID"),
                         ("end", "TAIL_ANCHOR_INVALID")):
        ok, detail = raises_code(
            lambda a=anchor: MODULE.measure_tail(fixture(PASS_TAU_S), RATE, a),
            code)
        check("anchor %r refused as %s" % (anchor, code), ok, detail)
    # Anchor one sample before the end: no frames left to measure.
    sig = fixture(PASS_TAU_S)
    ok, detail = raises_code(
        lambda: MODULE.measure_tail(sig, RATE, (len(sig) - 1) / float(RATE)),
        "TAIL_UNMEASURABLE")
    check("anchor at the last sample refused", ok, detail)
    ok, detail = raises_code(lambda: MODULE.measure_tail([0.0] * 8, RATE, 0.01),
                             "TAIL_UNMEASURABLE")
    check("buffer too short refused", ok, detail)

def test_silent_line_never_passes():
    silent = [0.0] * int(RATE * (BODY_S + TAIL_S))
    ok, detail = raises_code(lambda: MODULE.measure_tail(silent, RATE, BODY_S),
                             "LINE_SILENT")
    check("all-zero line refused", ok, detail)
    r = MODULE.evaluate(report([line("mute-1", samples=silent)]))
    check("silent line rejected", r["outcome"] == "rejected", r["outcome"])
    check("silent line code", "LINE_SILENT" in codes(r), str(codes(r)))
    # Loud tail after a silent body: the body still gives nothing to measure.
    weird = [0.0] * int(RATE * 0.4) + synth_tone(0.4)
    ok, detail = raises_code(lambda: MODULE.measure_tail(weird, RATE, 0.3),
                             "LINE_SILENT")
    check("silent body refused", ok, detail)

def test_missing_audio_fails_closed():
    r = MODULE.evaluate(report([{"line_id": "ghost-1"}]))
    check("line without audio rejected", r["outcome"] == "rejected",
          r["outcome"])
    check("code AUDIO_MISSING", "AUDIO_MISSING" in codes(r), str(codes(r)))
    r2 = MODULE.evaluate(report([line("norate-1", samples=[0.1] * 500,
                                      sample_rate=0)]))
    check("sample_rate 0 rejected",
          "AUDIO_UNREADABLE" in codes(r2), str(codes(r2)))
    r3 = MODULE.evaluate(report(["not an object"]))
    check("malformed line rejected", "LINE_MALFORMED" in codes(r3),
          str(codes(r3)))
    for res in (r, r2, r3):
        check("unmeasured line is never PASS", res["outcome"] != "ok",
              res["outcome"])

def test_report_shape_is_validated():
    for bad, code in ((None, "BAD_INPUT"),
                      ({"schema_version": "nope", "run_id": "x",
                        "stage": "audio", "lines": []}, "BAD_INPUT"),
                      ({"schema_version": MODULE.SCHEMA_VERSION,
                        "run_id": "", "stage": "audio", "lines": []},
                       "BAD_INPUT"),
                      ({"schema_version": MODULE.SCHEMA_VERSION,
                        "run_id": "x", "stage": "audio", "lines": []},
                       "BAD_INPUT")):
        ok, detail = raises_code(lambda b=bad: MODULE.evaluate(b), code)
        check("report rejected as %s" % code, ok, detail)

# ------------------------------------------------------------- fixtures -----

def test_wav_path_matches_inline_samples():
    """Same fixture through wav_path and through inline samples: same verdict.
    Proves the loader without ever putting media in the repository."""
    clean_inline = MODULE.evaluate(
        report([line("w1", samples=fixture(PASS_TAU_S))]))
    clean_wav = MODULE.evaluate(
        report([line("w1", wav=WAVS["clean"])]))
    ring_inline = MODULE.evaluate(
        report([line("w2", samples=fixture(FAIL_TAU_S))]))
    ring_wav = MODULE.evaluate(
        report([line("w2", wav=WAVS["ringing"])]))
    check("clean wav agrees with clean inline",
          clean_wav["outcome"] == clean_inline["outcome"] == "ok",
          "%s / %s" % (clean_wav["outcome"], clean_inline["outcome"]))
    check("ringing wav agrees with ringing inline",
          ring_wav["outcome"] == ring_inline["outcome"] == "rejected",
          "%s / %s" % (ring_wav["outcome"], ring_inline["outcome"]))
    ci = clean_inline["evidence"]["per_line"][0]["metrics"]
    cw = clean_wav["evidence"]["per_line"][0]["metrics"]
    check("to_quiet_ms agrees within one frame",
          abs(ci["to_quiet_ms"] - cw["to_quiet_ms"]) <= MODULE.FRAME_MS,
          "%s vs %s" % (ci["to_quiet_ms"], cw["to_quiet_ms"]))
    check("wav path queues the ringing line",
          queued_ids(ring_wav) == ["w2"], str(queued_ids(ring_wav)))
    check("wav path reports the same ringing codes",
          codes(ring_wav) == codes(ring_inline),
          "%s vs %s" % (codes(ring_wav), codes(ring_inline)))
    check("missing wav file is AUDIO_MISSING",
          "AUDIO_MISSING" in codes(
              MODULE.evaluate(report([line("w3", wav="/tmp/lane-AF-ECHO-U2-"
                                                    "missing.wav")]))),
          "wav_path missing not refused")

# ------------------------------------------------------------- qc record ----

def test_qc_gate_integration_and_refusal():
    ok = MODULE.evaluate(report([line("L1", samples=fixture(PASS_TAU_S))]))
    bad = MODULE.evaluate(report([line("L1", samples=fixture(FAIL_TAU_S))]))
    rev = {"identity": "qc_reverb_tail", "session": "t1",
           "authority": "owner-decision-D22a"}
    rec_ok = MODULE.to_qc_record(ok, rev)
    rec_bad = MODULE.to_qc_record(bad, rev)
    check("pass record validates in qc_gate",
          G.validate_record(rec_ok) is None, G.validate_record(rec_ok))
    check("fail record validates in qc_gate",
          G.validate_record(rec_bad) is None, G.validate_record(rec_bad))
    check("pass verdict is PASS", rec_ok["verdict"] == "PASS",
          rec_ok["verdict"])
    check("fail verdict is FAIL", rec_bad["verdict"] == "FAIL",
          rec_bad["verdict"])
    check("fail record counts the queued regen",
          "1 queued for Suno regen" in rec_bad["evidence"]["summary"],
          rec_bad["evidence"]["summary"])
    check("record check is audio", rec_ok["check"] == "audio",
          rec_ok["check"])
    check("record check_id is reverb-tail", rec_ok["check_id"] == "reverb-tail",
          rec_ok["check_id"])
    makers = {rec_ok["check_id"]: "suno_generator"}
    g_ok = G.evaluate("run-rt-1", "audio", [rec_ok], makers, ["audio"])
    g_bad = G.evaluate("run-rt-1", "audio", [rec_bad], makers, ["audio"])
    check("qc_gate PASS when the tail is clean", g_ok["gate"] == "PASS", g_ok)
    check("qc_gate FAIL when the line rings", g_bad["gate"] == "FAIL", g_bad)
    try:
        MODULE.refuse_before_assembly(bad)
        check("assembly refuses a ringing report", False)
    except PKG.AssemblyBlocked as e:
        check("assembly refuses a ringing report",
              str(e) == bad["reason_code"], str(e))
    check("assembly passes a clean report",
          MODULE.refuse_before_assembly(ok) is True)
    ok2, detail = raises_code(
        lambda: MODULE.to_qc_record(ok, {"identity": "x"}), "BAD_INPUT")
    check("reviewer without session refused", ok2, detail)

# ----------------------------------------------------------------- CLI ------

def test_cli_ok_and_rejected():
    d = fixture_dir()
    ok_path = os.path.join(d, "report-ok.json")
    bad_path = os.path.join(d, "report-bad.json")
    rec_path = os.path.join(d, "record.json")
    for path, body in ((ok_path, report(
                            [line("L1", samples=fixture(PASS_TAU_S))])),
                       (bad_path, report(
                            [line("L1", samples=fixture(FAIL_TAU_S))]))):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(body, f)
    p = subprocess.run([sys.executable, CLI, "check", "--report", ok_path,
                        "--qc-record", rec_path],
                       capture_output=True, text=True)
    check("cli exit 0 on a clean tail", p.returncode == 0,
          "%s %s" % (p.returncode, p.stderr[:200]))
    check("cli emits schema_version",
          MODULE.SCHEMA_VERSION in p.stdout, p.stdout[:200])
    check("qc-record file written",
          os.path.exists(rec_path) and
          '"verdict": "PASS"' in open(rec_path).read())
    p2 = subprocess.run([sys.executable, CLI, "check", "--report", bad_path],
                        capture_output=True, text=True)
    check("cli exit 5 on a ringing line", p2.returncode == 5, p2.returncode)
    check("cli names the ringing reason", "RINGING_TAIL" in p2.stdout,
          p2.stdout[:400])
    p3 = subprocess.run([sys.executable, CLI, "check", "--report",
                         "/tmp/lane-AF-ECHO-U2-nope.json"],
                        capture_output=True, text=True)
    check("cli exit 1 on unreadable report", p3.returncode == 1,
          p3.returncode)

# -------------------------------------------------------------- static ------

def test_determinism_and_no_spend():
    sig = fixture(FAIL_TAU_S)
    a = MODULE.measure_tail(sig, RATE, BODY_S)
    b = MODULE.measure_tail(list(sig), RATE, BODY_S)
    check("measurement deterministic", a == b, (a, b))
    a2 = MODULE.measure_tail(fixture(FAIL_TAU_S), RATE, BODY_S)
    check("fixture synthesis deterministic", a2 == a, a2)
    # Zero spend: the module carries no transport, no key, no paid hook.
    src = open(os.path.join(HERE, "qc_reverb_tail.py"), encoding="utf-8")
    low = src.read().lower()
    src.close()
    for needle in ("urllib", "requests", "http.client", "subprocess",
                   "socket", "os.system", "popen", "/users/", "/home/",
                   "spend_ledger", "https://", "api.kie.ai", "openai"):
        check("module source has no %r" % needle, needle not in low, needle)
    check("module carries no own transport",
          not any(hasattr(MODULE, attr)
                  for attr in ("session", "client", "engine", "adapter")))
    check("module never reads an environment key",
          "environ" not in low and "getenv" not in low, "env read found")

def test_no_media_and_owned_dir_only():
    banned_ext = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
                  ".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif")
    entries = sorted(os.listdir(HERE))
    media = [e for e in entries if e.lower().endswith(banned_ext)]
    check("no media file in the owned dir", media == [], str(media))
    py_files = [e for e in entries if e.endswith(".py")]
    check("module + test + package init are the only python files",
          sorted(py_files) == ["__init__.py", "qc_reverb_tail.py",
                               "test_qc_reverb_tail.py"], str(py_files))
    # Nothing outside the owned dir was written by this unit.
    stray = os.path.join(os.path.dirname(HERE),
                         "qc_reverb_tail." + "py")
    check("owned dir is core/qc_reverb_tail",
          os.path.basename(HERE) == "qc_reverb_tail", HERE)
    check("no sidecar module beside the package",
          os.path.exists(stray) is False, stray)
    for name in entries:
        path = os.path.join(HERE, name)
        if os.path.isdir(path) and name != "__pycache__":
            check("no unexpected subdirectory %s" % name, False, path)
    d = WAVS.get("_dir")
    if d:
        check("fixtures live outside the repo",
              not os.path.abspath(d).startswith(
                  os.path.abspath(os.path.dirname(HERE)) + os.sep), d)

def test_static_skill74_only_kie_path():
    src = open(os.path.join(HERE, "qc_reverb_tail.py"), encoding="utf-8").read()
    check("one transport constant",
          src.count("REGEN_TRANSPORT =") == 1, src.count("REGEN_TRANSPORT ="))
    check("transport is Skill 74",
          MODULE.REGEN_TRANSPORT == "skill-74-kie-live-adapter",
          MODULE.REGEN_TRANSPORT)
    check("endpoint is the createTask path",
          MODULE.REGEN_ENDPOINT == "POST /api/v1/jobs/createTask",
          MODULE.REGEN_ENDPOINT)
    check("model is the Suno route",
          MODULE.REGEN_MODEL == "ai-music-api/generate",
          MODULE.REGEN_MODEL)
    check("provider is suno", MODULE.PROVIDER == "suno", MODULE.PROVIDER)
    check("TTS is never", MODULE.TTS == "never", MODULE.TTS)
    check("no other provider name is spelled as a target",
          not re.search(r"\b(elevenlabs|fish[-_ ]?audio|playht|cartesia|"
                        r"azure|descript|edge[-_ ]?tts|azure[-_ ]?tts)\b",
                        src, re.I),
          "a foreign provider appears in module source")
    check("thresholds are all published",
          all(isinstance(v, (int, float))
              for v in (MODULE.FRAME_MS, MODULE.QUIET_RATIO,
                        MODULE.TAIL_BUDGET_MS, MODULE.MIN_DECAY_DB_PER_S,
                        MODULE.END_LEVEL_LIMIT_DB)), "threshold missing")
    check("thresholds hold their D22a values",
          (MODULE.FRAME_MS, MODULE.QUIET_RATIO, MODULE.TAIL_BUDGET_MS,
           MODULE.MIN_DECAY_DB_PER_S, MODULE.END_LEVEL_LIMIT_DB) ==
          (10.0, 0.02, 250.0, 40.0, -30.0),
          str((MODULE.FRAME_MS, MODULE.QUIET_RATIO, MODULE.TAIL_BUDGET_MS,
               MODULE.MIN_DECAY_DB_PER_S, MODULE.END_LEVEL_LIMIT_DB)))

def test_envelope_stamps_and_exports():
    stamps = (MODULE.evaluate(report(
                  [line("L1", samples=fixture(PASS_TAU_S))])),
              MODULE.evaluate(report(
                  [line("L2", samples=fixture(FAIL_TAU_S))])))
    for i, res in enumerate(stamps):
        check("envelope %d schema stamp" % i,
              res.get("schema_version") == MODULE.SCHEMA_VERSION,
              str(res.get("schema_version")))
        check("envelope %d tool stamp" % i,
              res.get("tool_version") == MODULE.TOOL_VERSION,
              str(res.get("tool_version")))
        check("envelope %d carries a next action" % i,
              bool(res.get("next_action")), str(res.get("next_action")))
    for name in ("SCHEMA_VERSION", "RULE_ID", "PROVIDER", "TTS",
                 "REGEN_TRANSPORT", "REGEN_MODEL", "RINGING_CODES",
                 "TAIL_BUDGET_MS", "MIN_DECAY_DB_PER_S", "measure_tail",
                 "check_line", "evaluate", "regen_path", "to_qc_record",
                 "refuse_before_assembly", "ReverbTailError",
                 "AssemblyBlocked", "load_wav_samples"):
        check("package exports %s" % name, hasattr(PKG, name))
    check("rule id is D22a", MODULE.RULE_ID == "D22a", MODULE.RULE_ID)
    check("ringing codes are the three tail codes",
          MODULE.RINGING_CODES == frozenset(
              ("RINGING_TAIL", "TAIL_DECAY_TOO_SLOW", "TAIL_ENDS_LOUD")),
          str(sorted(MODULE.RINGING_CODES)))

def test_no_failed_checks():
    """pytest guard: check() records failures, it does not raise them.

    Without this a bare ``pytest`` run would report green on a red suite.
    The direct runner gets the same signal through main()'s exit code.
    """
    assert not FAILS, "failed checks: %s" % FAILS

TESTS = [
    test_pass_fixture_clean_tail,
    test_dry_cut_passes,
    test_fail_fixture_rings_on,
    test_fail_line_queued_for_suno_regen,
    test_tts_and_foreign_transport_refused_by_name,
    test_mixed_report_only_failed_line_queued,
    test_sung_line_is_measured_too,
    test_missing_anchor_fails_closed,
    test_bad_anchor_fails_closed,
    test_silent_line_never_passes,
    test_missing_audio_fails_closed,
    test_report_shape_is_validated,
    test_wav_path_matches_inline_samples,
    test_qc_gate_integration_and_refusal,
    test_cli_ok_and_rejected,
    test_determinism_and_no_spend,
    test_no_media_and_owned_dir_only,
    test_static_skill74_only_kie_path,
    test_envelope_stamps_and_exports,
    test_no_failed_checks,
]

def main():
    build_fixtures()
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False, "%s: %s"
                  % (type(e).__name__, e))
    cleanup_fixtures()
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d outcome tests passed" % len(TESTS))
    return 0

if __name__ == "__main__":
    sys.exit(main())
