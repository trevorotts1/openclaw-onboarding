"""End-to-end + negative tests for the full-funnel P0→P5 pipeline (goal #196).

These are the on-fixture integration bites the acceptance checklist names
(T-1..T-9, T-N1..T-N6) plus the funnel_rollback idempotency contract. They run
OFFLINE (no live CRM / Gemini / network) by exercising funnel_fixture_harness +
funnel_rollback + funnel_rubrics against a temp evidence tree.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import funnel_fixture_harness as harness  # noqa: E402
import funnel_rubrics as rubrics  # noqa: E402
from funnel_rollback import FunnelRollbackInputs, run_funnel_rollback  # noqa: E402


@pytest.fixture
def happy_run(tmp_path):
    run_dir = str(tmp_path / "run")
    ev = harness.build_funnel(run_dir)
    return run_dir, ev


# ── T-1..T-9: the happy-path integration evidence the checklist demands ─────

def test_t1_all_seven_stage_artifacts_exist(happy_run):
    run_dir, _ = happy_run
    fr = os.path.join(run_dir, "working", "funnels", "scent-bar-workshop")
    assert os.path.isfile(os.path.join(fr, "offer-spec.json"))          # P0
    assert os.path.isfile(os.path.join(fr, "funnel-spec.json"))         # P1
    assert os.path.isfile(os.path.join(fr, "persona-selection-log.md")) # P1 grounding
    assert os.path.isfile(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md"))   # P2
    assert os.path.isfile(os.path.join(run_dir, "working", "email", "scent-bar-workshop", "email-sequence.json"))  # P2e
    assert os.path.isfile(os.path.join(fr, "assets-manifest.json"))     # P3
    assert os.path.isfile(os.path.join(fr, "build-result.json"))        # P4


def test_t2_offer_spec_has_required_fields(happy_run):
    run_dir, _ = happy_run
    offer = json.load(open(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "offer-spec.json")))
    for k in ["product_name", "deliverables", "price_points", "guarantee", "bonuses", "positioning"]:
        assert offer.get(k), f"offer-spec missing {k}"


def test_t3_persona_grounded_on_hormozi_with_real_selector(happy_run):
    run_dir, _ = happy_run
    log = open(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "persona-selection-log.md")).read()
    assert "hormozi-100m-offers" in log
    # The real selector ran for the web-development funnel surface (U1 tag widen).
    assert "selector_ran" in log


def test_t4_copy_reaches_approved(happy_run):
    run_dir, _ = happy_run
    copy = open(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md")).read()
    assert "status: APPROVED" in copy
    cjson = json.load(open(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.json")))
    assert cjson["status"] == "APPROVED"


def test_t5_ecosystem_receipts_present(happy_run):
    run_dir, _ = happy_run
    eco = os.path.join(run_dir, "ecosystem")
    for name in ["calendar", "product-price", "optin-form", "contact-test", "workflow"]:
        r = json.load(open(os.path.join(eco, f"{name}.json")))
        assert r["http_status"] == 201 and r["qc_passed"]


def test_t6_waiting_on_dependency_used_and_ordering_enforced(happy_run):
    _, ev = happy_run
    assert ev["board"]["waiting_on_dependency_used"] is True
    # Board handoff events fired at P-boundaries (SOP-07 F8).
    slugs = {h["job_id"] for h in ev["board"]["handoffs"]}
    assert {"p1-funnel-spec", "p4-build", "p5-automation"} & slugs


def test_t7_final_preview_verify_is_seven_of_seven(happy_run):
    run_dir, ev = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    assert raw["stages_total"] == 7
    assert raw["stages_complete"] == 7
    assert raw["overall_pass"] is True
    assert ev["parent_done"] is True


def test_t8_verify_summary_consistent_with_raw(happy_run):
    run_dir, _ = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    summary = json.load(open(os.path.join(run_dir, "scorecard", "verify-summary.json")))
    assert summary["passed"] == raw["stages_complete"]
    assert summary["overall_pass"] == raw["overall_pass"]


def test_t9_all_eleven_rubrics_pass(happy_run):
    run_dir, _ = happy_run
    results = rubrics.score_all(run_dir, cc_invariant_ok=True)
    assert {r.id for r in results} == set(rubrics.RUBRIC_IDS)
    for r in results:
        assert r.passed and r.score >= rubrics.THRESHOLD, f"{r.id} scored {r.score}"


# ── T-N1..T-N6: negative fixtures ───────────────────────────────────────────

def test_tn1_p4_failure_triggers_rollback_and_parent_not_done(tmp_path):
    run_dir = str(tmp_path / "fail")
    ev = harness.build_funnel(run_dir, inject_failure="p4-build")
    assert ev["parent_done"] is False              # parent does NOT publish (F5)
    rb = json.load(open(os.path.join(run_dir, "logs", "funnel_rollback.json")))
    assert rb["triggered_by_stage"] == "p4-build"
    # Every autosaved page reverted byte-identical (live pointer unmoved).
    assert all(c["byte_identical"] for c in rb["baseline_md5_confirmed"])


def test_tn2_surviving_pending_qc_fails_r_copy(happy_run):
    run_dir, _ = happy_run
    p = os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md")
    open(p, "w").write("# x\nstatus: PENDING-QC\n")
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-COPY"] is False


def test_tn3_deleted_persona_log_fails_r_persona_grounding(happy_run):
    run_dir, _ = happy_run
    os.remove(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "persona-selection-log.md"))
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-PERSONA-GROUNDING"] is False


def test_tn4_injected_false_summary_fails_kanban_and_raises_contradiction(happy_run):
    run_dir, _ = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    raw["stages_complete"] = 5
    raw["overall_pass"] = False
    for i in (5, 6):
        raw["stages"][i]["passed"] = False
    json.dump(raw, open(os.path.join(run_dir, "logs", "final-preview-verify.json"), "w"))
    # summary still claims 7/7 — the injected lie. Rubric must catch it.
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-KANBAN-CORRECTNESS"] is False
    # And the harness consistency guard would have raised on write.
    summary = {"passed": 7, "overall_pass": True}
    with pytest.raises(AssertionError):
        harness._assert_summary_consistent(summary, raw["stages"])


def test_tn5_empty_evidence_fails_every_artifact_rubric(tmp_path):
    run_dir = str(tmp_path / "empty")
    os.makedirs(run_dir)
    res = {r.id: r.passed for r in rubrics.score_all(run_dir, cc_invariant_ok=True)}
    # Every artifact-backed rubric fails; only R-CC-SYNC (external invariant) can pass.
    for rid in ["R-COPY", "R-STRUCTURE", "R-PAGES", "R-FORMS", "R-PRODUCT",
                "R-EMAILS", "R-AUTOMATIONS", "R-PERSONA-GROUNDING", "R-KANBAN-CORRECTNESS"]:
        assert res[rid] is False, f"{rid} should fail on empty evidence"


def test_tn6_cc_invariant_failure_fails_r_cc_sync(happy_run):
    run_dir, _ = happy_run
    res = {r.id: r.passed for r in rubrics.score_all(run_dir, cc_invariant_ok=False)}
    assert res["R-CC-SYNC"] is False


# ── funnel_rollback idempotency (SOP-07 §7 final rule) ──────────────────────

def test_rollback_is_idempotent(tmp_path):
    ev_root = str(tmp_path / "logs")
    deleted = []
    inp = FunnelRollbackInputs(
        parent_task_id="epic", idempotency_key="k",
        triggered_by_stage="p5-automation", failed_task_id="p5",
        autosaved_pages=[{"funnel_id": "f", "page_id": "pg", "baseline": {"a": 1}, "current_version": 2}],
        ecosystem_objects=[{"type": "calendar", "id": "cal1", "qc_passed": False}],
        test_contact_id="contact-1",
    )
    live_objects = {("calendar", "cal1")}
    live_contacts = {"contact-1"}

    def deleter(t, i):
        live_objects.discard((t, i))
        deleted.append((t, i))
        return {"deleted": i}

    def cdeleter(i):
        live_contacts.discard(i)
        deleted.append(("contact", i))
        return {"deleted": i}

    common = dict(
        reverter=lambda req: req["baseline"],
        object_deleter=deleter,
        contact_deleter=cdeleter,
        object_exists=lambda t, i: (t, i) in live_objects,
        contact_exists=lambda i: i in live_contacts,
    )
    r1 = run_funnel_rollback(inp, ev_root, **common)
    first_deletes = list(deleted)
    r2 = run_funnel_rollback(inp, ev_root, **common)
    # Second run deletes NOTHING new (idempotent); record marks already_done.
    assert deleted == first_deletes, "rollback double-deleted on replay"
    assert any(o.get("already_done") for o in r2["objects_deleted"])
    assert r2["test_contact_deleted"] is True


def test_rollback_keeps_verified_objects(tmp_path):
    ev_root = str(tmp_path / "logs")
    deleted = []
    inp = FunnelRollbackInputs(
        parent_task_id="epic", idempotency_key="k",
        triggered_by_stage="p5", failed_task_id="p5",
        autosaved_pages=[],
        ecosystem_objects=[
            {"type": "calendar", "id": "keep", "qc_passed": True},     # verified -> keep
            {"type": "workflow", "id": "drop", "qc_passed": False},    # unverified -> delete
        ],
        test_contact_id=None,
    )
    run_funnel_rollback(
        inp, ev_root,
        object_deleter=lambda t, i: deleted.append((t, i)),
        object_exists=lambda t, i: True,
    )
    assert ("workflow", "drop") in deleted
    assert ("calendar", "keep") not in deleted
