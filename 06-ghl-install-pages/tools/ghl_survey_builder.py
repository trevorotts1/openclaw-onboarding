#!/usr/bin/env python3
"""ghl_survey_builder.py — GoHighLevel native survey builder for Skill 06, Workstream B.

Implements ``build_survey(task, evidence_root)`` as a v2_dispatcher-injected
builder that:
  1. FIELD DEPENDENCIES (F1 grocery-shopping rule): by default (``field_creation
     ='api'``) the survey's custom fields are REUSED from Skill-44 API pre-creation
     — the builder GETs the location's existing keys (``caf locations custom-fields``,
     LOCATION PIT), confirms every field exists, and binds map-only in Part 2. It
     creates NOTHING in the browser. ``field_creation='map_only'`` forbids any
     create; ``field_creation='browser'`` is the LEGACY in-browser Part-1 create,
     retained ONLY as an explicit no-PIT fallback (never the default). Engine-owned
     keys use ``key_policy='verbatim'`` (byte-for-byte, must pre-exist); agent keys
     use ``key_policy='zhc'`` (idempotent ``zhc_<slug>`` create).
  2. Assembles the survey in ``survey-builder-v2`` — welcome slide, Add Object
     Fields (answers bind to {{contact.<key>}}), conditional-logic jump-to rules,
     required-field toggles, Quick-Add contact-capture slide with plain T&C
     consent checkbox, save, Integrate, and survey-URL capture (Part 2 —
     PRD §5.B.2 / canonical Part 2 transcript).

GLUE, NOT THE CLICKER
---------------------
Python emits ordered browser-control commands via ``ghl_builder.browser_cmd``
→ ``agent-browser``; it never mutates GoHighLevel state directly. Owns only
its ledgers (``routing/survey-plan.json``, ``routing/survey-field-map.json``,
``routing/survey-preflight.json``, ``shots/``).

NO LOGIN CODE — the CI guard ``guard-ghl-auth-fallback.sh`` forbids login
patterns outside ``ghl_auth_fallback.py`` / ``ghl_login_browser.py``.
Auth is handled upstream by the dispatcher / seeded browser session.

GOVERNING RULES
---------------
- Headless-only (D6): ``ghl_builder.headless_guard()`` + ``browser_manager.headless_guard()``
- Singleton session: ``browser_manager.browser_session(<GHL_LOCATION_ID>)``
- Rate limits: ``RateGovernor`` (≥ 6 s/save, ≥ 15 s/publish, honor 429 Retry-After)
- Session keepalive: ``SessionKeepalive.due()`` → eval-only ping, NEVER navigate/reload
- Locate by a11y ref first (``snapshot -i`` → ``@eN``), CSS only as documented fallback
- Wait on conditions, never fixed sleeps (``wait -- "<text>"``)
- Screenshot after every material step to ``shots/NN-<phase>.png``
- ``--dry-run`` default: write plan + field-map + ordered click list WITHOUT
  browser execution; flip off only after a full end-to-end live-verified run

MODEL DOCTRINE — client-owned providers, NEVER Anthropic
---------------------------------------------------------
Fallback order: Ollama Cloud → OpenRouter equivalent → Gemini last-resort.
``thinking=high`` on every rung. MiniMax M2 is BANNED; execution uses
MiniMax M3 only → DeepSeek v4 pro. Vision QC goes to MiniMax M3 only.
``assert_model_sovereignty`` hard-blocks any Anthropic slug before dispatch.

COMMAND CENTER HOOKS (fail-soft — never block the build)
---------------------------------------------------------
Phase boundaries call:
  ``cc_board.move_task(task_id, status, note=None)``
  ``cc_board.post_activity(task_id, activity_type, message, metadata=None)``
These functions are added by a parallel agent; called with getattr guard +
try/except so the build proceeds even if they are not yet present.

Flow:
  intake start  → move_task('in_progress') + post_activity('status_changed', …)
  per build step → post_activity('updated', 'Step k/N: …')
  artifact ready → register deliverable + move_task('review')   ← NEVER 'done'
  failure        → move_task('backlog'|'blocked', note=…)

REAL DOMAINS (from transcripts)
--------------------------------
App shell:     ``app.convertandflow.com/v2/location/<LOC>/…``
Survey builder: ``leadgen-apps-form-survey-builder.leadconnectorhq.com/survey-builder-v2/<surveyId>``
(agent-browser v0.27.0 auto-inlines the builder iframe — no manual frame switch needed)

USAGE
-----
    # Dry-run (default):
    result = build_survey(task, "/tmp/run01")          # dry_run=True by default
    result = build_survey(task, "/tmp/run01", dry_run=True)

    # Live (after end-to-end test on a test sub-account):
    result = build_survey(task, "/tmp/run01", dry_run=False)

    # CLI:
    python3 ghl_survey_builder.py --dry-run --location-id LOC123
    python3 ghl_survey_builder.py --selftest

    # Task-driven survey (fields + branching + slide layout from a payload):
    python3 ghl_survey_builder.py --dry-run --task-json /path/to/task.json

TASK-DRIVEN TOPOLOGY (Area 5 fix)
---------------------------------
The survey's shape comes from the TASK payload, never a hardcoded demo:
  task['survey_fields']      — list of field dicts (overrides REFERENCE_FIELDS).
  task['conditional_logic']  — list of {if_field, if_value, then_slide} jump-to
                               rules (overrides the CONDITIONAL_LOGIC_RULES demo).
                               ``if_field`` matches a field by label or key;
                               ``then_slide`` matches a slide by its "Pn - Name"
                               label, bare name, "Pn"/index, or "Slide n".
  task['slides']             — optional per-branch slide layout: an ordered list
                               of {name, fields:[<label|key>, …]} where a slide
                               may carry ONE OR MORE fields and branches may
                               target ANY slide. Omit for the default one-field-
                               per-slide linear layout (fully backward compatible).
  task['converge_slide']     — optional slide ref (label / name / "Pn" / index).
                               BRANCH-CONVERGENCE primitive (Area 5.1): once the
                               router sends a respondent into ONE branch, the other
                               branch slides must be skipped — otherwise their
                               (required) fields sit between the respondent and the
                               submit button and the survey is UNSUBMITTABLE. When
                               ``converge_slide`` is set the builder auto-derives one
                               Jump-To rule per branch, OWNED by that branch's exit
                               slide and conditioned on the router field, that jumps
                               forward to the shared converge slide. Omit for a plain
                               forward-router survey (byte-for-byte backward compat).
A conditional_logic rule may also carry an explicit ``owner_slide`` (slide ref) to
host the rule on a slide OTHER than the one that holds ``if_field`` — this is how a
branch-exit slide jumps on an EARLIER router field's value. ``owner_slide`` defaults
to the slide that hosts ``if_field`` (the forward-router case).
Every ``if_field``, ``then_slide``, ``owner_slide`` and ``converge_slide`` is
validated against the resolved field and slide sets during preflight (P4 family) —
a dangling reference OR a branch that falls through into a sibling (no convergence
jump) is a HARD STOP BEFORE any browser action, never a mid-build failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from typing import Any, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap — make tools/ importable
# ---------------------------------------------------------------------------
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_builder  # noqa: E402  — browser_cmd + headless_guard
import browser_manager  # noqa: E402  — browser_session context manager

# Rate governor + session keepalive + F5(b) pre-phase token re-mint live in
# v2_dispatcher (reused, not reinvented)
from v2_dispatcher import RateGovernor, SessionKeepalive, remint_if_stale  # noqa: E402

try:
    import cc_board as _cc_board  # noqa: E402 — best-effort board producer
except Exception:  # noqa: BLE001
    _cc_board = None  # type: ignore[assignment]

try:
    import ghl_verify as _ghl_verify  # noqa: E402
except Exception:  # noqa: BLE001
    _ghl_verify = None  # type: ignore[assignment]

try:
    import ghl_method as _ghl_method  # noqa: E402  — resolve_install_target
except Exception:  # noqa: BLE001
    _ghl_method = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
SURVEY_BUILDER_VERSION = "v1.3.0"

# ── Field-creation posture (F1 fix — grocery-shopping rule) ────────────────
# The survey rail MUST reuse API-pre-created custom fields (map-only via the
# Add Object Fields tab), NOT create fields in the browser. Three modes:
#   "api"      — DEFAULT. GET existing custom fields; missing ones are created
#                out-of-band by Skill 44 (``caf`` LOCATION PIT — same contract
#                as ghl_form_builder). Part 2 drags the read-back keys only.
#   "map_only" — every field MUST already exist (zero creates). Any planned
#                create is a hard STOP. Used when an engine (Podcast/Anthology)
#                owns the fields and the survey must bind verbatim keys.
#   "browser"  — LEGACY in-browser Part-1 create. Explicit operator-selected
#                fallback for boxes with no PIT ONLY. Never the default.
FIELD_CREATION_MODES = ("api", "map_only", "browser")
DEFAULT_FIELD_CREATION = "api"

# Machine key prefix for AGENT-created custom fields (F2 — matches form builder).
ZHC_KEY_PREFIX = "zhc_"
# Field-key policy per the F2 field-key contract:
#   "zhc"      — agent may idempotently create ``zhc_<snake_slug>`` keys.
#   "verbatim" — the key is engine-owned and MUST already exist; create REFUSED.
KEY_POLICIES = ("zhc", "verbatim")
DEFAULT_KEY_POLICY = "zhc"

# GoHighLevel real domains (from PRD §5.B / transcripts)
GHL_APP_ORIGIN_DEFAULT = os.environ.get(
    "GHL_AGENCY_URL", "https://app.convertandflow.com"
)
GHL_SURVEY_BUILDER_HOST = (
    "leadgen-apps-form-survey-builder.leadconnectorhq.com"
)

# Material step totals for progress reporting
_PART1_BASE_STEPS = 4   # navigate, settings, custom-fields, folder
_PART2_PHASES = 10      # A through K (10 named phases)
# Per-field steps add to _PART1_BASE_STEPS at runtime

# Reference survey custom fields (transcripts / PRD §5.B.1).
# When ``task['survey_fields']`` is supplied, it overrides these entirely.
REFERENCE_FIELDS: List[dict] = [
    {
        "type": "radio",
        "label": "Have you attended one of our events before?",
        "options": ["Yes", "No"],
        "required": True,
        "slide_name": "Attended Events Before",
    },
    {
        "type": "multiline",
        "label": "Which event did you attend, and approximately when was it?",
        "options": [],
        "required": True,
        "slide_name": "Yes, Attended",
    },
    {
        "type": "radio",
        "label": "How did you hear about us? (Select one)",
        "options": [
            "Social media (Instagram, Facebook, LinkedIn)",
            "Referred by a friend",
            "Google",
            "Other",
        ],
        "required": True,
        "slide_name": "How did you hear",
    },
    {
        "type": "dropdown_single",
        "label": "Which best describes your current business stage? "
                 "(Select one from the dropdown)",
        "options": [],  # resolved from task['survey_fields'][3]['options'] at runtime
        "required": True,
        "slide_name": "What Business Stage",
    },
    {
        "type": "file_upload",
        "label": (
            "Please upload your resume or a brief bio so we can learn more about "
            "your background. (Accepted file types: PDF, DOC, DOCX — Max size: 10MB)"
        ),
        "options": [],
        "file_types": ["PDF", "DOCX/DOC", "JPG/JPEG", "PNG"],
        "required": False,  # not in required sweep per PRD §5.B.2 Phase H
        "slide_name": "Upload Resume",
    },
    {
        "type": "dropdown_multiple",
        "label": "Which topics are you most interested in learning more about? "
                 "(Select all that apply)",
        # Leading/trailing spaces trimmed per PRD §5.B.1 gotcha
        "options": [
            "Business automation and AI tools",
            "Marketing and lead generation",
        ],
        "required": True,
        "slide_name": "Topics Interested In",
    },
]

# Conditional logic rules — DOCUMENTED DEMO/FALLBACK ONLY (PRD §5.B.2 Phase G;
# Pn- prefix is stable). A real build supplies ``task['conditional_logic']``,
# which OVERRIDES this constant entirely (see ``_resolve_conditional_rules``).
# This 2-rule "attended events" survey is retained purely as the reference
# example and the no-task fallback; it is NEVER the source of branching when a
# task payload provides its own rules.
CONDITIONAL_LOGIC_RULES: List[dict] = [
    {
        "if_field": "Have you attended one of our events before?",
        "if_value": "Yes",
        "then_slide": "P2 - Attended Events Before",
    },
    {
        "if_field": "Have you attended one of our events before?",
        "if_value": "No",
        "then_slide": "P4 - How did you hear",
    },
]

# ── Phase model ladders (passed to model_router.select when available) ────
# Ollama Cloud FIRST → OpenRouter equivalent → Gemini last-resort (only if live+credited)
# thinking=high on every rung. MiniMax M2 BANNED. Vision only to MiniMax M3.

THINK_LADDER: List[dict] = [
    {
        "rung": 1, "provider": "ollama-cloud", "model": "glm-5.2:cloud",
        "role": "funnel/reasoning", "thinking": "high",
        "note": "Verify glm-5.2:cloud tag live; fallback MODEL_ROUTER_GLM=glm-5.1:cloud",
    },
    {
        "rung": 2, "provider": "ollama-cloud", "model": "kimi-k2.6:cloud",
        "role": "reasoning", "thinking": "high",
        "note": "Kimi via Ollama Cloud ONLY; never kimi-2.6 (wrong slug)",
    },
    {
        "rung": 3, "provider": "ollama-cloud", "model": "deepseek-v4-pro:cloud",
        "role": "reasoning", "thinking": "high",
    },
    {
        "rung": 4, "provider": "openrouter", "model": "z-ai/glm-5.2",
        "role": "funnel/reasoning", "thinking": "high",
    },
    {
        "rung": 5, "provider": "openrouter", "model": "moonshotai/kimi-k2.6",
        "role": "reasoning", "thinking": "high",
    },
    {
        "rung": 6, "provider": "openrouter", "model": "deepseek/deepseek-v4-pro",
        "role": "reasoning", "thinking": "high",
    },
    {
        "rung": 7, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
        "role": "cheap-multimodal-fallback", "thinking": "high",
        "gate": "only_if_live_and_credited",
        "note": "Last-resort only; if 404 override to google/gemini-3.1-flash-lite via MODEL_ROUTER_GEMINI",
    },
]

EXECUTE_LADDER: List[dict] = [
    {
        "rung": 1, "provider": "ollama-cloud", "model": "minimax-m3:cloud",
        "role": "browser-control", "thinking": "high", "probe_gated": True,
        "note": "Probe: tool_call_fired AND parsed AND args=={ok:True}; one retry then advance",
    },
    {
        "rung": 2, "provider": "openrouter", "model": "minimax/minimax-m3",
        "role": "browser-control", "thinking": "high", "probe_gated": True,
    },
    {
        "rung": 3, "provider": "ollama-cloud", "model": "deepseek-v4-pro:cloud",
        "role": "browser-control", "thinking": "high",
    },
    {
        "rung": 4, "provider": "openrouter", "model": "deepseek/deepseek-v4-pro",
        "role": "browser-control", "thinking": "high",
    },
    {
        "rung": 5, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
        "role": "cheap-multimodal-fallback", "thinking": "high",
        "gate": "only_if_live_and_credited",
    },
]

QC_LADDER: List[dict] = [
    {
        "rung": 1, "provider": "ollama-cloud", "model": "minimax-m3:cloud",
        "role": "qc+vision", "thinking": "high", "probe_gated": True,
        "note": "Vision REQUIRED on this rung; never route vision to DeepSeek/GLM",
    },
    {
        "rung": 2, "provider": "openrouter", "model": "minimax/minimax-m3",
        "role": "qc+vision", "thinking": "high", "probe_gated": True,
    },
    {
        "rung": 3, "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
        "role": "cheap-multimodal-fallback", "thinking": "high",
        "gate": "only_if_live_and_credited",
    },
]

# ── GHL field-type display labels ─────────────────────────────────────────
_FIELD_TYPE_LABELS: dict[str, str] = {
    "radio": "Radio select",
    "multiline": "Multi line",
    "dropdown_single": "Dropdown (single)",
    "dropdown_multiple": "Dropdown (multiple)",
    "file_upload": "File upload",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(msg: str) -> None:
    print(f"[ghl_survey_builder] {msg}", file=sys.stderr, flush=True)


def _ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _shot_path(evidence_root: str, n: int, label: str) -> str:
    shots_dir = os.path.join(evidence_root, "shots")
    os.makedirs(shots_dir, exist_ok=True)
    return os.path.join(shots_dir, f"{n:03d}-{label}.png")


# ---------------------------------------------------------------------------
# Board helpers — fail-soft wrappers for the new cc_board v2 API
# (move_task / post_activity added by parallel agent; guarded with getattr)
# ---------------------------------------------------------------------------

def _board_move(task_id: Optional[str], status: str, note: Optional[str] = None) -> None:
    """Move Kanban card to ``status``. Fail-soft: never raises, never blocks build."""
    if not task_id or _cc_board is None:
        return
    try:
        fn = getattr(_cc_board, "move_task", None)
        if fn is not None:
            fn(task_id, status, note=note)
        else:
            # Fallback to existing update_status while new function is being added
            _cc_board.update_status(task_id, status, note=note or "")
    except Exception as exc:  # noqa: BLE001
        _log(f"_board_move({status!r}) fail-soft: {exc}")


def _board_activity(
    task_id: Optional[str],
    activity_type: str,
    message: str,
    metadata: Optional[dict] = None,
) -> None:
    """Post a build-step activity. Fail-soft: never raises, never blocks build."""
    if not task_id or _cc_board is None:
        _log(f"[board:{activity_type}] {message}")
        return
    try:
        fn = getattr(_cc_board, "post_activity", None)
        if fn is not None:
            fn(task_id, activity_type, message, metadata=metadata)
        else:
            _log(f"[board:{activity_type}] {message}")
    except Exception as exc:  # noqa: BLE001
        _log(f"_board_activity({activity_type!r}) fail-soft: {exc}")


def _board_register_deliverable(task_id: str, survey_url: str) -> None:
    """POST the survey URL to /api/tasks/<id>/deliverables. Fail-soft."""
    if not task_id or not survey_url or _cc_board is None:
        return
    try:
        cfg = _cc_board.board_config()
        if cfg is None:
            return
        payload = {"label": "Survey URL", "url": survey_url, "type": "survey_link"}
        url = f"{cfg['base_url']}/api/tasks/{task_id}/deliverables"
        _cc_board._post_json(url, payload, cfg)  # type: ignore[attr-defined]
        _log(f"Registered deliverable: {survey_url!r}")
    except Exception as exc:  # noqa: BLE001
        _log(f"_board_register_deliverable fail-soft: {exc}")


# ---------------------------------------------------------------------------
# Browser command execution (GLUE layer — all GHL writes go through agent-browser)
# ---------------------------------------------------------------------------

def _run_cmd(
    session: str,
    *args: str,
    timeout: int = 30,
    stdin: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Execute one agent-browser command. Returns CompletedProcess; never raises.

    ``stdin`` pipes a payload to the command (used by ``eval --stdin`` so a
    multi-token JS body is NOT shredded by ``browser_cmd`` space-join +
    ``shlex.split``). Mirrors ``ghl_form_builder._ab``.
    """
    cmd_str = ghl_builder.browser_cmd("--session", session, *args)
    _log(f"[ab] {cmd_str}")
    try:
        return subprocess.run(
            shlex.split(cmd_str),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"_run_cmd fail: {exc}")
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=str(exc))


def _screenshot(session: str, path: str) -> None:
    """Capture screenshot (fail-soft — a missed shot never fails the build)."""
    try:
        _run_cmd(session, "screenshot", path, timeout=20)
    except Exception as exc:  # noqa: BLE001
        _log(f"screenshot fail-soft ({path}): {exc}")


def _open(session: str, url: str, timeout: int = 45) -> None:
    """Navigate to a URL and wait for network-idle."""
    _run_cmd(session, "open", url, timeout=timeout)


def _wait(session: str, text: str, timeout: int = 25) -> None:
    """Wait until visible text appears (no fixed sleep)."""
    _run_cmd(session, "wait", "--", text, timeout=timeout)


def _click(session: str, target: str, timeout: int = 15) -> None:
    """Click a visible text/role target."""
    _run_cmd(session, "click", target, timeout=timeout)


def _dblclick(session: str, target: str) -> None:
    """Double-click (e.g. to enter inline edit mode)."""
    _run_cmd(session, "dblclick", target, timeout=15)


def _fill(session: str, label: str, value: str) -> None:
    """Fill an input field identified by label text."""
    _run_cmd(session, "fill", label, value, timeout=15)


def _type(session: str, text: str) -> None:
    """Type text into the focused element."""
    _run_cmd(session, "type", text, timeout=15)


def _eval(session: str, js: str, timeout: int = 15) -> str:
    """Evaluate JS and return stdout (for URL capture, keepalive, router.push).

    JS is piped via ``eval --stdin`` — NEVER a CLI arg: ``browser_cmd`` space-joins
    the argv and ``_run_cmd`` ``shlex.split``s it, which would shred any multi-token
    JS body (proven no-response on ``$router.push`` payloads). ``--stdin`` is the
    proven-safe path (mirrors ``ghl_form_builder._eval``)."""
    result = _run_cmd(session, "eval", "--stdin", stdin=js, timeout=timeout)
    return (result.stdout or "").strip().strip('"').strip("'")


def _snapshot(session: str) -> str:
    """Get the current accessibility snapshot (-i mode)."""
    result = _run_cmd(session, "snapshot", "-i", timeout=20)
    return result.stdout or ""


# ── in-SPA navigation — $router.push ONLY (never open/reload after a token seed) ─
# ROOT CAUSE (2026-07 first live run): Phase A used a full ``open`` of the app URL.
# A full open/reload re-runs GHL's SPA boot gate, which signs a TOKEN-SEEDED
# session out and bounces it to the login form — so Part 2 then fail-softs through
# a login page and builds nothing. The community + form builders never hit this
# because they navigate via ``$router.push`` exclusively (inject-ghl-auth.sh's
# "DO NOT RELOAD" note). These helpers port that proven pattern.
class SurveyAuthStop(RuntimeError):
    """A token-seeded session is not authenticated, or the SPA router is not
    mounted for an in-app navigation. STOP and report — there is NO UI-login / 2FA
    fallback (D7 token-only doctrine)."""


_ROUTER_PUSH_JS = (
    "(async () => {"
    "  const el = document.querySelector('#app');"
    "  const gp = el && el.__vue_app__ && el.__vue_app__.config && el.__vue_app__.config.globalProperties;"
    "  if (!gp || !gp.$router) return 'NO-ROUTER';"
    "  await gp.$router.push({ path: %s });"
    "  await new Promise(r => setTimeout(r, 900));"
    "  return 'nav:' + location.pathname;"
    "})()"
)

_LOGIN_CHECK_JS = (
    "(() => {"
    "  const pwd = !!document.querySelector('input[type=password]');"
    "  const onLogin = /[?&]logout=true/.test(location.href) "
    "|| /\\/login(\\b|$)/.test(location.pathname) || pwd;"
    "  return (onLogin ? 'login:' : 'app:') + location.pathname;"
    "})()"
)


def _assert_logged_in(session: str) -> str:
    """Confirm the token-seeded session is on the app, NOT the login form — so a
    bounced seed STOPS immediately instead of fail-softing Part 2 through a login
    page (the 2026-07 live-run root cause)."""
    res = _eval(session, _LOGIN_CHECK_JS, timeout=15)
    if not res.startswith("app:"):
        raise SurveyAuthStop(
            f"session is NOT logged in ({res or 'no-response'}): the token seed did "
            "not survive. Seed via inject-ghl-auth.sh with GHL_INJECT_KEEP_SESSION=1 "
            "--pre-open and navigate in-app only (a full open/reload re-runs the SPA "
            "boot gate). NO UI-login / 2FA fallback exists.")
    return res


def _router_push(session: str, path: str, expect_contains: str = "") -> str:
    """SPA-navigate via ``$router.push`` (NEVER open/reload — that bounces a
    token-seeded session to login). Raises SurveyAuthStop on a mismatch."""
    res = _eval(session, _ROUTER_PUSH_JS % json.dumps(path), timeout=25)
    if "NO-ROUTER" in res:
        raise SurveyAuthStop(f"SPA store/router not mounted for push to {path!r}")
    if expect_contains and expect_contains not in res:
        loc = _eval(session, "location.pathname", timeout=10)
        if expect_contains not in (loc or ""):
            raise SurveyAuthStop(
                f"router.push to {path!r} landed at {(res or loc)!r} "
                f"(expected to contain {expect_contains!r})")
    return res


def _pre_phase_check(session: str, keepalive: "SessionKeepalive") -> None:
    """F5 uniform keepalive + pre-phase re-mint — call once before EVERY
    multi-minute Part-2 phase (never navigate/reload; both actions below are
    eval-only per D7/F5 doctrine):
      1. keepalive.due() — a harmless no-op eval ping every 30min so the
         session never idles out mid-build.
      2. remint_if_stale() — F5(b): if the seeded id_token is already older
         than the 45min threshold, proactively re-mint + re-seed BEFORE the
         phase starts rather than waiting for a mid-phase 401. Best-effort:
         a failure here never aborts the phase (inject-ghl-auth.sh's own
         bounded reactive re-mint remains the backstop on an actual 401).
    """
    if keepalive.due():
        _eval(session, "true", timeout=5)  # harmless keepalive ping
    try:
        remint_if_stale(session)
    except Exception:  # noqa: BLE001 — proactive remint is never allowed to abort a phase
        pass


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def _idempotency_key(task: dict) -> str:
    client_id = task.get("client_id", task.get("location_id", ""))
    survey_slug = task.get("survey_slug", task.get("title", "survey"))
    brief_hash = hashlib.sha256(
        json.dumps(task.get("brief", {}), sort_keys=True).encode()
    ).hexdigest()[:16]
    raw = f"{client_id}:{survey_slug}:{brief_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

def _run_preflight(task: dict, evidence_root: str) -> dict:
    """Run P1–P8 preflight checks; record results to routing/survey-preflight.json.

    Returns {pass: bool, checks: list, stop_reason?: str}.
    """
    checks: List[dict] = []
    stop_reason: Optional[str] = None

    def chk(name: str, result: bool, detail: str = "", hard: bool = True) -> None:
        nonlocal stop_reason
        checks.append({"check": name, "pass": result, "detail": detail})
        if not result and hard and stop_reason is None:
            stop_reason = f"{name}: {detail}"

    # P1 — location_id present
    loc = (
        task.get("location_id")
        or task.get("GHL_LOCATION_ID")
        or os.environ.get("GHL_LOCATION_ID")
        or os.environ.get("GOHIGHLEVEL_LOCATION_ID", "")
    ).strip()
    chk("P1:location_id", bool(loc), f"location_id={loc!r}")

    # P2 — location gate: no co-mingling (delegated to dispatcher; logged here)
    chk("P2:location_gate", True, "delegated to dispatcher/v2_dispatcher.dispatch_one")

    # P3 — persona matched (warn only; never blocks)
    has_persona = bool(task.get("copy_persona"))
    chk("P3:persona_matched", has_persona,
        "copy_persona present" if has_persona else "no copy_persona; using default voice",
        hard=False)

    # P4 — spec / brief present
    has_spec = bool(task.get("survey_fields") or task.get("brief") or task.get("title"))
    chk("P4:spec_present", has_spec, "survey_fields or brief or title key present")

    # P4 — topology validity (Area-5): the task-driven slide layout and branching
    # references must ALL resolve. A dangling if_field / then_slide, an unknown
    # field in a custom slide, a duplicate placement, or an orphan field is a HARD
    # STOP here — BEFORE any browser action, never a mid-build failure.
    _fields_pf = _resolve_fields(task)
    _slides_pf = _plan_slides(task, _fields_pf)
    _rules_pf = _resolve_conditional_rules(task)
    _topo_errs = _validate_topology(task, _fields_pf, _slides_pf, _rules_pf)
    chk("P4:topology_valid", not _topo_errs,
        "; ".join(_topo_errs) if _topo_errs
        else f"{len(_slides_pf)} slides + {len(_rules_pf)} branch rule(s); "
             "all field + slide references resolve")

    # P5 — duplicate-survey check (delegated to ghl_method if available)
    chk("P5:no_duplicate", True,
        "resolve_install_target will raise InstallTargetError on ambiguous duplicates")

    # P6 — custom-field plan (F1/F2): api/map_only reuse API-pre-created fields.
    mode = _resolve_field_creation_mode(task)
    checks.append({"check": "P6:field_creation_mode", "pass": True,
                   "detail": f"field_creation={mode!r} (default {DEFAULT_FIELD_CREATION!r})"})
    if mode in ("api", "map_only"):
        _fields = _resolve_fields(task)
        _dep = plan_survey_dependencies(
            _fields, task, existing_field_keys=task.get("existing_field_keys")
        )
        # Confirmed-missing verbatim (engine-owned) keys are a HARD STOP.
        chk("P6:verbatim_keys_present", not _dep["blocked"],
            "missing verbatim keys: "
            + ", ".join(m.get("key", m.get("label", "?")) for m in _dep["missing_verbatim_keys"])
            if _dep["blocked"] else "all verbatim keys accounted for (or GET deferred to live)")
        # map_only forbids ANY create (all fields must pre-exist).
        if mode == "map_only":
            creates = [s["field_key"] for s in _dep["custom_fields"] if s["action"] == "create"]
            chk("P6:map_only_no_creates", not creates,
                f"map_only requires zero creates; would create: {creates}"
                if creates else "no creates required")
    else:
        # browser mode: legacy in-browser create — explicit no-PIT fallback only.
        checks.append({"check": "P6:field_plan", "pass": True,
                       "detail": "field_creation='browser' — LEGACY in-browser create "
                                 "(no-PIT fallback ONLY, not the default rail)"})

    # P7 — agent-browser version pin (warn only; logged)
    try:
        browser_manager.assert_agent_browser_version()
        chk("P7:browser_version", True, "version pin OK (0.27.0)")
    except Exception as exc:  # noqa: BLE001
        chk("P7:browser_version", False, str(exc), hard=False)

    # P6/D6 — headless guard
    try:
        ghl_builder.headless_guard()
        chk("P6:headless_guard", True, "AGENT_BROWSER_HEADED not set to a headed value")
    except RuntimeError as exc:
        chk("P6:headless_guard", False, str(exc))

    # P8 — idempotency key computed
    ikey = _idempotency_key(task)
    chk("P8:idempotency_key", True, f"sha256 key={ikey[:16]}…")

    outcome: dict = {"pass": stop_reason is None, "checks": checks, "ts": _ts()}
    if stop_reason:
        outcome["stop_reason"] = stop_reason

    path = os.path.join(evidence_root, "routing", "survey-preflight.json")
    _write_json(path, outcome)
    return outcome


# ---------------------------------------------------------------------------
# Survey plan + field-map builders
# ---------------------------------------------------------------------------

def _resolve_fields(task: dict) -> List[dict]:
    """Return the field list from task or the reference defaults."""
    raw = task.get("survey_fields")
    if raw and isinstance(raw, list) and raw:
        return [dict(f) for f in raw]
    return [dict(f) for f in REFERENCE_FIELDS]


def _resolve_conditional_rules(task: dict) -> List[dict]:
    """Return branching rules from the TASK payload, else the demo fallback.

    Area-5 fix: branching is TASK-DRIVEN. ``task['conditional_logic']`` (a list of
    ``{if_field, if_value, then_slide}`` dicts) OVERRIDES the CONDITIONAL_LOGIC_RULES
    module constant ENTIRELY. The constant is only the documented demo / no-task
    fallback — never the branching source once a task supplies its own rules. A
    task may pass an EMPTY list to build a survey with NO conditional logic.

    Area-5.1: when the task sets ``converge_slide`` the ROUTER rules are augmented
    with auto-derived branch-convergence jumps (one per branch, owned by that
    branch's exit slide) so no branch falls through into a sibling. Absent
    ``converge_slide`` the result is byte-for-byte the pre-existing behaviour.
    """
    raw = task.get("conditional_logic")
    if isinstance(raw, list):
        router = [dict(r) for r in raw]
    else:
        router = [dict(r) for r in CONDITIONAL_LOGIC_RULES]
    return router + _derive_convergence_rules(task, router)


def _norm(s: Any) -> str:
    """Case/space-insensitive normaliser used for reference matching."""
    return str(s or "").strip().lower()


def _match_field(ref: Any, fields: List[dict]) -> Optional[dict]:
    """Resolve a field reference (label, explicit key, or resolved field_key) to
    its field dict. Case-insensitive on label; exact on key. None if unmatched."""
    if ref is None:
        return None
    ref_s = str(ref).strip()
    ref_l = ref_s.lower()
    for f in fields:
        if _norm(f.get("label", "")) == ref_l:
            return f
        explicit = str(f.get("key") or f.get("field_key") or "").strip()
        if explicit and explicit == ref_s:
            return f
        try:
            fk, _pol = _resolve_field_key(f)
        except Exception:  # noqa: BLE001
            fk = ""
        if fk and (fk == ref_s or fk.lower() == ref_l):
            return f
    return None


def _slide_target_label(slide: dict) -> str:
    """Canonical GHL jump-to / navigation label for a question or capture slide:
    ``P{index} - {name}`` (the "Pn -" prefix GHL auto-assigns by position)."""
    return f"P{slide['index']} - {slide['name']}"


def _make_slide_resolver(slides: List[dict]):
    """Return ``resolve(ref) -> slide_dict | None`` for the addressable (question
    + capture) slides. A ref may be a canonical ``P{n} - Name`` label, a bare
    slide name, a ``Pn`` / ``Slide n`` token, or a bare index. Shared by the
    branching normaliser, the convergence-rule deriver, and the topology
    validator so every slide-ref resolves identically."""
    import re as _re
    target_slides = [s for s in slides if s.get("type") in ("question", "capture")]
    by_target_label = {_slide_target_label(s).lower(): s for s in target_slides}
    by_name: dict = {}
    for s in target_slides:
        by_name.setdefault(_norm(s.get("name", "")), s)
    by_index = {s["index"]: s for s in slides}

    def resolve(ref: Any) -> Optional[dict]:
        if ref is None:
            return None
        ref_s = str(ref).strip()
        ref_l = ref_s.lower()
        if ref_l in by_target_label:
            return by_target_label[ref_l]
        if ref_l in by_name:
            return by_name[ref_l]
        m = _re.match(r"^(?:p|slide)\s*(\d+)$", ref_l) or _re.match(r"^(\d+)$", ref_l)
        if m:
            n = int(m.group(1))
            tgt = by_index.get(n)
            if tgt is not None and tgt.get("type") in ("question", "capture"):
                return tgt
        return None

    return resolve


def _derive_convergence_rules(task: dict, router_rules: List[dict]) -> List[dict]:
    """Area-5.1 branch-convergence primitive.

    When the task sets ``converge_slide`` (a slide ref), each router branch must
    re-join the shared tail of the survey instead of falling through into a
    sibling branch (whose required fields would block submission). For every
    ROUTER rule ``{if_field: R, if_value: V, then_slide: B}`` this derives a
    Jump-To rule OWNED by branch B's exit slide, conditioned on ``R == V`` (always
    true once the respondent is on that branch), that jumps forward to the shared
    converge slide C. Emitting these as ordinary rules reuses the whole normalize
    / group / click-list / browser path — the only new datum is ``owner_slide``.

    Returns [] when ``converge_slide`` is absent (byte-for-byte backward
    compatible) or the topology is degenerate (a dangling converge ref is surfaced
    separately by ``_validate_topology``); it NEVER raises.
    """
    converge_ref = task.get("converge_slide")
    if not converge_ref:
        return []
    fields = _resolve_fields(task)
    slides = _plan_slides(task, fields)
    resolve = _make_slide_resolver(slides)
    converge = resolve(converge_ref)
    if converge is None:
        return []  # dangling — _validate_topology reports P4:topology_valid failure

    # Branch entry slides = the router rules' then_slide targets. Skip any rule
    # that already carries an explicit owner_slide (i.e. is itself a jump wired
    # onto a non-router slide, not a forward router).
    entries: List[tuple] = []  # [(branch_entry_slide, rule), …]
    for r in router_rules:
        if r.get("owner_slide"):
            continue
        b = resolve(r.get("then_slide"))
        if b is not None:
            entries.append((b, r))
    if not entries:
        return []

    entry_indices = sorted({b["index"] for b, _ in entries})
    by_index = {s["index"]: s for s in slides}
    derived: List[dict] = []
    for b, r in entries:
        if b["index"] >= converge["index"]:
            continue  # branch at/after the converge slide — nothing to skip
        # The branch runs contiguously from its entry to just before the next
        # branch entry (or the converge slide). Wire the jump onto its EXIT slide
        # — for the single-slide branches these intakes use, exit == entry.
        later = [i for i in entry_indices if i > b["index"]]
        boundary = min(later) if later else converge["index"]
        exit_index = min(boundary - 1, converge["index"] - 1)
        if exit_index < b["index"]:
            exit_index = b["index"]
        exit_slide = by_index.get(exit_index, b)
        derived.append({
            "if_field": r.get("if_field"),
            "if_value": r.get("if_value"),
            "then_slide": converge_ref,
            "owner_slide": _slide_target_label(exit_slide),
            "kind": "converge",
        })
    return derived


def _plan_slides(task: dict, fields: List[dict]) -> List[dict]:
    """Build the ordered slide model (THINK layer): welcome + question slide(s) +
    contact-capture. TASK-DRIVEN and per-branch capable.

    Default (no ``task['slides']``): one question slide per field, in order —
    byte-for-byte backward compatible with every existing caller.

    Custom (``task['slides']`` present): each entry is ``{name, fields:[ref…]}``
    (a bare list of refs, or ``{slide_name, field_labels}``, are also accepted).
    A slide may carry ONE OR MORE fields and branches may target any slide.
    Unresolved refs are recorded under a private ``_unresolved`` key so
    ``_validate_topology`` can HARD-STOP preflight; this builder never raises.
    """
    copy_persona = task.get("copy_persona") or {}
    business_name = task.get("business_name", "[BUSINESS NAME]")
    campaign = task.get("campaign", "our campaign")

    slides: List[dict] = [{
        "index": 1,
        "name": "Welcome Slide",
        "type": "welcome",
        "element": "Text",
        "copy_persona_label": copy_persona.get("label", ""),
    }]

    layout = task.get("slides")
    idx = 2
    if isinstance(layout, list) and layout:
        for entry in layout:
            # Accept {name, fields}, {slide_name, field_labels}, or a bare list.
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("slide_name") or f"Slide {idx}"
                refs = entry.get("fields")
                if refs is None:
                    refs = entry.get("field_labels", [])
            elif isinstance(entry, (list, tuple)):
                name = f"Slide {idx}"
                refs = list(entry)
            else:
                name = str(entry)
                refs = [entry]
            resolved: List[dict] = []
            unresolved: List[str] = []
            for r in (refs or []):
                mf = _match_field(r, fields)
                if mf is None:
                    unresolved.append(str(r))
                else:
                    resolved.append(mf)
            slide = {
                "index": idx,
                "name": name,
                "type": "question",
                "field_labels": [f.get("label", "") for f in resolved],
                "field_types": [f.get("type", "") for f in resolved],
                "fields": [
                    {"label": f.get("label", ""), "type": f.get("type", ""),
                     "required": bool(f.get("required", True))}
                    for f in resolved
                ],
                "required": any(f.get("required", True) for f in resolved),
                # back-compat singular mirrors (first field on the slide)
                "field_label": resolved[0].get("label", "") if resolved else "",
                "field_type": resolved[0].get("type", "") if resolved else "",
            }
            if unresolved:
                slide["_unresolved"] = unresolved
            slides.append(slide)
            idx += 1
    else:
        # Default linear layout: one field per slide.
        for f in fields:
            slides.append({
                "index": idx,
                "name": f.get("slide_name", ""),
                "type": "question",
                "field_labels": [f.get("label", "")],
                "field_types": [f.get("type", "")],
                "fields": [{"label": f.get("label", ""), "type": f.get("type", ""),
                            "required": bool(f.get("required", True))}],
                "required": bool(f.get("required", True)),
                "field_label": f.get("label", ""),
                "field_type": f.get("type", ""),
            })
            idx += 1

    slides.append({
        "index": idx,
        "name": "Contact Capture",
        "type": "capture",
        "elements": ["First Name", "Last Name", "Email", "Phone", "T & C"],
        "required_elements": ["Email", "Phone"],
        "business_name": business_name,
        "campaign": campaign,
        "note": "T & C is plain marketing-consent checkbox — NOT A2P/10DLC",
    })
    return slides


def _normalize_conditional_logic(
    rules: List[dict], fields: List[dict], slides: List[dict]
) -> tuple[List[dict], List[str]]:
    """Resolve + validate branching rules against the planned fields and slides.

    Returns ``(normalized_rules, errors)``. Each normalized rule carries the
    canonical ``if_field`` label, the canonical ``then_slide`` target label
    (``P{n} - {name}``), and the OWNER slide that hosts the ``if_field``
    (``owner_slide_index`` / ``owner_slide_label``) — so Phase G navigates to the
    RIGHT slide instead of a hardcoded "Slide 2". ``errors`` lists every unknown
    ``if_field`` and every dangling ``then_slide``.
    """
    errors: List[str] = []

    # Jump-to targets: question + capture slides are addressable (shared resolver).
    resolve_then = _make_slide_resolver(slides)

    # field label -> owner (first question slide that lists the label)
    owner_by_label: dict = {}
    for s in slides:
        if s.get("type") != "question":
            continue
        for lbl in s.get("field_labels", []):
            owner_by_label.setdefault(_norm(lbl), s)

    normalized: List[dict] = []
    for i, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            errors.append(f"conditional rule {i}: not an object")
            continue
        if_field_ref = rule.get("if_field")
        mf = _match_field(if_field_ref, fields)
        owner: Optional[dict] = None
        if mf is None:
            errors.append(
                f"conditional rule {i}: unknown if_field {if_field_ref!r} "
                "(no matching survey field)"
            )
        else:
            owner = owner_by_label.get(_norm(mf.get("label", "")))
            if owner is None:
                errors.append(
                    f"conditional rule {i}: if_field {mf.get('label')!r} is not "
                    "placed on any survey slide"
                )
        # An explicit ``owner_slide`` hosts the rule on a slide OTHER than the one
        # that holds ``if_field`` (branch-convergence / cross-slide jumps). It
        # OVERRIDES the field-derived owner; a dangling ref is a hard error.
        explicit_owner_ref = rule.get("owner_slide")
        if explicit_owner_ref is not None:
            ex_owner = resolve_then(explicit_owner_ref)
            if ex_owner is None:
                errors.append(
                    f"conditional rule {i}: dangling owner_slide "
                    f"{explicit_owner_ref!r} (no matching slide in the planned survey)"
                )
            else:
                owner = ex_owner
        then_ref = rule.get("then_slide")
        target = resolve_then(then_ref)
        if target is None:
            errors.append(
                f"conditional rule {i}: dangling then_slide {then_ref!r} "
                "(no matching slide in the planned survey)"
            )
        nrule = dict(rule)
        if mf is not None:
            nrule["if_field"] = mf.get("label", if_field_ref)
        if owner is not None:
            nrule["owner_slide_index"] = owner["index"]
            nrule["owner_slide_label"] = _slide_target_label(owner)
        if target is not None:
            nrule["then_slide"] = _slide_target_label(target)
        normalized.append(nrule)

    return normalized, errors


def _group_rules_by_owner_slide(rules: List[dict]) -> List[tuple]:
    """Group NORMALIZED branching rules by their owner slide (the slide that
    hosts each rule's ``if_field``), preserving first-seen order.

    Returns ``[(owner_slide_label, [rule, …]), …]`` so a multi-branch survey
    wires each rule on the RIGHT slide (never a hardcoded "Slide 2"). The owner
    label falls back to the first question slide ("Slide 2") only when a rule
    carries no owner metadata (defensive; valid topology always resolves it).
    """
    groups: List[list] = []          # [ [owner_label, [rule, …]], … ]
    order: dict = {}
    for rule in rules:
        owner_label = (
            rule.get("owner_slide_label")
            or (f"Slide {rule['owner_slide_index']}"
                if rule.get("owner_slide_index") else None)
            or "Slide 2"  # last-resort fallback (first question slide)
        )
        if owner_label not in order:
            order[owner_label] = len(groups)
            groups.append([owner_label, []])
        groups[order[owner_label]][1].append(rule)
    return [(lbl, grp) for lbl, grp in groups]


def _validate_topology(
    task: dict, fields: List[dict], slides: List[dict], rules: List[dict]
) -> List[str]:
    """Collect every structural error in the planned survey topology:
      • a custom slide layout referencing an unknown field,
      • a field placed on more than one slide,
      • a survey field not placed on any slide (orphan; custom layout only),
      • an unknown ``if_field`` or a dangling ``then_slide`` in the branching.
    Returns [] when sound. Consumed by preflight P4 as a HARD STOP so a dangling
    reference aborts BEFORE any browser action.
    """
    errors: List[str] = []
    question_slides = [s for s in slides if s.get("type") == "question"]

    # (1) unresolved field references inside a custom layout
    for s in question_slides:
        if s.get("_unresolved"):
            errors.append(
                f"slide {s['index']} ({s.get('name', '?')!r}) references unknown "
                f"field(s): {s['_unresolved']}"
            )

    # (2)/(3) placement coverage — only when a custom layout is supplied
    layout_given = isinstance(task.get("slides"), list) and bool(task.get("slides"))
    if layout_given:
        placed: dict = {}
        for s in question_slides:
            for lbl in s.get("field_labels", []):
                placed[_norm(lbl)] = placed.get(_norm(lbl), 0) + 1
        for lbl, cnt in placed.items():
            if cnt > 1:
                errors.append(
                    f"field {lbl!r} is placed on {cnt} slides (must be exactly one)"
                )
        for f in fields:
            if _norm(f.get("label", "")) not in placed:
                errors.append(
                    f"survey field {f.get('label', '?')!r} is not placed on any "
                    "slide (orphan) — add it to task['slides']"
                )

    # (4) branching references
    _norm_rules, rule_errors = _normalize_conditional_logic(rules, fields, slides)
    errors.extend(rule_errors)

    # (5) branch convergence (opt-in via ``converge_slide``): every router branch
    # must reach the shared converge slide — either it is immediately before it
    # (linear next) or it carries a convergence jump. A branch with neither falls
    # through into a sibling branch whose required fields make the survey
    # UNSUBMITTABLE, so it is a HARD STOP here (not a mid-build surprise).
    converge_ref = task.get("converge_slide")
    if converge_ref:
        resolve = _make_slide_resolver(slides)
        converge = resolve(converge_ref)
        if converge is None:
            errors.append(
                f"converge_slide {converge_ref!r} does not resolve to a survey slide"
            )
        else:
            c_label = _slide_target_label(converge)
            c_idx = converge["index"]
            # A convergence jump is any normalized rule that carries an explicit
            # ``owner_slide`` (it re-hosts the jump on a branch-exit slide); a
            # forward router does not. ``_norm_rules`` preserves both ``owner_slide``
            # and ``owner_slide_label``, so no re-zip against the raw rules is needed.
            conv_by_owner_idx: dict = {}
            for nr in _norm_rules:
                if nr.get("owner_slide"):
                    ow = resolve(nr.get("owner_slide_label"))
                    if ow is not None:
                        conv_by_owner_idx.setdefault(ow["index"], set()).add(
                            nr.get("then_slide"))
            for nr in _norm_rules:
                if nr.get("owner_slide"):
                    continue  # a convergence jump, not a forward router
                b = resolve(nr.get("then_slide"))
                if b is None or b["index"] >= c_idx or nr.get("then_slide") == c_label:
                    continue
                reaches = b["index"] == c_idx - 1 or any(
                    c_label in tgts and b["index"] <= oi < c_idx
                    for oi, tgts in conv_by_owner_idx.items()
                )
                if not reaches:
                    errors.append(
                        f"branch slide {nr.get('then_slide')!r} falls through into a "
                        f"sibling branch (no convergence jump to {c_label!r}) — "
                        "respondent cannot submit; set converge_slide / add a jump"
                    )
    return errors


def _build_survey_plan(task: dict, fields: List[dict]) -> dict:
    """Build the routing/survey-plan.json structure (THINK output).

    TASK-DRIVEN: the slide layout comes from ``_plan_slides`` (per-branch capable,
    default linear) and the branching from ``_resolve_conditional_rules`` +
    ``_normalize_conditional_logic`` — NEVER the hardcoded demo constant once the
    task supplies its own. The plan reflects the real survey definition, not the
    2-rule reference demo.
    """
    folder_name = task.get("folder_name", "Sample Survey")
    survey_name = task.get("survey_name", task.get("title", "New Survey"))
    location_id = (
        task.get("location_id")
        or task.get("GHL_LOCATION_ID")
        or os.environ.get("GHL_LOCATION_ID", "")
    )

    slides = _plan_slides(task, fields)
    raw_rules = _resolve_conditional_rules(task)
    norm_rules, _rule_errors = _normalize_conditional_logic(raw_rules, fields, slides)

    # Strip private planning keys before serialization.
    clean_slides = [{k: v for k, v in s.items() if not k.startswith("_")}
                    for s in slides]

    layout_given = isinstance(task.get("slides"), list) and bool(task.get("slides"))
    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "survey_name": survey_name,
        "folder_name": folder_name,
        "location_id": location_id,
        "total_slides": len(clean_slides),
        "slides": clean_slides,
        "fields": fields,
        "conditional_logic": norm_rules,
        "conditional_logic_source": (
            "task" if isinstance(task.get("conditional_logic"), list) else "reference-demo"
        ),
        "layout_source": "task" if layout_given else "linear-default",
        "model_ladders": {
            "think": THINK_LADDER,
            "execute": EXECUTE_LADDER,
            "qc": QC_LADDER,
        },
        "real_domains": {
            "app_shell": GHL_APP_ORIGIN_DEFAULT,
            "survey_builder": f"https://{GHL_SURVEY_BUILDER_HOST}/survey-builder-v2/<surveyId>",
        },
    }


def _auto_key(label: str) -> str:
    """Derive a GHL-style merge-token key from a field label."""
    import re
    key = label.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")[:48]
    return key


# ---------------------------------------------------------------------------
# F2 — field-key contract (zhc vs verbatim)
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """snake_slug (lowercase, no spaces/specials, ≤48) — matches ghl_form_builder."""
    import re
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower().strip()).strip("_")[:48]


def _resolve_field_key(field: dict) -> tuple[str, str]:
    """Return ``(field_key, key_policy)`` for one survey field per the F2 contract.

    ``key_policy: "verbatim"`` → the key is engine-owned; it is used EXACTLY as
    supplied (``field['key']``/``field['field_key']``) — never zhc-prefixed, never
    slugged — and MUST already exist on the location (create is REFUSED).
    ``key_policy: "zhc"`` (default) → the agent may idempotently create a
    ``zhc_<snake_slug>`` key derived from an explicit key or, failing that, the
    label. Idempotent: never double-prefixes.
    """
    policy = str(field.get("key_policy") or DEFAULT_KEY_POLICY).lower()
    if policy not in KEY_POLICIES:
        policy = DEFAULT_KEY_POLICY
    explicit = (field.get("key") or field.get("field_key") or "").strip()
    if policy == "verbatim":
        # Preserve byte-for-byte (including double underscores, e.g.
        # podcast_survey__additional_info). No slugging, no prefix.
        return explicit, "verbatim"
    base = explicit or field.get("label", "")
    slug = _slug(base)
    if not slug:
        slug = "field"
    if not slug.startswith(ZHC_KEY_PREFIX):
        slug = f"{ZHC_KEY_PREFIX}{slug}"
    return slug, "zhc"


def _caf_list_field_keys(location_id: str, timeout: int = 30) -> Optional[List[str]]:
    """Best-effort LIVE read-back of existing custom-field keys via Skill 44 ``caf``.

    GET-first idempotency probe (LOCATION PIT). Returns the list of existing
    custom-field keys, or ``None`` when the ``caf`` rail is unavailable / errors
    (the caller then falls back to task-provided ``existing_field_keys`` and, if
    it still cannot confirm a key, STOPS — it NEVER drags an unconfirmed field).

    Fully guarded: never raises, never mutates GHL state (read-only listing).
    """
    cmd = ["caf", "locations", "custom-fields", "--json"]
    if location_id:
        cmd += ["--location-id", location_id]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _log(f"_caf_list_field_keys: caf unavailable ({exc}) — GET-first probe skipped")
        return None
    if cp.returncode != 0:
        _log(f"_caf_list_field_keys: caf exit {cp.returncode}: {(cp.stderr or '')[:160]}")
        return None
    try:
        data = json.loads(cp.stdout or "[]")
    except Exception as exc:  # noqa: BLE001
        _log(f"_caf_list_field_keys: JSON parse failed ({exc})")
        return None
    # Tolerant extraction — caf may return a bare list or {customFields:[...]}.
    rows = data.get("customFields", data) if isinstance(data, dict) else data
    keys: List[str] = []
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            k = r.get("fieldKey") or r.get("key") or r.get("name") or ""
            # GHL fieldKey is often "contact.zhc_foo" — keep the tail token too.
            if isinstance(k, str) and k:
                keys.append(k)
                if "." in k:
                    keys.append(k.rsplit(".", 1)[-1])
    _log(f"_caf_list_field_keys: {len(keys)} existing keys read from location {location_id!r}")
    return keys


def plan_survey_dependencies(
    fields: List[dict],
    task: dict,
    existing_field_keys: Optional[List[str]] = None,
) -> dict:
    """Build the Skill-44 dependency plan for a survey's custom fields (F1/F2).

    Identical in shape+intent to ``ghl_form_builder.plan_dependencies`` so the
    survey rail obeys the same grocery-shopping rule the form rail already does:
    GET existing custom fields → REUSE any matching key → CREATE only the missing
    ``zhc_`` remainder (out-of-band via ``caf`` LOCATION PIT) → read back → the
    browser then only DRAGS pre-created keys via Add Object Fields.

    ``action`` per field:
      • ``reuse``          — key already exists on the location.
      • ``create``         — missing ``zhc`` key; Skill 44 creates it (api mode).
      • ``REFUSED``        — missing ``verbatim`` (engine-owned) key AFTER a GET;
                             hard-block, listed in ``missing_verbatim_keys``.
      • ``verify_required``— ``verbatim`` key, but no GET has been performed yet
                             (``existing_field_keys`` is None) — the live path
                             MUST GET-and-confirm before it may bind the field.
    """
    live_get_done = existing_field_keys is not None
    existing = [k.lower() for k in (existing_field_keys or [])]

    specs: List[dict] = []
    missing_verbatim: List[dict] = []
    for f in fields:
        key, policy = _resolve_field_key(f)
        label = f.get("label", "")
        exists = key.lower() in existing if key else False
        if policy == "verbatim":
            if not key:
                action = "REFUSED"
                missing_verbatim.append(
                    {"label": label, "reason": "key_policy=verbatim but no key supplied"}
                )
            elif not live_get_done:
                action = "verify_required"
            elif exists:
                action = "reuse"
            else:
                action = "REFUSED"
                missing_verbatim.append({"label": label, "key": key,
                                         "reason": "verbatim key not present on location"})
        else:  # zhc
            action = "reuse" if exists else "create"
        specs.append({
            "field_key": key,
            "custom_field_name": key,
            "label": label,
            "data_type": f.get("type", "single_line"),
            "options": [o.strip() for o in f.get("options", []) if str(o).strip()],
            "merge_token": f"{{{{contact.{key}}}}}" if key else "",
            "key_policy": policy,
            "action": action,
        })

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "owner_skill": "44-convert-and-flow-operator",
        "cli": "caf (PIT-authenticated, LOCATION PIT)",
        "folder": task.get("folder_name", "Sample Survey"),
        "idempotency": {
            "live_get_done": live_get_done,
            "live_get_required": not live_get_done,
            "probe_cmd": "caf locations custom-fields --json",
            "rule": "GET existing custom fields; REUSE any matching key; only "
                    "CREATE the missing zhc_ remainder. verbatim keys are never "
                    "created — they MUST pre-exist. Never duplicate.",
        },
        "custom_fields": specs,
        "blocked": bool(missing_verbatim),
        "missing_verbatim_keys": missing_verbatim,
        "note": "Skill 44 creates/looks-up these on the location BEFORE the browser "
                "build. Part 2 then only DRAGS pre-created keys via Add Object "
                "Fields. In-browser custom-field creation is DISALLOWED except in "
                "explicit field_creation='browser' fallback mode.",
    }


def _resolve_field_creation_mode(task: dict) -> str:
    """Resolve + validate the field-creation posture (default 'api')."""
    mode = str(task.get("field_creation") or DEFAULT_FIELD_CREATION).lower()
    if mode not in FIELD_CREATION_MODES:
        _log(f"unknown field_creation={mode!r} — defaulting to {DEFAULT_FIELD_CREATION!r}")
        mode = DEFAULT_FIELD_CREATION
    return mode


def _build_field_map(fields: List[dict], folder_name: str) -> dict:
    """Build routing/survey-field-map.json."""
    custom_entries: List[dict] = []
    for f in fields:
        key, policy = _resolve_field_key(f)
        custom_entries.append({
            "slide_name": f["slide_name"],
            "field_label": f["label"],
            "field_type": f["type"],
            "field_key": key,
            "key_policy": policy,  # 'zhc' (create-able) or 'verbatim' (must pre-exist)
            "merge_token": f"{{{{contact.{key}}}}}" if key else "",
            "folder": folder_name,
            "action": f.get("action", "create"),  # refined by plan_survey_dependencies
            "required": f.get("required", False),
            "options": [o.strip() for o in f.get("options", [])],
        })

    # Native Quick-Add contact-capture fields
    capture_entries: List[dict] = [
        {
            "slide_name": "Contact Capture",
            "field_label": "First Name",
            "field_type": "quick_add",
            "field_key": "first_name",
            "merge_token": "{{contact.first_name}}",
            "required": False,
        },
        {
            "slide_name": "Contact Capture",
            "field_label": "Last Name",
            "field_type": "quick_add",
            "field_key": "last_name",
            "merge_token": "{{contact.last_name}}",
            "required": False,
        },
        {
            "slide_name": "Contact Capture",
            "field_label": "Email",
            "field_type": "quick_add",
            "field_key": "email",
            "merge_token": "{{contact.email}}",
            "required": True,
        },
        {
            "slide_name": "Contact Capture",
            "field_label": "Phone",
            "field_type": "quick_add",
            "field_key": "phone",
            "merge_token": "{{contact.phone}}",
            "required": True,
        },
        {
            "slide_name": "Contact Capture",
            "field_label": "T & C",
            "field_type": "terms_and_conditions",
            "field_key": "tc_consent",
            "merge_token": "",
            "required": False,
            "note": "Plain marketing-consent checkbox — NOT A2P/10DLC. "
                    "Edit [BUSINESS NAME] and campaign placeholder in the consent copy.",
        },
    ]

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "folder": folder_name,
        "custom_fields": custom_entries,
        "capture_fields": capture_entries,
    }


# ---------------------------------------------------------------------------
# Part 1 — Contact custom-field folder + fields
# ---------------------------------------------------------------------------

def _p1_create_folder(
    session: str,
    location_id: str,
    folder_name: str,
    gov: RateGovernor,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Navigate to Custom Fields and create the folder (Part 1 steps 1–9).

    After this returns, the browser is on the open-folder URL:
    ``…/settings/fields?tab=field…&parentId=<FOLDER_ID>&object=contact``
    and the ``Add custom field`` button is visible.
    """
    _log(f"P1: creating folder {folder_name!r} for location {location_id}")
    app_url = f"{GHL_APP_ORIGIN_DEFAULT}/v2/location/{location_id}/dashboard"

    # Step 1: navigate to dashboard
    _open(session, app_url)
    _wait(session, "Dashboard")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-01-dashboard"))

    # Step 2: click Settings (pinned bottom of far-left nav)
    _click(session, "Settings")
    _wait(session, "Business Profile")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-02-settings"))

    # Step 3: click Custom Fields
    _click(session, "Custom Fields")
    _wait(session, "Custom fields")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-03-custom-fields"))

    # Step 4: confirm object selector shows Contact
    # (it defaults to Contact; no interaction needed unless it shows another object)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-04-contact-object"))

    # Step 5: click Create folder
    _click(session, "Create folder")
    _wait(session, "Folder name")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-05-create-folder-dialog"))

    # Step 6: type folder name + click Create in dialog
    _fill(session, "Folder name", folder_name)
    # Dialog Create button (scoped; distinct from any page-level Create)
    _run_cmd(session, "click", "Create")
    _wait(session, folder_name)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-06-folder-created"))

    # Step 7: click Folders tab
    _click(session, "Folders")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-07-folders-tab"))

    # Step 8: open the folder (blue link); URL must contain parentId=<FOLDER_ID>&object=contact
    _click(session, folder_name)
    _wait(session, "Add custom field")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p1-08-folder-open"))


def _p1_create_field(
    session: str,
    field: dict,
    is_first: bool,
    gov: RateGovernor,
    evidence_root: str,
    shot_n: List[int],
    field_index: int,
) -> None:
    """Create one custom field in the open folder (inner loop for Part 1).

    Covers steps a–g of the per-field inner loop (PRD §5.B.1).
    """
    label = field["label"]
    ftype = field["type"]
    type_label = _FIELD_TYPE_LABELS.get(ftype, ftype)
    _log(f"  P1 field {field_index}: {label[:40]!r} ({ftype})")

    # Step a/8: open the Create-custom-field modal
    if is_first:
        _click(session, "Add custom field")  # centered CTA for first field
    else:
        _click(session, "Create field")  # blue + upper-right for subsequent fields
    _wait(session, "Field type")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                    f"p1-field{field_index:02d}-modal"))

    # Step b: select field type
    # Open the combobox (default value is "Single line")
    _click(session, "Single line")
    _wait(session, "Radio select")  # wait for listbox to open
    # If the option shows "loading", wait and re-try (per PRD gotcha)
    _click(session, type_label)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                    f"p1-field{field_index:02d}-type"))

    # Step c: type the field name (trim whitespace)
    _fill(session, "Enter name", label.strip())

    # Step d: add options (choice types only; trim each option value)
    for opt in field.get("options", []):
        opt_clean = opt.strip()
        if not opt_clean:
            continue
        _click(session, "Add option")
        _type(session, opt_clean)

    # Step e: configure accepted file types (file_upload only)
    if ftype == "file_upload":
        for ft in field.get("file_types", ["PDF", "DOCX/DOC", "JPG/JPEG", "PNG"]):
            _click(session, ft)

    # Step f: save the field (wait for button to turn solid blue, then click)
    gov.before("save")
    _wait(session, "Create custom field")
    _click(session, "Create custom field")
    # Wait for the field label to appear in the folder list
    _wait(session, label.strip()[:25], timeout=20)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                    f"p1-field{field_index:02d}-saved"))


# ---------------------------------------------------------------------------
# Part 2 — Build survey in survey-builder-v2
# ---------------------------------------------------------------------------

def _p2_navigate_create(
    session: str,
    location_id: str,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase A: navigate to Surveys and click Add survey (PRD §5.B.2 steps 1–4)."""
    _log("P2-A: navigate to Surveys + create survey")

    # Step 1: land on the dashboard IN-APP. The token-seeded session is already on
    # the dashboard (inject-ghl-auth.sh --pre-open activates via $router.push); a
    # full `open` here would re-run the SPA boot gate and bounce the seed to the
    # login form (2026-07 live-run root cause). Assert we are logged in, then
    # SPA-route — NEVER a full open/reload.
    _assert_logged_in(session)
    _router_push(session, f"/v2/location/{location_id}/dashboard",
                 expect_contains="/dashboard")
    _wait(session, "Dashboard")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-a-dashboard"))

    # Step 2: open Sites (left rail)
    _click(session, "Sites")
    _wait(session, "Funnels")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-a-sites"))

    # Step 3: click Surveys sub-nav tab
    _click(session, "Surveys")
    _wait(session, "Add survey")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-a-surveys-tab"))

    # Step 4: click Add survey; builder opens in the iframe
    # URL: …/survey-builder/main → redirect to leadconnectorhq.com/survey-builder-v2/<surveyId>
    _click(session, "Add survey")
    _wait(session, "Slide 1", timeout=45)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-a-builder-opened"))


def _p2_rename_survey(
    session: str,
    survey_name: str,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase B: rename Survey 0 to the target name (steps 5–10, PRD §5.B.2)."""
    _log(f"P2-B: rename survey to {survey_name!r}")

    # Transcript steps 5–10: multiple clicks on 'Survey 0' to enter inline edit.
    # Double-click is the clean path; transcript shows multiple single-clicks as
    # the recorder captured the operator double-clicking imprecisely.
    _dblclick(session, "Survey 0")
    _fill(session, "Survey 0", survey_name)
    # Commit by clicking the canvas (outside the title input)
    _click(session, "Slide 1")
    _wait(session, survey_name)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-b-renamed"))


def _p2_add_slides(
    session: str,
    num_additional: int,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase C: click Add Slide N times (steps 13–17 + 68 + 85 + 94, PRD §5.B.2)."""
    _log(f"P2-C: adding {num_additional} additional slides")
    for i in range(num_additional):
        _click(session, "Add Slide")
        _wait(session, f"Slide {i + 2}")
        _log(f"  Slide {i + 2} added")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-c-all-slides-added"))


def _p2_welcome_slide(
    session: str,
    welcome_copy: str,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase D: Slide 1 welcome slide — Text element + copy + style + rename.

    IMPORTANT: use the plain Text element (Customized section), NOT Multi Line or
    Text Box List (those are answer inputs). If the wrong element is added,
    delete and re-add the Text element.
    """
    _log("P2-D: welcome slide — Text element")

    # Select Slide 1
    _click(session, "Slide 1")

    # Step 9: open Add Elements drawer
    _click(session, "Add Elements")
    _wait(session, "Quick Add")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-d-elements-drawer"))

    # Step 10: click Text (exact — NOT Multi Line / Text Box List)
    _click(session, "Text")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-d-text-element"))

    # Step 11: type the persona-voice welcome copy
    _click(session, "Survey Element")
    _type(session, welcome_copy)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-d-welcome-copy"))

    # Step 12: optional styling (inter, Paragraph, 16px, Center, Text color)
    # Emit clicks — actual toolbar controls depend on snapshot refs
    _run_cmd(session, "click", "inter", timeout=10)
    _run_cmd(session, "click", "Paragraph", timeout=10)

    # Step 13: rename slide via gear → Slide Name = 'Welcome Slide'
    _run_cmd(session, "click", "gear", timeout=10)
    _fill(session, "Slide Name", "Welcome Slide")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-d-slide-renamed"))


def _p2_pull_object_fields(
    session: str,
    folder_name: str,
    fields: List[dict],
    evidence_root: str,
    shot_n: List[int],
    dep_custom_fields: Optional[List[dict]] = None,
    slides: Optional[List[dict]] = None,
) -> None:
    """Phase E: Add Object Fields — drag each PRE-CREATED custom field onto its slide.

    Uses the ``Add Object Fields`` tab (NOT Quick Add). Each dragged field writes
    its answer directly to ``{{contact.<key>}}``.

    F1 CONTRACT: ``dep_custom_fields`` is the GET-confirmed read-back key list from
    ``plan_survey_dependencies``. When supplied, this method binds ONLY those
    confirmed keys — it never assumes a field was "just created" in the browser.
    A field whose key is not confirmed present (action not reuse/create) is a
    STOP-and-report, never a silent in-browser create.
    """
    _log(f"P2-E: Add Object Fields from folder {folder_name!r}")
    folder_upper = folder_name.upper()

    # F1 guard: bind only GET-confirmed keys.
    confirmed_by_label = {}
    if dep_custom_fields:
        for s in dep_custom_fields:
            if s.get("action") in ("reuse", "create") and s.get("field_key"):
                confirmed_by_label[s.get("label", "")] = s["field_key"]
        unconfirmed = [
            s.get("label") for s in dep_custom_fields
            if s.get("action") not in ("reuse", "create")
        ]
        if unconfirmed:
            raise RuntimeError(
                "P2-E refuses to bind unconfirmed custom field(s) "
                f"(no read-back key): {unconfirmed}. Pre-create via Skill 44 first."
            )

    # Build the ordered (field, target-slide) drag plan from the planned slide
    # model (Area-5). Default (no custom layout / slides=None): one field per
    # slide starting at Slide 2 — byte-identical to the legacy linear behavior.
    # Custom layout: a slide may host >1 field and each field drags onto its
    # OWNER slide (per-branch capable, not one-field-per-slide).
    by_label = {f.get("label", ""): f for f in fields}
    q_slides = [s for s in (slides or []) if s.get("type") == "question"]
    drag_plan: List[tuple] = []  # (field_dict, slide_label)
    if q_slides:
        for s in q_slides:
            slide_label = f"Slide {s['index']}"
            for lbl in s.get("field_labels", []):
                f = by_label.get(lbl)
                if f is not None:
                    drag_plan.append((f, slide_label))
    else:
        drag_plan = [(f, f"Slide {i + 2}") for i, f in enumerate(fields)]

    first_slide_label = drag_plan[0][1] if drag_plan else "Slide 2"

    # Navigate to the first question slide
    _click(session, first_slide_label)

    # Open Add Elements
    _click(session, "Add Elements")
    _wait(session, "Add Object Fields")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-e-drawer-opened"))

    # Switch to Add Object Fields tab (NOT Quick Add)
    _click(session, "Add Object Fields")
    _wait(session, folder_upper, timeout=20)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-e-object-fields-tab"))

    # Expand the survey folder group (name matches; (n) count is volatile)
    _click(session, folder_upper)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-e-folder-expanded"))

    # Drag each field onto its owner slide
    for i, (f, target_slide) in enumerate(drag_plan):
        label_prefix = f["label"][:28]
        _log(f"  Dragging field {i + 1}/{len(drag_plan)}: {label_prefix!r} → {target_slide}")

        # Use Search by Name for fast, reliable location (PRD §5.B.2 Phase E)
        _fill(session, "Search by Name", f["label"][:20])
        _run_cmd(session, "drag", label_prefix, target_slide, timeout=20)
        _wait(session, label_prefix[:20], timeout=20)
        shot_n[0] += 1
        _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                        f"p2-e-field{i + 1:02d}-placed"))

        # Clear search for next field
        _fill(session, "Search by Name", "")


def _p2_rename_question_slides(
    session: str,
    fields: List[dict],
    gov: RateGovernor,
    evidence_root: str,
    shot_n: List[int],
    slides: Optional[List[dict]] = None,
) -> None:
    """Phase F: rename each question slide via gear → Slide Name (short names).

    TASK-DRIVEN (Area-5): one rename per PLANNED question slide (a slide may host
    several fields, so renames are per-slide, not per-field). Default layout
    (``slides=None``) keeps the legacy one-field-per-slide naming byte-identical.
    Followed by an intermediate save (transcript steps 86–87).
    """
    _log("P2-F: rename question slides")
    q_slides = [s for s in (slides or []) if s.get("type") == "question"]
    if q_slides:
        renames = [(s["index"], s["name"]) for s in q_slides]
    else:
        renames = [(i + 2, f["slide_name"]) for i, f in enumerate(fields)]
    for slide_n, short_name in renames:
        _log(f"  Slide {slide_n} → {short_name!r}")
        _click(session, f"Slide {slide_n}")
        _run_cmd(session, "click", "gear", timeout=10)
        _fill(session, "Slide Name", short_name)
        shot_n[0] += 1
        _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                        f"p2-f-slide{slide_n:02d}-renamed"))

    # Intermediate save (transcript steps 86–87)
    gov.before("save")
    _click(session, "Save")
    _wait(session, "Yes")
    _click(session, "Yes")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-f-interim-save"))


def _p2_conditional_logic(
    session: str,
    rules: List[dict],
    gov: RateGovernor,
    evidence_root: str,
    shot_n: List[int],
) -> None:
    """Phase G: wire Jump-To conditional logic — TASK-DRIVEN, per OWNER slide.

    ``rules`` are the NORMALIZED task rules; each carries ``owner_slide_label``
    (the slide that hosts ``if_field``) and a canonical ``then_slide`` target. The
    per-field conditional-logic control is DEPRECATED; the canonical path is the
    amber ``Open Conditional Logic`` link on the field panel. Rules are GROUPED by
    owner slide so a multi-branch survey wires each rule on the RIGHT slide
    (never a hardcoded "Slide 2"); one save per rule; rules run top-down.
    """
    _log(f"P2-G: conditional logic ({len(rules)} rule(s))")
    if not rules:
        _log("  no conditional rules — Phase G skipped")
        return

    # Group rules by owner slide (the slide that hosts each rule's if_field).
    groups = _group_rules_by_owner_slide(rules)

    global_ri = 0
    for gi, (owner_label, grp) in enumerate(groups, start=1):
        _log(f"  owner slide {owner_label!r}: {len(grp)} rule(s)")

        # Navigate to the OWNER slide (the one that hosts if_field)
        _click(session, owner_label)
        shot_n[0] += 1
        _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                        f"p2-g-slide{gi:02d}"))

        # Open Conditions modal via the amber link on the field panel
        _click(session, "Open Conditional Logic")
        _wait(session, "Jump To")
        shot_n[0] += 1
        _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                        f"p2-g-conditions-modal{gi:02d}"))

        for rule in grp:
            global_ri += 1
            _log(f"  Rule {global_ri}/{len(rules)}: "
                 f"IF {str(rule.get('if_field', ''))[:30]!r} "
                 f"= {rule.get('if_value')!r} THEN {rule.get('then_slide')!r}")

            # Add Jump To card
            _click(session, "Jump To")
            _wait(session, "Select field")

            # Set condition type = Field
            _click(session, "Field")

            # Pick the IF field (may be truncated — use partial match)
            _click(session, str(rule.get("if_field", ""))[:28])

            # Operator defaults to "Is Equal To" — no change needed

            # Set value
            _click(session, rule.get("if_value", ""))

            # Set THEN target slide (Pn- prefix is stable)
            _click(session, rule.get("then_slide", ""))

            # Save this condition (one save per rule, RateGovernor spaced)
            gov.before("save")
            _click(session, "Save")
            # Modal stays open after save; wait for Jump To card to re-appear
            _wait(session, "Jump To", timeout=15)
            shot_n[0] += 1
            _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                            f"p2-g-rule{global_ri:02d}-saved"))


def _p2_required_toggles(
    session: str,
    fields: List[dict],
    evidence_root: str,
    shot_n: List[int],
    slides: Optional[List[dict]] = None,
) -> None:
    """Phase H: tick Required checkbox on each required question field.

    TASK-DRIVEN (Area-5): iterates the PLANNED question slides and toggles every
    required field. When a slide hosts >1 field, the field's own panel is focused
    (click its label) before ticking Required, so the right field is marked.
    Default layout (``slides=None``) is byte-identical to the legacy per-field
    sweep. Confirmation: the field label gains a trailing ``*``.
    """
    _log("P2-H: required toggles")
    q_slides = [s for s in (slides or []) if s.get("type") == "question"]
    n = 0
    if q_slides:
        for s in q_slides:
            slide_fields = s.get("fields", [])
            multi = len(slide_fields) > 1
            slide_label = f"P{s['index']} - {s['name']}"
            for ff in slide_fields:
                if not ff.get("required"):
                    continue
                n += 1
                _log(f"  {slide_label}: marking {ff.get('label', '')[:30]!r} required")
                # Navigate via the Pn- slide label
                _click(session, slide_label)
                # On a multi-field slide, focus the specific field's panel first
                if multi:
                    _click(session, ff.get("label", "")[:28])
                # Click Required checkbox (right panel, left of Hidden)
                _click(session, "Required")
                # Verify trailing * on the question label
                _wait(session, "*", timeout=10)
                shot_n[0] += 1
                _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                                f"p2-h-required-{n:02d}"))
    else:
        for i, f in enumerate(fields):
            if not f.get("required"):
                continue
            slide_n = i + 2
            short = f["slide_name"]
            _log(f"  P{slide_n} - {short}: marking required")
            # Navigate via the Pn- slide label
            _click(session, f"P{slide_n} - {short}")
            # Click Required checkbox (right panel, left of Hidden)
            _click(session, "Required")
            # Verify trailing * on the question label
            _wait(session, "*", timeout=10)
            shot_n[0] += 1
            _screenshot(session, _shot_path(evidence_root, shot_n[0],
                                            f"p2-h-required-{i + 1:02d}"))


def _p2_capture_slide(
    session: str,
    business_name: str,
    campaign: str,
    num_fields: int,
    evidence_root: str,
    shot_n: List[int],
    capture_slide_n: Optional[int] = None,
) -> None:
    """Phase J: Quick-Add contact-capture slide + T&C consent checkbox.

    Adds: First Name, Last Name, Email (required), Phone (required),
    T & C (plain marketing-consent checkbox — NOT A2P/10DLC).
    Edits the [BUSINESS NAME] placeholder in the T&C consent copy.

    TASK-DRIVEN (Area-5): ``capture_slide_n`` is the PLANNED capture-slide index
    (1 welcome + question slides + 1 capture). Falls back to ``num_fields + 2``
    (the legacy one-field-per-slide assumption) only when not supplied.
    """
    if capture_slide_n is None:
        capture_slide_n = num_fields + 2  # 1 welcome + n fields + capture
    _log(f"P2-J: Quick Add capture slide (Slide {capture_slide_n}) + T&C")

    # Navigate to the capture slide
    _click(session, f"Slide {capture_slide_n}")

    # Open Add Elements
    _click(session, "Add Elements")
    _wait(session, "Quick Add")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-j-quick-add-drawer"))

    # Ensure Quick Add tab is active
    _click(session, "Quick Add")
    _wait(session, "First Name")

    # Add native contact-capture fields (in order)
    for tile in ("First Name", "Last Name", "Email", "Phone"):
        _click(session, tile)
        _log(f"  Added {tile}")

    # Add T & C (Customized section; exact label has spaces around &)
    _click(session, "T & C")
    _wait(session, "[BUSINESS NAME]")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-j-tc-added"))

    # Edit the [BUSINESS NAME] placeholder inside the T&C consent copy
    # (per PRD §5.B.2 steps 129, 133–134 — transcript is canonical)
    _click(session, "[BUSINESS NAME]")
    _type(session, business_name)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-j-tc-business-name"))

    # Mark Email and Phone required
    for req_tile in ("Email", "Phone"):
        _click(session, req_tile)
        _click(session, "Required")

    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-j-capture-complete"))


def _p2_save_and_get_url(
    session: str,
    gov: RateGovernor,
    evidence_root: str,
    shot_n: List[int],
) -> str:
    """Phase K: final save + Integrate + capture the survey URL."""
    _log("P2-K: save + Integrate + capture survey URL")

    # Final save (transcript step 135)
    gov.before("save")
    _click(session, "Save")
    _wait(session, "Yes")
    _click(session, "Yes")
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-k-saved"))

    # Click Integrate (share panel shows the survey link + embed snippet)
    gov.before("publish")
    _click(session, "Integrate")
    _wait(session, "http", timeout=20)
    shot_n[0] += 1
    _screenshot(session, _shot_path(evidence_root, shot_n[0], "p2-k-integrate-panel"))

    # Capture the survey URL via JS eval (fallback: read from screenshot)
    survey_url = _eval(
        session,
        (
            "Array.from(document.querySelectorAll('a[href]'))"
            ".map(a=>a.href)"
            ".find(h=>h.includes('survey'))||''"
        ),
        timeout=15,
    )
    if not survey_url:
        _log("survey URL not captured via eval — read from integrate-panel screenshot")

    _log(f"Survey URL: {survey_url!r}")
    return survey_url


# ---------------------------------------------------------------------------
# Dry-run click list emitter
# ---------------------------------------------------------------------------

def _emit_click_list(
    fields: List[dict],
    folder_name: str,
    survey_name: str,
    business_name: str,
    campaign: str,
    welcome_copy: str,
    location_id: str,
    field_creation: str = DEFAULT_FIELD_CREATION,
    slides: Optional[List[dict]] = None,
    rules: Optional[List[dict]] = None,
) -> dict:
    """Build the full ordered click sequence for operator review (dry-run output).

    F1: in ``api``/``map_only`` mode, Part 1 is NOT an in-browser click sequence —
    the custom fields are pre-created via Skill 44 (see survey-dependency-plan.json)
    and the browser only DRAGS them in Phase E. Legacy in-browser field-create
    clicks are emitted ONLY in the explicit ``browser`` fallback mode.

    TASK-DRIVEN (Area-5): the Part-2 layout comes from the PLANNED ``slides`` and
    the NORMALIZED branching ``rules`` — a slide may carry >1 field and branches
    target any owner slide. When ``slides``/``rules`` are omitted this reproduces
    the linear default layout and the documented demo/fallback rules (resolved via
    ``_resolve_conditional_rules``); the CONDITIONAL_LOGIC_RULES constant is NEVER
    referenced directly here.
    """
    # Derive the slide model + normalized branching if the caller did not supply
    # them (keeps every legacy call site — and the linear default — working).
    if slides is None:
        slides = _plan_slides({}, fields)
    if rules is None:
        rules = _normalize_conditional_logic(
            _resolve_conditional_rules({}), fields, slides
        )[0]
    q_slides = [s for s in slides if s.get("type") == "question"]
    capture_slide = next((s for s in slides if s.get("type") == "capture"), None)
    capture_index = capture_slide["index"] if capture_slide else len(fields) + 2
    num_extra = len(q_slides) + 1  # question slides + 1 capture
    first_q_label = f"Slide {q_slides[0]['index']}" if q_slides else "Slide 2"
    by_label = {f.get("label", ""): f for f in fields}

    steps: List[dict] = []
    n = 0

    def add(phase: str, action: str, target: str, note: str = "") -> None:
        nonlocal n
        n += 1
        steps.append({"n": n, "phase": phase, "action": action,
                       "target": target, "note": note})

    app_url = f"{GHL_APP_ORIGIN_DEFAULT}/v2/location/{location_id}/dashboard"

    # ── Part 1 ───────────────────────────────────────────────────────────────
    if field_creation != "browser":
        add("P1", "skip",
            "custom fields pre-created via Skill 44 (caf, LOCATION PIT)",
            "F1 grocery-shopping rule: GET existing → create missing zhc_ keys "
            "out-of-band → read back. See routing/survey-dependency-plan.json. "
            "Browser creates NO fields; Phase E drags the read-back keys.")
    else:
        add("P1", "navigate", app_url, "Open app shell (LEGACY browser create — no-PIT fallback)")
        add("P1", "click", "Settings", "Far-left nav, pinned bottom")
        add("P1", "click", "Custom Fields", "Settings submenu")
        add("P1", "confirm", "Object = Contact", "Combobox default")
        add("P1", "click", "Create folder", "Opens Create folder dialog")
        add("P1", "fill+click", f"Folder name = {folder_name!r} → Create",
            "Dialog Create button")
        add("P1", "click", "Folders", "Tab switch")
        add("P1", "click", folder_name,
            "Blue link; URL must contain parentId=<FOLDER_ID>&object=contact")
        add("P1", "click", "Add custom field", "First field — centered CTA")

        for fi, f in enumerate(fields):
            tl = _FIELD_TYPE_LABELS.get(f["type"], f["type"])
            add("P1", "select", f"Field type → {tl}", f"Field {fi + 1}: {f['label'][:40]!r}")
            add("P1", "fill", f"Enter name = {f['label'].strip()!r}", "Char counter must be >0")
            for opt in f.get("options", []):
                add("P1", "click+type", f"Add option → {opt.strip()!r}",
                    "Trim leading/trailing spaces on every option")
            if f["type"] == "file_upload":
                for ft in f.get("file_types", ["PDF", "DOCX/DOC", "JPG/JPEG", "PNG"]):
                    add("P1", "check", ft, "File type checkbox")
            add("P1", "click", "Create custom field",
                "Enabled only when name + ≥1 option/format valid — wait for solid blue")
            if fi < len(fields) - 1:
                add("P1", "click", "Create field", "Blue + upper-right; reopens modal")

    # ── Part 2 ───────────────────────────────────────────────────────────────
    add("P2-A", "navigate", app_url, "Dashboard (fresh navigation)")
    add("P2-A", "click", "Sites", "Left rail → funnels-websites/funnels")
    add("P2-A", "click", "Surveys", "Orange sub-nav tab")
    add("P2-A", "click", "Add survey",
        "Creates survey; waits for Slide 1 in survey-builder-v2 iframe")
    add("P2-B", "dblclick", "Survey 0", "Enter inline title edit")
    add("P2-B", "fill", survey_name, "New survey name")
    add("P2-B", "click", "Slide 1", "Commit title (click canvas)")
    for i in range(num_extra):
        add("P2-C", "click", "Add Slide",
            f"→ Slide {i + 2}; total slides = {1 + num_extra}")
    add("P2-D", "click", "Slide 1", "Welcome slide")
    add("P2-D", "click", "Add Elements", "Opens Survey Element drawer")
    add("P2-D", "click", "Text",
        "Customized section — exact. NOT Multi Line / Text Box List (those are answer inputs)")
    add("P2-D", "click+type", f"Survey Element → {welcome_copy[:50]!r}…",
        "Persona-voice welcome copy")
    add("P2-D", "click", "inter", "Font (optional styling)")
    add("P2-D", "click", "Paragraph", "Style (optional)")
    add("P2-D", "gear+fill", "Slide Name = Welcome Slide", "Rename via slide gear")
    add("P2-E", "click", first_q_label, "First question slide for Add Object Fields")
    add("P2-E", "click", "Add Elements", "Opens drawer")
    add("P2-E", "click", "Add Object Fields",
        "Tab — NOT Quick Add. Object dropdown must read Contact")
    add("P2-E", "click", f"{folder_name.upper()} (n)",
        "Expand folder group; (n) = field count, volatile — match on name only")
    # Drag each field onto its OWNER slide (per-branch capable, not one-per-slide)
    for s in q_slides:
        for lbl in s.get("field_labels", []):
            f = by_label.get(lbl)
            if f is None:
                continue
            add("P2-E", "fill+drag",
                f"Search by Name = {f['label'][:20]!r} → drag to Slide {s['index']}",
                "Object field binds answer to {{contact.<key>}}")
    for s in q_slides:
        add("P2-F", "gear+fill",
            f"Slide {s['index']} → Slide Name = {s['name']!r}", "Short name")
    add("P2-F", "click+confirm", "Save → Yes", "Interim save (transcript steps 86–87)")
    # Conditional logic — TASK-DRIVEN, grouped by owner slide (never a hardcoded
    # "Slide 2"). Empty rules → no branching wired.
    if rules:
        global_ri = 0
        for owner_label, grp in _group_rules_by_owner_slide(rules):
            add("P2-G", "click", owner_label,
                "Navigate to the OWNER slide (the one that hosts if_field)")
            add("P2-G", "click", "Open Conditional Logic",
                "Amber link on the field panel — per-field dropdown is deprecated")
            for rule in grp:
                global_ri += 1
                add("P2-G", "click", "Jump To", f"Rule {global_ri}")
                add("P2-G", "select",
                    f"Field → {str(rule.get('if_field', ''))[:30]!r}", "IF field")
                add("P2-G", "select", rule.get("if_value", ""),
                    "IF value (Is Equal To default)")
                add("P2-G", "select", rule.get("then_slide", ""),
                    "THEN slide (Pn- prefix stable)")
                add("P2-G", "click", "Save",
                    "One save per rule; rules run top-down; modal stays open")
    else:
        add("P2-G", "skip", "no conditional logic",
            "task supplied no branching rules (conditional_logic: [])")
    for s in q_slides:
        for ff in s.get("fields", []):
            if ff.get("required"):
                add("P2-H", "check",
                    f"P{s['index']} - {s['name']} → Required",
                    "Right panel, left of Hidden; trailing * confirms")
    add("P2-J", "click", f"Slide {capture_index}", "Contact capture slide")
    add("P2-J", "click", "Add Elements → Quick Add", "Switch to Quick Add tab")
    for tile in ("First Name", "Last Name", "Email", "Phone"):
        add("P2-J", "click", tile, "Native contact field")
    add("P2-J", "click", "T & C",
        "Customized section — spaces around &; plain consent checkbox NOT A2P/10DLC")
    add("P2-J", "click+type", f"[BUSINESS NAME] → {business_name!r}",
        "Edit consent placeholder (PRD §5.B.2 steps 129, 133–134)")
    for req_f in ("Email", "Phone"):
        add("P2-J", "check", f"{req_f} → Required", "Required on capture slide")
    add("P2-K", "click+confirm", "Save → Yes", "Final save")
    add("P2-K", "click", "Integrate",
        "Share panel with survey link + embed snippet")
    add("P2-K", "read", "survey URL",
        "Copy visible link; also record builder URL leadconnectorhq.com/survey-builder-v2/<id>")

    return {
        "schema_version": "1.0",
        "generated_at": _ts(),
        "field_creation": field_creation,
        "total_steps": n,
        "dry_run": True,
        "note": (
            "Operator review: verify every step before flipping --no-dry-run. "
            "Transcript is canonical (PRD §5.B.1–2). "
            "Google-Doc detours in the recording are recorder noise — ignore them. "
            f"field_creation={field_creation}: custom fields "
            + ("pre-created via Skill 44 (map-only bind in Phase E)."
               if field_creation != "browser"
               else "created in-browser (LEGACY no-PIT fallback).")
        ),
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_survey(task: dict, evidence_root: str, *, dry_run: bool = True) -> dict:
    """Build a GoHighLevel native survey via browser-control.

    This is the v2_dispatcher INJECTED BUILDER: called as
    ``builder(task, evidence_root)`` from ``dispatch_one``.

    Args:
        task: Board task / brief dict. Relevant keys:
            location_id / GHL_LOCATION_ID  — sub-account location ID (required).
            survey_name                     — survey title.
            folder_name                     — custom-field folder name
                                              (default 'Sample Survey').
            survey_fields                   — list of field dicts; overrides
                                              REFERENCE_FIELDS when present.
            business_name                   — replaces [BUSINESS NAME] in T&C.
            campaign                        — replaces [campaign] in T&C copy.
            welcome_copy                    — welcome slide text body.
            copy_persona                    — persona dict from funnel_matcher.
            board_task_id                   — CC Kanban UUID for board hooks.
            dry_run (bool)                  — overrides the kwarg when present.
        evidence_root: Directory for routing/, shots/ ledgers.
        dry_run: If True (default), write plan + field-map + click list without
            any browser execution. Flip to False only after a full end-to-end
            live-verified run on a test sub-account.

    Returns dict with at minimum:
        pages           — list of slide specs (also satisfies dispatcher contract).
        location_gate_ok — bool.
        duration_s      — float.
        survey_url      — str (empty on dry-run / failure).
        field_map       — dict.
        preflight       — dict.
        plan_path       — str.
        field_map_path  — str.
        shots           — list[str].
    """
    started = time.monotonic()

    # task['dry_run'] overrides the kwarg so the dispatcher can control it
    dry_run = bool(task.get("dry_run", dry_run))

    _log(f"build_survey START dry_run={dry_run} evidence_root={evidence_root!r}")
    _ensure_dirs(
        os.path.join(evidence_root, "routing"),
        os.path.join(evidence_root, "shots"),
    )

    # Resolve key task fields
    location_id: str = (
        task.get("location_id")
        or task.get("GHL_LOCATION_ID")
        or os.environ.get("GHL_LOCATION_ID")
        or os.environ.get("GOHIGHLEVEL_LOCATION_ID", "")
    ).strip()
    survey_name: str = task.get("survey_name", task.get("title", "New Survey"))
    folder_name: str = task.get("folder_name", "Sample Survey")
    business_name: str = task.get("business_name", "[BUSINESS NAME]")
    campaign: str = task.get("campaign", "our campaign")
    board_task_id: Optional[str] = task.get("board_task_id")
    welcome_copy: str = (
        task.get("welcome_copy")
        or task.get("copy_persona", {}).get("welcome", "")
        or (
            "Welcome! We are excited to learn more about you. "
            "Please take a moment to fill out this short survey."
        )
    )
    fields = _resolve_fields(task)
    field_creation = _resolve_field_creation_mode(task)

    # Task-driven slide model + normalized branching (Area-5). Preflight
    # (P4:topology_valid) already proved every reference resolves; these drive
    # the LIVE phases (E/F/G/H/J) and the dry-run click list — never the demo
    # constant once the task supplies its own rules/layout.
    slides_model = _plan_slides(task, fields)
    norm_rules = _normalize_conditional_logic(
        _resolve_conditional_rules(task), fields, slides_model
    )[0]
    q_slides = [s for s in slides_model if s.get("type") == "question"]
    capture_slide = next(
        (s for s in slides_model if s.get("type") == "capture"), None
    )
    capture_slide_n = capture_slide["index"] if capture_slide else len(fields) + 2
    num_extra = len(q_slides) + 1  # question slides + 1 capture

    # Total step count for progress messages
    total_steps = _PART1_BASE_STEPS + len(fields) + _PART2_PHASES + 2  # preflight + plan

    # ── Board: intake start ───────────────────────────────────────────────────
    _board_move(board_task_id, "in_progress")
    _board_activity(
        board_task_id, "status_changed",
        f"Survey build started: {survey_name!r} (dry_run={dry_run}, "
        f"location={location_id!r}, folder={folder_name!r})",
        metadata={"location_id": location_id, "folder": folder_name,
                  "survey_name": survey_name, "dry_run": dry_run},
    )

    # ── Step 1: Preflight ─────────────────────────────────────────────────────
    _board_activity(board_task_id, "updated",
                    f"Step 1/{total_steps}: Running preflight checks")
    preflight = _run_preflight(task, evidence_root)
    if not preflight["pass"]:
        stop = preflight.get("stop_reason", "preflight failed")
        _log(f"PREFLIGHT HARD STOP: {stop}")
        _board_move(board_task_id, "blocked", note=f"Preflight failed: {stop}")
        _board_activity(board_task_id, "completed",
                        f"Build BLOCKED at preflight: {stop}")
        return {
            "pages": [], "location_gate_ok": False,
            "duration_s": time.monotonic() - started,
            "survey_url": "", "field_map": {}, "preflight": preflight,
            "plan_path": "", "field_map_path": "", "shots": [],
            "error": stop,
        }

    # ── Step 2: Write survey plan (THINK output) ──────────────────────────────
    _board_activity(board_task_id, "updated",
                    f"Step 2/{total_steps}: Writing survey plan (THINK phase)")
    plan = _build_survey_plan(task, fields)
    plan_path = os.path.join(evidence_root, "routing", "survey-plan.json")
    _write_json(plan_path, plan)
    _log(f"Survey plan: {plan_path}")

    # ── Step 3: Write field map ───────────────────────────────────────────────
    _board_activity(board_task_id, "updated",
                    f"Step 3/{total_steps}: Writing survey field map")
    field_map = _build_field_map(fields, folder_name)
    field_map_path = os.path.join(evidence_root, "routing", "survey-field-map.json")
    _write_json(field_map_path, field_map)
    _log(f"Field map: {field_map_path}")

    # ── Step 3.5: Skill-44 dependency plan (F1/F2 — grocery-shopping rule) ─────
    # api/map_only reuse API-pre-created custom fields; browser mode keeps the
    # legacy in-browser create as an explicit no-PIT fallback.
    dep_plan = plan_survey_dependencies(
        fields, task, existing_field_keys=task.get("existing_field_keys")
    )
    dep_plan["field_creation_mode"] = field_creation
    dep_plan_path = os.path.join(evidence_root, "routing", "survey-dependency-plan.json")
    _write_json(dep_plan_path, dep_plan)
    _log(f"Dependency plan ({field_creation}): {dep_plan_path} "
         f"[blocked={dep_plan['blocked']}]")

    # ── Dry-run: emit click list and return ───────────────────────────────────
    if dry_run:
        click_list = _emit_click_list(
            fields, folder_name, survey_name,
            business_name, campaign, welcome_copy, location_id,
            field_creation=field_creation,
            slides=slides_model, rules=norm_rules,
        )
        click_list_path = os.path.join(evidence_root, "routing", "survey-click-list.json")
        _write_json(click_list_path, click_list)
        _log(f"[dry-run] Click list ({click_list['total_steps']} steps): {click_list_path}")
        _board_activity(
            board_task_id, "updated",
            f"[dry-run] Plan + field-map + dependency-plan + click list written "
            f"({click_list['total_steps']} steps, field_creation={field_creation}). "
            "No browser execution. Flip --no-dry-run after operator review.",
        )
        duration = time.monotonic() - started
        return {
            "pages": plan["slides"],
            "location_gate_ok": bool(location_id),
            "duration_s": duration,
            "survey_url": "",
            "field_map": field_map,
            "dependency_plan": dep_plan,
            "field_creation": field_creation,
            "preflight": preflight,
            "plan_path": plan_path,
            "field_map_path": field_map_path,
            "dependency_plan_path": dep_plan_path,
            "click_list_path": click_list_path,
            "shots": [],
            "dry_run": True,
        }

    # ── F1/F2 LIVE gate: reuse API-pre-created custom fields (map-only) ────────
    # In api/map_only mode the browser NEVER creates a field. Before touching the
    # builder we GET the location's existing keys (Skill-44 caf, LOCATION PIT) and
    # confirm EVERY field to be bound already exists. An unconfirmed field is a
    # STOP-and-report (never a silent in-browser create) — Part 2 consumes only
    # the read-back key list.
    if field_creation in ("api", "map_only"):
        existing_keys = task.get("existing_field_keys")
        if existing_keys is None:
            existing_keys = _caf_list_field_keys(location_id)
        dep_plan = plan_survey_dependencies(
            fields, task, existing_field_keys=existing_keys
        )
        dep_plan["field_creation_mode"] = field_creation
        _write_json(dep_plan_path, dep_plan)

        # Any field not confirmed present on the location blocks the live bind.
        # api: 'create' fields must have been pre-created by Skill 44 already —
        #      if the live GET still shows them missing, STOP (run caf first).
        # map_only: 'create' is forbidden outright.
        unconfirmed = [
            s for s in dep_plan["custom_fields"]
            if s["action"] in ("REFUSED", "verify_required", "create")
        ]
        if existing_keys is None:
            # Could not GET at all — cannot prove any field exists. Refuse to guess.
            stop = ("field_creation=%s requires a Skill-44 GET of existing custom "
                    "fields, but `caf locations custom-fields` was unavailable and "
                    "no task['existing_field_keys'] was supplied. Cannot confirm "
                    "fields exist — refusing to bind. Provide existing_field_keys "
                    "or fix the caf rail, or use field_creation='browser'." % field_creation)
            _log(f"F1 LIVE STOP: {stop}")
            _board_move(board_task_id, "blocked", note=f"TOKEN-CONTEXT: {stop}")
            _board_activity(board_task_id, "completed", f"Build BLOCKED (field reuse): {stop}")
            return {
                "pages": [], "location_gate_ok": bool(location_id),
                "duration_s": time.monotonic() - started,
                "survey_url": "", "field_map": field_map,
                "dependency_plan": dep_plan, "field_creation": field_creation,
                "preflight": preflight, "plan_path": plan_path,
                "field_map_path": field_map_path,
                "dependency_plan_path": dep_plan_path, "shots": [],
                "error": stop,
            }
        if unconfirmed:
            missing = [s["field_key"] or s["label"] for s in unconfirmed]
            caf_hint = "; ".join(
                f"caf locations create-custom-field --location-id {location_id} "
                f"--key {s['field_key']} --name {s['label']!r}"
                for s in unconfirmed if s["action"] == "create"
            )
            stop = (f"{len(unconfirmed)} custom field(s) not present on location "
                    f"{location_id!r}: {missing}. Pre-create them via Skill 44 first "
                    f"(grocery-shopping rule). {caf_hint}")
            _log(f"F1 LIVE STOP: {stop}")
            _board_move(board_task_id, "blocked", note=f"AUTH-STOP: field reuse — {stop}")
            _board_activity(board_task_id, "completed", f"Build BLOCKED (field reuse): {stop}")
            return {
                "pages": [], "location_gate_ok": bool(location_id),
                "duration_s": time.monotonic() - started,
                "survey_url": "", "field_map": field_map,
                "dependency_plan": dep_plan, "field_creation": field_creation,
                "preflight": preflight, "plan_path": plan_path,
                "field_map_path": field_map_path,
                "dependency_plan_path": dep_plan_path, "shots": [],
                "error": stop,
            }
        _log(f"F1 LIVE: all {len(dep_plan['custom_fields'])} fields confirmed present "
             "on location — proceeding map-only (no in-browser field creation).")

    # ── Live browser execution ────────────────────────────────────────────────
    survey_url = ""
    shot_n = [0]  # mutable single-element list so helpers can increment it
    gov = RateGovernor()
    keepalive = SessionKeepalive()

    try:
        with browser_manager.browser_session(location_id) as bm_ctx:
            # Canonical session name: ghl-skill6-<location_id>
            session: str = (
                bm_ctx
                if isinstance(bm_ctx, str)
                else f"ghl-skill6-{location_id}"
            )
            _log(f"Browser session: {session!r}")

            # ── Part 1: custom-field folder + fields ──────────────────────────
            # F1 FIX: in api/map_only mode Part 1 is REPLACED by the Skill-44
            # dependency plan (fields already GET-confirmed above); the browser
            # creates NOTHING. Legacy in-browser create runs ONLY in the explicit
            # no-PIT 'browser' fallback mode.
            step_n = 4
            if field_creation != "browser":
                _board_activity(
                    board_task_id, "updated",
                    f"Step {step_n}/{total_steps}: Part 1 SKIPPED "
                    f"(field_creation={field_creation}) — "
                    f"{len(fields)} custom field(s) reused from Skill-44 "
                    "pre-creation; no in-browser field creation.",
                )
            else:
                _board_activity(board_task_id, "updated",
                                f"Step {step_n}/{total_steps}: Part 1 (LEGACY browser create) — "
                                f"folder {folder_name!r}")
                _p1_create_folder(
                    session, location_id, folder_name, gov, evidence_root, shot_n
                )
                for fi, field in enumerate(fields):
                    step_n += 1
                    _board_activity(
                        board_task_id, "updated",
                        f"Step {step_n}/{total_steps}: Part 1 — field {fi + 1}/{len(fields)}: "
                        f"{field['label'][:40]!r}",
                    )
                    _p1_create_field(
                        session, field, is_first=(fi == 0),
                        gov=gov, evidence_root=evidence_root,
                        shot_n=shot_n, field_index=fi + 1,
                    )
                    if keepalive.due():
                        _eval(session, "true", timeout=5)  # harmless keepalive ping

            # ── Part 2: Phase A — create survey ──────────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase A — create survey")
            _p2_navigate_create(session, location_id, evidence_root, shot_n)

            # ── Part 2: Phase B — rename survey ──────────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase B — rename survey")
            _p2_rename_survey(session, survey_name, evidence_root, shot_n)

            # ── Part 2: Phase C — add slides ──────────────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase C — add {num_extra} slides "
                f"(total={1 + num_extra})",
            )
            _p2_add_slides(session, num_extra, evidence_root, shot_n)

            # ── Part 2: Phase D — welcome slide ───────────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase D — welcome slide (Text element)")
            _p2_welcome_slide(session, welcome_copy, evidence_root, shot_n)

            # ── Part 2: Phase E — pull custom fields ──────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase E — Add Object Fields "
                f"from folder {folder_name!r}",
            )
            _p2_pull_object_fields(
                session, folder_name, fields, evidence_root, shot_n,
                dep_custom_fields=dep_plan.get("custom_fields", []),
                slides=slides_model,
            )

            # ── Part 2: Phase F — rename question slides ──────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase F — rename question slides")
            _p2_rename_question_slides(
                session, fields, gov, evidence_root, shot_n, slides=slides_model
            )

            # ── Part 2: Phase G — conditional logic ───────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase G — conditional logic "
                            f"({len(norm_rules)} rule(s))")
            _p2_conditional_logic(
                session, norm_rules, gov, evidence_root, shot_n
            )

            # ── Part 2: Phase H — required toggles ───────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            required_count = sum(1 for f in fields if f.get("required"))
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase H — required toggles "
                f"({required_count} fields)",
            )
            _p2_required_toggles(
                session, fields, evidence_root, shot_n, slides=slides_model
            )

            # ── Part 2: Phase J — capture slide + T&C ────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(
                board_task_id, "updated",
                f"Step {step_n}/{total_steps}: Part 2 Phase J — Quick-Add capture "
                "slide + T&C (plain consent checkbox, NOT A2P)",
            )
            _p2_capture_slide(
                session, business_name, campaign, len(fields),
                evidence_root, shot_n, capture_slide_n=capture_slide_n,
            )

            # ── Part 2: Phase K — save + get URL ─────────────────────────────
            _pre_phase_check(session, keepalive)
            step_n += 1
            _board_activity(board_task_id, "updated",
                            f"Step {step_n}/{total_steps}: Part 2 Phase K — save + capture URL")
            survey_url = _p2_save_and_get_url(session, gov, evidence_root, shot_n)

    except Exception as exc:  # noqa: BLE001
        _log(f"build_survey EXCEPTION: {type(exc).__name__}: {exc}")
        _board_move(board_task_id, "backlog",
                    note=f"Build exception: {type(exc).__name__}: {exc}")
        _board_activity(board_task_id, "completed",
                        f"Build FAILED: {type(exc).__name__}: {exc}")
        duration = time.monotonic() - started
        return {
            "pages": [], "location_gate_ok": False,
            "duration_s": duration,
            "survey_url": "", "field_map": field_map,
            "preflight": preflight,
            "plan_path": plan_path, "field_map_path": field_map_path,
            "shots": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    # ── Collect screenshots ───────────────────────────────────────────────────
    shots_dir = os.path.join(evidence_root, "shots")
    shots: List[str] = (
        sorted(
            os.path.join(shots_dir, f)
            for f in os.listdir(shots_dir)
            if f.endswith(".png")
        )
        if os.path.isdir(shots_dir)
        else []
    )

    duration = time.monotonic() - started

    # Enrich field map with built URLs
    field_map["survey_url"] = survey_url
    field_map["builder_url"] = (
        f"https://{GHL_SURVEY_BUILDER_HOST}/survey-builder-v2/<surveyId>"
    )
    _write_json(field_map_path, field_map)

    # ── Board: artifact ready → register deliverable + move to REVIEW ─────────
    if survey_url and board_task_id:
        _board_register_deliverable(board_task_id, survey_url)
    # NEVER move to 'done' — only QC gate (runQCOnReview ≥ 8.5) can promote
    _board_move(board_task_id, "review")
    _board_activity(
        board_task_id, "completed",
        f"Survey built: {survey_url!r} — {len(shots)} screenshots. "
        "Card is in REVIEW. QC gate (≥ 8.5) required before 'done'.",
        metadata={"survey_url": survey_url, "shots": len(shots),
                  "duration_s": round(duration, 1)},
    )

    _log(f"build_survey DONE in {duration:.1f}s survey_url={survey_url!r} shots={len(shots)}")
    return {
        "pages": plan["slides"],
        "location_gate_ok": bool(location_id),
        "duration_s": duration,
        "survey_url": survey_url,
        "field_map": field_map,
        "preflight": preflight,
        "plan_path": plan_path,
        "field_map_path": field_map_path,
        "shots": shots,
    }


# ---------------------------------------------------------------------------
# Self-test — no network, no browser
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Run unit-level assertions. Returns 0 on pass, 1 on any failure."""
    import tempfile
    errors: List[str] = []

    with tempfile.TemporaryDirectory() as tmp:

        # 1. Idempotency key is deterministic
        task = {"client_id": "abc", "survey_slug": "test", "brief": {"q": 1}}
        k1 = _idempotency_key(task)
        k2 = _idempotency_key(task)
        if k1 != k2:
            errors.append("_idempotency_key is not deterministic")

        # 2. Survey plan slide count: 1 welcome + N fields + 1 capture
        plan = _build_survey_plan(
            {"survey_name": "Test", "folder_name": "F"},
            REFERENCE_FIELDS,
        )
        expected = 1 + len(REFERENCE_FIELDS) + 1
        if plan["total_slides"] != expected:
            errors.append(
                f"plan.total_slides={plan['total_slides']} expected {expected}"
            )

        # 3. Field map: one custom entry per field, five capture entries
        fm = _build_field_map(REFERENCE_FIELDS, "Sample Survey")
        if len(fm["custom_fields"]) != len(REFERENCE_FIELDS):
            errors.append(
                f"field_map.custom_fields count={len(fm['custom_fields'])} "
                f"expected {len(REFERENCE_FIELDS)}"
            )
        if len(fm["capture_fields"]) != 5:  # FN, LN, Email, Phone, T&C
            errors.append(
                f"field_map.capture_fields count={len(fm['capture_fields'])} expected 5"
            )

        # 4. T&C field_map note confirms NOT A2P
        tc = next(
            (f for f in fm["capture_fields"] if f["field_label"] == "T & C"), None
        )
        if tc is None:
            errors.append("T & C entry missing from capture_fields")
        elif "NOT A2P" not in tc.get("note", ""):
            errors.append("T & C capture_fields note must contain 'NOT A2P'")

        # 5. No banned model tokens in ladders
        ladders_json = json.dumps(
            THINK_LADDER + EXECUTE_LADDER + QC_LADDER
        ).lower()
        for banned in (
            "minimax-m2", "minimax_m2",
            "anthropic", "claude", "opus", "sonnet", "haiku",
        ):
            if banned in ladders_json:
                errors.append(
                    f"BANNED model token found in ladders: {banned!r}"
                )

        # 6. build_survey dry-run returns expected keys without crashing
        try:
            result = build_survey(
                {
                    "survey_name": "SelfTest Survey",
                    "title": "SelfTest Survey",  # satisfies P4:spec_present check
                    "folder_name": "SelfTest Folder",
                    "location_id": "SELFTEST_LOC",
                    "brief": {"source": "selftest"},
                },
                tmp,
                dry_run=True,
            )
            required_keys = (
                "pages", "location_gate_ok", "duration_s",
                "survey_url", "field_map", "plan_path", "field_map_path",
            )
            for key in required_keys:
                if key not in result:
                    errors.append(f"build_survey dry-run missing key: {key!r}")
            if result.get("survey_url") != "":
                errors.append("dry-run survey_url should be empty string")
            if not result.get("plan_path"):
                errors.append("dry-run plan_path should be non-empty")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"build_survey dry-run raised: {type(exc).__name__}: {exc}")

        # 7. Click list has > 10 steps and no banned strings
        cl = _emit_click_list(
            REFERENCE_FIELDS,
            "Sample Survey", "Test Survey",
            "AcmeCo", "newsletter", "Welcome!", "LOC1",
        )
        if cl["total_steps"] < 10:
            errors.append(f"click list too short: {cl['total_steps']} steps")
        cl_json = json.dumps(cl).lower()
        # A2P / 10DLC must only appear in a "NOT A2P" denial context.
        # Our T&C note reads "NOT A2P/10DLC" — check that the bare token
        # never appears without a preceding negation marker within 10 chars.
        for banned in ("a2p", "10dlc"):
            if banned in cl_json:
                idx = cl_json.find(banned)
                context = cl_json[max(0, idx - 10): idx + len(banned)]
                if "not" not in context:
                    errors.append(
                        f"click list contains bare {banned!r} outside 'NOT' denial context"
                    )

        # 8. _auto_key produces clean keys
        ugly = "Which best describes your current business stage? (Select one)"
        key = _auto_key(ugly)
        if " " in key or "?" in key or "(" in key:
            errors.append(f"_auto_key produced a dirty key: {key!r}")

        # 9. F2 field-key contract — zhc default prefixes; verbatim preserved
        k_zhc, p_zhc = _resolve_field_key({"label": "Business Stage"})
        if p_zhc != "zhc" or not k_zhc.startswith("zhc_"):
            errors.append(f"zhc key policy wrong: {(k_zhc, p_zhc)!r}")
        k_vb, p_vb = _resolve_field_key(
            {"label": "Extra", "key": "podcast_survey__additional_info",
             "key_policy": "verbatim"})
        if p_vb != "verbatim" or k_vb != "podcast_survey__additional_info":
            errors.append(f"verbatim key not preserved byte-for-byte: {(k_vb, p_vb)!r}")
        # zhc must NOT double-prefix
        k_dbl, _ = _resolve_field_key({"key": "zhc_already", "key_policy": "zhc"})
        if k_dbl != "zhc_already":
            errors.append(f"zhc double-prefixed: {k_dbl!r}")

        # 10. F1 dependency plan — GET-first idempotency (reuse vs create)
        dep = plan_survey_dependencies(
            [{"label": "Fav Color", "type": "single_line"}],  # zhc → key zhc_fav_color
            {"folder_name": "F"},
            existing_field_keys=["zhc_fav_color"],
        )
        c = dep["custom_fields"][0]
        if c["action"] != "reuse":
            errors.append(f"idempotency: existing zhc_fav_color should be reuse, got {c['action']!r}")
        dep2 = plan_survey_dependencies(
            [{"label": "New One", "type": "single_line"}],
            {"folder_name": "F"}, existing_field_keys=[])
        if dep2["custom_fields"][0]["action"] != "create":
            errors.append("idempotency: unseen zhc key should be create")

        # 11. F2 verbatim-missing → plan blocked + listed (loud failure)
        depv = plan_survey_dependencies(
            [{"label": "Engine Field", "key": "engine__key", "key_policy": "verbatim",
              "type": "single_line"}],
            {"folder_name": "F"}, existing_field_keys=["some_other_key"])
        if not depv["blocked"] or not depv["missing_verbatim_keys"]:
            errors.append("verbatim-missing plan should be blocked + list missing keys")
        # verbatim WITH no GET yet → verify_required (not silently created)
        depvr = plan_survey_dependencies(
            [{"label": "Engine Field", "key": "engine__key", "key_policy": "verbatim",
              "type": "single_line"}],
            {"folder_name": "F"}, existing_field_keys=None)
        if depvr["custom_fields"][0]["action"] != "verify_required":
            errors.append("verbatim without GET should be verify_required")

        # 12. Default posture is 'api' and the dry-run dependency plan is emitted
        with tempfile.TemporaryDirectory() as tmp3:
            res_api = build_survey(
                {"survey_name": "S", "title": "S", "folder_name": "F",
                 "location_id": "LOC", "brief": {"s": 1}}, tmp3, dry_run=True)
            if res_api.get("field_creation") != "api":
                errors.append("default field_creation should be 'api'")
            if "dependency_plan" not in res_api or "dependency_plan_path" not in res_api:
                errors.append("dry-run must emit the dependency plan")
            # api-mode click list must NOT contain in-browser field-create clicks
            cl_api = _emit_click_list(REFERENCE_FIELDS, "F", "S", "Acme", "camp",
                                      "Hi", "LOC", field_creation="api")
            blob_api = json.dumps(cl_api).lower()
            if "create custom field" in blob_api or "add custom field" in blob_api:
                errors.append("api-mode click list must not create fields in-browser")
            if not any(s["phase"] == "P1" and s["action"] == "skip"
                       for s in cl_api["steps"]):
                errors.append("api-mode click list must mark Part 1 as skipped (Skill 44)")
            # browser-mode click list MUST still contain the legacy create path
            cl_br = _emit_click_list(REFERENCE_FIELDS, "F", "S", "Acme", "camp",
                                     "Hi", "LOC", field_creation="browser")
            if "create custom field" not in json.dumps(cl_br).lower():
                errors.append("browser-mode click list must retain legacy create path")

        # 13. map_only preflight hard-stops when a create would be required
        pf = _run_preflight(
            {"survey_name": "S", "title": "S", "location_id": "LOC",
             "field_creation": "map_only",
             "survey_fields": [{"label": "New Field", "type": "single_line",
                                "slide_name": "S1"}],
             "existing_field_keys": []},
            tmp)
        if pf["pass"]:
            errors.append("map_only with a would-be create should fail preflight")

        # ── Area-5: task-driven branching + per-branch slide layout ──────────
        branch_fields = [
            {"type": "radio", "label": "Q1", "options": ["A", "B"],
             "required": True, "slide_name": "S1"},
            {"type": "radio", "label": "Q2", "options": ["X", "Y"],
             "required": True, "slide_name": "S2"},
            {"type": "multiline", "label": "Q3", "options": [],
             "required": False, "slide_name": "S3"},
        ]

        # 14. Task conditional_logic OVERRIDES the demo constant and lands
        #     normalized in the plan (canonical if_field, owner slide, Pn- target).
        task_branch = {
            "survey_name": "Branch", "title": "Branch",
            "folder_name": "F", "location_id": "LOC",
            "survey_fields": branch_fields,
            "conditional_logic": [
                {"if_field": "Q1", "if_value": "A", "then_slide": "S2"},
                {"if_field": "Q1", "if_value": "B", "then_slide": "S3"},
            ],
        }
        plan_b = _build_survey_plan(task_branch, _resolve_fields(task_branch))
        if plan_b.get("conditional_logic_source") != "task":
            errors.append("task conditional_logic must set conditional_logic_source=task")
        if len(plan_b.get("conditional_logic", [])) != 2:
            errors.append(
                f"task branching count wrong: {len(plan_b.get('conditional_logic', []))}")
        else:
            r0, r1 = plan_b["conditional_logic"]
            if r0.get("if_field") != "Q1":
                errors.append(f"rule0 if_field not canonical: {r0.get('if_field')!r}")
            if r0.get("owner_slide_index") != 2:
                errors.append(
                    f"rule0 owner_slide_index should be 2, got {r0.get('owner_slide_index')!r}")
            if r0.get("then_slide") != "P3 - S2":
                errors.append(f"rule0 then_slide should be 'P3 - S2', got {r0.get('then_slide')!r}")
            if r1.get("then_slide") != "P4 - S3":
                errors.append(f"rule1 then_slide should be 'P4 - S3', got {r1.get('then_slide')!r}")
        if "attended one of our events" in json.dumps(plan_b.get("conditional_logic", [])):
            errors.append("task branching leaked the demo constant (if_field)")

        # 15. Dangling if_field → preflight P4:topology_valid HARD STOP.
        pf_badfield = _run_preflight({
            "survey_name": "B", "title": "B", "location_id": "LOC",
            "field_creation": "browser", "survey_fields": branch_fields,
            "conditional_logic": [
                {"if_field": "NoSuchField", "if_value": "A", "then_slide": "S2"},
            ],
        }, tmp)
        if pf_badfield["pass"]:
            errors.append("dangling if_field must fail preflight (topology)")
        if not any(c["check"] == "P4:topology_valid" and not c["pass"]
                   for c in pf_badfield["checks"]):
            errors.append("dangling if_field should fail P4:topology_valid specifically")

        # 16. Dangling then_slide → preflight HARD STOP (zero browser commands).
        pf_badslide = _run_preflight({
            "survey_name": "B", "title": "B", "location_id": "LOC",
            "field_creation": "browser", "survey_fields": branch_fields,
            "conditional_logic": [
                {"if_field": "Q1", "if_value": "A", "then_slide": "P99 - Nowhere"},
            ],
        }, tmp)
        if pf_badslide["pass"]:
            errors.append("dangling then_slide must fail preflight (topology)")

        # 17. Multi-field slide layout emits the RIGHT click-list: two fields
        #     drag onto one owner slide, branch targets the correct slide.
        task_multi = {
            "survey_fields": branch_fields,
            "slides": [
                {"name": "Combo", "fields": ["Q1", "Q2"]},
                {"name": "Solo", "fields": ["Q3"]},
            ],
            "conditional_logic": [
                {"if_field": "Q1", "if_value": "A", "then_slide": "Solo"},
            ],
        }
        fields_m = _resolve_fields(task_multi)
        slides_m = _plan_slides(task_multi, fields_m)
        topo_m = _validate_topology(
            task_multi, fields_m, slides_m, _resolve_conditional_rules(task_multi))
        if topo_m:
            errors.append(f"valid multi-field layout must have no topology errors: {topo_m}")
        rules_m = _normalize_conditional_logic(
            _resolve_conditional_rules(task_multi), fields_m, slides_m)[0]
        cl_m = _emit_click_list(fields_m, "F", "S", "Acme", "camp", "Hi", "LOC",
                                slides=slides_m, rules=rules_m)
        drag_steps = [s for s in cl_m["steps"]
                      if s["phase"] == "P2-E" and s["action"] == "fill+drag"]
        if len(drag_steps) != 3:
            errors.append(f"multi-field drag count should be 3, got {len(drag_steps)}")
        elif not ("drag to Slide 2" in drag_steps[0]["target"]
                  and "drag to Slide 2" in drag_steps[1]["target"]
                  and "drag to Slide 3" in drag_steps[2]["target"]):
            errors.append("multi-field drags must target Slide 2, Slide 2, Slide 3 in order")
        if not any(s["phase"] == "P2-J" and s["target"] == "Slide 4" for s in cl_m["steps"]):
            errors.append("multi-field capture slide should be Slide 4")
        if not any(s["phase"] == "P2-G" and s["target"] == "P2 - Combo" for s in cl_m["steps"]):
            errors.append("multi-field branch must navigate owner slide 'P2 - Combo'")
        if not any(s["phase"] == "P2-G" and s["target"] == "P3 - Solo" for s in cl_m["steps"]):
            errors.append("multi-field branch THEN target should be 'P3 - Solo'")

        # 18. CLI --task-json round-trip: payload drives the written plan.
        with tempfile.TemporaryDirectory() as tmp2:
            payload_path = os.path.join(tmp2, "task.json")
            with open(payload_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "survey_name": "CLI Branch", "location_id": "LOC_CLI",
                    "field_creation": "browser", "survey_fields": branch_fields,
                    "conditional_logic": [
                        {"if_field": "Q1", "if_value": "A", "then_slide": "S2"},
                    ],
                }, fh)
            ev_root = os.path.join(tmp2, "ev")
            import contextlib as _ctx
            import io as _io
            _buf = _io.StringIO()
            with _ctx.redirect_stdout(_buf):
                rc_cli = main(["--dry-run", "--task-json", payload_path,
                               "--evidence-root", ev_root])
            if rc_cli != 0:
                errors.append(f"--task-json round-trip rc should be 0, got {rc_cli}")
            plan_cli_path = os.path.join(ev_root, "routing", "survey-plan.json")
            if not os.path.exists(plan_cli_path):
                errors.append("--task-json did not write survey-plan.json")
            else:
                with open(plan_cli_path, "r", encoding="utf-8") as fh:
                    plan_cli = json.load(fh)
                if plan_cli.get("conditional_logic_source") != "task":
                    errors.append("--task-json plan must be task-sourced branching")
                if plan_cli.get("location_id") != "LOC_CLI":
                    errors.append("--task-json location_id not threaded into plan")
                if len(plan_cli.get("conditional_logic", [])) != 1:
                    errors.append("--task-json branching rule count wrong")

        # ── Area-5.1: branch-convergence primitive ───────────────────────────
        conv_fields = [
            {"type": "radio", "label": "Style", "key": "style",
             "options": ["A", "B", "C"], "required": True, "slide_name": "Pick"},
            {"type": "multiline", "label": "A1", "key": "a1",
             "required": True, "slide_name": "BranchA"},
            {"type": "multiline", "label": "B1", "key": "b1",
             "required": True, "slide_name": "BranchB"},
            {"type": "multiline", "label": "C1", "key": "c1",
             "required": True, "slide_name": "BranchC"},
            {"type": "multiline", "label": "Shared1", "key": "s1",
             "required": True, "slide_name": "Shared"},
            {"type": "multiline", "label": "Shared2", "key": "s2",
             "required": False, "slide_name": "Shared"},
        ]
        conv_slides = [
            {"name": "Pick", "fields": ["style"]},
            {"name": "BranchA", "fields": ["a1"]},
            {"name": "BranchB", "fields": ["b1"]},
            {"name": "BranchC", "fields": ["c1"]},
            {"name": "Shared", "fields": ["s1", "s2"]},
        ]
        conv_router = [
            {"if_field": "style", "if_value": "A", "then_slide": "BranchA"},
            {"if_field": "style", "if_value": "B", "then_slide": "BranchB"},
            {"if_field": "style", "if_value": "C", "then_slide": "BranchC"},
        ]
        conv_task = {
            "survey_name": "Conv", "title": "Conv", "location_id": "LOC",
            "field_creation": "browser",
            "survey_fields": conv_fields, "slides": conv_slides,
            "conditional_logic": conv_router,
            "converge_slide": "Shared",
        }

        # 19. converge_slide derives one jump per branch, each owned by that
        #     branch's slide and targeting the shared converge slide (P6 - Shared).
        fields_c = _resolve_fields(conv_task)
        slides_c = _plan_slides(conv_task, fields_c)
        plan_c = _build_survey_plan(conv_task, fields_c)
        cl_rules = plan_c.get("conditional_logic", [])
        routers = [r for r in cl_rules if r.get("kind") != "converge"]
        converges = [r for r in cl_rules if r.get("kind") == "converge"]
        if len(routers) != 3:
            errors.append(f"convergence: expected 3 router rules, got {len(routers)}")
        if len(converges) != 3:
            errors.append(
                f"convergence: expected 3 convergence rules, got {len(converges)}")
        else:
            owners = sorted(r.get("owner_slide_label") for r in converges)
            if owners != ["P3 - BranchA", "P4 - BranchB", "P5 - BranchC"]:
                errors.append(f"convergence: wrong owner slides {owners!r}")
            if any(r.get("then_slide") != "P6 - Shared" for r in converges):
                errors.append("convergence: every branch jump must target 'P6 - Shared'")
            # each convergence jump conditions on the router field, not a stray one
            if any(r.get("if_field") != "Style" for r in converges):
                errors.append("convergence: jump must condition on the router field")

        # 20. Topology is valid AND the click list wires the jumps on the branch
        #     slides (navigate P3/P4/P5, THEN 'P6 - Shared').
        topo_c = _validate_topology(
            conv_task, fields_c, slides_c, _resolve_conditional_rules(conv_task))
        if topo_c:
            errors.append(f"convergence: valid survey must have no topology errors: {topo_c}")
        norm_c = _normalize_conditional_logic(
            _resolve_conditional_rules(conv_task), fields_c, slides_c)[0]
        cl_c = _emit_click_list(fields_c, "F", "S", "Acme", "camp", "Hi", "LOC",
                                slides=slides_c, rules=norm_c)
        g_targets = {s["target"] for s in cl_c["steps"] if s["phase"] == "P2-G"}
        for need in ("P2 - Pick", "P3 - BranchA", "P4 - BranchB", "P5 - BranchC",
                     "P6 - Shared"):
            if need not in g_targets:
                errors.append(f"convergence click list missing P2-G target {need!r}")

        # 21. Path simulation: a respondent who picks ONE style visits only that
        #     branch + the shared tail + capture, never a sibling branch, and
        #     REACHES the capture slide (i.e. can submit).
        def _simulate(chosen: str) -> List[int]:
            answers = {_norm("Style"): chosen}
            by_idx = {s["index"]: s for s in slides_c}
            # rules grouped by owner index, in declared order
            owner_rules: dict = {}
            for r in norm_c:
                oi = r.get("owner_slide_index")
                owner_rules.setdefault(oi, []).append(r)
            first_q = min(s["index"] for s in slides_c if s.get("type") == "question")
            visited: List[int] = []
            cur = first_q
            guard = 0
            while cur in by_idx and guard < 50:
                guard += 1
                visited.append(cur)
                if by_idx[cur].get("type") == "capture":
                    break
                nxt = None
                for r in owner_rules.get(cur, []):
                    fld = _norm(r.get("if_field", ""))
                    if answers.get(fld) == r.get("if_value"):
                        tgt = _make_slide_resolver(slides_c)(r.get("then_slide"))
                        if tgt is not None:
                            nxt = tgt["index"]
                            break
                cur = nxt if nxt is not None else cur + 1
            return visited

        branch_slide = {"A": 3, "B": 4, "C": 5}
        capture_idx = next(s["index"] for s in slides_c if s.get("type") == "capture")
        for choice, own in branch_slide.items():
            path = _simulate(choice)
            siblings = [v for k, v in branch_slide.items() if k != choice]
            if own not in path:
                errors.append(f"convergence sim[{choice}]: chosen branch P{own} not visited")
            if any(sib in path for sib in siblings):
                errors.append(
                    f"convergence sim[{choice}]: visited a sibling branch {path!r}")
            if 6 not in path:  # P6 - Shared (converge)
                errors.append(f"convergence sim[{choice}]: never reached shared slide")
            if capture_idx not in path:
                errors.append(
                    f"convergence sim[{choice}]: never reached capture — cannot submit")

        # 22. Backward compat: the SAME survey without converge_slide derives NO
        #     convergence jumps (byte-identical to pre-Area-5.1 behaviour).
        conv_task_nc = dict(conv_task)
        conv_task_nc.pop("converge_slide")
        plan_nc = _build_survey_plan(conv_task_nc, _resolve_fields(conv_task_nc))
        if len(plan_nc.get("conditional_logic", [])) != 3:
            errors.append(
                "backward-compat: no converge_slide must yield only the 3 router rules, "
                f"got {len(plan_nc.get('conditional_logic', []))}")
        if any(r.get("kind") == "converge" for r in plan_nc.get("conditional_logic", [])):
            errors.append("backward-compat: no converge_slide must derive no convergence")

        # 23. Dangling converge_slide → preflight P4:topology_valid HARD STOP.
        pf_conv = _run_preflight(dict(conv_task, converge_slide="No Such Slide"), tmp)
        if pf_conv["pass"]:
            errors.append("dangling converge_slide must fail preflight (topology)")

        # 24. Fall-through guard fires when a non-adjacent branch has NO jump:
        #     validate the router-only rule set against a converge target and
        #     confirm the guard reports the unsubmittable branch(es).
        topo_ft = _validate_topology(conv_task, fields_c, slides_c, list(conv_router))
        if not any("falls through" in e for e in topo_ft):
            errors.append("fall-through guard must flag a branch with no convergence jump")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1

    print("[selftest] PASS — all checks passed (no network / no browser required)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ghl_survey_builder",
        description=(
            "GoHighLevel native survey builder — Skill 06 Workstream B. "
            "GLUE, NOT THE CLICKER: emits browser commands via agent-browser. "
            "Default: --dry-run (write plan + field-map + click list only)."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Write plan + field-map + click list WITHOUT browser execution (default).",
    )
    group.add_argument(
        "--no-dry-run", dest="dry_run", action="store_false",
        help=(
            "Run live browser execution. "
            "Only use after a full end-to-end verified run on a test sub-account."
        ),
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="Run no-network / no-browser self-test and exit.",
    )
    parser.add_argument(
        "--evidence-root", default="/tmp/survey-run-01",
        metavar="DIR",
        help="Evidence root directory for routing/ and shots/ (default: /tmp/survey-run-01).",
    )
    parser.add_argument(
        "--survey-name", default="New Survey",
        help="Survey title (default: 'New Survey').",
    )
    parser.add_argument(
        "--folder-name", default="Sample Survey",
        help="Contact custom-field folder name (default: 'Sample Survey').",
    )
    parser.add_argument(
        "--location-id",
        default=os.environ.get("GHL_LOCATION_ID", ""),
        help="GHL sub-account location ID (or set GHL_LOCATION_ID env var).",
    )
    parser.add_argument(
        "--business-name", default="[BUSINESS NAME]",
        help="Business name to replace [BUSINESS NAME] placeholder in T&C consent copy.",
    )
    parser.add_argument(
        "--campaign", default="our campaign",
        help="Campaign text for T&C consent copy.",
    )
    parser.add_argument(
        "--field-creation", default=DEFAULT_FIELD_CREATION,
        choices=list(FIELD_CREATION_MODES),
        help=(
            "Custom-field posture (F1 grocery-shopping rule). "
            "'api' (default): reuse API-pre-created fields, missing created by "
            "Skill 44. 'map_only': all fields MUST pre-exist (zero creates). "
            "'browser': LEGACY in-browser create (no-PIT fallback ONLY)."
        ),
    )
    parser.add_argument(
        "--task-json", metavar="FILE", default=None,
        help=(
            "Path to a JSON task payload (survey_fields + conditional_logic + "
            "slides + copy_persona + business_name + campaign + welcome_copy…). "
            "Merged OVER the CLI flags — any key the payload defines wins, flags "
            "fill the rest. This is how a task-driven, multi-branch survey is "
            "built from the CLI (Area-5)."
        ),
    )

    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    task: dict = {
        "id": "cli-survey-run",
        "survey_name": args.survey_name,
        "folder_name": args.folder_name,
        "location_id": args.location_id,
        "business_name": args.business_name,
        "campaign": args.campaign,
        "field_creation": args.field_creation,
        "brief": {"source": "cli"},
    }

    # --task-json layers a full task payload OVER the flag-built base (payload
    # keys win; flags supply anything the payload omits). This threads
    # survey_fields + conditional_logic + slides from the CLI (Area-5).
    if args.task_json:
        try:
            with open(args.task_json, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            print(f"--task-json: could not read {args.task_json!r}: {exc}",
                  file=sys.stderr)
            return 2
        if not isinstance(payload, dict):
            print("--task-json must contain a JSON object (task payload)",
                  file=sys.stderr)
            return 2
        task.update(payload)

    result = build_survey(task, args.evidence_root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("location_gate_ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
