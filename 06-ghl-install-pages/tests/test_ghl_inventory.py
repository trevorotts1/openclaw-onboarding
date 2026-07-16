"""Offline tests for U31 (B-U17) — GHL page inventory + staged lifecycle
(flag -> operator card -> fail-closed execute) + evidence-root retention.

MOCK-ONLY: no network, no browser, no live GoHighLevel of any kind. Every
funnel/page/media "read" here is a plain Python fake callable injected into
`ghl_inventory`'s dependency-injection seams — the same discipline as
`ghl_selector_canary.py`'s `finder`/`page_fetcher`. These tests both wrap the
module's own `--selftest` AND add direct behavioural assertions per the
BINARY acceptance criteria (a)-(e) in the master spec (B-U17):

  (a) zero write calls during enumeration            -> proven by construction
      (`enumerate_zhc_inventory` has no write-capable code path at all) +
      TestEnumerateZeroWriteCalls below (a fake funnel/page lister that
      would raise if ever called with anything resembling a write).
  (b) exactly ONE operator card per candidate set, idempotent            -> TestCardDedupe
  (c) an approved delete leaves a restorable export + an absent receipt  -> TestExecuteApprovedDeletes
  (d) evidence-root pruning skips roots referenced by open cards         -> TestPruneEvidenceRoots
  (e) nothing deletes without an approved card (fail-closed guard)       -> TestFailClosedGuard

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_inventory.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_inventory as inv  # noqa: E402
import ghl_method  # noqa: E402


# ---------------------------------------------------------------------------
# Module selftest (belt-and-suspenders)
# ---------------------------------------------------------------------------
def test_module_selftest_passes():
    assert inv._selftest() == 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _zhc_funnels(loc):
    return [
        {"id": "f1", "name": "ZHC Founders Circle"},
        {"id": "f2", "name": "Client's Own Funnel"},  # NOT ZHC-prefixed
    ]


def _zhc_pages(funnel_id, loc):
    if funnel_id == "f1":
        return [
            {"id": "p-old", "name": "ZHC Old Draft", "marker": "m-old",
             "status": "draft", "createdAt": "2020-01-01T00:00:00Z"},
            {"id": "p-new", "name": "ZHC Recent", "marker": "m-new",
             "status": "published", "createdAt": "2026-07-01T00:00:00Z"},
        ]
    return [{"id": "leaked", "name": "should never appear"}]


@pytest.fixture
def basic_report():
    return inv.enumerate_zhc_inventory(
        "loc-test", funnel_lister=_zhc_funnels, page_lister=_zhc_pages,
        now=lambda: "2026-07-15T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# enumerate_zhc_inventory
# ---------------------------------------------------------------------------
class TestEnumerateZhcInventory:
    def test_filters_to_zhc_prefixed_funnels_only(self, basic_report):
        ids = {p.page for p in basic_report.pages}
        assert ids == {"p-old", "p-new"}
        assert "leaked" not in ids

    def test_skips_records_with_no_id_rather_than_fabricating_one(self):
        report = inv.enumerate_zhc_inventory(
            "loc-test",
            funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [{"name": "no id field"}, {"id": "p1", "name": "ZHC ok"}],
        )
        assert [p.page for p in report.pages] == ["p1"]

    def test_page_record_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            inv.PageRecord(funnel="f1", page="p1", marker="m", status="deleted",
                            created="", last_verified="")

    def test_write_and_load_inventory_round_trip(self, basic_report, tmp_path):
        path = inv.write_inventory(str(tmp_path), basic_report)
        assert os.path.isfile(path)
        loaded = inv.load_inventory(path)
        assert loaded is not None
        assert len(loaded.pages) == len(basic_report.pages)
        assert loaded.location_id == "loc-test"

    def test_load_inventory_missing_file_returns_none(self, tmp_path):
        assert inv.load_inventory(str(tmp_path / "nope.json")) is None


class TestEnumerateZeroWriteCalls:
    """Acceptance (a) — "ZERO write calls" is true BY CONSTRUCTION
    (enumerate_zhc_inventory has no write-capable code path at all — the
    live network I/O boundary is entirely the two injected read callables).
    This test proves the injected callables are asked to READ ONLY, never
    handed a write-shaped payload, by asserting on the exact call signature
    the function issues."""

    def test_only_read_shaped_calls_are_made(self):
        calls = []

        def funnel_lister(location_id):
            calls.append(("funnel_lister", location_id))
            return [{"id": "f1", "name": "ZHC X"}]

        def page_lister(funnel_id, location_id):
            calls.append(("page_lister", funnel_id, location_id))
            return [{"id": "p1", "name": "ZHC Y", "status": "draft"}]

        inv.enumerate_zhc_inventory("loc9", funnel_lister=funnel_lister, page_lister=page_lister)

        assert calls == [("funnel_lister", "loc9"), ("page_lister", "f1", "loc9")]
        # Neither callable was ever asked to create/update/delete anything —
        # both signatures accept ids/location only, no body/payload argument
        # exists anywhere in enumerate_zhc_inventory's call sites.


# ---------------------------------------------------------------------------
# flag_lifecycle_candidates — stale / superseded
# ---------------------------------------------------------------------------
class TestFlagStale:
    def test_flags_only_old_unpublished_drafts(self, basic_report):
        flags = inv.flag_lifecycle_candidates(basic_report, now="2026-07-15T00:00:00Z")
        assert [c["id"] for c in flags.stale] == ["p-old"]

    def test_published_pages_never_flagged_regardless_of_age(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [{"id": "p1", "name": "ZHC live", "status": "published",
                                          "createdAt": "2010-01-01T00:00:00Z"}],
        )
        flags = inv.flag_lifecycle_candidates(report, now="2026-07-15T00:00:00Z")
        assert flags.stale == []

    def test_draft_within_threshold_not_flagged(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [{"id": "p1", "name": "ZHC fresh", "status": "draft",
                                          "createdAt": "2026-07-10T00:00:00Z"}],
        )
        flags = inv.flag_lifecycle_candidates(report, now="2026-07-15T00:00:00Z", stale_draft_days=30)
        assert flags.stale == []

    def test_custom_stale_threshold_respected(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [{"id": "p1", "name": "ZHC five days", "status": "draft",
                                          "createdAt": "2026-07-10T00:00:00Z"}],
        )
        flags = inv.flag_lifecycle_candidates(report, now="2026-07-15T00:00:00Z", stale_draft_days=3)
        assert [c["id"] for c in flags.stale] == ["p1"]

    def test_unparsable_created_never_flagged(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [{"id": "p1", "name": "ZHC bad", "status": "draft",
                                          "createdAt": "garbage"}],
        )
        flags = inv.flag_lifecycle_candidates(report, now="2026-07-15T00:00:00Z")
        assert flags.stale == []

    def test_repeat_runs_are_idempotent_pure_function(self, basic_report):
        f1 = inv.flag_lifecycle_candidates(basic_report, now="2026-07-15T00:00:00Z")
        f2 = inv.flag_lifecycle_candidates(basic_report, now="2026-07-15T00:00:00Z")
        assert f1.to_dict() == f2.to_dict()


class TestFlagSuperseded:
    def test_older_same_family_page_flagged_superseded(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "old", "name": "ZHC Landing", "marker": "m-old", "status": "published",
                 "createdAt": "2026-01-01T00:00:00Z"},
                {"id": "new", "name": "ZHC Landing", "marker": "m-new", "status": "published",
                 "createdAt": "2026-06-01T00:00:00Z"},
            ],
        )
        flags = inv.flag_lifecycle_candidates(report)
        assert [c["id"] for c in flags.superseded] == ["old"]
        assert flags.superseded[0]["superseded_by"] == "new"

    def test_single_page_family_never_superseded(self, basic_report):
        # p-old and p-new have DIFFERENT names -> different families -> no supersession.
        flags = inv.flag_lifecycle_candidates(basic_report)
        assert flags.superseded == []

    def test_custom_slug_of_page_grouping(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "a", "name": "Alpha", "marker": "m1", "status": "published",
                 "createdAt": "2026-01-01T00:00:00Z"},
                {"id": "b", "name": "Beta", "marker": "m2", "status": "published",
                 "createdAt": "2026-06-01T00:00:00Z"},
            ],
        )
        # force both pages into one family via a custom slug_of_page override
        flags = inv.flag_lifecycle_candidates(report, slug_of_page=lambda p: "same-family")
        assert [c["id"] for c in flags.superseded] == ["a"]


# ---------------------------------------------------------------------------
# detect_duplicate_markers — reuses ghl_method.resolve_install_target
# ---------------------------------------------------------------------------
class TestDetectDuplicateMarkers:
    def test_two_pages_sharing_a_marker_are_ambiguous(self):
        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "d1", "name": "ZHC A", "marker": "dup", "status": "draft"},
                {"id": "d2", "name": "ZHC B", "marker": "dup", "status": "draft"},
            ],
        )
        dups = inv.detect_duplicate_markers(report)
        assert len(dups) == 1
        assert sorted(dups[0]["ambiguous_ids"]) == ["d1", "d2"]

    def test_unique_markers_never_flagged_duplicate(self, basic_report):
        assert inv.detect_duplicate_markers(basic_report) == []

    def test_reuses_the_real_install_target_resolver_never_a_re_derived_rule(self):
        """The duplicate condition detected here must be the EXACT SAME
        condition that raises ghl_method.InstallTargetError at build time —
        never a separately re-implemented ambiguity rule that could drift."""
        pages = [{"id": "d1", "marker": "dup"}, {"id": "d2", "marker": "dup"}]
        with pytest.raises(ghl_method.InstallTargetError):
            ghl_method.resolve_install_target(pages, "dup")

        report = inv.enumerate_zhc_inventory(
            "loc", funnel_lister=lambda loc: [{"id": "f1", "name": "ZHC X"}],
            page_lister=lambda f, loc: [
                {"id": "d1", "name": "ZHC A", "marker": "dup", "status": "draft"},
                {"id": "d2", "name": "ZHC B", "marker": "dup", "status": "draft"},
            ],
        )
        assert len(inv.detect_duplicate_markers(report)) == 1


# ---------------------------------------------------------------------------
# post_lifecycle_card — acceptance (b): exactly ONE card, idempotent
# ---------------------------------------------------------------------------
class TestCardDedupe:
    def test_exactly_one_card_across_repeat_runs(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        candidates = [{"id": "p1", "funnel": "f1", "marker": "m", "reason": "stale"}]
        calls = []

        r1 = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
            board_notifier=lambda p: calls.append(p),
        )
        r2 = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
            board_notifier=lambda p: calls.append(p),
        )
        r3 = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
            board_notifier=lambda p: calls.append(p),
        )

        assert len(calls) == 1, "must notify exactly once across three repeat runs"
        assert r1["posted"] is True
        assert r2["posted"] is False and r2["reason"].startswith("deduped")
        assert r3["posted"] is False
        assert r1["dedupe_key"] == r2["dedupe_key"] == r3["dedupe_key"]

    def test_dedupe_survives_a_fresh_process_reload_of_the_ledger(self, tmp_path):
        """The event-ledger is ON DISK — a brand-new call (simulating a
        fresh cron invocation) against the SAME ledger path must still
        dedupe; nothing may rely on in-memory state."""
        ledger_path = str(tmp_path / "ledger.json")
        candidates = [{"id": "p1"}]
        inv.post_lifecycle_card(inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
                                 board_notifier=lambda p: "ok")
        calls = []
        result = inv.post_lifecycle_card(inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
                                          board_notifier=lambda p: calls.append(p))
        assert calls == []
        assert result["posted"] is False

    def test_different_candidate_set_gets_its_own_card(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        calls = []
        inv.post_lifecycle_card(inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
                                 board_notifier=lambda p: calls.append(p))
        inv.post_lifecycle_card(inv.CARD_KIND_STALE, [{"id": "p2"}], ledger_path=ledger_path,
                                 board_notifier=lambda p: calls.append(p))
        assert len(calls) == 2

    def test_different_card_kind_same_ids_is_a_different_card(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        calls = []
        inv.post_lifecycle_card(inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
                                 board_notifier=lambda p: calls.append(p))
        inv.post_lifecycle_card(inv.CARD_KIND_DUPLICATE, [{"id": "p1"}], ledger_path=ledger_path,
                                 board_notifier=lambda p: calls.append(p))
        assert len(calls) == 2

    def test_empty_candidates_never_posts(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        result = inv.post_lifecycle_card(inv.CARD_KIND_STALE, [], ledger_path=ledger_path,
                                          board_notifier=lambda p: (_ for _ in ()).throw(AssertionError("must not be called")))
        assert result["posted"] is False

    def test_failing_notifier_is_fail_soft_and_retried_next_run(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        r1 = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
            board_notifier=lambda p: (_ for _ in ()).throw(RuntimeError("board down")),
        )
        assert r1["posted"] is False
        assert r1["error"] == "board down"

        calls = []
        r2 = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
            board_notifier=lambda p: calls.append(p) or "ok",
        )
        assert r2["posted"] is True
        assert len(calls) == 1

    def test_invalid_card_kind_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            inv.post_lifecycle_card("not-a-real-kind", [{"id": "p1"}],
                                     ledger_path=str(tmp_path / "l.json"),
                                     board_notifier=lambda p: "ok")


# ---------------------------------------------------------------------------
# execute_approved_deletes — acceptance (c) present->export->delete->absent
# ---------------------------------------------------------------------------
class TestExecuteApprovedDeletes:
    def _carded(self, tmp_path, ids=("p1",)):
        ledger_path = str(tmp_path / "ledger.json")
        candidates = [{"id": i} for i in ids]
        post = inv.post_lifecycle_card(inv.CARD_KIND_STALE, candidates, ledger_path=ledger_path,
                                        board_notifier=lambda p: "ok")
        return ledger_path, post["dedupe_key"]

    def test_full_present_export_delete_absent_receipt_chain(self, tmp_path):
        ledger_path, key = self._carded(tmp_path)
        state = {"p1": True}
        report = inv.execute_approved_deletes(
            key, ["p1"], ledger_path=ledger_path,
            exporter=lambda i: {"id": i, "restorable": "page-data-copy"},
            deleter=lambda i: state.__setitem__(i, False),
            prober=lambda i: state.get(i, False),
            evidence_base=str(tmp_path),
        )
        assert report.all_deleted()
        entry = report.results[0]
        assert entry["present_before"] is True
        assert entry["absent_after"] is True
        assert entry["status"] == "deleted"

        # (c) — restorable export + receipt actually landed on disk.
        assert os.path.isfile(entry["export_path"])
        with open(entry["export_path"]) as fh:
            exported = json.load(fh)
        assert exported["restorable"] == "page-data-copy"

        assert os.path.isfile(entry["receipt_path"])
        with open(entry["receipt_path"]) as fh:
            receipt = json.load(fh)
        assert receipt["present_before"] is True
        assert receipt["absent_after"] is True

    def test_already_absent_id_is_skipped_never_fabricated(self, tmp_path):
        ledger_path, key = self._carded(tmp_path)
        deleter_calls = []
        report = inv.execute_approved_deletes(
            key, ["p1"], ledger_path=ledger_path,
            exporter=lambda i: {"id": i},
            deleter=lambda i: deleter_calls.append(i),
            prober=lambda i: False,  # never present
            evidence_base=str(tmp_path),
        )
        assert report.results[0]["status"] == "skipped-not-present"
        assert deleter_calls == []

    def test_delete_unconfirmed_is_recorded_honestly(self, tmp_path):
        ledger_path, key = self._carded(tmp_path)
        report = inv.execute_approved_deletes(
            key, ["p1"], ledger_path=ledger_path,
            exporter=lambda i: {"id": i},
            deleter=lambda i: None,       # deletes nothing really
            prober=lambda i: True,        # still present before AND after
            evidence_base=str(tmp_path),
        )
        assert report.results[0]["status"] == "delete-unconfirmed"
        assert report.all_deleted() is False

    def test_deleter_exception_isolates_to_one_entry_never_crashes_batch(self, tmp_path):
        ledger_path, key = self._carded(tmp_path, ids=("p1", "p2"))
        state = {"p1": True, "p2": True}
        def _deleter(i):
            if i == "p1":
                raise RuntimeError("boom")
            state[i] = False
        report = inv.execute_approved_deletes(
            key, ["p1", "p2"], ledger_path=ledger_path,
            exporter=lambda i: {"id": i},
            deleter=_deleter,
            prober=lambda i: state.get(i, False),
            evidence_base=str(tmp_path),
        )
        statuses = {r["id"]: r["status"] for r in report.results}
        assert statuses["p1"] == "failed"
        p1_entry = next(r for r in report.results if r["id"] == "p1")
        assert "boom" in p1_entry["error"]
        # p2 still processes independently -- one id's deleter exception
        # never aborts or skips the rest of the batch.
        assert statuses["p2"] == "deleted"

    def test_every_id_writes_its_own_receipt_even_on_failure(self, tmp_path):
        ledger_path, key = self._carded(tmp_path)
        def _boom_exporter(i):
            raise RuntimeError("export failed")
        report = inv.execute_approved_deletes(
            key, ["p1"], ledger_path=ledger_path,
            exporter=_boom_exporter,
            deleter=lambda i: None,
            prober=lambda i: True,
            evidence_base=str(tmp_path),
        )
        entry = report.results[0]
        assert entry["status"] == "failed"
        assert os.path.isfile(entry["receipt_path"])


# ---------------------------------------------------------------------------
# Fail-closed guard — acceptance (e): nothing deletes without an approved card
# ---------------------------------------------------------------------------
class TestFailClosedGuard:
    def test_unknown_dedupe_key_refused_and_deletes_nothing(self, tmp_path):
        deleter_calls = []
        with pytest.raises(inv.LifecycleGuardError):
            inv.execute_approved_deletes(
                "never-existed", ["p1"], ledger_path=str(tmp_path / "ledger.json"),
                exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
                prober=lambda i: True, evidence_base=str(tmp_path),
            )
        assert deleter_calls == []

    def test_id_outside_card_candidates_refused_and_deletes_nothing_in_batch(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        post = inv.post_lifecycle_card(inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
                                        board_notifier=lambda p: "ok")
        deleter_calls = []
        # p1 IS legitimately carded; p2 is NOT — the whole batch must refuse,
        # including p1 (fail-closed means the whole call stops, not a
        # partial "delete the legit ones" fallback).
        with pytest.raises(inv.LifecycleGuardError):
            inv.execute_approved_deletes(
                post["dedupe_key"], ["p1", "p2"], ledger_path=ledger_path,
                exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
                prober=lambda i: True, evidence_base=str(tmp_path),
            )
        assert deleter_calls == [], "fail-closed must delete ZERO ids, even the legitimate ones, on any violation"

    def test_undelivered_card_cannot_be_executed(self, tmp_path):
        ledger_path = str(tmp_path / "ledger.json")
        # A card that failed to deliver is recorded delivered=False.
        result = inv.post_lifecycle_card(
            inv.CARD_KIND_STALE, [{"id": "p1"}], ledger_path=ledger_path,
            board_notifier=lambda p: (_ for _ in ()).throw(RuntimeError("down")),
        )
        with pytest.raises(inv.LifecycleGuardError):
            inv.execute_approved_deletes(
                result["dedupe_key"], ["p1"], ledger_path=ledger_path,
                exporter=lambda i: {"id": i}, deleter=lambda i: None,
                prober=lambda i: True, evidence_base=str(tmp_path),
            )

    def test_a_guard_test_proves_nothing_deletes_without_any_card_at_all(self, tmp_path):
        """The literal acceptance-(e) shape: an empty/never-touched ledger,
        any dedupe_key at all -> refused."""
        deleter_calls = []
        with pytest.raises(inv.LifecycleGuardError):
            inv.execute_approved_deletes(
                "anything", ["p1", "p2", "p3"], ledger_path=str(tmp_path / "empty.json"),
                exporter=lambda i: {"id": i}, deleter=lambda i: deleter_calls.append(i),
                prober=lambda i: True, evidence_base=str(tmp_path),
            )
        assert deleter_calls == []


# ---------------------------------------------------------------------------
# prune_evidence_roots — acceptance (d): skips roots referenced by open cards
# ---------------------------------------------------------------------------
class TestPruneEvidenceRoots:
    def _make_runs(self, base_dir, names):
        made = []
        for name in names:
            run_dir = os.path.join(base_dir, name)
            os.makedirs(os.path.join(run_dir, "routing"), exist_ok=True)
            with open(os.path.join(run_dir, "routing", "intake-receipt.json"), "w") as fh:
                json.dump({"ok": True}, fh)
            made.append(run_dir)
        return made

    def test_keeps_newest_n_compresses_the_rest(self, tmp_path):
        names = [f"v2-run-{i:03d}" for i in range(15)]
        made = self._make_runs(str(tmp_path), names)
        report = inv.prune_evidence_roots(
            str(tmp_path), keep_n=10, slug_of=lambda d: "one-group",
            compressor=lambda d: d,
        )
        assert len(report.kept) == 10
        assert len(report.compressed) == 5
        assert set(report.kept) | set(report.compressed) == set(made)

    def test_root_referenced_by_open_card_is_kept_past_keep_n(self, tmp_path):
        names = [f"v2-run-{i:03d}" for i in range(12)]
        made = self._make_runs(str(tmp_path), names)
        oldest = sorted(made)[0]
        report = inv.prune_evidence_roots(
            str(tmp_path), keep_n=10, slug_of=lambda d: "one-group",
            open_card_referenced_roots=[oldest],
            compressor=lambda d: d,
        )
        assert oldest in report.kept
        assert oldest not in report.compressed
        assert oldest in report.skipped_open_card

    def test_root_referenced_by_blocked_card_is_never_touched(self, tmp_path):
        names = [f"v2-run-{i:03d}" for i in range(3)]
        made = self._make_runs(str(tmp_path), names)
        newest = sorted(made)[-1]
        report = inv.prune_evidence_roots(
            str(tmp_path), keep_n=0, slug_of=lambda d: "one-group",
            blocked_card_referenced_roots=[newest],
            compressor=lambda d: d,
        )
        assert newest in report.skipped_blocked
        assert newest not in report.compressed
        assert newest not in report.kept

    def test_compressor_never_called_for_kept_roots(self, tmp_path):
        names = [f"v2-run-{i:03d}" for i in range(5)]
        self._make_runs(str(tmp_path), names)
        compressed_calls = []
        inv.prune_evidence_roots(
            str(tmp_path), keep_n=10, slug_of=lambda d: "one-group",
            compressor=lambda d: compressed_calls.append(d),
        )
        assert compressed_calls == []

    def test_separate_slug_groups_are_retained_independently(self, tmp_path):
        names_a = [f"v2-acme-{i:03d}" for i in range(12)]
        names_b = [f"v2-globex-{i:03d}" for i in range(3)]
        self._make_runs(str(tmp_path), names_a + names_b)
        report = inv.prune_evidence_roots(
            str(tmp_path), keep_n=10,
            slug_of=lambda d: "acme" if "acme" in d else "globex",
            compressor=lambda d: d,
        )
        # acme group: 12 -> keep 10, compress 2. globex: 3 -> keep all 3, compress 0.
        assert len(report.compressed) == 2
        assert len(report.kept) == 13

    def test_default_slug_of_groups_by_stripped_run_id(self):
        assert inv._default_slug_of("/base/v2-acme-20260715-abcdef01") == "acme"
        assert inv._default_slug_of("v2-acme") == "acme"

    def test_never_deletes_only_compresses(self, tmp_path):
        names = [f"v2-run-{i:03d}" for i in range(15)]
        made = self._make_runs(str(tmp_path), names)
        inv.prune_evidence_roots(
            str(tmp_path), keep_n=10, slug_of=lambda d: "one-group",
            compressor=lambda d: d,  # a real compressor would archive, never rmtree here
        )
        # every original run directory must still exist on disk -- this
        # module's compressor call is the ONLY place removal could happen,
        # and the identity compressor above never touched the filesystem.
        for run_dir in made:
            assert os.path.isdir(run_dir)


# ---------------------------------------------------------------------------
# inventory_advisory (/api/health/deep tie-in, item 4)
# ---------------------------------------------------------------------------
class TestInventoryAdvisory:
    def test_shape_and_values(self, basic_report):
        flags = inv.flag_lifecycle_candidates(basic_report, now="2026-07-15T00:00:00Z")
        advisory = inv.inventory_advisory(basic_report, flags, orphan_media=[{"id": "m1"}, {"id": "m2"}])
        assert advisory["pages_total"] == 2
        assert advisory["drafts_stale"] == 1
        assert advisory["superseded"] == 0
        assert advisory["duplicate_markers"] == 0
        assert advisory["orphan_media"] == 2

    def test_no_orphan_media_defaults_to_zero(self, basic_report):
        flags = inv.flag_lifecycle_candidates(basic_report)
        advisory = inv.inventory_advisory(basic_report, flags)
        assert advisory["orphan_media"] == 0

    def test_pure_no_io(self, basic_report):
        flags = inv.flag_lifecycle_candidates(basic_report)
        a1 = inv.inventory_advisory(basic_report, flags)
        a2 = inv.inventory_advisory(basic_report, flags)
        assert a1 == a2


# ---------------------------------------------------------------------------
# find_orphan_media — report-only
# ---------------------------------------------------------------------------
class TestFindOrphanMedia:
    def test_reports_only_unreferenced_media(self):
        orphans = inv.find_orphan_media(
            lambda: [{"id": "m1", "url": "https://cdn/a.png"},
                     {"id": "m2", "url": "https://cdn/b.png"},
                     {"id": "m3", "url": "https://cdn/c.png"}],
            referenced_urls=["https://cdn/a.png", "https://cdn/c.png"],
        )
        assert [o["id"] for o in orphans] == ["m2"]

    def test_all_referenced_yields_no_orphans(self):
        orphans = inv.find_orphan_media(
            lambda: [{"id": "m1", "url": "https://cdn/a.png"}],
            referenced_urls=["https://cdn/a.png"],
        )
        assert orphans == []

    def test_never_deletes_pure_reporter(self):
        # find_orphan_media has no delete-shaped parameter at all -- there is
        # no way to make it mutate anything; this is a structural assertion
        # that the function signature carries no such capability.
        import inspect
        sig = inspect.signature(inv.find_orphan_media)
        assert set(sig.parameters) == {"media_lister", "referenced_urls"}


# ---------------------------------------------------------------------------
# Live wiring sketches — proven NOT to fabricate data
# ---------------------------------------------------------------------------
class TestLiveWiringSketches:
    def test_funnel_lister_sketch_refuses_rather_than_fabricates(self):
        sketch = inv.live_funnel_lister_over_browser_manager("sess", lambda s, e: None)
        with pytest.raises(NotImplementedError):
            sketch("loc1")

    def test_page_lister_sketch_builds_the_real_proven_eval_no_session_gateway_needed(self):
        seen = []
        def _ab_eval(session, js):
            seen.append((session, js))
            return {"funnelPages": [{"id": "px", "name": "ZHC Live Page"}]}
        lister = inv.live_page_lister_over_rest_canvas("sess-1", _ab_eval)
        pages = lister("funnel-123", "loc-1")
        assert [p["id"] for p in pages] == ["px"]
        assert seen[0][0] == "sess-1"
        assert "funnelId=funnel-123" in seen[0][1]
        assert "loc-1" in seen[0][1]

    def test_page_lister_sketch_handles_empty_body_gracefully(self):
        lister = inv.live_page_lister_over_rest_canvas("s", lambda s, e: None)
        assert lister("f1", "loc1") == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class TestCli:
    def test_selftest_flag_returns_zero(self):
        assert inv.main(["--selftest"]) == 0

    def test_advisory_requires_inventory_json(self):
        assert inv.main(["--advisory"]) == 2

    def test_advisory_missing_file_errors(self, tmp_path):
        assert inv.main(["--advisory", "--inventory-json", str(tmp_path / "missing.json")]) == 2

    def test_advisory_end_to_end(self, tmp_path, basic_report, capsys):
        path = inv.write_inventory(str(tmp_path), basic_report)
        rc = inv.main(["--advisory", "--inventory-json", path])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["pages_total"] == 2

    def test_prune_end_to_end(self, tmp_path, capsys):
        run_dir = os.path.join(str(tmp_path), "v2-x")
        os.makedirs(os.path.join(run_dir, "routing"), exist_ok=True)
        with open(os.path.join(run_dir, "routing", "intake-receipt.json"), "w") as fh:
            json.dump({"ok": True}, fh)
        rc = inv.main(["--prune", "--base-dir", str(tmp_path)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert run_dir in out["kept"]

    def test_no_args_prints_help_and_exits_nonzero(self, capsys):
        rc = inv.main([])
        assert rc == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
