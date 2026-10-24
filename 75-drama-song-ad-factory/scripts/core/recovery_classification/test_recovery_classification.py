#!/usr/bin/env python3
"""Assert-based self-check for recovery_classification (no test framework)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "recovery_classifier", os.path.join(_HERE, "classifier.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def _digest(path):
    return C.sha256_file(path)


def _approved(aid, ref="cc://run/approvals/" + "x"):
    return {"approval_id": aid, "state": "approved", "source_ref": ref,
            "verification": {"method": "operator-attested"}}


def _write(tmp, name, payload):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
    return path


def case_resumable(tmp):
    artifact = os.path.join(tmp, "clip-01.mp4")
    with open(artifact, "wb") as handle:
        handle.write(b"paid-clip-bytes")
    project = {
        "schema": C.INPUT_SCHEMA,
        "project_id": "hist-full",
        "requires_approvals": ["storyboard"],
        "approvals": [_approved("storyboard")],
        "evidence": [{
            "evidence_id": "clip-01",
            "kind": "paid_clip",
            "source_ref": "cc://run/1/clip-01.mp4",
            "verification": {"method": "sha256-of-file", "path": artifact,
                             "sha256": _digest(artifact)},
        }],
        "stages": [{"stage_id": "clips", "state": "done", "paid": True,
                    "evidence_ref": "clip-01"}],
    }
    source = _write(tmp, "full.json", project)
    before = _digest(source)
    out = C.classify(C.load_project(source), source_path=source,
                     journal_path=os.path.join(tmp, "journal", "full.json"))
    after = _digest(source)
    assert out["state"] == C.RESUMABLE, out
    assert out["blocked_by"] == [], out
    assert out["policy"]["regeneration"] == "NEVER_AUTO_REGENERATE"
    assert out["policy"]["paid_provider_calls"] == 0
    assert out["reconstructed_facts"], out
    for fact in out["reconstructed_facts"]:
        assert fact["reconstruction"]["reconstructed"] is True
        assert fact["reconstruction"]["is_receipt"] is False
        assert fact["reconstruction"]["observed_at_event"] is False
        assert fact["source_ref"], fact
    assert out["resume_plan"][0]["action"] == "SKIP"
    assert "clip-01" in out["protected_artifacts"]
    assert before == after, "source project must not be mutated"


def case_recoverable(tmp):
    project = {
        "schema": C.INPUT_SCHEMA,
        "project_id": "hist-partial",
        "requires_approvals": ["storyboard"],
        "approvals": [_approved("storyboard")],
        "evidence": [
            {"evidence_id": "state-01", "kind": "project_state",
             "source_ref": "cc://run/2/state.json"},
            {"evidence_id": "clip-02", "kind": "paid_clip",
             "source_ref": "cc://run/2/clip-02.mp4",
             "verification": {"method": "provider-record",
                              "provider": "kie"}},
        ],
        "stages": [
            {"stage_id": "clips", "state": "done", "paid": True,
             "evidence_ref": "clip-02"},
            {"stage_id": "lipsync", "state": "partial", "paid": True},
        ],
    }
    source = _write(tmp, "partial.json", project)
    out = C.classify(C.load_project(source), source_path=source,
                     journal_path=os.path.join(tmp, "journal", "partial.json"))
    assert out["state"] == C.RECOVERABLE, out
    assert out["blocked_by"] == [], out
    cited = {c.get("evidence_id") for c in out["citations"]}
    assert "state-01" in cited, out          # partial evidence is cited
    assert "clip-02" in cited, out
    assert "paid_stage_incomplete:lipsync" in out["reasons"], out
    plan = {p["stage_id"]: p for p in out["resume_plan"]}
    assert plan["lipsync"]["action"] == "RESUME_EXISTING_ONLY", plan
    assert plan["lipsync"]["paid"] is True
    assert "never regenerate" in plan["lipsync"]["note"]


def case_blocked_missing_approval(tmp):
    project = {
        "schema": C.INPUT_SCHEMA,
        "project_id": "hist-noapproval",
        "requires_approvals": ["spend"],
        "approvals": [],
        "evidence": [{"evidence_id": "state-01", "kind": "project_state",
                      "source_ref": "cc://run/3/state.json"}],
        "stages": [{"stage_id": "clips", "state": "done", "paid": True}],
    }
    source = _write(tmp, "blocked.json", project)
    out = C.classify(C.load_project(source), source_path=source,
                     journal_path=os.path.join(tmp, "journal", "blocked.json"))
    assert out["state"] == C.BLOCKED, out
    codes = {(b["code"], b["ref"]) for b in out["blocked_by"]}
    assert ("MISSING_APPROVAL", "spend") in codes, out
    assert "do not infer it" in out["blocked_by"][0]["action"]


def case_blocked_provenance(tmp):
    project = {
        "schema": C.INPUT_SCHEMA,
        "project_id": "hist-nosource",
        "requires_approvals": [],
        "approvals": [],
        "evidence": [{"evidence_id": "orphan", "kind": "clip",
                      "source_ref": ""}],
        "stages": [{"stage_id": "clips", "state": "done", "paid": True}],
    }
    source = _write(tmp, "nosource.json", project)
    out = C.classify(C.load_project(source), source_path=source)
    assert out["state"] == C.BLOCKED, out
    assert out["blocked_by"][0]["code"] == "UNVERIFIABLE_PROVENANCE"
    assert out["blocked_by"][0]["ref"] == "orphan"


def case_idempotent(tmp):
    artifact = os.path.join(tmp, "clip-03.mp4")
    with open(artifact, "wb") as handle:
        handle.write(b"more-paid-clip-bytes")
    project = {
        "schema": C.INPUT_SCHEMA,
        "project_id": "hist-idempotent",
        "requires_approvals": ["storyboard"],
        "approvals": [_approved("storyboard")],
        "evidence": [{"evidence_id": "clip-03", "kind": "paid_clip",
                      "source_ref": "cc://run/4/clip-03.mp4",
                      "verification": {"method": "sha256-of-file",
                                       "path": artifact,
                                       "sha256": _digest(artifact)}}],
        "stages": [{"stage_id": "clips", "state": "done", "paid": True,
                    "evidence_ref": "clip-03"}],
    }
    source = _write(tmp, "idem.json", project)
    journal_path = os.path.join(tmp, "journal", "idem.json")

    first = C.classify(C.load_project(source), source_path=source,
                       journal_path=journal_path)
    records_after_first = json.load(open(journal_path, encoding="utf-8"))["records"]
    journal = C.Journal(journal_path)
    second = C.classify(C.load_project(source), source_path=source,
                        journal=journal)
    records_after_second = json.load(open(journal_path, encoding="utf-8"))["records"]

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert len(records_after_first) == len(records_after_second), \
        "resumed run must not duplicate journal work"
    assert journal.cache_hits == 3, journal.cache_hits
    assert first["idempotency"]["journaled_steps"] == 3
    assert first["state"] == C.RESUMABLE


def case_schema_refusal(tmp):
    source = _write(tmp, "v9.json", {"schema": "s75.recovery.project/v9",
                                     "project_id": "future"})
    try:
        C.classify(C.load_project(source), source_path=source)
    except C.UnsupportedSchemaError as exc:
        assert exc.code == "UNSUPPORTED_INPUT_SCHEMA"
        assert "s75.recovery.project/v9" in str(exc), str(exc)
        assert C.INPUT_SCHEMA in str(exc), str(exc)
    else:
        raise AssertionError("unsupported schema must be refused, not guessed")


def case_absent_evidence_not_resumable(tmp):
    project = {"schema": C.INPUT_SCHEMA, "project_id": "hist-empty",
               "requires_approvals": [], "approvals": [],
               "evidence": [], "stages": []}
    source = _write(tmp, "empty.json", project)
    out = C.classify(C.load_project(source), source_path=source)
    assert out["state"] == C.RECOVERABLE, out
    assert "no_evidence_records" in out["reasons"], out

    project = {"schema": C.INPUT_SCHEMA, "project_id": "hist-unverified",
               "requires_approvals": [], "approvals": [],
               "evidence": [{"evidence_id": "state-01",
                             "kind": "project_state",
                             "source_ref": "cc://run/5/state.json"}],
               "stages": [{"stage_id": "clips", "state": "done",
                           "paid": True, "evidence_ref": "state-01"}]}
    source = _write(tmp, "unverified.json", project)
    out = C.classify(C.load_project(source), source_path=source)
    assert out["state"] == C.RECOVERABLE, out
    assert "stage_unverified:clips" in out["reasons"], out
    assert out["resume_plan"][0]["action"] == "SKIP", out


def main():
    with tempfile.TemporaryDirectory(prefix="recovery-classification-") as tmp:
        for case in (case_resumable, case_recoverable,
                     case_blocked_missing_approval, case_blocked_provenance,
                     case_absent_evidence_not_resumable, case_idempotent,
                     case_schema_refusal):
            case(tmp)
            print("PASS %s" % case.__name__)
    print("OK recovery_classification self-check: 7 cases")
    return 0


def test_resumable(tmp_path):
    case_resumable(str(tmp_path))


def test_recoverable(tmp_path):
    case_recoverable(str(tmp_path))


def test_blocked_missing_approval(tmp_path):
    case_blocked_missing_approval(str(tmp_path))


def test_blocked_provenance(tmp_path):
    case_blocked_provenance(str(tmp_path))


def test_absent_evidence_not_resumable(tmp_path):
    case_absent_evidence_not_resumable(str(tmp_path))


def test_idempotent(tmp_path):
    case_idempotent(str(tmp_path))


def test_schema_refusal(tmp_path):
    case_schema_refusal(str(tmp_path))



if __name__ == "__main__":
    sys.exit(main())
