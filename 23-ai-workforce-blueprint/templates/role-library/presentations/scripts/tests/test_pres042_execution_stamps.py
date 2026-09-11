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
# ── QC-SONNET repairs: production topology + upstream mutation ───────────────

def test_production_topology_report_plus_consumed_passes_aggregate(tmp_path):
    """QC-SONNET-R4/R5: the stamp layout a PRODUCTION dispatch leaves (author
    on report + reviewer on report AND on consumed inputs, producer author on
    inputs) passes the REAL aggregate — no always-block."""
    sys.path.insert(0, str(SCRIPTS))
    import qc_aggregate
    from presentation_job import execution_stamp as _es
    rd = tmp_path / "run"
    (rd / "working" / "qc").mkdir(parents=True)
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "prompts").mkdir(parents=True)
    (rd / "working" / "deliverables").mkdir(parents=True)
    (rd / "renders").mkdir(parents=True)
    # Five averaged domains with genuine reports + staged consumed inputs.
    domains = {
        "P1Q-COPY-QC": ("working/qc/copy_qc_report.json", ["working/copy/slides_copy.md"]),
        "P-TYPO-QC": ("working/qc/typography_qc_report.json", ["working/research/design-brief-a.md"]),
        "P-PROMPT-QC": ("working/qc/prompt_qc_report.json", ["working/prompts/slide-01.txt"]),
        "P-IMAGE-QC": ("working/qc/image_qc_report.json", ["renders/slide-01.png"]),
        "P-SPEECH-QC": ("working/qc/speech_qc_report.json",
                        ["working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md"]),
    }
    for phase_id, (report_rel, inputs) in domains.items():
        rp = rd / report_rel
        rp.write_text(json.dumps({
            "gate": phase_id, "average": 9.2, "pass": True,
            "triggered_autofails": [],
            "qc_independence": {"graded_by": "qc-specialist-x",
                                "independent": True},
        }), encoding="utf-8")
        for crel in inputs:
            cp = rd / crel
            cp.write_bytes(b"\x89PNG" + b"\x00" * 32 if cp.suffix == ".png"
                           else f"# input for {phase_id}\n".encode())
    # Priority-shift report (checklist shape).
    (rd / "working" / "qc" / "priority_shift_report.json").write_text(json.dumps({
        "schema": "priority_shift_report/v1", "pass": True,
        "items": [{"item": "i", "pass": True, "evidence": "ok"}]}))
    for crel in ["working/copy/priority_shift_spec.json", "working/copy/slides_copy.md"]:
        cp = rd / crel
        if not cp.is_file():
            cp.write_text("# shift input\n", encoding="utf-8")
    # Stamp EXACTLY like the production dispatcher: author on every produced
    # artifact; the QC execution's reviewer id on consumed inputs AND on the
    # report itself (R4); producer author + QC reviewer on inputs.
    for phase_id, (report_rel, inputs) in {
            **domains,
            "P-SHIFT-QC": ("working/qc/priority_shift_report.json",
                           ["working/copy/priority_shift_spec.json",
                            "working/copy/slides_copy.md"])}.items():
        rp = rd / report_rel
        rev_id = f"qc-{phase_id}-prod-1"
        _es.author_stamp(rd, phase_id, rp, model="deepseek-v4-pro",
                         provider="deepseek-direct")
        _es.qc_stamp(rd, phase_id, rp, reviewer_execution_id=rev_id,
                     model="kimi-v4-a", provider="moonshot",
                     rubric_version="manifest-prod")
        for crel in inputs:
            cp = rd / crel
            if not any(r.get("artifact") == crel
                       for r in _es._load_stamps(rd, "P-PROD").get("rows", [])):
                _es.author_stamp(rd, "P-PROD", cp, model="deepseek-v4-pro",
                                 provider="deepseek-direct")
            _es.qc_stamp(rd, phase_id, cp, reviewer_execution_id=rev_id,
                         model="kimi-v4-a", provider="moonshot",
                         rubric_version="manifest-prod")
    report = qc_aggregate.aggregate(rd)
    stamp_blocks = [b for b in report["blocking_reasons"] if "AF-EXEC-STAMP" in b]
    assert stamp_blocks == [], f"production topology must not block: {stamp_blocks}"


def test_upstream_mutation_after_pass_blocks_until_fresh_review(tmp_path):
    """QC-PRES-042 row 2 (production meaning): mutate a CONSUMED upstream
    input after the QC pass — the domain blocks even though the report bytes
    are untouched; a fresh reviewer stamp on the new bytes unblocks."""
    sys.path.insert(0, str(SCRIPTS))
    from presentation_job import execution_stamp as _es
    rd = _rd(tmp_path)
    p = _report(rd)
    _stamp(rd, author_exec="exec-A", reviewer_exec="exec-B")
    upstream = rd / "working" / "copy" / "slides_copy.md"
    upstream.parent.mkdir(parents=True, exist_ok=True)
    upstream.write_text("# deck copy v1\n", encoding="utf-8")
    # Production mints a producer author stamp at the artifact write sites.
    _es.author_stamp(rd, "P-PROD", upstream, model="deepseek-v4-pro",
                     provider="deepseek-direct")
    up_sha = _es.sha256_file(upstream)
    store = rd / "working" / "execution-stamps" / f"{PHASE}.stamp.json"
    obj = json.loads(store.read_text(encoding="utf-8"))
    obj["rows"].append(
        {"kind": "reviewer", "execution_id": "exec-B", "phase_id": PHASE,
         "reviewed_artifact": "working/copy/slides_copy.md",
         "reviewed_artifact_sha256": up_sha,
         "model": "kimi-v4-a", "provider": "moonshot",
         "model_class": "kimi", "rubric_version": "manifest-test",
         "stamped_at": _es.utcnow()})
    store.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    assert _es.consumed_coverage_reasons(rd, PHASE, upstream) == []
    # Mutate the upstream AFTER the pass: coverage breaks.
    upstream.write_text("# deck copy v2 -- repaired slide\n", encoding="utf-8")
    reasons = es.consumed_coverage_reasons(rd, PHASE, upstream)
    assert reasons and "CURRENT content" in reasons[0]
    # Fresh review of the NEW bytes restores coverage (production re-stamps
    # the producer author row at the repair write site, then QC re-stamps).
    _es.author_stamp(rd, "P-PROD", upstream, model="deepseek-v4-pro",
                     provider="deepseek-direct")
    obj = json.loads(store.read_text(encoding="utf-8"))
    obj["rows"].append(
        {"kind": "reviewer", "execution_id": "exec-B2", "phase_id": PHASE,
         "reviewed_artifact": "working/copy/slides_copy.md",
         "reviewed_artifact_sha256": _es.sha256_file(upstream),
         "model": "kimi-v4-a", "provider": "moonshot",
         "model_class": "kimi", "rubric_version": "manifest-test",
         "stamped_at": _es.utcnow()})
    store.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    assert _es.consumed_coverage_reasons(rd, PHASE, upstream) == []


def test_dispatcher_reviewer_stamp_covers_manifest_consumes_in_repo_layout(tmp_path):
    """QC-OPUS seam repair (PRES-042): the dispatcher's _stamp_qc_reviewer must
    resolve the manifest the SAME way qc_aggregate's _resolve_consumes does
    (run-pinned state.json > dept sops/ > find_repo_root walk-up). The previous
    hand-rolled candidates pointed at scripts/sops/ (wrong parent) and a fixed
    depth fallback, so in the REPO layout the dispatcher minted report-only
    stamps while the aggregate's walk-up resolver still demanded consumed
    coverage — an undeployable always-block. This test pins the repaired seam:
    from THIS scripts dir (repo layout, no sops/ sibling), the dispatcher's
    reviewer stamp must cover the phase's manifest consumes at their current
    sha, and the aggregate's consumed-coverage check must agree."""
    sys.path.insert(0, str(SCRIPTS))
    from presentation_job import dispatcher as _disp
    rd = _rd(tmp_path)
    # Stage exactly what a production P1Q-COPY-QC dispatch sees: the consumed
    # upstream artifact (produced by its own author execution) + the report.
    upstream = rd / "working" / "copy" / "slides_copy.md"
    upstream.parent.mkdir(parents=True, exist_ok=True)
    upstream.write_text("# deck copy (production topology)\n", encoding="utf-8")
    es.author_stamp(rd, "P4-COPY", upstream, model="deepseek-v4-pro",
                    provider="deepseek-direct")
    report = _report(rd)
    # No state.json manifest pin: exercise the dept-sops / walk-up legs.
    _disp._stamp_qc_reviewer(rd, PHASE, report, model="kimi-v4-a",
                             provider="moonshot")
    rows = es._load_stamps(rd, PHASE).get("rows") or []
    reviewed = {r.get("reviewed_artifact") for r in rows
                if r.get("kind") == "reviewer"}
    assert "working/copy/slides_copy.md" in reviewed, (
        f"dispatcher reviewer stamp must cover the manifest consumes "
        f"(got {reviewed!r}) — the repo-layout seam is open")
    assert "working/qc/copy_qc_report.json" in reviewed, (
        "dispatcher reviewer stamp must still attest the report itself")
    # The aggregate's own coverage check now agrees: zero blocks.
    reasons = es.consumed_coverage_reasons(rd, PHASE, upstream)
    assert reasons == [], reasons


def test_qc_manifest_for_run_prefers_state_pin(tmp_path):
    """The run's pinned state.json manifest_path is authoritative: when present
    it wins over every layout heuristic, so stamps and the engine always grade
    against the file this run was launched with."""
    sys.path.insert(0, str(SCRIPTS))
    from presentation_job import dispatcher as _disp
    rd = _rd(tmp_path)
    fake = rd / "elsewhere" / "PIPELINE-MANIFEST.json"
    fake.parent.mkdir(parents=True)
    fake.write_text(json.dumps({"manifest_version": "test-pin", "phases": []}),
                    encoding="utf-8")
    (rd / "state.json").write_text(
        json.dumps({"manifest_path": str(fake)}), encoding="utf-8")
    got = _disp._qc_manifest_for_run(rd)
    assert got == fake.resolve(), got
