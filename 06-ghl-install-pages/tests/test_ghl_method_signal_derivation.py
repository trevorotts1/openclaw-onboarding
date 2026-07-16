"""MOCK-only unit tests — U23/B-U9 decision-engine hardening, gap (1):
signal derivation from raw HTML.

These tests are MOCK-ONLY. There is NO live GoHighLevel, NO Vercel deploy,
NO network of any kind. ``derive_page_signals`` / ``merge_derived_under_explicit``
/ ``classify_page_from_html`` are all pure functions; the tests drive them
with crafted HTML strings and dicts and assert the output.

Coverage:
  * derive_page_signals detects known JS-framework fingerprints (hard
    signal territory) from both <script src=...> URLs and inline body
    markers.
  * derive_page_signals detects third-party JS libraries from <script
    src=...> URLs only (soft signal territory — distinct from frameworks).
  * derive_page_signals detects interactive behaviors (fetch/websocket/
    canvas/webgl/routing).
  * derive_page_signals detects CSS-fighting density (!important count,
    global selectors, @font-face blocks).
  * derive_page_signals returns just {"html": html} for boring/simple HTML
    (no false positives).
  * derive_page_signals raises MethodDecisionError on non-str input — fail
    loud, never silently defaults.
  * merge_derived_under_explicit: explicit ALWAYS wins key-for-key over
    derived — this is the acceptance-criterion property test ("derive_page_
    signals never overrides an explicit spec field").
  * merge_derived_under_explicit raises on non-dict inputs.
  * classify_page_from_html end-to-end: a plain <p> page classifies DIRECT;
    a page with a React fingerprint classifies VERCEL (hard signal); an
    explicit override (e.g. complexity is NOT derived, but js_frameworks
    IS) always beats the derived inference.

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_ghl_method_signal_derivation.py -v
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
import ghl_method as m


def _method_val(decision) -> str:
    meth = decision.method
    return meth.value if hasattr(meth, "value") else str(meth)


# ── derive_page_signals — framework detection ─────────────────────────────────

class TestDeriveFrameworkDetection:
    def test_react_via_script_src(self):
        html = '<script src="https://cdn.example.com/react.production.min.js"></script><div>hi</div>'
        derived = m.derive_page_signals(html)
        assert "react" in derived.get("js_frameworks", [])

    def test_react_via_inline_marker(self):
        html = '<div id="root" data-reactroot=""></div>'
        derived = m.derive_page_signals(html)
        assert "react" in derived.get("js_frameworks", [])

    def test_vue_via_inline_marker(self):
        html = '<div data-v-1234abcd>Hello</div>'
        derived = m.derive_page_signals(html)
        assert "vue" in derived.get("js_frameworks", [])

    def test_angular_via_ng_app(self):
        html = '<html ng-app="myApp"><body>hi</body></html>'
        derived = m.derive_page_signals(html)
        assert "angular" in derived.get("js_frameworks", [])

    def test_nextjs_via_next_data(self):
        html = '<script id="__NEXT_DATA__" type="application/json">{}</script>'
        derived = m.derive_page_signals(html)
        assert "next.js" in derived.get("js_frameworks", [])

    def test_no_duplicate_framework_entries(self):
        """Two different markers for the SAME framework must dedupe."""
        html = '<div data-reactroot=""></div><script>ReactDOM.render(x, y)</script>'
        derived = m.derive_page_signals(html)
        frameworks = derived.get("js_frameworks", [])
        assert frameworks.count("react") == 1

    def test_plain_html_has_no_frameworks(self):
        html = "<section><h1>Hello</h1><p>Copy text.</p></section>"
        derived = m.derive_page_signals(html)
        assert "js_frameworks" not in derived


# ── derive_page_signals — third-party JS library detection ────────────────────

class TestDeriveThirdPartyJs:
    def test_jquery_and_gsap_from_script_src(self):
        html = (
            '<script src="https://cdn.example.com/jquery.min.js"></script>'
            '<script src="https://cdn.example.com/gsap.min.js"></script>'
        )
        derived = m.derive_page_signals(html)
        libs = derived.get("third_party_js", [])
        assert "jquery" in libs
        assert "gsap" in libs

    def test_third_party_only_from_script_src_not_inline_text(self):
        """A library NAME mentioned in body text (not a script src) must NOT
        be picked up — only <script src=...> URLs are inspected."""
        html = "<p>We use jquery and gsap for our animations.</p>"
        derived = m.derive_page_signals(html)
        assert "third_party_js" not in derived

    def test_no_duplicate_lib_entries(self):
        html = (
            '<script src="/vendor/jquery.min.js"></script>'
            '<script src="/vendor/jquery-ui.jquery.min.js"></script>'
        )
        derived = m.derive_page_signals(html)
        assert derived["third_party_js"].count("jquery") == 1


# ── derive_page_signals — interactive behaviour ────────────────────────────────

class TestDeriveInteractive:
    def test_fetch_detected(self):
        html = "<script>fetch('/api/data').then(r => r.json())</script>"
        derived = m.derive_page_signals(html)
        assert "fetch" in derived.get("interactive", [])

    def test_websocket_detected(self):
        html = "<script>const ws = new WebSocket('wss://example.com')</script>"
        derived = m.derive_page_signals(html)
        assert "websocket" in derived.get("interactive", [])

    def test_canvas_tag_detected(self):
        html = "<canvas id='c' width='400' height='300'></canvas>"
        derived = m.derive_page_signals(html)
        assert "canvas" in derived.get("interactive", [])

    def test_webgl_detected(self):
        html = "<script>const gl = canvas.getContext('webgl');</script>"
        derived = m.derive_page_signals(html)
        assert "webgl" in derived.get("interactive", [])

    def test_client_routing_detected_via_pushstate(self):
        html = "<script>history.pushState({}, '', '/next-page')</script>"
        derived = m.derive_page_signals(html)
        assert "routing" in derived.get("interactive", [])

    def test_plain_html_has_no_interactive(self):
        html = "<section><h1>Hello</h1><p>Copy text.</p></section>"
        derived = m.derive_page_signals(html)
        assert "interactive" not in derived


# ── derive_page_signals — CSS-fighting density ─────────────────────────────────

class TestDeriveCssFighting:
    def test_important_storm_counted(self):
        html = "<style>.a{color:red!important} .b{color:blue!important}</style>"
        derived = m.derive_page_signals(html)
        assert derived["css_fighting"]["important_storms"] == 2

    def test_global_selectors_counted(self):
        html = "<style>body{margin:0} * {box-sizing:border-box} html{height:100%}</style>"
        derived = m.derive_page_signals(html)
        assert derived["css_fighting"]["global_selectors"] == 3

    def test_font_face_counted(self):
        html = (
            "<style>@font-face{font-family:'A';src:url(a.woff)}"
            "@font-face{font-family:'B';src:url(b.woff)}</style>"
        )
        derived = m.derive_page_signals(html)
        assert derived["css_fighting"]["font_face_blocks"] == 2

    def test_no_css_fighting_key_when_nothing_detected(self):
        html = "<style>.card{padding:8px}</style>"
        derived = m.derive_page_signals(html)
        assert "css_fighting" not in derived


# ── derive_page_signals — payload carrier + boring HTML ────────────────────────

class TestDerivePayloadAndBoring:
    def test_html_key_always_present(self):
        html = "<p>hi</p>"
        derived = m.derive_page_signals(html)
        assert derived["html"] == html

    def test_boring_html_derives_only_html_key(self):
        html = "<section><h1>Hello</h1><p>Copy text.</p></section>"
        derived = m.derive_page_signals(html)
        assert set(derived.keys()) == {"html"}

    def test_non_str_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.derive_page_signals(12345)

    def test_none_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.derive_page_signals(None)

    def test_never_calls_classify_page_itself(self, monkeypatch):
        """derive_page_signals must be a pure analyzer -- it never invokes
        classify_page on its own (that is the caller's job, or
        classify_page_from_html's job)."""
        called = {"n": 0}
        real_classify = m.classify_page

        def _spy(*a, **kw):
            called["n"] += 1
            return real_classify(*a, **kw)

        monkeypatch.setattr(m, "classify_page", _spy)
        m.derive_page_signals("<canvas></canvas><script>fetch('/x')</script>")
        assert called["n"] == 0, "derive_page_signals must never call classify_page"


# ── merge_derived_under_explicit — explicit ALWAYS wins ────────────────────────

class TestMergeDerivedUnderExplicit:
    def test_derived_only_key_passes_through(self):
        merged = m.merge_derived_under_explicit(None, {"js_frameworks": ["react"]})
        assert merged["js_frameworks"] == ["react"]

    def test_explicit_only_key_passes_through(self):
        merged = m.merge_derived_under_explicit({"complexity": "advanced"}, {})
        assert merged["complexity"] == "advanced"

    def test_explicit_wins_on_shared_key(self):
        """THE property test: a key declared in BOTH keeps the explicit
        value untouched -- derived never overrides an explicit spec field."""
        explicit = {"js_frameworks": ["vue"]}
        derived = {"js_frameworks": ["react", "angular"]}
        merged = m.merge_derived_under_explicit(explicit, derived)
        assert merged["js_frameworks"] == ["vue"], (
            "explicit_spec must win over derived_spec on a shared key — "
            f"got {merged['js_frameworks']!r}"
        )

    def test_explicit_empty_dict_still_no_override(self):
        """An explicit spec that is present but empty ({}) declares nothing
        -- derived values pass through untouched (falsy {} short-circuits
        the .update() but that is semantically correct: nothing to win)."""
        merged = m.merge_derived_under_explicit({}, {"interactive": ["fetch"]})
        assert merged["interactive"] == ["fetch"]

    def test_explicit_none_no_override(self):
        merged = m.merge_derived_under_explicit(None, {"interactive": ["fetch"]})
        assert merged["interactive"] == ["fetch"]

    def test_neither_input_mutated(self):
        explicit = {"complexity": "advanced"}
        derived = {"js_frameworks": ["react"]}
        explicit_copy = dict(explicit)
        derived_copy = dict(derived)
        m.merge_derived_under_explicit(explicit, derived)
        assert explicit == explicit_copy
        assert derived == derived_copy

    def test_non_dict_explicit_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.merge_derived_under_explicit("not a dict", {})

    def test_non_dict_derived_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.merge_derived_under_explicit(None, "not a dict")


# ── classify_page_from_html — end-to-end pure wrapper ───────────────────────────

class TestClassifyPageFromHtml:
    def test_plain_page_is_direct(self):
        decision = m.classify_page_from_html("<section><h1>Hi</h1></section>")
        assert _method_val(decision) == "direct"

    def test_react_fingerprint_forces_vercel(self):
        html = '<div id="root" data-reactroot=""></div>'
        decision = m.classify_page_from_html(html)
        assert _method_val(decision) == "vercel_embed"
        hard = [s for s in decision.signals if s["weight"] >= m.HARD_SIGNAL_WEIGHT]
        assert any(s["name"] == m.SIG_EXTERNAL_FRAMEWORK for s in hard)

    def test_interactive_plus_third_party_reaches_threshold(self):
        html = (
            '<script src="/vendor/jquery.min.js"></script>'
            '<script src="/vendor/gsap.min.js"></script>'
            "<canvas></canvas>"
        )
        decision = m.classify_page_from_html(html)
        assert decision.score >= m.ADVANCED_THRESHOLD
        assert _method_val(decision) == "vercel_embed"

    def test_explicit_spec_overrides_derived_framework_detection(self):
        """An explicit spec claiming js_frameworks=[] must WIN over an HTML
        body that would otherwise derive a react fingerprint -- proving the
        explicit-wins merge is actually wired through classify_page_from_html."""
        html = '<div id="root" data-reactroot=""></div>'
        decision = m.classify_page_from_html(html, explicit_spec={"js_frameworks": []})
        assert _method_val(decision) == "direct", (
            "an explicit js_frameworks=[] override must beat the derived "
            "react fingerprint"
        )

    def test_explicit_html_wins_over_derived_html_for_payload_check(self):
        """If the caller explicitly declares a SHORT html/content field, that
        must be what payload-size is checked against -- not the (possibly
        huge) raw html passed in for signal derivation."""
        big_html = "<p>" + ("A" * (m.MAX_DIRECT_BYTES + 1024)) + "</p>"
        decision = m.classify_page_from_html(
            big_html, explicit_spec={"html": "<p>short</p>"}
        )
        assert _method_val(decision) == "direct", (
            "explicit html must win over the derived (huge) html for the "
            "payload-size signal"
        )

    def test_bad_html_type_raises(self):
        with pytest.raises(m.MethodDecisionError):
            m.classify_page_from_html(None)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
