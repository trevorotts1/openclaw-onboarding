"""MOCK-only unit tests — U23/B-U9 decision-engine hardening, gap (2):
site-level routing aggregation.

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO Vercel deploy,
NO network of any kind. ``decide_site_method`` / ``decide_and_record_site``
are driven with crafted ``MethodDecision`` dicts (from real ``classify_page``
calls on fixture specs) and asserted against disk-written JSON.

Coverage:
  * decide_site_method is a no-op (overridden=False, method=None) when the
    GHL_SITE_LEVEL_ROUTING flag is unset -- the additive/flag-guarded revert
    doctrine (B-U9's own revert note: "revert = unset the flag").
  * A fixture site with 3-of-5 ADVANCED pages (60% >= 50% threshold), with
    the flag enabled, overrides the WHOLE SITE to VERCEL_EMBED.
  * A fixture site under the ratio threshold, with no nav-linked interactive
    core, does NOT override -- each page keeps its own method.
  * A nav-linked interactive core alone (ratio under threshold) still
    triggers the override.
  * decide_and_record_site writes routing/site-method-decision.json with the
    override reason, and the file's "method" field is null when there is no
    override.
  * Skill-44 widget routing is unaffected: pages carrying widget blocks are
    counted by their DIRECT/VERCEL_EMBED page method only; widgets are not a
    page "method" and never appear in advanced_page_count.
  * enabled=True/False passed explicitly overrides the env flag.
  * Zero pages / non-MethodDecision values raise MethodDecisionError --
    fail-closed, never silently picks a site method for invalid input.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_method_site_routing.py -v
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_method as m


SIMPLE_HTML = "<section><h1>Hello</h1><p>Copy text.</p></section>"


def _direct_decision() -> "m.MethodDecision":
    return m.classify_page({"html": SIMPLE_HTML})


def _advanced_decision() -> "m.MethodDecision":
    return m.classify_page({"html": SIMPLE_HTML, "complexity": "advanced"})


def _five_page_site(advanced_count: int) -> dict:
    """Build a 5-page fixture site with exactly ``advanced_count`` pages
    scoring VERCEL_EMBED and the rest DIRECT."""
    pages = {}
    for i in range(5):
        name = f"page{i}"
        pages[name] = _advanced_decision() if i < advanced_count else _direct_decision()
    return pages


# ── decide_site_method — flag-guarded no-op when disabled ─────────────────────

class TestSiteRoutingDisabledByDefault:
    def test_disabled_by_default_env(self):
        """With no GHL_SITE_LEVEL_ROUTING in the env, even a site that is
        100% ADVANCED must NOT be overridden -- per-page behavior is the
        default path (revert = unset the flag)."""
        pages = _five_page_site(5)
        decision = m.decide_site_method(pages, env={})
        assert decision.overridden is False
        assert decision.method is None
        assert decision.advanced_page_ratio == 1.0

    def test_disabled_reports_the_ratio_it_would_have_used(self):
        """Even disabled, the function reports the honest ratio/count picture
        -- a caller can see what WOULD happen without behavior changing."""
        pages = _five_page_site(3)
        decision = m.decide_site_method(pages, env={})
        assert decision.advanced_page_count == 3
        assert decision.total_page_count == 5
        assert abs(decision.advanced_page_ratio - 0.6) < 1e-9

    def test_site_level_routing_enabled_helper_false_by_default(self):
        assert m.site_level_routing_enabled(env={}) is False

    def test_site_level_routing_enabled_helper_true_when_flag_set(self):
        assert m.site_level_routing_enabled(env={"GHL_SITE_LEVEL_ROUTING": "1"}) is True

    def test_site_level_routing_enabled_helper_false_for_other_values(self):
        for v in ("0", "true", "yes", ""):
            assert m.site_level_routing_enabled(env={"GHL_SITE_LEVEL_ROUTING": v}) is False


# ── decide_site_method — ratio trigger (enabled) ───────────────────────────────

class TestSiteRoutingRatioTrigger:
    def test_three_of_five_advanced_overrides_whole_site(self):
        """3/5 = 60% >= 50% threshold -> the whole site routes VERCEL_EMBED."""
        pages = _five_page_site(3)
        decision = m.decide_site_method(pages, enabled=True)
        assert decision.overridden is True
        assert decision.method == m.PageMethod.VERCEL_EMBED
        assert decision.advanced_page_count == 3
        assert decision.total_page_count == 5

    def test_exactly_half_meets_threshold(self):
        """Threshold is >=, not >: exactly 50% must trigger."""
        pages = {"a": _advanced_decision(), "b": _direct_decision()}
        decision = m.decide_site_method(pages, enabled=True)
        assert decision.overridden is True

    def test_below_threshold_no_override(self):
        """1/5 = 20% < 50% threshold, no nav core -> no override."""
        pages = _five_page_site(1)
        decision = m.decide_site_method(pages, enabled=True)
        assert decision.overridden is False
        assert decision.method is None

    def test_zero_advanced_no_override(self):
        pages = _five_page_site(0)
        decision = m.decide_site_method(pages, enabled=True)
        assert decision.overridden is False
        assert decision.advanced_page_ratio == 0.0

    def test_custom_ratio_threshold_respected(self):
        """A custom (lower) threshold can trigger where the default would not."""
        pages = _five_page_site(1)  # 20%
        decision = m.decide_site_method(pages, enabled=True, ratio_threshold=0.2)
        assert decision.overridden is True


# ── decide_site_method — nav-linked interactive core trigger ──────────────────

class TestSiteRoutingNavCoreTrigger:
    def test_nav_core_alone_triggers_override_even_under_ratio(self):
        """0/5 ADVANCED (0% << 50%) but a declared nav-linked interactive
        core must still force the whole-site override."""
        pages = _five_page_site(0)
        decision = m.decide_site_method(
            pages, enabled=True, nav_linked_interactive_core=True
        )
        assert decision.overridden is True
        assert decision.method == m.PageMethod.VERCEL_EMBED
        assert "navigation-linked interactive core" in decision.reason

    def test_no_nav_core_and_under_ratio_no_override(self):
        pages = _five_page_site(0)
        decision = m.decide_site_method(
            pages, enabled=True, nav_linked_interactive_core=False
        )
        assert decision.overridden is False


# ── decide_site_method — per_page_methods audit + widgets unaffected ──────────

class TestSiteRoutingAuditTrailAndWidgets:
    def test_per_page_methods_snapshot_always_present(self):
        pages = _five_page_site(2)
        decision = m.decide_site_method(pages, env={})
        assert set(decision.per_page_methods.keys()) == set(pages.keys())
        assert decision.per_page_methods["page0"] == "vercel_embed"
        assert decision.per_page_methods["page4"] == "direct"

    def test_widget_blocks_do_not_count_toward_advanced_ratio(self):
        """A page carrying a form/calendar widget block is still classified
        DIRECT or VERCEL_EMBED by its OWN page-level signals; the widget
        itself is orthogonal (Skill-44 widget routing is unaffected)."""
        widget_page = m.classify_page({
            "html": SIMPLE_HTML,
            "form_blocks": [{"key": "contact_form"}],
        })
        assert widget_page.method == m.PageMethod.DIRECT
        assert len(widget_page.widgets) == 1

        pages = {"home": widget_page, "about": _direct_decision()}
        decision = m.decide_site_method(pages, enabled=True)
        assert decision.advanced_page_count == 0
        assert decision.overridden is False

    def test_reason_mentions_widget_unaffected_when_overridden(self):
        pages = _five_page_site(5)
        decision = m.decide_site_method(pages, enabled=True)
        assert "widget" in decision.reason.lower()


# ── decide_site_method — fail-closed on invalid input ──────────────────────────

class TestSiteRoutingFailClosed:
    def test_empty_dict_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.decide_site_method({}, enabled=True)

    def test_non_dict_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.decide_site_method(["not", "a", "dict"], enabled=True)

    def test_non_methoddecision_value_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.decide_site_method({"home": "not a MethodDecision"}, enabled=True)


# ── decide_and_record_site — writes site-method-decision.json ─────────────────

class TestDecideAndRecordSite:
    def test_writes_json_with_override_and_reason(self):
        with tempfile.TemporaryDirectory() as run_dir:
            pages = _five_page_site(4)
            decision = m.decide_and_record_site(pages, run_dir, enabled=True)
            record_path = pathlib.Path(run_dir) / "routing" / "site-method-decision.json"
            assert record_path.exists()
            data = json.loads(record_path.read_text())
            assert data["overridden"] is True
            assert data["method"] == "vercel_embed"
            assert isinstance(data["reason"], str) and len(data["reason"]) > 0
            assert data["advanced_page_count"] == decision.advanced_page_count

    def test_method_field_is_null_when_no_override(self):
        with tempfile.TemporaryDirectory() as run_dir:
            pages = _five_page_site(0)
            m.decide_and_record_site(pages, run_dir, enabled=True)
            record_path = pathlib.Path(run_dir) / "routing" / "site-method-decision.json"
            data = json.loads(record_path.read_text())
            assert data["method"] is None
            assert data["overridden"] is False

    def test_per_page_methods_written_to_disk(self):
        with tempfile.TemporaryDirectory() as run_dir:
            pages = _five_page_site(2)
            m.decide_and_record_site(pages, run_dir, enabled=True)
            record_path = pathlib.Path(run_dir) / "routing" / "site-method-decision.json"
            data = json.loads(record_path.read_text())
            assert data["per_page_methods"] == {
                name: dec.method.value for name, dec in pages.items()
            }

    def test_empty_run_dir_raises_value_error(self):
        with pytest.raises(ValueError):
            m.decide_and_record_site(_five_page_site(1), "")

    def test_does_not_collide_with_per_page_method_decision_files(self):
        """decide_and_record (per-page) and decide_and_record_site (site)
        must coexist in the same routing/ directory without clobbering each
        other's files."""
        with tempfile.TemporaryDirectory() as run_dir:
            for name, spec in (
                ("home", {"html": SIMPLE_HTML}),
                ("pricing", {"html": SIMPLE_HTML, "complexity": "advanced"}),
            ):
                m.decide_and_record(spec, name, run_dir)
            pages = {
                "home": m.classify_page({"html": SIMPLE_HTML}),
                "pricing": m.classify_page({"html": SIMPLE_HTML, "complexity": "advanced"}),
            }
            m.decide_and_record_site(pages, run_dir, enabled=True)

            routing_dir = pathlib.Path(run_dir) / "routing"
            names = sorted(p.name for p in routing_dir.glob("*.json"))
            assert "site-method-decision.json" in names
            assert "method-decision-home.json" in names
            assert "method-decision-pricing.json" in names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
