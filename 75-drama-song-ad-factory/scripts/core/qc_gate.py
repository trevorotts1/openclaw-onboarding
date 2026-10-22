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
    # DEL-08: the one cover image (thumbnail) rides the delivery gate as one
    # more independent record (check_id "cover_image", checker
    # scripts/core/delivery_variants/cover_image.py): measured pixels, the
    # receipt sha256 and the README listing, never the row's own claim.
    "cover_image",

    # DEL-01: the three clearly-labelled audio versions (full song,
    # instrumental, voice only) plus the plain-English note ride on the
    # delivery gate as one more independent record (checker
    # delivery_variants/song_files.check_audio_versions).
    "audio_versions",
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
    # DEL-05: the delivery folder ships the video twice (captioned + clean);
    # every delivered video has to clear delivery_audio before it is listed.
    "video_delivery",

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


def _warn(code, detail):
    """Record a named WARNING on the receipt (loud_failure.warn). A gate that
    only flags still advances; the warning keeps the reason visible."""
    if not code:
        return
    try:
        import loud_failure  # noqa: PLC0415 - sibling module, same buffer
        loud_failure.warn(code, detail or "")
    except Exception:  # noqa: BLE001 - the warning is already on the result
        pass


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
    warnings = []
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
            elif m.get("warning"):
                # Order 2026-10-21: an overshoot is a FLAG, never a stop.
                # The named warning reaches the receipt through loud_failure;
                # whether the master is redone belongs to the client.
                _warn(m["warning"].get("code"), m["warning"].get("detail"))
                warnings.append(dict(m["warning"]))

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
                "failures": [], "repair_scope": [], "warnings": warnings,
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
            "warnings": warnings,
            "critical_failures": crit}


# ---- S75-W02-U3: the versioned QC evidence contract ----------------------
#
# qc-schema 1.0.0 records name the verdict FAMILY (the ``check`` category) but
# not which measurement produced the verdict, on which artifact, under which
# evaluator. This contract adds the deterministic adapters between the three
# levels -- take-level measurement -> stage-level QC record -> delivered-audio
# acceptance -- around ONE validated schema that producer and consumer share,
# and the REQUIRED-CHECK REGISTRY declared independently of whatever records
# arrive: neither an arbitrary record list nor an empty list can establish
# all-checks-passed.

EVIDENCE_CONTRACT_VERSION = "1.0.0"

#: Finding severities. "advisory" is the ONLY surface a scoped creative
#: exception may ever address.
SEVERITIES = frozenset({"critical", "major", "advisory"})

#: Structural evidence failures. NONWAIVABLE: missing or corrupt QC, schema
#: errors, inaccessible evidence files, absent required measurements,
#: wrong-tenant evidence, unsupported attestations and paid-dispatch controls.
#: No operator decision, no creative exception and no re-aggregation ever
#: advances a stage under one -- MISSING_QC and SCHEMA_VIOLATION included.
STRUCTURAL_CODES = frozenset({
    "MISSING_QC", "QC_CORRUPT", "SCHEMA_VIOLATION", "EVIDENCE_INACCESSIBLE",
    "MEASUREMENT_MISSING", "WRONG_TENANT", "ATTESTATION_UNSUPPORTED",
    "PAID_DISPATCH_CONTROL",
    # binding and independence faults are structural too (17.6 / 24.4)
    "UNKNOWN_CHECK", "UNKNOWN_CHECK_ID", "UNKNOWN_STAGE",
    "MAKER_UNKNOWN", "MAKER_SELF_REVIEW", "WRONG_RUN", "WRONG_ARTIFACT",
    "STALE_BINDING", "CHECKER_VERSION_MISMATCH", "PROFILE_MISMATCH",
    "UNAVAILABLE_MANDATORY", "SUNG_CLAIM_UNMEASURED", "FILL_CLAIM_MEASURED",
})


def chain_link(stage, code, detail=""):
    """ONE boundary hop in a refusal's causal chain (same shape as
    song_choices.causal_link -- the two modules never import each other)."""
    return {"stage": str(stage), "reason_code": str(code or ""),
            "detail": str(detail or "")}


def refusal_envelope(code, detail, next_action, chain=()):
    """A refusal that survives every wrapper boundary: reason, detail, next    action and the causal chain travel together and are never rewritten."""
    out = []
    for link in chain or ():
        if not isinstance(link, dict) or not link.get("stage"):
            raise GateError("BAD_INPUT", "causal_chain entries need a stage")
        out.append(chain_link(link.get("stage"), link.get("reason_code", ""),
                              link.get("detail", "")))
    return {"reason_code": str(code or ""), "detail": str(detail or ""),
            "next_action": str(next_action or ""), "causal_chain": out}


def _entry(category, producer, consumer, measurement, severity,
           confidence=False, control=None):
    return {"category": category, "producer": producer, "consumer": consumer,
            "measurement": measurement, "severity": severity,
            "confidence": bool(confidence), "control": control}


#: The producer-to-consumer mapping. Each STABLE CHECK ID (what was measured)
#: declares the qc-schema CATEGORY its record rides, WHO measures it, WHICH
#: consumer reads it and the MEASUREMENT KEY the producer must attest. One
#: category carries many check IDs; the ID never changes category. Both
#: adapters read THIS table -- the mapping is declared, never caller-asserted.
CHECK_REGISTRY = {
    "take.lyrics.critical_words": _entry(
        "lyrics", "song_dispatch.judge_take", "qc_gate.evidence_to_record",
        "critical_word_coverage", "critical", confidence=True),
    "take.timing.word_alignment": _entry(
        "timing", "lyric_timing", "qc_gate.evidence_to_record",
        "median_ms", "critical", confidence=True),
    "take.audio.first_sung": _entry(
        "audio", "singing_detector", "qc_gate.evidence_to_record",
        "first_sung_s", "major", confidence=True),
    "stage.shots.no_blur_fill": _entry(
        "no_blur_fill", "no_blur_fill.still_fill", "qc_gate.evidence_to_record",
        "fill_method", "critical"),
    "stage.final_edit.master_length": _entry(
        "final_edit", "master_length.check_master", "qc_gate.evidence_to_record",
        "measured_s", "critical", confidence=True),
    "stage.final_qc.prompt_compliance": _entry(
        "prompt_compliance", "prompt_templates.receipt",
        "qc_gate.evidence_to_record", "receipt_rows", "major",
        control="paid_dispatch"),
    "delivery.audio.acceptance": _entry(
        "audio_versions", "delivery_variants.song_files",
        "qc_gate.delivery_acceptance", "accepted", "critical"),
}

#: REQUIRED CHECKS PER STAGE -- DECLARED here, never derived from received
#: records. An arbitrary record list cannot shrink the requirement and an
#: empty list cannot satisfy it: the consumers below measure records AGAINST
#: this registry, never FROM them.
REQUIRED_CHECK_REGISTRY = {
    "take": ("take.lyrics.critical_words", "take.timing.word_alignment",
             "take.audio.first_sung"),
    "shots": ("stage.shots.no_blur_fill",),
    "final_edit": ("stage.final_edit.master_length",),
    "final_qc": ("stage.final_qc.prompt_compliance",),
    "delivery": ("delivery.audio.acceptance",),
}


def required_checks_for(stage):
    """The stage's REQUIRED check IDs from the DECLARED registry (independent
    of any record list). Unknown stages fail closed."""
    if stage not in REQUIRED_CHECK_REGISTRY:
        raise GateError("UNKNOWN_STAGE",
                        "no declared required-check registry for stage %r" % (stage,))
    return tuple(REQUIRED_CHECK_REGISTRY[stage])


def _evidence_error_code(err):
    """Map a shared-schema validation error to its structural code."""
    e = (err or "").lower()
    if "unsupported attestation" in e:
        return "ATTESTATION_UNSUPPORTED"
    if "measured" in e or "confidence" in e:
        return "MEASUREMENT_MISSING"
    return "SCHEMA_VIOLATION"


def validate_evidence(doc):
    """THE validated schema both sides share: the producer builds with
    measurement_evidence(), the consumer re-checks with THIS function before
    trusting a byte of the doc. Error string or None."""
    if not isinstance(doc, dict):
        return "evidence doc must be an object"
    if doc.get("contract_version") != EVIDENCE_CONTRACT_VERSION:
        return "contract_version must be %r" % EVIDENCE_CONTRACT_VERSION
    cid = doc.get("check_id")
    ent = CHECK_REGISTRY.get(cid)
    if ent is None:
        return "unknown check_id %r (not in CHECK_REGISTRY)" % (cid,)
    for key in ("category", "producer", "consumer"):
        if doc.get(key) != ent[key]:
            return ("%s %r does not match the declared producer-to-consumer "
                    "mapping %r" % (key, doc.get(key), ent[key]))
    art = doc.get("artifact_sha256")
    if not isinstance(art, str) or not re.fullmatch(r"[0-9a-f]{64}", art):
        return "artifact_sha256 must be a 64-character lowercase hex digest"
    for key in ("plan_revision", "evaluator_version", "evidence_source",
                "tenant"):
        if not _nonempty_str(doc.get(key)):
            return "%s must be a non-empty string" % key
    if not isinstance(doc.get("applicable"), bool):
        return "applicable must be a boolean"
    if doc.get("severity") not in SEVERITIES:
        return "severity must be one of %s" % sorted(SEVERITIES)
    if doc.get("verdict") not in VERDICTS:
        return "verdict must be one of %s" % sorted(VERDICTS)
    meas = doc.get("measured")
    if not isinstance(meas, dict) or ent["measurement"] not in meas:
        return ("measured must record the declared measurement %r"
                % ent["measurement"])
    allowed = {ent["measurement"], "method", "detail", "sample_ref", "units"}
    extra = sorted(set(meas) - allowed)
    if extra:
        return ("unsupported attestation keys %r (the producer %r attests %r "
                "only)" % (extra, ent["producer"], ent["measurement"]))
    if ent["confidence"] and doc.get("applicable") and doc.get("confidence") is None:
        return "confidence must be recorded for %r" % cid
    rec = doc.get("record")
    if not isinstance(rec, dict):
        return "record must be an object"
    if rec.get("check_id") != cid or rec.get("check") != ent["category"]:
        return "record identity must match the declared check_id/category"
    err = validate_record(rec)
    if err is not None:
        return "record: " + err
    return None


def measurement_record(check_id, measurement, *, run_id, stage, verdict,
                       reviewer, summary="", reason_code=""):
    """take-level measurement -> ONE stage-level qc-schema record.
    DETERMINISTIC: the check identity and category come from CHECK_REGISTRY,
    the evaluator version becomes the checker version, the evidence source is
    recorded in refs. Nothing about the mapping is caller-asserted."""
    ent = CHECK_REGISTRY.get(check_id)
    if ent is None:
        raise GateError("UNKNOWN_CHECK_ID",
                        "check %r is not in CHECK_REGISTRY" % (check_id,))
    if verdict not in VERDICTS:
        raise GateError("SCHEMA_VIOLATION",
                        "verdict must be one of %s" % sorted(VERDICTS))
    if not _nonempty_str(summary):
        summary = "measured %s=%r via %s" % (
            ent["measurement"], (measurement or {}).get(ent["measurement"]),
            ent["producer"])
    return {"schema_version": "1.0.0", "check_id": check_id,
            "run_id": run_id, "stage": stage, "check": ent["category"],
            "verdict": verdict,
            "evidence": {"summary": summary,
                         "refs": ["qc-evidence:%s" % check_id]},
            "reason_code": reason_code, "checker_version": "",
            "reviewer": dict(reviewer or {})}


def measurement_evidence(check_id, measurement, *, verdict, artifact_sha256,
                         plan_revision, evaluator_version, evidence_source,
                         run_id, stage, reviewer, summary="", reason_code="",
                         confidence=None, applicable=True, tenant="default",
                         severity=None):
    """take-level measurement -> the shared evidence doc (PRODUCER side of the
    one validated schema). ``measurement`` is the measured result: a dict    carrying the declared measurement key. The category, producer, consumer and
    default severity come from CHECK_REGISTRY; the approved-plan revision,    artifact hash, evaluator version, evidence source, applicability and    confidence ride WITH the measurement. ``severity`` defaults to the    registry's declared severity and may carry the measured finding's own    severity (e.g. an advisory FLAG riding a critical-category check). Raises    GateError on any schema error -- a producer never emits a doc the consumer
    would refuse."""
    ent = CHECK_REGISTRY.get(check_id)
    if ent is None:
        raise GateError("UNKNOWN_CHECK_ID",
                        "check %r is not in CHECK_REGISTRY" % (check_id,))
    if verdict not in VERDICTS:
        raise GateError("SCHEMA_VIOLATION",
                        "verdict must be one of %s" % sorted(VERDICTS))
    if severity is not None and severity not in SEVERITIES:
        raise GateError("SCHEMA_VIOLATION",
                        "severity must be one of %s" % sorted(SEVERITIES))
    rec = measurement_record(check_id, measurement, run_id=run_id, stage=stage,
                             verdict=verdict, reviewer=reviewer,
                             summary=summary, reason_code=reason_code)
    rec["checker_version"] = str(evaluator_version or "")
    if ent["category"] == "timing":
        # 17.8: the qc-schema timing record carries its sample, confidence and
        # annotation method -- mapped deterministically from the measurement    # (the declared producer IS the annotation method), never caller-asserted.
        rec["timing_detail"] = {
            "sample_ref": str((measurement or {}).get("sample_ref")
                              or evidence_source),
            "confidence": str(confidence if confidence is not None else ""),
            "annotation_method": ent["producer"]}
    doc = {"contract_version": EVIDENCE_CONTRACT_VERSION,
           "check_id": check_id,
           "category": ent["category"], "producer": ent["producer"],
           "consumer": ent["consumer"],
           "artifact_sha256": artifact_sha256,
           "plan_revision": plan_revision,
           "evaluator_version": evaluator_version,
           "evidence_source": evidence_source,
           "tenant": tenant, "applicable": bool(applicable),
           "confidence": confidence, "measured": measurement,
           "severity": severity or ent["severity"], "verdict": verdict,
           "reason_code": reason_code, "record": rec}
    err = validate_evidence(doc)
    if err is not None:
        raise GateError(_evidence_error_code(err), err)
    return doc


def evidence_to_record(doc):
    """The CONSUMER-side adapter: the stage-level qc-schema record inside a
    validated evidence doc. Raises rather than return a record the shared    schema refused."""
    err = validate_evidence(doc)
    if err is not None:
        raise GateError(_evidence_error_code(err), err)
    return dict(doc["record"])


def required_satisfied(docs, stage):
    """ALL required checks for ``stage`` established by valid, applicable,
    PASSing evidence docs. The requirement comes from REQUIRED_CHECK_REGISTRY
    (an independent declaration); the record list only ever FULFILLS it -- an
    empty list reports every required check missing and an arbitrary list can
    never establish all-checks-passed."""
    req = required_checks_for(stage)
    ok = set()
    for d in docs or ():
        if not isinstance(d, dict) or d.get("check_id") not in req:
            continue
        if validate_evidence(d) is None and d.get("applicable") \
                and (d.get("record") or {}).get("verdict") == "PASS":
            ok.add(d["check_id"])
    missing = [c for c in req if c not in ok]
    return {"stage": stage, "required": list(req), "satisfied": not missing,
            "missing": missing}


def _source_accessible(src):
    """An evidence SOURCE that names a file must be readable. A logical source
    name (a dotted symbol, a URI) is not a file and is never file-checked."""
    if not isinstance(src, str) or "://" in src or os.sep not in src:
        return True
    return os.path.isfile(src)


def creative_exception(*, check_id, artifact_sha256, plan_revision, authority,
                       scope, rationale=""):
    """A SCOPED creative exception: binds the check, the EXACT artifact    revision, the approving authority and the named advisory findings it    covers. Version-bound: the contract version is stamped and re-checked on    every use. It never carries a verdict -- measured verdicts stay as    measured."""
    if isinstance(scope, str):
        scope = (scope,)
    scope = tuple(str(s) for s in (scope or ()) if str(s).strip())
    if not _nonempty_str(check_id):
        raise GateError("BAD_INPUT", "a creative exception names ONE check_id")
    if not _nonempty_str(authority):
        raise GateError("BAD_INPUT",
                        "a creative exception names its approving authority")
    if not scope:
        raise GateError("BAD_INPUT",
                        "a creative exception names the advisory findings it covers")
    return {"contract_version": EVIDENCE_CONTRACT_VERSION,
            "check_id": check_id, "artifact_sha256": artifact_sha256,
            "plan_revision": plan_revision, "authority": authority,
            "scope": scope, "rationale": str(rationale or "")}


def apply_creative_exception(finding, exception, *, artifact_sha256,
                             plan_revision):
    """ONE scoped creative exception over ONE named advisory finding on ONE
    exact artifact. The MEASURED verdict is preserved verbatim -- an exception
    never turns a FAIL into a PASS; it records who approved it, for which    artifact revision, and which named finding it covers. Structural findings,
    critical findings and unnamed findings are refused outright."""
    if not isinstance(finding, dict) or not isinstance(exception, dict):
        raise GateError("BAD_INPUT",
                        "a creative exception needs a finding and an exception object")
    if exception.get("contract_version") != EVIDENCE_CONTRACT_VERSION:
        raise GateError("EXCEPTION_REFUSED",
                        "exception contract_version %r is not the supported %r "
                        "(version-bound)" % (exception.get("contract_version"),
                                             EVIDENCE_CONTRACT_VERSION))
    code = finding.get("code")
    if code in STRUCTURAL_CODES:
        raise GateError("EXCEPTION_REFUSED",
                        "structural failure %s is nonwaivable" % code)
    if finding.get("verdict") == "UNAVAILABLE":
        raise GateError("EXCEPTION_REFUSED",
                        "UNAVAILABLE never becomes PASS (17.8); it cannot be excepted")
    name = finding.get("reason_code") or code
    if name not in (exception.get("scope") or ()):
        raise GateError("EXCEPTION_REFUSED",
                        "finding %r is not named in the exception scope %r"
                        % (name, exception.get("scope")))
    severity = finding.get("severity") or ("critical" if finding.get("critical")
                                           else "advisory")
    if severity != "advisory":
        raise GateError("EXCEPTION_REFUSED",
                        "only an ADVISORY finding may be excepted; %r is %s"
                        % (name, severity))
    if exception.get("check_id") != finding.get("check_id"):
        raise GateError("EXCEPTION_REFUSED",
                        "exception names check %r, finding is check %r"
                        % (exception.get("check_id"), finding.get("check_id")))
    if exception.get("artifact_sha256") != artifact_sha256:
        raise GateError("EXCEPTION_REFUSED",
                        "exception binds artifact %r, not %r (exact artifact only)"
                        % (exception.get("artifact_sha256"), artifact_sha256))
    if exception.get("plan_revision") != plan_revision:
        raise GateError("EXCEPTION_REFUSED",
                        "exception binds approved-plan revision %r, not %r"
                        % (exception.get("plan_revision"), plan_revision))
    if not _nonempty_str(exception.get("authority")):
        raise GateError("EXCEPTION_REFUSED",
                        "a creative exception names its approving authority")
    out = dict(finding)
    out["excepted"] = True
    out["measured_verdict"] = finding.get("verdict") or "FAIL"
    out["exception"] = {"authority": exception["authority"],
                        "scope": list(exception["scope"]),
                        "check_id": exception["check_id"],
                        "artifact_sha256": exception["artifact_sha256"],
                        "plan_revision": exception["plan_revision"],
                        "contract_version": exception["contract_version"],
                        "rationale": exception.get("rationale", "")}
    return out


def stage_complete(result):
    """True only when a stage may complete on this result. NEVER under
    MISSING_QC or SCHEMA_VIOLATION -- or any structural failure -- and an
    operator decision cannot change that (see apply_operator_decision)."""
    if not isinstance(result, dict):
        return False
    codes = {f.get("code") for f in (result.get("failures") or [])
             if isinstance(f, dict)}
    codes |= {s.get("code") for s in (result.get("structural") or [])
              if isinstance(s, dict)}
    if codes & STRUCTURAL_CODES:
        return False
    if "gate" in result:
        return result.get("gate") == "PASS"
    return bool(result.get("accepted"))


def apply_operator_decision(result, *, authority, exceptions=(),
                            artifact_sha256=None, plan_revision=None):
    """An OPERATOR DECISION over a gate result. Only explicitly scoped,
    version-bound creative exceptions for named ADVISORY findings on the    exact artifact may be applied, and each one PRESERVES the measured verdict    in the record. Structural evidence failures are nonwaivable: any of them    refuses the decision outright with the causal chain intact -- an operator
    override can never advance structurally invalid QC, and no stage completes
    under MISSING_QC or SCHEMA_VIOLATION."""
    if not isinstance(result, dict):
        raise GateError("BAD_INPUT", "result must be a gate result object")
    failures = [f for f in (result.get("failures") or []) if isinstance(f, dict)]
    structural = [f for f in failures if f.get("code") in STRUCTURAL_CODES]
    if structural:
        return {"advanced": False, "excepted": [], "result": result,
                "refusal": refusal_envelope(
                    "STRUCTURAL_EVIDENCE_FAILURE",
                    "structural evidence failures are nonwaivable: %s"
                    % ", ".join(sorted({f.get("code") for f in structural})),
                    "repair the named structural evidence; no operator "
                    "decision, override or exception advances it",
                    chain=[chain_link("evaluate", f.get("code"),
                                      str(f.get("detail") or ""))
                           for f in structural]
                    + [chain_link("operator_override",
                                  "STRUCTURAL_EVIDENCE_FAILURE",
                                  "override refused for authority %s" % authority)])}
    applied, kept = [], []
    for f in failures:
        name = f.get("reason_code") or f.get("code")
        exc = next((e for e in exceptions if isinstance(e, dict)
                    and e.get("check_id") == f.get("check_id")
                    and name in (e.get("scope") or ())), None)
        if exc is None:
            kept.append(f)
            continue
        applied.append(apply_creative_exception(
            f, exc, artifact_sha256=artifact_sha256,
            plan_revision=plan_revision))
    out = dict(result)
    out["failures"] = kept
    out["excepted"] = list(result.get("excepted") or []) + applied
    if kept:
        out["gate"] = "FAIL" if result.get("gate") != "BLOCKED" else "BLOCKED"
        out["reason_code"] = "+".join(sorted({f.get("code") or "" for f in kept}))
    else:
        out["gate"] = "PASS"
        out["reason_code"] = ("ALL_REQUIRED_PASS_EXCEPTED" if applied
                              else result.get("reason_code"))
    return {"advanced": not kept and result.get("gate") != "BLOCKED",
            "excepted": applied, "result": out, "refusal": None}


def delivery_acceptance(docs, *, artifact_sha256, plan_revision,
                        tenant="default", evaluator_version=None,
                        stage="delivery", exceptions=()):
    """delivered-audio acceptance over the evidence docs for ONE exact
    artifact under ONE approved-plan revision. Required checks come from
    REQUIRED_CHECK_REGISTRY -- the declaration is independent of ``docs``.
    Structural evidence failures (missing/corrupt QC, schema errors,
    inaccessible files, absent required measurements, wrong-tenant evidence,
    unsupported attestations, paid-dispatch controls) refuse the acceptance
    and can never be excepted. Scoped creative exceptions bind to the exact
    artifact and preserve the measured verdicts.
    Returns the acceptance row: accepted, the required set, every MEASURED    verdict (kept even under an exception), missing checks, structural    failures, findings and separate counts."""
    req = required_checks_for(stage)
    structural, findings, measured, foreign = [], [], {}, []
    counted = set()
    counts = {"required": len(req), "evidence": 0, "pass": 0, "fail": 0,
              "unavailable": 0, "structural": 0, "excepted": 0, "missing": 0}
    for d in docs or ():
        if not isinstance(d, dict):
            structural.append({"check_id": "", "code": "QC_CORRUPT",
                               "detail": "evidence entry is not an object"})
            continue
        counts["evidence"] += 1
        err = validate_evidence(d)
        if err is not None:
            structural.append({"check_id": d.get("check_id", ""),
                               "code": _evidence_error_code(err),
                               "detail": err})
            continue
        cid = d["check_id"]
        if d.get("tenant") != tenant:
            structural.append({"check_id": cid, "code": "WRONG_TENANT",
                               "detail": "evidence tenant %r != expected %r"
                                         % (d.get("tenant"), tenant)})
            continue
        if d["artifact_sha256"] != artifact_sha256:
            if cid in req:
                foreign.append(cid)     # another artifact: never this artifact's proof
            continue
        if d["plan_revision"] != plan_revision:
            structural.append({"check_id": cid, "code": "STALE_BINDING",
                               "detail": "evidence plan revision %r != "
                                         "approved-plan revision %r"
                                         % (d["plan_revision"], plan_revision)})
            continue
        if evaluator_version is not None and \
                d["evaluator_version"] != evaluator_version:
            structural.append({"check_id": cid,
                               "code": "CHECKER_VERSION_MISMATCH",
                               "detail": "evaluator %r != expected %r"
                                         % (d["evaluator_version"],
                                            evaluator_version)})
            continue
        if not _source_accessible(d["evidence_source"]):
            structural.append({"check_id": cid, "code": "EVIDENCE_INACCESSIBLE",
                               "detail": "evidence source %r is not readable"
                                         % (d["evidence_source"],)})
            continue
        verdict = d["record"]["verdict"]
        measured[cid] = {"verdict": verdict, "severity": d["severity"],
                         "measured": d["measured"],
                         "evaluator_version": d["evaluator_version"]}
        counted.add(cid)
        ent = CHECK_REGISTRY[cid]
        if ent.get("control") == "paid_dispatch" and verdict != "PASS":
            structural.append({"check_id": cid, "code": "PAID_DISPATCH_CONTROL",
                               "detail": "paid-dispatch control not satisfied "
                                         "(%s)" % verdict})
            continue
        if verdict == "PASS":
            counts["pass"] += 1
        elif verdict == "UNAVAILABLE":
            counts["unavailable"] += 1
            findings.append({"check_id": cid, "reason_code": d.get("reason_code"),
                             "verdict": verdict, "severity": d["severity"],
                             "waivable": False})
        else:
            counts["fail"] += 1
            findings.append({"check_id": cid, "reason_code": d.get("reason_code"),
                             "verdict": verdict, "severity": d["severity"],
                             "waivable": d["severity"] == "advisory"})
    for c in req:
        if c not in counted:
            counts["missing"] += 1
            structural.append({"check_id": c, "code": "MISSING_QC",
                               "detail": "no usable evidence for required check "
                                         "%r (foreign evidence: %s)"
                                         % (c, sorted(set(foreign)))})
    excepted = []
    for e in exceptions or ():
        target = next((f for f in findings
                       if f.get("waivable")
                       and f.get("check_id") == (e.get("check_id") if isinstance(e, dict) else None)
                       and (f.get("reason_code") or f.get("check_id"))
                       in ((e.get("scope") or ()) if isinstance(e, dict) else ())), None)
        if target is not None:
            excepted.append(apply_creative_exception(
                target, e, artifact_sha256=artifact_sha256,
                plan_revision=plan_revision))
    counts["structural"] = len(structural)
    counts["excepted"] = len(excepted)
    excepted_names = {(x.get("check_id"),
                       x.get("reason_code") or x.get("check_id"))
                      for x in excepted}
    blocking = [f for f in findings
                if (f.get("check_id"),
                    f.get("reason_code") or f.get("check_id"))
                not in excepted_names]
    accepted = (not structural and not blocking and
                all((measured.get(c) or {}).get("verdict") == "PASS"
                    or any(x.get("check_id") == c for x in excepted)
                    for c in req))
    return {"accepted": bool(accepted),
            "artifact_sha256": artifact_sha256,
            "plan_revision": plan_revision,
            "contract_version": EVIDENCE_CONTRACT_VERSION,
            "required": list(req), "missing": sorted(
                {s["check_id"] for s in structural if s["code"] == "MISSING_QC"}),
            "measured_verdicts": measured,
            "structural": structural, "findings": findings,
            "excepted": excepted, "counts": counts}


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
            evidence={"failures": [], "repair_scope": [],
                      "warnings": res.get("warnings") or []}), EXIT["ok"]
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
