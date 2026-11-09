"""WF25 workflow log/statistics tests: windows, cursors, dedupe, honest metrics.

Every test is offline.  ``FakeTransport`` replays scripted bodies through the
real ``PublicGhlAdapter``; the synthetic operation rows stand in only until
WF00 freezes the two documented log rows, and the unfrozen default binding is
asserted to fail loudly instead of faking success.

Acceptance map (Document 1 Sections 17.5 and 33.2):
    B04        cursor forwarding, bounded windows, retention, schema growth
    B05        event counts vs cohort conversion; rehearsal vs live execution
    IG-LOG-01  cursor fields and filters persist across pages
    IG-LOG-02  retention/window and aggregate-group limits validated, no silent drop
    IG-LOG-03  empty logs, builder tests and live executions are different states
    IG-LOG-04  counts labelled as events/cohorts correctly
    IG-LOG-05  sensitive execution details redacted
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.normpath(os.path.join(_HERE, ".."))
for _path in (_HERE, _ENGINE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from click.testing import CliRunner  # noqa: E402

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public import workflow_monitoring as wm  # noqa: E402
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.workflow_monitoring_commands import build_group  # noqa: E402

FIXTURES = Path(_HERE) / "fixtures" / "wf25"
NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=timezone.utc)
WORKFLOW_ID = "wf_synthetic_wf25"

#: Synthetic stand-ins for the WF00 rows.  WF25 must not claim these are the
#: documented literals; the default binding stays refused until WF00 freezes
#: the real path, Version and query names.
LOG_ROW = row(
    wm.LOG_OPERATION_ID,
    method="GET",
    path_template="/workflows/{workflowId}/logs",
    version="v3",
    tenant_binding="query.locationId",
)
AGG_ROW = row(
    wm.AGGREGATE_OPERATION_ID,
    method="GET",
    path_template="/workflows/{workflowId}/logs/aggregate",
    version="v3",
    tenant_binding="query.locationId",
)
ROWS = registry(LOG_ROW, AGG_ROW)
BINDING = wm.MonitoringContractBinding(
    logs_operation_id=LOG_ROW.operation_id,
    aggregate_operation_id=AGG_ROW.operation_id,
    window_params=("startDate", "endDate"),
    cursor_param="nextCursor",
)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def json_resp(payload: dict) -> object:
    return resp(200, json.dumps(payload).encode("utf-8"))


def monitoring_for(
    responses,
    *,
    gate: str = "enabled",
    binding: wm.MonitoringContractBinding | None = BINDING,
    contract: wm.MonitoringContract | None = None,
    clock=lambda: NOW,
):
    transport = FakeTransport(responses)
    gate_object = enabled_gate([LOG_ROW, AGG_ROW]) if gate == "enabled" else None
    adapter = make_adapter(transport, ROWS, gate=gate_object)
    monitoring = wm.WorkflowMonitoring(
        public=adapter,
        tenant=fake_tenant(),
        binding=binding,
        contract=contract,
        clock=clock,
    )
    return monitoring, transport


class WindowPolicy(unittest.TestCase):
    def test_period_is_split_into_contiguous_non_overlapping_windows(self) -> None:
        start = NOW - timedelta(days=59)
        windows = wm.DEFAULT_CONTRACT.windows(start, NOW, now=NOW)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0].start, start)
        self.assertEqual(windows[-1].end, NOW)
        for earlier, later in zip(windows, windows[1:]):
            self.assertEqual(earlier.end, later.start)
        for window in windows:
            self.assertLessEqual(window.days, wm.MAX_QUERY_WINDOW_DAYS)

    def test_window_longer_than_retention_is_refused(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.DEFAULT_CONTRACT.windows(NOW - timedelta(days=61), NOW, now=NOW)
        self.assertEqual(caught.exception.rule, "window_before_retention")

    def test_window_in_the_future_is_refused(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.DEFAULT_CONTRACT.windows(NOW - timedelta(days=1), NOW + timedelta(hours=1), now=NOW)
        self.assertEqual(caught.exception.rule, "window_after_now")

    def test_window_order_is_validated(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.DEFAULT_CONTRACT.windows(NOW, NOW - timedelta(days=1), now=NOW)
        self.assertEqual(caught.exception.rule, "window_order_invalid")

    def test_rfc3339_is_required(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.parse_time("2026-11-08 12:00")
        self.assertEqual(caught.exception.rule, "time_format_invalid")


class PaginationAndDedupe(unittest.TestCase):
    def test_fixture_scan_forwards_cursor_and_dedupes_at_window_boundary(self) -> None:
        """B04 / IG-LOG-01: cursor literal, identical filters, stable-identity dedupe."""

        fixture = load_fixture("pages.json")
        windows = tuple(
            wm.QueryWindow(wm.parse_time(item["start"]), wm.parse_time(item["end"]))
            for item in fixture["windows"]
        )
        queue = list(fixture["pages"])
        observed_cursors: list[str | None] = []

        def fetch(window, cursor, filters):
            item = queue.pop(0)
            self.assertEqual(item["cursor_in"], cursor)
            self.assertEqual(windows.index(window), item["window"])
            observed_cursors.append(cursor)
            return item["body"]

        result = wm.scan(
            workflow_id=fixture["workflow_id"],
            windows=windows,
            fetch_page=fetch,
            filters=fixture["expected"]["filters_fingerprint_input"],
            max_pages=10,
            receipts=["gxo_res_synthetic_0001"],
        )
        expected = fixture["expected"]
        self.assertEqual(observed_cursors, [None, "opaque-cursor-1", None])
        self.assertEqual(result.pages_read, expected["pages_read"])
        self.assertEqual(result.duplicates_dropped, expected["duplicates_dropped"])
        self.assertEqual(dict(result.counts), expected["counts"])
        self.assertEqual(len(result.events), 6)
        self.assertFalse(result.empty)

    def test_frozen_result_example_matches_the_live_summary(self) -> None:
        """The published CP01 redacted result type still matches the code."""

        fixture = load_fixture("pages.json")
        windows = tuple(
            wm.QueryWindow(wm.parse_time(item["start"]), wm.parse_time(item["end"]))
            for item in fixture["windows"]
        )
        queue = list(fixture["pages"])
        result = wm.scan(
            workflow_id=fixture["workflow_id"],
            windows=windows,
            fetch_page=lambda window, cursor, filters: queue.pop(0)["body"],
            filters=fixture["expected"]["filters_fingerprint_input"],
            max_pages=10,
            receipts=["gxo_res_synthetic_0001"],
        )
        self.assertEqual(result.summary(), load_fixture("monitoring_result.example.json"))

    def test_real_adapter_forwards_cursor_unchanged_and_keeps_filters(self) -> None:
        """B04 / IG-LOG-01 through the real PublicGhlAdapter."""

        page_one = {"logs": [{"logId": "log-1", "status": "completed"}], "meta": {"nextCursor": "opaque-cursor-1"}}
        page_two = {"logs": [{"logId": "log-2", "status": "waiting"}], "meta": {"nextCursor": None}}
        monitoring, transport = monitoring_for([json_resp(page_one), json_resp(page_two)])
        result = monitoring.logs(
            workflow_id=WORKFLOW_ID,
            start="2026-11-07T00:00:00Z",
            end="2026-11-08T00:00:00Z",
            filters={"tag": "synthetic-filter"},
            max_pages=4,
        )
        self.assertEqual(transport.call_count, 2)
        first, second = transport.requests[0]["query"], transport.requests[1]["query"]
        self.assertNotIn("nextCursor", first)
        self.assertEqual(second["nextCursor"], "opaque-cursor-1")
        for key in ("startDate", "endDate", "tag", "locationId"):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(first["startDate"], "2026-11-07T00:00:00Z")
        self.assertEqual(first["locationId"], SYNTHETIC_TENANT)
        self.assertEqual(transport.requests[0]["url"], f"/workflows/{WORKFLOW_ID}/logs")
        self.assertEqual(len(result.events), 2)

    def test_unrecognised_non_empty_page_is_refused_not_read_as_empty(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.read_page({"unexpected": [{"value": 1}]})
        self.assertEqual(caught.exception.rule, "monitoring_page_shape_unknown")

    def test_empty_body_and_empty_collection_are_legitimate_empty_pages(self) -> None:
        self.assertEqual(wm.read_page({}).records, ())
        self.assertEqual(wm.read_page({"logs": []}).records, ())

    def test_cursor_that_does_not_advance_is_refused(self) -> None:
        page = {"logs": [], "meta": {"nextCursor": "same-cursor"}}
        monitoring, _ = monitoring_for([json_resp(page), json_resp(page)])
        with self.assertRaises(ContractViolation) as caught:
            monitoring.logs(
                workflow_id=WORKFLOW_ID,
                start="2026-11-07T00:00:00Z",
                end="2026-11-08T00:00:00Z",
            )
        self.assertEqual(caught.exception.rule, "cursor_not_advancing")

    def test_polling_bound_is_enforced(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.scan(workflow_id=WORKFLOW_ID, windows=(_window(),), fetch_page=lambda w, c, f: {}, max_pages=0)
        self.assertEqual(caught.exception.rule, "polling_bound_invalid")
        with self.assertRaises(ContractViolation) as caught:
            wm.scan(
                workflow_id=WORKFLOW_ID,
                windows=(_window(),),
                fetch_page=lambda w, c, f: {},
                max_pages=wm.MAX_PAGES_PER_SCAN + 1,
            )
        self.assertEqual(caught.exception.rule, "polling_bound_exceeded")

        pages = [json_resp({"logs": [], "meta": {"nextCursor": f"cursor-{index}"}}) for index in range(3)]
        monitoring, _ = monitoring_for(pages)
        with self.assertRaises(ContractViolation) as caught:
            monitoring.logs(
                workflow_id=WORKFLOW_ID,
                start="2026-11-07T00:00:00Z",
                end="2026-11-08T00:00:00Z",
                max_pages=2,
            )
        self.assertEqual(caught.exception.rule, "polling_bound_exceeded")


def _window() -> wm.QueryWindow:
    return wm.QueryWindow(NOW - timedelta(days=1), NOW)


class StatusAndRedaction(unittest.TestCase):
    def test_statuses_are_distinct_and_never_collapsed_into_error(self) -> None:
        cases = {
            "Completed": "completed",
            "pending": "waiting",
            "failed": "failed",
            "removed": "removed",
            "brand_new_status": "unclassified",
            None: "unclassified",
        }
        for value, expected in cases.items():
            self.assertEqual(wm.classify_status(value), expected, value)

    def test_redaction_drops_contact_and_message_details(self) -> None:
        """IG-LOG-05: no contact identifier or message body survives."""

        record = load_fixture("pages.json")["pages"][0]["body"]["logs"][0]
        redacted = wm.redact_event(record)
        rendered = json.dumps(redacted)
        self.assertNotIn("contact-synthetic", rendered)
        self.assertNotIn("synthetic message body", rendered)
        self.assertEqual(redacted["fields"]["logId"], "log-1")
        self.assertGreaterEqual(redacted["withheld_field_count"], 2)

    def test_summary_carries_no_unredacted_event_payload(self) -> None:
        fixture = load_fixture("pages.json")
        windows = tuple(
            wm.QueryWindow(wm.parse_time(item["start"]), wm.parse_time(item["end"]))
            for item in fixture["windows"]
        )
        queue = list(fixture["pages"])
        result = wm.scan(
            workflow_id=fixture["workflow_id"],
            windows=windows,
            fetch_page=lambda window, cursor, filters: queue.pop(0)["body"],
            max_pages=10,
        )
        rendered = json.dumps(result.summary())
        self.assertNotIn("contact-synthetic", rendered)
        self.assertNotIn("synthetic message body", rendered)


class HonestMetrics(unittest.TestCase):
    def test_aggregate_is_labelled_event_count_not_conversion(self) -> None:
        """B05 / IG-LOG-04."""

        summary = wm.read_aggregate(
            {"groups": [{"status": "completed", "count": 4}, {"status": "failed", "count": 1}]},
            group_limit=wm.GroupLimit(value=5, verified=True),
        ).summary()
        self.assertEqual(summary["metric_kind"], "event_count")
        self.assertEqual(summary["label"], "workflow_log_event_count")
        self.assertIsNone(summary["cohort_conversion"])
        self.assertFalse(summary["is_cohort_conversion"])
        self.assertEqual(summary["total_events"], 5)

    def test_same_window_ratio_is_not_cohort_conversion(self) -> None:
        ratio = wm.same_window_event_ratio(numerator_events=5, denominator_events=4)
        self.assertEqual(ratio["ratio_kind"], "same_window_event_ratio")
        self.assertFalse(ratio["is_cohort_conversion"])
        self.assertAlmostEqual(ratio["value"], 1.25)

        cohort = wm.cohort_completion_rate(
            cohort_contact_ids=["contact-a", "contact-b"],
            completed_contact_ids=["contact-a", "contact-b", "contact-c"],
        )
        self.assertEqual(cohort["ratio_kind"], "cohort_conversion")
        self.assertTrue(cohort["is_cohort_conversion"])
        self.assertEqual(cohort["value"], 1.0)

        with self.assertRaises(ContractViolation) as caught:
            wm.same_window_event_ratio(numerator_events=1, denominator_events=0)
        self.assertEqual(caught.exception.rule, "ratio_denominator_zero")
        with self.assertRaises(ContractViolation) as caught:
            wm.cohort_completion_rate(cohort_contact_ids=[], completed_contact_ids=["contact-a"])
        self.assertEqual(caught.exception.rule, "cohort_conversion_unavailable")

    def test_aggregate_group_limit_is_validated_without_silent_truncation(self) -> None:
        """IG-LOG-02: an unfrozen limit is refused, not guessed."""

        contract = wm.MonitoringContract()
        with self.assertRaises(ContractViolation) as caught:
            contract.group_limit(limit=3)
        self.assertEqual(caught.exception.rule, "aggregate_group_limit_unverified")

        declared = contract.group_limit(limit=3, declared_limit=5)
        self.assertFalse(declared.verified)
        with self.assertRaises(ContractViolation) as caught:
            contract.group_limit(limit=6, declared_limit=5)
        self.assertEqual(caught.exception.rule, "aggregate_group_limit_exceeded")

        documented = wm.MonitoringContract(aggregate_group_limit=2)
        self.assertTrue(documented.group_limit(limit=2).verified)

        with self.assertRaises(ContractViolation) as caught:
            wm.read_aggregate(
                {"groups": [{"count": 1}, {"count": 1}, {"count": 1}]},
                group_limit=wm.GroupLimit(value=2, verified=True),
            )
        self.assertEqual(caught.exception.rule, "aggregate_groups_exceed_limit")

        with self.assertRaises(ContractViolation) as caught:
            wm.read_aggregate(
                {"groups": [{"count": 1}], "truncated": True},
                group_limit=wm.GroupLimit(value=2, verified=True),
            )
        self.assertEqual(caught.exception.rule, "aggregate_result_truncated")

    def test_aggregate_reads_each_window_and_labels_the_result(self) -> None:
        body = {"groups": [{"status": "completed", "count": 2}]}
        monitoring, transport = monitoring_for([json_resp(body), json_resp(body)])
        result = monitoring.aggregate(
            workflow_id=WORKFLOW_ID,
            start=(NOW - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            group_by=("status",),
            limit=5,
            group_query={"groupBy": "status"},
            declared_limit=5,
        )
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(transport.requests[0]["query"]["groupBy"], "status")
        self.assertNotEqual(
            transport.requests[0]["query"]["startDate"],
            transport.requests[1]["query"]["startDate"],
        )
        summary = result.summary()
        self.assertEqual(summary["metric_kind"], "event_count")
        self.assertFalse(summary["is_cohort_conversion"])
        self.assertIsNone(summary["cohort_conversion"])
        self.assertEqual(summary["total_events"], 4)
        self.assertEqual(len(summary["per_window"]), 2)


class EvidenceStates(unittest.TestCase):
    def test_builder_rehearsal_and_live_execution_remain_separate(self) -> None:
        """B05 / IG-LOG-03."""

        empty = wm.scan(workflow_id=WORKFLOW_ID, windows=(_window(),), fetch_page=lambda window, cursor, filters: {"logs": []})
        self.assertTrue(empty.empty)

        with self.assertRaises(ContractViolation) as caught:
            wm.RuntimeStatus(controlled_live_execution_verified=True).validate(
                scan=empty, live_reference={"test_contact": "contact-synthetic"}
            )
        self.assertEqual(caught.exception.rule, "empty_logs_not_execution_proof")

        with self.assertRaises(ContractViolation) as caught:
            wm.RuntimeStatus(controlled_live_execution_verified=True).validate(scan=None)
        self.assertEqual(caught.exception.rule, "live_execution_reference_missing")

        rehearsal = wm.RuntimeStatus(builder_rehearsal_verified=True)
        rehearsal.validate(scan=empty, rehearsal_reference={"run": "builder-run-1"})
        evidence = rehearsal.as_evidence()
        self.assertFalse(evidence["counts_as_production"])
        self.assertFalse(evidence["states"]["controlled_live_execution_verified"])
        self.assertTrue(evidence["states"]["builder_rehearsal_verified"])
        self.assertEqual(set(evidence["states"]), set(wm.EVIDENCE_STATES))

        with self.assertRaises(ContractViolation) as caught:
            rehearsal.validate(scan=empty)
        self.assertEqual(caught.exception.rule, "rehearsal_reference_missing")

    def test_ongoing_monitoring_requires_a_real_job_identity(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            wm.RuntimeStatus(ongoing_monitoring_configured=True).validate()
        self.assertEqual(caught.exception.rule, "monitoring_service_not_configured")
        wm.RuntimeStatus(ongoing_monitoring_configured=True).validate(monitoring_job_id="job-synthetic-1")


class UnfrozenUpstream(unittest.TestCase):
    def test_missing_operation_rows_fail_loudly(self) -> None:
        """WF00 has not frozen the log rows yet: the default binding refuses."""

        adapter = make_adapter(FakeTransport(), ROWS, gate=enabled_gate([LOG_ROW, AGG_ROW]))
        with self.assertRaises(ContractViolation) as caught:
            wm.WorkflowMonitoring(public=adapter, tenant=fake_tenant(), operations={})
        self.assertEqual(caught.exception.rule, "monitoring_operation_rows_missing")
        self.assertEqual(caught.exception.detail["owner"], "WF00")

    def test_unfrozen_window_params_refuse_before_transport(self) -> None:
        binding = wm.MonitoringContractBinding(
            logs_operation_id=LOG_ROW.operation_id,
            aggregate_operation_id=AGG_ROW.operation_id,
        )
        monitoring, transport = monitoring_for([json_resp({"logs": []})], binding=binding)
        with self.assertRaises(ContractViolation) as caught:
            monitoring.logs(workflow_id=WORKFLOW_ID, start="2026-11-07T00:00:00Z", end="2026-11-08T00:00:00Z")
        self.assertEqual(caught.exception.rule, "monitoring_window_params_unverified")
        self.assertEqual(transport.call_count, 0)

    def test_aggregate_requires_a_documented_grouping_query(self) -> None:
        monitoring, transport = monitoring_for([])
        with self.assertRaises(ContractViolation) as caught:
            monitoring.aggregate(
                workflow_id=WORKFLOW_ID,
                start="2026-11-07T00:00:00Z",
                end="2026-11-08T00:00:00Z",
                group_by=("status",),
                limit=5,
                group_query={},
                declared_limit=5,
            )
        self.assertEqual(caught.exception.rule, "aggregate_group_query_unverified")
        self.assertEqual(transport.call_count, 0)

    def test_denied_capability_is_not_an_empty_log_page(self) -> None:
        monitoring, transport = monitoring_for([], gate="none")
        with self.assertRaises(ContractViolation) as caught:
            monitoring.logs(workflow_id=WORKFLOW_ID, start="2026-11-07T00:00:00Z", end="2026-11-08T00:00:00Z")
        self.assertEqual(caught.exception.rule, "monitoring_call_not_ok")
        self.assertEqual(caught.exception.detail["rule"], "capability_disabled")
        self.assertEqual(transport.call_count, 0)

    def test_module_has_no_background_service(self) -> None:
        """No always-on polling service ships in this module."""

        source = (
            Path(_ENGINE)
            / "cli_anything"
            / "gohighlevel"
            / "public"
            / "workflow_monitoring.py"
        ).read_text(encoding="utf-8")
        for marker in ("import threading", "import asyncio", "import sched", "time.sleep", "schedule."):
            self.assertNotIn(marker, source, marker)


def _cli_output(result) -> str:
    return (result.output or "") + (getattr(result, "stderr", "") or "")


class CommandModule(unittest.TestCase):
    def _logged_page(self) -> dict:
        return {
            "logs": [
                {
                    "logId": "log-1",
                    "status": "completed",
                    "contactId": "contact-synthetic",
                    "message": "synthetic message body",
                }
            ],
            "meta": {},
        }

    def test_logs_command_prints_redacted_json(self) -> None:
        monitoring, transport = monitoring_for([json_resp(self._logged_page())])
        runner = CliRunner()
        result = runner.invoke(
            build_group(lambda ctx: monitoring),
            ["logs", "--workflow-id", WORKFLOW_ID, "--from", "2026-11-07T00:00:00Z", "--to", "2026-11-08T00:00:00Z"],
            obj={"json": True},
        )
        self.assertEqual(result.exit_code, 0, _cli_output(result))
        payload = json.loads(result.output)
        self.assertEqual(payload["metric_kind"], "event_count")
        self.assertEqual(payload["counts"]["total_events"], 1)
        self.assertNotIn("contact-synthetic", result.output)
        self.assertNotIn("synthetic message body", result.output)
        self.assertEqual(transport.call_count, 1)

    def test_logs_command_fails_non_zero_on_a_refusal(self) -> None:
        monitoring, transport = monitoring_for([])
        runner = CliRunner()
        result = runner.invoke(
            build_group(lambda ctx: monitoring),
            ["logs", "--workflow-id", WORKFLOW_ID, "--from", "2026-08-01T00:00:00Z", "--to", "2026-11-08T00:00:00Z"],
            obj={"json": True},
        )
        self.assertEqual(result.exit_code, 1, _cli_output(result))
        self.assertIn("window_before_retention", _cli_output(result))
        self.assertEqual(transport.call_count, 0)

    def test_stats_command_prints_event_counts(self) -> None:
        body = {"groups": [{"status": "completed", "count": 3}]}
        monitoring, _ = monitoring_for([json_resp(body)])
        runner = CliRunner()
        result = runner.invoke(
            build_group(lambda ctx: monitoring),
            [
                "stats",
                "--workflow-id",
                WORKFLOW_ID,
                "--from",
                "2026-11-07T00:00:00Z",
                "--to",
                "2026-11-08T00:00:00Z",
                "--group-by",
                "status",
                "--group-query",
                "groupBy=status",
                "--limit",
                "5",
                "--declared-limit",
                "5",
            ],
            obj={"json": True},
        )
        self.assertEqual(result.exit_code, 0, _cli_output(result))
        payload = json.loads(result.output)
        self.assertEqual(payload["metric_kind"], "event_count")
        self.assertEqual(payload["total_events"], 3)
        self.assertFalse(payload["is_cohort_conversion"])

    def test_windows_command_is_offline_and_splits(self) -> None:
        monitoring, transport = monitoring_for([])
        runner = CliRunner()
        result = runner.invoke(
            build_group(lambda ctx: monitoring),
            ["windows", "--from", "2026-09-10T12:00:00Z", "--to", "2026-11-08T12:00:00Z"],
            obj={"json": True},
        )
        self.assertEqual(result.exit_code, 0, _cli_output(result))
        payload = json.loads(result.output)
        self.assertEqual(len(payload["windows"]), 2)
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":
    unittest.main()
