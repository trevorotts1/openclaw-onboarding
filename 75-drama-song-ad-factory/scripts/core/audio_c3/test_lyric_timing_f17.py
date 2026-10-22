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
    way the real 'faster_whisper' import does. The CALL SHAPE IS the real
    supported faster-whisper contract (D18): loader(size, compute) -> model;
    model.transcribe(path, word_timestamps=True) -> (segments, info); each
    segment object carries .words of word objects with word/start/end
    (probability when the source reports it).
    """
    class _Word:
        def __init__(self, w, s, e, p):
            self.word, self.start, self.end, self.probability = w, s, e, p

    class _Seg:
        def __init__(self, words):
            self.words = words

    class FakeModel:
        def transcribe(self, path, word_timestamps=False):
            assert word_timestamps is True, "word_timestamps=True is the contract"
            counter.setdefault("paths", []).append(path)
            segs = [_Seg([_Word(w["word"], float(w["startS"]),
                                float(w["endS"]), 0.93)
                          for w in ALIGNED_DOC["alignedWords"]])]
            return iter(segs), object()

    def fake_loader(size, compute):
        counter["loads"] += 1
        counter["sizes"].append((size, compute))
        return FakeModel()
    fake_loader.__name__ = "fake_loader"          # no whisper surface
    fake_loader.__module__ = "test_lyric_timing_f17"
    return fake_loader


def make_audio(name="take.wav", content=b"RIFF....WAVEfmt fake-audio"):
    """An actual audio file on disk -- the real audio-path handoff."""
    p = os.path.join(make_tmp(), name)
    with open(p, "wb") as f:
        f.write(content)
    return p


def test_tier2_forced_failure_exactly_one_load_multi_track():
    counter = {"loads": 0, "sizes": []}
    session = LT.WhisperSession(loader=make_fake_loader(counter),
                                free_gb_probe=lambda: 16.0)
    got = LT.provide_word_timings(dict(TRACK, audio_path=make_audio()),
                                  dispatcher=fail_dispatch,
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
    tracks = [dict(TRACK, audio_path=make_audio("first.wav")),
              {"task_id": "t2", "audio_id": "a2",
               "audio_path": make_audio("second.wav")}]
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
    shutil.copytree(CORE, core2,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
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
    shutil.copytree(CORE, core2,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    with open(os.path.join(core2, "bad.py"), "w", encoding="utf-8") as f:
        f.write("import whisper\n")
    r = run_scan({"DRAMA75_CORE": core2})
    check("core 'import whisper' -> exit 2", r.returncode == 2)
    check("offender path named", "bad.py" in r.stderr)


# ── 6. D18 counterexample: production fallback API, no injected test loader ─

def test_no_loader_counterexample_production_api():
    """The 17.4 counterexample: local ASR fallback with sufficient mocked
    resource allowance and NO injected test loader. Before: LyricTimingError
    "no faster-whisper loader wired". Now: the production loader runs the
    real supported faster-whisper API on an actual audio path, producing
    word conversions under ONE governed load."""
    import types
    audio = make_audio("counterexample.wav")
    seen = {}

    class _Word:
        def __init__(self, w, s, e, p):
            self.word, self.start, self.end, self.probability = w, s, e, p

    class _Seg:
        def __init__(self, words):
            self.words = words

    class _Model:
        def transcribe(self, path, word_timestamps=False):
            seen["call"] = (path, word_timestamps)
            return iter([_Seg([_Word("power", 0.0, 0.42, 0.97),
                               _Word("climb", 0.75, 1.3, 0.91)])]), object()

    def fake_whisper_model(size, device="cpu", compute_type="int8"):
        seen["load"] = (size, device, compute_type)
        return _Model()

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = fake_whisper_model
    saved_mod = sys.modules.get("faster_whisper")
    sys.modules["faster_whisper"] = mod
    try:
        session = LT.WhisperSession(free_gb_probe=lambda: 16.0)  # NO loader
        tx = session.transcribe_all([{"task_id": "t1", "audio_id": "a1",
                                      "audio_path": audio}])
        words = session.words_of(tx[0])
    finally:
        if saved_mod is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = saved_mod
    check("no-loader counterexample runs", True)
    check("production loader used the real load contract",
          seen.get("load") == ("small", "cpu", "int8"), seen.get("load"))
    check("real call contract: transcribe(path, word_timestamps=True)",
          seen.get("call") == (audio, True), seen.get("call"))
    check("word conversions produced",
          [w["word"] for w in words] == ["power", "climb"], words)
    check("word rows carry word/start/end(+probability)",
          set(words[0]) == {"word", "start", "end", "probability"},
          sorted(words[0]))
    check("exactly ONE governed load", session.loads == 1,
          "loads=%s" % session.loads)


# ── 7. D25: each failure class keeps its causal chain to the saved record ──

def _trigger(name):
    """(error, exc) for one named failure class, via the real code paths."""
    if name == "missing-loader":
        saved = LT.WHISPER_LOADER_FACTORY
        LT.WHISPER_LOADER_FACTORY = None
        try:
            LT.WhisperSession(free_gb_probe=lambda: 16.0).transcribe_all(
                [{"audio_path": make_audio()}])
        finally:
            LT.WHISPER_LOADER_FACTORY = saved
    elif name == "missing-dependency":
        saved = sys.modules.pop("faster_whisper", None)
        sys.modules["faster_whisper"] = None  # forces ImportError
        try:
            LT.WhisperSession(free_gb_probe=lambda: 16.0).transcribe_all(
                [{"audio_path": make_audio()}])
        finally:
            sys.modules.pop("faster_whisper", None)
            if saved is not None:
                sys.modules["faster_whisper"] = saved
    elif name == "low-memory":
        LT.memory_guard("small", free_gb_probe=lambda: 1.0)
    elif name == "unreadable-resource-telemetry":
        LT.memory_guard("small", free_gb_probe=lambda: float("nan"))
    elif name == "unwired-loader":
        LT.WhisperSession(free_gb_probe=lambda: 16.0,
                          use_default_loader=False).transcribe_all(
            [{"audio_path": make_audio()}])
    elif name == "model-load-failure":
        def boom(size, compute):
            raise OSError("corrupt model shard")
        boom.__name__, boom.__module__ = "boom", "test_lyric_timing_f17"
        LT.WhisperSession(loader=boom,
                          free_gb_probe=lambda: 16.0).transcribe_all(
            [{"audio_path": make_audio()}])
    elif name == "bad-call-signature":
        class NoTranscribe:
            pass
        bad = lambda s, c: NoTranscribe()  # noqa: E731
        bad.__name__, bad.__module__ = "bad", "test_lyric_timing_f17"
        LT.WhisperSession(loader=bad,
                          free_gb_probe=lambda: 16.0).transcribe_all(
            [{"audio_path": make_audio()}])
    elif name == "missing-audio-path":
        LT.WhisperSession(loader=make_fake_loader({"loads": 0, "sizes": []}),
                          free_gb_probe=lambda: 16.0).transcribe_all(
            [{"task_id": "t1"}])
    elif name == "unavailable-timestamps":
        class _Seg:
            words = None

        class QuietModel:
            def transcribe(self, path, word_timestamps=False):
                return iter([_Seg()]), object()

        def quiet(size, compute):
            return QuietModel()
        quiet.__name__, quiet.__module__ = "quiet", "test_lyric_timing_f17"
        sess = LT.WhisperSession(loader=quiet, free_gb_probe=lambda: 16.0)
        got = LT.provide_word_timings(
            {"task_id": "t1", "audio_path": make_audio()},
            dispatcher=fail_dispatch, whisper_session=sess)
        assert got["ok"] is False and got["failure_class"] == name, got
        # surface the boundary envelope the consumer would save
        raise LT.LyricTimingError(got["error"]["code"], got["error"]["detail"],
                                  got["failure_class"])
    elif name == "malformed-qc-input":
        LT.words_from_segments([{"words": [{"word": "x"}]}])
    else:
        raise AssertionError(name)


def test_error_classes_distinct_causal_chain_saved_record():
    tmp = make_tmp()
    want = ["missing-loader", "missing-dependency", "low-memory",
            "unreadable-resource-telemetry", "unwired-loader",
            "model-load-failure", "bad-call-signature", "missing-audio-path",
            "unavailable-timestamps", "malformed-qc-input"]
    seen = []
    for name in want:
        try:
            _trigger(name)
            check("%s refused" % name, False, "no error raised")
            continue
        except AssertionError:
            raise
        except LT.LyricTimingError as e:
            err = e
        check("%s distinct failure_class" % name,
              err.failure_class == name, err.failure_class)
        seen.append(err.failure_class)
        env = err.envelope()
        check("%s envelope keeps code+class" % name,
              env["code"] == err.code and env["failure_class"] == name, env)
        rec = LT.save_error_record(os.path.join(tmp, "%s.json" % name), err)
        back = LT.read_error_record(os.path.join(tmp, "%s.json" % name))
        check("%s saved record keeps causal chain" % name,
              back.get("cause") == rec.get("cause")
              and back["failure_class"] == name
              and back["code"] == err.code, back)
    check("all ten failure classes distinct",
          len(set(seen)) == 10 and sorted(seen) == sorted(want), seen)


def test_error_detail_bounded_and_redacted():
    secret = "api_key=sk-supersecrettoken1234567890"
    err = LT.LyricTimingError("WHISPER_TRANSCRIBE_FAILED",
                              "boom %s %s" % (secret, "x" * 500),
                              LT.CLASS_TRANSCRIBE_FAILED)
    env = err.envelope()
    check("diagnostic bounded", len(env["detail"]) <= 220, len(env["detail"]))
    check("diagnostic redacted", "sk-supersecrettoken" not in env["detail"],
          env["detail"])
    check("cause chain keeps error_type",
          env.get("cause") is None or "error_type" in env["cause"])


def test_cause_chain_crosses_boundaries():
    inner = LT.LyricTimingError(LT.CLASS_CODE[LT.CLASS_DEPENDENCY_MISSING],
                                "No module named 'faster_whisper'",
                                LT.CLASS_DEPENDENCY_MISSING)
    mid = LT.LyricTimingError(LT.CLASS_CODE[LT.CLASS_MODEL_LOAD_FAILED],
                              "load failed", LT.CLASS_MODEL_LOAD_FAILED,
                              cause=inner)
    tmp = make_tmp()
    LT.save_error_record(os.path.join(tmp, "chain.json"), mid)
    back = LT.read_error_record(os.path.join(tmp, "chain.json"))
    check("two-level chain survives the saved record",
          back["cause"]["failure_class"] == LT.CLASS_DEPENDENCY_MISSING
          and back["cause"].get("cause") is None
          and bool(back["cause"].get("detail")), back)
    # boundary codes: guard umbrella surfaces the distinct class code
    guard_err = LT.LyricTimingError("LOCAL_MODEL_LOAD_REFUSED", "free 1 GB",
                                    LT.CLASS_LOW_MEMORY)
    check("guard boundary code is distinct, umbrella kept on the error",
          guard_err.code == "LOCAL_MODEL_LOAD_REFUSED"
          and guard_err.boundary_code() == "LOCAL_MODEL_LOW_MEMORY")


# ── 8. D26: non-generating operations ──────────────────────────────────────

def test_missing_fallback_never_regenerates_paid_music():
    """All tiers fail (fallback missing) -> zero music-generation calls, the
    dispatcher only ever saw the timestamped-lyrics ANALYSIS model."""
    calls = []

    def spy_dispatcher(**kw):
        calls.append(kw)
        return fail_dispatch(**kw)

    class DeadSession(LT.WhisperSession):
        def transcribe_all(self, tracks):
            raise LT.LyricTimingError(
                LT.CLASS_CODE[LT.CLASS_UNWIRED_LOADER], "nothing wired",
                LT.CLASS_UNWIRED_LOADER)

    got = LT.provide_word_timings({"task_id": "t1", "audio_id": "a1"},
                                  dispatcher=spy_dispatcher,
                                  whisper_session=DeadSession(loader=None))
    check("missing fallback fails closed", got["ok"] is False)
    check("failure attests zero music-generation calls",
          got["counts"]["music_generation_calls"] == 0, got["counts"])
    check("dispatcher only ever saw the analysis model",
          all(c["model"] == "ai-music-api/timeStamped-lyrics" for c in calls),
          [c["model"] for c in calls])
    check("next_action recovers WITHOUT generation",
          "NO paid music was generated" in got["next_action"]
          and "regenerat" not in got["next_action"].lower(),
          got["next_action"])
    check("failure carries the typed envelope",
          got["error"]["failure_class"] == LT.CLASS_UNWIRED_LOADER
          and got["error_code"] == "WHISPER_LOADER_UNWIRED",
          (got.get("error_code"), got.get("failure_class")))


def test_remeasure_unchanged_hash_zero_generation_calls():
    audio = make_audio("remeasure.wav", b"RIFF....WAVE saved-take")
    before = LT.audio_sha256(audio)

    def spy_dispatcher(**kw):
        raise AssertionError("remeasure must never dispatch: %r"
                             % (kw.get("model"),))

    counter = {"loads": 0, "sizes": []}
    session = LT.WhisperSession(loader=make_fake_loader(counter),
                                free_gb_probe=lambda: 16.0)
    got = LT.remeasure_saved_audio(
        audio, record={"track": {"task_id": "t-suno", "audio_id": "a-suno"},
                       "transcription_provider": "suno (KIE timeStamped-lyrics)"},
        whisper_session=session, dispatcher=spy_dispatcher)
    check("remeasure produced current evidence",
          [w["word"] for w in got["words"]] == ["power", "in", "the", "climb"],
          got["words"])
    check("audio hash unchanged",
          got["audio"]["sha256_before"] == got["audio"]["sha256_after"]
          == before and got["audio"]["unchanged"] is True, got["audio"])
    check("remeasure zero music-generation calls",
          got["counts"]["music_generation_calls"] == 0
          and got["counts"]["paid_analysis_calls"] == 0, got["counts"])
    check("remeasure ONE governed load", got["local_model_loads"] == 1
          and session.loads == 1, session.loads)
    check("provider provenance preserved",
          got["provenance"]["task_id"] == "t-suno"
          and got["provenance"]["audio_id"] == "a-suno"
          and got["provenance"]["provider"], got["provenance"])


def test_rejudge_uses_saved_measurements_only():
    """Rejudging calls NO provider and loads NO model -- it takes neither a
    dispatcher nor a loader."""
    import inspect
    sig = inspect.signature(LT.rejudge_saved)
    check("rejudge takes no dispatcher/loader",
          "dispatcher" not in sig.parameters and "loader" not in sig.parameters,
          sorted(sig.parameters))
    high = LT.rejudge_saved({"words": [
        {"word": "power", "start": 0.0, "end": 0.42, "probability": 0.95}]})
    check("high confidence rejudges pass", high["verdict"] == "pass", high)
    low = LT.rejudge_saved({"words": [
        {"word": "power", "start": 0.0, "end": 0.42, "probability": 0.3}]})
    check("low confidence is needs-review, never a definite failure",
          low["verdict"] == "needs-review" and low["verdict"] != "fail",
          low)
    check("low confidence triggers bounded remeasure + independent review",
          {a["action"] for a in low["next_actions"]} >=
          {"remeasure", "independent-media-review"}
          and all(a.get("bounded") for a in low["next_actions"]
                  if a["action"] == "remeasure")
          and all(a.get("max_passes") == 1 for a in low["next_actions"]
                  if a["action"] == "remeasure"), low["next_actions"])
    empty = LT.rejudge_saved({"words": []})
    check("no measurement -> needs-remeasure, not creative failure",
          empty["verdict"] == "needs-remeasure", empty)
    inverted = LT.rejudge_saved({"words": [
        {"word": "power", "start": 1.4, "end": 0.4, "probability": 0.9}]})
    check("inverted span is a definite fail", inverted["verdict"] == "fail",
          inverted)
    check("rejudge results attest zero provider/generation calls",
          all(r["provider_calls"] == 0 and r["music_generation_calls"] == 0
              for r in (high, low, empty, inverted)))
    try:
        LT.rejudge_saved({"words": [{"word": "x"}]})
        check("malformed QC input refused", False)
    except LT.LyricTimingError as e:
        check("malformed QC input refused",
              e.code == "MALFORMED_QC_INPUT" and e.failure_class ==
              "malformed-qc-input", e.code)


def test_validate_migrate_read_records_shapes():
    good = {"words": [{"word": "power", "start": 0.0, "end": 0.42}],
            "source": "suno-timestamped-lyrics"}
    check("validate accepts a good record", LT.validate_record(good) is good)
    check("read_records: single object", len(LT.read_records(good)) == 1)
    check("read_records: valid list", len(LT.read_records([good, good])) == 2)
    check("read_records: empty list valid", LT.read_records([]) == [])
    check("read_records: records wrapper",
          len(LT.read_records({"records": [good]})) == 1)
    for bad in ("nope", None, 7):
        try:
            LT.read_records(bad)
            check("read_records rejects %r" % (bad,), False)
        except LT.LyricTimingError as e:
            check("read_records rejects %r" % (bad,),
                  e.code == "MALFORMED_QC_INPUT", e.code)
    try:
        LT.validate_record({"words": [{"word": "x"}]})
        check("validate names the missing key", False)
    except LT.LyricTimingError as e:
        check("validate names the missing key",
              "words[0]" in str(e) and "start" in str(e), str(e))
    legacy = {"schema_version": "blackceo.audio-c3/lyric-timing/v0",
              "words": [{"word": "power", "startS": 0.0, "endS": 0.42}],
              "performance_tags": ["soul"], "provider_envelope_absent": True}
    mig = LT.migrate_record(legacy)
    check("migrate maps startS/endS with values unchanged",
          mig["words"] == [{"word": "power", "start": 0.0, "end": 0.42}],
          mig["words"])
    check("migrate preserves approved/unknown fields",
          mig["performance_tags"] == ["soul"]
          and mig["provider_envelope_absent"] is True)
    check("migrate reports what changed",
          mig["migration"]["changed"] is True
          and mig["migration"]["semantic_differences"], mig["migration"])
    check("absent provider-envelope fields are not an error",
          "obsolete" not in str(mig).lower())
    conflict = LT.migrate_record({"words": [
        {"word": "power", "startS": 0.0, "endS": 0.42, "start": 9.9}]})
    check("conflicting keys reported for review",
          any("review" in s for s in
              conflict["migration"]["semantic_differences"]),
          conflict["migration"])


def test_reconcile_reports_hash_mismatch():
    audio = make_audio("reconcile.wav", b"RIFF....WAVE take-bytes")
    good = {"words": [{"word": "power", "start": 0.0, "end": 0.42}],
            "audio": {"path": audio, "sha256": LT.audio_sha256(audio)}}
    bad = {"words": [], "audio": {"path": audio, "sha256": "0" * 64}}
    res = LT.reconcile_records([good, bad])
    check("reconcile reports per-record status",
          [r["status"] for r in res["rows"]] == ["match", "mismatch"], res)
    check("reconcile counts mismatches", res["mismatches"] == 1, res)
    check("reconcile never generates",
          res["counts"]["music_generation_calls"] == 0)
    gone = LT.reconcile_records([{"audio": {"path": "/no/such/file.wav"}}])
    check("missing audio reported, not crashed",
          gone["rows"][0]["status"] in ("audio-missing", "no-audio-path"),
          gone)


def test_low_confidence_receipt_keeps_words_and_triggers_bounded_review():
    counter = {"loads": 0, "sizes": []}
    session = LT.WhisperSession(loader=make_fake_loader(counter),
                                free_gb_probe=lambda: 16.0)
    # fake loader reports probability 0.93 -> force low via a quiet model
    class _W:
        word, start, end, probability = "power", 0.0, 0.42, 0.25

    class _S:
        words = [_W()]

    class LowModel:
        def transcribe(self, path, word_timestamps=False):
            return iter([_S()]), object()

    def low_loader(size, compute):
        return LowModel()
    low_loader.__name__, low_loader.__module__ = "low_loader", \
        "test_lyric_timing_f17"
    sess = LT.WhisperSession(loader=low_loader, free_gb_probe=lambda: 16.0)
    got = LT.provide_word_timings({"task_id": "t1", "audio_path": make_audio()},
                                  dispatcher=fail_dispatch, whisper_session=sess)
    check("low confidence still measured (ok, words kept)",
          got["ok"] and got["timings"]["words"], got)
    check("low confidence flagged, not failed",
          got.get("low_confidence") is True and "ok" in got, got)
    check("low confidence triggers bounded recovery",
          {a["action"] for a in got["next_actions"]} >=
          {"remeasure", "independent-media-review"}, got.get("next_actions"))


# ── 9. CLI contract: a refusal stays a refusal ─────────────────────────────

def test_cli_non_generating_ops_exit_contract():
    tmp = make_tmp()
    good = os.path.join(tmp, "good.json")
    lowr = os.path.join(tmp, "low.json")
    badr = os.path.join(tmp, "bad.json")
    with open(good, "w", encoding="utf-8") as f:
        json.dump({"words": [{"word": "power", "start": 0.0, "end": 0.42,
                              "probability": 0.95}]}, f)
    with open(lowr, "w", encoding="utf-8") as f:
        json.dump({"words": [{"word": "power", "start": 0.0, "end": 0.42,
                              "probability": 0.1}]}, f)
    with open(badr, "w", encoding="utf-8") as f:
        json.dump({"words": [{"word": "power"}]}, f)
    mod_path = os.path.join(HERE, "lyric_timing.py")

    def run(*args):
        return subprocess.run([sys.executable, mod_path] + list(args),
                              capture_output=True, text=True, timeout=120)

    r = run("validate", good)
    check("cli validate good -> exit 0", r.returncode == 0, r.returncode)
    r = run("validate", badr)
    out = json.loads(r.stdout)
    check("cli validate malformed -> exit 5 refusal",
          r.returncode == 5 and out["ok"] is False
          and out["error_code"] == "MALFORMED_QC_INPUT",
          (r.returncode, out.get("error_code")))
    r = run("migrate", good)
    check("cli migrate -> exit 0", r.returncode == 0, r.returncode)
    r = run("rejudge", good)
    check("cli rejudge pass -> exit 0", r.returncode == 0, r.returncode)
    r = run("rejudge", lowr)
    out = json.loads(r.stdout)
    check("cli rejudge low-confidence -> exit 5 (refusal stays refusal)",
          r.returncode == 5 and out["rejudge"]["verdict"] == "needs-review",
          (r.returncode, out.get("rejudge")))
    r = run("remeasure", "--audio", "/no/such/file.wav")
    out = json.loads(r.stdout)
    check("cli remeasure missing audio -> exit 5 typed refusal",
          r.returncode == 5 and out["ok"] is False
          and out["error_code"] == "AUDIO_PATH_MISSING",
          (r.returncode, out.get("error_code")))
    check("cli failure envelope attests zero generation",
          out["counts"]["music_generation_calls"] == 0, out.get("counts"))


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
    test_no_loader_counterexample_production_api()
    test_error_classes_distinct_causal_chain_saved_record()
    test_error_detail_bounded_and_redacted()
    test_cause_chain_crosses_boundaries()
    test_missing_fallback_never_regenerates_paid_music()
    test_remeasure_unchanged_hash_zero_generation_calls()
    test_rejudge_uses_saved_measurements_only()
    test_validate_migrate_read_records_shapes()
    test_reconcile_reports_hash_mismatch()
    test_low_confidence_receipt_keeps_words_and_triggers_bounded_review()
    test_cli_non_generating_ops_exit_contract()
    print("\n%d passed, %d failed" % (len(PASSES), len(FAILS)))
    if FAILS:
        print("FAILED:", ", ".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())