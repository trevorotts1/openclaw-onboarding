#!/usr/bin/env python3
"""rr_step_gate.py - step gate for the AI that RUNS Rescue Rangers cases.

DRAFT. Not installed anywhere. Target home after build:
  onboarding repo  23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rr_step_gate.py

WHY: the runner must not be able to say a step is done, or not needed, without
a real artifact. No grep, no echo "PASS". Each step of a case is a JSON file in
the case folder. A step can only be RECORDED through this script, and a step
can only START when this script confirms every earlier step's artifact exists,
parses, belongs to this ticket, carries its required fields, and is chained to
the artifact before it by a sha256 digest. Evidence files named in an artifact
must exist and be non-empty. Anything else is REFUSED with exit 20.

CASE FOLDER:  <cases-root>/<ticket_id>/
  01-intake.json     the escalation exactly as received
  02-cap.json        the live daily-cap reading for this box
  03-triage.json     severity, failure class, what the box already tried
  04-decision.json   the route: tell_agent | fix_ourselves | page_operator | not_an_incident
  05-work.json       what was done (the instruction text sent, or the fix applied)
  06-verify.json     the acceptance check that was re-run, and its result
  07-reply.json      the outcome delivered to the client's agent, with the delivery receipt
  08-close.json      the closing state written to the ledger, with the ledger receipt

REQUIRED FIELDS (all must be present and non-empty; lists must be non-empty):
  01 ticket_id, box_slug, problem, received_at, payload_sha256
  02 ticket_id, box_slug, cap_source, used_today, cap_limit, read_at
       cap_source must be "rr_cap_counters" (the live table). "rescue_ledger.py"
       is the retired drill ledger and is REFUSED here.
  03 ticket_id, severity (P1|P2|P3), failure_class, already_tried_reviewed (true),
       evidence_files (list of paths)
  04 ticket_id, route, rule_id, reason, one_way_door (true|false)
       rule_id must be one of the ids in decision-rules.json (this script's folder)
       and route must be that rule's route
       route=page_operator is required when one_way_door is true
  05 ticket_id, route, summary, evidence_files
       route must equal the route in 04
  06 ticket_id, check_id, result (passed|failed|not_applicable), evidence_files
       not_applicable is allowed only when 04.route is tell_agent or not_an_incident
  07 ticket_id, outcome (solved|owner_action|answer|specialist_follow_up),
       owner_message, delivery_receipt
  08 ticket_id, final_status, ledger_receipt

Every artifact also carries, added by this script (never by the runner):
  step, recorded_at, prev_sha256 (digest of the previous step's file; "" for 01),
  body_sha256 (digest of the runner-supplied body)

COMMANDS
  check  --cases-root DIR --ticket ID --step N
         exit 0 only when steps 1..N-1 are all valid. Run this BEFORE starting step N.
  record --cases-root DIR --ticket ID --step N --from FILE
         validates steps 1..N-1, validates FILE for step N, then writes it atomically.
  audit  --cases-root DIR --ticket ID
         validates every step that exists and prints which step is next.

Exit codes: 0 allowed / recorded, 20 REFUSED (a prior step is missing or invalid,
or the new artifact is invalid), 2 usage or filesystem failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time

STEPS = {
    1: ("01-intake.json", ["ticket_id", "box_slug", "problem", "received_at", "payload_sha256"]),
    2: ("02-cap.json", ["ticket_id", "box_slug", "cap_source", "used_today", "cap_limit", "read_at"]),
    3: ("03-triage.json", ["ticket_id", "severity", "failure_class", "already_tried_reviewed", "evidence_files"]),
    4: ("04-decision.json", ["ticket_id", "route", "rule_id", "reason", "one_way_door"]),
    5: ("05-work.json", ["ticket_id", "route", "summary", "evidence_files"]),
    6: ("06-verify.json", ["ticket_id", "check_id", "result", "evidence_files"]),
    7: ("07-reply.json", ["ticket_id", "outcome", "owner_message", "delivery_receipt"]),
    8: ("08-close.json", ["ticket_id", "final_status", "ledger_receipt"]),
}
ROUTES = {"tell_agent", "fix_ourselves", "page_operator", "not_an_incident"}
OUTCOMES = {"solved", "owner_action", "answer", "specialist_follow_up"}
RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decision-rules.json")
_RULES: dict[str, dict] | None = None


class Refused(Exception):
    pass


def sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_obj(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as exc:
        raise Refused("cannot read %s: %s" % (path, exc.strerror))
    except ValueError as exc:
        raise Refused("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise Refused("%s is not a JSON object" % path)
    return doc


def present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (str, list, dict)):
        return len(value) > 0
    return False


def decision_rules() -> dict[str, dict]:
    """The rule table from decision-rules.json beside this script, keyed by id."""
    global _RULES
    if _RULES is None:
        try:
            with open(RULES_PATH, encoding="utf-8") as fh:
                doc = json.load(fh)
        except OSError as exc:
            raise Refused("cannot read the decision rules %s: %s" % (RULES_PATH, exc.strerror))
        except ValueError as exc:
            raise Refused("%s is not valid JSON: %s" % (RULES_PATH, exc))
        rows = doc.get("rules") if isinstance(doc, dict) else None
        if not isinstance(rows, list) or not rows:
            raise Refused("%s has no rules list" % RULES_PATH)
        _RULES = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("id") or not row.get("route"):
                raise Refused("%s has a rule without an id or a route" % RULES_PATH)
            _RULES[str(row["id"])] = row
    return _RULES


def check_evidence(doc: dict, base: str, label: str) -> None:
    files = doc.get("evidence_files")
    if files is None:
        return
    if not isinstance(files, list) or not files:
        raise Refused("%s: evidence_files must be a non-empty list" % label)
    for f in files:
        p = f if os.path.isabs(str(f)) else os.path.join(base, str(f))
        if not os.path.isfile(p):
            raise Refused("%s: evidence file does not exist: %s" % (label, p))
        if os.path.getsize(p) == 0:
            raise Refused("%s: evidence file is empty: %s" % (label, p))


def validate_body(step: int, body: dict, ticket: str, case_dir: str, earlier: dict[int, dict]) -> None:
    name, required = STEPS[step]
    for key in required:
        if key not in body or not present(body[key]):
            raise Refused("%s: required field %r is missing or empty" % (name, key))
    if body["ticket_id"] != ticket:
        raise Refused("%s: ticket_id %r does not match this case %r" % (name, body["ticket_id"], ticket))
    check_evidence(body, case_dir, name)

    if step == 2:
        if body["cap_source"] != "rr_cap_counters":
            raise Refused("02-cap.json: cap_source must be the live table rr_cap_counters, not %r" % body["cap_source"])
        for k in ("used_today", "cap_limit"):
            if isinstance(body[k], bool) or not isinstance(body[k], int) or body[k] < 0:
                raise Refused("02-cap.json: %s must be a non-negative whole number" % k)
    if step == 3:
        if body["severity"] not in ("P1", "P2", "P3"):
            raise Refused("03-triage.json: severity must be P1, P2 or P3")
        if body["already_tried_reviewed"] is not True:
            raise Refused("03-triage.json: already_tried_reviewed must be true (read what the box already tried)")
    if step == 4:
        if body["route"] not in ROUTES:
            raise Refused("04-decision.json: route must be one of %s" % sorted(ROUTES))
        if not isinstance(body["one_way_door"], bool):
            raise Refused("04-decision.json: one_way_door must be true or false")
        if body["one_way_door"] and body["route"] != "page_operator":
            raise Refused("04-decision.json: a one-way door must be routed to page_operator")
        rules = decision_rules()
        rule = rules.get(str(body["rule_id"]))
        if rule is None:
            raise Refused("04-decision.json: rule_id %r is not one of the rules in decision-rules.json (%s)"
                          % (body["rule_id"], ", ".join(sorted(rules))))
        if body["route"] != rule["route"]:
            raise Refused("04-decision.json: rule %s routes to %r, not %r"
                          % (body["rule_id"], rule["route"], body["route"]))
        cap = earlier[2]
        if cap["used_today"] >= cap["cap_limit"] and body["route"] not in ("page_operator", "not_an_incident"):
            raise Refused("04-decision.json: this box is at its daily cap; the only routes allowed are page_operator or not_an_incident")
    if step == 5 and body["route"] != earlier[4]["route"]:
        raise Refused("05-work.json: route %r differs from the decision %r" % (body["route"], earlier[4]["route"]))
    if step == 6:
        if body["result"] not in ("passed", "failed", "not_applicable"):
            raise Refused("06-verify.json: result must be passed, failed or not_applicable")
        if body["result"] == "not_applicable" and earlier[4]["route"] == "fix_ourselves":
            raise Refused("06-verify.json: a fix we applied ourselves must be verified; not_applicable is refused")
    if step == 7:
        if body["outcome"] not in OUTCOMES:
            raise Refused("07-reply.json: outcome must be one of %s" % sorted(OUTCOMES))
        if body["outcome"] == "solved" and earlier[6]["result"] != "passed":
            raise Refused("07-reply.json: outcome solved requires 06-verify.json result passed")
        if len(str(body["owner_message"]).strip()) < 20:
            raise Refused("07-reply.json: owner_message is too short to tell the owner anything")


def validate_chain(case_dir: str, ticket: str, upto: int) -> dict[int, dict]:
    """Validate steps 1..upto. Returns the loaded artifacts keyed by step."""
    docs: dict[int, dict] = {}
    prev_sha = ""
    prev_time = 0
    for step in range(1, upto + 1):
        name, _ = STEPS[step]
        path = os.path.join(case_dir, name)
        if not os.path.isfile(path):
            raise Refused("step %d has not been done: %s does not exist" % (step, path))
        doc = load(path)
        body = doc.get("body")
        if not isinstance(body, dict):
            raise Refused("%s has no body object" % name)
        if doc.get("step") != step:
            raise Refused("%s says it is step %r" % (name, doc.get("step")))
        if doc.get("prev_sha256", None) != prev_sha:
            raise Refused("%s is not chained to the step before it (prev_sha256 mismatch); it was edited or written by hand" % name)
        if doc.get("body_sha256") != sha_obj(body):
            raise Refused("%s body was changed after it was recorded" % name)
        rec = doc.get("recorded_at")
        if isinstance(rec, bool) or not isinstance(rec, int) or rec < prev_time:
            raise Refused("%s has a recorded_at earlier than the step before it" % name)
        validate_body(step, body, ticket, case_dir, {k: v["body"] for k, v in docs.items()})
        docs[step] = doc
        prev_sha = sha_file(path)
        prev_time = rec
    return docs


def case_dir_for(root: str, ticket: str) -> str:
    safe = "".join(c for c in ticket if c.isalnum() or c in "-_.")
    if not safe or safe != ticket or ticket.startswith("."):
        raise Refused("ticket id %r contains characters that are not letters, digits, dash, underscore or dot" % ticket)
    return os.path.join(root, safe)


def cmd_check(a) -> int:
    d = case_dir_for(a.cases_root, a.ticket)
    validate_chain(d, a.ticket, a.step - 1)
    print("ALLOWED: steps 1 to %d are verified for %s; step %d may start" % (a.step - 1, a.ticket, a.step))
    return 0


def cmd_record(a) -> int:
    d = case_dir_for(a.cases_root, a.ticket)
    docs = validate_chain(d, a.ticket, a.step - 1)
    name, _ = STEPS[a.step]
    target = os.path.join(d, name)
    if os.path.exists(target):
        raise Refused("%s already exists; a recorded step is never overwritten" % target)
    body = load(a.from_file)
    validate_body(a.step, body, a.ticket, d, {k: v["body"] for k, v in docs.items()})
    prev = sha_file(os.path.join(d, STEPS[a.step - 1][0])) if a.step > 1 else ""
    doc = {"step": a.step, "recorded_at": int(time.time()), "prev_sha256": prev,
           "body_sha256": sha_obj(body), "body": body}
    os.makedirs(d, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".step-", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, indent=1)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    print("RECORDED: %s" % target)
    return 0


def cmd_audit(a) -> int:
    d = case_dir_for(a.cases_root, a.ticket)
    last = 0
    for step in range(1, len(STEPS) + 1):
        if os.path.isfile(os.path.join(d, STEPS[step][0])):
            last = step
    validate_chain(d, a.ticket, last)
    nxt = "the case is complete" if last == len(STEPS) else "next step is %d (%s)" % (last + 1, STEPS[last + 1][0])
    print("VALID: steps 1 to %d verified for %s; %s" % (last, a.ticket, nxt))
    return 0


def selftest() -> int:
    ok = True
    with tempfile.TemporaryDirectory() as root:
        t = "RR-000999"
        d = os.path.join(root, t)
        os.makedirs(d)
        ev = os.path.join(d, "evidence.txt")
        with open(ev, "w") as fh:
            fh.write("real evidence\n")

        def rec(step: int, body: dict) -> int:
            src = os.path.join(root, "in.json")
            with open(src, "w") as fh:
                json.dump(body, fh)
            ns = argparse.Namespace(cases_root=root, ticket=t, step=step, from_file=src)
            try:
                return cmd_record(ns)
            except Refused:
                return 20

        ok &= rec(2, {"ticket_id": t}) == 20                        # cannot skip step 1
        ok &= rec(1, {"ticket_id": t, "box_slug": "box-a", "problem": "p", "received_at": "x", "payload_sha256": "y"}) == 0
        ok &= rec(2, {"ticket_id": t, "box_slug": "box-a", "cap_source": "rescue_ledger.py", "used_today": 1, "cap_limit": 25, "read_at": "x"}) == 20
        ok &= rec(2, {"ticket_id": t, "box_slug": "box-a", "cap_source": "rr_cap_counters", "used_today": 1, "cap_limit": 25, "read_at": "x"}) == 0
        ok &= rec(3, {"ticket_id": t, "severity": "P2", "failure_class": "c", "already_tried_reviewed": True, "evidence_files": ["missing.txt"]}) == 20
        ok &= rec(3, {"ticket_id": t, "severity": "P2", "failure_class": "c", "already_tried_reviewed": True, "evidence_files": ["evidence.txt"]}) == 0
        ok &= rec(4, {"ticket_id": t, "route": "fix_ourselves", "rule_id": "R3", "reason": "r", "one_way_door": True}) == 20
        ok &= rec(4, {"ticket_id": t, "route": "fix_ourselves", "rule_id": "R3", "reason": "r", "one_way_door": False}) == 20   # R3 routes to tell_agent
        ok &= rec(4, {"ticket_id": t, "route": "fix_ourselves", "rule_id": "R4", "reason": "r", "one_way_door": False}) == 0
        ok &= rec(5, {"ticket_id": t, "route": "tell_agent", "summary": "s", "evidence_files": ["evidence.txt"]}) == 20
        ok &= rec(5, {"ticket_id": t, "route": "fix_ourselves", "summary": "s", "evidence_files": ["evidence.txt"]}) == 0
        ok &= rec(6, {"ticket_id": t, "check_id": "c1", "result": "not_applicable", "evidence_files": ["evidence.txt"]}) == 20
        ok &= rec(6, {"ticket_id": t, "check_id": "c1", "result": "failed", "evidence_files": ["evidence.txt"]}) == 0
        ok &= rec(7, {"ticket_id": t, "outcome": "solved", "owner_message": "We fixed the problem and checked it works.", "delivery_receipt": "m1"}) == 20
        # tampering with a recorded step breaks the chain
        p = os.path.join(d, "03-triage.json")
        doc = json.load(open(p))
        doc["body"]["severity"] = "P3"
        json.dump(doc, open(p, "w"))
        try:
            cmd_check(argparse.Namespace(cases_root=root, ticket=t, step=7))
            ok = False
        except Refused:
            pass
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Rescue Rangers case step gate")
    sub = ap.add_subparsers(dest="command")
    for name in ("check", "record", "audit"):
        s = sub.add_parser(name)
        s.add_argument("--cases-root", required=True)
        s.add_argument("--ticket", required=True)
        if name != "audit":
            s.add_argument("--step", type=int, required=True, choices=sorted(STEPS))
        if name == "record":
            s.add_argument("--from", dest="from_file", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    try:
        if a.command == "selftest":
            return selftest()
        if a.command == "check":
            return cmd_check(a)
        if a.command == "record":
            return cmd_record(a)
        if a.command == "audit":
            return cmd_audit(a)
    except Refused as why:
        print("REFUSED: %s" % why, file=sys.stderr)
        return 20
    except OSError as exc:
        print("FILESYSTEM FAILURE: %s" % exc, file=sys.stderr)
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
