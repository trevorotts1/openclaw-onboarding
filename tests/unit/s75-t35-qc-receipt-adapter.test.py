#!/usr/bin/env python3
"""tests/unit/s75-t35-qc-receipt-adapter.test.py

S75-T35 — immediate unit QC and durable exact-head receipts.

WHAT THIS FILE PROVES (hermetic: tempdir only, no network, no repo writes):

  T1  a receipt for a DIFFERENT head                     -> QC_UNCONFIRMED (wrong_head)
  T2  captured console output with no structured claim   -> QC_UNCONFIRMED (unstructured_stdout)
  T3  author and approver are the same identity          -> QC_UNCONFIRMED (self_approved)
  T4  different identity, same lineage                   -> QC_UNCONFIRMED (self_approved)
  T5  repair receipt verified by its own repair author   -> QC_UNCONFIRMED (repair_author_not_independent)
  T6  abbreviated 7-hex head                             -> QC_UNCONFIRMED (head_not_full_sha)
  T7  CONTROL: the same receipt with the candidate head
      and an independent approver                        -> QC_CONFIRMED
      (a pass here is what makes T1-T6 mean something: the
      instrument can confirm, so a rejection is a rejection)
  T8  CONTROL: the T1 receipt differs from the T7 receipt
      ONLY in head_tested (proves the rejection is head-specific)
  T9  the same verdict twice                             -> second is a no-op; ledger bytes identical
  T10 a DIFFERENT verdict for the same unit+head         -> QC_CONFLICT, first verdict retained,
      repeat of that conflict                            -> no-op
  T11 an unsupported event type                          -> UnsupportedEvent, state unmodified
  T12 commit_verdict durability                          -> when the ack is returned, the ledger on
      disk already holds the transition (ack is never first)
  T13 a failing durable write                            -> DurabilityError, no acknowledgement
  T14 contract JSON parity                               -> evidence/qc-receipt-contract.json agrees
      with the adapter's constants

ROUND 2 (the round-1 verifier's findings):

  T15 'builder-lane-7' / 'Builder-Lane-7'                -> QC_UNCONFIRMED (self_approved),
      same for a cased lineage, and a genuinely distinct party is still admitted
  T16 EVERY rejection is durable                         -> wrong_head, head_not_full_sha and
      wrong_unit are each written to the ledger's rejections and acknowledged; a repeat is a
      no-op; nothing raises past
  T17 first-writer-wins kept + one way out of QC_CONFLICT -> an adjudication by a third identity
      AND lineage under a separate authorisation writes a resolution record, never touches the
      first verdict, is idempotent, and refuses a recorded party, a lineage collision,
      self-authorisation and a second resolution
  T18 a second distinct approver                         -> recorded with its own identity, and the
      receipt can only name approvers the ledger names
  T19 reason text is not identity                        -> formatting drift is a duplicate, never
      a conflict that demotes a unit
  T20 outcome is derived                                 -> a record asserting result=QC_CONFIRMED
      with a refusal code cannot confirm, through apply_verdict and apply_event alike
  T21 applied/duplicate/conflict/duplicate               -> byte-identical ledger in both orders,
      a single entry, one conflict result, no counter

QC FIX (opus-chain QC at regrade): T22 an adjudicator recorded in a later
entry — not only in the first verdict or the conflict parties — is refused.
Round-2 G5 hole: before the fix, entries[1:] parties were unchecked, so a
second distinct approver could adjudicate its own conflict.

Run: python3 tests/unit/s75-t35-qc-receipt-adapter.test.py
"""

import copy
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONTROL = os.path.join(ROOT, "CONTROL")
sys.path.insert(0, CONTROL)

import qc_receipt_adapter as A  # noqa: E402

HEAD = "9023e6b0e04cddb2c01a779c4bc0baef166d0a07"
OTHER_HEAD = "29819886a7ffce52abb988bf58eb1e42c85d7b51"

FAILS = []
CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append(name)
    if not condition:
        FAILS.append("%s %s" % (name, detail))


def base_receipt(**overrides):
    receipt = {
        "unit": "S75-T35",
        "head_tested": HEAD,
        "verdict": "PASS",
        "kind": "qc",
        "author": {"identity": "builder-lane-7", "lineage": "deepseek-chain"},
        "approver": {"identity": "verifier-lane-9", "lineage": "opus-chain"},
        "checks": [{"name": "focused-suite", "status": "pass"}],
    }
    receipt.update(overrides)
    return receipt


def test_wrong_head():
    r = A.evaluate_receipt(base_receipt(head_tested=OTHER_HEAD), HEAD)
    check("T1 wrong head rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T1 wrong head code", r["code"] == A.REASON_HEAD_MISMATCH, r)


def test_stdout_only():
    stdout = (
        "running focused suite...\n"
        "ok 14 tests\n"
        "PASS S75-T35 head=%s\n" % HEAD
    )
    r = A.evaluate_receipt(stdout, HEAD)
    check("T2 stdout only rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T2 stdout code", r["code"] == A.REASON_STRUCTURE, r)


def test_self_approved():
    same = {"identity": "builder-lane-7", "lineage": "deepseek-chain"}
    r = A.evaluate_receipt(base_receipt(author=same, approver=dict(same)), HEAD)
    check("T3 self-approved rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T3 self-approved code", r["code"] == A.REASON_SELF_APPROVED, r)

    family = {
        "identity": "other-worker",
        "lineage": "opus-chain",
    }
    r = A.evaluate_receipt(
        base_receipt(author={"identity": "a1", "lineage": "opus-chain"}, approver=family),
        HEAD,
    )
    check("T4 same lineage rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T4 same lineage code", r["code"] == A.REASON_SELF_APPROVED, r)


def test_repair_author_dependence():
    author = {"identity": "fixer-2", "lineage": "opus-chain"}
    r = A.evaluate_receipt(
        base_receipt(
            kind="repair",
            author={"identity": "cli-lane-3", "lineage": "deepseek-chain"},
            repair_author=author,
        ),
        HEAD,
        kind="repair",
    )
    check("T5 repair author dependence rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T5 repair code", r["code"] == A.REASON_REPAIR_AUTHOR_DEPENDENT, r)


def test_abbreviated_head():
    r = A.evaluate_receipt(base_receipt(head_tested=HEAD[:7]), HEAD)
    check("T6 abbreviated head rejects", r["result"] == A.QC_UNCONFIRMED, r)
    check("T6 abbreviated code", r["code"] == A.REASON_HEAD_NOT_FULL_SHA, r)


def test_known_good_control():
    r = A.evaluate_receipt(base_receipt(), HEAD)
    check("T7 known-good control confirms", r["result"] == A.QC_CONFIRMED, r)
    only_head = copy.deepcopy(base_receipt())
    only_head["head_tested"] = OTHER_HEAD
    diff = [k for k in only_head if only_head[k] != base_receipt()[k]]
    check("T8 rejection is head-specific", diff == ["head_tested"], diff)


def test_duplicate_idempotent(tmp):
    ledger = os.path.join(tmp, "ledger.json")
    rpath = os.path.join(tmp, "receipt.json")
    rec = A.evaluate_receipt(base_receipt(), HEAD)

    ack1 = A.commit_verdict(base_receipt(), HEAD, rpath, ledger)
    after_one = open(ledger, "rb").read()
    ack2 = A.commit_verdict(base_receipt(), HEAD, rpath, ledger)
    after_two = open(ledger, "rb").read()

    check("T9 first verdict applied", ack1["outcome"] == "applied", ack1)
    check("T9 second verdict duplicate", ack2["outcome"] == "duplicate", ack2)
    check("T9 ledger bytes identical", after_one == after_two, "ledger changed on duplicate")
    state = json.loads(after_two)
    check("T9 single entry", len(state["entries"]) == 1, state)
    check("T9 status confirmed", state["status"] == A.QC_CONFIRMED, state)
    check("T9 record matches evaluation", rec["result"] == A.QC_CONFIRMED, rec)
    return ledger, state


def test_conflict(ledger, state):
    conflicting = A._unconfirmed(A.REASON_HEAD_MISMATCH, "second lane says no", unit="S75-T35")
    conflicting["head_tested"] = HEAD
    outcome, new = A.apply_verdict(state, conflicting)
    check("T10 different verdict is a conflict", outcome == "conflict", outcome)
    check("T10 unit becomes conflict", new["status"] == A.QC_CONFLICT, new)
    check("T10 first verdict retained", new["verdict"]["result"] == A.QC_CONFIRMED, new["verdict"])
    check("T10 first verdict not overwritten", new["verdict"]["reason"] != "second lane says no", new)
    check("T10 conflict needs third authority", new["conflict"]["required_resolution"] == "distinct third authority", new["conflict"])

    outcome2, again = A.apply_verdict(new, conflicting)
    check("T10 repeat conflict is a no-op", outcome2 == "duplicate" and again is new, outcome2)
    check("T10 conflict result set is stable", len(again["conflict"]["results"]) == 1, again["conflict"])


def test_unsupported_event():
    state = A.build_state("S75-T35", HEAD)
    before = json.dumps(state, sort_keys=True)
    raised = False
    try:
        A.apply_event(state, {"type": "promote_to_pass", "unit": "S75-T35"})
    except A.UnsupportedEvent:
        raised = True
    after = json.dumps(state, sort_keys=True)
    check("T11 unsupported event refuses", raised, "no UnsupportedEvent")
    check("T11 state unmodified", before == after, "state changed on refused event")


def test_durable_before_ack(tmp):
    ledger = os.path.join(tmp, "dur-ledger.json")
    rpath = os.path.join(tmp, "dur-receipt.json")
    ack = A.commit_verdict(base_receipt(), HEAD, rpath, ledger)
    on_disk = json.load(open(ledger))
    check("T12 ack claims durability", ack["durable"] is True, ack)
    check("T12 ledger already written at ack", on_disk["status"] == ack["ledger_status"], on_disk)
    check("T12 receipt on disk", os.path.exists(rpath), rpath)
    check("T12 receipt carries exact head", json.load(open(rpath))["head_tested"] == HEAD)


def test_durability_failure(tmp):
    if os.geteuid() == 0:
        check("T13 durability failure", True, "skipped: running as root")
        return
    blocked = os.path.join(tmp, "blocked")
    os.makedirs(blocked, exist_ok=True)
    os.chmod(blocked, 0o500)
    raised = False
    ack = None
    try:
        ack = A.commit_verdict(
            base_receipt(), HEAD, os.path.join(blocked, "r.json"), os.path.join(blocked, "l.json")
        )
    except A.DurabilityError:
        raised = True
    finally:
        os.chmod(blocked, 0o700)
    check("T13 failed write raises", raised, "no DurabilityError")
    check("T13 no acknowledgement", ack is None, ack)


def test_casing_variant_self_approval():
    """T15 relabelling a lane is not independence (QC-AND-REPAIR.md:11)."""
    cased_identity = base_receipt(
        author={"identity": "builder-lane-7", "lineage": "deepseek-chain"},
        approver={"identity": "Builder-Lane-7", "lineage": "opus-chain"},
    )
    r = A.evaluate_receipt(cased_identity, HEAD)
    check("T15 cased identity self-approves", r["result"] == A.QC_UNCONFIRMED, r)
    check("T15 cased identity code", r["code"] == A.REASON_SELF_APPROVED, r)

    cased_lineage = base_receipt(
        author={"identity": "worker-a", "lineage": "deepseek-chain"},
        approver={"identity": "worker-b", "lineage": "Deepseek-Chain"},
    )
    r = A.evaluate_receipt(cased_lineage, HEAD)
    check("T15 cased lineage self-approves", r["result"] == A.QC_UNCONFIRMED, r)
    check("T15 cased lineage code", r["code"] == A.REASON_SELF_APPROVED, r)

    both = base_receipt(
        author={"identity": "builder-lane-7", "lineage": "deepseek-chain"},
        approver={"identity": "Builder-Lane-7", "lineage": "Deepseek-Chain"},
    )
    r = A.evaluate_receipt(both, HEAD)
    check("T15 both halves cased", r["result"] == A.QC_UNCONFIRMED, r)

    r = A.evaluate_receipt(base_receipt(), HEAD)
    check("T15 distinct party still admitted", r["result"] == A.QC_CONFIRMED, r)

def test_every_rejection_durable(tmp):
    """T16 every rejection reaches the ledger and is acknowledged."""
    ledger = os.path.join(tmp, "rej-ledger.json")
    rpath = os.path.join(tmp, "rej-receipt.json")

    ack = A.commit_verdict(base_receipt(head_tested=OTHER_HEAD), HEAD, rpath, ledger)
    on_disk = json.load(open(ledger))
    check("T16 wrong head acknowledged", ack["acknowledged"] is True, ack)
    check("T16 wrong head outcome", ack["outcome"] == "rejected", ack)
    check(
        "T16 wrong head named",
        ack["result"] == A.QC_UNCONFIRMED and ack["code"] == A.REASON_HEAD_MISMATCH,
        ack,
    )
    check("T16 receipt written", os.path.exists(rpath), rpath)
    check(
        "T16 wrong head in ledger",
        any(e["code"] == A.REASON_HEAD_MISMATCH for e in on_disk.get("rejections", [])),
        on_disk.get("rejections"),
    )

    ack2 = A.commit_verdict(base_receipt(head_tested=HEAD[:7]), HEAD, rpath, ledger)
    on_disk = json.load(open(ledger))
    check(
        "T16 abbreviated head named",
        ack2["acknowledged"] is True
        and ack2["result"] == A.QC_UNCONFIRMED
        and ack2["code"] == A.REASON_HEAD_NOT_FULL_SHA,
        ack2,
    )
    check(
        "T16 abbreviated head in ledger",
        any(e["code"] == A.REASON_HEAD_NOT_FULL_SHA for e in on_disk.get("rejections", [])),
        on_disk.get("rejections"),
    )

    before = open(ledger, "rb").read()
    ack3 = A.commit_verdict(base_receipt(head_tested=OTHER_HEAD), HEAD, rpath, ledger)
    check("T16 repeat rejection is a no-op", ack3["outcome"] == "duplicate", ack3)
    check("T16 repeat rejection byte-stable", open(ledger, "rb").read() == before)

    ack4 = A.commit_verdict(base_receipt(unit="S75-T36"), HEAD, rpath, ledger)
    on_disk = json.load(open(ledger))
    check(
        "T16 foreign unit named",
        ack4["outcome"] == "rejected" and ack4["code"] == A.REASON_WRONG_UNIT,
        ack4,
    )
    check(
        "T16 foreign unit in ledger",
        any(e["code"] == A.REASON_WRONG_UNIT for e in on_disk.get("rejections", [])),
        on_disk.get("rejections"),
    )
    check("T16 ledger keeps its own unit", on_disk["unit"] == "S75-T35", on_disk["unit"])

def test_adjudication(tmp):
    """T17 first-writer-wins kept, with one separately authorised way out."""
    ledger = os.path.join(tmp, "adj-ledger.json")
    rpath = os.path.join(tmp, "adj-receipt.json")
    respath = os.path.join(tmp, "adj-resolution.json")

    A.commit_verdict(base_receipt(), HEAD, rpath, ledger)
    ack = A.commit_verdict(
        base_receipt(verdict="FAIL", checks=[{"name": "mine", "status": "fail"}]),
        HEAD,
        rpath,
        ledger,
    )
    st = json.load(open(ledger))
    check("T17 conflict raised", ack["outcome"] == "conflict", ack)
    check("T17 unit is conflict", st["status"] == A.QC_CONFLICT, st["status"])
    check("T17 first verdict retained", st["verdict"]["result"] == A.QC_CONFIRMED, st["verdict"])
    check("T17 parties recorded", len(st["conflict"]["parties"]) >= 2, st["conflict"])

    def adjudicate(identity, lineage, authorisation="operator-order-2026-10-25"):
        return A.commit_adjudication(
            {
                "type": "adjudication",
                "adjudicator": {"identity": identity, "lineage": lineage},
                "authorisation": authorisation,
                "resolution": {"result": A.QC_UNCONFIRMED, "reason": "reviewed by hand"},
            },
            respath,
            ledger,
        )

    def refused(identity, lineage, authorisation, name):
        try:
            adjudicate(identity, lineage, authorisation)
        except A.RefusedRecord:
            check(name, True)
            return
        check(name, False, "no refusal")

    refused("verifier-lane-9", "opus-chain", "operator-order-2026-10-25",
            "T17 approver may not adjudicate")
    refused("builder-lane-7", "deepseek-chain", "operator-order-2026-10-25",
            "T17 author may not adjudicate")
    refused("third-lane-3", "opus-chain", "operator-order-2026-10-25",
            "T17 lineage collision refused")
    refused("third-lane-3", "judge-chain", "third-lane-3",
            "T17 self-authorisation refused")

    ack = adjudicate("third-lane-3", "judge-chain")
    st = json.load(open(ledger))
    check("T17 adjudication applied", ack["outcome"] == "applied", ack)
    check("T17 adjudication durable", ack["durable"] is True, ack)
    check(
        "T17 resolution recorded",
        st["resolution"]["adjudicator"]["identity"] == "third-lane-3",
        st["resolution"],
    )
    check("T17 first verdict untouched", st["verdict"]["result"] == A.QC_CONFIRMED, st["verdict"])
    check("T17 unit unstranded", st["status"] == A.QC_UNCONFIRMED, st["status"])
    check("T17 resolution is not an entry", len(st["entries"]) == 1, st["entries"])

    before = open(ledger, "rb").read()
    ack2 = adjudicate("third-lane-3", "judge-chain")
    check("T17 adjudication idempotent", ack2["outcome"] == "duplicate", ack2)
    check("T17 adjudication byte-stable", open(ledger, "rb").read() == before)

    refused("fourth-lane-4", "judge-chain-two", "operator-order-2",
            "T17 first resolution wins")
    check("T17 refused resolution wrote nothing", open(ledger, "rb").read() == before)

def test_second_approver_recorded(tmp):
    """T18 a distinct second approver keeps its identity; files cannot disagree."""
    ledger = os.path.join(tmp, "sa-ledger.json")
    rpath = os.path.join(tmp, "sa-receipt.json")
    A.commit_verdict(base_receipt(), HEAD, rpath, ledger)
    ack = A.commit_verdict(
        base_receipt(approver={"identity": "verifier-lane-11", "lineage": "opus-chain"}),
        HEAD,
        rpath,
        ledger,
    )
    st = json.load(open(ledger))
    receipt = json.load(open(rpath))
    check("T18 second approver applied", ack["outcome"] == "applied", ack)
    check("T18 entries carry both", len(st["entries"]) == 2, st["entries"])
    check(
        "T18 second identity kept",
        st["entries"][1]["approver"]["identity"] == "verifier-lane-11",
        st["entries"][1],
    )
    check(
        "T18 first verdict still the verdict",
        st["verdict"]["approver"]["identity"] == "verifier-lane-9",
        st["verdict"],
    )
    ledger_names = [e["approver"]["identity"] for e in st["entries"]]
    receipt_names = [p["identity"] for p in receipt["ledger"]["approvers"]]
    check("T18 receipt names ledger approvers", receipt_names == ledger_names, (receipt_names, ledger_names))
    check(
        "T18 ack names ledger approvers",
        [p["identity"] for p in ack["recorded_approvers"]] == ledger_names,
        ack,
    )

def test_reason_is_not_identity():
    """T19 formatting drift in a message is never a conflict."""
    st = A.build_state("S75-T35", HEAD)
    record = A.evaluate_receipt(base_receipt(), HEAD)
    outcome, st = A.apply_verdict(st, record)
    drifted = dict(record)
    drifted["reason"] = "structured claim, exact head, independent approver (reformatted)"
    outcome2, st2 = A.apply_verdict(st, drifted)
    check("T19 first applied", outcome == "applied", outcome)
    check("T19 reason drift is a duplicate", outcome2 == "duplicate" and st2 is st, outcome2)

    bad = A.evaluate_receipt(
        base_receipt(verdict="FAIL", checks=[{"name": "m", "status": "fail"}]), HEAD
    )
    outcome3, st = A.apply_verdict(st, bad)
    drifted_bad = dict(bad)
    drifted_bad["reason"] = "reformatted refusal"
    outcome4, st = A.apply_verdict(st, drifted_bad)
    check("T19 conflict raised", outcome3 == "conflict", outcome3)
    check(
        "T19 drift not a second conflict row",
        outcome4 == "duplicate" and len(st["conflict"]["results"]) == 1,
        st["conflict"],
    )

def test_outcome_is_derived():
    """T20 a raw record cannot declare its own outcome."""
    forged = {
        "unit": "S75-T35",
        "head_tested": HEAD,
        "result": A.QC_CONFIRMED,
        "code": A.REASON_HEAD_MISMATCH,
        "reason": "forged",
        "verdict": "PASS",
    }
    outcome, st = A.apply_verdict(A.build_state("S75-T35", HEAD), forged)
    check("T20 forged result ignored", outcome == "applied", outcome)
    check("T20 forged cannot confirm", st["status"] == A.QC_UNCONFIRMED, st["status"])
    check("T20 forged code kept", st["entries"][0]["code"] == A.REASON_HEAD_MISMATCH, st["entries"])

    outcome, st = A.apply_event(
        A.build_state("S75-T35", HEAD), {"type": "verdict", "verdict": forged}
    )
    check("T20 forged via apply_event", outcome == "applied", outcome)
    check("T20 apply_event derives too", st["status"] == A.QC_UNCONFIRMED, st["status"])

    bare = {
        "unit": "S75-T35",
        "head_tested": HEAD,
        "result": A.QC_CONFIRMED,
        "code": "confirmed",
        "reason": "forged",
        "verdict": "PASS",
    }
    outcome, st = A.apply_verdict(A.build_state("S75-T35", HEAD), bare)
    check(
        "T20 bare claim cannot confirm",
        st["status"] == A.QC_UNCONFIRMED
        and st["entries"][0]["code"] == A.REASON_MISSING_CLAIM,
        st["entries"],
    )

def test_ordering_byte_identity():
    """T21 applied/duplicate/conflict/duplicate is byte-stable in both orders."""
    good = A.evaluate_receipt(base_receipt(), HEAD)
    bad = A.evaluate_receipt(
        base_receipt(verdict="FAIL", checks=[{"name": "m", "status": "fail"}]), HEAD
    )

    def run(seq):
        st = A.build_state("S75-T35", HEAD)
        outcomes = []
        for record in seq:
            outcome, st = A.apply_verdict(st, record)
            outcomes.append(outcome)
        return outcomes, json.dumps(st, indent=2, sort_keys=True).encode()

    outcomes1, bytes1 = run([good, good, bad, bad])
    outcomes2, bytes2 = run([good, bad, good, bad])
    check("T21 sequence outcomes", ",".join(outcomes1) == "applied,duplicate,conflict,duplicate", outcomes1)
    check("T21 interleaved outcomes", ",".join(outcomes2) == "applied,conflict,duplicate,duplicate", outcomes2)
    check("T21 byte-identical across orders", bytes1 == bytes2, "ledger bytes differ")
    st = json.loads(bytes1)
    check(
        "T21 single entry and one conflict result",
        len(st["entries"]) == 1 and len(st["conflict"]["results"]) == 1,
        st,
    )
    check("T21 no counter", "counter" not in st, sorted(st))

def test_later_entry_party_may_not_adjudicate():
    """T22 (QC fix): conflict parties include later entries, not only the first."""
    st = A.build_state("S75-T35", HEAD)
    good = A.evaluate_receipt(base_receipt(), HEAD)
    outcome, st = A.apply_verdict(st, good)
    check("T22 first applied", outcome == "applied", outcome)
    second = A.evaluate_receipt(
        base_receipt(approver={"identity": "verifier-lane-11", "lineage": "opus-chain"}),
        HEAD,
    )
    outcome, st = A.apply_verdict(st, second)
    check("T22 second recorded", outcome == "applied" and len(st["entries"]) == 2, outcome)
    bad = A.evaluate_receipt(
        base_receipt(verdict="FAIL", checks=[{"name": "m", "status": "fail"}]), HEAD
    )
    outcome, st = A.apply_verdict(st, bad)
    check("T22 conflict raised", outcome == "conflict" and st["status"] == A.QC_CONFLICT, outcome)

    def attempt(identity, lineage):
        try:
            A.apply_event(
                st,
                {
                    "type": "adjudication",
                    "adjudicator": {"identity": identity, "lineage": lineage},
                    "authorisation": "operator-order-2026-10-26",
                    "resolution": {"result": A.QC_UNCONFIRMED, "reason": "hand review"},
                },
            )
        except A.RefusedRecord:
            return "refused"
        return "applied"

    check("T22 later entry party refused", attempt("verifier-lane-11", "opus-chain") == "refused")
    check("T22 verdict author refused", attempt("builder-lane-7", "deepseek-chain") == "refused")
    outcome, st2 = A.apply_event(
        st,
        {
            "type": "adjudication",
            "adjudicator": {"identity": "arbiter-d7", "lineage": "arbiter-chain"},
            "authorisation": "operator-order-2026-10-26",
            "resolution": {"result": A.QC_UNCONFIRMED, "reason": "hand review"},
        },
    )
    check("T22 third authority admitted", outcome == "applied" and st2["status"] == A.QC_UNCONFIRMED, outcome)
    check("T22 first verdict untouched", st2["verdict"]["result"] == A.QC_CONFIRMED, st2["verdict"])

def test_contract_parity():
    path = os.path.join(ROOT, "evidence", "qc-receipt-contract.json")
    contract = json.load(open(path))
    check(
        "T14 confirmable verdicts match",
        tuple(contract["confirmable_verdicts"]) == A.CONFIRMABLE_VERDICTS,
        contract["confirmable_verdicts"],
    )
    check(
        "T14 required fields match",
        tuple(contract["required_claim_fields"]) == A.REQUIRED_CLAIM_FIELDS,
        contract["required_claim_fields"],
    )
    check(
        "T14 supported events match",
        tuple(contract["supported_events"]) == A.SUPPORTED_EVENTS,
        contract["supported_events"],
    )
    codes = set(contract["rejection_codes"])
    adapter_codes = {
        A.REASON_STRUCTURE,
        A.REASON_MISSING_CLAIM,
        A.REASON_HEAD_NOT_FULL_SHA,
        A.REASON_HEAD_MISMATCH,
        A.REASON_VERDICT_NOT_CONFIRMABLE,
        A.REASON_IDENTITY_MISSING,
        A.REASON_SELF_APPROVED,
        A.REASON_REPAIR_AUTHOR_DEPENDENT,
        A.REASON_NO_CHECKS,
        A.REASON_WRONG_UNIT,
    }
    check("T14 rejection codes match", codes == adapter_codes, sorted(codes ^ adapter_codes))
    check(
        "T14 ledger states match",
        set(contract["ledger_states"]) == {A.QC_CONFIRMED, A.QC_UNCONFIRMED, A.QC_CONFLICT},
        contract["ledger_states"],
    )


def main():
    tmp = tempfile.mkdtemp(prefix="s75-t35-")
    try:
        test_wrong_head()
        test_stdout_only()
        test_self_approved()
        test_repair_author_dependence()
        test_abbreviated_head()
        test_known_good_control()
        ledger, state = test_duplicate_idempotent(tmp)
        test_conflict(ledger, state)
        test_unsupported_event()
        test_durable_before_ack(tmp)
        test_durability_failure(tmp)
        test_casing_variant_self_approval()
        test_every_rejection_durable(tmp)
        test_adjudication(tmp)
        test_second_approver_recorded(tmp)
        test_reason_is_not_identity()
        test_outcome_is_derived()
        test_ordering_byte_identity()
        test_later_entry_party_may_not_adjudicate()
        test_contract_parity()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("checks run: %d" % len(CHECKS))
    if FAILS:
        print("FAILED %d:" % len(FAILS))
        for f in FAILS:
            print("  - " + f)
        return 1
    print("PASS: S75-T35 qc receipt adapter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
