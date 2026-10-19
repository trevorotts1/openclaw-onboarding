"""Offline tests for S06-07: the SUPPORTED PUBLIC funnel/page inventory
reads (tools/ghl_funnels_read.py) behind ghl_inventory's seams.

MOCK-ONLY: no network, no browser, no live GoHighLevel. Every HTTP call is
an injected fake opener; every credential is a fixture string resolved
through a monkeypatched resolver or passed explicitly. These tests pin the
prep step-7 fixture cases:

  (i)   empty inventory -> empty result, not an error
  (ii)  single page -> no second request
  (iii) multi-page -> all rows collected, in order, de-duplicated
  (iv)  completeness failure -> raises, returns nothing
  (v)   runaway pagination -> max-pages cap raises
  (vi)  ZHC filtering applies on public rows (end-to-end via enumerate)
  (vii) non-2xx / 403 -> token-context diagnosis, no credential printed

Plus: the transport header contract (Bearer LOCATION PIT + the funnels
Version, NOT the internal/media 2021-07-28), shared-resolver consumption
(delta C4), the explicit status mapping (Q7), the step-6 router read
registration, the probe declaration consistency (NQ1/NQ5), and the
stale-claim corrections (docstring + SKILL.md) with the protected build
claims untouched.

Run:
    python3 -m pytest tests/test_ghl_funnels_read.py -v
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.parse

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import ghl_funnels_read as fr  # noqa: E402
import ghl_inventory as inv  # noqa: E402
import ghl_media  # noqa: E402
import ghl_object_router as router  # noqa: E402
import capability_probe  # noqa: E402

FIXTURE_PIT = "pit-fixture-location-token-for-tests-only"


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, payload, code=200):
        self._payload = payload
        self._code = code

    def getcode(self):
        return self._code

    def read(self):
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


class RecordingOpener:
    """An opener callable (Request, timeout) -> FakeResponse, driven by a
    handler(req) that returns a FakeResponse or raises HTTPError."""

    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        return self.handler(req)

    def queries(self):
        return [
            urllib.parse.parse_qs(urllib.parse.urlsplit(r.full_url).query)
            for r in self.requests
        ]

    def offsets(self):
        return [int(q["offset"][0]) for q in self.queries()]


def _http_error(code, body=b"error body"):
    def _raise(req):
        raise urllib.error.HTTPError(
            req.full_url, code, f"HTTP {code}", hdrs=None, fp=io.BytesIO(body)
        )
    return _raise


def funnel_opener(pages_by_offset, calls=None):
    """Serve GET /funnels/funnel/list payloads keyed by offset."""
    def handler(req):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        offset = int(q["offset"][0])
        return FakeResponse(pages_by_offset[offset])
    opener = RecordingOpener(handler)
    if calls is not None:
        calls.append(opener)
    return opener


def page_opener(pages_by_offset):
    """Serve GET /funnels/page payloads keyed by offset."""
    def handler(req):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        offset = int(q["offset"][0])
        return FakeResponse(pages_by_offset[offset])
    return RecordingOpener(handler)


# ---------------------------------------------------------------------------
# Transport contract
# ---------------------------------------------------------------------------
class TestTransportContract:
    def test_headers_bearer_version_ua_and_services_origin(self):
        opener = funnel_opener({0: {"funnels": [], "count": 0, "traceId": "t"}})
        assert fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener) == []
        req = opener.requests[0]
        assert req.full_url.startswith(
            "https://services.leadconnectorhq.com/funnels/funnel/list?"
        )
        assert req.get_header("Authorization") == f"Bearer {FIXTURE_PIT}"
        # The funnels Version is its OWN constant (docs label 2023-02-21),
        # never the internal canvas or media 2021-07-28 (NQ4).
        assert req.get_header("Version") == fr.GHL_FUNNELS_VERSION == "2023-02-21"
        assert fr.GHL_FUNNELS_VERSION != ghl_media.GHL_MEDIA_VERSION
        ua = req.get_header("User-agent") or ""
        assert "Python-urllib" not in ua and ua != ""

    def test_resolver_is_consumed_when_pit_omitted(self, monkeypatch):
        seen = {}

        def _fake_resolve():
            seen["called"] = True
            return FIXTURE_PIT

        monkeypatch.setattr(ghl_media, "resolve_location_pit", _fake_resolve)
        opener = funnel_opener({0: {"funnels": [], "count": 0, "traceId": "t"}})
        fr.list_funnels("loc1", opener=opener)
        assert seen.get("called") is True
        assert opener.requests[0].get_header("Authorization") == f"Bearer {FIXTURE_PIT}"

    def test_resolver_failure_propagates(self, monkeypatch):
        def _boom():
            raise RuntimeError("GHL LOCATION PIT not found (fixture)")

        monkeypatch.setattr(ghl_media, "resolve_location_pit", _boom)
        opener = funnel_opener({0: {"funnels": [], "count": 0, "traceId": "t"}})
        with pytest.raises(RuntimeError, match="LOCATION PIT not found"):
            fr.list_funnels("loc1", opener=opener)
        assert opener.requests == []

    def test_403_is_token_context_diagnosis_without_credential(self):
        opener = RecordingOpener(_http_error(403, b"forbidden"))
        with pytest.raises(fr.FunnelsReadError) as excinfo:
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)
        msg = str(excinfo.value)
        assert "403" in msg and "LOCATION" in msg and "token-context" in msg.lower()
        assert FIXTURE_PIT not in msg

    def test_429_names_same_rail_cooldown_without_credential(self):
        opener = RecordingOpener(_http_error(429, b"slow down"))
        with pytest.raises(fr.FunnelsReadError) as excinfo:
            fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener)
        msg = str(excinfo.value)
        assert "429" in msg and "SAME rail" in msg
        assert FIXTURE_PIT not in msg

    def test_500_raises_with_status(self):
        opener = RecordingOpener(_http_error(500, b"boom"))
        with pytest.raises(fr.FunnelsReadError, match="500"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)

    def test_non_json_2xx_raises(self):
        opener = RecordingOpener(lambda req: FakeResponse(b"<html>nope</html>", 200))
        with pytest.raises(fr.FunnelsReadError, match="not JSON"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)

    def test_unrecognized_envelope_raises(self):
        opener = funnel_opener({0: {"somethingElse": []}})
        with pytest.raises(fr.FunnelsReadError, match="unrecognized response envelope"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)

    def test_non_object_row_raises(self):
        opener = funnel_opener({0: {"funnels": ["not-a-dict"], "count": 1, "traceId": "t"}})
        with pytest.raises(fr.FunnelsReadError, match="not a JSON object"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)


# ---------------------------------------------------------------------------
# Funnel pagination (prep step 7 cases i-v on the funnel endpoint)
# ---------------------------------------------------------------------------
class TestFunnelPagination:
    def test_empty_inventory_is_empty_not_error(self):  # (i)
        opener = funnel_opener({0: {"funnels": [], "count": 0, "traceId": "t"}})
        assert fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener) == []
        assert len(opener.requests) == 1

    def test_single_page_makes_no_second_request(self):  # (ii)
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1", "name": "ZHC A"}, {"id": "f2", "name": "ZHC B"}],
                "count": 2, "traceId": "t"},
        })
        got = fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=100)
        assert [f["id"] for f in got] == ["f1", "f2"]
        assert len(opener.requests) == 1

    def test_multi_page_all_collected_in_order_deduped(self):  # (iii)
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1"}, {"id": "f2"}], "count": 3, "traceId": "t"},
            2: {"funnels": [{"id": "f2"}, {"id": "f3"}], "count": 3, "traceId": "t"},
        })
        got = fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=2)
        assert [f["id"] for f in got] == ["f1", "f2", "f3"]
        assert opener.offsets() == [0, 2]

    def test_unmet_total_raises_and_returns_nothing(self):  # (iv)
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1"}], "count": 5, "traceId": "t"},
            2: {"funnels": [], "count": 5, "traceId": "t"},
        })
        with pytest.raises(fr.IncompleteInventoryError):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=2)

    def test_over_collected_vs_total_raises(self):  # (iv)
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1"}, {"id": "f2"}], "count": 1, "traceId": "t"},
        })
        with pytest.raises(fr.IncompleteInventoryError):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=100)

    def test_missing_count_raises(self):  # (iv)
        opener = funnel_opener({0: {"funnels": [{"id": "f1"}], "traceId": "t"}})
        with pytest.raises(fr.IncompleteInventoryError, match="no count"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener)

    def test_changing_total_raises(self):
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1"}], "count": 3, "traceId": "t"},
            1: {"funnels": [{"id": "f2"}], "count": 4, "traceId": "t"},
        })
        with pytest.raises(fr.IncompleteInventoryError, match="changed mid-read"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=1)

    def test_runaway_hits_max_pages_cap(self):  # (v)
        def handler(req):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            offset = int(q["offset"][0])
            return FakeResponse({
                "funnels": [{"id": f"f{offset}"}], "count": 10 ** 9, "traceId": "t",
            })

        opener = RecordingOpener(handler)
        with pytest.raises(fr.IncompleteInventoryError, match="max_pages|exceeded 3 pages"):
            fr.list_funnels("loc1", pit=FIXTURE_PIT, opener=opener, limit=1, max_pages=3)
        assert len(opener.requests) == 3


# ---------------------------------------------------------------------------
# Page pagination (prep step 7 cases i-v on the page endpoint)
# ---------------------------------------------------------------------------
class TestPagePagination:
    def test_empty_is_empty_not_error(self):  # (i)
        opener = page_opener({0: {"pages": []}})
        assert fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener) == []
        assert len(opener.requests) == 1

    def test_single_short_page_makes_no_second_request(self):  # (ii)
        opener = page_opener({0: {"pages": [{"_id": "p1", "name": "ZHC One"}]}})
        got = fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener, limit=100)
        assert [p["id"] for p in got] == ["p1"]
        assert len(opener.requests) == 1

    def test_multi_page_all_collected_in_order(self):  # (iii)
        opener = page_opener({
            0: {"pages": [{"_id": "p1"}, {"_id": "p2"}]},
            2: {"pages": [{"_id": "p3"}, {"_id": "p4"}]},
            4: {"pages": [{"_id": "p5"}]},
        })
        got = fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener, limit=2)
        assert [p["id"] for p in got] == ["p1", "p2", "p3", "p4", "p5"]
        assert opener.offsets() == [0, 2, 4]

    def test_runaway_hits_max_pages_cap(self):  # (v)
        def handler(req):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
            offset = int(q["offset"][0])
            return FakeResponse({"pages": [{"_id": f"p{offset}"}, {"_id": f"q{offset}"}]})

        opener = RecordingOpener(handler)
        with pytest.raises(fr.IncompleteInventoryError, match="exceeded 3 pages"):
            fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener, limit=2, max_pages=3)
        assert len(opener.requests) == 3

    def test_bare_list_envelope_accepted(self):
        opener = page_opener({0: [{"_id": "p1", "name": "ZHC Bare"}]})
        got = fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener)
        assert [p["id"] for p in got] == ["p1"]

    def test_alternate_envelope_key_accepted(self):
        opener = page_opener({0: {"funnelPages": [{"_id": "p1"}]}})
        got = fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener)
        assert [p["id"] for p in got] == ["p1"]

    def test_required_params_are_sent(self):
        opener = page_opener({0: {"pages": []}})
        fr.list_pages("funnel-9", "loc-9", pit=FIXTURE_PIT, opener=opener, limit=7)
        q = opener.queries()[0]
        assert q["funnelId"] == ["funnel-9"] and q["locationId"] == ["loc-9"]
        assert q["limit"] == ["7"] and q["offset"] == ["0"]


# ---------------------------------------------------------------------------
# Row mappings (prep step 4 + Q4/Q7)
# ---------------------------------------------------------------------------
class TestRowMappings:
    def test_page_id_aliased_from_documented_underscore_id(self):
        out = fr.normalize_page_row({"_id": "p1", "name": "ZHC P"})
        assert out["id"] == "p1"

    def test_funnel_id_aliased_when_id_absent(self):
        out = fr.normalize_funnel_row({"_id": "f1", "name": "ZHC F"})
        assert out["id"] == "f1"
        out2 = fr.normalize_funnel_row({"id": "f2", "_id": "other"})
        assert out2["id"] == "f2"  # an existing id is never overwritten

    def test_status_passes_through_case_insensitively(self):
        assert fr.normalize_page_row({"_id": "p", "status": "Published"})["status"] == "published"
        assert fr.normalize_page_row({"_id": "p", "status": "DRAFT"})["status"] == "draft"

    def test_absent_status_stays_absent(self):
        out = fr.normalize_page_row({"_id": "p1", "name": "ZHC P"})
        assert "status" not in out

    def test_unmapped_third_status_raises(self):  # Q7
        with pytest.raises(fr.FunnelsReadError, match="unmapped status"):
            fr.normalize_page_row({"_id": "p1", "status": "archived"})

    def test_unmapped_status_raises_through_the_lister(self):  # Q7
        opener = page_opener({0: {"pages": [{"_id": "p1", "status": "archived"}]}})
        with pytest.raises(fr.FunnelsReadError, match="unmapped status"):
            fr.list_pages("f1", "loc1", pit=FIXTURE_PIT, opener=opener)

    def test_marker_is_never_invented(self):  # Q4
        out = fr.normalize_page_row({"_id": "p1", "name": "ZHC P"})
        assert "marker" not in out

    def test_created_is_never_backfilled_from_updated_at(self):
        out = fr.normalize_page_row({"_id": "p1", "updatedAt": "2026-01-01T00:00:00Z"})
        assert "createdAt" not in out and "created" not in out
        assert out["updatedAt"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# End-to-end through the inventory seams (prep step 7 case vi + i)
# ---------------------------------------------------------------------------
def _inventory_opener():
    """One opener serving both public endpoints for a two-funnel location:
    one ZHC funnel (kept) and one non-ZHC funnel (filtered out)."""
    def handler(req):
        split = urllib.parse.urlsplit(req.full_url)
        q = urllib.parse.parse_qs(split.query)
        if split.path == "/funnels/funnel/list":
            return FakeResponse({
                "funnels": [
                    {"id": "f-zhc", "name": "ZHC Alpha"},
                    {"id": "f-client", "name": "Client's Own Funnel"},
                ],
                "count": 2, "traceId": "t",
            })
        if split.path == "/funnels/page":
            assert q["funnelId"] == ["f-zhc"], "pages must only be read for kept ZHC funnels"
            return FakeResponse({"pages": [
                {"_id": "p1", "name": "ZHC Landing", "status": "published",
                 "createdAt": "2026-07-01T00:00:00Z"},
                {"_id": "p2", "name": "ZHC Draft", "status": "draft",
                 "createdAt": "2020-01-01T00:00:00Z"},
            ]})
        raise AssertionError(f"unexpected path {split.path}")

    return RecordingOpener(handler)


class TestEnumerateEndToEnd:
    def test_zhc_filtering_applies_on_public_rows(self):  # (vi)
        opener = _inventory_opener()
        report = inv.enumerate_zhc_inventory(
            "loc-test",
            funnel_lister=inv.live_funnel_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
            page_lister=inv.live_page_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
            now=lambda: "2026-07-15T00:00:00Z",
        )
        assert {p.page for p in report.pages} == {"p1", "p2"}
        assert {p.funnel for p in report.pages} == {"f-zhc"}
        by_id = {p.page: p for p in report.pages}
        assert by_id["p1"].status == "published" and by_id["p2"].status == "draft"
        # No marker is documented by the public contract, so none is carried.
        assert all(p.marker == "" for p in report.pages)

    def test_empty_public_inventory_is_an_empty_report(self):  # (i)
        opener = funnel_opener({0: {"funnels": [], "count": 0, "traceId": "t"}})
        report = inv.enumerate_zhc_inventory(
            "loc-test",
            funnel_lister=inv.live_funnel_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
            page_lister=inv.live_page_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
        )
        assert report.pages == []

    def test_incomplete_public_read_propagates_and_returns_nothing(self):  # (iv)
        opener = funnel_opener({
            0: {"funnels": [{"id": "f1", "name": "ZHC A"}], "count": 9, "traceId": "t"},
            100: {"funnels": [], "count": 9, "traceId": "t"},
        })
        with pytest.raises(fr.IncompleteInventoryError):
            inv.enumerate_zhc_inventory(
                "loc-test",
                funnel_lister=inv.live_funnel_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
                page_lister=inv.live_page_lister_over_public_api(pit=FIXTURE_PIT, opener=opener),
            )

    def test_wiring_factory_signatures_match_the_seams(self):
        import inspect

        fl = inv.live_funnel_lister_over_public_api(pit=FIXTURE_PIT, opener=_inventory_opener())
        pl = inv.live_page_lister_over_public_api(pit=FIXTURE_PIT, opener=_inventory_opener())
        assert list(inspect.signature(fl).parameters) == ["location_id"]
        assert list(inspect.signature(pl).parameters) == ["funnel_id", "location_id"]


# ---------------------------------------------------------------------------
# CLI: --enumerate (prep step 8)
# ---------------------------------------------------------------------------
class TestEnumerateCli:
    def test_enumerate_writes_inventory_and_prints_summary_only(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(ghl_media, "resolve_location_id", lambda: "loc-test")
        monkeypatch.setattr(ghl_media, "resolve_location_pit", lambda: FIXTURE_PIT)
        monkeypatch.setattr(fr, "_default_opener", _inventory_opener())
        rc = inv.main(["--enumerate", "--base-dir", str(tmp_path)])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["location_id"] == "loc-test"
        assert out["pages_total"] == 2
        assert FIXTURE_PIT not in json.dumps(out)
        written = tmp_path / "page-lifecycle" / "inventory-loc-test.json"
        assert written.is_file()
        data = json.loads(written.read_text())
        assert {p["page"] for p in data["pages"]} == {"p1", "p2"}

    def test_enumerate_resolver_failure_returns_1(self, tmp_path, monkeypatch, capsys):
        def _boom():
            raise RuntimeError("GHL location id not found (fixture)")

        monkeypatch.setattr(ghl_media, "resolve_location_id", _boom)
        rc = inv.main(["--enumerate", "--base-dir", str(tmp_path)])
        assert rc == 1
        assert "location id not found" in capsys.readouterr().err

    def test_enumerate_without_evidence_base_returns_2(self, monkeypatch):
        monkeypatch.setattr(inv.cc_board, "resolve_evidence_base", lambda: "")
        rc = inv.main(["--enumerate"])
        assert rc == 2


# ---------------------------------------------------------------------------
# Step 6: router read registration (surface 1)
# ---------------------------------------------------------------------------
class TestRouterReadRegistration:
    def test_funnel_page_website_have_a_read_only_rest_rail(self):
        for obj in ("funnel", "website", "page"):
            steps = router.read_route(obj)
            assert len(steps) == 1, f"{obj}: expected exactly one registered read rail"
            step = steps[0]
            assert step.rail == router.Rail.REST_SERVICES
            assert step.tier == router.Tier.REST == 3
            assert step.token == router.Token.LOCATION_PIT
            assert step.can_create is False

    def test_read_rail_carries_tier_disclosure(self):
        step = router.read_route("funnel")[0]
        assert router.tier_disclosure(step).startswith("[GHL tier used: 3 — ")

    def test_create_api_exists_stays_false(self):
        # W3 documents READS only; the create flag must not move.
        for obj in ("funnel", "website", "page"):
            assert router.route(obj).create_api_exists is False

    def test_write_rails_unchanged(self):
        assert router.route("funnel").rail_names() == [
            router.Rail.REST_IN_BROWSER, router.Rail.BROWSER, router.Rail.VERCEL_EMBED,
        ]
        assert router.route("page").rail_names() == router.route("funnel").rail_names()

    def test_no_read_surface_invented_for_other_objects(self):
        assert router.read_route("tag") == []
        assert router.read_route("media") == []

    def test_matrix_serializes_read_rails(self):
        md = router.matrix_as_dict()
        assert len(md["objects"]["funnel"]["read_rails"]) == 1
        assert md["objects"]["tag"]["read_rails"] == []


# ---------------------------------------------------------------------------
# Step 6: probe declaration consistency (surface 3; NQ1/NQ5)
# ---------------------------------------------------------------------------
class TestProbeDeclarationConsistency:
    def test_declaration_data_unchanged_and_honestly_labeled(self):
        decl = capability_probe._DECLARED_API_OPERATIONS
        assert decl["verification"] == "declared-not-live-proven"
        public = {op["operation"]: op for op in decl["public"]}
        assert public["funnels.list"] == {
            "operation": "funnels.list", "method": "GET",
            "path": "/funnels/funnel/list", "kind": "read",
        }
        assert public["funnels.page.list"] == {
            "operation": "funnels.page.list", "method": "GET",
            "path": "/funnels/page", "kind": "read",
        }
        internal = {op["operation"]: op for op in decl["internal"]}
        assert internal["spa.funnels.page.list"]["path"] == "/funnels/page/list"


# ---------------------------------------------------------------------------
# Step 5: stale-claim corrections + protected claims + version pair
# ---------------------------------------------------------------------------
class TestStaleClaimCorrections:
    def test_inventory_docstring_no_longer_claims_no_funnels_endpoint(self):
        doc = inv.__doc__ or ""
        assert "no Funnels endpoint exists there at all" not in doc
        assert "no default live implementation" not in doc
        assert "ghl_funnels_read" in doc  # the wired public reader is named

    def test_skill_md_one_live_gap_block_is_corrected(self):
        text = open(os.path.join(_SKILL_ROOT, "SKILL.md"), encoding="utf-8").read()
        assert "THE ONE LIVE GAP THIS UNIT SHIPS WITHOUT A WIRED ROUTE" not in text
        assert "ghl_funnels_read" in text

    def test_version_pair_untouched(self):
        version = open(
            os.path.join(_SKILL_ROOT, "skill-version.txt"), encoding="utf-8"
        ).read().strip()
        assert version == "v27.1.39"

    def test_protected_build_claim_untouched(self):
        text = open(os.path.join(_TOOLS, "seed-ghl-auth.py"), encoding="utf-8").read()
        assert "has NO public or internal API for building Funnels" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
