#!/usr/bin/env python3
"""test_ghl_bulk_workflow_enroll.py — proof for U112 (E5-7; closes G5): Skill 6
bulk-send GHL workflow enrollment by tag / explicit array, fail-closed on any
ambiguous/partial match.

BINARY acceptance covered here (all against ``FakeGhlClient` fixtures — no
network, no browser, no live GHL call, ever):
  (a) bulk-add BY TAG enrolls exactly the tag-matched contacts, receipt +
      read-back (`enrolled == matched - failures`) proven.
  (b) bulk-add BY EXPLICIT ARRAY enrolls exactly the listed contacts.
  (c) an ambiguous/partial match fails closed: zero enrollment + a named
      ``AmbiguousMatchError`` — covers TAG-mode incomplete pagination,
      TAG-mode over-broad substring match, and ARRAY-mode an unresolved id.
  (d) cleanup: present -> delete -> absent proof.

Live enrollment read-back (an actual GET against a real GHL location
confirming true workflow membership) is deferred to the LIVE-PROOF tier —
this suite proves the harness only.

Run: pytest 06-ghl-install-pages/tests/test_ghl_bulk_workflow_enroll.py -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for p in (str(_TOOLS_DIR),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_bulk_workflow_enroll as bwe  # noqa: E402

_MODULE_PATH = _TOOLS_DIR / "ghl_bulk_workflow_enroll.py"


def test_module_exists():
    assert _MODULE_PATH.exists(), "ghl_bulk_workflow_enroll.py must exist (U112)"


# ---------------------------------------------------------------------------
# (a) TAG mode — exact match enrolls exactly the tag-matched contacts
# ---------------------------------------------------------------------------
def test_tag_mode_exact_match_enrolls_exactly_the_tagged_contacts(tmp_path):
    contacts = {
        "c1": {"id": "c1", "tags": ["vip", "east"]},
        "c2": {"id": "c2", "tags": ["vip"]},
        "c3": {"id": "c3", "tags": ["west"]},
    }
    client = bwe.FakeGhlClient(contacts=contacts, page_size=2)
    receipt = bwe.run_bulk_send(
        client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
        evidence_root=str(tmp_path),
    )
    assert sorted(receipt["matched_contact_ids"]) == ["c1", "c2"]
    assert sorted(receipt["enrolled_contact_ids"]) == ["c1", "c2"]
    assert receipt["matched"] == 2
    assert receipt["enrolled"] == 2
    assert receipt["failures"] == []
    assert receipt["read_back"]["ok"] is True
    assert sorted(client.enrolled) == [("c1", "W1"), ("c2", "W1")]
    # c3 (no vip tag) must never be touched.
    assert all(cid != "c3" for cid, _wf in client.enrolled)


def test_tag_mode_pagination_multi_page_exact_total_succeeds(tmp_path):
    """Multi-page fetch that DOES exhaust the total must NOT be flagged
    ambiguous — only an INCOMPLETE fetch is."""
    contacts = {f"c{i}": {"id": f"c{i}", "tags": ["vip"]} for i in range(5)}
    client = bwe.FakeGhlClient(contacts=contacts, page_size=2)
    receipt = bwe.run_bulk_send(
        client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
        evidence_root=str(tmp_path),
    )
    assert receipt["matched"] == 5
    assert receipt["enrolled"] == 5
    assert receipt["read_back"]["ok"] is True
    assert client.search_call_count >= 3  # 5 contacts / page_size=2 -> 3 pages


def test_tag_mode_receipt_written_to_routing_bulk_send_receipt_json(tmp_path):
    contacts = {"c1": {"id": "c1", "tags": ["vip"]}}
    client = bwe.FakeGhlClient(contacts=contacts)
    bwe.run_bulk_send(
        client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
        evidence_root=str(tmp_path),
    )
    path = tmp_path / "routing" / "bulk-send-receipt.json"
    assert path.exists()
    with open(path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["mode"] == "tag"
    assert on_disk["tag"] == "vip"
    assert on_disk["array"] is None


# ---------------------------------------------------------------------------
# (b) ARRAY mode — explicit array enrolls exactly the listed contacts
# ---------------------------------------------------------------------------
def test_array_mode_enrolls_exactly_the_listed_contacts(tmp_path):
    contacts = {
        "c1": {"id": "c1", "tags": []},
        "c2": {"id": "c2", "tags": []},
        "c3": {"id": "c3", "tags": []},
    }
    client = bwe.FakeGhlClient(contacts=contacts)
    receipt = bwe.run_bulk_send(
        client, mode="array", location_id="L1", workflow_id="W1",
        contact_ids=["c1", "c3"], evidence_root=str(tmp_path),
    )
    assert sorted(receipt["enrolled_contact_ids"]) == ["c1", "c3"]
    assert receipt["array"] == ["c1", "c3"]
    assert receipt["read_back"]["ok"] is True
    # c2 was never listed — must never be touched.
    assert all(cid != "c2" for cid, _wf in client.enrolled)


def test_array_mode_dedupes_duplicate_ids_without_treating_as_missing(tmp_path):
    contacts = {"c1": {"id": "c1", "tags": []}}
    client = bwe.FakeGhlClient(contacts=contacts)
    receipt = bwe.run_bulk_send(
        client, mode="array", location_id="L1", workflow_id="W1",
        contact_ids=["c1", "c1", "c1"], evidence_root=str(tmp_path),
    )
    assert receipt["matched"] == 1
    assert receipt["enrolled"] == 1
    assert receipt["read_back"]["ok"] is True


# ---------------------------------------------------------------------------
# (c) ambiguous/partial match fails closed — zero enrollment, named error
# ---------------------------------------------------------------------------
def test_tag_mode_over_broad_substring_match_fails_closed(tmp_path):
    """A "contains" search matching a DIFFERENT tag as a substring must
    refuse the whole batch, not silently pick a subset."""
    contacts = {
        "c1": {"id": "c1", "tags": ["vip"]},
        "c2": {"id": "c2", "tags": ["vip-archive"]},  # substring only, not exact
    }
    client = bwe.FakeGhlClient(contacts=contacts, tag_server_matches={"vip": ["c1", "c2"]})
    with pytest.raises(bwe.AmbiguousMatchError):
        bwe.run_bulk_send(
            client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
            evidence_root=str(tmp_path),
        )
    assert client.enrolled == [], "over-broad match must enroll NOTHING"
    receipt = bwe.load_receipt(str(tmp_path))
    assert receipt["fail_closed"] is True
    assert receipt["enrolled"] == 0
    assert receipt["matched"] == 0
    assert "over-matched" in receipt["fail_closed_reason"]


def test_tag_mode_incomplete_pagination_fails_closed(tmp_path):
    contacts = {f"c{i}": {"id": f"c{i}", "tags": ["vip"]} for i in range(5)}
    client = bwe.FakeGhlClient(
        contacts=contacts, page_size=2, simulate_incomplete_pagination=True,
    )
    with pytest.raises(bwe.AmbiguousMatchError, match="pagination incomplete"):
        bwe.run_bulk_send(
            client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
            evidence_root=str(tmp_path),
        )
    assert client.enrolled == []
    receipt = bwe.load_receipt(str(tmp_path))
    assert receipt["fail_closed"] is True
    assert receipt["enrolled"] == 0


def test_tag_mode_no_total_reported_fails_closed(tmp_path):
    class NoTotalClient(bwe.FakeGhlClient):
        def search_contacts(self, location_id, tag, page_limit=100, search_after=None):
            resp = super().search_contacts(location_id, tag, page_limit, search_after)
            resp.pop("total", None)
            return resp

    contacts = {"c1": {"id": "c1", "tags": ["vip"]}}
    client = NoTotalClient(contacts=contacts)
    with pytest.raises(bwe.AmbiguousMatchError, match="total count"):
        bwe.run_bulk_send(
            client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
            evidence_root=str(tmp_path),
        )
    assert client.enrolled == []


def test_array_mode_missing_contact_fails_closed(tmp_path):
    contacts = {"c1": {"id": "c1", "tags": []}}
    client = bwe.FakeGhlClient(contacts=contacts)
    with pytest.raises(bwe.AmbiguousMatchError, match="not found"):
        bwe.run_bulk_send(
            client, mode="array", location_id="L1", workflow_id="W1",
            contact_ids=["c1", "c_ghost"], evidence_root=str(tmp_path),
        )
    assert client.enrolled == [], "a partial-array match must enroll NOTHING, not even c1"
    receipt = bwe.load_receipt(str(tmp_path))
    assert receipt["fail_closed"] is True
    assert receipt["array"] == ["c1", "c_ghost"]


def test_tag_mode_pagination_runaway_fails_closed():
    """A pathological / mis-behaving pagination cursor that never exhausts
    must not loop forever or silently enroll a partial set — it fails closed
    once ``max_pages`` is exceeded."""
    contacts = {f"c{i}": {"id": f"c{i}", "tags": ["vip"]} for i in range(3)}
    client = bwe.FakeGhlClient(contacts=contacts, page_size=1)
    with pytest.raises(bwe.AmbiguousMatchError, match="pages"):
        bwe.resolve_matched_by_tag(client, "L1", "vip", page_limit=1, max_pages=1)
    assert client.enrolled == []


# ---------------------------------------------------------------------------
# Per-contact enroll FAILURE (allowed, counted) vs ambiguous MATCH (fatal)
# ---------------------------------------------------------------------------
def test_partial_enroll_failure_is_counted_not_treated_as_ambiguous(tmp_path):
    contacts = {
        "c1": {"id": "c1", "tags": ["vip"]},
        "c2": {"id": "c2", "tags": ["vip"]},
    }
    client = bwe.FakeGhlClient(
        contacts=contacts, enroll_failures={"c2": "workflow already contains contact"},
    )
    receipt = bwe.run_bulk_send(
        client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
        evidence_root=str(tmp_path),
    )
    assert receipt["matched"] == 2
    assert receipt["enrolled"] == 1
    assert receipt["enrolled_contact_ids"] == ["c1"]
    assert len(receipt["failures"]) == 1
    assert receipt["failures"][0]["contact_id"] == "c2"
    assert receipt["read_back"]["ok"] is True  # 1 == 2 - 1


# ---------------------------------------------------------------------------
# Read-back invariant
# ---------------------------------------------------------------------------
def test_read_back_mismatch_is_detected_and_raises():
    # Honest receipt first: 2 matched, c1 enrolled, c2 failed -> expected
    # enrolled = 2 - 1 = 1, which is exactly what's recorded (consistent).
    honest_receipt = bwe.build_receipt(
        mode="tag", tag="vip", contact_ids_requested=None, location_id="L1",
        workflow_id="W1", matched_ids=["c1", "c2"], enrolled_ids=["c1"],
        failures=[{"contact_id": "c2", "error": "boom"}],
    )
    assert honest_receipt["read_back"]["ok"] is True
    bwe.assert_read_back(honest_receipt)  # must not raise

    # Now tamper it the same way a hand-assembled summary could lie: claim 2
    # enrolled even though a failure is on record for c2 (matched - failures = 1).
    lying_receipt = dict(honest_receipt)
    lying_receipt["enrolled"] = 2
    with pytest.raises(bwe.ReadBackMismatch):
        bwe.assert_read_back(lying_receipt)


def test_read_back_skipped_for_fail_closed_and_dry_run_receipts():
    fc = bwe.build_receipt(
        mode="tag", tag="x", contact_ids_requested=None, location_id="L1",
        workflow_id="W1", matched_ids=[], enrolled_ids=[], failures=[],
        fail_closed=True, fail_closed_reason="test",
    )
    assert fc["read_back"] == {"ok": True, "skipped": True, "reason": "fail_closed"}

    dr = bwe.build_receipt(
        mode="array", tag=None, contact_ids_requested=["c1"], location_id="L1",
        workflow_id="W1", matched_ids=["c1"], enrolled_ids=[], failures=[],
        dry_run=True,
    )
    assert dr["read_back"] == {"ok": True, "skipped": True, "reason": "dry_run"}


def test_dry_run_matches_but_enrolls_nothing(tmp_path):
    contacts = {"c1": {"id": "c1", "tags": ["vip"]}}
    client = bwe.FakeGhlClient(contacts=contacts)
    receipt = bwe.run_bulk_send(
        client, mode="tag", location_id="L1", workflow_id="W1", tag="vip",
        evidence_root=str(tmp_path), dry_run=True,
    )
    assert receipt["matched"] == 1
    assert receipt["enrolled"] == 0
    assert receipt["dry_run"] is True
    assert client.enrolled == []


# ---------------------------------------------------------------------------
# (d) cleanup: present -> delete -> absent proof
# ---------------------------------------------------------------------------
def test_cleanup_present_delete_absent_proof():
    contacts = {
        "c1": {"id": "c1", "tags": []},
        "c2": {"id": "c2", "tags": []},
    }
    client = bwe.FakeGhlClient(contacts=contacts)
    cleanup = bwe.cleanup_present_delete_absent(client, ["c1", "c2"])
    assert cleanup["present_before"] == {"c1": True, "c2": True}
    assert sorted(cleanup["deleted"]) == ["c1", "c2"]
    assert cleanup["absent_after"] == {"c1": True, "c2": True}
    assert cleanup["ok"] is True
    assert client.get_contact("c1") is None
    assert client.get_contact("c2") is None


def test_cleanup_reports_dishonest_if_delete_did_not_take(monkeypatch):
    """A client whose delete does not actually remove the contact must
    surface ok=False, never a false 'cleaned up'."""
    contacts = {"c1": {"id": "c1", "tags": []}}

    class StubbornClient(bwe.FakeGhlClient):
        def delete_contact(self, contact_id):
            self.deleted.append(contact_id)
            return {"status": "deleted"}  # BUT never actually removes it

    client = StubbornClient(contacts=contacts)
    cleanup = bwe.cleanup_present_delete_absent(client, ["c1"])
    assert cleanup["ok"] is False
    assert cleanup["absent_after"] == {"c1": False}


# ---------------------------------------------------------------------------
# Flag gate (additive-behind-a-flag; revert = flip the flag)
# ---------------------------------------------------------------------------
def test_require_flag_raises_when_unset(monkeypatch):
    monkeypatch.delenv(bwe.FLAG_ENV_VAR, raising=False)
    with pytest.raises(bwe.BulkSendFlagOff):
        bwe._require_flag()


def test_require_flag_raises_when_zero(monkeypatch):
    monkeypatch.setenv(bwe.FLAG_ENV_VAR, "0")
    with pytest.raises(bwe.BulkSendFlagOff):
        bwe._require_flag()


def test_require_flag_passes_when_one(monkeypatch):
    monkeypatch.setenv(bwe.FLAG_ENV_VAR, "1")
    bwe._require_flag()  # must not raise


def test_cli_refuses_live_run_without_flag_and_touches_no_network(monkeypatch, capsys):
    monkeypatch.delenv(bwe.FLAG_ENV_VAR, raising=False)

    def _boom(*a, **kw):
        raise AssertionError("GhlHttpClient must never be constructed without the flag")

    monkeypatch.setattr(bwe, "GhlHttpClient", _boom)
    rc = bwe.main(["--location-id", "L1", "--workflow-id", "W1", "--tag", "vip"])
    assert rc == 2
    out = capsys.readouterr().err
    assert "REFUSED" in out
    assert bwe.FLAG_ENV_VAR in out


def test_cli_tag_and_contact_ids_mutually_exclusive():
    with pytest.raises(SystemExit):
        bwe.main([
            "--location-id", "L1", "--workflow-id", "W1",
            "--tag", "vip", "--contact-ids", "c1,c2",
        ])


def test_cli_requires_target_selector():
    with pytest.raises(SystemExit):
        bwe.main(["--location-id", "L1", "--workflow-id", "W1"])


# ---------------------------------------------------------------------------
# --selftest CLI entry point
# ---------------------------------------------------------------------------
def test_selftest_cli_passes():
    rc = bwe.main(["--selftest"])
    assert rc == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
