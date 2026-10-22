#!/usr/bin/env python3
"""WF-E (P7 / C8) — route + journey regression for the canonical verifier.

Owner: WF-E test lane (DeepSeek 1017). Scope is TEST FIXTURES ONLY — this file
never edits the verifier seam or the manifest contract; it asserts them.

What it proves (checklist C8, plan §11.1 + §14.2 B11):

  C8a  ``ghl_verify.py`` stays the sole ``overall_pass`` writer. Supplementary
       journey/recipe evidence folds into the EXISTING forced-fail channel and
       can only FAIL a page — never pass one, never clear a render error.
  C8b  Page and branch lists are read from the APPROVED MANIFESTS
       (``49-signature-funnel/structure/funnel_structure.json`` funnel_matrix +
       ``structure/page_types.json``), never a hardcoded seven-page assumption.
       A 3-, 5- and 7-step funnel each verify their own manifest's page set.
  C8c  B11 — a broken render FAILS even when the local marker / stored bytes
       contain the marker (marker_in_rendered_dom True is not a pass on its own).
  C8d  Desktop/mobile render identity: both manifest viewports are planned per
       manifest page, bound to the same step/page_id, with no drift.
  C8e  CTA navigation, no-pitch and wrong-order journey failures each force
       ``PASS: False`` and a ``failed`` summary.
  C8f  ZERO LLM requests and ZERO browser sessions during mock-mode browser
       actions (B18 ``llm_calls_during_recipe == 0``).

Synthetic/offline only: no network, no real GHL, no client identifiers. Every
"render" is an in-memory fetcher stub, exactly as the existing
``06-ghl-install-pages/tests/test_ghl_verify.py`` does.

Run:  python3 -m pytest tests/test_wf_e_verifier_regression.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "06-ghl-install-pages" / "tools"
SF = ROOT / "49-signature-funnel"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ghl_verify as gv  # noqa: E402  (the canonical verifier under test)

MATRIX_PATH = SF / "structure" / "funnel_structure.json"
PAGE_TYPES_PATH = SF / "structure" / "page_types.json"

MARKER = "WF-E-MARKER-RUNID"
BASE_URL = "https://preview.example.test/preview/PAGEIDwfefake"

# Rendered DOM that is genuinely healthy: well over the 400-char visible-text
# floor, and carries the marker in the RENDERED bytes (not just stored bytes).
HEALTHY_BODY = (
    "<html><body><h1>Approved page</h1><p>"
    + ("This approved paragraph renders in the real DOM. " * 12)
    + "</p></body></html>"
)


# ── manifest helpers (NOT hardcoded page lists) ──────────────────────────────

def _matrix() -> dict:
    """The approved funnel_matrix page lists: {"3": [...], "5": [...], "7": [...]}.

    The manifest block also carries a non-list ``rule`` string; only the numeric
    size keys are page lists, so they are selected structurally (a list value),
    never by naming a size.
    """
    raw = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["funnel_matrix"]
    return {k: v for k, v in raw.items() if isinstance(v, list)}


def _matrix_slugs() -> list[str]:
    """Every page slug any approved funnel size can contain, deduped + ordered."""
    seen: list[str] = []
    for size in sorted(_matrix(), key=int):
        for slug in _matrix()[size]:
            if slug not in seen:
                seen.append(slug)
    return seen


def _page_types_by_slug() -> dict[str, str]:
    """matrix_slug -> page_key, read from the approved page_types manifest."""
    pages = json.loads(PAGE_TYPES_PATH.read_text(encoding="utf-8"))["pages"]
    return {
        p["matrix_slug"]: key
        for key, p in pages.items()
        if isinstance(p, dict) and p.get("matrix_slug")
    }


def _approved_pages(size: int) -> list[dict]:
    """Build the verifier page list for one funnel size FROM THE MANIFEST.

    One page dict per matrix entry, in manifest order. Nothing here names a
    page: if the approved matrix changes, this list changes with it.
    """
    slugs = _matrix()[str(size)]
    by_slug = _page_types_by_slug()
    out = []
    for i, slug in enumerate(slugs):
        out.append({
            "step": slug,
            "page_key": by_slug.get(slug, slug),
            "page_id": f"PAGEID-{size}-{i}",
            "preview_url": f"{BASE_URL}/{size}/{slug}",
            "marker": MARKER,
        })
    return out


def _approved_order(size: int) -> list[str]:
    """The approved progression order — the manifest's own order, verbatim."""
    return list(_matrix()[str(size)])


# ── render stubs (synthetic, offline) ────────────────────────────────────────

def _healthy(url: str = BASE_URL, marker: str = MARKER) -> dict:
    return {
        "ok": True, "http": 200, "url": url,
        "marker_found": True, "marker_in_rendered_dom": True,
        "render_errors": [],
        "dom": HEALTHY_BODY,
        "visible_text_len": 600,
    }


def _broken_render_marker_stored(url: str = BASE_URL, marker: str = MARKER) -> dict:
    """B11: the marker IS in the stored/stub bytes, but the render is broken.

    This is the exact shape the plan forbids passing: HTTP 200 and
    ``marker_found`` True (stored bytes carry the marker) while the real render
    is a crash/blank — carried here as the render_check error channel.
    """
    return {
        "ok": False, "http": 200, "url": url,
        "marker_found": True, "marker_in_rendered_dom": True,
        "render_errors": [
            "render_check: pageerror TypeError: theme object missing "
            "(page crashed before content)",
        ],
        "dom": "<html><body><p>" + MARKER + "</p></body></html>",
        "visible_text_len": len(MARKER),
    }


def _fetcher(url_map: dict[str, dict] | None = None, default: dict | None = None):
    """URL-keyed stub fetcher. An unmapped URL is a hard FAIL, never a pass."""
    def _f(url: str, marker: str) -> dict:
        if url_map and url in url_map:
            return dict(url_map[url])
        if default is not None:
            return dict(default)
        return {"ok": False, "http": None, "marker_found": False,
                "render_errors": ["unmapped url (fail-closed)"], "url": url}
    return _f


def _group(source: str, ref_id: str, ok: bool, errors=None) -> dict:
    """The seam's documented group builder (contract from the ownership map)."""
    return gv.supplementary_evidence(source, ref_id, ok, errors)


# ── C8b: manifest-driven page sets (no hardcoded seven) ──────────────────────

class TestManifestDrivenPages:
    def test_every_matrix_size_verifies_its_own_manifest_page_set(self, tmp_path):
        """3/5/7 each reduce to exactly the pages the manifest names."""
        sizes = sorted(_matrix(), key=int)
        assert sizes == ["3", "5", "7"], f"approved funnel sizes changed: {sizes}"
        counts = {}
        for size in sizes:
            pages = _approved_pages(int(size))
            run_dir = tmp_path / f"run-{size}"
            out = gv.verify_all(
                str(run_dir), pages,
                live=False, fetcher=_fetcher(default=_healthy()),
            )
            summary = out["summary"]
            counts[int(size)] = summary["total"]
            assert summary["total"] == len(_matrix()[size])
            assert summary["passed"] == len(_matrix()[size])
            assert summary["overall_pass"] is True
            # the raw log names the manifest's pages, in manifest order
            assert [r["step"] for r in out["raw"]] == _approved_order(int(size))
        assert counts == {int(k): len(v) for k, v in _matrix().items()}
        assert len(set(counts.values())) == len(counts), (
            "sizes must not collapse to one page count (that would be the "
            "hardcoded-page-set failure this test exists to catch)"
        )

    def test_page_list_is_not_the_hardcoded_seven(self, tmp_path):
        """A 3-step funnel must not be padded or trimmed to seven pages."""
        pages = _approved_pages(3)
        assert len(pages) == 3
        out = gv.verify_all(
            str(tmp_path / "run3"), pages,
            live=False, fetcher=_fetcher(default=_healthy()),
        )
        assert out["summary"]["total"] == 3
        assert len(out["raw"]) == 3

    def test_every_matrix_slug_has_a_page_type_identity(self):
        """Branch/page identity is resolved from page_types.json, not invented."""
        by_slug = _page_types_by_slug()
        missing = [s for s in _matrix_slugs() if s not in by_slug]
        assert not missing, f"matrix slugs with no page_types identity: {missing}"

    def test_unknown_size_is_refused_not_guessed(self, tmp_path):
        """A size absent from the approved matrix must not silently verify."""
        with pytest.raises(KeyError):
            _approved_pages(9)
        assert "9" not in _matrix()


# ── C8c / B11: broken render fails even with the marker present ──────────────

class TestBrokenRenderNegative:
    def test_b11_broken_render_fails_with_marker_in_bytes(self, tmp_path):
        page = _approved_pages(3)[0]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_broken_render_marker_stored()),
        )
        # the marker IS present — that alone must never be a pass
        assert rec["marker_in_rendered_dom"] is True
        assert rec["marker_in_preview"] is True
        assert rec["http_code"] == 200
        # ...and the canonical verdict is still FAIL
        assert rec["PASS"] is False
        assert any("theme object missing" in e for e in rec["render_errors"])

    def test_b11_broken_render_fails_the_whole_summary(self, tmp_path):
        pages = _approved_pages(3)
        url_map = {p["preview_url"]: _healthy() for p in pages}
        url_map[pages[1]["preview_url"]] = _broken_render_marker_stored()
        out = gv.verify_all(
            str(tmp_path), pages, live=False,
            fetcher=_fetcher(url_map=url_map),
        )
        summary = out["summary"]
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert summary["overall_pass"] is False

    def test_clean_local_marker_with_empty_render_text_fails(self, tmp_path):
        """Marker-only DOM (blank page) is below the rendered-text floor."""
        page = _approved_pages(3)[0]
        blank = {
            "ok": False, "http": 200, "marker_found": True,
            "marker_in_rendered_dom": True,
            "render_errors": ["blank page: visible_text_len 12 < 400"],
            "dom": f"<html><body>{MARKER}</body></html>",
            "visible_text_len": 12,
        }
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=blank),
        )
        assert rec["PASS"] is False


# ── C8a: supplementary evidence is fail-only (one overall_pass writer) ───────

class TestSupplementaryIsFailOnly:
    def test_failing_group_forces_pass_false(self, tmp_path):
        page = dict(_approved_pages(3)[0])
        page["supplementary"] = [
            _group("playwright_journey", "cta-nav", False, ["CTA did not navigate"]),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False
        assert any("supplementary" in e and "cta-nav" in e
                   for e in rec["render_errors"])

    def test_passing_groups_never_change_a_failing_render(self, tmp_path):
        """A clean journey cannot rescue a broken render (B11 stays B11)."""
        page = dict(_approved_pages(3)[0])
        page["supplementary"] = [
            _group("playwright_journey", "cta-nav", True),
            _group("recipe", "native-state", True),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_broken_render_marker_stored()),
        )
        assert rec["PASS"] is False

    def test_supplementary_alone_never_writes_a_summary(self, tmp_path):
        """The seam adds no second overall_pass reducer and no second writer."""
        pages = _approved_pages(3)
        for p in pages:
            p["supplementary"] = [_group("playwright_journey", "journey", True)]
        out = gv.verify_all(
            str(tmp_path), pages, live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        summary = out["summary"]
        assert summary["writer"] == "ghl_verify.verify_all"
        assert summary["overall_pass"] is True
        # the documented single summary path is the only one written
        assert Path(out["summary_path"]).is_file()
        assert json.loads(Path(out["summary_path"]).read_text())["writer"] == \
            "ghl_verify.verify_all"

    def test_failing_group_is_never_swallowed_by_the_summary(self, tmp_path):
        pages = _approved_pages(3)
        pages[-1]["supplementary"] = [
            _group("playwright_journey", "no-pitch", False,
                   ["thank-you page pitched another offer"]),
        ]
        out = gv.verify_all(
            str(tmp_path), pages, live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert out["summary"]["overall_pass"] is False
        assert out["summary"]["failed"] == 1

    def test_empty_failure_detail_still_fails(self, tmp_path):
        page = dict(_approved_pages(3)[0])
        page["supplementary"] = [
            {"source": "recipe", "ref_id": "native-state", "ok": False, "errors": []},
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False
        assert any("no detail" in e or "failed" in e for e in rec["render_errors"])

    def test_malformed_group_fails_closed(self, tmp_path):
        page = dict(_approved_pages(3)[0])
        page["supplementary"] = ["not-a-dict"]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False
        assert any("malformed" in e for e in rec["render_errors"])


# ── C8d: desktop/mobile render identity ──────────────────────────────────────

class TestDesktopMobileIdentity:
    def test_both_viewports_planned_per_manifest_page(self, tmp_path, monkeypatch):
        """Screenshot plan covers every manifest page at desktop AND mobile."""
        import browser_manager
        import model_router
        monkeypatch.setattr(model_router, "select", lambda *a, **k: {})

        pages = _approved_pages(5)
        # The emitter refuses outside a session bracket (singleton gateway);
        # the plan itself is emit-only — no browser is launched.
        with browser_manager.browser_session("wf-e-fixture"):
            steps = gv.screenshot_plan(str(tmp_path), pages)
        shots = [s for s in steps if s.get("kind") == "screenshot"]
        doms = [s for s in steps if s.get("kind") == "dom"]

        viewport_names = sorted({s["viewport"] for s in shots})
        assert viewport_names == ["desktop", "mobile"]
        assert len(doms) == len(pages)
        assert len(shots) == len(pages) * len(viewport_names)

        # identity: same manifest step + same URL across both viewports
        for page in pages:
            mine = [s for s in shots if s["step"] == page["step"]]
            assert {s["viewport"] for s in mine} == {"desktop", "mobile"}
            for s in mine:
                assert page["preview_url"] in s["argv"]
                assert s["out"].endswith(f"{page['step']}-{s['viewport']}.png")

    def test_viewport_dimensions_are_distinct_and_named(self):
        dims = {(v["name"], v["width"], v["height"]) for v in gv.VIEWPORTS}
        assert dims == {("desktop", 1440, 900), ("mobile", 390, 844)}


# ── C8e: CTA navigation, no-pitch, wrong-order ───────────────────────────────

class TestJourneyAssertions:
    def test_cta_navigation_pass_keeps_page_green(self, tmp_path):
        order = _approved_order(5)
        page = dict(_approved_pages(5)[0])
        page["supplementary"] = [
            _group("playwright_journey", f"cta:{order[0]}->{order[1]}", True),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is True

    def test_cta_navigation_failure_fails_the_page(self, tmp_path):
        order = _approved_order(5)
        page = dict(_approved_pages(5)[0])
        page["supplementary"] = [
            _group("playwright_journey", f"cta:{order[0]}->{order[1]}", False,
                   [f"CTA landed on {order[2]!r}, expected {order[1]!r}"]),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False

    def test_wrong_order_failure_uses_the_manifest_order(self, tmp_path):
        """Wrong-order is detected against the manifest order, not a literal."""
        order = _approved_order(7)
        shuffled = list(reversed(order))
        observed = shuffled
        errors = [
            f"journey order {observed!r} != approved manifest order {order!r}"
        ]
        page = dict(_approved_pages(7)[-1])
        page["supplementary"] = [
            _group("playwright_journey", "order", False, errors),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False
        assert order != shuffled

    def test_no_pitch_failure_on_the_manifest_terminal_page(self, tmp_path):
        """The terminal page is the LAST manifest entry — derived, not named."""
        order = _approved_order(7)
        terminal = order[-1]
        page = dict(_approved_pages(7)[-1])
        assert page["step"] == terminal
        page["supplementary"] = [
            _group("playwright_journey", "no-pitch", False,
                   ["another offer CTA rendered on the terminal page"]),
        ]
        rec = gv.verify_page(
            page, run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is False

    def test_expected_native_state_fixture_pass_and_fail(self, tmp_path):
        """Native-state expectations are fixture data, asserted as evidence."""
        page = dict(_approved_pages(5)[-1])
        expected = {"purchase_state": "succeeded", "entitlement": "granted"}

        ok_page = dict(page)
        ok_page["supplementary"] = [
            _group("native_state", "expected-purchase", True),
        ]
        rec_ok = gv.verify_page(
            ok_page, run_dir=str(tmp_path / "ok"), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec_ok["PASS"] is True

        bad_page = dict(page)
        bad_page["supplementary"] = [
            _group("native_state", "expected-purchase", False,
                   [f"observed {expected} but native state was 'pending'"]),
        ]
        rec_bad = gv.verify_page(
            bad_page, run_dir=str(tmp_path / "bad"), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec_bad["PASS"] is False

    def test_full_journey_over_every_manifest_page(self, tmp_path):
        """One assertion per manifest page; a single failing edge fails the run."""
        for size in (3, 5, 7):
            pages = _approved_pages(size)
            order = _approved_order(size)
            for i, p in enumerate(pages):
                ref = f"{order[i]}->{order[i + 1]}" if i + 1 < len(order) \
                    else "no-pitch"
                p["supplementary"] = [_group("playwright_journey", ref, True)]
            out = gv.verify_all(
                str(tmp_path / f"ok-{size}"), pages, live=False,
                fetcher=_fetcher(default=_healthy()),
            )
            assert out["summary"]["overall_pass"] is True, size

            pages[0]["supplementary"] = [
                _group("playwright_journey", f"{order[0]}->{order[1]}", False,
                       ["CTA dead: no navigation event"]),
            ]
            bad = gv.verify_all(
                str(tmp_path / f"bad-{size}"), pages, live=False,
                fetcher=_fetcher(default=_healthy()),
            )
            assert bad["summary"]["overall_pass"] is False, size
            assert bad["summary"]["failed"] == 1, size


# ── C8f: zero LLM + zero browser during mock browser actions ─────────────────

class TestZeroLlmDuringBrowserActions:
    def test_mock_verify_makes_no_llm_call_and_opens_no_browser(
            self, tmp_path, monkeypatch):
        import browser_manager
        import ghl_builder
        import model_router

        def _boom(*a, **k):
            raise AssertionError(
                "FORBIDDEN during browser actions: model/browser call attempted "
                "(B18 llm_calls_during_recipe must be 0)"
            )

        monkeypatch.setattr(model_router, "select", _boom)
        monkeypatch.setattr(ghl_builder, "render_check", _boom)
        monkeypatch.setattr(browser_manager, "browser_session", _boom)

        pages = _approved_pages(5)
        for p in pages:
            p["supplementary"] = [
                _group("playwright_journey", "journey", True),
                _group("recipe", "native-state", True),
            ]
        out = gv.verify_all(
            str(tmp_path), pages, live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert out["summary"]["overall_pass"] is True
        assert out["summary"]["total"] == len(pages)

    def test_single_page_mock_also_makes_no_llm_call(self, tmp_path, monkeypatch):
        import model_router

        calls: list = []
        monkeypatch.setattr(model_router, "select",
                            lambda *a, **k: calls.append(a) or {})

        rec = gv.verify_page(
            _approved_pages(3)[0], run_dir=str(tmp_path), live=False,
            fetcher=_fetcher(default=_healthy()),
        )
        assert rec["PASS"] is True
        assert calls == [], f"llm_calls_during_recipe must be 0, saw {len(calls)}"
