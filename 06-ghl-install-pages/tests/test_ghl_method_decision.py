"""MOCK-only unit tests — ghl_method_decision (S06-02 unified per-run record).

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO network, NO
browser. They drive the three real source systems with fixture inputs —
``ghl_method.decide_and_record`` (pure classifier + file write),
``ghl_object_router.execute_write`` (fake rail runners), and
``ghl_fallback_ladder.run_ladder`` (fake rung callables) — and assert that
``ghl_method_decision`` aggregates their outcomes into ONE record at
``<run_dir>/routing/method-decision.json`` (the exact name SKILL.md's
Phase-5 table promises), in the spec-05-section-4 shape.

Coverage:
  * decide_and_record now ALSO writes the unified record, with a page entry
    carrying the spec operation class, the classifier's own lane word,
    rejected alternatives with reasons, scope, and evidence refs.
  * A vercel page entry rejects 'direct' (and vice versa for a direct page).
  * A widget block on a page becomes its OWN entry with chosen lane 'widget'
    and the widget's location id in scope.
  * Multiple pages aggregate; a refresh never duplicates entries and never
    drops router/ladder entries.
  * REGRESSION: the per-page record files are still written EXACTLY as
    before this unit (same keys, same values) — the unified record is
    additive only.
  * An object-router outcome (real execute_write, fake runners) becomes an
    entry with the rail as chosen lane and the remaining declared rails as
    rejected alternatives; a failed outcome records no fabricated success.
  * A ladder outcome (real run_ladder, fake rungs) becomes an entry whose
    rejected alternatives carry the failed rung's taxonomy code + reason.
  * A run with page decisions but NO ladder data still produces a valid
    record (no ladder entry is invented).
  * An unmapped object type raises instead of falling through silently.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_method_decision.py -v
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_method as m
import ghl_method_decision as md
import ghl_object_router as router
import ghl_fallback_ladder as ladder


SIMPLE_HTML = "<section><h1>Hello</h1><p>Copy text.</p></section>"
FAKE_LOC = "FIXTURELOC0001"


def _spec(**kw) -> dict:
    base = {"html": SIMPLE_HTML}
    base.update(kw)
    return base


def _read_unified(run_dir: str) -> dict:
    path = os.path.join(run_dir, "routing", "method-decision.json")
    assert os.path.isfile(path), f"unified record missing at {path}"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _entry(record: dict, entry_id: str) -> dict:
    for e in record["operations"]:
        if e["id"] == entry_id:
            return e
    raise AssertionError(f"entry {entry_id!r} not in {[e['id'] for e in record['operations']]}")


# ── Page decisions → unified record ───────────────────────────────────────────

class TestUnifiedRecordFromPages:
    def test_decide_and_record_writes_unified_record(self, tmp_path):
        run_dir = str(tmp_path)
        m.decide_and_record(_spec(), "home", run_dir)
        record = _read_unified(run_dir)
        assert record["schema"] == "skill6-method-decision/1"
        assert record["runId"] == tmp_path.name
        assert "generatedAt" in record
        assert record["scope"]["publishGate"] == "unknown"

        entry = _entry(record, "page:home")
        assert entry["source"] == "ghl_method"
        assert entry["operationClass"] == "visual_builder_write"
        assert entry["chosenLane"] == "direct"
        assert entry["outcome"] == "decided"
        assert entry["evidenceRefs"] == ["routing/method-decision-home.json"]
        rejected = {r["lane"]: r["reason"] for r in entry["rejectedAlternatives"]}
        assert "vercel_embed" in rejected
        assert "classifier" in rejected["vercel_embed"]
        assert "classifier-score:0" in entry["capabilitiesObserved"]

    def test_vercel_page_entry_rejects_direct(self, tmp_path):
        run_dir = str(tmp_path)
        m.decide_and_record(_spec(complexity="advanced"), "app", run_dir)
        entry = _entry(_read_unified(run_dir), "page:app")
        assert entry["chosenLane"] == "vercel_embed"
        rejected = {r["lane"] for r in entry["rejectedAlternatives"]}
        assert rejected == {"direct"}

    def test_widget_block_gets_own_widget_entry(self, tmp_path):
        run_dir = str(tmp_path)
        m.decide_and_record(
            _spec(form_blocks=[{"key": "contact_form", "location_id": FAKE_LOC}]),
            "contact", run_dir)
        record = _read_unified(run_dir)
        page_entry = _entry(record, "page:contact")
        assert page_entry["chosenLane"] == "direct"

        widget_entry = _entry(record, "page:contact#widget:contact_form")
        assert widget_entry["chosenLane"] == "widget"
        assert widget_entry["operationClass"] == "visual_builder_write"
        assert widget_entry["scope"]["locationRef"] == FAKE_LOC
        assert widget_entry["detail"]["widgetKind"] == "form"
        assert widget_entry["detail"]["blockKey"] == "contact_form"
        rejected = {r["lane"]: r["reason"] for r in widget_entry["rejectedAlternatives"]}
        assert "static_html" in rejected
        assert "forbidden" in rejected["static_html"]

    def test_multiple_pages_aggregate_without_duplicates(self, tmp_path):
        run_dir = str(tmp_path)
        m.decide_and_record(_spec(), "home", run_dir)
        m.decide_and_record(_spec(complexity="advanced"), "app", run_dir)
        # Re-deciding a page must replace its entry, never duplicate it.
        m.decide_and_record(_spec(), "home", run_dir)
        record = _read_unified(run_dir)
        ids = [e["id"] for e in record["operations"]]
        assert sorted(ids) == ["page:app", "page:home"]

    def test_record_with_no_ladder_data_is_valid_and_invents_none(self, tmp_path):
        """A page-only run has no ladder outcomes; the unified record must
        still be well-formed and must NOT fabricate a ladder entry."""
        run_dir = str(tmp_path)
        m.decide_and_record(_spec(), "home", run_dir)
        record = _read_unified(run_dir)
        sources = {e["source"] for e in record["operations"]}
        assert sources == {"ghl_method"}
        for e in record["operations"]:
            assert "ladder" not in e["id"]
            assert e["rejectedAlternatives"], "every entry carries rejected alternatives"

    def test_per_page_records_still_written_exactly_as_before(self, tmp_path):
        """REGRESSION (S06-02 is additive): decide_and_record's per-page file
        keeps its exact pre-unification shape and values."""
        run_dir = str(tmp_path)
        decision = m.decide_and_record(_spec(), "home", run_dir)
        path = os.path.join(run_dir, "routing", "method-decision-home.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert set(data.keys()) == {
            "page_name", "method", "score", "threshold", "hard_forced",
            "signals", "widgets", "reason", "decided_at",
        }
        assert data["page_name"] == "home"
        assert data["method"] == "direct"
        assert data["score"] == 0
        assert data["threshold"] == m.ADVANCED_THRESHOLD
        assert data["hard_forced"] is False
        assert data["signals"] == []
        assert data["widgets"] == []
        assert data["reason"] == decision.reason
        assert data["decided_at"] == decision.decided_at


# ── Object-router outcomes → unified record ───────────────────────────────────

class TestRouterAggregation:
    def test_router_created_entry(self, tmp_path):
        run_dir = str(tmp_path)
        res = router.execute_write(
            "tag", "zhc_fixture", evidence_root=run_dir,
            idempotency_probe=lambda: None,
            rail_runners={
                router.Rail.SKILL44_CAF: lambda s: router.RunResult(
                    ok=True, response_id="tagfix1"),
            },
            verifier=lambda rid: {"ok": True, "proof": "GET matched"},
        )
        assert res["action"] == "created"
        record = md.record_router_result(
            run_dir, res, run_id="fixture-run",
            location_ref="env:GOHIGHLEVEL_LOCATION_ID",
            publish_gate="draft_only")
        assert record["runId"] == "fixture-run"
        assert record["scope"]["locationRef"] == "env:GOHIGHLEVEL_LOCATION_ID"
        assert record["scope"]["publishGate"] == "draft_only"

        entry = _entry(record, "object:tag:zhc_fixture")
        assert entry["source"] == "ghl_object_router"
        assert entry["operationClass"] == "crm_product_write"
        assert entry["chosenLane"] == "skill44_caf"
        assert entry["outcome"] == "created"
        assert entry["scope"]["publishGate"] == "draft_only"
        assert entry["evidenceRefs"] == ["ecosystem/tag-zhc_fixture.json"]
        assert "tier:0" in entry["capabilitiesObserved"]
        assert "token-context:location_pit" in entry["capabilitiesObserved"]
        rejected = {r["lane"] for r in entry["rejectedAlternatives"]}
        assert rejected == {"rest_services"}

    def test_router_failed_entry_records_no_success(self, tmp_path):
        """A 429-exhausted write (F8: never tier-hops) must land as a failed
        entry on the attempted rail, never dressed up as created."""
        run_dir = str(tmp_path)
        res = router.execute_write(
            "tag", "zhc_429", evidence_root=run_dir,
            idempotency_probe=lambda: None,
            rail_runners={
                router.Rail.SKILL44_CAF: lambda s: router.RunResult(
                    ok=False, status=429, detail="rate limited"),
                router.Rail.REST_SERVICES: lambda s: router.RunResult(
                    ok=True, response_id="must-not-run"),
            },
            verifier=lambda rid: {"ok": True},
            rate_cooldown=lambda s: None)
        assert res["action"] == "failed"
        md.record_router_result(run_dir, res)
        entry = _entry(_read_unified(run_dir), "object:tag:zhc_429")
        assert entry["outcome"] == "failed"
        assert entry["chosenLane"] == "skill44_caf"
        assert entry["detail"]["hasError"] is True

    def test_router_media_maps_to_media_upload(self, tmp_path):
        run_dir = str(tmp_path)
        res = router.execute_write(
            "media", "logo.png", evidence_root=run_dir,
            idempotency_probe=lambda: None,
            rail_runners={
                router.Rail.REST_SERVICES: lambda s: router.RunResult(
                    ok=True, response_id="media1"),
            },
            verifier=lambda rid: {"ok": True})
        md.record_router_result(run_dir, res)
        entry = _entry(_read_unified(run_dir), "object:media:logo.png")
        assert entry["operationClass"] == "media_upload"

    def test_unmapped_object_type_raises(self):
        with pytest.raises(md.MethodDecisionRecordError):
            md.entry_from_router_result(
                {"action": "created", "rail": "rest_services",
                 "receipt": {"object_type": "nonsense_object", "slug": "x"}})


# ── Fallback-ladder outcomes → unified record ────────────────────────────────

class TestLadderAggregation:
    def _run_form_ladder(self, run_dir: str) -> str:
        receipt_path = os.path.join(run_dir, "receipts", "ladder-form.json")
        result = ladder.run_ladder(
            "form",
            {
                "mcp": lambda: {"ok": False, "code": "SELECTOR-MISS",
                                "detail": "fixture: mcp rung missed"},
                "browser": lambda: {"ok": True, "detail": "fixture: built"},
            },
            env={"GHL_FALLBACK_LADDER": "1"},
            receipt_path=receipt_path)
        assert result.ok and result.succeeded_rung == "browser"
        return receipt_path

    def test_ladder_entry_with_rejected_alternative(self, tmp_path):
        run_dir = str(tmp_path)
        receipt_path = self._run_form_ladder(run_dir)
        with open(receipt_path, encoding="utf-8") as fh:
            ladder_dict = json.load(fh)  # the LadderResult.to_dict() shape
        record = md.record_ladder_result(
            run_dir, ladder_dict, receipt_path=receipt_path)
        entry = _entry(record, "ladder:form")
        assert entry["source"] == "ghl_fallback_ladder"
        assert entry["operationClass"] == "visual_builder_write"
        assert entry["chosenLane"] == "browser"
        assert entry["outcome"] == "SUCCESS"
        assert entry["evidenceRefs"] == ["receipts/ladder-form.json"]
        rejected = {r["lane"]: r["reason"] for r in entry["rejectedAlternatives"]}
        assert set(rejected) == {"mcp"}
        assert rejected["mcp"].startswith("SELECTOR-MISS")

    def test_ladder_entry_accepts_result_object(self, tmp_path):
        run_dir = str(tmp_path)
        result = ladder.run_ladder(
            "workflow",
            {
                "mcp": lambda: {"ok": True, "detail": "fixture: built"},
                "browser": lambda: {"ok": True, "detail": "unused"},
            },
            env={"GHL_FALLBACK_LADDER": "1"})
        entry = md.entry_from_ladder_result(result)
        assert entry["operationClass"] == "workflow_write"
        assert entry["chosenLane"] == "mcp"
        rejected = {r["lane"]: r["reason"] for r in entry["rejectedAlternatives"]}
        assert set(rejected) == {"browser"}
        assert "first successful rung" in rejected["browser"]

    def test_all_sources_coexist_and_refresh_preserves_them(self, tmp_path):
        """The full aggregation: pages + router + ladder in ONE record, and
        a later page decision (which refreshes from disk) must not drop the
        router/ladder entries."""
        run_dir = str(tmp_path)
        m.decide_and_record(_spec(), "home", run_dir)
        res = router.execute_write(
            "media", "hero.png", evidence_root=run_dir,
            idempotency_probe=lambda: None,
            rail_runners={
                router.Rail.REST_SERVICES: lambda s: router.RunResult(
                    ok=True, response_id="media9"),
            },
            verifier=lambda rid: {"ok": True})
        md.record_router_result(run_dir, res)
        receipt_path = self._run_form_ladder(run_dir)
        with open(receipt_path, encoding="utf-8") as fh:
            ladder_dict = json.load(fh)
        md.record_ladder_result(run_dir, ladder_dict, receipt_path=receipt_path)

        # A second page decision triggers the ghl_method refresh path.
        m.decide_and_record(_spec(), "about", run_dir)
        record = _read_unified(run_dir)
        ids = {e["id"] for e in record["operations"]}
        assert ids == {"page:home", "page:about",
                       "object:media:hero.png", "ladder:form"}
        classes = {e["id"]: e["operationClass"] for e in record["operations"]}
        assert classes["object:media:hero.png"] == "media_upload"
        assert classes["ladder:form"] == "visual_builder_write"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
