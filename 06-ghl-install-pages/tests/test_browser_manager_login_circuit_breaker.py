"""SESSION-EXPIRED (GHL login-bounce) circuit breaker — Skill 06.

INCIDENT (2026-07-30, operator box): a live securetoken exchange confirmed the
GHL Firebase ID token is a hard ONE-HOUR expiry (`expires_in: 3600`). When it
lapsed mid-build, navigation silently bounced to app.gohighlevel.com/login
instead of the requested page, and nothing detected it — the caller kept
retrying against a session that could never self-recover, opening a NEW
Chrome page every cycle. These tests prove the fix in two layers:

  (A) PURE Python (browser_manager.py) — classify_login_check_result,
      bounded_retry, bounded_retry_with_reseed. No subprocess, no browser,
      fully hermetic, exercised with fake stub callables.

  (B) SHELL integration (browser_manager.sh) — the LIVE gateway wiring
      (_bm_login_state, _bm_guard_session_or_heal, _bm_self_heal_reseed,
      bm_ensure's open-retry loop, the `open` verb passthrough), exercised
      against STUBBED agent-browser / seed-ghl-auth.py / inject-ghl-auth.sh
      binaries. NO real browser is ever spawned, NO real credential is ever
      read, minted, or written — every "seed file" is a fixture string.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
_MANAGER_SH = _TOOLS_DIR / "browser_manager.sh"
_MANAGER_PY = _TOOLS_DIR / "browser_manager.py"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import browser_manager as bm  # noqa: E402


# ===========================================================================
# (A) PURE PYTHON — classify + bounded_retry + bounded_retry_with_reseed
# ===========================================================================

class TestClassifyLoginCheckResult:
    def test_ok(self):
        assert bm.classify_login_check_result("app:/dashboard") == "OK"

    def test_session_expired(self):
        assert bm.classify_login_check_result("login:/login") == "SESSION_EXPIRED"

    def test_unknown_empty(self):
        assert bm.classify_login_check_result("") == "UNKNOWN"
        assert bm.classify_login_check_result(None) == "UNKNOWN"

    def test_unknown_garbage_is_never_treated_as_expired(self):
        # An inconclusive read (timeout string, truncated output) must NOT
        # manufacture a false SESSION_EXPIRED positive.
        assert bm.classify_login_check_result("TIMEOUT") == "UNKNOWN"


class TestIsLoginUrl:
    def test_login_path(self):
        assert bm.is_login_url("https://app.gohighlevel.com/login")

    def test_logout_marker(self):
        assert bm.is_login_url("https://app.convertandflow.com/?logout=true")

    def test_domain_agnostic(self):
        # GHL is white-labeled — detection must not hinge on the hostname.
        assert bm.is_login_url("https://client-custom-domain.example.com/login")

    def test_normal_app_url_is_not_login(self):
        assert not bm.is_login_url(
            "https://app.gohighlevel.com/location/abc123/contacts/smart_list/all"
        )

    def test_empty_or_none(self):
        assert not bm.is_login_url("")
        assert not bm.is_login_url(None)


class TestSessionExpiredMessage:
    def test_names_session_and_remedy(self):
        msg = bm.session_expired_message("ghl-skill6-fixtureloc")
        assert "ghl-skill6-fixtureloc" in msg
        assert "seed-ghl-auth.py" in msg
        assert "inject-ghl-auth.sh" in msg
        assert "TERMINAL" in msg

    def test_never_contains_token_shaped_content(self):
        # The message is 100% static text plus a session name/profile hint —
        # never anything that could be a token/cookie value.
        msg = bm.session_expired_message("s", profile_hint="PROFILE_X")
        assert "PROFILE_X" in msg
        # No base64-ish long opaque blob patterns.
        import re as _re
        assert not _re.search(r"[A-Za-z0-9_-]{40,}", msg)


class TestBoundedRetry:
    def test_happy_path_single_call_no_sleep(self):
        calls = []
        sleeps = []

        def fn(attempt):
            calls.append(attempt)
            return "ok"

        result = bm.bounded_retry(fn, max_attempts=3, sleep=sleeps.append)
        assert result == "ok"
        assert calls == [1]
        assert sleeps == [], "happy path must never sleep/retry"

    def test_transient_recovers_within_cap(self):
        calls = []
        sleeps = []

        def fn(attempt):
            calls.append(attempt)
            if attempt < 3:
                raise ConnectionError("blip")
            return "recovered"

        result = bm.bounded_retry(fn, max_attempts=5, base_delay=2.0, sleep=sleeps.append)
        assert result == "recovered"
        assert calls == [1, 2, 3]
        # exponential backoff: base*2^0, base*2^1
        assert sleeps == [2.0, 4.0]

    def test_permanently_failing_stub_terminates_after_exact_attempt_count(self):
        calls = []
        sleeps = []

        def fn(attempt):
            calls.append(attempt)
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails"):
            bm.bounded_retry(fn, max_attempts=4, base_delay=1.0, sleep=sleeps.append)
        # UNBOUNDED-LOOP PROOF: exactly max_attempts calls, never more.
        assert calls == [1, 2, 3, 4], f"expected exactly 4 bounded attempts, got {calls}"
        assert sleeps == [1.0, 2.0, 4.0], "3 backoff sleeps between 4 attempts, exponential"

    def test_session_expired_short_circuits_zero_retry_zero_sleep(self):
        calls = []
        sleeps = []

        def fn(attempt):
            calls.append(attempt)
            raise bm.SessionExpiredError("login bounce")

        with pytest.raises(bm.SessionExpiredError):
            bm.bounded_retry(fn, max_attempts=5, sleep=sleeps.append)
        # PROVE THE "ONCE": exactly one call, no sleep, no second attempt.
        assert calls == [1], f"session-expired must fail ONCE, got {len(calls)} attempts: {calls}"
        assert sleeps == [], "session-expired must never sleep/retry"


class TestBoundedRetryWithReseed:
    """Mirrors the shell gateway's _bm_guard_session_or_heal /
    _bm_self_heal_reseed semantics: detect -> ONE capped re-seed -> retry
    ONCE -> terminal if still expired or the re-seed itself failed."""

    def test_happy_path_reseed_never_called(self):
        op_calls = []
        reseed_calls = []

        def operation():
            op_calls.append(1)
            return "app:/dashboard"

        def check_session(result):
            return bm.classify_login_check_result(result)

        def reseed():
            reseed_calls.append(1)
            return True

        result = bm.bounded_retry_with_reseed(
            operation, check_session=check_session, reseed=reseed,
        )
        assert result == "app:/dashboard"
        assert len(op_calls) == 1
        assert len(reseed_calls) == 0, "a healthy session must never trigger a re-seed"

    def test_expired_session_working_reseed_recovers_exactly_once(self):
        op_calls = []
        reseed_calls = []
        state = {"expired": True}

        def operation():
            op_calls.append(1)
            return "login:/login" if state["expired"] else "app:/dashboard"

        def reseed():
            reseed_calls.append(1)
            state["expired"] = False  # simulates a successful mint+inject
            return True

        result = bm.bounded_retry_with_reseed(
            operation,
            check_session=bm.classify_login_check_result,
            reseed=reseed,
        )
        assert result == "app:/dashboard"
        assert len(op_calls) == 2, "expect exactly 2 operation calls (original + one retry)"
        assert len(reseed_calls) == 1, "expect EXACTLY ONE re-seed attempt"

    def test_expired_session_failing_reseed_stops_with_exactly_one_attempt(self):
        op_calls = []
        reseed_calls = []

        def operation():
            op_calls.append(1)
            return "login:/login"

        def reseed():
            reseed_calls.append(1)
            return False  # mint/inject failed

        with pytest.raises(bm.SessionExpiredError, match="re-seed FAILED"):
            bm.bounded_retry_with_reseed(
                operation, check_session=bm.classify_login_check_result, reseed=reseed,
            )
        assert len(op_calls) == 1, "must NOT retry the operation after a failed re-seed"
        assert len(reseed_calls) == 1, "must attempt the re-seed exactly once, never twice"

    def test_still_expired_after_successful_reseed_stops_no_second_reseed(self):
        """The re-seed itself reports success, but the session is STILL on
        the login page afterward (e.g. cookies wrote but the token was
        already dead) — this must stop, NOT attempt a second re-seed."""
        op_calls = []
        reseed_calls = []

        def operation():
            op_calls.append(1)
            return "login:/login"  # never recovers, even after "successful" reseed

        def reseed():
            reseed_calls.append(1)
            return True

        with pytest.raises(bm.SessionExpiredError, match="still expired"):
            bm.bounded_retry_with_reseed(
                operation, check_session=bm.classify_login_check_result, reseed=reseed,
            )
        assert len(op_calls) == 2
        assert len(reseed_calls) == 1, "one re-seed reported success — must NOT try a second"

    def test_transient_exception_retries_independent_of_reseed_budget(self):
        """A transient exception (not a login classification) must still use
        the ordinary bounded-retry path, untouched by the re-seed cap."""
        op_calls = []
        reseed_calls = []

        def operation():
            op_calls.append(1)
            if len(op_calls) < 2:
                raise TimeoutError("network blip")
            return "app:/dashboard"

        def reseed():
            reseed_calls.append(1)
            return True

        result = bm.bounded_retry_with_reseed(
            operation, check_session=bm.classify_login_check_result,
            reseed=reseed, sleep=lambda s: None,
        )
        assert result == "app:/dashboard"
        assert len(op_calls) == 2
        assert len(reseed_calls) == 0, "a transient blip must never spend the re-seed budget"

    def test_permanently_failing_transient_terminates(self):
        """UNBOUNDED-LOOP PROOF for the transient axis: a permanently
        failing (non-login) operation still terminates at max_transient_attempts."""
        op_calls = []

        def operation():
            op_calls.append(1)
            raise ConnectionError("dead network")

        with pytest.raises(ConnectionError):
            bm.bounded_retry_with_reseed(
                operation, check_session=bm.classify_login_check_result,
                reseed=lambda: True, max_transient_attempts=3, sleep=lambda s: None,
            )
        assert len(op_calls) == 3, f"expected exactly 3 bounded attempts, got {len(op_calls)}"


def test_py_compile():
    """Sanity: the module compiles cleanly (also run via py_compile in CI)."""
    import py_compile
    py_compile.compile(str(_MANAGER_PY), doraise=True)


# ===========================================================================
# (B) SHELL INTEGRATION — stubbed agent-browser / seed-ghl-auth.py /
#     inject-ghl-auth.sh. NO real browser, NO real credential, ever.
# ===========================================================================

_FAKE_AGENT_BROWSER = r"""#!/usr/bin/env bash
state_dir="${_FAKE_STATE_DIR:?_FAKE_STATE_DIR not set}"
log="$state_dir/argv.log"
echo "$@" >> "$log"
args="$*"
# Portable "last positional arg" (bash 3.2-safe, no ${@: -1}).
last=""
for last in "$@"; do :; done
case "$args" in
  *"session list --json"*)
    printf ""
    exit 0
    ;;
  *" open "*)
    n=0
    [ -f "$state_dir/open_calls" ] && n="$(cat "$state_dir/open_calls")"
    n=$((n + 1))
    echo "$n" > "$state_dir/open_calls"
    printf '%s\n' "$last" > "$state_dir/last_open_url"
    fail_first_n=0
    [ -f "$state_dir/open_fail_first_n" ] && fail_first_n="$(cat "$state_dir/open_fail_first_n")"
    if [ "$n" -le "$fail_first_n" ]; then
      exit 1
    fi
    exit 0
    ;;
  *" eval "*)
    # URL-aware: a TARGET (page-specific) url uses its own state file so a
    # test can simulate "the agency root is fine, but THIS page bounces" —
    # the exact incident shape (root open ok minutes ago, one specific page
    # independently expired/bounced). Anything else (the agency root, or no
    # open recorded yet) uses the general login_state fixture.
    last_url=""
    [ -f "$state_dir/last_open_url" ] && last_url="$(cat "$state_dir/last_open_url")"
    state="app"
    case "$last_url" in
      *"target-marker"*)
        state="login"
        [ -f "$state_dir/target_login_state" ] && state="$(cat "$state_dir/target_login_state")"
        ;;
      *)
        [ -f "$state_dir/login_state" ] && state="$(cat "$state_dir/login_state")"
        ;;
    esac
    if [ "$state" = "login" ]; then
      printf 'login:/login'
    else
      printf 'app:/dashboard'
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""

_FAKE_SEED_GHL_AUTH_PY = r"""#!/usr/bin/env python3
# TEST FIXTURE ONLY — never a real credential path. Simulates seed-ghl-auth.py's
# exit-code contract (0=minted, 2=no refresh token, 3=revoked/expired) and its
# --out file-write behavior, without any network call or real token.
import json
import os
import sys

state_dir = os.environ["_FAKE_STATE_DIR"]
calls_file = os.path.join(state_dir, "mint_calls")
n = 0
if os.path.exists(calls_file):
    n = int(open(calls_file).read().strip() or "0")
with open(calls_file, "w") as f:
    f.write(str(n + 1))

code = 0
code_file = os.path.join(state_dir, "mint_exit_code")
if os.path.exists(code_file):
    code = int(open(code_file).read().strip() or "0")

if code == 0:
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        out_path = args[args.index("--out") + 1]
    if out_path:
        with open(out_path, "w") as f:
            # Clearly-fake fixture payload — never a real id_token/refresh_token.
            json.dump({"fixture": True, "note": "TEST-ONLY, not a real credential"}, f)
        os.chmod(out_path, 0o600)
sys.exit(code)
"""

_FAKE_INJECT_GHL_AUTH_SH = r"""#!/usr/bin/env bash
state_dir="${_FAKE_STATE_DIR:?_FAKE_STATE_DIR not set}"
calls_file="$state_dir/inject_calls"
n=0
[ -f "$calls_file" ] && n="$(cat "$calls_file")"
echo $((n + 1)) > "$calls_file"

code=0
[ -f "$state_dir/inject_exit_code" ] && code="$(cat "$state_dir/inject_exit_code")"
if [ "$code" = "0" ]; then
  fixes="1"
  [ -f "$state_dir/inject_fixes_state" ] && fixes="$(cat "$state_dir/inject_fixes_state")"
  if [ "$fixes" = "1" ]; then
    # A real cookie/IndexedDB re-seed fixes auth GLOBALLY (cookies are not
    # per-page) — flip every state file the fake classifier can consult, not
    # just the one the test happens to be probing.
    echo "app" > "$state_dir/login_state"
    echo "app" > "$state_dir/target_login_state"
  fi
fi
exit "$code"
"""


def _write_exec(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class _Scaffold:
    """Isolated tmp scaffold: a COPY of the real browser_manager.sh alongside
    FAKE seed-ghl-auth.py / inject-ghl-auth.sh (so _bm_self_heal_reseed's
    `$self_dir/...` resolution finds them), plus a fake `agent-browser` on
    PATH. Nothing here is the real credential-handling code."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.tools_dir = tmp_path / "tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(_MANAGER_SH, self.tools_dir / "browser_manager.sh")
        _write_exec(self.tools_dir / "seed-ghl-auth.py", _FAKE_SEED_GHL_AUTH_PY)
        _write_exec(self.tools_dir / "inject-ghl-auth.sh", _FAKE_INJECT_GHL_AUTH_SH)

        self.bindir = tmp_path / "bin"
        self.bindir.mkdir(parents=True, exist_ok=True)
        _write_exec(self.bindir / "agent-browser", _FAKE_AGENT_BROWSER)

        self.state_dir = tmp_path / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lockdir = tmp_path / "lockdir"

    @property
    def manager_sh(self) -> Path:
        return self.tools_dir / "browser_manager.sh"

    def set(self, name: str, value: str) -> None:
        (self.state_dir / name).write_text(str(value), encoding="utf-8")

    def get(self, name: str, default: str = "0") -> str:
        p = self.state_dir / name
        return p.read_text(encoding="utf-8").strip() if p.exists() else default

    def env(self, **extra) -> dict:
        base = dict(
            os.environ,
            PATH=f"{self.bindir}:{os.environ.get('PATH', '')}",
            TMPDIR=str(self.lockdir),
            HOME=str(self.tmp_path),
            BM_DURABLE_ROOT_OVERRIDE="",
            GHL_LOCATION_ID="circuitloc",
            AB_MAX_SESSIONS="1",
            AB_LOCK_WAIT="5",
            AB_SESSION_TTL="60",
            AB_CALL_TIMEOUT="15",
            AB_REESEED_TIMEOUT_S="15",
            _FAKE_STATE_DIR=str(self.state_dir),
        )
        base.update(extra)
        return base

    def run_ensure(self, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(self.manager_sh), "ensure"],
            capture_output=True, text=True, env=self.env(), timeout=timeout,
        )

    def run_open(self, url: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(self.manager_sh), "open", "--", url],
            capture_output=True, text=True, env=self.env(), timeout=timeout,
        )


@pytest.fixture
def scaffold(tmp_path):
    return _Scaffold(tmp_path)


class TestHappyPathUnchanged:
    def test_ensure_ok_no_login_no_reseed(self, scaffold):
        scaffold.set("login_state", "app")  # already authenticated
        res = scaffold.run_ensure()
        assert res.returncode == 0, res.stderr
        assert scaffold.get("mint_calls") == "0", "a healthy session must never mint"
        assert scaffold.get("inject_calls") == "0", "a healthy session must never inject"


class TestSessionExpiredSelfHeal:
    def test_working_reseed_recovers_exactly_once(self, scaffold):
        scaffold.set("login_state", "login")   # starts expired
        scaffold.set("mint_exit_code", "0")
        scaffold.set("inject_exit_code", "0")
        scaffold.set("inject_fixes_state", "1")  # inject flips login_state -> app
        res = scaffold.run_ensure()
        assert res.returncode == 0, f"heal should recover: {res.stderr}"
        assert scaffold.get("mint_calls") == "1", "exactly ONE re-seed mint attempt"
        assert scaffold.get("inject_calls") == "1", "exactly ONE re-seed inject attempt"
        assert "self-heal" in res.stderr.lower()

    def test_failing_mint_stops_no_second_attempt_no_inject(self, scaffold):
        scaffold.set("login_state", "login")
        scaffold.set("mint_exit_code", "2")   # "no usable refresh token"
        res = scaffold.run_ensure()
        assert res.returncode != 0
        assert "no usable Firebase refresh token" in res.stderr
        assert scaffold.get("mint_calls") == "1", "must not retry a failed mint"
        assert scaffold.get("inject_calls") == "0", "must never inject after a failed mint"

    def test_revoked_token_marker_named(self, scaffold):
        scaffold.set("login_state", "login")
        scaffold.set("mint_exit_code", "3")   # revoked/expired refresh token
        res = scaffold.run_ensure()
        assert res.returncode != 0
        assert "REVOKED/EXPIRED" in res.stderr
        assert scaffold.get("mint_calls") == "1"
        assert scaffold.get("inject_calls") == "0"

    def test_mint_ok_inject_fails_stops_exactly_once(self, scaffold):
        scaffold.set("login_state", "login")
        scaffold.set("mint_exit_code", "0")
        scaffold.set("inject_exit_code", "1")  # activation failure
        res = scaffold.run_ensure()
        assert res.returncode != 0
        assert "activation FAILED" in res.stderr
        assert scaffold.get("mint_calls") == "1"
        assert scaffold.get("inject_calls") == "1", "must not retry inject either"

    def test_permanently_expired_terminates_no_infinite_loop(self, scaffold):
        """UNBOUNDED-LOOP PROOF: even when mint+inject both report SUCCESS but
        the session is STILL on the login page afterward (dead token that
        mints fine but never actually logs in), the gateway stops — it does
        NOT loop, does NOT re-mint again, does NOT open a second page."""
        scaffold.set("login_state", "login")
        scaffold.set("mint_exit_code", "0")
        scaffold.set("inject_exit_code", "0")
        scaffold.set("inject_fixes_state", "0")  # inject "succeeds" but state never flips
        res = scaffold.run_ensure()
        assert res.returncode != 0
        assert "STILL on the GHL login page" in res.stderr
        assert scaffold.get("mint_calls") == "1", "exactly one mint attempt, never more"
        assert scaffold.get("inject_calls") == "1", "exactly one inject attempt, never more"
        # Exactly one `open` of the agency root (bm_ensure's own open) — no
        # extra Chrome pages spawned chasing the dead session.
        argv_log = (scaffold.state_dir / "argv.log").read_text(encoding="utf-8")
        open_calls = sum(1 for line in argv_log.splitlines() if " open " in line)
        assert open_calls == 1, f"expected exactly ONE open call, got {open_calls}\n{argv_log}"

    def test_no_second_reseed_when_page_specific_open_also_bounces(self, scaffold):
        """The `open <target>` verb (a caller-specific page, distinct from
        bm_ensure's own agency-root open) shares the SAME one-reseed-per-
        operation budget. If bm_ensure's own open already spent it, a
        page-specific bounce must refuse immediately, not spend a second."""
        scaffold.set("login_state", "login")
        scaffold.set("mint_exit_code", "0")
        scaffold.set("inject_exit_code", "0")
        scaffold.set("inject_fixes_state", "0")  # heal never actually recovers
        res = scaffold.run_open("https://app.gohighlevel.com/location/x/contacts/smart_list/all")
        assert res.returncode != 0
        assert scaffold.get("mint_calls") == "1", "must not spend a second re-seed budget"
        assert scaffold.get("inject_calls") == "1"


class TestPageSpecificOpenSelfHeal:
    def test_open_verb_heals_and_reissues_target_open_once(self, scaffold):
        """bm_ensure's own agency-root open succeeds fine (already logged
        in); a SEPARATE, caller-specific TARGET page is what bounces to
        /login — the exact incident shape (root open ok, one specific page
        independently expired). The heal must fire on THIS open, then
        re-issue the SAME target URL exactly once more so the caller
        actually lands on the page it asked for — all within ONE process
        invocation (one `browser_manager.sh open <target>` call)."""
        scaffold.set("login_state", "app")          # agency root: fine
        scaffold.set("target_login_state", "login")  # THIS page: bounced
        scaffold.set("mint_exit_code", "0")
        scaffold.set("inject_exit_code", "0")
        scaffold.set("inject_fixes_state", "1")

        target = "https://app.gohighlevel.com/location/x/contacts/target-marker/all"
        res = scaffold.run_open(target)
        assert res.returncode == 0, res.stderr
        assert scaffold.get("mint_calls") == "1", "exactly ONE re-seed mint attempt"
        assert scaffold.get("inject_calls") == "1", "exactly ONE re-seed inject attempt"
        argv_log = (scaffold.state_dir / "argv.log").read_text(encoding="utf-8")
        target_opens = sum(1 for line in argv_log.splitlines() if target in line)
        assert target_opens == 2, (
            f"expected the target re-issued exactly once after the heal "
            f"(bounced once, landed once), got {target_opens}\n{argv_log}"
        )


class TestTransientOpenFailureStillBounded:
    def test_recovers_within_cap_exponential_backoff(self, scaffold, monkeypatch):
        scaffold.set("login_state", "app")
        scaffold.set("open_fail_first_n", "2")  # first 2 opens fail, 3rd succeeds
        env = scaffold.env(AB_OPEN_MAX_ATTEMPTS="4", AB_OPEN_RETRY_BASE_S="1")
        res = subprocess.run(
            ["bash", str(scaffold.manager_sh), "ensure"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert res.returncode == 0, res.stderr
        argv_log = (scaffold.state_dir / "argv.log").read_text(encoding="utf-8")
        open_calls = sum(1 for line in argv_log.splitlines() if " open " in line)
        assert open_calls == 3, f"expected exactly 3 open attempts, got {open_calls}"

    def test_permanently_failing_open_terminates_exact_attempt_count(self, scaffold):
        """UNBOUNDED-LOOP PROOF (pre-existing transient-open path): a
        permanently-failing `open` still terminates at AB_OPEN_MAX_ATTEMPTS,
        never spins forever."""
        scaffold.set("login_state", "app")
        scaffold.set("open_fail_first_n", "999")  # never succeeds
        env = scaffold.env(AB_OPEN_MAX_ATTEMPTS="3", AB_OPEN_RETRY_BASE_S="1")
        res = subprocess.run(
            ["bash", str(scaffold.manager_sh), "ensure"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert res.returncode != 0
        argv_log = (scaffold.state_dir / "argv.log").read_text(encoding="utf-8")
        open_calls = sum(1 for line in argv_log.splitlines() if " open " in line)
        assert open_calls == 3, f"expected exactly 3 bounded attempts, got {open_calls}"
        assert "after 3 attempt(s)" in res.stderr


class TestNoRecursiveSelfHealDuringInjectPreOpen:
    def test_guard_skips_when_nested_inside_own_heal(self, scaffold):
        """_bm_guard_session_or_heal must no-op when
        _BM_SELF_HEAL_IN_PROGRESS=1 is already set (the FAKE inject-ghl-
        auth.sh does not itself call bm_ensure, so this exercises the guard
        function directly rather than depending on the fixture script's
        internals)."""
        script = f'''
set -euo pipefail
source "{scaffold.manager_sh}"
_BM_SELF_HEAL_IN_PROGRESS=1
_bm_guard_session_or_heal "some-session"
echo "GUARD_RC=$?"
'''
        harness = scaffold.tmp_path / "nested_guard_harness.sh"
        harness.write_text(script, encoding="utf-8")
        scaffold.set("login_state", "login")  # would normally trigger a heal
        res = subprocess.run(
            ["bash", str(harness)],
            capture_output=True, text=True, env=scaffold.env(), timeout=30,
        )
        assert res.returncode == 0, res.stderr
        assert "GUARD_RC=0" in res.stdout
        assert scaffold.get("mint_calls") == "0", "nested guard must never self-heal"
        assert scaffold.get("inject_calls") == "0"


def test_shellcheck_no_new_warnings():
    """Static: my additions introduce no NEW shellcheck warnings vs. the
    pre-existing baseline (SC2155 on line ~546, bm_stale_env_preflight,
    predates this change)."""
    import shutil as _shutil
    if not _shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    res = subprocess.run(
        ["shellcheck", "-S", "warning", str(_MANAGER_SH)],
        capture_output=True, text=True, timeout=30,
    )
    warnings = [l for l in res.stdout.splitlines() if "SC" in l and "warning" in l]
    assert len(warnings) <= 1, f"unexpected new shellcheck warnings:\n{res.stdout}"


def test_bash_syntax_ok():
    res = subprocess.run(["bash", "-n", str(_MANAGER_SH)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
