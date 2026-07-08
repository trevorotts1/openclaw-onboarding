"""Regression tests for the F-P9 interpreter/Playwright preflight guard
(v18.1.11, fix/skill6-ghl-form-iframe-drag).

THE LIVE 2026-07-08 ENVIRONMENT MISS THIS LOCKS OUT: a live-test harness
resolved `python3` to a Homebrew python3.14 install WITHOUT Playwright instead
of the interpreter Playwright is installed under. Nothing in the skill failed
fast — the wrong-interpreter run would only surface DEEP in the live walk
(F3 rename / F4 field-removal ride ghl_iframe_drag's Playwright-over-CDP seam)
as an opaque `playwright-unavailable`, AFTER a real form already existed in the
account. The preflight now HARD-verifies (live mode only) that Playwright is
importable under THIS interpreter and fails with a CLEAR, actionable message
(names sys.executable, gives the `<python3> -m pip` fix) so an environment
mistake can never burn a live attempt. Dry-run/THINK stays soft (warning only)
— the reasoning layer must keep working on boxes without Playwright.

HERMETIC — NO network, NO live browser, NO GHL. Style, imports, and sys.path
handling mirror ``test_ghl_form_rename_and_cleanup.py``.
"""
from __future__ import annotations

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


def _task() -> dict:
    return {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form"}


def _preflight(monkeypatch, *, live: bool, pw_available):
    """Run _run_preflight with ghl_iframe_drag scripted: None (module absent)
    or a stub whose PLAYWRIGHT_AVAILABLE is the given bool."""
    if pw_available is None:
        monkeypatch.setattr(fb, "ghl_iframe_drag", None)
    else:
        class _Stub:
            PLAYWRIGHT_AVAILABLE = bool(pw_available)
        monkeypatch.setattr(fb, "ghl_iframe_drag", _Stub)
    task = _task()
    fields = fb._resolve_fields(task)
    dep = fb.plan_dependencies(fields, task, existing_field_keys=[], existing_tags=[])
    return fb._run_preflight(task, fields, dep, live=live)


def _fp9(pre: dict) -> dict:
    matches = [c for c in pre["checks"] if c["check"] == "F-P9:playwright_interpreter"]
    assert len(matches) == 1, "F-P9 must run exactly once per preflight"
    return matches[0]


class TestFP9LiveHardGate:
    def test_missing_playwright_hard_stops_a_live_run(self, monkeypatch):
        pre = _preflight(monkeypatch, live=True, pw_available=False)
        assert pre["pass"] is False
        assert pre["stop_reason"].startswith("F-P9:playwright_interpreter")
        assert _fp9(pre)["pass"] is False

    def test_missing_module_hard_stops_a_live_run(self, monkeypatch):
        """ghl_iframe_drag not importable at all is the same environment miss."""
        pre = _preflight(monkeypatch, live=True, pw_available=None)
        assert pre["pass"] is False
        assert _fp9(pre)["pass"] is False

    def test_failure_message_is_actionable_not_cryptic(self, monkeypatch):
        """The whole point: name the interpreter and spell out the fix, so the
        operator never has to reverse-engineer a downstream
        `playwright-unavailable` after a live attempt was wasted."""
        pre = _preflight(monkeypatch, live=True, pw_available=False)
        detail = _fp9(pre)["detail"]
        assert sys.executable in detail, "must NAME the wrong interpreter"
        assert "-m pip install playwright" in detail
        assert "-m playwright install chromium" in detail
        assert "import playwright.sync_api" in detail, "must give the verify probe"
        assert "DIFFERENT python" in detail, (
            "must explain the bare-pip/PATH trap that caused the live miss")

    def test_playwright_present_passes_live(self, monkeypatch):
        pre = _preflight(monkeypatch, live=True, pw_available=True)
        assert _fp9(pre)["pass"] is True
        assert pre["pass"] is True


class TestFP9DryRunStaysSoft:
    def test_dry_run_records_warning_but_never_blocks(self, monkeypatch):
        """THINK-layer (dry-run) must keep working on boxes without Playwright
        — the check is recorded as a WARNING, not a stop."""
        pre = _preflight(monkeypatch, live=False, pw_available=False)
        assert pre["pass"] is True
        c = _fp9(pre)
        assert c["pass"] is True, "soft in dry-run"
        assert "WARNING" in c["detail"]
        assert "NOT importable" in c["detail"], "the gap must still be visible"

    def test_dry_run_with_playwright_is_clean(self, monkeypatch):
        pre = _preflight(monkeypatch, live=False, pw_available=True)
        c = _fp9(pre)
        assert c["pass"] is True and "WARNING" not in c["detail"]


class TestBuildFormWiring:
    def test_dry_run_calls_preflight_soft(self, monkeypatch, tmp_path):
        seen = {}
        real = fb._run_preflight

        def spy(task, fields, dep_plan, *, live=False):
            seen["live"] = live
            return real(task, fields, dep_plan, live=live)

        monkeypatch.setattr(fb, "_run_preflight", spy)
        out = fb.build_form(_task(), str(tmp_path), dry_run=True)
        assert seen["live"] is False
        assert out.get("dry_run") is True

    def test_live_run_stops_at_preflight_before_any_browser(self, monkeypatch, tmp_path):
        """dry_run=False + Playwright missing → build_form returns the
        preflight STOP (clear error, evidence written) and never reaches the
        live browser path."""
        class _Stub:
            PLAYWRIGHT_AVAILABLE = False
        monkeypatch.setattr(fb, "ghl_iframe_drag", _Stub)
        touched = []
        monkeypatch.setattr(fb, "_live_build",
                            lambda *a, **k: (touched.append(1), {})[1])
        out = fb.build_form(_task(), str(tmp_path), dry_run=False)
        assert touched == [], "the live walk must NEVER start on F-P9 failure"
        assert "F-P9" in (out.get("error") or "")
        assert out["preflight"]["pass"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
