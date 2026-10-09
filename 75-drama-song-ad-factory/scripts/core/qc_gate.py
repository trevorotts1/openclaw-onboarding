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
  check must PASS; critical failures are flagged, never averaged away;
- a PASS record asserting a sung/first-sung share names the G3 detector
  (SUNG_CLAIM_UNMEASURED otherwise): sung shares are measured by
  core/singing_detector, never computed from section labels.
- a PASS record for the no_blur_fill check never asserts a blur fill
  (FILL_CLAIM_MEASURED otherwise): full height comes from crop-in of the
  source frame only, never from a blurred, letterboxed or stretched fill
  (DEL-14; the claim is evidence text, see fill_claim).

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
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_length import check_master  # noqa: E402  (Part I I4)

TOOL_NAME = "qc_gate"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
COMPATIBLE = {"1.0.0"}

VERDICTS = frozenset({"PASS", "FAIL", "UNAVAILABLE"})
CHECKS = frozenset({
    "export", "timeline", "lyrics", "timing", "audio", "text_product",
    "continuity", "creative", "song", "storyboard", "video", "final_edit", "song_files",
    # G7 (Trevor order 1140): the 7-question delivery checklist rides on
    # the Final edit QC gate as one more independent record (check_id
    # "delivery-checklist", checker scripts/core/delivery_checklist/).
    "delivery_checklist",
    # FU-U10: the book orientation contract. A book campaign's shots stage
    # requires one PASS record per book clip from the CALIBRATED book_shot
    # checker (scripts/core/book_shot/).
    "book_orientation",
    # U15h (design 8.9): every paid prompt in the spend ledger carries a
    # matching receipt; final QC requires one row per ledger job.
    "prompt_compliance",
    # U8: the Script gate (SOP DS-9 gate 1) carries the spelling and
    # grammar record as one more independent check; see SCRIPT_STAGES.
    "spelling_grammar",
    # DEL-14: the no-blur-fill check carries the render-path record. Its
    # PASS must come from a crop-in render attempt, never from a fill; see
    # fill_claim.
    "no_blur_fill",
})
# 17.8 critical categories (identity, lyrics, offer, claim, product_label,
# CTA) ride on these checks: lyrics carries the critical-word coverage,
# text_product carries identity/copy/CTA at the mobile rendition.
CRITICAL_CHECKS = frozenset({"lyrics", "text_product"})

#: U8: the checks the Script stage always requires. The script judge already
#: covers beats/claims/CTA; spelling and grammar ride the SAME gate as a
#: required record, so a stage cannot pass with the words unread.
SCRIPT_STAGES = frozenset({"script", "script-lyrics"})

def required_checks(stage, required, campaign_type=None):
    """FU-U10: a book campaign's shots stage also requires book_orientation.

    Acceptance is 'no book clip is accepted without a PASS book_orientation
    record from a calibrated checker'; requiring the check for EVERY book
    campaign (not just ones that remembered to ask) is what makes that true.

    U8: a Script-stage gate always also requires the spelling_grammar record
    (the words are read by the same independent judge, not by a later stage).
    """
    req = list(required or [])
    ct = campaign_type if isinstance(campaign_type, str) else ""
    if stage == "shots" and ct.strip().lower() in BOOK_CAMPAIGN_TYPES \
            and "book_orientation" not in req:
        req.append("book_orientation")
    if stage in SCRIPT_STAGES and "spelling_grammar" not in req:
        req.append("spelling_grammar")
    return req

EXIT = {"ok": 0, "waiting": 3, "parked": 4, "rejected": 5, "error": 1}


class GateError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _nonempty_str(v):
    return isinstance(v, str) and bool(v.strip())

# G3-WIRE (Trevor order 2026-10-08 11:35 Part G G3): a sung share in QC or
# a receipt is MEASURED by core/singing_detector, never derived from
# section labels ("54% sung" from [Verse]/[Chorus] time was the fake number
# the waiver accepted). This gate cannot run the audio detector (stdlib
# only, no numpy/ffmpeg), so it enforces the provenance the receipt paths
# attach: a PASS record whose evidence asserts a sung/first-sung number
# must name the detector.
# ponytail: string-level provenance check on evidence.summary (qc-schema
# v1.0.0 evidence allows summary+refs only); move to a schema evidence key
# when qc-schema names one.
SUNG_DETECTOR = "singing_detector"
_SUNG_CLAIM = re.compile(
    r"sung_coverage\s*=|sung\s+coverage|sung_pct\s*=|first[_\s]sung"
    r"|first real singing at \d|sung\s+\d+(?:\.\d+)?\s*%", re.I)


def sung_claim(summary):
    """True when evidence text asserts a sung or first-sung share."""
    return bool(isinstance(summary, str) and _SUNG_CLAIM.search(summary))


def sung_claim_measured(summary):
    """True when that text names the G3 singing detector as its source.

    Normalizes away separators so "singing-detector(vocal-stem)",
    "singing_detector v2.0.0" and "detector=singing_detector" all count.
    """
    if not isinstance(summary, str):
        return False
    flat = "".join(ch for ch in summary.lower() if ch.isalnum())
    return "singingdetector" in flat


# DEL-14 (Trevor order 2026-10-09): blur fill is never used. Full height is
# reached by crop-in of the source frame only. This gate cannot render or
# inspect pixels (stdlib only), so it refuses the CLAIM in evidence text the
# same way G3 refuses an unmeasured sung claim: a PASS record for the
# no_blur_fill check whose evidence names a blur fill can never pass.
# ponytail: negation-aware string matching on evidence.summary (qc-schema
# v1.0.0 evidence allows summary+refs only); move to a schema evidence key
# (e.g. fill_method) when qc-schema names one.
FILL_CLAIM_DETECTOR = "fill_claim"
_FILL_TOKEN = (
    r"(?:blur[-_\s]?fill|blurfill"
    r"|blur(?:red)?\s+(?:fill|backdrop|background|mask|strip|edge|band)"
    r"|fill(?:ed)?\s+with\s+a\s+blur|gaussian[-_\s]?fill"
    r"|gblur|boxblur|avgblur|smartblur|alphamerge)")
#: a negator up to 40 chars ahead of the token (and coordinated tokens after
#: it: "never a blur fill or blurred mask") documents the refusal, it is not
#: a fill claim. The span stops at sentence punctuation so "no letterbox;
#: gblur sigma=30" still claims.
_FILL_NEGATED = re.compile(
    r"\b(?:no|not|never|without|zero|free\s+of|absent|lacks?"
    r"|avoid(?:s|ed)?)\b[^.!?\n;]{0,40}?"
    r"(?:\s+(?:or\s+|and\s+|nor\s+)?" + _FILL_TOKEN + r")+",
    re.I)
#: the same refusal spelled the other way round: "blur fill is never used".
_FILL_REPEALED = re.compile(
    _FILL_TOKEN + r"[^.!?\n;]{0,24}\s+(?:is\s+|are\s+|was\s+|were\s+|be\s+)?"
    r"(?:never|not|no\b|none\b|without|absent)", re.I)
_FILL_CLAIM = re.compile(_FILL_TOKEN, re.I)


def fill_claim(summary):
    """True when evidence text asserts a blur fill / blurred mask backdrop."""
    if not isinstance(summary, str):
        return False
    text = _FILL_NEGATED.sub(" ", summary)
    text = _FILL_REPEALED.sub(" ", text)
    return bool(_FILL_CLAIM.search(text))


# U15h (design 8.9): at final QC every paid prompt in the spend ledger must
# carry the prompt receipt that was minted when the prompt was assembled
# (prompt_templates.receipt -> kie_dispatch PROMPT_NOT_TEMPLATED). One row
# per ledger job; a job with no receipt (or a REFUSE/TRIM receipt) is not
# compliance. The rows are data the checker built; this module only decides
# whether the record for check "prompt_compliance" exists and passed.
PROMPT_COMPLIANCE_CHECK = "prompt_compliance"
PROMPT_COMPLIANCE_OK_VERDICTS = frozenset({"PASS", "FLAG"})

def prompt_compliance_rows(ledger_jobs, receipts):
    """One row per ledger job, matched to its receipt. -> (rows, bad).

    A receipt matches a job when they share logical_key + attempt_id, or
    (when the receipt carries neither) request_digest, or the job's own
    prompt_sha256. A receipt whose check verdict is REFUSE/TRIM/FAIL never
    counts. ``bad`` names every job without a compliant receipt.
    """
    jobs = [j for j in (ledger_jobs or []) if isinstance(j, dict)]
    recs = [r for r in (receipts or []) if isinstance(r, dict)]
    rows, bad = [], []
    for job in jobs:
        lk, at = job.get("logical_key"), job.get("attempt_id")
        digest, sha = job.get("request_digest"), job.get("prompt_sha256")
        match = None
        for r in recs:
            if r.get("logical_key") is not None or r.get("attempt_id") is not None:
                hit = (r.get("logical_key") == lk and r.get("attempt_id") == at)
            elif r.get("request_digest") is not None:
                hit = (r.get("request_digest") == digest)
            elif r.get("prompt_sha256") is not None and sha is not None:
                hit = (r.get("prompt_sha256") == sha)
            else:
                hit = False
            if hit:
                match = r
                break
        verdict = None
        if isinstance(match, dict):
            chk = match.get("check")
            verdict = ((chk.get("verdict") if isinstance(chk, dict) else None)
                       or match.get("verdict"))
        ok = (verdict is not None
              and str(verdict).upper() in PROMPT_COMPLIANCE_OK_VERDICTS)
        rows.append({"logical_key": lk, "attempt_id": at,
                     "prompt_sha256": (sha or (match or {}).get("prompt_sha256")),
                     "matched": bool(match), "verdict": verdict, "ok": ok})
        if not ok:
            if match is None:
                bad.append("%s/%s: no prompt receipt" % (lk, at))
            else:
                bad.append("%s/%s: receipt verdict %s" % (lk, at, verdict))
    return rows, bad

def prompt_compliance_record(rows, bad, reviewer, run_id, stage):
    """qc-schema 1.0.0 record (check=prompt_compliance) for core/qc_gate.py.

    PASS when every row matched a compliant receipt; FAIL naming each
    unmatched job otherwise. The reviewer must be independent of the maker
    (the gate enforces that too, 17.6).
    """
    summary = ("every paid prompt carries a matching prompt receipt (%d rows)"
               % len(rows)) if not bad else \
        "; ".join(bad[:8]) + ("" if len(bad) <= 8 else " (+%d more)" % (len(bad) - 8))
    return {"schema_version": "1.0.0", "check_id": "prompt-compliance",
            "run_id": run_id, "stage": stage, "check": PROMPT_COMPLIANCE_CHECK,
            "verdict": "PASS" if not bad else "FAIL",
            "evidence": {"summary": summary,
                         "refs": ["prompt_templates.receipt"]},
            "reason_code": "PROMPT_COMPLIANT" if not bad else "PROMPT_NO_RECEIPT",
            "checker_version": "1.0.0", "reviewer": reviewer}

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


BOOK_CAMPAIGN_TYPES = frozenset({"book"})

def evaluate(run_id, stage, records, makers, required,
             critical=CRITICAL_CHECKS, profile_version=None,
             expected_profile_version=None, expected_checker_version=None,
             master=None, campaign_type=None, ledger_jobs=None):
    """Gate decision. Returns dict with gate/reason_code/failures/repair_scope.

    I4: when "final_edit" is required, master={"chosen_length_s", "measured_s"}
    is mandatory and a master longer than chosen length minus 2 s fails
    (MASTER_TOO_LONG); a missing/unmeasured master never passes.

    U15h: when ``ledger_jobs`` is a non-empty list (the run's paid jobs),
    the final-QC gate REQUIRES ``prompt_compliance``: the caller must pass a
    prompt_compliance record built from prompt_compliance_rows()/record().
    A final QC with a ledger job and no compliant record never passes.

    makers maps check_id -> maker identity (from artifact provenance).
    gate is PASS (advance), FAIL (targeted repair allowed) or BLOCKED
    (structural problem: no repair of the same records can pass).

    U8: a Script-stage gate always also requires the ``spelling_grammar``
    record (see ``required_checks``) -- the words are read by the same
    independent judge that reads the beats, not by a later stage.
    """
    failures = []
    required = required_checks(stage, required, campaign_type)
    required = list(required)
    if ledger_jobs and PROMPT_COMPLIANCE_CHECK not in required:
        required.append(PROMPT_COMPLIANCE_CHECK)

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
    if "final_edit" in required:
        if not isinstance(master, dict):
            fail("i4-master-length", "MASTER_LENGTH_MISSING",
                 "final_edit needs chosen_length_s and the measured master")
        else:
            try:
                m = check_master(master.get("chosen_length_s"),
                                 master.get("measured_s"))
            except ValueError as e:
                m = {"outcome": "rejected",
                     "reason_code": "MASTER_LENGTH_MISSING", "detail": str(e)}
            if m["outcome"] != "ok":
                fail("i4-master-length", m["reason_code"], m["detail"], True)

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
        # G3: a PASS record that asserts a sung share must have flowed
        # through core/singing_detector (receipt paths attach its name).
        # FAIL/UNAVAILABLE never advance a stage, so the rule binds PASS.
        if rec["verdict"] == "PASS" \
                and sung_claim(rec["evidence"]["summary"]) \
                and not sung_claim_measured(rec["evidence"]["summary"]):
            fail(rec["check_id"], "SUNG_CLAIM_UNMEASURED",
                 "sung claim carries no singing_detector provenance: %s"
                 % rec["evidence"]["summary"][:160])
        # DEL-14: the no_blur_fill record's PASS must never assert a blur
        # fill; the summary carries the render attempt's method, so a blur
        # fill claim on a PASS is a contradiction the gate refuses outright.
        if rec["verdict"] == "PASS" \
                and rec["check"] == "no_blur_fill" \
                and fill_claim(rec["evidence"]["summary"]):
            fail(rec["check_id"], "FILL_CLAIM_MEASURED",
                 "no_blur_fill PASS asserts a blur fill; full height is "
                 "crop-in only: %s" % rec["evidence"]["summary"][:160])
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
    # FILL_CLAIM_MEASURED (DEL-14) joins SUNG_CLAIM_UNMEASURED as structural:
    # the same record can never pass, so repair means a new crop-in render,
    # not a re-aggregation of this one.
    structural = codes - {"CHECK_FAIL", "MASTER_TOO_LONG"}
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
                       expected_checker_version=ns.expect_checker,
                       master=({"chosen_length_s": ns.chosen_length_s,
                                "measured_s": ns.master_s}
                               if ns.chosen_length_s is not None else None),
                       campaign_type=ns.campaign_type or None,
                       ledger_jobs=(_load_json(ns.ledger_jobs)
                                    if ns.ledger_jobs else None))
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
    a.add_argument("--chosen-length-s", type=float, default=None,
                   help="I4: chosen video length; required with final_edit")
    a.add_argument("--master-s", type=float, default=None,
                   help="I4: measured master length in seconds")
    a.add_argument("--campaign-type", default="",
                   help="campaign type; 'book' requires book_orientation at shots")
    a.add_argument("--expect-profile", default=None)
    a.add_argument("--expect-checker", default=None)
    a.add_argument("--ledger-jobs", default="",
                   help="U15h: JSON array of paid ledger jobs; a non-empty "
                        "list requires the prompt_compliance record at final QC")
    ns = p.parse_args(argv)
    out, rc = cmd_evaluate(ns)
    print(json.dumps(out, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(_cli())
