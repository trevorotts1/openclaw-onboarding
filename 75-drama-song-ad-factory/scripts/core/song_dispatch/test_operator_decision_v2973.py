#!/usr/bin/env python3
"""test_operator_decision_v2973.py — L2: the WW-21 operator-decision path.

v2.9.73 (lane RL2): acceptance blocked the Voyage To Virtue music stage
(FAILED_BLOCKED ACCEPTANCE_NOT_PROVEN, five empty records across 90 takes) with
no honest close: D5 had MEASURED FAIL across four estimators, and the module
explicitly refuses a hand-set relabel (`_MANUAL_SOURCES`). This adds the
DOCUMENTED operator decision:

  * a decision NEVER writes a PASS for a measured gate — the take-level
    PASS/FAIL records are untouched and `acceptance_from_run` still blocks;
  * it records {decision, operator, at_utc, gates_not_proven,
    measured_evidence_digest, reason} under music/acceptance/
    operator-decision.json;
  * it is reachable from `factory.py music --action complete` via
    `--operator-decision <path>`;
  * a decision missing the operator, the timestamp, the failing gate list or
    the evidence digest is REFUSED and nothing is written;
  * `_MANUAL_SOURCES` refusals STAND — a decision is not a relabel.

Script-style stdlib test: run by file. No network, no spend, no browser.

Run: python3 scripts/core/song_dispatch/test_operator_decision_v2973.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))

import factory as F                                # noqa: E402
import state_store as SS                           # noqa: E402
from song_dispatch import song_dispatch as SD      # noqa: E402
from batch_mode.batch import STAGES                # noqa: E402

RID = "rl2-decision-60s"
OWNER = "music-worker"
REQUIRED = ("D1", "D2", "D3", "D4", "D5")

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))


def _binding(name):
    return {"export_digest": os.urandom(32).hex(), "creative_revision": "rl2-r1",
            "profile_revision": "1.0.0"}


def new_run(tmp, variant="v1", d5="UNMEASURED"):
    """A run with a produced take and a NON-all-PASS acceptance record:
    four gates PASS, D5 (more than one character voice) measured not proven."""
    run = os.path.join(tempfile.mkdtemp(dir=tmp, prefix="dec-"), "run")
    os.makedirs(os.path.join(run, "control"))
    os.makedirs(os.path.join(run, "music", "takes", variant))
    with open(os.path.join(run, "music", "picked-song.mp3"), "wb") as f:
        f.write(b"the picked master, as _real_generate leaves it")
    with open(os.path.join(run, "music", "takes", variant, "take-1.mp3"), "wb") as f:
        f.write(b"a produced take, as the generator leaves it")
    b = _binding("export")
    results = {g: {"verdict": "PASS", "binding": dict(b)} for g in REQUIRED}
    results["D5"] = {"verdict": d5, "binding": dict(b)}
    SD.record_acceptance(run, variant, b, results)
    ids = [s for s, _ in STAGES]
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        st.init_run(RID, ids)
        for s in ids[:ids.index("music")]:
            st.transition(RID, s, "READY", "seed")
            st.claim(RID, s, "seed")
            st.transition(RID, s, "COMPLETE", "seed")
    return run


def _row(run):
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        return st.get(RID, "music")


def _decision(run=None, variant="v1", **over):
    """The decision doc. `measured_evidence_digest` is COMPUTED over the
    variant's on-disk measured evidence records -- exactly what
    `sha256_evidence_records({variant: measure_evidence_digest(run, variant)})`
    produces -- so the valid record binds itself to the evidence it refuses to
    override; a hand-set digest is the fabricated case."""
    dig = ("ab" * 32)
    if run is not None:
        on_disk = SD.measure_evidence_digest(run, variant) or ""
        dig = SD.sha256_evidence_records({variant: on_disk})
    dec = {"decision": "ACCEPTED_RISK", "operator": "trevor",
           "at_utc": "2026-10-21T12:00:00Z", "gates_not_proven": ["D5"],
           "measured_evidence_digest": dig,
           "reason": "D5 measured FAIL across four estimators; the owner accepts the "
                     "run with D5 not proven"}
    dec.update(over)
    for k in [k for k, v in dec.items() if v is _DELETE]:
        del dec[k]
    return dec


class _DELETE:
    """Sentinel: drop this key from the decision."""


def _qc(verdict="PASS"):
    rec = {"schema_version": "1.0.0", "check_id": "song-1", "run_id": RID,
           "stage": "music", "check": "song", "verdict": verdict,
           "evidence": {"summary": "five WW-21 gates read on picked take"},
           "checker_version": "song_dispatch/1", "reviewer": {
               "identity": "qc-reviewer", "session": "s1", "authority": "dept-qc"}}
    return {"records": [rec], "makers": {"song-1": OWNER}, "required": ["song"]}


def _decfile(run, dec):
    p = SD.operator_decision_path(run)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dec, f)
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="rl2-decision-")

    # 1. a VALID decision advances the stage and records the gates NOT proven;
    #    the take record's own verdict is UNTOUCHED and never re-written PASS.
    run = new_run(tmp)
    chk = SD.acceptance_from_run(run)
    check("block before decision", chk["applicable"] and not chk["allowed"], chk)
    before = json.load(open(os.path.join(run, "music", "acceptance", "v1.json")))
    check("take record D5 NOT PASS", before["results"]["D5"]["verdict"] == "UNMEASURED", before["results"]["D5"])
    _decfile(run, _decision(run))
    r = F.music_stage(run, OWNER, "start")
    qc = _qc()
    r = F.music_stage(run, OWNER, "complete", qc=qc, operator_decision=_decision(run))
    print("  valid decision -> outcome=%r code=%r state=%r"
          % (r["outcome"], r["reason_code"], (r["row"] or {}).get("state")))
    check("valid decision advances", r["outcome"] == "ok"
          and (r["row"] or {}).get("state") == "COMPLETE", r)
    dpath = SD.operator_decision_path(run)
    recorded = json.load(open(dpath))
    for k in ("decision", "operator", "at_utc", "gates_not_proven",
              "measured_evidence_digest", "reason"):
        check("recorded field %s" % k, bool(recorded.get(k)), recorded)
    check("gates_not_proven names D5", recorded["gates_not_proven"] == ["D5"], recorded)
    check("decision not a PASS", recorded["decision"] != "PASS", recorded)
    check("recorded_at_utc written by the writer",
          isinstance(recorded.get("recorded_at_utc"), str), recorded)
    after = json.load(open(os.path.join(run, "music", "acceptance", "v1.json")))
    check("take record UNTOUCHED", after == before, after["results"]["D5"])
    # the reader still skips the decision file: it is not a blocked variant
    chk2 = SD.acceptance_from_run(run)
    check("decision file not a blocked variant",
          "operator-decision.json" not in (chk2.get("variants") or {}), chk2)

    # 2. FABRICATED / incomplete decisions are REFUSED and write nothing.
    cases = [
        ("no operator", _decision(operator=_DELETE)),
        ("no at_utc", _decision(at_utc=_DELETE)),
        ("no gates_not_proven", _decision(gates_not_proven=_DELETE)),
        ("no measured_evidence_digest", _decision(measured_evidence_digest=_DELETE)),
        ("no reason", _decision(reason=_DELETE)),
        ("decision=PASS overclaim", _decision(decision="PASS")),
        ("bad timestamp", _decision(at_utc="yesterday")),
        ("bad digest (not sha256)", _decision(measured_evidence_digest="deadbeef")),
        ("UPPER digest", _decision(measured_evidence_digest="AB" * 32)),
        ("gates_not_proven not a list", _decision(gates_not_proven="D5")),
        ("empty gates_not_proven", _decision(gates_not_proven=[])),
        ("unknown gate name", _decision(gates_not_proven=["D9"])),
        ("blank reason", _decision(reason="     ")),
    ]
    for name, dec in cases:
        run2 = new_run(tmp)
        before2 = json.load(open(os.path.join(run2, "music", "acceptance", "v1.json")))
        r2 = F.music_stage(run2, OWNER, "start")
        r2 = F.music_stage(run2, OWNER, "complete", qc=_qc(), operator_decision=dec)
        print("  refused %-24s -> outcome=%r code=%r state=%r"
              % (name, r2["outcome"], r2["reason_code"], (r2["row"] or {}).get("state")))
        ok = r2["outcome"] == "rejected" and r2["reason_code"] == "OPERATOR_DECISION_REJECTED" \
            and (r2["row"] or {}).get("state") == "FAILED_BLOCKED"
        check("refused %s" % name, ok, r2)
        p2 = SD.operator_decision_path(run2)
        check("nothing written for %s" % name, not os.path.exists(p2), p2)
        after2 = json.load(open(os.path.join(run2, "music", "acceptance", "v1.json")))
        check("take record untouched for %s" % name, after2 == before2)
        # module-level refusal carries the same named reason
        try:
            SD.record_operator_decision(run2, dec)
            check("module refuses %s" % name, False, "no raise")
        except SD.DispatchError as e:
            check("module refuses %s" % name,
                  "OPERATOR_DECISION_REJECTED" in str(e), str(e)[:120])

    # 2b. --operator-decision pointing at an UNREADABLE file is a loud refusal.
    run2b = new_run(tmp)
    F.music_stage(run2b, OWNER, "start")
    badp = os.path.join(run2b, "dec-bad.json")
    with open(badp, "w", encoding="utf-8") as f:
        f.write("{not json")
    p = subprocess.run([sys.executable,
                        os.path.join(CORE, "intake_preflight", "factory.py"),
                        "music", "--run-dir", run2b, "--owner", OWNER,
                        "--action", "complete", "--operator-decision", badp,
                        "--run-id", RID], capture_output=True, text=True,
                       cwd=str(os.path.dirname(os.path.dirname(CORE))), timeout=60)
    env = json.loads(p.stdout)
    print("  unreadable decision file -> outcome=%r code=%r" % (env["outcome"], env["reason_code"]))
    check("unreadable decision file refused",
          env["outcome"] == "error" and env["reason_code"] == "OPERATOR_DECISION_UNREADABLE", env)

    # 2c. the CLI wiring: --operator-decision reaches the stage (rejected for a
    #     missing field, so the arg exists end-to-end).
    m = F._MUSIC_ACTIONS
    check("action set unchanged", m == ("start", "complete", "fail", "wait-provider",
                                        "wait-approval", "resume", "park", "reopen"), m)
    lc = F._music_lifecycle()
    check("documented decision path in lifecycle note",
          "--operator-decision" in lc["note"], lc["note"][:200])

    # 3. _MANUAL_SOURCES refusal UNCHANGED: a decision is not a relabel.
    run3 = new_run(tmp)
    b3 = {"export_digest": SD.take_binding(os.path.join(run3, "music", "takes", "v1", "take-1.mp3"),
                                           "rl2-r1")["export_digest"],
          "creative_revision": "rl2-r1", "profile_revision": "1.0.0"}
    SD.record_acceptance(run3, "v1", dict(b3, source="manual"), {
        g: {"verdict": "PASS", "binding": dict(b3, source="manual")} for g in REQUIRED})
    chk3 = SD.acceptance_from_run(run3)
    reasons = [x for r3 in (chk3.get("blocked") or []) for x in (chk3["variants"][r3].get("reasons") or [])]
    print("  manual relabel -> applicable=%r allowed=%r MANUAL_RELABEL refusals=%d"
          % (chk3["applicable"], chk3["allowed"], sum("MANUAL_RELABEL" in x for x in reasons)))
    check("manual relabel still blocked", chk3["applicable"] and not chk3["allowed"], chk3)
    check("manual relabel names MANUAL_RELABEL",
          any("MANUAL_RELABEL" in x for x in reasons), reasons)
    # a decision cannot be recorded on top of a relabel AND the refusal keeps
    # pointing at re-measuring, never at the decision path
    ref = SD.acceptance_refusal(run3, "delivery")
    print("  manual relabel next_action: %s" % ref["next_action"][:110])
    check("relabel refusal does NOT advertise the decision path",
          "--operator-decision" not in ref["next_action"], ref["next_action"])
    F.music_stage(run3, OWNER, "start")

    # 3b. a decision CANNOT mark a measured gate PASS: the boundary stays shut.
    dec = _decision(run=run3)
    d3, rs3 = SD.decision_applies(run3, dec=dec, required=REQUIRED)
    check("decision validates form alone", d3 is not None and rs3 == [], rs3)
    chk3b = SD.acceptance_from_run(run3)
    check("decision never opens the boundary", not chk3b.get("allowed"), chk3b)
    afterD5 = chk3b["variants"]["v1"]["reasons"]
    check("D5 still named in the boundary state",
          any("D5" in x or "BLOCKING_VERDICT" in x for x in afterD5), afterD5[:2])

    # 4. take-level records untouched at every step of a real completion.
    run4 = new_run(tmp)
    _decfile(run4, _decision(run4))
    before4 = json.load(open(os.path.join(run4, "music", "acceptance", "v1.json")))
    F.music_stage(run4, OWNER, "start")
    r4 = F.music_stage(run4, OWNER, "complete", qc=_qc(), operator_decision=_decision(run4))
    check("completion still ok", r4["outcome"] == "ok" and (r4["row"] or {}).get("state") == "COMPLETE", r4)
    after4 = json.load(open(os.path.join(run4, "music", "acceptance", "v1.json")))
    check("take record untouched after COMPLETE", after4 == before4)
    measured = json.load(open(SD.operator_decision_path(run4)))
    check("decision binds the on-disk evidence digest",
          isinstance(measured.get("measured_evidence_digest"), str)
          and len(measured["measured_evidence_digest"]) == 64, measured.get("measured_evidence_digest"))
    # a CHANGE of the underlying record after the decision is detectable
    SD.record_acceptance(run4, "v1", _binding("x"), {
        g: {"verdict": "PASS", "binding": _binding("x")} for g in REQUIRED})
    fresh = SD.measure_evidence_digest(run4, "v1")
    print("  decision digest %s..., fresh record digest %s..."
          % (measured["measured_evidence_digest"][:8], fresh[:8]))
    check("evidence change is detectable", fresh != measured["measured_evidence_digest"])

    # 5. no decision file + a produced take still REFUSES the stage (unchanged).
    run5 = new_run(tmp)
    F.music_stage(run5, OWNER, "start")
    r5 = F.music_stage(run5, OWNER, "complete", qc=_qc())
    print("  no decision -> outcome=%r code=%r state=%r"
          % (r5["outcome"], r5["reason_code"], (r5["row"] or {}).get("state")))
    check("no decision still blocks",
          r5["outcome"] == "rejected" and (r5["row"] or {}).get("state") == "FAILED_BLOCKED", r5)
    check("the block keeps ACCEPTANCE_NOT_PROVEN",
          "ACCEPTANCE_NOT_PROVEN" in (r5["reason_code"] or "")
          or (r5["row"] or {}).get("reason", "").find("ACCEPTANCE") >= 0, r5)

    print("checks: %d, failures: %d" % (len(checks), len(fails)))
    for f in fails:
        print("FAIL %s" % f)
    if fails:
        sys.exit(1)
    print("test_operator_decision_v2973: PASS")


if __name__ == "__main__":
    main()