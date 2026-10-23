#!/usr/bin/env python3
"""Versioned, idempotent recovery classification for historical Skill 75 runs.

Reads project evidence read-only. Emits exactly one of RESUMABLE, RECOVERABLE
or BLOCKED. Never writes a receipt, never grants an approval, never regenerates
paid work, never rolls anything back and never mutates source evidence.

Reconstructed facts are labelled as reconstructed and are never receipts: they
carry a source reference plus reconstruction metadata and observed_at_event is
always false.

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

CLASSIFIER_VERSION = "1.1.0"
INPUT_SCHEMA = "s75.recovery.project/v1"
OUTPUT_SCHEMA = "s75.recovery.classification/v1"
JOURNAL_SCHEMA = "s75.recovery.journal/v1"

SUPPORTED_INPUT_SCHEMAS = (INPUT_SCHEMA,)
SUPPORTED_JOURNAL_SCHEMAS = (JOURNAL_SCHEMA,)

RESUMABLE = "RESUMABLE"
RECOVERABLE = "RECOVERABLE"
BLOCKED = "BLOCKED"
STATES = (RESUMABLE, RECOVERABLE, BLOCKED)

VERIFICATION_METHODS = ("sha256-of-file", "provider-record", "operator-attested")
STAGE_STATES = ("done", "partial", "pending")

REGENERATION_POLICY = "NEVER_AUTO_REGENERATE"
ROLLBACK_POLICY = "NONE"


class RecoveryError(ValueError):
    """Input or journal this classifier cannot interpret."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


class UnsupportedSchemaError(RecoveryError):
    """Declared schema/version is outside what this classifier supports."""


def _need(ok, code, message):
    if not ok:
        raise RecoveryError(code, message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def digest_of(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(path, base):
    return path if os.path.isabs(path) else os.path.join(base, path)


# --------------------------------------------------------------------------
# Journal: append-only, atomic, keyed by (input digest, step). A resumed run
# reuses recorded steps instead of redoing them, and never records a step twice.
# --------------------------------------------------------------------------
class Journal:
    def __init__(self, path=None):
        self.path = os.path.abspath(path) if path else None
        self.cache_hits = 0
        self._memory = None
        self._records = self._load()

    @property
    def records(self):
        return self._records

    def _load(self):
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            raise RecoveryError("CORRUPT_JOURNAL", "cannot read %s: %s"
                                % (self.path, exc))
        if not isinstance(raw, dict):
            raise RecoveryError("CORRUPT_JOURNAL", "journal root must be object")
        schema = raw.get("schema")
        if schema not in SUPPORTED_JOURNAL_SCHEMAS:
            raise UnsupportedSchemaError(
                "UNSUPPORTED_JOURNAL_SCHEMA",
                "%r (supported: %s)" % (schema, JOURNAL_SCHEMA))
        records = raw.get("records")
        _need(isinstance(records, dict), "CORRUPT_JOURNAL",
              "journal records must be an object")
        return records

    def _flush(self):
        if not self.path:
            self._memory = dict(self._records)
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp-%d" % os.getpid()
        payload = {"schema": JOURNAL_SCHEMA,
                   "classifier_version": CLASSIFIER_VERSION,
                   "records": self._records}
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2,
                      ensure_ascii=True)
            handle.write("\n")
        os.replace(tmp, self.path)

    def _key(self, input_digest, step):
        # Version-scoped: a behaviour change must never reuse an older cached
        # step result for the same input.
        return "%s:%s:%s" % (CLASSIFIER_VERSION, input_digest, step)

    def get(self, input_digest, step):
        entry = self._records.get(self._key(input_digest, step))
        return entry.get("result") if isinstance(entry, dict) else None

    def record(self, input_digest, step, result):
        self._records[self._key(input_digest, step)] = {
            "step": step, "input_digest": input_digest,
            "classifier_version": CLASSIFIER_VERSION, "result": result}
        self._flush()
        return result

    def step(self, input_digest, name, compute):
        key = self._key(input_digest, name)
        if key in self._records:
            self.cache_hits += 1
            return self._records[key]["result"]
        return self.record(input_digest, name, compute())


# --------------------------------------------------------------------------
# Input validation: refuse what cannot be interpreted, name the version.
# --------------------------------------------------------------------------
def validate_project(project):
    _need(isinstance(project, dict), "INVALID_INPUT", "project must be an object")
    schema = project.get("schema")
    if schema not in SUPPORTED_INPUT_SCHEMAS:
        raise UnsupportedSchemaError(
            "UNSUPPORTED_INPUT_SCHEMA",
            "%r (supported: %s)" % (schema, INPUT_SCHEMA))
    project_id = project.get("project_id")
    _need(isinstance(project_id, str) and project_id.strip(),
          "INVALID_INPUT", "project_id must be a non-empty string")

    evidence = project.get("evidence", [])
    _need(isinstance(evidence, list), "INVALID_INPUT", "evidence must be a list")
    seen = set()
    for item in evidence:
        _need(isinstance(item, dict), "INVALID_INPUT",
              "each evidence entry must be an object")
        eid = item.get("evidence_id")
        _need(isinstance(eid, str) and eid.strip(), "INVALID_INPUT",
              "evidence_id must be a non-empty string")
        _need(eid not in seen, "INVALID_INPUT",
              "duplicate evidence_id %r" % eid)
        seen.add(eid)

    approvals = project.get("approvals", [])
    _need(isinstance(approvals, list), "INVALID_INPUT",
          "approvals must be a list")
    ids = set()
    for item in approvals:
        _need(isinstance(item, dict), "INVALID_INPUT",
              "each approval entry must be an object")
        aid = item.get("approval_id")
        _need(isinstance(aid, str) and aid.strip(), "INVALID_INPUT",
              "approval_id must be a non-empty string")
        _need(aid not in ids, "INVALID_INPUT",
              "duplicate approval_id %r" % aid)
        ids.add(aid)

    requires = project.get("requires_approvals", [])
    _need(isinstance(requires, list) and all(
        isinstance(x, str) and x.strip() for x in requires), "INVALID_INPUT",
        "requires_approvals must be a list of non-empty ids")

    stages = project.get("stages", [])
    _need(isinstance(stages, list), "INVALID_INPUT", "stages must be a list")
    stage_ids = set()
    for item in stages:
        _need(isinstance(item, dict), "INVALID_INPUT",
              "each stage entry must be an object")
        sid = item.get("stage_id")
        _need(isinstance(sid, str) and sid.strip(), "INVALID_INPUT",
              "stage_id must be a non-empty string")
        _need(sid not in stage_ids, "INVALID_INPUT",
              "duplicate stage_id %r" % sid)
        stage_ids.add(sid)
        _need(item.get("state") in STAGE_STATES, "INVALID_INPUT",
              "stage %r state must be one of %s, got %r"
              % (sid, ", ".join(STAGE_STATES), item.get("state")))


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def _blocked(code, ref, detail, action):
    return {"code": code, "ref": ref, "detail": detail, "action": action}


def verify_evidence(item, base):
    eid = item["evidence_id"]
    kind = item.get("kind", "unspecified")
    ref = item.get("source_ref")
    verification = item.get("verification")
    method = verification.get("method") if isinstance(verification, dict) else None

    if not (isinstance(ref, str) and ref.strip()):
        return {"evidence_id": eid, "kind": kind, "state": "blocked",
                "blocked": _blocked(
                    "UNVERIFIABLE_PROVENANCE", eid,
                    "evidence %r carries no source reference" % eid,
                    "record the originating record/file for this evidence")}

    citation = {"evidence_id": eid, "kind": kind, "source_ref": ref,
                "verification": method or None}

    if method not in VERIFICATION_METHODS:
        citation["state"] = "partial"
        citation["missing"] = "verification-method"
        return {"evidence_id": eid, "kind": kind, "state": "partial",
                "blocked": None, "citation": citation}

    if method == "sha256-of-file":
        path = verification.get("path")
        expected = verification.get("sha256")
        if not (isinstance(path, str) and path.strip()
                and isinstance(expected, str) and expected.strip()):
            return {"evidence_id": eid, "kind": kind, "state": "blocked",
                    "blocked": _blocked(
                        "MISSING_ARTIFACT", eid,
                        "sha256-of-file needs both path and sha256",
                        "supply the recorded artifact path and digest")}
        resolved = _resolve(path, base)
        if not os.path.isfile(resolved):
            return {"evidence_id": eid, "kind": kind, "state": "blocked",
                    "blocked": _blocked(
                        "MISSING_ARTIFACT", eid,
                        "artifact not found at %s" % resolved,
                        "restore or re-point the preserved artifact; do not "
                        "re-generate paid output")}
        actual = sha256_file(resolved)
        if actual != expected.strip().lower():
            return {"evidence_id": eid, "kind": kind, "state": "blocked",
                    "blocked": _blocked(
                        "PROVENANCE_MISMATCH", eid,
                        "digest %s != recorded %s" % (actual, expected),
                        "stop and reconcile against the paid provider record")}
        citation["verified_digest"] = actual

    citation["state"] = "verified"
    return {"evidence_id": eid, "kind": kind, "state": "verified",
            "blocked": None, "citation": citation}


def check_approvals(project):
    approvals = {a["approval_id"]: a for a in project.get("approvals", [])}
    results = []
    for aid in sorted(project.get("requires_approvals", [])):
        entry = approvals.get(aid)
        if entry is None:
            results.append({"approval_id": aid, "state": "blocked",
                            "blocked": _blocked(
                                "MISSING_APPROVAL", aid,
                                "required approval %r has no record" % aid,
                                "obtain the recorded approval; do not infer it")})
            continue
        if entry.get("state") != "approved":
            results.append({"approval_id": aid, "state": "blocked",
                            "blocked": _blocked(
                                "APPROVAL_NOT_GRANTED", aid,
                                "approval %r state is %r, not approved"
                                % (aid, entry.get("state")),
                                "obtain an explicit approved record")})
            continue
        ref = entry.get("source_ref")
        verification = entry.get("verification")
        method = verification.get("method") if isinstance(verification, dict) else None
        if not (isinstance(ref, str) and ref.strip()):
            results.append({"approval_id": aid, "state": "blocked",
                            "blocked": _blocked(
                                "UNVERIFIABLE_PROVENANCE", aid,
                                "approval %r has no source reference" % aid,
                                "cite the original approval record")})
            continue
        if method not in VERIFICATION_METHODS:
            results.append({"approval_id": aid, "state": "blocked",
                            "blocked": _blocked(
                                "UNVERIFIED_APPROVAL", aid,
                                "approval %r has no accepted provenance method"
                                % aid,
                                "attach provider-record or operator-attested "
                                "provenance")})
            continue
        results.append({"approval_id": aid, "state": "approved",
                        "citation": {"approval_id": aid, "source_ref": ref,
                                     "verification": method}})
    return results


def _reconstruction():
    return {"classifier_version": CLASSIFIER_VERSION,
            "reconstructed": True,
            "observed_at_event": False,
            "is_receipt": False}


def build_stage_view(project, source_path, evidence_states):
    """Facts about recorded stages, each carrying a source reference.

    A stage is only treated as verified when its evidence reference resolves to
    VERIFIED evidence. Recorded-but-unverified stages stay in the plan as SKIP
    (never redo paid work) but raise a recovery gap, so they can never make a
    project RESUMABLE by assumption.
    """
    facts, resume_plan, gaps = [], [], []
    done = 0
    for index, stage in enumerate(project.get("stages", [])):
        sid = stage["stage_id"]
        state = stage["state"]
        paid = bool(stage.get("paid", False))
        evidence_ref = stage.get("evidence_ref")
        if state == "done":
            done += 1
            verified = (isinstance(evidence_ref, str)
                        and evidence_states.get(evidence_ref) == "verified")
            if verified:
                source_ref = {"kind": "evidence", "evidence_id": evidence_ref}
            else:
                source_ref = {"kind": "project-state",
                              "file": source_path,
                              "pointer": "/stages/%d" % index}
            facts.append({
                "fact": "stage %r recorded done" % sid,
                "source_ref": source_ref,
                "reconstruction": dict(_reconstruction(),
                                       method="project-state-record"),
            })
            resume_plan.append({"stage_id": sid, "action": "SKIP",
                                "reason": "ALREADY_RECORDED_DONE",
                                "paid": paid,
                                "verified": verified})
            if not verified:
                gaps.append("stage_unverified:%s" % sid)
        else:
            if paid:
                gaps.append("paid_stage_incomplete:%s" % sid)
                resume_plan.append(
                    {"stage_id": sid, "action": "RESUME_EXISTING_ONLY",
                     "reason": "INCOMPLETE_PAID_STAGE",
                     "paid": True,
                     "note": "reuse preserved artifacts; never regenerate"})
            else:
                gaps.append("stage_incomplete:%s" % sid)
                resume_plan.append({"stage_id": sid, "action": "RESUME",
                                    "reason": "STAGE_INCOMPLETE",
                                    "paid": False})
    if not project.get("evidence") and not done:
        gaps.append("no_evidence_records")
    return facts, resume_plan, gaps


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
def classify(project, *, source_path=None, journal_path=None, journal=None,
             base_dir=None):
    """Classify a historical project. Pure read; writes only the journal."""
    validate_project(project)
    source_path = os.path.abspath(source_path) if source_path else None
    base = base_dir or (os.path.dirname(source_path) if source_path
                        else os.getcwd())

    if journal is not None and journal_path is not None:
        raise RecoveryError("INVALID_INPUT",
                            "pass journal or journal_path, not both")
    if journal is None:
        journal = Journal(journal_path)
    if source_path and journal.path and journal.path == source_path:
        raise RecoveryError("JOURNAL_PATH_CONFLICT",
                            "journal must not overwrite the source project file")

    digest = digest_of(project)

    evidence = journal.step(digest, "verify_evidence", lambda: [
        verify_evidence(item, base) for item in sorted(
            project.get("evidence", []),
            key=lambda entry: entry["evidence_id"])])
    approvals = journal.step(digest, "check_approvals",
                             lambda: check_approvals(project))
    evidence_ids = {e["evidence_id"]: e["state"] for e in evidence}

    def _stage_view():
        facts, plan, gaps = build_stage_view(project, source_path, evidence_ids)
        return {"facts": facts, "plan": plan, "gaps": gaps}

    stages = journal.step(digest, "stage_view", _stage_view)

    blocked = [a["blocked"] for a in approvals if a.get("blocked")]
    blocked += [e["blocked"] for e in evidence if e.get("blocked")]
    blocked.sort(key=lambda item: (item["code"], item["ref"]))

    partial = [e["evidence_id"] for e in evidence if e["state"] == "partial"]
    gaps = list(stages["gaps"])
    facts = list(stages["facts"])

    if blocked:
        state = BLOCKED
        reasons = ["%s:%s" % (b["code"], b["ref"]) for b in blocked]
    elif partial or gaps:
        state = RECOVERABLE
        reasons = ["partial_evidence:%s" % eid for eid in partial]
        reasons += gaps
        reasons.sort()
    else:
        state = RESUMABLE
        reasons = ["all_required_evidence_verified",
                   "required_approvals_satisfied",
                   "no_incomplete_stages"]

    citations = [e["citation"] for e in evidence if e.get("citation")]
    citations += [a["citation"] for a in approvals if a.get("citation")]
    citations.sort(key=lambda item: (item.get("evidence_id")
                                     or item.get("approval_id") or ""))

    protected = sorted(
        {e["evidence_id"] for e in evidence
         if e.get("kind") in ("clip", "paid_clip", "provider_record", "backup")}
        | {p["stage_id"] for p in stages["plan"]
           if p.get("paid") and p["action"] == "SKIP"})

    return {
        "schema": OUTPUT_SCHEMA,
        "classifier_version": CLASSIFIER_VERSION,
        "input_schema": INPUT_SCHEMA,
        "project_id": project["project_id"],
        "input_digest": digest,
        "state": state,
        "reasons": reasons,
        "blocked_by": blocked,
        "citations": citations,
        "reconstructed_facts": facts,
        "resume_plan": stages["plan"],
        "protected_artifacts": protected,
        "policy": {"regeneration": REGENERATION_POLICY,
                   "rollback": ROLLBACK_POLICY,
                   "paid_provider_calls": 0},
        "idempotency": {"journaled_steps": len(journal.records),
                        "input_digest": digest},
    }


def load_project(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _cli(argv=None):
    parser = argparse.ArgumentParser(
        prog="recovery_classification",
        description="Classify historical Skill 75 projects without mutating them")
    parser.add_argument("--project", required=True,
                        help="project evidence JSON (read-only)")
    parser.add_argument("--journal", default=None,
                        help="idempotency journal path (created outside evidence)")
    args = parser.parse_args(argv)
    try:
        project = load_project(args.project)
        out = classify(project, source_path=args.project,
                       journal_path=args.journal)
    except (RecoveryError, OSError, ValueError) as exc:
        code = getattr(exc, "code", "UNREADABLE_PROJECT")
        print(json.dumps({"schema": OUTPUT_SCHEMA,
                          "classifier_version": CLASSIFIER_VERSION,
                          "state": BLOCKED,
                          "blocked_by": [{"code": code, "ref": args.project,
                                          "detail": str(exc),
                                          "action": "supply an interpretable "
                                                    "project record"}],
                          "reasons": [code]}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out["state"] != BLOCKED else 1


if __name__ == "__main__":
    sys.exit(_cli())
