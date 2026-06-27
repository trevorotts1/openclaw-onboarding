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
``launchPersistentContext`` anywhere in the repo Python). The live-process
lifecycle (lock, lease, TTL self-kill, pool ceiling, breaker, host reaper) lives
in ``browser_manager.sh`` and ``scripts/agent-browser-reaper.sh``. This module's
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
import os
import re
import signal
import sys
from typing import Iterator, Optional

# Version marker (kept in sync by scripts/bump-version.sh):
BROWSER_MANAGER_PY_VERSION = "v14.9.0"

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
    an exception or signal."""
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
