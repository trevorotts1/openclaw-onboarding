"""F5 (SKILL-6-BULLETPROOF-SPEC-v1) — uniform 30-min keepalive + pre-phase
token re-mint, asserted as WIRED (not just importable) across every live
browser builder + the session layer.

The reactive half (inject-ghl-auth.sh's ONE bounded 401 re-mint) already had
tests. What was NOT proven anywhere: (a) that `SessionKeepalive.due()` pings
are actually threaded through every phase of a build — the survey builder's
Part-2 phases (A-K) had ZERO due() calls despite Part 1 having them, and the
form builder IMPORTED `SessionKeepalive`/`RateGovernor` but never constructed
or called either (a dead import); (b) that a NEW, PROACTIVE pre-phase re-mint
(v2_dispatcher.TokenAgeGate / remint_if_stale) exists and is unit-testable
without a real browser/subprocess; (c) that inject-ghl-auth.sh stamps the
auth-age clock browser_manager.sh now exposes, on every confirmed seed.

All checks here are STATIC (source reads) or HERMETIC (pure Python / a
stubbed `bash browser_manager.sh` with no real agent-browser) — no live GHL
account, no real browser, no secret.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_INJECT_SH = _TOOLS_DIR / "inject-ghl-auth.sh"
_SURVEY_PY = _TOOLS_DIR / "ghl_survey_builder.py"
_FORM_PY = _TOOLS_DIR / "ghl_form_builder.py"
_GATES_JSON = _TOOLS_DIR / "gates.json"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import v2_dispatcher as disp  # noqa: E402


def _read(p: Path) -> str:
    assert p.exists(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) v2_dispatcher: TokenAgeGate is pure, unit-testable decision logic
# ---------------------------------------------------------------------------

class TestTokenAgeGate:
    def test_fresh_age_is_not_stale(self):
        gate = disp.TokenAgeGate(threshold_s=2700)
        assert gate.is_stale(0) is False
        assert gate.is_stale(2699) is False

    def test_age_at_or_past_threshold_is_stale(self):
        gate = disp.TokenAgeGate(threshold_s=2700)
        assert gate.is_stale(2700) is True
        assert gate.is_stale(99999) is True

    def test_unknown_age_negative_is_always_stale(self):
        """age_s < 0 (no stamp found / read failed) MUST fail toward a
        re-mint, never toward trusting an unconfirmed session."""
        gate = disp.TokenAgeGate(threshold_s=2700)
        assert gate.is_stale(-1) is True

    def test_default_threshold_is_45_minutes(self):
        assert disp.TOKEN_PRE_PHASE_REMINT_THRESHOLD_S == 45 * 60
        assert disp.TokenAgeGate().threshold_s == 45 * 60


# ---------------------------------------------------------------------------
# (b) remint_if_stale: dependency-injected age_reader — no subprocess required
#     to prove the branch logic (fresh => no-op; stale => attempts a remint).
# ---------------------------------------------------------------------------

class TestRemintIfStale:
    def test_fresh_session_never_shells_out(self, monkeypatch):
        calls = {"n": 0}

        def _fake_reader(session, tools_dir):
            return 10.0  # very fresh

        def _boom(*a, **k):  # pragma: no cover - must never be called
            calls["n"] += 1
            raise AssertionError("subprocess.run must not fire for a fresh session")

        monkeypatch.setattr(disp.subprocess, "run", _boom)
        ran = disp.remint_if_stale("sess", tools_dir=str(_TOOLS_DIR), age_reader=_fake_reader)
        assert ran is False
        assert calls["n"] == 0

    def test_stale_session_attempts_remint(self, monkeypatch):
        seen = []

        class _FakeCompleted:
            def __init__(self, rc):
                self.returncode = rc
                self.stdout = ""
                self.stderr = ""

        def _fake_run(cmd, **kwargs):
            seen.append(cmd)
            return _FakeCompleted(0)

        def _fake_reader(session, tools_dir):
            return 99999.0  # very stale

        monkeypatch.setattr(disp.subprocess, "run", _fake_run)
        ran = disp.remint_if_stale("sess", tools_dir=str(_TOOLS_DIR), age_reader=_fake_reader)
        assert ran is True
        # both the seed-mint AND the re-seed/activate steps ran
        assert any("seed-ghl-auth.py" in " ".join(c) for c in seen)
        assert any("inject-ghl-auth.sh" in " ".join(c) for c in seen)

    def test_unknown_age_treated_as_stale(self, monkeypatch):
        def _fake_reader(session, tools_dir):
            return -1.0

        called = {"n": 0}

        class _FakeCompleted:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, **kwargs):
            called["n"] += 1
            return _FakeCompleted()

        monkeypatch.setattr(disp.subprocess, "run", _fake_run)
        disp.remint_if_stale("sess", tools_dir=str(_TOOLS_DIR), age_reader=_fake_reader)
        assert called["n"] >= 1

    def test_remint_failure_is_swallowed_never_raises(self, monkeypatch):
        def _fake_reader(session, tools_dir):
            return 99999.0

        def _explode(*a, **k):
            raise RuntimeError("simulated subprocess failure")

        monkeypatch.setattr(disp.subprocess, "run", _explode)
        # must not raise — a proactive remint failure is never fatal (F5-b doctrine)
        ran = disp.remint_if_stale("sess", tools_dir=str(_TOOLS_DIR), age_reader=_fake_reader)
        assert ran is False

    def test_read_auth_age_s_never_raises_on_missing_script(self):
        age = disp.read_auth_age_s("nosuch-session", tools_dir="/nonexistent/tools/dir")
        assert age == -1.0


# ---------------------------------------------------------------------------
# (c) browser_manager.sh: bm_record_auth_seeded / bm_auth_age_s / bm_auth_is_stale
#     — hermetic, no real agent-browser needed (pure file-stamp arithmetic).
# ---------------------------------------------------------------------------

class TestBrowserManagerAuthAge:
    def _env(self, tmp_path):
        lockdir = tmp_path / "lockdir"
        return dict(
            os.environ,
            TMPDIR=str(lockdir),
            HOME=str(tmp_path / "home"),  # keep durable-root detection out of the real box
            GHL_LOCATION_ID="keepaliveloc",
        )

    def test_no_stamp_reads_as_unknown_negative_one(self, tmp_path):
        env = self._env(tmp_path)
        res = subprocess.run(
            ["bash", str(_MANAGER_SH), "auth-age", "--", "ghl-skill6-keepaliveloc"],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert res.returncode == 0
        assert res.stdout.strip() == "-1"

    def test_record_then_age_is_small_nonnegative(self, tmp_path):
        env = self._env(tmp_path)
        session = "ghl-skill6-keepaliveloc"
        rec = subprocess.run(
            ["bash", "-c",
             f'source "{_MANAGER_SH}"; bm_record_auth_seeded "{session}"'],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert rec.returncode == 0, rec.stderr
        age = subprocess.run(
            ["bash", str(_MANAGER_SH), "auth-age", "--", session],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert age.returncode == 0
        val = int(age.stdout.strip())
        assert 0 <= val < 10  # just stamped — must read back as ~0s, never negative

    def test_auth_stale_verb_exit_codes(self, tmp_path):
        env = self._env(tmp_path)
        session = "ghl-skill6-keepaliveloc"
        # no stamp yet -> STALE -> exit 0
        stale = subprocess.run(
            ["bash", str(_MANAGER_SH), "auth-stale", "--", session],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert stale.returncode == 0
        assert "STALE" in stale.stdout
        # record a fresh stamp -> FRESH -> exit 1
        subprocess.run(
            ["bash", "-c", f'source "{_MANAGER_SH}"; bm_record_auth_seeded "{session}"'],
            capture_output=True, text=True, env=env, timeout=20,
        )
        fresh = subprocess.run(
            ["bash", str(_MANAGER_SH), "auth-stale", "--", session],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert fresh.returncode == 1
        assert "FRESH" in fresh.stdout

    def test_threshold_is_env_overridable(self, tmp_path):
        env = self._env(tmp_path)
        env["AB_AUTH_REMINT_THRESHOLD_S"] = "1"  # 1 second — trivially stale almost instantly
        session = "ghl-skill6-keepaliveloc"
        subprocess.run(
            ["bash", "-c", f'source "{_MANAGER_SH}"; bm_record_auth_seeded "{session}"'],
            capture_output=True, text=True, env=env, timeout=20,
        )
        import time as _t
        _t.sleep(1.2)
        stale = subprocess.run(
            ["bash", str(_MANAGER_SH), "auth-stale", "--", session],
            capture_output=True, text=True, env=env, timeout=20,
        )
        assert stale.returncode == 0, "a 1s threshold + 1.2s sleep must read STALE"


# ---------------------------------------------------------------------------
# (d) inject-ghl-auth.sh: stamps bm_record_auth_seeded on a confirmed seed
# ---------------------------------------------------------------------------

class TestInjectStampsAuthAge:
    def test_inject_calls_bm_record_auth_seeded(self):
        src = _read(_INJECT_SH)
        assert re.search(r'^\s*bm_record_auth_seeded\s+"\$SESSION"', src, re.MULTILINE), (
            "inject-ghl-auth.sh must stamp bm_record_auth_seeded on every "
            "confirmed seed+activate (F5-b) — the pre-phase re-mint check has "
            "nothing to measure age against otherwise."
        )
        # the stamp call must be AFTER the retry driver's success fall-through
        # (both the first-attempt AND the one bounded remint reach it), and
        # BEFORE the final echoes report success to the caller.
        stamp_pos = src.index('bm_record_auth_seeded "$SESSION"')
        echo_pos = src.index('echo "$INJECT_RESULT"')
        driver_pos = src.index("CURRENT_SEED_FILE=\"$SEED_FILE\"")
        assert driver_pos < stamp_pos < echo_pos


# ---------------------------------------------------------------------------
# (e) ghl_survey_builder.py: Part-2 phases A-K each fire the uniform check
#     (previously ONLY Part-1's per-field loop had a keepalive.due() call).
# ---------------------------------------------------------------------------

class TestSurveyBuilderPrePhaseWired:
    def test_pre_phase_check_helper_exists(self):
        src = _read(_SURVEY_PY)
        assert "def _pre_phase_check(" in src

    def test_pre_phase_check_calls_keepalive_and_remint(self):
        src = _read(_SURVEY_PY)
        fn = src[src.index("def _pre_phase_check("):]
        fn = fn[:fn.index("\n\n\n")]  # up to the next top-level blank-blank break
        assert "keepalive.due()" in fn
        assert "remint_if_stale(" in fn

    def test_remint_if_stale_is_imported(self):
        src = _read(_SURVEY_PY)
        assert re.search(r"from v2_dispatcher import .*remint_if_stale", src)

    @pytest.mark.parametrize("phase_letter", list("ABCDEFGHJK"))
    def test_every_part2_phase_calls_pre_phase_check(self, phase_letter):
        """Each of Phase A..K (skipping I, matching the codebase's own PRD
        lettering) must be preceded by `_pre_phase_check(session, keepalive)`
        — this is the exact gap that let a long survey (many required-toggle
        / conditional-logic slides) run Part 2 end-to-end with ZERO keepalive
        pings, risking the session-death failure on a long build."""
        src = _read(_SURVEY_PY)
        marker = f"# ── Part 2: Phase {phase_letter} —"
        assert marker in src, f"phase marker missing: {marker!r}"
        idx = src.index(marker)
        # the pre-phase check call must appear on the line immediately AFTER
        # this phase's comment marker (before that phase's own steps run).
        following = src[idx:]
        next_lines = "\n".join(following.splitlines()[1:2])
        assert "_pre_phase_check(session, keepalive)" in next_lines, (
            f"Phase {phase_letter} has no _pre_phase_check call immediately "
            f"after its marker — found instead: {next_lines!r}"
        )


# ---------------------------------------------------------------------------
# (f) ghl_form_builder.py: the PREVIOUSLY DEAD SessionKeepalive/RateGovernor
#     import is now actually constructed and called inside the click-list walk.
# ---------------------------------------------------------------------------

class TestFormBuilderKeepaliveWired:
    def test_imports_remint_if_stale(self):
        src = _read(_FORM_PY)
        assert "remint_if_stale as _real_remint_if_stale" in src

    def test_keepalive_is_constructed_in_the_walk(self):
        src = _read(_FORM_PY)
        assert "_RealKeepalive()" in src, (
            "ghl_form_builder.py imported SessionKeepalive but never "
            "constructed an instance anywhere — the F5 dead-import gap."
        )

    def test_pre_phase_check_called_on_phase_transition(self):
        src = _read(_FORM_PY)
        walk_src = src[src.index("def _walk_click_list("):]
        assert "if phase != _last_phase[0]:" in walk_src
        assert "_pre_phase_check(session, _keepalive)" in walk_src

    def test_pre_phase_check_helper_never_raises_when_keepalive_none(self, monkeypatch):
        """keepalive=None must be a true no-op for the ping half. The remint
        half is stubbed here (never shell out to a real seed/browser from a
        unit test — no live GHL account touched, no secret needed) to prove
        ONLY that a raising remint helper is swallowed, not propagated."""
        sys.path.insert(0, str(_TOOLS_DIR))
        import ghl_form_builder as fb  # noqa: E402

        def _boom(session):
            raise RuntimeError("simulated remint failure — must be swallowed")

        monkeypatch.setattr(fb, "_real_remint_if_stale", _boom)
        fb._pre_phase_check("nonexistent-session", None)  # must not raise
