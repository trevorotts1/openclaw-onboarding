"""test_pres042_execution_stamps.py -- the QC-PRES-042 acceptance battery.

PRES-042: QC independence proven from TRUSTED EXECUTION EVIDENCE, not report
text. The trusted dispatcher stamps author + reviewer executions (ids,
models, providers, reviewed artifact SHAs, rubric version) outside model
prose; qc_aggregate's AF-EXEC-STAMP surface consumes them.

Every row of QC.md QC-PRES-042:
  1. Forge graded_by in a same-execution report -> gate rejects on the
     TRUSTED execution id, whatever the prose claims.
  2. Mutate one reviewed file after pass -> its QC is stale (AF-EXEC-STAMP
     names the revision drift); only changed units go stale, untouched ones
     stay covered (stale_units).
  3. A reviewer-stamped repair of an artifact without a fresh author stamp is
     incomplete: the unit needs a fresh independent review of its NEW hash.
  4. The pre-existing missing/self-review report tests still reject, while
     valid trusted independent review passes (both surfaces run).

No network, no credentials. Stdlib + pytest/tmp_path only.
"""
import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
_PJ = SCRIPTS / "presentation_job"
if str(_PJ) not in sys.path:
    sys.path.insert(0, str(_PJ))

from presentation_job import execution_stamp as es  # noqa: E402

PHASE = "P1Q-COPY-QC"
ARTIFACT_REL = "working/qc/copy_qc_report.json"


def _rd(tmp_path: pathlib.Path) -> pathlib.Path:
    rd = tmp_path / "run"
    (rd / "working" / "qc").mkdir(parents=True)
    return rd


def _report(rd: pathlib.Path, graded_by: str = "qc-specialist-presentations") -> pathlib.Path:
    p = rd / ARTIFACT_REL
    p.write_text(json.dumps({
        "gate": "Phase 1Q", "average": 9.2, "pass": True,
        "triggered_autofails": [],
        "qc_independence": {"graded_by": graded_by, "independent": True,
                            "builder": "slide-copywriter", "self_graded": False},
    }), encoding="utf-8")
    return p


def _stamp(rd: pathlib.Path, *, author_exec: str, reviewer_exec: str,
           author_model: str = "deepseek-v4-pro", reviewer_model: str = "kimi-v4-a",
           sha: str = None, reviewed_artifact_rel: str = ARTIFACT_REL,
           rubric_version: str = "manifest-test") -> None:
    p = rd / ARTIFACT_REL
    sha = sha or es.sha256_file(p)
    rows = {"schema_version": 1, "phase_id": PHASE, "rows": [
        {"kind": "author", "execution_id": author_exec, "phase_id": PHASE,
         "artifact": ARTIFACT_REL, "artifact_sha256": sha,
         "model": author_model, "provider": "deepseek-direct",
         "model_class": es.model_class_of(author_model),
         "stamped_at": es.utcnow()},
        {"kind": "reviewer", "execution_id": reviewer_exec, "phase_id": PHASE,
         "reviewed_artifact": reviewed_artifact_rel,
         "reviewed_artifact_sha256": sha,
         "model": reviewer_model, "provider": "moonshot",
         "model_class": es.model_class_of(reviewer_model),
         "rubric_version": rubric_version, "stamped_at": es.utcnow()},
    ]}
    d = rd / "working" / "execution-stamps"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{PHASE}.stamp.json").write_text(json.dumps(rows, indent=2))


def _reason(rd: pathlib.Path, **kw) -> str:
    return es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL, **kw)


# ── 1. Same-execution forgery: prose claims a different reviewer ────────────

def test_forged_graded_by_same_execution_report_rejected_by_trusted_id(tmp_path):
    """The report PROSE claims 'qc-specialist-presentations' graded it — but
    the trusted stamps show the reviewer execution IS the author execution.
    The gate refuses on the trusted id, never the prose."""
    rd = _rd(tmp_path)
    _report(rd, graded_by="qc-specialist-presentations")  # the forgery
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-A")
    reason = es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL)
    assert reason, "same-execution review must be refused"
    assert "SAME execution" in reason
    assert "AF-EXEC-STAMP" in reason


def test_forged_graded_by_cannot_launder_through_report_text(tmp_path):
    """Even an elaborate prose qc_independence block naming a reviewer and an
    'independent: true' flag cannot substitute for the reviewer stamp."""
    rd = _rd(tmp_path)
    p = rd / ARTIFACT_REL
    p.write_text(json.dumps({
        "gate": "Phase 1Q", "average": 9.2, "pass": True,
        "qc_independence": {"graded_by": "totally-independent-reviewer",
                            "independent": True, "self_graded": False},
    }), encoding="utf-8")
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-A")  # same execution
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert "SAME execution" in reason


# ── 2. Post-pass mutation: staleness is per-artifact ────────────────────────

def test_mutate_reviewed_file_after_pass_stales_only_that_qc(tmp_path):
    rd = _rd(tmp_path)
    p = _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B")
    assert es.qc_independence_reason(rd, PHASE, None, p) == ""

    # Post-pass mutation: bytes change AFTER the pass.
    p.write_text(json.dumps({"gate": "Phase 1Q", "average": 9.9, "pass": True,
                             "qc_independence": {"graded_by": "x"}}), encoding="utf-8")
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert reason and "no ACTIVE author stamp" in reason, reason

    # stale_units: the mutated unit is stale, an untouched sibling is not.
    sibling = rd / "working" / "qc" / "untouched_qc_report.json"
    sibling.write_text(json.dumps({"gate": "Phase 1Q", "average": 9.2}))
    # stamp the sibling too (its own phase for the units contract)
    sib_rel = "working/qc/untouched_qc_report.json"
    sha = es.sha256_file(sibling)
    d = rd / "working" / "execution-stamps"
    rows = json.loads((d / f"{PHASE}.stamp.json").read_text())
    rows["rows"].append({"kind": "author", "execution_id": "exec-B", "phase_id": PHASE,
                         "artifact": sib_rel, "artifact_sha256": sha,
                         "model": "m", "provider": "p", "model_class": "deepseek",
                         "stamped_at": es.utcnow()})
    rows["rows"].append({"kind": "reviewer", "execution_id": "exec-C", "phase_id": PHASE,
                         "reviewed_artifact": sib_rel, "reviewed_artifact_sha256": sha,
                         "model": "kimi-v4-a", "provider": "moonshot",
                         "model_class": "kimi", "rubric_version": "r",
                         "stamped_at": es.utcnow()})
    (d / f"{PHASE}.stamp.json").write_text(json.dumps(rows))
    stale = es.stale_units(rd, PHASE, [p, sibling])
    assert ARTIFACT_REL in stale, "the mutated unit must be stale"
    assert sib_rel not in stale, "the untouched sibling stays covered"


def test_review_of_older_revision_never_passes_for_current(tmp_path):
    """A reviewer stamp bound to the OLD sha does not cover the mutated file —
    'a review of an older revision is stale'."""
    rd = _rd(tmp_path)
    p = _report(rd)
    old_sha = es.sha256_file(p)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B", sha=old_sha)
    p.write_text('{"gate":"Phase 1Q","average":9.2,"pass":true,"tampered":true}')
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert reason and "no ACTIVE author stamp" in reason


# ── 3. Repair needs a fresh independent review of the NEW hash ──────────────

def test_repair_promotes_new_author_revision_needs_fresh_review(tmp_path):
    rd = _rd(tmp_path)
    p = _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B")
    assert es.qc_independence_reason(rd, PHASE, None, p) == ""

    # The reviewer repairs content: NEW author revision...
    p.write_text(json.dumps({"gate": "Phase 1Q", "average": 9.4, "pass": True,
                             "repaired": True,
                             "qc_independence": {"graded_by": "qc-specialist-presentations"}}))
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert reason, "a repaired artifact without a fresh stamp+review is incomplete"

    # ...the repair promotes a new author revision and a FRESH review covers it.
    _stamp(rd, author_exec="exec-A2", reviewer_exec="exec-B2")
    assert es.qc_independence_reason(rd, PHASE, None, p) == "", \
        "the repaired revision with fresh trusted review must pass"


def test_repair_reviewed_by_same_execution_is_refused(tmp_path):
    rd = _rd(tmp_path)
    p = _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-A")
    assert "SAME execution" in es.qc_independence_reason(rd, PHASE, None, p)


# ── 4. Opposite-model policy + rubric version + rollback ────────────────────

def test_opposite_model_policy_enforced_when_demanded(tmp_path):
    rd = _rd(tmp_path)
    _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B",
           author_model="deepseek-v4-pro", reviewer_model="deepseek-v4-flash")
    assert es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL) == "", \
        "default policy does not demand opposite models"
    reason = es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL,
                                       require_opposite_model=True)
    assert reason and "opposite implementation/QC model" in reason
    # A genuinely opposite class passes the demanded policy.
    _stamp(rd, author_exec="exec-A2", reviewer_exec="exec-B2",
           author_model="deepseek-v4-pro", reviewer_model="claude-opus-4")
    assert es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL,
                                     require_opposite_model=True) == ""


def test_rubric_version_required(tmp_path):
    rd = _rd(tmp_path)
    _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B", rubric_version=None)
    reason = es.qc_independence_reason(rd, PHASE, None, rd / ARTIFACT_REL)
    assert reason and "rubric version" in reason


def test_missing_stamp_is_unproven_fail_closed(tmp_path):
    rd = _rd(tmp_path)
    p = _report(rd)
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert reason and "no ACTIVE author stamp" in reason


def test_reviewer_stamp_only_author_missing_is_unproven(tmp_path):
    rd = _rd(tmp_path)
    p = _report(rd)
    sha = es.sha256_file(p)
    d = rd / "working" / "execution-stamps"
    d.mkdir(parents=True, exist_ok=True)
    rows = {"schema_version": 1, "phase_id": PHASE, "rows": [
        {"kind": "reviewer", "execution_id": "exec-B", "phase_id": PHASE,
         "reviewed_artifact": ARTIFACT_REL, "reviewed_artifact_sha256": sha,
         "model": "kimi-v4-a", "provider": "moonshot", "model_class": "kimi",
         "rubric_version": "r", "stamped_at": es.utcnow()}]}
    (d / f"{PHASE}.stamp.json").write_text(json.dumps(rows))
    reason = es.qc_independence_reason(rd, PHASE, None, p)
    assert reason and "no ACTIVE author stamp" in reason


def test_rollback_flag_restores_text_only_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_EXECUTION_STAMPS", "0")
    rd = _rd(tmp_path)
    p = _report(rd)
    # No stamps at all — the surface is OFF, so the reason is "" (the caller
    # then applies its own pre-PRES-042 text check).
    assert es.qc_independence_reason(rd, PHASE, None, p) == ""


def test_aggregate_consumes_stamps_end_to_end(tmp_path):
    """Full aggregate row: a domain whose stamps are MISSING is a blocking
    finding; once the trusted stamps exist the same aggregate passes the
    stamp surface (other domains' text provenance unchanged)."""
    import qc_aggregate
    rd = _rd(tmp_path)
    _report(rd)
    report = qc_aggregate.aggregate(rd)
    assert report["pass"] is False
    assert any("AF-EXEC-STAMP" in r for r in report["blocking_reasons"])

    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B")
    report = qc_aggregate.aggregate(rd)
    assert not any("AF-EXEC-STAMP" in r for r in report["blocking_reasons"]), \
        report["blocking_reasons"]