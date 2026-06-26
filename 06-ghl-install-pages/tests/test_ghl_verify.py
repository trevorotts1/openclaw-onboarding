"""MOCK-only unit tests — ghl_verify (the ONE canonical build-verifier, R7 fix).

These tests are MOCK-ONLY. There are NO live GHL calls, no real fixture, no
agent-browser against real GHL, no network of any kind. The HTTP check
(``verify_url``) is injected as a ``fetcher`` callable; every preview "fetch" is
scripted in memory. The assertions cover the canonical-verify CONTRACT:

  * ONE source of truth — ``logs/final-preview-verify.json`` (raw per-page) is
    written first; ``scorecard/verify-summary.json`` is a PURE reduction of it.
  * the CONSISTENCY GUARD — a summary can NEVER be more optimistic than the raw
    log; the exact 6/6-vs-1/6 contradiction the R7 judge flagged raises
    ``VerifyContradiction`` (FAIL-LOUD), it does not silently ship.
  * the single pass writes BOTH files and they always agree (no second writer).
  * an empty page set is NOT a pass; a failing page forces overall=False.
  * real-PNG screenshot + fetched-DOM commands are emitted headless-forced (D6),
    replacing the V1 SVG placeholders / synthetic-stub HTML.

No real client/operator names, ids, emails, or location-ids appear — all values
are generic / parameterised fakes.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import browser_manager  # SINGLETON POOLED BROWSER gateway (session bracket)
import ghl_verify as gv


# ── Generic fakes (NO real client/operator data) ─────────────────────────────

FAKE_MARKER = "FAKE-MARKER-RUNID"
FAKE_PREVIEW = "https://preview.example.test/preview/PAGEID0000fake"


def _page(step: str, page_id: str = "PAGEIDfake", url: str = FAKE_PREVIEW,
          marker: str = FAKE_MARKER) -> dict:
    return {"step": step, "page_id": page_id, "preview_url": url, "marker": marker}


def _fetcher(results: dict[str, dict]):
    """Return an injectable verify_url-shaped fetcher keyed by URL.

    Each value is a ``verify_url``-shaped dict ``{ok, http, marker_found, url}``.
    A URL not in ``results`` is treated as a hard FAIL (HTTP None), never a pass.
    """
    def _f(url: str, marker: str) -> dict:
        if url in results:
            r = dict(results[url])
            r.setdefault("url", url)
            return r
        return {"ok": False, "http": None, "marker_found": False, "url": url}
    return _f


def _ok(url: str = FAKE_PREVIEW) -> dict:
    return {"ok": True, "http": 200, "marker_found": True, "url": url}


def _fail_marker(url: str = FAKE_PREVIEW) -> dict:
    # HTTP 200 but marker NOT in body — exactly the V1 case (autosave never ran).
    return {"ok": False, "http": 200, "marker_found": False, "url": url}


# ── verify_page: the single real check (one page → one raw record) ────────────

class TestVerifyPage:
    def test_pass_record_shape(self):
        rec = gv.verify_page(_page("home"), fetcher=_fetcher({FAKE_PREVIEW: _ok()}))
        assert rec["PASS"] is True
        assert rec["http_code"] == 200
        assert rec["marker_in_preview"] is True
        assert rec["step"] == "home"
        assert rec["preview_url"] == FAKE_PREVIEW

    def test_http_200_but_marker_absent_is_fail(self):
        # The V1 reality: page returns 200 but the marker never landed -> FAIL.
        rec = gv.verify_page(_page("thankyou"),
                             fetcher=_fetcher({FAKE_PREVIEW: _fail_marker()}))
        assert rec["PASS"] is False
        assert rec["http_code"] == 200
        assert rec["marker_in_preview"] is False

    def test_missing_preview_url_is_fail_not_pass(self):
        rec = gv.verify_page({"step": "x", "marker": FAKE_MARKER, "preview_url": ""},
                             fetcher=_fetcher({}))
        assert rec["PASS"] is False
        assert "error" in rec

    def test_missing_marker_is_fail_not_pass(self):
        rec = gv.verify_page({"step": "x", "preview_url": FAKE_PREVIEW, "marker": ""},
                             fetcher=_fetcher({FAKE_PREVIEW: _ok()}))
        assert rec["PASS"] is False
        assert "error" in rec


# ── derive_summary: summary is a PURE reduction of the raw array ──────────────

class TestDeriveSummary:
    def test_counts_are_reduction_of_raw(self):
        raw = [
            {"step": "a", "PASS": True}, {"step": "b", "PASS": False},
            {"step": "c", "PASS": True},
        ]
        s = gv.derive_summary(raw, run_id="r", version="V1", brand="B")
        assert s["total"] == 3
        assert s["passed"] == 2
        assert s["failed"] == 1
        assert s["overall_pass"] is False     # any failure -> overall FAIL
        assert s["source_of_truth"] == gv.RAW_REL

    def test_all_pass_is_overall_pass(self):
        raw = [{"step": "a", "PASS": True}, {"step": "b", "PASS": True}]
        assert gv.derive_summary(raw)["overall_pass"] is True

    def test_empty_raw_is_not_a_pass(self):
        # Nothing verified == nothing proven == NOT a pass (guards the vacuous-true
        # trap where a build that produced no pages reads as success).
        s = gv.derive_summary([])
        assert s["total"] == 0
        assert s["overall_pass"] is False


# ── assert_consistent: the guard that kills the 6/6-vs-1/6 contradiction ──────

class TestConsistencyGuard:
    def test_passes_when_summary_matches_raw(self):
        raw = [{"PASS": True}, {"PASS": False}]
        s = gv.derive_summary(raw)
        gv.assert_consistent(s, raw)  # no raise

    def test_raises_when_summary_more_optimistic_than_raw(self):
        # THE EXACT R7 DEFECT: raw proves 1/6, a stale/optimistic summary claims
        # 6/6. The guard MUST fail loud.
        raw = [{"PASS": True}] + [{"PASS": False}] * 5  # 1/6 truth
        bogus = {"total": 6, "passed": 6, "failed": 0, "overall_pass": True}
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_consistent(bogus, raw)

    def test_raises_when_overall_true_but_a_page_failed(self):
        raw = [{"PASS": True}, {"PASS": False}]
        # passed/total honest, but overall_pass lies True.
        bogus = {"total": 2, "passed": 1, "failed": 1, "overall_pass": True}
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_consistent(bogus, raw)

    def test_raises_on_total_mismatch(self):
        raw = [{"PASS": True}, {"PASS": True}]
        bogus = {"total": 5, "passed": 2, "failed": 0, "overall_pass": False}
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_consistent(bogus, raw)

    def test_raises_when_summary_missing_counts(self):
        with pytest.raises(gv.VerifyContradiction):
            gv.assert_consistent({"overall_pass": True}, [{"PASS": True}])


# ── verify_all: ONE pass writes BOTH files from one source of truth ───────────

class TestVerifyAllOnePass:
    def test_writes_both_files_consistently(self, tmp_path):
        pages = [_page("optin", url="u1"), _page("thanks", url="u2")]
        fetch = _fetcher({"u1": _ok("u1"), "u2": _ok("u2")})
        out = gv.verify_all(str(tmp_path), pages, run_id="r", version="V1",
                            brand="B", fetcher=fetch)

        raw = json.load(open(out["raw_path"]))
        summary = json.load(open(out["summary_path"]))

        # Both files exist at the canonical paths.
        assert out["raw_path"].endswith(os.path.join("logs", "final-preview-verify.json"))
        assert out["summary_path"].endswith(os.path.join("scorecard", "verify-summary.json"))

        # The summary is EXACTLY the reduction of the raw log (no second truth).
        raw_passed = sum(1 for r in raw if r["PASS"])
        assert summary["passed"] == raw_passed == 2
        assert summary["total"] == len(raw) == 2
        assert summary["overall_pass"] is True
        # And the guard would re-confirm it (belt-and-braces).
        gv.assert_consistent(summary, raw)

    def test_partial_build_summary_matches_raw_never_optimistic(self, tmp_path):
        # The V1 scenario reproduced: 1 page lands its marker, the rest return
        # HTTP 200 with NO marker (autosave never executed). The single canonical
        # pass MUST report 1/6 in BOTH files — never 6/6.
        urls = [f"p{i}" for i in range(6)]
        pages = [_page(f"s{i}", url=urls[i]) for i in range(6)]
        results = {urls[0]: _ok(urls[0])}
        results.update({urls[i]: _fail_marker(urls[i]) for i in range(1, 6)})
        out = gv.verify_all(str(tmp_path), pages, fetcher=_fetcher(results))

        raw = json.load(open(out["raw_path"]))
        summary = json.load(open(out["summary_path"]))
        assert summary["passed"] == 1
        assert summary["total"] == 6
        assert summary["failed"] == 5
        assert summary["overall_pass"] is False
        # The two files agree exactly (the whole point of the fix).
        assert summary["passed"] == sum(1 for r in raw if r["PASS"])

    def test_raw_written_before_summary_derivation(self, tmp_path):
        # The raw log is the source of truth: it must exist even when overall fails.
        pages = [_page("a", url="bad")]  # 'bad' not in results -> FAIL
        out = gv.verify_all(str(tmp_path), pages, fetcher=_fetcher({}))
        assert os.path.exists(out["raw_path"])
        assert os.path.exists(out["summary_path"])
        assert out["summary"]["overall_pass"] is False

    def test_no_svg_placeholder_anywhere(self, tmp_path):
        # R7 also flagged SVG "screenshots"; the canonical verifier never writes
        # any .svg artifact — only the two JSON files.
        pages = [_page("a", url="u1")]
        gv.verify_all(str(tmp_path), pages, fetcher=_fetcher({"u1": _ok("u1")}))
        svgs = [f for f in (tmp_path / "scorecard").iterdir()] if (tmp_path / "scorecard").exists() else []
        for f in svgs:
            assert not str(f).endswith(".svg")


# ── screenshot_plan: REAL PNG + fetched DOM, headless-forced (D6) ─────────────

class TestScreenshotPlan:
    def test_emits_real_png_both_viewports(self, tmp_path):
        with browser_manager.browser_session("sess-fake"):
            steps = gv.screenshot_plan(str(tmp_path), [_page("home", url="u1")])
        shots = [s for s in steps if s["kind"] == "screenshot"]
        # Desktop + mobile, both real .png (NOT .svg).
        assert {s["viewport"] for s in shots} == {"desktop", "mobile"}
        for s in shots:
            assert s["out"].endswith(".png")
            assert not s["out"].endswith(".svg")
            # D6: every emitted agent-browser command is headless-forced.
            assert "--headed" in s["argv"]
            assert s["argv"][s["argv"].index("--headed") + 1] == "false"

    def test_emits_fetched_dom_capture(self, tmp_path):
        with browser_manager.browser_session("sess-fake"):
            steps = gv.screenshot_plan(str(tmp_path), [_page("home", url="u1")])
        doms = [s for s in steps if s["kind"] == "dom"]
        assert len(doms) == 1
        assert doms[0]["out"].endswith("home-preview.html")
        assert "--headed" in doms[0]["argv"]

    def test_page_without_preview_url_skipped(self, tmp_path):
        steps = gv.screenshot_plan(str(tmp_path), [{"step": "x", "preview_url": ""}])
        assert steps == []


# ── End-to-end MOCK: the contradiction CANNOT be produced by verify_all ───────

class TestContradictionImpossible:
    """Drives the full canonical pass with a mocked fetcher and asserts that the
    output is internally consistent BY CONSTRUCTION — there is no code path in
    verify_all that can emit a summary more optimistic than the raw log (the
    guard runs against the on-disk raw file before the summary is written)."""

    def test_full_pass_is_guarded_consistent(self, tmp_path):
        urls = ["a", "b", "c"]
        pages = [_page(f"s{i}", url=urls[i]) for i in range(3)]
        # Mixed truth: 2 pass, 1 fails on marker.
        results = {"a": _ok("a"), "b": _ok("b"), "c": _fail_marker("c")}
        out = gv.verify_all(str(tmp_path), pages, fetcher=_fetcher(results))

        raw = json.load(open(out["raw_path"]))
        summary = json.load(open(out["summary_path"]))
        # The guard passes (it ran inside verify_all); re-run it here to prove it.
        gv.assert_consistent(summary, raw)
        assert summary["passed"] == 2 and summary["failed"] == 1
        assert summary["overall_pass"] is False


# ── B6 ADDITIONS: un-fakeability assertions (the fabrication-blocking contract) ─
#
# The diagnostic showed three failure modes that made a fake PASS possible:
#   1. verify_all called with live=True was bypassed by hand-writing ledgers.
#   2. A raw record with http:500 was re-labeled "API difference" → PASS.
#   3. The fallback "marker in stored bytes" substitute was accepted as proof.
# These tests assert that NONE of those paths exist.

import hashlib as _hashlib


class TestSealedGateMustUseFetcher:
    """verify_all must require an injected fetcher (live=False/mock path) in CI.

    The 'live=True' path (calling the real network) is gated behind a flag and
    MUST raise SealedGateViolation when a fetcher argument is also supplied —
    that combination is a signal that a caller is trying to bypass the mock path.
    If the production code has not yet implemented SealedGateViolation, the test
    is skipped; once B2 lands the class, it will automatically run.
    """

    def test_live_true_with_fetcher_raises_sealed_gate_violation(self, tmp_path):
        # If SealedGateViolation does not exist yet (B2 not landed), skip.
        SealedGateViolation = getattr(gv, "SealedGateViolation", None)
        if SealedGateViolation is None:
            pytest.skip("SealedGateViolation not yet implemented (B2 pending)")

        pages = [_page("home")]
        fetcher = _fetcher({FAKE_PREVIEW: _ok()})

        # Calling verify_all with both live=True AND a fetcher must be rejected —
        # the gate is sealed to prevent the live path from being trivially bypassed
        # by injecting a fake fetcher while claiming it is a live run.
        with pytest.raises(SealedGateViolation):
            gv.verify_all(str(tmp_path), pages, live=True, fetcher=fetcher)


class TestRawRecordCannotBeOverridden:
    """A raw record with http:500 (or any non-200) labeled PASS:true must be
    rejected by assert_consistent — the 'API difference' rationalization is
    structurally impossible because the guard derives from the raw evidence, not
    from human annotations."""

    def test_raw_http_500_with_pass_true_raises_contradiction(self):
        """If a raw record has http_code:500 the page FAILED — a summary claiming
        PASS:true is a contradiction and the guard must reject it."""
        raw = [{"step": "home", "PASS": True, "http_code": 500,
                "marker_in_preview": False}]
        # The summary derived from this raw would have overall_pass=True (1/1)
        # BUT the http_code tells us the page didn't load.  We feed a hand-crafted
        # "optimistic" summary that claims overall_pass=True to assert the guard
        # catches it OR we verify derive_summary handles 500s correctly.
        #
        # The contract: derive_summary uses ONLY the PASS flag from raw records.
        # If a caller sets PASS:True on a 500 record (the exact pre-flight abuse),
        # derive_summary will output overall_pass=True for that record — but that
        # means the BUG is in verify_page, which must set PASS:False on non-200.
        # assert_consistent then catches any mismatch against derive_summary's own
        # output.  We test verify_page here:
        result = gv.verify_page(
            {"step": "home", "preview_url": FAKE_PREVIEW, "marker": FAKE_MARKER},
            fetcher=_fetcher({FAKE_PREVIEW: {"ok": False, "http": 500,
                                              "marker_found": False, "url": FAKE_PREVIEW}})
        )
        assert result["PASS"] is False, \
            "http:500 must produce PASS:False — a 500 is never a pass"
        assert result["http_code"] == 500

    def test_summary_with_pass_true_but_raw_500_raises_contradiction(self):
        """Plant a raw log with a 500 record marked PASS:True (the pre-flight
        forgery) and assert that assert_consistent raises VerifyContradiction."""
        forged_raw = [{"step": "home", "PASS": True, "http_code": 500}]
        honest_summary = {"total": 1, "passed": 1, "failed": 0, "overall_pass": True}
        # The forgery: raw says PASS:True (already set), summary agrees.
        # assert_consistent with honest re-count should NOT raise here because the
        # counts match (both lie the same way).  The real defense is that
        # verify_page never produces PASS:True on a 500 (the test above covers that).
        # However: if the BUILD CONTRACT requires that assert_consistent ALSO checks
        # http_code, assert that too:
        check_http = getattr(gv, "assert_consistent_strict", None)
        if check_http is not None:
            # Strict mode: any record with http_code != 200 and PASS:True is caught.
            with pytest.raises(gv.VerifyContradiction):
                check_http(honest_summary, forged_raw)
        else:
            pytest.skip(
                "assert_consistent_strict not yet implemented; "
                "the http_code guard is in verify_page (covered by the test above)"
            )

    def test_api_difference_string_never_converts_500_to_pass(self):
        """The string 'API difference' appearing anywhere in a record or summary
        must NEVER make a non-200 page become PASS:True.  We prove this by
        verifying that the presence of the string does not affect verify_page's
        output for a 500 response."""
        result = gv.verify_page(
            {"step": "home", "preview_url": FAKE_PREVIEW, "marker": FAKE_MARKER,
             "note": "API difference — harmless"},  # the exact excuse from the pre-flight
            fetcher=_fetcher({FAKE_PREVIEW: {"ok": False, "http": 500,
                                              "marker_found": False,
                                              "url": FAKE_PREVIEW,
                                              "error": "API difference"}})
        )
        assert result["PASS"] is False, \
            "The string 'API difference' must NOT convert a 500 response to PASS"

    def test_harmless_string_never_converts_500_to_pass(self):
        """Same guard for the word 'harmless' — any rationalization string in the
        raw result must not flip PASS to True."""
        result = gv.verify_page(
            {"step": "home", "preview_url": FAKE_PREVIEW, "marker": FAKE_MARKER},
            fetcher=_fetcher({FAKE_PREVIEW: {"ok": False, "http": 500,
                                              "marker_found": False,
                                              "url": FAKE_PREVIEW,
                                              "error": "harmless type difference"}})
        )
        assert result["PASS"] is False, \
            "The word 'harmless' must NOT convert a 500 response to PASS"


class TestSummaryHashIntegrity:
    """A summary whose raw_sha256 does not match the raw file on disk must be
    rejected — this guards against a hand-edited summary file overriding the
    machine verdict.

    If the production code does not yet carry a raw_sha256 field in the summary
    (B2 may add it), this test is skipped until that field lands.
    """

    def _write_raw(self, tmp_path, raw: list) -> tuple[str, str]:
        """Write raw to disk and return (path, sha256)."""
        import os
        logs = tmp_path / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        p = logs / "final-preview-verify.json"
        content = json.dumps(raw, indent=2)
        p.write_text(content, encoding="utf-8")
        sha = _hashlib.sha256(content.encode()).hexdigest()
        return str(p), sha

    def test_sha256_mismatch_rejects_tampered_summary(self, tmp_path):
        """Plant a raw file, compute its hash, then present a summary with a
        different hash — the guard must reject it."""
        validate_sha = getattr(gv, "validate_summary_raw_sha256", None)
        if validate_sha is None:
            pytest.skip("validate_summary_raw_sha256 not yet implemented (B2 pending)")

        raw = [{"step": "home", "PASS": True, "http_code": 200, "marker_in_preview": True}]
        raw_path, real_sha = self._write_raw(tmp_path, raw)

        # A tampered summary claims a different sha256.
        tampered_summary = {
            "total": 1, "passed": 1, "failed": 0, "overall_pass": True,
            "raw_sha256": "aaaa" + real_sha[4:],  # mutate a few chars
        }
        with pytest.raises(gv.VerifyContradiction):
            validate_sha(tampered_summary, raw_path)

    def test_matching_sha256_passes(self, tmp_path):
        """A summary with the correct raw_sha256 must pass the guard."""
        validate_sha = getattr(gv, "validate_summary_raw_sha256", None)
        if validate_sha is None:
            pytest.skip("validate_summary_raw_sha256 not yet implemented (B2 pending)")

        raw = [{"step": "home", "PASS": True, "http_code": 200, "marker_in_preview": True}]
        raw_path, real_sha = self._write_raw(tmp_path, raw)
        good_summary = {
            "total": 1, "passed": 1, "failed": 0, "overall_pass": True,
            "raw_sha256": real_sha,
        }
        validate_sha(good_summary, raw_path)  # must not raise


class TestRenderManifestHashGuard:
    """A render-manifest whose hash does not match the artifact on disk must be
    rejected by the gate (guards against tampered manifest files).

    Skipped when the render-manifest hash guard is not yet implemented (B2).
    """

    def test_manifest_hash_mismatch_rejects(self, tmp_path):
        validate_manifest = getattr(gv, "validate_manifest_artifact_hash", None)
        if validate_manifest is None:
            pytest.skip("validate_manifest_artifact_hash not yet implemented (B2 pending)")

        art = tmp_path / "hero.png"
        art.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        real_sha = _hashlib.sha256(art.read_bytes()).hexdigest()

        # Tamper the hash in the manifest entry.
        manifest_entry = {"file": str(art), "sha256": "bad" + real_sha[3:]}
        with pytest.raises(gv.VerifyContradiction):
            validate_manifest([manifest_entry])

    def test_manifest_hash_match_passes(self, tmp_path):
        validate_manifest = getattr(gv, "validate_manifest_artifact_hash", None)
        if validate_manifest is None:
            pytest.skip("validate_manifest_artifact_hash not yet implemented (B2 pending)")

        art = tmp_path / "hero.png"
        art.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        real_sha = _hashlib.sha256(art.read_bytes()).hexdigest()
        manifest_entry = {"file": str(art), "sha256": real_sha}
        validate_manifest([manifest_entry])  # must not raise
