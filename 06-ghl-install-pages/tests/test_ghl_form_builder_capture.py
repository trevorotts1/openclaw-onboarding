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
directly.

HARDENING (v17.0.6): ``_capture_form_id`` now RE-VALIDATES the captured id's SHAPE
server-side against the GHL form-id shape (``[A-Za-z0-9]{15,30}``, fullmatch) before
returning it — a malformed / oversized / punctuation-bearing capture is rejected to
'' so it can't poison the downstream delete/verify targeting. The fixture ids below
are realistic ~15-20 char alphanumeric GHL form ids (e.g. ``cuPqQhLbk0GKeguEbGYW``)
so they clear the shape gate, and a dedicated case proves the gate rejects bad ids.
Style, imports, and sys.path handling mirror
``test_ghl_secret_hygiene.py`` / ``test_browser_manager_singleton.py`` so this runs
under the same ``ghl-auth-fallback-guard`` / pytest CI.
"""
from __future__ import annotations

import builtins
import json
import os
import re
import subprocess
import sys
import time
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


# ── fast poll window for EVERY test in this file ──────────────────────────────
# _capture_form_id now POLLS on a deadline (live 2026-07-07 fix: the single-shot
# read raced the SPA's builder-iframe mount). The production window is 15s; in
# tests it is shrunk so the pre-existing failure-path cases (which now poll to
# the deadline before returning '') stay hermetic-fast. Success-path cases are
# unaffected (they return on the FIRST attempt).
@pytest.fixture(autouse=True)
def _fast_capture_poll(monkeypatch):
    monkeypatch.setattr(fb, "_FORM_ID_CAPTURE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(fb, "_FORM_ID_CAPTURE_POLL_S", 0.005)


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

    def test_form_id_shape_gate_is_the_expected_conservative_regex(self):
        """Lock the exact server-side shape gate: 15-30 chars, [A-Za-z0-9] only.
        A drift here (e.g. widening to allow punctuation) is a regression."""
        assert fb._FORM_ID_SHAPE_RE.pattern == r"[A-Za-z0-9]{15,30}"
        # fullmatch semantics: whole-string, alphanumeric, bounded length.
        assert fb._FORM_ID_SHAPE_RE.fullmatch("cuPqQhLbk0GKeguEbGYW")  # 20-char sample
        assert not fb._FORM_ID_SHAPE_RE.fullmatch("short")
        assert not fb._FORM_ID_SHAPE_RE.fullmatch("has_underscore_1234567")


# ---------------------------------------------------------------------------
# _capture_form_id — the three id-source branches
# ---------------------------------------------------------------------------
class TestCaptureFormId:
    def test_returns_id_from_iframe_src(self, monkeypatch):
        """Case 1: the id comes from the builder IFRAME's .src match; the
        trailing ?query is excluded by the [^/?#]+ boundary. The id is a
        realistic ~20-char alphanumeric GHL form id so it clears the shape gate."""
        calls = []
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://app.leadconnectorhq.com/v2/location/L/forms",
                "https://leadgen-apps-form-survey-builder.leadconnectorhq.com/"
                "form-builder-v2/abc123DEF456ghi789JK?embed=1#top",
            ],
            top_frame="/v2/location/L/form-builder",  # no id here
            calls=calls,
        )
        assert fb._capture_form_id("sess-1") == "abc123DEF456ghi789JK"
        # proves it actually evaluated the capture JS via _eval
        assert calls and calls[0]["js"] == fb._FORM_ID_CAPTURE_JS

    def test_first_matching_iframe_wins_over_top_frame(self, monkeypatch):
        """The iframe src is preferred over any top-frame match (fix intent).
        BOTH ids are valid-shaped, so preference (not the shape gate) is what
        decides the winner."""
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://x.leadconnectorhq.com/form-builder-v2/IFRAMEid9abcDEF12",
            ],
            top_frame="/form-builder-v2/TOPFRAMEid0ghiJKL",
            calls=[],
        )
        assert fb._capture_form_id("sess-2") == "IFRAMEid9abcDEF12"

    def test_top_frame_fallback_when_no_iframe_match(self, monkeypatch):
        """Case 2: no iframe carries the id -> fall back to the top-frame
        path/hash/search match (preserves the prior behavior)."""
        _install_fake_eval(
            monkeypatch,
            iframe_srcs=[
                "https://app.leadconnectorhq.com/some-other-iframe",
                "about:blank",
            ],
            top_frame="/v2/location/L/form-builder-v2/topFrameId789abcd#tab",
            calls=[],
        )
        assert fb._capture_form_id("sess-3") == "topFrameId789abcd"

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
        """_capture_form_id defensively .strip()s the _eval transport result
        (before the shape gate), so a valid-shaped id padded with whitespace
        still passes."""
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=20: "  paddedId12345678  ")
        assert fb._capture_form_id("sess-5") == "paddedId12345678"

    def test_none_result_becomes_empty_string(self, monkeypatch):
        """A None from _eval must not raise; (got or '').strip() -> '' -> ''."""
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=20: None)
        assert fb._capture_form_id("sess-6") == ""

    def test_accepts_realistic_ghl_form_id_shape(self, monkeypatch):
        """A realistic ~20-char alphanumeric GHL form id (like the ones GHL
        actually mints, e.g. ``cuPqQhLbk0GKeguEbGYW``) clears the shape gate."""
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=20: "cuPqQhLbk0GKeguEbGYW")
        assert fb._capture_form_id("sess-ok") == "cuPqQhLbk0GKeguEbGYW"

    @pytest.mark.parametrize("bad", [
        "abc123",                                # too short (< 15 chars)
        "x" * 14,                                # one char under the floor
        "x" * 31,                                # oversized (> 30 chars)
        "y" * 200,                               # grossly oversized DOM blob
        "has-a-dash-1234567",                    # punctuation (dash)
        "has_underscore_12345",                  # punctuation (underscore)
        "has.a.dot.1234567890",                  # punctuation (dot)
        "/v2/location/L/form-builder",           # a stray path segment (slashes)
        "<script>alert(1)</script>evilpayload",  # junk / injection-y blob
        "  spaced out id here  ",                # inner spaces survive .strip()
    ])
    def test_rejects_malformed_or_oversized_id(self, monkeypatch, bad):
        """SERVER-SIDE SHAPE RE-VALIDATION: a captured value that does NOT match
        the GHL form-id shape (``[A-Za-z0-9]{15,30}`` fullmatch) is rejected to ''
        — raw eval output is never trusted as an id. Covers too-short, oversized,
        punctuation, path segments, and injection-y blobs."""
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=20: bad)
        assert fb._capture_form_id("sess-bad") == "", f"should reject {bad!r}"


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


# ---------------------------------------------------------------------------
# _capture_form_id POLLING (live 2026-07-07 fix) — the builder iframe mounts
# ASYNCHRONOUSLY after the create-modal Create click flips the SPA route, so a
# single-shot read raced it and returned '' forever (STOP@F2.create on slow,
# form-heavy client accounts even though the form WAS created). The capture polls
# on a monotonic deadline: succeeds as soon as one attempt clears the shape
# gate, returns '' CLEANLY at the deadline (bounded — never hangs), and always
# makes at least one attempt.
# ---------------------------------------------------------------------------
class TestCaptureFormIdPolling:
    def test_captures_id_when_iframe_src_populates_late(self, monkeypatch):
        """THE regression: the first attempts see the pre-builder DOM (no
        /form-builder-v2 iframe yet — exactly what the live 2026-07-07 failure
        evaluated), then the iframe mounts with the id-bearing src. The poll
        must ride through the misses and capture the id."""
        state = {"n": 0}

        def _fake_eval(session, js, timeout=20):
            assert js == fb._FORM_ID_CAPTURE_JS, "capture used the wrong JS payload"
            state["n"] += 1
            if state["n"] <= 3:   # iframe not mounted yet: forms list, no builder src
                return _simulate_capture_js(
                    ["about:blank"], "/v2/location/L/form-builder/main")
            return _simulate_capture_js(
                ["https://leadgen-apps-form-survey-builder.leadconnectorhq.com/"
                 "form-builder-v2/lateMountId1234abc?x=1"],
                "/v2/location/L/form-builder-v2/lateMountId1234abc")

        monkeypatch.setattr(fb, "_eval", _fake_eval)
        got = fb._capture_form_id("sess-poll", timeout_s=5.0, poll_s=0.005)
        assert got == "lateMountId1234abc"
        assert state["n"] >= 4, "must have POLLED past the empty attempts"

    def test_returns_empty_cleanly_at_deadline_never_hangs(self, monkeypatch):
        """If the src NEVER populates the capture must return '' at the deadline
        — bounded wall-clock, multiple attempts (a poll, not a single shot),
        and no exception/hang."""
        calls = []
        monkeypatch.setattr(
            fb, "_eval",
            lambda session, js, timeout=20: (calls.append(js), "")[1])
        started = time.monotonic()
        got = fb._capture_form_id("sess-nohang", timeout_s=0.25, poll_s=0.01)
        elapsed = time.monotonic() - started
        assert got == ""
        assert elapsed < 2.0, f"deadline not honored (took {elapsed:.2f}s)"
        assert len(calls) > 1, "must poll (re-evaluate), not read once"

    def test_zero_budget_still_makes_exactly_one_attempt(self, monkeypatch):
        """timeout_s=0 keeps the pre-fix single-shot semantics: one attempt,
        success passes through, miss returns '' immediately."""
        calls = []

        def _hit(session, js, timeout=20):
            calls.append(js)
            return "cuPqQhLbk0GKeguEbGYW"

        monkeypatch.setattr(fb, "_eval", _hit)
        assert fb._capture_form_id("s", timeout_s=0.0) == "cuPqQhLbk0GKeguEbGYW"
        assert len(calls) == 1

        calls.clear()
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=20:
                            (calls.append(js), "")[1])
        assert fb._capture_form_id("s", timeout_s=0.0) == ""
        assert len(calls) == 1

    def test_shape_gate_enforced_on_every_attempt(self, monkeypatch):
        """A bad-shaped value arriving DURING the poll must never be returned —
        the shape gate applies per attempt, so a junk read polls on and the
        capture ends '' at the deadline."""
        monkeypatch.setattr(fb, "_eval",
                            lambda session, js, timeout=20: "/v2/location/L/x")
        assert fb._capture_form_id("sess-junk", timeout_s=0.1, poll_s=0.01) == ""

    def test_default_window_reads_module_constants_at_call_time(self, monkeypatch):
        """The None-sentinel defaults must read the MODULE constants at call
        time (the testability/ops seam) — with the budget pinned to 0 a
        default-args call makes exactly one attempt."""
        monkeypatch.setattr(fb, "_FORM_ID_CAPTURE_TIMEOUT_S", 0.0)
        calls = []
        monkeypatch.setattr(fb, "_eval", lambda session, js, timeout=20:
                            (calls.append(js), "")[1])
        assert fb._capture_form_id("sess-const") == ""
        assert len(calls) == 1

    def test_production_poll_window_is_sane(self):
        """Lock the shipped window: a 10-15s budget (task-rubric bound) and a
        sub-second pause — wide enough for a slow SPA mount, bounded enough to
        never stall the walk."""
        # the autouse fixture monkeypatches the module attrs, so lock the
        # PRISTINE shipped values against the source text instead
        src = Path(fb.__file__).read_text(encoding="utf-8")
        assert "_FORM_ID_CAPTURE_TIMEOUT_S = 15.0" in src
        assert "_FORM_ID_CAPTURE_POLL_S = 0.5" in src


# ---------------------------------------------------------------------------
# F2 walk gates (live 2026-07-07) — the create-modal wait rc was IGNORED, so on
# a slow, form-heavy account where the modal never opened the walk blundered
# into Create/capture blind and the miss surfaced two steps later as a
# misleading F2.create "iframe src" failure (evidence: the f2-create-modal
# screenshot was byte-identical to the forms-list screenshot). The walk now
# (a) fail-fasts honestly at F2.modal after ONE retry, and (b) attaches live
# page-state evidence (top path + iframe srcs) to both F2 STOP reports.
# ---------------------------------------------------------------------------
def _cp(rc: int) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout="", stderr="")


def _minimal_plan() -> dict:
    return {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form",
            "default_fields_keep": [], "fields": []}


_DIAG_FIXTURE = {"path": "/v2/location/L/form-builder/main", "iframes": ["about:blank"]}


class TestWalkF2Gates:
    @pytest.fixture(autouse=True)
    def _mute_screenshots(self, monkeypatch):
        monkeypatch.setattr(fb, "_screenshot", lambda session, path: None)

    def _wire_eval_diag_only(self, monkeypatch):
        """_eval answers the diag JS with a fixture page-state; the capture JS
        (if ever reached) sees a pre-builder DOM and misses."""
        def _fake_eval(session, js, timeout=20):
            if js == fb._ENTRY_DIAG_JS:
                return json.dumps(_DIAG_FIXTURE)
            if js == fb._FORM_ID_CAPTURE_JS:
                return _simulate_capture_js(["about:blank"],
                                            "/v2/location/L/form-builder/main")
            return ""
        monkeypatch.setattr(fb, "_eval", _fake_eval)

    def test_modal_never_opens_stops_at_f2_modal_after_one_retry(self, monkeypatch):
        """Modal wait misses twice -> StopAndReport at F2.modal (NOT a
        misleading downstream F2.create), with exactly one click retry and the
        page-state evidence in the reason. The capture step is never reached."""
        clicks, captured = [], []
        monkeypatch.setattr(fb, "_click",
                            lambda session, target, timeout=15: (clicks.append(target), _cp(0))[1])
        monkeypatch.setattr(fb, "_wait_text",
                            lambda session, text, timeout=20: _cp(1))
        monkeypatch.setattr(fb, "_capture_form_id",
                            lambda session, *a, **k: (captured.append(1), "")[1])
        self._wire_eval_diag_only(monkeypatch)

        click_list = {"steps": [{"phase": "F2", "action": "click", "target": "Create form"}]}
        with pytest.raises(fb.StopAndReport) as exc:
            fb._walk_click_list("sess-f2", click_list, _minimal_plan(),
                                "/tmp/ev", [0], [], [])
        assert exc.value.step == "F2.modal"
        assert clicks == ["Create form", "Create form"], "exactly ONE retry click"
        assert _DIAG_FIXTURE["path"] in exc.value.reason, "page-state evidence attached"
        assert captured == [], "must not blunder into the capture step"

    def test_modal_opening_on_retry_proceeds(self, monkeypatch):
        """First modal wait misses, the retry sees 'Start from Scratch' -> the
        step completes normally (recorded in steps_done, no STOP)."""
        waits = {"n": 0}

        def _fake_wait(session, text, timeout=20):
            waits["n"] += 1
            return _cp(1 if waits["n"] == 1 else 0)

        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text", _fake_wait)

        steps_done: list = []
        click_list = {"steps": [{"phase": "F2", "action": "click", "target": "Create form"}]}
        out = fb._walk_click_list("sess-f2r", click_list, _minimal_plan(),
                                  "/tmp/ev", [0], [], steps_done)
        assert steps_done and steps_done[0].startswith("F2:click:Create form")
        assert out["form_id"] == ""          # id capture happens on the Create step

    def test_create_step_uses_polling_capture_and_returns_id(self, monkeypatch):
        """The Create step must ride the POLL: the first capture attempts see a
        pre-builder DOM, a later attempt sees the mounted iframe src, and the
        walk comes back with the id (no STOP)."""
        state = {"n": 0}

        def _fake_eval(session, js, timeout=20):
            assert js == fb._FORM_ID_CAPTURE_JS
            state["n"] += 1
            if state["n"] <= 2:
                return _simulate_capture_js(["about:blank"],
                                            "/v2/location/L/form-builder/main")
            return _simulate_capture_js(
                ["https://x.leadconnectorhq.com/form-builder-v2/walkPolledId567xyz"],
                "/v2/location/L/form-builder-v2/walkPolledId567xyz")

        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text", lambda session, text, timeout=20: _cp(0))
        monkeypatch.setattr(fb, "_eval", _fake_eval)
        monkeypatch.setattr(fb, "_FORM_ID_CAPTURE_TIMEOUT_S", 5.0)  # ample, poll is fast

        click_list = {"steps": [{"phase": "F2", "action": "click", "target": "Create"}]}
        out = fb._walk_click_list("sess-f2c", click_list, _minimal_plan(),
                                  "/tmp/ev", [0], [], [])
        assert out["form_id"] == "walkPolledId567xyz"
        assert state["n"] >= 3, "the walk must use the polling capture"

    def test_create_step_capture_miss_stops_with_evidence(self, monkeypatch):
        """When the id never appears the STOP stays at F2.create but now carries
        the poll budget + Save-wait rc + live page-state (path/iframe srcs) so
        the next operator sees WHERE the browser actually was."""
        monkeypatch.setattr(fb, "_click", lambda session, target, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text", lambda session, text, timeout=20: _cp(1))
        self._wire_eval_diag_only(monkeypatch)

        click_list = {"steps": [{"phase": "F2", "action": "click", "target": "Create"}]}
        with pytest.raises(fb.StopAndReport) as exc:
            fb._walk_click_list("sess-f2m", click_list, _minimal_plan(),
                                "/tmp/ev", [0], [], [])
        assert exc.value.step == "F2.create"
        assert "polling" in exc.value.reason
        assert "rc=1" in exc.value.reason, "Save-wait rc recorded as evidence"
        assert _DIAG_FIXTURE["path"] in exc.value.reason, "page-state evidence attached"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
