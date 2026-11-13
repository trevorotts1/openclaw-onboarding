#!/usr/bin/env python3
"""S75-W06-U2: continuity-bible stage runner — typed readers, declared
required evidence, registry predicate, executable advancement.

Proves (findings D08, D33, S75-016):
  * qc-records.json is read as a LIST (the dict-only reader bug class cannot
    pass); a legacy {"records": [...]} wrapper migrates with a note; any
    other shape is an explicit bad state, never an empty pass;
  * REQUIRED_CHECKS is declared independently of what arrives: missing
    evidence fails the gate and NEVER shrinks the required set;
  * gate PASS needs an independent maker/reviewer pair (qc_gate rules);
  * S75-016: the stage SEALS the finished bible before it advances — a run
    holding only ``continuity/qc-records.json`` and ``continuity/makers.json``
    does NOT advance, and the refusal names the missing record;
  * advance() moves the continuity-bible row to COMPLETE through state_store
    guarded transitions in ONE call (no separate manual action) and reports
    the seven downstream stages' rows;
  * register() wires proven() into a stage registry dict.

Run: python3 scripts/core/character_continuity/test_stage.py  (stdlib, no spend)
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import character_continuity.stage as ST                     # noqa: E402
import state_store as SS                                    # noqa: E402
from batch_mode import batch as BATCH                       # noqa: E402

SG = ST.step_gate_module()                                  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def record(run_id="run1", check_id="continuity-dna-1", check="continuity",
           verdict="PASS", reviewer="qc-reviewer-1", maker="agent-writer-1",
           summary="Character DNA, product DNA and style bible records agree "
                   "across every planned shot."):
    return {"schema_version": "1.0.0", "check_id": check_id,
            "run_id": run_id, "stage": "continuity-bible", "check": check,
            "verdict": verdict, "evidence": {"summary": summary},
            "checker_version": "1.0.0",
            "reviewer": {"identity": reviewer, "session": "s1",
                         "authority": "qc"}, "_maker": maker}


def write_run(records=None, makers=None):
    run = tempfile.mkdtemp(prefix="cont-stage-")
    os.makedirs(os.path.join(run, "continuity"))
    os.makedirs(os.path.join(run, "control"))
    if records == "MISSING":
        pass
    elif records == "CORRUPT":
        open(os.path.join(run, "continuity", "qc-records.json"), "w").write("{nope")
    else:
        json.dump(records if records is not None else [],
                  open(os.path.join(run, "continuity", "qc-records.json"), "w"))
    if makers is not None:
        json.dump(makers, open(os.path.join(run, "continuity", "makers.json"), "w"))
    return run


def clean(recs):
    """Strip the maker sidecar into a makers map (qc-schema records only)."""
    out, makers = [], {}
    for r in recs:
        r = dict(r)
        makers[r["check_id"]] = r.pop("_maker")
        out.append(r)
    return out, makers


def make_store(run):
    db = os.path.join(run, "control", "state.sqlite3")
    with SS.Store(db) as st:
        st.init_run("run1", [s for s, _ in BATCH.STAGES])
    return db


def write_finished_bible(run, approved=True):
    """The two records a FINISHED continuity bible consists of, written the way
    ``character_approval`` writes them (save_bible, then approve)."""
    char = os.path.join(run, "character")
    os.makedirs(char, exist_ok=True)
    json.dump({"schema": "blackceo.character-bible/v2", "revision": 1,
               "fingerprint": "0" * 64,
               "characters": [{"slug": "mia", "name": "Mia",
                               "role": "protagonist",
                               "background": "raised in the same town",
                               "appearance": "brown eyes, short hair",
                               "voice_notes": "warm and low",
                               "images": {"close-up": {"path": "refs/mia.png"}}}]},
              open(os.path.join(char, "bible.json"), "w"))
    json.dump({"schema": "blackceo.character-approval/v1",
               "status": "approved" if approved else "pending",
               "bible_revision": 1, "approved_by": "the client",
               "image_hashes": {"mia": {"close-up": "0" * 64}}},
              open(os.path.join(char, "approval.json"), "w"))


def gate_contract():
    """The SHIPPED contract's continuity-bible rows, declared as the only stage
    so this test needs no seal for the stages before it. The artifact list is
    the real one, read from stage_contracts.json — never a copy."""
    real = SG.load_contract()
    path = os.path.join(tempfile.mkdtemp(prefix="cont-gate-"), "contract.json")
    with open(path, "w") as fh:
        json.dump({"order": [ST.STAGE],
                   "stages": {ST.STAGE: real["stages"][ST.STAGE]}}, fh)
    return path


def test_typed_readers():
    good0, makers0 = clean([record()])
    run = write_run(good0, makers0)
    recs, note = ST.load_records(run)
    check("list shape reads as a list", isinstance(recs, list) and note == "ok", (type(recs), note))
    # dict-only document: the D33 bug class — never passes, never coerces
    run2 = write_run({"not": "a record set"})
    recs2, note2 = ST.load_records(run2)
    check("dict-only doc is an explicit bad state",
          recs2 is None and note2.startswith("records-bad-shape"), (recs2, note2))
    ok, ev = ST.proven(run2)
    check("dict-only doc never proves the stage",
          not ok and ev["gate"] == "BLOCKED" and ev["required"] == list(ST.REQUIRED_CHECKS),
          ev)
    # legacy dict wrapper migrates with a note
    good, _makers = clean([record()])
    run3 = write_run({"records": good}, {"continuity-dna-1": "agent-writer-1"})
    recs3, note3 = ST.load_records(run3)
    check("legacy dict wrapper migrates",
          recs3 == good and note3 == "migrated:dict-wrapper", (note3, recs3))
    # missing / corrupt are explicit, never an empty pass
    run4 = write_run("MISSING")
    recs4, note4 = ST.load_records(run4)
    check("missing records named", recs4 is None and note4 == "records-missing", note4)
    run5 = write_run("CORRUPT")
    recs5, note5 = ST.load_records(run5)
    check("corrupt records named", recs5 is None and note5 == "records-corrupt", note5)
    # makers reader: missing = {} (gate fails MAKER_UNKNOWN, fail closed)
    m, mn = ST.load_makers(run4)
    check("missing makers = empty map with note", m == {} and mn == "makers-missing", (m, mn))


def test_required_checks_are_declared_not_received():
    # a record set that carries NO required check: the requirement survives
    good, makers = clean([record(check="creative", check_id="creative-1")])
    run = write_run(good, {"creative-1": "agent-writer-1"})
    res = ST.evaluate(run, "run1")
    codes = [f["code"] for f in res.get("failures", [])]
    check("missing declared check fails (MISSING_QC)",
          res["gate"] != "PASS" and "MISSING_QC" in codes, res)
    check("required set never derived from received records",
          res["required"] == list(ST.REQUIRED_CHECKS) and "continuity" in res["required"], res)
    # empty record list: still no shrinking
    run2 = write_run([], {})
    res2 = ST.evaluate(run2, "run1")
    check("empty evidence keeps the full required set",
          res2["gate"] != "PASS" and res2["required"] == list(ST.REQUIRED_CHECKS), res2)
    # self-review is not independent evidence
    good3, makers3 = clean([record(reviewer="agent-writer-1")])
    run3 = write_run(good3, makers3)
    res3 = ST.evaluate(run3, "run1")
    check("maker cannot review own record",
          res3["gate"] != "PASS"
          and any(f["code"] == "MAKER_SELF_REVIEW" for f in res3["failures"]), res3)


def test_gate_pass_and_proven():
    good, makers = clean([record()])
    run = write_run(good, makers)
    res = ST.evaluate(run, "run1")
    check("valid independent records pass the gate",
          res["gate"] == "PASS" and res["readers"]["records"] == "ok", res)
    ok, ev = ST.proven(run, "run1")
    check("proven() agrees with the gate", ok and ev["gate"] == "PASS", ev)
    ok2, ev2 = ST.proven(run, "other-run")
    check("wrong run_id never proves", not ok2, ev2)


def test_contract_declares_the_finished_bible():
    real = SG.load_contract()
    artifacts = real["stages"][ST.STAGE]["artifacts"]
    paths = [a["path"] for a in artifacts]
    check("the declared set is exactly the finished bible's records",
          sorted(paths) == sorted(ST.CONTRACT_ARTIFACTS), paths)
    approval = [a for a in artifacts if a["path"] == "character/approval.json"]
    check("the approval event must be the approved one",
          bool(approval) and approval[0].get("equals") == {"status": "approved"},
          approval)


def test_records_alone_never_advance():
    """S75-016: qc-records.json + makers.json alone are not a continuity bible."""
    good, makers = clean([record()])
    run = write_run(good, makers)
    make_store(run)
    res = ST.advance(run, contract=gate_contract())
    check("only qc records and makers: NOT advanced",
          res["outcome"] == "not-proven", res)
    check("the gate names the missing bible record",
          res.get("reason_code") == "ARTIFACT_MISSING"
          and "character/bible.json" in str(res.get("detail")), res)
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        check("row untouched",
              st.get("run1", "continuity-bible")["state"] == "NOT_STARTED")
    # and on the SHIPPED chain, the stage before it is still unproven: the
    # seal can never be opened by skipping the stages it follows.
    res2 = ST.advance(run)
    check("the shipped chain refuses a stage before its own seal is proven",
          res2["outcome"] == "not-proven"
          and res2.get("reason_code") == "PREVIOUS_STAGE_NOT_PROVEN", res2)


def test_advance_moves_the_row_and_reports_the_seven():
    good, makers = clean([record()])
    run = write_run(good, makers)
    write_finished_bible(run)
    make_store(run)
    contract = gate_contract()
    res = ST.advance(run, contract=contract)
    check("advance() outcome advanced", res["outcome"] == "advanced", res)
    check("the advancement carries the gate's sealed records",
          sorted(res["evidence"].get("sealed") or []) == sorted(ST.CONTRACT_ARTIFACTS),
          res["evidence"])
    check("continuity-bible row COMPLETE via guarded transitions",
          res["row"]["state"] == "COMPLETE", res["row"])
    seven = res["downstream"]
    check("seven downstream stages reported",
          sorted(seven) == sorted(ST.DOWNSTREAM_STAGES) and len(seven) == 7, seven)
    check("downstream rows readable with registry entrypoints",
          all(seven[s]["state"] == "NOT_STARTED" for s in ST.DOWNSTREAM_STAGES)
          and all(seven[s].get("entrypoint") for s in ST.DOWNSTREAM_STAGES), seven)
    again = ST.advance(run, contract=contract)
    check("advance() is idempotent", again["outcome"] == "already-complete", again)
    # no manual action was needed: nothing but the records + the one call
    status = ST.downstream_status(run)
    check("downstream_status lists all seven",
          sorted(status) == sorted(ST.DOWNSTREAM_STAGES), status)


def test_not_proven_never_advances():
    run = write_run("MISSING")
    make_store(run)
    res = ST.advance(run)
    check("missing evidence: no advancement",
          res["outcome"] == "not-proven", res)
    db = os.path.join(run, "control", "state.sqlite3")
    with SS.Store(db) as st:
        check("row untouched", st.get("run1", "continuity-bible")["state"] == "NOT_STARTED")


def test_register_wires_the_registry():
    registry = {}
    out = ST.register(registry)
    check("register() adds the reconciler",
          out is registry and registry.get("continuity-bible") is ST.proven, registry)
    good, makers = clean([record()])
    run = write_run(good, makers)
    ok, ev = registry["continuity-bible"](run, "run1")
    check("registered predicate is executable", ok, ev)


if __name__ == "__main__":
    test_typed_readers()
    test_required_checks_are_declared_not_received()
    test_gate_pass_and_proven()
    test_contract_declares_the_finished_bible()
    test_records_alone_never_advance()
    test_advance_moves_the_row_and_reports_the_seven()
    test_not_proven_never_advances()
    test_register_wires_the_registry()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)
