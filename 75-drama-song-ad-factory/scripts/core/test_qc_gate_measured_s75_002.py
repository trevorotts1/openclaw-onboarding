#!/usr/bin/env python3
"""U-C02 / S75-002: quality control MEASURES instead of being told.

Proves, against the real gate and the real store (real SQLite files in a temp
folder, no network, no providers):
 1. the final-QC and delivery required sets come from the declared
    STAGE_REQUIRED, and a narrower --required list is refused
    REQUIRED_CHECKS_NARROWED (nobody measures less by saying less);
 2. --master-file is MEASURED (the probe is stubbed here; the command line
    still goes through the gate's own path) and the typed --master-s is
    accepted only with --offline-test;
 3. a final QC with no --ledger is refused LEDGER_REQUIRED;
 4. qc/final-qc-verdict.json is written on PASS, FAIL and BLOCKED alike, so a
    stale PASS can never be left behind;
 5. a reviewer whose MODEL equals the maker's model is MAKER_SELF_REVIEW;
 6. state_store.Store.transition refuses COMPLETE for a canonical stage when
    the completion guard rejects the proof, and writes nothing.

Run: python3 -B scripts/core/test_qc_gate_measured_s75_002.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import qc_gate                                    # noqa: E402
import state_store as ss                          # noqa: E402

RUN = "run-c02"
STAGE = "final-qc"
FINAL_REQUIRED = ("final_edit", "export", "timeline", "audio", "text_product")
REVIEWER = {"identity": "rev-independent", "session": "s-1",
            "authority": "qc", "model": "opus-chain"}
MAKER = {"identity": "maker-1", "model": "deepseek-chain"}

FAILS = []
TMPDIRS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def tmpdir():
    d = tempfile.mkdtemp(prefix="c02-")
    TMPDIRS.append(d)
    return d


def record(check_name, verdict="PASS", reviewer=None, **over):
    rec = {"schema_version": "1.0.0", "check_id": "chk:%s" % check_name,
           "run_id": RUN, "stage": STAGE, "check": check_name,
           "verdict": verdict,
           "evidence": {"summary": "measured %s" % check_name},
           "checker_version": "1.0.0",
           "reviewer": dict(reviewer or REVIEWER)}
    rec.update(over)
    return rec


def passing_records():
    return [record(c) for c in FINAL_REQUIRED]


def write(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return path


def make_ledger(path, rows=()):
    """A real spend.sqlite3 holding the jobs table, with `rows` (paid) in it."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE jobs(logical_key TEXT, attempt_id TEXT, run_id TEXT,"
        " request_digest TEXT, stage TEXT, state TEXT, created_at TEXT)")
    for row in rows:
        con.execute(
            "INSERT INTO jobs(logical_key, attempt_id, run_id, request_digest,"
            " stage, state, created_at) VALUES(?,?,?,?,?,?,?)", row)
    con.commit()
    con.close()
    return path


def run_gate(argv):
    """Call the gate's real command line; return (parsed JSON, exit code)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = qc_gate._cli(argv)
    return json.loads(buf.getvalue()), rc


def stub_probe(duration):
    """Patch the governor-backed probe the gate measures with (real path kept).

    The gate calls ``platform_fit.probe_file`` on every measure; stubbing the
    ffprobe READ (not the gate's own measurement code) is what keeps this file
    offline while still exercising ``qc_gate._measure_master``.
    """
    import platform_fit.platform_fit as pf
    saved = pf.probe_file
    pf.probe_file = lambda path: {"duration_s": duration, "path": str(path)}
    return saved


def restore_probe(saved):
    import platform_fit.platform_fit as pf
    pf.probe_file = saved


def case(tmp, *, records=None, required=",".join(FINAL_REQUIRED),
         master_s=None, measured=30.0, ledger=None):
    """One gate invokation over a prepared run folder; returns (out, rc, dir)."""
    run_dir = os.path.join(tmp, "run")
    os.makedirs(os.path.join(run_dir, "qc"), exist_ok=True)
    master = os.path.join(tmp, "master.mp4")
    with open(master, "wb") as fh:
        fh.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    recs = write(os.path.join(tmp, "records.json"),
                 records if records is not None else passing_records())
    makers = write(os.path.join(tmp, "makers.json"),
                   {"chk:%s" % c: dict(MAKER) for c in FINAL_REQUIRED})
    argv = ["evaluate", "--run", RUN, "--stage", STAGE,
            "--records", recs, "--makers", makers,
            "--required", required, "--chosen-length-s", "45",
            "--run-dir", run_dir]
    if ledger is not None:
        argv += ["--ledger", ledger]
    if master_s is not None:
        argv += ["--master-s", str(master_s)]
    elif measured is not None:
        argv += ["--master-file", master]
    out, rc = run_gate(argv)
    return out, rc, run_dir, master


def verdict_of(run_dir):
    path = os.path.join(run_dir, "qc", "final-qc-verdict.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- the cases --

def test_declared_sets_are_real_checks():
    for stage, names in qc_gate.STAGE_REQUIRED.items():
        unknown = [n for n in names if n not in qc_gate.CHECKS]
        check("declared required set for %s names real checks" % stage,
              not unknown, "unknown: %r" % (unknown,))
    check("final-qc declares the QC.md 17.5 set",
          tuple(qc_gate.STAGE_REQUIRED["final-qc"]) == FINAL_REQUIRED)
    check("delivery declares the delivery records",
          set(qc_gate.STAGE_REQUIRED["delivery"]) == {
              "final_edit", "song_files", "audio_versions", "cover_image",
              "video_delivery"})


def test_narrowed_list_is_refused():
    for stage in ("final-qc", "delivery"):
        narrow = ",".join(qc_gate.STAGE_REQUIRED[stage][:2])
        buf = io.StringIO()
        tmp = tmpdir()
        recs = write(os.path.join(tmp, "r.json"), [])
        makers = write(os.path.join(tmp, "m.json"), {})
        with contextlib.redirect_stdout(buf):
            rc = qc_gate._cli(["evaluate", "--run", RUN, "--stage", stage,
                               "--records", recs, "--makers", makers,
                               "--required", narrow])
        out = json.loads(buf.getvalue())
        check("%s: a narrowed --required list is rejected" % stage,
              rc == qc_gate.EXIT["rejected"]
              and out["reason_code"] == "REQUIRED_CHECKS_NARROWED", str(out))
        check("%s: the refusal names the omitted checks" % stage,
              set(out["evidence"]["missing"])
              == set(qc_gate.STAGE_REQUIRED[stage]) - set(narrow.split(",")),
              str(out.get("evidence")))


def test_typed_master_needs_offline_flag():
    tmp = tmpdir()
    out, rc, _run_dir, _master = case(tmp, master_s=30.0, measured=None)
    check("a typed --master-s without --offline-test is rejected",
          rc == qc_gate.EXIT["rejected"]
          and out["reason_code"] == "MASTER_NOT_MEASURED", str(out))


def test_master_file_is_measured():
    tmp = tmpdir()
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, master = case(tmp, ledger=make_ledger(
            os.path.join(tmp, "spend.sqlite3")))
    finally:
        restore_probe(saved)
    check("--master-file: the gate passes on the measured master",
          rc == qc_gate.EXIT["ok"] and out["outcome"] == "ok", str(out))
    doc = verdict_of(run_dir)
    check("--master-file: the verdict records the measured seconds",
          doc is not None and doc.get("measured_master_s") == 30.0, str(doc))
    check("--master-file: the verdict hashes the master it measured",
          doc is not None and doc.get("master_sha256")
          == qc_gate._sha256_file(master), str(doc))


def test_missing_ledger_is_refused():
    tmp = tmpdir()
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _master = case(tmp, ledger=None)
    finally:
        restore_probe(saved)
    check("final-qc without a ledger is rejected LEDGER_REQUIRED",
          rc == qc_gate.EXIT["rejected"]
          and out["reason_code"] == "LEDGER_REQUIRED", str(out))
    check("the LEDGER_REQUIRED refusal writes no verdict",
          verdict_of(run_dir) is None)


def test_verdict_written_on_every_gate():
    # PASS
    tmp = tmpdir()
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _m = case(tmp, ledger=make_ledger(
            os.path.join(tmp, "spend.sqlite3")))
    finally:
        restore_probe(saved)
    doc = verdict_of(run_dir)
    check("PASS writes a PASS verdict file",
          rc == qc_gate.EXIT["ok"] and doc and doc["gate"] == "PASS", str(doc))
    check("the verdict names the declared required set",
          doc is not None and list(doc["required"]) == list(FINAL_REQUIRED),
          str(doc))
    check("the verdict hashes the records it judged",
          doc is not None and doc["records_sha256"]
          == qc_gate._sha256_file(os.path.join(tmp, "records.json")),
          str(doc))
    check("the verdict carries the run, stage and an epoch",
          doc is not None and doc["run_id"] == RUN and doc["stage"] == STAGE
          and isinstance(doc["evaluated_at"], int), str(doc))
    # FAIL: one required record fails
    tmp = tmpdir()
    recs = passing_records()
    recs[-1]["verdict"] = "FAIL"
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _m = case(
            tmp, records=recs,
            ledger=make_ledger(os.path.join(tmp, "spend.sqlite3")))
    finally:
        restore_probe(saved)
    doc = verdict_of(run_dir)
    check("FAIL writes a FAIL verdict file over any older one",
          rc == qc_gate.EXIT["rejected"] and doc and doc["gate"] == "FAIL",
          str(doc))
    # BLOCKED: an UNAVAILABLE required record is structural
    tmp = tmpdir()
    recs = passing_records()
    recs[3]["verdict"] = "UNAVAILABLE"
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _m = case(
            tmp, records=recs,
            ledger=make_ledger(os.path.join(tmp, "spend.sqlite3")))
    finally:
        restore_probe(saved)
    doc = verdict_of(run_dir)
    check("BLOCKED writes a BLOCKED verdict file",
          rc == qc_gate.EXIT["rejected"] and doc and doc["gate"] == "BLOCKED",
          str(doc))


def test_paid_jobs_come_from_the_ledger():
    tmp = tmpdir()
    ledger = make_ledger(os.path.join(tmp, "spend.sqlite3"), rows=[
        ("music/song:1:abc", "att-1", RUN, "sha256:req-1", "music",
         "succeeded", "2026-11-12T00:00:00+00:00")])
    jobs = qc_gate._read_paid_jobs(ledger, RUN)
    check("a paid job is read from the run's own ledger",
          len(jobs) == 1 and jobs[0]["logical_key"] == "music/song:1:abc",
          str(jobs))
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _m = case(tmp, ledger=ledger)
    finally:
        restore_probe(saved)
    doc = verdict_of(run_dir)
    check("a paid job with no receipt never passes final QC",
          rc == qc_gate.EXIT["rejected"], str(out))
    check("the verdict records prompt_compliance as required when jobs exist",
          doc is not None
          and "prompt_compliance" in doc["required"], str(doc))


def test_same_model_reviewer_is_self_review():
    tmp = tmpdir()
    recs = passing_records()
    for rec in recs:
        rec["reviewer"] = dict(REVIEWER, model="DeepSeek-Chain")   # maker's
    saved = stub_probe(30.0)
    try:
        out, rc, run_dir, _m = case(
            tmp, records=recs,
            ledger=make_ledger(os.path.join(tmp, "spend.sqlite3")))
    finally:
        restore_probe(saved)
    check("same model as the maker -> MAKER_SELF_REVIEW",
          rc == qc_gate.EXIT["rejected"]
          and "MAKER_SELF_REVIEW" in out["reason_code"], str(out))
    doc = verdict_of(run_dir)
    check("a self-reviewed gate writes BLOCKED, never PASS",
          doc is not None and doc["gate"] == "BLOCKED", str(doc))
    # the old bare-string makers form still works (identity only)
    makers = {"chk:%s" % c: "maker-1" for c in FINAL_REQUIRED}
    res = qc_gate.evaluate(RUN, STAGE, passing_records(), makers,
                           list(FINAL_REQUIRED), master={
                               "chosen_length_s": 45, "measured_s": 30.0})
    check("the bare-string makers form still gates normally",
          res["gate"] == "PASS", str(res.get("reason_code")))


# ------------------------------------------------------- the store's hook ---

def test_complete_guard_blocks_unproven_completion():
    tmp = tmpdir()
    st = ss.Store(os.path.join(tmp, "state.sqlite3"))
    try:
        st.init_run(RUN, ["music", "drafting"])
        seen = []

        def guard(run_id, stage, proof):
            seen.append((run_id, stage, proof))
            return None if proof == "sealed" else "no seal for %s" % stage

        ss.COMPLETE_GUARD = guard
        row = st.get(RUN, "music")
        row = st.transition(RUN, "music", "READY", "w1",
                            expected_version=row["version"])
        row = st.claim(RUN, "music", "w1", lease_s=60)
        try:
            st.transition(RUN, "music", "COMPLETE", "w1",
                          expected_version=row["version"], proof="unsigned")
            check("an unproven completion raises COMPLETION_NOT_PROVEN", False)
        except ss.StoreError as e:
            check("an unproven completion raises COMPLETION_NOT_PROVEN",
                  e.code == "COMPLETION_NOT_PROVEN", str(e))
        after = st.get(RUN, "music")
        check("a refused completion leaves the row untouched",
              after["state"] == "RUNNING"
              and after["version"] == row["version"], str(after))
        check("the guard receives the run, the stage and the proof",
              seen == [(RUN, "music", "unsigned")], str(seen))
        row = st.transition(RUN, "music", "COMPLETE", "w1",
                            expected_version=after["version"], proof="sealed")
        check("a proven completion is written", row["state"] == "COMPLETE")

        seen.clear()
        row = st.get(RUN, "drafting")
        row = st.transition(RUN, "drafting", "READY", "w1",
                            expected_version=row["version"])
        row = st.claim(RUN, "drafting", "w1", lease_s=60)
        row = st.transition(RUN, "drafting", "COMPLETE", "w1",
                            expected_version=row["version"], proof="anything")
        check("a stage outside the twelve completes without the guard",
              row["state"] == "COMPLETE" and seen == [], str(seen))
    finally:
        ss.COMPLETE_GUARD = None
        st.close()


TESTS = [
    test_declared_sets_are_real_checks,
    test_narrowed_list_is_refused,
    test_typed_master_needs_offline_flag,
    test_master_file_is_measured,
    test_missing_ledger_is_refused,
    test_verdict_written_on_every_gate,
    test_paid_jobs_come_from_the_ledger,
    test_same_model_reviewer_is_self_review,
    test_complete_guard_blocks_unproven_completion,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                       # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    for d in TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d S75-002 measured-QC groups passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
