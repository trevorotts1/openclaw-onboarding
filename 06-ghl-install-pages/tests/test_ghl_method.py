"""MOCK-only unit tests — ghl_method (method-decision classifier + embed snippets).

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO Vercel deploy,
NO network of any kind.  ``classify_page`` is a pure function; the tests
drive it with crafted page-spec dicts and assert the output.

Coverage:
  * classify_page returns DIRECT for a simple HTML fragment (no hard signals).
  * classify_page returns VERCEL when a hard signal fires:
      - js_frameworks list non-empty (external framework).
      - html payload > MAX_DIRECT_BYTES.
      - complexity:'advanced' explicit override.
  * classify_page returns VERCEL when the weighted score >= ADVANCED_THRESHOLD
    (via third_party_js + interactive signals).
  * Unparseable / None input raises MethodDecisionError — fail-loud.
  * The method-decision JSON written by decide_and_record carries a non-empty
    'reason' string.
  * widget_embed_snippet for WidgetKind.FORM omits SRI (GoHighLevel rotates the
    script content; a pinned integrity= hash would always break the embed).

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_method.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import pathlib

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_method as m


# ── Helpers ───────────────────────────────────────────────────────────────────

def _method_val(decision) -> str:
    """Extract the string value from a PageMethod enum or plain string method field.

    ``PageMethod`` is a ``str``-based Enum but ``str(PageMethod.DIRECT)`` gives
    ``'PageMethod.DIRECT'`` (the repr), not ``'direct'``.  Use ``.value`` when
    the object has it, otherwise fall back to ``str()``.
    """
    meth = decision.method
    return meth.value if hasattr(meth, "value") else str(meth)


# ── Convenience helpers ───────────────────────────────────────────────────────

SIMPLE_HTML = "<section><h1>Hello</h1><p>Copy text.</p></section>"
FAKE_LOC = "LOCATIONfake0000"


def _spec(**kw) -> dict:
    """Build a minimal page spec with sensible defaults."""
    base = {"html": SIMPLE_HTML}
    base.update(kw)
    return base


# ── classify_page → DIRECT ────────────────────────────────────────────────────

class TestClassifyPageDirect:
    """Simple pages with no advanced signals must be classified DIRECT."""

    def test_simple_html_is_direct(self):
        decision = m.classify_page(_spec())
        assert _method_val(decision) == "direct", \
            f"simple HTML fragment must be DIRECT; got {decision.method!r}"

    def test_direct_decision_has_non_empty_reason(self):
        decision = m.classify_page(_spec())
        assert isinstance(decision.reason, str) and len(decision.reason.strip()) > 0, \
            "method decision must carry a non-empty 'reason' string"

    def test_direct_score_below_threshold(self):
        """A simple spec must score below ADVANCED_THRESHOLD."""
        decision = m.classify_page(_spec())
        assert decision.score < m.ADVANCED_THRESHOLD, \
            f"simple spec scored {decision.score} >= threshold {m.ADVANCED_THRESHOLD}"

    def test_decide_and_record_writes_json_with_non_empty_reason(self):
        """decide_and_record must write method-decision-<page>.json with a
        non-empty reason — the audit trail the CI guard checks."""
        with tempfile.TemporaryDirectory() as run_dir:
            decision = m.decide_and_record(_spec(html=SIMPLE_HTML), "home", run_dir)
            record_path = pathlib.Path(run_dir) / "routing" / "method-decision-home.json"
            assert record_path.exists(), \
                f"decide_and_record must write routing/method-decision-home.json; not found"
            data = json.loads(record_path.read_text())
            assert isinstance(data.get("reason"), str) and len(data["reason"].strip()) > 0, \
                "method-decision JSON must have a non-empty 'reason' key"
            assert data.get("method") in ("direct", "vercel", "vercel_embed"), \
                "method-decision JSON must have 'method' in {'direct', 'vercel', 'vercel_embed'}"
            # The decision object returned must match the file.
            assert _method_val(decision) == data["method"]

    def test_spec_with_only_html_has_no_signals(self):
        """A spec with only a simple html key must produce zero signals."""
        decision = m.classify_page(_spec())
        assert len(decision.signals) == 0, \
            f"simple spec must have no signals; got {decision.signals}"


# ── classify_page → VERCEL (hard signals) ────────────────────────────────────

class TestClassifyPageVercelHardSignals:
    """Hard signals (weight >= HARD_SIGNAL_WEIGHT) must force VERCEL."""

    def test_js_frameworks_forces_vercel(self):
        """A non-empty js_frameworks list is a hard signal (external framework)."""
        decision = m.classify_page(_spec(js_frameworks=["next"]))
        assert _method_val(decision) in ("vercel", "vercel_embed"), \
            "js_frameworks non-empty must force VERCEL"

    def test_react_in_js_frameworks_forces_vercel(self):
        decision = m.classify_page(_spec(js_frameworks=["react"]))
        assert _method_val(decision) in ("vercel", "vercel_embed")

    def test_explicit_complexity_advanced_forces_vercel(self):
        decision = m.classify_page(_spec(complexity="advanced"))
        assert _method_val(decision) in ("vercel", "vercel_embed"), \
            "complexity:'advanced' must force VERCEL"

    def test_explicit_complexity_advanced_case_insensitive(self):
        """Complexity check must be case-insensitive ('ADVANCED', 'Advanced', etc.)."""
        for val in ("ADVANCED", "Advanced", "advanced"):
            decision = m.classify_page(_spec(complexity=val))
            assert _method_val(decision) in ("vercel", "vercel_embed"), \
                f"complexity:{val!r} must force VERCEL"

    def test_payload_over_max_direct_bytes_forces_vercel(self):
        """A fragment larger than MAX_DIRECT_BYTES must force VERCEL."""
        big_html = "<p>" + ("A" * (m.MAX_DIRECT_BYTES + 1024)) + "</p>"
        decision = m.classify_page(_spec(html=big_html))
        assert _method_val(decision) in ("vercel", "vercel_embed"), \
            f"payload > MAX_DIRECT_BYTES ({m.MAX_DIRECT_BYTES}) must force VERCEL"

    def test_hard_signal_produces_hard_signal_in_signals(self):
        """A hard-signal decision must have at least one signal with weight >= 3."""
        decision = m.classify_page(_spec(complexity="advanced"))
        heavy = [s for s in decision.signals if s.get("weight", 0) >= 3]
        assert len(heavy) > 0, \
            "a hard-signal decision must have at least one signal with weight >= 3"


# ── classify_page → VERCEL (weighted score) ──────────────────────────────────

class TestClassifyPageWeightedScore:
    """Pages with no single hard signal but enough weighted signals = VERCEL."""

    def test_two_third_party_plus_interactive_reaches_threshold(self):
        """third_party_js > 1 (weight 2) + interactive (weight 2) = score 4 >= 3."""
        decision = m.classify_page(_spec(
            third_party_js=["gsap", "three.js"],
            interactive=["fetch"],
        ))
        assert decision.score >= m.ADVANCED_THRESHOLD, \
            f"expected score >= {m.ADVANCED_THRESHOLD}; got {decision.score}"
        assert _method_val(decision) in ("vercel", "vercel_embed"), \
            f"score {decision.score} >= threshold must be VERCEL"

    def test_single_third_party_lib_stays_direct(self):
        """Only one third-party lib: score < 2 (soft signal needs >1 lib)."""
        decision = m.classify_page(_spec(third_party_js=["jquery"]))
        # One lib doesn't trigger the soft signal — score should be 0.
        assert decision.score < m.ADVANCED_THRESHOLD, \
            f"one third-party lib should not reach threshold; score={decision.score}"
        assert _method_val(decision) == "direct"

    def test_interactive_fetch_alone_is_soft(self):
        """A single interactive:fetch signal scores 2 < threshold 3 = DIRECT."""
        decision = m.classify_page(_spec(interactive=["fetch"]))
        assert decision.score == 2, \
            f"interactive:fetch alone should score 2; got {decision.score}"
        assert _method_val(decision) == "direct", \
            "interactive:fetch alone (score 2) < threshold 3 must remain DIRECT"

    def test_interactive_websocket_alone_is_soft(self):
        decision = m.classify_page(_spec(interactive=["websocket"]))
        assert decision.score == 2
        assert _method_val(decision) == "direct"

    def test_css_fighting_plus_interactive_can_reach_threshold(self):
        """css_fighting important_storms (weight 1) + global_selectors (weight 1)
        + interactive (weight 2) = score 4 >= 3."""
        decision = m.classify_page(_spec(
            css_fighting={"important_storms": 5, "global_selectors": 3},
            interactive=["fetch"],
        ))
        assert decision.score >= m.ADVANCED_THRESHOLD
        assert _method_val(decision) in ("vercel", "vercel_embed")


# ── classify_page → MethodDecisionError (fail loud) ─────────────────────────

class TestClassifyPageFailLoud:
    """Bad input must raise MethodDecisionError — never silently default."""

    def test_none_input_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page(None)

    def test_non_dict_string_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page("not a dict")

    def test_non_dict_list_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page(["a", "b"])

    def test_empty_dict_raises(self):
        """An empty dict has no page information — must raise."""
        with pytest.raises(m.MethodDecisionError):
            m.classify_page({})

    def test_js_frameworks_non_list_raises(self):
        """js_frameworks must be a list; a string is rejected."""
        with pytest.raises(m.MethodDecisionError):
            m.classify_page(_spec(js_frameworks="react"))

    def test_css_fighting_non_dict_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page(_spec(css_fighting="lots of !important"))

    def test_html_content_non_str_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page({"html": 12345})


# ── widget_embed_snippet ──────────────────────────────────────────────────────

class TestWidgetEmbedSnippet:
    """widget_embed_snippet produces the GoHighLevel embed shape and must NOT
    include an SRI integrity= hash on the form_embed.js script tag."""

    def test_form_snippet_contains_form_object_id(self):
        snippet = m.widget_embed_snippet(m.WidgetKind.FORM, "FORM0001fake", FAKE_LOC)
        assert "FORM0001fake" in snippet, \
            "form snippet must include the form object id"

    def test_form_snippet_contains_form_widget_url(self):
        snippet = m.widget_embed_snippet(m.WidgetKind.FORM, "FORM0001fake", FAKE_LOC)
        # The widget host is link.msgsndr.com (verified from the production code).
        assert "widget/form/FORM0001fake" in snippet, \
            "form snippet must include the GoHighLevel form widget path"

    def test_form_snippet_omits_sri_integrity_hash(self):
        """GoHighLevel rotates the form_embed.js content so a pinned SRI hash
        would always break the embed.  The snippet must NOT include
        integrity='sha...' on the script tag.

        This is a deliberate design decision documented in the module docstring:
        DO NOT add SRI hashes to GoHighLevel's widget script tags."""
        snippet = m.widget_embed_snippet(m.WidgetKind.FORM, "FORM0001fake", FAKE_LOC)
        assert "integrity=" not in snippet, (
            "form widget script tag must NOT carry integrity= (SRI) — "
            "GoHighLevel rotates the script contents, making any pinned hash "
            "immediately invalid.  Omitting SRI is intentional (by design)."
        )

    def test_form_snippet_no_async_sri_crossorigin(self):
        """No crossorigin or SRI-related attributes."""
        snippet = m.widget_embed_snippet(m.WidgetKind.FORM, "FORM0001fake", FAKE_LOC)
        assert "crossorigin=" not in snippet, \
            "form snippet must not have crossorigin= (would pair with SRI)"

    def test_calendar_snippet_contains_calendar_id(self):
        snippet = m.widget_embed_snippet(m.WidgetKind.BOOKING, "CAL0001fake", FAKE_LOC)
        assert "CAL0001fake" in snippet, \
            "calendar snippet must include the calendar object id"

    def test_calendar_snippet_contains_booking_path(self):
        snippet = m.widget_embed_snippet(m.WidgetKind.BOOKING, "CAL0001fake", FAKE_LOC)
        assert "widget/booking/CAL0001fake" in snippet, \
            "calendar snippet must include the GoHighLevel booking widget path"

    def test_blank_object_id_raises(self):
        with pytest.raises(ValueError):
            m.widget_embed_snippet(m.WidgetKind.FORM, "", FAKE_LOC)

    def test_blank_location_id_raises(self):
        with pytest.raises(ValueError):
            m.widget_embed_snippet(m.WidgetKind.FORM, "FORM0001fake", "")

    def test_unknown_widget_kind_string_raises(self):
        """Passing a raw string instead of a WidgetKind must raise."""
        with pytest.raises((ValueError, TypeError, KeyError, Exception)):
            m.widget_embed_snippet("video", "OBJIDfake", FAKE_LOC)


# ── iframe_embed_snippet ──────────────────────────────────────────────────────

class TestIframeEmbedSnippet:
    """iframe_embed_snippet must produce a responsive 100%-wide iframe."""

    FAKE_VERCEL_URL = "https://skill6-fixture-abc123.vercel.app"

    def test_contains_src_with_url(self):
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL)
        assert f'src="{self.FAKE_VERCEL_URL}"' in snippet, \
            "iframe snippet must contain src with the Vercel URL"

    def test_is_iframe_tag(self):
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL)
        assert "<iframe" in snippet.lower(), \
            "iframe snippet must contain an <iframe> tag"

    def test_responsive_width_100_percent(self):
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL)
        assert "width:100%" in snippet or "width: 100%" in snippet, \
            "iframe must be responsive (width:100%)"

    def test_no_border(self):
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL)
        assert "border:0" in snippet or "border: 0" in snippet, \
            "iframe must have no border (border:0)"

    def test_blank_url_raises(self):
        with pytest.raises(ValueError):
            m.iframe_embed_snippet("")

    def test_whitespace_only_url_raises(self):
        with pytest.raises(ValueError):
            m.iframe_embed_snippet("   ")

    def test_custom_height_reflected(self):
        """The height_px parameter must appear in the snippet."""
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL, height_px=900)
        assert "900px" in snippet, \
            "custom height_px must appear in the iframe style"

    def test_no_doctype_no_html_tag(self):
        """The snippet is a FRAGMENT — it must not contain <!DOCTYPE> or <html>."""
        snippet = m.iframe_embed_snippet(self.FAKE_VERCEL_URL)
        assert "<!doctype" not in snippet.lower(), \
            "iframe snippet is a fragment and must not contain <!DOCTYPE>"
        assert "<html" not in snippet.lower(), \
            "iframe snippet is a fragment and must not contain <html>"


# ── MethodDecision dataclass contract ────────────────────────────────────────

class TestMethodDecisionShape:
    """The MethodDecision returned by classify_page must carry all expected fields."""

    def test_decision_has_method_field(self):
        d = m.classify_page(_spec())
        assert _method_val(d) in ("direct", "vercel", "vercel_embed")

    def test_decision_has_score_field(self):
        d = m.classify_page(_spec())
        assert isinstance(d.score, int)

    def test_decision_has_signals_list(self):
        d = m.classify_page(_spec())
        assert isinstance(d.signals, list)

    def test_decision_has_reason_string(self):
        d = m.classify_page(_spec())
        assert isinstance(d.reason, str) and len(d.reason.strip()) > 0

    def test_decision_has_widgets_list(self):
        d = m.classify_page(_spec())
        assert isinstance(d.widgets, list)

    def test_decision_has_threshold_field(self):
        d = m.classify_page(_spec())
        assert isinstance(d.threshold, int)
        assert d.threshold == m.ADVANCED_THRESHOLD


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
