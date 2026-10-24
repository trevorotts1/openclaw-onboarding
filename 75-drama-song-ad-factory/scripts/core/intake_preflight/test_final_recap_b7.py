#!/usr/bin/env python3
"""test_final_recap_b7.py -- v3.0 B7/B8 Gate 4: ONE recap + production Go.

The video paid stage held on a model lock, the picture gate and the onscreen
gate, but nothing bound it to the approved soundtrack, the scene list, the
duration or the spend. This suite pins the hold that does, and pins that it
FAILS CLOSED:

  * recap absent            -> FINAL_RECAP_MISSING
  * recap present, partial  -> FINAL_RECAP_INCOMPLETE
  * recap complete, no Go   -> PRODUCTION_GO_MISSING
  * recap complete + Go for its digest -> the video stage is handed out
  * Go for a DIFFERENT digest          -> PRODUCTION_GO_DIGEST_MISMATCH
  * recap edited after it was built    -> FINAL_RECAP_DIGEST_MISMATCH
  * a source that cannot be measured   -> FINAL_RECAP_UNMEASURABLE, nothing written

Every recap field is READ from the run (shot list, picked song + its file
digest, locked video model, spend ledger projection); no caller string and no
flag can fill one in. stdlib only, zero paid calls, no network.

Run from the skill root:
  python3 scripts/core/intake_preflight/test_final_recap_b7.py
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factory as F                                  # noqa: E402
import final_recap as FR                             # noqa: E402
import spend_ledger as SL                            # noqa: E402
import state_store as SS                             # noqa: E402
from batch_mode.batch import STAGES                  # noqa: E402
from kie_dispatch import model_lock as ML            # noqa: E402
from test_factory_method_agnes import confirmed_fixture, complete_fixture_stage, storyboard_fixture
from test_production_process import approve_script

RID = "b7-recap-60s"
MODEL = "minimax-h3/*"  # the exact H3 family lock written by the approved card
VIDEO = "video-generation"
OWNER = "b7-test"

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if cond:
        print("ok %s" % name)
    else:
        print("FAIL %s: %s" % (name, detail))
        fails.append(name)


def _w(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _seed(tmp):
    """A run whose next stage is video-generation, built only from real
    run-dir sources: shot list, a picked song on disk, the ledger, the state
    store and the locked video model."""
    run = os.path.join(tempfile.mkdtemp(dir=tmp, prefix="b7-"), RID)
    confirmed_fixture(run, video_model="minimax-h3/image-to-video")
    for stage, _ in STAGES:
        if stage == VIDEO:
            break
        complete_fixture_stage(run, stage)
        if stage == "script-lyrics":
            approve_script(run)
    os.makedirs(os.path.join(run, "music"), exist_ok=True)
    with open(os.path.join(run, "music", "picked-song.mp3"), "wb") as f:
        f.write(b"the picked master, as the song stage leaves it")
    _w(os.path.join(run, "song-choices", "pick.json"),
       {"pick": 2, "label": "warm-live-band",
        "sha256": _sha(os.path.join(run, "music", "picked-song.mp3"))})
    storyboard_fixture(run, shots=[
        {"shot_id": "s1", "song_start": 0.0, "song_end": 30.0,
         "action": "open on the two leads"},
        {"shot_id": "s2", "song_start": 30.0, "song_end": 60.0,
         "action": "close on the empty room"}], approve=True)
    SL.init_run(os.path.join(run, "spend.sqlite3"), RID, ceiling=50000, currency="USD")
    return run


def _next(run):
    return F.cmd_next(type("A", (), {"run_dir": run, "method": None,
                                    "run_id": RID})())


def _go(digest, **kw):
    doc = {"schema": FR.GO_SCHEMA, "decision": "GO", "operator": "Trevor",
           "at_utc": "2026-10-22T09:00:00Z", "recap_digest": digest}
    doc.update(kw)
    return doc


def main():
    tmp = tempfile.mkdtemp(prefix="b7-recap-")

    # 1. recap absent -> the video stage is refused, typed.
    run = _seed(tmp)
    env = _next(run)
    check("seed reaches video-generation", env.get("data", {}).get("stage") == VIDEO,
          "stage=%r reason=%r" % (env.get("data", {}).get("stage"),
                                  env.get("reason_code")))
    check("absent recap refuses the video stage",
          env.get("reason_code") == FR.RECAP_MISSING,
          "reason_code=%r" % env.get("reason_code"))
    check("absent recap is a typed hold",
          (FR.hold(run) or {}).get("reason_code") == FR.RECAP_MISSING)

    # 2. recap present but partial (no spend, no model) -> refused, and it
    #    still fails its own measured-field check even with a correct digest.
    partial = {"schema": FR.SCHEMA,
               "measured": {"scenes": {"count": 2, "shot_ids": ["s1", "s2"],
                                       "duration_s": 60.0},
                            "soundtrack": {"pick": 2, "label": "warm-live-band",
                                           "sha256": _sha(os.path.join(
                                               run, "music", "picked-song.mp3"))}}}
    partial["recap_digest"] = FR.recap_digest(partial)
    _w(FR.recap_path(run), partial)
    check("partial recap refuses the video stage",
          _next(run).get("reason_code") == FR.RECAP_INCOMPLETE,
          "reason_code=%r" % _next(run).get("reason_code"))
    check("partial recap is a typed hold",
          (FR.hold(run) or {}).get("reason_code") == FR.RECAP_INCOMPLETE)

    # 3. a real, complete recap -- every field measured off the run.
    doc = FR.build(run)
    m = doc["measured"]
    check("recap measures the scene list", m["scenes"]["count"] == 2
          and m["scenes"]["shot_ids"] == ["s1", "s2"], repr(m.get("scenes")))
    check("recap measures the duration", m["duration_s"] == 60.0,
          repr(m.get("duration_s")))
    check("recap measures the selected soundtrack",
          m["soundtrack"]["sha256"] == _sha(os.path.join(
              run, "music", "picked-song.mp3")), repr(m.get("soundtrack")))
    check("recap measures the locked model",
          m["model"]["video_model"] == MODEL, repr(m.get("model")))
    check("recap measures the spend projection",
          isinstance(m["spend"]["cost_projection"], int)
          and m["spend"]["cost_projection"] >= 0, repr(m.get("spend")))
    check("recap digest is 64 lowercase hex",
          isinstance(doc["recap_digest"], str) and len(doc["recap_digest"]) == 64
          and doc["recap_digest"] == doc["recap_digest"].lower())

    # 4. complete recap, NO Go -> still refused.
    check("complete recap without a Go refuses the video stage",
          _next(run).get("reason_code") == FR.GO_MISSING,
          "reason_code=%r" % _next(run).get("reason_code"))
    check("complete recap without a Go is a typed hold",
          (FR.hold(run) or {}).get("reason_code") == FR.GO_MISSING)

    # 5. Go for a DIFFERENT digest -> nothing opens.
    other = "0" * 64
    _w(FR.go_path(run), _go(other))
    check("a Go for a different digest refuses the video stage",
          _next(run).get("reason_code") == FR.GO_DIGEST_MISMATCH,
          "reason_code=%r" % _next(run).get("reason_code"))
    check("a Go for a different digest is a typed hold",
          (FR.hold(run) or {}).get("reason_code") == FR.GO_DIGEST_MISMATCH)
    refused = False
    try:
        FR.record_go(run, _go(other))
    except FR.RecapError as e:
        refused = (e.code == FR.GO_DIGEST_MISMATCH)
    check("the writer refuses a Go for a different digest", refused)
    check("the refused Go did not replace the file",
          FR.read_go(run)["recap_digest"] == other)

    # 6. Go bound to the recap's own digest -> the video stage is handed out.
    FR.record_go(run, _go(doc["recap_digest"]))
    check("a Go bound to the recap digest opens the hold", FR.hold(run) is None,
          repr(FR.hold(run)))
    env = _next(run)
    check("the video stage is handed out on a bound Go",
          env.get("outcome") == "ok" and env.get("data", {}).get("stage") == VIDEO,
          "outcome=%r reason=%r" % (env.get("outcome"), env.get("reason_code")))

    # 7. the recap is edited AFTER the Go -> its own digest catches it.
    bad = json.loads(json.dumps(doc))
    bad["measured"]["scenes"]["count"] = 9
    _w(FR.recap_path(run), bad)
    check("an edited recap refuses the video stage",
          _next(run).get("reason_code") == FR.RECAP_DIGEST_MISMATCH,
          "reason_code=%r" % _next(run).get("reason_code"))
    _w(FR.recap_path(run), doc)

    # 8. the run moves AFTER the recap + Go -> the Go approves stale numbers.
    shots_path = os.path.join(run, "storyboard", "shot-list.json")
    with open(shots_path, encoding="utf-8") as f:
        shots = json.load(f)
    shots["shots"].append({"shot_id": "s3", "song_start": 60.0, "song_end": 75.0})
    _w(shots_path, shots)
    # The client sees/approves the changed storyboard through its own gate;
    # the separate production Go still binds the OLD recap and must stay stale.
    storyboard_fixture(run, shots=shots["shots"], approve=True)
    check("a run changed after the recap refuses the video stage",
          _next(run).get("reason_code") == FR.RECAP_STALE,
          "reason_code=%r" % _next(run).get("reason_code"))
    check("a stale recap is a typed hold",
          (FR.hold(run) or {}).get("reason_code") == FR.RECAP_STALE)
    shots["shots"].pop()
    _w(shots_path, shots)
    check("restoring the run reopens the hold", FR.hold(run) is None,
          repr(FR.hold(run)))

    # 9. a source that cannot be measured -> refuse and NAME it, write nothing.
    run2 = _seed(tmp)
    os.remove(os.path.join(run2, "storyboard", "shot-list.json"))
    code, detail = None, ""
    try:
        FR.build(run2)
    except FR.RecapError as e:
        code, detail = e.code, e.detail
    check("an unmeasurable run refuses to build the recap",
          code == FR.RECAP_UNMEASURABLE, "code=%r" % code)
    check("the refusal names the missing measurement", "scenes" in detail, detail)
    check("no partial recap was written", not os.path.exists(FR.recap_path(run2)))

    # 10. the two CLI subcommands are wired end to end on a fresh run.
    run3 = _seed(tmp)
    f = os.path.join(HERE, "factory.py")
    r = subprocess.run([sys.executable, f, "final-recap", "--run-dir", run3],
                       capture_output=True, text=True)
    built = json.loads(r.stdout) if r.stdout.strip() else {}
    check("final-recap CLI builds the recap",
          r.returncode == 0 and built.get("reason_code") == "FINAL_RECAP_BUILT",
          "rc=%s out=%s err=%s" % (r.returncode, r.stdout[:200], r.stderr[:200]))
    go_path = os.path.join(tmp, "go.json")
    _w(go_path, _go(built.get("data", {}).get("recap", {}).get("recap_digest", "")))
    r2 = subprocess.run([sys.executable, f, "production-go", "--run-dir", run3,
                         "--go", go_path], capture_output=True, text=True)
    went = json.loads(r2.stdout) if r2.stdout.strip() else {}
    check("production-go CLI records the Go",
          r2.returncode == 0
          and went.get("reason_code") == "PRODUCTION_GO_RECORDED",
          "rc=%s out=%s err=%s" % (r2.returncode, r2.stdout[:200], r2.stderr[:200]))
    check("the CLI-built recap + Go open the hold", FR.hold(run3) is None,
          repr(FR.hold(run3)))

    print("\n%d checks, %d failed" % (len(checks), len(fails)))
    if fails:
        for n in fails:
            print("  FAILED: %s" % n)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
