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
import json
import os
import re
import signal
import subprocess
import sys
from typing import Callable, Iterator, Optional

# Version marker (kept in sync by scripts/bump-version.sh):
BROWSER_MANAGER_PY_VERSION = "v19.19.1"

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
