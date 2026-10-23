#!/usr/bin/env python3
"""Recovery classification is wired into job_recovery.recover().

Proves, without any provider call:
  (a) a fully evidenced historical run is reported RESUMABLE;
  (b) a run with absent/missing evidence is never reported RESUMABLE;
  (c) classification performs zero dispatches and zero network calls --
      proven with tripwires that raise if the path is touched, plus a
      positive control showing the tripwires are live.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "scripts", "core")
sys.path.insert(0, CORE)

import job_recovery as JR  # noqa: E402
import recovery_classification as RC  # noqa: E402
import spend_ledger as L  # noqa: E402


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
    return path


def _ledger(tmp):
    db = os.path.join(tempfile.mkdtemp(dir=tmp), "ledger.db")
    assert L.init_run(db, "run-1", 100000)["outcome"] == "ok"
    planned = L.plan(db, "run-1", "clip-a", "att-1", "digest-a",
                     estimated_cost=10)
    assert planned["outcome"] == "ok", planned
    return db


def _project(tmp, *, evidence, stages, approvals, requires):
    return {
        "schema": RC.INPUT_SCHEMA,
        "project_id": "hist-1",
        "requires_approvals": requires,
        "approvals": approvals,
        "evidence": evidence,
        "stages": stages,
    }


def _approved(aid):
    return {"approval_id": aid, "state": "approved",
            "source_ref": "cc://run/approvals/%s" % aid,
            "verification": {"method": "operator-attested"}}


def test_resumable_run_reported_resumable(tmp_path):
    tmp = str(tmp_path)
    db = _ledger(tmp)
    clip = os.path.join(tmp, "clip-01.mp4")
    with open(clip, "wb") as handle:
        handle.write(b"paid-clip-bytes")
    project = _project(
        tmp,
        evidence=[{"evidence_id": "clip-01", "kind": "paid_clip",
                   "source_ref": "cc://run/1/clip-01.mp4",
                   "verification": {"method": "sha256-of-file",
                                    "path": clip, "sha256": _sha(clip)}}],
        stages=[{"stage_id": "clips", "state": "done", "paid": True,
                 "evidence_ref": "clip-01"}],
        approvals=[_approved("storyboard")],
        requires=["storyboard"])
    out = JR.recover(db, "run-1", project=project)
    assert out["outcome"] == "ok", out
    classification = out["evidence"]["classification"]
    assert classification is not None, out
    assert classification["state"] == RC.RESUMABLE, classification
    assert out["evidence"]["recovery_gate"]["state"] == "RESUME_ALLOWED"
    assert classification["policy"]["paid_provider_calls"] == 0
    assert classification["policy"]["regeneration"] == "NEVER_AUTO_REGENERATE"


def test_missing_evidence_is_never_resumable(tmp_path):
    tmp = str(tmp_path)
    db = _ledger(tmp)

    empty = _project(tmp, evidence=[], stages=[], approvals=[], requires=[])
    out = JR.recover(db, "run-1", project=empty)
    state = out["evidence"]["classification"]["state"]
    assert state != RC.RESUMABLE, out
    assert "no_evidence_records" in out["evidence"]["classification"]["reasons"]

    no_approval = _project(
        tmp,
        evidence=[{"evidence_id": "state-01", "kind": "project_state",
                   "source_ref": "cc://run/3/state.json"}],
        stages=[{"stage_id": "clips", "state": "done", "paid": True,
                 "evidence_ref": "state-01"}],
        approvals=[],
        requires=["spend"])
    out = JR.recover(db, "run-1", project=no_approval)
    classification = out["evidence"]["classification"]
    assert classification["state"] == RC.BLOCKED, classification
    assert {"code": "MISSING_APPROVAL", "ref": "spend"} in [
        {k: b[k] for k in ("code", "ref")} for b in classification["blocked_by"]]
    assert out["evidence"]["recovery_gate"]["state"] == "HOLD"

    unverified = _project(
        tmp,
        evidence=[{"evidence_id": "state-02", "kind": "project_state",
                   "source_ref": "cc://run/4/state.json"}],
        stages=[{"stage_id": "clips", "state": "done", "paid": True,
                 "evidence_ref": "state-02"}],
        approvals=[], requires=[])
    out = JR.recover(db, "run-1", project=unverified)
    classification = out["evidence"]["classification"]
    assert classification["state"] == RC.RECOVERABLE, classification
    assert "stage_unverified:clips" in classification["reasons"]


def test_no_project_evidence_is_unclassified_not_assumed(tmp_path):
    db = _ledger(str(tmp_path))
    out = JR.recover(db, "run-1")
    assert out["evidence"]["classification"] is None, out
    assert out["evidence"]["classification_reason"] == "NO_PROJECT_EVIDENCE_SUPPLIED"
    assert out["evidence"]["recovery_gate"]["state"] == "UNCLASSIFIED"
    assert out["evidence"]["jobs"], "existing recovery contract must be preserved"


def test_unreadable_project_fails_closed(tmp_path):
    tmp = str(tmp_path)
    db = _ledger(tmp)
    missing = os.path.join(tmp, "does-not-exist.json")
    out = JR.recover(db, "run-1", project_path=missing)
    classification = out["evidence"]["classification"]
    assert classification["state"] == RC.BLOCKED, classification
    assert classification["blocked_by"][0]["code"] == "UNREADABLE_PROJECT"
    assert out["evidence"]["recovery_gate"]["state"] == "HOLD"

    wrong = _write_json(os.path.join(tmp, "future.json"),
                        {"schema": "s75.recovery.project/v9",
                         "project_id": "future"})
    out = JR.recover(db, "run-1", project_path=wrong)
    classification = out["evidence"]["classification"]
    assert classification["state"] == RC.BLOCKED, classification
    assert classification["blocked_by"][0]["code"] == "UNSUPPORTED_INPUT_SCHEMA"
    assert "s75.recovery.project/v9" in classification["blocked_by"][0]["detail"]


def test_classification_zero_dispatch_zero_network(tmp_path):
    tmp = str(tmp_path)
    db = _ledger(tmp)
    clip = os.path.join(tmp, "clip-02.mp4")
    with open(clip, "wb") as handle:
        handle.write(b"paid-clip-two")
    project = _project(
        tmp,
        evidence=[{"evidence_id": "clip-02", "kind": "paid_clip",
                   "source_ref": "cc://run/2/clip-02.mp4",
                   "verification": {"method": "sha256-of-file",
                                    "path": clip, "sha256": _sha(clip)}}],
        stages=[{"stage_id": "clips", "state": "done", "paid": True,
                 "evidence_ref": "clip-02"}],
        approvals=[_approved("storyboard")],
        requires=["storyboard"])

    class Tripwire:
        def __init__(self):
            self.calls = []
            self.saved = []

        def _arm(self, owner, name):
            original = getattr(owner, name)
            self.saved.append((owner, name, original))

            def boom(*args, **kwargs):
                self.calls.append(name)
                raise AssertionError("TRIPWIRE: %s called" % name)

            setattr(owner, name, boom)

        def __enter__(self):
            for owner, name in (
                    (socket.socket, "connect"),
                    (socket, "create_connection"),
                    (socket, "getaddrinfo"),
                    (urllib.request, "urlopen"),
                    (http.client.HTTPConnection, "connect"),
                    (subprocess, "Popen"),
                    (subprocess, "run"),
                    (L, "_open"),
                    (L, "reserve"),
                    (L, "allocate_attempt"),
                    (L, "mark_submitted"),
                    (JR, "ingest_event"),
                    (JR, "record_result")):
                self._arm(owner, name)
            return self

        def __exit__(self, *exc):
            for owner, name, original in reversed(self.saved):
                setattr(owner, name, original)
            return False

    with Tripwire() as wire:
        # Positive control: the tripwires are live, so silence below means
        # the classification path touched none of them.
        try:
            JR.ingest_event(db, "run-1", "clip-a", "att-1", "evt-1")
        except AssertionError as exc:
            assert "TRIPWIRE: ingest_event" in str(exc), exc
        else:
            raise AssertionError("tripwire control did not fire")
        wire.calls.clear()

        out = JR.recover(db, "run-1", project=project,
                         journal_path=os.path.join(tmp, "journal", "idem.json"))

    assert wire.calls == [], "classification touched a dispatch/network seam: %s" % (
        wire.calls,)
    assert out["evidence"]["classification"]["state"] == RC.RESUMABLE, out
    assert out["outcome"] == "ok"


def test_classification_is_idempotent_across_recover_calls(tmp_path):
    tmp = str(tmp_path)
    db = _ledger(tmp)
    project = _project(tmp, evidence=[], stages=[], approvals=[], requires=[])
    journal = os.path.join(tmp, "journal", "j.json")
    first = JR.recover(db, "run-1", project=project, journal_path=journal)
    second = JR.recover(db, "run-1", project=project, journal_path=journal)
    assert (json.dumps(first["evidence"]["classification"], sort_keys=True)
            == json.dumps(second["evidence"]["classification"], sort_keys=True))
    with open(journal, encoding="utf-8") as handle:
        records = json.load(handle)["records"]
    assert len(records) == 3, records


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="job-recovery-cls-") as tmp:
        for case in (test_resumable_run_reported_resumable,
                     test_missing_evidence_is_never_resumable,
                     test_no_project_evidence_is_unclassified_not_assumed,
                     test_unreadable_project_fails_closed,
                     test_classification_zero_dispatch_zero_network,
                     test_classification_is_idempotent_across_recover_calls):
            case(tmp)
            print("PASS %s" % case.__name__)
    print("OK job_recovery classification wiring: 6 cases")
