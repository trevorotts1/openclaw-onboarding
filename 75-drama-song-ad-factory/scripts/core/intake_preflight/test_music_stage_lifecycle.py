#!/usr/bin/env python3
"""Music stage lifecycle self-check (factory.py `music`). Stdlib, temp dirs only,
no provider, no ledger. Run: python3 scripts/core/intake_preflight/test_music_stage_lifecycle.py

Proves the defect is closed: before this command nothing moved the music row out
of NOT_STARTED, so `next` could never reach continuity-bible however many songs
were bought."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))
import factory as F          # noqa: E402
import state_store as SS     # noqa: E402
from batch_mode.batch import STAGES  # noqa: E402
from test_production_process import confirmed_run, complete_stage, approve_script

RID = "eoe-test-60s"


def new_run(tmp, upto="music", *, song=False):
    run = Path(tempfile.mkdtemp(dir=tmp, prefix="music-")) / RID
    confirmed_run(run, song=song)
    ids = [s for s, _ in STAGES]
    for stage in ids[:ids.index(upto)]:
        complete_stage(run, stage)
    approve_script(run)
    return run


def cli_command(*args):
    """Exercise the real argparse entrypoint under the offline process guard."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = F.main(list(args))
    return subprocess.CompletedProcess(args, code, out.getvalue(), err.getvalue())


def row(run):
    with SS.Store(run / "control" / "state.sqlite3") as st:
        return st.get(RID, "music")


def qc(verdict="PASS"):
    rec = {"schema_version": "1.0.0", "check_id": "song-1", "run_id": RID,
           "stage": "music", "check": "song", "verdict": verdict,
           "evidence": {"summary": "five WW-21 gates read on picked take"},
           "checker_version": "song_dispatch/1", "reviewer": {
               "identity": "qc-reviewer", "session": "s1", "authority": "dept-qc"}}
    return {"records": [rec], "makers": {"song-1": "music-worker"}, "required": ["song"]}


def main():
    tmp = tempfile.mkdtemp(prefix="music-lifecycle-")
    W = "music-worker"

    # a+b+c: NOT_STARTED -> claim (RUNNING) -> provider wait -> resume -> COMPLETE
    run = new_run(tmp)
    assert row(run)["state"] == "NOT_STARTED"
    r = F.music_stage(run, W, "start")
    assert r["outcome"] == "ok" and r["reason_code"] == "music-claimed", r
    assert r["row"]["state"] == "RUNNING" and r["row"]["owner"] == W, r
    v = r["row"]["version"]
    print("ok a/b: NOT_STARTED -> READY -> claim -> RUNNING (owner %s, v%d)" % (W, v))

    # d: identical second claim = heartbeat/resume, no new claim, no raise
    r2 = F.music_stage(run, W, "start")
    assert r2["outcome"] == "ok" and r2["reason_code"] == "music-resumed", r2
    assert r2["row"]["version"] == v and r2["row"]["owner"] == W, r2
    with SS.Store(run / "control" / "state.sqlite3") as st:
        claims = [e for e in st.events(RID) if e[0] == "music" and e[1] == "claim"]
    assert len(claims) == 1, claims
    print("ok d: second identical start resumed, version unchanged, 1 claim event")
    rx = F.music_stage(run, "other-worker", "start")
    assert rx["outcome"] == "rejected" and rx["reason_code"] == "NOT_OWNER", rx
    print("ok d: competing owner refused NOT_OWNER")

    assert F.music_stage(run, W, "wait-provider")["row"]["state"] == "WAITING_PROVIDER"
    assert F.music_stage(run, W, "start")["reason_code"] == "music-resumed"
    assert F.music_stage(run, W, "resume")["row"]["state"] == "RUNNING"

    # complete refuses without audio (FAILED_BLOCKED, reason recorded)
    blk = new_run(tmp)
    F.music_stage(blk, W, "start")
    rb = F.music_stage(blk, W, "complete", qc=qc())
    assert rb["reason_code"] == "MUSIC_AUDIO_MISSING" and rb["row"]["state"] == "FAILED_BLOCKED", rb
    assert rb["row"]["owner"] is None and rb["row"]["reason"], rb
    print("ok: complete with no audio -> FAILED_BLOCKED (owner cleared, reason kept)")

    (run / "music").mkdir()
    (run / "music" / "picked-song.mp3").write_bytes(b"ID3" + b"\0" * 64)
    rf = F.music_stage(run, W, "complete", qc=qc("FAIL"))
    assert rf["reason_code"] == "QC_FAIL" and rf["row"]["state"] == "FAILED_BLOCKED", rf
    print("ok: independent QC FAIL -> FAILED_BLOCKED, never COMPLETE")
    assert F.music_stage(run, W, "reopen")["row"]["state"] == "READY"
    assert F.music_stage(run, W, "start")["row"]["state"] == "RUNNING"
    rc = F.music_stage(run, W, "complete", qc=qc())
    assert rc["outcome"] == "ok" and rc["row"]["state"] == "COMPLETE", rc
    assert rc["row"]["owner"] is None, rc
    again = F.music_stage(run, W, "start")
    assert again["reason_code"] == "music-complete" and again["row"]["version"] == rc["row"]["version"]
    print("ok c: RUNNING -> QC -> COMPLETE on independent PASS + audio; start after COMPLETE is a no-op")

    # three-song run with no client pick: waits for approval, never invents a pick
    sp = new_run(tmp, song=True)
    (sp / "song-choices").mkdir(exist_ok=True)
    (sp / "song-choices" / "state.json").write_text(json.dumps({"required": True, "offered": {}}))
    (sp / "music").mkdir()
    (sp / "music" / "picked-song.mp3").write_bytes(b"ID3" + b"\0" * 64)
    F.music_stage(sp, W, "start")
    rw = F.music_stage(sp, W, "complete", qc=qc())
    assert rw["outcome"] == "waiting" and rw["reason_code"] == "SONG_PICK_MISSING", rw
    assert rw["row"]["state"] == "WAITING_APPROVAL" and rw["row"]["owner"] == W, rw
    print("ok: SONG APPROVAL run without a pick -> WAITING_APPROVAL, not COMPLETE")

    # the Jennifer symptom: `next` now moves past music
    p = cli_command("next", "--run-dir", str(run))
    env = json.loads(p.stdout)
    assert env["data"].get("stage") == "continuity-bible", (p.returncode, env)
    print("ok: `next` after music COMPLETE -> continuity-bible")

    # c (failure path): simulated provider failure parks / fails correctly
    pf = new_run(tmp)
    F.music_stage(pf, W, "start")
    F.music_stage(pf, W, "wait-provider")
    ff = F.music_stage(pf, W, "fail", retryable=True, reason="provider 500 after ack")
    assert ff["row"]["state"] == "FAILED_RETRYABLE" and ff["row"]["owner"] is None, ff
    assert F.music_stage(pf, W, "start")["row"]["state"] == "RUNNING"
    nr = F.music_stage(pf, W, "park")
    assert nr["reason_code"] == "MISSING_REASON" and row(pf)["state"] == "RUNNING", nr
    pk = F.music_stage(pf, W, "park", reason="provider outage")
    assert pk["outcome"] == "parked" and pk["row"]["state"] == "PARKED", pk
    print("ok c: provider failure -> FAILED_RETRYABLE -> reclaim -> PARKED (reason required)")

    p = cli_command("next", "--run-dir", str(pf))
    env = json.loads(p.stdout)
    assert env["reason_code"] == "MUSIC_NOT_COMPLETE" and env["outcome"] == "rejected", env
    print("ok: `next` with music PARKED refuses MUSIC_NOT_COMPLETE, never skips to continuity-bible")

    # e: transition outside TRANSITIONS is refused and writes nothing
    before = row(pf)
    bad = F.music_stage(pf, W, "wait-approval")          # PARKED -> WAITING_APPROVAL
    assert bad["outcome"] == "rejected" and bad["reason_code"] == "ILLEGAL_TRANSITION", bad
    assert row(pf) == before, (row(pf), before)
    fresh = new_run(tmp)
    bad2 = F.music_stage(fresh, W, "complete", qc=qc())   # NOT_STARTED, no lease
    assert bad2["outcome"] == "rejected" and row(fresh)["state"] == "NOT_STARTED", bad2
    print("ok e: PARKED -> WAITING_APPROVAL refused ILLEGAL_TRANSITION, row unchanged; "
          "complete on NOT_STARTED refused")

    # CLI wiring
    cli = new_run(tmp)
    p = cli_command("music", "--run-dir", str(cli), "--owner", W, "--action", "start")
    env = json.loads(p.stdout)
    assert p.returncode == 0 and env["data"]["row"]["state"] == "RUNNING", (p.returncode, p.stderr)
    print("ok: CLI `factory.py music --action start` -> RUNNING, exit 0")
    print("test_music_stage_lifecycle: PASS")


if __name__ == "__main__":
    main()
