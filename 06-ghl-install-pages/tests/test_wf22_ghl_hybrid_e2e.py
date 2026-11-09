"""WF22 (GHL-022) cross-lane end-to-end integration checks.

One fake, deterministic scenario pack consumes the shared contract shapes and
drives the REAL Skill 6 receipts store and rail router with fake runners. No
network, no browser, no GoHighLevel write, no owner notification.

Acceptance coverage (see the run acceptance map):
  A27  — one end-to-end course/group/post/fulfillment/board fake scenario
         consumes the shared schema consistently.
  The individual seams (workflow public/fallback/monitoring, KB -> responder ->
  widget, Meeting/quiz managed-browser boundary, CC -> Projects one-way,
  launch fulfillment/board with old+new producers) are exercised here as
  integration fixtures; their owning lanes keep their own unit suites.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from ghl_hybrid_fixtures import harness  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(TESTS_DIR))
TOOLS_DIR = os.path.join(REPO_ROOT, "06-ghl-install-pages", "tools")
SHARED_GHL_DIR = os.path.join(REPO_ROOT, "shared-utils", "ghl")
for _path in (TOOLS_DIR, SHARED_GHL_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _router():
    import ghl_object_router
    return ghl_object_router


def _receipts():
    return harness.receipts_module()


def _fixture_path(name: str) -> str:
    if name.endswith(".json"):
        path = os.path.join(harness.SCENARIOS_DIR, name)
    else:
        path = os.path.join(harness.SCENARIOS_DIR, name + ".json")
    return path


def test_a27_end_to_end_schema_consistency():
    """A27: every scenario consumes the shared fixture contract consistently."""
    names = harness.scenario_names()
    assert len(names) == 6, names
    tenant_ids = set()
    run_ids = set()
    for name in names:
        scenario = harness.load_scenario(name)
        assert scenario["scenario_id"]
        assert scenario["assumed_checkpoints"], f"{name} must name its assumed checkpoints"
        assert scenario["acceptance_ids"], f"{name} must map to acceptance ids"
        tenant_ids.add((scenario["tenant"]["company_id"], scenario["tenant"]["location_id"]))
        run_ids.add(scenario["tenant"]["run_id"])
        for receipt in harness.iter_receipts(scenario):
            harness.validate_named(receipt, "hybrid-operation-receipt.v1.schema.json")
            assert receipt["company_id"] == scenario["tenant"]["company_id"]
            assert receipt["location_id"] == scenario["tenant"]["location_id"]
            assert receipt["run_id"] == scenario["tenant"]["run_id"]
            if receipt["outcome"] == "verified":
                assert receipt["readback"]["state"] == "matched", receipt["receipt_id"]
            if receipt["outcome"] == "unknown_outcome":
                assert receipt["readback"]["state"] != "matched", receipt["receipt_id"]
            assert receipt["next_action"] is None or isinstance(receipt["next_action"], str)
    assert len(tenant_ids) == 1, "all scenarios must share one synthetic tenant"
    assert len(run_ids) == 1, "all scenarios must share one synthetic run"


def test_course_group_post_access_receipt_is_consistent(tmp_path):
    """Course/group/post/access: real router + real F6 reducer, no fake success."""
    scenario = harness.load_scenario("course-group-post-access")
    tenant = scenario["tenant"]

    plan = {"schema_version": "1.0.0", "course": scenario["course"],
            "modules": scenario["modules"]}
    harness.validate_named(plan, "course-build-plan.v1.schema.json")
    harness.validate_named(scenario["asset_manifest"], "course-asset-manifest.v1.schema.json")
    harness.validate_named(scenario["learning_association"], "learning-association.v1.schema.json")
    harness.validate_named(scenario["access"], "course-delivery-receipt.v1.schema.json")

    router = _router()
    evidence_root = str(tmp_path / "evidence")
    os.makedirs(evidence_root, exist_ok=True)
    calls = []

    def course_runner(step):
        calls.append(step.rail)
        return {"ok": True, "response_id": scenario["course"]["course_product_id"],
                "location_id": tenant["location_id"]}

    def verifier(response_id):
        return {"ok": True, "checked_fields": ["title", "visibility"],
                "location_id": tenant["location_id"]}

    created = router.execute_write(
        "course", "synthetic-launch-101",
        evidence_root=evidence_root,
        rail_runners={"browser": course_runner},
        verifier=verifier,
        request_shape={"title": scenario["course"]["title"]},
        expected_location_id=tenant["location_id"],
        run_id=tenant["run_id"],
    )
    assert created["ok"] is True, created
    assert created["action"] == "created"
    assert created["receipt"]["verify"]["ok"] is True

    # Persist every scenario object through the SAME F6 store (the course entry
    # re-verifies the object the router just created).
    harness.write_object_receipts(evidence_root, scenario["object_receipts"])

    receipts = _receipts()
    summary = receipts.reduce_receipts(evidence_root, strict=True)
    receipts.assert_consistent(summary, evidence_root)

    assert summary["total"] == scenario["expected"]["object_receipt_total_after_dedupe"], summary
    assert summary["all_verified"] is scenario["expected"]["all_object_receipts_verified"], summary
    assert summary["failed"] == [] and summary["unreadable"] == [] and summary["unverified"] == []
    assert "course:synthetic-launch-101" in summary["created"]
    assert "access_grant:synthetic-enrollment" in summary["created"]
    assert "community_group:synthetic-launch-101" in summary["reused"]

    # Idempotent resume: the probe short-circuits the create rail entirely.
    reuse_root = str(tmp_path / "reuse")
    os.makedirs(reuse_root, exist_ok=True)
    reuse_calls = []

    def reuse_runner(step):  # pragma: no cover - must not run
        reuse_calls.append(step.rail)
        return {"ok": True, "response_id": "SYNTHETIC_SECOND_COURSE"}

    reused = router.execute_write(
        "course", "synthetic-launch-101",
        evidence_root=reuse_root,
        idempotency_probe=lambda: {"id": scenario["course"]["course_product_id"],
                                   "location_id": tenant["location_id"]},
        rail_runners={"browser": reuse_runner},
        verifier=verifier,
        expected_location_id=tenant["location_id"],
        run_id=tenant["run_id"],
    )
    assert reused["action"] == "reused", reused
    assert reuse_calls == [], "idempotent reuse must not run the create rail again"

    # Cross-tenant reuse is refused, never silently accepted, and lands in its
    # own evidence root so it cannot overwrite the truthful scenario receipts.
    foreign_root = str(tmp_path / "foreign")
    os.makedirs(foreign_root, exist_ok=True)
    foreign = router.execute_write(
        "course", "synthetic-launch-101",
        evidence_root=foreign_root,
        idempotency_probe=lambda: {"id": "SYNTHETIC_FOREIGN_COURSE",
                                   "location_id": "SYNTHETIC_OTHER_LOCATION"},
        rail_runners={"browser": course_runner},
        verifier=verifier,
        expected_location_id=tenant["location_id"],
        run_id=tenant["run_id"],
    )
    assert foreign["action"] == "failed", foreign
    assert "tenant mismatch" in (foreign["error"] or "")

    assert scenario["access"]["payment_claim"] is False
    assert scenario["access"]["access_verified"] is True
    assert scenario["expected"]["duplicate_objects_on_resume"] == 0
    assert scenario["learning_association"]["detach_deletes_course"] is False
    assert scenario["community_post"]["state"] == "published"


def test_readback_mismatch_and_overclaim_are_refused(tmp_path):
    """No receipt = not created: a mismatched read-back is an honest failure."""
    evidence_root = str(tmp_path / "evidence")
    os.makedirs(evidence_root, exist_ok=True)
    router = _router()
    result = router.execute_write(
        "course", "synthetic-readback-mismatch",
        evidence_root=evidence_root,
        rail_runners={"browser": lambda step: {"ok": True, "response_id": "SYNTHETIC_X"}},
        verifier=lambda rid: {"ok": False, "detail": "title mismatch"},
        expected_location_id="SYNTHETIC_GHL_LOCATION",
        run_id="SYNTHETIC_RUN_WF22_001",
    )
    assert result["ok"] is False
    assert result["action"] == "failed"
    receipts = _receipts()
    summary = receipts.reduce_receipts(evidence_root)
    assert summary["created"] == []
    assert "course:synthetic-readback-mismatch" in summary["failed"]
    assert summary["all_verified"] is False

    lie = dict(summary)
    lie["created"] = ["course:synthetic-readback-mismatch"]
    with pytest.raises(receipts.ReceiptContradiction):
        receipts.assert_consistent(lie, evidence_root)


def test_workflow_public_route_fallback_and_monitoring(tmp_path):
    """Workflow: public route facts, explicit beta fallback, event-vs-cohort label."""
    scenario = harness.load_scenario("workflow-public-fallback-monitoring")
    import capability_inventory as contracts
    from capability_inventory import OpClass

    reads = contracts.select_route(OpClass.LIST, resource="workflows")
    assert reads, "workflow LIST must have a public read route"
    assert all(cap.route == "GET /workflows/" for cap in reads), reads
    for write_class in (OpClass.CREATE, OpClass.EDIT, OpClass.DELETE):
        assert contracts.select_route(write_class, resource="workflows",
                                      dynamic_confirmed=False) == [], write_class

    router = _router()
    workflow_rails = [step.rail for step in router.route("workflow").rails]
    assert "skill44_build_api" in workflow_rails, workflow_rails
    assert router.rail_requires_browser_context("skill44_build_api") is True
    assert router.is_services_route("rest_services") is True

    evidence_root = str(tmp_path / "evidence")
    os.makedirs(evidence_root, exist_ok=True)
    attempts = []

    def build_runner(step):
        attempts.append(step.rail)
        return {"ok": True, "response_id": "SYNTHETIC_WORKFLOW_ID"}

    fallback = router.execute_write(
        "workflow", "synthetic-launch-followup",
        evidence_root=evidence_root,
        rail_runners={"skill44_build_api": build_runner},
        verifier=lambda rid: {"ok": True, "checked_fields": ["graph", "revision"]},
        expected_location_id=scenario["tenant"]["location_id"],
        run_id=scenario["tenant"]["run_id"],
    )
    assert fallback["action"] == "created", fallback
    assert fallback["rail"] == "skill44_build_api"
    assert attempts == ["skill44_build_api"], "the failed public route must not be re-run"

    public_route = scenario["public_route"]
    assert public_route["available"] is False
    assert public_route["beta_error"] == "WORKFLOW_API_NOT_ENABLED_FOR_LOCATION"
    assert public_route["classified_as"] == "beta_not_enabled"
    assert scenario["fallback"]["retried_public_after_submit"] is False

    assert scenario["validation"]["http_status"] == 200
    assert scenario["validation"]["valid"] is False
    assert scenario["validation"]["save_attempted"] is False
    assert scenario["published_workflow"]["silent_draft_transition"] is False
    assert scenario["stale_revision"]["reread_before_retry"] is True

    monitoring = scenario["monitoring"]
    assert monitoring["count_kind"] == "events"
    assert monitoring["same_window_ratio_is_cohort_conversion"] is False
    assert monitoring["retention"]["silently_dropped_rows"] == 0
    states = monitoring["evidence_states"]
    assert states["builder_tests"] == "offline"
    assert states["empty_log"] == "not_run"
    assert states["controlled_live_execution"] == "not_run"
    require = contracts.require_route(OpClass.LIST, resource="workflows")
    assert require.route == "GET /workflows/"


def test_rate_limit_never_tier_hops(tmp_path):
    """F8: a 429 cools down on the SAME rail; it never falls to the browser."""
    evidence_root = str(tmp_path / "evidence")
    os.makedirs(evidence_root, exist_ok=True)
    router = _router()
    calls = []

    def caf_runner(step):
        calls.append(step.rail)
        return {"ok": False, "status": 429, "error_kind": "rate_limit"}

    def browser_runner(step):  # pragma: no cover - must never run
        calls.append(step.rail)
        return {"ok": True, "response_id": "SYNTHETIC_SHOULD_NOT_EXIST"}

    result = router.execute_write(
        "workflow", "synthetic-rate-limited",
        evidence_root=evidence_root,
        rail_runners={"skill44_build_api": caf_runner, "browser": browser_runner},
        verifier=lambda rid: {"ok": True},
        rate_cooldown=lambda step: None,
    )
    assert result["action"] == "failed"
    assert result["rail"] == "skill44_build_api"
    assert "browser" not in calls
    assert calls == ["skill44_build_api", "skill44_build_api", "skill44_build_api"], calls


def test_kb_responder_widget_single_responder():
    """KB -> native responder -> widget: one response, real thread evidence."""
    scenario = harness.load_scenario("kb-responder-widget")
    kb = scenario["kb"]
    assert all(kb[key] is True for key in
               ("uploaded", "ingested", "trained", "attached_to_agent"))
    responder = scenario["responder"]
    assert responder["single_responder_owner"] == "native"
    assert all(item["responses_sent"] == 1 for item in responder["inbound"])
    widget = scenario["widget"]
    assert widget["embeds"] == 1
    assert widget["thread"]["reached_inbox"]
    assert widget["thread"]["responder"] == "native"
    assert scenario["expected"]["bubble_render_counts_as_conversation"] is False
    assert scenario["expected"]["duplicate_responses"] == 0
    # The widget create allowlist must reject a chat type that only appears in reads.
    assert widget["chat_type"] in ("live_chat", "sms_only")
    assert all(t not in ("live_chat",) for t in widget["unsupported_chat_types"])


def test_meeting_quiz_managed_browser_boundary():
    """Meeting/quiz: UI-bound builder work stays managed-browser; AV is NOT RUN."""
    scenario = harness.load_scenario("meeting-quiz-boundary")
    import capability_inventory as contracts
    from capability_inventory import OpClass, Transport

    page_build = contracts.select_route(OpClass.CREATE, resource="page", surface="page")
    assert any(cap.transport is Transport.MANAGED_BROWSER for cap in page_build), page_build

    meeting = scenario["meeting"]
    assert meeting["guest_session_isolated"] is True
    assert meeting["reused_room"] is True
    av = meeting["av"]
    assert set(av.values()) >= {"not_run"}
    assert "audio" not in {k for k, v in av.items() if v == "passed"}
    assert scenario["marketing_quiz"]["lesson_quiz_separate"] is True
    assert scenario["marketing_quiz"]["builder"] == "managed_browser"
    assert all(scenario["marketing_quiz"]["outcomes"].values())
    assert scenario["expected"]["av_claimed_passed"] is False


def test_cc_projects_projection_is_one_way():
    """CC -> Projects: one-way, no echo, no duplicate on replay, CC owns done."""
    scenario = harness.load_scenario("cc-projects-projection")
    projection = scenario["projection"]
    assert projection["direction"] == "one_way"
    assert projection["target"] == "ghl_projects"
    assert projection["target_to_cc_events"] == []
    assert projection["echo_loop"] is False
    assert projection["replay_creates_duplicate"] is False
    assert projection["promotes_unverified_build_to_done"] is False
    event_ids = [event["event_id"] for event in projection["events"]]
    assert len(event_ids) == len(set(event_ids))
    assert scenario["cc_task"]["completion_authority"] == "cc"
    assert scenario["expected"]["echo_events"] == 0
    assert scenario["expected"]["duplicates_on_replay"] == 0


def test_launch_fulfillment_board_old_new_producer_mix(tmp_path):
    """Launch/board: old+new bindings, receipt-backed cards, outage outbox."""
    scenario = harness.load_scenario("launch-fulfillment-board")
    assert scenario["binding_formats"]["old"]["accepted"] is True
    assert scenario["binding_formats"]["new"]["accepted"] is True
    assert scenario["fulfillment"]["delivery_state"] == "verified"
    board = scenario["board"]
    assert board["receipt_id"], "a board card must cite a receipt"
    assert board["create_success_is_done"] is False
    assert scenario["outage"]["board_available"] is False
    assert scenario["outage"]["ghl_mutation_repeated"] is False
    assert scenario["outage"]["execution_continued"] is True
    ambiguous = scenario["ambiguous_write"]
    assert ambiguous["outcome"] == "unknown_outcome"
    assert ambiguous["retried_on_other_rail"] is False
    assert ambiguous["reconciled_before_retry"] is True

    operation_receipts = harness.iter_receipts(scenario)
    for receipt in operation_receipts:
        if receipt["outcome"] == "unknown_outcome":
            assert receipt["readback"]["state"] != "matched"


def test_evidence_labels_never_upgrade_a_live_claim():
    """IG-RELEASE-02: offline, live and functional evidence stay separate."""
    labels = harness.classify_evidence("PASS", "NOT_RUN", "PENDING")
    assert labels["offline_tests"] == "OFFLINE_PASS"
    assert labels["live_canary"] == "NOT_RUN"
    assert labels["functional_verification"] == "PENDING"
    assert labels["claim_upgraded"] == "false"
    with pytest.raises(ValueError):
        harness.classify_evidence("PASS", "NOT_RUN", "PASS")
    with pytest.raises(ValueError):
        harness.classify_evidence("MAYBE", "NOT_RUN", "PENDING")

    checkpoint = harness.checkpoint_entry(
        implemented=["fixture"],
        tests=[{"command": "pytest ...", "result": "not_run", "reason": "live canary not authorized"}],
        acceptance_ids=["IG-RELEASE-02"],
    )
    assert checkpoint["tests"][0]["result"] == "not_run"
    with pytest.raises(ValueError):
        harness.checkpoint_entry(
            implemented=["fixture"],
            tests=[{"command": "pytest ...", "result": "not_run", "exit_code": 1}],
            acceptance_ids=["IG-RELEASE-02"],
        )


def test_checkpoint_state_is_pending_without_a_record(tmp_path):
    run_root = str(tmp_path / "run")
    os.makedirs(run_root, exist_ok=True)
    assert harness.checkpoint_state(run_root, "WF00-CP01") == "pending"
    os.makedirs(os.path.join(run_root, "contracts"), exist_ok=True)
    with open(os.path.join(run_root, "contracts", "WF00-CP01.json"), "w", encoding="utf-8") as fh:
        json.dump({"checkpoint_id": "WF00-CP01"}, fh)
    assert harness.checkpoint_state(run_root, "WF00-CP01") == "recorded"
