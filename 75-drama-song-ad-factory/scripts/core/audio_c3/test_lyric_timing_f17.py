#!/usr/bin/env python3
"""F17 unit tests: the 3-tier transcription order, the Part D load guard,
the qc scan rule. stdlib only, every provider mocked, $0 spend.

Run: python3 core/audio_c3/test_lyric_timing_f17.py
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)                       # .../scripts/core
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "audio_c3"))

MODULE = importlib.import_module("lyric_timing")
import lyric_timing as LT  # noqa: E402

FAILS = []
PASSES = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    (PASSES if cond else FAILS).append(name)


# ── fixtures ─────────────────────────────────────────────────────────────────

def make_tmp():
    return tempfile.mkdtemp(prefix="lyric-timing-f17-")


TRACK = {"task_id": "suno-task-1", "audio_id": "audio-9"}

ALIGNED_DOC = {
    "alignedWords": [
        {"word": "power", "startS": 0.0, "endS": 0.42},
        {"word": "in", "startS": 0.42, "endS": 0.6},
        {"word": "the", "startS": 0.6, "endS": 0.75},
        {"word": "climb", "startS": 0.75, "endS": 1.3},
    ]
}


def ok_dispatch(dispatcher_calls):
    """Fake kie_dispatch.dispatch: saves one alignedWords file, records args."""
    def fake(**kw):
        dispatcher_calls.append(kw)
        doc = os.path.join(make_tmp(), "aligned.json")
        with open(doc, "w", encoding="utf-8") as f:
            json.dump(ALIGNED_DOC, f)
        return {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK",
                "evidence": {"saved_paths": [doc]}}
    return fake


def fail_dispatch(**kw):
    return {"outcome": "rejected", "reason_code": "KIE_RUN_FAILED",
            "next_action": "reconcile"}


# ── 1. tier 1: Suno alignment, zero local loads ─────────────────────────────

def test_tier1_returns_suno_alignment_no_local_loads():
    calls = []
    got = LT.provide_word_timings(dict(TRACK), dispatcher=ok_dispatch(calls))
    check("tier1 ok", got["ok"] is True)
    t = got["timings"]
    check("tier1 source suno-timestamped-lyrics",
          t["source"] == "suno-timestamped-lyrics", t["source"])
    check("tier1 payload suno-alignedWords",
          t["evidence"]["payload"] == "suno-alignedWords")
    check("tier1 words", [w["word"] for w in t["words"]] ==
          ["power", "in", "the", "climb"])
    check("tier1 startS/endS numeric",
          t["words"][0]["start"] == 0.0 and t["words"][0]["end"] == 0.42)
    check("tier1 zero local loads", t["local_model_loads"] == 0)
    check("tier1 rode kie_dispatch (model id)",
          calls and calls[0]["model"] == "ai-music-api/timeStamped-lyrics",
          "no dispatch call recorded")
    check("tier1 provider suno",
          t["transcription_provider"] == "suno (KIE timeStamped-lyrics)")


def test_tier1_hint_skips_dispatch():
    calls = []
    hint = {"alignedWords": ALIGNED_DOC["alignedWords"]}
    got = LT.provide_word_timings(dict(TRACK), timing_map_hint=hint,
                                  dispatcher=ok_dispatch(calls))
    check("tier1 hint ok + no dispatch", got["ok"] and not calls)
    check("tier1 hint source", got["timings"]["source"] ==
          "suno-timestamped-lyrics")
    check("tier1 hint zero loads",
          got["timings"]["local_model_loads"] == 0)


def test_tier1_words_shape_exact():
    got = LT.provide_word_timings(dict(TRACK),
                                  timing_map_hint={"alignedWords":
                                                   ALIGNED_DOC["alignedWords"]})
    w = got["timings"]["words"][0]
    check("tier1 word keys word/start/end",
          set(w) == {"word", "start", "end"}, sorted(w))


# ── 2. tier 2: forced tier-1 failure -> exactly ONE faster-whisper load ─────

def make_fake_loader(counter):
    """A fake faster_whisper.WhisperModel: records loads + per-track calls.

    Name/module surface must keep passing the banned-ASR check exactly the
    way the real 'faster_whisper' import does.
    """
    def fake_loader(size, compute):
        counter["loads"] += 1
        counter["sizes"].append((size, compute))
        # A real faster_whisper.WhisperModel.transcribe() yields segments; the
        # stand-in returns the segment list directly.
        return lambda audio: [
            {"words": [{"word": w["word"], "start": float(w["startS"]),
                        "end": float(w["endS"])}
                       for w in ALIGNED_DOC["alignedWords"]]}]
    fake_loader.__name__ = "fake_loader"          # no whisper surface
    fake_loader.__module__ = "test_lyric_timing_f17"
    return fake_loader


def test_tier2_forced_failure_exactly_one_load_multi_track():
    counter = {"loads": 0, "sizes": []}
    session = LT.WhisperSession(loader=make_fake_loader(counter),
                                free_gb_probe=lambda: 16.0)
    got = LT.provide_word_timings(dict(TRACK), dispatcher=fail_dispatch,
                                  whisper_session=session,
                                  ledger_db=os.path.join(make_tmp(), "l.db"))
    check("tier2 ok", got["ok"] is True)
    t = got["timings"]
    check("tier2 source faster-whisper-local",
          t["source"] == "faster-whisper-local", t["source"])
    check("tier2 exactly ONE load", t["evidence"]["loads"] == 1
          and session.loads == 1,
          "loads=%s" % session.loads)
    check("tier2 words present",
          [w["word"] for w in t["words"]] == ["power", "in", "the", "climb"])
    check("tier2 local_model_loads receipt = 1", t["local_model_loads"] == 1)
    check("tier2 small default",
          counter["sizes"] == [("small", "int8")], counter["sizes"])
    check("tier2 provider faster-whisper",
          t["transcription_provider"] == "faster-whisper")


def test_tier2_multi_track_one_session_counts_one_load():
    counter = {"loads": 0, "sizes": []}
    session = LT.WhisperSession(loader=make_fake_loader(counter),
                                free_gb_probe=lambda: 16.0)
    tracks = [dict(TRACK), {"task_id": "t2", "audio_id": "a2",
                            "audio_path": "/x/second.wav"}]
    tx = session.transcribe_all(tracks)
    one = LT.provide_word_timings(tracks[0], dispatcher=fail_dispatch,
                                  whisper_session=session)
    check("multi-track ONE session two transcriptions",
          len(tx) == 2)
    check("multi-track still exactly one load", session.loads == 1,
          "loads=%s" % session.loads)
    check("multi-track second track used SAME model",
          session.model is not None and session.loads == 1)
    check("one-at-a-time receipt", one["timings"]["evidence"]["loads"] == 1)


def test_tier2_never_openai_whisper_loader():
    def openai_loader(size, compute):
        raise AssertionError("never called")
    openai_loader.__name__ = "whisper.load"       # banned surface
    openai_loader.__module__ = "whisper"
    try:
        LT.WhisperSession(loader=openai_loader, free_gb_probe=lambda: 16.0)
        check("openai-whisper loader refused", False, "constructed anyway")
    except LT.LyricTimingError as e:
        check("openai-whisper loader refused", e.code == "LOCAL_ASR_FORBIDDEN",
              e.code)


def test_tier2_size_guard():
    try:
        LT.WhisperSession(loader=lambda s, c: None, model_size="large-v3",
                          free_gb_probe=lambda: 16.0)
        check("size large refused", False)
    except LT.LyricTimingError as e:
        check("size large refused", e.code == "WHISPER_SIZE_FORBIDDEN", e.code)


# ── 3. tier 3: both fail -> client key only, operator keys refused ──────────

def test_tier3_fires_only_after_both_fail_and_cites_client_key():
    class BoomSession(LT.WhisperSession):
        def transcribe_all(self, tracks):
            raise LT.LyricTimingError("LOCAL_MODEL_LOAD_REFUSED", "out of RAM")

    def cloud(track):
        return {"schema_version": LT.SCHEMA_VERSION, "tool": "lyric_timing",
                "source": "cloud-stt", "words": [{"word": "hi", "start": 0.0,
                                                  "end": 0.3}],
                "evidence": {"stt_key_env": "DRAMA75_CLOUD_STT_API_KEY"}}
    got = LT.provide_word_timings(dict(TRACK), dispatcher=fail_dispatch,
                                  whisper_session=BoomSession(loader=None),
                                  cloud=cloud)
    check("tier3 ok", got["ok"] is True, got)
    check("tier3 source cloud-stt",
          got["timings"]["source"] == "cloud-stt", got["timings"]["source"])
    check("tier3 cites the CLIENT key env",
          got["timings"]["evidence"]["stt_key_env"] ==
          "DRAMA75_CLOUD_STT_API_KEY")


def test_tier3_no_cloud_wired_reports_chain():
    class BoomSession(LT.WhisperSession):
        def transcribe_all(self, tracks):
            raise LT.LyricTimingError("LOCAL_MODEL_LOAD_REFUSED", "out of RAM")

    got = LT.provide_word_timings(dict(TRACK), dispatcher=fail_dispatch,
                                  whisper_session=BoomSession(loader=None))
    check("tier3 absent -> fail-closed", got["ok"] is False)
    check("tier3 answer carries tier1+tier2 evidence",
          got["evidence"]["tier1_error"] and got["evidence"]["tier2_error"])


def test_tier3_refuses_operator_keys():
    env = {"KIE_API_KEY": "x", "OPENAI_API_KEY": "y"}
    for name in ("KIE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                 "GOOGLE_API_KEY"):
        try:
            LT.client_stt_key(key_name=name, env=env)
            check("operator key %s refused" % name, False)
        except LT.LyricTimingError as e:
            check("operator key %s refused" % name,
                  e.code == "OPERATOR_KEY_REFUSED", e.code)
    try:
        LT.client_stt_key(env=env)  # no client key; operator keys present
        check("operator-keys-present-no-client-key refused", False)
    except LT.LyricTimingError as e:
        check("operator-keys-present-no-client-key refused",
              e.code == "OPERATOR_KEY_REFUSED", e.code)
    try:
        LT.client_stt_key(env={})
        check("no client key refuses", False)
    except LT.LyricTimingError as e:
        check("no client key refuses", e.code == "CLIENT_KEY_MISSING", e.code)
    check("client key name accepted (presence only)",
          LT.client_stt_key(env={"DRAMA75_CLOUD_STT_API_KEY": "sk-x"}) ==
          "DRAMA75_CLOUD_STT_API_KEY")


def test_tier3_word_timestamps_from_provider():
    def provider(key, track):
        assert key == "DRAMA75_CLOUD_STT_API_KEY"
        return [{"word": "cloud", "start": 1.0, "end": 1.5}]
    got = LT.cloud_stt_word_timings(
        dict(TRACK), env={"DRAMA75_CLOUD_STT_API_KEY": "present"},
        provider_fn=provider)
    check("tier3 provider words", got["words"] ==
          [{"word": "cloud", "start": 1.0, "end": 1.5}])
    check("tier3 receipt zero local loads", got["local_model_loads"] == 0)


# ── 4. Part D load guard ─────────────────────────────────────────────────────

def test_load_guard_refuses_low_free_memory():
    try:
        LT.memory_guard("small", free_gb_probe=lambda: 3.0)
        check("guard refuses free 3.0 < needed 3.5", False)
    except LT.LyricTimingError as e:
        check("guard refuses free 3.0 < needed 3.5",
              e.code == "LOCAL_MODEL_LOAD_REFUSED", e.code)
    try:
        LT.memory_guard("medium", free_gb_probe=lambda: 3.49)
        check("guard refuses medium at 3.49", False)
    except LT.LyricTimingError as e:
        check("guard refuses medium at 3.49", e.code == "LOCAL_MODEL_LOAD_REFUSED")
    okd = LT.memory_guard("small", free_gb_probe=lambda: 3.5)
    check("guard passes exactly at needed",
          okd["checked"] is True and okd["needed_gb"] == 3.5, okd)
    try:
        LT.memory_guard("small", free_gb_probe=lambda: float("nan"))
        check("unreadable probe refuses", False)
    except LT.LyricTimingError as e:
        check("unreadable probe refuses", e.code == "LOCAL_MODEL_LOAD_REFUSED")
    try:
        def boom():
            raise OSError("vm_stat gone")
        LT.memory_guard(free_gb_probe=boom)
        check("raising probe refuses", False)
    except LT.LyricTimingError as e:
        check("raising probe refuses", e.code == "LOCAL_MODEL_LOAD_REFUSED")


def test_load_guard_numbers_match_lane_size():
    """Guard reuses lane_size's Part D numbers (one place), per the task."""
    ls = sys.modules.get("lane_size")
    check("guard reserve = lane_size RESERVE_GB (2.0)",
          LT.LOCAL_MODEL_RESERVE_GB == 2.0
          and (ls is None or ls.DEFAULTS["RESERVE_GB"] == 2.0))
    check("guard headroom = lane_size GB_PER_AGENT (1.5)",
          LT.LOCAL_MODEL_HEADROOM_GB == 1.5)


def test_guard_reads_live_lane_size():
    """When lane_size is importable, the guard's real probe answers a number
    (the instrument works, not just the mock)."""
    val = LT._free_ram_gb()
    check("live probe answers GB on this box",
          val == val and val > 0, "got %r" % val)


def test_tier2_blocked_when_guard_refuses():
    """End-to-end: low memory -> tier 2 never loads a model, chain fails
    closed (no crash past the guard)."""
    counter = {"loads": 0}
    loader = make_fake_loader(counter)

    def probe():
        raise LT.LyricTimingError("LOCAL_MODEL_LOAD_REFUSED", "free 2 GB")
    session = LT.WhisperSession(loader=loader, free_gb_probe=probe)
    got = LT.provide_word_timings(dict(TRACK), dispatcher=fail_dispatch,
                                  whisper_session=session)
    check("guard refusal stops tier 2 (fail-closed result)", got["ok"] is False)
    check("guard refusal counted ZERO real loads", counter["loads"] == 0)


# ── 5. scan rule: planted run-folder whisper script detected ────────────────

SCAN = os.path.abspath(os.path.join(
    HERE, os.pardir, os.pardir, "qc-no-local-asr.sh"))


def run_scan(env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    r = subprocess.run(["bash", SCAN], env=env, capture_output=True,
                       text=True, timeout=60)
    return r


def test_scan_detects_planted_whisper_script():
    tmp = make_tmp()
    runx = os.path.join(tmp, "run-a")
    os.makedirs(runx, exist_ok=True)
    with open(os.path.join(runx, "asr1.py"), "w", encoding="utf-8") as f:
        f.write('import whisper\nmodel = whisper.load("medium.en")\n')
    r = run_scan({"DRAMA75_CORE": CORE, "DRAMA75_RUN_DIRS": runx})
    check("planted run-folder whisper script -> exit 2", r.returncode == 2,
          "rc=%s out=%s err=%s" % (r.returncode, r.stdout[-200:],
                                   r.stderr[-300:]))
    check("planted offender named in output", "asr1.py" in r.stderr)


def test_scan_permits_faster_whisper_only_in_module():
    r = run_scan({"DRAMA75_CORE": CORE})
    check("scan clean on this tree (module is the only faster_whisper)",
          r.returncode == 0,
          "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))
    tmp = make_tmp()
    core2 = os.path.join(tmp, "core")
    shutil.copytree(CORE, core2)
    os.makedirs(os.path.join(core2, "audio_c3"), exist_ok=True)
    with open(os.path.join(core2, "audio_c3", "second.py"), "w",
              encoding="utf-8") as f:
        f.write("from faster_whisper import WhisperModel\n")
    r2 = run_scan({"DRAMA75_CORE": core2})
    check("second faster_whisper importer in core -> exit 2",
          r2.returncode == 2, "rc=%s err=%s" % (r2.returncode, r2.stderr[-200:]))


def test_scan_banned_surface_in_core():
    tmp = make_tmp()
    core2 = os.path.join(tmp, "core")
    shutil.copytree(CORE, core2)
    with open(os.path.join(core2, "bad.py"), "w", encoding="utf-8") as f:
        f.write("import whisper\n")
    r = run_scan({"DRAMA75_CORE": core2})
    check("core 'import whisper' -> exit 2", r.returncode == 2)
    check("offender path named", "bad.py" in r.stderr)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    test_tier1_returns_suno_alignment_no_local_loads()
    test_tier1_hint_skips_dispatch()
    test_tier1_words_shape_exact()
    test_tier2_forced_failure_exactly_one_load_multi_track()
    test_tier2_multi_track_one_session_counts_one_load()
    test_tier2_never_openai_whisper_loader()
    test_tier2_size_guard()
    test_tier3_fires_only_after_both_fail_and_cites_client_key()
    test_tier3_no_cloud_wired_reports_chain()
    test_tier3_refuses_operator_keys()
    test_tier3_word_timestamps_from_provider()
    test_load_guard_refuses_low_free_memory()
    test_load_guard_numbers_match_lane_size()
    test_guard_reads_live_lane_size()
    test_tier2_blocked_when_guard_refuses()
    test_scan_detects_planted_whisper_script()
    test_scan_permits_faster_whisper_only_in_module()
    test_scan_banned_surface_in_core()
    print("\n%d passed, %d failed" % (len(PASSES), len(FAILS)))
    if FAILS:
        print("FAILED:", ", ".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())