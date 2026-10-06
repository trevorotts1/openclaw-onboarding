#!/usr/bin/env python3
"""Independent QC gate. Directive 24.2 row 9, 17.6-17.8, 24.4, 24.6. Stdlib only.

Decides whether a stage may advance on its QC verdict records. Fail-closed:
- every required check needs a schema-valid record (validates against
  core/contracts/qc-schema.json shape; no third-party validator);
- reviewer identity must differ from the maker (17.6 independent verifier
  law; a caller-supplied PASS flag or maker-authored JSON is not evidence);
- approved QC binds the verified reviewer session and applicable authority
  (24.4); records without session/authority cannot advance a stage;
- UNAVAILABLE on a required check never becomes PASS (17.8);
- no aggregate erases a critical defect (17.8): every record for a required
  check must PASS; critical failures are flagged, never averaged away.

Stateless: keeps no DB, sets no stage state. Repair budgets live in
spend_ledger; the gate only names the failed checks (targeted repair, 17.7:
repair the shot, not the movie).

ponytail: makers bind by check_id from caller provenance (artifact_graph /
state_store own the record->artifact link; qc-schema v1.0.0 has no
artifact_id foreign key). Add the key to the schema when directive names it.
ponytail: numeric threshold-vs-profile comparison lives in the checker, not
here; the gate only requires timing sample/confidence/method be recorded.
"""
from __future__ import annotations

import argparse
import json
import sys

TOOL_NAME = "qc_gate"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
COMPATIBLE = {"1.0.0"}

VERDICTS = frozenset({"PASS", "FAIL", "UNAVAILABLE"})
CHECKS = frozenset({
    "export", "timeline", "lyrics", "timing", "audio", "text_product",
    "continuity", "creative", "song", "storyboard", "video", "final_edit",
})
# 17.8 critical categories (identity, lyrics, offer, claim, product_label,
# CTA) ride on these checks: lyrics carries the critical-word coverage,
# text_product carries identity/copy/CTA at the mobile rendition.
CRITICAL_CHECKS = frozenset({"lyrics", "text_product"})

EXIT = {"ok": 0, "waiting": 3, "parked": 4, "rejected": 5, "error": 1}


class GateError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _nonempty_str(v):
    return isinstance(v, str) and bool(v.strip())


def validate_record(rec):
    """Schema-shape check mirroring qc-schema.json. Returns error string or None."""
    if not isinstance(rec, dict):
        return "record must be an object"
    if rec.get("schema_version") not in COMPATIBLE:
        return "schema_version must be one of %s" % sorted(COMPATIBLE)
    for key in ("schema_version", "check_id", "run_id", "stage", "check",
                "verdict", "evidence", "checker_version", "reviewer"):
        if key not in rec:
            return "missing required field %s" % key
    if not _nonempty_str(rec["check_id"]):
        return "check_id must be a non-empty string"
    if not _nonempty_str(rec["run_id"]):
        return "run_id must be a non-empty string"
    if not _nonempty_str(rec["stage"]):
        return "stage must be a non-empty string"
    if rec["check"] not in CHECKS:
        return "unknown check %r" % (rec["check"],)
    if rec["verdict"] not in VERDICTS:
        return "verdict must be one of %s" % sorted(VERDICTS)
    if not _nonempty_str(rec["checker_version"]):
        return "checker_version must be a non-empty string"
    ev = rec["evidence"]
    if not isinstance(ev, dict) or not _nonempty_str(ev.get("summary")):
        return "evidence.summary must be a non-empty string"
    rev = rec["reviewer"]
    if not isinstance(rev, dict) or not _nonempty_str(rev.get("identity")):
        return "reviewer.identity must be a non-empty string"
    # 24.4: accepted QC binds the verified reviewer/session identity and
    # applicable authority; a caller-supplied PASS flag or maker-authored
    # JSON is not independent review evidence.
    if not _nonempty_str(rev.get("session")):
        return "reviewer.session must be a non-empty string"
    if not _nonempty_str(rev.get("authority")):
        return "reviewer.authority must be a non-empty string"
    if rec["check"] == "timing":
        # 17.8: record the sample, confidence and annotation method.
        td = rec.get("timing_detail")
        if not isinstance(td, dict):
            return "timing check requires timing_detail"
        for key in ("sample_ref", "confidence", "annotation_method"):
            if not _nonempty_str(td.get(key)):
                return "timing_detail.%s must be recorded" % key
    return None


def evaluate(run_id, stage, records, makers, required,
             critical=CRITICAL_CHECKS, profile_version=None,
             expected_profile_version=None, expected_checker_version=None):
    """Gate decision. Returns dict with gate/reason_code/failures/repair_scope.

    makers maps check_id -> maker identity (from artifact provenance).
    gate is PASS (advance), FAIL (targeted repair allowed) or BLOCKED
    (structural problem: no repair of the same records can pass).
    """
    failures = []

    def fail(check_id, code, detail, is_critical=False):
        failures.append({"check_id": check_id, "code": code,
                         "detail": detail, "critical": bool(is_critical)})

    if expected_profile_version is not None and \
            profile_version != expected_profile_version:
        fail("", "PROFILE_MISMATCH",
             "profile %r != required %r"
             % (profile_version, expected_profile_version))
    if not isinstance(records, list):
        raise GateError("BAD_INPUT", "records must be a list")
    if not required:
        raise GateError("BAD_INPUT", "required checks must be non-empty")

    by_check = {}
    seen = set()  # required checks with at least one offered record
    for rec in records:
        err = validate_record(rec)
        if err is not None:
            fail(rec.get("check_id", "") if isinstance(rec, dict) else "",
                 "SCHEMA_VIOLATION", err)
            if isinstance(rec, dict) and rec.get("check") in CHECKS:
                seen.add(rec["check"])
            continue
        seen.add(rec["check"])
        if rec["run_id"] != run_id:
            fail(rec["check_id"], "WRONG_RUN",
                 "record run %r != gate run %r" % (rec["run_id"], run_id))
            continue
        if rec["stage"] != stage:
            fail(rec["check_id"], "STALE_BINDING",
                 "record stage %r != gate stage %r" % (rec["stage"], stage))
            continue
        if expected_checker_version is not None and \
                rec["checker_version"] != expected_checker_version:
            fail(rec["check_id"], "CHECKER_VERSION_MISMATCH",
                 "checker %r != required %r"
                 % (rec["checker_version"], expected_checker_version))
            continue
        maker = makers.get(rec["check_id"]) \
            if isinstance(makers, dict) else None
        if not _nonempty_str(maker):
            fail(rec["check_id"], "MAKER_UNKNOWN",
                 "no maker binding for check_id; cannot prove independence")
            continue
        if rec["reviewer"]["identity"] == maker:
            # 17.6: maker cannot judge its own output, whatever the verdict.
            fail(rec["check_id"], "MAKER_SELF_REVIEW",
                 "reviewer %r is the maker; not independent evidence"
                 % maker)
            continue
        by_check.setdefault(rec["check"], []).append(rec)

    for check in required:
        if check not in CHECKS:
            fail(check, "UNKNOWN_CHECK", "not a qc-schema check")
            continue
        recs = by_check.get(check, [])
        if not recs:
            # A rejected record still proves the check was offered; only a
            # check with no record at all is missing.
            if check not in seen:
                fail(check, "MISSING_QC", "no record for required check")
            continue
        for rec in recs:
            if rec["verdict"] == "UNAVAILABLE":
                # 17.8: UNAVAILABLE cannot become PASS. Never averaged away.
                fail(rec["check_id"], "UNAVAILABLE_MANDATORY",
                     "required check unavailable; delivery blocked",
                     rec["check"] in critical)
            elif rec["verdict"] == "FAIL":
                fail(rec["check_id"], "CHECK_FAIL",
                     rec["evidence"]["summary"][:200],
                     rec["check"] in critical)

    if not failures:
        return {"gate": "PASS", "reason_code": "ALL_REQUIRED_PASS",
                "failures": [], "repair_scope": [],
                "critical_failures": []}
    codes = {f["code"] for f in failures}
    structural = codes - {"CHECK_FAIL"}
    gate = "BLOCKED" if structural else "FAIL"
    # repair_scope names records to repair (17.7 targeted repair); bare
    # check-name failures (MISSING_QC/UNKNOWN_CHECK) have no record to fix.
    scope = sorted({f["check_id"] for f in failures
                    if f["check_id"] and f["code"] not in
                    ("MISSING_QC", "UNKNOWN_CHECK", "PROFILE_MISMATCH")})
    crit = sorted({f["check_id"] for f in failures if f["critical"]})
    return {"gate": gate,
            "reason_code": "+".join(sorted(codes)),
            "failures": failures, "repair_scope": scope,
            "critical_failures": crit}


def envelope(command, outcome, reason_code, next_action="", run_id="",
             stage="", evidence=None, state_version=0):
    return {"schema_version": SCHEMA_VERSION, "tool": TOOL_NAME,
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "stage": stage, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence or {}, "state_version": state_version}


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise GateError("BAD_INPUT", "%s: %s" % (path, e))


def cmd_evaluate(ns):
    try:
        records = _load_json(ns.records)
        makers = _load_json(ns.makers)
        required = [c.strip() for c in ns.required.split(",") if c.strip()]
        profile_version = None
        if ns.profile:
            profile_version = _load_json(ns.profile).get("profile_version")
        critical = (frozenset(c.strip() for c in ns.critical.split(",")
                              if c.strip()) if ns.critical else CRITICAL_CHECKS)
        res = evaluate(ns.run, ns.stage, records, makers, required,
                       critical=critical, profile_version=profile_version,
                       expected_profile_version=ns.expect_profile,
                       expected_checker_version=ns.expect_checker)
    except GateError as e:
        return envelope("evaluate", "error", e.code, str(e),
                        run_id=ns.run, stage=ns.stage), EXIT["error"]
    if res["gate"] == "PASS":
        return envelope(
            "evaluate", "ok", res["reason_code"], "advance stage",
            run_id=ns.run, stage=ns.stage,
            evidence={"failures": [], "repair_scope": []}), EXIT["ok"]
    if res["gate"] == "FAIL":
        action = "repair checks %s with new attempt ids; approved assets stand" \
            % ",".join(res["repair_scope"])
    else:
        action = "hand back: %s; same records cannot pass" % res["reason_code"]
    return envelope(
        "evaluate", "rejected", res["reason_code"], action,
        run_id=ns.run, stage=ns.stage,
        evidence={"failures": res["failures"],
                  "repair_scope": res["repair_scope"],
                  "critical_failures": res["critical_failures"]}), \
        EXIT["rejected"]


def _cli(argv=None):
    p = argparse.ArgumentParser(prog="qc_gate",
                                description="Independent QC gate (fail-closed)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("evaluate")
    a.add_argument("--run", required=True)
    a.add_argument("--stage", required=True)
    a.add_argument("--records", required=True,
                   help="JSON array of qc-schema verdict records")
    a.add_argument("--makers", required=True,
                   help="JSON object check_id -> maker identity")
    a.add_argument("--required", required=True,
                   help="comma-separated required checks")
    a.add_argument("--critical", default="",
                   help="comma-separated critical checks (default: lyrics,text_product)")
    a.add_argument("--profile", default="",
                   help="acceptance-profile.json path (optional)")
    a.add_argument("--expect-profile", default=None)
    a.add_argument("--expect-checker", default=None)
    ns = p.parse_args(argv)
    out, rc = cmd_evaluate(ns)
    print(json.dumps(out, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(_cli())
