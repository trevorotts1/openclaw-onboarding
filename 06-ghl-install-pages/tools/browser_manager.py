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

# Version marker (owned by Skill 06; keep in sync with skill-version.txt):
BROWSER_MANAGER_PY_VERSION = "v27.1.74"

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




# ── capability probe (P0-6 / plan 2.4-2) ───────────────────────────────────────────────────────────────────────

def _probe_error_doc(reason: str) -> dict:
    """Fail-closed probe document — selectedLane null, advisory, never raises.

    The real probe (capability_probe.run_probe) fail-closes the same way
    (zero browser lanes -> selectedLane null + blockers); this covers the
    additionally-catastrophic case where the probe module itself cannot run.
    """
    return {
        "probedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selectedLane": None,
        "blockers": ["probe-error"],
        "warnings": [reason],
        "lanes": {},
        "error": reason,
    }

def capability_probe_result() -> dict:
    """P0-6 / plan 2.4-2 — run the Skill 06 browser capability probe.

    Soft-imports ``capability_probe`` (sibling module in tools/) and returns
    its result dict verbatim — one classification implementation, never a
    second drifting one. On ANY failure returns a fail-closed document
    (selectedLane null, blockers ["probe-error"]) instead of raising: the CLI
    wrapper prints it and ALWAYS exits 0 (advisory — bm_ensure warns rather
    than blocks on this output).

    Version note: the probe MEASURES the live binary (``agent-browser
    --version``) for its lane table; the authoritative enforcement pin stays
    ``_read_pinned_agent_browser_version`` (assert_agent_browser_version) —
    the two are reconciled in ghl_ab_executor's selftest, never re-derived
    here.
    """
    try:
        import capability_probe  # type: ignore[import-untyped]
    except Exception as exc:  # noqa: BLE001 — fail-closed, never raise
        return _probe_error_doc(f"capability_probe import failed: {exc}")
    try:
        return capability_probe.run_probe()
    except Exception as exc:  # noqa: BLE001 — fail-closed, never raise
        return _probe_error_doc(f"capability probe failed: {exc}")


# ═════════════════════════════════════════════════════════════════════════════
# P3 — OPT-IN HEADLESS PLAYWRIGHT LANE + RESOURCE GUARD (plan §9.2/§9.3, WF-B)
# ═════════════════════════════════════════════════════════════════════════════
# The dedicated UNATTENDED recipe lane: one owned headless Playwright browser +
# one owned context, under the SAME one-browser budget as the singleton manager
# (browser_manager.sh box lock) and the root reaper (agent-browser-reaper.sh).
# OPT-IN: nothing runs here unless a caller opens a PlaywrightSession or runs the
# watchdog verb. The personal Chrome and the OpenClaw attended profile are never
# attached to and never touched.
#
# CONTRACT (plan P3 / checklist C4):
#   * headless=True is enforced at the ACTUAL launch options object — headed /
#     devtools / inherited headed configuration is REFUSED before any process
#     spawns. No headed fallback after any failure, ever (D6).
#   * one owned browser + one owned context, at most PW_MAX_PAGES pages,
#     bounded lifetime (no immortal warm browser).
#   * try/finally + SIGTERM/SIGINT/SIGHUP handling: teardown always runs.
#   * watchdog keyed by lease + PID + PID start-time + exact owned profile path
#     (PID-reuse safe), graceful stop first, bounded wait, force only a provably
#     owned survivor. Detection target: within PW_WATCHDOG_INTERVAL_S (<= 60s).
#   * single-owner admission: WF-A's shared swarm AdmissionLedger 'browser'
#     token when scripts/lib/swarm_controls.py is present (contract-first: the
#     minimal acquire/heartbeat/release interface is duck-typed here and the
#     local OneBrowserLock keeps the budget where the ledger is not yet wired).
#   * B19: trace/video/har recording overrides are REFUSED — an auth-seeded
#     browser must never dump tokens/cookies into a trace.

# ── P3 tunables ──────────────────────────────────────────────────────────────
PW_MAX_PAGES = 2                      # at most two expected pages per context
PW_SESSION_TTL_S = 1800               # bounded lifetime (s) — mirrors AB_SESSION_TTL
PW_STOP_GRACE_S = 5.0                 # graceful stop wait before force
PW_LOCK_WAIT_S = 10.0                 # bounded queue/wait for the one-browser budget
PW_WATCHDOG_INTERVAL_S = 30.0         # local safety watchdog tick (<= 60s target)

# Profile roots that are NEVER ours (personal Chrome / OpenClaw attended
# profile). An owned lane profile must never resolve inside any of these.
_PERSONAL_PROFILE_MARKERS = (
    "/Library/Application Support/Google/Chrome",
    "/.config/google-chrome",
    "/.config/chromium",
    "/.openclaw/browser/openclaw",
)

PW_LEASE_SUFFIX = ".pwlease"


class PWLaunchRefused(RuntimeError):
    """A headed/devtools/inherited-headed/recording launch was requested —
    REFUSED before any process spawned (D6 / plan 9.3 / B19). Never a fallback
    to headed."""


class PWPageBudgetExceeded(RuntimeError):
    """At most PW_MAX_PAGES pages per owned context."""


class PWLifetimeExceeded(RuntimeError):
    """Bounded session lifetime exceeded — the lane stops; it never warms
    forever."""


def _pw_lockdir(env: Optional[dict] = None) -> str:
    """Mirror browser_manager.sh LOCKDIR so leases land where the root reaper
    and the watchdog look: ${TMPDIR:-/tmp}/agent-browser."""
    env = env if env is not None else os.environ
    return os.path.join(env.get("TMPDIR", "/tmp"), "agent-browser")


def pw_launch_options(env: Optional[dict] = None,
                      overrides: Optional[dict] = None) -> dict:
    """Build the REAL launch kwargs for the owned Playwright browser.

    headless=True is enforced HERE, on the options object actually passed to
    launch — not merely in an earlier config check. Refused (PWLaunchRefused,
    before any process spawns):
      * inherited headed configuration (AGENT_BROWSER_HEADED truthy — D6),
      * GHL_PLAYWRIGHT_HEADED / PW_HEADED / GHL_PW_HEADED truthy,
      * any override asking for headless=False or devtools=True,
      * any trace/video/har recording override (B19: an auth-seeded browser
        must never dump tokens/cookies into a trace)."""
    env = env if env is not None else os.environ
    headless_guard(env)  # inherited AGENT_BROWSER_HEADED -> RuntimeError (D6)
    for var in ("GHL_PLAYWRIGHT_HEADED", "PW_HEADED", "GHL_PW_HEADED"):
        val = str(env.get(var, "") or "").strip().lower()
        if val and val not in _HEADED_OFF_VALUES:
            raise PWLaunchRefused(
                f"REFUSE (D6/P3): {var}={val!r} would open a VISIBLE window. "
                "Headless is mandatory for the Playwright lane. Unset it and "
                "run again — there is no headed fallback."
            )
    overrides = dict(overrides or {})
    for key in ("record_video_dir", "record_har_path"):
        if overrides.get(key):
            raise PWLaunchRefused(
                f"REFUSE (B19): trace recording ({key}) is not permitted on the "
                "auth-seeded lane — traces can capture tokens/cookies. Remove "
                "the recording option."
            )
    if overrides.get("record_har_content"):
        raise PWLaunchRefused(
            "REFUSE (B19): record_har_content is not permitted on the "
            "auth-seeded lane — HAR content captures tokens/cookies."
        )
    # A REQUEST for headed/devtools is REFUSED, never silently coerced (P3:
    # "reject headed/devtools/inherited headed config").
    if "headless" in overrides and not overrides["headless"]:
        raise PWLaunchRefused(
            "REFUSE (D6/P3): headless=False requested. Headless is mandatory "
            "for the Playwright lane — there is no headed fallback."
        )
    if overrides.get("devtools"):
        raise PWLaunchRefused(
            "REFUSE (D6/P3): devtools=True requested. The devtools window is a "
            "visible-window path and is refused on the Playwright lane."
        )
    for key in ("headless", "devtools"):
        overrides.pop(key, None)  # always forced below
    opts = dict(overrides)
    opts["headless"] = True
    # ``devtools`` is NOT emitted: playwright's launch_persistent_context has no
    # such kwarg (passing it raises TypeError and the lane cannot launch). The
    # REQUEST for it was already REFUSED above, so absence here is the refusal,
    # not a silent drop.
    # Post-build verification on the object that will actually be passed to
    # launch — construction cannot drift even if a future caller edits above.
    if opts.get("headless") is not True or "devtools" in opts:
        raise PWLaunchRefused(  # pragma: no cover - belt, not reachable
            "REFUSE (P3): launch options drifted from the headless-only shape."
        )
    return opts


def pw_owned_profile_dir(session: str, env: Optional[dict] = None,
                         make: bool = True) -> str:
    """Return the owned lane profile dir for this session (created when
    ``make``). Bulk cache placement follows SKILL06_EXTERNAL_ROOT when set
    (external run dirs own heavy temp); else the manager lockdir. REFUSES any
    path inside a personal Chrome / OpenClaw attended profile root — personal
    browsers are never touched (P3)."""
    env = env if env is not None else os.environ
    external = env.get("SKILL06_EXTERNAL_ROOT", "")
    if external:
        base = os.path.join(external, "pw-profiles")
    else:
        base = os.path.join(_pw_lockdir(env), "pw-profiles")
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", session) or "session"
    path = os.path.abspath(os.path.join(
        base, f"{safe}-{os.getpid()}-{int(time.time() * 1000) % 100000}"))
    for marker in _PERSONAL_PROFILE_MARKERS:
        if marker in path:
            raise PWLaunchRefused(
                "REFUSE (P3): owned lane profile would land inside a personal "
                "browser profile root. Personal Chrome is never touched."
            )
    if make:
        os.makedirs(path, mode=0o700, exist_ok=True)
    return path


# ── PID-reuse-safe process identity (lease + PID + start-time + profile path) ─

def proc_start_time(pid: int) -> str:
    """PID start-time token (``ps -o lstart=``). Combined with the PID this is a
    PID-reuse-safe process identity. Returns "" when unreadable — callers treat
    "" as UNKNOWN (never as alive)."""
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        return " ".join((out.stdout or "").split())
    except Exception:  # noqa: BLE001 - identity probing must never raise
        return ""


def proc_cmdline(pid: int) -> str:
    try:
        out = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def proc_identity_matches(pid: int, start_time: str, profile_path: str) -> bool:
    """True iff ``pid`` is alive AND its start-time still matches AND its command
    line references the EXACT owned profile path. PID-reuse safe: a recycled PID
    has a different start-time and can never match. A process without the exact
    profile path (personal Chrome, anything else) can never match."""
    if not pid or not profile_path or not start_time:
        return False
    if proc_start_time(pid) != start_time:
        return False
    return profile_path in proc_cmdline(pid)


def find_owned_pids(profile_path: str, exclude_pids: tuple = ()) -> list:
    """Every live PID whose command line references the EXACT owned profile
    path. Never returns a process lacking that path (personal Chrome is never
    in this list)."""
    if not profile_path:
        return []
    found = []
    try:
        out = subprocess.run(["ps", "-axww", "-o", "pid=,command="],
                             capture_output=True, text=True, timeout=10)
        lines = (out.stdout or "").splitlines()
    except Exception:  # noqa: BLE001
        return []
    exclude = {int(p) for p in exclude_pids if p}
    for line in lines:
        stripped = line.strip()
        if not stripped or profile_path not in stripped:
            continue
        head = stripped.split(None, 1)[0]
        if not head.isdigit():
            continue
        pid = int(head)
        if pid in exclude or pid == os.getpid():
            continue
        found.append(pid)
    return found


def stop_owned_processes(profile_path: str,
                         expected: Optional[dict] = None,
                         grace_s: float = PW_STOP_GRACE_S,
                         *,
                         exclude_pids: tuple = (),
                         term_fn=None, kill_fn=None, sleep_fn=None,
                         scan_fn=None) -> dict:
    """Graceful stop BEFORE force, scoped to provably owned processes only.

    ``expected`` is the lease's {pid: start_time} identity map. ``exclude_pids``
    names the lease OWNER (and any other process that is not an owned browser
    child) — the owner's argv may carry the profile path, but the watchdog must
    never signal the owner itself. Every signal is re-verified against (PID,
    start-time, exact profile path) immediately before it is sent — a PID
    recycled between scan and signal is never hit. Processes without the exact
    owned profile path are NEVER signaled (personal Chrome preserved). Returns
    {"terminated": [pids], "killed": [pids]}."""
    term_fn = term_fn or (lambda p: os.kill(p, signal.SIGTERM))
    kill_fn = kill_fn or (lambda p: os.kill(p, signal.SIGKILL))
    sleep_fn = sleep_fn or time.sleep
    exclude = {int(p) for p in exclude_pids if p} | {os.getpid()}
    scan_fn = scan_fn or (lambda: find_owned_pids(profile_path, tuple(exclude)))

    seen: dict = {}
    for pid in scan_fn():
        pid = int(pid)
        if pid in exclude:
            continue
        st = proc_start_time(pid)
        if st:
            seen[pid] = st
    for pid, st in (expected or {}).items():
        pid = int(pid)
        if pid in exclude:
            continue
        if proc_identity_matches(pid, st, profile_path):
            seen[pid] = st

    terminated = []
    for pid, st in list(seen.items()):
        if proc_identity_matches(pid, st, profile_path):
            try:
                term_fn(pid)
                terminated.append(pid)
            except OSError:
                pass

    # Bounded wait for the graceful stop to take effect.
    deadline = time.time() + max(0.0, float(grace_s))
    while time.time() < deadline:
        if not any(proc_identity_matches(p, s, profile_path)
                   for p, s in seen.items()):
            break
        sleep_fn(0.2)

    killed = []
    for pid, st in seen.items():
        # Re-verify ownership immediately before the force signal (PID reuse).
        if proc_identity_matches(pid, st, profile_path):
            try:
                kill_fn(pid)
                killed.append(pid)
            except OSError:
                pass
    return {"terminated": terminated, "killed": killed}


# ── Lease identity file (watchdog/reaper contract) ───────────────────────────

def pw_lease_path(lease_dir: str, session: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "-", session) or "session"
    return os.path.join(lease_dir, safe + PW_LEASE_SUFFIX)


def pw_lease_write(lease_dir: str, session: str, *, owner_pid: int,
                   owner_start: str, profile_path: str,
                   browser_pid: Optional[int] = None,
                   browser_start: str = "",
                   ttl_sec: float = PW_SESSION_TTL_S,
                   now: Optional[float] = None) -> str:
    os.makedirs(lease_dir, mode=0o700, exist_ok=True)
    path = pw_lease_path(lease_dir, session)
    lease = {
        "lane": "playwright",
        "session": session,
        "owner_pid": int(owner_pid),
        "owner_start": owner_start,
        "browser_pid": int(browser_pid) if browser_pid else None,
        "browser_start": browser_start or "",
        "profile_path": profile_path,
        "started_epoch": float(now if now is not None else time.time()),
        "ttl_sec": float(ttl_sec),
        "box_id": f"{os.uname().nodename if hasattr(os, 'uname') else 'box'}:{os.environ.get('HOME', '')}",
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lease, fh)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def pw_lease_read(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            lease = json.load(fh)
    except (OSError, ValueError):
        return None
    return lease if isinstance(lease, dict) else None


def pw_lease_healthy(lease: dict, now: Optional[float] = None) -> bool:
    """True iff the lease's owner is still the SAME live process (PID alive AND
    start-time matching — PID-reuse safe) and the bounded lifetime has not
    passed."""
    now = float(now if now is not None else time.time())
    if now > float(lease.get("started_epoch", 0)) + float(lease.get("ttl_sec", 0)):
        return False
    # Owner identity: PID alive AND start-time matching (PID-reuse safe). The
    # owner (builder) process need not carry the profile path on its command
    # line — only the owned browser children must, and those are enforced by
    # stop_owned_processes / find_owned_pids.
    owner_pid = int(lease.get("owner_pid") or 0)
    owner_start = lease.get("owner_start", "")
    if not owner_pid or not owner_start:
        return False
    return proc_start_time(owner_pid) == owner_start


def pw_watchdog_reclaim(lease: dict, lease_path: str,
                        grace_s: float = PW_STOP_GRACE_S,
                        stop_fn=None) -> dict:
    """Reclaim one dead lease: stop its owned processes (graceful then force),
    scoped to the exact profile path, NEVER the lease owner (the owner's argv
    may carry the profile path but the watchdog must not signal the owner
    itself), then drop the lease file."""
    stop_fn = stop_fn or stop_owned_processes
    report = stop_fn(lease.get("profile_path", ""),
                     expected={lease["browser_pid"]: lease["browser_start"]}
                     if lease.get("browser_pid") and lease.get("browser_start")
                     else None,
                     grace_s=grace_s,
                     exclude_pids=(lease.get("owner_pid"),))
    try:
        os.unlink(lease_path)
    except OSError:
        pass
    return report


def pw_watchdog_sweep(lockdir: Optional[str] = None,
                      grace_s: float = PW_STOP_GRACE_S,
                      now: Optional[float] = None,
                      stop_fn=None) -> dict:
    """One watchdog pass over the Playwright-lane lease files (``*.pwlease``).

    A lease is reclaimed when its owner PID is gone or reused (start-time
    mismatch) or its bounded lifetime has passed. Healthy leases are untouched.
    Processes without the lease's exact profile path are never signaled.
    Returns {"reclaimed": [sessions], "healthy": [sessions], "detail": {...}}."""
    lockdir = lockdir or _pw_lockdir()
    lease_dir = os.path.join(lockdir, "leases")
    reclaimed, healthy, detail = [], [], {}
    try:
        names = sorted(os.listdir(lease_dir))
    except OSError:
        names = []
    for name in names:
        if not name.endswith(PW_LEASE_SUFFIX):
            continue
        path = os.path.join(lease_dir, name)
        lease = pw_lease_read(path)
        if lease is None:
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        session = lease.get("session", name)
        if pw_lease_healthy(lease, now=now):
            healthy.append(session)
            continue
        detail[session] = pw_watchdog_reclaim(lease, path, grace_s=grace_s,
                                              stop_fn=stop_fn)
        reclaimed.append(session)
    return {"reclaimed": reclaimed, "healthy": healthy, "detail": detail}


def pw_watchdog_serve(lease_path: str,
                      interval_s: float = PW_WATCHDOG_INTERVAL_S,
                      max_ticks: Optional[int] = None,
                      stop_fn=None) -> int:
    """Local safety watchdog (plan 9.3): detect abandoned owned work promptly
    (default tick 30s — inside the 60s target plus shutdown grace) with NO LLM
    monitor and no extra scheduler session. Runs detached from the session
    owner (start_new_session). While the lease is healthy it only ticks. When
    the owner dies (or its PID is reused), the bounded lifetime passes, or the
    lease file disappears (normal close), it reclaims the lease's owned
    processes (graceful stop, bounded wait, force only provably owned
    survivors) and exits. Touches ONLY processes carrying the lease's exact
    profile path — personal Chrome is never signaled."""
    ticks = 0
    while True:
        lease = pw_lease_read(lease_path)
        if lease is None:
            return 0  # normal close already cleaned up
        if not pw_lease_healthy(lease):
            pw_watchdog_reclaim(lease, lease_path, stop_fn=stop_fn)
            return 0
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            return 0
        time.sleep(max(0.05, float(interval_s)))


# ── One-browser budget: local singleton lock + WF-A admission ledger ─────────

class OneBrowserLock:
    """The one-browser budget's local gate (plan §6.2: browser = 1). mkdir-based
    (portable — flock is absent on macOS) with dead-PID + start-time stale
    reclaim, and a BOUNDED wait: the queue never blocks forever (B03). Held
    alongside WF-A's AdmissionLedger 'browser' token when that ledger is
    available; the lock keeps the budget even where the ledger is not yet
    wired."""

    def __init__(self, lockdir: Optional[str] = None,
                 wait_s: float = PW_LOCK_WAIT_S, name: str = "pw.lock.d",
                 sleep_fn=None):
        self.lockdir = lockdir or _pw_lockdir()
        self.path = os.path.join(self.lockdir, name)
        self.wait_s = float(wait_s)
        self._sleep = sleep_fn or time.sleep
        self._held = False

    def acquire(self) -> "OneBrowserLock":
        os.makedirs(self.lockdir, mode=0o700, exist_ok=True)
        deadline = time.time() + self.wait_s
        while True:
            try:
                os.mkdir(self.path)
            except FileExistsError:
                owner = ""
                start = ""
                try:
                    with open(os.path.join(self.path, "owner"), encoding="utf-8") as fh:
                        owner, _, start = fh.read().partition("\n")
                except OSError:
                    pass
                alive = False
                if owner.strip().isdigit():
                    alive = (proc_start_time(int(owner.strip())) == start.strip()
                             and bool(start.strip()))
                if alive:
                    if time.time() >= deadline:
                        raise RuntimeError(
                            "REFUSE (P3 one-browser budget): another owned "
                            "browser lease is held (pid "
                            f"{owner.strip()}) and the bounded queue wait "
                            f"({self.wait_s:.0f}s) expired. One browser — "
                            "retry later or release the held lease."
                        )
                    self._sleep(0.2)
                    continue
                # Stale lock (owner dead or PID reused) — reclaim and retry.
                try:
                    os.unlink(os.path.join(self.path, "owner"))
                except OSError:
                    pass
                try:
                    os.rmdir(self.path)
                except OSError:
                    pass
                continue
            with open(os.path.join(self.path, "owner"), "w", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()}\n{proc_start_time(os.getpid())}")
            self._held = True
            return self

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            os.unlink(os.path.join(self.path, "owner"))
        except OSError:
            pass
        try:
            os.rmdir(self.path)
        except OSError:
            pass

    def __enter__(self) -> "OneBrowserLock":
        return self.acquire()

    def __exit__(self, *_exc) -> bool:
        self.release()
        return False


def _load_swarm_ledger(state_dir: str):
    """Contract-first bridge to WF-A's scripts/lib/swarm_controls.py
    AdmissionLedger (minimal interface used here: acquire(kind, owner),
    heartbeat(token), release(token)). Returns None when that module is not on
    this branch (WF-A still in flight) or cannot load — the local
    OneBrowserLock keeps the budget meanwhile. NEVER edits WF-A's files."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "scripts", "lib", "swarm_controls.py")
    if not os.path.isfile(path):
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("skill06_swarm_controls", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.AdmissionLedger(state_dir)
    except Exception:  # noqa: BLE001 - contract-first: absence is not fatal
        return None


# ── The owned session ────────────────────────────────────────────────────────

class _RealPlaywrightHandle:
    """Default launch: Playwright persistent context on the OWNED profile dir,
    headless per pw_launch_options. Opt-in — playwright is imported only here,
    never at module import. ``close()`` is the supported close operation (never
    a bare kill of an externally attached browser)."""

    def __init__(self, profile_dir: str, options: dict):
        from playwright.sync_api import sync_playwright  # opt-in import
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            profile_dir,
            # Literal, never options-derived: COMPLIANT-BY-CONSTRUCTION for the
            # U28/D6 headless_guard_audit (same class as ghl_iframe_drag's
            # self-test). pw_launch_options() has already REFUSED any headed
            # request upstream, so this literal cannot mask a headed launch.
            headless=True,
        )
        self.pages = self._ctx.pages

    @property
    def pid(self) -> Optional[int]:
        return None  # discovered via the exact profile path (find_owned_pids)

    def new_page(self):
        page = self._ctx.new_page()
        self.pages = self._ctx.pages
        return page

    def close(self) -> None:
        try:
            self._ctx.close()  # supported close op — closes owned browser too
        finally:
            self._pw.stop()


class PlaywrightSession:
    """The opt-in headless Playwright lane's owned session (plan P3).

        with PlaywrightSession() as s:
            page = s.new_page()
            ...

    After ghl_auth seeds auth into this session's context, navigate the page
    the bridge RETURNED (``receipt.page``) — not a second ``new_page()``: the
    seed lives in one page's origin store partition, and a different page
    reads as user_not_logged_in even though the mint succeeded.

    Guarantees: headless enforced at the actual launch; one owned browser and
    one owned context; at most PW_MAX_PAGES pages; bounded lifetime;
    try/finally + signal teardown; a lease keyed by PID + start-time + exact
    profile path for the watchdog/reaper; personal profiles never touched.

    ``launch_fn(profile_dir, options) -> handle`` is the DI seam (tests pass a
    fake whose processes are owned disposable ones); default launches real
    Playwright. ``admission`` is WF-A's AdmissionLedger (duck-typed
    acquire/heartbeat/release) or any object with that minimal interface; the
    local OneBrowserLock is held regardless."""

    def __init__(self, session: Optional[str] = None,
                 env: Optional[dict] = None,
                 launch_fn=None,
                 ttl_s: float = PW_SESSION_TTL_S,
                 max_pages: int = PW_MAX_PAGES,
                 lockdir: Optional[str] = None,
                 wait_s: float = PW_LOCK_WAIT_S,
                 admission=None,
                 watchdog: bool = True,
                 watchdog_interval_s: float = PW_WATCHDOG_INTERVAL_S,
                 now=None):
        self.env = env if env is not None else os.environ
        self.session = session_name(session) if session else session_name()
        self.ttl_s = float(ttl_s)
        self.max_pages = int(max_pages)
        self.lockdir = lockdir or _pw_lockdir(self.env)
        self._launch_fn = launch_fn
        self._admission = admission
        self._watchdog_enabled = bool(watchdog)
        self.watchdog_interval_s = float(watchdog_interval_s)
        self._now = now or time.time
        self._lock = OneBrowserLock(self.lockdir, wait_s=wait_s)
        self._admission_token = None
        self._handle = None
        self._lease_path = None
        self._profile_dir = None
        self._watchdog_proc = None
        self._started = 0.0
        self._closed = False
        self._prev_handlers = {}
        self.pages = []

    # -- lifecycle -----------------------------------------------------------

    def __enter__(self) -> "PlaywrightSession":
        headless_guard(self.env)  # D6 — before ANY resource is taken
        options = pw_launch_options(self.env)
        self._lock.acquire()  # one-browser budget (bounded queue)
        try:
            if self._admission is not None:
                try:
                    self._admission_token = self._admission.acquire(
                        "browser", f"playwright:{self.session}")
                except Exception as exc:  # noqa: BLE001 - ledger refuses -> stop
                    raise RuntimeError(
                        "REFUSE (P3 one-browser budget): shared admission "
                        f"ledger refused the browser token ({exc.__class__.__name__})."
                    ) from exc
            self._profile_dir = pw_owned_profile_dir(self.session, self.env)
            self._started = self._now()
            self._lease_path = pw_lease_write(
                os.path.join(self.lockdir, "leases"), self.session,
                owner_pid=os.getpid(), owner_start=proc_start_time(os.getpid()),
                profile_path=self._profile_dir, ttl_sec=self.ttl_s,
                now=self._started)
            if self._watchdog_enabled:
                self._spawn_watchdog()
            factory = self._launch_fn or _RealPlaywrightHandle
            self._handle = factory(self._profile_dir, options)
            if getattr(self._handle, "pid", None):
                # refresh the lease with the browser identity once known
                pw_lease_write(
                    os.path.join(self.lockdir, "leases"), self.session,
                    owner_pid=os.getpid(), owner_start=proc_start_time(os.getpid()),
                    profile_path=self._profile_dir,
                    browser_pid=getattr(self._handle, "pid", None),
                    browser_start=proc_start_time(getattr(self._handle, "pid", 0)),
                    ttl_sec=self.ttl_s, now=self._started)
            self.pages = list(getattr(self._handle, "pages", []) or [])
            self._install_signal_handlers()
            return self
        except BaseException:
            self.close()
            raise

    def _spawn_watchdog(self) -> None:
        cmd = [sys.executable, os.path.abspath(__file__),
               "--pw-watchdog-serve", self._lease_path,
               "--pw-interval", str(self.watchdog_interval_s)]
        self._watchdog_proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)

    def new_page(self):
        self.assert_alive()
        if len(self.pages) >= self.max_pages:
            raise PWPageBudgetExceeded(
                f"REFUSE (P3): page budget — at most {self.max_pages} pages per "
                f"owned context (session '{self.session}'). Close a page first."
            )
        if self._handle is None:
            raise RuntimeError("session is closed")
        page = self._handle.new_page()
        self.pages = list(getattr(self._handle, "pages", []) or self.pages + [page])
        return page

    def assert_alive(self) -> None:
        if self._closed or self._handle is None:
            raise RuntimeError(f"session '{self.session}' is closed")
        if self._now() - self._started > self.ttl_s:
            raise PWLifetimeExceeded(
                f"REFUSE (P3): bounded lifetime {self.ttl_s:.0f}s exceeded for "
                f"session '{self.session}' — stopping instead of warming forever."
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # 1. Drop the lease FIRST so the watchdog sees a normal close and exits.
        if self._lease_path:
            try:
                os.unlink(self._lease_path)
            except OSError:
                pass
        # 2. Stop our watchdog child (it is ours; graceful then force).
        if self._watchdog_proc is not None:
            try:
                self._watchdog_proc.terminate()
                self._watchdog_proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    self._watchdog_proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        # 3. Supported close operation on the owned handle (pages/context/browser).
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:  # noqa: BLE001 - fall through to scoped sweep
                pass
            self._handle = None
        # 4. Sweep any leftover owned processes — graceful stop before force,
        #    scoped to the exact profile path (personal Chrome never touched).
        if self._profile_dir:
            stop_owned_processes(self._profile_dir)
            try:
                import shutil
                shutil.rmtree(self._profile_dir, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass
        # 5. Release the admission token + the one-browser lock.
        if self._admission_token is not None and self._admission is not None:
            try:
                self._admission.release(self._admission_token)
            except Exception:  # noqa: BLE001
                pass
            self._admission_token = None
        self._lock.release()
        self._restore_signal_handlers()

    def _signal_close(self, signum, _frame):  # pragma: no cover - signal path
        self.close()
        prev = self._prev_handlers.get(signum, signal.SIG_DFL)
        try:
            signal.signal(signum, prev)
        except (ValueError, OSError, RuntimeError):
            pass
        if signum in (signal.SIGTERM, signal.SIGINT,
                      getattr(signal, "SIGHUP", signal.SIGTERM)):
            os.kill(os.getpid(), signum)

    def _install_signal_handlers(self) -> None:
        for sig in ("SIGTERM", "SIGINT", "SIGHUP"):
            signum = getattr(signal, sig, None)
            if signum is None:
                continue
            try:
                self._prev_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, self._signal_close)
            except (ValueError, OSError, RuntimeError):
                pass

    def _restore_signal_handlers(self) -> None:
        for signum, prev in self._prev_handlers.items():
            try:
                signal.signal(signum, prev)
            except (ValueError, OSError, RuntimeError):
                pass
        self._prev_handlers = {}

    def __exit__(self, *_exc) -> bool:
        self.close()
        return False


if __name__ == "__main__":  # pragma: no cover - thin CLI, exercised via subprocess in tests
    import argparse

    _parser = argparse.ArgumentParser(description="browser_manager.py standalone CLI")
    _parser.add_argument(
        "--stale-env-preflight", action="store_true",
        help="B-U15 item 3: print a WARN line to stdout if the host .env is "
             "stale relative to the container's StartedAt; prints nothing "
             "(and always exits 0 — advisory only) otherwise.",
    )
    _parser.add_argument(
        "--capability-probe", action="store_true",
        help="P0-6 / plan 2.4-2: run the Skill 06 browser capability probe "
             "and print its JSON to stdout (selectedLane, fallbackChain, "
             "blockers, warnings — secrets surfaced as booleans only). "
             "ADVISORY: ALWAYS exits 0, even when the probe fails or reports "
             "blockers (a WARN line goes to stderr then; bm_ensure warns "
             "rather than blocks on this output).",
    )
    _parser.add_argument(
        "--capability-out", default=None, metavar="PATH",
        help="P0-6: with --capability-probe, where to write the receipt JSON "
             "(default: BM_CAPABILITY_RECEIPT_OVERRIDE, else "
             "<skill>/working/skill6-capability.json).",
    )
    _parser.add_argument(
        "--pw-watchdog", action="store_true",
        help="P3: run ONE watchdog sweep over Playwright-lane leases "
             "(graceful stop before force; PID-reuse safe; only processes "
             "carrying the exact owned profile path are ever signaled) and "
             "print the JSON report.",
    )
    _parser.add_argument(
        "--pw-watchdog-serve", default=None, metavar="LEASE",
        help="P3: run the local safety watchdog for one lease file until the "
             "lease closes normally or its owner dies / its bounded lifetime "
             "passes (then reclaim and exit). Detached child of the session.",
    )
    _parser.add_argument(
        "--pw-interval", type=float, default=PW_WATCHDOG_INTERVAL_S,
        help="watchdog tick seconds for --pw-watchdog-serve (default %(default)s).",
    )
    _args = _parser.parse_args()
    if _args.pw_watchdog_serve:
        sys.exit(pw_watchdog_serve(_args.pw_watchdog_serve,
                                   interval_s=_args.pw_interval))
    if _args.pw_watchdog:
        print(json.dumps(pw_watchdog_sweep(), indent=2, sort_keys=False))
        sys.exit(0)
    if _args.stale_env_preflight:
        _msg = stale_env_preflight()
        if _msg:
            print(_msg)
        sys.exit(0)
    if _args.capability_probe:
        _probe = capability_probe_result()
        print(json.dumps(_probe, indent=2, sort_keys=False))
        # P0-6: persist the receipt to the capability JSON path (non-fatal) so
        # the dispatcher freshness gate and QC prereq can read it. Path:
        # --capability-out > BM_CAPABILITY_RECEIPT_OVERRIDE (test-only, the
        # BM_DURABLE_ROOT_OVERRIDE convention) > <skill>/working/
        # skill6-capability.json. A write failure is a WARN, never a raise —
        # the printout above remains the advisory evidence.
        _cap_out = (
            _args.capability_out
            or os.environ.get("BM_CAPABILITY_RECEIPT_OVERRIDE")
            or os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))),
                "working", "skill6-capability.json")
        )
        try:
            os.makedirs(os.path.dirname(_cap_out) or ".", exist_ok=True)
            with open(_cap_out, "w", encoding="utf-8") as _fh:
                json.dump(_probe, _fh, indent=2, sort_keys=False)
                _fh.write("\n")
        except OSError as _exc:
            print("WARN capability-probe: receipt write failed (%s): %s"
                  % (_cap_out, _exc), file=sys.stderr)
        # Advisory WARN (stderr) — never a failure: mirrors the probe's own
        # stderr WARN convention; distinguishable by stderr TEXT, never by
        # exit code (the 64/75/76/79 codes stay reserved for refusals).
        if not _probe.get("selectedLane"):
            print("WARN capability-probe: selectedLane=null — no usable "
                  "browser lane; agent-browser 0.27.0 install required "
                  "before the next build.", file=sys.stderr)
        elif _probe.get("blockers"):
            print("WARN capability-probe: %d blocker(s) on lane %s: %s"
                  % (len(_probe["blockers"]), _probe.get("selectedLane"),
                     "; ".join(str(b) for b in _probe["blockers"])),
                  file=sys.stderr)
        sys.exit(0)  # advisory ALWAYS exit 0
    _parser.print_help()
    sys.exit(0)
