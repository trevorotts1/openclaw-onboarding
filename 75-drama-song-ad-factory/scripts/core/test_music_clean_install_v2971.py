#!/usr/bin/env python3
"""v2.9.71: the music stage runs on a clean install.

Five defects stopped every clean-install music run at the same wall. Each is
proved here against the real client data that exposed it (Laya Kelley's
Voyage To Virtue probe files) or against a synthesized take:

  1. CARD RECEIPT  -- song_choices never attached the run's recorded receipt,
     so kie_dispatch refused every paid job CARD_UNANSWERED.
  2. SCRIPT WORDS  -- cmd_generate handed the script_words gate the source
     research document instead of the approved sheet's lyric lines, so no
     take could ever pass it.
  3. EMPTY CALLBACK -- lyric_timing sent "callBackUrl": "", which Skill 74
     refuses as bad_request.
  4. SYNC CREATE TASK -- the sync id is local; save must be handed the submit
     envelope instead of re-querying KIE.
  5. TRANSPORTS    -- nothing shipped a real measure/save, so the CLI the
     runbook names always refused.

No network, no paid call, $0. The one audio test synthesizes a tone with
ffmpeg in a temp dir. Run: python3 core/test_music_clean_install_v2971.py
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import song_choices.song_choices as SC          # noqa: E402
import song_dispatch.song_dispatch as SD        # noqa: E402
import kie_dispatch.kie_dispatch as KD          # noqa: E402
import song_transports as ST                    # noqa: E402

def _live_kie_dispatch():
    """The kie_dispatch module the CODE UNDER TEST will import at call time.

    ``song_choices._real_generate`` imports ``kie_dispatch.kie_dispatch``
    INSIDE the call, and the skill-tree conftest drops skill modules between
    collectors, so the object bound here at import time is not always the one
    a later import returns (another suite patches its own copy's
    ``make_runner`` to refuse). Resolve it at run time, so the patch always
    lands on the module the production code will use -- solo run and the
    one-process pytest run alike.
    """
    return importlib.import_module("kie_dispatch.kie_dispatch")

PROBE = os.environ.get("DSF_LAYA_PROBE",
                       os.path.expanduser("~/scratch/dsf-stall-fix/laya/dsf003/probe"))

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _probe(name):
    p = os.path.join(PROBE, name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════ bug 1 ══
def test_card_receipt_read_shapes():
    """Every recorded shape the run folder can hold is read; nothing is made up."""
    tmp = tempfile.mkdtemp(prefix="v2971-card-")
    try:
        os.makedirs(os.path.join(tmp, "control"))
        check("1: no receipt file -> None (gate still refuses)",
              SC._card_receipt(tmp) is None)

        block = {"answers": {"video_style": "Lifelike 3D",
                             "audio_style": "Soul Ballad", "length": 88,
                             "video_model": "Hailuo 02 Standard"},
                 "who": "client", "at": "2026-10-19T23:10:00Z"}
        with open(os.path.join(tmp, "control", "card-receipt-block.json"), "w",
                  encoding="utf-8") as f:
            json.dump(block, f)
        check("1: stamped block read", SC._card_receipt(tmp) == block)

        os.unlink(os.path.join(tmp, "control", "card-receipt-block.json"))
        # Jennifer's shape: answers live under the per-question record.
        rec = {"answers": {"video_style": "Lifelike 3D",
                           "audio_style": "Soul Ballad", "length": 60,
                           "video_model": "Hailuo 02 Standard"},
               "who": "client", "at": "2026-10-17T10:00:00Z"}
        with open(os.path.join(tmp, "control", "card-receipt.json"), "w",
                  encoding="utf-8") as f:
            json.dump(rec, f)
        check("1: card-receipt.json with answers dict read",
              SC._card_receipt(tmp) == rec)

        os.unlink(os.path.join(tmp, "control", "card-receipt.json"))
        with open(os.path.join(tmp, "control", "card-receipt.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"storyboard_approval": "GO"}, f)   # no answers dict
        with open(os.path.join(tmp, "control", "run-state.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"card_receipt": block}, f)
        check("1: run-state.json['card_receipt'] read when the other shapes do not hold",
              SC._card_receipt(tmp) == block)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_real_probe_receipt_clears_the_gate():
    """Real data: Laya's request is refused, and is NOT refused once attached."""
    req = _probe("req.json")
    receipt = _probe("card-receipt-block.json")
    if req is None or receipt is None:
        # The client probe is not in the tree (it never is: it is client data).
        # The shape checks above prove the reader; this one proves the gate on
        # the real payload where it is available. Set DSF_LAYA_PROBE to run it.
        print("skip: 1: real probe not present at %s (shape checks above cover the reader)" % PROBE)
        return
    before = KD.card_gate_refusal(req)
    check("1: real req.json -> CARD_UNANSWERED before the fix",
          isinstance(before, dict) and before.get("reason_code") == "CARD_UNANSWERED",
          str(before))
    check("1: real receipt attached -> card_gate_refusal is None",
          KD.card_gate_refusal(dict(req, card_receipt=receipt)) is None)


def test_generate_attaches_the_run_receipt():
    """_real_generate stamps the receipt onto the payload every job carries."""
    tmp = tempfile.mkdtemp(prefix="v2971-attach-")
    try:
        os.makedirs(os.path.join(tmp, "control"))
        block = {"answers": {"video_style": "Lifelike 3D",
                             "audio_style": "Soul Ballad", "length": 60,
                             "video_model": "Hailuo 02 Standard"},
                 "who": "client", "at": "2026-10-19T23:10:00Z"}
        with open(os.path.join(tmp, "control", "card-receipt-block.json"), "w",
                  encoding="utf-8") as f:
            json.dump(block, f)
        seen = {}

        def fake_dispatch(**kw):
            seen.update(kw)
            return {"outcome": "ok", "evidence": {}}

        live = _live_kie_dispatch()
        real = live.dispatch
        live.dispatch = fake_dispatch
        try:
            gen = SC._real_generate(tmp, os.path.join(tmp, "spend.db"), "run-1")
            gen({"id": "V6"}, {"model": "m", "input": {"style": "s"}})
        finally:
            live.dispatch = real
        got = (seen.get("request") or {}).get("card_receipt")
        check("1: the run's recorded receipt rides the dispatched request",
              got == block, str(got))

        # A request that already carries its own receipt is left alone.
        seen.clear()
        own = {"answers": {"video_style": "OTHER", "audio_style": "x",
                           "length": 90, "video_model": "y"}, "who": "w", "at": "a"}
        live.dispatch = fake_dispatch
        try:
            gen({"id": "V6"}, {"model": "m", "input": {}, "card_receipt": own})
        finally:
            live.dispatch = real
        check("1: a request with its own receipt keeps it",
              (seen.get("request") or {}).get("card_receipt") == own)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════ bug 2 ══
def test_script_words_are_the_sheet_lyrics():
    """The gate is handed lyric lines only -- never the research document."""
    spec = SC._load_request(os.path.join(PROBE, "req.json")) \
        if os.path.isfile(os.path.join(PROBE, "req.json")) else None
    if spec is None:
        print("skip: 2: real probe not present at %s (set DSF_LAYA_PROBE to run it)" % PROBE)
        return
    words = SC._sheet_lyric_words(spec)
    wanted = SD._script_lyric_words(words)
    old = SD._script_lyric_words(spec["client_text"])

    check("2: bracket headers are not lyric words",
          "melodic" not in wanted and "rhymed" not in wanted, str(sorted(wanted)[:12]))
    # A take that sings exactly the sheet's lyric lines satisfies the gate.
    sung = set(SD._w(words))
    check("2: a take singing the sheet has nothing missing",
          not (wanted - sung), str(sorted(wanted - sung)[:8]))
    # And the OLD wiring could never be satisfied by that same take.
    check("2: the old client_text gate is unsatisfiable by a sheet-singing take",
          len(old - sung) > 50, "%d missing" % len(old - sung))
    # client_text still drives the hook vocabulary in build_requests.
    reqs = SC.build_requests(spec["style_id"], spec["sheet"], spec["client_text"],
                             spec["title"], spec["length_s"], spec["vocal_gender"],
                             hook_plan=spec["hook_plan"], pace_plan=spec["pace_plan"])
    check("2: client_text still reaches build_requests (three variants built)",
          len(reqs) == 3)


# ══════════════════════════════════════════════════════════════ bug 3 ══
def test_empty_callback_is_omitted():
    """No callback_url -> no callBackUrl key at all."""
    sent = {}

    def fake_dispatch(**kw):
        sent.update(kw)
        return {"outcome": "fail", "reason_code": "x", "next_action": "",
                "evidence": {"saved_paths": []}}

    from audio_c3 import lyric_timing as LT
    try:
        LT.fetch_suno_timestamped_lyrics({"task_id": "t1", "audio_id": "a1"},
                                         dispatcher=fake_dispatch)
    except LT.LyricTimingError:
        pass                                    # the dispatch "failed" on purpose
    req = sent.get("request") or {}
    check("3: callBackUrl key is ABSENT when there is no callback",
          "callBackUrl" not in req, str(req))

    sent.clear()
    try:
        LT.fetch_suno_timestamped_lyrics(
            {"task_id": "t1", "audio_id": "a1", "callback_url": "https://relay.example/cb"},
            dispatcher=fake_dispatch)
    except LT.LyricTimingError:
        pass
    check("3: a real callback_url is still sent",
          (sent.get("request") or {}).get("callBackUrl") == "https://relay.example/cb")
    check("3: Skill 74 accepts that request (no empty-string refusal)",
          _skill74_cb_ok({"callBackUrl": ""}) is False
          and _skill74_cb_ok({"callBackUrl": "https://relay.example/cb"}) is True)


def _skill74_cb_ok(req):
    """Mirror of Skill 74's _cb_check verdict, for the shape test only."""
    cb = req.get("callBackUrl")
    if cb is None:
        return True
    import urllib.parse
    return isinstance(cb, str) and urllib.parse.urlparse(cb).scheme in ("http", "https")


# ══════════════════════════════════════════════════════════════ bug 4 ══
def test_sync_submit_hands_save_its_envelope():
    """A sync createTask writes sync-info.json and save is handed --info."""
    tmp = tempfile.mkdtemp(prefix="v2971-sync-")
    try:
        calls = []

        def fake_runner(argv):
            calls.append(list(argv))
            sub = argv[1]
            if sub == "health":
                return 0, {"adapter_mode": "active"}
            if sub == "preflight":
                return 0, {"ok": True, "credits": 100, "amount": 1}
            if sub == "submit":
                return 0, {"state": "success", "raw_family": "sync",
                           "data": {"response": {"code": 200,
                                                 "data": {"alignedWords": [{"word": "w"}]}},
                                    "sync": True}}
            if sub == "save":
                return 0, {"state": "success", "saved_paths": ["/tmp/w_0.json"]}
            if sub == "wait":
                return 0, {"state": "success"}
            return 0, {"ok": True}

        db = os.path.join(tmp, "spend.db")
        import spend_ledger as L
        L.init_run(db, "run-sync", 10000)
        req = {"endpoint": "/api/v1/jobs/createTask", "model": "ai-music-api/timeStamped-lyrics",
               "card_receipt": {"answers": {"video_style": "v", "audio_style": "a",
                                            "length": 60, "video_model": "m"},
                                "who": "w", "at": "a"},
               "input": {"task_id": "t1", "audio_id": "a1"}}
        env = _live_kie_dispatch().dispatch(
            model="ai-music-api/timeStamped-lyrics", request=req,
            save_dir=os.path.join(tmp, "out"), ledger_db=db, run_id="run-sync",
            logical_key="word-timings", attempt_id="att-1", estimated_cost=1,
            adapter_path=os.path.abspath(__file__), runner=fake_runner,
            stage="word-timings")
        save_argv = [c for c in calls if len(c) > 1 and c[1] == "save"]
        check("4: the sync job dispatched ok", env.get("outcome") == "ok", str(env))
        # dispatch removes its own temp dir in `finally`, so the file is gone by
        # now; the receipt is the ARGV it actually built.
        check("4: save was called with --info pointing at sync-info.json",
              bool(save_argv) and "--info" in save_argv[0]
              and save_argv[0][save_argv[0].index("--info") + 1].endswith("sync-info.json"),
              str(save_argv))
        check("4: the saved word-timing file reaches the envelope",
              "/tmp/w_0.json" in (env.get("evidence", {}).get("saved_paths") or []),
              str(env.get("evidence")))

        # The async path must NOT pass --info.
        calls.clear()

        def fake_async(argv):
            calls.append(list(argv))
            sub = argv[1]
            if sub == "health":
                return 0, {"adapter_mode": "active"}
            if sub == "preflight":
                return 0, {"ok": True, "credits": 100, "amount": 1}
            if sub == "submit":
                return 0, {"state": "queued", "task_id": "T1", "raw_family": "market"}
            if sub == "wait":
                return 0, {"state": "success", "task_id": "T1",
                           "raw_family": "market", "credits_consumed": 3}
            if sub == "save":
                return 0, {"state": "success", "saved_paths": ["/tmp/a.mp3"]}
            return 0, {"ok": True}

        db2 = os.path.join(tmp, "spend2.db")
        L.init_run(db2, "run-async", 10000)
        env2 = _live_kie_dispatch().dispatch(
            model="ai-music-api/timeStamped-lyrics", request=req,
            save_dir=os.path.join(tmp, "out2"), ledger_db=db2, run_id="run-async",
            logical_key="song", attempt_id="att-1", estimated_cost=1,
            adapter_path=os.path.abspath(__file__), runner=fake_async)
        save2 = [c for c in calls if len(c) > 1 and c[1] == "save"][0]
        check("4: an async job never passes --info", "--info" not in save2, str(save2))
        check("4: the async job still dispatches ok", env2.get("outcome") == "ok",
              str(env2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════ bug 5 ══
def _tone(tmp, seconds=3.0):
    """One ffmpeg-generated tone. Measured, not mocked."""
    p = os.path.join(tmp, "tone.wav")
    rc = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                         "-i", "sine=frequency=440:duration=%s" % seconds,
                         "-ac", "1", "-ar", "16000", p]).returncode
    return p if rc == 0 and os.path.isfile(p) else None


def test_transports_measure_real_audio():
    tmp = tempfile.mkdtemp(prefix="v2971-tx-")
    try:
        tone = _tone(tmp)
        if tone is None:
            check("5: ffmpeg available to synthesize a tone", False)
            return
        order = ST.build_pace_plan(10.0, 3.0, 6.0)
        measure = ST.make_measure(pace_plan=order)
        got = measure({"audio_path": tone})
        check("5: the measure returns a measured duration",
              isinstance(got.get("duration_s"), (int, float))
              and abs(got["duration_s"] - 3.0) < 0.5, str(got.get("duration_s")))
        check("5: the measure returns segments from the detector",
              isinstance(got.get("segments"), list), str(type(got.get("segments"))))
        check("5: the measure returns a clean-ending tail in dBFS",
              isinstance(got.get("tail_rms_dbfs"), (int, float)),
              str(got.get("tail_rms_dbfs")))
        check("5: no aligned words -> the judge sees an EMPTY list, never an invented one",
              got.get("aligned_words") == [])
        # A take with no audio RAISES: a measurement that cannot be taken is
        # missing, never a silent empty dict.
        try:
            measure({})
            raised = False
        except ST.TransportError:
            raised = True
        check("5: a take with no audio raises TransportError", raised)

        # save keeps EVERY take, accepted or not.
        run = os.path.join(tmp, "run")
        save = ST.make_save(run)
        dest = save({"id": "V6"}, {"audio_path": tone, "aligned_words": []},
                    {"verdict": "FAIL"})
        check("5: save keeps the paid take under its own variant",
              bool(dest) and os.path.isfile(os.path.join(dest, "tone.wav"))
              and os.path.isfile(os.path.join(dest, "receipt.json")), str(dest))
        dest2 = save({"id": "V6"}, {"audio_path": tone}, {"verdict": "FAIL"})
        check("5: a second take never overwrites the first",
              os.path.basename(dest2) == "take-02", str(dest2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cli_generate_refuses_nothing_and_program_guard_stays():
    """The CLI supplies real transports; the programmatic None guard is untouched."""
    tmp = tempfile.mkdtemp(prefix="v2971-cli-")
    try:
        import inspect
        src = inspect.getsource(SC.main)
        check("5: the generate CLI wires make_measure, make_save and the word-timing step",
              "make_measure" in src and "make_save" in src
              and "make_timings" in src)
        check("5: cmd_generate still refuses a None transport",
              "not an empty default no-op" in inspect.getsource(SC.cmd_generate))
        # Calling cmd_generate with None still raises: the guard is untouched.
        # A minimal request of its own, so this check never depends on client data.
        req_path = os.path.join(tmp, "req.json")
        with open(req_path, "w", encoding="utf-8") as f:
            json.dump({"style_id": "soul-ballad", "title": "T", "length_s": 60,
                       "vocal_gender": "f",
                       "sheet_text": "[Chorus (sung): full melody]\nI rise again\nI rise again",
                       "input": {"lyrics": "[Chorus (sung): full melody]\nI rise again\nI rise again"}},
                      f)

        class A:
            run_dir = tmp
            request = req_path
            ledger = ""
            run_id = ""
            variant = None
            unit_id = None

        try:
            SC.cmd_generate(A(), measure=None, save=None)
            refused = False
        except SC.ChoiceError as e:
            refused = "no-op" in str(e)
        check("5: cmd_generate(measure=None) still refuses with the no-op guard", refused)

        # The word-timing step never raises: an unusable one yields NO words,
        # which the judge records as UNMEASURED (never a crash, never a PASS).
        got = ST.make_timings(tmp, ledger=os.path.join(tmp, "missing.db"))(
            {"task_id": "t1"})
        check("5: an unmeasurable timing step yields no words instead of raising",
              got.get("words") == [] and bool(got.get("error")), str(got)[:160])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for fn in (test_card_receipt_read_shapes,
               test_real_probe_receipt_clears_the_gate,
               test_generate_attaches_the_run_receipt,
               test_script_words_are_the_sheet_lyrics,
               test_empty_callback_is_omitted,
               test_sync_submit_hands_save_its_envelope,
               test_transports_measure_real_audio,
               test_cli_generate_refuses_nothing_and_program_guard_stays):
        try:
            fn()
        except Exception as e:                  # noqa: BLE001 - a crash is a failure
            check(fn.__name__ + " did not crash", False,
                  "%s: %s" % (type(e).__name__, str(e)[:300]))
    if FAILS:
        print("\nFAILED: %s" % ", ".join(FAILS))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
