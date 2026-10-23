"""Acceptance-v3 (2026-10-22) regression locks — the four defects fixed on
``fix/s06-drive-click-and-instrument``.

1. DRIVE-LOOP CLICK MECHANICS. ``find text <x> click`` returned rc=0 '✓ Done'
   and activated NOTHING on live GHL, while a direct DOM ``.click()`` on the
   same button DID open the Create-new-form modal. Evidence:
   row7-live/form/routing/probe-create-modal.json (dialog 'Create new form /
   Start from Scratch / From templates') vs probe-raw-transport.json
   (A find-text AND B find-role both rc=0, has_create_new_form=false).
   Fix: ``_click_with_proof`` verifies the step's OWN wait_for target and, when
   the text click did not activate it, retries ONCE via a direct DOM click;
   both failing still STOPs honestly.

2. INSTRUMENT SESSION DEFECT. ``browser_cmd`` never appends ``--session`` and
   ``browser_session()`` is emitter-only, so ``render_check`` drove the DEFAULT
   agent-browser daemon and read its ACCUMULATED console buffer (example.com
   reproduced byte-identical 3 errors, console_sha256 a212bf03…,
   row12-verify/golden-probe-2). Fix: drain the buffer with ``console --clear``
   immediately BEFORE the navigation; entries are attributable only when that
   drain landed. The zero-console gate is untouched.

3. LATENT HAZARD ``_live_build`` delete-on-success. The pre-fix ``finally``
   deleted the created form on EVERY path that reached it, so a plain
   ``--no-dry-run`` SUCCESS created then instantly deleted (nothing to read
   back); only ``--stop-after-phase`` preserved it. Fix: PRESERVE on success,
   delete only on failure/cleanup paths.

4. PREFLIGHT FALSE-NEGATIVE TRAP. ``python3 -I`` removed the script directory
   from ``sys.path``, so the module's own sibling import failed and F-P9
   reported ``pass=False`` spuriously. Fix: the module bootstraps its own
   tools/ dir before the sibling imports, and ``_isolated_mode()`` reports the
   isolation honestly instead of blaming Playwright.

HERMETIC: no network, no live browser, no GHL. Style and sys.path handling
mirror the sibling 06 suites.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_builder as gb  # noqa: E402
import ghl_form_builder as fb  # noqa: E402

_SESSION = "ghl-skill6-s06-acceptance-v3-2026-10-22t02z"


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


# ===========================================================================
# 1. DRIVE-LOOP CLICK MECHANICS — verified activation + DOM fallback
# ===========================================================================
class TestVerifiedActivationClick:
    def test_text_click_that_activates_never_falls_back(self, monkeypatch):
        """The normal path: find-text lands AND the proof materializes → one
        mechanism, no DOM click, no second click."""
        clicks, dom = [], []
        monkeypatch.setattr(fb, "_click",
                            lambda s, t, timeout=15: (clicks.append(t), _cp(0))[1])
        monkeypatch.setattr(fb, "_wait_text_polling",
                            lambda s, text, timeout_s=None: True)
        monkeypatch.setattr(fb, "_dom_click_text",
                            lambda s, t, timeout=15: (dom.append(t), {"clicked": True})[1])
        out = fb._click_with_proof(_SESSION, "Create form", "Start from Scratch")
        assert out["activated"] is True and out["mechanism"] == "find-text"
        assert clicks == ["Create form"] and dom == [], "no fallback on a proven activation"

    def test_rc0_but_inert_text_click_falls_back_to_dom_click(self, monkeypatch):
        """THE LIVE DEFECT: rc=0 '✓ Done' and the modal never appears. The DOM
        click (probe-create-modal.json's proven rail) must rescue the step."""
        clicks, dom = [], []

        def _fake_click(s, t, timeout=15):
            clicks.append(t)
            return _cp(0)          # rc=0 — exactly what fooled the live run

        def _fake_wait(s, text, timeout_s=None):
            return bool(dom)   # only true AFTER the DOM click happened
        monkeypatch.setattr(fb, "_click", _fake_click)
        monkeypatch.setattr(fb, "_wait_text_polling", _fake_wait)
        monkeypatch.setattr(
            fb, "_dom_click_text",
            lambda s, t, timeout=15: (dom.append(t),
                                      {"clicked": True, "n": 1, "err": ""})[1])
        out = fb._click_with_proof(_SESSION, "Create form", "Start from Scratch")
        assert out["activated"] is True, "the DOM click must rescue an inert find-click"
        assert out["mechanism"] == "dom-click"
        assert clicks == ["Create form"] and dom == ["Create form"], "exactly ONE retry"
        assert [a["mechanism"] for a in out["attempts"]] == ["find-text", "dom-click"]

    def test_both_mechanisms_inert_reports_not_activated_and_stops_honestly(self, monkeypatch):
        """Neither rail works → activated=False (never a fabricated pass), and the
        F2 walk raises StopAndReport at F2.modal rather than blundering on."""
        monkeypatch.setattr(fb, "_click", lambda s, t, timeout=15: _cp(0))
        monkeypatch.setattr(fb, "_wait_text_polling", lambda s, text, timeout_s=None: False)
        monkeypatch.setattr(fb, "_dom_click_text",
                            lambda s, t, timeout=15: {"clicked": True, "n": 2, "err": ""})
        monkeypatch.setattr(fb, "_screenshot", lambda s, p: None)
        monkeypatch.setattr(fb, "_eval", lambda s, js, timeout=20: "{}")

        out = fb._click_with_proof(_SESSION, "Create form", "Start from Scratch")
        assert out["activated"] is False
        assert "neither a find-text click" in out["detail"]

        click_list = {"steps": [{"phase": "F2", "action": "click", "target": "Create form"}]}
        plan = {"location_id": "L", "form_name": "ZHC T", "default_fields_keep": [],
                "fields": []}
        with pytest.raises(fb.StopAndReport) as exc:
            fb._walk_click_list("sess-x", click_list, plan, "/tmp/ev-s06", [0], [], [])
        assert exc.value.step == "F2.modal"
        assert "direct DOM click" in exc.value.reason

    def test_dom_click_reports_no_visible_match_as_evidence(self, monkeypatch):
        """A DOM-click miss must be EXPLAINABLE (match count + reason), not a
        silent False."""
        def _fake_eval(s, js, timeout=20):
            assert "querySelectorAll('button,[role=button],a')" in js
            return json.dumps({"clicked": False, "n": 0, "err": "NO-VISIBLE-MATCH"})

        monkeypatch.setattr(fb, "_eval", _fake_eval)
        out = fb._dom_click_text(_SESSION, "Create form")
        assert out == {"clicked": False, "n": 0, "err": "NO-VISIBLE-MATCH"}

    def test_dom_click_is_an_exact_text_visible_match(self):
        """The JS must filter to VISIBLE elements whose OWN text equals the
        target — the same contract the probe used, never a substring/first-DOM
        guess (the collision class documented on _click)."""
        js = fb._DOM_CLICK_JS
        assert "(e.innerText || '').trim() === q" in js, "must be an EXACT text match"
        assert "getBoundingClientRect()" in js and "visibility !== 'hidden'" in js
        assert "nodes[0].click()" in js, "must be a DIRECT DOM click"


# ===========================================================================
# 2. INSTRUMENT SESSION — console captured per-navigation
# ===========================================================================
class _RenderRecorder:
    """Scriptable agent-browser for render_check: records every argv in order and
    serves stdout per VERB, with an optional rc override per verb."""

    def __init__(self, rc_map=None, stdout_map=None):
        self.argvs: list[list[str]] = []
        self.rc_map = dict(rc_map or {})
        self.stdout_map = dict(stdout_map or {})

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.argvs.append(argv)
        # Key on the command as the CLI spells it, so a test can script each
        # subcommand independently: `get html html`, `get html html`, `screenshot`,
        # `console --clear`, `console`, `open <url>`.
        tail = argv[argv.index("--session") + 2:] if "--session" in argv else argv[3:]
        head = tail[0] if tail else ""
        if head == "get":
            key = " ".join(tail[:3])
        elif head == "console" and "--clear" in tail:
            key = "console --clear"
        else:
            key = head
        return _cp(self.rc_map.get(key, 0), self.stdout_map.get(key, ""))


def _render_kwargs(tmp_path):
    return {"run_dir": str(tmp_path), "step": "s06-acceptance"}


# A rendered DOM that satisfies the marker + content floor, so a test that is
# NOT about the DOM floor never trips it. The marker is the batch's own prefix.
_RENDER_STDOUT = {
    "get html html": ("<html><body><h1>S06-ACCEPTANCE-v3-2026-10-22T02Z</h1>"
                      "<p>Acceptance render body for the click/instrument "
                      "regression suite.</p>"
                      "<div>a</div><div>b</div><div>c</div></body></html>"),
    "screenshot": "/nonexistent/s06-acceptance.png",
    "console": "",
}


@pytest.fixture()
def render_env(monkeypatch, tmp_path):
    """Wire render_check hermetically: no live version check, a scripted
    subprocess seam, and a run_dir that already holds nothing."""
    import browser_manager as bm
    monkeypatch.setattr(bm, "assert_agent_browser_version", lambda env=None: None)
    monkeypatch.setattr(bm, "_SESSION_ACTIVE", True, raising=False)
    monkeypatch.setattr(bm, "_ACTIVE_SESSION_NAME", "sess-fake", raising=False)

    def _rec(**kw):
        rec = _RenderRecorder(**kw)
        monkeypatch.setattr(subprocess, "run", rec.run)
        return rec

    return {"rec": _rec, "tmp_path": tmp_path}


def _render(monkeypatch, render_env, tmp_path, **kw):
    rec = render_env["rec"](**kw.pop("rec_kwargs", {}))
    import browser_manager as bm
    with bm.browser_session(_SESSION):
        out = gb.render_check(
            "https://example.test/preview",
            "S06-ACCEPTANCE-v3-2026-10-22T02Z",
            inspect_screenshot=False, **_render_kwargs(tmp_path))
    return rec, out


class TestConsoleBufferIsPerNavigation:
    def test_console_clear_runs_before_open(self, render_env, monkeypatch, tmp_path):
        """ORDER IS THE FIX: the drain must be the FIRST agent-browser call, and
        it must precede the navigation. Otherwise the read below still returns
        another page's accumulated errors."""
        rec, _ = _render(monkeypatch, render_env, tmp_path)
        verbs = [a[a.index("--session") + 2] if "--session" in a else a[3] for a in rec.argvs]
        assert verbs, "render_check must drive agent-browser"
        assert verbs[0] == "console" and "--clear" in rec.argvs[0], (
            f"the console drain must come FIRST — got {verbs!r}")
        assert verbs.index("open") > verbs.index("console"), (
            "the drain must precede the navigation it scopes")

    def test_stale_daemon_errors_are_not_attributed_to_the_page(self, render_env,
                                                                monkeypatch, tmp_path):
        """The proven contamination: a clean page must not inherit the previous
        page's errors. With the drain in place the buffer is empty by the time
        the navigation's own entries are read."""
        rec, out = _render(monkeypatch, render_env, tmp_path,
                           rec_kwargs={"stdout_map": _RENDER_STDOUT})
        assert out["console_drained"] is True
        assert out["render_errors"] == [], (
            "an empty (drained) buffer must yield NO render errors")
        assert out["marker_in_rendered_dom"] is True, "control: the page itself is fine"

    def test_real_navigation_errors_still_fail_the_gate(self, render_env, monkeypatch,
                                                       tmp_path):
        """The GATE is untouched: an error emitted by THIS page still fails."""
        _rec, out = _render(
            monkeypatch, render_env, tmp_path,
            rec_kwargs={"stdout_map": {
                "console": "[error] TypeError: Cannot read properties of undefined"}})
        assert out["console_drained"] is True
        assert any("Cannot read properties" in e for e in out["render_errors"])
        assert out["ok"] is False, "the zero-console gate must still fail the render"

    def test_failed_drain_fails_the_gate_and_does_not_blame_the_page(self, render_env,
                                                                   monkeypatch, tmp_path):
        """If `console --clear` cannot run, entries are UNATTRIBUTABLE: the check
        still fails (never a silent pass) but the message names the drain, not a
        fabricated page error."""
        _rec, out = _render(
            monkeypatch, render_env, tmp_path,
            rec_kwargs={"rc_map": {"console --clear": 1},
                        "stdout_map": {"console": "[error] BOOM from some other page"}})
        assert out["console_drained"] is False
        assert out["ok"] is False
        joined = " ".join(out["render_errors"])
        assert "console drain" in joined
        assert "BOOM from some other page" not in joined, (
            "an unattributable line must not be reported as this page's error")


# ===========================================================================
# 3. _live_build CLEANUP POLICY — preserve on success, delete on failure
# ===========================================================================
class _FakeSessionCM:
    def __enter__(self):
        return _SESSION

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def live_env(monkeypatch, tmp_path):
    """Hermetic _live_build rig: the session bracket, seeding, the walk, the
    delete/verify helpers and the browser-version guards are all scripted."""
    import browser_manager as bm

    monkeypatch.setattr(bm, "headless_guard", lambda: None)
    monkeypatch.setattr(bm, "assert_agent_browser_version", lambda env=None: None)
    monkeypatch.setattr(bm, "browser_session", lambda slug=None: _FakeSessionCM())
    monkeypatch.setattr(fb, "_seed_and_land",
                        lambda s, loc, root: {"landed": "app:/dashboard"})
    monkeypatch.setattr(fb, "_screenshot", lambda s, p: None)
    monkeypatch.setattr(fb, "_close_session", lambda loc: None)
    monkeypatch.setattr(fb, "_write_json", lambda p, d: None)

    calls = {"delete": [], "verify": []}
    monkeypatch.setattr(
        fb, "_delete_form",
        lambda s, loc, fid, name, actual_title="": (
            calls["delete"].append(fid),
            {"deleted": True, "verified_gone": True})[1])
    monkeypatch.setattr(
        fb, "_verify_no_residue",
        lambda s, loc, name, possible_unnamed_orphan=False: (
            calls["verify"].append(name), {"deleted": False})[1])
    monkeypatch.setattr(fb, "_ghl_verify_available", lambda: False)

    plan = {"location_id": "L", "form_name": "ZHC S06 Acceptance",
            "default_fields_keep": [], "fields": []}
    return {"plan": plan, "calls": calls, "root": str(tmp_path)}


def _run_live(monkeypatch, live_env, walk):
    monkeypatch.setattr(fb, "_walk_click_list", walk)
    return fb._live_build({"stop_after_phase": ""}, live_env["plan"],
                          {"steps": []}, [], {"tags": []}, {"pass": True},
                          live_env["root"], 0.0)


class TestLiveBuildCleanupPolicy:
    def test_success_preserves_the_created_form(self, monkeypatch, live_env):
        """THE HAZARD: a plain success must leave the form READABLE. The pre-fix
        finally deleted it, so form_id/form_url/embed_code named a dead object."""
        def _ok_walk(*a, **k):
            a[7]["form_id"] = "form-abc"          # walk_state, positional
            a[7]["actual_title"] = "ZHC S06 Acceptance"
            return {"form_id": "form-abc", "form_url": "https://x/widget/form/abc",
                    "embed_snippet": "<script src=x></script>",
                    "actual_title": "ZHC S06 Acceptance"}

        out = _run_live(monkeypatch, live_env, _ok_walk)
        assert live_env["calls"]["delete"] == [], (
            "a SUCCESSFUL build must NOT delete its own deliverable")
        assert out["cleanup"]["attempted"] is False
        assert out["cleanup"]["preserved"] is True
        assert out["cleanup"]["form_id"] == "form-abc"
        assert out["form_id"] == "form-abc" and out["form_url"].endswith("/abc")

    def test_failure_deletes_what_the_run_created(self, monkeypatch, live_env):
        """The cleanup path that still exists: a STOP mid-walk deletes the form
        (present → absent proof) and reports it."""
        def _fail_walk(*a, **k):
            a[7]["form_id"] = "form-xyz"
            a[7]["actual_title"] = "ZHC S06 Acceptance"
            raise fb.StopAndReport("F5.drag", "tile would not place")

        out = _run_live(monkeypatch, live_env, _fail_walk)
        assert live_env["calls"]["delete"] == ["form-xyz"], (
            "a FAILED run must clean up after itself")
        assert out["cleanup"]["deleted"] is True
        assert out["stop_step"] == "F5.drag"

    def test_stop_after_phase_still_preserves_for_resume(self, monkeypatch, live_env):
        """Unchanged contract: --stop-after-phase leaves the form for --resume."""
        import ghl_run_state

        def _stop_walk(*a, **k):
            a[7]["form_id"] = "form-half"
            raise ghl_run_state.StopAfterPhase("F5")

        out = _run_live(monkeypatch, live_env, _stop_walk)
        assert live_env["calls"]["delete"] == []
        assert out["stopped_after_phase"] == "F5"
        assert out["cleanup"]["attempted"] is False


# ===========================================================================
# 4. PREFLIGHT robust under `python3 -I`
# ===========================================================================
class TestPreflightUnderIsolatedInterpreter:
    def test_sibling_import_survives_python_dash_I(self):
        """The module must put its OWN directory on sys.path before the soft
        sibling imports, so `-I` (which drops sys.path[0] AND PYTHONPATH) cannot
        turn ghl_iframe_drag into a false-negative."""
        src = (_TOOLS_DIR / "ghl_form_builder.py").read_text(encoding="utf-8")
        boot = src.index("_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))")
        first_sibling = src.index("import ghl_builder")
        assert boot < first_sibling, (
            "the tools/ dir must be bootstrapped BEFORE the sibling imports")

    def test_dash_I_run_reports_playwright_ok_not_a_false_fail(self):
        """THE TRAP: `python3 -I` used to report pass=False. Under the fix it must
        agree with the non-isolated run. Skips honestly when this box has no
        Playwright at all (then both runs agree on fail — also correct)."""
        script = (
            "import json, sys, os;"
            f"sys.path.insert(0, {str(_TOOLS_DIR)!r});"
            "import ghl_form_builder as fb;"
            "t={'location_id':'TESTLOCATION12345678','form_name':'ZHC Test Form'};"
            "f=fb._resolve_fields(t);"
            "d=fb.plan_dependencies(f,t,existing_field_keys=[],existing_tags=[]);"
            "p=fb._run_preflight(t,f,d,live=True);"
            "print(json.dumps({'pass':p['pass'],"
            "'isolated':fb._isolated_mode(),"
            "'fp9':[c for c in p['checks'] "
            "if c['check']=='F-P9:playwright_interpreter'][0]}))"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        env.setdefault("MODEL_ROUTER_DEFAULT", "selftest-default:cloud")
        iso = subprocess.run([sys.executable, "-I", "-c", script],
                             capture_output=True, text=True, timeout=120, env=env)
        plain = subprocess.run([sys.executable, "-c", script],
                              capture_output=True, text=True, timeout=120, env=env)
        assert iso.returncode == 0, f"-I run crashed: {iso.stderr[-600:]}"
        assert plain.returncode == 0, f"plain run crashed: {plain.stderr[-600:]}"
        a = json.loads(iso.stdout.strip().splitlines()[-1])
        b = json.loads(plain.stdout.strip().splitlines()[-1])
        assert a["fp9"]["pass"] == b["fp9"]["pass"], (
            "F-P9 must reach the SAME verdict with and without -I "
            f"(isolated={a['fp9']['detail']!r} vs plain={b['fp9']['detail']!r})")

    def test_isolated_mode_detects_isolation_and_reports_it_honestly(self, monkeypatch):
        """When Playwright genuinely IS missing, the message must NOT blame
        isolation it did not cause — and when isolation IS present it says so."""
        class _Stub:
            PLAYWRIGHT_AVAILABLE = False

        monkeypatch.setattr(fb, "ghl_iframe_drag", _Stub)
        monkeypatch.setattr(fb, "_isolated_mode", lambda: True)
        t = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form"}
        f = fb._resolve_fields(t)
        d = fb.plan_dependencies(f, t, existing_field_keys=[], existing_tags=[])
        pre = fb._run_preflight(t, f, d, live=True)
        fp9 = [c for c in pre["checks"]
               if c["check"] == "F-P9:playwright_interpreter"][0]
        assert fp9["pass"] is False, "a REAL Playwright miss must still hard-fail"
        assert "ISOLATED interpreter" in fp9["detail"], (
            "the isolation context must be reported so the miss is diagnosable")
        assert "-I" in fp9["detail"]

    def test_preflight_passes_when_playwright_present_under_isolation(self, monkeypatch):
        """The false-negative itself: isolation + Playwright importable ⇒ PASS."""
        class _Stub:
            PLAYWRIGHT_AVAILABLE = True

        monkeypatch.setattr(fb, "ghl_iframe_drag", _Stub)
        monkeypatch.setattr(fb, "_isolated_mode", lambda: True)
        t = {"location_id": "TESTLOCATION12345678", "form_name": "ZHC Test Form"}
        f = fb._resolve_fields(t)
        d = fb.plan_dependencies(f, t, existing_field_keys=[], existing_tags=[])
        pre = fb._run_preflight(t, f, d, live=True)
        fp9 = [c for c in pre["checks"]
               if c["check"] == "F-P9:playwright_interpreter"][0]
        assert fp9["pass"] is True
        assert "ISOLATED interpreter" in fp9["detail"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
