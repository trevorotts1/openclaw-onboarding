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


if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); n += 1; print("ok", k)
    print("all %d E01 checks passed" % n)
