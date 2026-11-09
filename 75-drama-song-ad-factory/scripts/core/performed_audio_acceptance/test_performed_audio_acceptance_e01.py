#!/usr/bin/env python3
"""E01 suite: 6 planted refusals + measured-fixture positive (offline, $0).

The positive uses a synthetic temp file and synthetic measures: it proves the
refusal logic only. It is NOT live audio acceptance (owner-gated)."""
import hashlib, os, sys, tempfile, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import performed_audio_acceptance as P

NOW, M, S = 1_800_000_000, "m" * 64, "s" * 64
d = tempfile.mkdtemp()
f = os.path.join(d, "a.mp3")
open(f, "wb").write(b"fixture-bytes")
H = hashlib.sha256(b"fixture-bytes").hexdigest()
ok = lambda: {"status": "measured", "source": "listened", "evaluator": "approved-model", "value": 1}
LEDGER = [{"job_id": "j1", "state": "succeeded", "output_sha256": H}]
GOOD = {"method_sha256": M, "sheet_sha256": S, "measured_at": NOW - 60, "claimed_verdict": "PASS",
        "jobs": [{"job_id": "j1", "audio_path": f, "audio_sha256": H,
                  "measures": {k: ok() for k in P.REQUIRED}}]}


def codes(rec, ledger=LEDGER, m=M, s=S):
    return {r["code"] for r in P.refusals(rec, ledger, m, s, NOW)}


def mut(fn):
    r = copy.deepcopy(GOOD); fn(r); return r


def test_positive_measured_fixture_passes():
    assert P.accept(GOOD, LEDGER, M, S, NOW) == "PASS"


def test_missing_audio_refused():
    assert "AUDIO_MISSING" in codes(mut(lambda r: r["jobs"][0].update(audio_path=os.path.join(d, "nope.mp3"))))


def test_unavailable_or_duration_only_refused():
    r = mut(lambda r: r["jobs"][0].__setitem__("measures", {"timing": ok()}))
    assert "MEASURE_UNAVAILABLE" in codes(r)
    try:
        P.accept(r, LEDGER, M, S, NOW); assert False
    except P.AcceptanceRefused:
        pass


def test_failed_measure_refused():
    assert "MEASURE_FAILED" in codes(mut(lambda r: r["jobs"][0]["measures"].__setitem__("hooks", {"status": "failed"})))


def test_stale_binding_and_measurement_refused():
    assert "STALE_BINDING" in codes(GOOD, s="x" * 64)
    assert "STALE_MEASUREMENT" in codes(mut(lambda r: r.update(measured_at=NOW - 30 * 24 * 3600)))


def test_omitted_job_refused():
    led = LEDGER + [{"job_id": "j2", "state": "succeeded", "output_sha256": "z"}]
    assert "JOB_OMITTED" in codes(GOOD, ledger=led)


def test_caption_label_standing_for_listening_refused():
    r = mut(lambda r: r["jobs"][0]["measures"]["voices"].update(source="caption"))
    assert "LABEL_AS_LISTENING" in codes(r)


def test_hash_mismatch_refused():
    assert "AUDIO_HASH_MISMATCH" in codes(mut(lambda r: r["jobs"][0].update(audio_sha256="0" * 64)))


def test_accepted_risk_keeps_fail():
    bad = mut(lambda r: r.update(claimed_verdict="ACCEPTED_RISK", underlying_verdict="PASS"))
    try:
        P.accept(bad, LEDGER, M, S, NOW); assert False
    except P.AcceptanceRefused as e:
        assert e.reasons[-1]["code"] == "RISK_HIDES_FAIL"
    good = mut(lambda r: r.update(claimed_verdict="ACCEPTED_RISK", underlying_verdict="FAIL", client_choice="keep"))
    assert P.accept(good, LEDGER, M, S, NOW) == "ACCEPTED_RISK"


def test_empty_ledger_and_empty_record_refused():
    rec = mut(lambda r: r.update(jobs=[]))
    assert "NO_AUDIO_JOBS" in codes(rec, ledger=[])
    try:
        P.accept(rec, [], M, S, NOW); assert False
    except P.AcceptanceRefused:
        pass
    assert "NO_AUDIO_JOBS" in codes(rec)  # ledger has job, record empty
    assert "NO_AUDIO_JOBS" in codes(GOOD, ledger=[])  # record has job, ledger empty


def _real_ledger(states):
    """In-memory DB built from the real spend_ledger DDL."""
    import sqlite3
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import spend_ledger as SL
    c = sqlite3.connect(":memory:")
    c.executescript(SL.DDL)
    c.execute("INSERT INTO runs(run_id,ceiling,created_at,updated_at) VALUES('r',100,'t','t')")
    for i, (stage, state, final) in enumerate(states):
        c.execute("INSERT INTO jobs(logical_key,attempt_id,run_id,request_digest,stage,state,final_outcome,"
                  "created_at,updated_at) VALUES(?,?,?,?,?,?,?,'t','t')",
                  ("k%d" % i, "att-0001-x", "r", "d", stage, state, final))
        c.execute("INSERT INTO results(run_id,logical_key,attempt_id,artifact_path,sha256,created_at) "
                  "VALUES('r',?,?,?,?,'t')", ("k%d" % i, "att-0001-x", f, H))
    c.row_factory = sqlite3.Row
    jobs = [dict(r) for r in c.execute("SELECT * FROM jobs")]
    res = [dict(r) for r in c.execute("SELECT * FROM results")]
    return P.ledger_jobs_from_rows(jobs, res)


def _rec_for(job_ids):
    return mut(lambda r: r.update(jobs=[dict(copy.deepcopy(GOOD["jobs"][0]), job_id=i) for i in job_ids]))


def test_real_spend_ledger_shape_succeeded_and_reconciled():
    led = _real_ledger([("audio", "succeeded", "succeeded"), ("audio", "reconciled", "succeeded"),
                        ("audio", "reconciled", "failed"), ("video", "succeeded", "succeeded")])
    assert [j["job_id"] for j in led] == ["k0/att-0001-x", "k1/att-0001-x", "k2/att-0001-x"]  # video dropped
    ok_ids = ["k0/att-0001-x", "k1/att-0001-x"]  # reconciled+succeeded counts; reconciled+failed does not
    assert P.accept(_rec_for(ok_ids), led, M, S, NOW) == "PASS"
    assert "JOB_OMITTED" in codes(_rec_for(ok_ids[:1]), ledger=led)  # reconciled-succeeded cannot be omitted
    assert "JOB_NOT_IN_LEDGER" in codes(_rec_for(ok_ids + ["k2/att-0001-x"]), ledger=led)


def test_unrecorded_result_sha_refuses():
    led = _real_ledger([("audio", "succeeded", "succeeded")])
    led[0]["output_sha256"] = None  # results.sha256 NULL
    assert "AUDIO_HASH_MISMATCH" in codes(_rec_for(["k0/att-0001-x"]), ledger=led)


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); n += 1; print("ok", k)
    print("all %d E01 checks passed" % n)
