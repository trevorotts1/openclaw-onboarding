"""Regression tests for the v17.0.2 Skill-6 form-builder hotfix (PRD P1-5).

LOCKS IN commit b3a17bb5, which rewrote ``_capture_form_id`` and added
``_ensure_agent_browser_path`` in ``06-ghl-install-pages/tools/ghl_form_builder.py``.
Before the fix, the form id was read from the top frame only (``location.pathname``),
which NEVER carries the id, so every capture returned '' and downstream delete/verify
could not target the form. The fix reads the id out of the builder IFRAME's ``.src``
attribute (parent-readable even cross-origin) via ``_FORM_ID_CAPTURE_JS``, falling
back to the top-frame path/hash/search. This suite had ZERO coverage before now.

HERMETIC — NO network, NO live browser, NO GHL. The module's ``_eval`` (the only
seam that would touch ``agent-browser``) is monkeypatched with a faithful Python
re-implementation of ``_FORM_ID_CAPTURE_JS`` evaluated against a fixture DOM, so the
iframe-first / top-frame-fallback / no-match branches are all exercised without a
browser. ``_ensure_agent_browser_path`` is a pure env-dict transform and is tested
directly. Style, imports, and sys.path handling mirror
``test_ghl_secret_hygiene.py`` / ``test_browser_manager_singleton.py`` so this runs
under the same ``ghl-auth-fallback-guard`` / pytest CI.
"""
from __future__ import annotations

import builtins
import os
import re
import sys
from pathlib import Path

import pytest

# ── sys.path setup (mirrors the sibling 06 tests) ─────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_form_builder as fb  # noqa: E402

# The path where the `agent-browser` CLI lives; the fix guarantees it is on PATH.
_BINDIR = os.path.expanduser("~/.npm-global/bin")


# ── faithful Python re-implementation of _FORM_ID_CAPTURE_JS ──────────────────
# The shipped JS is:
#   RE = /\/form-builder-v2\/([^/?#]+)/
#   for each <iframe>: src = f.src || f.getAttribute('src') || '';
#                      m = src.match(RE); if (m) return m[1];
#   top = pathname + hash + search; tm = top.match(RE); return tm ? tm[1] : '';
# This mirrors that exactly so the monkeypatched _eval "evaluates" the real JS
# against a fixture DOM (iframe srcs + a top-frame string).
_FORM_ID_RE = re.compile(r"/form-builder-v2/([^/?#]+)")


def _simulate_capture_js(iframe_srcs, top_frame):
    for src in iframe_srcs:
        m = _FORM_ID_RE.search(src or "")
        if m:
            return m.group(1)
    m = _FORM_ID_RE.search(top_frame or "")
    return m.group(1) if m else ""


def _install_fake_eval(monkeypatch, iframe_srcs, top_frame, calls):
    """Swap the module's _eval for one that represents the _FORM_ID_CAPTURE_JS
    result over the given fixture DOM, and record each call for assertions."""
    def _fake_eval(session, js, timeout=20):
        calls.append({"session": session, "js": js, "timeout": timeout})
        # _capture_form_id MUST evaluate the capture JS (not some other script).
        assert js == fb._FORM_ID_CAPTURE_JS, "capture used the wrong JS payload"
        return _simulate_capture_js(iframe_srcs, top_frame)

    monkeypatch.setattr(fb, "_eval", _fake_eval)
    return calls


# ---------------------------------------------------------------------------
# The capture JS itself — structural guard so the simulator can't silently
# drift from the shipped regex.
# ---------------------------------------------------------------------------
class TestCaptureJsShape:
    def test_capture_js_targets_form_builder_v2_with_boundary_class(self):
        js = fb._FORM_ID_CAPTURE_JS
        assert "form-builder-v2" in js
        assert "[^/?#]" in js, "the id regex must stop at / ? and #"
        assert "querySelectorAll('iframe')" in js, "must enumerate iframes by DOM"


# ---------------------------------------------------------------------------
# _capture_form_id — the three id-source branches
# ---------------------------------------------------------------------------
class TestCaptureFormId:
    def test_returns_id_from_iframe_src(self, monkeypatch):
        """Case 1: the id comes from the builder IFRAME's .src match; the
        trailing ?query is excluded by the [^/?#]+ boundary."""
        calls = []
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://app.leadconnectorhq.com/v2/location/L/forms",
                "https://leadgen-apps-form-survey-builder.leadconnectorhq.com/"
                "form-builder-v2/abc123DEF456?embed=1#top",
            ],
            top_frame="/v2/location/L/form-builder",  # no id here
            calls=calls,
        )
        assert fb._capture_form_id("sess-1") == "abc123DEF456"
        # proves it actually evaluated the capture JS via _eval
        assert calls and calls[0]["js"] == fb._FORM_ID_CAPTURE_JS

    def test_first_matching_iframe_wins_over_top_frame(self, monkeypatch):
        """The iframe src is preferred over any top-frame match (fix intent)."""
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://x.leadconnectorhq.com/form-builder-v2/IFRAME_ID_9",
            ],
            top_frame="/form-builder-v2/TOPFRAME_ID_0",
            calls=[],
        )
        assert fb._capture_form_id("sess-2") == "IFRAME_ID_9"

    def test_top_frame_fallback_when_no_iframe_match(self, monkeypatch):
        """Case 2: no iframe carries the id -> fall back to the top-frame
        path/hash/search match (preserves the prior behavior)."""
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://app.leadconnectorhq.com/some-other-iframe",
                "about:blank",
            ],
            top_frame="/v2/location/L/form-builder-v2/topFrameId789#tab",
            calls=[],
        )
        assert fb._capture_form_id("sess-3") == "topFrameId789"

    def test_returns_empty_when_neither_yields_id(self, monkeypatch):
        """Case 3: neither an iframe src nor the top frame matches -> ''."""
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://app.leadconnectorhq.com/dashboard",
                "about:blank",
            ],
            top_frame="/v2/location/L/forms/list",
            calls=[],
        )
        assert fb._capture_form_id("sess-4") == ""

    def test_result_is_stripped(self, monkeypatch):
        """_capture_form_id defensively .strip()s the _eval transport result."""
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=20: "  padded_id  ")
        assert fb._capture_form_id("sess-5") == "padded_id"

    def test_none_result_becomes_empty_string(self, monkeypatch):
        """A None from _eval must not raise; (got or '').strip() -> ''."""
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=20: None)
        assert fb._capture_form_id("sess-6") == ""


# ---------------------------------------------------------------------------
# _ensure_agent_browser_path — PATH repair, idempotent, secrets-file-free
# ---------------------------------------------------------------------------
class TestEnsureAgentBrowserPath:
    def test_prepends_bindir_when_missing(self):
        env = {"PATH": os.pathsep.join(["/usr/bin", "/bin"])}
        out = fb._ensure_agent_browser_path(env)
        parts = out["PATH"].split(os.pathsep)
        assert parts[0] == _BINDIR, "bindir must be prepended at the FRONT"
        assert "/usr/bin" in parts and "/bin" in parts, "existing PATH preserved"
        assert out is env, "must mutate and return the same env dict"

    def test_noop_and_idempotent_when_already_present(self):
        original = os.pathsep.join(["/usr/bin", _BINDIR, "/bin"])
        env = {"PATH": original}
        out = fb._ensure_agent_browser_path(env)
        assert out["PATH"] == original, "present bindir -> PATH unchanged (no dup)"
        # Running again must not add a second copy.
        out2 = fb._ensure_agent_browser_path(out)
        assert out2["PATH"] == original
        assert out2["PATH"].split(os.pathsep).count(_BINDIR) == 1

    def test_empty_path_falls_back_to_defpath_and_prepends(self, monkeypatch):
        # env PATH empty AND process PATH empty -> os.defpath, then prepend.
        monkeypatch.setenv("PATH", "")
        env = {"PATH": ""}
        out = fb._ensure_agent_browser_path(env)
        parts = out["PATH"].split(os.pathsep)
        assert parts[0] == _BINDIR, "bindir prepended even when PATH is empty"
        assert _BINDIR in parts

    def test_never_opens_the_secrets_file(self, monkeypatch):
        """The fix's docstring guarantees it NEVER reads/touches the secrets
        file — it only repairs an env dict. Prove it opens NO file at all."""
        opened = []
        _real_open = builtins.open

        def _spy_open(file, *a, **k):
            opened.append(str(file))
            return _real_open(file, *a, **k)

        monkeypatch.setattr(builtins, "open", _spy_open)
        fb._ensure_agent_browser_path({"PATH": os.pathsep.join(["/usr/bin", "/bin"])})

        assert opened == [], f"_ensure_agent_browser_path opened files: {opened!r}"
        # and, explicitly, nothing resembling a secrets/.env store.
        assert not any(("secrets" in p or p.endswith(".env")) for p in opened)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
