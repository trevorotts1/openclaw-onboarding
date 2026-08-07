#!/usr/bin/env python3
"""browser_manager.py — Python analogue of browser_manager.sh, SCOPED to the
EMITTERS only.

SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
reaper backstop.

WHY THIS IS EMITTER-ONLY
------------------------
``ghl_builder.py`` and ``ghl_rest_canvas.py`` are pure EMITTERS: they build the
agent-browser command STRINGS / argv lists the agent runs, but they hold NO live
browser handle and spawn nothing (verified: no ``chromium.launch`` /
``launchPersistentContext`` in EITHER module). The live-process lifecycle
(lock, lease, TTL self-kill, pool ceiling, breaker, host reaper) lives in
``browser_manager.sh`` and ``scripts/agent-browser-reaper.sh``.

CORRECTION (U28 / B-U14 headless-guard coverage audit, 2026-07): the prior
version of this claim said no ``chromium.launch`` / ``launchPersistentContext``
call existed "anywhere in the repo Python" — that was STALE. One real site
exists: ``ghl_iframe_drag.py``'s offline cross-origin-drag self-test
(``_live_selftest``) spins up its own throwaway, fully-local Playwright
Chromium (two ``127.0.0.1``/``localhost`` HTTP fixtures, no agent-browser CLI,
no GHL location, no chokepoint involvement) to prove the drag mechanism
end-to-end. It hardcodes ``headless=True`` as a Python literal — it can never
read ``AGENT_BROWSER_HEADED`` and open a headed window — so it is
COMPLIANT-BY-CONSTRUCTION, not a D6 gap. It is still a REAL exception to the
"spawns nothing" claim above, which is why the U28 audit tool
(``headless_guard_audit.py``) sweeps for raw ``chromium.launch*`` sites on
every run instead of trusting this docstring going forward. This module's own
job is narrow but essential:

  1. Refuse to EMIT a browser command outside an active ``browser_session()``
     context — so a plan can never be assembled without a session bracket.
  2. Make the canonical session name the SINGLE source of truth on the Python
     side (mirrors ``bm_session_name`` in the shell gateway) — killing the
     22-distinct-name root cause from the emitter side too.
  3. Append a MANDATORY final ``close --session <s>`` teardown step to EVERY
     emitted plan (``emit_teardown_step``), so even a detach-and-exit run leaves
     no orphan: the plan itself carries its own teardown.
  4. Register ``atexit`` + SIGTERM/SIGINT/SIGHUP handlers that emit (NOT execute)
     the teardown step on interpreter exit — a belt for the brace above.

It performs NO live-process management (no kill, no Chromium handling) — that is
the reaper's job, by design (blast-radius safety).
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Callable, Iterator, Optional

# Version marker (kept in sync by scripts/bump-version.sh):
BROWSER_MANAGER_PY_VERSION = "v22.0.1"

# Tunables mirror browser_manager.sh / the ADVISORY openclaw.json
# browser.agentBrowser block (agent-browser ignores that config natively — the
# real cap lives in the manager + reaper, never in config).
AB_MAX_SESSIONS_DEFAULT = 1

# AB_SAVE_CONCURRENCY — parallel eval fan-out cap.  AB_MAX_SESSIONS STAYS 1.
# Hard upper bound is 5 (proven safe in the live 5-concurrent-eval test).
SAVE_CONCURRENCY_DEFAULT = 5
SAVE_CONCURRENCY_MIN = 1
SAVE_CONCURRENCY_MAX = 5


def save_concurrency(env: Optional[dict] = None) -> int:
    """Return the clamped save concurrency from the environment.

    Reads ``AB_SAVE_CONCURRENCY``; falls back to ``SAVE_CONCURRENCY_DEFAULT``
    (5).  Always returns an int in [``SAVE_CONCURRENCY_MIN``,
    ``SAVE_CONCURRENCY_MAX``] = [1, 5].  AB_MAX_SESSIONS STAYS 1.
    Mirrors ``bm_save_concurrency()`` in ``browser_manager.sh``."""
    env = env if env is not None else os.environ
    raw = env.get("AB_SAVE_CONCURRENCY", str(SAVE_CONCURRENCY_DEFAULT))
    try:
        n = int(raw)
    except (ValueError, TypeError):
        n = SAVE_CONCURRENCY_DEFAULT
    return max(SAVE_CONCURRENCY_MIN, min(SAVE_CONCURRENCY_MAX, n))


# ── D6 headless guard (Python side; mirrors ghl_builder.headless_guard) ───────
_HEADED_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})


def headless_guard(env: Optional[dict] = None) -> None:
    """REFUSE to proceed if a headed window could open (D6). Raises RuntimeError
    rather than ever risk taking over a screen. Same contract as
    ghl_builder.headless_guard (re-implemented to avoid a hard import cycle)."""
    env = env if env is not None else os.environ
    val = str(env.get("AGENT_BROWSER_HEADED", "")).strip().lower()
    if val not in _HEADED_OFF_VALUES:
        raise RuntimeError(
            "REFUSE (D6 headless guard): AGENT_BROWSER_HEADED is set to a headed "
            "value, which would open a VISIBLE browser window. Headless is "
            "mandatory. Run: unset AGENT_BROWSER_HEADED and always pass "
            "`--headed false`."
        )


# ── P2-4: agent-browser version-pin guard (Python side) ───────────────────────
# The command spellings used in render_check (``get html html``, ``screenshot``,
# ``console``) and the eval/snapshot JSON encoding were captured and proven
# against agent-browser 0.27.0.  An unverified upgrade can silently break those
# commands.  This guard REFUSES (RuntimeError) when the live binary drifts from
# the pinned version — exactly like the shell-side gate in inject-ghl-auth.sh —
# so mis-capturing can never happen silently.
#
# Override: set GHL_AB_ALLOW_VERSION_DRIFT=1 to downgrade to a WARN (risk
# acknowledged).  The pinned version is read from gates.json
# (agent_browser_version_pin.pinned_version) so the shell and Python sides share
# one source of truth; set GHL_AB_PINNED_VERSION to re-pin after a deliberate
# re-capture.

_GATES_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gates.json")


def _read_pinned_agent_browser_version(env: Optional[dict] = None) -> str:
    """Return the pinned agent-browser version string.

    Precedence (highest first):
      1. ``GHL_AB_PINNED_VERSION`` env var (operator override after re-capture).
      2. ``agent_browser_version_pin.pinned_version`` in ``gates.json``.
      3. Hard-coded fallback ``"0.27.0"`` (matches gates.json at ship time).
    """
    env = env if env is not None else os.environ
    if env.get("GHL_AB_PINNED_VERSION"):
        return str(env["GHL_AB_PINNED_VERSION"]).strip()
    try:
        with open(_GATES_JSON_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        version = data["agent_browser_version_pin"]["pinned_version"]
        if version and isinstance(version, str):
            return version.strip()
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        pass
    return "0.27.0"


def _read_live_agent_browser_version() -> Optional[str]:
    """Run ``agent-browser --version`` and extract the semver string.

    Returns the version string (e.g. ``"0.27.0"``) or ``None`` when the binary
    is absent or its output does not contain a recognisable semver."""
    try:
        result = subprocess.run(
            ["agent-browser", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw = (result.stdout or result.stderr or "").strip()
        match = re.search(r"\d+\.\d+\.\d+", raw)
        if match:
            return match.group(0)
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def assert_agent_browser_version(env: Optional[dict] = None) -> None:
    """REFUSE when the live agent-browser version drifts from the pin (P2-4).

    The command spellings proven against agent-browser 0.27.0 — ``get html html``,
    ``screenshot``, and ``console`` — are NOT guaranteed stable across versions.
    A silent drift would mis-capture rendered HTML, screenshots, or console logs
    without any error, defeating the render_check gate entirely.

    Behaviour:
      * Live version matches pin  → no-op (fast path).
      * Live version unreadable + ``GHL_AB_ALLOW_VERSION_DRIFT=1``
          → WARN to stderr, proceed.
      * Live version unreadable (no override)
          → REFUSE (RuntimeError, exit-70 contract).
      * Version mismatch + ``GHL_AB_ALLOW_VERSION_DRIFT=1``
          → WARN to stderr, proceed.
      * Version mismatch (no override)
          → REFUSE (RuntimeError, exit-70 contract).

    Called automatically by ``browser_session()``; callers that drive the
    browser without a session context may call it explicitly."""
    env = env if env is not None else os.environ
    allow_drift = str(env.get("GHL_AB_ALLOW_VERSION_DRIFT", "")).strip() not in (
        "", "0", "false", "no", "off"
    )
    pinned = _read_pinned_agent_browser_version(env)
    live = _read_live_agent_browser_version()

    if live is None:
        msg = (
            f"REFUSE (P2-4 version-pin guard): could not determine agent-browser "
            f"version. This flow is PINNED to {pinned}; an unverifiable engine "
            f"cannot be trusted. Set GHL_AB_ALLOW_VERSION_DRIFT=1 to override "
            f"(operator-acknowledged, risk accepted). STOP."
        )
        if allow_drift:
            sys.stderr.write(
                f"[browser_manager] WARN (P2-4): could not read agent-browser "
                f"version; GHL_AB_ALLOW_VERSION_DRIFT=1 — proceeding unpinned "
                f"(risk acknowledged). Pinned version: {pinned}\n"
            )
            return
        raise RuntimeError(msg)

    if live == pinned:
        return  # fast path — versions match, all good

    msg = (
        f"REFUSE (P2-4 version-pin guard): agent-browser version drift — "
        f"found {live}, pinned {pinned}. The render_check command spellings "
        f"(`get html html`, `screenshot`, `console`) and eval/snapshot semantics "
        f"were captured against {pinned}; an unverified upgrade can silently "
        f"mis-capture HTML, screenshots, or console logs, defeating the render "
        f"gate. Re-capture the gates against the new version and re-pin via "
        f"GHL_AB_PINNED_VERSION (or update pinned_version in gates.json), then "
        f"set GHL_AB_ALLOW_VERSION_DRIFT=1 to override during re-capture. STOP."
    )
    if allow_drift:
        sys.stderr.write(
            f"[browser_manager] WARN (P2-4): agent-browser {live} != pinned "
            f"{pinned}; GHL_AB_ALLOW_VERSION_DRIFT=1 — proceeding despite drift "
            f"(risk acknowledged).\n"
        )
        return
    raise RuntimeError(msg)


# ── SESSION-EXPIRED (GHL login-bounce) circuit breaker ────────────────────────
# INCIDENT (2026-07-30, operator box): a GHL Firebase ID token is short-lived
# (securetoken confirms ``expires_in: 3600`` — a hard ONE HOUR). When it lapsed
# mid-session the SPA silently bounced navigation to
# ``app.gohighlevel.com/login`` instead of the requested page, and NOTHING
# detected it: the caller kept retrying against a session that could never
# self-recover, opening a NEW Chrome page every cycle (renderer spawn ages
# tightened 40min -> 11 -> 11 -> 11 -> 2 -> 1s before a human killed it by
# hand). The defect was never "the session expired" — GHL sessions expire
# routinely, on a fixed one-hour clock — it was that expiry produced an
# infinite retry loop instead of ONE bounded self-heal or ONE loud, actionable
# failure.
#
# Detection mirrors the ALREADY-PROVEN "onLogin" heuristic used by
# ghl_form_builder.py's ``_LOGIN_CHECK_JS``, ghl_survey_builder.py, and
# inject-ghl-auth.sh (identical pathname + ``logout=true`` query + password-
# field check) — this is the SAME doctrine, not a newly-invented detector, so
# it carries the same live-proven confidence those three copies already have.
#
# These are PURE, hermetic functions — no subprocess, no network, no browser —
# so the retry/self-heal shape below is unit-testable with fake stub
# callables. The LIVE wiring (spawning ``seed-ghl-auth.py`` to mint a fresh
# token, then ``inject-ghl-auth.sh`` to write it into the browser, capped at
# ONE re-seed attempt per operation) lives in ``browser_manager.sh`` — the
# actual singleton gateway that owns the box lock + the live agent-browser
# process — because a Python caller here has no live browser handle to re-seed
# into (see the module docstring: EMITTER-ONLY, no live-process management).
GHL_LOGIN_CHECK_JS = (
    "(() => {"
    "  const pwd = !!document.querySelector('input[type=password]');"
    "  const onLogin = /[?&]logout=true/.test(location.href) || /\\/login(\\b|$)/.test(location.pathname) || pwd;"
    "  return (onLogin ? 'login:' : 'app:') + location.pathname;"
    "})()"
)


class SessionExpiredError(RuntimeError):
    """Raised when navigation has landed on the GHL login page (or a re-seed
    attempt failed to recover from that state). This is a TERMINAL condition
    — an expired session cookie/token, never a transient network blip — and
    callers MUST NOT retry past it beyond the one permitted re-seed attempt
    ``bounded_retry_with_reseed`` already applies. Never carries token/cookie
    content in its message; only session/profile names and remediation steps."""


def classify_login_check_result(result: Optional[str]) -> str:
    """Classify the string returned by evaluating ``GHL_LOGIN_CHECK_JS``.

    Returns:
      "SESSION_EXPIRED" — result starts with the ``"login:"`` prefix (a
        positive login-bounce signal).
      "OK"              — result starts with the ``"app:"`` prefix.
      "UNKNOWN"         — anything else (empty, a timeout string, unparseable
        output). Deliberately NOT treated as expired: only a POSITIVE login
        signal is terminal. An inconclusive read must fall through to the
        ordinary bounded-transient-retry path instead of manufacturing a false
        terminal failure from a flaky eval call.
    """
    text = (result or "").strip()
    if text.startswith("login:"):
        return "SESSION_EXPIRED"
    if text.startswith("app:"):
        return "OK"
    return "UNKNOWN"


def is_login_url(url: Optional[str]) -> bool:
    """URL-only fallback (no DOM/eval access) — true when the path carries a
    ``logout=true`` bounce marker or looks like GHL's login route. Mirrors the
    pathname/query half of ``GHL_LOGIN_CHECK_JS`` for callers that only have a
    resulting URL (e.g. a CDP target list) and no eval channel. Deliberately
    domain-agnostic (GHL is white-labeled across gohighlevel.com,
    convertandflow.com, and client-custom domains) — same as the JS check,
    which never inspects the hostname either."""
    if not url:
        return False
    return bool(re.search(r"[?&]logout=true", url)) or bool(re.search(r"/login(?:\b|$)", url))


def session_expired_message(session: str, profile_hint: Optional[str] = None) -> str:
    """The ONE actionable message for a detected/unrecovered session expiry.
    Names the profile + session and the exact remedy — never a bare stack
    trace, and NEVER a token/cookie value (only names and paths)."""
    profile = profile_hint or "the OpenClaw browser profile (~/.openclaw/browser/openclaw/user-data)"
    return (
        f"SESSION EXPIRED (GHL login bounce) on session '{session}': navigation "
        "landed on the GoHighLevel /login page instead of the requested page. "
        "This is TERMINAL, not transient. Remedy: re-authenticate "
        f"{profile} — re-run seed-ghl-auth.py to mint a fresh Firebase ID token "
        "(the token is a hard one-hour expiry) and inject-ghl-auth.sh to "
        "re-seed the browser session — then re-run the build. Do NOT retry "
        "blindly: a stale/revoked refresh token will bounce to /login again "
        "every time."
    )


def bounded_retry(
    fn: Callable[[int], object],
    *,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    sleep: Optional[Callable[[float], None]] = None,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
) -> object:
    """Generic bounded-retry-with-exponential-backoff circuit breaker.

    Calls ``fn(attempt)`` (1-based). On success, returns the value. On
    ``SessionExpiredError``, re-raises IMMEDIATELY — no sleep, no further
    attempt, regardless of attempts remaining: an expired session is terminal,
    never transient. On any OTHER exception, retries with exponential backoff
    (``base_delay * 2 ** (attempt - 1)``) up to ``max_attempts`` total tries,
    then re-raises the last exception. This is the shape
    ``browser_manager.sh``'s open-retry loop follows too (bounded attempts,
    exponential backoff, session-expiry short-circuits to zero further
    retries) — kept here as the one Python-side reference implementation so a
    future Python-only caller never has to invent its own retry shape.
    """
    _sleep = sleep or time.sleep
    if max_attempts < 1:
        max_attempts = 1
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(attempt)
        except SessionExpiredError:
            raise
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any transient failure
            last_exc = exc
            if attempt >= max_attempts:
                raise
            if on_retry is not None:
                on_retry(attempt, exc)
            _sleep(base_delay * (2 ** (attempt - 1)))
    if last_exc is not None:  # pragma: no cover - unreachable, keeps type-checkers honest
        raise last_exc
    raise RuntimeError("bounded_retry: exhausted with no exception recorded")  # pragma: no cover


def bounded_retry_with_reseed(
    operation: Callable[[], object],
    *,
    check_session: Callable[[object], str],
    reseed: Callable[[], bool],
    max_transient_attempts: int = 3,
    max_reseed_attempts: int = 1,
    base_delay: float = 2.0,
    sleep: Optional[Callable[[float], None]] = None,
) -> object:
    """Self-heal circuit breaker: bounded transient retry PLUS a hard-capped
    (default: exactly ONE) re-seed-then-retry-once path for a detected expired
    session. Mirrors ``browser_manager.sh``'s
    ``_bm_guard_session_or_heal`` / ``_bm_self_heal_reseed`` shell functions
    for any Python caller that wants the identical circuit-breaker semantics
    without shelling to the gateway itself.

    - ``operation()`` performs the real navigation/action and returns a
      result (or raises).
    - ``check_session(result)`` classifies that result: return
      ``"SESSION_EXPIRED"`` for a detected login bounce, anything else (e.g.
      ``"OK"``) means the operation is done and its result is returned as-is.
    - On ``"SESSION_EXPIRED"``: calls ``reseed()`` at most
      ``max_reseed_attempts`` times TOTAL across the whole call (default 1 —
      "at most one re-seed per operation", the exact cap that prevents a
      smarter infinite loop). ``reseed()`` returns True on success.
        * Re-seed succeeds -> ``operation()`` is retried exactly once more
          (no sleep — a freshly re-authenticated session is not a
          rate-limit/backoff case).
        * Re-seed fails, OR the retried operation is STILL
          ``"SESSION_EXPIRED"`` after a successful re-seed, OR the re-seed
          budget is already spent -> raises :class:`SessionExpiredError`
          immediately. No further attempt of any kind.
    - Any OTHER exception from ``operation()`` is treated as transient and
      retried up to ``max_transient_attempts`` with exponential backoff
      (independent of, and never resetting, the re-seed budget).
    """
    _sleep = sleep or time.sleep
    if max_transient_attempts < 1:
        max_transient_attempts = 1
    reseed_used = 0
    attempt = 1
    while True:
        try:
            result = operation()
        except SessionExpiredError:
            raise
        except Exception:  # noqa: BLE001 - deliberately broad: any transient failure
            if attempt >= max_transient_attempts:
                raise
            _sleep(base_delay * (2 ** (attempt - 1)))
            attempt += 1
            continue

        state = check_session(result)
        if state != "SESSION_EXPIRED":
            return result

        if reseed_used >= max_reseed_attempts:
            raise SessionExpiredError(
                "session still expired after the permitted re-seed attempt(s) "
                f"({reseed_used}/{max_reseed_attempts}) — STOP, no further retry. "
                "Re-authenticate the OpenClaw browser profile manually."
            )
        reseed_used += 1
        if not reseed():
            raise SessionExpiredError(
                "re-seed FAILED — STOP, no further retry (re-seed budget spent: "
                f"{reseed_used}/{max_reseed_attempts}). Supply a fresh Firebase "
                "refresh token and re-run."
            )
        # Re-seed succeeded: loop retries `operation()` exactly once more. The
        # transient-attempt counter is untouched — the re-seed budget and the
        # transient-retry budget are independent axes, never conflated.
        continue


# ── Canonical session name (mirrors bm_session_name in browser_manager.sh) ────

def session_name(slug: Optional[str] = None) -> str:
    """ONE deterministic canonical session per box, sanitized [a-z0-9-].

    Mirrors ``bm_session_name``: ``ghl-skill6-<GHL_LOCATION_ID | CLIENT_SLUG |
    slug | default>``. This is the SINGLE Python-side source of truth — no
    per-iteration multiplication."""
    raw = (
        slug
        or os.environ.get("GHL_LOCATION_ID")
        or os.environ.get("CLIENT_SLUG")
        or "default"
    )
    raw = f"ghl-skill6-{raw}"
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9-]", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw


# ── Session-active flag + signal/atexit teardown emission ─────────────────────
_SESSION_ACTIVE: bool = False
_ACTIVE_SESSION_NAME: Optional[str] = None
_TEARDOWN_EMITTED: bool = False
_PREV_HANDLERS: dict = {}


def emit_teardown_step(session: str) -> str:
    """Return the MANDATORY final teardown step appended to every emitted plan.

    A detach-and-exit run still tears down because the teardown rides INSIDE the
    plan the agent executes. Always headless-forced (D6)."""
    return f"agent-browser --headed false close --session {session}"


def _emit_teardown_on_exit() -> None:
    """atexit / signal hook: emit (NOT execute) the teardown step to stderr so an
    abrupt interpreter exit still surfaces the mandatory close. This module never
    manages a live process, so it cannot itself close a browser — it makes the
    teardown step impossible to lose."""
    global _TEARDOWN_EMITTED
    if _TEARDOWN_EMITTED:
        return
    if _SESSION_ACTIVE and _ACTIVE_SESSION_NAME:
        _TEARDOWN_EMITTED = True
        sys.stderr.write(
            "[browser_manager] MANDATORY teardown step (emit-only): "
            + emit_teardown_step(_ACTIVE_SESSION_NAME)
            + "\n"
        )


def _signal_teardown(signum, _frame):  # pragma: no cover - exercised via raise
    _emit_teardown_on_exit()
    # Restore + re-raise the default disposition so exit codes are honest.
    prev = _PREV_HANDLERS.get(signum, signal.SIG_DFL)
    try:
        signal.signal(signum, prev)
    except (ValueError, OSError, RuntimeError):
        pass
    if signum in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGHUP", signal.SIGTERM)):
        os.kill(os.getpid(), signum)


@contextlib.contextmanager
def browser_session(slug: Optional[str] = None) -> Iterator[str]:
    """Bracket every emitted browser plan. On enter: D6 guard, register
    atexit + SIGTERM/SIGINT/SIGHUP handlers, set ``_SESSION_ACTIVE``, yield the
    canonical session name. On exit (try/finally): emit (NOT execute) the
    teardown step — so the plan/run always carries its mandatory close even on
    an exception or signal.

    Note: the P2-4 agent-browser version-pin check (``assert_agent_browser_version``)
    is NOT called here because ``browser_session`` is an EMITTER-ONLY bracket —
    no live agent-browser binary is spawned inside it. The version check is called
    by ``ghl_builder.render_check`` immediately before the 0.27.0-specific
    subprocesses (``get html html``, ``screenshot``, ``console``) are launched."""
    global _SESSION_ACTIVE, _ACTIVE_SESSION_NAME, _TEARDOWN_EMITTED
    headless_guard()
    name = session_name(slug)
    _SESSION_ACTIVE = True
    _ACTIVE_SESSION_NAME = name
    _TEARDOWN_EMITTED = False

    atexit.register(_emit_teardown_on_exit)
    for sig in ("SIGTERM", "SIGINT", "SIGHUP"):
        signum = getattr(signal, sig, None)
        if signum is None:
            continue
        try:
            _PREV_HANDLERS[signum] = signal.getsignal(signum)
            signal.signal(signum, _signal_teardown)
        except (ValueError, OSError, RuntimeError):
            # e.g. not in the main thread — atexit still covers the common path.
            pass

    try:
        yield name
    finally:
        # In finally we EMIT the teardown step (the canonical close line) so any
        # plan assembled inside this context is guaranteed to end with a close.
        if not _TEARDOWN_EMITTED:
            _TEARDOWN_EMITTED = True
            sys.stderr.write(
                "[browser_manager] MANDATORY teardown step (emit-only): "
                + emit_teardown_step(name)
                + "\n"
            )
        _SESSION_ACTIVE = False
        _ACTIVE_SESSION_NAME = None


def session_active() -> bool:
    """True iff inside an active ``browser_session()`` context."""
    return _SESSION_ACTIVE


def assert_session_active(caller: str = "browser command") -> None:
    """Raise (exit-75 contract) if a browser command is emitted with no active
    session bracket. The emitters call this so a plan can never be built outside
    ``browser_session()``."""
    if not _SESSION_ACTIVE:
        raise RuntimeError(
            f"REFUSE (singleton gateway): {caller} emitted outside an active "
            "browser_session(). Wrap emitter calls in "
            "`with browser_manager.browser_session(slug) as session:` so every "
            "plan is bracketed by ONE canonical session + a guaranteed teardown."
        )


# ── ENVIRONMENT MATRIX (spec §4) — VPS-vs-Mac detection, Python side ──────────
# Mirrors ``_bm_durable_root()`` in browser_manager.sh EXACTLY: VPS's
# ``/data/.openclaw`` checked FIRST (survives a reboot; PARK markers, receipts
# and other durable state live there), else the Mac's ``~/.openclaw``, else ""
# (a bare CI/dev checkout with no onboarded root — callers fall back to an
# ephemeral dir, same contract as the shell side's PARK_DIR fallback).
#
# WHY THIS EXISTS: browser_manager.sh has owned this detection since D7/D14,
# but browser_manager.py (the emitter-only Python mirror) had NO equivalent —
# any new Python-only tool (the community/course builders planned in §5, or a
# future receipt writer) that needed to know "am I on the VPS or the Mac" had
# no sanctioned primitive and would have hand-rolled its own check, risking
# drift from the shell gateway's canonical detection. This closes that gap
# additively — it does not change any existing browser_manager.py behavior.
#
# ``isdir`` is INJECTABLE (defaults to ``os.path.isdir``) so tests can prove
# both branches (VPS-present, VPS-absent-Mac-present, neither) hermetically
# without creating a real ``/data`` directory, which requires root.
_VPS_DURABLE_ROOT = "/data/.openclaw"


def durable_root(
    env: Optional[dict] = None,
    isdir: Optional[Callable[[str], bool]] = None,
) -> str:
    """Return the box's durable OpenClaw root, VPS-first.

    Mirrors ``_bm_durable_root()`` (browser_manager.sh) bit-for-bit:
      1. ``/data/.openclaw`` if it is a directory (VPS/Docker convention).
      2. ``$HOME/.openclaw`` if it is a directory (real Mac / Mac mini).
      3. ``""`` — no onboarded root (CI / a bare dev checkout); callers must
         fall back to an ephemeral dir, same as ``PARK_DIR`` does on the shell
         side.
    Never raises; never touches the network; does no I/O beyond the two
    ``isdir`` probes.
    """
    env = env if env is not None else os.environ
    _isdir = isdir if isdir is not None else os.path.isdir
    if _isdir(_VPS_DURABLE_ROOT):
        return _VPS_DURABLE_ROOT
    home = env.get("HOME", "")
    if home:
        mac_root = os.path.join(home, ".openclaw")
        if _isdir(mac_root):
            return mac_root
    return ""


def is_vps(env: Optional[dict] = None, isdir: Optional[Callable[[str], bool]] = None) -> bool:
    """True iff ``durable_root()`` resolved the VPS convention
    (``/data/.openclaw``), false for Mac or the no-onboarded-root case."""
    return durable_root(env, isdir) == _VPS_DURABLE_ROOT


def supervisor(env: Optional[dict] = None) -> str:
    """Best-effort name of the process supervisor for this box — informational
    only (docs/diagnostics), NEVER used to branch behavior inside a build: the
    skill's browser/build logic is identical on both sides of the matrix by
    design (spec §4 adaptation contract item 5). Mac mini boxes run the MCP
    server + hourly reaper under ``launchd``; VPS/Docker boxes run under
    ``pm2`` (in-container process manager) or ``systemd`` depending on the
    box's provisioning. Detected via ``sys.platform`` — 'darwin' -> launchd,
    anything else -> 'pm2-or-systemd' (Skill 6 does not itself need to
    disambiguate pm2 vs systemd; it never restarts a supervised service)."""
    return "launchd" if sys.platform == "darwin" else "pm2-or-systemd"


# ── B-U15 item 3: stale-env preflight (WARN-only, VPS/Docker-only) ────────────
# ENV-MATRIX.md documents two Docker operational traps as prose only
# ("Operational doctrine, not code inside this skill"). This unit folds ONE of
# them — `docker compose restart` SKIPPING `env_file` re-read, so a changed
# `/docker/<project>/.env` can leave a running container on STALE
# credentials/config with no error anywhere — into an automated preflight
# check, not prose. It is advisory ONLY (WARN, never REFUSE): matches the
# matrix's own framing of this trap as an operational doctrine item, and this
# unit's BINARY acceptance criterion (d) requires it to "fire on a seeded
# stale .env and stay silent otherwise" — a hard REFUSE here would turn an
# advisory doctrine note into an unplanned new build-blocking gate, which is
# out of scope for B-U15.
#
# Fail-soft by construction: every input this needs (are we on a VPS, is
# docker reachable, does the container exist, can its StartedAt be read, does
# the env path exist) can be legitimately absent — on a Mac there IS no
# container to be stale relative to, and on a bare CI/dev checkout there is no
# docker socket at all. Any of those absences returns None (silent), NEVER a
# guessed answer and NEVER an exception.


def hostinger_env_path(project: Optional[str] = None, env: Optional[dict] = None) -> str:
    """Return the Hostinger-convention HOST env path for a project:
    ``/docker/<project>/.env`` (ENV-MATRIX.md's "Env stores" row). `project`
    defaults to `CLIENT_SLUG` / `GHL_LOCATION_ID`, same resolution order and
    slug-sanitizing as `session_name()`, so the two never drift apart."""
    env = env if env is not None else os.environ
    raw = project or env.get("CLIENT_SLUG") or env.get("GHL_LOCATION_ID") or "default"
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9-]", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-") or "default"
    return f"/docker/{raw}/.env"


def _docker_inspect_started_at(container: str) -> Optional[str]:
    """Shell out to ``docker inspect --format {{.State.StartedAt}} <container>``.

    Returns the raw RFC3339Nano timestamp string, or None on ANY failure —
    docker binary absent, no socket reachable, unknown container, timeout.
    Never raises: an undeterminable answer must silence the preflight, not
    crash the caller that folded it into its own startup path."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.StartedAt}}", container],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip()
        return out or None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _file_mtime(path: str) -> Optional[float]:
    """Return a file's mtime as a unix timestamp, or None if it does not
    exist / is not stat-able (never raises)."""
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


_DOCKER_TS_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?P<frac>\.\d+)?"
    r"(?P<tz>[+-]\d{2}:\d{2})?Z?$"
)


def _parse_docker_timestamp(raw: str) -> Optional[float]:
    """Parse Docker's `.State.StartedAt` RFC3339Nano string (e.g.
    ``2026-07-15T05:20:11.123456789Z``) into a UTC unix timestamp.

    Docker emits up to 9 fractional digits (nanoseconds); Python's
    `datetime.fromisoformat` accepts at most 6 (microseconds) — the excess
    precision is truncated. That is fine here: this comparison is against an
    env file's mtime, which is second-granularity on every filesystem this
    skill runs on, so sub-microsecond precision was never meaningful. Returns
    None (never raises) on any unparseable input, e.g. Docker not installed
    and `raw` is empty/garbage."""
    if not raw:
        return None
    m = _DOCKER_TS_RE.match(raw.strip())
    if not m:
        return None
    base, frac, tz = m.group("base"), m.group("frac"), m.group("tz")
    iso = base + (frac[:7] if frac else "") + (tz or "+00:00")
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


def stale_env_preflight(
    container: Optional[str] = None,
    env_path: Optional[str] = None,
    *,
    env: Optional[dict] = None,
    inspect_fn: Optional[Callable[[str], Optional[str]]] = None,
    mtime_fn: Optional[Callable[[str], Optional[float]]] = None,
    isvps_fn: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """B-U15 item 3 — the automated stale-env preflight.

    Returns a human-readable WARN string when the host `.env` file's mtime is
    AFTER the running container's `StartedAt` (the `docker compose restart`
    trap: a changed env was never picked up), else None.

    Silent (returns None, never raises) when:
      * this box is not VPS/Docker (`is_vps()` false — a Mac has no container
        to be stale relative to);
      * docker/the container/the env path cannot be determined at all (never
        guesses "stale" from an absence — that would be a false positive on
        every non-Docker/offline box, defeating acceptance criterion (d)).
    """
    env = env if env is not None else os.environ
    _isvps = isvps_fn if isvps_fn is not None else (lambda: is_vps(env))
    if not _isvps():
        return None

    # Resolved from the injected `env` dict (never real os.environ directly)
    # so callers can fully hermetically test this function — mirrors
    # session_name()'s slug resolution without session_name()'s own hard
    # dependency on the real process environment.
    resolved_container = container or env.get("GHL_DOCKER_CONTAINER") or session_name(
        env.get("CLIENT_SLUG") or env.get("GHL_LOCATION_ID")
    )
    resolved_env_path = env_path or hostinger_env_path(env=env)

    _inspect = inspect_fn if inspect_fn is not None else _docker_inspect_started_at
    _mtime = mtime_fn if mtime_fn is not None else _file_mtime

    started_raw = _inspect(resolved_container)
    env_mtime = _mtime(resolved_env_path)
    if started_raw is None or env_mtime is None:
        return None

    started_ts = _parse_docker_timestamp(started_raw)
    if started_ts is None:
        return None

    if env_mtime > started_ts:
        return (
            f"WARN (stale-env preflight, B-U15): {resolved_env_path} was "
            f"modified AFTER container '{resolved_container}' last started "
            f"({started_raw}). `docker compose restart` SKIPS env_file "
            f"re-read — the running container may be on STALE credentials/"
            f"config. Run `docker compose up -d --force-recreate` to pick up "
            f"the change."
        )
    return None


if __name__ == "__main__":  # pragma: no cover - thin CLI, exercised via subprocess in tests
    import argparse

    _parser = argparse.ArgumentParser(description="browser_manager.py standalone CLI")
    _parser.add_argument(
        "--stale-env-preflight", action="store_true",
        help="B-U15 item 3: print a WARN line to stdout if the host .env is "
             "stale relative to the container's StartedAt; prints nothing "
             "(and always exits 0 — advisory only) otherwise.",
    )
    _args = _parser.parse_args()
    if _args.stale_env_preflight:
        _msg = stale_env_preflight()
        if _msg:
            print(_msg)
        sys.exit(0)
    else:
        _parser.print_help()
        sys.exit(0)
